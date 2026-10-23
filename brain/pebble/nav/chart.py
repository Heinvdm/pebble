import math
import uuid
from dataclasses import dataclass, field

from ..alive.rooms import MEMBERS, SIGNS
from ..things.words import canonical
from .grid import Grid
from .walls import Axis

CHARTS = "charts.json"
FORMAT = 1
MAX_CHARTS = 6
MAX_CHUNKS = 500
MAX_PLACES = 80
MAX_SEEN = 120
MAX_PRINTS = 2
PATH_STEP_M = 0.2
PATH_KEEP = 3000
DOOR_WIDTH_M = 1.05
DOOR_SIDE_M = 0.7
DOOR_WIDE_M = 1.5
DOOR_GAP_M = 1.5
CORRIDOR_WIDTH_M = 2.2
CORRIDOR_LONG_M = 3.0
ROOM_GAP_M = 3.5
NEAR_PLACE_M = 0.8
SEEN_MERGE_M = 0.7
HOME = "home"


@dataclass
class Place:
    id: str
    kind: str
    name: str
    x: float
    y: float
    radius: float = 0.5
    heading: float | None = None
    labels: list = field(default_factory=list)
    prints: list = field(default_factory=list)
    visits: int = 1

    def as_dict(self) -> dict:
        out = {"id": self.id, "kind": self.kind, "name": self.name, "x": round(self.x, 2), "y": round(self.y, 2), "radius": round(self.radius, 2), "labels": list(self.labels)[:12], "visits": self.visits}
        if self.heading is not None:
            out["heading"] = round(self.heading, 2)
        if self.prints:
            out["prints"] = [[round(v, 3) for v in vec] for vec in self.prints[:MAX_PRINTS]]
        return out

    @classmethod
    def from_dict(cls, data: dict) -> "Place | None":
        try:
            return cls(
                str(data["id"]),
                str(data.get("kind") or "spot"),
                str(data.get("name") or ""),
                float(data["x"]),
                float(data["y"]),
                float(data.get("radius") or 0.5),
                None if data.get("heading") is None else float(data["heading"]),
                [str(v) for v in data.get("labels") or []],
                [tuple(float(v) for v in vec) for vec in data.get("prints") or [] if isinstance(vec, list)],
                int(data.get("visits") or 1),
            )
        except (KeyError, TypeError, ValueError):
            return None


