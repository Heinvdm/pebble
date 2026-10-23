import math

from ..link.protocol import (
    EMPTY_VALUE,
    SETTING_KEYS,
    TEXT_SETTINGS,
    Air,
    Drive,
    Event,
    Flags,
    GetSetting,
    ListSettings,
    Ping,
    Pong,
    ProtocolError,
    Query,
    Reboot,
    SetSetting,
    SettingValue,
    Speed,
    Status,
    Stop,
    Tilt,
    format_message,
    parse_command,
)
from .world import World

VERSION = "sim-0.3"
DEFAULT_SETTINGS = {
    "ssid": "",
    "pass": "",
    "cpm": "0",
    "edge": "75",
    "stop": "60",
    "tmin": "-35",
    "tmax": "90",
    "trim": "0",
    "rest": "8",
}
SETTING_RANGES = {
    "cpm": (0.0, 1000.0),
    "edge": (10.0, 2000.0),
    "stop": (0.0, 2000.0),
    "tmin": (-90.0, 0.0),
    "tmax": (0.0, 120.0),
    "trim": (-30.0, 30.0),
    "rest": (-90.0, 120.0),
}
RAMP_PER_S = 2000.0
STATUS_PERIOD_MS = 50.0
DEADMAN_MS = 500.0
STALL_POWER = 300.0
STALL_MS = 400.0
STALL_HOLD_MS = 1000.0
BUMP_HOLD_MS = 1000.0
BUMP_REVERSE_MM = 30.0
EDGE_REVERSE_MM = 40.0
REFLEX_POWER = 450.0
LOWBAT_MV = 3300.0
LOWBAT_MS = 5000.0
LOWBAT_CLEAR_MV = 3400.0
LOWBAT_CLEAR_MS = 5000.0
CUTOFF_MV = 3100.0
CUTOFF_CLEAR_MV = 3200.0
CUTOFF_CLEAR_MS = 2000.0
LOWBAT_CAP = 500.0
DEADBAND = 80.0
TILT_SLEW = 120.0
CHARGE_TOP_MV = 4150.0
OBSTACLE_REARM_MM = 20
AIR_PERIOD_MS = 3000.0
AIR_LAG_S = 40.0
DEFAULT_AIR = {"temperature_c": 21.5, "humidity_pct": 45.0, "pressure_pa": 101325, "gas_ohm": 120000}
BUMP_CODES = {"L": 1, "R": 2, "B": 3}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def no_forward(pair: list[float]) -> list[float]:
    left, right = pair
    if left + right <= 0:
        return [left, right]
    turn = (left - right) / 2.0
    return [turn, -turn]


