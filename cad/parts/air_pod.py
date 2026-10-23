from functools import lru_cache
from geom import box, cyl_z, union, cut, extrude_z, body_outline
from params import Body, Floor, AirPod, Fit

PRINT = (0.0, 0.0, 0.0)
MATERIAL = "PLA"


def screw_points():
    a = AirPod
    y = a.tab_y0 + 2.2
    return [(a.x0 + a.tab_w / 2.0, y), (a.x1 - a.tab_w / 2.0, y)]


def front_limit():
    return extrude_z(body_outline(-Body.wall - AirPod.wall_gap), Floor.z1 - 1.0, AirPod.roof_z1 + 1.0)


def cavity():
    a = AirPod
    return box(a.board_x0 + a.groove_depth, a.board_x1 - a.groove_depth, a.back_y1, Body.half_y + 5.0, Floor.z1 - 1.0, a.roof_z0)


@lru_cache(maxsize=1)
def build():
    a = AirPod
    z0 = Floor.z1
    body = box(a.x0, a.x1, a.back_y0, Body.half_y + 5.0, z0, a.roof_z1)
    tabs = [box(x0, x0 + a.tab_w, a.tab_y0, a.back_y0 + 0.5, z0, z0 + a.tab_h) for x0 in (a.x0, a.x1 - a.tab_w)]
    m = union([body] + tabs) ^ front_limit()
    cuts = [cavity()]
    for gx0, gx1 in ((a.board_x0 - a.groove_fit, a.board_x0 + a.groove_depth + 0.01), (a.board_x1 - a.groove_depth - 0.01, a.board_x1 + a.groove_fit)):
        cuts.append(box(gx0, gx1, a.board_y0 - a.groove_fit, a.board_y1 + a.groove_fit, z0 - 1.0, a.roof_z0))
    cuts.append(box(a.cx - a.notch_w / 2.0, a.cx + a.notch_w / 2.0, a.back_y0 - 1.0, a.back_y1 + 0.5, z0 - 1.0, z0 + a.notch_h))
    for x, y in screw_points():
        cuts.append(cyl_z(x, y, Fit.pilot_m2 / 2.0, z0 - 1.0, z0 + a.tab_h - 1.0))
    return cut(m, cuts)