class Chart:
    def __init__(self, id: str, name: str = "", created: str = "", home: bool = False):
        self.id = id
        self.name = name
        self.created = created
        self.last = created
        self.home = home
        self.grid = Grid()
        self.axis = Axis()
        self.places: list[Place] = []
        self.edges: dict[tuple[str, str], float] = {}
        self.seen: dict[str, list[list[float]]] = {}
        self.careful: list[list] = []
        self.path: list[tuple[float, float]] = []
        self.at_place: str | None = None
        self.since_place_m = 0.0
        self.narrow_from: tuple[float, float, float] | None = None
        self.narrow_best: tuple[float, float, float] | None = None
        self.narrow_m = 0.0

    def place(self, name: str) -> Place | None:
        key = canonical(name)
        for place in self.places:
            if place.name and (place.name == name or canonical(place.name) == key):
                return place
        return None

    def spots(self) -> list[str]:
        return [p.name for p in self.places if p.kind in ("spot", "start") and p.name]

    def add_place(self, kind: str, name: str, x: float, y: float, radius: float = 0.5, heading: float | None = None) -> Place:
        place = Place(uuid.uuid4().hex[:8], kind, name, x, y, radius, heading)
        self.places.append(place)
        if len(self.places) > MAX_PLACES:
            spare = [p for p in self.places if p.kind in ("doorway", "corridor")]
            victim = min(spare or self.places, key=lambda p: p.visits)
            self.drop_place(victim.id)
        self._link(place)
        return place

    def drop_place(self, place_id: str) -> None:
        self.places = [p for p in self.places if p.id != place_id]
        self.edges = {k: v for k, v in self.edges.items() if place_id not in k}
        if self.at_place == place_id:
            self.at_place = None

    def _link(self, place: Place) -> None:
        if self.at_place is not None and self.at_place != place.id:
            key = tuple(sorted((self.at_place, place.id)))
            length = max(0.1, self.since_place_m)
            self.edges[key] = min(self.edges.get(key, math.inf), length)
        self.at_place = place.id
        self.since_place_m = 0.0

    def remember_spot(self, name: str, x: float, y: float, kind: str = "spot") -> Place:
        old = self.place(name)
        if old is not None:
            old.x, old.y = x, y
            old.visits += 1
            return old
        return self.add_place(kind, name, x, y, 0.4)

    def moved(self, x: float, y: float, heading: float) -> None:
        if self.path:
            step = math.hypot(x - self.path[-1][0], y - self.path[-1][1])
            if step < PATH_STEP_M:
                return
            self.since_place_m += step
        self.path.append((x, y))
        del self.path[:-PATH_KEEP]
        self._doorway(x, y, heading)
        for place in self.places:
            if math.hypot(place.x - x, place.y - y) <= max(NEAR_PLACE_M, place.radius) and place.id != self.at_place:
                place.visits += 1
                self._link(place)
                break

    def width_at(self, x: float, y: float, heading: float, reach: float = DOOR_WIDE_M) -> tuple[float, bool, bool]:
        sides = []
        for sign in (1.0, -1.0):
            angle = heading + sign * math.pi / 2.0
            found = None
            step = self.grid.res
            d = step
            while d <= reach:
                if self.grid.occupied_at(x + d * math.cos(angle), y + d * math.sin(angle)):
                    found = d
                    break
                d += step
            sides.append(found)
        left, right = sides
        width = (left if left is not None else reach) + (right if right is not None else reach)
        return width, left is not None, right is not None

    def _doorway(self, x: float, y: float, heading: float) -> None:
        width, left, right = self.width_at(x, y, heading)
        walled = left and right
        if walled and width <= DOOR_WIDTH_M:
            if self.narrow_from is None:
                self.narrow_from = (x, y, width)
                self.narrow_m = 0.0
                self.narrow_best = (x, y, width)
            else:
                self.narrow_m = math.hypot(x - self.narrow_from[0], y - self.narrow_from[1])
                if width < self.narrow_best[2]:
                    self.narrow_best = (x, y, width)
            return
        if self.narrow_from is None:
            return
        bx, by, best = self.narrow_best
        long = self.narrow_m
        self.narrow_from = self.narrow_best = None
        kind = "doorway" if long <= DOOR_GAP_M else "corridor"
        if any(p.kind == kind and math.hypot(p.x - bx, p.y - by) < 1.0 for p in self.places):
            return
        self.add_place(kind, "", bx, by, max(0.3, best / 2.0), heading)

    def saw(self, label: str, x: float, y: float) -> None:
        kind = canonical(label)
        spots = self.seen.setdefault(kind, [])
        for spot in spots:
            if math.hypot(spot[0] - x, spot[1] - y) <= SEEN_MERGE_M:
                n = spot[2]
                spot[0] = (spot[0] * n + x) / (n + 1)
                spot[1] = (spot[1] * n + y) / (n + 1)
                spot[2] = min(n + 1, 50)
                return
        spots.append([x, y, 1])
        spots.sort(key=lambda s: -s[2])
        del spots[6:]
        if len(self.seen) > MAX_SEEN:
            weakest = min(self.seen, key=lambda k: sum(s[2] for s in self.seen[k]))
            del self.seen[weakest]

    def name_rooms(self) -> list[Place]:
        made = []
        sure = {kind: [s for s in spots if s[2] >= 3] for kind, spots in self.seen.items()}
        for name, options in SIGNS.items():
            for needed in options:
                if not all(sure.get(kind) for kind in needed):
                    continue
                anchor = sure[needed[0]][0]
                members = []
                for kind in MEMBERS[name]:
                    for spot in sure.get(kind, []):
                        if math.hypot(spot[0] - anchor[0], spot[1] - anchor[1]) <= 3.0:
                            members.append((kind, spot))
                if not members:
                    continue
                cx = sum(s[0] for _, s in members) / len(members)
                cy = sum(s[1] for _, s in members) / len(members)
                spread = max(math.hypot(s[0] - cx, s[1] - cy) for _, s in members)
                old = next((p for p in self.places if p.kind == "room" and p.name == name and math.hypot(p.x - cx, p.y - cy) < ROOM_GAP_M), None)
                if old is not None:
                    old.x, old.y, old.radius = cx, cy, max(1.2, spread + 0.8)
                    old.labels = sorted({k for k, _ in members})
                    continue
                place = Place(uuid.uuid4().hex[:8], "room", name, cx, cy, max(1.2, spread + 0.8), None, sorted({k for k, _ in members}))
                self.places.append(place)
                made.append(place)
                break
        return made

    def place_at(self, x: float, y: float) -> str | None:
        best = None
        for place in self.places:
            if place.kind not in ("room", "spot", "start", "dock") or not place.name:
                continue
            gap = math.hypot(place.x - x, place.y - y) - place.radius
            if gap <= 0.5 and (best is None or gap < best[0]):
                best = (gap, place.name)
        return best[1] if best else None

    def to_dict(self) -> dict:
        self.grid.prune(MAX_CHUNKS)
        return {
            "id": self.id,
            "name": self.name,
            "home": self.home,
            "created": self.created,
            "last": self.last,
            "grid": self.grid.to_dict(),
            "places": [p.as_dict() for p in self.places],
            "edges": [[a, b, round(v, 2)] for (a, b), v in sorted(self.edges.items())],
            "seen": {k: [[round(s[0], 2), round(s[1], 2), int(s[2])] for s in v] for k, v in sorted(self.seen.items())},
            "axis": None if self.axis.angle is None else round(self.axis.angle, 4),
            "careful": [[round(float(c[0]), 2), round(float(c[1]), 2), str(c[2]), int(c[3])] for c in self.careful],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Chart":
        chart = cls(str(data.get("id") or uuid.uuid4().hex[:8]), str(data.get("name") or ""), str(data.get("created") or ""), bool(data.get("home")))
        chart.last = str(data.get("last") or chart.created)
        chart.grid = Grid.from_dict(data.get("grid") or {})
        if isinstance(data.get("axis"), (int, float)):
            chart.axis.angle = float(data["axis"])
        chart.places = [p for p in (Place.from_dict(d) for d in data.get("places") or [] if isinstance(d, dict)) if p is not None]
        ids = {p.id for p in chart.places}
        for item in data.get("edges") or []:
            try:
                a, b, length = str(item[0]), str(item[1]), float(item[2])
            except (TypeError, ValueError, IndexError):
                continue
            if a in ids and b in ids:
                chart.edges[tuple(sorted((a, b)))] = length
        for kind, spots in (data.get("seen") or {}).items():
            good = [[float(s[0]), float(s[1]), int(s[2])] for s in spots if isinstance(s, list) and len(s) == 3]
            if good:
                chart.seen[str(kind)] = good
        for item in data.get("careful") or []:
            try:
                chart.careful.append([float(item[0]), float(item[1]), str(item[2]), int(item[3])])
            except (TypeError, ValueError, IndexError):
                continue
        return chart


class Charts:
    def __init__(self, store=None, now_text=lambda: ""):
        self.store = store
        self.now_text = now_text
        self.charts: dict[str, Chart] = {}
        self.current: Chart | None = None
        self.dirty = False
        if store is not None:
            data = store.read(CHARTS, {}) or {}
            for raw in data.get("charts") or []:
                if isinstance(raw, dict):
                    chart = Chart.from_dict(raw)
                    self.charts[chart.id] = chart
        if HOME not in self.charts:
            self.charts[HOME] = Chart(HOME, "home", now_text(), True)

    def home(self) -> Chart:
        return self.charts[HOME]

    def use(self, chart: Chart) -> Chart:
        self.current = chart
        chart.last = self.now_text() or chart.last
        self.dirty = True
        return chart

    def visit(self) -> Chart:
        chart = Chart(uuid.uuid4().hex[:8], "", self.now_text(), False)
        self.charts[chart.id] = chart
        others = sorted((c for c in self.charts.values() if not c.home and c is not chart), key=lambda c: c.last)
        while len(self.charts) > MAX_CHARTS and others:
            del self.charts[others.pop(0).id]
        return self.use(chart)

    def save(self) -> bool:
        if self.store is None:
            return False
        data = {"format": FORMAT, "charts": [c.to_dict() for c in sorted(self.charts.values(), key=lambda c: (not c.home, c.last))]}
        self.store.write(CHARTS, data)
        self.dirty = False
        return True
