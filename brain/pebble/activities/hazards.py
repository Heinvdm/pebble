import math

from ..seams.sight import Sight
from ..things.words import canonical, matches

FLOOR_HAZARDS = frozenset(
    {
        "cable", "extension cord", "wire", "charger", "plug", "plug socket", "lego", "building block", "toy", "toy car",
        "soft toy", "sock", "shoe", "slipper", "boot", "sandal", "flip-flop", "flip flop", "jandal", "dog food", "cat food",
        "marble", "crayon", "puzzle", "towel", "clothes", "rope", "string", "leash", "hose", "bowl", "ball", "teddy bear",
        "book", "bag",
    }
)
CREEP_POSTURES = frozenset({"crouching", "lying"})
LOOK_AHEAD_M = 0.9
HALF_WIDTH_M = 0.11
MARGIN_M = 0.12
STOP_M = 0.25
SLOW_TOP = 0.22
STEER = 0.25
CREEP_TOP = 0.15
CREEP_GAP_M = 2.5
CREEP_SCORE = 0.5
BODY_M = 0.45


def hazard(label: str) -> bool:
    kind = canonical(label)
    return kind in FLOOR_HAZARDS or label in FLOOR_HAZARDS or any(kind.endswith(" " + word) for word in ("toy", "cable", "cord", "shoe", "sock", "bowl"))


def in_path(sight: Sight | None, exempt: str = "") -> list[tuple[str, float, float]]:
    if sight is None or sight.camera != "front":
        return []
    found = []
    for thing in sight.things:
        if thing.floor_m is None or thing.floor_bearing_deg is None or thing.floor_m > LOOK_AHEAD_M or thing.animal or not hazard(thing.label):
            continue
        if exempt and (matches(exempt, thing.label) or matches(thing.label, exempt)):
            continue
        angle = math.radians(-thing.floor_bearing_deg)
        ahead, side = thing.floor_m * math.cos(angle), thing.floor_m * math.sin(angle)
        if ahead > 0.0 and abs(side) < HALF_WIDTH_M + MARGIN_M:
            found.append((thing.label, ahead, side))
    return sorted(found, key=lambda item: item[1])


def steer(sight: Sight | None, forward: float, turn: float, exempt: str = "") -> tuple[float, float, str | None]:
    if forward <= 0.0:
        return forward, turn, None
    ahead = in_path(sight, exempt)
    if not ahead:
        return forward, turn, None
    label, distance, side = ahead[0]
    away = -1.0 if side > 0 else 1.0
    if distance < STOP_M:
        return 0.0, away * STEER * 1.2, label
    return min(forward, SLOW_TOP), turn + away * STEER, label


def rough_gap_m(person, sight: Sight) -> float:
    return BODY_M / (2.0 * max(person.width_frac, 1e-3) * math.tan(math.radians(max(1.0, sight.fov_h_deg)) / 2.0))


def someone_low(sight: Sight | None) -> bool:
    if sight is None:
        return False
    for person in sight.people:
        if person.posture in CREEP_POSTURES and person.posture_score >= CREEP_SCORE and rough_gap_m(person, sight) <= CREEP_GAP_M:
            return True
    return False
