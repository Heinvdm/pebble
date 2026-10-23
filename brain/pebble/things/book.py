import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Callable

from .facts import Facts
from .guarded import STRANGER_NO, guarded, stranger_may_ask, told_to_anyone
from .words import LANDMARKS, canonical, matches, spoken, with_article

THINGS = "things.json"
SPOTS_PER_THING = 4
THING_CAP = 150
KEEP_DAYS = 30.0
SAME_SPOT_M = 0.6
LANDMARK_M = 1.3
NEAR_DOCK_M = 0.6
DAY_S = 86400.0
UNSURE_SCORE = 0.5
NEAR_KEEP = 4


@dataclass
class Spot:
    at: float
    camera: str
    x: float | None = None
    y: float | None = None
    distance_m: float | None = None
    near: list = field(default_factory=list)
    score: float = 0.0
    lane: str = "fast"
    count: int = 1

    @property
    def placed(self) -> bool:
        return self.x is not None and self.y is not None

    def to_dict(self) -> dict:
        out = asdict(self)
        for key in ("x", "y", "distance_m"):
            if out[key] is not None:
                out[key] = round(out[key], 3)
        out["score"] = round(self.score, 3)
        return out

    @classmethod
    def from_dict(cls, data: dict) -> "Spot | None":
        try:
            return cls(
                float(data["at"]),
                str(data.get("camera", "front")),
                None if data.get("x") is None else float(data["x"]),
                None if data.get("y") is None else float(data["y"]),
                None if data.get("distance_m") is None else float(data["distance_m"]),
                [str(n) for n in data.get("near") or []][:NEAR_KEEP],
                float(data.get("score", 0.0)),
                str(data.get("lane", "fast")),
                int(data.get("count", 1)),
            )
        except (KeyError, TypeError, ValueError):
            return None


@dataclass
class Thing:
    label: str
    animal: bool = False
    first: float = 0.0
    seen: int = 0
    spots: list = field(default_factory=list)

    @property
    def last(self) -> Spot | None:
        return max(self.spots, key=lambda s: s.at) if self.spots else None

    def to_dict(self) -> dict:
        return {"label": self.label, "animal": self.animal, "first": self.first, "seen": self.seen, "spots": [s.to_dict() for s in self.spots]}

    @classmethod
    def from_dict(cls, data: dict) -> "Thing | None":
        try:
            thing = cls(str(data["label"]), bool(data.get("animal", False)), float(data.get("first", 0.0)), int(data.get("seen", 0)))
        except (KeyError, TypeError, ValueError):
            return None
        thing.spots = [s for s in (Spot.from_dict(raw) for raw in data.get("spots") or [] if isinstance(raw, dict)) if s is not None][-SPOTS_PER_THING:]
        return thing


@dataclass(frozen=True)
class Noted:
    label: str
    new_kind: bool
    new_place: bool
    animal: bool


def age_words(seconds: float, local: Callable[[float], datetime] | None = None, at: float | None = None, now: float | None = None) -> str:
    if seconds < 60:
        return "a moment ago"
    if seconds < 90:
        return "about a minute ago"
    if seconds < 3300:
        return f"about {round(seconds / 60)} minutes ago"
    if seconds < 5400:
        return "about an hour ago"
    if seconds < 6 * 3600:
        return f"about {round(seconds / 3600)} hours ago"
    if local is not None and at is not None and now is not None:
        then, today = local(at).date(), local(now).date()
        days = (today - then).days
        if days == 0:
            return "earlier today"
        if days == 1:
            return "yesterday"
        return f"{days} days ago"
    return f"about {round(seconds / DAY_S)} days ago"


