import sys
import time
from params import Tilt, Body, ShellCfg, Dock, dock_pins
import assembly as A

EPS = 0.01


def overlap(a, b):
    ba = a.bounding_box()
    bb = b.bounding_box()
    if ba[3] < bb[0] or bb[3] < ba[0] or ba[4] < bb[1] or bb[4] < ba[1] or ba[5] < bb[2] or bb[5] < ba[2]:
        return 0.0
    return (a ^ b).volume()


def stationary(with_shell=True):
    d = {}
    d.update(A.static_parts())
    d.update(A.static_dummies())
    d.update(A.shell_mounted())
    if not with_shell:
        d.pop("shell")
    return {k: v[0] for k, v in d.items()}


EXPECTED_STATIC = {
    frozenset(("motor_L", "wheel_hub_L")): "D-shaft pressed into the hub bore",
    frozenset(("motor_R", "wheel_hub_R")): "D-shaft pressed into the hub bore",
    frozenset(("motor_L", "drive_wheel_L")): "D-shaft in the wheel bore",
    frozenset(("motor_R", "drive_wheel_R")): "D-shaft in the wheel bore",
    frozenset(("drop_sensor_bracket", "underside_screws")): "M2 self-tapper in its pilot hole",
    frozenset(("front_sensor_mount", "underside_screws")): "M2 self-tapper in its pilot hole",
    frozenset(("air_pod", "underside_screws")): "M2 self-tapper in its pilot hole",
    frozenset(("switch_L", "underside_screws")): "M2 through the switch's own mounting holes",
    frozenset(("switch_R", "underside_screws")): "M2 through the switch's own mounting holes",
}


def static_interference():
    s = stationary()
    names = sorted(s)
    hits = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            v = overlap(s[a], s[b])
            if v > EPS:
                hits.append((a, b, v, EXPECTED_STATIC.get(frozenset((a, b)), "")))
    return hits


def tilt_hits(theta, s):
    mv = {k: v[0] for k, v in A.moving(theta).items()}
    out = []
    for mk, mm in mv.items():
        for sk, sm in s.items():
            v = overlap(mm, sm)
            if v > EPS:
                out.append((mk, sk, v))
    return out


def tilt_sweep(step=Tilt.check_step):
    s = stationary()
    rows = []
    th = Tilt.t_min
    while th <= Tilt.t_max + 1e-9:
        rows.append((th, tilt_hits(th, s)))
        th += step
    return rows


def tilt_limits(step=1.0):
    s = stationary()
    lo = Tilt.rest
    while lo > -120.0 and not tilt_hits(lo - step, s):
        lo -= step
    hi = Tilt.rest
    while hi < 200.0 and not tilt_hits(hi + step, s):
        hi += step
    return lo, hi, tilt_hits(lo - step, s), tilt_hits(hi + step, s)


def shell_lift(max_dz=140.0, step=2.0):
    s = stationary(with_shell=False)
    for k in list(A.shell_mounted()):
        s.pop(k)
    moving = [A.static_parts()["shell"][0]] + [v[0] for v in A.shell_mounted().values()]
    hits = []
    dz = 0.0
    while dz <= max_dz:
        for m in moving:
            mt = m.translate((0.0, 0.0, dz))
            for k, sm in s.items():
                v = overlap(mt, sm)
                if v > EPS:
                    hits.append((dz, k, v))
        dz += step
    return hits


def docking():
    r = {}
    r.update({k: v[0] for k, v in A.robot_items(Tilt.rest).items()})
    d = {k: v[0] for k, v in A.dock_items().items()}
    hits = []
    for dk, dm in d.items():
        for rk, rm in r.items():
            v = overlap(dm, rm)
            if v > EPS:
                hits.append((dk, rk, v))
    pins = []
    for y, z, name in dock_pins():
        zc = ShellCfg.strips_z[ShellCfg.strip_names.index(name)]
        hw = ShellCfg.strip_w / 2.0
        hh = ShellCfg.strip_h / 2.0
        r_tip = Dock.pogo_tip_d / 2.0
        ok = abs(y) + r_tip <= hw and abs(z - zc) + r_tip <= hh
        pins.append((name, y, z, zc, ok, hh - abs(z - zc) - r_tip))
    return hits, pins


