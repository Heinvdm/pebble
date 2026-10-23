import asyncio
import hashlib
import json
import logging
import math
import time
import urllib.error
import urllib.request
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

from ..clock import iso
from ..laws import laws_text
from .base import Mind, MindReply, MindUnavailable, options_kwargs
from .tokens import CHARS_PER_TOKEN, MESSAGE_OVERHEAD

log = logging.getLogger(__name__)

BUDGET_LOG = "logs/budget.jsonl"
PIXEL_WINDOW = 8192
TALK_SHARE = 0.6
KEEP_SHARE = 0.5
SMALL_WINDOW_SHARE = 0.3
ROOM_FLOOR = 48
ESTIMATE_MARGIN = 1.05
CALIBRATE_AFTER = 400
DOWN_S = 60.0
CACHE_LIMIT = 4096
TOKENIZE_TIMEOUT_S = 2.0

REPLY, TURN, READER, JOB, NIGHT, SCRIPT, TEACH = "reply", "turn", "reader", "job", "night", "script", "teach"
KINDS = (REPLY, TURN, READER, JOB, NIGHT, SCRIPT, TEACH)
BACKGROUND = frozenset({NIGHT, SCRIPT, TEACH})
PURPOSES = {"reply": REPLY, "turn": TURN, "understand": READER, "understand_quietly": READER, "summary": NIGHT, "script": SCRIPT, "teach": TEACH}

LAWS, CORE, GUIDE, EXAMPLES, TOOLS = "laws", "core", "guide", "examples", "tools"
SELF, NOTES, HOUSEHOLD = "self", "notes", "household"
HISTORY, WORK = "history", "work"
PEOPLE, TASK, BOARD, MATCHED, WORDS, ROOM = "people", "task", "board", "matched", "words", "room"
ROWS = {LAWS: CORE, GUIDE: CORE, EXAMPLES: CORE}
KEPT = frozenset({LAWS, CORE, GUIDE, EXAMPLES, TOOLS, WORDS, WORK})
TRIM_ORDER = (MATCHED, PEOPLE, BOARD, TASK, HOUSEHOLD, NOTES, SELF)
SPILL_ORDER = (MATCHED, BOARD, PEOPLE, TASK, HOUSEHOLD, NOTES, SELF)
SECTION_ORDER = (LAWS, CORE, GUIDE, EXAMPLES, TOOLS, SELF, NOTES, HOUSEHOLD, HISTORY, PEOPLE, TASK, BOARD, MATCHED, WORDS, WORK, ROOM)

TABLE = {
    REPLY: {CORE: 900, TOOLS: 0, SELF: 350, NOTES: 300, HOUSEHOLD: 60, PEOPLE: 250, TASK: 200, BOARD: 60, MATCHED: 150, WORDS: 200, ROOM: 250},
    TURN: {CORE: 900, TOOLS: 1200, SELF: 350, NOTES: 300, HOUSEHOLD: 60, PEOPLE: 250, TASK: 200, BOARD: 60, MATCHED: 300, WORDS: 300, ROOM: 400},
    READER: {CORE: 700, PEOPLE: 40, TASK: 60, MATCHED: 150, WORDS: 100, ROOM: 200},
    JOB: {CORE: 1200, WORDS: 2000, ROOM: 400},
    NIGHT: {CORE: 1200, ROOM: 600},
    SCRIPT: {CORE: 1200, ROOM: 1200},
    TEACH: {CORE: 1200, ROOM: 600},
}
PEOPLE_HEAD = "People here now:"
ALSO_HERE = "Also here: "
BOARD_LEADS = ("Things on your mind (", "You thought back (")
LAWS_TEXT = laws_text()
SAID_FINE = "prompts stayed in budget"
SAID_TRIMMED = "prompts went over budget {count} {times} and were trimmed ({what})"
SAID_REFUSED = "{count} {calls} would not have fitted the window and were not sent"
SAID_FOLDED = "the history was folded {count} {times} in quiet moments"
SAID_REPLY_TRIMS = "the reply path had to trim the history {count} {times}"
FOLD, REPLY_TRIM = "fold", "reply_trim"


def row(section: str) -> str:
    return ROWS.get(section, section)


def kind_of(purpose: str) -> str:
    return PURPOSES.get(purpose, JOB)


def ceiling(kind: str, window: int) -> int:
    if kind in BACKGROUND:
        return window
    return min(window, max(PIXEL_WINDOW, int(window * TALK_SHARE)))


