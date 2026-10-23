import math
from manifold3d import Manifold
from geom import box, boxc, cyl_x, cyl_y, cyl_z, sphere, union, extrude_x, rrect2, sym_y, mirror_y
from params import (Body, Floor, Motor, Wheel, Omni, OmniFork, Cells, BOARDS, Cap, Vl53, FrontSensor, DropSensor, AirPod,
                    Switch, Bumper, Phone, Plate, Servo, Horn, Tilt, Post, ShellCfg, Dock, Fit, Esp, dock_pins)


def phone_local(grow=0.0, side=None):
    side = Phone.bar_side if side is None else side
    w0 = Plate.back_w - grow
    w1 = Plate.back_w + Phone.t + grow
    hy = Phone.w / 2.0 + grow
    hs = Phone.h / 2.0 + grow
    case = extrude_x(rrect2(-hy, hy, -hs, hs, Phone.corner_r), w0, w1)
    if Phone.bar_proud <= 0.0:
        return case
    y0, y1 = sorted((side * (Phone.body_w / 2.0 - Phone.bar_top), side * (Phone.body_w / 2.0 - Phone.bar_bottom)))
    bar = box(Plate.back_w - Phone.bar_proud - grow, Plate.back_w + 1.0, y0 - grow, y1 + grow, -hs, hs)
    return union([case, bar])


def rear_lenses(side=None):
    side = Phone.bar_side if side is None else side
    out = {}
    for name, from_top, from_left in Phone.lenses:
        out[name] = (side * (Phone.body_w / 2.0 - from_top), -side * (Phone.body_h / 2.0 - from_left))
    return out


def servo(grow=0.0, front_tab=None):
    front_tab = (not Servo.snip_front_tab) if front_tab is None else front_tab
    g = grow
    z0 = Tilt.axis_z - Servo.body_w / 2.0
    z1 = Tilt.axis_z + Servo.body_w / 2.0
    y0 = Servo.bottom_y
    parts = [box(Servo.back_x - g, Servo.front_x + g, y0 - g, y0 + Servo.body_h + g, z0 - g, z1 + g)]
    ty0 = y0 + Servo.tab_y0
    parts.append(box(Servo.back_x - Servo.tab_len - g, Servo.back_x, ty0 - g, ty0 + Servo.tab_t + g, z0 - g, z1 + g))
    if front_tab:
        parts.append(box(Servo.front_x, Servo.front_x + Servo.tab_len + g, ty0 - g, ty0 + Servo.tab_t + g, z0 - g, z1 + g))
    parts.append(cyl_y(Tilt.axis_x, Tilt.axis_z, Servo.boss_d / 2.0 + g, y0 + Servo.body_h - 0.5, y0 + Servo.boss_top + g))
    parts.append(cyl_y(Tilt.axis_x, Tilt.axis_z, Servo.spline_d / 2.0 + g, y0 + Servo.boss_top - 0.1, y0 + Servo.total_h + g))
    if g == 0.0:
        parts.append(box(Servo.back_x - 6.0, Servo.back_x, y0 + 1.0, y0 + 1.0 + Servo.lead_w, z0 + 2.0, z0 + 2.0 + Servo.lead_h))
    return union(parts)


def horn_local():
    y1 = Horn.outer_y
    y0 = y1 - Horn.t
    disc = cyl_y(0.0, 0.0, Horn.d / 2.0, y0, y1)
    hub = cyl_y(0.0, 0.0, Horn.hub_d / 2.0, Horn.hub_y0, y0)
    bore = cyl_y(0.0, 0.0, Servo.spline_d / 2.0 + 0.1, Horn.hub_y0 - 1.0, y1 - 1.0)
    return union([disc, hub]) - bore