def sensor_cones():
    import dummies
    from params import Bumper
    out = []
    s = stationary()
    for name, cone in (("front", dummies.front_cone()), ("drop", dummies.drop_cone())):
        for k, m in s.items():
            v = overlap(cone, m)
            if v > EPS:
                out.append((name, k, v))
    pushed = A.static_parts()["bumper"][0].translate((-Bumper.travel, 0.0, 0.0))
    for name, cone in (("front", dummies.front_cone()), ("drop", dummies.drop_cone())):
        v = overlap(cone, pushed)
        if v > EPS:
            out.append((name, "bumper pushed fully back", v))
    return out


def bumper_travel():
    from params import Bumper, Switch, Fit
    import dummies
    s = stationary()
    for k in ("bumper", "bumper_screw_L", "bumper_screw_R", "spring_L", "spring_R", "switch_L", "switch_R"):
        s.pop(k)
    pushed = A.static_parts()["bumper"][0].translate((-Bumper.travel, 0.0, 0.0))
    hits = [(k, overlap(pushed, m)) for k, m in s.items() if overlap(pushed, m) > EPS]
    head_rest = Bumper.tower_x0 - Fit.m3_head_h
    lever_tip = dummies.switch_front_x() + Switch.lever_free
    body = dummies.switch_front_x()
    return hits, head_rest - lever_tip, head_rest - Bumper.travel - body


def tag_sightlines():
    import dummies
    from geom import tilt_place
    from params import Plate, Dock
    import numpy as np
    s = stationary()
    d = {k: v[0] for k, v in A.dock_items().items()}
    mv = {k: v[0] for k, v in A.moving(Tilt.rest).items() if k != "phone"}
    rows = []
    th = np.radians(Tilt.rest)
    n = np.array([np.cos(th), 0.0, np.sin(th)])
    u = np.array([-np.sin(th), 0.0, np.cos(th)])
    axis = np.array([Tilt.axis_x, 0.0, Tilt.axis_z])
    tag = np.array([Dock.wall_x1 - Dock.tag_recess, 0.0, Dock.tag_z])
    for cy in (-70.0, -55.0, -40.0, -25.0, 25.0, 40.0, 55.0, 70.0):
        for cs in (25.0, 10.0):
            cam = axis + (Plate.back_w - 0.5) * n + cs * u + np.array([0.0, cy, 0.0])
            line = dummies.sightline(cam - 2.5 * n, tag + np.array([1.0, 0.0, 0.0]))
            blocked = [k for k, m in list(s.items()) + list(mv.items()) + list(d.items()) if k != "dock_wall" and overlap(line, m) > EPS]
            rows.append((cy, cs, blocked))
    return rows


def tag_points():
    import numpy as np
    x = Dock.wall_x1 - Dock.tag_recess + 1.0
    h = Dock.tag_black / 2.0
    pts = [("centre", np.array([x, 0.0, Dock.tag_z]))]
    for name, dy, dz in (("top left", h, h), ("top right", -h, h), ("bottom left", h, -h), ("bottom right", -h, -h)):
        pts.append((name, np.array([x, dy, Dock.tag_z + dz])))
    return pts


def lens_view(side, lens, theta):
    import dummies
    import numpy as np
    from params import Plate, Phone
    y, s_up = dummies.rear_lenses(side)[lens]
    th = np.radians(theta)
    n = np.array([np.cos(th), 0.0, np.sin(th)])
    u = np.array([-np.sin(th), 0.0, np.cos(th)])
    axis = np.array([Tilt.axis_x, 0.0, Tilt.axis_z])
    cam = axis + (Plate.back_w - Phone.bar_proud) * n + s_up * u + np.array([0.0, y, 0.0])
    s = stationary()
    d = {k: v[0] for k, v in A.dock_items().items() if k != "dock_wall"}
    mv = {k: v[0] for k, v in A.moving(theta).items() if k != "phone"}
    rows = []
    for name, p in tag_points():
        line = dummies.sightline(cam - 0.5 * n, p)
        blocked = [k for k, m in list(s.items()) + list(mv.items()) + list(d.items()) if overlap(line, m) > EPS]
        v = p - cam
        look = -n
        across = np.degrees(np.arctan2(v[1], v @ look))
        up = np.degrees(np.arctan2(v @ u, v @ look))
        rows.append((name, blocked, across, up, float(np.linalg.norm(v))))
    return cam, rows


