from functools import lru_cache
from geom import box, cyl_x, cyl_z, union, cut, extrude_x, hull2, circle2, rect2
from params import Dock, Fit
from parts.dock_base import wall_screws

PRINT = (0.0, -90.0, 0.0)
MATERIAL = "PLA"


@lru_cache(maxsize=1)
def build():
    z0 = Dock.base_t
    top = z0 + Dock.wall_h
    hw = Dock.wall_w / 2.0
    r = Dock.wall_corner_r
    prof = hull2([rect2(-hw, hw, z0, top - r), circle2(-hw + r, top - r, r), circle2(hw - r, top - r, r)])
    wall = extrude_x(prof, Dock.wall_x0, Dock.wall_x1)
    tab = box(Dock.wall_x0, Dock.wall_x0 + Dock.tab_t, -50.0, 50.0, z0 - Dock.tab_depth, z0 + 0.5)
    m = union([wall, tab])
    tg = Dock.tag / 2.0 + Dock.tag_fit / 2.0
    cuts = [box(Dock.wall_x1 - Dock.tag_recess, Dock.wall_x1 + 1.0, -tg, tg, Dock.tag_z - tg, Dock.tag_z + tg)]
    bl, bw, bt = Dock.usb_board
    g = 0.3
    cuts.append(box(Dock.wall_x0 - 1.0, Dock.wall_x0 + bt + 0.2, -bl / 2.0 - g, bl / 2.0 + g, Dock.usb_z - bw / 2.0 - g, Dock.usb_z + bw / 2.0 + g))
    cuts.append(cyl_x(0.0, Dock.usb_z, 2.5, Dock.wall_x0 - 1.0, Dock.wall_x1 + 1.0))
    for x, y in wall_screws():
        cuts.append(cyl_z(x, y, Fit.pilot_m3 / 2.0, z0 - Dock.tab_depth - 1.0, z0 + 8.0))
    return cut(m, cuts)
