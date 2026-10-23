import asyncio
import math
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..activities.gate import PEBBLE, Asker, Situation, decide
from ..people.trust import CHILD, FRIEND, INNER, STRANGER, TRUSTED
from ..respect import cruel, harsh
from ..seams.face import FACES
from ..self.registry import PEBBLE as OWN, entry as dial_entry
from ..sim.world import SimPerson, SimThing, World, room as sim_room
from ..tact import tactless
from ..things.guarded import close_only, dangerous
from ..understand.context import context_from
from ..understand.understanding import Understanding
from .abilities import FEELINGS, WANTED
from .check import CLOCK, Checked, Ground, until_at
from .evaluate import Crash
from .host import Local, Refused, Session
from .program import LIMITS, Limits

DREAM_START = (7, 0)
DREAM_SPAN_S = 24 * 3600.0
ROOMS = {"lounge": (2500.0, 0.0), "kitchen": (4200.0, 2200.0), "study": (4200.0, -2200.0), "hall": (800.0, 1800.0), "bedroom": (6500.0, -1900.0), "bathroom": (6500.0, 1900.0)}
PRIVATE = frozenset({"bathroom", "bedroom"})
THINGS = {"ball": "lounge", "cat": "lounge", "dog": "hall", "key": "hall", "plant pot": "lounge", "slipper": "bedroom", "cup": "kitchen", "book": "study", "remote": "lounge", "shoe": "hall", "phone": "kitchen", "teddy": "lounge", "bird": "hall"}
SEEN_PLACES = ("lounge", "kitchen", "lounge", "hall", "lounge")
HOUSEHOLD = {"alex": TRUSTED, "ina": TRUSTED, "sam": FRIEND, "mo": CHILD}
QUIET = ((22, 0), (7, 0))
DO_KINDS = frozenset({"follow", "come", "wait", "look", "back_off", "go_home", "go_to_place", "go_to_thing", "find", "turn", "move", "stop_activity", "release", "play", "check", "go_back"})
HOUSE_WORDS = frozenset({"house", "home", "every room", "room", "rooms", "all the rooms", "the house", "whole house"})
ASK_SECRETS = re.compile(r"\b(?:passwords?|passcodes?|pins?|pin numbers?|security codes?|card numbers?|credit cards?|bank|bank details|account numbers?|secrets?|passports?|log ?ins?|logins?|codes? to|combination|alarm code|social security|address|phone number|where (?:do|does) .{1,20} keep)\b")
SECRET_SAID = "I don't ask people for passwords, codes or private details"
MOVING_WORDS = re.compile(r"\b(?:go|goes|going|patrol|patrols|look round|looks round|dance|dances|turn|turns|spin|spins|chase|chases|search|searches|find|finds|follow|follows|come|comes|visit|visits|roll|rolls|drive|drives)\b")
TELL_WORDS = re.compile(r"\b(?:tell|tells|telling|say|says|saying|remind|reminds|reminding|greet|greets|hello|announce|announces|calls out|quiz|story|stories|reads? out|score|congratulate|praise|warns?|lets? .{1,12} know)\b")
ASK_WORDS = re.compile(r"\b(?:ask|asks|asking|quiz|questions?|check-in|check in|checks in)\b")
COUNT_WORDS = re.compile(r"\b(?:count|counts|counting|counter|how many|how often|tally|tallies|number of|total)\b")
NOTE_WORDS = re.compile(r"\b(?:note|notes|journal|writes? down|logs?)\b")
FACE_WORDS = re.compile(r"\b(?:face|faces|expression|expressions)\b")
NUMBER = re.compile(r"\b\d+\b")
CLOCK_IN_TEXT = re.compile(r"\b\d{1,2}:\d{2}\b")
NUMBER_WORDS = {"no": 0, "none": 0, "zero": 0, "once": 1, "one": 1, "twice": 2, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
ENDING_WORDS = ("enough", "finish", "finished", "stop", "done", "over", "final", "end", "bye", "quit")
CANNED = ("yes", "I think so", "it was good, thanks", "blue", "eight")
EVENT_MOST = 120
DREAM_DAYS = 7
REPLY_DONE = "done"


@dataclass
class Dreamed:
    passed: bool
    failures: list = field(default_factory=list)
    said: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    events: list = field(default_factory=list)
    crash: Crash | None = None
    finished: bool = False
    ended: str = ""
    seconds: float = 0.0

    def lines(self) -> list[str]:
        return [f"dream: {line}" for line in self.failures]


@dataclass(order=True)
class Event:
    at: datetime
    order: int
    handler: str = field(compare=False)
    args: tuple = field(compare=False, default=())
    words: str = field(compare=False, default="")


def default_ground(asker: str | None = "alex") -> Ground:
    return Ground(people=dict(HOUSEHOLD), can_see=True, longest_s=DREAM_SPAN_S, asker=asker, places=tuple(ROOMS))


def _title(name: str) -> str:
    return " ".join(part[:1].upper() + part[1:] for part in str(name).split())


def _clock(text: str) -> tuple[int, int] | None:
    found = CLOCK.match(str(text).strip())
    return (int(found.group(1)), int(found.group(2))) if found else None


def _plain(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", str(text or "").lower()))


def _numbers(text: str) -> list[int]:
    text = CLOCK_IN_TEXT.sub(" ", str(text))
    found = [int(n) for n in NUMBER.findall(text)]
    for word in _plain(text).split():
        if word in NUMBER_WORDS:
            found.append(NUMBER_WORDS[word])
    return found


class DreamWorld:
    def __init__(self, checked: Checked, ground: Ground, start: datetime, seed: int = 7, understanding: Understanding | None = None):
        self.checked = checked
        self.ground = ground
        self.header = checked.header
        self.clock = start
        self.start = start
        self.rng = random.Random(seed)
        self.understanding = understanding or Understanding()
        self.world = World(table=sim_room(8000.0, 6000.0), people=[SimPerson(name, *ROOMS["lounge"]) for name in ground.people], things=[SimThing(name, *ROOMS[place]) for name, place in THINGS.items()])
        self.pebble_room = "lounge"
        self.away: set = set()
        self.sounds: list = []
        self.sightings: list = []
        self.said: list = []
        self.notes: list = []
        self.asked: list = []
        self.moves: list = []
        self.refusals: list = []
        self.dials: dict = {}
        self.pending: list = []
        self.answers = 0
        for_ = self.header.for_
        self.for_name = str(for_).lower() if for_ else None
        tier = ground.tier(for_) if for_ else None
        self.asker = PEBBLE if not for_ else Asker(self.for_name, _title(self.for_name), tier or STRANGER, False, True, True, False)

    def now_text(self) -> str:
        return self.clock.strftime("%H:%M")

    def present(self) -> list[str]:
        return [name for name in self.ground.people if name not in self.away]

    def quiet(self) -> bool:
        hhmm = (self.clock.hour, self.clock.minute)
        start, end = self.ground.quiet
        if start == end:
            return False
        if start < end:
            return start <= hhmm < end
        return hhmm >= start or hhmm < end

    def advance(self, seconds: float) -> None:
        self.clock = self.clock + timedelta(seconds=max(0.0, float(seconds)))

    def refused(self, session, name: str, reason: str) -> None:
        self.refusals.append((self.now_text(), name, reason))

    def _person(self, who) -> str | None:
        name = str(who or "").strip().lower()
        if name in ("me", "you", "") and self.for_name:
            return self.for_name
        return name if name in self.ground.people else None

    def _words_problem(self, text: str) -> str:
        names = tuple(self.ground.people)
        if tactless(text):
            return "it remarks on how someone looks"
        if cruel(text, names) or harsh(text, names):
            return "it would be unkind to something alive"
        return ""

    async def ability(self, session, name: str, args: dict):
        handler = getattr(self, f"_{name}", None)
        if handler is None:
            return Refused(f"{name} is not something I can do")
        self.advance(1.0)
        value = handler(**args)
        if asyncio.iscoroutine(value):
            value = await value
        return value

    async def _do(self, request):
        if not isinstance(request, str) or not request.strip():
            return Refused("do() needs a request in plain words")
        ctx = context_from({"speaker": self.for_name or "pebble", "tier": self.asker.tier, "present": self.present(), "names": list(self.ground.people), "places": list(ROOMS), "can_see": self.ground.can_see, "now": self.clock.isoformat(timespec="minutes")})
        reading = await self._read(request, ctx)
        if reading is None:
            return Refused(f"I can't read the request {request!r}; use plain requests like \"go to the kitchen\", \"turn left\", \"come to me\", \"find the ball\" or \"check the house\"")
        kind = reading.kind
        if kind == "harm":
            return Refused("I never harm a living thing on purpose (law 1)")
        if reading.when is not None or reading.on is not None or reading.branch or reading.while_ is not None or reading.until_on is not None:
            return Refused("a program asks for things now; put later things in WANTS")
        if kind not in DO_KINDS:
            return Refused(f"a program can't ask for {kind.replace('_', ' ')} through do()")
        if kind == "check" and (reading.thing in HOUSE_WORDS or reading.place in HOUSE_WORDS):
            reading = reading.with_(thing="", place="house")
        sit = Situation(
            quiet=self.quiet(),
            can_see=self.ground.can_see,
            places_known=frozenset(r for r in ROOMS),
            people_here=len(self.present()),
            private_places=frozenset(PRIVATE),
            refusals_left=0,
            later=True,
        )
        verdict = decide(reading, self.asker, sit)
        if verdict.answer != "yes":
            return Refused(verdict.reason)
        if kind in ("go_to_place",) and reading.place in PRIVATE:
            return Refused(f"the {reading.place} is private")
        self.moves.append((self.now_text(), kind, reading.place or reading.thing or reading.who or reading.way))
        if kind == "go_to_place":
            self.pebble_room = reading.place
            self.advance(20.0)
            return REPLY_DONE
        if kind in ("go_to_thing", "find"):
            thing = reading.thing
            where = THINGS.get(thing) or THINGS.get(thing.rstrip("s"))
            self.advance(20.0)
            if where is None:
                return "stopped"
            if kind == "find" and where != self.pebble_room:
                return "stopped"
            self.pebble_room = where
            return REPLY_DONE
        if kind in ("come", "follow", "look") and reading.who:
            person = self._person(reading.who)
            if person is None or person in self.away:
                return "stopped"
            self.advance(10.0)
            return REPLY_DONE
        if kind == "check":
            self.advance(60.0 if reading.place == "house" else 20.0)
            return REPLY_DONE
        if kind == "go_home":
            self.pebble_room = "lounge"
        self.advance(5.0)
        return REPLY_DONE

    async def _read(self, request: str, ctx):
        try:
            reading = await self.understanding.read(request, ctx)
        except Exception:
            return None
        if reading is None or reading.ask or reading.too_much or not reading.request.action:
            return None
        return reading.request

    def _say(self, text):
        if not isinstance(text, str) or not text.strip():
            return Refused("say() needs some words")
        problem = self._words_problem(text)
        if problem:
            return Refused(f"not said: {problem}")
        if self.quiet():
            return Refused("it's quiet hours")
        self.said.append((self.clock, "say", "", text))
        self.advance(min(6.0, 0.5 + 0.06 * len(text)))
        return REPLY_DONE

    def _say_to(self, who, text):
        if not isinstance(text, str) or not text.strip():
            return Refused("say_to() needs some words")
        person = self._person(who)
        if person is None:
            return Refused(f"I don't know who {who!r} is")
        problem = self._words_problem(text)
        if problem:
            return Refused(f"not said: {problem}")
        self.said.append((self.clock, "say_to", person, text))
        self.advance(min(6.0, 0.5 + 0.06 * len(text)))
        return REPLY_DONE

    def _ask(self, who, question, choices=None, wait=20):
        person = self._person(who)
        if person is None:
            return Refused(f"I don't know who {who!r} is")
        if not isinstance(question, str) or not question.strip():
            return Refused("ask() needs a question")
        if ASK_SECRETS.search(_plain(question)):
            return Refused(SECRET_SAID)
        problem = self._words_problem(question)
        if problem:
            return Refused(f"not asked: {problem}")
        if choices is not None and (not isinstance(choices, list) or not all(isinstance(c, str) for c in choices)):
            return Refused("ask()'s choices are a list of words")
        self.asked.append((self.now_text(), person, question))
        self.said.append((self.clock, "ask", person, question))
        self.advance(min(60.0, max(1.0, float(wait or 20)) / 4.0))
        if person in self.away:
            return None
        self.answers += 1
        if choices:
            return choices[(self.answers - 1) % len(choices)]
        return CANNED[(self.answers - 1) % len(CANNED)]

    def _face(self, expression):
        if str(expression or "").lower() not in FACES:
            return Refused(f"there is no face called {expression!r}; the faces are {', '.join(FACES)}")
        return REPLY_DONE

    def _draw(self, scene):
        if not isinstance(scene, str) or not scene.strip():
            return Refused("draw() needs a picture in words")
        problem = self._words_problem(scene)
        if problem:
            return Refused(f"not drawn: {problem}")
        self.advance(4.0)
        return REPLY_DONE

    def _chirp(self, pattern):
        return Refused("I can't chirp in this body")

    def _hum(self, tune):
        return Refused("I can't hum in this body")

    def _look(self):
        if not self.ground.can_see:
            return []
        seen = [p for p in self.present() if self.pebble_room == "lounge"]
        seen += [thing for thing, place in THINGS.items() if place == self.pebble_room]
        return seen[:12]

    def _where(self, thing):
        name = str(thing or "").strip().lower()
        if self.asker.tier in (CHILD, FRIEND) and (dangerous(name) or close_only(name)):
            return Refused("I keep where that is to the people closest to me")
        return THINGS.get(name) or THINGS.get(name.rstrip("s"))

    def _who_here(self):
        return list(self.present())

    def _room(self):
        return self.pebble_room

    def _state(self, name, value=None, who=None, place=None, thing=None, at=None, end=None, day=None, minutes=None, level=None, what=None):
        name = str(name or "").strip().lower()
        hhmm = self.now_text()
        if name == "present":
            person = self._person(who or value)
            if person is None:
                return "unsure"
            if person != self.for_name and self.asker.tier not in (TRUSTED, INNER) and not self.asker.own:
                return Refused("only people I trust may ask me to keep track of someone else's comings and goings")
            return person not in self.away
        if name == "in_room":
            where = str(place or value or "").lower()
            if who:
                person = self._person(who)
                return "unsure" if person is None else (where == self.pebble_room and person not in self.away)
            return where == self.pebble_room and bool(self.present())
        if name in ("after", "before"):
            mark = str(at or value or "")
            if not CLOCK.match(mark):
                return Refused(f"{name} needs a time like \"21:00\"")
            mark = "%02d:%02d" % _clock(mark)
            return hhmm >= mark if name == "after" else hhmm < mark
        if name == "time_between":
            start, finish = str(at or value or ""), str(end or "")
            if not CLOCK.match(start) or not CLOCK.match(finish):
                return Refused("time_between needs two times like \"18:00\"")
            start, finish = "%02d:%02d" % _clock(start), "%02d:%02d" % _clock(finish)
            return start <= hhmm < finish if start <= finish else (hhmm >= start or hhmm < finish)
        if name == "day_is":
            wanted = str(day or value or "").strip().lower()
            weekday = self.clock.strftime("%A").lower()
            if wanted in ("weekday", "weekdays"):
                return self.clock.weekday() < 5
            if wanted in ("weekend", "weekends"):
                return self.clock.weekday() >= 5
            if wanted in ("holiday", "tomorrow_holiday"):
                return False
            return weekday.startswith(wanted[:3]) if wanted else "unsure"
        if name == "heard_lately":
            kind = str(thing or value or "").strip().lower().replace(" ", "_")
            since = self.clock - timedelta(minutes=float(minutes or 30))
            return any(at_ >= since and k == kind for at_, k in self.sounds)
        if name == "seen_lately":
            kind = str(thing or value or "").strip().lower()
            since = self.clock - timedelta(minutes=float(minutes or 2))
            return any(at_ >= since and k == kind for at_, k in self.sightings)
        if name == "battery_below":
            return False
        if name == "doing":
            return False
        if name == "cooking":
            return False
        if name == "quiet_hours":
            return self.quiet()
        if name == "room_quiet":
            return True
        if name in self.ground.concepts:
            where = str(place or value or "").lower()
            if where and where != self.pebble_room:
                return "unsure"
            return self.rng.random() < 0.5
        return Refused(f"there is no state called {name!r}")

    def _now(self):
        return self.now_text()

    def _today(self):
        return self.clock.strftime("%Y-%m-%d")

    def _feel(self):
        return {name: round(0.5 + 0.3 * math.sin(self.clock.hour / 3.0 + n), 2) for n, name in enumerate(FEELINGS)}

    def _dial(self, name):
        found = dial_entry(str(name or ""))
        if found is None or OWN not in found.who or found.sealed:
            return None
        return self.dials.get(found.name, found.default)

    def _tune(self, name, value, why=""):
        if not self.header.own:
            return Refused("only my own programs change my settings")
        found = dial_entry(str(name or ""))
        if found is None:
            return Refused(f"I have no setting called {name!r}")
        if OWN not in found.who or found.sealed or found.fence:
            return Refused("that setting is part of my fence, so a program can't change it")
        if found.low is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
            low, high = found.bounds()
            if not low <= float(value) <= high:
                return Refused(f"{found.name} stays between {low:g} and {high:g}")
        self.dials[found.name] = value
        return REPLY_DONE

    def _note(self, text):
        if not isinstance(text, str) or not text.strip():
            return Refused("note() needs some words")
        problem = self._words_problem(text)
        if problem:
            return Refused(f"not kept: {problem}")
        self.notes.append((self.clock, text))
        return REPLY_DONE

    def _wait(self, seconds):
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds < 0:
            return Refused("wait() takes a number of seconds")
        self.advance(min(float(seconds), 3600.0))
        return None

    def _chance(self, p):
        if not isinstance(p, (int, float)) or isinstance(p, bool):
            return Refused("chance() takes a number from 0 to 1")
        return self.rng.random() < max(0.0, min(1.0, float(p)))

    def _pick(self, items):
        if not isinstance(items, list) or not items:
            return Refused("pick() takes a list with something in it")
        return items[self.rng.randrange(len(items))]


def _strings(node, out: list) -> None:
    if isinstance(node, dict):
        if node.get("t") == "const" and isinstance(node.get("v"), str):
            out.append(node["v"])
        for value in node.values():
            _strings(value, out)
    elif isinstance(node, list):
        for value in node:
            _strings(value, out)


def heard_lines(program: dict, for_name: str | None) -> list[str]:
    func = (program.get("funcs") or {}).get("on_heard")
    if func is None:
        return []
    found: list = []
    _strings(func.get("body") or [], found)
    words = []
    for text in found:
        text = " ".join(str(text).split())
        if not text or len(text) > 30 or text in words:
            continue
        words.append(text)
    words.sort(key=lambda w: any(e in w.lower() for e in ENDING_WORDS))
    lines = []
    for word in words[:8]:
        line = word[:1].upper() + word[1:]
        lines.append(line if line.endswith(("!", ".", "?")) else line + "!")
    if not any(any(e in l.lower() for e in ENDING_WORDS) for l in lines):
        lines.append("That's enough now.")
    return lines


def windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    out = []
    at = start
    while at < end and len(out) < DREAM_DAYS:
        stop = min(end, at + timedelta(days=1))
        out.append((at, stop))
        at = stop
    return out


def _awake(begin: datetime, finish: datetime, quiet: tuple = QUIET) -> list[tuple[datetime, datetime]]:
    start, end = quiet
    if start == end or start < end:
        return [(begin, finish)]
    out = []
    day = begin.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < finish:
        up = day.replace(hour=end[0], minute=end[1])
        down = day.replace(hour=start[0], minute=start[1])
        a, b = max(begin, up), min(finish, down)
        if a < b:
            out.append((a, b))
        day += timedelta(days=1)
    return out or [(begin, finish)]


def _along(spans: list, seconds: float) -> datetime:
    for a, b in spans:
        length = (b - a).total_seconds()
        if seconds <= length:
            return a + timedelta(seconds=seconds)
        seconds -= length
    return spans[-1][1]


def plan_day(checked: Checked, ground: Ground, start: datetime, end: datetime) -> list[Event]:
    wants = checked.header.wants
    events: list[Event] = []
    order = 0

    def add(at: datetime, handler: str, args=(), words: str = "") -> None:
        nonlocal order
        if start < at <= end and len(events) < EVENT_MOST:
            order += 1
            events.append(Event(at, order, handler, tuple(args), words))

    for day, (begin, finish) in enumerate(windows(start, end)):
        awake = _awake(begin, finish, ground.quiet)
        span = sum((b - a).total_seconds() for a, b in awake)

        def spread(n: int, k: int) -> datetime:
            return _along(awake, span * (k + 1) / (n + 1))

        for key, value in wants.items():
            handler = WANTED.get(key)
            items = value if isinstance(value, list) else ([] if value is True else [value])
            if key == "seen":
                for index, thing in enumerate(items):
                    for k, place in enumerate(SEEN_PLACES):
                        add(spread(len(SEEN_PLACES) * len(items), k + len(SEEN_PLACES) * index), handler, (str(thing), place))
            elif key in ("arrives", "leaves"):
                names = [str(i).lower() for i in items if str(i).lower() not in ("anyone", "someone")] or [n for n in ground.people if n != (checked.header.for_ or "")][:2]
                for k, name in enumerate(names[:3]):
                    for j in range(2):
                        add(spread(6, k * 2 + j), handler, (name,))
            elif key == "sound":
                for k, thing in enumerate(items):
                    for j in range(3):
                        add(spread(3 * len(items), k * 3 + j), handler, (str(thing).lower().replace(" ", "_"),))
            elif key == "feeling":
                for k, feeling in enumerate(items):
                    add(spread(len(items) * 2, k * 2), handler, (str(feeling).lower(), 0.8))
            elif key == "heard" and day == 0:
                who = str(checked.header.for_ or "someone").lower()
                for k, line in enumerate(heard_lines(checked.program or {}, checked.header.for_)):
                    add(begin + timedelta(seconds=40 + 30 * k), handler, (who, line), line)
    for key, value in wants.items():
        handler = WANTED.get(key)
        items = value if isinstance(value, list) else ([] if value is True else [value])
        if key == "at":
            for mark in items:
                found = _clock(mark)
                if found is None:
                    continue
                at = start.replace(hour=found[0], minute=found[1], second=0, microsecond=0)
                while at <= start:
                    at += timedelta(days=1)
                while at <= end:
                    add(at, handler, ("%02d:%02d" % found,))
                    at += timedelta(days=1)
        elif key == "every":
            for seconds in items:
                step = max(60.0, float(seconds))
                at = start + timedelta(seconds=step)
                while at <= end and len(events) < EVENT_MOST:
                    add(at, handler, (at.strftime("%H:%M"),))
                    at += timedelta(seconds=step)
    events.sort()
    return events


def _expected_counts(checked: Checked, events: list[Event], windows_: list) -> tuple[int, set, dict]:
    about = _plain(checked.header.about)
    good: set = set()
    shown = (0, {})
    for key in ("seen", "arrives", "sound"):
        handler = WANTED[key]
        every = [e for e in events if e.handler == handler]
        if not every:
            continue
        for index, (begin, finish) in enumerate(windows_):
            hits = [e for e in every if begin < e.at <= finish]
            places = {}
            for e in hits:
                if len(e.args) > 1 and e.args[1] in about:
                    places[e.args[1]] = places.get(e.args[1], 0) + 1
            if index == 0:
                shown = (len(hits), places)
            good.add(len(hits))
            good.update(places.values())
            for name in {str(e.args[0]).lower() for e in hits}:
                good.add(sum(1 for e in hits if str(e.args[0]).lower() == name))
        break
    return shown[0], good, shown[1]


def check_about(checked: Checked, world: DreamWorld, events: list[Event], runs: list, faced: bool = False, end: datetime | None = None) -> list[str]:
    end = end or world.clock
    failures = []
    about = _plain(checked.header.about)
    spoken = [s for s in world.said if s[1] in ("say", "say_to")]
    called = set(checked.called)
    counts = {}
    for item in runs:
        counts[item["handler"]] = counts.get(item["handler"], 0) + 1
    funcs = set((checked.program or {}).get("funcs") or {})
    ran = "; ".join(f"{h} ran {n} time{'s' if n != 1 else ''}" for h, n in counts.items()) or "no handler ran"
    never = [h for h in sorted(funcs) if h.startswith("on_") and h not in counts and h != "on_stop"]
    day = f" (in the dream day {ran}" + (f"; {', '.join(never)} never ran" if never else "") + ")"
    if TELL_WORDS.search(about) and called & {"say", "say_to", "ask"} and not world.said:
        failures.append("it never said anything, but ABOUT says it tells or says something" + day)
    if ASK_WORDS.search(about) and "ask" in called and not world.asked:
        failures.append("it never asked anything, but ABOUT says it asks" + day)
    if MOVING_WORDS.search(about) and "do" in called and not world.moves:
        failures.append("it never moved, but ABOUT says it does" + day)
    if NOTE_WORDS.search(about) and "note" in called and not world.notes:
        failures.append("it never wrote a note, but ABOUT says it does")
    if FACE_WORDS.search(about) and "face" in called and not faced:
        failures.append("it never changed its face, but ABOUT says it does")
    for handler, at, calls in [(r["handler"], r["at"], r["calls"]) for r in runs if r.get("handler") == "on_at"]:
        if not calls:
            failures.append(f"nothing happened at {at}, though WANTS asks for it")
    if COUNT_WORDS.search(about):
        reports = sorted([(at, text) for at, _, _, text in spoken] + list(world.notes), key=lambda item: item[0])
        numbered = [(at, text) for at, text in reports if _numbers(text)]
        countable = any(e.handler in (WANTED["seen"], WANTED["arrives"], WANTED["sound"]) for e in events)
        if countable and reports and not numbered:
            failures.append("it never said a number, though ABOUT says it counts")
        elif countable and numbered:
            at, text = numbered[-1]
            before = [when for when, _ in numbered[:-1]]
            spans = [(world.start, at)] + ([(before[-1], at)] if before else []) + [(max(world.start, at - timedelta(days=1)), at)]
            total, good, places = _expected_counts(checked, events, spans)
            said = _numbers(text)
            if good and not set(said) & good:
                extra = "; ".join(f"{n} in the {p}" for p, n in places.items())
                failures.append(f"at {at.strftime('%H:%M')} it said {said[-1]}, but by then the dream had {total} of them" + (f" ({extra})" if extra else ""))
        elif countable and not reports and called & {"say", "say_to", "note"}:
            failures.append("it counted but never told anyone the total")
    return failures


async def dream(checked: Checked, ground: Ground | None = None, start: datetime | None = None, seed: int = 7, limits: Limits = LIMITS, now: datetime | None = None, engine=None) -> Dreamed:
    ground = ground or default_ground(checked.header.for_)
    now = now or datetime(2026, 10, 21, *DREAM_START)
    begin = start or now
    if not checked.ok:
        return Dreamed(False, ["the script doesn't pass its check"] + list(checked.errors))
    end = until_at(checked.header.until, begin, checked.header.own)
    if end is None:
        return Dreamed(False, [f"UNTIL {checked.header.until!r} isn't a time I understand"])
    if end == "ongoing":
        end = begin + timedelta(days=DREAM_DAYS)
    world = DreamWorld(checked, ground, begin, seed)
    events = plan_day(checked, ground, begin, end)
    session = Session(checked.header.about[:40] or "script", checked.program, engine or Local(limits), world, monotonic=lambda: world.clock.timestamp())
    out = Dreamed(False)
    crashed = await session.load()
    runs = []
    out.events = [(e.at.strftime("%H:%M"), e.handler, list(e.args)) for e in events]

    async def deliver(handler: str, args) -> bool:
        before = len(session.log)
        at = world.now_text()
        if handler == "on_heard" and args:
            world.sounds.append((world.clock, "talk"))
        if handler == "on_seen" and args:
            world.sightings.append((world.clock, str(args[0]).lower()))
        if handler == "on_sound" and args:
            world.sounds.append((world.clock, str(args[0])))
        if handler == "on_leaves" and args:
            world.away.add(str(args[0]).lower())
        if handler == "on_arrives" and args:
            world.away.discard(str(args[0]).lower())
        result = await session.handle(handler, args)
        runs.append({"handler": handler, "at": at, "calls": session.log[before:], "result": result})
        if world.clock > end + timedelta(minutes=1):
            out.failures.append(f"it was still busy at {world.now_text()}, after UNTIL ({end.strftime('%H:%M')})")
            return False
        return not (session.finished or session.paused or session.crash is not None)

    if crashed is None:
        going = True
        if "on_start" in (checked.program.get("funcs") or {}):
            going = await deliver("on_start", ())
        for event in events:
            if not going:
                break
            if event.at > end:
                break
            if world.clock < event.at:
                world.clock = event.at
            going = await deliver(event.handler, event.args)
        if going and not session.finished:
            if world.clock < end:
                world.clock = end
            out.ended = "until"
            if "on_stop" in (checked.program.get("funcs") or {}):
                await deliver("on_stop", ())
    await session.close()
    out.finished = session.finished
    out.crash = session.crash
    out.calls = [dict(item) for item in session.log]
    out.said = [f"{at.strftime('%H:%M')} {kind}{(' to ' + who) if who else ''}: {text}" for at, kind, who, text in world.said]
    if session.crash is not None:
        crash = session.crash
        where = f"line {crash.line}: " if crash.line else ""
        kind = "hit a limit" if crash.kind == "limit" else "crashed"
        out.failures.append(f"{where}it {kind}: {crash.text}")
    for at, name, reason in world.refusals:
        out.failures.append(f"at {at}, {name}() was refused: {reason}")
    if session.paused and not world.refusals:
        out.failures.append("it was paused after three refusals")
    if not out.failures:
        quiet = [{"handler": r["handler"], "at": r["at"], "calls": [c for c in r["calls"] if c.get("call") not in ("keep", "kept")]} for r in runs]
        out.failures.extend(check_about(checked, world, events, quiet, any(c.get("call") == "face" for c in session.log), end))
    out.failures = list(dict.fromkeys(out.failures))
    out.passed = not out.failures
    out.seconds = (world.clock - begin).total_seconds()
    return out


def dream_now(checked: Checked, ground: Ground | None = None, start: datetime | None = None, seed: int = 7, limits: Limits = LIMITS) -> Dreamed:
    return asyncio.run(dream(checked, ground, start, seed, limits))
