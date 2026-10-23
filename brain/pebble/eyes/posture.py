import math

from .pose import INDEX, SEEN

TORSO_M = 0.50
SHOULDERS_M = 0.38
FLOOR_HIP_M = 0.35
FLOOR_SHOULDER_M = 0.45
LYING_TILT = 55.0
UPRIGHT_TILT = 35.0
SHORT_TORSO = 0.8
STRAIGHT_KNEE = 145.0
BENT_KNEE = 115.0
SQUAT_KNEE = 70.0
LEVEL_THIGH = 55.0
SIDE_ON = 0.5


def _plane(raw, width: int, height: int, fov_h_deg: float, roll_deg: float):
    f = (width / 2) / math.tan(math.radians(fov_h_deg) / 2)
    c, s = math.cos(math.radians(-roll_deg)), math.sin(math.radians(-roll_deg))
    out = {}
    for name, i in INDEX.items():
        u, v, score = (float(x) for x in raw[i])
        if score < SEEN:
            continue
        x, y = (u - 0.5) * width / f, (v - 0.5) * height / f
        out[name] = (x * c - y * s, x * s + y * c)
    return out


def _middle(points, left: str, right: str):
    seen = [points[n] for n in (left, right) if n in points]
    if not seen:
        return None
    return sum(p[0] for p in seen) / len(seen), sum(p[1] for p in seen) / len(seen)


def _angle(a, b, c) -> float:
    ab = (a[0] - b[0], a[1] - b[1])
    cb = (c[0] - b[0], c[1] - b[1])
    na, nc = math.hypot(*ab), math.hypot(*cb)
    if na < 1e-9 or nc < 1e-9:
        return 180.0
    cos = max(-1.0, min(1.0, (ab[0] * cb[0] + ab[1] * cb[1]) / (na * nc)))
    return math.degrees(math.acos(cos))


def _from_vertical(a, b) -> float:
    return math.degrees(math.atan2(abs(b[0] - a[0]), b[1] - a[1]))


def _height(point, distance: float, camera_height_m: float, pitch_deg: float) -> float:
    return camera_height_m + distance * math.tan(math.atan(-point[1]) + math.radians(pitch_deg))


def posture(raw, box, width: int, height: int, fov_h_deg: float, camera_height_m: float = 0.14, pitch_deg: float = 0.0, roll_deg: float = 0.0):
    points = _plane(raw, width, height, fov_h_deg, roll_deg)
    shoulders = _middle(points, "left_shoulder", "right_shoulder")
    hips = _middle(points, "left_hip", "right_hip")
    if shoulders is None or hips is None:
        return None, 0.0
    torso = math.hypot(hips[0] - shoulders[0], hips[1] - shoulders[1])
    if torso < 1e-4:
        return None, 0.0
    span = None
    if "left_shoulder" in points and "right_shoulder" in points:
        a, b = points["left_shoulder"], points["right_shoulder"]
        span = math.hypot(a[0] - b[0], a[1] - b[1])
    distance = TORSO_M / torso
    if span and span > 1e-4:
        distance = min(distance, SHOULDERS_M / span)
    distance = max(0.3, min(8.0, distance))
    hip_height = _height(hips, distance, camera_height_m, pitch_deg)
    shoulder_height = _height(shoulders, distance, camera_height_m, pitch_deg)
    tilt = _from_vertical(shoulders, hips)
    short = span is not None and span > 1e-4 and torso / span < SHORT_TORSO
    low = hip_height <= FLOOR_HIP_M and shoulder_height <= FLOOR_SHOULDER_M
    if low and (tilt >= LYING_TILT or short):
        margin = min(1.0, (FLOOR_HIP_M + 0.1 - hip_height) / 0.25)
        shape = min(1.0, (tilt - LYING_TILT) / 25.0 + 0.6) if tilt >= LYING_TILT else 0.55
        return "lying", round(max(0.3, min(0.95, margin * shape)), 2)
    if tilt >= LYING_TILT:
        return None, 0.2
    legs = []
    for side in ("left", "right"):
        hip, knee, ankle = points.get(f"{side}_hip"), points.get(f"{side}_knee"), points.get(f"{side}_ankle")
        if hip and knee:
            legs.append((hip, knee, ankle))
    thighs = [_from_vertical(hip, knee) for hip, knee, _ in legs]
    knees = [_angle(hip, knee, ankle) for hip, knee, ankle in legs if ankle]
    side_on = any(math.hypot(knee[0] - hip[0], knee[1] - hip[1]) / torso >= SIDE_ON for hip, knee, _ in legs)
    knee = min(knees) if knees else None
    if tilt <= UPRIGHT_TILT:
        if not legs:
            box_wide = box.w * width / max(1e-6, box.h * height)
            return ("standing", 0.4) if box_wide < 0.45 else (None, 0.2)
        thigh = min(thighs)
        if thigh >= LEVEL_THIGH or not side_on:
            if knee is not None and knee <= SQUAT_KNEE and side_on:
                return "crouching", 0.6
            if hip_height <= FLOOR_HIP_M or thigh >= LEVEL_THIGH:
                return "sitting", 0.8 if side_on else 0.5
        if knee is not None and knee >= STRAIGHT_KNEE and thigh < 30:
            return "standing", 0.85
        if knee is not None and knee <= BENT_KNEE:
            return "crouching", 0.55
        if knee is None and thigh < 25:
            return "standing", 0.55
        return None, 0.3
    if knee is not None and knee <= SQUAT_KNEE:
        return "crouching", 0.65
    if knee is not None and knee <= BENT_KNEE and hips[1] > shoulders[1] and thighs and min(thighs) < LEVEL_THIGH + 20:
        return "crouching", 0.6
    if thighs and min(thighs) >= LEVEL_THIGH:
        return "sitting", 0.55
    return None, 0.25
