import math
from dataclasses import dataclass, field

from ..speech.events import SpeechEvent
from .words import complete, words

END_S = 0.65
QUICK_S = 0.25
FINAL_WAIT_S = 1.5
TURN_HIGH = 0.7
TURN_LOW = 0.3
LONG_S = 1.2
LATE_S = 0.02
VOCATIVE_WORDS = 2
SPLIT_BELOW = 0.2
PRINT_MIN_S = 1.0


def unit(vector) -> tuple[float, ...] | None:
    if not vector:
        return None
    length = math.sqrt(sum(v * v for v in vector))
    return None if length == 0 else tuple(v / length for v in vector)


def cosine(a, b) -> float:
    if a is None or b is None or len(a) != len(b):
        return -1.0
    return sum(x * y for x, y in zip(unit(a), unit(b)))


def blend(prints: list[tuple[tuple[float, ...], float]]) -> tuple[float, ...] | None:
    usable = [(unit(p), w) for p, w in prints if p]
    usable = [(p, w) for p, w in usable if p is not None]
    if not usable or len({len(p) for p, _ in usable}) != 1:
        return None
    size = len(usable[0][0])
    total = [0.0] * size
    for vector, weight in usable:
        for i, value in enumerate(vector):
            total[i] += value * max(weight, 0.1)
    return unit(total)


@dataclass
class Segment:
    id: int
    started: float
    start: float | None = None
    end: float | None = None
    text: str = ""
    partial: str = ""
    final: bool = False
    keyword: bool = False
    voiceprint: tuple | None = None
    print_s: float = 0.0
    level_db: float | None = None
    peak_db: float | None = None
    pebble_speaking: bool = False
    paused_at: float | None = None
    ended_at: float | None = None
    turn_end: float | None = None
    turn_end_at: float | None = None
    turn_end_after: str = ""

    @property
    def words(self) -> str:
        return self.text if self.final else self.partial


@dataclass
class Turn:
    id: int
    started: float
    segments: list[Segment] = field(default_factory=list)
    keyword: bool = False
    closed: bool = False
    closed_at: float | None = None
    speaker: str | None = None
    track: int | None = None
    bearing_deg: float | None = None
    label: str = "someone"
    verdict: object = None
    heard: object = None
    notes: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return " ".join(s.words for s in self.segments if s.words).strip()

    @property
    def start(self) -> float:
        starts = [s.start for s in self.segments if s.start is not None]
        return min(starts) if starts else self.started

    @property
    def end(self) -> float | None:
        ends = [s.end for s in self.segments if s.end is not None]
        return max(ends) if ends else None

    @property
    def voiceprint(self) -> tuple | None:
        return blend([(s.voiceprint, s.print_s) for s in self.segments if s.voiceprint])

    @property
    def print_s(self) -> float:
        return sum(s.print_s for s in self.segments if s.voiceprint)

    @property
    def level_db(self) -> float | None:
        levels = [s.level_db for s in self.segments if s.level_db is not None]
        return max(levels) if levels else None

    @property
    def peak_db(self) -> float | None:
        peaks = [s.peak_db for s in self.segments if s.peak_db is not None]
        return max(peaks) if peaks else None

    @property
    def name_alone(self) -> bool:
        return any(s.keyword and s.final and not s.text for s in self.segments) or (self.keyword and not self.segments)

    @property
    def pebble_speaking(self) -> bool:
        return bool(self.segments) and all(s.pebble_speaking for s in self.segments)

    def finals(self) -> bool:
        return all(s.final for s in self.segments)

    def talking(self) -> bool:
        return any(s.ended_at is None for s in self.segments)

    @property
    def done_chance(self) -> float | None:
        return self.segments[-1].turn_end if self.segments else None


