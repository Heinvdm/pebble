import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from ..clock import Clock, iso
from ..selfstore import SelfStore

log = logging.getLogger(__name__)

TRANSCRIPT = "logs/speech.jsonl"


@dataclass(frozen=True)
class SpeechResult:
    spoken: bool
    engine: str


class Voice(Protocol):
    async def say(self, text: str, whisper: bool = False) -> SpeechResult: ...


class TranscriptVoice:
    def __init__(self, store: SelfStore, clock: Clock, echo: bool = True):
        self.store = store
        self.clock = clock
        self.echo = echo
        self.lines: list[str] = []

    async def say(self, text: str, whisper: bool = False) -> SpeechResult:
        text = " ".join(text.split())
        self.store.append(TRANSCRIPT, {"at": iso(self.clock.now()), "text": text, "whisper": whisper})
        self.lines.append(text)
        del self.lines[:-50]
        if self.echo:
            log.info("%s %d words", "whispers" if whisper else "says", len(text.split()))
        return SpeechResult(False, "transcript-only")


def voice_from(config: dict | None, store: SelfStore, clock: Clock) -> Voice:
    config = dict(config or {})
    transcript = TranscriptVoice(store, clock)
    if config.get("kind") == "android":
        from ..android.voice import AndroidVoice

        return AndroidVoice(transcript)
    return transcript


class Talker(Protocol):
    def talk(self, loudness: float) -> None: ...


SECONDS_PER_CHAR = 0.065
MIN_TALK_S = 0.6
MAX_TALK_S = 12.0


class LipSyncVoice:
    def __init__(self, voice: Voice, face: Talker):
        self.voice = voice
        self.face = face
        self._quiet_handle: asyncio.TimerHandle | None = None

    def __getattr__(self, name: str):
        return getattr(self.voice, name)

    async def say(self, text: str, whisper: bool = False) -> SpeechResult:
        result = await self.voice.say(text, whisper)
        seconds = max(MIN_TALK_S, min(MAX_TALK_S, len(" ".join(text.split())) * SECONDS_PER_CHAR))
        self.face.talk(0.4 if whisper else 0.8)
        if self._quiet_handle is not None:
            self._quiet_handle.cancel()
        self._quiet_handle = asyncio.get_running_loop().call_later(seconds, self._hush)
        return result

    def _hush(self) -> None:
        self._quiet_handle = None
        self.face.talk(0.0)
