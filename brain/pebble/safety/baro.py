import math
from collections import deque
from typing import Callable

from .feeds import Sample
from .motion import Felt

HPA_PER_M = 0.12
SMOOTH_S = 0.5
FLOOR_STEP_HPA = 0.25
FLOOR_WITHIN_S = 20.0
FLOOR_SETTLE_S = 5.0
FLOOR_EVERY_S = 0.5
PULSE_HPA = 0.04
PULSE_BASE_S = 4.0
PULSE_MAX_S = 3.0
PULSE_GAP_S = 30.0
STORM_HOURS = 3.0
STORM_FALL_HPA = 3.0
STORM_FAST_HPA = 6.0
STORM_GAP_S = 6 * 3600.0
MINUTE_S = 60.0
KEEP_MINUTES = 6 * 60


class Barometer:
    def __init__(self, still: Callable[[], bool] = lambda: True):
        self.still = still
        self.smooth: float | None = None
        self.last_at: float | None = None
        self.history: deque = deque()
        self.base: deque = deque()
        self.pulse_from: float | None = None
        self.pulse_peak = 0.0
        self.pulse_base = 0.0
        self.pulse_said = -math.inf
        self.minute_sum = 0.0
        self.minute_count = 0
        self.minute_start: float | None = None
        self.minutes: deque = deque(maxlen=KEEP_MINUTES)
        self.offset = 0.0
        self.storm_said = -math.inf
        self.step_said = -math.inf
        self.floors_at = -math.inf
        self.latest: float | None = None

    def feed(self, samples: list[Sample]) -> list:
        out = []
        for sample in samples:
            out.extend(self._sample(sample.at, sample.value))
        return out

    def _sample(self, at: float, hpa: float) -> list:
        if not 300.0 < hpa < 1200.0:
            return []
        self.latest = hpa
        dt = 0.1 if self.last_at is None else max(1e-3, min(5.0, at - self.last_at))
        self.last_at = at
        if self.smooth is None:
            self.smooth = hpa
        else:
            self.smooth += (hpa - self.smooth) * dt / (SMOOTH_S + dt)
        out = []
        out.extend(self._floors(at))
        out.extend(self._pulse(at, hpa))
        out.extend(self._minutes(at))
        return out

    def _floors(self, at: float) -> list:
        self.history.append((at, self.smooth))
        while self.history and at - self.history[0][0] > FLOOR_WITHIN_S + FLOOR_SETTLE_S:
            self.history.popleft()
        if not self.history or at - self.history[0][0] < FLOOR_WITHIN_S or at - self.floors_at < FLOOR_EVERY_S:
            return []
        self.floors_at = at
        settled = [p for t, p in self.history if at - t <= FLOOR_SETTLE_S]
        before = [p for t, p in self.history if at - t >= FLOOR_WITHIN_S]
        if not settled or not before or max(settled) - min(settled) > FLOOR_STEP_HPA / 3.0:
            return []
        change = sum(settled) / len(settled) - sum(before) / len(before)
        if abs(change) < FLOOR_STEP_HPA or at - self.step_said < FLOOR_WITHIN_S:
            return []
        self.step_said = at
        self.offset += change
        self.history.clear()
        metres = abs(change) / HPA_PER_M
        way = "down" if change > 0 else "up"
        return [Felt(f"moved_{way}", f"you were moved {way} about {metres:.0f} metres, about {max(1, round(metres / 3))} floor{'s' if metres >= 4.5 else ''}", {"metres": round(metres, 1), "way": way, "hpa": round(change, 2)})]

    def _pulse(self, at: float, hpa: float) -> list:
        self.base.append((at, hpa))
        while self.base and at - self.base[0][0] > PULSE_BASE_S:
            self.base.popleft()
        if len(self.base) < 5 or not self.still():
            self.pulse_from = None
            return []
        if self.pulse_from is None:
            ordered = sorted(p for _, p in self.base)
            middle = ordered[len(ordered) // 2]
            if abs(hpa - middle) >= PULSE_HPA:
                self.pulse_from = at
                self.pulse_base = middle
                self.pulse_peak = abs(hpa - middle)
            return []
        away = abs(hpa - self.pulse_base)
        self.pulse_peak = max(self.pulse_peak, away)
        lasted = at - self.pulse_from
        if lasted > PULSE_MAX_S:
            self.pulse_from = None
            return []
        if away >= PULSE_HPA / 2.0:
            return []
        peak, self.pulse_from = self.pulse_peak, None
        if at - self.pulse_said < PULSE_GAP_S:
            return []
        self.pulse_said = at
        return [Felt("door", "the air pressure jumped for a moment, like a door opening or shutting somewhere", {"pa": round(peak * 100, 1), "seconds": round(lasted, 1)})]

    def _minutes(self, at: float) -> list:
        if self.minute_start is None:
            self.minute_start = at
        self.minute_sum += self.smooth - self.offset
        self.minute_count += 1
        if at - self.minute_start < MINUTE_S:
            return []
        self.minutes.append((at, self.minute_sum / self.minute_count))
        self.minute_start, self.minute_sum, self.minute_count = at, 0.0, 0
        span = [(t, p) for t, p in self.minutes if at - t <= STORM_HOURS * 3600.0 + MINUTE_S]
        if len(span) < 2 or at - span[0][0] < STORM_HOURS * 3600.0 - MINUTE_S:
            return []
        fall = span[0][1] - span[-1][1]
        if fall < STORM_FALL_HPA or at - self.storm_said < STORM_GAP_S:
            return []
        self.storm_said = at
        fast = "very fast" if fall >= STORM_FAST_HPA else "fast"
        return [Felt("storm", f"the air pressure has fallen {fast} ({fall:.1f} hPa in 3 hours), which often means stormy weather is coming", {"hpa": round(fall, 1)})]

    def status(self) -> dict:
        return {"hpa": None if self.latest is None else round(self.latest, 2), "minutes": len(self.minutes)}
