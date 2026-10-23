from functools import lru_cache
from manifold3d import JoinType
from geom import box, cyl_y, sphere, union, cut, extrude_y, extrude_z, hull2, circle2, rect2, poly, inverse_sweep
from params import Yoke, Plate, Horn, Fit
import dummies

PRINT = (0.0, 0.0, 0.0)
MATERIAL = "PLA"


def tongue_cs():
    return poly([(Plate.tip_w, -Plate.tongue_tip_hw), (Plate.front_w, -Plate.tongue_root_hw),
                 (Plate.front_w, Plate.tongue_root_hw), (Plate.tip_w, Plate.tongue_tip_hw)])


def cavity_cs():
    slope = (Plate.tongue_tip_hw - Plate.tongue_root_hw) / Plate.tongue_h
    x_far = Plate.front_w + 4.0
    hw_far = Plate.tongue_root_hw - 4.0 * slope
    return poly([(Plate.tip_w, -Plate.tongue_tip_hw), (x_far, -hw_far), (x_far, hw_far),
                 (Plate.tip_w, Plate.tongue_tip_hw)]).offset(Fit.slide, JoinType.Miter)


def _ear(y0, y1, r, w0, g):
    prof = hull2([circle2(0.0, 0.0, r + g), rect2(w0 - g, Yoke.bar_w1 + g, Yoke.s_min - g, Yoke.s_max + g)])
    return extrude_y(prof, y0 - g, y1 + g)


def solid(g=0.0):
    s0, s1 = Yoke.s_min - g, Yoke.s_max + g
    parts = [
        box(Yoke.socket_w0 - g, Yoke.socket_w1 + g, -Yoke.socket_hw - g, Yoke.socket_hw + g, s0, s1),
        box(Yoke.bar_w0 - g, Yoke.socket_w1 + g, Yoke.socket_hw - 1.0, Yoke.bar_neck_y + g, s0, s1),
        box(Yoke.bar_w0 - g, Yoke.bar_w1 + g, Yoke.bar_neck_y - g, Yoke.horn_ear_y1 + g, s0, s1),
        box(Yoke.pin_w0 - g, Yoke.socket_w1 + g, -Yoke.bar_neck_y - g, -Yoke.socket_hw + 1.0, s0, s1),
        box(Yoke.pin_w0 - g, Yoke.bar_w1 + g, Yoke.pin_ear_y0 - g, -Yoke.bar_neck_y + g, s0, s1),
        _ear(Yoke.horn_ear_y0, Yoke.horn_ear_y1, Yoke.horn_ear_r, Yoke.bar_w0, g),
        _ear(Yoke.pin_ear_y0, Yoke.pin_ear_y1, Yoke.pin_ear_r, Yoke.pin_w0, g),
    ]
    return union(parts)


def detent_cuts():
    w_back = Plate.tip_w - Fit.slide
    hw = Yoke.tab_hw
    sl = Yoke.tab_slot
    c = [box(Yoke.socket_w0 - 1.0, w_back - Yoke.tab_t, -hw - sl, hw + sl, Yoke.tab_root_s, Yoke.tab_free_s + sl)]
    for sy in (1.0, -1.0):
        ya, yb = sorted((sy * hw, sy * (hw + sl)))
        c.append(box(Yoke.socket_w0 - 1.0, w_back + 0.5, ya, yb, Yoke.tab_root_s, Yoke.tab_free_s + sl))
    c.append(box(Yoke.socket_w0 - 1.0, w_back + 0.5, -hw - sl, hw + sl, Yoke.tab_free_s, Yoke.tab_free_s + sl))
    return c


def detent_bump():
    w_back = Plate.tip_w - Fit.slide
    b = sphere(w_back + Yoke.bump_h - Yoke.bump_r, 0.0, Yoke.bump_s, Yoke.bump_r)
    return b ^ box(w_back - 0.2, w_back + 2.0, -3.0, 3.0, Yoke.bump_s - 3.0, Yoke.bump_s + 3.0)


def horn_cuts():
    y0 = Yoke.horn_ear_y0
    c = [cyl_y(0.0, 0.0, Horn.d / 2.0 + Horn.pocket_fit, y0 - 1.0, Horn.outer_y)]
    c.append(cyl_y(0.0, 0.0, Horn.centre_hole / 2.0, y0 - 1.0, Yoke.horn_ear_y1 + 1.0))
    import math
    for a in Horn.screw_angles:
        x = Horn.screw_r * math.cos(math.radians(a))
        z = Horn.screw_r * math.sin(math.radians(a))
        c.append(cyl_y(x, z, Horn.screw_pilot / 2.0, y0, Yoke.horn_ear_y1 + 1.0))
    return c


def pin_cuts():
    return [cyl_y(0.0, 0.0, Fit.insert_m3 / 2.0, Yoke.pin_ear_y0 - 1.0, Yoke.pin_ear_y1 + 1.0)]


@lru_cache(maxsize=1)
def servo_keepout():
    return inverse_sweep(dummies.servo(grow=Yoke.servo_clear))


@lru_cache(maxsize=1)
def build():
    m = union([solid(0.0)])
    cav = extrude_z(cavity_cs(), Plate.tongue_len * -0.5 - Fit.slide, Yoke.s_max + 5.0)
    m = cut(m, [cav] + detent_cuts() + horn_cuts() + pin_cuts())
    m = union([m, detent_bump()])
    return m - servo_keepout()


@lru_cache(maxsize=4)
def envelope(g):
    return solid(g)
