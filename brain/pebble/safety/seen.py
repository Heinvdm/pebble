import math
from collections import deque
from dataclasses import dataclass

from .notice import Notice

RESTING = ("couch", "sofa", "bed", "armchair", "chair", "bench", "mattress", "hammock", "beanbag", "bean bag", "futon", "recliner", "daybed", "sofa bed", "cushion", "pillow", "dog bed", "lounger", "deck chair")
LYING = "lying"
FLOOR_CONFIRM_S = 8.0
FLOOR_SHARE = 0.7
FLOOR_GAP_S = 600.0
FLOOR_OVERLAP_DEG = 8.0
FIRE_LABELS = ("fire", "flame", "flames")
SMOKE_LABELS = ("smoke",)
FIRE_SCORE = 0.5
FIRST_LOOK_S = 3.0
SECOND_LOOK_S = 10.0
FIRE_SHARE = 0.6
FIRE_CLOSE_HEIGHT = 0.25
FIRE_AHEAD_DEG = 30.0
FIRE_HOLD_S = 5.0
FIRE_GAP_S = 120.0
SMOKE_FIRST = 0.45
SMOKE_SECOND = 0.7
USUAL_AFTER = 2
PLACE_DEG = 25.0


@dataclass
class _Track:
    first: float
    last: float
    seen: int
    lying: int
    bearing: float


def _overlaps(person, thing) -> bool:
    half_p = max(FLOOR_OVERLAP_DEG, 30.0 * person.width_frac)
    half_t = max(FLOOR_OVERLAP_DEG, 30.0 * thing.width_frac)
    return abs(person.bearing_deg - thing.bearing_deg) <= half_p + half_t


def place_of(person, things) -> str | None:
    near = [t for t in things if not getattr(t, "animal", False) and str(t.label).lower() not in FIRE_LABELS + SMOKE_LABELS and abs(t.bearing_deg - person.bearing_deg) <= PLACE_DEG]
    if not near:
        return None
    return str(min(near, key=lambda t: abs(t.bearing_deg - person.bearing_deg)).label).lower()


def resting_on(person, things) -> str | None:
    for thing in things:
        label = str(thing.label).lower()
        if any(word == label or word in label.split() or label.endswith(" " + word) for word in RESTING) and _overlaps(person, thing):
            return label
    return None


class FloorWatch:
    def __init__(self):
        self.tracks: dict = {}
        self.said: dict = {}
        self.usual: dict[str, int] = {}
        self.last_at: float | None = None

    def feed(self, sight, now: float, mono: float) -> list[Notice]:
        if sight is None or sight.at == self.last_at:
            return []
        self.last_at = sight.at
        out = []
        seen_keys = set()
        for index, person in enumerate(sight.people):
            key = person.track if person.track is not None else f"b{round(person.bearing_deg / 15.0)}"
            seen_keys.add(key)
            track = self.tracks.get(key)
            if track is None:
                track = self.tracks[key] = _Track(mono, mono, 0, 0, person.bearing_deg)
            track.last = mono
            track.seen += 1
            track.bearing = person.bearing_deg
            if person.posture == LYING and resting_on(person, sight.things) is None:
                track.lying += 1
            if mono - track.first >= FLOOR_CONFIRM_S and track.seen >= 4 and track.lying >= FLOOR_SHARE * track.seen:
                if mono - self.said.get(key, -math.inf) >= FLOOR_GAP_S:
                    self.said[key] = mono
                    place = place_of(person, sight.things)
                    usual = place is not None and self.usual.get(place, 0) >= USUAL_AFTER
                    confidence = 0.45 if usual else 0.7
                    where = f" near the {place}" if place else ""
                    out.append(Notice("on_floor", confidence, "eyes", now, f"someone has been lying on the floor{where} for {round(mono - track.first)} seconds, not on a bed or couch", {"bearing_deg": round(person.bearing_deg), "place": place, "usual": usual, "track": person.track}))
                track.first, track.seen, track.lying = mono, 0, 0
            elif mono - track.first >= FLOOR_CONFIRM_S * 2:
                track.first, track.seen, track.lying = mono, 0, 0
        for key in [k for k, t in self.tracks.items() if k not in seen_keys and mono - t.last > FLOOR_CONFIRM_S]:
            del self.tracks[key]
        return out

    def fine_at(self, place: str | None) -> None:
        if place:
            self.usual[place] = self.usual.get(place, 0) + 1


class FireWatch:
    def __init__(self):
        self.sightings: deque = deque()
        self.first_said = -math.inf
        self.second_said = -math.inf
        self.close_until = -math.inf
        self.last_at: float | None = None
        self.started: float | None = None

    def feed(self, sight, now: float, mono: float) -> list[Notice]:
        if sight is None or sight.at == self.last_at:
            return []
        self.last_at = sight.at
        found = [t for t in sight.things if str(t.label).lower() in FIRE_LABELS + SMOKE_LABELS and t.score >= FIRE_SCORE]
        self.sightings.append((mono, bool(found), any(str(t.label).lower() in FIRE_LABELS for t in found)))
        while self.sightings and mono - self.sightings[0][0] > SECOND_LOOK_S:
            self.sightings.popleft()
        for thing in found:
            if abs(thing.bearing_deg) <= FIRE_AHEAD_DEG and thing.height_frac >= FIRE_CLOSE_HEIGHT and str(thing.label).lower() in FIRE_LABELS:
                self.close_until = mono + FIRE_HOLD_S
        if not found:
            if self.started is not None and not any(hit for _, hit, _ in self.sightings):
                self.started = None
            return []
        if self.started is None:
            self.started = mono
        span = mono - self.started
        recent = [s for s in self.sightings if mono - s[0] <= span + 0.01]
        share = sum(1 for _, hit, _ in recent if hit) / max(1, len(recent))
        flames = any(fire for _, hit, fire in recent if hit)
        what = "flames" if flames else "smoke"
        out = []
        if span >= SECOND_LOOK_S and share >= FIRE_SHARE and mono - self.second_said >= FIRE_GAP_S:
            self.second_said = mono
            out.append(Notice("smoke_seen", 0.86 if flames else SMOKE_SECOND, "eyes", now, f"you looked again and still see what looks like {what}", {"what": what, "second_look": True}))
        elif span >= FIRST_LOOK_S and share >= FIRE_SHARE and mono - self.first_said >= FIRE_GAP_S:
            self.first_said = mono
            out.append(Notice("smoke_seen", 0.6 if flames else SMOKE_FIRST, "eyes", now, f"you think you see {what} (candles, fireplaces, steam and fires on television can look the same)", {"what": what, "second_look": False}))
        return out

    def hold_reason(self, mono: float) -> str | None:
        return "there's fire right in front of me" if mono < self.close_until else None
