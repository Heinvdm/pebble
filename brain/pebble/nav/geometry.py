import math

TRACK_M = 0.165
FRONT_M = 0.10
REAR_M = 0.08
HALF_WIDTH_M = 0.095
BODY_RADIUS_M = 0.13
BODY_CENTRE_M = 0.01
CAMERA_AHEAD_M = {"front": 0.087, "rear": 0.045}
CAMERA_HEIGHT_M = {"front": 0.14, "rear": 0.15}
TOF_AHEAD_M = 0.10
TOF_CONE_DEG = 12.0
DROP_AHEAD_M = 0.11


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def wrap_deg(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def body_angle(bearing_deg: float, camera: str) -> float:
    if camera == "rear":
        return math.radians(wrap_deg(180.0 - bearing_deg))
    return math.radians(wrap_deg(-bearing_deg))


def ahead(x: float, y: float, heading: float, forward: float, side: float = 0.0) -> tuple[float, float]:
    c, s = math.cos(heading), math.sin(heading)
    return x + forward * c - side * s, y + forward * s + side * c


def to_body(px: float, py: float, x: float, y: float, heading: float) -> tuple[float, float]:
    dx, dy = px - x, py - y
    c, s = math.cos(heading), math.sin(heading)
    return dx * c + dy * s, -dx * s + dy * c


def camera_spot(x: float, y: float, heading: float, camera: str) -> tuple[float, float, float]:
    reach = CAMERA_AHEAD_M.get(camera, 0.087)
    facing = heading + (math.pi if camera == "rear" else 0.0)
    cx, cy = ahead(x, y, heading, reach if camera != "rear" else reach)
    return cx, cy, facing


def project(x: float, y: float, heading: float, camera: str, bearing_deg: float, distance: float) -> tuple[float, float]:
    cx, cy, _ = camera_spot(x, y, heading, camera)
    angle = heading + body_angle(bearing_deg, camera)
    return cx + distance * math.cos(angle), cy + distance * math.sin(angle)


def floor_distance(elevation_deg: float, pitch_deg: float, height_m: float) -> float | None:
    down = -(elevation_deg + pitch_deg)
    if down < 1.5:
        return None
    return height_m / math.tan(math.radians(down))


def point_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    if length <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def ray_segment(ox: float, oy: float, dx: float, dy: float, ax: float, ay: float, bx: float, by: float) -> float | None:
    ex, ey = bx - ax, by - ay
    denom = dx * ey - dy * ex
    if abs(denom) < 1e-12:
        return None
    wx, wy = ax - ox, ay - oy
    t = (wx * ey - wy * ex) / denom
    u = (wx * dy - wy * dx) / denom
    if t >= 0.0 and 0.0 <= u <= 1.0:
        return t
    return None


def ray_circle(ox: float, oy: float, dx: float, dy: float, cx: float, cy: float, r: float) -> float | None:
    fx, fy = cx - ox, cy - oy
    along = fx * dx + fy * dy
    off = fx * dy - fy * dx
    if abs(off) > r:
        return None
    back = math.sqrt(r * r - off * off)
    near = along - back
    if near >= 0.0:
        return near
    if along + back >= 0.0:
        return 0.0
    return None


def segments_cross(a: tuple, b: tuple, c: tuple, d: tuple) -> bool:
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    d1, d2, d3, d4 = side(c, d, a), side(c, d, b), side(a, b, c), side(a, b, d)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def path_length(points: list[tuple[float, float]]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))
