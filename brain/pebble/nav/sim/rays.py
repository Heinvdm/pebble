import math
import random

from ...seams.sight import FLOOR_OPEN_M, FloorRay
from ..geometry import ray_circle, ray_segment

REACH_M = 2.0
RAYS = 32
VFOV_ASPECT = 0.75
SCORE = 0.8
FEET_M = 0.15
LOW_MM = 30.0
MISS = 0.05
EARLY = 0.01
DROP_SEEN_M = 0.7
DROP_SEEN = 0.4


def near_limit(height_m: float, pitch_deg: float, fov_h_deg: float) -> float:
    half_v = math.degrees(math.atan(math.tan(math.radians(fov_h_deg) / 2.0) * VFOV_ASPECT))
    down = half_v - pitch_deg
    if down <= 1.0:
        return REACH_M
    return height_m / math.tan(math.radians(down))


def obstacles(world) -> tuple[list, list]:
    segments = []
    walls = getattr(world, "segments", None)
    if walls is not None:
        for item in walls:
            if item[4] != "glass":
                segments.append(tuple(v / 1000.0 for v in item[:4]))
    t = world.table
    corners = {"x_min": ((t.x_min, t.y_min), (t.x_min, t.y_max)), "x_max": ((t.x_max, t.y_min), (t.x_max, t.y_max)), "y_min": ((t.x_min, t.y_min), (t.x_max, t.y_min)), "y_max": ((t.x_min, t.y_max), (t.x_max, t.y_max))}
    for side in t.walls:
        (ax, ay), (bx, by) = corners[side]
        segments.append((ax / 1000.0, ay / 1000.0, bx / 1000.0, by / 1000.0))
    circles = []
    for person in world.people:
        if person.home:
            circles.append((person.x / 1000.0, person.y / 1000.0, FEET_M))
    for thing in world.things:
        if not thing.home or thing.held_by is not None or thing.z_mm > 100.0 or thing.height_mm < LOW_MM:
            continue
        circles.append((thing.x / 1000.0, thing.y / 1000.0, thing.radius_mm / 1000.0))
    return segments, circles


def drops(world) -> list:
    out = []
    for x0, y0, x1, y1 in getattr(world, "cliffs", []):
        x0, y0, x1, y1 = x0 / 1000.0, y0 / 1000.0, x1 / 1000.0, y1 / 1000.0
        out += [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]
    return out


def floor_rays(world, x_mm: float, y_mm: float, facing: float, pitch_deg: float, fov_h_deg: float, height_m: float = 0.14, rng: random.Random | None = None, reach: float = REACH_M, honest: bool = False) -> tuple[FloorRay, ...]:
    ox, oy = x_mm / 1000.0, y_mm / 1000.0
    near = near_limit(height_m, pitch_deg, fov_h_deg)
    if near >= reach:
        return ()
    segments, circles = obstacles(world)
    edges = drops(world)
    half = fov_h_deg / 2.0
    out = []
    for index in range(RAYS):
        bearing = -half + fov_h_deg * index / (RAYS - 1)
        angle = facing - math.radians(bearing)
        dx, dy = math.cos(angle), math.sin(angle)
        best = math.inf
        for ax, ay, bx, by in segments:
            hit = ray_segment(ox, oy, dx, dy, ax, ay, bx, by)
            if hit is not None and hit < best:
                best = hit
        for cx, cy, r in circles:
            hit = ray_circle(ox, oy, dx, dy, cx, cy, r)
            if hit is not None and hit < best:
                best = hit
        for ax, ay, bx, by in edges:
            hit = ray_segment(ox, oy, dx, dy, ax, ay, bx, by)
            if hit is not None and hit < best and (not honest or (hit <= DROP_SEEN_M and rng is not None and rng.random() < DROP_SEEN)):
                best = hit
        if honest and rng is not None and best <= reach:
            roll = rng.random()
            if roll < MISS:
                best = math.inf
            elif roll < MISS + EARLY:
                best = near + rng.random() * (best - near)
        if best > reach:
            out.append(FloorRay(round(bearing, 2), FLOOR_OPEN_M, SCORE))
        else:
            distance = max(near, best)
            if rng is not None:
                distance = max(near, distance + rng.gauss(0.0, 0.03 + 0.02 * distance))
            out.append(FloorRay(round(bearing, 2), round(distance, 3), (SCORE if best >= near else SCORE * 0.6) * (1.0 - 0.15 * distance / reach)))
    return tuple(out)
