from functools import lru_cache
from geom import box, cyl_z, union, cut
from params import Floor, Vl53, FrontSensor, Fit

PRINT = (0.0, 90.0, 0.0)
MATERIAL = "PLA"


def board_box():
    x1 = FrontSensor.chip_face_x - Vl53.chip_h
    x0 = x1 - Vl53.pcb_t
    cy = FrontSensor.y - Vl53.chip_off_short
    cz = FrontSensor.z - Vl53.chip_off_long
    return x0, x1, cy - Vl53.ly / 2.0, cy + Vl53.ly / 2.0, cz - Vl53.lx / 2.0, cz + Vl53.lx / 2.0


def screw_points():
    xc = (FrontSensor.post_x0 + FrontSensor.base_x1) / 2.0
    return [(xc, FrontSensor.y + s * FrontSensor.screw_dy) for s in (1.0, -1.0)]


@lru_cache(maxsize=1)
def build():
    f = FrontSensor
    bx0, bx1, by0, by1, bz0, bz1 = board_box()
    g = Vl53.groove_fit
    z0 = Floor.z1
    gx0 = bx0 - g
    gx1 = bx1 + g
    top0 = bz1 + g
    top1 = top0 + f.top_t
    rail_in = Vl53.ly / 2.0 - Vl53.groove_depth
    parts = []
    for s in (1.0, -1.0):
        ya, yb = sorted((f.y + s * f.post_y0, f.y + s * f.post_y1))
        parts.append(box(f.post_x0, f.base_x1, ya, yb, z0, top1))
        fa, fb = sorted((f.y + s * f.post_y0, f.y + s * (f.post_y1 + 1.0)))
        parts.append(box(f.foot_x0, f.base_x1, fa, fb, z0, z0 + 3.0))
        ra, rb = sorted((f.y + s * rail_in, f.y + s * f.post_y0))
        parts.append(box(gx0 - f.rail_back, f.base_x1, ra, rb, f.full_rail_z, top1))
        parts.append(box(gx0, f.base_x1, ra, rb, bz0 - g - f.stop_t, f.full_rail_z))
    parts.append(box(gx0 - f.rail_back, f.base_x1, f.y - f.post_y1, f.y + f.post_y1, top0, top1))
    m = union(parts)
    cuts = [box(gx0, gx1, by0 - g, by1 + g, bz0 - g, top1 + 1.0)]
    for x, y in screw_points():
        cuts.append(cyl_z(x, y, Fit.pilot_m2 / 2.0, z0 - 1.0, z0 + 8.0))
    return cut(m, cuts)
