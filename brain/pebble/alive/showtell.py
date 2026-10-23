import math
import re
from dataclasses import dataclass

from ..seams.sight import SeenThing, Sight
from ..things.words import canonical, spoken, with_article
from .book import AliveBook, Known, unit

CENTRE_DEG = 15.0
CLOSE_AREA = 0.04
HOLD_S = 1.0
COOLDOWN_S = 45.0
SUBJECT_KEEP_S = 90.0
MATCH = 0.75
HOLDER_DEG = 30.0
FACING_DEG = 60.0


@dataclass
class Shown:
    label: str
    track: int | None
    at: float
    by: str | None
    by_label: str
    vec: list | None = None
    known: str | None = None


def similarity(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(unit(a), unit(b)))


def best_known(book: AliveBook, vec) -> tuple[Known | None, float]:
    best, score = None, 0.0
    for known in book.known.values():
        for view in known.prints:
            value = similarity(vec, view)
            if value > score:
                best, score = known, value
    return (best, score) if score >= MATCH else (None, score)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "thing"


def key_for(book: AliveBook, label: str, name: str, owner: str | None) -> str:
    base = slug(name) if name else slug(f"{owner or 'house'} {label}")
    key, n = base, 2
    while key in book.known:
        key, n = f"{base}-{n}", n + 1
    return key


class ShowAndTell:
    def __init__(self):
        self.holding: dict[int | str, float] = {}
        self.cooled: dict[str, float] = {}
        self.subject: Shown | None = None

    def watch(self, sight: Sight | None, now: float) -> SeenThing | None:
        if sight is None or sight.camera != "front" or not sight.people:
            self.holding.clear()
            return None
        live = set()
        chosen = None
        for thing in sight.things:
            if not thing.held or thing.animal or not self._offered(thing, sight):
                continue
            close = thing.height_frac * thing.width_frac >= CLOSE_AREA
            centred = abs(thing.bearing_deg) <= CENTRE_DEG
            key = thing.track if thing.track is not None else canonical(thing.label)
            if not (close and centred):
                continue
            live.add(key)
            since = self.holding.setdefault(key, now)
            label = thing.known or canonical(thing.label)
            cooled = max(self.cooled.get(label, -math.inf), self.cooled.get(f"track:{thing.track}", -math.inf))
            if now - since >= HOLD_S and now - cooled >= COOLDOWN_S:
                chosen = thing
        for key in [k for k in self.holding if k not in live]:
            self.holding.pop(key, None)
        if chosen is not None:
            self.cool(chosen, now)
        return chosen

    def cool(self, thing: SeenThing, now: float) -> None:
        self.cooled[thing.known or canonical(thing.label)] = now
        if thing.track is not None:
            self.cooled[f"track:{thing.track}"] = now

    def _offered(self, thing: SeenThing, sight: Sight) -> bool:
        holders = [p for p in sight.people if abs(p.bearing_deg - thing.bearing_deg) <= HOLDER_DEG]
        return any(p.facing_deg is None or abs(p.facing_deg) <= FACING_DEG for p in holders)

    def shown(self, thing: SeenThing, now: float, by: str | None, by_label: str) -> Shown:
        self.subject = Shown(canonical(thing.label), thing.track, now, by, by_label, None, thing.known)
        return self.subject

    def current(self, now: float) -> Shown | None:
        if self.subject is not None and now - self.subject.at > SUBJECT_KEEP_S:
            self.subject = None
        return self.subject


def first_look(shown: Shown, known: Known | None) -> str:
    if known is not None:
        return f"{known.name.title()}!" if known.name else f"That's {known.title()}!"
    return f"Ooh, {with_article(spoken(shown.label))}? What's it called?"


def thanks(known: Known, asker_id: str | None) -> str:
    label = spoken(known.label)
    if known.owner == "pebble":
        return f"{known.name.title()}! My very own {label}? Thank you!" if known.name else f"My very own {label}? Thank you!"
    if known.name:
        return f"{known.name.title()}! I'll remember."
    if known.owner and known.owner == asker_id:
        return f"Your {label}. Got it."
    if known.owner_label:
        return f"{known.owner_label}'s {label}. Got it."
    return f"{with_article(label)[0].upper()}{with_article(label)[1:]}. Got it."
