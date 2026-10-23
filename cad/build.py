import importlib
import os
import sys
import time
from geom import write_stl, drop_to_bed, bbox_size
from params import Print

HERE = os.path.dirname(os.path.abspath(__file__))
STL_DIR = os.path.join(HERE, "stl")

PARTS = (
    ("chassis_floor", 1),
    ("shell", 1),
    ("bumper", 1),
    ("front_sensor_mount", 1),
    ("drop_sensor_bracket", 1),
    ("air_pod", 1),
    ("neck_post", 1),
    ("tilt_yoke", 1),
    ("case_plate", 1),
    ("battery_hatch", 1),
    ("motor_clamp_cap", 2),
    ("wheel_hub", 2),
    ("omni_fork", 1),
    ("electronics_shelf", 1),
    ("dock_base", 1),
    ("dock_pin_block", 1),
    ("dock_wall", 1),
)

DENSITY = {"PLA": Print.pla_density}
BED = 220.0


def skin_thickness():
    return (Print.walls * Print.line_w + Print.top_bottom_layers * Print.layer) / 2.0


def estimate_grams(m, material):
    v = m.volume()
    shell = min(v, m.surface_area() * skin_thickness())
    return DENSITY[material] * (shell + Print.infill * (v - shell)) / 1000.0


def module(name):
    return importlib.import_module("parts." + name)


def print_pose(name):
    mod = module(name)
    return drop_to_bed(mod.build().rotate(mod.PRINT))


def export(names=None):
    os.makedirs(STL_DIR, exist_ok=True)
    rows = []
    for name, count in PARTS:
        if names and name not in names:
            continue
        t = time.time()
        mod = module(name)
        m = print_pose(name)
        path = os.path.join(STL_DIR, name + ".stl")
        write_stl(m, path)
        sx, sy, sz = bbox_size(m)
        g = estimate_grams(m, mod.MATERIAL)
        fits = sx <= BED and sy <= BED
        rows.append((name, count, mod.MATERIAL, sx, sy, sz, g, fits, m.num_tri(), time.time() - t))
        print("%-20s x%d %-4s %6.1f x %6.1f x %6.1f mm  %6.1f g each  bed %s  %d tris  %.1fs" % rows[-1], flush=True)
    total = {}
    for r in rows:
        total[r[2]] = total.get(r[2], 0.0) + r[1] * r[6]
    for k, v in total.items():
        print("total %s %.0f g" % (k, v))
    return rows


if __name__ == "__main__":
    export(sys.argv[1:] or None)
