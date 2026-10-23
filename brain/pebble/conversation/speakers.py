import math
from collections import deque
from dataclasses import dataclass

from .turns import cosine

SURE = 0.40
LIKELY = 0.28
SPEAKING = 0.5
LOOKING_DEG = 25.0
AWAY_DEG = 45.0
SIGHT_KEEP_S = 30.0
TRACK_KEEP_S = 600.0
PHONE_LABELS = frozenset({"phone", "cell phone", "mobile phone", "smartphone", "telephone"})
PHONE_NEAR_DEG = 12.0
ADAPT_BELOW = 0.6


@dataclass(frozen=True)
class Seen:
    at: float
    track: int | None
    bearing_deg: float
    elevation_deg: float
    facing_deg: float | None
    speaking: float | None
    face: bool
    on_phone: bool


@dataclass(frozen=True)
class Who:
    person_id: str | None
    score: float
    how: str
    track: int | None = None
    bearing_deg: float | None = None
    looking: bool | None = None
    looking_at_other: bool = False
    on_phone: bool = False
    in_view: int = 0
    lips: bool = False
    voiced: bool = False


def on_phone(person, sight) -> bool:
    for thing in getattr(sight, "things", ()) or ():
        label = str(getattr(thing, "label", "")).lower()
        if label not in PHONE_LABELS or not getattr(thing, "held", False):
            continue
        if abs(thing.bearing_deg - person.bearing_deg) <= PHONE_NEAR_DEG and thing.elevation_deg >= person.elevation_deg - 8.0:
            return True
    return False


