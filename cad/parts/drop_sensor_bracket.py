from functools import lru_cache
from geom import box, cyl_z, union, cut, hull, extrude_z, body_outline
from params import Body, Floor, Vl53, DropSensor, Fit
import dummies

PRINT = (0.0, 0.0, 0.0)
MATERIAL = "PLA"


def local_board():
    g = Vl53.groove_fit
    hx = Vl53.ly / 2.0
    hy = Vl53.lx / 2.0
    cx = -Vl53.chip_off_short
    cy = -Vl53.chip_off_long
    z0 = Vl53.chip_h
    return cx - hx - g, cx + hx + g, cy - hy - g, cy + hy + g, z0 - g, z0 + Vl53.pcb_t + g


def post_ranges():
    x0, x1, y0, y1, z0, z1 = local_board()
    d = Vl53.groove_depth
    t = DropSensor.post_t
    return (y0 + d - t, y0 + d), (y1 - d, y1 - d + t)


def _heads():
    x0, x1, y0, y1, z0, z1 = local_board()
    w = DropSensor.post_wall
    return [dummies.drop_place(box(x0 - w, x1 + w, ya, yb, z0 - w, z1 + w)) for ya, yb in post_ranges()]


def _footprint(m):
    b = m.bounding_box()
    return b[0], b[3], b[1], b[4]


def screw_points():
    pts = []
    for head in _heads():
        x0, x1, y0, y1 = _footprint(head)
        pts.append(((x0 + x1) / 2.0 - 1.0, (y0 + y1) / 2.0))
    return pts


@lru_cache(maxsize=1)
def build():
    x0, x1, y0, y1, z0, z1 = local_board()
    w = DropSensor.post_wall
    z_floor = Floor.z1
    parts = []
    for head in _heads():
        fx0, fx1, fy0, fy1 = _footprint(head)
        parts.append(hull([head, box(fx0, fx1, fy0, fy1, z_floor, z_floor + 3.0)]))
    (a0, a1), (b0, b1) = post_ranges()
    parts.append(dummies.drop_place(box(x0 - w, x0 + 3.0, a0, b1, z1 + 0.6, z1 + w + 1.5)))
    m = union(parts) ^ extrude_z(body_outline(-Body.wall - 0.6), Floor.z0, Body.top_z)
    cuts = [dummies.drop_place(box(x0 - DropSensor.slide, x1, y0, y1, z0, z1)), dummies.drop_cone(DropSensor.margin)]
    for x, y in screw_points():
        cuts.append(cyl_z(x, y, Fit.pilot_m2 / 2.0, z_floor - 1.0, z_floor + 6.0))
    return cut(m, cuts)
