from functools import lru_cache
from geom import box, cyl_z, union, cut, extrude_z, poly, rrect2, outline_halfwidth
from params import Body, Dock, Fit

PRINT = (0.0, 0.0, 0.0)
MATERIAL = "PLA"


def rail_inner(x):
    t = min(max((x - Dock.rail_x0) / Dock.rail_len, 0.0), 1.0)
    hw = outline_halfwidth(max(x, Body.rear_x + 0.1))
    return hw + Dock.rail_gap0 + (Dock.rail_gap1 - Dock.rail_gap0) * t * t


def rail_polys(n=40):
    xs = [Dock.rail_x0 + (Dock.rail_x1 - Dock.rail_x0) * i / n for i in range(n + 1)]
    inner = [(x, rail_inner(x)) for x in xs]
    rail = inner + [(x, y + Dock.rail_t) for x, y in reversed(inner)]
    wing = [(x, y - 3.0) for x, y in inner] + [(x, y + Dock.rail_t + Dock.wing_margin) for x, y in reversed(inner)]
    return rail, wing


def block_screws():
    xc = (Dock.block_x0 + Dock.face_x) / 2.0 - 2.0
    return [(xc, s * (Dock.block_hw - 8.0)) for s in (1.0, -1.0)]


def wall_screws():
    xc = Dock.wall_x0 + Dock.tab_t / 2.0
    return [(xc, s * 40.0) for s in (1.0, -1.0)]


@lru_cache(maxsize=1)
def build():
    t = Dock.base_t
    hw = Dock.base_w / 2.0
    plate = extrude_z(rrect2(Dock.base_x0, Dock.base_x1, -hw, hw, 8.0), 0.0, t)
    rail, wing = rail_polys()
    parts = [plate]
    for s in (1.0, -1.0):
        r = extrude_z(poly(rail), t - 0.01, t + Dock.rail_h)
        w = extrude_z(poly(wing), 0.0, t)
        if s < 0:
            r = r.mirror((0.0, 1.0, 0.0))
            w = w.mirror((0.0, 1.0, 0.0))
        parts += [r, w]
    m = union(parts)
    cuts = []
    px, py, pd = Dock.weight_pocket
    xc = (Body.rear_x + Dock.base_x1) / 2.0 - 4.0
    for s in (1.0, -1.0):
        yc = s * (py / 2.0 + 5.0)
        cuts.append(box(xc - px / 2.0, xc + px / 2.0, yc - py / 2.0, yc + py / 2.0, -1.0, pd))
    fi = Dock.feet_inset
    for x in (Dock.base_x0 + fi, Dock.base_x1 - fi):
        for y in (-hw + fi, hw - fi):
            cuts.append(cyl_z(x, y, Dock.feet_d / 2.0, -1.0, Dock.feet_depth))
    g = 0.2
    cuts.append(box(Dock.wall_x0 - g, Dock.wall_x0 + Dock.tab_t + g, -50.0 - g, 50.0 + g, t - Dock.tab_depth - g, t + 1.0))
    for x, y in block_screws() + wall_screws():
        cuts.append(cyl_z(x, y, Fit.clear_m3 / 2.0, -1.0, t + 1.0))
        cuts.append(cyl_z(x, y, Fit.m3_head_d / 2.0 + 0.3, -1.0, 2.5))
    return cut(m, cuts)
