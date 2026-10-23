import math
from dataclasses import dataclass, field

FRONT_MM = 100.0
REAR_MM = 80.0
DROP_MM = 90.0
CASTER_MM = 75.0
CORNER_Y = 60.0
TRACK_MM = 165.0
WHEEL_Y = TRACK_MM / 2
DOWN_ON_TABLE = 45
SENSOR_RANGE = 1200
ALL_WALLS = frozenset({"x_min", "x_max", "y_min", "y_max"})
TAG_Z_MM = 120.0
LIFTED_MM = 100.0
LOW_MM = 40.0
ROLL_FRICTION = 1.4
ROLL_STOP_MM_S = 15.0
PUSH_GAIN = 2.2
RAIL_ZONE_MM = 160.0
RAIL_Y_MM = 55.0
RAIL_HEADING = 0.4
RAIL_SIDE_GAIN = 0.45
RAIL_TURN_GAIN = 0.005


@dataclass(frozen=True)
class Table:
    x_min: float = 0.0
    x_max: float = 1000.0
    y_min: float = -400.0
    y_max: float = 400.0
    height_mm: float = 750.0
    walls: frozenset = frozenset({"x_min", "y_max"})


@dataclass
class Pose:
    x: float
    y: float
    heading: float


@dataclass
class SimPerson:
    name: str
    x: float
    y: float
    speed_mm_s: float = 120.0
    radius_mm: float = 150.0
    height_mm: float = 1700.0
    width_mm: float = 400.0
    track: int = 0
    home: bool = True
    route: list = field(default_factory=list)
    facing: float | None = None
    arm: str = "down"
    arm_side: str = "right"
    point_at: tuple | None = None
    hiding: bool = False
    holding: str | None = None
    hold_at: tuple = (350.0, 900.0)
    posture: str | None = None
    undressed: bool = False
    nod: bool = False

    def walk_to(self, *points: tuple[float, float], speed_mm_s: float | None = None) -> None:
        self.route = [(float(x), float(y)) for x, y in points]
        if speed_mm_s is not None:
            self.speed_mm_s = speed_mm_s

    @property
    def walking(self) -> bool:
        return bool(self.route)

    def step(self, dt: float) -> None:
        budget = self.speed_mm_s * dt
        while self.route and budget > 0:
            tx, ty = self.route[0]
            dx, dy = tx - self.x, ty - self.y
            gap = math.hypot(dx, dy)
            if gap <= budget:
                self.x, self.y = tx, ty
                budget -= gap
                self.route.pop(0)
            else:
                self.x += dx / gap * budget
                self.y += dy / gap * budget
                budget = 0.0


@dataclass
class SimThing(SimPerson):
    width_mm: float = 300.0
    height_mm: float = 300.0
    depth_mm: float = 300.0
    fast: str | None = None
    slow: str | None = None
    animal: bool = False
    speed_mm_s: float = 150.0
    roam: list = field(default_factory=list)
    roamed: int = 0
    z_mm: float = 0.0
    pushable: bool = False
    vx: float = 0.0
    vy: float = 0.0
    held_by: str | None = None
    print_id: str | None = None

    def __post_init__(self):
        self.radius_mm = min(self.width_mm, self.depth_mm) / 2.0
        if self.print_id is None:
            self.print_id = self.name

    @property
    def rolling(self) -> bool:
        return abs(self.vx) > 0.0 or abs(self.vy) > 0.0

    def step(self, dt: float) -> None:
        if self.held_by is not None:
            return
        if self.rolling:
            self.x += self.vx * dt
            self.y += self.vy * dt
            fade = math.exp(-ROLL_FRICTION * dt)
            self.vx, self.vy = self.vx * fade, self.vy * fade
            if math.hypot(self.vx, self.vy) < ROLL_STOP_MM_S:
                self.vx = self.vy = 0.0
            return
        if not self.route and self.roam:
            self.route = [self.roam[self.roamed % len(self.roam)]]
            self.roamed += 1
        super().step(dt)


def room(width_mm: float = 4000.0, depth_mm: float = 3000.0) -> Table:
    return Table(0.0, width_mm, -depth_mm / 2, depth_mm / 2, 0.0, ALL_WALLS)


@dataclass(frozen=True)
class StepResult:
    left_mm: float
    right_mm: float
    bump: str | None


@dataclass(frozen=True)
class AirZone:
    x: float
    y: float
    radius_mm: float
    temperature_c: float
    humidity_pct: float
    gas_ohm: float = 120000.0


