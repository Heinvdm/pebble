import asyncio
import logging
import re
import time
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Callable

from ..mind.base import CallOptions, MindInterrupted, MindUnavailable, options_kwargs
from ..mind.budget import GUIDE, SCRIPT, WORDS, Prompt
from .abilities import CARD, GROUP_OF, SHAPE, can_words
from .check import Checked, Ground, read, static, until_at
from .dream import Dreamed, dream

log = logging.getLogger(__name__)

FIXES = 3
DREAM_FIXES = 2
LINES_MOST = 80
WRITE_TOKENS = 1200
WRITE_WAIT_S = 240.0
LANGUAGE = """Pebble script is a small part of Python, checked line by line and run by Pebble's own interpreter.
Allowed: assignment (also d[key] = value, a, b = pair, +=); if, elif, else, while, for over a list, dict or range(), break, continue; def at the top level (plain arguments, return); numbers, text, True, False, None, lists, dicts with text keys, tuples, indexing, slices; + - * / // % **, comparisons, and, or, not, in, is None; f-strings with plain {name} fields only; len, min, max, abs, round, int, float, str, range, sorted (reverse=True), sum, any, all, enumerate, zip; methods: list append, pop, insert, remove, index, count; dict get, keys, values, items; text lower, upper, strip, split, join, startswith, endswith, replace.
Not allowed: import, class, lambda, global, with, try, async, yield, decorators, comprehensions, print, open, eval, exec, getattr, list(), dict(), sets, other built-ins, methods or attributes, names with __.
A function can't change a top-level name: keep(name, value) and kept(name, default) remember things from one event to the next.
Limits: 100,000 steps a run, 50 ms of computing between abilities, text 2,000 characters, lists and dicts 500 items and 4 deep, 256 KB in all, 20 calls deep."""
GUIDE_TEXT = """You write small programs in Pebble script for {name}, a small home robot on two wheels with a face screen, eyes, ears and a voice. Reply with the script only: at most 80 lines, no comments. Every ability goes through {name}'s checks: write plainly and kindly, and never ask for passwords or private details."""
FIX_ASK = "Problems with that script:\n{errors}\nReply with the whole script again, fixed."
DREAM_ASK = "The script passed its check, but when you dreamed it through a day:\n{errors}\nReply with the whole script again, fixed."
SPAN_WORDS = re.compile(r"\bfor (?:the next |a |one |another )?(?:(\d+|a|one|two|three|four|five|six|seven|ten|fourteen|thirty) )?(day|days|week|weeks|fortnight|month)\b|\b(?:this|all) (week|month)\b")
COUNTS = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10, "fourteen": 14, "thirty": 30}
UNIT_S = {"day": 86400.0, "days": 86400.0, "week": 604800.0, "weeks": 604800.0, "fortnight": 1209600.0, "month": 2592000.0}
FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


@dataclass
class Task:
    words: str
    for_name: str | None = None
    for_label: str = ""
    tier: str = "self"
    longest_s: float = 86400.0
    change: str = ""
    previous: str = ""

    @property
    def own(self) -> bool:
        return self.for_name is None


@dataclass
class Written:
    ok: bool = False
    source: str = ""
    checked: Checked | None = None
    dreamed: Dreamed | None = None
    calls: int = 0
    valid_first: bool = False
    valid: bool = False
    dream_passed: bool = False
    seconds: float = 0.0
    errors: list = field(default_factory=list)
    failed: str = ""
    history: list = field(default_factory=list)


def asked_span(words: str) -> float:
    said = " ".join(str(words or "").lower().split())
    longest = 86400.0
    for found in SPAN_WORDS.finditer(said):
        if found.group(3):
            seconds = UNIT_S[found.group(3)]
        else:
            count = found.group(1)
            number = int(count) if count and count.isdigit() else COUNTS.get(count or "a", 1)
            seconds = number * UNIT_S[found.group(2)]
        longest = max(longest, seconds)
    return min(longest, 30 * 86400.0)