def budgets(kind: str, window: int) -> dict:
    table = dict(TABLE.get(kind, TABLE[JOB]))
    top = ceiling(kind, window)
    if kind in (REPLY, TURN):
        table[HISTORY] = max(0, top - sum(table.values()))
    if kind == TURN:
        table[WORK] = max(0, window - top)
    if kind in BACKGROUND:
        table[WORDS] = max(0, window - sum(table.values()))
    return table


def compaction(window: int) -> tuple[int, int]:
    table = budgets(TURN, window)
    compact = max(1, ceiling(TURN, window) - table[TOOLS] - table[ROOM])
    keep = max(1, min(compact - 1, int(max(table[HISTORY], compact * SMALL_WINDOW_SHARE) * KEEP_SHARE)))
    return compact, keep


def note_event(store, clock, event: str, **data) -> dict | None:
    if store is None or clock is None:
        return None
    now = clock.now()
    out = {"at": iso(now), "day": clock.local(now).date().isoformat(), "event": event}
    out.update({key: value for key, value in data.items() if value is not None})
    try:
        store.append(BUDGET_LOG, out)
    except Exception:
        log.exception("could not write a history event to the prompt log")
        return None
    return out


def message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, list):
        text = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    else:
        text = content or ""
    if message.get("tool_calls"):
        text += json.dumps(message["tool_calls"], ensure_ascii=False)
    return text


class Prompt(list):
    def __init__(self, messages=(), kind: str = JOB, parts=(), spans=()):
        super().__init__(messages)
        self.kind = kind
        self.parts = tuple((section, index, text) for section, index, text in parts if text)
        self.spans = tuple((section, start, end) for section, start, end in spans if end > start)

    def like(self, messages) -> "Prompt":
        return Prompt(messages, self.kind, self.parts, self.spans)

    def ahead(self, message: dict) -> "Prompt":
        parts = [(s, i + 1, t) for s, i, t in self.parts]
        spans = [(s, a + 1, b + 1) for s, a, b in self.spans]
        return Prompt([message] + list(self), self.kind, parts, spans)

    def span(self, section: str) -> tuple[int, int] | None:
        for name, start, end in self.spans:
            if name == section:
                return start, end
        return None

    def replaced(self, index: int, old: str, new: str) -> "Prompt":
        messages = list(self)
        message = dict(messages[index])
        message["content"] = (message.get("content") or "").replace(old, new, 1)
        messages[index] = message
        parts = []
        for section, at, text in self.parts:
            if at == index and text == old:
                text = new
            parts.append((section, at, text))
        return Prompt(messages, self.kind, parts, self.spans)

    def dropped(self, start: int, count: int) -> "Prompt":
        if count <= 0:
            return self
        end = start + count
        messages = list(self[:start]) + list(self[end:])
        parts = [(s, i if i < start else i - count, t) for s, i, t in self.parts if not start <= i < end]
        spans = []
        for section, a, b in self.spans:
            a = a if a < start else max(start, a - count)
            b = b if b <= start else max(start, b - count)
            spans.append((section, a, b))
        return Prompt(messages, self.kind, parts, spans)


@dataclass(frozen=True)
class Piece:
    section: str
    index: int
    text: str
    overhead: int = 0


def pieces(prompt: Prompt, tools: list[dict] | None) -> list[Piece]:
    home = CORE if prompt.kind in (REPLY, TURN) else GUIDE
    out = []
    spans = [(section, start, end) for section, start, end in prompt.spans]
    for index, message in enumerate(prompt):
        section = next((name for name, start, end in spans if start <= index < end), None)
        if section is not None:
            out.append(Piece(section, index, message_text(message), MESSAGE_OVERHEAD))
            continue
        text = message_text(message)
        if message.get("role") == "system" and LAWS_TEXT in text:
            out.append(Piece(LAWS, index, LAWS_TEXT))
            text = text.replace(LAWS_TEXT, "", 1)
        for name, at, part in prompt.parts:
            if at == index and part and part in text:
                out.append(Piece(name, index, part))
                text = text.replace(part, "", 1)
        default = home if message.get("role") == "system" else WORDS
        out.append(Piece(default, index, text, MESSAGE_OVERHEAD))
    if tools:
        out.append(Piece(TOOLS, -1, json.dumps(tools, ensure_ascii=False, sort_keys=True)))
    return out


