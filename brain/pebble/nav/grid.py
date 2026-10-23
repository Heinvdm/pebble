import base64
import math
import zlib

RES_M = 0.05
CHUNK = 32
SHIFT = 5
MASK = CHUNK - 1
UNKNOWN = 128
TOP = 228
BOTTOM = 28
OCCUPIED = 152
FREE = 112
STRONG = 20
SOFT_KEEP_S = 600.0
TOUCH_KEEP_S = 3600.0
FAR_M = 9.0
STUBBORN = 0.35
STUBBORN_ABOVE = 190


class Grid:
    def __init__(self, res: float = RES_M):
        self.res = res
        self.chunks: dict[tuple[int, int], bytearray] = {}
        self.cliffs: set[tuple[int, int]] = set()
        self.touched: dict[tuple[int, int], float] = {}
        self.rises: set[tuple[int, int]] = set()
        self.soft: dict[tuple[int, int], tuple[str, float]] = {}
        self.version = 0

    def cell(self, x: float, y: float) -> tuple[int, int]:
        return math.floor(x / self.res), math.floor(y / self.res)

    def centre(self, ix: int, iy: int) -> tuple[float, float]:
        return (ix + 0.5) * self.res, (iy + 0.5) * self.res

    def _chunk(self, ix: int, iy: int, create: bool) -> bytearray | None:
        key = (ix >> SHIFT, iy >> SHIFT)
        chunk = self.chunks.get(key)
        if chunk is None and create:
            chunk = bytearray([UNKNOWN]) * (CHUNK * CHUNK)
            self.chunks[key] = chunk
        return chunk

    def value(self, ix: int, iy: int) -> int:
        chunk = self.chunks.get((ix >> SHIFT, iy >> SHIFT))
        if chunk is None:
            return UNKNOWN
        return chunk[((iy & MASK) << SHIFT) | (ix & MASK)]

    def add(self, ix: int, iy: int, delta: float, cap: int = TOP) -> None:
        if delta < 0 and ((ix, iy) in self.touched or (ix, iy) in self.cliffs):
            return
        chunk = self._chunk(ix, iy, True)
        index = ((iy & MASK) << SHIFT) | (ix & MASK)
        value = chunk[index]
        if delta > 0:
            chunk[index] = max(value, min(cap, TOP, value + int(round(delta))))
        else:
            if value > STUBBORN_ABOVE:
                delta *= STUBBORN
            chunk[index] = max(BOTTOM, value + int(round(delta)))
        self.version += 1

    def occupied(self, ix: int, iy: int) -> bool:
        return self.value(ix, iy) >= OCCUPIED or (ix, iy) in self.cliffs or (ix, iy) in self.touched

    def free(self, ix: int, iy: int) -> bool:
        return self.value(ix, iy) <= FREE and (ix, iy) not in self.cliffs and (ix, iy) not in self.touched

    def known(self, ix: int, iy: int) -> bool:
        value = self.value(ix, iy)
        return value >= OCCUPIED or value <= FREE or (ix, iy) in self.cliffs or (ix, iy) in self.touched

    def blocked(self, ix: int, iy: int, now: float | None = None) -> bool:
        if self.occupied(ix, iy):
            return True
        soft = self.soft.get((ix, iy))
        return soft is not None and (now is None or now - soft[1] <= SOFT_KEEP_S)

    def occupied_at(self, x: float, y: float) -> bool:
        return self.occupied(*self.cell(x, y))

    def free_at(self, x: float, y: float) -> bool:
        return self.free(*self.cell(x, y))

    def cells_on(self, x0: float, y0: float, x1: float, y1: float):
        ix, iy = self.cell(x0, y0)
        jx, jy = self.cell(x1, y1)
        dx, dy = x1 - x0, y1 - y0
        step_x = 1 if dx > 0 else -1
        step_y = 1 if dy > 0 else -1
        res = self.res
        if dx != 0:
            next_x = ((ix + (1 if dx > 0 else 0)) * res - x0) / dx
            delta_x = abs(res / dx)
        else:
            next_x = delta_x = math.inf
        if dy != 0:
            next_y = ((iy + (1 if dy > 0 else 0)) * res - y0) / dy
            delta_y = abs(res / dy)
        else:
            next_y = delta_y = math.inf
        limit = abs(jx - ix) + abs(jy - iy) + 1
        for _ in range(limit):
            yield ix, iy
            if ix == jx and iy == jy:
                return
            if next_x < next_y:
                next_x += delta_x
                ix += step_x
            else:
                next_y += delta_y
                iy += step_y

    def ray(self, x0: float, y0: float, x1: float, y1: float, hit: bool, hit_gain: float, free_gain: float, cap: int = TOP) -> None:
        end = self.cell(x1, y1)
        for ix, iy in self.cells_on(x0, y0, x1, y1):
            if (ix, iy) == end:
                break
            if free_gain:
                self.add(ix, iy, -free_gain)
        if hit:
            self.add(end[0], end[1], hit_gain, cap)
        elif free_gain:
            self.add(end[0], end[1], -free_gain)

    def mark(self, x: float, y: float, gain: float, cap: int = TOP) -> None:
        self.add(*self.cell(x, y), gain, cap)

    def touch(self, x: float, y: float, now: float, radius: float = 0.0) -> None:
        for cell in self._disc(x, y, radius):
            self.touched[cell] = now
            self.add(cell[0], cell[1], TOP)

    def cliff(self, x: float, y: float, radius: float = 0.0) -> None:
        for cell in self._disc(x, y, radius):
            self.cliffs.add(cell)
            self.version += 1

    def rise(self, x: float, y: float) -> None:
        self.rises.add(self.cell(x, y))

    def hazard(self, x: float, y: float, label: str, now: float, radius: float = 0.05) -> None:
        for cell in self._disc(x, y, radius):
            self.soft[cell] = (label, now)
        self.version += 1

    def clear_hazards(self, x: float, y: float, radius: float) -> None:
        for cell in self._disc(x, y, radius):
            self.soft.pop(cell, None)

    def _disc(self, x: float, y: float, radius: float) -> list[tuple[int, int]]:
        cx, cy = self.cell(x, y)
        reach = int(math.ceil(radius / self.res))
        out = []
        for ix in range(cx - reach, cx + reach + 1):
            for iy in range(cy - reach, cy + reach + 1):
                px, py = self.centre(ix, iy)
                if math.hypot(px - x, py - y) <= radius + self.res * 0.71:
                    out.append((ix, iy))
        return out

    def clear(self, x: float, y: float, radius: float) -> None:
        for ix, iy in self._disc(x, y, radius):
            if (ix, iy) in self.touched or (ix, iy) in self.cliffs:
                continue
            chunk = self._chunk(ix, iy, False)
            if chunk is None:
                continue
            index = ((iy & MASK) << SHIFT) | (ix & MASK)
            if chunk[index] > FREE:
                chunk[index] = FREE
                self.version += 1

    def soften(self, x: float, y: float, radius: float) -> None:
        for ix, iy in self._disc(x, y, radius):
            if (ix, iy) in self.touched or (ix, iy) in self.cliffs:
                continue
            chunk = self._chunk(ix, iy, False)
            if chunk is None:
                continue
            index = ((iy & MASK) << SHIFT) | (ix & MASK)
            if chunk[index] >= OCCUPIED:
                chunk[index] = UNKNOWN
                self.version += 1
        self.soft = {cell: item for cell, item in self.soft.items() if math.hypot(self.centre(*cell)[0] - x, self.centre(*cell)[1] - y) > radius}

    def forget(self, now: float) -> None:
        self.soft = {cell: item for cell, item in self.soft.items() if now - item[1] <= SOFT_KEEP_S}
        stale = [cell for cell, at in self.touched.items() if now - at > TOUCH_KEEP_S]
        for cell in stale:
            del self.touched[cell]

    def blocked_cells(self, ix0: int, iy0: int, ix1: int, iy1: int, now: float | None = None) -> list[tuple[int, int]]:
        out = []
        for (cx, cy), chunk in self.chunks.items():
            bx, by = cx << SHIFT, cy << SHIFT
            if bx > ix1 or by > iy1 or bx + CHUNK <= ix0 or by + CHUNK <= iy0:
                continue
            for index, value in enumerate(chunk):
                if value >= OCCUPIED:
                    ix, iy = bx + (index & MASK), by + (index >> SHIFT)
                    if ix0 <= ix <= ix1 and iy0 <= iy <= iy1:
                        out.append((ix, iy))
        for cells in (self.cliffs, self.touched):
            for ix, iy in cells:
                if ix0 <= ix <= ix1 and iy0 <= iy <= iy1:
                    out.append((ix, iy))
        for (ix, iy), (_, at) in self.soft.items():
            if ix0 <= ix <= ix1 and iy0 <= iy <= iy1 and (now is None or now - at <= SOFT_KEEP_S):
                out.append((ix, iy))
        return out

    def counts(self) -> dict:
        free = occupied = 0
        for chunk in self.chunks.values():
            for value in chunk:
                if value >= OCCUPIED:
                    occupied += 1
                elif value <= FREE:
                    free += 1
        area = self.res * self.res
        return {"free_m2": round(free * area, 1), "occupied_m2": round(occupied * area, 2), "cliff_cells": len(self.cliffs), "touched_cells": len(self.touched)}

    def bounds(self) -> tuple[int, int, int, int] | None:
        if not self.chunks:
            return None
        xs = [cx for cx, _ in self.chunks]
        ys = [cy for _, cy in self.chunks]
        return min(xs) << SHIFT, min(ys) << SHIFT, ((max(xs) + 1) << SHIFT) - 1, ((max(ys) + 1) << SHIFT) - 1

    def strength(self, chunk: bytearray) -> int:
        return sum(1 for value in chunk if abs(value - UNKNOWN) >= STRONG)

    def prune(self, max_chunks: int) -> int:
        weak = [key for key, chunk in self.chunks.items() if self.strength(chunk) == 0]
        for key in weak:
            del self.chunks[key]
        dropped = len(weak)
        if len(self.chunks) > max_chunks:
            ranked = sorted(self.chunks, key=lambda key: self.strength(self.chunks[key]))
            for key in ranked[: len(self.chunks) - max_chunks]:
                del self.chunks[key]
                dropped += 1
        if dropped:
            self.version += 1
        return dropped

    def to_dict(self) -> dict:
        return {
            "res": self.res,
            "chunks": [[cx, cy, base64.b64encode(zlib.compress(bytes(chunk), 9)).decode("ascii")] for (cx, cy), chunk in sorted(self.chunks.items())],
            "cliffs": sorted([list(cell) for cell in self.cliffs]),
            "touched": sorted([list(cell) for cell in self.touched]),
            "rises": sorted([list(cell) for cell in self.rises]),
        }

    @classmethod
    def from_dict(cls, data: dict, now: float = 0.0) -> "Grid":
        grid = cls(float(data.get("res") or RES_M))
        for item in data.get("chunks") or []:
            try:
                cx, cy, packed = int(item[0]), int(item[1]), str(item[2])
                raw = zlib.decompress(base64.b64decode(packed))
            except (ValueError, TypeError, IndexError, zlib.error):
                continue
            if len(raw) == CHUNK * CHUNK:
                grid.chunks[(cx, cy)] = bytearray(raw)
        for name, target in (("cliffs", grid.cliffs), ("rises", grid.rises)):
            for cell in data.get(name) or []:
                if isinstance(cell, list) and len(cell) == 2:
                    target.add((int(cell[0]), int(cell[1])))
        for cell in data.get("touched") or []:
            if isinstance(cell, list) and len(cell) == 2:
                grid.touched[(int(cell[0]), int(cell[1]))] = now
        return grid


