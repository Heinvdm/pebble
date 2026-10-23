import math
from functools import lru_cache
from geom import (box, cyl_x, cyl_y, cyl_z, union, cut, extrude_z, body_outline, rrect2, slot_z,
                  outline_halfwidth, outline_x_at)
from params import (Body, Floor, Motor, Omni, OmniFork, Cells, BOARDS, ESP, UPS, Cap, Deck, Bumper, Switch, Post, Fit,
                    DropSensor, ShellCfg, Shelf)
from parts import shell, front_sensor_mount, drop_sensor_bracket, omni_fork, air_pod
import dummies

PRINT = (0.0, 0.0, 0.0)
MATERIAL = "PLA"


def plate():
    return extrude_z(body_outline(-Floor.inset), Floor.z0, Floor.z1)


def motor_cradles():
    adds, cuts = [], []
    hw = Motor.gear_w / 2.0 + Motor.pocket_fit / 2.0
    hh = Motor.gear_h / 2.0 + Motor.pocket_fit / 2.0
    ow = hw + Motor.clamp_wall
    top = Motor.axis_z + Motor.gear_h / 2.0 - Motor.clamp_squeeze
    for s in (1.0, -1.0):
        y0, y1 = sorted((s * Motor.clamp_y0, s * Motor.clamp_y1))
        adds.append(box(Motor.axis_x - ow, Motor.axis_x + ow, y0, y1, Floor.z1, top))
        cuts.append(box(Motor.axis_x - hw, Motor.axis_x + hw, y0 - 1.0, y1 + 1.0, Motor.axis_z - hh, top + 5.0))
        for xs in (1.0, -1.0):
            for yy in Motor.cap_screw_y:
                cuts.append(cyl_z(Motor.axis_x + xs * (hw + Motor.clamp_wall / 2.0), s * yy, Fit.insert_m2 / 2.0, top - 4.5, top + 1.0))
    return adds, cuts


def cap_screw_points():
    hw = Motor.gear_w / 2.0 + Motor.pocket_fit / 2.0
    return [(Motor.axis_x + xs * (hw + Motor.clamp_wall / 2.0), yy) for xs in (1.0, -1.0) for yy in Motor.cap_screw_y]


def omni_features():
    hw = Omni.keep_hw + 0.5
    cuts = [cyl_y(Omni.x, Omni.z, Omni.keep_r, -hw, hw)]
    for x, y in omni_fork.screw_points():
        cuts.append(cyl_z(x, y, Fit.insert_m3 / 2.0, Floor.z0 - 1.0, Floor.z1 + 1.0))
    return [], cuts


def shelf_pillars():
    adds, cuts = [], []
    for x, y in Shelf.pillars:
        adds.append(cyl_z(x, y, Shelf.pillar_d / 2.0, Floor.z1, Shelf.z0))
        cuts.append(cyl_z(x, y, Fit.insert_m3 / 2.0, Shelf.z0 - 6.0, Shelf.z0 + 1.0))
    return adds, cuts


def drop_window():
    return [dummies.drop_cone(DropSensor.margin)]


def countersink(x, y, d_hole, d_head):
    depth = (d_head - d_hole) / 2.0
    return [cyl_z(x, y, d_hole / 2.0, Floor.z0 - 1.0, Floor.z1 + 1.0),
            cyl_z(x, y, d_head / 2.0 + 0.01, Floor.z0 - 0.01, Floor.z0 + depth, r1=d_hole / 2.0)]


def battery_features():
    c = Cells.open_clear
    hy = Cells.holder_y / 2.0 + c
    cuts = [box(Cells.x0 - c, Cells.x1 + c, -hy, hy, Floor.z0 - 1.0, Floor.z1 + 1.0)]
    adds = []
    ew = Cells.ear_w / 2.0 + c
    for s in (1.0, -1.0):
        y_end = s * (Cells.holder_y / 2.0 + Cells.ear_len + c)
        ya, yb = sorted((s * (hy - 1.0), y_end))
        cuts.append(extrude_z(rrect2(Cells.cx - ew, Cells.cx + ew, ya, yb, 3.0), Floor.z0 - 1.0, Floor.z0 + Cells.ear_t))
        y = s * Cells.screw_y
        adds.append(cyl_z(Cells.cx, y, 4.5, Floor.z1, Floor.z1 + 5.0))
        cuts.append(cyl_z(Cells.cx, y, Fit.insert_m3 / 2.0, Floor.z0 + Cells.ear_t - 0.01, Floor.z0 + Cells.ear_t + 6.0))
    return adds, cuts


