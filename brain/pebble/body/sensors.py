import json
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

log = logging.getLogger(__name__)

AIR_WARMUP_S = 300
AIR_STALE_S = 10.0


@dataclass(frozen=True)
class BatteryReading:
    percent: float
    charging: bool | None
    temperature_c: float | None = None
    health_pct: float | None = None
    source: str = ""


@dataclass(frozen=True)
class ImuReading:
    accel: tuple[float, float, float]
    gyro: tuple[float, float, float]


@dataclass(frozen=True)
class AirReading:
    at: float
    body_ms: int
    present: bool
    temperature_c: float | None = None
    humidity_pct: float | None = None
    pressure_pa: int | None = None
    gas_ohm: int | None = None
    heated_s: int | None = None

    @property
    def pressure_hpa(self) -> float | None:
        return None if self.pressure_pa is None else self.pressure_pa / 100.0

    @property
    def warming(self) -> bool:
        return self.present and (self.heated_s is None or self.heated_s < AIR_WARMUP_S)

    def age(self, now: float) -> float:
        return max(0.0, now - self.at)

    def fresh(self, now: float, max_age: float = AIR_STALE_S) -> bool:
        return self.age(now) <= max_age


@dataclass(frozen=True)
class SensorSnapshot:
    at: float
    battery: BatteryReading | None
    temperature_c: float | None
    light_lux: float | None
    imu: ImuReading | None


class BatterySource(Protocol):
    def read(self) -> BatteryReading | None: ...


class ValueSource(Protocol):
    def read(self) -> float | None: ...


class ImuSource(Protocol):
    def read(self) -> ImuReading | None: ...


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii", errors="replace").strip()
    except OSError:
        return None


def _read_number(path: Path) -> float | None:
    text = _read_text(path)
    try:
        return float(text) if text is not None else None
    except ValueError:
        return None


class SysfsBattery:
    def __init__(self, root: str = "/sys/class/power_supply"):
        self.root = Path(root)

    def _battery_dir(self) -> Path | None:
        if not self.root.exists():
            return None
        for entry in sorted(self.root.iterdir()):
            if (_read_text(entry / "type") or "").lower() == "battery" and (entry / "capacity").exists():
                return entry
        return None

    def read(self) -> BatteryReading | None:
        directory = self._battery_dir()
        if directory is None:
            return None
        capacity = _read_number(directory / "capacity")
        if capacity is None:
            return None
        status = (_read_text(directory / "status") or "").lower()
        charging = None if not status or status == "unknown" else status in ("charging", "full")
        temp = _read_number(directory / "temp")
        full = _read_number(directory / "charge_full")
        design = _read_number(directory / "charge_full_design")
        health = round(100 * full / design, 1) if full and design else None
        return BatteryReading(
            percent=max(0.0, min(100.0, capacity)),
            charging=charging,
            temperature_c=None if temp is None else temp / 10.0,
            health_pct=health,
            source="sysfs",
        )