def sized(found: list[Piece], counter: "Counter", room: int) -> tuple[dict, set]:
    sizes: dict = {}
    estimated: set = set()
    for piece in found:
        if piece.section == TOOLS:
            count = counter.known(piece.text)
            real = count is not None
            if not real:
                count = counter.estimate(piece.text)
        else:
            count, real = counter.quick(piece.text)
        if not real:
            estimated.add(piece.section)
        sizes[piece.section] = sizes.get(piece.section, 0) + count + piece.overhead
    sizes[ROOM] = room
    return sizes, estimated


def _key(text: str) -> bytes:
    return hashlib.blake2b(text.encode("utf-8", errors="replace"), digest_size=12).digest()


class Counter:
    def __init__(self, endpoint: str | None = None, chars_per_token: float = CHARS_PER_TOKEN, timeout_s: float = TOKENIZE_TIMEOUT_S, monotonic: Callable[[], float] = time.monotonic):
        self.base = endpoint.rstrip("/") if endpoint else None
        self.default_ratio = float(chars_per_token) or CHARS_PER_TOKEN
        self.timeout_s = timeout_s
        self.monotonic = monotonic
        self.cache: dict[bytes, int] = {}
        self.chars = 0
        self.tokens = 0
        self.down_until = -math.inf
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @property
    def live(self) -> bool:
        return self.base is not None and self.monotonic() >= self.down_until

    @property
    def ratio(self) -> float:
        if self.tokens >= CALIBRATE_AFTER and self.chars > 0:
            return self.chars / self.tokens
        return self.default_ratio

    def estimate(self, text: str) -> int:
        if not text:
            return 0
        return math.ceil(len(text) / self.ratio * ESTIMATE_MARGIN)

    def known(self, text: str) -> int | None:
        if not text:
            return 0
        return self.cache.get(_key(text))

    def quick(self, text: str) -> tuple[int, bool]:
        found = self.known(text)
        if found is not None:
            return found, True
        return self.estimate(text), False

    def _remember(self, key: bytes, text: str, count: int) -> None:
        if len(self.cache) >= CACHE_LIMIT:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = count
        self.chars += len(text)
        self.tokens += count

    def post(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(self.base + path, data=json.dumps(payload).encode("utf-8"), method="POST", headers={"Content-Type": "application/json"})
        with self._opener.open(request, timeout=self.timeout_s) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))

    def real(self, text: str) -> int | None:
        if not text:
            return 0
        key = _key(text)
        if key in self.cache:
            return self.cache[key]
        if not self.live:
            return None
        try:
            tokens = self.post("/tokenize", {"content": text}).get("tokens")
        except (urllib.error.URLError, OSError, ValueError, AttributeError):
            self.down_until = self.monotonic() + DOWN_S
            return None
        if not isinstance(tokens, list):
            self.down_until = self.monotonic() + DOWN_S
            return None
        self._remember(key, text, len(tokens))
        return len(tokens)

    def rendered(self, tools: list[dict]) -> int | None:
        text = json.dumps(tools, ensure_ascii=False, sort_keys=True)
        key = _key(text)
        if key in self.cache:
            return self.cache[key]
        if not self.live:
            return None
        bare = [{"role": "user", "content": "."}]
        try:
            with_tools = self.post("/apply-template", {"messages": bare, "tools": tools}).get("prompt")
            without = self.post("/apply-template", {"messages": bare}).get("prompt")
            if not isinstance(with_tools, str) or not isinstance(without, str):
                return None
            extra = len(self.post("/tokenize", {"content": with_tools}).get("tokens") or []) - len(self.post("/tokenize", {"content": without}).get("tokens") or [])
        except (urllib.error.URLError, OSError, ValueError, AttributeError):
            self.down_until = self.monotonic() + DOWN_S
            return None
        if len(self.cache) >= CACHE_LIMIT:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = max(0, extra)
        return self.cache[key]

    def settle(self, found: list[Piece]) -> None:
        for piece in found:
            if piece.section == TOOLS:
                continue
            if self.known(piece.text) is None and self.real(piece.text) is None:
                return


@dataclass
class Fit:
    kind: str
    purpose: str
    window: int
    messages: list
    room: int
    room_asked: int | None
    found: list = field(default_factory=list)
    sizes: dict = field(default_factory=dict)
    estimated: set = field(default_factory=set)
    trimmed: dict = field(default_factory=dict)
    over: list = field(default_factory=list)
    refused: bool = False

    @property
    def total(self) -> int:
        return sum(self.sizes.values())


