import math
from dataclasses import dataclass

from ..respect import ANIMAL, PLANT, SMALL, life_kind
from ..things.words import matches
from .geometry import BODY_RADIUS_M, body_angle, wrap

SMALL_ROOM_M = 0.35
URGENT_SMALL_ROOM_M = 0.23
NEAR_SMALL_ROOM_M = 0.25
PLANT_ROOM_M = 0.15
URGENT_PLANT_ROOM_M = 0.05
SMALL_SLOW_M = 0.8
PLANT_SLOW_M = 0.6
SMALL_KEEP_S = 20.0
PLANT_KEEP_S = 120.0
SIDE_RAD = math.radians(70.0)
AHEAD_RAD = math.radians(35.0)
SPARE_M = 0.03
SMALL_SOFT_M = 0.12
PLANT_HALF_M = (0.08, 0.4)
MOVER_MAX_M = 0.08
MOVER_REACH_M = 1.5
MOVER_STEP_M = 0.08
MOVER_WINDOW_S = 4.0
MOVER_FORGET_S = 2.0
RECENT_S = 8.0
BUMP_REACH_M = 0.25
BUMP_SIDE_RAD = math.radians(50.0)
CAREFUL_M = 0.6
CAREFUL_KEEP = 12
MERGE_M = 0.15
MARK_MOVE_M = 0.1
MOVING = "small moving thing"


@dataclass
class Spot:
    x: float
    y: float
    at: float
    label: str
    kind: str
    radius: float = 0.0
    marked: tuple | None = None
    told: bool = False


def _width(thing, sight) -> float:
    return thing.width_frac * 2.0 * (thing.floor_m or 0.0) * math.tan(math.radians(max(1.0, sight.fov_h_deg)) / 2.0)


