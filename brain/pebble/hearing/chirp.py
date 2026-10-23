import math
from collections import deque
from dataclasses import dataclass

LONGEST_S = 0.4
SHORTEST_S = 0.02
RISE_DB = 20.0
ALONE_S = 2.5
ALONE_ANY_S = 0.6
QUIETER_DB = 20.0
SAME_HZ = 150.0
LINK_HZ = 40.0
LINK_LENGTH = 0.4
PERIOD_S = (20.0, 90.0)
STEADY = 0.1
MISSED = 3
KEEP_S = 600.0
CAP = 64
SINGLE = 0.3
REPEAT = 0.6
STEADY_SCORE = 0.9


@dataclass(frozen=True)
class Chirp:
    at: float
    level_db: float
    freq_hz: float
    period_s: float | None
    score: float


@dataclass(frozen=True)
class Heard:
    onset: float
    level_db: float
    freq_hz: float
    period_s: float | None
    score: float
    unit_s: float | None
    seconds: float = 0.0


class ChirpWatch:
    def __init__(self, keep_s: float = KEEP_S, cap: int = CAP):
        self.keep_s = keep_s
        self.cap = cap
        self.beeps: deque = deque()
        self.waiting: list = []
        self.found: deque = deque(maxlen=cap)
        self.last_gap: float | None = None

    def add(self, beeps: list) -> None:
        for beep in beeps:
            self.beeps.append(beep)
            if SHORTEST_S <= beep.duration <= LONGEST_S and getattr(beep, "rise_db", RISE_DB) >= RISE_DB:
                self.waiting.append(beep)

    def gap(self, at: float) -> None:
        self.last_gap = at
        self.waiting = []

    def check(self, now: float) -> list[Heard]:
        while self.beeps and now - self.beeps[0].end > 2 * ALONE_S + LONGEST_S:
            self.beeps.popleft()
        out = []
        still = []
        for beep in self.waiting:
            if now - beep.end < ALONE_S:
                still.append(beep)
                continue
            if self._alone(beep) and not self._near_gap(beep):
                heard = self._take(beep)
                self.found.append(heard)
                out.append(heard)
        self.waiting = still
        while self.found and now - self.found[0].onset > self.keep_s:
            self.found.popleft()
        return out

    def _alone(self, beep) -> bool:
        for other in self.beeps:
            if other is beep or other.level_db < beep.level_db - QUIETER_DB:
                continue
            around = ALONE_S if abs(other.freq - beep.freq) <= SAME_HZ else ALONE_ANY_S
            if other.end >= beep.onset - around and other.onset <= beep.end + around:
                return False
        return True

    def _near_gap(self, beep) -> bool:
        return self.last_gap is not None and beep.onset - ALONE_S <= self.last_gap <= beep.end + ALONE_S

    def _same(self, heard: Heard, beep) -> bool:
        if abs(heard.freq_hz - beep.freq) > LINK_HZ or beep.onset - heard.onset > MISSED * PERIOD_S[1]:
            return False
        longer = max(heard.seconds, beep.duration)
        return longer <= 0.0 or abs(heard.seconds - beep.duration) <= LINK_LENGTH * longer

    def _take(self, beep) -> Heard:
        previous = next((h for h in reversed(self.found) if self._same(h, beep)), None)
        if previous is None:
            return Heard(beep.onset, beep.level_db, beep.freq, None, SINGLE, None, beep.duration)
        gap = beep.onset - previous.onset
        unit = self._unit(gap, previous.unit_s)
        if unit is None:
            return Heard(beep.onset, beep.level_db, beep.freq, gap, SINGLE, None, beep.duration)
        steady = previous.unit_s is not None and abs(unit - previous.unit_s) <= STEADY * previous.unit_s
        return Heard(beep.onset, beep.level_db, beep.freq, gap, STEADY_SCORE if steady else REPEAT, unit, beep.duration)

    @staticmethod
    def _unit(gap: float, before: float | None) -> float | None:
        options = [gap / n for n in range(1, MISSED + 1) if PERIOD_S[0] <= gap / n <= PERIOD_S[1]]
        if not options:
            return None
        if before is None:
            return options[0]
        return min(options, key=lambda unit: abs(unit - before))

    def steady_period(self) -> float | None:
        units = sorted(h.unit_s for h in self.found if h.unit_s is not None and h.score >= STEADY_SCORE)
        if not units:
            return None
        return units[len(units) // 2]

    def status(self) -> dict:
        best = max((h.score for h in self.found), default=0.0)
        period = self.steady_period()
        return {"heard": len(self.found), "best": round(best, 2), "period_s": None if period is None else round(period, 1)}


def to_wall(heard: Heard, block_end: float, wall_now: float) -> Chirp:
    at = wall_now - max(0.0, block_end - heard.onset)
    period = None if heard.period_s is None or not math.isfinite(heard.period_s) else round(heard.period_s, 2)
    return Chirp(at, round(heard.level_db, 1), round(heard.freq_hz, 1), period, heard.score)