class Guard:
    def __init__(self, counter: Counter, window: Callable[[], int], room: int = 200):
        self.counter = counter
        self.window = window
        self.room = room

    def measure(self, prompt: Prompt, tools: list[dict] | None, room: int) -> tuple[list[Piece], dict, set]:
        found = pieces(prompt, tools)
        sizes, estimated = sized(found, self.counter, room)
        return found, sizes, estimated

    def shorten(self, prompt: Prompt, section: str, limit: int, tools, room: int) -> Prompt:
        for _ in range(200):
            found, sizes, _ = self.measure(prompt, tools, room)
            if sizes.get(section, 0) <= limit:
                return prompt
            owned = [p for p in found if p.section == section and p.overhead == 0 and p.text]
            if not owned:
                return prompt
            piece = owned[-1]
            smaller = cut(section, piece.text)
            if smaller == piece.text:
                if len(owned) == 1:
                    return prompt
                smaller = ""
            prompt = prompt.replaced(piece.index, piece.text, smaller)
        return prompt

    def drop_oldest(self, prompt: Prompt) -> Prompt | None:
        span = prompt.span(HISTORY)
        if span is None:
            return None
        start, end = span
        if end <= start:
            return None
        count = 1
        while start + count < end and prompt[start + count].get("role") != "user":
            count += 1
        return prompt.dropped(start, count)

    def fit(self, messages: list, tools: list[dict] | None, purpose: str, max_tokens: int | None) -> Fit:
        prompt = messages if isinstance(messages, Prompt) else Prompt(messages, kind_of(purpose))
        kind = prompt.kind
        window = int(self.window())
        table = budgets(kind, window)
        room = int(max_tokens or self.room)
        result = Fit(kind, purpose, window, prompt, room, max_tokens)
        _, sizes, _ = self.measure(prompt, tools, room)
        for section in TRIM_ORDER:
            limit = table.get(section)
            if limit is None or sizes.get(section, 0) <= limit:
                continue
            before = sizes[section]
            prompt = self.shorten(prompt, section, limit, tools, room)
            _, sizes, _ = self.measure(prompt, tools, room)
            result.trimmed[section] = [before, sizes.get(section, 0)]
        top = ceiling(kind, window)
        prompt, sizes = self._spill(prompt, tools, room, top, sizes, result, history_only=True)
        prompt, sizes = self._spill(prompt, tools, room, window, sizes, result, history_only=False)
        total = sum(sizes.values())
        if total > window:
            room = max(ROOM_FLOOR, room - (total - window))
            sizes[ROOM] = room
        found, sizes, estimated = self.measure(prompt, tools, room)
        result.messages, result.room, result.found, result.sizes, result.estimated = prompt, room, found, sizes, estimated
        merged: dict = {}
        for section, count in sizes.items():
            merged[row(section)] = merged.get(row(section), 0) + count
        result.over = sorted(name for name, count in merged.items() if name not in (HISTORY, ROOM) and name in table and count > table[name])
        result.refused = sum(sizes.values()) > window
        return result

    def _spill(self, prompt: Prompt, tools, room: int, limit: int, sizes: dict, result: Fit, history_only: bool) -> tuple[Prompt, dict]:
        def counted(found_sizes: dict) -> int:
            if history_only:
                return sum(v for k, v in found_sizes.items() if k != WORK)
            return sum(found_sizes.values())

        if counted(sizes) <= limit:
            return prompt, sizes
        before = sizes.get(HISTORY, 0)
        while counted(sizes) > limit:
            smaller = self.drop_oldest(prompt)
            if smaller is None or smaller is prompt:
                break
            prompt = smaller
            _, sizes, _ = self.measure(prompt, tools, room)
        if sizes.get(HISTORY, 0) < before:
            old = result.trimmed.get(HISTORY, [before, 0])[0]
            result.trimmed[HISTORY] = [old, sizes.get(HISTORY, 0)]
        if history_only:
            return prompt, sizes
        for section in SPILL_ORDER:
            excess = counted(sizes) - limit
            if excess <= 0:
                break
            have = sizes.get(section, 0)
            if have <= 0:
                continue
            prompt = self.shorten(prompt, section, max(0, have - excess), tools, room)
            _, sizes, _ = self.measure(prompt, tools, room)
            if sizes.get(section, 0) < have:
                old = result.trimmed.get(section, [have, 0])[0]
                result.trimmed[section] = [old, sizes.get(section, 0)]
        return prompt, sizes


