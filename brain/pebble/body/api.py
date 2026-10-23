import asyncio
import logging
from dataclasses import asdict, dataclass, field

from ..clock import Clock
from ..link.client import LinkClient, LinkDown, LinkUp
from ..link.replies import Listing
from ..link.protocol import (
    Air,
    Drive,
    Err,
    Event,
    GetSetting,
    ListSettings,
    Ok,
    POWER_LIMIT,
    ProtocolError,
    Query,
    Reboot,
    SetSetting,
    SettingValue,
    Speed,
    Status,
    Stop,
    Tilt,
    format_command,
    setting_from_wire,
    setting_text,
)
from .checks import unsafe_settings
from .profile import BodyProfile
from .telemetry import Telemetry

log = logging.getLogger(__name__)

STOPPING_EVENTS = frozenset({"edge", "bump", "stall", "deadman", "fault"})
MOTION_LETTERS = frozenset({"D", "M"})
SETTLE_S = 0.15
MOTION_REFRESH_S = 0.2
SETTINGS_WAIT_S = 2.0
SETTINGS_RETRY_S = 5.0
SETTINGS_UNKNOWN = "unknown"
SETTINGS_CHECKING = "checking"
SETTINGS_OK = "ok"
SETTINGS_UNSAFE = "unsafe"
SETTINGS_UNREAD = "unread"


@dataclass
class MoveReport:
    ok: bool
    dry_run: bool
    left: int
    right: int
    seconds: float
    counts: tuple[int, int] | None = None
    travelled_mm: float | None = None
    events: list[str] = field(default_factory=list)
    stopped_early: bool = False
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _clamp(value: float, limit: float) -> int:
    return int(max(-limit, min(limit, round(value))))