def motor(side):
    s = 1.0 if side > 0 else -1.0
    hw = Motor.gear_w / 2.0
    hh = Motor.gear_h / 2.0
    z = Motor.axis_z
    y1 = Motor.face_y
    y_g = y1 - Motor.gear_len
    y_c = y_g - Motor.can_len
    y_e = y_c - Motor.enc_len
    gear = box(-hw, hw, y_g, y1, z - hh, z + hh)
    can = box(-hw, hw, y_c, y_g, z - hh, z + hh) ^ cyl_y(0.0, z, hw, y_c, y_g)
    enc = box(-Motor.enc_w / 2.0, Motor.enc_w / 2.0, y_e, y_c, z - Motor.enc_h / 2.0, z + Motor.enc_h / 2.0)
    shaft = cyl_y(0.0, z, Motor.shaft_d / 2.0, y1, y1 + Motor.shaft_len)
    m = union([gear, can, enc, shaft])
    return m if s > 0 else mirror_y(m)


def omni_wheel():
    x, z = Omni.x, Omni.z
    hw = Omni.width / 2.0
    ring = cyl_y(x, z, Omni.r, -hw, hw) - cyl_y(x, z, Omni.boss_d / 2.0 + 4.0, -hw - 1.0, hw + 1.0)
    web = cyl_y(x, z, Omni.boss_d / 2.0 + 4.5, -2.0, 2.0)
    boss = cyl_y(x, z, Omni.boss_d / 2.0, -Omni.face_to_face / 2.0, Omni.face_to_face / 2.0)
    return union([ring, web, boss]) - cyl_y(x, z, Omni.bore / 2.0, -hw - 2.0, hw + 2.0)


def omni_bolt():
    from parts.omni_fork import hexagon
    from geom import extrude_y
    x, z = Omni.x, Omni.z
    y1 = OmniFork.cheek_y1
    shank = cyl_y(x, z, Omni.bolt_d / 2.0 - 0.05, y1 - OmniFork.bolt_len, y1)
    head = cyl_y(x, z, 5.0, y1, y1 + 4.0)
    y_in = -y1 + OmniFork.nut_pocket
    nut = extrude_y(hexagon(x, z, Omni.nut_af), y_in - Omni.nylock_h, y_in) - cyl_y(x, z, Omni.bolt_d / 2.0, y_in - 8.0, y_in + 1.0)
    return union([shank, head, nut])


def bought_drive_wheel(side):
    y0 = Wheel.inner_y
    y1 = y0 + Wheel.bought_w
    tyre = cyl_y(Motor.axis_x, Motor.axis_z, Wheel.bought_d / 2.0, y0, y1) - cyl_y(Motor.axis_x, Motor.axis_z, Wheel.bought_d / 2.0 - 5.0, y0 - 1.0, y1 + 1.0)
    rim = cyl_y(Motor.axis_x, Motor.axis_z, Wheel.bought_d / 2.0 - 5.0, y0 + 2.0, y1 - 2.0) - cyl_y(Motor.axis_x, Motor.axis_z, Wheel.bought_hub_d / 2.0 + 2.0, y0, y1)
    hub = cyl_y(Motor.axis_x, Motor.axis_z, Wheel.bought_hub_d / 2.0, y0, y1) - cyl_y(Motor.axis_x, Motor.axis_z, Motor.shaft_d / 2.0 + 0.05, y0 - 1.0, y1 + 1.0)
    m = union([tyre, rim, hub])
    return m if side > 0 else mirror_y(m)


def orings(side):
    from parts.wheel_hub import groove_centres
    out = []
    r_c = (Wheel.floor_d + Wheel.oring_cs) / 2.0
    for zc in groove_centres():
        y = Wheel.centre_y - Wheel.w / 2.0 + zc
        out.append(cyl_y(Motor.axis_x, Motor.axis_z, r_c + Wheel.oring_cs / 2.0, y - Wheel.oring_cs / 2.0, y + Wheel.oring_cs / 2.0)
                   - cyl_y(Motor.axis_x, Motor.axis_z, Wheel.floor_d / 2.0, y - 2.0, y + 2.0))
    m = union(out)
    return m if side > 0 else mirror_y(m)


