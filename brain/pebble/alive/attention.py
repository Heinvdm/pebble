import math
from dataclasses import dataclass

from ..activities.seeing import THING_SCORE
from ..seams.sight import SeenPerson, SeenThing, Sight
from ..things.words import canonical, matches

GAZE_X_DEG = 30.0
GAZE_Y_DEG = 22.0
SWITCH_RATIO = 1.25
DWELL_S = 1.2
BORED_S = 6.0
BORED_DROP = 0.25
NAMED_S = 8.0
LOST_S = 1.5
MOVING_DEG_S = 60.0
PERSON_BASE = 0.35
FACE_BONUS = 0.15
THING_BASE = 0.12
ANIMAL_BASE = 0.4
ARRIVED_S = 3.0
FACE_HOLD_S = 4.0
ANSWER_S = 10.0
GLANCE_S = (0.3, 0.6)
HELD_PULL = 0.7
SPEAKING_PULL = 0.7
SPEAKING_S = 2.5


@dataclass(frozen=True)
class Focus:
    kind: str
    key: str
    label: str
    bearing_deg: float
    elevation_deg: float
    camera: str
    salience: float
    track: int | None = None
    held: bool = False
    why: str = ""


def gaze_for(bearing_deg: float, elevation_deg: float) -> tuple[float, float]:
    x = max(-1.0, min(1.0, -bearing_deg / GAZE_X_DEG))
    y = max(-1.0, min(1.0, -elevation_deg / GAZE_Y_DEG))
    return x, y


def key_of(seen) -> str:
    if isinstance(seen, SeenPerson):
        return f"person:{seen.track}" if seen.track is not None else "person"
    if seen.known:
        return f"known:{seen.known}"
    return f"thing:{canonical(seen.label)}" + (f":{seen.track}" if seen.track is not None else "")


