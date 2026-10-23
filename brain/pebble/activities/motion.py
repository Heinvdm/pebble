import asyncio
import math

from ..laws import move_limits
from ..link.protocol import Event, Flags
from .kit import Kit

REFLEXES = frozenset({"edge", "bump", "stall", "fault", "lowbat", "deadman"})
HOLDS = ((Flags.EDGE_HOLD, "edge"), (Flags.BUMP_HOLD, "bump"), (Flags.STALL, "stall"), (Flags.SENSOR_FAULT, "fault"))
TURN_POWER = 0.35
TURN_RATE_GUESS_DEG_S = 25.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def wrap_deg(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


class Wheels:
    def __init__(self, kit: Kit, homing: bool = False, exempt: str = ""):
        self.kit = kit
        self.homing = homing
        self.exempt = exempt
        self._queue: asyncio.Queue | None = None
        self.moving = False
        self.noted: set[str] = set()

    def open(self) -> "Wheels":
        if self._queue is None:
            self._queue = self.kit.body.subscribe_events()
        return self

    def close(self) -> None:
        if self._queue is not None:
            self.kit.body.unsubscribe_events(self._queue)
            self._queue = None

    def reflexes(self) -> list[str]:
        found = []
        while self._queue is not None and not self._queue.empty():
            message = self._queue.get_nowait()
            if isinstance(message, Event) and message.name in REFLEXES:
                found.append(message.name)
        return found

    def held(self) -> str | None:
        flags = self.kit.body.telemetry.flags
        for flag, name in HOLDS:
            if flag in flags:
                return name
        return None

    def why_not(self) -> str | None:
        blocked = self.kit.guard()
        if blocked:
            return blocked
        permissions = self.kit.permissions
        if permissions.can_move or (self.homing and getattr(permissions, "homing", False)):
            return None
        return "moving is off right now"

    def cap(self) -> float:
        speed, _, _ = move_limits(1.0, 0.0, self.kit.people_near())
        return speed

    async def drive(self, forward: float, turn: float, top: float = 1.0) -> str | None:
        reason = self.why_not()
        if reason:
            await self.halt()
            return reason
        limit = min(top, self.cap())
        left, right = forward - turn, forward + turn
        biggest = max(abs(left), abs(right))
        if biggest > limit > 0:
            left, right = left * limit / biggest, right * limit / biggest
        power = self.kit.body.profile.max_power
        sent = await self.kit.body.drive(left * power, right * power)
        self.moving = bool(round(left * power) or round(right * power))
        return None if sent else "the body is not connected"

    async def halt(self) -> None:
        self.moving = False
        await self.kit.body.drive(0, 0)


class Odometry:
    def __init__(self, kit: Kit):
        self.kit = kit
        self.start: tuple[int, int] | None = None
        self.started_at = kit.pace.now()

    @property
    def calibrated(self) -> bool:
        return self.kit.body.profile.cpm > 0

    def mark(self) -> None:
        self.start = self.kit.body.telemetry.encoders()
        self.started_at = self.kit.pace.now()

    def _delta(self) -> tuple[float, float] | None:
        now = self.kit.body.telemetry.encoders()
        if now is None or self.start is None or not self.calibrated:
            return None
        cpm = self.kit.body.profile.cpm
        return (now[0] - self.start[0]) / cpm, (now[1] - self.start[1]) / cpm

    def turned_deg(self) -> float | None:
        delta = self._delta()
        if delta is None:
            return None
        return math.degrees((delta[1] - delta[0]) / self.kit.body.profile.wheel_track_mm)

    def travelled_mm(self) -> float | None:
        delta = self._delta()
        if delta is None:
            return None
        return (delta[0] + delta[1]) / 2.0


async def turn_by(kit: Kit, wheels: Wheels, degrees: float, power: float = TURN_POWER, timeout_s: float | None = None) -> tuple[float, str | None]:
    if abs(degrees) < 1.0:
        return 0.0, None
    odometry = Odometry(kit)
    odometry.mark()
    sign = 1.0 if degrees > 0 else -1.0
    guess_s = abs(degrees) / TURN_RATE_GUESS_DEG_S
    limit = timeout_s if timeout_s is not None else guess_s * 3.0 + 3.0
    start = kit.pace.now()
    turned = 0.0
    problem = None
    progress_at, progress = start, 0.0
    try:
        while True:
            elapsed = kit.pace.now() - start
            measured = odometry.turned_deg()
            if measured is not None:
                if abs(measured - progress) > 1.0:
                    progress_at, progress = kit.pace.now(), measured
                elif kit.pace.now() - progress_at > 1.5:
                    problem = "the turn is stuck"
                    turned = measured
                    break
            turned = measured if measured is not None else sign * min(abs(degrees), elapsed * TURN_RATE_GUESS_DEG_S)
            left = abs(degrees) - abs(turned)
            if left <= 2.0:
                break
            if elapsed >= limit:
                problem = "the turn took too long"
                break
            hits = [r for r in wheels.reflexes() if r in ("stall", "fault", "edge")]
            if hits:
                problem = hits[0]
                break
            slow = clamp(left / 30.0, 0.55, 1.0)
            reason = await wheels.drive(0.0, sign * power * slow)
            if reason:
                problem = reason
                break
            await kit.pace.sleep(kit.control_s)
    finally:
        await wheels.halt()
    return turned, problem


LEAVE_DOCK_MM = 130.0
LEG_M = 0.6
CLEAR_MM = 220


async def drive_towards(kit: Kit, wheels: Wheels, x: float, y: float, stop_m: float) -> str | None:
    going = getattr(kit.nav, "go_to", None)
    if going is not None:
        trip = await going(kit, x, y, stop_m=stop_m, exempt=wheels.exempt)
        return None if trip.ok else (trip.text or trip.how)
    odometer = kit.odometer
    if odometer is None or not getattr(odometer, "usable", False):
        return "you do not know where you are"
    for _ in range(20):
        px, py, heading = odometer.pose()
        gap = math.hypot(x - px, y - py)
        if gap <= stop_m:
            return None
        aim = math.degrees(math.atan2(y - py, x - px))
        _, problem = await turn_by(kit, wheels, wrap_deg(aim - heading))
        if problem and problem != "the turn took too long":
            return problem
        status = kit.body.telemetry.status
        if status is not None and status.front_mm is not None and 0 <= status.front_mm < CLEAR_MM:
            return "something is in the way"
        _, problem = await roll_by(kit, wheels, min(LEG_M, gap - stop_m + 0.02) * 1000.0, 0.4)
        if problem:
            return problem
    return "it took too many legs"


async def leave_dock(kit: Kit, wheels: Wheels) -> str | None:
    if not kit.body.telemetry.docked:
        return None
    _, problem = await roll_by(kit, wheels, LEAVE_DOCK_MM, 0.35)
    return problem


async def roll_by(kit: Kit, wheels: Wheels, mm: float, power: float, timeout_s: float | None = None) -> tuple[float, str | None]:
    odometry = Odometry(kit)
    odometry.mark()
    sign = 1.0 if mm > 0 else -1.0
    limit = timeout_s if timeout_s is not None else abs(mm) / 20.0 + 3.0
    start = kit.pace.now()
    travelled = 0.0
    last_progress, last_value = start, 0.0
    problem = None
    try:
        while True:
            now = kit.pace.now()
            measured = odometry.travelled_mm()
            travelled = measured if measured is not None else sign * (now - start) * 40.0
            if abs(travelled) >= abs(mm) - 3.0:
                break
            if now - start >= limit:
                problem = "it took too long"
                break
            if abs(travelled - last_value) > 2.0:
                last_progress, last_value = now, travelled
            elif now - last_progress > 1.5:
                problem = "the wheels stopped making progress"
                break
            hits = [r for r in wheels.reflexes() if r in ("edge", "bump", "stall", "fault")]
            if hits:
                problem = hits[0]
                break
            reason = await wheels.drive(sign * power, 0.0)
            if reason:
                problem = reason
                break
            await kit.pace.sleep(kit.control_s)
    finally:
        await wheels.halt()
    return travelled, problem
