from functools import lru_cache
from geom import box, cyl_z, union, cut, extrude_z, rrect2
from params import Floor, Cells, Fit

PRINT = (0.0, 0.0, 0.0)
MATERIAL = "PLA"


@lru_cache(maxsize=1)
def build():
    hy = Cells.holder_y / 2.0
    plug = box(Cells.x0, Cells.x1, -hy, hy, Floor.z0, Floor.z1)
    ears = []
    ew = Cells.ear_w / 2.0
    for s in (1.0, -1.0):
        ya, yb = sorted((s * (hy - 1.0), s * (hy + Cells.ear_len)))
        ears.append(extrude_z(rrect2(Cells.cx - ew, Cells.cx + ew, ya, yb, 3.0), Floor.z0, Floor.z0 + Cells.ear_t))
    m = union([plug] + ears)
    cuts = []
    d = (Fit.csk_m3_d - Fit.clear_m3) / 2.0
    for s in (1.0, -1.0):
        cuts.append(cyl_z(Cells.cx, s * Cells.screw_y, Fit.clear_m3 / 2.0, Floor.z0 - 1.0, Floor.z1 + 1.0))
        cuts.append(cyl_z(Cells.cx, s * Cells.screw_y, Fit.csk_m3_d / 2.0, Floor.z0 - 0.01, Floor.z0 + d, r1=Fit.clear_m3 / 2.0))
    for hx, hy_ in Cells.holder_holes:
        x, y = Cells.cx + hx, hy_
        cuts.append(cyl_z(x, y, Fit.clear_m3 / 2.0, Floor.z0 - 1.0, Floor.z1 + 1.0))
        d = (Cells.csk_d - Fit.clear_m3) / 2.0
        cuts.append(cyl_z(x, y, Cells.csk_d / 2.0, Floor.z0 - 0.01, Floor.z0 + d, r1=Fit.clear_m3 / 2.0))
    cuts.append(box(Cells.x0 - 1.0, Cells.x0 + 4.0, -8.0, 8.0, Floor.z0 - 1.0, Floor.z0 + 1.0))
    return cut(m, cuts)
