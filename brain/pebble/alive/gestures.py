import math
from collections import deque
from dataclasses import dataclass

from ..activities.seeing import body_bearing
from ..seams.sight import SeenPerson

HISTORY_S = 2.0
POINT_HOLD_S = 0.6
SWING_S = 1.6
WAVE_SWINGS = 2
WAVE_AMPLITUDE_DEG = 1.5
BECKON_AMPLITUDE_DEG = 1.5
BECKON_SIDE_DEG = 10.0
STRAIGHT_DEG = 35.0
ARM_M = 0.6
POINT_REACH_M = 1.5
POINT_MAX_M = 3.0
CAMERA_Z_M = 0.14
PEEK_GONE_S = 4.0
MIN_SCORE = 0.3
RAISED_DEG = 35.0
POINT_GAP_S = 4.0
GESTURE_GAP_S = 8.0


@dataclass(frozen=True)
class Gesture:
    kind: str
    track: int | None
    at: float
    bearing_deg: float = 0.0
    side: str = ""
    target: tuple[float, float] | None = None


def body_point(person: SeenPerson, name: str):
    for point in person.points:
        if point.name == name and point.score >= MIN_SCORE:
            return point
    return None


def _angle(a, b) -> tuple[float, float]:
    return b.bearing_deg - a.bearing_deg, b.elevation_deg - a.elevation_deg


def _straight(shoulder, elbow, wrist) -> bool:
    upper, lower = _angle(shoulder, elbow), _angle(elbow, wrist)
    if math.hypot(*upper) < 0.5 or math.hypot(*lower) < 0.5:
        return False
    turn = abs(math.degrees(math.atan2(upper[1], upper[0]) - math.atan2(lower[1], lower[0])))
    turn = min(turn, 360.0 - turn)
    return turn <= STRAIGHT_DEG


def _swings(values: list[float], amplitude: float) -> int:
    if not values:
        return 0
    low = high = values[0]
    direction = 0
    turns = 0
    for value in values[1:]:
        if direction == 0:
            if value - low >= amplitude:
                direction, high = 1, value
            elif high - value >= amplitude:
                direction, low = -1, value
            else:
                low, high = min(low, value), max(high, value)
        elif direction == 1:
            if value > high:
                high = value
            elif high - value >= amplitude:
                direction, low, turns = -1, value, turns + 1
        else:
            if value < low:
                low = value
            elif value - low >= amplitude:
                direction, high, turns = 1, value, turns + 1
    return turns


def _ray(point, camera: str, tilt_deg: float) -> tuple[float, float, float]:
    angle = math.radians(body_bearing(point.bearing_deg, camera))
    pitch = tilt_deg if camera == "front" else -tilt_deg
    up = math.radians(point.elevation_deg + pitch)
    return math.cos(up) * math.cos(angle), math.cos(up) * math.sin(angle), math.sin(up)


def pointed_target(gap_m: float, shoulder, wrist, camera: str = "front", tilt_deg: float = 0.0, camera_z: float = CAMERA_Z_M) -> tuple[float, float]:
    sx, sy, sz = _ray(shoulder, camera, tilt_deg)
    reach = max(0.3, gap_m) / (math.hypot(sx, sy) or 1e-6)
    shoulder_at = (reach * sx, reach * sy, reach * sz)
    wx, wy, wz = _ray(wrist, camera, tilt_deg)
    along = wx * shoulder_at[0] + wy * shoulder_at[1] + wz * shoulder_at[2]
    t = along
    ux, uy, uz = t * wx - shoulder_at[0], t * wy - shoulder_at[1], t * wz - shoulder_at[2]
    norm = math.sqrt(ux * ux + uy * uy + uz * uz) or 1e-6
    ux, uy, uz = ux / norm, uy / norm, uz / norm
    height = camera_z + shoulder_at[2]
    flat = math.hypot(ux, uy) or 1e-6
    if uz >= -0.05:
        distance = POINT_REACH_M
    else:
        distance = min(POINT_MAX_M, height / -uz * flat)
    return shoulder_at[0] + ux / flat * distance, shoulder_at[1] + uy / flat * distance


