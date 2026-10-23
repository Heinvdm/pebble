import os
import sys
import time
from functools import lru_cache
from geom import union, tilt_place, mirror_y
from params import Tilt, Wheel, Motor, Body
from render import render
import dummies
from parts import (chassis_floor, shell, bumper, front_sensor_mount, drop_sensor_bracket, neck_post, tilt_yoke,
                   case_plate, battery_hatch, motor_clamp_cap, wheel_hub, omni_fork, electronics_shelf, dock_base,
                   dock_pin_block, dock_wall, air_pod)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "renders")

PART = (236, 156, 52)
RUBBER = (40, 40, 44)
SHELL = (240, 196, 120)
PLA = (92, 156, 214)
DUMMY = (150, 150, 158)
BOARD = (60, 140, 80)
PHONE = (48, 52, 70)
SERVO = (70, 90, 190)
CELL = (190, 110, 60)
BRASS = (205, 170, 60)
MAGNET = (120, 120, 130)


def wheel_place(m, side):
    w = m.rotate((-90.0, 0.0, 0.0)).translate((Motor.axis_x, Wheel.centre_y - Wheel.w / 2.0, Motor.axis_z))
    return w if side > 0 else mirror_y(w)


def drive_wheels(bought=None):
    bought = Wheel.bought if bought is None else bought
    if bought:
        return {"drive_wheel_L": (dummies.bought_drive_wheel(1), RUBBER), "drive_wheel_R": (dummies.bought_drive_wheel(-1), RUBBER)}
    return {"wheel_hub_L": (wheel_place(wheel_hub.build(), 1), PART), "wheel_hub_R": (wheel_place(wheel_hub.build(), -1), PART),
            "orings_L": (dummies.orings(1), RUBBER), "orings_R": (dummies.orings(-1), RUBBER)}


@lru_cache(maxsize=1)
def static_parts():
    cap = motor_clamp_cap.build()
    d = {
        "chassis_floor": (chassis_floor.build(), PART),
        "shell": (shell.build(), SHELL),
        "bumper": (bumper.build(), PART),
        "front_sensor_mount": (front_sensor_mount.build(), PART),
        "drop_sensor_bracket": (drop_sensor_bracket.build(), PART),
        "neck_post": (neck_post.build(), PART),
        "battery_hatch": (battery_hatch.build(), PART),
        "electronics_shelf": (electronics_shelf.build(), PART),
        "motor_clamp_cap_L": (cap, PART),
        "motor_clamp_cap_R": (mirror_y(cap), PART),
        "omni_fork": (omni_fork.build(), PART),
        "air_pod": (air_pod.build(), PART),
    }
    return d


@lru_cache(maxsize=1)
def static_dummies():
    d = {
        "motor_L": (dummies.motor(1), DUMMY),
        "motor_R": (dummies.motor(-1), DUMMY),
        "omni_wheel": (dummies.omni_wheel(), RUBBER),
        "omni_bolt": (dummies.omni_bolt(), DUMMY),
        "underside_screws": (dummies.underside_screws(), DUMMY),
        "cells": (dummies.cell_pack(), CELL),
        "boards": (dummies.boards(), BOARD),
        "servo": (dummies.servo(), SERVO),
        "vl53_front": (dummies.vl53_front(), BOARD),
        "vl53_drop": (dummies.vl53_drop(), BOARD),
        "switch_L": (dummies.switch_body(1), DUMMY),
        "switch_R": (dummies.switch_body(-1), DUMMY),
        "bumper_screw_L": (dummies.bumper_screw(1), DUMMY),
        "bumper_screw_R": (dummies.bumper_screw(-1), DUMMY),
        "spring_L": (dummies.bumper_spring(1), DUMMY),
        "spring_R": (dummies.bumper_spring(-1), DUMMY),
        "air_board": (dummies.air_board(), BOARD),
    }
    d.update(drive_wheels())
    return d


@lru_cache(maxsize=1)
def shell_mounted():
    return {
        "dock_strips": (dummies.strips(), BRASS),
        "robot_magnets": (dummies.robot_magnets(), MAGNET),
        "kcd11": (dummies.kcd11(), DUMMY),
    }


@lru_cache(maxsize=None)
def moving(theta):
    return {
        "phone": (tilt_place(dummies.phone_local(), theta), PHONE),
        "case_plate": (tilt_place(case_plate.build(), theta), PART),
        "tilt_yoke": (tilt_place(tilt_yoke.build(), theta), PART),
        "horn": (tilt_place(dummies.horn_local(), theta), DUMMY),
        "pin_screw": (tilt_place(dummies.pin_screw_local(), theta), DUMMY),
    }


