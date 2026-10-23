import math

import numpy as np

from pebble.eyes.geometry import Box
from pebble.seams.sight import BODY_POINTS

HEAD = {"nose": (0.0, 0.09, 0.0), "left_eye": (-0.03, 0.07, 0.03), "right_eye": (0.03, 0.07, 0.03), "left_ear": (-0.075, 0.0, 0.0), "right_ear": (0.075, 0.0, 0.0)}


def _person(head_centre, shoulders, elbows, wrists, hips, knees, ankles, head_axes=None):
    joints = {}
    forward, up = head_axes or ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    right = np.cross(np.array(forward), np.array(up))
    for name, (x, y, z) in HEAD.items():
        p = np.array(head_centre) - x * right + y * np.array(forward) + z * np.array(up)
        joints[name] = tuple(p)
    for side, sign in (("left", -1), ("right", 1)):
        for name, (x, y, z) in (("shoulder", shoulders), ("elbow", elbows), ("wrist", wrists), ("hip", hips), ("knee", knees), ("ankle", ankles)):
            joints[f"{side}_{name}"] = (sign * x, y, z)
    return joints


POSES = {
    "standing": _person((0, 0.02, 1.62), (0.19, 0, 1.43), (0.22, 0, 1.13), (0.24, 0.05, 0.85), (0.1, 0, 0.92), (0.1, 0.02, 0.5), (0.1, 0, 0.08)),
    "chair": _person((0, 0.0, 1.17), (0.19, -0.03, 0.98), (0.22, 0.05, 0.72), (0.2, 0.3, 0.62), (0.1, 0, 0.47), (0.12, 0.45, 0.5), (0.12, 0.47, 0.08)),
    "floor_sitting": _person((0, 0.0, 0.83), (0.19, -0.02, 0.64), (0.23, 0.05, 0.38), (0.22, 0.3, 0.2), (0.1, 0, 0.12), (0.15, 0.4, 0.14), (0.12, 0.8, 0.06)),
    "crouching": _person((0, 0.42, 1.0), (0.19, 0.25, 0.88), (0.2, 0.42, 0.68), (0.18, 0.55, 0.5), (0.1, -0.1, 0.42), (0.12, 0.25, 0.5), (0.1, 0.05, 0.08), ((0, 0.6, -0.8), (0, 0.8, 0.6))),
    "lying_floor": _person((0, 0.8, 0.14), (0.19, 0.55, 0.12), (0.25, 0.3, 0.1), (0.28, 0.05, 0.08), (0.1, 0, 0.12), (0.1, -0.45, 0.12), (0.1, -0.85, 0.08), ((0, 0, 1), (0, 1, 0))),
    "lying_couch": None,
    "leaning_back": _person((0, -0.45, 1.0), (0.19, -0.32, 0.85), (0.24, -0.1, 0.62), (0.2, 0.25, 0.55), (0.1, 0, 0.47), (0.12, 0.45, 0.5), (0.12, 0.5, 0.08), ((0, 0.5, 0.85), (0, -0.85, 0.5))),
}
POSES["lying_couch"] = {k: (x, y, z + 0.45) for k, (x, y, z) in POSES["lying_floor"].items()}


def view(pose: str, distance: float, bearing_deg: float = 0.0, facing_deg: float = 180.0, camera_height: float = 0.14, pitch_deg: float = 8.0, width: int = 640, height: int = 480, fov_h_deg: float = 70.0, noise: float = 0.0, seed: int = 0):
    rng = np.random.default_rng(seed)
    yaw = math.radians(facing_deg)
    rotation = np.array([[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]])
    b = math.radians(bearing_deg)
    place = np.array([distance * math.sin(b), distance * math.cos(b), 0.0])
    p = math.radians(pitch_deg)
    forward = np.array([0, math.cos(p), math.sin(p)])
    up = np.array([0, -math.sin(p), math.cos(p)])
    f = (width / 2) / math.tan(math.radians(fov_h_deg) / 2)
    raw = np.zeros((len(BODY_POINTS), 3), np.float32)
    for i, name in enumerate(BODY_POINTS):
        world = rotation @ np.array(POSES[pose][name]) + place - np.array([0, 0, camera_height])
        z = world @ forward
        x = world[0] / z * f
        y = -(world @ up) / z * f
        raw[i] = (0.5 + x / width + rng.normal(0, noise), 0.5 + y / height + rng.normal(0, noise), 0.9)
    us, vs = raw[:, 0], raw[:, 1]
    mx, my = (us.max() - us.min()) * 0.08, (vs.max() - vs.min()) * 0.08
    box = Box(float(us.min() - mx), float(vs.min() - my), float(us.max() - us.min() + 2 * mx), float(vs.max() - vs.min() + 2 * my), 0.9)
    return raw, box
