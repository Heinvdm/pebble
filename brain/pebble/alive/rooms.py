import math
from dataclasses import dataclass

from ..things.book import ThingBook
from ..things.words import canonical

PLACES = "places.json"
SIGNS = {
    "kitchen": (("fridge",), ("oven",), ("microwave",), ("toaster", "sink"), ("kettle", "sink")),
    "lounge": (("couch", "tv"),),
    "bedroom": (("bed",),),
    "bathroom": (("toilet",),),
    "office": (("desk", "monitor"), ("desk", "laptop"), ("desk", "keyboard"), ("desk", "tv")),
}
MEMBERS = {
    "kitchen": {"fridge", "oven", "microwave", "toaster", "sink", "kettle", "dining table", "table"},
    "lounge": {"couch", "tv", "armchair", "cushion", "rug"},
    "bedroom": {"bed", "pillow", "wardrobe"},
    "bathroom": {"toilet", "sink", "bath", "towel"},
    "office": {"desk", "monitor", "laptop", "keyboard", "computer mouse", "chair"},
}
MIN_RADIUS_M = 1.2
SPREAD_M = 0.8
DRIFT_PER_M = 0.04
BASE_DRIFT_M = 0.05
MOVED_M = 1.0
GATHER_M = 3.0
NEAR_ROOM_M = 1.0


@dataclass(frozen=True)
class Room:
    name: str
    x: float
    y: float
    radius: float
    signs: tuple[str, ...]
    confidence: float

    def as_dict(self) -> dict:
        return {"name": self.name, "x": round(self.x, 2), "y": round(self.y, 2), "radius": round(self.radius, 2), "signs": list(self.signs), "confidence": round(self.confidence, 2)}


def _anchor(thing) -> tuple[float, float, int] | None:
    spots = [s for s in thing.spots if s.placed]
    if not spots:
        return None
    best = max(spots, key=lambda s: (s.count, s.at))
    return best.x, best.y, best.count


class RoomMap:
    def __init__(self, things: ThingBook, odometer=None, store=None):
        self.things = things
        self.odometer = odometer
        self.store = store
        self.rooms: dict[str, Room] = {}
        if store is not None:
            for raw in (store.read(PLACES, {}) or {}).get("places") or []:
                try:
                    room = Room(str(raw["name"]), float(raw["x"]), float(raw["y"]), float(raw["radius"]), tuple(raw.get("signs") or ()), float(raw.get("confidence", 0.5)))
                except (KeyError, TypeError, ValueError):
                    continue
                self.rooms[room.name] = room

    def _where(self) -> dict[str, tuple[float, float, int]]:
        out: dict[str, tuple[float, float, int]] = {}
        for thing in self.things.things.values():
            if thing.animal:
                continue
            kind = canonical(thing.label)
            spot = _anchor(thing)
            if spot is not None and (kind not in out or spot[2] > out[kind][2]):
                out[kind] = spot
        return out

    def update(self) -> list[tuple[str, bool]]:
        seen = self._where()
        found: dict[str, Room] = {}
        for name, options in SIGNS.items():
            for needed in options:
                if all(kind in seen for kind in needed):
                    ax = sum(seen[kind][0] for kind in needed) / len(needed)
                    ay = sum(seen[kind][1] for kind in needed) / len(needed)
                    near = [kind for kind in MEMBERS[name] if kind in seen and math.hypot(seen[kind][0] - ax, seen[kind][1] - ay) <= GATHER_M]
                    cx = sum(seen[kind][0] for kind in near) / len(near)
                    cy = sum(seen[kind][1] for kind in near) / len(near)
                    spread = max(math.hypot(seen[kind][0] - cx, seen[kind][1] - cy) for kind in near)
                    confidence = min(1.0, 0.4 + 0.15 * len(near) + 0.02 * sum(seen[kind][2] for kind in needed))
                    found[name] = Room(name, cx, cy, max(MIN_RADIUS_M, spread + SPREAD_M), tuple(sorted(near)), confidence)
                    break
        fresh = [(name, name not in self.rooms) for name in found if name not in self.rooms or math.hypot(self.rooms[name].x - found[name].x, self.rooms[name].y - found[name].y) > MOVED_M]
        if any(self.rooms.get(name) != room for name, room in found.items()):
            self.rooms.update(found)
            self.save()
        return fresh

    def save(self) -> None:
        if self.store is None:
            return
        data = self.store.read(PLACES, {}) or {}
        data["format"] = data.get("format", 1)
        data["places"] = [room.as_dict() for room in sorted(self.rooms.values(), key=lambda r: r.name)]
        data.setdefault("routes", [])
        self.store.write(PLACES, data)

    def place(self, name: str) -> Room | None:
        return self.rooms.get(canonical(name)) or self.rooms.get(name)

    def drift_m(self) -> float | None:
        odometer = self.odometer
        if odometer is None or not getattr(odometer, "usable", False):
            return None
        return BASE_DRIFT_M + DRIFT_PER_M * getattr(odometer, "travelled_m", 0.0)

    def where_am_i(self) -> str | None:
        odometer = self.odometer
        if odometer is None or not getattr(odometer, "usable", False):
            return None
        x, y, _ = odometer.pose()
        return self.room_at(x, y)

    def room_at(self, x: float, y: float) -> str | None:
        near = [(math.hypot(room.x - x, room.y - y) - room.radius, room.name) for room in self.rooms.values()]
        near = [(gap, name) for gap, name in near if gap <= NEAR_ROOM_M]
        return min(near)[1] if near else None

    def say_where(self) -> str:
        odometer = self.odometer
        if odometer is None or not getattr(odometer, "usable", False):
            return "I'm not sure where I am. I lose track until I've been back on my charger."
        drift = self.drift_m() or 0.0
        room = self.where_am_i()
        x, y, _ = odometer.pose()
        if math.hypot(x, y) < 0.5:
            return "I'm by my charger."
        if room is None:
            known = ", ".join(sorted(self.rooms)) if self.rooms else ""
            tail = f" I know where the {known} is." if known and len(self.rooms) == 1 else (f" I know the {known}." if known else "")
            return f"I'm not sure which room this is.{tail}".strip()
        if drift > 0.6:
            return f"I think this is the {room}, but I've come a long way since I last knew exactly where I was."
        return f"I think this is the {room}."
