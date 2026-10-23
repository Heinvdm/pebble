import math
from dataclasses import dataclass, field

from ...sim.world import CASTER_MM, CORNER_Y, DROP_MM, FRONT_MM, REAR_MM, SENSOR_RANGE, WHEEL_Y, Pose, SimPerson, SimThing, StepResult, Table, World
from ..geometry import point_segment, ray_circle, ray_segment

WALL_MM = 50.0
MAKE_WAY_MM = 900.0
DOWN_FLOOR = 45
TOF_SPREAD_DEG = 8.0
CATCH_SPEED_MM_S = 130.0
CATCH_ANGLE_DEG = 35.0
CATCH_S = 0.6
LEFT_SCALE = 0.996
SIDE_POINTS = ((0.0, WHEEL_Y + 10.0), (0.0, -WHEEL_Y - 10.0), (-REAR_MM + 10.0, CORNER_Y), (-REAR_MM + 10.0, -CORNER_Y), (FRONT_MM - 40.0, WHEEL_Y), (FRONT_MM - 40.0, -WHEEL_Y))


@dataclass
class Strip:
    x1: float
    y1: float
    x2: float
    y2: float
    height_mm: float = 15.0
    width_mm: float = 60.0


@dataclass
class Walker(SimPerson):
    stops: dict = field(default_factory=dict)
    waiting_until: float = -math.inf
    plan: list = field(default_factory=list)
    leg: int = 0
    loop: bool = False
    print_id: str = ""
    talking_until: float = -math.inf
    t: float = 0.0
    hold: bool = False
    robot: object = None
    polite: bool = True
    guided: bool = False

    def __post_init__(self):
        if not self.print_id:
            self.print_id = self.name

    def go(self, points: list, speed_mm_s: float, stops: dict | None = None, loop: bool = False) -> None:
        self.plan = [(float(x), float(y)) for x, y in points]
        self.leg = 0
        self.speed_mm_s = speed_mm_s
        self.stops = dict(stops or {})
        self.loop = loop
        self.route = [self.plan[0]] if self.plan else []

    def step(self, dt: float) -> None:
        self.t += dt
        if self.hold or self.t < self.waiting_until:
            return
        if self.guided and not self.route:
            return
        if not self.route and self.plan:
            reached = self.leg
            pause = self.stops.pop(reached, 0.0) if not self.loop else self.stops.get(reached, 0.0)
            self.leg += 1
            if self.leg >= len(self.plan):
                if self.loop:
                    self.leg = 0
                else:
                    self.plan = []
                    return
            self.route = [self.plan[self.leg]]
            if pause > 0:
                self.waiting_until = self.t + pause
                return
        if self.route:
            tx, ty = self.route[0]
            if math.hypot(tx - self.x, ty - self.y) > 1.0:
                self.facing = math.atan2(ty - self.y, tx - self.x)
            if self.polite and self.robot is not None and self._make_way(dt, tx, ty):
                return
        super().step(dt)

    def _make_way(self, dt: float, tx: float, ty: float) -> bool:
        rx, ry = self.robot()
        gap = math.hypot(rx - self.x, ry - self.y)
        if gap > MAKE_WAY_MM:
            return False
        going = math.atan2(ty - self.y, tx - self.x)
        toward = math.atan2(ry - self.y, rx - self.x)
        off = math.atan2(math.sin(toward - going), math.cos(toward - going))
        if abs(off) > math.radians(75.0):
            return False
        side = going - math.copysign(math.radians(60.0), off)
        step = self.speed_mm_s * dt
        self.x += step * math.cos(side)
        self.y += step * math.sin(side)
        return True

    @property
    def done(self) -> bool:
        return not self.plan and not self.route


