import math
from dataclasses import dataclass, field
from datetime import timedelta

from ..hearing.taught import thing_of
from ..house.tell import NOW as HOUSE_SOUNDS
from ..people.trust import STRANGER
from ..things.words import canonical, matches
from ..understand.logic import CANNOT_TELL_EVENT
from ..understand.request import DAYS, Cond, Trigger

ARRIVE_AFTER_S = 600.0
LEFT_AFTER_S = 600.0
PRESENT_S = 600.0
WITH_PEBBLE_S = 120.0
KEEP_S = 86400.0
KEEP_MOST = 400
VIEW_AGAIN_S = 60.0
QUIET_MINUTES = 10.0
TV_QUIET_MINUTES = 10.0
HEARD_MINUTES = 30.0
SEEN_MINUTES = 2.0
LOW_BATTERY = 20.0
SOUND_WORDS = {"knock": "knock", "knocking": "knock", "door knock": "knock", "doorbell": "doorbell", "door bell": "doorbell", "bell": "doorbell", "microwave": "microwave", "kettle": "kettle", "phone": "phone", "telephone": "phone", "alarm clock": "alarm_clock", "rain": "rain", "thunder": "thunder", "smoke alarm": "alarm", "fire alarm": "alarm", "alarm": "alarm", "co alarm": "alarm"}
HEARABLE = frozenset(HOUSE_SOUNDS) | {"rain", "thunder", "alarm", "meowing", "dog_crying"}
STATE_EVENTS = frozenset({"quiet", "battery", "tv_off", "at"})


@dataclass(frozen=True)
class Happened:
    event: str
    at: float
    who: str = ""
    label: str = ""
    thing: str = ""
    guess: bool = False

    def as_dict(self) -> dict:
        out = {"event": self.event, "at": round(self.at, 1)}
        for key in ("who", "thing"):
            value = getattr(self, key)
            if value:
                out[key] = value
        if self.guess:
            out["guess"] = True
        return out


def sound_kind(word: str) -> str:
    plain = " ".join((word or "").lower().replace("_", " ").split())
    return SOUND_WORDS.get(plain, plain.replace(" ", "_"))


@dataclass
class Feed:
    started: float
    log: list = field(default_factory=list)
    fresh: list = field(default_factory=list)
    last: dict = field(default_factory=dict)
    gone: dict = field(default_factory=dict)
    view: dict = field(default_factory=dict)
    talk_at: float = -math.inf
    noise_at: float = -math.inf

    def _add(self, happened: Happened) -> Happened:
        self.log.append(happened)
        self.fresh.append(happened)
        cut = happened.at - KEEP_S
        self.log = [h for h in self.log if h.at >= cut][-KEEP_MOST:]
        return happened

    def drain(self) -> list[Happened]:
        out, self.fresh = self.fresh, []
        return out

    def people(self, now: float, seen: list) -> list[Happened]:
        out = []
        for person_id, label, last in seen:
            before = self.last.get(person_id, -math.inf)
            if last > before:
                away = last - before >= ARRIVE_AFTER_S
                watched = before > -math.inf or last - self.started >= ARRIVE_AFTER_S
                if away and watched and now - last <= WITH_PEBBLE_S:
                    out.append(self._add(Happened("arrives", now, person_id, label)))
                self.last[person_id] = last
            if last > -math.inf and now - last >= LEFT_AFTER_S and self.gone.get(person_id) != last:
                self.gone[person_id] = last
                out.append(self._add(Happened("leaves", now, person_id, label, guess=True)))
        return out

    def forget(self, person_id: str) -> None:
        self.last.pop(person_id, None)
        self.gone.pop(person_id, None)
        self.log = [h for h in self.log if h.who != person_id]
        self.fresh = [h for h in self.fresh if h.who != person_id]

    def seen(self, now: float, labels: list) -> list[Happened]:
        out = []
        for label in labels:
            if now - self.view.get(label, -math.inf) > VIEW_AGAIN_S:
                out.append(self._add(Happened("seen", now, thing=label)))
            self.view[label] = now
        return out

    def sound(self, now: float, kind: str) -> Happened:
        self.noise_at = now
        return self._add(Happened("sound", now, thing=sound_kind(kind)))

    def talk(self, now: float) -> None:
        self.talk_at = now

    def done(self, now: float, kind: str) -> Happened:
        return self._add(Happened("done", now, thing=kind))

    def quiet_for(self, now: float) -> float:
        return now - max(self.talk_at, self.noise_at, self.started)

    def heard(self, thing: str, since: float) -> bool:
        kind = sound_kind(thing)
        return any(h.event == "sound" and h.thing == kind and h.at >= since for h in self.log)

    def saw(self, thing: str, since: float) -> bool:
        return any(h.event == "seen" and matches(thing, h.thing) and h.at >= since for h in self.log)


