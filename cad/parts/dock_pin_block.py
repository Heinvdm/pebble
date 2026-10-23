from functools import lru_cache
from geom import box, cyl_x, cyl_z, union, cut
from params import Dock, ShellCfg, Fit, dock_pins
from parts.dock_base import block_screws

PRINT = (0.0, 0.0, 0.0)
MATERIAL = "PLA"


def perf_x():
    x1 = Dock.face_x + Dock.pogo_proud - Dock.pogo_len
    return x1 - Dock.perf_t, x1


@lru_cache(maxsize=1)
def build():
    z0 = Dock.base_t
    hw = Dock.block_hw
    w = Dock.block_wall
    body = box(Dock.block_x0, Dock.face_x, -hw, hw, z0, Dock.block_z1)
    px0, px1 = perf_x()
    cavity = box(Dock.block_x0 - 1.0, px1, -hw + w, hw - w, z0 + w, Dock.block_z1 - w)
    m = body - cavity
    adds = []
    for x, y in block_screws():
        adds.append(cyl_z(x, y, 4.5, z0, z0 + 9.0))
    pz0 = 29.0 - Dock.perf_h / 2.0
    adds.append(box(px1 - 4.0, px1, -Dock.perf_w / 2.0, Dock.perf_w / 2.0, z0, pz0))
    m = union([m] + adds)
    cuts = []
    for y, z, _ in dock_pins():
        cuts.append(cyl_x(y, z, Dock.pogo_hole / 2.0, px1 - 1.0, Dock.face_x + 1.0))
    for s in (1.0, -1.0):
        cuts.append(cyl_x(s * ShellCfg.magnet_y, ShellCfg.magnet_z, Fit.magnet_d / 2.0, Dock.face_x - Fit.magnet_h, Dock.face_x + 1.0))
    for y in (-Dock.perf_w / 2.0 + 2.5, Dock.perf_w / 2.0 - 2.5):
        for z in (pz0 + 2.5, pz0 + Dock.perf_h - 2.5):
            cuts.append(cyl_x(y, z, Fit.pilot_m2 / 2.0, px1 - 4.0, px1 + 0.5))
    for x, y in block_screws():
        cuts.append(cyl_z(x, y, Fit.insert_m3 / 2.0, z0 - 1.0, z0 + 6.0))
    cuts.append(box(Dock.block_x0 - 1.0, Dock.block_x0 + w + 1.0, -6.0, 6.0, z0 - 1.0, z0 + 6.0))
    return cut(m, cuts)