class LifeWatch:
    def __init__(self):
        self.spots: list[Spot] = []
        self.movers: dict = {}

    def kind_of(self, thing) -> str | None:
        kind = life_kind(thing.label)
        if kind in (SMALL, PLANT):
            return kind
        return None

    def saw(self, sight, now: float, cx: float, cy: float, th: float, grid=None) -> None:
        kept = []
        for spot in self.spots:
            if now - spot.at <= (PLANT_KEEP_S if spot.kind == PLANT else SMALL_KEEP_S):
                kept.append(spot)
            elif grid is not None and spot.marked is not None and spot.kind == SMALL:
                grid.clear_hazards(spot.marked[0], spot.marked[1], SMALL_SOFT_M)
        self.spots = kept
        self.movers = {key: item for key, item in self.movers.items() if now - item[3] <= MOVER_FORGET_S}
        if sight is None or getattr(sight, "camera", "front") != "front":
            return
        for thing in sight.things:
            if thing.floor_m is None or thing.floor_bearing_deg is None:
                continue
            kind = self.kind_of(thing)
            if kind is None and (thing.animal or life_kind(thing.label) == ANIMAL):
                continue
            angle = th + body_angle(thing.floor_bearing_deg, sight.camera)
            px, py = cx + thing.floor_m * math.cos(angle), cy + thing.floor_m * math.sin(angle)
            width = _width(thing, sight)
            label = thing.label
            if kind is None:
                if not self._moving(thing, px, py, width, now):
                    continue
                kind, label = SMALL, MOVING
            radius = 0.0
            if kind == PLANT:
                radius = min(PLANT_HALF_M[1], max(PLANT_HALF_M[0], width / 2.0))
                px, py = px + radius * math.cos(angle), py + radius * math.sin(angle)
            spot = self._merge(px, py, now, label, kind, radius)
            if grid is not None and (spot.marked is None or math.hypot(spot.x - spot.marked[0], spot.y - spot.marked[1]) > MARK_MOVE_M):
                grid.hazard(spot.x, spot.y, spot.label, now, SMALL_SOFT_M if kind == SMALL else spot.radius)
                spot.marked = (spot.x, spot.y)

    def _moving(self, thing, px: float, py: float, width: float, now: float) -> bool:
        if width > MOVER_MAX_M or (thing.floor_m or 0.0) > MOVER_REACH_M:
            return False
        key = thing.track if thing.track is not None else thing.label
        before = self.movers.get(key)
        if before is None or now - before[2] > MOVER_WINDOW_S:
            self.movers[key] = (px, py, now, now)
            return False
        self.movers[key] = (before[0], before[1], before[2], now)
        return math.hypot(px - before[0], py - before[1]) >= MOVER_STEP_M

    def _merge(self, x: float, y: float, now: float, label: str, kind: str, radius: float) -> Spot:
        for spot in self.spots:
            if spot.kind == kind and (math.hypot(spot.x - x, spot.y - y) <= max(MERGE_M, spot.radius) or (spot.label == label and kind == SMALL and math.hypot(spot.x - x, spot.y - y) <= 0.3)):
                spot.x, spot.y, spot.at, spot.label = x, y, now, label
                spot.radius = max(spot.radius * 0.8, radius) if kind == PLANT else radius
                return spot
        spot = Spot(x, y, now, label, kind, radius)
        self.spots.append(spot)
        return spot

    def room(self, spot: Spot, urgent: bool = False, exempt: str = "") -> float:
        aimed = bool(exempt) and (matches(exempt, spot.label) or matches(spot.label, exempt))
        if spot.kind == SMALL:
            if urgent:
                return URGENT_SMALL_ROOM_M
            return NEAR_SMALL_ROOM_M if aimed else SMALL_ROOM_M
        if urgent or aimed:
            return spot.radius + URGENT_PLANT_ROOM_M + BODY_RADIUS_M
        return spot.radius + PLANT_ROOM_M + BODY_RADIUS_M

    def obstacles(self, exempt: str = "", urgent: bool = False) -> list[tuple[float, float, float]]:
        return [(s.x, s.y, max(0.05, self.room(s, urgent, exempt) - BODY_RADIUS_M)) for s in self.spots]

    def guard(self, x: float, y: float, th: float, urgent: bool = False, exempt: str = "") -> tuple[str | None, str | None]:
        slow = block = None
        for spot in self.spots:
            bearing = abs(wrap(math.atan2(spot.y - y, spot.x - x) - th))
            if bearing > SIDE_RAD:
                continue
            gap = math.hypot(spot.x - x, spot.y - y)
            near = (SMALL_SLOW_M if spot.kind == SMALL else PLANT_SLOW_M + spot.radius)
            if gap < near:
                slow = slow or spot.label
            aimed = bool(exempt) and (matches(exempt, spot.label) or matches(spot.label, exempt))
            if not urgent and not aimed and bearing <= AHEAD_RAD and gap < self.room(spot, urgent, exempt) + SPARE_M:
                block = block or spot.label
        return slow, block

    def passed(self, x: float, y: float, now: float) -> list[Spot]:
        found = []
        for spot in self.spots:
            if spot.kind != SMALL or spot.told or now - spot.at > RECENT_S:
                continue
            if math.hypot(spot.x - x, spot.y - y) <= BODY_RADIUS_M:
                spot.told = True
                found.append(spot)
        return found

    def bumped(self, x: float, y: float, th: float, now: float) -> Spot | None:
        for spot in self.spots:
            if spot.kind != PLANT or now - spot.at > PLANT_KEEP_S:
                continue
            bearing = abs(wrap(math.atan2(spot.y - y, spot.x - x) - th))
            if bearing <= BUMP_SIDE_RAD and math.hypot(spot.x - x, spot.y - y) - spot.radius <= BODY_RADIUS_M + BUMP_REACH_M:
                return spot
        return None


def careful_near(careful: list, x: float, y: float) -> str | None:
    for item in careful:
        if math.hypot(item[0] - x, item[1] - y) <= CAREFUL_M:
            return str(item[2])
    return None


def remember_careful(careful: list, x: float, y: float, label: str) -> None:
    for item in careful:
        if math.hypot(item[0] - x, item[1] - y) <= CAREFUL_M / 2.0:
            item[3] = int(item[3]) + 1
            item[2] = label
            return
    careful.insert(0, [round(x, 2), round(y, 2), label, 1])
    del careful[CAREFUL_KEEP:]