def _csk(x, y, d_head, d_shank, length):
    z0 = Floor.z0
    depth = (d_head - d_shank) / 2.0
    return union([cyl_z(x, y, d_head / 2.0, z0, z0 + depth, r1=d_shank / 2.0), cyl_z(x, y, d_shank / 2.0 - 0.05, z0 + depth - 0.01, z0 + length)])


def underside_screws():
    from parts import shell, front_sensor_mount, drop_sensor_bracket, air_pod
    out = []
    for x, y in list(shell.boss_centres()) + list(Post.screw_xy):
        out.append(_csk(x, y, Fit.csk_m3_d - 0.2, 3.0, 8.0))
    for s in (1.0, -1.0):
        out.append(_csk(Cells.cx, s * Cells.screw_y, Fit.csk_m3_d - 0.2, 3.0, 8.0))
    for x, y in front_sensor_mount.screw_points() + drop_sensor_bracket.screw_points() + air_pod.screw_points():
        out.append(_csk(x, y, Fit.csk_m2_d - 0.2, 2.0, 6.0))
    xb = switch_front_x() - Switch.h + Switch.hole_from_back
    y_mid = Bumper.guide_y + Switch.lever_contact_from_end - Switch.l / 2.0
    for s in (1.0, -1.0):
        for k in (-0.5, 0.5):
            y = s * (y_mid + k * Switch.hole_pitch)
            out.append(cyl_z(xb, y, Fit.m2_head_d / 2.0, Floor.z0 + 0.05, Floor.z0 + Fit.m2_head_h))
            out.append(cyl_z(xb, y, 0.95, Floor.z0 + Fit.m2_head_h - 0.01, Floor.z0 + 12.0))
    return union(out)


def cell_pack():
    x0, x1 = Cells.x0, Cells.x1
    hy = Cells.holder_y / 2.0
    z0 = Floor.z1
    z1 = z0 + Cells.holder_h
    holder = box(x0, x1, -hy, hy, z0, z0 + 2.0)
    walls = union([box(x0, x1, -hy, -hy + 2.0, z0, z1), box(x0, x1, hy - 2.0, hy, z0, z1)])
    r = Cells.cell_d / 2.0
    cz = z0 + 1.0 + r
    c1 = cyl_y(Cells.cx - Cells.holder_x / 4.0, cz, r, -Cells.cell_l / 2.0, Cells.cell_l / 2.0)
    c2 = cyl_y(Cells.cx + Cells.holder_x / 4.0, cz, r, -Cells.cell_l / 2.0, Cells.cell_l / 2.0)
    return union([holder, walls, c1, c2])


def boards():
    out = []
    for b in BOARDS:
        z0 = b.z0
        out.append(box(b.x0, b.x1, b.y0, b.y1, z0, z0 + b.pcb_t))
        out.append(box(b.x0 + 1.5, b.x1 - 1.5, b.y0 + 1.5, b.y1 - 1.5, z0 + b.pcb_t, z0 + b.pcb_t + b.comp_h))
    e = BOARDS[0]
    uz0 = e.z0 + e.pcb_t
    out.append(box(e.x0 - Esp.usb_overhang, e.x0 + 7.0, e.cy - Esp.usb_w / 2.0, e.cy + Esp.usb_w / 2.0, uz0, uz0 + Esp.usb_h))
    cz = Floor.z1 + Cap.lift + Cap.d / 2.0
    out.append(cyl_x(Cap.cy, cz, Cap.d / 2.0, Cap.x0, Cap.x0 + Cap.l))
    return union(out)


def vl53_front():
    x1 = FrontSensor.chip_face_x - Vl53.chip_h
    x0 = x1 - Vl53.pcb_t
    hy = Vl53.ly / 2.0
    hz = Vl53.lx / 2.0
    cy = FrontSensor.y - Vl53.chip_off_short
    cz = FrontSensor.z - Vl53.chip_off_long
    pcb = box(x0, x1, cy - hy, cy + hy, cz - hz, cz + hz)
    chip = box(x1, FrontSensor.chip_face_x, FrontSensor.y - 2.2, FrontSensor.y + 1.2, FrontSensor.z - 1.2, FrontSensor.z + 1.2)
    return union([pcb, chip])


