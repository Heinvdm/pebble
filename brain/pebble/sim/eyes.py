import math
import random
from dataclasses import dataclass
from typing import Callable

from ..seams.sight import BODY_POINTS, CAMERAS, DOCK_TAG_ID, DOCK_TAG_SIZE_M, BodyPoint, SeenPerson, SeenTag, SeenThing, Sight
from ..nav.sim.rays import floor_rays
from ..privacy.cues import boxes_of
from .world import SimThing, World

FRONT_FOV_DEG = 70.0
REAR_FOV_DEG = 65.0
ASPECT = 0.75
PERSON_RANGE_M = 6.0
TAG_MAX_YAW_DEG = 70.0
FRAME_PX = {"front": 640, "rear": 1280}
TAG_MIN_PX = 20.0
TAG_FULL_PX = 60.0
BEARING_NOISE_DEG = 0.2
DISTANCE_NOISE = 0.015
STEADY_YAW_NOISE_DEG = 2.0
SHAKY_YAW_NOISE_DEG = 50.0
STEADY_SCORE = 0.5
THING_RANGE_M = {"fast": 6.0, "slow": 4.0}
THING_MIN_PX = 6.0
FAST_SCORE = 0.8
SLOW_SCORE = 0.62
SLOW_EVERY_S = 1.0
SLOW_KEEP_S = 1.5
FACE_RANGE_M = 3.5
HEAD_AIM = 0.12
PRINT_SIZE = 16
PRINT_NOISE = 0.06
PRINT_MATCH = 0.75
PRINT_VIEWS = 8
DOCK_PRINT_M = (0.25, 1.3)
CHARGER_CONE_DEG = 35.0
WAVE_HZ = 1.0
BECKON_HZ = 0.8
SHOO_HZ = 2.0
NOD_HZ = 1.2
NOD_M = 0.05
POSE = {
    "nose": (0.1, 0.0, 1.6),
    "left_eye": (0.08, 0.035, 1.63),
    "right_eye": (0.08, -0.035, 1.63),
    "left_ear": (0.0, 0.08, 1.6),
    "right_ear": (0.0, -0.08, 1.6),
    "left_shoulder": (0.0, 0.2, 1.4),
    "right_shoulder": (0.0, -0.2, 1.4),
    "left_hip": (0.0, 0.12, 0.95),
    "right_hip": (0.0, -0.12, 0.95),
    "left_knee": (0.0, 0.12, 0.5),
    "right_knee": (0.0, -0.12, 0.5),
    "left_ankle": (0.0, 0.12, 0.08),
    "right_ankle": (0.0, -0.12, 0.08),
}


@dataclass(frozen=True)
class Lens:
    ahead_mm: float
    height_mm: float
    fov_h_deg: float
    behind: bool


LENSES = {"front": Lens(87.0, 140.0, FRONT_FOV_DEG, False), "rear": Lens(45.0, 150.0, REAR_FOV_DEG, True)}


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _vfov(fov_h_deg: float) -> float:
    return 2.0 * math.atan(math.tan(math.radians(fov_h_deg) / 2.0) * ASPECT)


