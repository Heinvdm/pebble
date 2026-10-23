import math
from functools import lru_cache
from geom import cyl_z, union, cut, extrude_z, circle2, rect2
from params import Wheel, Fit

PRINT = (180.0, 0.0, 0.0)
MATERIAL = "PLA"


def bore_cs():
    r = Wheel.bore_d / 2.0 + Fit.press
    flat = Wheel.bore_flat - Wheel.bore_d / 2.0 + Fit.press
    return circle2(0.0, 0.0, r) ^ rect2(-r - 1.0, flat, -r - 1.0, r + 1.0)


def groove_centres():
    n = Wheel.oring_count
    mid = Wheel.w / 2.0
    return [mid + (i - (n - 1) / 2.0) * Wheel.groove_pitch for i in range(n)]


@lru_cache(maxsize=1)
def build():
    r_rim = Wheel.rim_d / 2.0
    r_in = Wheel.floor_d / 2.0 - 1.6
    ring = cyl_z(0.0, 0.0, r_rim, 0.0, Wheel.w) - cyl_z(0.0, 0.0, r_in, -1.0, Wheel.w + 1.0)
    web = cyl_z(0.0, 0.0, r_rim - 1.0, Wheel.w - Wheel.web_t, Wheel.w)
    boss = cyl_z(0.0, 0.0, Wheel.hub_boss_d / 2.0, 0.0, Wheel.w)
    m = union([ring, web, boss])
    cuts = [extrude_z(bore_cs(), -1.0, Wheel.w + 1.0)]
    for zc in groove_centres():
        g = cyl_z(0.0, 0.0, r_rim + 1.0, zc - Wheel.groove_w / 2.0, zc + Wheel.groove_w / 2.0)
        cuts.append(g - cyl_z(0.0, 0.0, Wheel.floor_d / 2.0, zc - Wheel.groove_w, zc + Wheel.groove_w))
    rh = (Wheel.hub_boss_d / 2.0 + r_in) / 2.0
    for i in range(Wheel.holes):
        a = 2.0 * math.pi * i / Wheel.holes
        cuts.append(cyl_z(rh * math.cos(a), rh * math.sin(a), Wheel.hole_d / 2.0, -1.0, Wheel.w + 1.0))
    return cut(m, cuts)