@lru_cache(maxsize=1)
def dock_items():
    return {
        "dock_base": (dock_base.build(), PLA),
        "dock_pin_block": (dock_pin_block.build(), PLA),
        "dock_wall": (dock_wall.build(), PLA),
        "pogo_pins": (dummies.pogo_pins(compressed=True), BRASS),
        "perfboard": (dummies.perfboard(), BOARD),
        "dock_magnets": (dummies.dock_magnets(), MAGNET),
    }


def robot_items(theta, with_shell=True):
    d = {}
    d.update(static_parts())
    d.update(static_dummies())
    d.update(shell_mounted())
    d.update(moving(theta))
    if not with_shell:
        d.pop("shell")
    return d


def items_list(d):
    return [v for v in d.values()]


def render_views():
    os.makedirs(OUT, exist_ok=True)
    out = []
    for theta, tag in ((Tilt.rest, "rest"), (Tilt.t_min, "down35"), (Tilt.t_max, "up90")):
        items = items_list(robot_items(theta))
        p = os.path.join(OUT, "assembly_front_iso_%s.png" % tag)
        render(items, p, -38.0, 22.0, title="Pebble, tilt %+g deg, front iso" % theta)
        out.append(p)
        p = os.path.join(OUT, "assembly_side_%s.png" % tag)
        render(items, p, -90.0, 0.0, title="Pebble, tilt %+g deg, side (from -y)" % theta)
        out.append(p)
    items = items_list(robot_items(Tilt.rest, with_shell=False))
    p = os.path.join(OUT, "assembly_no_shell_iso.png")
    render(items, p, -50.0, 35.0, title="Pebble without shell, rest tilt")
    out.append(p)
    p = os.path.join(OUT, "assembly_no_shell_rear_iso.png")
    render(items, p, 140.0, 35.0, title="Pebble without shell, from rear")
    out.append(p)
    d = robot_items(Tilt.rest)
    d.update(dock_items())
    p = os.path.join(OUT, "docked_rear_iso.png")
    render(items_list(d), p, 145.0, 25.0, title="Docked (pins compressed 1.5 mm)")
    out.append(p)
    p = os.path.join(OUT, "docked_side.png")
    render(items_list(d), p, -90.0, 0.0, title="Docked, side")
    out.append(p)
    dd = dict(dock_items())
    p = os.path.join(OUT, "dock_iso.png")
    render(items_list(dd), p, 35.0, 30.0, title="Dock")
    out.append(p)
    return out


def render_details():
    out = []
    d = robot_items(Tilt.rest, with_shell=False)
    for k in ("phone",):
        d.pop(k)
    neck = [d[k] for k in ("neck_post", "servo", "tilt_yoke", "case_plate", "horn", "pin_screw")]
    p = os.path.join(OUT, "detail_neck_front.png")
    render(neck, p, -35.0, 20.0, title="Neck: post, MG90S (front tab snipped), yoke, case plate")
    out.append(p)
    p = os.path.join(OUT, "detail_neck_back.png")
    render(neck, p, 135.0, 25.0, title="Neck from behind")
    out.append(p)
    front = [v for k, v in d.items() if k not in ("neck_post", "servo", "tilt_yoke", "case_plate", "horn", "pin_screw", "dock_strips", "robot_magnets", "kcd11")]
    p = os.path.join(OUT, "detail_front_interior.png")
    render(front, p, -150.0, 40.0, bounds=(55.0, -80.0, 0.0, 110.0, 80.0, 50.0), title="Front interior: bumper guides, switches, sensors, omni wheel")
    out.append(p)
    rear = robot_items(Tilt.rest)
    rear_items = [rear[k] for k in ("shell", "chassis_floor", "boards", "dock_strips", "robot_magnets", "kcd11")]
    p = os.path.join(OUT, "detail_rear_wall.png")
    render(rear_items, p, 180.0, 10.0, bounds=(-80.0, -75.0, 10.0, -60.0, 75.0, 80.0), title="Rear wall: switch, dock strips, magnets, ESP32 USB slot")
    out.append(p)
    side = robot_items(Tilt.rest)
    near = (30.0, 40.0, 5.0, 80.0, 100.0, 55.0)
    p = os.path.join(OUT, "detail_air_vents.png")
    render([side[k] for k in ("shell", "chassis_floor", "bumper", "drive_wheel_L", "air_pod", "air_board")], p, 70.0, 12.0, bounds=near,
           title="Air sensor vents in the left side wall, ahead of the wheel and behind the bumper")
    out.append(p)
    p = os.path.join(OUT, "detail_air_pod.png")
    render([side[k] for k in ("chassis_floor", "air_pod", "air_board")], p, -115.0, 28.0,
           bounds=(42.0, 56.0, 12.0, 72.0, 74.0, 44.0), title="Air pod from inside (shell hidden): walled off from the robot, open only to the vents")
    out.append(p)
    under = [v for k, v in robot_items(Tilt.rest).items()]
    p = os.path.join(OUT, "detail_underside.png")
    render(under, p, -40.0, -50.0, title="Underside: hatch, omni wheel, drop-sensor window, screws")
    out.append(p)
    return out