def code_of(text: str) -> str:
    found = FENCE.search(text or "")
    body = found.group(1) if found else str(text or "")
    if not found and "```" in body:
        body = body.replace("```python", "").replace("```", "")
    lines = body.replace("\r\n", "\n").split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith(("ABOUT", "USES", "FOR", "UNTIL", "WANTS", "def "))), 0)
    return "\n".join(lines[start:]).strip() + "\n"


def length_errors(source: str) -> list[str]:
    lines = [line for line in source.splitlines() if line.strip()]
    if len(lines) > LINES_MOST:
        return [f"line {LINES_MOST + 1}: a script is at most {LINES_MOST} lines; make it shorter"]
    return []


def readback(name: str, header: dict, called, for_label: str, now: datetime, own: bool = False) -> str:
    about = " ".join(str(header.get("ABOUT") or "").split()).rstrip(".")
    if for_label:
        about = re.sub(rf"\b{re.escape(for_label)}'s\b", "your", about, flags=re.IGNORECASE)
        about = re.sub(rf"\b{re.escape(for_label)}\b", "you", about, flags=re.IGNORECASE)
    if about[:1].isupper() and not about.startswith(("I ", "I'")):
        about = about[:1].lower() + about[1:]
    groups = {GROUP_OF[c] for c in called if c in GROUP_OF}
    can = can_words(groups)
    moving = "do" in groups
    end = until_at(str(header.get("UNTIL") or ""), now, own)
    when = ""
    if isinstance(end, datetime):
        when = _when_words(end, now)
    lead = "I've made a little program for you" if not own else "I've made myself a little program"
    parts = [f"{lead}: it {about}."]
    parts.append(f"{can}; it can't move me." if not moving else f"{can}.")
    if when and when not in about:
        parts.append(f"It ends {when} at the latest.")
    parts.append(f"Say 'stop the {name}' to end it.")
    return " ".join(parts)


def _when_words(end: datetime, now: datetime) -> str:
    hour = end.hour % 12 or 12
    clock = f"{hour}" if end.minute == 0 else f"{hour}:{end.minute:02d}"
    half = "in the morning" if end.hour < 12 else ("in the afternoon" if end.hour < 18 else "tonight" if end.date() == now.date() else "in the evening")
    if end.date() == now.date():
        return f"at {clock} {half}" if half != "tonight" else f"at {clock} tonight"
    if (end.date() - now.date()).days == 1:
        return f"tomorrow at {clock} {half if half != 'tonight' else 'in the evening'}"
    return f"on {end.strftime('%A')} at {clock}"


