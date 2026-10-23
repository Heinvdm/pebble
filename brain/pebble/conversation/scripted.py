import math
from dataclasses import dataclass

from ..people.fake import fake_print
from ..speech.events import SpeechEvent
from .words import name_at, words

WORD_S = 0.36
ONSET_S = 0.1
CHUNK_S = 0.48
SILENCE_S = 0.25
DECODE_S = 0.06
KEYWORD_S = 0.11
NAME_GAP_S = 0.35
PRINT_MIN_S = 1.0
PAUSE_S = 0.04
THINK_S = 0.9
THINK_MARK = "..."
TURN_S = 0.12
INNER_TURN = 0.1


@dataclass(frozen=True)
class Said:
    who: str
    text: str
    level_db: float = -24.0
    turn_end: float | None = None


class ScriptedSpeech:
    def __init__(self, name: str = "Pebble", word_s: float = WORD_S, prints: bool = True, turn_s: float = TURN_S):
        self.name = name
        self.word_s = word_s
        self.prints = prints
        self.turn_s = turn_s
        self.segment = 0
        self.turn_free = -math.inf

    def _segments(self, text: str) -> list[tuple[str, float]]:
        parts = [part.strip() for part in text.split(THINK_MARK) if part.strip()] or [text]
        out = []
        for number, part in enumerate(parts):
            gap = THINK_S if number < len(parts) - 1 else 0.0
            said = part.split()
            for index, word in enumerate(said[:2]):
                if word.endswith(",") and name_at(word, self.name) and len(said) > index + 1:
                    out += [(" ".join(said[: index + 1]), NAME_GAP_S), (" ".join(said[index + 1 :]), gap)]
                    break
            else:
                out.append((part, gap))
        return out

    def _judged(self, seg: int, end: float, score: float) -> list[SpeechEvent]:
        out = []
        for after, asked in (("pause", end + PAUSE_S), ("voice_end", end + SILENCE_S)):
            begin = max(asked, self.turn_free)
            self.turn_free = begin + self.turn_s
            out.append(SpeechEvent("turn_end", self.turn_free, seg, turn_end=score, turn_end_ms=round(self.turn_s * 1000.0, 1), after=after))
        return out

    def events(self, said: Said, start: float, speaking: bool = False) -> tuple[list[SpeechEvent], float]:
        out: list[SpeechEvent] = []
        t = start
        pieces = self._segments(said.text)
        last_end = start
        for number, (piece, gap) in enumerate(pieces):
            self.segment += 1
            seg = self.segment
            spoken = [w for w in piece.split() if w]
            length = max(1, len(spoken)) * self.word_s
            begin, end = t, t + length
            out.append(SpeechEvent("voice_start", begin + ONSET_S, seg, start=begin, pebble_speaking=speaking))
            heard = ""
            chunk = begin + CHUNK_S
            while chunk < end:
                count = int((chunk - begin) / self.word_s)
                text = " ".join(words(" ".join(spoken[:count])))
                if text and text != heard:
                    heard = text
                    out.append(SpeechEvent("partial", chunk, seg, text=text, pebble_speaking=speaking))
                chunk += CHUNK_S
            out.append(SpeechEvent("pause", end + PAUSE_S, seg, pebble_speaking=speaking))
            if name_at(piece, self.name):
                out.append(SpeechEvent("keyword", end + KEYWORD_S, seg, word=self.name.lower(), pebble_speaking=speaking))
            out.append(SpeechEvent("voice_end", end + SILENCE_S, seg, end=end, pebble_speaking=speaking))
            final_text = " ".join(words(piece))
            if len(spoken) == 1 and name_at(piece, self.name):
                final_text = ""
            voiceprint = tuple(fake_print(said.who, "voice")) if self.prints and length >= PRINT_MIN_S else None
            out.append(
                SpeechEvent(
                    "final",
                    end + SILENCE_S + DECODE_S,
                    seg,
                    text=final_text,
                    start=begin,
                    end=end,
                    voiceprint=voiceprint,
                    print_s=round(length, 2) if voiceprint else 0.0,
                    level_db=said.level_db,
                    peak_db=said.level_db + 12.0,
                    keyword=bool(name_at(piece, self.name)),
                    pebble_speaking=speaking,
                )
            )
            if said.turn_end is not None:
                out += self._judged(seg, end, said.turn_end if number == len(pieces) - 1 else INNER_TURN)
            last_end = end
            t = end + gap
        return sorted(out, key=lambda e: e.t), last_end