def match(trigger: Trigger, happened: Happened, whom: dict) -> bool:
    if trigger.first_of:
        return any(match(one, happened, whom) for one in trigger.first_of)
    if trigger.event == "seen" and trigger.who and not trigger.thing:
        wanted = whom.get(trigger.who)
        return happened.event == "arrives" and wanted is not None and happened.who == wanted
    if trigger.event != happened.event:
        return False
    if trigger.event in ("arrives", "leaves"):
        wanted = whom.get(trigger.who)
        return wanted is not None and wanted == happened.who
    if trigger.event == "sound":
        return sound_kind(trigger.thing or trigger.what) == happened.thing
    if trigger.event == "seen":
        wanted = trigger.thing or trigger.what
        return bool(wanted) and matches(wanted, happened.thing)
    if trigger.event == "done":
        return True
    return False


class LifeSenses:
    def __init__(self, life, feed: Feed):
        self.life = life
        self.feed = feed

    @property
    def clock(self):
        return self.life.p.clock

    def person(self, who: str, asker: str | None):
        if who in ("", "me"):
            return self.life.company.book.get(asker) if asker else None
        return self.life.company.book.find(who)

    def eyes_open(self) -> bool:
        life = self.life
        if not getattr(life.p.eyes, "available", False):
            return False
        privacy = getattr(life, "privacy", None)
        try:
            return not (privacy is not None and privacy.active())
        except Exception:
            return False

    def can_sense(self, trigger: Trigger) -> str:
        for one in trigger.first_of or (trigger,):
            if one.event == "cannot_tell":
                return CANNOT_TELL_EVENT
            if one.event == "seen" and not getattr(self.life.p.eyes, "available", False):
                return "I can't see yet, so I can't tell when that happens."
            if one.event == "sound" and not self.can_hear(one.thing or one.what):
                return "I can't tell that sound apart yet, so I can't tell when it happens."
            if (one.event in ("arrives", "leaves") or (one.event == "seen" and not one.thing)) and one.who and self.person(one.who, None) is None and one.who not in ("", "me"):
                return f"I don't know who {one.who.title()} is, so I can't tell when they come and go."
        return ""

    def can_hear(self, thing: str) -> bool:
        kind = sound_kind(thing)
        if kind in HEARABLE:
            return True
        house = getattr(self.life, "house", None)
        taught = getattr(house, "taught", None)
        sounds = getattr(taught, "sounds", {}) or {}
        return any(kind == sound_kind(thing_of(sound.name)) or kind == sound_kind(sound.name) for sound in sounds.values())

    def present(self, person_id: str, now: float) -> bool:
        return now - self.life.company.presence.last_present(person_id) <= PRESENT_S

    def with_pebble(self, person_id: str, now: float) -> bool:
        return now - self.life.company.presence.last_present(person_id) <= WITH_PEBBLE_S

    def room(self) -> str | None:
        try:
            return self.life.alive.rooms.where_am_i()
        except Exception:
            return None

    def state(self, cond: Cond, asker: str | None, results: dict | None = None):
        life = self.life
        now = self.clock.now()
        local = self.clock.local(now)
        kind = cond.state
        if kind == "present":
            person = self.person(cond.who, asker)
            if person is None:
                return None
            if self.present(person.id, now):
                return True
            return False if self.eyes_open() else None
        if kind == "in_room":
            room = self.room()
            if cond.who:
                person = self.person(cond.who, asker)
                if person is None:
                    return None
                if not self.present(person.id, now):
                    return False if self.eyes_open() else None
                if room is None or not self.with_pebble(person.id, now):
                    return None
                return room == cond.place
            if room != cond.place:
                return None
            if not self.eyes_open():
                return None
            here = [p for p in life.company.here(now)]
            return bool(here) or life.company.someone_new(now)
        if kind in ("after", "before", "time_between"):
            hhmm = local.strftime("%H:%M")
            if kind == "after":
                return hhmm >= cond.at
            if kind == "before":
                return hhmm < cond.at
            start, end = cond.from_, cond.to
            return start <= hhmm < end if start <= end else (hhmm >= start or hhmm < end)
        if kind == "day_is":
            return self.day_is(cond.day, local.date())
        if kind == "result":
            answer = (results or {}).get(cond.name) or (results or {}).get("")
            if answer in (None, "unsure"):
                return None
            return answer == (cond.is_ or "yes")
        if kind == "heard_lately":
            return self.feed.heard(cond.thing or cond.what, now - 60.0 * (cond.minutes or HEARD_MINUTES))
        if kind == "seen_lately":
            since = now - 60.0 * (cond.minutes or SEEN_MINUTES)
            if self.feed.saw(cond.thing or cond.what, since):
                return True
            found = life.p.books.things.last_seen(canonical(cond.thing or cond.what)) if (cond.thing or cond.what) else None
            if found is not None and found[1].at >= since:
                return True
            return False if self.eyes_open() else None
        if kind == "battery_below":
            sensors = getattr(life, "sensors", None)
            battery = getattr(sensors, "battery", None)
            percent = getattr(battery, "percent", None)
            if percent is None:
                return None
            return percent < (cond.level or LOW_BATTERY)
        if kind == "doing":
            current = life.commands.runner.current
            if not cond.what:
                return current is not None
            return current is not None and current.kind == cond.what
        if kind == "cooking":
            house = getattr(life, "house", None)
            cooking = getattr(house, "cooking", None)
            if cooking is None:
                return None
            if cooking.open:
                return True
            doings = getattr(getattr(life, "alive", None), "doings", None)
            try:
                return bool(doings.cooking()) if doings is not None else None
            except Exception:
                return None
        if kind == "quiet_hours":
            return life.quiet_hours.contains(local)
        if kind == "room_quiet":
            return self.feed.quiet_for(now) >= 60.0 * (cond.minutes or QUIET_MINUTES)
        if kind == "looks":
            teaching = getattr(life, "teaching", None)
            return teaching.looks_now(cond.what, cond.place, cond.thing) if teaching is not None else None
        return None

    def day_is(self, day: str, today) -> bool:
        if day in DAYS:
            return DAYS[today.weekday()] == day
        if day == "weekday":
            return today.weekday() < 5
        if day == "weekend":
            return today.weekday() >= 5
        if day == "holiday":
            return self.holiday(today)
        if day == "tomorrow_holiday":
            return self.holiday(today + timedelta(days=1))
        return False

    def holiday(self, day) -> bool:
        try:
            return any(o.kind == "holiday" for o in self.life.p.books.calendar.on(day))
        except Exception:
            return False

    def edge(self, trigger: Trigger, since: float) -> bool:
        now = self.clock.now()
        if trigger.event in ("quiet", "tv_off"):
            minutes = trigger.minutes or (TV_QUIET_MINUTES if trigger.event == "tv_off" else QUIET_MINUTES)
            return now - since >= 60.0 * minutes and self.feed.quiet_for(now) >= 60.0 * minutes
        if trigger.event == "battery":
            sensors = getattr(self.life, "sensors", None)
            percent = getattr(getattr(sensors, "battery", None), "percent", None)
            return percent is not None and percent < (trigger.level or LOW_BATTERY)
        return False

    def tier(self, person_id: str | None) -> str:
        person = self.life.company.book.get(person_id) if person_id else None
        return self.life.company.tier(person, self.clock.now()) if person is not None else STRANGER