class Writer:
    def __init__(self, mind_of: Callable[[], object | None], book, name: str = "Pebble", record: Callable[..., None] | None = None, monotonic: Callable[[], float] = time.monotonic, wait_s: float = WRITE_WAIT_S, seed: int | None = None):
        self.mind_of = mind_of
        self.book = book
        self.name = name
        self.record = record or (lambda kind, **data: None)
        self.monotonic = monotonic
        self.wait_s = wait_s
        self.seed = seed

    def ready(self) -> bool:
        try:
            return self.mind_of() is not None
        except Exception:
            return False

    def guide(self) -> str:
        return GUIDE_TEXT.format(name=self.name) + "\n\n" + LANGUAGE + "\n\n" + CARD + "\n\n" + SHAPE

    def task_text(self, task: Task, ground: Ground, now: datetime) -> str:
        people = ", ".join(n.title() for n in ground.people) or "none yet"
        rooms = ", ".join(ground.places) or "none yet"
        sounds = ", ".join(sorted(ground.hearable))
        lines = [f"It is now {now.strftime('%A %H:%M')}. People you know: {people}. Rooms you know: {rooms}. Sounds you can tell apart: {sounds}."]
        if task.own:
            lines.append(f'Your own idea: "{task.words}". Leave FOR out. UNTIL may be "ongoing".')
        else:
            span = f"{round(task.longest_s / 86400.0)} days" if task.longest_s > 86400.0 else "24 hours"
            lines.append(f'{task.for_label or task.for_name.title()} asked: "{task.words}". Write FOR = "{task.for_name}" and use "me" for them in say_to() and ask(). UNTIL: at most {span} from now.')
        if task.change and task.previous:
            lines.append(f'They asked for a change: "{task.change}". The script before the change:\n```python\n{task.previous.strip()}\n```')
        lines.append("Write the script.")
        return "\n".join(lines)

    def messages(self, task: Task, ground: Ground, now: datetime, recipes: list) -> Prompt:
        system = self.guide()
        examples = []
        for name, about, source in recipes:
            examples.append(f"Example, {name}:\n```python\n{source.strip()}\n```")
        known = "Scripts that worked before:\n\n" + "\n\n".join(examples) if examples else ""
        ask = self.task_text(task, ground, now)
        content = (known + "\n\n" + ask) if known else ask
        out = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        parts = [(GUIDE, 0, system), (WORDS, 1, ask)]
        if known:
            parts.append((WORDS, 1, known))
        return Prompt(out, SCRIPT, parts)

    async def _call(self, mind, prompt: Prompt, round_: int):
        seed = None if self.seed is None else self.seed + round_
        options = CallOptions("steady", 0.3, 0.9, 0.1, seed=seed)
        try:
            return await asyncio.wait_for(mind.chat(prompt, purpose="script", max_tokens=WRITE_TOKENS, **options_kwargs(options)), self.wait_s)
        except (MindUnavailable, MindInterrupted, asyncio.TimeoutError) as error:
            log.info("writing a script stopped: %s", error)
            return None

    async def write(self, task: Task, ground: Ground, now: datetime) -> Written:
        out = Written()
        mind = self.mind_of()
        if mind is None:
            out.failed = "no model to write with"
            return out
        start = self.monotonic()
        recipes = self.book.closest(task.words) if self.book is not None else []
        ground = replace(ground, longest_s=max(ground.longest_s, task.longest_s))
        prompt = self.messages(task, ground, now, recipes)
        messages = list(prompt)
        fixes = 0
        dream_fixes = 0
        while True:
            started = self.monotonic()
            answer = await self._call(mind, prompt.like(messages), out.calls)
            out.calls += 1
            if answer is None:
                out.failed = "the model didn't answer"
                break
            reply = answer.text or ""
            source = code_of(reply)
            checked = read(source)
            errors = length_errors(source) + list(checked.errors)
            if not errors:
                errors = static(checked, ground, now)
            out.history.append({"round": out.calls, "errors": list(errors), "prompt_tokens": answer.prompt_tokens, "completion_tokens": answer.completion_tokens, "seconds": round(self.monotonic() - started, 2), "source": source})
            if out.calls == 1:
                out.valid_first = not errors
            if errors:
                out.errors = errors
                if fixes >= FIXES:
                    out.failed = "it still had problems after three fixes"
                    break
                fixes += 1
                messages = list(prompt) + [{"role": "assistant", "content": reply}, {"role": "user", "content": FIX_ASK.format(errors="\n".join(errors[:8]))}]
                continue
            out.valid = True
            out.source = source
            out.checked = checked
            dreamed = await dream(checked, ground, now=now)
            out.dreamed = dreamed
            if dreamed.passed:
                out.dream_passed = True
                out.ok = True
                out.errors = []
                break
            out.errors = dreamed.lines()
            out.history[-1]["dream"] = list(dreamed.failures)
            if dream_fixes >= DREAM_FIXES:
                out.failed = "its dream still went wrong after two fixes"
                break
            dream_fixes += 1
            messages = list(prompt) + [{"role": "assistant", "content": reply}, {"role": "user", "content": DREAM_ASK.format(errors="\n".join(dreamed.failures[:6]))}]
        out.seconds = self.monotonic() - start
        self.record("script_written", ok=out.ok, calls=out.calls, valid_first=out.valid_first, valid=out.valid, dreamed=out.dream_passed, seconds=round(out.seconds, 1), own=task.own)
        return out
