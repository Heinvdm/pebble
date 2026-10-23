import math
import random
from dataclasses import replace

from ...seams.sight import Sight
from ...sim.eyes import LENSES, PRINT_SIZE, SimEyes
from .rays import floor_rays

LIKE_SHARE = 0.8
SCAN_EVERY_S = 0.4
SCAN_LATE_S = 0.35
SCAN_KEEP_S = 1.0
MOVING_TAIL_S = 1.0


class BuildingEyes(SimEyes):
    def __init__(self, world, now, tilt, seed: int = 7, noise: bool = True):
        super().__init__(world, now, tilt, seed, noise)
        self.ray_rng = random.Random(seed + 101)
        self.fingerprints = 0
        self.moving = False
        self.stopped_at = -math.inf
        self.asked = False
        self.scan_due = -math.inf
        self.pending: list = []
        self.scan: tuple = ()
        self.scan_at: float | None = None
        self.scans = 0

    def set_moving(self, moving: bool) -> None:
        if self.moving and not moving:
            self.stopped_at = self.now()
        self.moving = bool(moving)

    def scan_floor(self) -> None:
        self.asked = True

    def _scan(self, x, y, facing, pitch, lens) -> None:
        now = self.now()
        while self.pending and self.pending[0][0] <= now:
            _, at, rays = self.pending.pop(0)
            self.scan, self.scan_at = rays, at
        if self.scan_at is not None and now - self.scan_at > SCAN_KEEP_S:
            self.scan, self.scan_at = (), None
        awake = self.moving or now - self.stopped_at <= MOVING_TAIL_S or self.asked
        if self._camera == "front" and awake and now >= self.scan_due:
            self.asked = False
            self.scan_due = now + SCAN_EVERY_S
            rays = floor_rays(self.world, x, y, facing, math.degrees(pitch), lens.fov_h_deg, lens.height_mm / 1000.0, self.ray_rng if self.noise else None, honest=True)
            self.pending.append((now + SCAN_LATE_S, now, rays))
            self.scans += 1

    def _identity(self, name: str) -> list[float]:
        if name.endswith("-like") and name not in self.identities:
            base = super()._identity(name[: -len("-like")])
            rng = random.Random(f"print:{name}")
            other = [rng.gauss(0.0, 1.0) for _ in range(PRINT_SIZE)]
            norm = math.sqrt(sum(v * v for v in other)) or 1.0
            other = [v / norm for v in other]
            mixed = [LIKE_SHARE * a + math.sqrt(1.0 - LIKE_SHARE**2) * b for a, b in zip(base, other)]
            norm = math.sqrt(sum(v * v for v in mixed)) or 1.0
            self.identities[name] = [v / norm for v in mixed]
        return super()._identity(name)

    def latest(self, max_age_s: float = 0.5) -> Sight | None:
        sight = super().latest(max_age_s)
        if sight is None:
            return None
        lens = LENSES[self._camera]
        x, y, facing, pitch = self._origin(lens)
        world = self.world
        tracks = {p.track: p for p in world.people}
        now = self.now()
        people = []
        for seen in sight.people:
            body = tracks.get(seen.track)
            if body is not None and hasattr(world, "sees") and not world.sees(x, y, body.x, body.y):
                continue
            if body is not None and getattr(body, "talking_until", -math.inf) >= now:
                seen = replace(seen, speaking=0.9)
            people.append(seen)
        things = []
        by_track = {t.track: t for t in world.things}
        for seen in sight.things:
            body = by_track.get(seen.track)
            if body is not None and hasattr(world, "sees") and not world.sees(x, y, body.x, body.y):
                continue
            things.append(seen)
        self._scan(x, y, facing, pitch, lens)
        return replace(sight, people=tuple(people), things=tuple(things), floor=self.scan if self._camera == "front" else (), floor_at=self.scan_at if self._camera == "front" else None)

    def visible(self, name: str) -> bool:
        sight = self.latest()
        person = next((p for p in self.world.people if p.name == name), None)
        return sight is not None and person is not None and any(seen.track == person.track for seen in sight.people)

    async def fingerprint(self, track):
        lens = LENSES[self._camera]
        x, y, _, _ = self._origin(lens)
        sight = self.latest()
        for person in self.world.people:
            if person.track == track and sight is not None and any(seen.track == track for seen in sight.people):
                self.fingerprints += 1
                return self._view(getattr(person, "print_id", person.name))
        return await super().fingerprint(track)

    async def look_for(self, key: str, camera: str | None = None):
        self.looks_for += 1
        views = self.prints.get(key)
        sight = self.latest()
        if not views or sight is None:
            return None
        best, score = None, 0.0
        for seen in sight.people:
            person = next((p for p in self.world.people if p.track == seen.track), None)
            if person is None:
                continue
            identity = self._identity(getattr(person, "print_id", person.name))
            value = max(sum(a * b for a, b in zip(identity, view)) for view in views)
            if value > score:
                best, score = seen, value
        if best is None or score < 0.75:
            return await super().look_for(key, camera)
        from ...seams.sight import SeenThing

        return SeenThing(key, best.bearing_deg, best.elevation_deg, best.height_frac, best.width_frac, round(score, 3), self.now(), "slow", False, None, False, key, round(score, 3))