def air_chip():
    a = AirPod
    hw = a.chip_w / 2.0
    return box(a.cx - hw, a.cx + hw, a.board_y1, a.board_y1 + a.chip_h, a.chip_z - hw, a.chip_z + hw)


def air_board():
    a = AirPod
    pcb = box(a.board_x0, a.board_x1, a.board_y0, a.board_y1, a.board_z0, a.board_z1)
    m = a.groove_depth + 0.3
    front = box(a.board_x0 + m, a.board_x1 - m, a.board_y1, a.board_y1 + a.comp_front, a.board_z0 + 4.0, a.board_z1 - 1.0)
    back = box(a.board_x0 + m, a.board_x1 - m, a.board_y0 - a.comp_back, a.board_y0, a.board_z0 + 4.0, a.board_z1 - 1.0)
    return union([pcb, front, back, air_chip()])


def drop_place(m):
    return m.rotate((0.0, -DropSensor.pitch, 0.0)).translate((DropSensor.x, DropSensor.y, DropSensor.chip_z))


def vl53_drop():
    z0 = Vl53.chip_h
    hx = Vl53.ly / 2.0
    hy = Vl53.lx / 2.0
    pcb = box(-Vl53.chip_off_short - hx, -Vl53.chip_off_short + hx, -Vl53.chip_off_long - hy, -Vl53.chip_off_long + hy, z0, z0 + Vl53.pcb_t)
    chip = box(-1.2, 1.2, -2.2, 2.2, 0.0, z0)
    return drop_place(union([pcb, chip]))


def drop_cone(grow=0.0, extra=12.0):
    import math
    t = math.tan(math.radians(DropSensor.half_fov))
    length = DropSensor.chip_z / math.cos(math.radians(DropSensor.pitch)) + extra
    r0 = Vl53.aperture_sep / 2.0 + grow
    r1 = r0 + length * t
    cone = Manifold.cylinder(length + grow, r1, r0).translate((0.0, 0.0, -length))
    return drop_place(cone)


def front_cone(length=40.0):
    import math
    x0 = FrontSensor.chip_face_x + 0.3
    r0 = Vl53.aperture_sep / 2.0 + 0.3 * math.tan(math.radians(Vl53.fov_deg / 2.0))
    r1 = Vl53.aperture_sep / 2.0 + (length + 0.3) * math.tan(math.radians(Vl53.fov_deg / 2.0))
    return cyl_x(FrontSensor.y, FrontSensor.z, r0, x0, x0 + length, r1=r1)


def sightline(p0, p1, r=1.5):
    import numpy as np
    from manifold3d import Manifold
    a = np.asarray(p0, dtype=float)
    b = np.asarray(p1, dtype=float)
    return Manifold.hull(union([sphere(a[0], a[1], a[2], r, 12), sphere(b[0], b[1], b[2], r, 12)]))


def switch_body(side):
    s = 1.0 if side > 0 else -1.0
    xf = switch_front_x()
    x0 = xf - Switch.h
    z0 = Floor.z1 + switch_pedestal_h()
    y_end = Bumper.guide_y + Switch.lever_contact_from_end
    body = box(x0, xf, y_end - Switch.l, y_end, z0, z0 + Switch.t)
    lever = box(xf, xf + Switch.lever_free, y_end - Switch.l + 2.0, y_end - 1.0, z0 + Switch.t / 2.0 - 1.0, z0 + Switch.t / 2.0 + 1.0)
    m = union([body, lever])
    return m if s > 0 else mirror_y(m)


def switch_front_x():
    return Bumper.tower_x0 - Fit.m3_head_h - Switch.rest_play - Switch.lever_free


def switch_pedestal_h():
    return Bumper.guide_z - Switch.t / 2.0 - Floor.z1