class Attention:
    def __init__(self, novelty=lambda key: 0.0, taste=lambda kind: (0.0, 0.0), weights=lambda: {}):
        self.novelty = novelty
        self.taste = taste
        self.weights = weights
        self.focus: Focus | None = None
        self.since = -math.inf
        self.named: dict[str, float] = {}
        self.first_seen: dict[str, float] = {}
        self.last_bearing: dict[str, tuple[float, float]] = {}
        self.override: tuple[float, float, float, str] | None = None
        self.last_seen: dict[str, float] = {}
        self.face_at: dict[str, float] = {}
        self.speaking: tuple[int | None, float | None, float] | None = None
        self.asked_at = -math.inf

    def hear_speaker(self, now: float, track: int | None = None, bearing_deg: float | None = None) -> None:
        self.speaking = (track, bearing_deg, now)

    def _speaking(self, seen: SeenPerson, sight: Sight, now: float) -> bool:
        if self.speaking is None or now - self.speaking[2] > SPEAKING_S:
            return False
        track, bearing, _ = self.speaking
        if track is not None:
            return seen.track == track
        if bearing is not None:
            return abs(seen.bearing_deg - bearing) <= 15.0 and min(sight.people, key=lambda p: abs(p.bearing_deg - bearing)) is seen
        return len(sight.people) == 1

    def asked(self, now: float) -> None:
        self.asked_at = now

    def hear_named(self, words: list[str], now: float) -> None:
        for word in words:
            self.named[canonical(word)] = now

    def glance_at(self, bearing_deg: float, elevation_deg: float, now: float, seconds: float, why: str = "") -> None:
        self.override = (bearing_deg, elevation_deg, now + seconds, why)

    def _moving(self, key: str, bearing: float, now: float) -> float:
        last = self.last_bearing.get(key)
        self.last_bearing[key] = (bearing, now)
        if last is None or now - last[1] <= 0.0 or now - last[1] > 2.0:
            return 0.0
        rate = abs(bearing - last[0]) / (now - last[1])
        return min(0.3, 0.3 * rate / MOVING_DEG_S)

    def _was_named(self, label: str, now: float) -> bool:
        for word, at in self.named.items():
            if now - at <= NAMED_S and (matches(word, label) or word == canonical(label)):
                return True
        return False

    def score(self, seen, sight: Sight, now: float) -> tuple[float, str]:
        key = key_of(seen)
        self.first_seen.setdefault(key, now)
        self.last_seen[key] = now
        why = []
        weights = self.weights() or {}
        if isinstance(seen, SeenPerson):
            if seen.face:
                self.face_at[key] = now
            value = PERSON_BASE + (FACE_BONUS if now - self.face_at.get(key, -math.inf) <= FACE_HOLD_S else 0.0)
            if now - self.first_seen[key] <= ARRIVED_S:
                value += 0.3
                why.append("just arrived")
            value += min(0.25, seen.height_frac * seen.width_frac * 1.5)
            value *= float(weights.get("people", 1.0))
            if self._speaking(seen, sight, now):
                value += SPEAKING_PULL
                why.append("speaking")
            elif now - self.asked_at <= ANSWER_S and len(sight.people) == 1:
                value += SPEAKING_PULL
                why.append("asked")
        else:
            kind = canonical(seen.label)
            value = ANIMAL_BASE if seen.animal else THING_BASE
            fresh = self.novelty(kind)
            value += 0.5 * fresh
            if fresh > 0.6:
                why.append("new")
            value += min(0.25, seen.height_frac * seen.width_frac * 1.5)
            value *= float(weights.get("things", 1.0))
            if self._was_named(seen.label, now):
                value += 0.6
                why.append("named")
            like, fear = self.taste(kind)
            value += 0.25 * abs(like) + 0.5 * fear
            if fear > 0.3:
                why.append("feared")
            elif like > 0.3:
                why.append("liked")
            if seen.held:
                value += HELD_PULL
                why.append("held")
            if seen.known:
                value += 0.2
                why.append("known")
        moving = self._moving(key, seen.bearing_deg, now)
        if moving > 0.1:
            why.append("moving")
        value += moving * float(weights.get("movement", 1.0))
        if self.focus is not None and self.focus.key == key and now - self.since > BORED_S:
            value -= BORED_DROP
        return value, ", ".join(why)

    def update(self, sight: Sight | None, now: float) -> Focus | None:
        if self.override is not None and now >= self.override[2]:
            self.override = None
        if self.override is not None:
            bearing, elevation, _, why = self.override
            return Focus("glance", "glance", why, bearing, elevation, sight.camera if sight else "front", 9.0, why=why)
        if sight is None:
            if self.focus is not None and now - self.since > LOST_S:
                self.focus = None
            return self.focus
        candidates = [p for p in sight.people if p.score >= 0.4] + [t for t in sight.things if t.score >= THING_SCORE]
        best, best_value, best_why = None, -math.inf, ""
        current_value = None
        for seen in candidates:
            value, why = self.score(seen, sight, now)
            if self.focus is not None and key_of(seen) == self.focus.key:
                current_value = value
            if value > best_value:
                best, best_value, best_why = seen, value, why
        if best is None:
            if self.focus is not None and now - self.last_seen.get(self.focus.key, -math.inf) > LOST_S:
                self.focus = None
            return self.focus
        key = key_of(best)
        keep = self.focus is not None and current_value is not None and key != self.focus.key and (now - self.since < DWELL_S or best_value < current_value * SWITCH_RATIO)
        if keep:
            seen = next(s for s in candidates if key_of(s) == self.focus.key)
            self.focus = self._focus(seen, sight, current_value, self.focus.why)
            return self.focus
        if self.focus is None or key != self.focus.key:
            self.since = now
        self.focus = self._focus(best, sight, best_value, best_why)
        return self.focus

    def _focus(self, seen, sight: Sight, value: float, why: str) -> Focus:
        if isinstance(seen, SeenPerson):
            return Focus("person", key_of(seen), "someone", seen.bearing_deg, seen.elevation_deg, sight.camera, value, seen.track, why=why)
        return Focus("thing", key_of(seen), seen.known or seen.label, seen.bearing_deg, seen.elevation_deg, sight.camera, value, seen.track, seen.held, why)

    def forget(self, now: float, keep_s: float = 30.0) -> None:
        for table in (self.first_seen, self.last_seen, self.face_at):
            for key in [k for k, at in table.items() if now - at > keep_s]:
                table.pop(key, None)
        for key in [k for k, (_, at) in self.last_bearing.items() if now - at > keep_s]:
            self.last_bearing.pop(key, None)
        for word in [w for w, at in self.named.items() if now - at > NAMED_S]:
            self.named.pop(word, None)


def glance_seconds(rng) -> float:
    return rng.uniform(*GLANCE_S)


def find_target(sight: Sight | None, thing: str = "", person: bool = False) -> SeenPerson | SeenThing | None:
    if sight is None:
        return None
    if thing:
        found = [t for t in sight.things if matches(thing, t.label) or (t.known and matches(thing, t.known))]
        return max(found, key=lambda t: t.score) if found else None
    if person and sight.people:
        return max(sight.people, key=lambda p: (p.face, p.height_frac * p.width_frac))
    return None
