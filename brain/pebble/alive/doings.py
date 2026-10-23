import math
from dataclasses import dataclass

from ..activities.seeing import THING_SCORE
from ..seams.sight import SeenPerson, Sight
from ..things.words import canonical

NEAR_DEG = 25.0
END_S = 20.0
STILL = 0.2
STILL_DEG = 10.0
STILL_M = 0.5
SIGNS = {
    "working": ({"laptop", "keyboard", "computer mouse", "monitor", "computer"}, 15.0),
    "eating": ({"fork", "spoon", "knife", "bowl", "plate", "sandwich", "pizza", "banana", "apple", "orange", "cake", "donut", "hot dog", "carrot", "broccoli"}, 10.0),
    "watching tv": ({"tv", "television"}, 20.0),
    "cooking": ({"oven", "stove", "microwave", "pot", "pan", "frying pan", "toaster", "kettle"}, 15.0),
    "packing": ({"suitcase", "backpack", "bag", "handbag"}, 8.0),
    "reading": ({"book"}, 15.0),
    "on the phone": ({"cell phone", "phone"}, 12.0),
}
LEAVING_CARRY = {"backpack", "bag", "handbag", "suitcase", "umbrella", "key", "car keys", "keys"}
BED_KINDS = {"bed", "toothbrush", "pillow"}
EVENTS = {
    "working": "is working at the {thing}",
    "eating": "is eating",
    "watching tv": "is watching TV",
    "cooking": "is cooking",
    "packing": "is packing a bag",
    "reading": "is reading",
    "on the phone": "is on the phone",
    "leaving": "looks like they're heading out",
    "going to bed": "looks like they're going to bed",
}
HUSHED = frozenset({"working", "watching tv", "reading", "on the phone"})


@dataclass(frozen=True)
class Doing:
    what: str
    track: int | None
    since: float
    thing: str = ""

    def text(self, who: str) -> str:
        return f"{who} {EVENTS[self.what].format(thing=self.thing or 'computer')}"


@dataclass(frozen=True)
class Change:
    started: bool
    doing: Doing


def _near(person: SeenPerson, sight: Sight, kinds: set[str]) -> str:
    for thing in sight.things:
        if thing.score < THING_SCORE:
            continue
        kind = canonical(thing.label)
        if (kind in kinds or thing.label in kinds) and abs(thing.bearing_deg - person.bearing_deg) <= NEAR_DEG:
            return kind
    return ""


def _held(person: SeenPerson, sight: Sight, kinds: set[str]) -> str:
    for thing in sight.things:
        kind = canonical(thing.label)
        if thing.held and (kind in kinds or thing.label in kinds) and abs(thing.bearing_deg - person.bearing_deg) <= NEAR_DEG:
            return kind
    return ""


class DoingReader:
    def __init__(self):
        self.seen: dict[tuple[int | None, str], tuple] = {}
        self.current: dict[tuple[int | None, str], Doing] = {}
        self.gaps: dict[int | None, list[tuple[float, float]]] = {}

    def _leaving(self, person: SeenPerson, sight: Sight, now: float) -> str:
        rows = self.gaps.setdefault(person.track, [])
        rows.append((now, person.height_frac))
        del rows[:-12]
        away = person.facing_deg is not None and abs(person.facing_deg) >= 120.0
        carrying = _held(person, sight, LEAVING_CARRY) or _near(person, sight, {"backpack", "suitcase"})
        shrinking = len(rows) >= 4 and rows[-1][1] < rows[0][1] * 0.8 and rows[-1][0] - rows[0][0] >= 1.5
        if away and carrying and shrinking:
            return carrying
        return ""

    def read(self, sight: Sight | None, now: float, hour: int, places: dict | None = None) -> list[Change]:
        places = places or {}
        changes: list[Change] = []
        live: set[tuple[int | None, str]] = set()
        if sight is not None:
            for person in sight.people:
                found: dict[str, str] = {}
                for what, (kinds, _) in SIGNS.items():
                    thing = _held(person, sight, kinds) if what in ("on the phone", "packing") else _near(person, sight, kinds)
                    if thing:
                        found[what] = thing
                if "watching tv" in found and not (person.facing_deg is not None and abs(person.facing_deg) >= 60.0):
                    found.pop("watching tv")
                if "working" in found and "watching tv" in found:
                    found.pop("watching tv")
                leaving = self._leaving(person, sight, now)
                if leaving:
                    found["leaving"] = leaving
                if (hour >= 20 or hour < 2) and _near(person, sight, BED_KINDS):
                    found["going to bed"] = "bed"
                for what, thing in found.items():
                    key = (person.track, what)
                    live.add(key)
                    spot = places.get(person.track)
                    first, _, _, size, anchor = self.seen.get(key, (now, now, thing, person.height_frac, spot if spot is not None else person.bearing_deg))
                    if spot is not None and isinstance(anchor, tuple):
                        moved = math.hypot(spot[0] - anchor[0], spot[1] - anchor[1]) > STILL_M
                    else:
                        moved = size > 0 and abs(person.height_frac / size - 1.0) > STILL or not isinstance(anchor, tuple) and abs(person.bearing_deg - anchor) > STILL_DEG
                    if what != "leaving" and moved:
                        first, size, anchor = now, person.height_frac, spot if spot is not None else person.bearing_deg
                    self.seen[key] = (first, now, thing, size, anchor)
                    hold = SIGNS.get(what, (None, 2.0))[1]
                    if key not in self.current and now - first >= hold:
                        doing = Doing(what, person.track, first, thing)
                        self.current[key] = doing
                        changes.append(Change(True, doing))
        for key, (first, last, thing, _, _) in list(self.seen.items()):
            if key in live:
                continue
            if now - last > END_S:
                self.seen.pop(key, None)
                doing = self.current.pop(key, None)
                if doing is not None:
                    changes.append(Change(False, doing))
        return changes

    def hushed(self) -> bool:
        return any(d.what in HUSHED for d in self.current.values())

    def doing(self) -> list[Doing]:
        return list(self.current.values())

    def cooking(self) -> list[Doing]:
        return [d for d in self.current.values() if d.what == "cooking"]

    def on_the_phone(self) -> bool:
        return any(d.what == "on the phone" for d in self.current.values())


def describe(doings: list[Doing], who) -> str:
    if not doings:
        return ""
    return "; ".join(d.text(who(d.track)) for d in doings)
