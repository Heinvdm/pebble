import math

from ..eyes.geometry import Box
from ..things.words import canonical

ASPECT = 4.0 / 3.0
STRONG = frozenset({
    "towel", "bath towel", "beach towel", "bathrobe", "robe", "bikini", "bikini top", "swimwear", "swimsuit", "bathing suit",
    "corset", "pantyhose", "stocking", "silk stocking", "leotard", "lingerie", "underwear", "undies", "bra", "brassiere",
})
WEAK = frozenset({"sleepwear", "pyjamas", "pajamas", "nightgown", "nightie", "diaper", "nappy", "hand towel", "face towel", "shower cap", "swim cap", "dressing gown"})
FIXTURES = frozenset({
    "toilet", "toilet bowl", "toilet seat", "shower", "shower curtain", "shower head", "shower door", "bath", "bathtub",
    "bath mat", "bathroom sink", "bathroom mirror", "bathroom cabinet", "towel bar", "bidet", "urinal", "bath heater",
})
BEDS = frozenset({"bed", "bunk bed", "canopy bed", "daybed", "day bed", "infant bed", "hospital bed", "cot", "crib", "cradle"})
REST = BEDS | frozenset({"couch", "sofa", "settee", "futon", "recliner", "hammock"})
EXPOSED_AT = 0.35
BARE_AT = 0.5
THING_SCORE = 0.35
FLAT = 1.4
STILL_DEG = 4.0
SLEEP_S = 90.0
SLEEP_NIGHT_S = 30.0
SLEEP_KEEP_S = 120.0
SPEAKING = 0.4
CLOSE_S = 1.5
NOSES = 0.6
HUG = 0.6
SAME_SIZE = (0.75, 1.33)
POINT_SCORE = 0.3
SAME_FLOOR = 0.15


def word(label: str) -> set[str]:
    raw = " ".join(str(label or "").lower().split())
    return {raw, canonical(raw)}


def box_of(seen, fov_h_deg: float) -> Box:
    t = math.tan(math.radians(max(1.0, fov_h_deg)) / 2.0)
    u = 0.5 + math.tan(math.radians(seen.bearing_deg)) / (2.0 * t)
    v = 0.5 - math.tan(math.radians(seen.elevation_deg)) / (2.0 * t) * ASPECT
    w, h = max(0.0, seen.width_frac), max(0.0, seen.height_frac)
    if hasattr(seen, "posture"):
        top = v - (0.08 if getattr(seen, "face", False) else 0.12) * h
        return Box(u - w / 2.0, top, w, h, seen.score)
    return Box(u - w / 2.0, v - h / 2.0, w, h, seen.score)


def boxes_of(sight) -> tuple[list[Box], list[tuple[str, Box]]]:
    if sight is None:
        return [], []
    people = [box_of(p, sight.fov_h_deg) for p in sight.people]
    things = [(t.label, box_of(t, sight.fov_h_deg)) for t in sight.things if t.lane != "hazard"]
    return people, things


def inside(a: Box, b: Box) -> float:
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1, y1 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    inner = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    small = min(a.w * a.h, b.w * b.h)
    return inner / small if small > 0 else 0.0


def worn(thing: Box, person: Box) -> bool:
    if thing.w < 0.3 * person.w:
        return False
    if not person.x <= thing.cx <= person.x + person.w:
        return False
    return person.y + 0.1 * person.h <= thing.cy <= person.y + 0.85 * person.h


def beside(thing: Box, person: Box) -> bool:
    if abs((thing.y + thing.h) - (person.y + person.h)) > SAME_FLOOR:
        return False
    reach = person.w * 1.5
    return thing.x - reach <= person.x + person.w and person.x - reach <= thing.x + thing.w


def frame_cue(people: list[Box], things: list[tuple[str, Box]], undressed=None, place: str | None = None, night: bool = False) -> str | None:
    if not people:
        return None
    if undressed is not None and undressed[0] >= EXPOSED_AT:
        return "undress"
    named = [(word(label), box) for label, box in things if box.score >= THING_SCORE]
    bathroom = place == "bathroom" or any(words & FIXTURES and any(beside(box, person) for person in people) for words, box in named)
    bedroom = place == "bedroom" or any(words & BEDS and any(beside(box, person) for person in people) for words, box in named)
    if bathroom:
        return "bathroom"
    private = bedroom
    if undressed is not None and undressed[1] >= BARE_AT and (private or night):
        return "undress"
    for words, box in named:
        on = any(worn(box, person) for person in people)
        if on and words & STRONG:
            return "undress"
        if on and words & WEAK and (private or night):
            return "undress"
    return None


