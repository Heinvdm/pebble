import math
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from .feeds import Sample

G = 9.81
HIGH_PASS_HZ = 0.8
LOW_PASS_HZ = 10.0
SUB_S = 0.25
QUAKE_WINDOW = 16
QUAKE_RMS = 0.10
QUAKE_SUSTAINED = 13
QUAKE_CREST = 4.5
QUAKE_STILL_S = 3.0
QUAKE_CALM_S = 3.0
QUAKE_EVERY_S = 1.0
FREE_FALL = 3.0
FREE_FALL_S = 0.08
IMPACT = 20.0
IMPACT_WITHIN_S = 1.0
TIP_DEG = 50.0
TIP_S = 1.5
LIFT = 2.5
LIFT_S = 0.2
CARRY_RMS = 0.6
CARRY_S = 4.0
SHAKE_RMS = 5.0
SHAKE_S = 1.0
FELT_GAP_S = 10.0
GRAVITY_S = 0.5


@dataclass(frozen=True)
class Felt:
    kind: str
    text: str
    detail: dict = field(default_factory=dict)


def strength(peak_ms2: float) -> str:
    g = peak_ms2 / G
    if g < 0.02:
        return "light shaking"
    if g < 0.09:
        return "moderate shaking"
    if g < 0.18:
        return "strong shaking"
    return "very strong shaking"


class _Pole:
    def __init__(self, hz: float, high: bool):
        self.hz = hz
        self.high = high
        self.last_in = None
        self.out = 0.0

    def step(self, x: float, dt: float) -> float:
        if self.last_in is None:
            self.last_in = x
            self.out = 0.0 if self.high else x
            return self.out
        rc = 1.0 / (2.0 * math.pi * self.hz)
        if self.high:
            a = rc / (rc + dt)
            self.out = a * (self.out + x - self.last_in)
        else:
            a = dt / (rc + dt)
            self.out += a * (x - self.out)
        self.last_in = x
        return self.out