class TermuxBattery:
    def __init__(self, command: tuple[str, ...] = ("termux-battery-status",), cache_s: float = 5.0):
        self.command = command
        self.cache_s = cache_s
        self._cached: tuple[float, BatteryReading | None] | None = None

    def read(self) -> BatteryReading | None:
        now = time.monotonic()
        if self._cached and now - self._cached[0] < self.cache_s:
            return self._cached[1]
        try:
            result = subprocess.run(self.command, capture_output=True, text=True, timeout=8)
            data = json.loads(result.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            reading = None
        else:
            status = str(data.get("status", "")).upper()
            reading = BatteryReading(
                percent=float(data.get("percentage", 0)),
                charging=status in ("CHARGING", "FULL"),
                temperature_c=data.get("temperature"),
                source="termux",
            )
        self._cached = (now, reading)
        return reading


class FakeBattery:
    def __init__(self, percent: float = 80.0, charging: bool = False, drain_per_hour: float = 0.0, clock: Callable[[], float] = time.monotonic, temperature_c: float | None = 33.0):
        self.percent = float(percent)
        self.charging = charging
        self.drain_per_hour = drain_per_hour
        self.temperature_c = temperature_c
        self._clock = clock
        self._last = clock()

    def set(self, percent: float | None = None, charging: bool | None = None) -> None:
        if percent is not None:
            self.percent = float(percent)
        if charging is not None:
            self.charging = charging

    def read(self) -> BatteryReading:
        now = self._clock()
        hours = max(0.0, now - self._last) / 3600.0
        self._last = now
        if self.charging:
            self.percent = min(100.0, self.percent + 30.0 * hours)
        else:
            self.percent = max(0.0, self.percent - self.drain_per_hour * hours)
        return BatteryReading(round(self.percent, 1), self.charging, self.temperature_c, None, "fake")


class NoBattery:
    def read(self) -> None:
        return None


class SysfsThermal:
    def __init__(self, root: str = "/sys/class/thermal"):
        self.root = Path(root)

    def read(self) -> float | None:
        if not self.root.exists():
            return None
        readings = []
        for zone in self.root.glob("thermal_zone*"):
            value = _read_number(zone / "temp")
            if value is not None and 0 < value < 150_000:
                readings.append(value / 1000.0 if value > 200 else value)
        return max(readings) if readings else None


class BatteryTemperature:
    def __init__(self, battery: BatterySource):
        self.battery = battery

    def read(self) -> float | None:
        reading = self.battery.read()
        return None if reading is None else reading.temperature_c


class FakeValue:
    def __init__(self, value: float | None):
        self.value = value

    def read(self) -> float | None:
        return self.value


class NoValue:
    def read(self) -> None:
        return None


class FakeImu:
    def __init__(self, accel=(0.0, 0.0, 9.81), gyro=(0.0, 0.0, 0.0)):
        self.accel = tuple(accel)
        self.gyro = tuple(gyro)

    def read(self) -> ImuReading:
        return ImuReading(self.accel, self.gyro)


class NoImu:
    def read(self) -> None:
        return None


def _battery_from(config: dict, monotonic: Callable[[], float]) -> BatterySource:
    kind = config.get("kind", "auto")
    if kind == "sysfs":
        return SysfsBattery(config.get("path", "/sys/class/power_supply"))
    if kind == "termux":
        return TermuxBattery()
    if kind == "fake":
        return FakeBattery(config.get("percent", 80), config.get("charging", False), config.get("drain_per_hour", 0.0), monotonic, config.get("temperature_c", 33.0))
    if kind == "none":
        return NoBattery()
    if kind == "android":
        from ..android.sensors import AndroidBattery

        return AndroidBattery()
    sysfs = SysfsBattery()
    if sysfs.read() is not None:
        return sysfs
    termux = TermuxBattery()
    if termux.read() is not None:
        return termux
    return NoBattery()


def _temperature_from(config: dict, battery: BatterySource) -> ValueSource:
    kind = config.get("kind", "auto")
    if kind == "sysfs":
        return SysfsThermal(config.get("path", "/sys/class/thermal"))
    if kind == "battery":
        return BatteryTemperature(battery)
    if kind == "fake":
        return FakeValue(config.get("celsius", 33.0))
    if kind == "none":
        return NoValue()
    if kind == "android":
        from ..android.sensors import AndroidTemperature

        return AndroidTemperature(battery)
    thermal = SysfsThermal()
    return thermal if thermal.read() is not None else BatteryTemperature(battery)


def _light_from(config: dict) -> ValueSource:
    if config.get("kind") == "fake":
        return FakeValue(config.get("lux", 150.0))
    if config.get("kind") == "android":
        from ..android.sensors import AndroidLight

        return AndroidLight()
    return NoValue()


def _imu_from(config: dict) -> ImuSource:
    if config.get("kind") == "fake":
        return FakeImu(config.get("accel", (0.0, 0.0, 9.81)), config.get("gyro", (0.0, 0.0, 0.0)))
    if config.get("kind") == "android":
        from ..android.sensors import AndroidImu

        return AndroidImu()
    return NoImu()


class PhoneSensors:
    def __init__(self, battery: BatterySource, temperature: ValueSource, light: ValueSource, imu: ImuSource, clock: Callable[[], float] = time.time):
        self.battery = battery
        self.temperature = temperature
        self.light = light
        self.imu = imu
        self._clock = clock
        self._failed: set[str] = set()

    @classmethod
    def from_config(cls, config: dict, clock: Callable[[], float] = time.time, monotonic: Callable[[], float] = time.monotonic) -> "PhoneSensors":
        battery = _battery_from(config.get("battery", {}), monotonic)
        return cls(
            battery,
            _temperature_from(config.get("temperature", {}), battery),
            _light_from(config.get("light", {})),
            _imu_from(config.get("imu", {})),
            clock,
        )

    def _guard(self, name: str, read: Callable):
        try:
            return read()
        except Exception as error:
            if name not in self._failed:
                self._failed.add(name)
                log.warning("phone %s sensor failed: %s", name, error)
            return None

    def read(self) -> SensorSnapshot:
        return SensorSnapshot(
            at=self._clock(),
            battery=self._guard("battery", self.battery.read),
            temperature_c=self._guard("temperature", self.temperature.read),
            light_lux=self._guard("light", self.light.read),
            imu=self._guard("imu", self.imu.read),
        )
