import asyncio
import http.client
import json
import math
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import AsyncIterator, Iterator

from .base import CallOptions, Mind, MindInterrupted, MindReply, MindUnavailable, ToolCall
from .profile import ModelProfile

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
VISION_CHECK_S = 60.0
FOREGROUND = frozenset({"reply", "understand", "look", "talk", "joke", "warm"})
BACKGROUND = frozenset({"turn", "summary", "ready", "sense", "understand_quietly", "rewarm", "picks", "script"})
PUT_OFF = "put off: someone is talking to Pebble"


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def _arguments(raw) -> tuple[dict, str]:
    if isinstance(raw, dict):
        return raw, json.dumps(raw)
    text = raw if isinstance(raw, str) else ""
    try:
        value = json.loads(text) if text.strip() else {}
    except ValueError:
        return {}, text
    return (value if isinstance(value, dict) else {}), text


def _probability(item: dict) -> float | None:
    value = item.get("prob")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    value = item.get("logprob")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.exp(max(-1e4, float(value)))
    return None


def token_probs(choice: dict) -> list[list[tuple[str, float]]]:
    content = (choice.get("logprobs") or {}).get("content") if isinstance(choice.get("logprobs"), dict) else None
    out = []
    for item in content or []:
        if not isinstance(item, dict):
            continue
        tops = item.get("top_probs") or item.get("top_logprobs") or []
        alternatives = []
        for top in tops:
            if isinstance(top, dict):
                chance = _probability(top)
                if chance is not None:
                    alternatives.append((str(top.get("token", "")), chance))
        out.append(alternatives)
    return out


def parse_completion(body: dict) -> MindReply:
    choices = body.get("choices") or [{}]
    message = choices[0].get("message") or {}
    calls = []
    for index, call in enumerate(message.get("tool_calls") or []):
        function = call.get("function") or {}
        arguments, raw = _arguments(function.get("arguments"))
        calls.append(ToolCall(str(call.get("id") or f"call_{index}"), str(function.get("name") or ""), arguments, raw))
    usage = body.get("usage") or {}
    extra = {"finish_reason": choices[0].get("finish_reason")}
    probs = token_probs(choices[0])
    if probs:
        extra["probs"] = probs
    return MindReply(
        text=_content_text(message.get("content")).strip(),
        tool_calls=tuple(calls),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        extra=extra,
    )


def stream_piece(line: str) -> tuple[str | None, bool]:
    text = line.strip()
    if not text.startswith("data:"):
        return None, False
    data = text[5:].strip()
    if data == "[DONE]":
        return None, True
    try:
        body = json.loads(data)
    except ValueError:
        return None, False
    if not isinstance(body, dict):
        return None, False
    if body.get("error"):
        raise MindUnavailable(f"the model server reported an error: {body['error']}")
    choices = body.get("choices") or [{}]
    first = choices[0] if isinstance(choices[0], dict) else {}
    delta = first.get("delta") or {}
    piece = delta.get("content") if isinstance(delta, dict) else None
    if piece is None:
        piece = first.get("text") or body.get("content")
    done = bool(first.get("finish_reason")) or bool(body.get("stop"))
    return (piece if isinstance(piece, str) and piece else None), done


def fold_system(messages: list[dict]) -> list[dict]:
    system = "\n\n".join(m.get("content") or "" for m in messages if m.get("role") == "system")
    rest = [dict(m) for m in messages if m.get("role") != "system"]
    if not system:
        return rest
    for message in rest:
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, list):
                message["content"] = [{"type": "text", "text": system}] + list(content)
            else:
                message["content"] = f"{system}\n\n{content or ''}"
            return rest
    return [{"role": "user", "content": system}] + rest


def _settle(wake) -> None:
    if not wake.done():
        wake.set_result(None)


def _forget(future) -> None:
    if not future.cancelled():
        future.exception()