class Building(World):
    def __init__(self, table: Table, segments: list, boxes: list, strips: list, cliffs: list, pose: Pose, people=None, things=None):
        super().__init__(table=table, pose=pose, people=list(people or []), things=list(things or []))
        self.segments = list(segments)
        self.boxes = list(boxes)
        self.strips = list(strips)
        self.cliffs = list(cliffs)
        for x0, y0, x1, y1 in self.boxes:
            for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
                self.segments.append((a[0], a[1], b[0], b[1], "furniture"))
        self.jam_until = -math.inf
        self.clock = 0.0
        self.catches = 0
        self.bumps = 0
        self.side_scrapes = 0
        self._bumping = False
        self.carry: list = []
        self.carry_speed = 1000.0
        self.carried = False
        self.yaw_rate = 0.0

    def _in_box(self, x: float, y: float) -> bool:
        return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in self.boxes)

    def _near_segment(self, x: float, y: float, glass: bool = True) -> bool:
        for ax, ay, bx, by, kind in self.segments:
            if not glass and kind == "glass":
                continue
            if point_segment(x, y, ax, ay, bx, by) < WALL_MM / 2.0:
                return True
        return False

    def in_cliff(self, x: float, y: float) -> bool:
        return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in self.cliffs)

    def _beyond_wall(self, x: float, y: float) -> bool:
        return super()._beyond_wall(x, y) or self._near_segment(x, y) or self._in_box(x, y)

    def _blocked(self, x: float, y: float) -> bool:
        return self._beyond_wall(x, y) or (bool(self.people or self.things) and self._touches_person(x, y))

    def on_table(self, x: float, y: float) -> bool:
        return super().on_table(x, y) and not self.in_cliff(x, y)

    def down_mm(self) -> int:
        if self.carried:
            return -1
        x, y = self.point(DROP_MM + 15.0)
        if self.in_cliff(x, y):
            return -1
        for strip in self.strips:
            if point_segment(x, y, strip.x1, strip.y1, strip.x2, strip.y2) <= strip.width_mm / 2.0:
                return int(DOWN_FLOOR - strip.height_mm)
        return DOWN_FLOOR

    def _cast(self, x0: float, y0: float, angle: float) -> float:
        dx, dy = math.cos(angle), math.sin(angle)
        best = math.inf
        for ax, ay, bx, by, kind in self.segments:
            if kind == "glass":
                continue
            hit = ray_segment(x0, y0, dx, dy, ax, ay, bx, by)
            if hit is not None and hit < best:
                best = hit
        t = self.table
        for side in t.walls:
            if side == "x_min":
                hit = ray_segment(x0, y0, dx, dy, t.x_min, t.y_min, t.x_min, t.y_max)
            elif side == "x_max":
                hit = ray_segment(x0, y0, dx, dy, t.x_max, t.y_min, t.x_max, t.y_max)
            elif side == "y_min":
                hit = ray_segment(x0, y0, dx, dy, t.x_min, t.y_min, t.x_max, t.y_min)
            else:
                hit = ray_segment(x0, y0, dx, dy, t.x_min, t.y_max, t.x_max, t.y_max)
            if hit is not None and hit < best:
                best = hit
        for body in self._bodies():
            if isinstance(body, SimThing) and body.height_mm < 40.0:
                continue
            hit = ray_circle(x0, y0, dx, dy, body.x, body.y, body.radius_mm)
            if hit is not None and hit < best:
                best = hit
        return best

    def front_mm(self) -> int:
        if self.carried:
            return -1
        x0, y0 = self.point(FRONT_MM)
        best = min(self._cast(x0, y0, self.pose.heading + math.radians(a)) for a in (0.0, -TOF_SPREAD_DEG, TOF_SPREAD_DEG))
        return int(best) if best <= SENSOR_RANGE else -1

    def sees(self, x0: float, y0: float, x1: float, y1: float) -> bool:
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length < 1.0:
            return True
        dx, dy = dx / length, dy / length
        for ax, ay, bx, by, kind in self.segments:
            if kind != "wall":
                continue
            hit = ray_segment(x0, y0, dx, dy, ax, ay, bx, by)
            if hit is not None and hit < length - 1.0:
                return False
        return True

    def _side_blocked(self, pose: Pose) -> bool:
        return any(self._beyond_wall(*self.point(ahead, side, pose)) for ahead, side in SIDE_POINTS)

    def _catch(self, candidate: Pose, speed: float) -> bool:
        cx, cy = self.point(CASTER_MM, 0.0, candidate)
        for strip in self.strips:
            if point_segment(cx, cy, strip.x1, strip.y1, strip.x2, strip.y2) <= strip.width_mm / 2.0:
                px, py = self.point(CASTER_MM)
                if point_segment(px, py, strip.x1, strip.y1, strip.x2, strip.y2) <= strip.width_mm / 2.0:
                    return False
                along = math.atan2(strip.y2 - strip.y1, strip.x2 - strip.x1)
                normal = along + math.pi / 2.0
                off = abs(math.degrees(math.atan2(math.sin(candidate.heading - normal), math.cos(candidate.heading - normal))))
                off = min(off, 180.0 - off)
                return speed > CATCH_SPEED_MM_S or off > CATCH_ANGLE_DEG
        return False

    def step(self, dt: float, left_mm_s: float, right_mm_s: float) -> StepResult:
        self.clock += dt
        before = self.pose.heading
        if self.carried:
            self._carried(dt)
            self.yaw_rate = (self.pose.heading - before) / dt if dt > 0 else 0.0
            return StepResult(0.0, 0.0, None)
        if self.clock < self.jam_until and left_mm_s + right_mm_s > 0:
            self.yaw_rate = 0.0
            return StepResult(0.0, 0.0, None)
        speed = abs(left_mm_s + right_mm_s) / 2.0
        old = Pose(self.pose.x, self.pose.y, self.pose.heading)
        result = super().step(dt, left_mm_s * LEFT_SCALE, right_mm_s)
        if result.left_mm or result.right_mm:
            if self._side_blocked(self.pose):
                self.pose = old
                self.side_scrapes += 1
                self.yaw_rate = 0.0
                return StepResult(0.0, 0.0, None)
            if left_mm_s + right_mm_s > 0 and self._catch(self.pose, speed):
                self.pose = old
                self.catches += 1
                self.jam_until = self.clock + CATCH_S
                self.yaw_rate = 0.0
                return StepResult(0.0, 0.0, None)
        self.yaw_rate = (self.pose.heading - before) / dt if dt > 0 else 0.0
        if result.bump and not self._bumping:
            self.bumps += 1
        self._bumping = bool(result.bump)
        return StepResult(result.left_mm / LEFT_SCALE, result.right_mm, result.bump)

    def truth(self):
        from ..grid import Grid, TOP

        grid = Grid()
        items = [seg[:4] for seg in self.segments]
        t = self.table
        items += [(t.x_min, t.y_min, t.x_max, t.y_min), (t.x_max, t.y_min, t.x_max, t.y_max), (t.x_max, t.y_max, t.x_min, t.y_max), (t.x_min, t.y_max, t.x_min, t.y_min)]
        for ax, ay, bx, by in items:
            length = math.hypot(bx - ax, by - ay)
            steps = max(1, int(length / 25.0))
            for i in range(steps + 1):
                px, py = (ax + (bx - ax) * i / steps) / 1000.0, (ay + (by - ay) * i / steps) / 1000.0
                grid.add(*grid.cell(px, py), TOP)
        for x0, y0, x1, y1 in self.cliffs:
            grid.cliff((x0 + x1) / 2000.0, (y0 + y1) / 2000.0, max(x1 - x0, y1 - y0) / 2000.0)
        return grid

    def lift(self, path: list, speed_mm_s: float = 1000.0) -> None:
        self.carried = True
        self.carry = [(float(x), float(y)) for x, y in path]
        self.carry_speed = speed_mm_s

    def _carried(self, dt: float) -> None:
        if not self.carry:
            return
        tx, ty = self.carry[0]
        dx, dy = tx - self.pose.x, ty - self.pose.y
        gap = math.hypot(dx, dy)
        step = self.carry_speed * dt
        if gap <= step:
            self.pose = Pose(tx, ty, self.pose.heading)
            self.carry.pop(0)
            if not self.carry:
                self.carried = False
            return
        heading = math.atan2(dy, dx)
        turn = math.atan2(math.sin(heading - self.pose.heading), math.cos(heading - self.pose.heading))
        self.pose = Pose(self.pose.x + dx / gap * step, self.pose.y + dy / gap * step, self.pose.heading + max(-1.5 * dt, min(1.5 * dt, turn)))


