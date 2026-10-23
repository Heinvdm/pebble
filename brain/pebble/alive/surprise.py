import math
from dataclasses import dataclass

from ..activities.seeing import DEFAULT_WIDTH_M, THING_SCORE, WIDTHS_M, body_bearing
from ..seams.sight import Sight
from ..things.book import SAME_SPOT_M, ThingBook
from ..things.words import LANDMARKS, canonical, matches, spoken
from .book import toy

USUAL_COUNT = 3
GOOD_VIEW_M = (0.5, 3.0)
EDGE_DEG = 6.0
CONFIRM_GAP_S = 1.5
CONFIRM_KEEP_S = 30.0
QUIET_S = 6 * 3600.0
LEVEL_TILT_DEG = 6.0
GOOD_SCORE = 0.6


@dataclass(frozen=True)
class Surprise:
    kind: str
    label: str
    text: str
    bearing_deg: float
    say: str


def usual_spot(book: ThingBook, label: str, furniture: bool = True):
    thing = book.things.get(label)
    if thing is None or thing.animal or toy(canonical(label)) or (not furniture and canonical(label) in LANDMARKS):
        return None
    spots = [s for s in thing.spots if s.placed and s.count >= USUAL_COUNT]
    if not spots:
        return None
    return max(spots, key=lambda s: s.count)


class Expectations:
    def __init__(self, book: ThingBook):
        self.book = book
        self.pending: dict[tuple[str, str], tuple[float, int]] = {}
        self.said: dict[tuple[str, str], float] = {}

    def _confirm(self, key: tuple[str, str], now: float) -> bool:
        first, count = self.pending.get(key, (now, 0))
        if count and now - first > CONFIRM_KEEP_S:
            first, count = now, 0
        if count and now - first < CONFIRM_GAP_S:
            return False
        count += 1
        self.pending[key] = (first if count > 1 else now, count)
        if count >= 2:
            self.pending.pop(key, None)
            if now - self.said.get(key, -math.inf) < QUIET_S:
                return False
            self.said[key] = now
            return True
        return False

    def clear(self, kind: str, label: str) -> None:
        self.pending.pop((kind, label), None)

    def check(self, sight: Sight | None, pose: tuple[float, float, float] | None, tilt_off_deg: float, now: float) -> list[Surprise]:
        if sight is None or sight.camera != "front" or pose is None or abs(tilt_off_deg) > LEVEL_TILT_DEG:
            return []
        x, y, heading = pose
        half = sight.fov_h_deg / 2.0 - EDGE_DEG
        seen = [t for t in sight.things if t.score >= THING_SCORE]
        found = []
        for label, thing in self.book.things.items():
            spot = usual_spot(self.book, label)
            if spot is None:
                continue
            gap = math.hypot(spot.x - x, spot.y - y)
            if not GOOD_VIEW_M[0] <= gap <= GOOD_VIEW_M[1]:
                continue
            if spot.distance_m is not None and not 0.6 * spot.distance_m <= gap <= 1.6 * spot.distance_m + 0.2:
                continue
            angle = (math.degrees(math.atan2(spot.y - y, spot.x - x)) - heading + 180.0) % 360.0 - 180.0
            if abs(angle) > half:
                continue
            here = [t for t in seen if matches(label, t.label) or canonical(t.label) == canonical(label)]
            near_spot = [t for t in here if abs(body_bearing(t.bearing_deg, sight.camera) - angle) <= 15.0]
            if near_spot:
                self.clear("missing", label)
                continue
            if here:
                continue
            if self._confirm(("missing", label), now):
                name = spoken(label)
                place = self.book.where(thing, spot).strip()
                found.append(Surprise("missing", label, f"the {name} is not {place or 'where it usually is'}", angle, f"Huh. Where's the {name}?"))
        return found

    def moved(self, label: str, score: float, gap_m: float | None, now: float, level: bool = True) -> Surprise | None:
        if score < GOOD_SCORE or gap_m is None or gap_m > GOOD_VIEW_M[1] or not level:
            return None
        thing = self.book.things.get(label)
        spot = usual_spot(self.book, label, furniture=False)
        if thing is None or spot is None:
            return None
        last = thing.last
        size = WIDTHS_M.get(canonical(label), DEFAULT_WIDTH_M)
        far = max(SAME_SPOT_M, 1.5 * size) + 0.25 * (spot.distance_m or gap_m)
        if last is None or not last.placed or math.hypot(last.x - spot.x, last.y - spot.y) <= far:
            self.clear("moved", label)
            return None
        if not self._confirm(("moved", label), now):
            return None
        name = spoken(label)
        place = self.book.where(thing, spot).strip()
        return Surprise("moved", label, f"the {name} has moved from {place or 'its usual spot'}", 0.0, f"Oh! The {name} moved.")
