import asyncio
import json
import re
from dataclasses import dataclass, replace
from typing import Callable

from ..seams.face import FACES
from .base import CallOptions, Mind, MindUnavailable, options_kwargs

JOB_SYSTEM = "You are {name}'s quick reflexes. Reply with one line of JSON and nothing else."
HOLD_SYSTEM = (
    "You are {name}'s quick reflexes. Someone just said something to {name}, and {name} is still thinking about the answer. "
    "Write the few words {name} says aloud while it thinks: at most five words, no answer, no promise, no numbers, no question back, no quotes. "
    "Reply with only those words."
)
SENSE_SYSTEM = "You are {name}'s quick sense. Pick one option and reply with its letter only."
HOLD_TOKENS = 16
HOLD_TIMEOUT_S = 2.0
SENSE_TIMEOUT_S = 3.0
LETTERS = "ABCDEFGH"
_OBJECT = re.compile(r"\{.*?\}", re.DOTALL)


@dataclass(frozen=True)
class Sensed:
    choice: str
    doubt: float | None
    chances: tuple[tuple[str, float], ...] = ()


def letter_chances(probs, letters: str) -> dict[str, float]:
    if not probs or not probs[0]:
        return {}
    found: dict[str, float] = {}
    for token, chance in probs[0]:
        letter = str(token).strip().strip(").:").upper()
        if letter in letters and len(letter) == 1:
            found[letter] = found.get(letter, 0.0) + max(0.0, float(chance))
    total = sum(found.values())
    return {letter: chance / total for letter, chance in found.items()} if total > 0 else {}


def doubt_of(chances: dict[str, float], options: int) -> float | None:
    if not chances:
        return None
    ranked = sorted(chances.values(), reverse=True) + [0.0] * options
    return max(0.0, min(1.0, 1.0 - (ranked[0] - ranked[1])))


class Subconscious:
    def __init__(self, mind: Mind | None, name: str = "Pebble", timeout_s: float = 10.0, options: Callable[[str], CallOptions | None] | None = None):
        self.mind = mind
        self.name = name
        self.timeout_s = timeout_s
        self.options = options

    @property
    def available(self) -> bool:
        return self.mind is not None

    async def choose(self, job: str, choices: list[str], context: str) -> str | None:
        if self.mind is None or not choices:
            return None
        request = {"job": job, "choices": choices, "context": context[:300], "answer": {"choice": "one of choices"}}
        messages = [
            {"role": "system", "content": JOB_SYSTEM.format(name=self.name)},
            {"role": "user", "content": json.dumps(request)},
        ]
        try:
            options = self.options("job") if self.options is not None else None
            reply = await asyncio.wait_for(self.mind.chat(messages, purpose="job", max_tokens=32, **options_kwargs(options)), self.timeout_s)
        except (MindUnavailable, asyncio.TimeoutError):
            return None
        match = _OBJECT.search(reply.text or "")
        if match is None:
            return None
        try:
            choice = json.loads(match.group(0)).get("choice")
        except (ValueError, AttributeError):
            return None
        return choice if choice in choices else None

    async def hold(self, heard: str, situation: str = "question") -> str | None:
        if self.mind is None or not heard.strip():
            return None
        messages = [
            {"role": "system", "content": HOLD_SYSTEM.format(name=self.name)},
            {"role": "user", "content": f"Just said to {self.name} ({situation}): {heard.strip()[:160]}"},
        ]
        try:
            options = self.options("job") if self.options is not None else None
            reply = await asyncio.wait_for(self.mind.chat(messages, purpose="hold", max_tokens=HOLD_TOKENS, **options_kwargs(options)), HOLD_TIMEOUT_S)
        except (MindUnavailable, asyncio.TimeoutError):
            return None
        lines = [line.strip() for line in (reply.text or "").splitlines() if line.strip()]
        return lines[0].strip("\"'“”‘’ ") if lines else None

    async def ask(self, question: str, options: list[str], context: str = "") -> Sensed | None:
        if self.mind is None or not options or len(options) > len(LETTERS):
            return None
        letters = LETTERS[: len(options)]
        lines = [question.strip()] + [f"{letter}) {option}" for letter, option in zip(letters, options)]
        if context.strip():
            lines.append(f"What is going on: {context.strip()[:300]}")
        messages = [
            {"role": "system", "content": SENSE_SYSTEM.format(name=self.name)},
            {"role": "user", "content": "\n".join(lines)},
        ]
        base = self.options("job") if self.options is not None else None
        options_for = replace(base or CallOptions(kind="steady"), grammar="root ::= " + " | ".join(f'"{letter}"' for letter in letters), probs=len(letters) + 3)
        try:
            reply = await asyncio.wait_for(self.mind.chat(messages, purpose="sense", max_tokens=1, options=options_for), SENSE_TIMEOUT_S)
        except (MindUnavailable, asyncio.TimeoutError):
            return None
        chances = letter_chances(reply.extra.get("probs"), letters)
        said = next((ch for ch in (reply.text or "").strip().upper() if ch in letters), "")
        if not said and chances:
            said = max(chances, key=chances.get)
        if not said:
            return None
        ranked = tuple(sorted(((options[letters.index(letter)], chance) for letter, chance in chances.items()), key=lambda pair: -pair[1]))
        return Sensed(options[letters.index(said)], doubt_of(chances, len(options)), ranked)

    async def pick_expression(self, mood: str, event: str) -> str | None:
        return await self.choose("pick_expression", list(FACES), f"mood: {mood}; just happened: {event}")
