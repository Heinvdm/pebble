import math

from ..respect import PLANT, SMALL, life_kind
from ..seams.sight import SeenPerson, SeenThing, Sight
from ..things.words import canonical, matches
from .kit import Kit
from .motion import Wheels, leave_dock, turn_by, wrap_deg

PERSON_WIDTH_M = 0.40
CAMERA_BEHIND_FRONT_M = 0.02
FRONT_RANGE_MM = 1200
FRONT_CONE_DEG = 12.0
MATCH_DEG = 30.0
SIGHT_AGE_S = 0.8
SCAN_STEP_DEG = 40.0
SCAN_PAUSE_S = 0.6
ASPECT = 0.75
CAMERA_HEIGHT_M = {"front": 0.14, "rear": 0.15}
THING_SCORE = 0.35
ANIMAL_GAP_M = 0.8
ANIMAL_SLOW_M = 1.5
ANIMAL_CONE_DEG = 35.0
ROOMY_ANIMALS = frozenset({"dog", "puppy"})
ROOMY_GAP_M = 1.2
ROOMY_SLOW_M = 2.0
LIFE_GAP_M = {SMALL: 0.3, PLANT: 0.4}
LIFE_SLOW_M = {SMALL: 0.8, PLANT: 0.6}
SMALL_WIDTH_M = 0.03


def animal_gap(label: str) -> float:
    return ROOMY_GAP_M if canonical(label) in ROOMY_ANIMALS else ANIMAL_GAP_M


def animal_slow(label: str) -> float:
    return ROOMY_SLOW_M if canonical(label) in ROOMY_ANIMALS else ANIMAL_SLOW_M


def life_gap(label: str) -> float | None:
    return LIFE_GAP_M.get(life_kind(label))


def life_slow(label: str) -> float:
    return LIFE_SLOW_M.get(life_kind(label), 0.0)


def view_cone_deg(fov_h_deg: float | None) -> float:
    try:
        half = float(fov_h_deg) / 2.0
    except (TypeError, ValueError):
        return ANIMAL_CONE_DEG
    return max(ANIMAL_CONE_DEG, half) if math.isfinite(half) else ANIMAL_CONE_DEG


def camera_fov_deg(eyes, profile, camera: str = "front") -> float | None:
    cameras = getattr(eyes, "cameras", None)
    values = cameras.get(camera) if isinstance(cameras, dict) else None
    if not isinstance(values, dict):
        values = (getattr(profile, "eyes", None) or {}).get(camera)
    try:
        return float(values["fov_h_deg"])
    except (TypeError, KeyError, ValueError):
        return None
WIDTHS_M = {
    "ball": 0.2,
    "chair": 0.5,
    "armchair": 0.8,
    "couch": 1.8,
    "cat": 0.45,
    "dog": 0.7,
    "cup": 0.08,
    "plant": 0.35,
    "plant pot": 0.3,
    "slipper": 0.25,
    "jandal": 0.25,
    "shoe": 0.28,
    "bed": 1.5,
    "table": 1.2,
    "tv": 1.0,
    "bottle": 0.08,
    "book": 0.2,
    "bag": 0.4,
    "teddy bear": 0.3,
    "key": 0.08,
    "phone": 0.08,
    "remote control": 0.05,
    "flower": 0.15,
    "snail": 0.04,
    "slug": 0.06,
    "worm": 0.08,
    "spider": 0.04,
    "small moving thing": 0.04,
}
DEFAULT_WIDTH_M = 0.3


def body_bearing(bearing_deg: float, camera: str) -> float:
    if camera == "rear":
        return wrap_deg(180.0 - bearing_deg)
    return wrap_deg(-bearing_deg)


def person_gap_m(person: SeenPerson, sight: Sight, front_mm: int | None) -> float:
    half = math.radians(max(1.0, sight.fov_h_deg)) / 2.0
    seen = PERSON_WIDTH_M / (2.0 * max(person.width_frac, 1e-3) * math.tan(half)) - CAMERA_BEHIND_FRONT_M
    if sight.camera == "front" and front_mm is not None and 0 <= front_mm < FRONT_RANGE_MM and abs(person.bearing_deg) <= FRONT_CONE_DEG:
        measured = front_mm / 1000.0
        if abs(measured - seen) < 0.5 or measured < seen:
            return measured
    return max(0.0, seen)


def thing_gap_m(thing: SeenThing, sight: Sight, tilt_deg: float | None, front_mm: int | None) -> float:
    half = math.radians(max(1.0, sight.fov_h_deg)) / 2.0
    scale = math.tan(half) * ASPECT
    pitch = (tilt_deg or 0.0) * (-1.0 if sight.camera == "rear" else 1.0)
    low = math.tan(math.radians(thing.elevation_deg)) - thing.height_frac * scale
    clipped = low <= -scale * 0.98
    bottom = math.degrees(math.atan(low)) + pitch
    width = _width_of(thing.label)
    seen = width / (2.0 * max(thing.width_frac, 1e-3) * math.tan(half))
    if not clipped and bottom < -1.5:
        seen = CAMERA_HEIGHT_M.get(sight.camera, 0.14) / math.tan(math.radians(-bottom))
    seen = max(0.0, seen - CAMERA_BEHIND_FRONT_M)
    if sight.camera == "front" and front_mm is not None and 0 <= front_mm < FRONT_RANGE_MM and abs(thing.bearing_deg) <= FRONT_CONE_DEG:
        measured = front_mm / 1000.0
        if abs(measured - seen) < 0.3:
            return measured
    return seen