class Clearance:
    def __init__(self, grid: Grid, x: float, y: float, radius_m: float, extra: list[tuple[float, float, float]] = (), now: float | None = None, cap_m: float = 0.8):
        self.res = grid.res
        cx, cy = grid.cell(x, y)
        reach = int(math.ceil(radius_m / grid.res))
        self.ix0, self.iy0 = cx - reach, cy - reach
        self.n = n = 2 * reach + 1
        self.cap = cap_m
        big = cap_m / grid.res + 1.0
        dist = [big] * (n * n)
        ix1, iy1 = self.ix0 + n - 1, self.iy0 + n - 1
        for ix, iy in grid.blocked_cells(self.ix0, self.iy0, ix1, iy1, now):
            dist[(iy - self.iy0) * n + (ix - self.ix0)] = 0.0
        for ox, oy, r in extra:
            for ix, iy in grid._disc(ox, oy, r):
                if self.ix0 <= ix <= ix1 and self.iy0 <= iy <= iy1:
                    dist[(iy - self.iy0) * n + (ix - self.ix0)] = 0.0
        diag = 1.4142
        for j in range(n):
            row = j * n
            for i in range(n):
                k = row + i
                v = dist[k]
                if v == 0.0:
                    continue
                if i > 0:
                    w = dist[k - 1] + 1.0
                    if w < v:
                        v = w
                if j > 0:
                    up = k - n
                    w = dist[up] + 1.0
                    if w < v:
                        v = w
                    if i > 0:
                        w = dist[up - 1] + diag
                        if w < v:
                            v = w
                    if i < n - 1:
                        w = dist[up + 1] + diag
                        if w < v:
                            v = w
                dist[k] = v
        for j in range(n - 1, -1, -1):
            row = j * n
            for i in range(n - 1, -1, -1):
                k = row + i
                v = dist[k]
                if v == 0.0:
                    continue
                if i < n - 1:
                    w = dist[k + 1] + 1.0
                    if w < v:
                        v = w
                if j < n - 1:
                    down = k + n
                    w = dist[down] + 1.0
                    if w < v:
                        v = w
                    if i < n - 1:
                        w = dist[down + 1] + diag
                        if w < v:
                            v = w
                    if i > 0:
                        w = dist[down - 1] + diag
                        if w < v:
                            v = w
                dist[k] = v
        self.dist = dist

    def at(self, x: float, y: float) -> float:
        i = math.floor(x / self.res) - self.ix0
        j = math.floor(y / self.res) - self.iy0
        if i < 0 or j < 0 or i >= self.n or j >= self.n:
            return self.cap
        return min(self.cap, self.dist[j * self.n + i] * self.res)

    def inside(self, x: float, y: float, margin_m: float = 0.0) -> bool:
        i = math.floor(x / self.res) - self.ix0
        j = math.floor(y / self.res) - self.iy0
        edge = int(margin_m / self.res)
        return edge <= i < self.n - edge and edge <= j < self.n - edge