class SimEyes:
    available = True

    def __init__(self, world: World, now: Callable[[], float], tilt: Callable[[], float], seed: int = 7, noise: bool = True):
        self.world = world
        self.now = now
        self.tilt = tilt
        self.rng = random.Random(seed)
        self.noise = noise
        self.busy = False
        self.slow_at = -math.inf
        self.close_looks = 0
        self._camera = "front"
        self.switches = 0
        self.prints: dict[str, list[tuple]] = {}
        self.identities: dict[str, list[float]] = {}
        self.moves = 0
        self.looks_for = 0
        self.dock_prints = 0
        self._last = None
        self.private = False
        self.keep: frozenset = frozenset()
        self.private_frames = 0
        self.privacy_calls: list = []
        self.snapshots = 0
        self.snapshot_veto = None
        self.on_cue = None

    def set_privacy(self, on: bool, keep=()) -> None:
        self.private = bool(on)
        self.keep = frozenset(k for k in keep if k in ("floor", "tag")) if on else frozenset()
        self.privacy_calls.append((self.private, tuple(sorted(self.keep))))
        self._last = None

    def undressed(self, max_age_s: float = 2.5) -> tuple[float, float] | None:
        if self.private:
            return None
        sight = self.latest()
        if sight is None:
            return None
        tracks = {p.track for p in sight.people}
        bare = any(p.undressed for p in self.world.people if p.track in tracks)
        return (0.9, 0.9) if bare else (0.02, 0.02)

    def set_busy(self, busy: bool) -> None:
        self.busy = bool(busy)

    async def look_closely(self) -> Sight | None:
        if self.private:
            return None
        self.close_looks += 1
        self.slow_at = self.now()
        return self.latest()

    def camera(self) -> str | None:
        return self._camera

    async def use_camera(self, camera: str) -> bool:
        if camera not in CAMERAS:
            return False
        if camera != self._camera:
            self.switches += 1
        self._camera = camera
        return True

    def _origin(self, lens: Lens) -> tuple[float, float, float, float]:
        pose = self.world.pose
        x, y = self.world.point(lens.ahead_mm)
        facing = pose.heading + (math.pi if lens.behind else 0.0)
        pitch = math.radians(-self.tilt() if lens.behind else self.tilt())
        return x, y, facing, pitch

    def _private_sight(self) -> Sight | None:
        self.private_frames += 1
        lens = LENSES[self._camera]
        x, y, facing, pitch = self._origin(lens)
        floor = floor_rays(self.world, x, y, facing, math.degrees(pitch), lens.fov_h_deg, lens.height_mm / 1000.0) if self._camera == "front" and "floor" in self.keep else ()
        tags = ()
        if self._camera == "rear" and "tag" in self.keep:
            half_h = math.radians(lens.fov_h_deg) / 2.0
            tag = self._tag(x, y, facing, pitch, lens, half_h, _vfov(lens.fov_h_deg) / 2.0)
            tags = (tag,) if tag is not None else ()
        if not floor and not tags:
            return None
        now = self.now()
        return Sight(now, self._camera, lens.fov_h_deg, (), tags, (), floor, now if floor else None)

    def latest(self, max_age_s: float = 0.5) -> Sight | None:
        if self.private:
            return self._private_sight()
        lens = LENSES[self._camera]
        x, y, facing, pitch = self._origin(lens)
        key = (self.now(), self._camera, x, y, facing, pitch, self.busy, tuple((p.x, p.y, p.home, p.arm, p.arm_side, p.hiding, p.holding, p.facing, p.point_at) for p in self.world.people), tuple((t.x, t.y, t.home, t.z_mm, getattr(t, "held_by", None)) for t in self.world.things))
        if self._last is not None and self._last[0] == key:
            return self._last[1]
        half_h = math.radians(lens.fov_h_deg) / 2.0
        half_v = _vfov(lens.fov_h_deg) / 2.0
        people = []
        for person in self.world.people:
            seen = self._person(person, x, y, facing, pitch, lens, half_h, half_v)
            if seen is not None:
                people.append(seen)
        now = self.now()
        if not self.busy and now - self.slow_at >= SLOW_EVERY_S:
            self.slow_at = now
        slow = now - self.slow_at <= SLOW_KEEP_S
        things = []
        for thing in self.world.things:
            seen = self._thing(thing, x, y, facing, pitch, lens, half_h, half_v, now, slow)
            if seen is not None:
                things.append(seen)
        tags = []
        if self._camera == "rear":
            tag = self._tag(x, y, facing, pitch, lens, half_h, half_v)
            if tag is not None:
                tags.append(tag)
        floor = floor_rays(self.world, x, y, facing, math.degrees(pitch), lens.fov_h_deg, lens.height_mm / 1000.0) if self._camera == "front" else ()
        sight = Sight(now, self._camera, lens.fov_h_deg, tuple(people), tuple(tags), tuple(things), floor, now if floor else None)
        self._last = (key, sight)
        return sight

    def _box(self, thing, x, y, facing, pitch, lens, half_h, half_v, reach_m: float):
        dx, dy = thing.x - x, thing.y - y
        centre = math.hypot(dx, dy) / 1000.0
        surface = max(0.05, centre - thing.depth_mm / 2000.0)
        if centre > reach_m:
            return None
        relative = _wrap(math.atan2(dy, dx) - facing)
        if abs(relative) > half_h:
            return None
        camera_z = lens.height_mm / 1000.0
        base = getattr(thing, "z_mm", 0.0) / 1000.0
        bottom = max(math.atan2(base - camera_z, surface) - pitch, -half_v)
        top = min(math.atan2(base + thing.height_mm / 1000.0 - camera_z, surface) - pitch, half_v)
        if top <= bottom:
            return None
        scale = math.tan(half_v)
        low, high = math.tan(bottom), math.tan(top)
        width_frac = (thing.width_mm / 1000.0 / surface) / (2.0 * math.tan(half_h))
        if width_frac * FRAME_PX[self._camera] < THING_MIN_PX:
            return None
        return (
            round(-math.degrees(relative), 2),
            round(math.degrees(math.atan((high + low) / 2.0)), 2),
            round(min(1.0, (high - low) / (2.0 * scale)), 4),
            round(min(1.0, width_frac), 4),
        )

    def _thing(self, thing, x, y, facing, pitch, lens, half_h, half_v, now, slow) -> SeenThing | None:
        if not thing.home:
            return None
        if slow and thing.slow:
            label, lane, score, at = thing.slow, "slow", SLOW_SCORE, self.slow_at
        elif thing.fast:
            label, lane, score, at = thing.fast, "fast", FAST_SCORE, now
        else:
            return None
        box = self._box(thing, x, y, facing, pitch, lens, half_h, half_v, THING_RANGE_M[lane])
        if box is None:
            return None
        known, known_score = self._known(thing.print_id) if lane == "slow" else (None, 0.0)
        bearing, elevation, height_frac, width_frac = box
        return SeenThing(
            label=label,
            bearing_deg=bearing,
            elevation_deg=elevation,
            height_frac=height_frac,
            width_frac=width_frac,
            score=score,
            at=at,
            lane=lane,
            animal=thing.animal,
            track=thing.track,
            held=thing.held_by is not None,
            known=known,
            known_score=known_score,
            floor_m=self._floor(thing, x, y) if thing.z_mm <= 100.0 else None,
            floor_bearing_deg=bearing if thing.z_mm <= 100.0 else None,
        )

    def _floor(self, thing, x: float, y: float) -> float:
        return round(max(0.05, math.hypot(thing.x - x, thing.y - y) / 1000.0 - thing.depth_mm / 2000.0), 3)

    async def snapshot(self, max_side: int = 768, camera: str | None = None) -> bytes | None:
        if self.private:
            return None
        if camera is not None and not await self.use_camera(camera):
            return None
        sight = self.latest()
        if self.private or sight is None:
            return None
        veto = self.snapshot_veto
        if veto is not None and veto(*boxes_of(sight), self.undressed()):
            if self.on_cue is not None:
                self.on_cue()
            return None
        self.snapshots += 1
        names = ", ".join(sorted({t.label for t in sight.things})) if sight else ""
        return bytes([0xFF, 0xD8]) + b"SIM " + names.encode("utf-8") + bytes([0xFF, 0xD9])

    def _identity(self, name: str) -> list[float]:
        if name not in self.identities:
            if "|" in name:
                parts = [self._identity(part) for part in name.split("|") if part]
                vec = [sum(values) for values in zip(*parts)]
            else:
                rng = random.Random(f"print:{name}")
                vec = [rng.gauss(0.0, 1.0) for _ in range(PRINT_SIZE)]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            self.identities[name] = [v / norm for v in vec]
        return self.identities[name]

    async def place_print(self, camera: str | None = None) -> tuple | None:
        if self.private or (camera is not None and camera != self._camera):
            return None
        lens = LENSES[self._camera]
        x, y, facing, pitch = self._origin(lens)
        half_h = math.radians(lens.fov_h_deg) / 2.0
        half_v = _vfov(lens.fov_h_deg) / 2.0
        total = [0.0] * PRINT_SIZE
        seen = False
        for thing in self.world.things:
            if not thing.home:
                continue
            box = self._box(thing, x, y, facing, pitch, lens, half_h, half_v, THING_RANGE_M["slow"])
            if box is None:
                continue
            weight = math.sqrt(max(1e-6, box[2] * box[3]))
            total = [a + weight * b for a, b in zip(total, self._identity(thing.print_id))]
            seen = True
        if not seen:
            return None
        norm = math.sqrt(sum(v * v for v in total)) or 1.0
        vec = [v / norm + (self.rng.gauss(0.0, PRINT_NOISE) if self.noise else 0.0) for v in total]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return tuple(round(v / norm, 6) for v in vec)

    def _view(self, name: str) -> tuple:
        base = self._identity(name)
        vec = [v + (self.rng.gauss(0.0, PRINT_NOISE) if self.noise else 0.0) for v in base]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return tuple(round(v / norm, 6) for v in vec)

    def _known(self, name: str | None) -> tuple[str | None, float]:
        if not name:
            return None, 0.0
        identity = self._identity(name)
        best, score = None, 0.0
        for key, views in self.prints.items():
            for view in views:
                value = sum(a * b for a, b in zip(identity, view))
                if value > score:
                    best, score = key, value
        return (best, round(score, 3)) if score >= PRINT_MATCH else (None, 0.0)

    def moved(self) -> None:
        self.moves += 1

    async def fingerprint(self, track) -> tuple | None:
        lens = LENSES[self._camera]
        x, y, facing, pitch = self._origin(lens)
        half_h = math.radians(lens.fov_h_deg) / 2.0
        half_v = _vfov(lens.fov_h_deg) / 2.0
        for thing in self.world.things:
            if thing.home and thing.track == track and self._box(thing, x, y, facing, pitch, lens, half_h, half_v, THING_RANGE_M["slow"]) is not None:
                return self._view(thing.print_id)
        return None

    def remember_print(self, key: str, vec, replace: bool = False) -> int:
        values = [float(v) for v in vec or ()]
        if not values or any(math.isnan(v) for v in values) or not any(values):
            raise ValueError("a print needs numbers")
        views = [] if replace else self.prints.get(key, [])
        if views and len(views[0]) != len(values):
            raise ValueError("a print must match the length of the others")
        norm = math.sqrt(sum(v * v for v in values))
        views = (views + [tuple(v / norm for v in values)])[-PRINT_VIEWS:]
        self.prints[key] = views
        return len(views)

    def forget_print(self, key: str) -> bool:
        return self.prints.pop(key, None) is not None

    def _charger_thing(self):
        spot = self.world.charger()
        if spot is None:
            return None
        return SimThing("charger", spot[0], spot[1], width_mm=200.0, height_mm=150.0, depth_mm=100.0, print_id="charger")

    async def look_for(self, key: str, camera: str | None = None) -> SeenThing | None:
        self.looks_for += 1
        if camera is not None and not await self.use_camera(camera):
            return None
        views = self.prints.get(key)
        if not views:
            return None
        lens = LENSES[self._camera]
        x, y, facing, pitch = self._origin(lens)
        half_h = math.radians(lens.fov_h_deg) / 2.0
        half_v = _vfov(lens.fov_h_deg) / 2.0
        candidates = [t for t in self.world.things if t.home]
        charger = self._charger_thing()
        if charger is not None:
            candidates.append(charger)
        best, best_score = None, 0.0
        for thing in candidates:
            box = self._box(thing, x, y, facing, pitch, lens, half_h, half_v, THING_RANGE_M["slow"])
            if box is None:
                continue
            if thing is charger and math.degrees(math.atan2(abs(y - thing.y), max(1.0, x - self.world.table.x_min))) > CHARGER_CONE_DEG:
                continue
            identity = self._identity(thing.print_id)
            score = max(sum(a * b for a, b in zip(identity, view)) for view in views)
            if score >= PRINT_MATCH and score > best_score:
                best, best_score = box, score
        if best is None:
            return None
        bearing, elevation, height_frac, width_frac = best
        if self.noise:
            bearing = round(bearing + self.rng.gauss(0.0, 1.0), 2)
        return SeenThing(key, bearing, elevation, height_frac, width_frac, round(best_score, 3), self.now(), "slow", False, None, False, key, round(best_score, 3))

    async def dock_print(self) -> tuple | None:
        if self._camera != "rear" or self.world.tag_hidden:
            return None
        sight = self.latest()
        if sight is None or not sight.tags:
            return None
        distance = sight.tags[0].distance_m
        if not DOCK_PRINT_M[0] <= distance <= DOCK_PRINT_M[1] or abs(sight.tags[0].bearing_deg) > 20.0:
            return None
        self.dock_prints += 1
        return self._view("charger")

    def _points(self, person, x, y, facing, pitch, lens, half_h) -> tuple[BodyPoint, ...]:
        toward = math.atan2(y - person.y, x - person.x)
        heading = person.facing if person.facing is not None else toward
        scale = person.height_mm / 1700.0
        c, s = math.cos(heading), math.sin(heading)
        offsets = dict(POSE)
        sign = {"left": 1.0, "right": -1.0}
        for side in ("left", "right"):
            k = sign[side]
            offsets[f"{side}_elbow"] = (0.0, 0.2 * k, 1.1)
            offsets[f"{side}_wrist"] = (0.02, 0.2 * k, 0.82)
        side = person.arm_side
        k = sign.get(side, -1.0)
        t = self.now()
        if getattr(person, "nod", False):
            dip = NOD_M * math.sin(2 * math.pi * NOD_HZ * t)
            for name in ("nose", "left_eye", "right_eye"):
                f, l, z = offsets[name]
                offsets[name] = (f, l, z + dip)
        if person.arm == "wave":
            offsets[f"{side}_elbow"] = (0.05, 0.3 * k, 1.45)
            offsets[f"{side}_wrist"] = (0.05, (0.32 + 0.1 * math.sin(2 * math.pi * WAVE_HZ * t)) * k, 1.78)
        elif person.arm == "beckon":
            swing = math.sin(2 * math.pi * BECKON_HZ * t)
            offsets[f"{side}_elbow"] = (0.25, 0.15 * k, 1.15)
            offsets[f"{side}_wrist"] = (0.35 + 0.05 * swing, 0.1 * k, 1.12 + 0.1 * swing)
        elif person.arm == "hold":
            offsets[f"{side}_elbow"] = (0.15, 0.18 * k, 1.05)
            offsets[f"{side}_wrist"] = (0.35, 0.1 * k, 1.1)
        elif person.arm == "palm":
            offsets[f"{side}_elbow"] = (0.25, 0.15 * k, 1.3)
            offsets[f"{side}_wrist"] = (0.35, 0.1 * k, 1.55)
        elif person.arm == "shoo":
            flick = max(0.0, math.sin(2 * math.pi * SHOO_HZ * t))
            offsets[f"{side}_elbow"] = (0.1, 0.22 * k, 1.0)
            offsets[f"{side}_wrist"] = (0.25, (0.2 + 0.15 * flick) * k, 0.98)
        world = {}
        for name, (f, l, z) in offsets.items():
            world[name] = (person.x + (f * c - l * s) * 1000.0 * scale, person.y + (f * s + l * c) * 1000.0 * scale, z * scale)
        if person.arm == "point" and person.point_at is not None:
            sx, sy, sz = world[f"{side}_shoulder"]
            tx, ty = person.point_at
            dx, dy, dz = (tx - sx) / 1000.0, (ty - sy) / 1000.0, -sz
            length = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
            for name, reach in ((f"{side}_elbow", 0.3), (f"{side}_wrist", 0.6)):
                world[name] = (sx + dx / length * reach * 1000.0, sy + dy / length * reach * 1000.0, sz + dz / length * reach)
        camera_z = lens.height_mm / 1000.0
        out = []
        for name in BODY_POINTS:
            wx, wy, wz = world[name]
            relative = _wrap(math.atan2(wy - y, wx - x) - facing)
            flat = max(0.05, math.hypot(wx - x, wy - y) / 1000.0)
            elevation = math.atan2(wz - camera_z, flat) - pitch
            score = 0.9 if abs(relative) <= half_h else 0.1
            if person.hiding and name in ("nose", "left_eye", "right_eye"):
                score = 0.1
            out.append(BodyPoint(name, round(-math.degrees(relative), 2), round(math.degrees(elevation), 2), score))
        return tuple(out)

    def _facing(self, person, x, y) -> float | None:
        if person.facing is None:
            return 0.0
        toward = math.atan2(y - person.y, x - person.x)
        diff = math.degrees(_wrap(person.facing - toward))
        return 180.0 if abs(diff) > 100.0 else round(diff, 1)

    def _person(self, person, x, y, facing, pitch, lens, half_h, half_v) -> SeenPerson | None:
        if not person.home:
            return None
        dx, dy = person.x - x, person.y - y
        centre = math.hypot(dx, dy) / 1000.0
        surface = max(0.05, centre - person.radius_mm / 1000.0)
        if centre > PERSON_RANGE_M:
            return None
        relative = _wrap(math.atan2(dy, dx) - facing)
        if abs(relative) > half_h:
            return None
        camera_z = lens.height_mm / 1000.0
        feet = math.atan2(-camera_z, surface) - pitch
        head = math.atan2(person.height_mm / 1000.0 - camera_z, surface) - pitch
        bottom, top = max(feet, -half_v), min(head, half_v)
        if top <= bottom:
            return None
        scale = math.tan(half_v)
        height_frac = (math.tan(top) - math.tan(bottom)) / (2.0 * scale)
        width_frac = (person.width_mm / 1000.0 / surface) / (2.0 * math.tan(half_h))
        facing_deg = self._facing(person, x, y)
        face = head <= half_v and surface <= FACE_RANGE_M and not person.hiding and (facing_deg is None or abs(facing_deg) < 100.0)
        aim = head - 0.04 if face else top - HEAD_AIM * (top - bottom)
        return SeenPerson(
            bearing_deg=round(-math.degrees(relative), 2),
            elevation_deg=round(math.degrees(aim), 2),
            height_frac=round(min(1.0, height_frac), 4),
            width_frac=round(min(1.0, width_frac), 4),
            score=0.9,
            face=face,
            track=person.track,
            points=self._points(person, x, y, facing, pitch, lens, half_h),
            facing_deg=facing_deg,
            posture=person.posture,
            posture_score=0.8 if person.posture else 0.0,
        )

    def _tag(self, x, y, facing, pitch, lens, half_h, half_v) -> SeenTag | None:
        spot = self.world.tag()
        if spot is None:
            return None
        tx, ty, tz = spot
        if x <= tx:
            return None
        dx, dy = tx - x, ty - y
        flat = math.hypot(dx, dy) / 1000.0
        distance = math.hypot(flat, (tz - lens.height_mm) / 1000.0)
        if flat < 0.03:
            return None
        relative = _wrap(math.atan2(dy, dx) - facing)
        if abs(relative) > half_h:
            return None
        elevation = math.atan2((tz - lens.height_mm) / 1000.0, flat) - pitch
        if abs(elevation) > half_v:
            return None
        back = math.atan2(y - ty, x - tx)
        yaw = _wrap(-back)
        if abs(math.degrees(yaw)) > TAG_MAX_YAW_DEG:
            return None
        pixels = DOCK_TAG_SIZE_M / (2.0 * distance * math.tan(half_h)) * FRAME_PX[self._camera] * math.cos(yaw)
        if pixels < TAG_MIN_PX:
            return None
        score = max(0.05, min(1.0, (pixels - TAG_MIN_PX) / TAG_FULL_PX))
        bearing, yaw_deg = -math.degrees(relative), math.degrees(yaw)
        if self.noise:
            bearing += self.rng.gauss(0.0, BEARING_NOISE_DEG)
            distance *= 1.0 + self.rng.gauss(0.0, DISTANCE_NOISE)
            spread = STEADY_YAW_NOISE_DEG if score >= STEADY_SCORE else STEADY_YAW_NOISE_DEG + (STEADY_SCORE - score) * SHAKY_YAW_NOISE_DEG
            yaw_deg += self.rng.gauss(0.0, spread)
        return SeenTag(DOCK_TAG_ID, round(bearing, 2), round(distance, 4), round(yaw_deg, 2), round(score, 3))