class Body:
    def __init__(self, link: LinkClient, clock: Clock, profile: BodyProfile, dry_run: bool = False):
        self.link = link
        self.clock = clock
        self.profile = profile
        self.dry_run = dry_run
        self.telemetry = Telemetry()
        self.wheel_commands_sent = 0
        self.dry_run_requests: list[tuple[int, int]] = []
        self._subscribers: list[asyncio.Queue] = []
        self._pump_task: asyncio.Task | None = None
        self._interrupt = asyncio.Event()
        self.settings_state = SETTINGS_UNKNOWN
        self.settings_problem = ""
        self._settings_checked = asyncio.Event()
        self._check_task: asyncio.Task | None = None
        self._checked_at = 0.0
        self._refusal_said = ""

    @property
    def connected(self) -> bool:
        return self.link.connected

    def start(self) -> None:
        queue = self.link.subscribe()
        self.link.start()
        if self._pump_task is None or self._pump_task.done():
            self._pump_task = asyncio.create_task(self._pump(queue), name="pebble-body")

    async def close(self) -> None:
        if self.connected:
            await self.stop()
        for task in (self._pump_task, self._check_task):
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self._pump_task = None
        self._check_task = None
        await self.link.stop()

    def subscribe_events(self, maxsize: int = 200) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(queue)
        return queue

    def unsubscribe_events(self, queue: asyncio.Queue) -> None:
        self._subscribers = [q for q in self._subscribers if q is not queue]

    def _publish(self, item) -> None:
        for queue in list(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(item)

    async def _pump(self, queue: asyncio.Queue) -> None:
        while True:
            message = await queue.get()
            now = self.clock.now()
            if isinstance(message, Status):
                self.telemetry.apply_status(message, now)
            elif isinstance(message, Air):
                self.telemetry.apply_air(message, now)
            elif isinstance(message, Event):
                if message.name == "boot":
                    self.telemetry.boot_version = message.arg
                self._publish(message)
            elif isinstance(message, Err):
                if message.command in MOTION_LETTERS:
                    log.warning("the body refused a motion command: %s %s", message.command, message.reason)
                    self._publish(message)
            elif isinstance(message, LinkUp):
                self.telemetry.link_up = True
                self.telemetry.link_label = message.label
                self._start_check(apply=bool(self.profile.firmware_settings))
                self._publish(message)
            elif isinstance(message, LinkDown):
                self.telemetry.link_up = False
                if self._check_task is not None and not self._check_task.done():
                    self._check_task.cancel()
                self.settings_state = SETTINGS_UNKNOWN
                self._settings_checked.clear()
                self._publish(message)

    def _start_check(self, apply: bool = False) -> None:
        if self._check_task is not None and not self._check_task.done():
            return
        self.settings_state = SETTINGS_CHECKING
        self._settings_checked.clear()
        self._check_task = asyncio.create_task(self._check_settings(apply), name="pebble-body-settings")

    async def _check_settings(self, apply: bool) -> None:
        try:
            if apply:
                await self.apply_profile_settings()
            values = await self.settings(timeout=1.5)
            self._checked_at = asyncio.get_running_loop().time()
            if not values:
                self.settings_state = SETTINGS_UNREAD
                self.settings_problem = "the body did not list its settings"
                log.warning("not driving: %s", self.settings_problem)
                return
            problems = unsafe_settings(values)
            if problems:
                self.settings_state = SETTINGS_UNSAFE
                self.settings_problem = "; ".join(problems)
                log.error("not driving: the body's reflex settings are outside the safe ranges: %s", self.settings_problem)
                self._publish(Event("fault", ("settings",)))
                return
            self.settings_state = SETTINGS_OK
            self.settings_problem = ""
        except Exception as error:
            self.settings_state = SETTINGS_UNREAD
            self.settings_problem = f"the settings check failed: {error}"
            log.exception("the body's settings could not be checked")
        finally:
            self._settings_checked.set()

    async def may_drive(self) -> bool:
        if not self.link.connected:
            return True
        if self.settings_state in (SETTINGS_UNKNOWN, SETTINGS_UNREAD):
            if self.settings_state == SETTINGS_UNKNOWN or asyncio.get_running_loop().time() - self._checked_at >= SETTINGS_RETRY_S:
                self._start_check()
        if self.settings_state == SETTINGS_CHECKING:
            try:
                await asyncio.wait_for(self._settings_checked.wait(), SETTINGS_WAIT_S)
            except asyncio.TimeoutError:
                return False
        if self.settings_state == SETTINGS_OK:
            self._refusal_said = ""
            return True
        if self._refusal_said != self.settings_problem:
            self._refusal_said = self.settings_problem
            log.warning("refusing to drive: %s", self.settings_problem or self.settings_state)
        return False

    async def apply_profile_settings(self) -> dict[str, str | None]:
        current = await self.settings()
        results = {}
        for key, value in self.profile.firmware_settings.items():
            if current.get(key) != value:
                results[key] = await self.set_setting(key, value)
        return results

    async def drive(self, left: float, right: float) -> bool:
        left_power, right_power = _clamp(left, POWER_LIMIT), _clamp(right, POWER_LIMIT)
        if self.dry_run and (left_power or right_power):
            self.dry_run_requests.append((left_power, right_power))
            log.info("dry run: would drive %d %d", left_power, right_power)
            return True
        if (left_power or right_power) and not await self.may_drive():
            return False
        if left_power or right_power:
            self.wheel_commands_sent += 1
        return await self.link.send(Drive(left_power, right_power))

    async def speed(self, left_mm_s: float, right_mm_s: float) -> bool:
        limit = self.profile.max_speed_mm_s
        left, right = _clamp(left_mm_s, limit), _clamp(right_mm_s, limit)
        if self.dry_run and (left or right):
            self.dry_run_requests.append((left, right))
            return True
        if (left or right) and not await self.may_drive():
            return False
        if left or right:
            self.wheel_commands_sent += 1
        return await self.link.send(Speed(left, right))

    def clamp_tilt(self, degrees: float) -> float:
        return max(self.profile.tilt_min, min(self.profile.tilt_max, float(degrees)))

    async def tilt(self, degrees: float) -> float | None:
        target = round(self.clamp_tilt(degrees))
        return float(target) if await self.link.send(Tilt(target)) else None

    async def stop(self) -> bool:
        self._interrupt.set()
        return await self.link.send(Stop())

    async def ping(self, timeout: float = 1.0) -> float | None:
        return await self.link.ping(timeout)

    async def query(self, timeout: float = 1.0) -> Status | None:
        return await self.link.request(Query(), lambda m: isinstance(m, Status), timeout)

    async def set_setting(self, key: str, value, timeout: float = 1.0) -> str | None:
        command = SetSetting(key, setting_text(key, str(value)))
        try:
            format_command(command)
        except ProtocolError as error:
            return f"refused: {error}"
        reply = await self.link.exchange(command, timeout)
        if isinstance(reply, Ok):
            return "ok"
        return reply.reason if isinstance(reply, Err) else None

    async def get_setting(self, key: str, timeout: float = 1.0) -> str | None:
        command = GetSetting(key)
        try:
            format_command(command)
        except ProtocolError:
            return None
        reply = await self.link.exchange(command, timeout)
        return setting_from_wire(key, reply.value) if isinstance(reply, SettingValue) else None

    async def settings(self, timeout: float = 1.0) -> dict[str, str]:
        reply = await self.link.exchange(ListSettings(), timeout)
        if not isinstance(reply, Listing):
            return {}
        return {item.key: setting_from_wire(item.key, item.value) for item in reply.values}

    async def reboot(self, timeout: float = 1.0) -> bool:
        reply = await self.link.exchange(Reboot(), timeout)
        return isinstance(reply, Ok)

    def _mm(self, counts: tuple[int, int]) -> float | None:
        if self.profile.cpm <= 0:
            return None
        return round((abs(counts[0]) + abs(counts[1])) / 2 / self.profile.cpm, 1)

    async def move(self, left: float, right: float, seconds: float) -> MoveReport:
        left_power, right_power = _clamp(left, POWER_LIMIT), _clamp(right, POWER_LIMIT)
        seconds = max(0.0, min(self.profile.max_move_seconds, float(seconds)))
        if self.dry_run:
            self.dry_run_requests.append((left_power, right_power))
            return MoveReport(True, True, left_power, right_power, seconds, note="dry run: the wheels are off")
        if not self.connected:
            return MoveReport(False, False, left_power, right_power, 0.0, note="the body is not connected")
        if (left_power or right_power) and not await self.may_drive():
            return MoveReport(False, False, left_power, right_power, 0.0, note=f"not driving: {self.settings_problem or 'the body settings are not checked yet'}")
        before = self.telemetry.encoders()
        events_queue = self.subscribe_events()
        self._interrupt.clear()
        loop = asyncio.get_running_loop()
        started = loop.time()
        events: list[str] = []
        stopped_early = False
        try:
            if not await self.drive(left_power, right_power):
                return MoveReport(False, False, left_power, right_power, 0.0, note="the drive command did not go out")
            refresh_at = loop.time() + MOTION_REFRESH_S
            while True:
                now = loop.time()
                remaining = started + seconds - now
                if remaining <= 0:
                    break
                if self._interrupt.is_set():
                    stopped_early = True
                    events.append("stop requested")
                    break
                if now >= refresh_at:
                    if not await self.drive(left_power, right_power):
                        events.append("link lost")
                        stopped_early = True
                        break
                    refresh_at = now + MOTION_REFRESH_S
                try:
                    message = await asyncio.wait_for(events_queue.get(), min(remaining, refresh_at - now, 0.05))
                except asyncio.TimeoutError:
                    continue
                if isinstance(message, Event):
                    events.append(message.text())
                    if message.name in STOPPING_EVENTS:
                        stopped_early = True
                        break
                elif isinstance(message, Err):
                    events.append(f"refused: {message.command} {message.reason}")
                    stopped_early = True
                    break
                elif isinstance(message, LinkDown):
                    events.append("link lost")
                    stopped_early = True
                    break
        finally:
            self.unsubscribe_events(events_queue)
            await self.link.send(Drive(0, 0))
        elapsed = loop.time() - started
        await asyncio.sleep(SETTLE_S)
        after = self.telemetry.encoders()
        counts = None if before is None or after is None else (after[0] - before[0], after[1] - before[1])
        return MoveReport(
            ok=True,
            dry_run=False,
            left=left_power,
            right=right_power,
            seconds=round(elapsed, 2),
            counts=counts,
            travelled_mm=None if counts is None else self._mm(counts),
            events=events,
            stopped_early=stopped_early,
            note="stopped early" if stopped_early else "",
        )
