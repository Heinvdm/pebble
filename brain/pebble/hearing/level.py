import math
import threading
from collections import deque
from dataclasses import dataclass

from .audio import FULL_SCALE, RATE, SILENT_DB, Block, decibels

STEP_S = 0.1
KEEP_S = 90.0
FLOOR_PERCENTILE = 0.2
SHOUT_OVER_FLOOR_DB = 25.0
SHOUT_OVER_TALK_DB = 12.0
SHOUT_DB = -30.0
TALK_OVER_FLOOR_DB = 10.0
TALK_PERCENTILE = 0.5
TALK_MIN = 20
LOUD_OVER_FLOOR_DB = 15.0
RECENT_S = 6.0
PEAK_SPAN = 3


@dataclass(frozen=True)
class Loudness:
    peak_db: float
    floor_db: float
    shouted: bool
    loud: bool

    def as_dict(self) -> dict:
        return {"peak_db": round(self.peak_db, 1), "floor_db": round(self.floor_db, 1), "shouted": self.shouted, "loud": self.loud}


class LevelMeter:
    def __init__(self, keep_s: float = KEEP_S):
        self.levels: deque = deque(maxlen=int(keep_s / STEP_S))
        self.carry: list[int] = []
        self.step = int(STEP_S * RATE)
        self.sumprod = getattr(math, "sumprod", None) or (lambda a, b: sum(x * y for x, y in zip(a, b)))
        self.muted_until = -math.inf
        self.lock = threading.Lock()

    def feed(self, block: Block, muted: bool = False) -> None:
        samples = self.carry + list(block.samples)
        count = len(samples) // self.step
        start = block.end - len(samples) / RATE
        scale = 1.0 / (FULL_SCALE * FULL_SCALE * self.step)
        for index in range(count):
            chunk = samples[index * self.step : (index + 1) * self.step]
            at = start + (index + 1) * self.step / RATE
            level = decibels(self.sumprod(chunk, chunk) * scale)
            with self.lock:
                self.levels.append((at, level, muted or block.own_voice))
        self.carry = samples[count * self.step :]

    def snapshot(self) -> list:
        with self.lock:
            return list(self.levels)

    def floor(self, levels: list | None = None) -> float:
        values = sorted(level for _, level, own in (self.snapshot() if levels is None else levels) if not own)
        if not values:
            return SILENT_DB
        return values[int(FLOOR_PERCENTILE * (len(values) - 1))]

    def now_db(self) -> float:
        levels = self.snapshot()
        return levels[-1][1] if levels else SILENT_DB

    def talk_level(self, floor: float, levels: list | None = None) -> float | None:
        voiced = sorted(level for _, level, own in (self.snapshot() if levels is None else levels) if not own and level >= floor + TALK_OVER_FLOOR_DB)
        if len(voiced) < TALK_MIN:
            return None
        return voiced[int(TALK_PERCENTILE * (len(voiced) - 1))]

    def recent(self, now: float, within_s: float = RECENT_S) -> Loudness:
        levels = self.snapshot()
        floor = self.floor(levels)
        values = [level for at, level, own in levels if now - at <= within_s and not own]
        if len(values) < PEAK_SPAN:
            return Loudness(SILENT_DB, floor, False, False)
        peak = max(sum(values[i : i + PEAK_SPAN]) / PEAK_SPAN for i in range(len(values) - PEAK_SPAN + 1))
        talk = self.talk_level(floor, levels)
        shouted = peak >= SHOUT_DB or (talk is not None and peak - talk >= SHOUT_OVER_TALK_DB and peak - floor >= SHOUT_OVER_FLOOR_DB)
        return Loudness(peak, floor, shouted, peak - floor >= LOUD_OVER_FLOOR_DB)