class TurnTaker:
    def __init__(self, on_open=None, on_change=None, on_close=None, on_name=None, end_s: float = END_S, quick_s: float = QUICK_S):
        self.on_open = on_open or (lambda turn: None)
        self.on_change = on_change or (lambda turn, kind: None)
        self.on_close = on_close or (lambda turn: None)
        self.on_name = on_name or (lambda turn: None)
        self.end_s = end_s
        self.quick_s = quick_s
        self.turn: Turn | None = None
        self.segments: dict[int, Segment] = {}
        self.count = 0
        self.last_voice = -math.inf
        self.silence_since: float | None = None

    def _open(self, t: float) -> Turn:
        self.count += 1
        self.turn = Turn(self.count, t)
        self.on_open(self.turn)
        return self.turn

    def _segment(self, event: SpeechEvent) -> Segment:
        seg = self.segments.get(event.segment)
        if seg is None:
            seg = Segment(event.segment, event.t, start=event.start if event.start is not None else event.t, pebble_speaking=event.pebble_speaking)
            self.segments[event.segment] = seg
            turn = self.turn or self._open(event.t)
            turn.segments.append(seg)
            for old in [k for k in self.segments if k < event.segment - 40]:
                self.segments.pop(old, None)
        return seg

    def feed(self, event: SpeechEvent) -> Segment | None:
        kind = event.kind
        if kind == "spoken":
            return None
        if kind == "turn_end":
            seg = self.segments.get(event.segment)
            if seg is None or self.turn is None or seg not in self.turn.segments:
                return None
            self._judged(seg, event)
            self.on_change(self.turn, "turn_end")
            return seg
        if kind == "keyword" and self.turn is None and event.segment not in self.segments:
            self._open(event.t).keyword = True
            self.on_name(self.turn)
            return None
        seg = self._segment(event)
        turn = self.turn
        if kind == "voice_start":
            self.last_voice = event.t
            self.silence_since = None
            seg.pebble_speaking = seg.pebble_speaking and event.pebble_speaking
            if turn is not None:
                self.on_change(turn, "voice")
        elif kind == "partial":
            seg.partial = event.text
            seg.pebble_speaking = seg.pebble_speaking and event.pebble_speaking
            self.last_voice = event.t
            if turn is not None:
                self.on_change(turn, "partial")
        elif kind == "keyword":
            seg.keyword = True
            if turn is not None:
                was = turn.keyword
                turn.keyword = True
                if not was:
                    self.on_name(turn)
        elif kind == "pause":
            seg.paused_at = event.t
            if seg.turn_end_after != "voice_end":
                seg.turn_end, seg.turn_end_at, seg.turn_end_after = None, None, ""
            self._judged(seg, event)
            if turn is not None:
                self.on_change(turn, "pause")
        elif kind == "voice_end":
            seg.ended_at = event.t
            seg.end = event.end if event.end is not None else event.t
            self.silence_since = seg.end
            self._judged(seg, event)
            if turn is not None:
                self.on_change(turn, "voice_end")
        elif kind == "final":
            seg.final = True
            seg.text = event.text
            seg.keyword = seg.keyword or event.keyword
            seg.level_db = event.level_db
            seg.peak_db = event.peak_db
            seg.pebble_speaking = seg.pebble_speaking and event.pebble_speaking
            if event.start is not None:
                seg.start = event.start
            if event.end is not None:
                seg.end = event.end
            if seg.ended_at is None:
                seg.ended_at = event.t
                self.silence_since = seg.end
            if event.voiceprint is not None:
                seg.voiceprint, seg.print_s = event.voiceprint, event.print_s
            if turn is not None:
                if event.keyword and not turn.keyword:
                    turn.keyword = True
                    self.on_name(turn)
                self._maybe_split(turn, seg, event.t)
                if self.turn is not None:
                    self.on_change(self.turn, "final")
        elif kind == "print":
            if event.voiceprint is not None:
                seg.voiceprint, seg.print_s = event.voiceprint, event.print_s
        return seg

    def _judged(self, seg: Segment, event: SpeechEvent) -> None:
        if event.turn_end is None:
            return
        after = event.after or event.kind
        if after == "turn_end":
            after = "voice_end" if seg.ended_at is not None else "pause"
        if after not in ("pause", "voice_end"):
            return
        if event.kind == "turn_end":
            if after == "voice_end" and seg.ended_at is None:
                return
            if after == "pause" and (seg.paused_at is None or seg.turn_end_after == "voice_end" or self._older(event, seg.paused_at)):
                return
        seg.turn_end, seg.turn_end_at, seg.turn_end_after = event.turn_end, event.t, after

    def _older(self, event: SpeechEvent, paused_at: float) -> bool:
        if event.turn_end_ms is None:
            return False
        return event.t - event.turn_end_ms / 1000.0 < paused_at - LATE_S

    def _maybe_split(self, turn: Turn, seg: Segment, t: float) -> None:
        if seg.voiceprint is None or seg.print_s < PRINT_MIN_S or len(turn.segments) < 2:
            return
        before = [s for s in turn.segments if s is not seg]
        earlier = blend([(s.voiceprint, s.print_s) for s in before if s.voiceprint and s.print_s >= PRINT_MIN_S])
        if earlier is None or cosine(earlier, seg.voiceprint) >= SPLIT_BELOW:
            return
        turn.segments = before
        self.close(t)
        fresh = self._open(t)
        fresh.segments.append(seg)

    def split_for(self, t: float) -> None:
        turn = self.turn
        if turn is None or len(turn.segments) < 2 or not turn.segments[-1].ended_at is None:
            return
        last = turn.segments[-1]
        turn.segments = turn.segments[:-1]
        self.close(t)
        fresh = self._open(t)
        fresh.segments.append(last)

    def due(self, now: float) -> float | None:
        turn = self.turn
        if turn is None or turn.talking():
            return None
        if not turn.segments:
            return turn.started + self.end_s
        end = turn.end if turn.end is not None else now
        return end + self.wait(turn)[0]

    def wait(self, turn: Turn) -> tuple[float, str]:
        if not turn.finals():
            return max(self.end_s, FINAL_WAIT_S), "no words yet"
        chance = turn.done_chance
        if chance is not None and chance <= TURN_LOW:
            return max(self.end_s, LONG_S), "sounded unfinished"
        if chance is not None and chance >= TURN_HIGH and not self._vocative(turn):
            return self.quick_s, "sounded finished"
        if complete(turn.text):
            return self.quick_s, "read as finished"
        return self.end_s, "silence"

    def _vocative(self, turn: Turn) -> bool:
        last = turn.segments[-1]
        return not turn.text or (last.keyword and len(words(last.words)) <= VOCATIVE_WORDS)

    def tick(self, now: float) -> Turn | None:
        due = self.due(now)
        if due is None or now < due:
            return None
        if self.turn is not None and self.turn.segments:
            self.turn.notes["closed_by"] = self.wait(self.turn)[1]
        return self.close(now)

    def close(self, now: float) -> Turn | None:
        turn = self.turn
        if turn is None:
            return None
        self.turn = None
        turn.closed = True
        turn.closed_at = now
        if turn.segments or turn.keyword:
            self.on_close(turn)
        return turn

    def silent_for(self, now: float) -> float:
        if self.turn is not None and self.turn.talking():
            return 0.0
        since = self.silence_since if self.silence_since is not None else self.last_voice
        return max(0.0, now - since) if since != -math.inf else math.inf


def word_count(turn: Turn) -> int:
    return len(words(turn.text))
