from functools import lru_cache
from geom import box, cyl_x, union, cut, extrude_z, body_outline, rect2, outline_x_at
from params import Bumper, Fit

PRINT = (0.0, 0.0, 0.0)
MATERIAL = "PLA"


def boss_x():
    return outline_x_at(Bumper.guide_y, Bumper.gap) - Bumper.boss_back


@lru_cache(maxsize=1)
def build():
    ring = body_outline(Bumper.gap + Bumper.thick) - body_outline(Bumper.gap)
    plan = ring ^ rect2(Bumper.x_end, 400.0, -400.0, 400.0)
    m = extrude_z(plan, Bumper.z0, Bumper.z1)
    bosses = []
    cuts = [box(90.0, 130.0, -Bumper.window_w / 2.0, Bumper.window_w / 2.0, Bumper.window_z - Bumper.window_h / 2.0, Bumper.window_z + Bumper.window_h / 2.0)]
    xb = boss_x()
    for s in (1.0, -1.0):
        gy = s * Bumper.guide_y
        x_in = outline_x_at(Bumper.guide_y, Bumper.gap)
        bosses.append(cyl_x(gy, Bumper.guide_z, Bumper.boss_d / 2.0, xb, x_in + 1.0))
        cuts.append(cyl_x(gy, Bumper.guide_z, Fit.insert_m3 / 2.0, xb - 1.0, xb + Bumper.insert_len))
    m = union([m] + bosses)
    import dummies
    from params import DropSensor
    keep = dummies.drop_cone(DropSensor.margin)
    n = 6
    cuts += [keep.translate((Bumper.travel * i / n, 0.0, 0.0)) for i in range(n + 1)]
    return cut(m, cuts)
