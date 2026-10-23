from functools import lru_cache
from geom import box, sphere, union, cut, extrude_z, extrude_y, poly
from params import Plate

PRINT = (0.0, 90.0, 0.0)
MATERIAL = "PLA"


def tongue():
    from parts.tilt_yoke import tongue_cs
    t = extrude_z(tongue_cs(), -Plate.tongue_len / 2.0, Plate.tongue_len / 2.0)
    c = Plate.tongue_chamfer
    z0 = -Plate.tongue_len / 2.0
    wedge = extrude_y(poly([(Plate.tip_w - 0.1, z0 - 0.1), (Plate.tip_w + c, z0 - 0.1), (Plate.tip_w - 0.1, z0 + c + 0.1)]),
                      -Plate.tongue_tip_hw - 1.0, Plate.tongue_tip_hw + 1.0)
    dimple = sphere(Plate.tip_w - Plate.dimple_r + Plate.dimple_depth, 0.0, Plate.dimple_s, Plate.dimple_r)
    return cut(t, [wedge, dimple])


def grooves():
    c = []
    hy = Plate.wy / 2.0
    hs = Plate.hs / 2.0
    w0 = Plate.back_w - Plate.groove_d
    n = int(Plate.hs / Plate.groove_pitch)
    for i in range(1, n):
        s = -hs + i * Plate.groove_pitch
        c.append(box(w0, Plate.back_w + 1.0, -hy - 1.0, hy + 1.0, s - Plate.groove_w / 2.0, s + Plate.groove_w / 2.0))
    n = int(Plate.wy / Plate.groove_pitch)
    for i in range(1, n + 1):
        y = -hy + (i - 0.5) * (Plate.wy / n)
        c.append(box(w0, Plate.back_w + 1.0, y - Plate.groove_w / 2.0, y + Plate.groove_w / 2.0, -hs - 1.0, hs + 1.0))
    return c


@lru_cache(maxsize=1)
def build():
    hy = Plate.wy / 2.0
    hs = Plate.hs / 2.0
    base = box(Plate.front_w, Plate.back_w, -hy, hy, -hs, hs)
    base = cut(base, grooves())
    return union([base, tongue()])