def _items(text: str) -> tuple[str, list[str], str, str]:
    if "\n" in text.strip():
        return "", text.split("\n"), "\n", ""
    for lead in BOARD_LEADS:
        if text.startswith(lead):
            body = text[len(lead):]
            return lead, body.split(" / "), " / ", ""
    if ": " in text and ", " in text:
        lead, body = text.split(": ", 1)
        end = "." if body.endswith(".") else ""
        body = body[:-1] if end else body
        return lead + ": ", body.split(", "), ", ", end
    return "", text.split(" "), " ", ""


def _people(text: str) -> str:
    lines = text.split("\n")
    described = [n for n, line in enumerate(lines) if line.startswith("- ") and not line.startswith("- someone you have not met")]
    if not described:
        return text
    last = described[-1]
    name = lines[last][2:].split(";", 1)[0].split(" (", 1)[0].strip()
    also = next((n for n, line in enumerate(lines) if line.startswith(ALSO_HERE)), None)
    rest = lines[:last] + lines[last + 1:]
    if also is None:
        head = 1 if rest and rest[0].startswith(PEOPLE_HEAD) else 0
        rest.insert(head, f"{ALSO_HERE}{name}.")
    else:
        index = also if also < last else also - 1
        names = rest[index][len(ALSO_HERE):].rstrip(".")
        rest[index] = f"{ALSO_HERE}{name}, {names}."
    return "\n".join(rest)


def cut(section: str, text: str) -> str:
    if section == PEOPLE and text.startswith(PEOPLE_HEAD):
        return _people(text)
    lead, items, joiner, end = _items(text)
    if section == TASK:
        if joiner != "\n" or len(items) <= 1:
            return text
        return "\n".join(items[:-1])
    if len(items) <= 1:
        return ""
    kept = joiner.join(items[:-1]).rstrip()
    return f"{lead}{kept}{end}" if kept else ""


class Meter:
    def __init__(self, store, clock, counter: Counter):
        self.store = store
        self.clock = clock
        self.counter = counter
        self.tasks: set = set()

    def note(self, fit: Fit, server: int | None = None) -> None:
        if fit.estimated and self.counter.live:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self._write(fit, server)
                return
            task = loop.create_task(self._settle_and_write(fit, server))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            return
        self._write(fit, server)

    async def _settle_and_write(self, fit: Fit, server: int | None) -> None:
        try:
            await asyncio.to_thread(self.counter.settle, fit.found)
        except Exception:
            log.exception("could not count a prompt with the real tokenizer")
        self._write(fit, server)

    def _sizes(self, fit: Fit) -> tuple[dict, list]:
        sizes, estimated = sized(fit.found, self.counter, fit.room)
        return sizes, sorted(estimated)

    def record(self, fit: Fit, server: int | None = None) -> dict:
        sizes, estimated = self._sizes(fit)
        now = self.clock.now()
        out = {
            "at": iso(now),
            "day": self.clock.local(now).date().isoformat(),
            "kind": fit.kind,
            "purpose": fit.purpose,
            "window": fit.window,
            "sizes": {name: sizes[name] for name in SECTION_ORDER if sizes.get(name)},
            "total": sum(sizes.values()),
            "counted": "estimate" if estimated else "tokenizer",
        }
        if estimated:
            out["estimated"] = estimated
        if server is not None:
            out["server"] = int(server)
        if fit.trimmed:
            out["trimmed"] = {name: list(pair) for name, pair in fit.trimmed.items()}
        if fit.over:
            out["over"] = list(fit.over)
        if fit.refused:
            out["refused"] = True
        return out

    def _write(self, fit: Fit, server: int | None) -> None:
        if self.store is None:
            return
        try:
            self.store.append(BUDGET_LOG, self.record(fit, server))
        except Exception:
            log.exception("could not write the prompt sizes")

    async def settle(self) -> None:
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    def day_line(self, day: str) -> str:
        lines = [r for r in self.store.read_lines(BUDGET_LOG) if isinstance(r, dict) and r.get("day") == day]
        records = [r for r in lines if "sizes" in r]
        if not records:
            return ""
        folds = sum(1 for r in lines if r.get("event") == FOLD and r.get("where") != REPLY_TRIM)
        reply_trims = sum(1 for r in lines if r.get("event") == REPLY_TRIM)
        trims: dict = {}
        refused = 0
        biggest = None
        for record in records:
            window = int(record.get("window") or PIXEL_WINDOW)
            table = budgets(record.get("kind") or JOB, window)
            for name in record.get("trimmed") or {}:
                trims[name] = trims.get(name, 0) + 1
            refused += 1 if record.get("refused") else 0
            for name, used in (record.get("sizes") or {}).items():
                limit = table.get(name)
                if name in KEPT or name in (HISTORY, ROOM) or not limit:
                    continue
                share = used / limit
                if biggest is None or share > biggest[0]:
                    biggest = (share, name, used, limit)
        count = sum(trims.values())
        if count:
            what = ", ".join(f"{name} {n}" for name, n in sorted(trims.items(), key=lambda item: -item[1]))
            line = SAID_TRIMMED.format(count=count, times="time" if count == 1 else "times", what=what)
        else:
            line = SAID_FINE
        if refused:
            line += "; " + SAID_REFUSED.format(count=refused, calls="call" if refused == 1 else "calls")
        if biggest is not None:
            line += f"; the biggest was the {biggest[1]} section at {biggest[2]} of {biggest[3]}"
        if folds:
            line += "; " + SAID_FOLDED.format(count=folds, times="time" if folds == 1 else "times")
        if reply_trims:
            line += "; " + SAID_REPLY_TRIMS.format(count=reply_trims, times="time" if reply_trims == 1 else "times")
        return f"{len(records)} model calls; {line}."

    def write_day(self, day: str) -> str:
        line = self.day_line(day)
        if line and self.store is not None:
            self.store.append(BUDGET_LOG, {"at": iso(self.clock.now()), "day": day, "line": line})
        return line


