import logging
from typing import Callable

from ..clock import iso
from ..inner.temperament import Temperament
from ..selfstore.atomic import CorruptFile, TamperedFile
from .checker import Ruling, check, refused, valid
from .registry import DIALS, PEBBLE, PERSONALITY, REGISTRY
from .stability import held

log = logging.getLogger(__name__)

DIALS_FILE = "dials.json"
KEEP_CHANGES = 200
KEEP_TRIPS = 50
HISTORY_KEEP = 100
WONDER = ("stakes", "surprise", "stuck", "invalid", "doubt", "drives", "pile")
RECALL = ("recency", "importance", "relevance", "people")
BOARD = ("memories", "drives", "wonderings", "surprises")
GATE = {
    "scared_at": "gate.scared_at",
    "low_at": "gate.low_at",
    "sleepy_at": "gate.sleepy_at",
    "stranger_play_mood": "gate.stranger_play_mood",
    "stranger_play_fear": "gate.stranger_play_fear",
    "stranger_come_mood": "gate.stranger_come_mood",
    "stranger_come_fear": "gate.stranger_come_fear",
}


class Dials:
    def __init__(self, store, clock, record: Callable[..., None] | None = None, own_name: str = "Pebble"):
        self.store = store
        self.clock = clock
        self.record = record or (lambda kind, **data: None)
        self.on_change: Callable[[str], None] = lambda name: None
        self.own_name = own_name
        try:
            data = store.read(DIALS_FILE, {}) or {}
        except (CorruptFile, TamperedFile):
            log.warning("%s could not be read, so Pebble's dials start from their defaults", DIALS_FILE)
            data = {}
        self.values: dict = {}
        for name, raw in (data.get("values") or {}).items():
            found = REGISTRY.get(name)
            if found is None or found.home != DIALS:
                continue
            ruling = valid(found, raw, own_name)
            if ruling.ok:
                self.values[name] = ruling.value
        self.changes: list[dict] = [c for c in data.get("changes") or [] if isinstance(c, dict)][-KEEP_CHANGES:]
        self.trips: list[dict] = [t for t in data.get("trips") or [] if isinstance(t, dict)][-KEEP_TRIPS:]

    def value(self, name: str):
        return self.values.get(name, REGISTRY[name].default)

    def temperament(self) -> Temperament:
        return Temperament(
            half_life_s=float(self.value("mood.half_life_min")) * 60.0,
            resting=float(self.value("mood.resting")),
            shift_h=float(self.value("rhythm.shift_h")),
            company=float(self.value("needs.company")),
            curiosity=float(self.value("needs.curiosity")),
            rest=float(self.value("needs.rest")),
            startle=float(self.value("startle")),
            getting_used=float(self.value("getting_used")),
            praise=float(self.value("events.praise")),
            touch=float(self.value("events.touch")),
            talk=float(self.value("events.talk")),
            scold=float(self.value("events.scold")),
        )

    def pulls(self) -> dict:
        return {kind: float(self.value(f"wonder.{kind}")) for kind in WONDER}

    def recall_weights(self) -> dict:
        return {kind: float(self.value(f"recall.{kind}")) for kind in RECALL}

    def board_weights(self) -> dict:
        return {kind: float(self.value(f"board.{kind}")) for kind in BOARD}

    def thoughtfulness(self) -> float:
        return float(self.value("thoughtfulness"))

    def doubt_at(self) -> float:
        return float(self.value("doubt.at"))

    def current(self, name: str):
        found = REGISTRY[name]
        if found.home == DIALS:
            return self.value(name)
        if found.home == PERSONALITY:
            personality = self.store.read(PERSONALITY, {}) or {}
            head, _, tail = found.key.partition(".")
            holder = personality.get(head) if tail else personality
            return (holder or {}).get(tail or head, found.default) if isinstance(holder, dict) else found.default
        return found.default

    def _own_range(self, name: str) -> tuple | None:
        found = REGISTRY[name]
        if found.home != PERSONALITY or not found.key.startswith("traits."):
            return None
        raw = ((self.store.read(PERSONALITY, {}) or {}).get("ranges") or {}).get(found.key.split(".", 1)[1])
        try:
            return int(raw[0]), int(raw[1])
        except (TypeError, ValueError, IndexError):
            return None

    def _write_personality(self, name: str, before, after, who: str, why: str, now: float) -> None:
        found = REGISTRY[name]
        personality = self.store.read(PERSONALITY, {}) or {}
        head, _, tail = found.key.partition(".")
        if tail:
            personality.setdefault(head, {})[tail] = after
            entry = {"at": iso(now), "trait": tail, "from": before, "to": after}
        else:
            personality[head] = after
            entry = {"at": iso(now), "field": head}
        entry.update({"by": who, "why": why})
        personality.setdefault("history", []).append(entry)
        del personality["history"][:-HISTORY_KEEP]
        self.store.write(PERSONALITY, personality)

    def attention(self) -> dict:
        return {kind: float(self.value(f"attention.{kind}")) for kind in ("people", "things", "movement")}

    def gate(self) -> dict:
        return {field: float(self.value(name)) for field, name in GATE.items()}

    def idea_weights(self) -> tuple[float, float, float]:
        return float(self.value("ideas.needs")), float(self.value("ideas.values")), float(self.value("ideas.mood"))

    def chaos_mood(self) -> float:
        return float(self.value("chaos.mood"))

    def propose(self, name: str, value, who: str = PEBBLE, why: str = "") -> Ruling:
        ruling = check(name, value, who, self.own_name)
        if not ruling.ok:
            return ruling
        found = REGISTRY[name]
        if found.home not in (DIALS, PERSONALITY):
            return refused(f"{found.about} changes through {found.via or found.home}")
        if not found.live:
            return refused(f"nothing uses {found.about} yet, so it stays as it is")
        before, after = self.current(name), ruling.value
        own = self._own_range(name)
        if own is not None and not own[0] <= after <= own[1]:
            return refused(f"{found.about} goes from {own[0]} to {own[1]} for this Pebble")
        if after == before:
            return Ruling(True, "it is already that", after)
        if not why.strip():
            return refused("a change needs a reason")
        why = " ".join(why.split())[:200]
        now = self.clock.now()
        hold = held(self.changes, name, before, after, now)
        if hold:
            self.trips.append({"at": now, "name": name, "from": before, "to": after})
            del self.trips[:-KEEP_TRIPS]
            self.record("stability_held", dial=name)
            self.save()
            return refused(hold)
        if found.home == PERSONALITY:
            self._write_personality(name, before, after, who, why, now)
        else:
            self.values[name] = after
        self.changes.append({"at": now, "name": name, "from": before, "to": after, "who": who, "why": why})
        del self.changes[:-KEEP_CHANGES]
        self.record("dial_changed", dial=name, before=before, after=after, who=who, why=why)
        self.save()
        self.on_change(name)
        return Ruling(True, "", after)

    def born(self, drawn: dict) -> None:
        for name, raw in drawn.items():
            found = REGISTRY.get(name)
            if found is None or found.home != DIALS:
                continue
            ruling = valid(found, raw, self.own_name)
            if ruling.ok:
                self.values[name] = ruling.value
        self.save()
        self.on_change("birth")

    def save(self) -> None:
        self.store.write(DIALS_FILE, {"format": 1, "values": dict(sorted(self.values.items())), "changes": self.changes, "trips": self.trips})