def m(*values: float) -> tuple:
    return tuple(v * 1000.0 for v in values)


def wall(x1, y1, x2, y2, kind="wall"):
    return (*m(x1, y1, x2, y2), kind)


def office(lead_speed: float = 1150.0) -> tuple[Building, Walker, list]:
    segments = [
        wall(0, 7, 2.5, 7), wall(3.5, 7, 9.0, 7), wall(9.9, 7, 21, 7), wall(22.2, 7, 24, 7),
        wall(6, 0, 6, 7), wall(15, 0, 15, 7),
        wall(21, 1, 21, 7), wall(22.2, 1, 22.2, 7), wall(21, 1, 22.2, 1),
        wall(0, 9, 5, 9), wall(5.9, 9, 13, 9), wall(13, 9, 17, 9, "glass"), wall(17, 9, 18, 9), wall(18.9, 9, 24, 9),
        wall(12, 9, 12, 14),
    ]
    boxes = [
        m(0.3, 5.9, 2.1, 6.8),
        m(11.0, 3.0, 12.6, 3.8), m(11.5, 2.3, 12.0, 2.8), m(14.2, 0.2, 14.9, 2.0),
        m(0.2, 12.8, 0.9, 13.8), m(3.0, 11.0, 4.5, 12.0), m(6.0, 13.4, 11.0, 13.9),
        m(19.0, 12.0, 20.5, 12.8), m(22.8, 9.4, 23.8, 13.6),
    ]
    strips = [Strip(*m(9.0, 7.0, 9.9, 7.0), 15.0), Strip(*m(5.0, 9.0, 5.9, 9.0), 10.0)]
    cliffs = [m(0.0, 7.1, 1.2, 8.9)]
    table = Table(0.0, 24000.0, 0.0, 14000.0, 0.0, frozenset({"x_min", "x_max", "y_min", "y_max"}))
    lead = Walker("ina", *m(3.0, 3.2), speed_mm_s=lead_speed, height_mm=1650.0, track=1, print_id="ina")
    route = [m(3.0, 3.2), m(3.0, 6.5), m(3.0, 8.0), m(9.45, 8.0), m(9.45, 6.0), m(10.5, 4.6), m(12.9, 4.6), m(13.2, 2.4), m(10.2, 1.6), m(9.45, 5.5), m(9.45, 8.0), m(21.6, 8.0), m(21.6, 2.0), m(21.6, 8.0), m(18.45, 8.0), m(18.45, 10.5), m(16.5, 9.7), m(13.5, 9.7), m(13.5, 11.5), m(18.6, 11.4), m(18.45, 10.5), m(18.45, 8.0), m(5.45, 8.0), m(5.45, 10.0), m(2.2, 10.4), m(1.3, 12.2)]
    lead.go(route, lead_speed, {7: 6.0, 12: 3.0})
    sam = Walker("sam", *m(20.0, 8.3), speed_mm_s=1200.0, height_mm=1800.0, track=2, print_id="sam")
    sam.go([m(20.0, 8.3), m(4.5, 8.3), m(4.5, 8.4), m(20.0, 8.4)], 1200.0, {1: 8.0, 3: 20.0}, loop=True)
    ana = Walker("ana", *m(16.0, 11.0), speed_mm_s=1000.0, height_mm=1660.0, track=3, print_id="ina-like")
    ana.go([m(16.0, 11.0), m(21.5, 10.0), m(21.5, 12.8), m(16.0, 12.8)], 900.0, {0: 8.0, 2: 8.0}, loop=True)
    mo = Walker("mo", *m(7.5, 11.5), speed_mm_s=0.0, height_mm=1720.0, track=4, print_id="mo")
    things = [
        SimThing("plant pot", *m(5.5, 0.6), width_mm=400.0, depth_mm=400.0, height_mm=500.0, fast="potted plant", slow="plant pot", track=101),
        SimThing("cable", *m(9.4, 5.6), width_mm=600.0, depth_mm=60.0, height_mm=12.0, slow="cable", track=102),
        SimThing("bag", *m(14.0, 7.6), width_mm=400.0, depth_mm=300.0, height_mm=350.0, fast="backpack", slow="bag", track=103),
        SimThing("cat", *m(1.5, 3.5), width_mm=450.0, depth_mm=200.0, height_mm=250.0, fast="cat", animal=True, track=104, speed_mm_s=120.0),
        SimThing("chair", *m(3.7, 10.6), width_mm=450.0, depth_mm=450.0, height_mm=900.0, fast="chair", slow="chair", track=105),
        SimThing("fridge", *m(0.55, 13.3), width_mm=700.0, depth_mm=700.0, height_mm=1800.0, fast="refrigerator", slow="fridge", track=106),
        SimThing("desk", *m(11.8, 3.4), width_mm=1600.0, depth_mm=800.0, height_mm=750.0, fast="dining table", slow="desk", track=107),
    ]
    things[3].roam = [m(1.5, 3.5), m(1.2, 1.0), m(4.5, 1.2), m(4.8, 4.0)]
    for thing in things:
        if thing.name in ("fridge", "desk"):
            thing.home = True
    world = Building(table, segments, boxes, strips, cliffs, Pose(*m(3.0, 2.0), math.pi / 2.0), [lead, sam, ana, mo], things)
    for person in (sam, ana, mo):
        person.robot = lambda: (world.pose.x, world.pose.y)
    lead.polite = False
    return world, lead, route