def bumper_screw(side, travel=0.0):
    s = 1.0 if side > 0 else -1.0
    xh = Bumper.tower_x0 - travel
    shank = cyl_x(Bumper.guide_y, Bumper.guide_z, 1.5, xh, xh + Bumper.screw_len)
    head = cyl_x(Bumper.guide_y, Bumper.guide_z, Fit.m3_head_d / 2.0, xh - Fit.m3_head_h, xh)
    m = union([shank, head])
    return m if s > 0 else mirror_y(m)


def bumper_spring(side):
    s = 1.0 if side > 0 else -1.0
    from geom import outline_x_at
    xb = outline_x_at(Bumper.guide_y, Bumper.gap) - Bumper.boss_back
    r = Bumper.spring_od / 2.0
    m = cyl_x(Bumper.guide_y, Bumper.guide_z, r, Bumper.tower_x1, xb) - cyl_x(Bumper.guide_y, Bumper.guide_z, r - 0.6, Bumper.tower_x1 - 1, xb + 1)
    return m if s > 0 else mirror_y(m)


def strips():
    out = []
    hw = ShellCfg.strip_w / 2.0
    for z in ShellCfg.strips_z:
        out.append(box(Body.rear_x, Body.rear_x + ShellCfg.strip_t, -hw, hw, z - ShellCfg.strip_h / 2.0, z + ShellCfg.strip_h / 2.0))
    return union(out)


def robot_magnets():
    out = []
    for s in (1.0, -1.0):
        out.append(cyl_x(s * ShellCfg.magnet_y, ShellCfg.magnet_z, 5.0, Body.rear_x, Body.rear_x + 3.0))
    return union(out)


def kcd11():
    x0 = Body.rear_x
    bezel = box(x0 - 2.0, x0, -ShellCfg.kcd_w / 2.0 - 1.0, ShellCfg.kcd_w / 2.0 + 1.0, ShellCfg.kcd_z - ShellCfg.kcd_h / 2.0 - 1.0, ShellCfg.kcd_z + ShellCfg.kcd_h / 2.0 + 1.0)
    body = box(x0, x0 + 14.0, -ShellCfg.kcd_w / 2.0 + 0.2, ShellCfg.kcd_w / 2.0 - 0.2, ShellCfg.kcd_z - ShellCfg.kcd_h / 2.0 + 0.2, ShellCfg.kcd_z + ShellCfg.kcd_h / 2.0 - 0.2)
    return union([bezel, body])


def pogo_pins(compressed=True):
    out = []
    tip_x = Body.rear_x if compressed else Dock.face_x + Dock.pogo_proud
    base_x = Dock.face_x + Dock.pogo_proud - Dock.pogo_len
    for (y, z, _) in dock_pins():
        out.append(cyl_x(y, z, Dock.pogo_d / 2.0, base_x, Dock.face_x - 0.01))
        out.append(cyl_x(y, z, Dock.pogo_tip_d / 2.0, Dock.face_x - 0.02, tip_x - 0.05))
    return union(out)


def perfboard():
    x1 = Dock.face_x + Dock.pogo_proud - Dock.pogo_len
    return box(x1 - Dock.perf_t, x1, -Dock.perf_w / 2.0, Dock.perf_w / 2.0, 29.0 - Dock.perf_h / 2.0, 29.0 + Dock.perf_h / 2.0)


def dock_magnets():
    out = []
    for s in (1.0, -1.0):
        out.append(cyl_x(s * ShellCfg.magnet_y, ShellCfg.magnet_z, 5.0, Dock.face_x - 3.0, Dock.face_x))
    return union(out)


def pin_screw_local():
    from params import Yoke
    y_out = Post.arm_y0 - Yoke.pin_gap - Yoke.pin_ear_t
    shank = cyl_y(0.0, 0.0, 1.5, y_out, Post.arm_y1 - 1.0)
    head = cyl_y(0.0, 0.0, Fit.m3_head_d / 2.0, y_out - Fit.m3_head_h, y_out)
    return union([shank, head])
