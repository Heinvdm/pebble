import logging
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, time, timedelta
from typing import Callable

from ..understand.logic import wake_up
from ..understand.request import BadRequest, Request, When, from_dict
from .times import AHEAD_S, DEFAULT_PARTS, first_anchor, hm, instant, next_time, one_shot_in, part_time

log = logging.getLogger(__name__)

AGENDA = "agenda.json"
PER_PERSON = 20
IN_ALL = 100
TRIGGER_S = 86400.0
TRIGGER_MOST_S = 7 * 86400.0
USEFUL_S = 12 * 3600.0
LATE_BY_S = 900.0
OWED_KEEP_S = 3 * 86400.0
SEEN_EVERY_S = 60.0
WORD = re.compile(r"[a-z0-9']+")
O_CLOCK = re.compile(r"\b([a-z]+|[0-9]{1,2}) o'?clock\b")
FILLER = frozenset("the a an one ones my your reminder reminders remind me thing things that this for about to of at on in o'clock oclock clock please pebble and it its it's i you later all every".split())
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
DAY_WORDS = {"mon": ("monday", "mondays"), "tue": ("tuesday", "tuesdays"), "wed": ("wednesday", "wednesdays"), "thu": ("thursday", "thursdays"), "fri": ("friday", "fridays"), "sat": ("saturday", "saturdays"), "sun": ("sunday", "sundays")}
KIND_TAGS = {"wake": ("wake", "waking", "alarm", "up"), "reminder": ("remind", "reminder"), "message": ("message", "tell"), "action": ()}
STEP_TAGS = {"check": ("patrol", "round", "rounds", "look", "house", "check"), "go_to_place": ("go", "come"), "come": ("come",), "go_home": ("charger", "bed", "home")}


@dataclass
class Item:
    id: int
    request: dict
    by: str | None
    by_label: str
    tier: str
    made: float
    kind: str = "reminder"
    aimed: str | None = None
    about: list = field(default_factory=list)
    next_at: float | None = None
    key: str = ""
    last_key: str = ""
    anchor: str = ""
    anchor_ts: float | None = None
    armed: float | None = None
    runs_out: float | None = None
    skip: int = 0
    fired: int = 0
    state: str = "waiting"
    private: bool = False
    useful_s: float = USEFUL_S
    words: str = ""
    family: bool = False
    remind: bool = False

    def req(self) -> Request:
        return from_dict(self.request)

    @property
    def when(self) -> When | None:
        return self.req().when

    @property
    def trigger(self):
        return self.req().on

    @property
    def repeats(self) -> bool:
        when = self.when
        return when is not None and when.repeats

    @property
    def speech(self) -> bool:
        return self.kind in ("reminder", "wake")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Item | None":
        try:
            names = {f.name for f in fields(cls)}
            item = cls(**{k: v for k, v in data.items() if k in names})
            item.req()
            return item
        except (TypeError, ValueError, BadRequest):
            return None


def tags(item: Item, local: Callable[[float], datetime]) -> set:
    request = item.req()
    found = set(WORD.findall(item.words.lower()))
    found.update(KIND_TAGS.get(item.kind, ()))
    for step in request.steps():
        found.update(STEP_TAGS.get(step.kind, ()))
        for value in (step.place, step.thing, step.who):
            found.update(WORD.findall(value.lower()))
    when = request.when
    if when is not None:
        for day in when.days:
            found.update(DAY_WORDS[day])
        if when.part:
            found.add(when.part.replace("_", " "))
            found.add("night" if when.part == "tonight" else when.part)
    if item.next_at is not None:
        moment = local(item.next_at)
        hour = moment.hour % 12 or 12
        found.update({str(hour), str(moment.hour), f"{hour}:{moment.minute:02d}"})
        if moment.minute == 0:
            found.add(f"{hour}oclock")
        found.update(word for word, number in NUMBER_WORDS.items() if number == hour)
    return {word[:-1] if word.endswith("s") and len(word) > 3 else word for word in found}


def wanted_words(text: str) -> set:
    lowered = (text or "").lower()
    words = [w for w in WORD.findall(lowered) if w not in FILLER]
    found = {w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words}
    for hour in O_CLOCK.findall(lowered):
        found.add(f"{NUMBER_WORDS.get(hour, hour)}oclock")
    return found


