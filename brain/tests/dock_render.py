import math
from pathlib import Path

import numpy as np

from pebble.eyes.scene import TAG36H11_0

DATA = Path(__file__).resolve().parent / "data"
PLA = (178, 182, 186)
DARK = (60, 62, 66)
COLOURS = {"base": PLA, "pins": PLA, "wall": PLA, "magnets": DARK}


def load_dock(path: Path = DATA / "dock_mesh.npz") -> dict:
    data = np.load(path)
    parts = {name: (data[name + "_v"].astype(np.float64), data[name + "_f"]) for name in COLOURS}
    return {"parts": parts, "tag": data["tag"].astype(np.float64)}


def box_mesh(x0, x1, y0, y1, z0, z1):
    v = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], np.float64)
    f = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]], np.int64)
    return v, f


class Camera:
    def __init__(self, x, y, z, yaw_deg, pitch_deg, width, height, fov_h_deg):
        self.c = np.array([x, y, z], np.float64)
        yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
        self.d = np.array([math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), math.sin(pitch)])
        self.r = np.array([math.sin(yaw), -math.cos(yaw), 0.0])
        self.u = np.cross(self.r, self.d)
        self.w, self.h = width, height
        self.f = (width / 2) / math.tan(math.radians(fov_h_deg) / 2)

    def to_cam(self, p):
        q = p - self.c
        return np.stack([q @ self.r, -(q @ self.u), q @ self.d], axis=-1)

    def rays(self):
        xs = (np.arange(self.w) + 0.5 - self.w / 2) / self.f
        ys = (np.arange(self.h) + 0.5 - self.h / 2) / self.f
        gx, gy = np.meshgrid(xs, ys)
        return gx[..., None] * self.r - gy[..., None] * self.u + self.d


def looking_at(target, distance, bearing_deg, height, width=640, height_px=480, fov_h_deg=65.0, aim_offset_deg=0.0, pitch_deg=-8.0):
    angle = math.radians(bearing_deg)
    x = target[0] + distance * math.cos(angle)
    y = target[1] + distance * math.sin(angle)
    yaw = math.degrees(math.atan2(target[1] - y, target[0] - x)) + aim_offset_deg
    return Camera(x, y, height, yaw, pitch_deg, width, height_px, fov_h_deg)


def room(camera: Camera, seed: int = 0, wall_x: float = -0.32) -> np.ndarray:
    rng = np.random.default_rng(seed)
    rays = camera.rays()
    image = np.zeros((camera.h, camera.w, 3), np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        t_floor = -camera.c[2] / rays[..., 2]
        t_wall = (wall_x - camera.c[0]) / rays[..., 0]
    floor = (t_floor > 0) & ((t_wall <= 0) | (t_floor < t_wall))
    hit = camera.c + rays * np.where(floor, t_floor, t_wall)[..., None]
    plank = (np.floor(hit[..., 1] / 0.14) % 2)
    wood = np.array([150, 112, 78]) * (0.92 + 0.08 * plank)[..., None]
    paint = np.array([226, 220, 206]) * (0.95 + 0.05 * np.clip(hit[..., 2], 0, 1))[..., None]
    image = np.where(floor[..., None], wood, paint)
    image *= (0.97 + 0.06 * rng.random((camera.h, camera.w, 1)))
    return image


def render(meshes, camera: Camera, image: np.ndarray, tag=None, light=(0.4, -0.3, 0.85)) -> np.ndarray:
    image = image.copy()
    zbuf = np.full((camera.h, camera.w), np.inf)
    light = np.array(light, np.float64) / np.linalg.norm(light)
    for verts, faces, colour in meshes:
        cam = camera.to_cam(verts)
        tri = cam[faces]
        normals = np.cross(verts[faces][:, 1] - verts[faces][:, 0], verts[faces][:, 2] - verts[faces][:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        keep = (lengths > 1e-12) & (tri[:, :, 2] > 0.02).all(axis=1)
        for t in np.nonzero(keep)[0]:
            p = tri[t]
            n = normals[t] / lengths[t]
            toward = camera.c - verts[faces[t]].mean(axis=0)
            if n @ toward < 0:
                continue
            sx = camera.w / 2 + camera.f * p[:, 0] / p[:, 2]
            sy = camera.h / 2 + camera.f * p[:, 1] / p[:, 2]
            x0, x1 = max(0, int(math.floor(sx.min()))), min(camera.w - 1, int(math.ceil(sx.max())))
            y0, y1 = max(0, int(math.floor(sy.min()))), min(camera.h - 1, int(math.ceil(sy.max())))
            if x1 < x0 or y1 < y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            d = (sy[1] - sy[2]) * (sx[0] - sx[2]) + (sx[2] - sx[1]) * (sy[0] - sy[2])
            if abs(d) < 1e-9:
                continue
            a = ((sy[1] - sy[2]) * (gx - sx[2]) + (sx[2] - sx[1]) * (gy - sy[2])) / d
            b = ((sy[2] - sy[0]) * (gx - sx[2]) + (sx[0] - sx[2]) * (gy - sy[2])) / d
            c = 1 - a - b
            inside = (a >= 0) & (b >= 0) & (c >= 0)
            if not inside.any():
                continue
            z = 1 / (a / p[0, 2] + b / p[1, 2] + c / p[2, 2])
            region = zbuf[y0:y1 + 1, x0:x1 + 1]
            closer = inside & (z < region)
            if not closer.any():
                continue
            region[closer] = z[closer]
            shade = 0.45 + 0.55 * max(0.0, float(n @ light))
            image[y0:y1 + 1, x0:x1 + 1][closer] = np.array(colour, np.float64) * shade
    if tag is not None:
        tx, ty, tz, size = tag
        rays = camera.rays()
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (tx + 0.0003 - camera.c[0]) / rays[..., 0]
        hit = camera.c + rays * t[..., None]
        cell = size / 10
        u = ((hit[..., 1] - ty) + size / 2) / cell
        v = ((tz - hit[..., 2]) + size / 2) / cell
        on = (t > 0) & (u >= 0) & (u < 10) & (v >= 0) & (v < 10) & (np.abs(t - zbuf) < 0.004)
        grid = np.array([[24 if ch == "#" else 236 for ch in row] for row in TAG36H11_0], np.float64)
        values = grid[np.clip(v, 0, 9.999).astype(int), np.clip(u, 0, 9.999).astype(int)]
        image[on] = values[on][:, None]
    return image


def dock_scene(dock: dict, distance: float, bearing_deg: float = 0.0, aim_offset_deg: float = 0.0, height: float = 0.15, width: int = 640, height_px: int = 480, fov_h_deg: float = 65.0, seed: int = 0, extras=()) -> np.ndarray:
    target = np.array([-0.1, 0.0, 0.07])
    camera = looking_at(target, distance, bearing_deg, height, width, height_px, fov_h_deg, aim_offset_deg)
    meshes = [(v, f, COLOURS[name]) for name, (v, f) in dock["parts"].items()] if dock else []
    meshes.extend(extras)
    image = render(meshes, camera, room(camera, seed), dock["tag"] if dock else None)
    return np.clip(image, 0, 255).astype(np.uint8), camera
