import math

from ..seams.sight import FLOOR_OPEN_M, Sight
from .geometry import CAMERA_HEIGHT_M, DROP_AHEAD_M, FRONT_M, TOF_AHEAD_M, TOF_CONE_DEG, ahead, body_angle, camera_spot
from .grid import OCCUPIED, Grid

TOF_RANGE_M = 1.2
TOF_FREE_M = 0.9
TOF_HIT = 40.0
TOF_MISS = 10.0
TOF_EMPTY = 4.0
FLOOR_REACH_M = 2.0
THINGS_REACH_M = 3.0
FLOOR_SLACK_M = 0.06
FLOOR_SLACK_PER_M = 0.04
FLOOR_HIT = 22.0
FLOOR_MISS = 10.0
FLOOR_CAP = 190
TOF_CAP = 205
FLOOR_NEAR_M = 0.35
PEOPLE_SKIP_M = 0.4
FLOOR_DOWN_MM = 32.0
RISE_MM = 9.0
BUMP_SIDE_DEG = 38.0
BUMP_SPREAD_M = 0.05
CLIFF_SPREAD_M = 0.07
HAZARD_RADIUS_M = 0.08
HAZARD_WIDE_M = 1.2
HAZARD_STEP_M = 0.05
GLASS_HALF_M = 0.8
WALL_NEAR_M = 0.25


