from ..body.sensors import BatteryReading, BatterySource, ImuReading
from .bridge import as_json, number, require


class _Bridged:
    def __init__(self, bridge=None):
        self._bridge = bridge

    def bridge(self):
        return self._bridge if self._bridge is not None else require("the phone's sensors")


class AndroidBattery(_Bridged):
    def read(self) -> BatteryReading | None:
        data = as_json(self.bridge().battery())
        if not isinstance(data, dict):
            return None
        percent = number(data.get("percent"))
        if percent is None or percent < 0:
            return None
        charging = data.get("charging")
        return BatteryReading(
            percent=max(0.0, min(100.0, percent)),
            charging=None if charging is None else bool(charging),
            temperature_c=number(data.get("temperature_c")),
            health_pct=None,
            source="android",
        )


class AndroidTemperature(_Bridged):
    def __init__(self, battery: BatterySource, bridge=None):
        super().__init__(bridge)
        self.battery = battery

    def read(self) -> float | None:
        value = number(self.bridge().temperature())
        if value is not None and -40.0 < value < 150.0:
            return value
        reading = self.battery.read()
        return None if reading is None else reading.temperature_c


class AndroidLight(_Bridged):
    def read(self) -> float | None:
        value = number(self.bridge().light())
        return None if value is None or value < 0 else value


class AndroidImu(_Bridged):
    def read(self) -> ImuReading | None:
        data = as_json(self.bridge().motion())
        if not isinstance(data, dict):
            return None
        accel, gyro = data.get("accel"), data.get("gyro")
        if not isinstance(accel, list) or len(accel) != 3:
            return None
        values = [number(v) for v in accel]
        spins = [number(v) for v in gyro] if isinstance(gyro, list) and len(gyro) == 3 else [0.0, 0.0, 0.0]
        if any(v is None for v in values + spins):
            return None
        return ImuReading(tuple(values), tuple(spins))