@dataclass
class World:
    table: Table = field(default_factory=Table)
    pose: Pose = field(default_factory=lambda: Pose(500.0, 0.0, 0.0))
    dock_y: float = 0.0
    jam: list = field(default_factory=lambda: [False, False])
    fallen: bool = False
    people: list = field(default_factory=list)
    things: list = field(default_factory=list)
    tag_hidden: bool = False
    climate: list = field(default_factory=list)

    def air_at(self, x: float, y: float) -> dict | None:
        inside = [zone for zone in self.climate if math.hypot(zone.x - x, zone.y - y) <= zone.radius_mm]
        if not inside:
            return None
        zone = min(inside, key=lambda z: math.hypot(z.x - x, z.y - y))
        return {"temperature_c": zone.temperature_c, "humidity_pct": zone.humidity_pct, "gas_ohm": zone.gas_ohm}

    def person(self, name: str) -> SimPerson | None:
        return next((p for p in self.people if p.name == name), None)

    def thing(self, name: str) -> SimThing | None:
        return next((t for t in self.things if t.name == name), None)

    def _bodies(self) -> list:
        out = []
        for body in self.people + self.things:
            if not body.home:
                continue
            if isinstance(body, SimThing) and (body.held_by is not None or body.z_mm > LIFTED_MM or body.pushable or body.height_mm < LOW_MM):
                continue
            out.append(body)
        return out

    def step_people(self, dt: float) -> None:
        for body in self.people + self.things:
            if body.home:
                body.step(dt)
        for person in self.people:
            for thing in self.things:
                if thing.held_by == person.name and person.holding != thing.name:
                    thing.held_by = None
                    thing.z_mm = 0.0
            if person.holding and person.home:
                thing = self.thing(person.holding)
                if thing is not None:
                    self._carry(person, thing)
        self._keep_in(dt)

    def _carry(self, person, thing) -> None:
        facing = person.facing if person.facing is not None else math.atan2(self.pose.y - person.y, self.pose.x - person.x)
        ahead, z = person.hold_at
        thing.held_by = person.name
        thing.vx = thing.vy = 0.0
        thing.x = person.x + ahead * math.cos(facing)
        thing.y = person.y + ahead * math.sin(facing)
        thing.z_mm = z

    def _keep_in(self, dt: float) -> None:
        t = self.table
        for thing in self.things:
            if not thing.rolling:
                continue
            r = thing.radius_mm
            if thing.x - r < t.x_min:
                thing.x, thing.vx = t.x_min + r, abs(thing.vx) * 0.5
            if thing.x + r > t.x_max:
                thing.x, thing.vx = t.x_max - r, -abs(thing.vx) * 0.5
            if thing.y - r < t.y_min:
                thing.y, thing.vy = t.y_min + r, abs(thing.vy) * 0.5
            if thing.y + r > t.y_max:
                thing.y, thing.vy = t.y_max - r, -abs(thing.vy) * 0.5

    def _push(self, pose: Pose, speed_mm_s: float) -> None:
        if speed_mm_s <= 0:
            return
        nose = self.point(FRONT_MM, 0.0, pose)
        c, s = math.cos(pose.heading), math.sin(pose.heading)
        for thing in self.things:
            if not thing.home or not thing.pushable or thing.held_by is not None or thing.z_mm > LIFTED_MM:
                continue
            gap = math.hypot(thing.x - nose[0], thing.y - nose[1])
            if gap < thing.radius_mm:
                thing.x = nose[0] + c * (thing.radius_mm + 2.0)
                thing.y = nose[1] + s * (thing.radius_mm + 2.0)
                thing.vx = c * speed_mm_s * PUSH_GAIN
                thing.vy = s * speed_mm_s * PUSH_GAIN

    def tag(self) -> tuple[float, float, float] | None:
        if "x_min" not in self.table.walls or self.tag_hidden:
            return None
        return self.table.x_min, self.dock_y, TAG_Z_MM

    def charger(self) -> tuple[float, float] | None:
        if "x_min" not in self.table.walls:
            return None
        return self.table.x_min + 50.0, self.dock_y

    def _rails(self, pose: Pose, distance: float) -> Pose:
        if distance >= 0 or "x_min" not in self.table.walls:
            return pose
        rear = self.point(-REAR_MM, 0.0, pose)
        heading = math.atan2(math.sin(pose.heading), math.cos(pose.heading))
        if rear[0] - self.table.x_min > RAIL_ZONE_MM or abs(rear[1] - self.dock_y) > RAIL_Y_MM or abs(heading) > RAIL_HEADING:
            return pose
        moved = abs(distance)
        side = self.dock_y - rear[1]
        shift = math.copysign(min(abs(side), moved * RAIL_SIDE_GAIN), side)
        turn = -math.copysign(min(abs(heading), moved * RAIL_TURN_GAIN), heading)
        return Pose(pose.x, pose.y + shift, pose.heading + turn)

    def _people_hit(self, x0: float, y0: float, dx: float, dy: float) -> float:
        best = math.inf
        for person in self._bodies():
            fx, fy = person.x - x0, person.y - y0
            along = fx * dx + fy * dy
            if along < 0:
                continue
            off = fx * dy - fy * dx
            if abs(off) > person.radius_mm:
                continue
            best = min(best, along - math.sqrt(person.radius_mm**2 - off**2))
        return best

    def _touches_person(self, x: float, y: float) -> bool:
        return any(math.hypot(body.x - x, body.y - y) < body.radius_mm for body in self._bodies())

    def point(self, ahead: float, side: float = 0.0, pose: Pose | None = None) -> tuple[float, float]:
        p = pose or self.pose
        c, s = math.cos(p.heading), math.sin(p.heading)
        return p.x + ahead * c - side * s, p.y + ahead * s + side * c

    def on_table(self, x: float, y: float) -> bool:
        t = self.table
        return t.x_min <= x <= t.x_max and t.y_min <= y <= t.y_max

    def _beyond_wall(self, x: float, y: float) -> bool:
        t = self.table
        return (
            ("x_min" in t.walls and x < t.x_min)
            or ("x_max" in t.walls and x > t.x_max)
            or ("y_min" in t.walls and y < t.y_min)
            or ("y_max" in t.walls and y > t.y_max)
        )

    def down_mm(self) -> int:
        x, y = self.point(DROP_MM)
        if self.on_table(x, y):
            return DOWN_ON_TABLE
        drop = DOWN_ON_TABLE + self.table.height_mm
        return int(drop) if drop <= SENSOR_RANGE else -1

    def front_mm(self) -> int:
        x0, y0 = self.point(FRONT_MM)
        dx, dy = math.cos(self.pose.heading), math.sin(self.pose.heading)
        t = self.table
        best = math.inf
        for side in t.walls:
            if side in ("x_min", "x_max"):
                line = t.x_min if side == "x_min" else t.x_max
                if abs(dx) < 1e-9:
                    continue
                distance = (line - x0) / dx
                hit = y0 + distance * dy
                if distance >= 0 and t.y_min <= hit <= t.y_max:
                    best = min(best, distance)
            else:
                line = t.y_min if side == "y_min" else t.y_max
                if abs(dy) < 1e-9:
                    continue
                distance = (line - y0) / dy
                hit = x0 + distance * dx
                if distance >= 0 and t.x_min <= hit <= t.x_max:
                    best = min(best, distance)
        if self.people or self.things:
            best = min(best, max(0.0, self._people_hit(x0, y0, dx, dy)))
        return int(best) if best <= SENSOR_RANGE else -1

    def docked(self) -> bool:
        if "x_min" not in self.table.walls:
            return False
        x, y = self.point(-REAR_MM)
        heading = math.atan2(math.sin(self.pose.heading), math.cos(self.pose.heading))
        return abs(x - self.table.x_min) <= 6.0 and abs(y - self.dock_y) <= 15.0 and abs(heading) <= 0.2

    def _blocked(self, x: float, y: float) -> bool:
        return self._beyond_wall(x, y) or (bool(self.people or self.things) and self._touches_person(x, y))

    def _front_contact(self, pose: Pose) -> str | None:
        left = self._blocked(*self.point(FRONT_MM - 15, CORNER_Y, pose))
        centre = self._blocked(*self.point(FRONT_MM, 0.0, pose))
        right = self._blocked(*self.point(FRONT_MM - 15, -CORNER_Y, pose))
        if centre or (left and right):
            return "B"
        if left:
            return "L"
        if right:
            return "R"
        return None

    def _rear_contact(self, pose: Pose) -> bool:
        return any(self._beyond_wall(*self.point(-REAR_MM, side, pose)) for side in (-CORNER_Y, 0.0, CORNER_Y))

    def _side_contact(self, pose: Pose) -> bool:
        return any(self._beyond_wall(*self.point(0.0, side, pose)) for side in (-WHEEL_Y, WHEEL_Y))

    def step(self, dt: float, left_mm_s: float, right_mm_s: float) -> StepResult:
        if self.fallen or dt <= 0:
            return StepResult(0.0, 0.0, None)
        left = 0.0 if self.jam[0] else left_mm_s * dt
        right = 0.0 if self.jam[1] else right_mm_s * dt
        if left == 0.0 and right == 0.0:
            return StepResult(0.0, 0.0, None)
        distance = (left + right) / 2
        turn = (right - left) / TRACK_MM
        middle = self.pose.heading + turn / 2
        candidate = Pose(
            self.pose.x + distance * math.cos(middle),
            self.pose.y + distance * math.sin(middle),
            self.pose.heading + turn,
        )
        self._push(candidate, distance / dt if dt > 0 else 0.0)
        candidate = self._rails(candidate, distance)
        bump = self._front_contact(candidate)
        if bump is not None:
            return StepResult(0.0, 0.0, bump)
        if self._rear_contact(candidate) or self._side_contact(candidate):
            return StepResult(0.0, 0.0, None)
        self.pose = candidate
        supports = (self.point(0.0), self.point(CASTER_MM), self.point(0.0, WHEEL_Y), self.point(0.0, -WHEEL_Y))
        if not all(self.on_table(x, y) for x, y in supports):
            self.fallen = True
        return StepResult(left, right, None)