def lens_sightlines():
    from params import Phone
    out = []
    for side in (Phone.bar_side, -Phone.bar_side):
        for lens, _, _ in Phone.lenses:
            cam, rows = lens_view(side, lens, Tilt.rest)
            out.append((side, lens, cam, rows))
    return out


def lens_tilt_range(side, lens, lo=-20.0, hi=45.0, step=1.0):
    from params import Phone
    clear = []
    th = lo
    while th <= hi + 1e-9:
        _, rows = lens_view(side, lens, th)
        fits = all(abs(a) <= Phone.rear_fov_h / 2.0 and abs(b) <= Phone.rear_fov_v / 2.0 for _, _, a, b, _ in rows)
        if fits and not any(r[1] for r in rows):
            clear.append(th)
        th += step
    return clear


def bar_other_side():
    import dummies
    from geom import tilt_place, box
    from parts import tilt_yoke
    from params import Phone, Plate
    flip = dummies.phone_local(side=-Phone.bar_side)
    local = {"tilt_yoke": tilt_yoke.build(), "horn": dummies.horn_local(), "pin_screw": dummies.pin_screw_local()}
    fixed = [(k, overlap(flip, m)) for k, m in local.items() if overlap(flip, m) > EPS]
    side = -Phone.bar_side
    y0, y1 = sorted((side * (Phone.body_w / 2.0 - Phone.bar_top), side * (Phone.body_w / 2.0 - Phone.bar_bottom)))
    room = {}
    for s in (side, -side):
        a, b = sorted((s * abs(y0), s * abs(y1)))
        slab = box(-30.0, Plate.back_w, a, b, -Phone.h / 2.0, Phone.h / 2.0)
        reach = [m ^ slab for m in local.values()]
        top = max((r.bounding_box()[3] for r in reach if not r.is_empty()), default=None)
        room[s] = None if top is None else Plate.back_w - top
    st = stationary()
    swept = []
    th = Tilt.t_min
    while th <= Tilt.t_max + 1e-9:
        p = tilt_place(flip, th)
        for k, m in st.items():
            v = overlap(p, m)
            if v > EPS:
                swept.append((th, k, v))
        th += Tilt.check_step
    return fixed, room, swept


def servo_load(step=1.0):
    import math
    import build
    import dummies
    from params import Mass, Servo
    from parts import case_plate, tilt_yoke
    items = [("phone", Mass.phone, centroid(dummies.phone_local())),
             ("case_plate", build.estimate_grams(case_plate.build(), "PLA"), centroid(case_plate.build())),
             ("tilt_yoke", build.estimate_grams(tilt_yoke.build(), "PLA"), centroid(tilt_yoke.build()))]
    rows = []
    n = int(round((95.0 + 43.0) / step))
    for i in range(n + 1):
        th = -43.0 + i * step
        c, s = math.cos(math.radians(th)), math.sin(math.radians(th))
        t = sum(g * (p[0] * c - p[2] * s) for _, g, p in items) / 10000.0
        rows.append((th, t))
    return items, rows, Servo.stall_kgcm


