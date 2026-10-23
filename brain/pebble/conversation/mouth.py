import asyncio
import logging
import math
import re
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

from ..clock import iso
from ..seams.voice import TRANSCRIPT
from .words import overlap

log = logging.getLogger(__name__)

SECONDS_PER_CHAR = 0.065
MIN_PART_S = 0.35
ECHO_S = 3.0
ECHO_AT = 0.6
END = re.compile(r"([.!?]+)[\"')\]]*(\s+|$)")
FIRST_COMMA_WORDS = 4
MAX_PART = 200
QUOTES = "\"'“”‘’ "


@dataclass
class Part:
    id: str
    text: str
    sent_at: float
    started_at: float | None = None
    done_at: float | None = None
    chars: int = 0
    stopped: bool = False


@dataclass
class Spoken:
    text: str
    parts: int
    first_at: float | None
    stopped: bool
    whole: str = ""


def sentences(buffer: str, first: bool, done: bool) -> tuple[list[str], str]:
    out = []
    rest = buffer
    while True:
        match = END.search(rest)
        if match is None:
            break
        cut = match.end(1)
        piece = rest[:cut].strip()
        rest = rest[match.end() :]
        if piece:
            out.append(piece)
    if first and not out and "," in rest:
        head, _, tail = rest.partition(",")
        if len(head.split()) >= FIRST_COMMA_WORDS:
            out.append(head.strip() + ",")
            rest = tail
    if len(rest) > MAX_PART:
        cut = rest.rfind(" ", 0, MAX_PART)
        cut = cut if cut > 0 else MAX_PART
        out.append(rest[:cut].strip())
        rest = rest[cut:]
    if done and rest.strip():
        out.append(rest.strip())
        rest = ""
    return [p.strip(QUOTES) for p in out if p.strip(QUOTES)], rest


