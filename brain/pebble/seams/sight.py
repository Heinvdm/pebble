from dataclasses import dataclass, field
from typing import Protocol

CAMERAS = ("front", "rear")
DOCK_TAG_ID = 0
DOCK_TAG_SIZE_M = 0.048
FLOOR_OPEN_M = 9.0
BODY_POINTS = ("nose", "left_eye", "right_eye", "left_ear", "right_ear", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist", "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle")


@dataclass(frozen=True)
class BodyPoint:
    name: str
    bearing_deg: float
    elevation_deg: float
    score: float


@dataclass(frozen=True)
class SeenPerson:
    bearing_deg: float
    elevation_deg: float
    height_frac: float
    width_frac: float
    score: float
    face: bool = False
    track: int | None = None
    points: tuple[BodyPoint, ...] = field(default_factory=tuple)
    facing_deg: float | None = None
    posture: str | None = None
    speaking: float | None = None
    posture_score: float = 0.0


@dataclass(frozen=True)
class SeenTag:
    id: int
    bearing_deg: float
    distance_m: float
    yaw_deg: float
    score: float = 1.0


@dataclass(frozen=True)
class SeenThing:
    label: str
    bearing_deg: float
    elevation_deg: float
    height_frac: float
    width_frac: float
    score: float
    at: float
    lane: str = "fast"
    animal: bool = False
    track: int | None = None
    held: bool = False
    known: str | None = None
    known_score: float = 0.0
    floor_m: float | None = None
    floor_bearing_deg: float | None = None


@dataclass(frozen=True)
class FloorRay:
    bearing_deg: float
    distance_m: float
    score: float


@dataclass(frozen=True)
class Sight:
    at: float
    camera: str
    fov_h_deg: float
    people: tuple[SeenPerson, ...] = field(default_factory=tuple)
    tags: tuple[SeenTag, ...] = field(default_factory=tuple)
    things: tuple[SeenThing, ...] = field(default_factory=tuple)
    floor: tuple[FloorRay, ...] = field(default_factory=tuple)
    floor_at: float | None = None


class Eyes(Protocol):
    available: bool

    def latest(self, max_age_s: float = 0.5) -> Sight | None: ...

    async def use_camera(self, camera: str) -> bool: ...

    def camera(self) -> str | None: ...


class NoEyes:
    available = False

    def latest(self, max_age_s: float = 0.5) -> Sight | None:
        return None

    async def use_camera(self, camera: str) -> bool:
        return False

    def camera(self) -> str | None:
        return None