def air_vents():
    import math
    import dummies
    from geom import union, box
    from params import AirPod, Body, BOARDS, Cap, Floor
    from parts import shell as shell_part
    a = AirPod
    s = stationary()
    shell = s.pop("shell")
    inner_y = a.board_y1 + a.comp_front + 0.1
    passages = union(shell_part.air_vents(inner_y, Body.half_y + a.vent_reach))
    blocked = [(k, overlap(passages, m)) for k, m in s.items() if overlap(passages, m) > EPS]
    for k, m in A.dock_items().items():
        if overlap(passages, m[0]) > EPS:
            blocked.append(("docked " + k, overlap(passages, m[0])))
    for theta in (Tilt.t_min, Tilt.rest, Tilt.t_max):
        for k, m in A.moving(theta).items():
            if overlap(passages, m[0]) > EPS:
                blocked.append(("%s at %+g deg" % (k, theta), overlap(passages, m[0])))
    shell_left = overlap(passages, shell)
    r = a.vent_w / 2.0
    area = a.vent_count * (a.vent_w * (a.vent_z1 - a.vent_z0 - a.vent_w) + math.pi * r * r)
    chip = dummies.air_chip()
    sources = {"motor_L": s["motor_L"], "motor_R": s["motor_R"], "cells": s["cells"], "servo": s["servo"],
               "phone at rest": A.moving(Tilt.rest)["phone"][0],
               "1000 uF cap": dummies.cyl_x(Cap.cy, Floor.z1 + Cap.lift + Cap.d / 2.0, Cap.d / 2.0, Cap.x0, Cap.x0 + Cap.l)}
    for b in BOARDS:
        sources[b.name] = box(b.x0, b.x1, b.y0, b.y1, b.z0, b.z0 + b.pcb_t + b.comp_h)
    gaps = {k: chip.min_gap(m, 400.0) for k, m in sources.items()}
    pod = A.static_parts()["air_pod"][0]
    open_to_inside = overlap(dummies.air_board(), pod)
    return blocked, shell_left, area, gaps, chip.bounding_box(), open_to_inside


WHEEL_KEYS = ("wheel_hub_L", "wheel_hub_R", "orings_L", "orings_R", "drive_wheel_L", "drive_wheel_R", "omni_wheel", "omni_bolt")


def centroid(m):
    from geom import mesh_arrays
    import numpy as np
    v, f = mesh_arrays(m)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    vol = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
    cen = (a + b + c) / 4.0
    return (cen * vol[:, None]).sum(axis=0) / vol.sum()


def mass_items(theta):
    import build
    from params import Mass, Cells, Floor, Omni, Wheel, Motor, Body, ShellCfg, BOARDS, Cap, Servo
    names = {"esp32s3_supermini": "esp", "drv8833": "drv", "hw465a_ups": "ups", "bms_1s": "bms"}
    items = []
    for name, (m, _) in A.static_parts().items():
        items.append((name, build.estimate_grams(m, "PLA"), centroid(m)))
    for name in ("case_plate", "tilt_yoke"):
        items.append((name, build.estimate_grams(build.module(name).build(), "PLA"), centroid(A.moving(theta)[name][0])))
    items.append(("phone", Mass.phone, centroid(A.moving(theta)["phone"][0])))
    items.append(("cells+holder", Mass.cells + Mass.holder, (Cells.cx, 0.0, Floor.z1 + Cells.holder_h / 2.0)))
    for s in (1.0, -1.0):
        items.append(("motor", Mass.motor, (0.0, s * 58.0, Motor.axis_z)))
        if Wheel.bought:
            items.append(("drive_wheel", Mass.drive_wheel, (0.0, s * Wheel.bought_centre_y, Motor.axis_z)))
        else:
            items.append(("drive_wheel", build.estimate_grams(build.module("wheel_hub").build(), "PLA") + 1.0, (0.0, s * Wheel.centre_y, Motor.axis_z)))
    items.append(("servo", Mass.servo, (Servo.centre_x, Servo.bottom_y + Servo.body_h / 2.0, Tilt.axis_z)))
    for b in BOARDS:
        items.append((b.name, getattr(Mass, names[b.name]), (b.cx, b.cy, b.z0 + 2.0)))
    items.append(("cap", Mass.cap, (Cap.x0 + Cap.l / 2.0, Cap.cy, Floor.z1 + 5.5)))
    items.append(("vl53 x2", 2 * Mass.vl53, (90.0, -15.0, 40.0)))
    from params import AirPod
    items.append(("bme688 board", Mass.bme688, (AirPod.cx, (AirPod.board_y0 + AirPod.board_y1) / 2.0, AirPod.chip_z)))
    items.append(("kcd11", Mass.kcd11, (Body.rear_x + 7.0, 0.0, ShellCfg.kcd_z)))
    items.append(("magnets", 2 * Mass.magnet, (Body.rear_x + 1.5, 0.0, ShellCfg.magnet_z)))
    items.append(("strips", Mass.strips, (Body.rear_x, 0.0, 29.0)))
    items.append(("omni wheel", Omni.mass, (Omni.x, 0.0, Omni.z)))
    items.append(("m6 bolt", Mass.bolt_m6, (Omni.x, 0.0, Omni.z)))
    items.append(("wiring", Mass.wiring, (-10.0, 0.0, 25.0)))
    items.append(("hardware", Mass.hardware, (5.0, 0.0, 20.0)))
    return items