def in_bathroom(person, sight) -> bool:
    me = box_of(person, sight.fov_h_deg)
    for thing in sight.things:
        if thing.score >= THING_SCORE and word(thing.label) & FIXTURES and beside(box_of(thing, sight.fov_h_deg), me):
            return True
    return False


def sight_cue(sight, undressed=None, place: str | None = None, night: bool = False) -> str | None:
    if sight is None:
        return None
    return frame_cue(*boxes_of(sight), undressed, place, night)


def _point(person, name: str):
    return next((p for p in person.points if p.name == name and p.score >= POINT_SCORE), None)


def _middle(person, left: str, right: str):
    a, b = _point(person, left), _point(person, right)
    if a is None or b is None:
        return None
    return (a.bearing_deg + b.bearing_deg) / 2.0, (a.elevation_deg + b.elevation_deg) / 2.0


def torso_flat(person) -> bool:
    shoulders = _middle(person, "left_shoulder", "right_shoulder")
    hips = _middle(person, "left_hip", "right_hip")
    if shoulders is None or hips is None:
        return False
    across, up = abs(shoulders[0] - hips[0]), abs(shoulders[1] - hips[1])
    return across > 1.0 and across > FLAT * up


def resting_on(person, sight) -> str | None:
    me = box_of(person, sight.fov_h_deg)
    for thing in sight.things:
        words = word(thing.label)
        if words & REST and thing.score >= THING_SCORE and inside(me, box_of(thing, sight.fov_h_deg)) >= 0.2:
            return canonical(thing.label)
    return None


def reclined(person, sight, place: str | None = None) -> bool:
    lying = person.posture == "lying" or torso_flat(person)
    if not lying:
        return False
    return resting_on(person, sight) is not None or place == "bedroom"


class Sleepers:
    def __init__(self):
        self.tracks: dict = {}
        self.asleep_at = -math.inf
        self.asleep: set = set()

    def update(self, sight, mono: float, night: bool = False, place: str | None = None) -> set:
        if sight is None:
            return self.asleep if mono - self.asleep_at <= SLEEP_KEEP_S else set()
        needed = SLEEP_NIGHT_S if night or place == "bedroom" else SLEEP_S
        seen = set()
        asleep = set()
        for person in sight.people:
            if person.track is None or not reclined(person, sight, place):
                continue
            seen.add(person.track)
            entry = self.tracks.get(person.track)
            if entry is None:
                self.tracks[person.track] = [person.bearing_deg, person.elevation_deg, mono]
                continue
            moved = math.hypot(person.bearing_deg - entry[0], person.elevation_deg - entry[1]) > STILL_DEG
            talking = person.speaking is not None and person.speaking >= SPEAKING
            if moved or talking:
                entry[:] = [person.bearing_deg, person.elevation_deg, mono]
            elif mono - entry[2] >= needed:
                asleep.add(person.track)
        self.tracks = {k: v for k, v in self.tracks.items() if k in seen}
        if asleep:
            self.asleep_at = mono
            self.asleep = asleep
        elif mono - self.asleep_at > SLEEP_KEEP_S:
            self.asleep = set()
        return asleep

    def near(self, mono: float) -> bool:
        return bool(self.asleep) and mono - self.asleep_at <= SLEEP_KEEP_S


def _shoulders(person) -> float | None:
    a, b = _point(person, "left_shoulder"), _point(person, "right_shoulder")
    if a is None or b is None:
        return None
    return math.hypot(a.bearing_deg - b.bearing_deg, a.elevation_deg - b.elevation_deg)


def pair_close(a, b, fov_h_deg: float) -> bool:
    ratio = a.height_frac / b.height_frac if b.height_frac > 0 else 0.0
    if not SAME_SIZE[0] <= ratio <= SAME_SIZE[1]:
        return False
    na, nb = _point(a, "nose"), _point(b, "nose")
    width = max(_shoulders(a) or 0.0, _shoulders(b) or 0.0)
    if na is not None and nb is not None and width > 0:
        if math.hypot(na.bearing_deg - nb.bearing_deg, na.elevation_deg - nb.elevation_deg) <= NOSES * width:
            return True
    return inside(box_of(a, fov_h_deg), box_of(b, fov_h_deg)) >= HUG


class Closeness:
    def __init__(self):
        self.since: float | None = None

    def update(self, sight, mono: float) -> bool:
        people = list(sight.people) if sight is not None else []
        close = len(people) == 2 and pair_close(people[0], people[1], sight.fov_h_deg)
        if not close:
            self.since = None
            return False
        if self.since is None:
            self.since = mono
        return mono - self.since >= CLOSE_S
