import logging

from ..seams.voice import SpeechResult, TranscriptVoice
from .bridge import require

log = logging.getLogger(__name__)


class AndroidVoice:
    def __init__(self, transcript: TranscriptVoice, bridge=None):
        self.transcript = transcript
        self._bridge = bridge
        self.spoken = 0
        self.problem = ""

    def bridge(self):
        return self._bridge if self._bridge is not None else require("speaking out loud")

    def __getattr__(self, name: str):
        return getattr(self.transcript, name)

    async def say(self, text: str, whisper: bool = False) -> SpeechResult:
        await self.transcript.say(text, whisper)
        words = " ".join(text.split())
        if not words:
            return SpeechResult(False, "android-tts")
        try:
            ok = bool(self.bridge().speak(words, bool(whisper)))
        except Exception as error:
            ok = False
            self.problem = str(error)
            log.warning("voice: the phone could not speak: %s", error)
        if ok:
            self.spoken += 1
            self.problem = ""
        return SpeechResult(ok, "android-tts" if ok else "transcript-only")

    def say_part(self, part_id: str, text: str, last: bool = True, whisper: bool = False) -> bool:
        try:
            return bool(self.bridge().sayPart(str(part_id), str(text), bool(last), bool(whisper)))
        except Exception as error:
            self.problem = str(error)
            log.warning("voice: the phone could not speak a part: %s", error)
            return False

    def stop_speaking(self) -> None:
        try:
            self.bridge().stopSpeaking()
        except Exception as error:
            log.warning("voice: the phone could not stop speaking: %s", error)