class Speakers:
    def __init__(self, book, presence, now):
        self.book = book
        self.presence = presence
        self.now = now
        self.sights: deque = deque()
        self.tracks: dict[int, tuple[str, float]] = {}
        self.voice_tracks: dict[int, tuple[str, float]] = {}

    def look(self, sight, at: float) -> None:
        if sight is None or getattr(sight, "camera", "front") != "front":
            return
        if self.sights and self.sights[-1][0] >= at:
            return
        people = tuple(
            Seen(at, p.track, p.bearing_deg, p.elevation_deg, p.facing_deg, p.speaking, p.face, on_phone(p, sight))
            for p in sight.people
            if p.score >= 0.4
        )
        self.sights.append((at, people))
        while self.sights and at - self.sights[0][0] > SIGHT_KEEP_S:
            self.sights.popleft()

    def during(self, start: float, end: float) -> list[tuple[float, tuple[Seen, ...]]]:
        return [(at, people) for at, people in self.sights if start - 0.5 <= at <= end + 0.5]

    def talker(self, start: float, end: float, prefer: int | None = None) -> tuple[Seen | None, int, list[Seen]]:
        frames = self.during(start, end)
        if not frames:
            return None, 0, []
        in_view = max(len(people) for _, people in frames)
        scores: dict[int | None, list[float]] = {}
        latest: dict[int | None, Seen] = {}
        for _, people in frames:
            for seen in people:
                latest[seen.track] = seen
                if seen.speaking is not None:
                    scores.setdefault(seen.track, []).append(seen.speaking)
        rows = [s for s in latest.values()]
        if prefer is not None and prefer in latest:
            return latest[prefer], in_view, rows
        if scores:
            track, values = max(scores.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
            if sum(values) / len(values) >= SPEAKING:
                return latest[track], in_view, rows
        if len(latest) == 1:
            return next(iter(latest.values())), in_view, rows
        return None, in_view, rows

    def looking(self, talker: Seen | None, start: float, end: float) -> bool | None:
        if talker is None:
            return None
        values = [s.facing_deg for _, people in self.during(start, end) for s in people if s.track == talker.track and s.facing_deg is not None]
        if not values:
            return None
        near = sum(1 for v in values if abs(v) <= LOOKING_DEG)
        away = sum(1 for v in values if abs(v) >= AWAY_DEG)
        if near >= away and near > 0:
            return True
        return False if away > near else None

    def lips_moved(self, talker: Seen | None, start: float, end: float, prefer: int | None = None) -> bool:
        if talker is None or not talker.face:
            return False
        if prefer is not None and talker.track == prefer:
            return True
        values = [s.speaking for _, people in self.during(start, end) for s in people if s.track == talker.track and s.speaking is not None]
        return bool(values) and sum(values) / len(values) >= SPEAKING

    def bound_to(self, track: int | None, now: float) -> str | None:
        found = self.voice_tracks.get(track) if track is not None else None
        if found is None or now - found[1] > TRACK_KEEP_S:
            return None
        return found[0]

    def at_other(self, talker: Seen | None, others: list[Seen]) -> bool:
        if talker is None or talker.facing_deg is None or abs(talker.facing_deg) < AWAY_DEG:
            return False
        side = math.copysign(1.0, talker.facing_deg)
        return any(o.track != talker.track and math.copysign(1.0, o.bearing_deg - talker.bearing_deg) == side for o in others)

    def by_voice(self, voiceprint) -> tuple[str | None, float]:
        if voiceprint is None:
            return None, 0.0
        best, best_score = None, -1.0
        for person in self.book.people.values():
            for stored in person.print_vectors("voice"):
                score = cosine(voiceprint, stored)
                if score > best_score:
                    best, best_score = person.id, score
        return best, best_score

    def remember_track(self, track: int | None, person_id: str | None, at: float) -> None:
        if track is None or person_id is None:
            return
        self.tracks[track] = (person_id, at)
        for old in [t for t, (_, when) in self.tracks.items() if at - when > TRACK_KEEP_S]:
            self.tracks.pop(old, None)

    def identify(self, voiceprint, start: float, end: float, now: float, prefer: int | None = None) -> Who:
        talker, in_view, rows = self.talker(start, end, prefer)
        looking = self.looking(talker, start, end)
        at_other = self.at_other(talker, rows)
        phone = talker is not None and talker.on_phone
        track = talker.track if talker is not None else None
        bearing = talker.bearing_deg if talker is not None else None
        voice_id, score = self.by_voice(voiceprint)
        here = set(self.presence.here(now))
        tracked = self.tracks.get(track)[0] if track in self.tracks else None
        person, how = None, "unknown"
        if voice_id is not None and score >= SURE:
            person, how = voice_id, "voice"
        elif voice_id is not None and score >= LIKELY and (voice_id in here or voice_id == tracked):
            person, how = voice_id, "voice and presence"
        elif tracked is not None:
            person, how = tracked, "seen before"
        elif len(here) == 1 and voiceprint is None and in_view <= 1:
            person, how = next(iter(here)), "only one here"
        if person is not None:
            self.remember_track(track, person, now)
        lips = self.lips_moved(talker, start, end, prefer)
        bound = self.bound_to(track, now)
        lips = lips and bound in (None, person)
        voiced = person is not None and (how == "voice" or (bound == person and voiceprint is None))
        if lips and how == "voice" and track is not None:
            self.voice_tracks[track] = (person, now)
            for old in [t for t, (_, when) in self.voice_tracks.items() if now - when > TRACK_KEEP_S]:
                self.voice_tracks.pop(old, None)
        return Who(person, score, how, track, bearing, looking, at_other, phone, in_view, lips, voiced)

    def enrol_target(self, voiceprint, now: float) -> str | None:
        if voiceprint is None:
            return None
        here = [self.book.get(pid) for pid in self.presence.here(now)]
        fresh = [p for p in here if p is not None and not p.print_vectors("voice") and self.presence.seen(p.id, now)]
        return fresh[0].id if len(fresh) == 1 else None

    def adapt(self, person_id: str | None, voiceprint, score: float, alone: bool, now: float, sure: bool = False) -> bool:
        if person_id is None or voiceprint is None or not alone or not sure or not SURE <= score < ADAPT_BELOW:
            return False
        person = self.book.get(person_id)
        return bool(person is not None and person.add_print("voice", voiceprint, now))
