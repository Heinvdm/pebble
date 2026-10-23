import heapq
import math

from .geometry import BODY_RADIUS_M
from .grid import Grid

PLAN_RES_M = 0.10
MARGIN_M = 2.5
MARGINS = (2.5, 6.0, 12.0)
MAX_NODES = 60000
UNKNOWN_COST = 2.5
NEAR_WALL_COST = 1.5
SQRT2 = math.sqrt(2.0)


class Coarse:
    def __init__(self, grid: Grid, box: tuple[float, float, float, float], now: float | None = None, radius: float = BODY_RADIUS_M + 0.02, res: float = PLAN_RES_M):
        self.grid = grid
        self.res = res
        x0, y0, x1, y1 = box
        self.ix0, self.iy0 = math.floor(x0 / res), math.floor(y0 / res)
        self.ix1, self.iy1 = math.floor(x1 / res), math.floor(y1 / res)
        self.blocked: set[tuple[int, int]] = set()
        self.near: set[tuple[int, int]] = set()
        fine = grid.cell(x0, y0), grid.cell(x1, y1)
        reach = int(math.ceil(radius / res))
        halo = reach + 2
        near_offsets, block_offsets = [], []
        for dx in range(-halo, halo + 1):
            for dy in range(-halo, halo + 1):
                gap = math.hypot(dx * res, dy * res)
                if gap <= radius + res * 0.5:
                    block_offsets.append((dx, dy))
                elif gap <= radius + 0.15:
                    near_offsets.append((dx, dy))
        hits = set()
        for fx, fy in grid.blocked_cells(fine[0][0] - 4, fine[0][1] - 4, fine[1][0] + 4, fine[1][1] + 4, now):
            px, py = grid.centre(fx, fy)
            hits.add((math.floor(px / res), math.floor(py / res)))
        for cx, cy in hits:
            for dx, dy in block_offsets:
                self.blocked.add((cx + dx, cy + dy))
            for dx, dy in near_offsets:
                self.near.add((cx + dx, cy + dy))

    def cell(self, x: float, y: float) -> tuple[int, int]:
        return math.floor(x / self.res), math.floor(y / self.res)

    def centre(self, cell: tuple[int, int]) -> tuple[float, float]:
        return (cell[0] + 0.5) * self.res, (cell[1] + 0.5) * self.res

    def inside(self, cell: tuple[int, int]) -> bool:
        return self.ix0 <= cell[0] <= self.ix1 and self.iy0 <= cell[1] <= self.iy1

    def cost(self, cell: tuple[int, int], known_only: bool) -> float | None:
        if cell in self.blocked or not self.inside(cell):
            return None
        x, y = self.centre(cell)
        known = self.grid.known(*self.grid.cell(x, y))
        if not known and known_only:
            return None
        cost = 1.0 if known else UNKNOWN_COST
        if cell in self.near:
            cost += NEAR_WALL_COST
        return cost

    def clear_line(self, a: tuple[float, float], b: tuple[float, float], known_only: bool = False) -> bool:
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        steps = max(1, int(length / (self.res * 0.5)))
        for i in range(steps + 1):
            t = i / steps
            cell = self.cell(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if cell in self.blocked:
                return False
            if known_only and not self.grid.known(*self.grid.cell(*self.centre(cell))):
                return False
        return True


def box_around(points: list[tuple[float, float]], margin: float = MARGIN_M) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin


def nearest_open(coarse: Coarse, cell: tuple[int, int], reach: int = 4) -> tuple[int, int] | None:
    if cell not in coarse.blocked:
        return cell
    best = None
    for dx in range(-reach, reach + 1):
        for dy in range(-reach, reach + 1):
            other = (cell[0] + dx, cell[1] + dy)
            if other not in coarse.blocked and coarse.inside(other):
                gap = dx * dx + dy * dy
                if best is None or gap < best[0]:
                    best = (gap, other)
    return best[1] if best else None


def astar(coarse: Coarse, start: tuple[float, float], goal: tuple[float, float], known_only: bool = False) -> list[tuple[float, float]] | None:
    s = nearest_open(coarse, coarse.cell(*start))
    g = nearest_open(coarse, coarse.cell(*goal))
    if s is None or g is None:
        return None
    open_set = [(0.0, 0, s)]
    came: dict = {s: None}
    best = {s: 0.0}
    counter = 0
    while open_set:
        _, _, current = heapq.heappop(open_set)
        if current == g:
            break
        if len(came) > MAX_NODES:
            return None
        base = best[current]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nxt = (current[0] + dx, current[1] + dy)
                step = coarse.cost(nxt, known_only)
                if step is None:
                    continue
                if dx and dy:
                    if coarse.cost((current[0] + dx, current[1]), known_only) is None or coarse.cost((current[0], current[1] + dy), known_only) is None:
                        continue
                    step *= SQRT2
                total = base + step
                if total < best.get(nxt, math.inf):
                    best[nxt] = total
                    came[nxt] = current
                    h = math.hypot(g[0] - nxt[0], g[1] - nxt[1])
                    counter += 1
                    heapq.heappush(open_set, (total + h, counter, nxt))
    if g not in came:
        return None
    cells = []
    node = g
    while node is not None:
        cells.append(node)
        node = came[node]
    cells.reverse()
    points = [start] + [coarse.centre(c) for c in cells[1:-1]] + [goal]
    return pull(coarse, points)


def pull(coarse: Coarse, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) <= 2:
        return points
    out = [points[0]]
    i = 0
    while i < len(points) - 1:
        j = len(points) - 1
        while j > i + 1 and not coarse.clear_line(points[i], points[j]):
            j -= 1
        out.append(points[j])
        i = j
    return out


def plan(grid: Grid, start: tuple[float, float], goal: tuple[float, float], now: float | None = None, known_only: bool = False, extra: list[tuple[float, float]] = ()) -> list[tuple[float, float]] | None:
    for margin in MARGINS:
        box = box_around([start, goal, *extra], margin)
        if margin == MARGINS[-1]:
            bounds = grid.bounds()
            if bounds is not None:
                x0, y0 = grid.centre(bounds[0], bounds[1])
                x1, y1 = grid.centre(bounds[2], bounds[3])
                box = (min(box[0], x0), min(box[1], y0), max(box[2], x1), max(box[3], y1))
        path = astar(Coarse(grid, box, now), start, goal, known_only)
        if path is not None:
            return path
    return None