class LlamaServerMind(Mind):
    def __init__(self, profile: ModelProfile):
        self.profile = profile
        self.name = f"llama:{profile.name}"
        self.base = profile.endpoint.rstrip("/")
        self._vision: tuple[float, bool] | None = None
        self._background: list[dict] = []
        self._lock = threading.Lock()

    def _get(self, path: str, timeout: float) -> tuple[int, dict]:
        request = urllib.request.Request(self.base + path, method="GET")
        try:
            with _OPENER.open(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return response.status, json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as error:
            return error.code, {}
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise MindUnavailable(str(error)) from error

    def _post(self, path: str, payload: dict, timeout: float, holder: dict | None = None) -> dict:
        holder = {} if holder is None else holder
        data = json.dumps(payload).encode("utf-8")
        parts = urllib.parse.urlsplit(self.base)
        connection = http.client.HTTPConnection(parts.hostname or "127.0.0.1", parts.port or 80, timeout=timeout)
        holder["connection"] = connection
        try:
            if holder.get("interrupted"):
                raise MindInterrupted(PUT_OFF)
            connection.request("POST", parts.path.rstrip("/") + path, body=data, headers={"Content-Type": "application/json"})
            if holder.get("interrupted"):
                raise MindInterrupted(PUT_OFF)
            response = connection.getresponse()
            status = response.status
            raw = response.read()
        except (OSError, http.client.HTTPException) as error:
            if holder.get("interrupted"):
                raise MindInterrupted(PUT_OFF) from error
            raise MindUnavailable(str(error) or type(error).__name__) from error
        finally:
            connection.close()
        if holder.get("interrupted"):
            raise MindInterrupted(PUT_OFF)
        if status >= 400:
            raise MindUnavailable(f"HTTP {status} from {self.base}{path}")
        try:
            body = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError as error:
            raise MindUnavailable(str(error)) from error
        if not isinstance(body, dict):
            raise MindUnavailable("the model server sent something that is not a JSON object")
        return body

    def give_way(self) -> int:
        return self.interrupt_background()

    async def warm(self, messages, tools=None, purpose="warm") -> bool:
        try:
            await self.chat(messages, tools=tools, purpose=purpose, max_tokens=1)
        except MindUnavailable:
            return False
        return True

    def interrupt_background(self) -> int:
        with self._lock:
            waiting = list(self._background)
        for holder in waiting:
            holder["interrupted"] = True
            sock = getattr(holder.get("connection"), "sock", None)
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            wake = holder.get("wake")
            if wake is not None:
                wake.get_loop().call_soon_threadsafe(_settle, wake)
        return len(waiting)

    def payload(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        max_tokens: int | None,
        options: CallOptions | None = None,
        stream: bool = False,
    ) -> dict:
        body = {
            "messages": messages if self.profile.system_role else fold_system(messages),
            "max_tokens": max_tokens or self.profile.max_reply_tokens,
            "temperature": self.profile.temperature,
            "stream": stream,
        }
        if self.profile.model:
            body["model"] = self.profile.model
        if tools and self.profile.tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        body.update(self.profile.extra_body)
        if options is not None:
            body.update(options.sampling())
            if options.grammar and not body.get("tools"):
                body["grammar"] = options.grammar
            if options.probs and not stream:
                body["logprobs"] = True
                body["top_logprobs"] = int(options.probs)
        return body

    def _stream_lines(self, payload: dict, timeout: float, holder: dict, stop: threading.Event) -> Iterator[str]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + "/v1/chat/completions",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        )
        try:
            with _OPENER.open(request, timeout=timeout) as response:
                holder["response"] = response
                for raw in response:
                    if stop.is_set():
                        return
                    piece, done = stream_piece(raw.decode("utf-8", errors="replace"))
                    if piece:
                        yield piece
                    if done:
                        return
        except urllib.error.HTTPError as error:
            raise MindUnavailable(f"HTTP {error.code} from {self.base}/v1/chat/completions") from error
        except (urllib.error.URLError, OSError, ValueError) as error:
            if stop.is_set():
                return
            raise MindUnavailable(str(error)) from error

    async def ready(self) -> bool:
        try:
            status, body = await asyncio.to_thread(self._get, "/health", 5.0)
        except MindUnavailable:
            return False
        ok = status == 200 and isinstance(body, dict) and body.get("status") == "ok"
        if ok:
            await self._props()
        return ok

    async def _props(self) -> bool:
        try:
            status, body = await asyncio.to_thread(self._get, "/props", 5.0)
        except MindUnavailable:
            status, body = 0, {}
        if status != 200 or not isinstance(body, dict):
            body = {}
        settings = body.get("default_generation_settings")
        context = settings.get("n_ctx") if isinstance(settings, dict) else None
        if isinstance(context, int) and not isinstance(context, bool) and context > 0:
            self.profile.served["context"] = context
        modalities = body.get("modalities")
        vision = isinstance(modalities, dict) and modalities.get("vision") is True
        self._vision = (time.monotonic(), vision)
        return vision

    async def sees(self) -> bool:
        if self._vision is not None and time.monotonic() - self._vision[0] < VISION_CHECK_S:
            return self._vision[1]
        return await self._props()

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None) -> MindReply:
        if purpose in FOREGROUND:
            self.interrupt_background()
        holder: dict = {}
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, self._post, "/v1/chat/completions", self.payload(messages, tools, max_tokens, options), self.profile.timeout_s, holder)
        if purpose in BACKGROUND:
            wake = loop.create_future()
            holder["wake"] = wake
            with self._lock:
                self._background.append(holder)
            try:
                await asyncio.wait({future, wake}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                with self._lock:
                    self._background = [h for h in self._background if h is not holder]
                if not wake.done():
                    wake.cancel()
            if not future.done():
                future.add_done_callback(_forget)
                raise MindInterrupted(PUT_OFF)
        return parse_completion(await future)

    async def stream(self, messages, purpose="turn", max_tokens=None, options=None, tools=None) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        stop = threading.Event()
        holder: dict = {}
        payload = self.payload(messages, tools, max_tokens, options, stream=True)
        if purpose in FOREGROUND:
            self.interrupt_background()

        def send(kind: str, value) -> None:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, (kind, value))
            except RuntimeError:
                stop.set()

        def pump() -> None:
            try:
                for piece in self._stream_lines(payload, self.profile.timeout_s, holder, stop):
                    send("piece", piece)
                send("done", None)
            except MindUnavailable as error:
                send("error", error)
            except Exception as error:
                send("error", MindUnavailable(str(error)))

        worker = threading.Thread(target=pump, name="pebble-llama-stream", daemon=True)
        worker.start()
        try:
            while True:
                kind, value = await queue.get()
                if kind == "piece":
                    yield value
                elif kind == "error":
                    raise value
                else:
                    return
        finally:
            stop.set()
            response = holder.get("response")
            if response is not None and worker.is_alive():
                try:
                    response.close()
                except Exception:
                    pass