class Agenda:
    def __init__(self, store, clock):
        self.store = store
        self.clock = clock
        data = {}
        try:
            data = store.read(AGENDA, {}) or {}
        except Exception:
            log.exception("the agenda could not be read; starting with an empty one")
        self.items: list[Item] = [item for item in (Item.from_dict(d) for d in data.get("items") or []) if item is not None]
        self.next_id = max([int(data.get("next_id") or 1)] + [item.id + 1 for item in self.items])
        self.parts = dict(data.get("parts") or {})
        self.own_parts = {k: dict(v) for k, v in (data.get("own_parts") or {}).items()}
        self.owed = list(data.get("owed") or [])
        self.seen_at = data.get("seen_at")
        self.dirty = False
        self.every = SEEN_EVERY_S
        self._seen_saved = -1e18

    def save(self, force: bool = False) -> None:
        now = self.clock.now()
        if not self.dirty and not force and now - self._seen_saved < self.every:
            return
        self.seen_at = now
        self._seen_saved = now
        data = {
            "format": 1,
            "items": [item.to_dict() for item in self.items if item.state == "waiting"],
            "next_id": self.next_id,
            "parts": self.parts,
            "own_parts": self.own_parts,
            "owed": [o for o in self.owed if o.get("until", 0) > now],
            "seen_at": self.seen_at,
        }
        try:
            self.store.write(AGENDA, data)
            self.dirty = False
        except Exception:
            log.exception("the agenda could not be saved")

    def local(self, ts: float) -> datetime:
        return self.clock.local(ts)

    def parts_for(self, person_id: str | None) -> dict:
        return {**DEFAULT_PARTS, **self.parts, **(self.own_parts.get(person_id or "", {}))}

    def set_part(self, person_id: str | None, part: str, at: str, everyone: bool) -> None:
        if everyone:
            self.parts[part] = at
            if part == "night":
                self.parts["tonight"] = at
        else:
            own = self.own_parts.setdefault(person_id or "", {})
            own[part] = at
            if part == "night":
                own["tonight"] = at
        self.dirty = True
        for item in self.waiting():
            if item.by == person_id or everyone:
                self.schedule(item, self.clock.now())

    def waiting(self) -> list[Item]:
        return [item for item in self.items if item.state == "waiting"]

    def mine(self, person_id: str | None) -> list[Item]:
        return [item for item in self.waiting() if item.by == person_id]

    def full(self, person_id: str | None) -> str:
        if len(self.waiting()) >= IN_ALL:
            return f"I'm already keeping {IN_ALL} things for later, so I can't take on another one."
        if person_id is not None and len(self.mine(person_id)) >= PER_PERSON:
            return f"You've already got {PER_PERSON} things waiting with me. If you cancel one, I'll take this."
        return ""

    def new(self, request: Request, by: str | None, by_label: str, tier: str, kind: str, aimed: str | None, about: list, private: bool, words: str, family: bool = False) -> Item:
        item = Item(self.next_id, request.as_dict(), by, by_label, tier, self.clock.now(), kind, aimed, list(about), private=private, words=words, family=family)
        self.next_id += 1
        return item

    def plan(self, item: Item, now: float) -> str:
        request = item.req()
        when, trigger = request.when, request.on
        parts = self.parts_for(item.by)
        if when is not None:
            anchor = first_anchor(when, item.made, self.local, parts)
            item.anchor = anchor.isoformat() if anchor else ""
            if when.every_s and not (when.from_ or when.part):
                item.anchor_ts = item.made + when.every_s
        if trigger is not None:
            start = now
            if when is not None and (when.at or when.part or when.date or when.repeats or when.in_s):
                found = next_time(when, now - 1.0, item.made, self.local, parts, self._anchor(item), item.anchor_ts)
                if found is None:
                    return "That time has already gone."
                start = found[0]
            item.armed = start
            longest = TRIGGER_MOST_S
            limit = TRIGGER_S
            if when is not None and when.until_date:
                limit = min(longest, instant(datetime.combine(date.fromisoformat(when.until_date) + timedelta(days=1), time(0)), self.local) - start)
            item.runs_out = start + max(60.0, min(limit, longest))
            item.next_at = None
            for one in trigger.first_of or (trigger,):
                if one.event == "at" and one.at:
                    found = next_time(When(at=one.at), start - 1.0, item.made, self.local, parts)
                    if found is not None and found[0] <= item.runs_out:
                        item.next_at, item.key = found
            if item.runs_out - now > TRIGGER_MOST_S + 1.0:
                return "That's too far ahead for me to keep watch."
            return ""
        found = self.schedule(item, now)
        if found is None:
            return "That time has already gone."
        if when is not None and when.every_s and (when.from_ or when.part) and not (when.days or when.until_date or when.times):
            first = self.local(found[0])
            day = first.date() - timedelta(days=1 if first.time().replace(tzinfo=None) < hm(when.from_ or part_time(when.part, parts)) else 0)
            item.anchor = day.isoformat()
        if item.next_at - now > AHEAD_S + 3600.0 and not item.repeats:
            return "That's more than 30 days away, too far ahead for me to keep."
        return ""

    def _anchor(self, item: Item) -> date | None:
        return date.fromisoformat(item.anchor) if item.anchor else None

    def schedule(self, item: Item, after: float) -> tuple[float, str] | None:
        request = item.req()
        when = request.when
        if when is None:
            if request.on is not None:
                return (item.next_at, item.key) if item.next_at else None
            return None
        if request.on is not None:
            return (item.next_at, item.key) if item.next_at else None
        found = next_time(when, after, item.made, self.local, self.parts_for(item.by), self._anchor(item), item.anchor_ts, item.last_key)
        if found is None:
            item.next_at, item.key = None, ""
            return None
        item.next_at, item.key = found
        self.dirty = True
        return found

    def add(self, item: Item) -> None:
        self.items.append(item)
        self.dirty = True

    def same(self, item: Item) -> tuple[Item | None, Item | None]:
        text = " ".join(item.words.lower().split())
        for other in self.waiting():
            if other is item or other.by != item.by or other.aimed != item.aimed or other.kind != item.kind:
                continue
            if " ".join(other.words.lower().split()) != text:
                continue
            mine, theirs = item.req(), other.req()
            if mine.when == theirs.when and mine.on == theirs.on and mine.if_ == theirs.if_:
                return other, None
            return None, other
        return None, None

    def due(self, now: float) -> list[Item]:
        return [item for item in self.waiting() if item.next_at is not None and item.next_at <= now]

    def advance(self, item: Item, now: float) -> None:
        item.last_key = item.key
        item.fired += 1
        self.dirty = True
        request = item.req()
        when = request.when
        if request.on is not None and when is not None and when.repeats and not (when.times and item.fired >= when.times):
            found = next_time(when, now, item.made, self.local, self.parts_for(item.by), self._anchor(item), item.anchor_ts)
            if found is not None:
                item.armed, item.runs_out, item.next_at, item.key = found[0], found[0] + TRIGGER_S, None, ""
                return
        if when is None or not when.repeats or request.on is not None:
            item.state = "done"
            item.next_at = None
            return
        if when.times and item.fired >= when.times:
            item.state = "done"
            item.next_at = None
            return
        if self.schedule(item, max(now, item.next_at or now)) is None:
            item.state = "done"

    def skip_next(self, item: Item, now: float) -> None:
        item.last_key = item.key
        self.dirty = True
        if self.schedule(item, max(now, item.next_at or now)) is None:
            item.state = "done"

    def remove(self, item: Item, why: str = "cancelled") -> None:
        item.state = why
        self.items = [other for other in self.items if other is not item]
        self.dirty = True

    def forget(self, person_id: str, names: list) -> list[Item]:
        lowered = {name.lower() for name in names or []}
        gone = []
        for item in self.waiting():
            words = set(WORD.findall(item.words.lower()))
            if person_id in (item.by, item.aimed) or person_id in item.about or (lowered and lowered & words and person_id in item.about):
                gone.append(item)
        for item in gone:
            self.remove(item, "forgotten")
        self.own_parts.pop(person_id, None)
        self.owed = [o for o in self.owed if o.get("to") != person_id]
        self.dirty = True
        return gone

    def owe(self, person_id: str | None, text: str, now: float, keep_s: float = OWED_KEEP_S, fresh: bool = False) -> None:
        if person_id is None or not text:
            return
        if any(o.get("to") == person_id and o.get("text") == text for o in self.owed):
            return
        item = {"to": person_id, "text": text, "made": now, "until": now + keep_s}
        if fresh:
            item["after"] = now
        self.owed.append(item)
        self.dirty = True

    def owed_to(self, person_id: str, now: float, seen: float | None = None) -> list[str]:
        mine = [o for o in self.owed if o.get("to") == person_id and o.get("until", 0) > now and (o.get("after") is None or (seen is not None and seen > o["after"]))]
        if mine:
            self.owed = [o for o in self.owed if o not in mine]
            self.dirty = True
        return [o["text"] for o in mine]

    def match(self, text: str, items: list[Item]) -> list[Item]:
        wanted = wanted_words(text)
        if not wanted:
            return list(items)
        scored = []
        for item in items:
            have = tags(item, self.local)
            score = len(wanted & have)
            if score:
                scored.append((score, item))
        if not scored:
            return []
        best = max(score for score, _ in scored)
        return [item for score, item in scored if score == best]

    def shift(self, seconds: float) -> None:
        for item in self.waiting():
            when = item.when
            if when is not None and one_shot_in(when) and item.next_at is not None:
                item.next_at += seconds
                item.made += seconds
            if item.runs_out is not None:
                item.runs_out += seconds
            if item.armed is not None:
                item.armed += seconds
        self.dirty = True

    def recompute(self, now: float) -> None:
        for item in self.waiting():
            when = item.when
            if when is None or one_shot_in(when) or item.req().on is not None:
                continue
            self.schedule(item, now - 1.0)
        self.dirty = True


def kind_of(request: Request) -> str:
    steps = [step for step in request.steps() if not step.branch]
    if steps and all(step.kind == "say_to" and step.who in ("", "me") for step in steps):
        return "wake" if all(wake_up(step.text) for step in steps) else "reminder"
    if steps and all(step.kind == "say_to" for step in steps):
        return "message"
    return "action"


def words_of(request: Request) -> str:
    parts = []
    for step in request.steps():
        for value in (step.text, step.place, step.thing):
            if value and not any(value.lower() in part.lower() for part in parts):
                parts.append(value)
    return " ".join(parts)
