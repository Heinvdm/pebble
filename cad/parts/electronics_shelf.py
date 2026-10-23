from functools import lru_cache
from geom import box, cyl_z, union, cut, extrude_z, rrect2
from params import Shelf, BOARDS, Deck, Fit

PRINT = (0.0, 0.0, 0.0)
MATERIAL = "PLA"


def shelf_boards():
    return [b for b in BOARDS if b.deck == "shelf"]


@lru_cache(maxsize=1)
def build():
    from parts.chassis_floor import board_features
    plate = extrude_z(rrect2(Shelf.x0, Shelf.x1, -Shelf.hw, Shelf.hw, Shelf.corner_r), Shelf.z0, Shelf.z1)
    adds, cuts = [], []
    for b in shelf_boards():
        a, c = board_features(b, Shelf.z0, Shelf.z1)
        adds += a
        cuts += c
    d = (Fit.csk_m3_d - Fit.clear_m3) / 2.0
    for x, y in Shelf.pillars:
        cuts.append(cyl_z(x, y, Fit.clear_m3 / 2.0, Shelf.z0 - 1.0, Shelf.z1 + 10.0))
        cuts.append(cyl_z(x, y, Fit.clear_m3 / 2.0, Shelf.z1 - d, Shelf.z1 + 0.01, r1=Fit.csk_m3_d / 2.0))
    for x in (Shelf.x0 + 8.0, Shelf.x1 - 8.0):
        for y in (-10.0, 10.0):
            cuts.append(box(x - Fit.zip_t / 2.0, x + Fit.zip_t / 2.0, y - Fit.zip_w / 2.0, y + Fit.zip_w / 2.0, Shelf.z0 - 1.0, Shelf.z1 + 1.0))
    return cut(union([plate] + adds), cuts)
