from dataclasses import dataclass

from ..link.protocol import Air, Flags, Status
from .sensors import AirReading

PACK_EMPTY_MV = 3300
PACK_FULL_MV = 4150


def pack_fraction(pack_mv: int | None) -> float | None:
    if not pack_mv:
        return None
    return max(0.0, min(1.0, (pack_mv - PACK_EMPTY_MV) / (PACK_FULL_MV - PACK_EMPTY_MV)))


@dataclass
class Telemetry:
    status: Status | None = None
    status_at: float | None = None
    link_up: bool = False
    link_label: str = ""
    last_motion_at: float | None = None
    boot_version: str | None = None
    air: AirReading | None = None

    def apply_air(self, message: Air, now: float) -> AirReading:
        self.air = AirReading(
            at=now,
            body_ms=message.ms,
            present=message.present,
            temperature_c=message.temperature_c,
            humidity_pct=message.humidity_pct,
            pressure_pa=message.pressure_pa,
            gas_ohm=message.gas_ohm,
            heated_s=message.heated_s,
        )
        return self.air

    def air_reading(self, now: float, max_age: float | None = None) -> AirReading | None:
        air = self.air
        if air is None or not air.present:
            return None
        if max_age is not None and not air.fresh(now, max_age):
            return None
        return air

    def air_snapshot(self, now: float) -> dict | str | None:
        air = self.air
        if air is None:
            return None
        if not air.present:
            return "no air sensor"
        return {
            "temperature_c": round(air.temperature_c, 1),
            "humidity_pct": round(air.humidity_pct, 1),
            "pressure_hpa": round(air.pressure_hpa, 1),
            "gas_kohm": None if air.gas_ohm is None else round(air.gas_ohm / 1000.0, 1),
            "warming_up": air.warming,
            "age_s": round(air.age(now), 1),
        }

    def apply_status(self, status: Status, now: float) -> None:
        previous = self.status
        if previous is not None and (status.enc_left != previous.enc_left or status.enc_right != previous.enc_right):
            self.last_motion_at = now
        self.status = status
        self.status_at = now

    def fresh(self, now: float, max_age: float = 1.0) -> bool:
        return self.status_at is not None and now - self.status_at <= max_age

    @property
    def docked(self) -> bool:
        return self.status is not None and self.status.dock == 1

    @property
    def pack_mv(self) -> int | None:
        return self.status.pack_mv if self.status else None

    @property
    def tilt(self) -> float | None:
        return self.status.tilt if self.status else None

    @property
    def flags(self) -> Flags:
        return self.status.flags if self.status else Flags.NONE

    def encoders(self) -> tuple[int, int] | None:
        if self.status is None:
            return None
        return self.status.enc_left, self.status.enc_right

    def snapshot(self, now: float) -> dict:
        status = self.status
        if status is None:
            return {"link_up": self.link_up, "status": None, "air": self.air_snapshot(now)}
        return {
            "link_up": self.link_up,
            "age_s": round(now - self.status_at, 2) if self.status_at else None,
            "front_mm": None if status.front_mm < 0 else status.front_mm,
            "down_mm": None if status.down_mm < 0 else status.down_mm,
            "bump": {0: "none", 1: "left", 2: "right", 3: "both"}[status.bump],
            "docked": status.dock == 1,
            "pack_mv": status.pack_mv,
            "pack_pct": None if pack_fraction(status.pack_mv) is None else round(pack_fraction(status.pack_mv) * 100),
            "tilt_deg": status.tilt,
            "encoders": [status.enc_left, status.enc_right],
            "holds": [flag.name.lower() for flag in Flags if flag and flag in status.flags],
            "last_motion_s": None if self.last_motion_at is None else round(now - self.last_motion_at, 1),
            "air": self.air_snapshot(now),
        }