def com_report(step=1.0):
    import numpy as np
    rows = []
    n = int(round((95.0 + 43.0) / step))
    for i in range(n + 1):
        th = -43.0 + i * step
        it = mass_items(th)
        m = sum(g for _, g, _ in it)
        c = sum(np.asarray(p, dtype=float) * g for _, g, p in it) / m
        rows.append((th, m, c))
    return rows


def omni_report():
    from params import Omni, DropSensor
    import dummies
    from geom import box
    lows = {"omni_wheel": A.static_dummies()["omni_wheel"][0].bounding_box()[2]}
    for k, (m, _) in A.drive_wheels(True).items():
        lows[k + " (bought)"] = m.bounding_box()[2]
    for k, (m, _) in A.drive_wheels(False).items():
        if k.startswith("orings"):
            lows[k + " (printed hub)"] = m.bounding_box()[2]
    s = stationary()
    clear_all = min(m.bounding_box()[2] for k, m in s.items() if k not in WHEEL_KEYS)
    clear_parts = min(m.bounding_box()[2] for k, m in s.items() if k not in WHEEL_KEYS + ("underside_screws",))
    foot = dummies.drop_cone() ^ box(-200.0, 400.0, -200.0, 200.0, 0.0, 0.05)
    fb = foot.bounding_box()
    return {"lows": lows, "clear_with_screws": clear_all, "clear_parts": clear_parts,
            "footprint_x": (fb[0], fb[3]), "footprint_y": (fb[1], fb[4]), "reading": DropSensor.reading,
            "footprint_rear_gap": fb[0] - Omni.x}


def omni_vs_everything():
    from params import Omni, Bumper, OmniFork
    from geom import cyl_y
    s = stationary()
    s["bumper_full_travel"] = A.static_parts()["bumper"][0].translate((-Bumper.travel, 0.0, 0.0))
    keep = cyl_y(Omni.x, Omni.z, Omni.keep_r, -Omni.keep_hw, Omni.keep_hw) - cyl_y(Omni.x, Omni.z, OmniFork.spacer_d / 2.0 + 0.5, -Omni.keep_hw - 1.0, Omni.keep_hw + 1.0)
    hits = []
    for k, m in s.items():
        if k in ("omni_wheel", "omni_bolt"):
            continue
        v = overlap(keep, m)
        if v > EPS:
            hits.append(("omni wheel + 2 mm", k, v))
    return hits


def printed_hub_variant():
    s = stationary()
    for k in ("drive_wheel_L", "drive_wheel_R"):
        s.pop(k, None)
    hits = []
    for k, (m, _) in A.drive_wheels(False).items():
        for sk, sm in s.items():
            v = overlap(m, sm)
            if v > EPS and frozenset((k, sk)) not in EXPECTED_STATIC:
                hits.append((k, sk, v))
    return hits


