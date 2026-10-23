import math
import time
from typing import Callable

from ..link.protocol import Status
from .geometry import wrap

DOCKED_X_M = 0.08
HOME = "home"
BASE_DRIFT_M = 0.05
DRIFT_WHEELS = 0.04
DRIFT_GYRO = 0.02
GYRO_FRESH_S = 0.3
GYRO_COVER_S = 0.03
OFFSET_CREEP = 0.001
CAL_TURN_RAD_S = 0.4
PRIOR_TURN_RAD_S = 0.2
CAL_SAMPLES = 30
CAL_FIT = 0.85
PRIOR_SAMPLES = 5
PRIOR_FIT = 0.5
LANDSCAPE = (1.0, 0.0, 0.0)
STILL_S = 0.6
BIAS_RATE = 0.01
STILL_SKIP_S = 0.3
STILL_RAD_S = 0.05
SLIP_RAD_S = 0.6
SLIP_COUNT = 4
JUMP_M = 0.5
STEP_PEAK = 1.3
STEP_GAP_S = 0.3
STRIDE_M = 0.6
STEP_DRIFT_M = 0.25
PUT_DOWN_S = 0.8
FLOOR_MM = (8, 70)
LOST_DRIFT_M = 1.5


class Pose:
    def __init__(
        self,
        cpm: float,
        track_mm: float,
        gyro=None,
        accel=None,
        tilt: Callable[[], float | None] = lambda: None,
        monotonic: Callable[[], float] = time.monotonic,
        edge_mm: float = 75.0,
        prior: tuple[float, float, float] | None = None,
    ):
        self.cpm = cpm
        self.track_m = track_mm / 1000.0
        self.gyro = gyro
        self.accel = accel
        self.tilt = tilt
        self.monotonic = monotonic
        self.edge_mm = edge_mm
        self.prior = list(prior) if prior is not None else None
        self.x = DOCKED_X_M
        self.y = 0.0
        self.heading = 0.0
        self.shadow = 0.0
        self.known = False
        self.frame: str | None = None
        self.travelled_m = 0.0
        self.extra_drift_m = 0.0
        self.total_m = 0.0
        self._last: tuple[int, int] | None = None
        self._last_at: float | None = None
        self._offset: float | None = None
        self._offset_at: float | None = None
        self._body_last: float | None = None
        self.samples: list[tuple[float, tuple]] = []
        self.bias = [0.0, 0.0, 0.0]
        self.bias_n = 0
        self.axis: list[float] | None = None
        self.axis_tilt = 8.0
        self.fit = 0.0
        self.cal: list[tuple[float, float, float, float]] = []
        self.still_since: float | None = None
        self.slip_count = 0
        self.slipping_since: float | None = None
        self.gyro_rate = 0.0
        self.wheel_rate = 0.0
        self.speed = 0.0
        self.carried = False
        self.carried_since: float | None = None
        self.put_down_since: float | None = None
        self.steps = 0
        self.step_at = -math.inf
        self.gravity = [0.0, 0.0, 9.81]
        self.lifted_by_floor = False
        self.listeners: list[Callable[[str], None]] = []

    @classmethod
    def for_body(cls, body, **kwargs) -> "Pose":
        return cls(body.profile.cpm, body.profile.wheel_track_mm, tilt=lambda: body.telemetry.tilt, **kwargs)

    @property
    def usable(self) -> bool:
        return self.known and self.frame == HOME and self.cpm > 0

    @property
    def local_usable(self) -> bool:
        return self.frame is not None and self.cpm > 0

    @property
    def gyro_ready(self) -> bool:
        return self.axis is not None and self.samples_fresh()

    @property
    def bias_known(self) -> bool:
        return self.bias_n >= 30

    @property
    def slipping(self) -> bool:
        return self.slipping_since is not None

    def samples_fresh(self) -> bool:
        return bool(self.samples) and self.monotonic() - self.samples[-1][0] <= GYRO_FRESH_S

    def drift_m(self) -> float:
        rate = DRIFT_GYRO if self.axis is not None else DRIFT_WHEELS
        return BASE_DRIFT_M + rate * self.travelled_m + self.extra_drift_m

    def pose(self) -> tuple[float, float, float]:
        return self.x, self.y, math.degrees(self.heading)

    def pose_rad(self) -> tuple[float, float, float]:
        return self.x, self.y, self.heading

    def _tell(self, what: str) -> None:
        for listener in list(self.listeners):
            listener(what)

    def reset(self, x: float, y: float, heading_rad: float) -> None:
        self.x, self.y, self.heading = x, y, wrap(heading_rad)
        self.shadow = 0.0
        self.known = True
        self.frame = HOME
        self.travelled_m = 0.0
        self.extra_drift_m = 0.0

    def relocate(self, x: float, y: float, heading_deg: float) -> None:
        was = self.frame
        self.reset(x, y, math.radians(heading_deg))
        if was != HOME:
            self._tell("home")

    def anchor(self, x: float, y: float, weight: float) -> None:
        if not self.local_usable:
            return
        weight = max(0.0, min(1.0, weight))
        self.x += weight * (x - self.x)
        self.y += weight * (y - self.y)
        self.travelled_m *= 1.0 - weight
        self.extra_drift_m *= 1.0 - weight

    def nudge_heading(self, delta_rad: float) -> None:
        if self.local_usable:
            self.heading = wrap(self.heading + delta_rad)

    def turn_anchor(self, heading_rad: float, weight: float) -> None:
        if not self.local_usable:
            return
        self.heading = wrap(self.heading + max(0.0, min(1.0, weight)) * wrap(heading_rad - self.heading))

    def start_visit(self, name: str, x: float = 0.0, y: float = 0.0, heading_rad: float = 0.0) -> None:
        self.x, self.y, self.heading = x, y, heading_rad
        self.shadow = 0.0
        self.known = False
        self.frame = name
        self.travelled_m = 0.0
        self.extra_drift_m = 0.0
        self._tell("visit")

    def lose(self) -> None:
        if self.frame == HOME:
            self.known = False
        self._tell("lost")

    def felt(self, kind: str) -> None:
        if kind in ("lifted", "carried") and not self.carried:
            self.carried = True
            self.carried_since = self.monotonic()
            self.put_down_since = None
            self._tell("carried")
        elif kind in ("dropped", "tipped"):
            self.extra_drift_m += 0.3

    def _yaw_rate(self, values: tuple) -> float:
        axis = self.axis
        if axis is None:
            return 0.0
        g = [values[i] - self.bias[i] for i in range(3)]
        tilt = self.tilt()
        if tilt is not None and abs(tilt - self.axis_tilt) > 2.0:
            axis = self._tilted(axis, math.radians(tilt - self.axis_tilt))
        return axis[0] * g[0] + axis[1] * g[1] + axis[2] * g[2]

    def _tilted(self, axis: list[float], delta: float) -> list[float]:
        pitch = min(range(3), key=lambda i: abs(axis[i]))
        a, b = [i for i in range(3) if i != pitch]
        phi = math.atan2(axis[b], axis[a])
        phi += delta if math.cos(phi) >= 0 else -delta
        size = math.hypot(axis[a], axis[b])
        out = list(axis)
        out[a] = size * math.cos(phi)
        out[b] = size * math.sin(phi)
        return out

    def _pump(self) -> None:
        if self.gyro is not None:
            for sample in self.gyro.read():
                if len(sample.values) >= 3:
                    self.samples.append((sample.at, tuple(sample.values[:3])))
            if len(self.samples) > 400:
                del self.samples[:-400]
        if self.accel is not None:
            for sample in self.accel.read():
                if len(sample.values) >= 3:
                    self._accel(sample.at, sample.values[:3])

    def _between(self, start: float, end: float) -> list[tuple[float, tuple]]:
        return [s for s in self.samples if start < s[0] <= end]

    def _integrate(self, start: float, end: float) -> tuple[float, list[float]] | None:
        chunk = self._between(start, end)
        if not chunk:
            return None
        total = 0.0
        parts = [0.0, 0.0, 0.0]
        previous = start
        for at, values in chunk:
            dt = max(0.0, min(0.1, at - previous))
            previous = at
            total += self._yaw_rate(values) * dt
            for i in range(3):
                parts[i] += (values[i] - self.bias[i]) * dt
        gap = max(0.0, end - previous)
        if gap > 0 and chunk:
            last = chunk[-1][1]
            total += self._yaw_rate(last) * min(gap, 0.1)
            for i in range(3):
                parts[i] += (last[i] - self.bias[i]) * min(gap, 0.1)
        return total, parts

    def _still(self, start: float, end: float) -> None:
        for _, values in self._between(start, end):
            if max(abs(values[i] - self.bias[i]) for i in range(3)) > STILL_RAD_S and self.bias_n >= 10:
                continue
            self.bias_n += 1
            rate = max(BIAS_RATE, 1.0 / self.bias_n)
            for i in range(3):
                self.bias[i] += rate * (values[i] - self.bias[i])

    def _calibrate(self, wheel_turn: float, parts: list[float], dt: float) -> None:
        if dt <= 0 or abs(wheel_turn) / dt < (PRIOR_TURN_RAD_S if self.axis is None else CAL_TURN_RAD_S) or self.slipping:
            return
        self.cal.append((wheel_turn, parts[0], parts[1], parts[2]))
        del self.cal[:-120]
        ee = sum(e * e for e, _, _, _ in self.cal)
        if ee <= 0:
            return
        if self.axis is None and self.prior is not None and len(self.cal) >= PRIOR_SAMPLES:
            tilt = self.tilt()
            guess = self._tilted(self.prior, math.radians(tilt if tilt is not None else 8.0))
            predicted = [guess[0] * g0 + guess[1] * g1 + guess[2] * g2 for _, g0, g1, g2 in self.cal]
            residual = sum((e - p) ** 2 for (e, _, _, _), p in zip(self.cal, predicted))
            if 1.0 - residual / ee >= PRIOR_FIT:
                self.heading = wrap(self.heading + self.shadow)
                self.shadow = 0.0
                self.axis = guess
                self.axis_tilt = tilt if tilt is not None else 8.0
                self.fit = 1.0 - residual / ee
                self._tell("gyro")
                return
        if len(self.cal) < CAL_SAMPLES:
            return
        weights = [sum(row[0] * row[i + 1] for row in self.cal) / ee for i in range(3)]
        norm = math.sqrt(sum(w * w for w in weights))
        if norm < 0.3:
            return
        unit = [w / norm for w in weights]
        predicted = [unit[0] * g0 + unit[1] * g1 + unit[2] * g2 for _, g0, g1, g2 in self.cal]
        residual = sum((e - p) ** 2 for (e, _, _, _), p in zip(self.cal, predicted))
        fit = 1.0 - residual / ee
        if fit >= CAL_FIT:
            first = self.axis is None
            self.axis = unit
            self.axis_tilt = self.tilt() if self.tilt() is not None else 8.0
            self.fit = fit
            if first:
                self._tell("gyro")

    def calibrate_axis(self, axis: tuple[float, float, float], tilt_deg: float = 8.0) -> None:
        norm = math.sqrt(sum(a * a for a in axis)) or 1.0
        self.axis = [a / norm for a in axis]
        self.axis_tilt = tilt_deg
        self.fit = 1.0

    def _accel(self, at: float, values) -> None:
        for i in range(3):
            self.gravity[i] += 0.05 * (values[i] - self.gravity[i])
        if not self.carried:
            return
        size = math.sqrt(sum(v * v for v in values))
        g = math.sqrt(sum(v * v for v in self.gravity)) or 9.81
        if size - g > STEP_PEAK and at - self.step_at >= STEP_GAP_S:
            self.step_at = at
            self.steps += 1
            self.x += STRIDE_M * math.cos(self.heading)
            self.y += STRIDE_M * math.sin(self.heading)
            self.extra_drift_m += STEP_DRIFT_M
            self.total_m += STRIDE_M

    def _carried_turn(self, start: float, end: float) -> None:
        g = math.sqrt(sum(v * v for v in self.gravity))
        if g < 5.0:
            return
        up = [v / g for v in self.gravity]
        total = 0.0
        previous = start
        for at, values in self._between(start, end):
            dt = max(0.0, min(0.1, at - previous))
            previous = at
            total += sum((values[i] - self.bias[i]) * up[i] for i in range(3)) * dt
        self.heading = wrap(self.heading + total)

    def _floor_seen(self, status: Status) -> bool | None:
        down = status.down_mm
        if down is None:
            return None
        if down < 0 or down > max(self.edge_mm, FLOOR_MM[1]):
            return False
        return FLOOR_MM[0] <= down <= FLOOR_MM[1]

    def _status_time(self, status: Status, now: float) -> float:
        ms = getattr(status, "ms", None)
        if ms is None:
            return now
        body = ms / 1000.0
        if self._body_last is not None and body < self._body_last - 1.0:
            self._offset = None
        self._body_last = body
        lag = now - body
        if self._offset is None or lag < self._offset:
            self._offset = lag
        elif self._offset_at is not None:
            self._offset += OFFSET_CREEP * max(0.0, now - self._offset_at)
            self._offset = min(self._offset, lag)
        self._offset_at = now
        return body + self._offset

    def update(self, status: Status) -> None:
        self._pump()
        now = self._status_time(status, self.monotonic())
        counts = (status.enc_left, status.enc_right)
        started, self._last_at = self._last_at, now
        if status.dock == 1:
            if self.frame != HOME:
                self._tell("home")
            self.reset(DOCKED_X_M, 0.0, 0.0)
            self._last = counts
            self.carried = False
            return
        last, self._last = self._last, counts
        if self.carried:
            if started is not None:
                self._carried_turn(started, now)
            floor = self._floor_seen(status)
            if floor:
                if self.put_down_since is None:
                    self.put_down_since = now
                elif now - self.put_down_since >= PUT_DOWN_S:
                    self.carried = False
                    self.put_down_since = None
                    if self.extra_drift_m > LOST_DRIFT_M and self.frame == HOME:
                        self.known = False
                    self._tell("put_down")
            else:
                self.put_down_since = None
            return
        if last is None or self.cpm <= 0 or started is None:
            return
        dt = max(1e-3, now - started)
        left = (counts[0] - last[0]) / self.cpm / 1000.0
        right = (counts[1] - last[1]) / self.cpm / 1000.0
        if abs(left) > JUMP_M or abs(right) > JUMP_M:
            return
        distance = (left + right) / 2.0
        wheel_turn = (right - left) / self.track_m
        moving = abs(left) > 1e-4 or abs(right) > 1e-4
        if not moving:
            if self.still_since is None:
                self.still_since = started
            if now - self.still_since >= STILL_S:
                self._still(max(started, self.still_since + STILL_SKIP_S), now)
        else:
            self.still_since = None
        covered = bool(self.samples) and self.samples[-1][0] >= now - GYRO_COVER_S and self.samples_fresh()
        integrated = self._integrate(started, now) if covered else None
        turn = wheel_turn
        if integrated is not None:
            gyro_turn, parts = integrated
            had_axis = self.axis is not None
            diff = 0.0
            if not had_axis and self.prior is not None:
                tilt = self.tilt()
                guess = self._tilted(self.prior, math.radians(tilt if tilt is not None else 8.0))
                diff = sum(guess[i] * parts[i] for i in range(3)) - wheel_turn
            self._calibrate(wheel_turn, parts, dt)
            if self.axis is None:
                self.shadow += diff
            elif not had_axis:
                tilt = self.tilt()
                axis = self.axis if tilt is None or abs(tilt - self.axis_tilt) <= 2.0 else self._tilted(self.axis, math.radians(tilt - self.axis_tilt))
                gyro_turn = sum(axis[i] * parts[i] for i in range(3))
            if self.axis is not None:
                self.gyro_rate = gyro_turn / dt
                if abs(wheel_turn - gyro_turn) / dt > SLIP_RAD_S:
                    self.slip_count += 1
                    if self.slip_count >= SLIP_COUNT and self.slipping_since is None:
                        self.slipping_since = now
                else:
                    self.slip_count = 0
                    self.slipping_since = None
                turn = gyro_turn
        self.wheel_rate = wheel_turn / dt
        self.speed = distance / dt
        middle = self.heading + turn / 2.0
        self.x += distance * math.cos(middle)
        self.y += distance * math.sin(middle)
        self.heading = wrap(self.heading + turn)
        self.travelled_m += abs(distance)
        self.total_m += abs(distance)
        floor = self._floor_seen(status)
        if floor is False and not moving and not self.carried and status.flags == 0:
            self.lifted_by_floor = True
        else:
            self.lifted_by_floor = False

    async def run(self, body) -> None:
        queue = body.link.subscribe((Status,))
        try:
            while True:
                self.update(await queue.get())
        finally:
            body.link.unsubscribe(queue)
