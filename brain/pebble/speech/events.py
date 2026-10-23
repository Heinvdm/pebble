import json
import math
from dataclasses import dataclass

KINDS = ("voice_start", "partial", "pause", "keyword", "final", "print", "voice_end", "spoken", "turn_end")
AFTERS = ("pause", "voice_end")
SPOKEN_STATES = ("start", "word", "done", "stopped")
MODES = ("words", "keywords", "off")
TEXT_MAX = 400
PRINT_MIN = 4
PRINT_MAX = 2048


def _number(value, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _print(value) -> tuple[float, ...] | None:
    if not isinstance(value, (list, tuple)) or not PRINT_MIN <= len(value) <= PRINT_MAX:
        return None
    numbers = [_number(v) for v in value]
    if any(n is None for n in numbers):
        return None
    return tuple(numbers)


def _text(value) -> str:
    return " ".join(str(value or "").split())[:TEXT_MAX]


@dataclass(frozen=True)
class SpeechEvent:
    kind: str
    t: float
    segment: int = 0
    text: str = ""
    word: str = ""
    start: float | None = None
    end: float | None = None
    voiceprint: tuple[float, ...] | None = None
    print_s: float = 0.0
    print_follows: bool = False
    level_db: float | None = None
    peak_db: float | None = None
    keyword: bool = False
    pebble_speaking: bool = False
    part: str = ""
    state: str = ""
    chars: int | None = None
    turn_end: float | None = None
    turn_end_ms: float | None = None
    after: str = ""

    def as_dict(self) -> dict:
        out = {"kind": self.kind, "t": round(self.t, 4), "segment": self.segment}
        for name in ("text", "word", "part", "state", "after"):
            value = getattr(self, name)
            if value:
                out[name] = value
        for name in ("start", "end", "level_db", "peak_db", "chars", "turn_end", "turn_end_ms"):
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        if self.voiceprint is not None:
            out["print"] = list(self.voiceprint)
            out["print_s"] = self.print_s
        if self.print_follows:
            out["print_follows"] = True
        if self.keyword:
            out["keyword"] = True
        if self.pebble_speaking:
            out["pebble_speaking"] = True
        return out


def parse(data) -> SpeechEvent | None:
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except ValueError:
            return None
    if not isinstance(data, dict):
        return None
    kind = data.get("kind")
    t = _number(data.get("t"))
    if kind not in KINDS or t is None:
        return None
    segment = data.get("segment", 0)
    try:
        segment = int(segment)
    except (TypeError, ValueError):
        segment = 0
    state = str(data.get("state") or "")
    if kind == "spoken" and state not in SPOKEN_STATES:
        return None
    chars = data.get("chars")
    if chars is None and kind == "spoken" and state == "word":
        chars = data.get("end")
    try:
        chars = None if chars is None else max(0, int(chars))
    except (TypeError, ValueError):
        chars = None
    voiceprint = _print(data.get("print"))
    turn_end = _number(data.get("turn_end"))
    if turn_end is not None:
        turn_end = min(1.0, max(0.0, turn_end))
    if kind == "turn_end" and turn_end is None:
        return None
    after = str(data.get("after") or "")
    return SpeechEvent(
        kind=kind,
        t=t,
        segment=segment,
        text=_text(data.get("text")),
        word=_text(data.get("word"))[:60],
        start=_number(data.get("start")),
        end=_number(data.get("end")),
        voiceprint=voiceprint,
        print_s=max(0.0, _number(data.get("print_s"), 0.0) or 0.0) if voiceprint is not None else 0.0,
        print_follows=bool(data.get("print_follows")),
        level_db=_number(data.get("level_db")),
        peak_db=_number(data.get("peak_db")),
        keyword=bool(data.get("keyword")),
        pebble_speaking=bool(data.get("pebble_speaking")),
        part=str(data.get("id") or data.get("part") or "")[:40],
        state=state,
        chars=chars,
        turn_end=turn_end,
        turn_end_ms=_number(data.get("turn_end_ms")),
        after=after if after in AFTERS else "",
    )