class GestureReader:
    def __init__(self):
        self.history: dict[int, deque] = {}
        self.pointing_since: dict[tuple[int, str], float] = {}
        self.face_lost: dict[int, float] = {}
        self.face_seen: dict[int, bool] = {}
        self.last: dict[tuple[int, str], float] = {}

    def _remember(self, track: int, at: float, person: SeenPerson) -> deque:
        rows = self.history.setdefault(track, deque())
        points = {p.name: p for p in person.points if p.score >= MIN_SCORE}
        rows.append((at, points))
        while rows and at - rows[0][0] > HISTORY_S:
            rows.popleft()
        return rows

    def _cool(self, track: int, kind: str, at: float, gap: float = 3.0) -> bool:
        key = (track, kind)
        if at - self.last.get(key, -math.inf) < gap:
            return False
        self.last[key] = at
        return True

    def read(self, person: SeenPerson, at: float) -> list[Gesture]:
        track = person.track if person.track is not None else -1
        rows = self._remember(track, at, person)
        found: list[Gesture] = []
        found.extend(self._peekaboo(person, track, at))
        for side in ("left", "right"):
            shoulder, elbow, wrist = (body_point(person, f"{side}_{part}") for part in ("shoulder", "elbow", "wrist"))
            if shoulder is None or elbow is None or wrist is None:
                self.pointing_since.pop((track, side), None)
                continue
            recent = [(t, p.get(f"{side}_wrist"), p.get(f"{side}_elbow"), p.get(f"{side}_shoulder")) for t, p in rows if at - t <= SWING_S]
            recent = [(t, w, e, s) for t, w, e, s in recent if w is not None and e is not None and s is not None]
            above = [w.elevation_deg > e.elevation_deg + 1.0 and w.elevation_deg > s.elevation_deg for _, w, e, s in recent]
            if len(recent) >= 4 and sum(above) >= len(above) * 0.7:
                if _swings([w.bearing_deg - s.bearing_deg for _, w, _, s in recent], WAVE_AMPLITUDE_DEG) >= WAVE_SWINGS and self._cool(track, "wave", at, GESTURE_GAP_S):
                    found.append(Gesture("wave", track, at, person.bearing_deg, side))
                    continue
            near_body = [abs(w.bearing_deg - person.bearing_deg) <= BECKON_SIDE_DEG for _, w, _, s in recent]
            if len(recent) >= 4 and sum(near_body) >= len(near_body) * 0.7:
                ups = [w.elevation_deg - s.elevation_deg for _, w, _, s in recent]
                sides = [w.bearing_deg - s.bearing_deg for _, w, _, s in recent]
                if max(ups) - min(ups) > 2.0 * (max(sides) - min(sides)) and _swings(ups, BECKON_AMPLITUDE_DEG) >= WAVE_SWINGS and self._cool(track, "beckon", at, GESTURE_GAP_S):
                    found.append(Gesture("beckon", track, at, person.bearing_deg, side))
                    continue
            across, up = _angle(shoulder, wrist)
            reach = math.hypot(across, up)
            spread = abs(_angle(body_point(person, "left_shoulder") or shoulder, body_point(person, "right_shoulder") or shoulder)[0]) or 4.0
            raised = math.degrees(math.atan2(abs(across), max(1e-6, -up))) >= RAISED_DEG
            extended = _straight(shoulder, elbow, wrist) and raised and reach >= spread * 0.9 and wrist.elevation_deg <= shoulder.elevation_deg + 2.0
            key = (track, side)
            if extended:
                since = self.pointing_since.setdefault(key, at)
                if at - since >= POINT_HOLD_S and self._cool(track, "point", at, POINT_GAP_S):
                    found.append(Gesture("point", track, at, wrist.bearing_deg, side))
            else:
                self.pointing_since.pop(key, None)
        return found

    def _peekaboo(self, person: SeenPerson, track: int, at: float) -> list[Gesture]:
        was = self.face_seen.get(track)
        self.face_seen[track] = person.face
        if was and not person.face and abs(person.bearing_deg) < 20.0:
            self.face_lost[track] = at
            return []
        lost = self.face_lost.get(track)
        if person.face and lost is not None:
            del self.face_lost[track]
            if at - lost <= PEEK_GONE_S and self._cool(track, "peekaboo", at, 5.0):
                return [Gesture("peekaboo", track, at, person.bearing_deg)]
        return []

    def forget(self, tracks: set[int]) -> None:
        for track in list(self.history):
            if track not in tracks:
                self.history.pop(track, None)
                self.face_seen.pop(track, None)