def clean_piece(text: str) -> str:
    text = re.sub(r"\*[^*]*\*", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    return text


class Mouth:
    def __init__(self, voice, face, clock, store=None, monotonic: Callable[[], float] | None = None, sleep=None):
        self.voice = voice
        self.sleep = sleep or asyncio.sleep
        self.face = face
        self.clock = clock
        self.store = store
        self.monotonic = monotonic or clock.monotonic
        self.parts: dict[str, Part] = {}
        self.order: list[str] = []
        self.count = 0
        self.utterance = 0
        self._sleeper: asyncio.Task | None = None
        self._stopped = False
        self._recent: list[tuple[float, str]] = []
        self.first_word_at: float | None = None
        self.last_said = ""
        self.held_back = 0
        self.on_part_start: Callable[[Part], None] = lambda part: None

    @property
    def phone(self) -> bool:
        return callable(getattr(self.voice, "say_part", None)) and callable(getattr(self.voice, "stop_speaking", None)) and bool(getattr(self.voice, "streams", True))

    @property
    def speaking(self) -> bool:
        return any(p.done_at is None and not p.stopped for p in self.parts.values())

    def echo(self, text: str, now: float | None = None) -> bool:
        now = self.monotonic() if now is None else now
        said = " ".join(t for at, t in self._recent if now - at <= ECHO_S) + " " + " ".join(p.text for p in self.parts.values() if p.done_at is None or now - p.done_at <= ECHO_S)
        return bool(said.strip()) and overlap(text, said) >= ECHO_AT

    def allows(self, text: str) -> bool:
        allows = getattr(self.voice, "allows", None)
        return allows is None or bool(allows(text))

    def _remember(self, text: str) -> None:
        now = self.monotonic()
        self._recent.append((now, text))
        self._recent = [(at, t) for at, t in self._recent if now - at <= 30.0]

    async def say(self, text: str, whisper: bool = False) -> Spoken:
        async def one():
            yield text

        return await self.stream(one(), whisper=whisper)

    async def stream(self, pieces: AsyncIterator[str], whisper: bool = False, lead: str = "", check: Callable[[str], bool] | None = None) -> Spoken:
        self.utterance += 1
        self._stopped = False
        self.last_said = ""
        sent: list[Part] = []
        buffer = ""
        first = True

        async def speak(text: str) -> None:
            if (check is not None and not check(text)) or not self.allows(text):
                self.held_back += 1
                return
            sent.append(await self._part(text, whisper))

        try:
            if lead:
                await speak(lead)
            async for piece in pieces:
                if self._stopped:
                    break
                buffer += clean_piece(piece)
                parts, buffer = sentences(buffer, first, False)
                for text in parts:
                    if self._stopped:
                        break
                    await speak(text)
                    first = False
            if not self._stopped:
                parts, buffer = sentences(buffer, first, True)
                for text in parts:
                    if self._stopped:
                        break
                    await speak(text)
            await self.finish()
        except asyncio.CancelledError:
            self.stop()
            self.last_said = self._said(sent)
            self._transcript(self.last_said, whisper, True)
            raise
        said = self._said(sent)
        self.last_said = said
        self._transcript(said, whisper, self._stopped)
        return Spoken(said, len(sent), sent[0].started_at if sent else None, self._stopped, " ".join(p.text for p in sent))

    def _said(self, sent: list[Part]) -> str:
        words = []
        for part in sent:
            if part.stopped:
                if part.chars:
                    words.append(part.text[: part.chars].rsplit(" ", 1)[0] if part.chars < len(part.text) else part.text)
                break
            if part.started_at is None and part.done_at is None:
                break
            words.append(part.text)
        return " ".join(w for w in words if w).strip()

    async def _part(self, text: str, whisper: bool) -> Part:
        self.count += 1
        part = Part(f"r{self.utterance}.{self.count}", text, self.monotonic())
        self.parts[part.id] = part
        self.order.append(part.id)
        del self.order[:-40]
        for old in [k for k in self.parts if k not in self.order]:
            self.parts.pop(old, None)
        self._remember(text)
        if self.phone:
            ok = self.voice.say_part(part.id, text, False, whisper)
            if not ok:
                part.stopped = True
            return part
        await self._previous_done()
        if self._stopped:
            part.stopped = True
            return part
        self._started(part)
        try:
            await self.voice.say(text, whisper=whisper)
        except Exception:
            log.exception("mouth: the voice could not say a line of %d characters", len(text))
        self._sleeper = asyncio.ensure_future(self.sleep(max(MIN_PART_S, len(text) * SECONDS_PER_CHAR)))
        part.chars = 0
        return part

    async def _previous_done(self) -> None:
        sleeper = self._sleeper
        if sleeper is not None and not sleeper.done():
            try:
                await sleeper
            except asyncio.CancelledError:
                pass
        for part in self.parts.values():
            if part.started_at is not None and part.done_at is None and not part.stopped and not self.phone:
                part.done_at = self.monotonic()
                part.chars = len(part.text)

    async def finish(self) -> None:
        if self.phone:
            while self.speaking and not self._stopped:
                await self.sleep(0.05)
            return
        await self._previous_done()
        self._hush()

    def _started(self, part: Part) -> None:
        part.started_at = self.monotonic()
        if self.first_word_at is None:
            self.first_word_at = part.started_at
        talk = getattr(self.face, "talk", None)
        if talk is not None and self.phone:
            talk(0.8)
        try:
            self.on_part_start(part)
        except Exception:
            log.exception("mouth: a part-start listener failed")

    def _hush(self) -> None:
        talk = getattr(self.face, "talk", None)
        if talk is not None and self.phone and not self.speaking:
            talk(0.0)

    def heard_spoken(self, event) -> None:
        part = self.parts.get(event.part)
        if part is None:
            return
        if event.state == "start":
            self._started(part)
        elif event.state == "word":
            part.chars = max(part.chars, int(event.chars or 0))
        elif event.state == "done":
            part.done_at = self.monotonic()
            part.chars = len(part.text)
            self._hush()
        elif event.state == "stopped":
            part.stopped = True
            part.chars = int(event.chars or part.chars)
            part.done_at = self.monotonic()
            self._hush()

    def answer_at(self, lead: str) -> float | None:
        mine = [self.parts[k] for k in self.order if k in self.parts and k.startswith(f"r{self.utterance}.")]
        if lead and mine and mine[0].text == lead:
            mine = mine[1:]
        return mine[0].started_at if mine else None

    def stop(self) -> str:
        self._stopped = True
        live = [self.parts[k] for k in self.order if k in self.parts and self.parts[k].done_at is None and not self.parts[k].stopped]
        if self.phone:
            try:
                self.voice.stop_speaking()
            except Exception:
                log.exception("mouth: the voice would not stop")
        sleeper = self._sleeper
        if sleeper is not None and not sleeper.done():
            sleeper.cancel()
        now = self.monotonic()
        for part in live:
            if part.started_at is not None and not self.phone:
                part.chars = min(len(part.text), int((now - part.started_at) / SECONDS_PER_CHAR))
            part.stopped = True
            part.done_at = now
        talk = getattr(self.face, "talk", None)
        if talk is not None:
            talk(0.0)
        return " ".join(p.text[: p.chars] for p in live if p.chars)

    def _transcript(self, said: str, whisper: bool, stopped: bool) -> None:
        if self.store is None or not self.phone or not said:
            return
        try:
            self.store.append(TRANSCRIPT, {"at": iso(self.clock.now()), "text": said, "whisper": whisper, "cut_short": stopped})
        except Exception:
            log.exception("mouth: could not write the speech log")

    def status(self) -> dict:
        return {"speaking": self.speaking, "phone": self.phone, "parts": len(self.parts), "first_word_at": None if self.first_word_at is None else round(self.first_word_at, 3)}
