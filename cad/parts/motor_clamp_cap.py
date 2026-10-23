from functools import lru_cache
from geom import box, cyl_z, cut
from params import Motor, Fit

PRINT = (0.0, 0.0, 0.0)
MATERIAL = "PLA"


@lru_cache(maxsize=1)
def build():
    hw = Motor.gear_w / 2.0 + Motor.pocket_fit / 2.0
    ow = hw + Motor.clamp_wall
    z0 = Motor.axis_z + Motor.gear_h / 2.0
    m = box(Motor.axis_x - ow, Motor.axis_x + ow, Motor.clamp_y0, Motor.clamp_y1, z0, z0 + Motor.cap_t)
    cuts = []
    for xs in (1.0, -1.0):
        for yy in Motor.cap_screw_y:
            cuts.append(cyl_z(Motor.axis_x + xs * (hw + Motor.clamp_wall / 2.0), yy, Fit.clear_m2 / 2.0, z0 - 1.0, z0 + Motor.cap_t + 1.0))
    return cut(m, cuts)