class Senses:
    def __init__(self, grid: Grid, hazard=None, floor_open_m: float = FLOOR_OPEN_M, floor_reach_m: float = FLOOR_REACH_M):
        self.grid = grid
        self.hazard = hazard or (lambda label: False)
        self.floor_open_m = floor_open_m
        self.floor_reach_m = floor_reach_m
        self.down_base = FLOOR_DOWN_MM
        self.down_seen = 0
        self.floor_rays_seen = 0
        self.rises_seen = 0

    def tof(self, front_mm: int | None, x: float, y: float, heading: float) -> None:
        if front_mm is None:
            return
        ox, oy = ahead(x, y, heading, TOF_AHEAD_M)
        spread = math.radians(TOF_CONE_DEG) / 3.0
        if 0 <= front_mm:
            reach = front_mm / 1000.0
            if reach > TOF_RANGE_M:
                return
            for angle, gain in ((0.0, TOF_MISS), (-spread, TOF_MISS * 0.5), (spread, TOF_MISS * 0.5)):
                ex, ey = ox + reach * math.cos(heading + angle), oy + reach * math.sin(heading + angle)
                self.grid.ray(ox, oy, ex, ey, angle == 0.0, TOF_HIT, gain, TOF_CAP)
        else:
            ex, ey = ox + TOF_FREE_M * math.cos(heading), oy + TOF_FREE_M * math.sin(heading)
            self.grid.ray(ox, oy, ex, ey, False, 0.0, TOF_EMPTY)

    def down(self, down_mm: int | None, x: float, y: float, heading: float, edge_mm: float) -> bool:
        if down_mm is None or down_mm < 0 or down_mm > edge_mm:
            return False
        if self.down_seen < 50:
            self.down_seen += 1
            self.down_base += (down_mm - self.down_base) / self.down_seen
        else:
            self.down_base += 0.01 * (down_mm - self.down_base)
        if self.down_base - down_mm >= RISE_MM:
            px, py = ahead(x, y, heading, DROP_AHEAD_M)
            self.grid.rise(px, py)
            self.rises_seen += 1
            return True
        return False

    def edge(self, x: float, y: float, heading: float) -> None:
        px, py = ahead(x, y, heading, DROP_AHEAD_M)
        self.grid.cliff(px, py, CLIFF_SPREAD_M)

    def contact(self, side: str, x: float, y: float, heading: float) -> tuple[float, float]:
        angle = {"L": BUMP_SIDE_DEG, "R": -BUMP_SIDE_DEG}.get(side, 0.0)
        reach = FRONT_M + 0.03
        return x + reach * math.cos(heading + math.radians(angle)), y + reach * math.sin(heading + math.radians(angle))

    def wall_near(self, side: str, x: float, y: float, heading: float) -> bool:
        px, py = self.contact(side, x, y, heading)
        grid = self.grid
        for cell in grid._disc(px, py, WALL_NEAR_M):
            if cell not in grid.touched and grid.value(*cell) >= OCCUPIED:
                return True
        return False

    def bump(self, side: str, x: float, y: float, heading: float, now: float, unseen: bool = False) -> tuple[float, float]:
        px, py = self.contact(side, x, y, heading)
        self.grid.touch(px, py, now, BUMP_SPREAD_M)
        if unseen:
            across = heading + math.pi / 2.0
            steps = int(GLASS_HALF_M / self.grid.res)
            for i in range(-steps, steps + 1):
                d = i * self.grid.res
                self.grid.touch(px + d * math.cos(across), py + d * math.sin(across), now, self.grid.res * 0.5)
        return px, py

    def looked_clear(self, x: float, y: float, heading: float) -> bool:
        grid = self.grid
        for d in (FRONT_M + 0.05, FRONT_M + 0.1, FRONT_M + 0.15):
            cell = grid.cell(*ahead(x, y, heading, d))
            if grid.value(*cell) >= 128 or cell in grid.touched:
                return False
        return True

    def floor(self, sight: Sight | None, x: float, y: float, heading: float, skip: list[tuple[float, float]] = ()) -> int:
        if sight is None or not sight.floor or sight.camera != "front":
            return 0
        cx, cy, _ = camera_spot(x, y, heading, sight.camera)
        used = 0
        for ray in sight.floor:
            if ray.score <= 0.05 or ray.distance_m <= 0.0:
                continue
            angle = heading + body_angle(ray.bearing_deg, sight.camera)
            c, s = math.cos(angle), math.sin(angle)
            open_ray = ray.distance_m >= self.floor_open_m
            if open_ray:
                reach = self.floor_reach_m
                self.grid.ray(cx, cy, cx + reach * c, cy + reach * s, False, 0.0, FLOOR_MISS * ray.score)
                used += 1
                continue
            if ray.distance_m > self.floor_reach_m + 0.3:
                continue
            reach = ray.distance_m
            hit = reach >= FLOOR_NEAR_M * 0.9
            ex, ey = cx + reach * c, cy + reach * s
            if hit and any(math.hypot(ex - px, ey - py) < PEOPLE_SKIP_M for px, py in skip):
                hit = False
                reach = max(0.0, reach - PEOPLE_SKIP_M)
            clear = max(0.0, reach - FLOOR_SLACK_M - FLOOR_SLACK_PER_M * reach)
            if clear > 0.0:
                self.grid.ray(cx, cy, cx + clear * c, cy + clear * s, False, 0.0, FLOOR_MISS * ray.score)
            if hit:
                self.grid.mark(ex, ey, FLOOR_HIT * ray.score, FLOOR_CAP)
            used += 1
        self.floor_rays_seen += used
        return used

    def floor_things(self, sight: Sight | None, x: float, y: float, heading: float, now: float, exempt=lambda label: False) -> list[tuple[str, float, float]]:
        if sight is None or sight.camera != "front":
            return []
        cx, cy, _ = camera_spot(x, y, heading, sight.camera)
        found = []
        for thing in sight.things:
            if thing.floor_m is None or thing.floor_bearing_deg is None or thing.animal:
                continue
            if thing.floor_m > THINGS_REACH_M or not self.hazard(thing.label) or exempt(thing.label):
                continue
            angle = heading + body_angle(thing.floor_bearing_deg, sight.camera)
            px, py = cx + thing.floor_m * math.cos(angle), cy + thing.floor_m * math.sin(angle)
            width = min(HAZARD_WIDE_M, thing.width_frac * 2.0 * thing.floor_m * math.tan(math.radians(max(1.0, sight.fov_h_deg)) / 2.0))
            across = angle + math.pi / 2.0
            steps = max(0, int(width / 2.0 / HAZARD_STEP_M))
            for i in range(-steps, steps + 1):
                d = i * HAZARD_STEP_M
                self.grid.hazard(px + d * math.cos(across), py + d * math.sin(across), thing.label, now, HAZARD_RADIUS_M)
            found.append((thing.label, px, py))
        return found


def camera_height(camera: str) -> float:
    return CAMERA_HEIGHT_M.get(camera, 0.14)