def bumper_features():
    adds, cuts = [], []
    hx = Switch.h
    xf = dummies.switch_front_x()
    xb = xf - hx
    ped_top = Floor.z1 + dummies.switch_pedestal_h()
    pad = Bumper.pedestal_pad
    y_end = Bumper.guide_y + Switch.lever_contact_from_end
    y_mid = y_end - Switch.l / 2.0
    for s in (1.0, -1.0):
        gy = s * Bumper.guide_y
        adds.append(box(Bumper.tower_x0, Bumper.tower_x1, gy - Bumper.tower_hw, gy + Bumper.tower_hw, Floor.z1, Bumper.tower_z1))
        cuts.append(cyl_x(gy, Bumper.guide_z, Bumper.bore_d / 2.0, Bumper.tower_x0 - 1.0, Bumper.tower_x1 + 1.0))
        ya, yb = sorted((s * (y_end - Switch.l - pad), s * (y_end + pad)))
        adds.append(box(xb - pad, xf + pad, ya, yb, Floor.z1, ped_top))
        hx_hole = xb + Switch.hole_from_back
        for k in (-0.5, 0.5):
            hy = s * (y_mid + k * Switch.hole_pitch)
            cuts.append(slot_z(hx_hole - 1.5, hy, hx_hole + 1.5, hy, Fit.clear_m2, Floor.z0 - 1.0, ped_top + 1.0))
            cuts.append(slot_z(hx_hole - 1.5, hy, hx_hole + 1.5, hy, Fit.m2_head_d + 0.4, Floor.z0 - 1.0, Floor.z0 + Fit.m2_head_h + 0.2))
    return adds, cuts


def _zip(x, y, along_x, zb, zt):
    if along_x:
        return box(x - Fit.zip_w / 2.0, x + Fit.zip_w / 2.0, y - Fit.zip_t / 2.0, y + Fit.zip_t / 2.0, zb - 1.0, zt + 1.0)
    return box(x - Fit.zip_t / 2.0, x + Fit.zip_t / 2.0, y - Fit.zip_w / 2.0, y + Fit.zip_w / 2.0, zb - 1.0, zt + 1.0)


def _board_cradle(b, zb, zt, open_x0=False):
    adds, cuts = [], []
    top = b.z0 + b.pcb_t + Deck.cradle_lip * 0.5
    g = Fit.slide
    if b.z0 > zt:
        adds.append(box(b.x0 + 1.0, b.x1 - 1.0, b.y0 + 1.0, b.y1 - 1.0, zt, b.z0))
    t = Deck.cradle_wall
    L = 4.0
    for cx in (b.x0, b.x1):
        if open_x0:
            continue
        sx = -1.0 if cx == b.x0 else 1.0
        for cy in (b.y0, b.y1):
            sy = -1.0 if cy == b.y0 else 1.0
            xo = cx + sx * g
            yo = cy + sy * g
            xa, xb_ = sorted((xo, xo + sx * t))
            ya, yb = sorted((yo, yo + sy * t))
            adds.append(box(xa, xb_, min(ya, yo - sy * L), max(yb, yo - sy * L), zt, top))
            adds.append(box(min(xa, xo - sx * L), max(xb_, xo - sx * L), ya, yb, zt, top))
    if b.lx >= b.ly:
        for x in (b.cx - b.lx * 0.25, b.cx + b.lx * 0.25):
            for s in (1.0, -1.0):
                cuts.append(_zip(x, b.cy + s * (b.ly / 2.0 + g + t + 1.8), True, zb, zt))
    else:
        for y in (b.cy - b.ly * 0.25, b.cy + b.ly * 0.25):
            for s in (1.0, -1.0):
                cuts.append(_zip(b.cx + s * (b.lx / 2.0 + g + t + 1.8), y, False, zb, zt))
    return adds, cuts


def _board_standoffs(b, zb, zt):
    adds, cuts = [], []
    for hx, hy in b.holes:
        x, y = b.cx + hx, b.cy + hy
        adds.append(cyl_z(x, y, Deck.standoff_d / 2.0, zt, b.z0))
        cuts.append(cyl_z(x, y, Fit.pilot_m2 / 2.0, zb + 1.0, b.z0 + 1.0))
    for y in (b.cy - b.ly * 0.25, b.cy + b.ly * 0.25):
        for s in (1.0, -1.0):
            cuts.append(_zip(b.cx + s * (b.lx / 2.0 + 2.5), y, False, zb, zt))
    return adds, cuts


def board_features(b, zb, zt):
    if b.mount == "standoffs":
        return _board_standoffs(b, zb, zt)
    return _board_cradle(b, zb, zt, open_x0=(b is ESP))


