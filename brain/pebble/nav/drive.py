import math

from ..laws import move_limits
from .geometry import TRACK_M

DEADBAND = 80.0
FULL_POWER = 1000.0
CREEP_M_S = 0.03
TRIM_GAIN = 300.0
TRIM_LIMIT = 160.0
TRIM_FADE = 0.9


class Driver:
    def __init__(self, body, sprint_power: float = FULL_POWER):
        self.body = body
        profile = body.profile
        self.full = max(0.05, profile.max_speed_mm_s / 1000.0)
        self.cruise_power = float(profile.max_power)
        self.sprint_power = max(self.cruise_power, min(FULL_POWER, float(sprint_power)))
        self.v = 0.0
        self.w = 0.0
        self.sent = (0, 0)
        self.trim = [0.0, 0.0]
        self.last_counts: tuple[int, int] | None = None
        self.last_at: float | None = None
        self.measured = [0.0, 0.0]
        self.wanted = [0.0, 0.0]

    def speed_of(self, power: float) -> float:
        return max(0.0, (abs(power) - DEADBAND) / (FULL_POWER - DEADBAND)) * self.full

    def power_of(self, speed: float) -> float:
        if abs(speed) < 0.004:
            return 0.0
        return math.copysign(DEADBAND + min(1.0, abs(speed) / self.full) * (FULL_POWER - DEADBAND), speed)

    @property
    def cruise(self) -> float:
        return self.speed_of(self.cruise_power)

    @property
    def sprint(self) -> float:
        return self.speed_of(self.sprint_power)

    def wheel_cap(self, near: bool, sprint_ok: bool, creep: bool) -> float:
        cap = self.sprint if sprint_ok and not near else self.cruise
        if near:
            fraction, _, _ = move_limits(1.0, 0.0, True)
            cap = min(cap, self.speed_of(fraction * self.cruise_power))
        if creep:
            cap = min(cap, CREEP_M_S)
        return cap

    def _measure(self, now: float) -> None:
        counts = self.body.telemetry.encoders()
        cpm = self.body.profile.cpm
        if counts is None or cpm <= 0:
            return
        if self.last_counts is not None and self.last_at is not None and now - self.last_at > 0.02:
            dt = now - self.last_at
            self.measured = [(counts[i] - self.last_counts[i]) / cpm / 1000.0 / dt for i in range(2)]
        self.last_counts, self.last_at = counts, now

    async def send(self, v: float, w: float, wheel_cap: float, now: float) -> bool:
        left, right = v - w * TRACK_M / 2.0, v + w * TRACK_M / 2.0
        biggest = max(abs(left), abs(right))
        if biggest > wheel_cap > 0:
            left, right = left * wheel_cap / biggest, right * wheel_cap / biggest
        elif wheel_cap <= 0:
            left = right = 0.0
        self.v, self.w = (left + right) / 2.0, (right - left) / TRACK_M
        self._measure(now)
        ceiling = self.sprint_power if wheel_cap > self.cruise + 1e-6 else self.cruise_power
        out = []
        for index, want in enumerate((left, right)):
            power = self.power_of(want)
            if power == 0.0:
                self.trim[index] = 0.0
            elif abs(want) > 0.02 and self.body.profile.cpm > 0 and math.copysign(1.0, self.measured[index]) == math.copysign(1.0, want) and abs(self.wanted[index] - want) < 0.05:
                error = want - self.measured[index]
                self.trim[index] = max(-TRIM_LIMIT, min(TRIM_LIMIT, self.trim[index] * TRIM_FADE + error * TRIM_GAIN * 0.1))
                power += self.trim[index]
            out.append(max(-ceiling, min(ceiling, power)))
        self.wanted = [left, right]
        self.sent = (round(out[0]), round(out[1]))
        return await self.body.drive(out[0], out[1])

    async def halt(self) -> None:
        self.v = self.w = 0.0
        self.trim = [0.0, 0.0]
        self.sent = (0, 0)
        await self.body.drive(0, 0)