def render_omni():
    out = []
    d = robot_items(Tilt.rest)
    keys = ("chassis_floor", "omni_fork", "omni_wheel", "omni_bolt", "drop_sensor_bracket", "front_sensor_mount", "vl53_front",
            "vl53_drop", "battery_hatch", "underside_screws", "neck_post", "bumper", "cells")
    items = [d[k] for k in keys]
    p = os.path.join(OUT, "omni_from_below.png")
    render(items, p, -35.0, -40.0, bounds=(25.0, -50.0, -1.0, 110.0, 50.0, 66.0), title="58 mm bought omni wheel from below: floor slot, fork, drop window ahead")
    out.append(p)
    side = [d[k] for k in ("chassis_floor", "omni_fork", "omni_wheel", "omni_bolt", "front_sensor_mount", "vl53_front",
                           "drop_sensor_bracket", "vl53_drop", "neck_post", "bumper")]
    p = os.path.join(OUT, "omni_side.png")
    render(side, p, -90.0, 0.0, bounds=(20.0, -50.0, -1.0, 110.0, 50.0, 70.0), title="Omni wheel from the side (-y), shell hidden")
    out.append(p)
    cone = dummies.drop_cone()
    front = [d[k] for k in ("chassis_floor", "shell", "bumper", "drop_sensor_bracket", "vl53_drop", "omni_fork", "omni_wheel",
                            "front_sensor_mount", "vl53_front")] + [(cone, (220, 60, 60))]
    p = os.path.join(OUT, "drop_sensor_side.png")
    render([front[0]] + front[2:], p, -90.0, 0.0, bounds=(30.0, -45.0, -1.0, 125.0, 0.0, 62.0), title="Drop sensor pitched 32 deg (shell hidden): cone (red) passes under the bumper, well ahead of the omni contact")
    out.append(p)
    p = os.path.join(OUT, "drop_sensor_front_below.png")
    render(front, p, -30.0, -25.0, bounds=(40.0, -60.0, -1.0, 125.0, 20.0, 60.0), title="Drop sensor cone through the floor, shell and bumper notches")
    out.append(p)
    lay = robot_items(Tilt.rest, with_shell=False)
    for k in ("phone", "case_plate", "tilt_yoke", "horn", "pin_screw", "neck_post", "servo", "dock_strips", "robot_magnets", "kcd11"):
        lay.pop(k, None)
    p = os.path.join(OUT, "layout_top.png")
    render(list(lay.values()), p, -90.0, 89.0, title="Layout from above: cells behind the axle, shelf with UPS and DRV8833, omni wheel in front")
    out.append(p)
    p = os.path.join(OUT, "layout_iso.png")
    render(list(lay.values()), p, -50.0, 35.0, title="Layout (shell, neck and phone hidden)")
    out.append(p)
    return out


def render_parts():
    import build as b
    from geom import drop_to_bed
    out = []
    for name, _ in b.PARTS:
        mod = b.module(name)
        col = PART if not name.startswith("dock") else PLA
        p = os.path.join(OUT, "part_%s.png" % name)
        render([(b.print_pose(name), col)], p, -50.0, 30.0, title="%s (print orientation, %s)" % (name, mod.MATERIAL))
        out.append(p)
    return out


if __name__ == "__main__":
    t = time.time()
    what = sys.argv[1:] or ["views", "details", "omni", "parts"]
    if "parts" in what:
        for p in render_parts():
            print(p, flush=True)
    if "omni" in what:
        for p in render_omni():
            print(p, flush=True)
    if "details" in what:
        for p in render_details():
            print(p, flush=True)
    if "views" in what:
        for p in render_views():
            print(p, flush=True)
    print("%.1fs" % (time.time() - t))
