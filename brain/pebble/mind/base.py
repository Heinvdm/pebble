import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import AsyncIterator


class MindUnavailable(RuntimeError):
    pass


class MindInterrupted(MindUnavailable):
    pass


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict
    raw_arguments: str = ""


@dataclass(frozen=True)
class CallOptions:
    kind: str = "steady"
    temperature: float | None = None
    top_p: float | None = None
    min_p: float | None = None
    seed: int | None = None
    grammar: str | None = None
    probs: int = 0

    def sampling(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k not in ("kind", "grammar", "probs") and v is not None}

    def summary(self) -> dict:
        out = {"kind": self.kind, **self.sampling()}
        if self.grammar:
            out["grammar"] = True
        if self.probs:
            out["probs"] = self.probs
        return out


def options_kwargs(options: CallOptions | None) -> dict:
    return {} if options is None else {"options": options}


@dataclass(frozen=True)
class MindReply:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    extra: dict = field(default_factory=dict)


class Mind(ABC):
    name = "mind"

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        purpose: str = "turn",
        max_tokens: int | None = None,
        options: CallOptions | None = None,
    ) -> MindReply: ...

    async def stream(
        self,
        messages: list[dict],
        purpose: str = "turn",
        max_tokens: int | None = None,
        options: CallOptions | None = None,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        reply = await self.chat(messages, tools=tools, purpose=purpose, max_tokens=max_tokens, **options_kwargs(options))
        if reply.text:
            yield reply.text

    async def ready(self) -> bool:
        return True

    async def sees(self) -> bool:
        return False

    def give_way(self) -> int:
        return 0

    async def warm(self, messages: list[dict], tools: list[dict] | None = None, purpose: str = "warm") -> bool:
        return False

    async def close(self) -> None:
        return None


def assistant_message(reply: MindReply) -> dict:
    message = {"role": "assistant", "content": reply.text or ""}
    if reply.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)},
            }
            for call in reply.tool_calls
        ]
    return message


def tool_message(call: ToolCall, result: dict) -> dict:
    return {
        "role": "tool",
        "tool_call_id": call.id,
        "name": call.name,
        "content": json.dumps(result, ensure_ascii=False, default=str),
    }
