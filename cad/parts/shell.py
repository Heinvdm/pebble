import math
from functools import lru_cache
from geom import (box, cyl_x, cyl_z, union, cut, hull, extrude_z, extrude_x, extrude_y, body_outline, outline_halfwidth,
                  rrect2, sym_y)
from params import Body, Floor, Motor, Bumper, FrontSensor, ShellCfg, Esp, ESP, Post, Servo, Tilt, Fit, AirPod

PRINT = (0.0, 0.0, 0.0)
MATERIAL = "PLA"


def _rounded_solid(offset, z0, z_top, radius, steps=18):
    layers = [extrude_z(body_outline(offset), z0, z_top - radius)]
    for i in range(steps + 1):
        a = math.radians(90.0 * i / steps)
        z = z_top - radius + radius * math.sin(a)
        inset = radius * (1.0 - math.cos(a))
        layers.append(extrude_z(body_outline(offset - inset), z - 0.01, z))
    return hull(layers)


def outer_solid():
    return _rounded_solid(0.0, Body.bottom_z, Body.top_z, Body.top_fillet)


def inner_solid():
    w = Body.wall
    return _rounded_solid(-w, Body.bottom_z - 5.0, Body.top_z - w, Body.top_fillet - w)


def boss_centres():
    out = []
    for x, s in ShellCfg.bosses:
        hw = outline_halfwidth(x, -Body.wall)
        out.append((x, s * (hw - ShellCfg.boss_inset)))
    return out


def _bosses():
    parts = []
    for x, y in boss_centres():
        s = 1.0 if y > 0 else -1.0
        wall_y = s * (outline_halfwidth(x, -Body.wall) + 1.0)
        parts.append(cyl_z(x, y, ShellCfg.boss_d / 2.0, Floor.z1, ShellCfg.boss_top))
        y0, y1 = sorted((y, wall_y))
        parts.append(box(x - 2.0, x + 2.0, y0, y1, Floor.z1, ShellCfg.boss_top))
    return union(parts)


def _boss_holes():
    return union([cyl_z(x, y, Fit.insert_m3 / 2.0, Floor.z1 - 1.0, Floor.z1 + ShellCfg.insert_depth) for x, y in boss_centres()])


def _magnet_bosses():
    x_in = Body.rear_x + Body.wall
    x_end = Body.rear_x + Fit.magnet_h + ShellCfg.magnet_back
    return union([cyl_x(s * ShellCfg.magnet_y, ShellCfg.magnet_z, ShellCfg.magnet_boss_d / 2.0, x_in - 0.5, x_end) for s in (1.0, -1.0)])


def top_opening_box():
    x0 = Post.col_x0 - ShellCfg.top_open_margin
    x1 = max(Tilt.axis_x + Post.boss_r, Servo.front_x) + ShellCfg.top_open_margin
    y0 = Post.col_y0 - ShellCfg.top_open_margin
    y1 = Servo.spline_top_y + ShellCfg.top_open_margin
    return x0, x1, y0, y1


def air_vents(y0=None, y1=None):
    a = AirPod
    y0 = Body.half_y - Body.wall - 3.0 if y0 is None else y0
    y1 = Body.half_y + 3.0 if y1 is None else y1
    r = a.vent_w / 2.0
    return [extrude_y(rrect2(x - r, x + r, a.vent_z0, a.vent_z1, r), y0, y1) for x in a.vent_x]


def _cuts():
    c = air_vents()
    mc = ShellCfg.motor_notch_clear
    for s in (1.0, -1.0):
        y0, y1 = sorted((s * (Body.half_y - Body.wall - 3.0), s * (Body.half_y + 3.0)))
        c.append(box(Motor.axis_x - Motor.gear_w / 2.0 - mc, Motor.axis_x + Motor.gear_w / 2.0 + mc, y0, y1, Body.bottom_z - 1.0, Motor.axis_z + Motor.gear_h / 2.0 + mc))
        gy = s * Bumper.guide_y
        c.append(box(Bumper.tower_x1 - 4.0, Body.front_x + 5.0, gy - Bumper.notch_w / 2.0, gy + Bumper.notch_w / 2.0, Body.bottom_z - 1.0, Bumper.notch_top))
    c.append(box(Body.front_x - Body.wall - 3.0, Body.front_x + 3.0, FrontSensor.y - FrontSensor.window_w / 2.0, FrontSensor.y + FrontSensor.window_w / 2.0, FrontSensor.z - FrontSensor.window_h / 2.0, FrontSensor.z + FrontSensor.window_h / 2.0))
    xr = Body.rear_x
    xi = Body.rear_x + Body.wall
    c.append(box(xr - 3.0, xi + 3.0, -ShellCfg.kcd_w / 2.0, ShellCfg.kcd_w / 2.0, ShellCfg.kcd_z - ShellCfg.kcd_h / 2.0, ShellCfg.kcd_z + ShellCfg.kcd_h / 2.0))
    m = ShellCfg.kcd_recess_margin
    c.append(box(xr + ShellCfg.kcd_panel, xi + 3.0, -ShellCfg.kcd_w / 2.0 - m, ShellCfg.kcd_w / 2.0 + m, ShellCfg.kcd_z - ShellCfg.kcd_h / 2.0 - m, ShellCfg.kcd_z + ShellCfg.kcd_h / 2.0 + m))
    sw, sh = Esp.slot_w, Esp.slot_h
    c.append(extrude_x(rrect2(ESP.cy - sw / 2.0, ESP.cy + sw / 2.0, Esp.usb_z - sh / 2.0, Esp.usb_z + sh / 2.0, 2.0), xr - 3.0, xi + 3.0))
    hw = ShellCfg.strip_w / 2.0 + ShellCfg.strip_fit
    hh = ShellCfg.strip_h / 2.0 + ShellCfg.strip_fit
    for z in ShellCfg.strips_z:
        c.append(box(xr - 1.0, xr + ShellCfg.strip_t, -hw, hw, z - hh, z + hh))
        c.append(cyl_x(ShellCfg.wire_hole_y, z, ShellCfg.wire_hole_d / 2.0, xr - 1.0, xi + 3.0))
    for s in (1.0, -1.0):
        c.append(cyl_x(s * ShellCfg.magnet_y, ShellCfg.magnet_z, Fit.magnet_d / 2.0, xr - 1.0, xr + Fit.magnet_h))
    x0, x1, y0, y1 = top_opening_box()
    c.append(extrude_z(rrect2(x0, x1, y0, y1, ShellCfg.top_open_r), Body.top_z - Body.wall - 1.0, Body.top_z + 5.0))
    return c


@lru_cache(maxsize=1)
def build():
    shell = outer_solid() - inner_solid()
    shell = union([shell, _bosses(), _magnet_bosses() ^ outer_solid()])
    import dummies
    from params import DropSensor
    return cut(shell, _cuts() + [_boss_holes(), dummies.drop_cone(DropSensor.margin)])