def _cap_saddles():
    adds, cuts = [], []
    r = Cap.d / 2.0
    cz = Floor.z1 + Cap.lift + r
    top = cz + 1.5
    for x in (Cap.x0 + 2.5, Cap.x0 + Cap.l - 2.5):
        adds.append(box(x - 1.5, x + 1.5, Cap.cy - r - 2.0, Cap.cy + r + 2.0, Floor.z1, top))
    cuts.append(cyl_x(Cap.cy, cz, r + 0.15, Cap.x0 - 1.0, Cap.x0 + Cap.l + 1.0))
    xm = Cap.x0 + Cap.l / 2.0
    for s in (1.0, -1.0):
        y = Cap.cy + s * (r + 2.5)
        cuts.append(box(xm - Fit.zip_w / 2.0, xm + Fit.zip_w / 2.0, y - Fit.zip_t / 2.0, y + Fit.zip_t / 2.0, Floor.z0 - 1.0, Floor.z1 + 1.0))
    return adds, cuts


def deck_features():
    adds, cuts = [], []
    for b in BOARDS:
        if b.deck != "floor":
            continue
        a, c = board_features(b, Floor.z0, Floor.z1)
        adds += a
        cuts += c
    a, c = _cap_saddles()
    return adds + a, cuts + c


def _keepouts():
    m = Deck.grid_margin
    k = []
    for b in BOARDS:
        if b.deck == "floor":
            k.append((b.x0 - m - 4.0, b.x1 + m + 4.0, b.y0 - m - 4.0, b.y1 + m + 4.0))
    hy = Cells.holder_y / 2.0 + Cells.ear_len + m
    k.append((Cells.x0 - m - 2.0, Cells.x1 + m, -hy, hy))
    for x, y in Shelf.pillars:
        k.append((x - 6.0, x + 6.0, y - 6.0, y + 6.0))
    k.append((Omni.x - Omni.keep_r - m, 200.0, -OmniFork.cheek_y1 - OmniFork.foot_w - m, OmniFork.cheek_y1 + OmniFork.foot_w + m))
    k.append((Post.front_foot[0] - m, Post.front_foot[1] + m, -40.0, 40.0))
    k.append((Cap.x0 - m, Cap.x0 + Cap.l + m, Cap.cy - Cap.d / 2.0 - m - 4.0, Cap.cy + Cap.d / 2.0 + m + 4.0))
    for x, y in shell.boss_centres():
        k.append((x - 6.0, x + 6.0, y - 6.0, y + 6.0))
    for x, y in Post.screw_xy:
        k.append((x - 6.0, x + 6.0, y - 6.0, y + 6.0))
    k.append((Post.back_foot[0] - m, Post.back_foot[1] + m, -60.0, 60.0))
    k.append((-16.0, 16.0, Motor.clamp_y0 - 6.0, 80.0))
    k.append((-16.0, 16.0, -80.0, -Motor.clamp_y0 + 6.0))
    return k


def grid_points():
    pts = []
    p = Deck.grid_pitch
    nx = int((Deck.x1 - Deck.x0) / p)
    k = _keepouts()
    for i in range(nx + 1):
        x = Deck.x0 + i * p
        for j in range(-12, 13):
            y = j * p
            if abs(y) > outline_halfwidth(x, -Floor.inset) - Deck.edge_margin:
                continue
            if any(a <= x <= b and c <= y <= d for a, b, c, d in k):
                continue
            pts.append((x, y))
    return pts


def deck_grid():
    return [cyl_z(x, y, Fit.pilot_m2 / 2.0, Floor.z0 - 1.0, Floor.z1 + 1.0) for x, y in grid_points()]


def mount_holes():
    cuts = []
    for x, y in list(Post.screw_xy) + shell.boss_centres():
        cuts += countersink(x, y, Fit.clear_m3, Fit.csk_m3_d)
    for x, y in front_sensor_mount.screw_points() + drop_sensor_bracket.screw_points() + air_pod.screw_points():
        cuts += countersink(x, y, Fit.clear_m2, Fit.csk_m2_d)
    return cuts + drop_window()


def cable_slots():
    cuts = []
    for x, y in ((20.0, 45.0), (20.0, -45.0), (20.0, 20.0), (20.0, -20.0), (47.0, 58.0), (47.0, -58.0)):
        for d in (-4.5, 4.5):
            cuts.append(box(x + d - Fit.zip_t / 2.0, x + d + Fit.zip_t / 2.0, y - Fit.zip_w / 2.0, y + Fit.zip_w / 2.0, Floor.z0 - 1.0, Floor.z1 + 1.0))
    return cuts


@lru_cache(maxsize=1)
def build():
    adds, cuts = [], []
    for fn in (motor_cradles, omni_features, battery_features, bumper_features, deck_features, shelf_pillars):
        a, c = fn()
        adds += a
        cuts += c
    m = union([plate()] + adds)
    cuts += mount_holes() + deck_grid() + cable_slots()
    return cut(m, cuts)
