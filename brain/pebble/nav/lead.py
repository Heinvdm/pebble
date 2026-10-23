import math
from collections import deque
from dataclasses import dataclass

from ..seams.sight import SeenPerson, Sight
from .geometry import CAMERA_HEIGHT_M, TOF_CONE_DEG, body_angle, camera_spot, floor_distance

PERSON_WIDTH_M = 0.40
TOF_AGREE_M = 0.35
SURFACE_TO_MIDDLE_M = 0.12
ANKLE_HEIGHT_M = 0.08
HEAD_ABOVE_NOSE_M = 0.10
CRUMB_M = 0.15
GATE_M = 0.6
GATE_GROWTH_M_S = 1.3
GATE_MAX_M = 4.5
PRINT_MATCH = 0.75
PRINT_SURE = 0.85
PRINT_VIEWS = 8
PRINT_EVERY_S = 1.2
PRINT_SLOW_S = 4.0
OTHER_PRINT_EVERY_S = 1.5
HEIGHT_TOLERANCE_M = 0.15
HEIGHT_GATE_M = 0.14
SWAP_FREE_S = 1.0
PRINT_RELOCK = 0.88
SETTLED_S = 2.0
JUMP_S = 0.5
JUMP_M = 0.6
UNSURE_MARGIN = 0.9
HISTORY_S = 1.6
TRAIL_KEEP = 4000


@dataclass(frozen=True)
class Seen:
    track: int | None
    x: float
    y: float
    range_m: float
    angle: float
    height_m: float | None
    face: bool
    speaking: float | None
    person: SeenPerson
    at: float


def _point(person: SeenPerson, name: str, score: float = 0.5):
    for point in person.points:
        if point.name == name and point.score >= score:
            return point
    return None


def person_range(person: SeenPerson, sight: Sight, tilt_deg: float | None, front_mm: int | None) -> float:
    pitch = (tilt_deg or 0.0) * (-1.0 if sight.camera == "rear" else 1.0)
    height = CAMERA_HEIGHT_M.get(sight.camera, 0.14)
    ankles = [p for p in (_point(person, "left_ankle"), _point(person, "right_ankle")) if p is not None]
    seen = None
    if ankles:
        elevation = sum(p.elevation_deg for p in ankles) / len(ankles)
        seen = floor_distance(elevation, pitch, height - ANKLE_HEIGHT_M)
    if seen is None:
        half = math.radians(max(1.0, sight.fov_h_deg)) / 2.0
        seen = PERSON_WIDTH_M / (2.0 * max(person.width_frac, 1e-3) * math.tan(half)) + SURFACE_TO_MIDDLE_M
    if sight.camera == "front" and front_mm is not None and 0 <= front_mm < 1200 and abs(person.bearing_deg) <= TOF_CONE_DEG:
        measured = front_mm / 1000.0 + 0.013 + SURFACE_TO_MIDDLE_M
        if abs(measured - seen) < TOF_AGREE_M:
            return measured
    return max(0.2, seen)


def person_height(person: SeenPerson, sight: Sight, tilt_deg: float | None, range_m: float) -> float | None:
    nose = _point(person, "nose") or _point(person, "left_eye") or _point(person, "right_eye")
    if nose is None:
        return None
    pitch = (tilt_deg or 0.0) * (-1.0 if sight.camera == "rear" else 1.0)
    height = CAMERA_HEIGHT_M.get(sight.camera, 0.14)
    up = math.radians(nose.elevation_deg + pitch)
    return height + range_m * math.tan(up) + HEAD_ABOVE_NOSE_M


def place_people(sight: Sight | None, x: float, y: float, heading: float, tilt_deg: float | None, front_mm: int | None) -> list[Seen]:
    if sight is None:
        return []
    cx, cy, _ = camera_spot(x, y, heading, sight.camera)
    out = []
    for person in sight.people:
        reach = person_range(person, sight, tilt_deg, front_mm)
        angle = body_angle(person.bearing_deg, sight.camera)
        px, py = cx + reach * math.cos(heading + angle), cy + reach * math.sin(heading + angle)
        out.append(Seen(person.track, px, py, reach, angle, person_height(person, sight, tilt_deg, reach), person.face, person.speaking, person, sight.at))
    return out


def cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