class SimFirmware:
    def __init__(
        self,
        world: World | None = None,
        version: str = VERSION,
        pack_mv: float = 3950.0,
        drain_mv_per_s: float = 0.01,
        load_mv_per_s: float = 0.0005,
        charge_mv_per_s: float = 1.5,
        max_speed_mm_s: float = 250.0,
        true_cpm: float = 20.7,
    ):
        self.world = world or World()
        self.version = version
        self.max_speed = max_speed_mm_s
        self.true_cpm = true_cpm
        self.drain = drain_mv_per_s
        self.load = load_mv_per_s
        self.charge = charge_mv_per_s
        self.settings = dict(DEFAULT_SETTINGS)
        self.pack_mv = float(pack_mv)
        self.ms = 0.0
        self.enc = [0.0, 0.0]
        self.sensor_faults: set[str] = set()
        self.reported_faults: set[str] = set()
        self.air: dict | None = dict(DEFAULT_AIR)
        self.air_on_ms = 0.0
        self._reset()

    def _reset(self) -> None:
        self.mode = "power"
        self.command = [0.0, 0.0]
        self.applied = [0.0, 0.0]
        self.maneuver_mm = 0.0
        self.edge_hold = False
        self.bump_until = -1.0
        self.stall_until = [-1.0, -1.0]
        self.bump_state = 0
        self.tilt = self.setting("rest")
        self.tilt_target = self.tilt
        self.last_motion_ms = self.ms
        self.deadman_fired = True
        self.deadman_active = False
        self.lowbat_since: float | None = None
        self.lowbat_clear_since: float | None = None
        self.lowbat_sent = False
        self.cutoff = False
        self.cutoff_clear_since: float | None = None
        self.was_docked = self.world.docked()
        self.obstacle_armed = True
        self.boot_pending = True
        self.reboot_requested = False
        self.reported_faults = set()
        self._status_due = self.ms
        self._air_due = self.ms + AIR_PERIOD_MS
        self.air_on_ms = self.ms
        self._count_seen = [int(self.enc[0]), int(self.enc[1])]
        self._count_change_ms = [self.ms, self.ms]
        self._measured = [0.0, 0.0]

    def setting(self, key: str) -> float:
        try:
            return float(self.settings.get(key) or DEFAULT_SETTINGS.get(key) or 0)
        except ValueError:
            return float(DEFAULT_SETTINGS.get(key) or 0)

    def set_fault(self, name: str, active: bool = True) -> None:
        if active:
            self.sensor_faults.add(name)
        else:
            self.sensor_faults.discard(name)
            self.reported_faults.discard(name)

    def set_air(self, reading: dict | None) -> None:
        if reading is None:
            self.air = None
            return
        if self.air is None:
            self.air_on_ms = self.ms
        self.air = {**(self.air or DEFAULT_AIR), **reading}

    def _follow_air(self, dt: float) -> None:
        if self.air is None or not getattr(self.world, "climate", None):
            return
        target = self.world.air_at(self.world.pose.x, self.world.pose.y)
        if target is None:
            return
        k = 1.0 - math.exp(-dt / AIR_LAG_S)
        for key, value in target.items():
            now = self.air.get(key)
            if now is not None and value is not None:
                self.air[key] = now + (value - now) * k

    def air_line(self) -> str:
        ms = int(self.ms) % (2**32)
        if self.air is None:
            return format_message(Air(ms))
        gas = self.air["gas_ohm"]
        return format_message(
            Air(
                ms,
                round(self.air["temperature_c"], 2),
                round(self.air["humidity_pct"], 2),
                int(self.air["pressure_pa"]),
                None if gas is None else int(gas),
                int((self.ms - self.air_on_ms) / 1000.0),
            )
        )

    @property
    def faulted(self) -> bool:
        return bool(self.sensor_faults)

    def connected(self) -> list[str]:
        if not self.boot_pending:
            return []
        self.boot_pending = False
        return [format_message(Event("boot", (self.version,)))]

    def _halt(self) -> None:
        self.applied = [0.0, 0.0]
        self.command = [0.0, 0.0]
        self.mode = "power"

    def _listed(self, key: str) -> str:
        value = self.settings.get(key, "")
        if key == "pass":
            return "*" if value else EMPTY_VALUE
        if key in TEXT_SETTINGS and not value:
            return EMPTY_VALUE
        return value

    def _store_setting(self, key: str, value: str) -> str | None:
        if key in TEXT_SETTINGS:
            self.settings[key] = "" if value == EMPTY_VALUE else value
            return None
        number = float(value)
        low, high = SETTING_RANGES[key]
        if not low <= number <= high:
            return "range"
        if key == "tmin" and number >= self.setting("tmax"):
            return "range"
        if key == "tmax" and number <= self.setting("tmin"):
            return "range"
        self.settings[key] = value
        return None

    def _motion_accepted(self) -> None:
        self.last_motion_ms = self.ms
        self.deadman_fired = False
        self.deadman_active = False

    def receive(self, line: str) -> list[str]:
        if not line.strip():
            return []
        try:
            command = parse_command(line)
        except ProtocolError as error:
            return [f"err {error.command} {error.reason}"]
        if isinstance(command, Drive):
            self._motion_accepted()
            self.mode = "power"
            self.command = [_clamp(command.left, -1000, 1000), _clamp(command.right, -1000, 1000)]
            if command.left + command.right < 0:
                self.edge_hold = False
            return []
        if isinstance(command, Speed):
            if self.setting("cpm") <= 0:
                return ["err M cpm"]
            self._motion_accepted()
            self.mode = "speed"
            self.command = [_clamp(command.left, -self.max_speed, self.max_speed), _clamp(command.right, -self.max_speed, self.max_speed)]
            if command.left + command.right < 0:
                self.edge_hold = False
            return []
        if isinstance(command, Tilt):
            self.tilt_target = _clamp(command.degrees, self.setting("tmin"), self.setting("tmax"))
            return []
        if isinstance(command, Stop):
            self._halt()
            self.deadman_active = False
            self.maneuver_mm = 0.0
            self.edge_hold = False
            self.bump_until = -1.0
            self.stall_until = [-1.0, -1.0]
            return ["ok"]
        if isinstance(command, Ping):
            return [format_message(Pong(command.n))]
        if isinstance(command, Query):
            return [self.status_line()]
        if isinstance(command, SetSetting):
            problem = self._store_setting(command.key, command.value)
            return [f"err C {problem}"] if problem else ["ok"]
        if isinstance(command, GetSetting):
            return [format_message(SettingValue(command.key, self._listed(command.key)))]
        if isinstance(command, ListSettings):
            return [format_message(SettingValue(key, self._listed(key))) for key in SETTING_KEYS] + ["ok"]
        if isinstance(command, Reboot):
            self._reset()
            self.reboot_requested = True
            return ["ok"]
        return ["err ? unknown"]

    def obstacle_close(self) -> bool:
        front = self.world.front_mm()
        return 0 <= front < self.setting("stop")

    def forward_refused(self) -> bool:
        return self.edge_hold or self.ms < self.bump_until or self.obstacle_close()

    def _motion_commanded(self) -> bool:
        return any(value != 0 for value in self.command)

    def _speed_power(self, index: int) -> float:
        target = self.command[index]
        if target == 0:
            return 0.0
        feed = target / self.max_speed * (1000 - DEADBAND) + math.copysign(DEADBAND, target)
        return _clamp(feed + 2.0 * (target - self._measured[index]), -1000, 1000)

    def _wheels_refused(self) -> bool:
        return self.faulted or self.cutoff

    def _targets(self) -> list[float]:
        if self._wheels_refused():
            return [0.0, 0.0]
        if self.maneuver_mm > 0:
            return [-REFLEX_POWER, -REFLEX_POWER]
        target = [self._speed_power(0), self._speed_power(1)] if self.mode == "speed" else list(self.command)
        if self.forward_refused():
            target = no_forward(target)
        for index in (0, 1):
            if self.ms < self.stall_until[index]:
                target[index] = 0.0
        if self.lowbat_sent:
            target = [_clamp(value, -LOWBAT_CAP, LOWBAT_CAP) for value in target]
        return target

    def _safety_cuts(self) -> None:
        if self._wheels_refused():
            self.applied = [0.0, 0.0]
            return
        if self.maneuver_mm > 0:
            return
        if self.forward_refused():
            self.applied = no_forward(self.applied)
        for index in (0, 1):
            if self.ms < self.stall_until[index]:
                self.applied[index] = 0.0
        if self.lowbat_sent:
            self.applied = [_clamp(value, -LOWBAT_CAP, LOWBAT_CAP) for value in self.applied]

    def _ramp(self, target: list[float], dt: float) -> None:
        step = RAMP_PER_S * dt
        for index in (0, 1):
            self.applied[index] += _clamp(target[index] - self.applied[index], -step, step)

    def _wheel_speed(self, power: float) -> float:
        magnitude = abs(power)
        if magnitude < DEADBAND:
            return 0.0
        volts = _clamp(self.pack_mv / 3900.0, 0.7, 1.08)
        return math.copysign((magnitude - DEADBAND) / (1000 - DEADBAND) * self.max_speed * volts, power)

    def _deadman(self, out: list[str]) -> None:
        if self.deadman_fired or self.ms - self.last_motion_ms <= DEADMAN_MS:
            return
        self.deadman_fired = True
        if not self._motion_commanded():
            return
        self.deadman_active = True
        self._halt()
        out.append(format_message(Event("deadman")))

    def _slew_tilt(self, dt: float) -> None:
        step = TILT_SLEW * dt
        self.tilt += _clamp(self.tilt_target - self.tilt, -step, step)

    def _count(self, moved: tuple[float, float], dt: float) -> None:
        calibrated = self.setting("cpm")
        for index in (0, 1):
            self.enc[index] += moved[index] * self.true_cpm
            count = int(self.enc[index])
            if count != self._count_seen[index]:
                self._count_seen[index] = count
                self._count_change_ms[index] = self.ms
            if abs(self.applied[index]) <= STALL_POWER:
                self._count_change_ms[index] = self.ms
            if dt > 0 and calibrated > 0:
                self._measured[index] = moved[index] * self.true_cpm / calibrated / dt

    def _maneuver_progress(self, moved: tuple[float, float]) -> None:
        if self.maneuver_mm <= 0:
            return
        backwards = -(moved[0] + moved[1]) / 2
        if backwards > 0:
            self.maneuver_mm -= backwards
        if self.maneuver_mm <= 0:
            self.maneuver_mm = 0.0
            self.applied = [0.0, 0.0]

    def _on_bump(self, side: str, out: list[str]) -> None:
        self.bump_state = BUMP_CODES[side]
        if self.maneuver_mm > 0:
            return
        out.append(format_message(Event("bump", (side,))))
        self._halt()
        self.bump_until = self.ms + BUMP_HOLD_MS
        self.maneuver_mm = BUMP_REVERSE_MM

    def _check_edge(self, out: list[str]) -> None:
        if self._wheels_refused() or self.maneuver_mm > 0 or self.applied[0] + self.applied[1] <= 0:
            return
        down = self.world.down_mm()
        if down == -1 or down > self.setting("edge"):
            out.append(format_message(Event("edge")))
            self._halt()
            self.edge_hold = True
            self.maneuver_mm = EDGE_REVERSE_MM

    def _check_stall(self, out: list[str]) -> None:
        for index, side in enumerate("LR"):
            if abs(self.applied[index]) > STALL_POWER and self.ms - self._count_change_ms[index] >= STALL_MS:
                out.append(format_message(Event("stall", (side,))))
                self.applied[index] = 0.0
                self.stall_until[index] = self.ms + STALL_HOLD_MS
                self._count_change_ms[index] = self.ms
                if self.maneuver_mm > 0:
                    self.maneuver_mm = 0.0
                    self.applied = [0.0, 0.0]

    def _check_obstacle(self, out: list[str]) -> None:
        front = self.world.front_mm()
        stop = self.setting("stop")
        close = 0 <= front < stop
        if close and self.obstacle_armed and self.command[0] + self.command[1] > 0:
            out.append(format_message(Event("obstacle", (str(front),))))
            self.obstacle_armed = False
        if front == -1 or front > stop + OBSTACLE_REARM_MM:
            self.obstacle_armed = True

    def _battery(self, dt: float, out: list[str]) -> None:
        if self.world.docked():
            self.pack_mv = min(CHARGE_TOP_MV, self.pack_mv + self.charge * dt)
        else:
            load = abs(self.applied[0]) + abs(self.applied[1])
            self.pack_mv = max(2800.0, self.pack_mv - (self.drain + self.load * load) * dt)
        if self.pack_mv < LOWBAT_MV:
            self.lowbat_clear_since = None
            if self.lowbat_since is None:
                self.lowbat_since = self.ms
            if not self.lowbat_sent and self.ms - self.lowbat_since >= LOWBAT_MS:
                out.append(format_message(Event("lowbat", (str(int(self.pack_mv)),))))
                self.lowbat_sent = True
        else:
            self.lowbat_since = None
            if self.lowbat_sent and self.pack_mv > LOWBAT_CLEAR_MV:
                if self.lowbat_clear_since is None:
                    self.lowbat_clear_since = self.ms
                if self.ms - self.lowbat_clear_since >= LOWBAT_CLEAR_MS:
                    self.lowbat_sent = False
                    self.lowbat_clear_since = None
            else:
                self.lowbat_clear_since = None
        if self.pack_mv < CUTOFF_MV:
            self.cutoff = True
            self.cutoff_clear_since = None
        elif self.cutoff and self.pack_mv > CUTOFF_CLEAR_MV:
            if self.cutoff_clear_since is None:
                self.cutoff_clear_since = self.ms
            if self.ms - self.cutoff_clear_since >= CUTOFF_CLEAR_MS:
                self.cutoff = False
                self.cutoff_clear_since = None
        else:
            self.cutoff_clear_since = None

    def _dock(self, out: list[str]) -> None:
        docked = self.world.docked()
        if docked != self.was_docked:
            self.was_docked = docked
            out.append(format_message(Event("dock", ("1" if docked else "0",))))

    def _faults(self, out: list[str]) -> None:
        if self.world.fallen:
            self.sensor_faults.add("fell")
        for name in sorted(self.sensor_faults - self.reported_faults):
            self.reported_faults.add(name)
            self._halt()
            self.maneuver_mm = 0.0
            out.append(format_message(Event("fault", (name,))))

    def step(self, dt: float) -> list[str]:
        out: list[str] = []
        self.ms += dt * 1000.0
        self.world.step_people(dt)
        self._deadman(out)
        self._faults(out)
        self._slew_tilt(dt)
        self._safety_cuts()
        self._ramp(self._targets(), dt)
        result = self.world.step(dt, self._wheel_speed(self.applied[0]), self._wheel_speed(self.applied[1]))
        moved = (result.left_mm, result.right_mm)
        self._count(moved, dt)
        self._maneuver_progress(moved)
        if result.bump:
            self._on_bump(result.bump, out)
        else:
            self.bump_state = 0
        self._check_edge(out)
        self._check_stall(out)
        self._check_obstacle(out)
        self._battery(dt, out)
        self._dock(out)
        self._faults(out)
        self._follow_air(dt)
        if self.ms >= self._status_due:
            out.append(self.status_line())
            self._status_due = self.ms + STATUS_PERIOD_MS
        if self.ms >= self._air_due:
            out.append(self.air_line())
            self._air_due = self.ms + AIR_PERIOD_MS
        return out

    def flags(self) -> Flags:
        flags = Flags.NONE
        if self.edge_hold:
            flags |= Flags.EDGE_HOLD
        if self.ms < self.bump_until:
            flags |= Flags.BUMP_HOLD
        if self.obstacle_close():
            flags |= Flags.OBSTACLE
        if any(self.ms < until for until in self.stall_until):
            flags |= Flags.STALL
        if self.lowbat_sent or self.cutoff:
            flags |= Flags.LOW_BATTERY
        if self.deadman_active:
            flags |= Flags.DEADMAN
        if self.faulted:
            flags |= Flags.SENSOR_FAULT
        return flags

    def status_line(self) -> str:
        return format_message(
            Status(
                ms=int(self.ms) % (2**32),
                enc_left=int(self.enc[0]),
                enc_right=int(self.enc[1]),
                front_mm=self.world.front_mm(),
                down_mm=self.world.down_mm(),
                bump=self.bump_state,
                dock=1 if self.world.docked() else 0,
                pack_mv=int(self.pack_mv),
                tilt=round(self.tilt),
                flags=self.flags(),
            )
        )