class GuardedMind(Mind):
    def __init__(self, inner: Mind, guard: Guard, meter: Meter | None = None):
        self.inner = inner
        self.guard = guard
        self.meter = meter
        self.name = inner.name

    def _fit(self, messages, tools, purpose, max_tokens) -> Fit:
        fit = self.guard.fit(messages, tools, purpose, max_tokens)
        if fit.refused:
            if self.meter is not None:
                self.meter.note(fit)
            raise MindUnavailable("the prompt would not fit in the model's window")
        return fit

    def _room(self, fit: Fit) -> int | None:
        if fit.room_asked is None and fit.room == self.guard.room:
            return None
        return fit.room

    def _metered(self, fit: Fit, server: int | None = None) -> None:
        if self.meter is not None:
            self.meter.note(fit, server)

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None) -> MindReply:
        fit = self._fit(messages, tools, purpose, max_tokens)
        reply = await self.inner.chat(list(fit.messages), tools=tools, purpose=purpose, max_tokens=self._room(fit), **options_kwargs(options))
        self._metered(fit, reply.prompt_tokens)
        return reply

    async def stream(self, messages, purpose="turn", max_tokens=None, options=None, tools=None) -> AsyncIterator[str]:
        fit = self._fit(messages, tools, purpose, max_tokens)
        extra = {"tools": tools} if tools else {}
        try:
            async with aclosing(self.inner.stream(list(fit.messages), purpose=purpose, max_tokens=self._room(fit), options=options, **extra)) as pieces_out:
                async for piece in pieces_out:
                    yield piece
        finally:
            self._metered(fit)

    async def warm(self, messages, tools=None, purpose="warm") -> bool:
        fit = self.guard.fit(messages, tools, purpose, None)
        counter = self.guard.counter
        if fit.trimmed and fit.estimated and counter.live:
            prompt = messages if isinstance(messages, Prompt) else Prompt(messages, kind_of(purpose))
            try:
                await asyncio.to_thread(counter.settle, pieces(prompt, tools))
            except Exception:
                log.exception("could not count a prompt before reading it ahead")
            fit = self.guard.fit(messages, tools, purpose, None)
        if fit.refused:
            return False
        warmed = await self.inner.warm(list(fit.messages), tools=tools, purpose=purpose)
        self._metered(fit)
        return warmed

    async def ready(self) -> bool:
        return await self.inner.ready()

    async def sees(self) -> bool:
        return await self.inner.sees()

    def give_way(self) -> int:
        return self.inner.give_way()

    async def close(self) -> None:
        if self.meter is not None:
            await self.meter.settle()
        await self.inner.close()


def guarded(inner: Mind, profile, store=None, clock=None, endpoint: str | None = None) -> GuardedMind:
    counter = Counter(endpoint, profile.chars_per_token)
    guard = Guard(counter, profile.window, profile.max_reply_tokens)
    meter = Meter(store, clock, counter) if store is not None and clock is not None else None
    return GuardedMind(inner, guard, meter)


def meter_of(mind) -> Meter | None:
    seen = 0
    while mind is not None and seen < 8:
        if isinstance(mind, GuardedMind):
            return mind.meter
        mind = getattr(mind, "inner", None)
        seen += 1
    return None
