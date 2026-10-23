import math

import numpy as np


class Scene:
    def __init__(self, boxes=(), wall_x=3.0, side_y=(-1.5, 1.5), drop_x=None, drop_z=-0.2, floor_colour=(78, 112, 150), seed=0):
        self.boxes = [tuple(map(float, b[:6])) + (tuple(b[6]) if len(b) > 6 else (60, 60, 180),) for b in boxes]
        self.wall_x = wall_x
        self.side_y = side_y
        self.drop_x = drop_x
        self.drop_z = drop_z
        self.floor_colour = np.array(floor_colour, np.float64)
        self.rng = np.random.default_rng(seed)

    def render(self, height=0.14, pitch_deg=8.0, yaw_deg=0.0, width=640, rows=480, fov_h_deg=70.0):
        f = (width / 2) / math.tan(math.radians(fov_h_deg) / 2)
        p, yaw = math.radians(pitch_deg), math.radians(yaw_deg)
        d = np.array([math.cos(yaw) * math.cos(p), math.sin(yaw) * math.cos(p), math.sin(p)])
        r = np.array([math.sin(yaw), -math.cos(yaw), 0.0])
        u = np.cross(r, d)
        xs = (np.arange(width) + 0.5 - width / 2) / f
        ys = (np.arange(rows) + 0.5 - rows / 2) / f
        gx, gy = np.meshgrid(xs, ys)
        ray = gx[..., None] * r - gy[..., None] * u + d
        c = np.array([0.0, 0.0, height])
        t = np.full((rows, width), np.inf)
        colour = np.zeros((rows, width, 3))
        normal = np.zeros((rows, width, 3))
        with np.errstate(divide="ignore", invalid="ignore"):
            tf = -c[2] / ray[..., 2]
            hit = c + ray * tf[..., None]
            ok = (tf > 0) & ((self.drop_x is None) | (hit[..., 0] < (self.drop_x if self.drop_x is not None else 0)))
            self._take(t, colour, normal, tf, ok, self._floor(hit), (0, 0, 1))
            if self.drop_x is not None:
                tl = (self.drop_z - c[2]) / ray[..., 2]
                hl = c + ray * tl[..., None]
                self._take(t, colour, normal, tl, (tl > 0) & (hl[..., 0] >= self.drop_x), self._floor(hl) * 0.8, (0, 0, 1))
                ts = (self.drop_x - c[0]) / ray[..., 0]
                hs = c + ray * ts[..., None]
                self._take(t, colour, normal, ts, (ts > 0) & (hs[..., 2] <= 0) & (hs[..., 2] >= self.drop_z), np.broadcast_to(np.array([90.0, 90.0, 95.0]), hs.shape), (-1, 0, 0))
            tw = (self.wall_x - c[0]) / ray[..., 0]
            hw = c + ray * tw[..., None]
            self._take(t, colour, normal, tw, tw > 0, self._wall(hw), (-1, 0, 0))
            for side, sign in ((self.side_y[0], 1), (self.side_y[1], -1)):
                ts = (side - c[1]) / ray[..., 1]
                hs = c + ray * ts[..., None]
                self._take(t, colour, normal, ts, ts > 0, self._wall(hs) * 0.93, (0, sign, 0))
            for x0, x1, y0, y1, z0, z1, col in self.boxes:
                self._box(c, ray, t, colour, normal, (x0, x1, y0, y1, z0, z1), np.array(col, np.float64))
        light = np.array([0.3, -0.4, 0.86])
        light /= np.linalg.norm(light)
        shade = 0.55 + 0.45 * np.clip(normal @ light, 0, 1)
        self.depth = t
        image = colour * shade[..., None] * (0.97 + 0.06 * self.rng.random((rows, width, 1)))
        return np.clip(image, 0, 255).astype(np.uint8)

    def _floor(self, hit):
        plank = (np.floor(hit[..., 1] / 0.14) % 2)
        grain = 0.94 + 0.06 * np.sin(hit[..., 0] * 37.0 + hit[..., 1] * 3.0)
        return self.floor_colour * ((0.9 + 0.1 * plank) * grain)[..., None]

    def _wall(self, hit):
        return np.broadcast_to(np.array([206.0, 218.0, 226.0]), hit.shape) * (0.96 + 0.04 * np.clip(hit[..., 2], 0, 1))[..., None]

    def _take(self, t, colour, normal, tt, ok, col, n):
        better = ok & np.isfinite(tt) & (tt < t)
        t[better] = tt[better]
        colour[better] = np.broadcast_to(col, colour.shape)[better]
        normal[better] = np.array(n, np.float64)

    def _box(self, c, ray, t, colour, normal, box, col):
        x0, x1, y0, y1, z0, z1 = box
        for axis, lo, hi in ((0, x0, x1), (1, y0, y1), (2, z0, z1)):
            for plane, sign in ((lo, -1), (hi, 1)):
                tt = (plane - c[axis]) / ray[..., axis]
                h = c + ray * tt[..., None]
                o = [i for i in range(3) if i != axis]
                lims = {0: (x0, x1), 1: (y0, y1), 2: (z0, z1)}
                ok = (tt > 0)
                for i in o:
                    ok &= (h[..., i] >= lims[i][0] - 1e-9) & (h[..., i] <= lims[i][1] + 1e-9)
                n = [0, 0, 0]
                n[axis] = sign
                self._take(t, colour, normal, tt, ok, col, n)

    def truth(self, bearings_deg, height=0.14, reach=4.0, step=0.01):
        out = []
        for b in bearings_deg:
            a = math.radians(b)
            dx, dy = math.cos(a), -math.sin(a)
            dist = None
            s = 0.0
            while s <= reach:
                x, y = dx * s, dy * s
                if x >= self.wall_x or y <= self.side_y[0] or y >= self.side_y[1]:
                    dist = s
                    break
                if self.drop_x is not None and x >= self.drop_x:
                    dist = s
                    break
                if any(x0 <= x <= x1 and y0 <= y <= y1 for x0, x1, y0, y1, *_ in self.boxes):
                    dist = s
                    break
                s += step
            out.append(dist)
        return out
