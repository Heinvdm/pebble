import math
from functools import lru_cache
from geom import box, cyl_y, cyl_z, union, cut, extrude_y, hull2, circle2, rect2, poly
from params import Floor, Omni, OmniFork, Fit

PRINT = (0.0, 0.0, 0.0)
MATERIAL = "PLA"


def screw_points():
    f = OmniFork
    return [(Omni.x + dx, s * f.screw_y) for dx in (-f.screw_dx, f.screw_dx) for s in (1.0, -1.0)]


def hexagon(cx, cz, af):
    r = af / math.sqrt(3.0)
    return poly([(cx + r * math.cos(math.radians(60.0 * i)), cz + r * math.sin(math.radians(60.0 * i))) for i in range(6)])


@lru_cache(maxsize=1)
def build():
    x, z = Omni.x, Omni.z
    f = OmniFork
    z0 = Floor.z1
    top = f.bridge_z0 + f.bridge_t
    prof = hull2([circle2(x, z, f.axle_boss_r), rect2(x - f.half_x, x + f.half_x, z0, z0 + 2.0),
                  rect2(x - f.bridge_hx, x + f.bridge_hx, f.bridge_z0, top)])
    parts = []
    for s in (1.0, -1.0):
        ya, yb = sorted((s * f.cheek_y0, s * f.cheek_y1))
        parts.append(extrude_y(prof, ya, yb))
        fa, fb = sorted((s * (f.cheek_y1 - 0.5), s * (f.cheek_y1 + f.foot_w)))
        parts.append(box(x - f.foot_hx, x + f.foot_hx, fa, fb, z0, z0 + f.foot_t))
        sa, sb = sorted((s * Omni.face_to_face / 2.0, s * (f.cheek_y0 + 0.5)))
        parts.append(cyl_y(x, z, f.spacer_d / 2.0, sa, sb))
    parts.append(box(x - f.bridge_hx, x + f.bridge_hx, -f.cheek_y1, f.cheek_y1, f.bridge_z0, top))
    m = union(parts)
    cuts = [cyl_y(x, z, Omni.bolt_clear / 2.0, -f.cheek_y1 - 1.0, f.cheek_y1 + 1.0)]
    cuts.append(extrude_y(hexagon(x, z, Omni.nut_af + 0.2), -f.cheek_y1 - 1.0, -f.cheek_y1 + f.nut_pocket))
    for px, py in screw_points():
        cuts.append(cyl_z(px, py, Fit.clear_m3 / 2.0, z0 - 1.0, z0 + f.foot_t + 1.0))
        d = (Fit.csk_m3_d - Fit.clear_m3) / 2.0
        cuts.append(cyl_z(px, py, Fit.clear_m3 / 2.0, z0 + f.foot_t - d, z0 + f.foot_t + 0.01, r1=Fit.csk_m3_d / 2.0))
        cuts.append(cyl_z(px, py, Fit.insert_m3 / 2.0 + 0.3, z0 - 1.0, z0 + f.insert_proud + 0.2))
    return cut(m, cuts)