class LeadLock:
    def __init__(self, name: str = "", track: int | None = None):
        self.name = name
        self.track = track
        self.x: float | None = None
        self.y: float | None = None
        self.vx = 0.0
        self.vy = 0.0
        self.seen_at: float | None = None
        self.locked_at: float | None = None
        self.height: float | None = None
        self.heights: deque = deque(maxlen=20)
        self.views: list[tuple] = []
        self.track_prints: dict[int, float] = {}
        self.track_print_at: dict[int, float] = {}
        self.print_at = -math.inf
        self.history: deque = deque()
        self.trail: list[tuple[float, float, float]] = []
        self.path: list[tuple[float, float]] = []
        self.unsure = False
        self.unsure_tracks: tuple = ()
        self.candidates: list[Seen] = []
        self.others: list[Seen] = []
        self.swaps = 0
        self.still_since: float | None = None
        self.consumed = 0
        self.maybe: tuple | None = None
        self.track_since: float | None = None

    @property
    def locked(self) -> bool:
        return self.seen_at is not None

    def lost_for(self, now: float) -> float:
        return math.inf if self.seen_at is None else now - self.seen_at

    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)

    def heading(self) -> float | None:
        if self.speed() < 0.15:
            return None
        return math.atan2(self.vy, self.vx)

    def predict(self, now: float) -> tuple[float, float] | None:
        if self.x is None:
            return None
        dt = min(2.0, max(0.0, now - (self.seen_at or now)))
        return self.x + self.vx * dt, self.y + self.vy * dt

    def print_score(self, track: int | None) -> float | None:
        if track is None or not self.views:
            return None
        return self.track_prints.get(track)

    def _score(self, seen: Seen, now: float, heard: bool = False) -> float | None:
        guess = self.predict(now)
        lost = self.lost_for(now)
        gate = min(GATE_MAX_M, GATE_M + GATE_GROWTH_M_S * min(lost, 3.0)) if guess is not None else math.inf
        gap = math.hypot(seen.x - guess[0], seen.y - guess[1]) if guess is not None else 0.0
        same = self.track is not None and seen.track == self.track
        printed = self.print_score(seen.track)
        if not same:
            if printed is not None and printed < PRINT_MATCH:
                return None
            if printed is not None and printed < PRINT_RELOCK and not heard:
                self.maybe = (seen.track, now)
                return None
            if self.views and printed is None and (lost > SWAP_FREE_S or gap > GATE_M):
                return None
            if self.height is not None and seen.height_m is not None and abs(seen.height_m - self.height) > HEIGHT_GATE_M and len(self.heights) >= 5:
                return None
            if gap > gate and (printed is None or printed < PRINT_SURE or lost < 2.0):
                return None
        score = 0.0
        if same:
            score += 2.0
        if gate < math.inf:
            score -= min(gap, gate * 2.0) / max(gate, 1e-3)
        if self.height is not None and seen.height_m is not None:
            score -= min(2.0, abs(seen.height_m - self.height) / HEIGHT_TOLERANCE_M) * 0.6
        if printed is not None:
            score += (printed - PRINT_MATCH) * 8.0
        return score

    def start(self, seen: list[Seen], now: float, track: int | None = None) -> Seen | None:
        if not seen:
            return None
        chosen = None
        if track is not None:
            chosen = next((s for s in seen if s.track == track), None)
        if chosen is None:
            chosen = max(seen, key=lambda s: (s.face, -s.range_m))
        self.track = chosen.track
        self.locked_at = now
        self.track_since = now
        self._accept(chosen, now)
        return chosen

    def update(self, seen: list[Seen], now: float, heard_from: int | None = None) -> Seen | None:
        self.candidates = seen
        if self.seen_at is None:
            return None
        scored = []
        for item in seen:
            score = self._score(item, now, heard_from is not None and item.track == heard_from)
            if score is None:
                continue
            if heard_from is not None and item.track == heard_from:
                score += 3.0
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        self.others = [s for s in seen if not scored or s is not scored[0][1]]
        if not scored:
            self.unsure = False
            return None
        best_score, best = scored[0]
        if len(scored) > 1 and best_score - scored[1][0] < UNSURE_MARGIN and best.track != self.track:
            self.unsure = True
            self.unsure_tracks = (best.track, scored[1][1].track)
            return None
        if len(scored) > 1 and best_score - scored[1][0] < UNSURE_MARGIN * 0.5:
            printed = self.print_score(best.track)
            rival = self.print_score(scored[1][1].track)
            if printed is None or rival is None or abs(printed - rival) < 0.05:
                self.unsure = True
                self.unsure_tracks = (best.track, scored[1][1].track)
                return None
        self.unsure = False
        if best.track != self.track and self.track is not None and best.track is not None:
            self.track_prints.pop(self.track, None)
            self.track_since = now
        self.track = best.track if best.track is not None else self.track
        if self.track_since is None:
            self.track_since = now
        self.maybe = None
        self._accept(best, now)
        return best

    def _accept(self, seen: Seen, now: float) -> None:
        jumped = self.x is None or self.lost_for(now) > JUMP_S or math.hypot(seen.x - self.x, seen.y - self.y) > JUMP_M
        if jumped:
            self.x, self.y = seen.x, seen.y
            self.history.clear()
        else:
            self.x += 0.65 * (seen.x - self.x)
            self.y += 0.65 * (seen.y - self.y)
        self.seen_at = now
        if seen.height_m is not None and 0.6 < seen.height_m < 2.3:
            self.heights.append(seen.height_m)
            ordered = sorted(self.heights)
            self.height = ordered[len(ordered) // 2]
        self.history.append((now, self.x, self.y))
        while self.history and now - self.history[0][0] > HISTORY_S:
            self.history.popleft()
        self._velocity()
        if not self.trail or math.hypot(self.x - self.trail[-1][0], self.y - self.trail[-1][1]) >= CRUMB_M:
            self.trail.append((self.x, self.y, now))
            self.path.append((self.x, self.y))
            del self.path[:-TRAIL_KEEP]
        if self.speed() < 0.15:
            if self.still_since is None:
                self.still_since = now
        else:
            self.still_since = None

    def _velocity(self) -> None:
        if len(self.history) < 3:
            return
        t0 = self.history[0][0]
        ts = [t - t0 for t, _, _ in self.history]
        span = ts[-1] - ts[0]
        if span < 0.4:
            return
        mean_t = sum(ts) / len(ts)
        mean_x = sum(p[1] for p in self.history) / len(ts)
        mean_y = sum(p[2] for p in self.history) / len(ts)
        var = sum((t - mean_t) ** 2 for t in ts)
        if var <= 1e-9:
            return
        self.vx = sum((t - mean_t) * (p[1] - mean_x) for t, p in zip(ts, self.history)) / var
        self.vy = sum((t - mean_t) * (p[2] - mean_y) for t, p in zip(ts, self.history)) / var
        speed = math.hypot(self.vx, self.vy)
        if speed > 2.5:
            self.vx, self.vy = self.vx * 2.5 / speed, self.vy * 2.5 / speed

    def stood_for(self, now: float) -> float:
        return 0.0 if self.still_since is None else now - self.still_since

    def wants_print(self, now: float) -> int | None:
        if self.track is not None and self.lost_for(now) < 0.3 and not self.unsure:
            every = PRINT_EVERY_S if len(self.views) < PRINT_VIEWS else PRINT_SLOW_S
            if now - self.print_at >= every:
                return self.track
        if self.views:
            for seen in self.candidates:
                if seen.track is None or seen.track == self.track:
                    continue
                if now - self.track_print_at.get(seen.track, -math.inf) >= OTHER_PRINT_EVERY_S:
                    return seen.track
        return None

    def alone(self) -> bool:
        if self.x is None:
            return False
        return all(math.hypot(s.x - self.x, s.y - self.y) > 0.9 for s in self.candidates if s.track != self.track)

    def took_print(self, track: int, vec, now: float) -> None:
        if vec is None:
            return
        self.track_print_at[track] = now
        settled = self.track_since is not None and now - self.track_since >= SETTLED_S
        agrees = not self.views or max(cosine(vec, view) for view in self.views) >= PRINT_SURE
        if track == self.track and self.alone() and not self.unsure and (settled or not self.views) and agrees:
            self.print_at = now
            self.views.append(tuple(vec))
            del self.views[:-PRINT_VIEWS]
            self.track_prints[track] = max(cosine(vec, view) for view in self.views)
            return
        if self.views:
            self.track_prints[track] = max(cosine(vec, view) for view in self.views)

    def consume(self, x: float, y: float, reach: float = 0.3) -> None:
        cut = 0
        for index, (cx, cy, _) in enumerate(self.trail):
            if math.hypot(cx - x, cy - y) <= reach:
                cut = index + 1
        if cut > 1:
            self.consumed += cut - 1
            del self.trail[: cut - 1]
