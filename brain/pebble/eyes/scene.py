import math
from dataclasses import dataclass

from ..seams.sight import DOCK_TAG_SIZE_M
from .geometry import focal

TAG36H11_0 = (
    "..........",
    ".########.",
    ".#..#.#.#.",
    ".##...#.#.",
    ".##..####.",
    ".#.#.####.",
    ".##.#..##.",
    ".####.###.",
    ".########.",
    "..........",
)
BLACK = 28
WHITE = 232
SAMPLES = 3


@dataclass(frozen=True)
class TagPlacement:
    distance_m: float = 0.5
    bearing_deg: float = 0.0
    elevation_deg: float = 0.0
    yaw_deg: float = 0.0
    size_m: float = DOCK_TAG_SIZE_M


def tag_scene(width: int, height: int, fov_h_deg: float, tag: TagPlacement | None = None, cells=TAG36H11_0):
    import numpy as np

    tag = tag or TagPlacement()
    rows = np.linspace(141, 92, height, dtype=np.float32)[:, None]
    image = np.repeat(np.repeat(rows, width, axis=1)[:, :, None], 3, axis=2)
    f = focal(width, fov_h_deg)
    cx, cy = width / 2, height / 2
    b, e, a = math.radians(tag.bearing_deg), math.radians(tag.elevation_deg), math.radians(tag.yaw_deg - tag.bearing_deg)
    t = (tag.distance_m * math.sin(b) * math.cos(e), -tag.distance_m * math.sin(e), tag.distance_m * math.cos(b) * math.cos(e))
    n = (math.sin(a), 0.0, -math.cos(a))
    r = (math.cos(a), 0.0, math.sin(a))
    cell = tag.size_m / 8
    half = cell * 5
    us, vs = [], []
    for sx in (-1, 1):
        for sy in (-1, 1):
            p = (t[0] + sx * half * r[0], t[1] + sy * half, t[2] + sx * half * r[2])
            if p[2] <= 0.01:
                continue
            us.append(cx + f * p[0] / p[2])
            vs.append(cy + f * p[1] / p[2])
    if not us:
        return image.astype(np.uint8)
    x0, x1 = max(0, math.floor(min(us)) - 1), min(width, math.ceil(max(us)) + 1)
    y0, y1 = max(0, math.floor(min(vs)) - 1), min(height, math.ceil(max(vs)) + 1)
    if x1 <= x0 or y1 <= y0:
        return image.astype(np.uint8)
    offsets = (np.arange(SAMPLES, dtype=np.float64) + 0.5) / SAMPLES
    xs = (np.arange(x0, x1)[:, None] + offsets[None, :]).ravel()
    ys = (np.arange(y0, y1)[:, None] + offsets[None, :]).ravel()
    dx = ((xs - cx) / f)[None, :]
    dy = ((ys - cy) / f)[:, None]
    nd = n[0] * dx + n[2]
    nt = n[0] * t[0] + n[2] * t[2]
    with np.errstate(divide="ignore", invalid="ignore"):
        lam = nt / nd
    qx, qy, qz = lam * dx - t[0], lam * dy - t[1], lam - t[2]
    u = (qx * r[0] + qz * r[2]) / cell + 5
    v = qy / cell + 5
    u, v, lam = np.broadcast_arrays(u, v, lam)
    inside = (u >= 0) & (u < 10) & (v >= 0) & (v < 10) & np.isfinite(lam) & (lam > 0)
    grid = np.array([[BLACK if ch == "#" else WHITE for ch in row] for row in cells], np.float32)
    values = np.zeros(u.shape, np.float32)
    ui = np.clip(np.floor(np.where(inside, u, 0)).astype(int), 0, 9)
    vi = np.clip(np.floor(np.where(inside, v, 0)).astype(int), 0, 9)
    values[inside] = grid[vi[inside], ui[inside]]
    hh, ww = y1 - y0, x1 - x0
    cover = inside.reshape(hh, SAMPLES, ww, SAMPLES).mean(axis=(1, 3))
    total = (values * inside).reshape(hh, SAMPLES, ww, SAMPLES).sum(axis=(1, 3))
    mean = np.where(cover > 0, total / np.maximum(cover * SAMPLES * SAMPLES, 1e-6), 0)
    patch = image[y0:y1, x0:x1]
    image[y0:y1, x0:x1] = patch * (1 - cover[:, :, None]) + mean[:, :, None] * cover[:, :, None]
    return np.clip(image, 0, 255).astype(np.uint8)