def main():
    t = time.time()
    print("== static interference (all parts and reference bodies) ==")
    for a, b, v, note in static_interference():
        print("  %-22s x %-22s %9.2f mm3 %s" % (a, b, v, note))
    print("== wheel to shell gap ==")
    sh = A.static_parts()["shell"][0]
    for bought in (True, False):
        for k, (m, _) in A.drive_wheels(bought).items():
            print("  %s%s min gap %.2f mm" % (k, " (bought)" if bought else " (printed)", sh.min_gap(m, 10.0)))
    print("== tilt sweep, %g deg steps ==" % Tilt.check_step)
    for th, hits in tilt_sweep():
        print("  %+6.1f  %s" % (th, "clear" if not hits else "; ".join("%s x %s %.2f mm3" % h for h in hits)))
    lo, hi, hl, hh = tilt_limits()
    print("== true tilt range (1 deg search) ==")
    print("  clear from %+g to %+g deg" % (lo, hi))
    print("  first hit below: %s" % ("; ".join("%s x %s %.2f" % h for h in hl) or "none in search"))
    print("  first hit above: %s" % ("; ".join("%s x %s %.2f" % h for h in hh) or "none in search"))
    print("== shell lift-off (yoke, plate and phone removed) ==")
    hits = shell_lift()
    print("  clear" if not hits else "\n".join("  dz %5.1f  %s %.2f mm3" % h for h in hits))
    print("== docking ==")
    hits, pins = docking()
    for h in hits:
        print("  %-16s x %-20s %.2f mm3" % h)
    for p in pins:
        print("  pin %-6s y %+5.2f z %5.2f on strip z %4.1f  inside %s (margin %.2f)" % p)
    print("== sensor fields of view ==")
    hits = sensor_cones()
    for h in hits:
        print("  %s cone x %s %.2f mm3" % h)
    if not hits:
        print("  clear")
    hits, play, left = bumper_travel()
    print("== bumper at full travel (%.1f mm) ==" % __import__("params").Bumper.travel)
    print("  %s" % ("clear (shell is the hard stop)" if not hits else ", ".join("%s %.2f" % h for h in hits)))
    print("  screw head to lever tip at rest %.2f mm; head to switch body at full travel %.2f mm" % (play, left))
    from params import Omni
    print("== front omni wheel (bought, %.0f x %.0f, contact x %.1f) ==" % (Omni.d, Omni.width, Omni.x))
    hits = omni_vs_everything()
    print("  swept wheel + 2 mm vs every part, reference body and the bumper at full travel: %s" % ("clear" if not hits else "; ".join("%s x %s %.2f" % h for h in hits)))
    hits = printed_hub_variant()
    print("  printed drive hub + O-rings variant: %s" % ("clear" if not hits else "; ".join("%s x %s %.2f" % h for h in hits)))
    r = omni_report()
    print("  lowest points (level check): " + ", ".join("%s %.2f" % kv for kv in r["lows"].items()))
    print("  ground clearance apart from the wheels: %.2f mm (printed parts), %.2f mm (with screw heads)" % (r["clear_parts"], r["clear_with_screws"]))
    print("  drop footprint on the floor: x %.1f to %.1f, y %.1f to %.1f; rear edge %.2f mm ahead of the omni contact" % (r["footprint_x"] + r["footprint_y"] + (r["footprint_rear_gap"],)))
    print("  drop sensor nominal reading on a flat floor: %.1f mm" % r["reading"])
    from params import AirPod
    print("== air sensor pod (BME688 behind %d vents in the left side wall) ==" % AirPod.vent_count)
    blocked, shell_left, area, gaps, cb, board_in_pod = air_vents()
    print("  vent passages from the board to %.0f mm outside the wall: %s" % (AirPod.vent_reach, "clear" if not blocked else "; ".join("%s %.2f mm3" % h for h in blocked)))
    print("  shell material left in the vents: %.3f mm3; open area %.0f mm2; board vs pod %.3f mm3" % (shell_left, area, board_in_pod))
    print("  chip at x %.1f, y %.1f, z %.1f to %.1f (inside air pools under the shell top at z %.1f)" % ((cb[0] + cb[3]) / 2.0, cb[4], cb[2], cb[5], Body.top_z - Body.wall))
    print("  chip to heat sources: " + ", ".join("%s %.0f mm" % kv for kv in sorted(gaps.items(), key=lambda kv: kv[1])))
    print("== centre of mass (axle at x = 0, omni contact at x = %.1f) ==" % Omni.x)
    rows = com_report(1.0)
    total = rows[0][1]
    lo = min(rows, key=lambda q: q[2][0])
    hi = max(rows, key=lambda q: q[2][0])
    for th in (-43.0, -35.0, 8.0, 90.0, 95.0):
        row = min(rows, key=lambda q: abs(q[0] - th))
        print("  tilt %+5.0f: CoM x %.1f, z %.1f; front wheel carries %.0f g of %.0f g (%.0f%%)" % (row[0], row[2][0], row[2][2], total * row[2][0] / Omni.x, total, 100.0 * row[2][0] / Omni.x))
    print("  CoM x ranges %.1f (tilt %+.0f) to %.1f (tilt %+.0f) over -43..+95" % (lo[2][0], lo[0], hi[2][0], hi[0]))
    items, load, stall = servo_load(1.0)
    print("== tilt servo holding load (phone %.0f g, case plate %.1f g, yoke %.1f g) ==" % tuple(g for _, g, _ in items))
    print("  phone centre of mass %.1f mm in front of the tilt axis, %.1f mm off its middle sideways" % (items[0][2][0], items[0][2][1]))
    peak = max(load, key=lambda q: abs(q[1]))
    rest = min(load, key=lambda q: abs(q[0] - Tilt.rest))
    print("  at rest (%+g deg) %.2f kg cm; largest %.2f kg cm at %+g deg; MG90S stall %.1f kg cm at 4.8 V, so %.0f %% of it" % (rest[0], rest[1], peak[1], peak[0], stall, 100.0 * abs(peak[1]) / stall))
    print("== rear camera to AprilTag sightlines when docked (camera on the case back) ==")
    for cy, cs, blocked in tag_sightlines():
        print("  camera y %+5.1f, %4.1f above phone centre: %s" % (cy, cs, "clear" if not blocked else "blocked by " + ", ".join(blocked)))
    from params import Phone
    print("== the phone's own rear lenses to the tag's centre and corners, docked, tilt %+g ==" % Tilt.rest)
    for side, lens, cam, rows in lens_sightlines():
        where = "camera bar on %sy (%s)" % ("+" if side > 0 else "-", "as mounted" if side == Phone.bar_side else "the other way round")
        bad = ["%s (%s)" % (name, ", ".join(blocked)) for name, blocked, _, _, _ in rows if blocked]
        c = rows[0]
        print("  %s, %s lens at y %+.1f, z %.1f: %s; tag centre %.0f mm away, %+.1f deg across, %+.1f deg up" % (
            where, lens, cam[1], cam[2], "all clear" if not bad else "blocked: " + "; ".join(bad), c[4], c[2], c[3]))
    clear = lens_tilt_range(Phone.bar_side, Phone.rear_camera)
    print("  %s lens as mounted sees the whole tag, inside a %.1f x %.1f deg view, at tilts: %s" % (
        Phone.rear_camera, Phone.rear_fov_h, Phone.rear_fov_v, ("%+g to %+g deg" % (clear[0], clear[-1])) if clear else "none from -20 to +45"))
    if clear and len(clear) != int(round(clear[-1] - clear[0])) + 1:
        print("  (with gaps: %s)" % ", ".join("%+g" % th for th in clear))
    print("== camera bar (%.1f mm proud of the case back) on the other side ==" % Phone.bar_proud)
    fixed, room, swept = bar_other_side()
    print("  against the parts that tilt with it: %s" % ("clear" if not fixed else "; ".join("%s %.2f mm3" % h for h in fixed)))
    for s, r in sorted(room.items()):
        print("  room behind the case back over the bar's span on %sy: %s" % ("+" if s > 0 else "-", "nothing there" if r is None else "%.2f mm" % r))
    print("  swept over the tilt range against the fixed parts: %s" % ("clear" if not swept else "; ".join("%+g %s %.2f" % h for h in swept)))
    print("%.1fs" % (time.time() - t))


if __name__ == "__main__":
    main()
