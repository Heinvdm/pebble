import itertools
import math
from dataclasses import dataclass, field

from ..seams.sight import SeenPerson

DEG = 180.0 / math.pi
TRACK_KEEP_S = 1.0
HEAD_DROP = 0.12


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float
    score: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass
class Candidate:
    u: float
    v: float
    bw: float
    bh: float
    score: float
    face: bool
    track: int | None = None
    label: str = ""
    box: "Box | None" = None
    body: bool = False


def focal(width: float, fov_h_deg: float) -> float:
    return (width / 2) / math.tan(math.radians(fov_h_deg) / 2)


def angles(u: float, v: float, width: int, height: int, fov_h_deg: float) -> tuple[float, float]:
    f = focal(width, fov_h_deg)
    return math.atan((u - 0.5) * width / f) * DEG, math.atan(-(v - 0.5) * height / f) * DEG


def floor_point(u: float, v: float, width: int, height: int, fov_h_deg: float, camera_height_m: float, pitch_deg: float, roll_deg: float = 0.0, reach_m: float = 6.0):
    f = focal(width, fov_h_deg)
    x, y = (u - 0.5) * width / f, (v - 0.5) * height / f
    c, s = math.cos(math.radians(-roll_deg)), math.sin(math.radians(-roll_deg))
    x, y = x * c - y * s, x * s + y * c
    p = math.radians(pitch_deg)
    ahead = math.cos(p) + y * math.sin(p)
    down = y * math.cos(p) - math.sin(p)
    if down <= 1e-3 or ahead <= 0:
        return None
    t = camera_height_m / down
    gx, gy = t * x, t * ahead
    distance = math.hypot(gx, gy)
    if distance > reach_m:
        return None
    return distance, math.degrees(math.atan2(gx, gy))


def wrap(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def tag_angles(t, normal) -> tuple[float, float, float]:
    tx, ty, tz = (float(v) for v in t)
    nx, ny, nz = (float(v) for v in normal)
    if nx * tx + ny * ty + nz * tz > 0:
        nx, ny, nz = -nx, -ny, -nz
    bearing = math.atan2(tx, tz) * DEG
    yaw = wrap(math.atan2(nx, -nz) * DEG + bearing)
    return bearing, math.sqrt(tx * tx + ty * ty + tz * tz), yaw


def combine(faces: list[Box], bodies: list[Box]) -> list[Candidate]:
    used: set[int] = set()
    out: list[Candidate] = []
    for body in bodies:
        pick, area = -1, 0.0
        for i, face in enumerate(faces):
            if i in used:
                continue
            inside = body.x <= face.cx <= body.x + body.w and body.y - face.h * 0.3 <= face.cy <= body.y + body.h * 0.6
            if inside and face.w * face.h > area:
                pick, area = i, face.w * face.h
        if pick >= 0:
            used.add(pick)
            face = faces[pick]
            out.append(Candidate(face.cx, face.cy, body.w, body.h, max(body.score, face.score), True, box=body, body=True))
        else:
            out.append(Candidate(body.cx, body.y + body.h * HEAD_DROP, body.w, body.h, body.score, False, box=body, body=True))
    for i, face in enumerate(faces):
        if i not in used:
            out.append(Candidate(face.cx, face.cy, face.w, face.h, face.score, True, box=face))
    return out


@dataclass
class _Track:
    id: int
    u: float
    v: float
    bw: float
    bh: float
    face: bool
    last: float
    label: str = ""


@dataclass
class Tracker:
    keep_s: float = TRACK_KEEP_S
    camera: str | None = None
    ids: itertools.count = field(default_factory=lambda: itertools.count(1))
    tracks: list[_Track] = field(default_factory=list)

    def reset(self) -> None:
        self.tracks = []
        self.camera = None

    def update(self, found: list[Candidate], now: float, camera: str, aspect: float) -> list[Candidate]:
        if camera != self.camera:
            self.tracks = []
            self.camera = camera
        self.tracks = [k for k in self.tracks if now - k.last < self.keep_s]
        free = list(self.tracks)
        found = sorted(found, key=lambda c: c.bw * c.bh, reverse=True)
        for c in found:
            best, cost = None, 1.3
            for k in free:
                if k.label != c.label:
                    continue
                scale = max(0.04, c.bw, k.bw)
                score = math.hypot(c.u - k.u, (c.v - k.v) / max(aspect, 1e-6)) / scale
                score += abs(math.log((c.bh + 0.01) / (k.bh + 0.01))) * 0.6 + (0.0 if c.face == k.face else 0.15)
                if score < cost:
                    best, cost = k, score
            if best is not None:
                free.remove(best)
                best.u, best.v, best.bw, best.bh, best.face, best.last = c.u, c.v, c.bw, c.bh, c.face, now
                c.track = best.id
            else:
                track = _Track(next(self.ids), c.u, c.v, c.bw, c.bh, c.face, now, c.label)
                self.tracks.append(track)
                c.track = track.id
        return found


def seen_people(found: list[Candidate], width: int, height: int, fov_h_deg: float, poses: dict | None = None, speaking: dict | None = None) -> tuple[SeenPerson, ...]:
    people = []
    for c in found:
        bearing, elevation = angles(c.u, c.v, width, height, fov_h_deg)
        extra = tuple((poses or {}).get(c.track, ())) + ((), None, None, 0.0)[len((poses or {}).get(c.track, ())):]
        points, facing, posture, posture_score = extra[:4]
        people.append(SeenPerson(
            bearing_deg=round(bearing, 2),
            elevation_deg=round(elevation, 2),
            height_frac=round(min(1.0, max(0.0, c.bh)), 4),
            width_frac=round(min(1.0, max(0.0, c.bw)), 4),
            score=round(min(1.0, max(0.0, c.score)), 3),
            face=c.face,
            track=c.track,
            points=tuple(points),
            facing_deg=facing,
            posture=posture,
            posture_score=float(posture_score or 0.0),
            speaking=(speaking or {}).get(c.track),
        ))
    return tuple(people)


def weight(person: SeenPerson) -> float:
    return (2.0 if person.face else 1.0) * person.height_frac


def nearest(people, keep: int | None = None, switch: float = 1.6) -> SeenPerson | None:
    if not people:
        return None
    best = max(people, key=weight)
    held = next((p for p in people if keep is not None and p.track == keep), None)
    if held is None or (best is not held and weight(best) > switch * weight(held)):
        return best
    return held