def thing_lift_m(thing: SeenThing, sight: Sight, tilt_deg: float | None) -> float:
    half = math.radians(max(1.0, sight.fov_h_deg)) / 2.0
    scale = math.tan(half) * ASPECT
    pitch = (tilt_deg or 0.0) * (-1.0 if sight.camera == "rear" else 1.0)
    low = math.tan(math.radians(thing.elevation_deg)) - thing.height_frac * scale
    if low <= -scale * 0.98:
        return 0.0
    bottom = math.atan(low) + math.radians(pitch)
    width = _width_of(thing.label)
    gap = width / (2.0 * max(thing.width_frac, 1e-3) * math.tan(half))
    return max(0.0, CAMERA_HEIGHT_M.get(sight.camera, 0.14) + gap * math.tan(bottom))


def _width_of(label: str) -> float:
    found = WIDTHS_M.get(canonical(label))
    if found is not None:
        return found
    return SMALL_WIDTH_M if life_kind(label) == SMALL else DEFAULT_WIDTH_M


def life_ahead(sight: Sight | None, tilt_deg: float | None, exempt: str = "") -> list[tuple[SeenThing, float]]:
    if sight is None:
        return []
    out = []
    cone = view_cone_deg(sight.fov_h_deg)
    for thing in sight.things:
        if life_kind(thing.label) not in LIFE_GAP_M or thing.score < THING_SCORE or abs(body_bearing(thing.bearing_deg, sight.camera)) > cone:
            continue
        if exempt and (matches(exempt, thing.label) or matches(thing.label, exempt)):
            continue
        out.append((thing, thing_gap_m(thing, sight, tilt_deg, None)))
    return out


def animals_ahead(sight: Sight | None, tilt_deg: float | None) -> list[tuple[SeenThing, float]]:
    if sight is None:
        return []
    out = []
    cone = view_cone_deg(sight.fov_h_deg)
    for thing in sight.things:
        if thing.animal and life_kind(thing.label) not in LIFE_GAP_M and thing.score >= THING_SCORE and abs(body_bearing(thing.bearing_deg, sight.camera)) <= cone:
            out.append((thing, thing_gap_m(thing, sight, tilt_deg, None)))
    return out


class ThingTracker:
    def __init__(self, label: str):
        self.label = label
        self.track: int | None = None
        self.bearing: float | None = None
        self.last_at: float | None = None

    def reset(self) -> None:
        self.track = None
        self.bearing = None

    def turned(self, degrees: float) -> None:
        if self.bearing is not None:
            self.bearing = wrap_deg(self.bearing - degrees)

    def pick(self, sight: Sight | None) -> SeenThing | None:
        if sight is None:
            return None
        found = [t for t in sight.things if t.score >= THING_SCORE and matches(self.label, t.label)]
        if not found:
            return None
        chosen = None
        if self.track is not None:
            same = [t for t in found if t.track == self.track]
            chosen = same[0] if same else None
        if chosen is None and self.bearing is not None:
            near = sorted(found, key=lambda t: abs(wrap_deg(body_bearing(t.bearing_deg, sight.camera) - self.bearing)))
            if abs(wrap_deg(body_bearing(near[0].bearing_deg, sight.camera) - self.bearing)) <= MATCH_DEG:
                chosen = near[0]
        if chosen is None and self.bearing is None:
            chosen = max(found, key=lambda t: (t.score, t.height_frac * t.width_frac))
        if chosen is None:
            return None
        self.track = chosen.track if chosen.track is not None else self.track
        self.bearing = body_bearing(chosen.bearing_deg, sight.camera)
        self.last_at = sight.at
        return chosen


class Tracker:
    def __init__(self):
        self.track: int | None = None
        self.bearing: float | None = None
        self.last_at: float | None = None

    def reset(self) -> None:
        self.track = None
        self.bearing = None

    def turned(self, degrees: float) -> None:
        if self.bearing is not None:
            self.bearing = wrap_deg(self.bearing - degrees)

    def pick(self, sight: Sight | None) -> SeenPerson | None:
        if sight is None or not sight.people:
            return None
        people = list(sight.people)
        chosen = None
        if self.track is not None:
            same = [p for p in people if p.track == self.track]
            if same:
                chosen = same[0]
        if chosen is None and self.bearing is not None:
            near = sorted(people, key=lambda p: abs(wrap_deg(body_bearing(p.bearing_deg, sight.camera) - self.bearing)))
            if abs(wrap_deg(body_bearing(near[0].bearing_deg, sight.camera) - self.bearing)) <= MATCH_DEG:
                chosen = near[0]
        if chosen is None and self.bearing is None:
            chosen = max(people, key=lambda p: (p.face, p.height_frac * p.width_frac, p.score))
        if chosen is None:
            return None
        self.track = chosen.track if chosen.track is not None else self.track
        self.bearing = body_bearing(chosen.bearing_deg, sight.camera)
        self.last_at = sight.at
        return chosen


def look(kit: Kit, tracker: Tracker) -> tuple[SeenPerson | None, Sight | None]:
    sight = kit.eyes.latest(SIGHT_AGE_S)
    return tracker.pick(sight), sight


async def scan(kit: Kit, wheels: Wheels, tracker: Tracker, max_deg: float = 360.0, step_deg: float = SCAN_STEP_DEG) -> tuple[SeenPerson | None, Sight | None, str | None]:
    turned = 0.0
    tracker.reset()
    await leave_dock(kit, wheels)
    while True:
        await kit.pace.sleep(SCAN_PAUSE_S)
        person, sight = look(kit, tracker)
        if person is not None:
            return person, sight, None
        if turned >= max_deg - 1.0:
            return None, sight, None
        step = min(step_deg, max_deg - turned)
        done, problem = await turn_by(kit, wheels, step)
        turned += abs(done) if done else step
        if problem:
            return None, sight, problem