class PhoneMotion:
    def __init__(self, still: Callable[[], bool] = lambda: False, driving: Callable[[], bool] = lambda: False, docked: Callable[[], bool] = lambda: False, roll_axis: int = 1):
        self.still = still
        self.driving = driving
        self.docked = docked
        self.roll_axis = roll_axis
        self.high = [_Pole(HIGH_PASS_HZ, True) for _ in range(3)]
        self.low = [_Pole(LOW_PASS_HZ, False) for _ in range(3)]
        self.gravity = [_Pole(1.0 / (2.0 * math.pi * GRAVITY_S), False) for _ in range(3)]
        self.last_at: float | None = None
        self.sub: list = []
        self.sub_start: float | None = None
        self.windows: deque = deque(maxlen=QUAKE_WINDOW)
        self.still_since: float | None = None
        self.quake_since: float | None = None
        self.quake_last: float = -math.inf
        self.quake_peak = 0.0
        self.quake_reported: float = -math.inf
        self.fall_since: float | None = None
        self.fell_at: float = -math.inf
        self.tip_since: float | None = None
        self.tipped = False
        self.lift_since: float | None = None
        self.carry: deque = deque(maxlen=int(CARRY_S / SUB_S))
        self.shake: deque = deque(maxlen=int(SHAKE_S / SUB_S))
        self.said: dict[str, float] = {}

    def feed(self, samples: list[Sample]) -> list:
        out: list = []
        for sample in samples:
            out.extend(self._sample(sample))
        return out

    def _felt(self, at: float, kind: str, text: str, **detail) -> list:
        if at - self.said.get(kind, -math.inf) < FELT_GAP_S:
            return []
        self.said[kind] = at
        return [Felt(kind, text, detail)]

    def _sample(self, sample: Sample) -> list:
        at = sample.at
        ax, ay, az = sample.values[:3]
        dt = 0.02 if self.last_at is None else max(1e-3, min(0.2, at - self.last_at))
        self.last_at = at
        band = [self.low[i].step(self.high[i].step(v, dt), dt) for i, v in enumerate((ax, ay, az))]
        grav = [self.gravity[i].step(v, dt) for i, v in enumerate((ax, ay, az))]
        size = math.sqrt(ax * ax + ay * ay + az * az)
        motion = math.sqrt(sum(b * b for b in band))
        out = []
        out.extend(self._falling(at, size))
        out.extend(self._tipping(at, grav))
        out.extend(self._lifting(at, size))
        if self.sub_start is None:
            self.sub_start = at
        self.sub.append(motion)
        if at - self.sub_start >= SUB_S:
            rms = math.sqrt(sum(m * m for m in self.sub) / len(self.sub))
            peak = max(self.sub)
            self.sub = []
            self.sub_start = at
            out.extend(self._window(at, rms, peak))
        return out

    def _falling(self, at: float, size: float) -> list:
        if size < FREE_FALL:
            if self.fall_since is None:
                self.fall_since = at
            return []
        out = []
        if self.fall_since is not None and at - self.fall_since >= FREE_FALL_S:
            self.fell_at = at
        self.fall_since = None
        if size >= IMPACT and at - self.fell_at <= IMPACT_WITHIN_S:
            self.fell_at = -math.inf
            out = self._felt(at, "dropped", "you fell and hit something hard", impact_g=round(size / G, 1))
        return out

    def _tipping(self, at: float, grav: list) -> list:
        g = math.sqrt(sum(v * v for v in grav))
        if g < 5.0:
            return []
        roll = math.degrees(math.asin(max(-1.0, min(1.0, grav[self.roll_axis] / g))))
        if abs(roll) < TIP_DEG:
            self.tip_since = None
            if self.tipped:
                self.tipped = False
                return self._felt(at, "righted", "you are back on your wheels")
            return []
        if self.tip_since is None:
            self.tip_since = at
        if not self.tipped and at - self.tip_since >= TIP_S:
            self.tipped = True
            return self._felt(at, "tipped", "you tipped over on your side", roll=round(roll))
        return []

    def _lifting(self, at: float, size: float) -> list:
        if self.driving() or self.docked():
            self.lift_since = None
            return []
        if size - G >= LIFT:
            if self.lift_since is None:
                self.lift_since = at
            if at - self.lift_since >= LIFT_S:
                self.lift_since = -math.inf
                return self._felt(at, "lifted", "someone picked you up")
            return []
        if self.lift_since is not None and self.lift_since != -math.inf:
            self.lift_since = None
        elif self.lift_since == -math.inf and abs(size - G) < 0.5:
            self.lift_since = None
        return []

    def _window(self, at: float, rms: float, peak: float) -> list:
        out = []
        self.windows.append((at, rms, peak))
        self.carry.append(rms)
        self.shake.append(rms)
        if not self.docked() and not self.driving():
            if len(self.shake) == self.shake.maxlen and min(self.shake) >= SHAKE_RMS:
                out.extend(self._felt(at, "shaken", "someone shook you hard", rms=round(rms, 1)))
            elif len(self.carry) == self.carry.maxlen and sum(1 for r in self.carry if r >= CARRY_RMS) >= 0.8 * len(self.carry) and max(self.carry) < SHAKE_RMS:
                out.extend(self._felt(at, "carried", "someone is carrying you around"))
        out.extend(self._quake(at))
        return out

    def _quake(self, at: float) -> list:
        still = self.still()
        if not still:
            self.still_since = None
        elif self.still_since is None:
            self.still_since = at
        calm = self.quake_since is None and (self.still_since is None or at - self.still_since < QUAKE_STILL_S)
        windows = list(self.windows)
        shaking = False
        rms_all = peak_all = 0.0
        if len(windows) == QUAKE_WINDOW and not calm:
            rms_all = math.sqrt(sum(r * r for _, r, _ in windows) / len(windows))
            peak_all = max(p for _, _, p in windows)
            sustained = sum(1 for _, r, _ in windows if r >= 0.5 * QUAKE_RMS)
            shaking = rms_all >= QUAKE_RMS and sustained >= QUAKE_SUSTAINED and peak_all <= QUAKE_CREST * rms_all
        if shaking:
            self.quake_last = at
            if self.quake_since is None:
                self.quake_since = at - QUAKE_WINDOW * SUB_S
                self.quake_peak = 0.0
            self.quake_peak = max(self.quake_peak, peak_all)
            if at - self.quake_reported >= QUAKE_EVERY_S:
                self.quake_reported = at
                return [Felt("quake", "the floor is shaking, like an earthquake", {"seconds": round(at - self.quake_since, 1), "peak_g": round(self.quake_peak / G, 3), "strength": strength(self.quake_peak)})]
            return []
        if self.quake_since is not None and at - self.quake_last >= QUAKE_CALM_S:
            self.quake_since = None
        return []

    def status(self) -> dict:
        last = self.windows[-1] if self.windows else None
        return {"shaking_rms": None if last is None else round(last[1], 3), "quake": self.quake_since is not None, "tipped": self.tipped}
