import asyncio
import re
from contextlib import aclosing
from dataclasses import dataclass
from typing import Awaitable, Callable

from ..conversation.mouth import sentences
from .base import CallOptions, Mind, MindUnavailable, options_kwargs

MAX_TOKENS = 70
TIMEOUT_S = 20.0
MAX_CHARS = 240
NUMBER = re.compile(r"\d+(?:[.,:]\d+)?")
QUOTES = "\"'“”‘’ "
ASKS = {
    "talk": "Say this in your own voice: {draft}",
    "joke": "Turn this into a small joke in your own voice, still true: {draft}",
}
GUIDE = (
    "You choose {name}'s spoken words. You get the gist of what {name} wants to say. "
    "Reply with only the words to say aloud: one or two short sentences, no quotes, no stage directions. "
    "Keep every fact, name, time and number exactly as given; change only the wording."
)


@dataclass(frozen=True)
class Phrased:
    text: str
    source: str
    note: str = ""
    spoken: bool = False


def tidy(text: str) -> str:
    lines = [line.strip() for line in (text or "").strip().splitlines() if line.strip()]
    if not lines:
        return ""
    words = " ".join(lines[0].split()).strip(QUOTES)
    return words[:MAX_CHARS]


def keeps_facts(draft: str, words: str) -> bool:
    have = set(NUMBER.findall(words))
    return all(number in have for number in NUMBER.findall(draft))


class Wordsmith:
    def __init__(
        self,
        mind: Mind | None,
        options: Callable[[str], CallOptions | None],
        persona: Callable[[], str] = lambda: "",
        idea: Callable[[str], str] = lambda kind: "",
        name: str = "Pebble",
        timeout_s: float = TIMEOUT_S,
        max_tokens: int = MAX_TOKENS,
    ):
        self.mind = mind
        self.options = options
        self.persona = persona
        self.idea = idea
        self.name = name
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens

    def messages(self, draft: str, kind: str) -> list[dict]:
        system = "\n\n".join(part for part in (GUIDE.format(name=self.name), self.persona()) if part)
        ask = ASKS.get(kind, ASKS["talk"]).format(draft=draft)
        idea = self.idea(kind)
        return [{"role": "system", "content": system}, {"role": "user", "content": f"{ask}\n{idea}".strip()}]

    async def phrase(self, draft: str, kind: str = "talk", speak: Callable[[str], Awaitable] | None = None) -> Phrased:
        kind = kind if kind in ASKS else "talk"
        if self.mind is None:
            return Phrased(draft, "draft", "no mind to find words with")
        options = self.options(kind)
        if speak is not None and not NUMBER.search(draft):
            return await self._aloud(draft, kind, options, speak)
        try:
            reply = await asyncio.wait_for(self.mind.chat(self.messages(draft, kind), purpose=kind, max_tokens=self.max_tokens, **options_kwargs(options)), self.timeout_s)
        except (MindUnavailable, asyncio.TimeoutError) as error:
            return Phrased(draft, "draft", str(error) or "timed out")
        words = tidy(reply.text)
        if not words:
            return Phrased(draft, "draft", "the words came back empty")
        if not keeps_facts(draft, words):
            return Phrased(draft, "draft", "the new words changed a number")
        return Phrased(words, "creative")

    async def _aloud(self, draft: str, kind: str, options: CallOptions | None, speak: Callable[[str], Awaitable]) -> Phrased:
        said: list[str] = []
        buffer = ""
        size = 0
        problem = ""

        async def out(parts: list[str]) -> bool:
            nonlocal size
            for part in parts:
                part = " ".join(part.split()).strip(QUOTES)
                if not part:
                    continue
                if NUMBER.search(part) or size + len(part) > MAX_CHARS:
                    return False
                await speak(part)
                said.append(part)
                size += len(part) + 1
            return True

        try:
            async with asyncio.timeout(self.timeout_s):
                async with aclosing(self.mind.stream(self.messages(draft, kind), purpose=kind, max_tokens=self.max_tokens, **options_kwargs(options))) as pieces:
                    async for piece in pieces:
                        buffer = (buffer + piece).lstrip()
                        line, newline, _ = buffer.partition("\n")
                        parts, buffer = sentences(line, not said, bool(newline))
                        if not await out(parts) or newline:
                            buffer = ""
                            break
            if buffer:
                await out(sentences(buffer, not said, True)[0])
        except (MindUnavailable, TimeoutError) as error:
            problem = str(error) or "timed out"
        if not said:
            return Phrased(draft, "draft", problem or "the words came back empty")
        return Phrased(" ".join(said), "creative", problem, True)