class ThingBook:
    def __init__(self, data: dict | None, clock=None):
        data = data or {}
        self.clock = clock
        self.things: dict[str, Thing] = {}
        for raw in data.get("things") or []:
            thing = Thing.from_dict(raw) if isinstance(raw, dict) else None
            if thing is not None:
                self.things[thing.label] = thing
        self.facts = Facts(data.get("told"))
        self.dirty = False

    def tell(self, name: str, where: str, by: str | None, by_label: str, at: float):
        fact = self.facts.tell(name, where, by, by_label, at)
        self.dirty = True
        return fact

    def forget_teller(self, person_id: str) -> bool:
        changed = self.facts.forget_teller(person_id)
        if changed:
            self.dirty = True
        return changed

    def __len__(self) -> int:
        return len(self.things)

    def note(self, label: str, at: float, camera: str, x: float | None, y: float | None, distance_m: float | None, near: list[str], score: float, lane: str, animal: bool) -> Noted:
        label = " ".join(label.lower().split())
        thing = self.things.get(label)
        new_kind = thing is None
        if thing is None:
            thing = Thing(label, animal, at)
            self.things[label] = thing
        thing.seen += 1
        thing.animal = thing.animal or animal
        near = [n for n in dict.fromkeys(near) if n != label][:NEAR_KEEP]
        spot = None
        if x is not None and y is not None:
            placed = [s for s in thing.spots if s.placed]
            closest = min(placed, key=lambda s: math.hypot(s.x - x, s.y - y), default=None)
            if closest is not None and math.hypot(closest.x - x, closest.y - y) <= SAME_SPOT_M:
                spot = closest
        elif thing.spots and not thing.spots[-1].placed:
            spot = thing.spots[-1]
        new_place = spot is None and not new_kind and any(s.placed for s in thing.spots) and x is not None
        if spot is None:
            spot = Spot(at, camera, x, y, distance_m, near, score, lane)
            thing.spots.append(spot)
            del thing.spots[:-SPOTS_PER_THING]
        else:
            spot.at, spot.camera, spot.distance_m, spot.lane = at, camera, distance_m, lane
            spot.score = max(score, spot.score * 0.8)
            spot.count += 1
            if x is not None:
                spot.x, spot.y = (spot.x * 0.7 + x * 0.3, spot.y * 0.7 + y * 0.3) if spot.placed else (x, y)
            if near:
                spot.near = list(dict.fromkeys(near + spot.near))[:NEAR_KEEP]
        self.dirty = True
        self._cap()
        return Noted(label, new_kind, new_place, thing.animal)

    def _cap(self) -> None:
        if len(self.things) <= THING_CAP:
            return
        ordered = sorted(self.things.values(), key=lambda t: t.last.at if t.last else t.first)
        for thing in ordered[: len(self.things) - THING_CAP]:
            del self.things[thing.label]

    def prune(self, now: float) -> int:
        dropped = 0
        for label in list(self.things):
            thing = self.things[label]
            kept = [s for s in thing.spots if now - s.at <= KEEP_DAYS * DAY_S]
            dropped += len(thing.spots) - len(kept)
            thing.spots = kept
            if not kept:
                del self.things[label]
        if dropped:
            self.dirty = True
        return dropped

    def find(self, wanted: str) -> list[Thing]:
        return [thing for thing in self.things.values() if matches(wanted, thing.label)]

    def last_seen(self, wanted: str) -> tuple[Thing, Spot] | None:
        best = None
        for thing in self.find(wanted):
            spot = thing.last
            if spot is not None and (best is None or spot.at > best[1].at):
                best = (thing, spot)
        return best

    def landmark(self, x: float, y: float, skip: str) -> str | None:
        best, gap = None, LANDMARK_M
        for thing in self.things.values():
            if thing.label == skip or canonical(thing.label) not in LANDMARKS or thing.animal:
                continue
            for spot in thing.spots:
                if spot.placed and math.hypot(spot.x - x, spot.y - y) < gap:
                    best, gap = thing.label, math.hypot(spot.x - x, spot.y - y)
        return best

    def where(self, thing: Thing, spot: Spot) -> str:
        if spot.placed:
            mark = self.landmark(spot.x, spot.y, thing.label)
            if mark:
                return f" near the {spoken(mark)}"
            if math.hypot(spot.x, spot.y) <= NEAR_DOCK_M:
                return " by my charger"
        for near in spot.near:
            if canonical(near) in LANDMARKS or len(spot.near) == 1:
                return f" near the {spoken(near)}"
        if spot.placed:
            return f" about {max(1, round(math.hypot(spot.x, spot.y)))} metres from my charger"
        return ""

    def answer(self, wanted: str, now: float, local: Callable[[float], datetime] | None = None, stranger: bool = False) -> str:
        if stranger and not stranger_may_ask(wanted):
            return STRANGER_NO
        fact = self.facts.find(wanted)
        if stranger and fact is not None and not told_to_anyone(fact.name):
            return STRANGER_NO
        told = self.facts.answer(wanted, now)
        if told:
            return told
        found = self.last_seen(wanted)
        if stranger and found is not None and guarded(found[0].label):
            return STRANGER_NO
        name = spoken(wanted)
        if found is None:
            return f"I haven't seen {with_article(name)}. I'll keep an eye out."
        thing, spot = found
        ago = now - spot.at
        when = age_words(ago, local, spot.at, now)
        place = self.where(thing, spot)
        what = with_article(thing.label)
        unsure = spot.score < UNSURE_SCORE
        start = "I think I saw" if unsure else "I saw"
        if thing.animal:
            tail = f", but {'they' if what.startswith('some') else 'it'} could be anywhere by now." if ago > 600 else "."
        elif ago > DAY_S:
            tail = ", so it may have moved since."
        else:
            tail = "."
        if not place:
            return f"{start} {what} {when}, but I'm not sure where."
        return f"{start} {what}{place} {when}{tail}"

    def to_dict(self) -> dict:
        out = {"format": 1, "things": [t.to_dict() for t in sorted(self.things.values(), key=lambda t: t.label)]}
        if self.facts.told:
            out["told"] = self.facts.to_list()
        return out
