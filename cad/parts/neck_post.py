from functools import lru_cache
from geom import box, cyl_y, cyl_z, union, cut, extrude_y, extrude_x, hull2, circle2, rect2, poly, rrect2, sweep
import math
from params import Floor, Tilt, Post, Servo, Plate, Fit, Omni
from parts import tilt_yoke
import dummies

PRINT = (0.0, 0.0, 0.0)
MATERIAL = "PLA"

AX = Tilt.axis_x
AZ = Tilt.axis_z
FEET_Y1 = 32.0


def column():
    top = AZ + Post.col_top_rel
    c = box(Post.col_x0, Post.col_x1, Post.col_y0, Post.col_y1, Post.col_z0, top)
    w = Post.wall
    hollow = box(Post.col_x0 + w, Post.col_x1 - w, Post.col_y0 + w, Post.col_y1 - w, Post.col_z0 - 10.0, Post.hollow_top)
    return c, hollow


def legs():
    z0 = Floor.z1
    zt = Post.col_z0 + 4.0
    bf0, bf1 = Post.back_foot
    ff0, ff1 = Post.front_foot
    back = extrude_y(poly([(bf0, z0), (bf0 + 5.0, z0), (Post.col_x0 + 5.0, zt), (Post.col_x0, zt)]), Post.col_y0, FEET_Y1)
    back = back - box(-30.0, Post.col_x0 - 2.0, -15.0, 24.0, z0 + 9.0, Post.col_z0 - 10.0)
    front = extrude_y(poly([(ff0, z0), (ff0 + 5.0, z0), (Post.col_x1, zt), (Post.col_x1 - 5.0, zt)]), Post.col_y0, FEET_Y1)
    front = front - omni_opening()
    feet = [box(bf0, bf1, Post.col_y0, FEET_Y1, z0, z0 + Post.foot_t), box(ff0, ff1, Post.col_y0, FEET_Y1, z0, z0 + Post.foot_t) - omni_opening()]
    return union([back, front] + feet)


def omni_opening():
    return cyl_y(Omni.x, Omni.z, Omni.keep_r + Post.omni_gap, -Omni.keep_hw - Post.omni_gap, Omni.keep_hw + Post.omni_gap)


def bearing_arm():
    prof = hull2([circle2(AX, AZ, Post.boss_r), rect2(Post.col_x1 - 7.0, Post.col_x1, AZ - 28.0, AZ + Post.col_top_rel)])
    return extrude_y(prof, Post.arm_y0, Post.arm_y1)


def cradle():
    top = AZ - Servo.body_w / 2.0 - Post.shelf_gap
    bot = top - Post.shelf_t
    prof = hull2([rect2(Post.col_x1 - 0.5, Post.shelf_x1, bot, top), rect2(Post.col_x1 - 3.0, Post.col_x1, bot - (Post.shelf_x1 - Post.col_x1), top)])
    shelf = extrude_y(prof, Servo.bottom_y, Post.shelf_y1)
    roof = AZ + Servo.body_w / 2.0 + Post.hood_gap
    hood = box(Post.col_x0, Post.col_x1 + Post.hood_len, Servo.bottom_y, Post.col_y1, roof, roof + Post.hood_t)
    riser = box(Post.col_x0, Post.col_x1, Servo.bottom_y, Post.col_y1, AZ, roof)
    return union([shelf, hood, riser])


def holes():
    c = []
    c.append(cyl_y(AX, AZ, Post.bearing_d / 2.0, Post.arm_y0 - 1.0, Post.arm_y1 + 1.0))
    for x, y in Post.screw_xy:
        c.append(cyl_z(x, y, Fit.insert_m3 / 2.0, Floor.z1 - 1.0, Floor.z1 + Post.insert_depth))
    c.append(cyl_y(Servo.rear_hole_x, AZ, Fit.pilot_m2 / 2.0, Post.col_y1 - Post.tab_pilot_depth, Post.col_y1 + 1.0))
    lw, lh = Post.lead_hole
    ly = Servo.bottom_y + 0.5
    c.append(box(Post.col_x1 - 6.0, Post.col_x1 + 1.0, ly, ly + lw, AZ - Servo.body_w / 2.0 + 0.5, AZ - Servo.body_w / 2.0 + 0.5 + lh))
    c.append(cyl_z(Post.col_x1 - 5.0, ly + lw / 2.0, 2.5, Post.hollow_top - 5.0, AZ - Servo.body_w / 2.0 + 0.5 + lh))
    c.append(box(Post.col_x0 - 1.0, Post.col_x0 + Post.wall + 1.0, 18.0, 28.0, 98.0, 108.0))
    c.append(box(Post.col_x0 - 1.0, Post.col_x0 + Post.wall + 1.0, -15.0, -5.0, 98.0, 108.0))
    for yc in (17.0, 29.0):
        c.append(box(Post.col_x0 - 1.0, Post.col_x0 + Post.wall + 1.0, yc - Fit.zip_t / 2.0, yc + Fit.zip_t / 2.0, 86.0, 86.0 + Fit.zip_w))
    return c


def plate_keepout(g):
    hy = Plate.wy / 2.0 + g
    hs = Plate.hs / 2.0 + g
    a = box(Plate.front_w - g, Plate.back_w, -hy, hy, -hs, hs)
    b = box(Plate.tip_w - g, Plate.front_w, -Plate.tongue_tip_hw - g, Plate.tongue_tip_hw + g, -Plate.tongue_len / 2.0 - g, Plate.tongue_len / 2.0 + g)
    return union([a, b])


@lru_cache(maxsize=1)
def moving_keepout():
    local = union([tilt_yoke.envelope(Post.clear), dummies.phone_local(Post.clear + 0.5), plate_keepout(Post.clear)])
    return sweep(local)


@lru_cache(maxsize=1)
def raw():
    col, hollow = column()
    m = union([col, legs(), bearing_arm(), cradle()])
    return cut(m, [hollow] + holes())


@lru_cache(maxsize=1)
def build():
    return raw() - moving_keepout()
