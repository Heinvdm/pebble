import json
from dataclasses import dataclass, field
from pathlib import Path

from .checks import CPM, TILT_DEG, safe_setting

PROFILE_DIR = Path(__file__).resolve().parent.parent / "profiles"
SPEED_MM_S = (20, 400)
TRACK_MM = (100.0, 250.0)


def _clamp(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def _cpm(value) -> float:
    cpm = float(value)
    return cpm if CPM[0] <= cpm <= CPM[1] else 0.0


def _tilt(tilt: dict) -> tuple[float, float, float]:
    low = _clamp(float(tilt.get("min", -35.0)), *TILT_DEG)
    high = _clamp(float(tilt.get("max", 90.0)), *TILT_DEG)
    if low >= high:
        low, high = float(TILT_DEG[0]), float(TILT_DEG[1])
    return low, high, _clamp(float(tilt.get("rest", 8.0)), low, high)


def _firmware_settings(raw: dict) -> dict:
    return {str(k): str(v) for k, v in raw.items() if safe_setting(str(k), v)}


def resolve_profile(name_or_path: str, kind: str) -> Path:
    candidate = Path(name_or_path)
    if candidate.suffix == ".json" and candidate.exists():
        return candidate
    named = PROFILE_DIR / f"{kind}_{name_or_path}.json"
    if named.exists():
        return named
    raise FileNotFoundError(f"no {kind} profile {name_or_path!r} (looked in {PROFILE_DIR})")


@dataclass(frozen=True)
class BodyProfile:
    name: str
    link: str = "tcp:pebble.local:7777"
    sensors: dict = field(default_factory=dict)
    max_power: int = 600
    max_speed_mm_s: int = 250
    max_move_seconds: float = 3.0
    wheel_track_mm: float = 165.0
    cpm: float = 0.0
    tilt_min: float = -35.0
    tilt_max: float = 90.0
    tilt_rest: float = 8.0
    screen: dict = field(default_factory=dict)
    firmware_settings: dict = field(default_factory=dict)
    power: dict = field(default_factory=dict)
    eyes: dict = field(default_factory=dict)
    voice: dict = field(default_factory=dict)
    hearing: dict = field(default_factory=dict)
    safety: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "BodyProfile":
        drive = data.get("drive", {})
        tilt_min, tilt_max, tilt_rest = _tilt(data.get("tilt", {}))
        return cls(
            name=str(data.get("name", "unnamed")),
            link=str(data.get("link", "tcp:pebble.local:7777")),
            sensors=dict(data.get("sensors", {})),
            max_power=max(50, min(1000, int(drive.get("max_power", 600)))),
            max_speed_mm_s=int(_clamp(int(drive.get("max_speed_mm_s", 250)), *SPEED_MM_S)),
            max_move_seconds=max(0.2, min(10.0, float(drive.get("max_move_seconds", 3.0)))),
            wheel_track_mm=_clamp(float(drive.get("wheel_track_mm", 165.0)), *TRACK_MM),
            cpm=_cpm(drive.get("cpm", 0.0)),
            tilt_min=tilt_min,
            tilt_max=tilt_max,
            tilt_rest=tilt_rest,
            screen=dict(data.get("screen", {})),
            firmware_settings=_firmware_settings(data.get("firmware_settings", {})),
            power=dict(data.get("power", {})),
            eyes=dict(data.get("eyes", {})),
            voice=dict(data.get("voice", {})),
            hearing=dict(data.get("hearing", {})),
            safety=dict(data.get("safety", {})),
        )

    @classmethod
    def load(cls, path: Path) -> "BodyProfile":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
