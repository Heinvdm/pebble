import asyncio
import json
import logging
import math
import re
import time
from dataclasses import dataclass, field

from ..activities.gate import PEBBLE, Asker, Verdict, decide
from ..activities.skills import plain as plain_words
from ..activities.trying import answer_of, changed
from ..clock import iso
from ..life.events import SOUND_WORDS, match, sound_kind
from ..nav.life import remember_careful
from ..people.trust import CHILD, FRIEND, INNER, STRANGER, TRUSTED
from ..activities.commands import PRIVATE_NAMES
from ..privacy.rooms import ALWAYS
from ..script.voice import loopy
from ..understand.request import BadRequest, Request, trigger_from
from ..understand.rules import harmed
from .book import Entry, HowTo, pattern_of, shown_name
from .concepts import ALIVE_NO, Concepts, names_alive
from .copy import Mimic
from .induce import Inducer, Made, answer_question, made_from, plain_made, readback, said_steps, values_seen
from .record import Record, is_move, join, nouns, request_of, step_of
from .replay import Drive, Player, Route, holes, length
from .words import Said, bare, clean, name_from
from .words import read as read_words

log = logging.getLogger(__name__)

IDLE_S = 120.0
LONGEST_S = 1800.0
WORDS_KEEP_S = 1800.0
ANSWER_S = 20.0
QUESTION_S = 30.0
NAME_S = 30.0
WINDOW_S = 30.0
OFFER_S = 30.0
PUT_DOWN_S = 120.0
TRAIL_EVERY_S = 0.5
WONDER_EVERY_S = 60.0
HABIT_GAP_S = 60.0
LOOK_EVERY_S = 10.0
LOOKED_KEEP_S = 60.0
COPY_S = 45.0
TEACHERS = frozenset({FRIEND, TRUSTED, INNER, CHILD})
CLOSE = frozenset({TRUSTED, INNER})
MOVING = frozenset({"turn", "move", "wiggle", "back_off", "go_to_place", "go_to_thing", "come", "find", "push", "request", "route", "spot"})
SAID_EVENTS = {
    "come home": "arrives", "get home": "arrives", "come in": "arrives", "get back": "arrives", "come back": "arrives", "arrive": "arrives",
    "walk in": "arrives", "come back home": "arrives", "get in": "arrives", "leave": "leaves", "go out": "leaves", "head out": "leaves",
}
CLAUSES = re.compile(r"(?:,\s*(?:and\s+)?then\s+|\s+and\s+then\s+|\s+then\s+|\.\s+|;\s*|,\s*and\s+(?=go|come|look|turn|spin|say|tell|wait|find|check|back|make|wiggle|nod|roll)|,\s+(?=go|come|look|turn|spin|say|tell|wait|find|check|back|make|wiggle|nod|roll))")
COME_GET = re.compile(r"\bcome (?:and )?(?:get|fetch|find) (?:me|us)\b", re.I)
LEAD_IN = re.compile(r"^(?:you |first |and |then |just |finally |after that )+")
ARRIVES = re.compile(r"^(?P<who>[a-z]+) (?:comes home|gets home|comes in|gets back|arrives|walks in)$")
LEAVES = re.compile(r"^(?P<who>[a-z]+) (?:goes out|leaves|heads out)$")
SEES = re.compile(r"^(?:you see|i see|the) (?:the |a )?(?P<thing>[a-z ]+?)(?: comes in| comes| appears| is here)?$")
CONCEPT_IF = re.compile(r"^(?:if|when|whenever) (?:the )?(?P<place>[a-z ]+?) (?:is|looks|gets) (?P<what>[a-z' ]+?),? (?P<then>.+)$")
CONCEPT_TELL = re.compile(r"^(?:tell me|let me know|come and tell me|come tell me) (?:if|when|whether) (?:the )?(?P<place>[a-z ]+?) (?:is|looks|gets) (?P<what>[a-z' ]+)$")
CONCEPT_ASK = re.compile(r"^(?:is|does) (?:this|that|it|the (?P<place>[a-z ]+?)) (?:look )?(?P<what>[a-z' ]+)$")
YES = re.compile(r"^(?:yes|yeah|yep|yup|ja|it is|that is right|correct|right|exactly|sure is|it sure is|definitely)\b")
NO = re.compile(r"^(?:no|nope|nah|it is not|not really|not at all|wrong)\b")

START_OK = ("Okay, show me!", "Ooh, okay. Show me!", "Okay, I'm watching.")
STRANGER_NO = "I'd rather learn from people I know."
BUSY = "I'm learning something from {name} just now."
UNDONE = "Okay, I've left that last bit out."
NOTHING_TO_UNDO = "There's nothing to take back yet."
AGAIN_OK = "Okay, from the top."
NOTHING_SHOWN = "You haven't shown me anything yet, so there's nothing to keep."
LIKE_THIS = "Like this?"
ROUTE_CHECK = "I'll go back the way we came, to check I've got it."
ROUTE_ASK = "Did I get the way right?"
ASK_NAME = "What should I call it?"
HOLD = "Let me think about how that works."
DRAFT = "I'll keep what you showed me as a draft for now."
SHOW_AGAIN = "Okay, show me again."
NAMED_FOR_NOW = "I'll call it the {name} for now."
CHILD_NO = "{name} taught me that one, so I'll keep doing it {name}'s way."
CLOSE_ONLY = "Only someone I know really well can teach me something that {why}."
WAY_OWN = "Only {name} can teach me what to do for {name}."
WAY_SENSE = "I can't tell when you {event} yet, so I can't learn that one."
FORGOT = "Okay, I've forgotten {what}."
FORGET_NO = "Only {name}, someone who knows me better, or my owner can make me forget that."
NOT_TAUGHT = "You haven't taught me anything yet."
KNOW_NOTHING = "Nobody has taught me anything yet."
LEAD_OK = "Okay, I'm right behind you. Tell me when we're there."
LEAD_PRIVATE = "That's a private room, so I won't learn a way into it."
LEAD_SHORT = "We didn't really go anywhere, so there's no way to keep."
CONCEPT_FIRST = "Okay, that's {name}."
CONCEPT_MORE = "Got it. I think I know what {name} looks like now."
CONCEPT_NOT = "Okay, that's not {name}."
CONCEPT_ASK_PLACE = "Is this {name}?"
CONCEPT_ASK_THING = "Is that the {name}?"
THANKS = "Thanks, that helps."
LOOKS_YES = "That looks {name} to me."
LOOKS_NO = "That doesn't look {name} to me."
LOOKS_UNSURE = "I'm not sure whether that's {name}."
THING_YES = "That's the {name}."
THING_NO = "I don't think that's the {name}."
ALIVE_NEVER = "I don't put that on people or animals."
COPY_START = "Okay! I'll copy you."
COPY_NOTHING = "I didn't see anything to copy yet."
WORD_EMPTY = "I'm not sure what to do when you say that."
EXPLAIN_EMPTY = "I couldn't work out the steps from that. Can you show me instead?"
GAME_HOLD = "Ooh, a game. Give me a minute to work out the rules."
SKIPPED = "Okay, I'll leave out the {what} this time."
NOT_FOUND = "I don't know how to do that yet."
NOTHING_TO_SKIP = "There's no {what} in that one."
CANT_DO = "I can't do that in this body."
SAID_FOR_NOW = "Okay."
PRIVATE_STEP = "The {room} is private, so I won't learn a way in there."
RAN_NO = "Okay. Show me again or tell me what to change, and I'll do it that way next time."
PART_ONLY = "I couldn't do all of it just now. "


@dataclass
class Session:
    teacher: Asker
    record: Record
    started_mono: float
    last: float
    name: str = ""
    kind: str = ""
    trigger: dict = field(default_factory=dict)
    adding: str = ""
    leading: dict | None = None
    sampled: float = -math.inf
    shown: int = 0


@dataclass
class Waiting:
    kind: str
    asker: Asker
    until: float
    entry: str = ""
    record: Record | None = None
    examples: list = field(default_factory=list)
    made: Made | None = None
    question: object | None = None
    steps: list = field(default_factory=list)
    data: dict = field(default_factory=dict)


@dataclass
class Making:
    record: Record
    teacher: Asker
    name: str
    examples: list
    kind: str = ""
    trigger: dict = field(default_factory=dict)
    adding: str = ""
    task: asyncio.Task | None = None
    made: Made | None = None
    question: object | None = None
    answered: bool = False
    yes: bool = False
    ended_at: float = 0.0
    replay_started: float | None = None
    said_hold: bool = False
    points: list = field(default_factory=list)
    rooms: list = field(default_factory=list)
    shown: list = field(default_factory=list)
    data: dict = field(default_factory=dict)


class Teaching:
    def __init__(self, life):
        self.life = life
        p = life.p
        self.p = p
        self.commands = life.commands
        self.clock = p.clock
        self.book = HowTo(p.store, p.clock, life._record, p.embedder)
        self.concepts = Concepts(self)
        self.player = Player(self)
        self.inducer = Inducer(self.commands.thinker, p.books.name, monotonic=self.clock.monotonic, sleep=self.commands.runner.kit.pace.sleep)
        self.session: Session | None = None
        self.waiting: Waiting | None = None
        self.making: Making | None = None
        self.drive: Drive | None = None
        self.mimic: Mimic | None = None
        self.copied: tuple | None = None
        self.offer: tuple | None = None
        self.put_down: tuple | None = None
        self.tasks: set = set()
        self.screen: dict = {"on": False, "steps": [], "pad": False}
        self.fired: dict = {}
        self.wondered = -math.inf
        self.runs: dict = {}
        self.turns = 0
        self.timings: list = []
        self.looked: dict = {}
        self.look_at = -math.inf
        self.looking: asyncio.Task | None = None

    @property
    def kit(self):
        return self.commands.runner.kit

    def record(self, kind: str, **data) -> None:
        self.commands.record(kind, **data)

    def mono(self) -> float:
        return self.kit.pace.now()

    def _spawn(self, coro, wait: bool = True) -> asyncio.Task | None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            coro.close()
            return None
        task = loop.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        if wait:
            self.commands.tasks.add(task)
            task.add_done_callback(self.commands.tasks.discard)
        return task

    async def speak(self, text: str) -> None:
        if text:
            await self.commands.speak(text, False)

    def say(self, text: str) -> None:
        if text:
            self._spawn(self.speak(text))

    def _line(self, lines: tuple) -> str:
        self.turns += 1
        return lines[self.turns % len(lines)]

    def card(self):
        return self.life._card()

    def room(self) -> str | None:
        try:
            return self.life.alive.rooms.where_am_i()
        except Exception:
            return None

    def _names(self) -> tuple:
        return tuple(n.lower() for person in self.life.company.book.people.values() for n in person.names + person.nicknames if n)

    def spoken(self, text: str) -> str:
        names = set(self._names())
        return " ".join(word.title() if word.strip(",.!?'s") in names else word for word in str(text).split(" "))

    def show(self) -> None:
        session = self.session
        steps = []
        if session is not None:
            steps = [self.spoken(said_steps([item.step])) for item in session.record.items][-6:]
            if session.record.trail:
                steps.append(f"the way, {length(session.record.trail):.1f} m so far")
            for example in session.record.examples[-3:]:
                steps.append(f"{'not ' if not example.get('yes', True) else ''}{example.get('name', '')}")
        self.screen = {"on": session is not None, "steps": steps, "pad": session is not None, "teacher": session.teacher.label if session is not None else ""}
        face = self.kit.face
        teach = getattr(face, "teach", None)
        if teach is not None:
            try:
                teach(self.screen["on"], steps, self.screen["pad"])
            except Exception:
                log.exception("could not show the learning mark")
        if session is not None:
            face.show("curious")

    def private(self, place: str) -> bool:
        return always_private(place)

    def busy(self) -> bool:
        return self.session is not None or self.making is not None or self.waiting is not None or self.player.busy()

    def who_may(self, asker: Asker) -> str:
        if asker.own:
            return "own"
        if asker.id is None or (asker.tier == STRANGER and not asker.owner):
            return ""
        if asker.owner or asker.tier in TEACHERS:
            return asker.tier if not asker.owner else INNER
        return ""

    def close(self, asker: Asker) -> bool:
        return asker.owner or asker.tier in CLOSE

    async def heard(self, heard) -> object | None:
        try:
            return await self._heard(heard)
        except Exception:
            log.exception("teaching could not take a heard line")
            self.record("error", where="teaching heard")
            return None

    async def _heard(self, heard):
        from ..understand.resolve import Reading

        text = (heard.text or "").strip()
        if not text:
            return None
        done = Reading(Request("chat"), source="rules", answered=True)
        if heard.stop is not None:
            self.player.stop()
            if self.mimic is not None:
                self.mimic.done = True
            return None
        asker = self.commands.asker_heard(heard)
        if asker.own:
            return None
        said = read_words(text, self.commands.name.lower())
        session = self.session
        waiting = self.waiting
        if waiting is not None and self.mono() <= waiting.until and not (session is not None and asker.id == session.teacher.id):
            handled = await self._answer(waiting, asker, text, said, heard)
            if handled:
                return done
        if session is not None:
            if asker.id != session.teacher.id:
                if said is not None and said.kind in ("start",):
                    await self.speak(BUSY.format(name=session.teacher.label))
                    return done
                return None
            session.record.heard(text)
            handled = await self._in_session(session, said, text, heard)
            return done if handled else None
        return done if await self._outside(said, asker, text, heard) else None

    async def _outside(self, said: Said | None, asker: Asker, text: str, heard) -> bool:
        offer = self.offer
        if offer is not None and self.mono() <= offer[3] and asker.id == offer[2]:
            answer = answer_of(text, self.commands.name.lower())
            if (said is not None and said.kind == "start") or (answer is not None and answer[0] == "yes"):
                self.offer = None
                await self.begin(asker, offer[0], offer[1], "try")
                return True
            if answer is not None and answer[0] in ("no", "end"):
                self.offer = None
                return False
        if said is None:
            handled = await self._concept_words(text, asker)
            if handled:
                return True
            return await self._entry_words(text, asker)
        kind = said.kind
        if kind == "start":
            await self.begin(asker, said.name, said.words, said.extra)
            return True
        if kind == "lead":
            await self.begin(asker, said.name, said.words, "lead", quiet=True)
            if self.session is not None and self.session.teacher.id == asker.id:
                await self.lead(self.session, said.name)
            return True
        if kind == "list":
            await self.speak(self.listing(asker, "taught" in clean(text)))
            return True
        if kind == "copy":
            await self.copy_me(asker)
            return True
        if kind == "keep" and self.copied is not None:
            await self.keep_copied(asker, said.name)
            return True
        if kind == "carry" and self.put_down is not None and self.mono() - self.put_down[0] <= PUT_DOWN_S:
            await self.spot(asker, said, None)
            return True
        if kind == "word":
            await self.word(asker, said)
            return True
        if kind == "habit":
            await self.habit(asker, said.words, said.extra, None)
            return True
        if kind == "way":
            if said.extra == "shown":
                await self.begin(asker, "", text, "way", trigger_words=said.name)
                return True
            await self.way(asker, said.name, said.words, None)
            return True
        if kind == "explain":
            await self.explain(asker, said.name, said.words, None)
            return True
        if kind == "carry_on":
            return await self.carry_on(asker, said.name)
        if kind == "skip":
            return await self.skip(asker, said.name, said.extra)
        if kind == "from_now":
            return await self.from_now(asker, said.name, said.extra)
        if kind == "show" and said.extra:
            if names_alive(said.extra, self._names()) or names_alive(said.name, self._names()):
                self.record("teach_refused", why="alive concept")
                await self.speak(ALIVE_NO)
                return True
            return False
        if kind == "show" and re.search(r"\blooks? like\b", clean(text)):
            await self.begin(asker, "", "", "")
            if self.session is not None:
                await self.show_concept(self.session, said)
            return True
        return await self._entry_words(text, asker)

    async def _entry_words(self, text: str, asker: Asker) -> bool:
        flat = bare(text, self.commands.name.lower())
        found = re.match(r"^(?:(?:can|could|would|will) you\s+)?(?:please\s+)?(?:forget|unlearn|you can forget|delete) (?:the |your |how to do the |how to do |how to |about the |what )?(?P<name>.+?)(?: means)?$", flat)
        if found:
            entry = self._named(found.group("name"))
            if entry is not None:
                await self.forget_entry(entry, asker)
                return True
            skill = self.life.skills.get(found.group("name")) or self.life.skills.find(found.group("name"))
            if skill is not None and (skill.taught_by or {}).get("id") is not None:
                await self.forget_skill(skill, asker)
                return True
            return False
        found = re.match(r"^(?:(?:can|could|would|will) you\s+)?(?:please\s+)?(?:show me|let me see|let us see) (?:the |your |how you do the |how you do your |how to )?(?P<name>.+)$", flat)
        if found:
            entry = self._named(found.group("name"))
            if entry is not None:
                await self.run_entry(entry, {}, asker, "heard", text)
                return True
        return False

    def _named(self, name: str) -> Entry | None:
        name = name_from(name)
        entry = self.book.get(name)
        if entry is not None:
            return entry
        for item in self.book.all():
            if name in item.forms() or name == shown_name(item):
                return self.book.get(item.name) or item
        return None

    async def begin(self, asker: Asker, name: str = "", words: str = "", how: str = "", trigger_words: str = "", quiet: bool = False) -> None:
        tier = self.who_may(asker)
        if not tier or tier == "own":
            self.record("teach_refused", why="stranger", tier=asker.tier)
            await self.speak(STRANGER_NO)
            return
        if self.session is not None and self.session.teacher.id != asker.id:
            await self.speak(BUSY.format(name=self.session.teacher.label))
            return
        now = self.clock.now()
        record = Record(asker.label, "owner" if asker.owner else asker.tier, now, intent=" ".join(str(words or "").split())[:120])
        session = Session(asker, record, self.mono(), self.mono(), name=name if how != "how" else name)
        if how == "way":
            event = SAID_EVENTS.get(trigger_words)
            if event is None:
                await self.speak(WAY_SENSE.format(event=trigger_words))
                return
            session.kind = "way"
            session.trigger = {"event": event, "who": "me"}
            session.name = session.name or f"{'greeting' if event == 'arrives' else 'goodbye'} for {asker.label.lower()}"
        if how == "try":
            session.name = name
            record.intent = words
        existing = self._named(session.name) if session.name else None
        if existing is not None and existing.kind in ("move", "procedure", "way", "habit", "route"):
            refused = self.overrides(existing, asker)
            if refused:
                await self.speak(refused)
                return
            session.adding = existing.name
        draft = None
        if how == "carry_on":
            draft = self.book.take_draft(asker.id, name)
        if draft is not None:
            session.name = draft.get("name") or session.name
            for step in draft.get("steps") or []:
                record.add(step, now, "draft")
            record.trail = [list(p) for p in draft.get("trail") or []]
            record.examples = [dict(e) for e in draft.get("examples") or []]
        self.session = session
        if self.waiting is not None and self.waiting.kind == "window":
            self.waiting = None
        self.record("teach_started", person=asker.id, tier=record.tier, named=bool(session.name), way=how or "start", resumed=draft is not None)
        self.commands.note(f"{asker.label} started teaching you something" + (f" ({session.name})" if session.name else ""), False)
        self.show()
        if not quiet:
            await self.speak(self._line(START_OK))

    def overrides(self, entry: Entry, asker: Asker) -> str:
        if asker.tier != CHILD or asker.owner:
            return ""
        if entry.teacher_tier in ("", CHILD) or entry.teacher_id == asker.id:
            return ""
        teacher = entry.taught_by.get("name") or "A grown-up"
        return CHILD_NO.format(name=teacher)

    async def _in_session(self, session: Session, said: Said | None, text: str, heard) -> bool:
        kind = said.kind if said is not None else ""
        if kind == "undo":
            removed = session.record.undo()
            self.show()
            await self.speak(UNDONE if removed is not None else NOTHING_TO_UNDO)
            return True
        if kind == "again":
            session.record.clear()
            session.leading = None
            self.show()
            await self.speak(AGAIN_OK)
            return True
        if kind == "end":
            if said.name:
                session.name = said.name
            await self.end(session)
            return True
        if kind == "start":
            await self.speak(self._line(START_OK))
            return True
        if kind == "lead":
            await self.lead(session, said.name)
            return True
        if kind == "carry":
            await self.spot(session.teacher, said, session)
            return True
        if kind == "show":
            await self.show_concept(session, said)
            return True
        if kind == "word":
            await self.word(session.teacher, said)
            return True
        if kind == "habit":
            await self.habit(session.teacher, said.words, said.extra, session)
            return True
        if kind == "way":
            event = SAID_EVENTS.get(said.name)
            if event is None:
                await self.speak(WAY_SENSE.format(event=said.name))
                return True
            session.kind, session.trigger = "way", {"event": event, "who": "me"}
            if said.extra != "shown":
                steps = await self._clauses(said.words, session.teacher)
                for step in steps:
                    session.record.add(step, self.clock.now(), "explained")
            await self.speak(self._line(START_OK))
            return True
        if kind == "explain":
            await self.explain(session.teacher, said.name, said.words, session)
            return True
        if kind == "copy":
            await self.copy_me(session.teacher)
            return True
        if kind == "keep" and self.copied is not None:
            for step in self.copied[0]:
                session.record.add(step, self.clock.now(), "copied")
            self.copied = None
            self.show()
            await self.speak(SAID_FOR_NOW)
            return True
        if self.commands.pending is not None and self.commands.pending.asker == session.teacher.id:
            return False
        reading = await self.commands.read_words(text, session.teacher, "understand")
        request = reading.request
        if not request.action or reading.ask or reading.too_much:
            return False
        private = next((step.place for step in request.steps() if always_private(step.place)), "")
        if private:
            self.record("teach_refused", why="private room", place=private)
            await self.speak(PRIVATE_STEP.format(room=private))
            return True
        if request.kind == "try_new" and not request.name:
            return False
        if request.kind == "say_to" and request.who in ("", "me") and request.when is None and request.on is None and request.text:
            problem = self.commands.words_problem(request.text)
            if problem:
                await self.speak("I won't say that.")
                return True
            self.did(request, session.teacher, "heard")
            await self.speak(request.text)
            return True
        await self.commands.act(request, session.teacher, "heard")
        return True

    def did(self, request: Request, asker: Asker, how: str) -> None:
        session = self.session
        if session is None or asker.id != session.teacher.id or how not in ("heard", "named"):
            return
        if request.kind in ("where_is", "what_is", "what_see", "sight_question", "where_am_i", "teach", "stop_activity", "release", "adjust", "try_new", "follow") or request.when is not None or request.on is not None:
            return
        if request.kind == "remember_spot":
            return
        if any(always_private(step.place) for step in request.steps()):
            return
        steps = []
        for step in [request.with_(then=())] + list(request.then):
            steps.append(step_of(step))
        for step in steps:
            session.record.add(step, self.clock.now(), "said")
        session.last = self.mono()
        session.shown += 1
        self.record("teach_step", person=asker.id, step=steps[0].get("do"), asked=request.kind)
        self.show()

    def pad(self, command: dict) -> None:
        self._spawn(self._pad(dict(command or {})))

    async def _pad(self, command: dict) -> None:
        session = self.session
        if session is None:
            self.record("pad_ignored", why="no lesson")
            return
        teacher = self.commands.fresh(session.teacher)
        kind = str(command.get("kind") or "")
        session.last = self.mono()
        if kind == "drive":
            forward = _unit(command.get("y"))
            turn = _unit(command.get("x"))
            drive = self.drive
            runner = self.commands.runner
            if drive is None or runner.current is not drive:
                if abs(forward) < 0.12 and abs(turn) < 0.12:
                    return
                verdict, _ = await self.commands.check_step(Request("move", way="forward"), teacher, True)
                if not verdict.yes:
                    self.record("pad_refused", reason=verdict.reason[:60])
                    if verdict.say:
                        await self.speak(verdict.say)
                    return
                drive = Drive(Request("move", way="forward"), teacher, None, False, lambda step: self._driven(step))
                self.drive = drive
                runner.start(drive)
            drive.push(forward, turn, self.mono())
            return
        if kind == "tilt":
            way = "up" if command.get("way") == "up" else "down"
            step = {"do": "tilt", "way": way, "degrees": 15}
            refused, _ = await self.commands.trying.gate(step, teacher)
            if refused is not None:
                return
            rest = self.kit.body.profile.tilt_rest
            await self.kit.body.tilt(rest + (15.0 if way == "up" else -15.0))
            self._driven(step)
            return
        if kind == "face":
            expression = str(command.get("expression") or "happy")
            step, problem = self.card().clean({"do": "face", "expression": expression})
            if problem or step is None:
                return
            self.kit.face.show(step["expression"])
            self._driven(step)
            return
        if kind == "stop":
            if self.drive is not None and self.commands.runner.current is self.drive:
                self.commands.runner.end("stopped", "the touch pad said stop")

    def _driven(self, step: dict) -> None:
        session = self.session
        if session is None:
            return
        session.record.add(step, self.clock.now(), "drive")
        session.last = self.mono()
        session.shown += 1
        self.show()

    async def lead(self, session: Session, to: str) -> None:
        place = name_from(to)
        privacy = getattr(self.life, "privacy", None)
        if privacy is not None and privacy.rooms.kind(place):
            self.record("teach_refused", why="private room", place=place)
            await self.speak(LEAD_PRIVATE)
            return
        verdict = await self.commands.act(Request("follow", who="me"), session.teacher, "taught")
        if not verdict.yes:
            return
        session.leading = {"to": place, "since": self.mono()}
        session.record.trail.clear()
        self._sample(session, force=True)
        if "lead" not in session.record.ways:
            session.record.ways.append("lead")
        session.name = session.name or place
        await self.speak(LEAD_OK)

    def _sample(self, session: Session, force: bool = False) -> None:
        odometer = self.life.odometer
        if odometer is None or not getattr(odometer, "local_usable", False):
            return
        now = self.mono()
        if not force and now - session.sampled < TRAIL_EVERY_S:
            return
        session.sampled = now
        x, y, _ = odometer.pose()
        room = None
        try:
            room = self.life.privacy.rooms.room_at(x, y)
        except Exception:
            room = None
        if session.record.walked(x, y, room, force):
            session.last = now
            self.show()

    async def spot(self, asker: Asker, said: Said, session: Session | None) -> None:
        if not self.who_may(asker) or self.who_may(asker) == "own":
            await self.speak(STRANGER_NO)
            return
        nav = self.life.nav
        name = said.name or "your spot"
        if not nav.remember_spot(name):
            await self.speak("I'm not sure where I am, so I can't remember this spot.")
            return
        about = f"where I {said.words}" if said.words and not said.words.startswith(("where", "the")) else said.words
        entry = Entry(name, "spot", aliases=[a for a in (said.words, f"where you {said.words}") if a][:3], about=about[:120], taught_by=self._teacher(asker), learned_at=iso(self.clock.now()), last_used=iso(self.clock.now()), link={"spot": name})
        x, y, _ = self.life.odometer.pose()
        entry.points = [[round(x, 2), round(y, 2), self.room() or ""]]
        if session is not None:
            session.record.add({"do": "spot", "spot": name}, self.clock.now(), "carried")
        self.book.put(entry)
        self.put_down = None
        self.record("howto_kept", name=name, shape="spot", tier=asker.tier)
        self.commands.note(f"{asker.label} showed you a spot and called it the {name}", False)
        await self.speak(readback(entry, self.spoken))

    def lifted(self, what: str) -> None:
        if what == "put_down":
            self.put_down = (self.mono(), self.life.odometer.pose() if self.life.odometer is not None else None)
            session = self.session
            if session is not None:
                session.last = self.mono()
                if "carry" not in session.record.ways:
                    session.record.ways.append("carry")

    async def show_concept(self, session: Session, said: Said) -> None:
        name = said.name
        if not name:
            return
        if names_alive(name, self._names()):
            self.record("teach_refused", why="alive concept")
            await self.speak(ALIVE_NO)
            return
        entry = self.concepts.find(name) or self.book.get(name)
        if entry is not None and entry.kind != "concept":
            entry = None
        if entry is not None:
            refused = self.overrides(entry, session.teacher)
            if refused:
                await self.speak(refused)
                return
        captured = await self.concepts.capture(name, said.words)
        if captured.problem:
            self.record("teach_refused", why="concept example", problem=captured.problem[:40])
            await self.speak(captured.problem)
            return
        looks = await self.concepts.describe()
        if entry is None:
            entry = Entry(name, "concept", taught_by=self._teacher(session.teacher), learned_at=iso(self.clock.now()), last_used=iso(self.clock.now()))
        self.concepts.add(entry, captured, not said.negative, session.teacher.id, looks)
        if looks:
            entry.examples = (list(entry.examples) + [{"said": looks, "yes": not said.negative}])[-8:]
        self.book.put(entry)
        session.record.examples.append({"name": name, "yes": not said.negative, "said": looks})
        session.kind = session.kind or "concept"
        session.name = session.name or name
        session.last = self.mono()
        session.shown += 1
        self.show()
        self.record("concept_example", name=name, yes=not said.negative, look=captured.look, examples=len(entry.prints))
        if said.negative:
            await self.speak(CONCEPT_NOT.format(name=name))
        elif self.concepts.sure(entry) and sum(1 for _, good in entry.vectors() if good) == 2:
            await self.speak(CONCEPT_MORE.format(name=name))
        else:
            await self.speak(CONCEPT_FIRST.format(name=name))

    async def end(self, session: Session) -> None:
        started = time.perf_counter()
        self.session = None
        self.show()
        if session.leading is not None:
            self._sample(session, force=True)
            current = self.commands.runner.current
            if current is not None and current.kind == "follow":
                self.commands.runner.end("stopped", f"{session.teacher.label} said that's it, so you stopped following")
        if self.drive is not None and self.commands.runner.current is self.drive:
            self.commands.runner.end("stopped", "the lesson ended")
        record = session.record
        teacher = self.commands.fresh(session.teacher)
        if session.kind == "concept" and not record.items:
            self.record("teach_ended", name=session.name, shape="concept", examples=len(record.examples))
            entry = self.concepts.find(session.name)
            if entry is not None:
                await self.speak(readback(entry, self.spoken))
                self._spawn(self._concept_finish(entry, record))
            return
        if session.leading is not None and len(record.trail) >= 2 and length(record.trail) >= 0.5:
            await self._route_made(session, teacher, started)
            return
        if session.leading is not None and not record.items:
            await self.speak(LEAD_SHORT)
            return
        steps = [s for s in record.steps() if s.get("do") != "spot"]
        if not steps:
            if any(item.step.get("do") == "spot" for item in record.items) or record.examples:
                record.forget_words()
                return
            await self.speak(NOTHING_SHOWN)
            return
        examples = [steps]
        existing = self._named(session.adding or session.name) if (session.adding or session.name) else None
        if existing is not None and existing.kind in ("move", "procedure", "way", "habit"):
            examples = [list(e.get("steps") or []) for e in existing.examples if e.get("steps")] + [steps]
        elif existing is None:
            similar = self._like(steps, record.intent)
            if similar is not None:
                existing = similar
                examples = [list(e.get("steps") or []) for e in similar.examples if e.get("steps")] + [steps]
        making = Making(record, teacher, session.name or (existing.name if existing is not None else ""), examples, session.kind, dict(session.trigger), existing.name if existing is not None else "")
        making.shown = list(steps)
        making.ended_at = self.mono()
        self.making = making
        if self.inducer.ready():
            making.task = self._spawn(self._induce(making))
        self.record("teach_ended", name=making.name, steps=len(steps), examples=len(examples), shape=session.kind or "steps")
        self.commands.note(f"{teacher.label} finished showing you {_called(making.name) if making.name else 'something'}; you are showing it back", False)
        task = self.player.start(steps, teacher, making.name or "what you showed me", done=lambda played: self._replayed(making, played))
        making.replay_started = self.mono()
        self.timings.append(time.perf_counter() - started)
        if task is None:
            await self._replayed(making, None)

    def _like(self, steps: list, intent: str) -> Entry | None:
        if not intent:
            return None
        said = name_from(intent)
        for entry in self.book.of_kind("procedure", "move"):
            for example in entry.examples:
                other = name_from(example.get("intent") or "")
                if not other or other == said:
                    if other == said and other:
                        return entry
                    continue
                a, b = other.split(), said.split()
                if len(a) == len(b) and sum(1 for x, y in zip(a, b) if x != y) <= 2 and a[0] == b[0]:
                    shape = [s.get("do") if s.get("do") != "request" else (s.get("request") or {}).get("kind") for s in steps]
                    theirs = [s.get("do") if s.get("do") != "request" else (s.get("request") or {}).get("kind") for s in join(example.get("steps") or [])]
                    if shape == theirs:
                        return entry
        return None

    async def _replayed(self, making: Making, played) -> None:
        if self.making is not making:
            return
        self.record("teach_replayed", name=making.name, ok=bool(played and played.ok), how=played.how if played else "none")
        await self.kit.pace.sleep(0.6)
        if played is not None and not played.ok and played.how in ("refused",) and played.say:
            await self.speak(played.say)
        self.waiting = Waiting("replay", making.teacher, self.mono() + ANSWER_S)
        await self.speak(LIKE_THIS if played is None or played.ok else PART_ONLY + LIKE_THIS)

    async def _route_made(self, session: Session, teacher: Asker, started: float) -> None:
        record = session.record
        points = [list(p) for p in record.trail]
        rooms = list(dict.fromkeys(p[2] for p in points if len(p) > 2 and p[2]))
        name = session.name or session.leading.get("to") or "new way"
        making = Making(record, teacher, name, [], "route")
        making.points, making.rooms = points, rooms
        self.making = making
        self.record("teach_ended", name=name, shape="route", points=len(points))
        refused = await self._route_people(rooms, teacher)
        if refused:
            self.making = None
            await self.speak(refused)
            return
        await self.speak(ROUTE_CHECK)
        activity = Route(Request("go_to_place", place=name), teacher, None, False, points, name, back=True)
        self.commands.runner.start(activity)
        making.replay_started = self.mono()
        self.timings.append(time.perf_counter() - started)
        self._spawn(self._route_back(making, activity), wait=False)

    async def _route_back(self, making: Making, activity: Route) -> None:
        ending = await self.player.wait(activity)
        making.data = {"track": list(activity.track)}
        if self.making is not making:
            return
        self.record("teach_replayed", name=making.name, ok=bool(ending and ending.how == "done"), how=ending.how if ending else "none", shape="route")
        self.waiting = Waiting("route", making.teacher, self.mono() + ANSWER_S)
        await self.speak(ROUTE_ASK)

    async def _route_people(self, rooms: list, asker: Asker, running: bool = False) -> str:
        privacy = getattr(self.life, "privacy", None)
        for room in rooms:
            if (privacy is not None and privacy.rooms.private(room) and not privacy.permitted(room)) or always_private(room):
                return f"That way goes into the {room}, and it's private, so I won't {'go that way' if running else 'keep it'}."
            if self.life.rules is not None:
                kept = self.commands._ruled(Request("go_to_place", place=room))
                if kept is not None:
                    return kept.say
            verdict = decide(Request("go_to_place", place=room), asker, self.commands.situation(refusals_left=0))
            if not verdict.yes and asker.tier == CHILD:
                return verdict.say or f"I can't go to the {room} for you."
        return ""

    async def route_refused(self, entry: Entry, asker: Asker) -> str | None:
        rooms = list(entry.rooms) or list(dict.fromkeys(p[2] for p in entry.points if len(p) > 2 and p[2]))
        refused = await self._route_people(rooms, asker, True)
        if refused:
            self.record("route_refused", name=entry.name, person=asker.id)
            return refused
        verdict = decide(Request("go_to_place", place=entry.name), asker, self.commands.situation(refusals_left=0))
        if not verdict.yes and verdict.reason and "know where" not in verdict.reason and "way" not in verdict.reason:
            return verdict.say or "I can't go there just now."
        return None

    async def _answer(self, waiting: Waiting, asker: Asker, text: str, said: Said | None, heard) -> bool:
        if waiting.kind == "concept":
            return await self._concept_answer(waiting, asker, text)
        if asker.id != waiting.asker.id:
            return False
        if waiting.kind == "name":
            name = name_from(text)
            if said is not None and said.kind == "end" and said.name:
                name = said.name
            if not name or len(name.split()) > 6:
                return False
            self.waiting = None
            making = self.making
            if making is not None:
                making.name = name
                await self._finish(making)
            return True
        if waiting.kind in ("replay", "route"):
            answer = answer_of(text, self.commands.name.lower())
            if answer is None and said is not None and said.kind == "end":
                answer = ("yes", "")
            if answer is None:
                return False
            kind, change = answer
            if kind == "laugh":
                return True
            self.waiting = None
            making = self.making
            if making is None:
                return True
            if kind == "yes":
                making.yes = True
                if waiting.kind == "route":
                    await self._keep_route(making)
                    return True
                await self._after_yes(making)
                return True
            if kind == "nearly" and waiting.kind == "replay":
                steps = making.examples[-1]
                fixed = changed(steps, change) if is_move(steps) else _changed_requests(steps, change)
                if fixed:
                    making.examples[-1] = fixed
                    making.shown = list(fixed)
                    making.record.add({"do": "note", "change": change[:40]}, self.clock.now(), "corrected")
                    making.record.items.pop()
                    self.record("teach_corrected", name=making.name, change=change[:40])
                    if making.task is not None and not making.task.done():
                        making.task.cancel()
                    if self.inducer.ready():
                        making.task = self._spawn(self._induce(making))
                    await self.speak("Okay, like this then.")
                    self.player.start(fixed, making.teacher, making.name or "what you showed me", done=lambda played: self._replayed(making, played))
                    return True
            if kind == "end":
                self.making = None
                await self.speak("Okay, never mind.")
                return True
            self.making = None
            self.session = Session(making.teacher, Record(making.teacher.label, making.record.tier, self.clock.now(), intent=making.record.intent), self.mono(), self.mono(), name=making.name, kind=making.kind, trigger=making.trigger, adding=making.adding)
            self.show()
            await self.speak(SHOW_AGAIN)
            return True
        if waiting.kind == "question":
            making = self.making
            self.waiting = None
            if making is None or making.question is None:
                return True
            steps = answer_question(making.question, clean(text))
            making.examples = [steps]
            making.answered = True
            making.made = None
            self.record("teach_question_answered", name=making.name)
            await self._finish(making, plain_only=True)
            return True
        if waiting.kind == "window":
            answer = answer_of(text, self.commands.name.lower())
            entry = self.book.get(waiting.entry)
            if entry is None:
                self.waiting = None
                return False
            if said is not None and said.kind == "end" and said.name:
                self.waiting = None
                await self.rename(entry, said.name)
                return True
            if answer is None:
                return False
            kind, change = answer
            if waiting.data.get("ran") and kind in ("no", "end"):
                self.waiting = None
                current = self.book.get(entry.name) or entry
                current.bad += 1
                current.good = max(0, current.good - 1)
                self.book.put(current)
                self.record("howto_corrected", name=entry.name, change="no")
                await self.speak(RAN_NO)
                return True
            if kind in ("no", "end"):
                self.waiting = None
                if waiting.steps:
                    entry.steps = list(waiting.steps)
                    entry.slots = dict(waiting.data.get("slots") or {})
                    entry.pattern = pattern_of(entry.name, entry.slots)
                    entry.made_by = "plain"
                    self.book.put(entry)
                    await self.speak("Okay, I'll keep it just as you showed me.")
                else:
                    self._drop(entry)
                    await self.speak("Okay, I won't keep it.")
                return True
            if kind == "nearly" and entry.kind in ("move", "procedure", "way", "habit"):
                self.waiting = None
                fixed = changed(entry.steps, change) if is_move(entry.steps) else _changed_requests(entry.steps, change)
                if fixed:
                    self.book.new_version(entry, self.clock.now(), f"changed: {change}")
                    entry.steps = fixed
                    if waiting.data.get("ran"):
                        entry.examples = (list(entry.examples) + [{"steps": list(fixed), "by": asker.id, "tier": asker.tier, "at": iso(self.clock.now()), "ways": ["corrected"]}])[-8:]
                        self.record("howto_corrected", name=entry.name, change=change[:40])
                    self._save_entry(entry)
                    await self.speak(readback(entry, self.spoken))
                    self._window(entry)
                return True
            if kind == "yes":
                self.waiting = None
                return True
            return False
        return False

    async def _after_yes(self, making: Making) -> None:
        if not making.name:
            self.waiting = Waiting("name", making.teacher, self.mono() + NAME_S)
            await self.speak(ASK_NAME)
            return
        await self._finish(making)

    async def _finish(self, making: Making, plain_only: bool = False) -> None:
        if self.making is not making:
            return
        if not making.answered:
            made, question = plain_made(making.examples, making.name)
            if question is not None:
                making.question = question
                self.waiting = Waiting("question", making.teacher, self.mono() + QUESTION_S)
                self.record("teach_question", name=making.name, shape=question.kind)
                await self.speak(question.text)
                return
        if not plain_only and making.task is not None and not making.task.done():
            if not making.said_hold:
                making.said_hold = True
                await self.speak(HOLD)
            try:
                await asyncio.shield(making.task)
            except Exception:
                pass
        await self._keep(making, plain_only)

    async def _induce(self, making: Making) -> None:
        started = self.mono()
        try:
            known = self.book.closest(making.record.intent or making.name or said_steps(making.examples[-1]))
            text = making.record.text(examples=making.examples)
            data, calls, failed = await self.inducer.ask(text, self.card(), known, kinds=(making.kind,) if making.kind in ("way", "habit") else ("move", "procedure"))
            if data is None:
                making.made = Made("", "", [], failed=failed, calls=calls)
                return
            made = made_from(data, self.card(), making.examples, values_seen(making.examples))
            made.calls = calls
            made.seconds = self.mono() - started
            making.made = made
            self.record("teach_induced", name=making.name, ok=not made.problems, problems=len(made.problems), seconds=round(made.seconds, 2), shape=made.kind)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("working out what was taught failed")

    async def _keep(self, making: Making, plain_only: bool) -> None:
        if self.making is not making:
            return
        self.making = None
        plain, _ = plain_made(making.examples, making.name)
        made = making.made
        teacher = self.commands.fresh(making.teacher)
        chosen = plain
        literal = list(plain.steps)
        if not plain_only and made is not None and made.kind and not made.problems and made.steps:
            if not making.answered or not made.slots:
                chosen = Made(made.kind if made.kind in ("move", "procedure") else plain.kind, making.name or made.name, made.steps, made.slots, made.aliases, made.about, "model")
        if chosen.kind == "move" and not is_move(chosen.steps):
            chosen.kind = "procedure"
        if not chosen.name:
            chosen.name = (made.name if made is not None and made.name else "") or name_from(making.record.intent) or "new trick"
        if making.kind in ("way", "habit"):
            chosen.kind = making.kind
        problem = await self.allowed(chosen, teacher, making)
        if problem:
            self.record("teach_refused", why="who may teach", shape=chosen.kind)
            await self.speak(problem)
            return
        for words in [chosen.name] + list(chosen.aliases) + [chosen.about]:
            if words and (self.commands.words_problem(words) or harmed(words, self.commands.context(None, teacher)) is not None):
                chosen.aliases = [a for a in chosen.aliases if a != words]
                if words == chosen.about:
                    chosen.about = ""
                if words == chosen.name:
                    chosen.name = name_from(making.record.intent) or "new trick"
        entry = self._made_entry(chosen, making, teacher)
        self._save_entry(entry)
        making.record.forget_words()
        self.record("howto_kept", name=entry.name, shape=entry.kind, steps=len(entry.steps), slots=len(entry.slots), made_by=entry.made_by, tier=teacher.tier)
        self.commands.note(f"{teacher.label} taught you {_thing_name(entry)}, and you said it back", False)
        self.commands.diary(f"{teacher.label} taught me {shown_name(entry)}.", "activity")
        self.kit.face.show("love")
        await self.speak(readback(entry, self.spoken))
        self._window(entry, literal if entry.made_by == "model" else [], plain.slots)

    def _window(self, entry: Entry, literal: list | None = None, slots: dict | None = None) -> None:
        teacher = self.commands.asker_for(entry.teacher_id) if entry.teacher_id else PEBBLE
        self.waiting = Waiting("window", teacher, self.mono() + WINDOW_S, entry.name, steps=list(literal or []), data={"slots": dict(slots or {})})

    def _made_entry(self, chosen: Made, making: Making, teacher: Asker) -> Entry:
        now = iso(self.clock.now())
        existing = self._named(making.adding) if making.adding else self._named(chosen.name)
        example = {"steps": list(making.shown or making.examples[-1]), "intent": name_from(making.record.intent) if making.kind not in ("way", "habit") else "", "by": teacher.id, "tier": teacher.tier, "at": now, "ways": list(making.record.ways)}
        if existing is not None and existing.kind == chosen.kind:
            self.book.new_version(existing, self.clock.now(), "taught again")
            entry = existing
            entry.examples = (list(entry.examples) + [example])[-8:]
        else:
            entry = Entry(chosen.name, chosen.kind, learned_at=now, examples=[example])
        entry.steps = list(chosen.steps)
        entry.slots = {k: list(v) for k, v in chosen.slots.items()}
        entry.pattern = pattern_of(entry.name, entry.slots) or _pattern_from_intents(entry)
        entry.aliases = list(dict.fromkeys([a for a in chosen.aliases if a and a != entry.name] + [a for a in entry.aliases if a != entry.name]))[:8]
        intent = name_from(making.record.intent)
        if intent and intent != entry.name and intent not in entry.aliases and not entry.slots and chosen.kind in ("move", "procedure") and len(intent.split()) <= 6:
            entry.aliases.append(intent)
        entry.about = chosen.about or said_steps(entry.steps)[:160]
        entry.made_by = chosen.made_by
        entry.taught_by = self._teacher(teacher)
        entry.learned_at = now
        entry.last_used = now
        entry.body = self.life.skills.body
        if chosen.kind in ("way", "habit"):
            entry.trigger = dict(making.trigger)
            if chosen.kind == "way":
                entry.person = teacher.id
                entry.trigger["who"] = "me"
        return entry

    def _save_entry(self, entry: Entry) -> None:
        if entry.kind == "move" and not entry.slots and is_move(entry.steps):
            try:
                skill = self.life.skills.get(entry.name)
                self.life.skills.keep(entry.name, entry.examples[-1].get("intent") or entry.name if entry.examples else entry.name, entry.steps, entry.taught_by, replacing=skill)
            except Exception:
                log.exception("could not keep a taught move as a skill")
            entry.link = {"skill": entry.name}
        self.book.put(entry)
        selection = getattr(self.life, "selection", None)
        if selection is not None:
            selection.stale()

    def _drop(self, entry: Entry) -> None:
        self.book.remove(entry.name, "the teacher said no")
        if entry.link.get("skill"):
            self.life.skills.drop(entry.link["skill"]) if hasattr(self.life.skills, "drop") else None

    async def rename(self, entry: Entry, name: str) -> None:
        old = entry.name
        self.book.remove(old, "renamed")
        entry.aliases = list(dict.fromkeys([old] + entry.aliases))[:8]
        entry.name = name
        entry.pattern = pattern_of(entry.name, entry.slots) or entry.pattern
        if entry.link.get("skill"):
            self.life.skills.drop(entry.link["skill"])
        self._save_entry(entry)
        await self.speak(f"Okay, I'll call it the {name}.")

    async def allowed(self, made: Made, teacher: Asker, making: Making | None = None) -> str:
        for step in made.steps:
            request = request_of(step)
            private = next((inner.place for inner in request.steps() if always_private(inner.place)), "") if request is not None else ""
            if private:
                return PRIVATE_STEP.format(room=private)
        if teacher.owner:
            return ""
        if made.kind in ("way",):
            return ""
        reasons = []
        for step in made.steps:
            request = request_of(step)
            if request is None:
                continue
            for inner in request.steps():
                if inner.kind == "say_to" and inner.who not in ("", "me"):
                    reasons.append("passes things on to other people")
                if inner.kind in ("come", "look", "follow") and inner.who not in ("", "me"):
                    reasons.append("goes to other people")
                if inner.place and self._ruled_room(inner.place):
                    reasons.append(f"goes into the {inner.place}, which has a house rule")
        if made.kind == "habit" and making is not None and making.trigger.get("who") not in (None, "", "me"):
            reasons.append("watches for someone else")
        if reasons and not self.close(teacher):
            return CLOSE_ONLY.format(why=reasons[0])
        return ""

    def _ruled_room(self, room: str) -> bool:
        privacy = getattr(self.life, "privacy", None)
        if privacy is not None and privacy.rooms.kind(room):
            return True
        rules = self.life.rules
        try:
            return any(rule.kind == "keep_out" and rule.place == room for rule in rules.holding()) if rules is not None else False
        except Exception:
            return False

    def _teacher(self, asker: Asker) -> dict:
        return {"id": asker.id, "name": asker.label, "tier": "owner" if asker.owner else asker.tier}

    async def _keep_route(self, making: Making) -> None:
        self.making = None
        teacher = self.commands.fresh(making.teacher)
        name = making.name
        now = iso(self.clock.now())
        entry = self._named(name)
        if entry is not None and entry.kind == "route":
            self.book.new_version(entry, self.clock.now(), "led again")
        else:
            entry = Entry(name, "route", learned_at=now)
        entry.points = [list(p) for p in making.points]
        entry.rooms = list(making.rooms)
        entry.aliases = list(dict.fromkeys([f"the way to the {name}", f"way to the {name}"] + entry.aliases))[:8]
        entry.about = f"the way to the {name}" + (f" through the {', '.join(making.rooms[:-1])}" if len(making.rooms) > 1 else "")
        entry.taught_by = self._teacher(teacher)
        entry.last_used = now
        entry.examples = (list(entry.examples) + [{"points": len(making.points), "by": teacher.id, "tier": teacher.tier, "at": now, "ways": ["lead"]}])[-8:]
        nav = self.life.nav
        try:
            last = making.points[-1]
            nav.chart.remember_spot(name, float(last[0]), float(last[1]))
            nav.charts.dirty = True
        except Exception:
            log.exception("could not mark the end of a taught way on the map")
        self.book.put(entry)
        making.record.forget_words()
        self.record("howto_kept", name=name, shape="route", points=len(entry.points), tier=teacher.tier)
        await self.speak(readback(entry, self.spoken))
        self._window(entry)

    async def word(self, asker: Asker, said: Said) -> None:
        tier = self.who_may(asker)
        if not tier or tier == "own":
            await self.speak(STRANGER_NO)
            return
        ctx = self.commands.context(None, asker)
        harmful = harmed(said.words, ctx) or harmed(f"{said.name}", ctx)
        if harmful is not None:
            self.record("teach_refused", why="harm", shape="word")
            await self.commands.act(harmful, asker, "heard")
            return
        reading = await self.commands.read_words(said.words, asker)
        if not reading.request.action and not reading.request.kind == "other":
            await self.speak(WORD_EMPTY)
            return
        existing = self._named(said.name)
        if existing is not None:
            refused = self.overrides(existing, asker)
            if refused:
                await self.speak(refused)
                return
        now = iso(self.clock.now())
        entry = existing if existing is not None and existing.kind == "word" else Entry(said.name, "word", learned_at=now)
        if existing is not None and existing.kind == "word":
            self.book.new_version(entry, self.clock.now(), "taught again")
        entry.words = said.words[:160]
        entry.about = f"when someone says {said.name}, {said.words}"[:160]
        entry.taught_by = self._teacher(asker)
        entry.last_used = now
        entry.examples = (list(entry.examples) + [{"words": said.words[:80], "by": asker.id, "tier": asker.tier, "at": now}])[-8:]
        self.book.put(entry)
        self.record("howto_kept", name=entry.name, shape="word", tier=asker.tier)
        await self.speak(readback(entry, self.spoken))
        self._window(entry)

    async def _clauses(self, words: str, asker: Asker) -> list:
        steps = []
        words = COME_GET.sub("come to me", " ".join(str(words or "").split()))
        for part in CLAUSES.split(words):
            clause = LEAD_IN.sub("", part.strip(" ,.")).strip()
            if not clause:
                continue
            reading = await self.commands.read_words(clause, asker)
            request = reading.request
            if not request.action or reading.ask or reading.too_much:
                continue
            if request.kind == "harm":
                await self.commands.act(request, asker, "heard")
                return []
            for step in [request.with_(then=())] + list(request.then):
                steps.append(step_of(step))
        return steps

    async def explain(self, asker: Asker, name: str, words: str, session: Session | None) -> None:
        tier = self.who_may(asker)
        if not tier or tier == "own":
            await self.speak(STRANGER_NO)
            return
        harmful = harmed(words, self.commands.context(None, asker))
        if harmful is not None:
            await self.commands.act(harmful, asker, "heard")
            return
        if loopy(words) or re.search(r"\b(?:game|score|points|winner|round of)\b", f"{name} {words}"):
            scripts = getattr(self.life, "scripts", None)
            if scripts is not None and scripts.can_write(asker):
                entry = Entry(name or "game", "game", about=f"{name}: {words}"[:160], taught_by=self._teacher(asker), learned_at=iso(self.clock.now()), link={"words": f"{name}: {words}"[:300]})
                self.book.put(entry)
                self.record("howto_game", name=entry.name, tier=asker.tier)
                await scripts.ask_for(f"{name}: {words}", asker, "heard")
                return
        steps = await self._clauses(words, asker)
        if not steps:
            await self.speak(EXPLAIN_EMPTY)
            return
        record = session.record if session is not None else Record(asker.label, asker.tier, self.clock.now(), intent=name)
        for step in steps:
            record.add(step, self.clock.now(), "explained")
        if session is not None:
            self.session = None
            self.show()
        existing = self._named(name)
        if existing is not None:
            refused = self.overrides(existing, asker)
            if refused:
                await self.speak(refused)
                return
        examples = [list(e.get("steps") or []) for e in existing.examples if e.get("steps")] + [join(steps)] if existing is not None and existing.kind in ("procedure", "move") else [join(steps)]
        making = Making(record, asker, name, examples, session.kind if session is not None else "", dict(session.trigger) if session is not None else {}, existing.name if existing is not None else "")
        making.answered = len(examples) == 1
        self.making = making
        if self.inducer.ready():
            making.task = self._spawn(self._induce(making))
        await self._finish(making)

    async def habit(self, asker: Asker, words: str, event_words: str, session: Session | None) -> None:
        tier = self.who_may(asker)
        if not tier or tier == "own":
            await self.speak(STRANGER_NO)
            return
        ctx = self.commands.context(None, asker)
        harmful = harmed(words, ctx)
        if harmful is not None:
            self.record("teach_refused", why="harm", shape="habit")
            await self.commands.act(harmful, asker, "heard")
            return
        trigger = self.trigger_of(event_words, asker)
        if trigger is None:
            reading = await self.commands.read_words(f"when {event_words}, {words}", asker)
            if reading.request.on is not None:
                trigger = reading.request.on.as_dict()
        if trigger is None:
            await self.speak("I can't tell when that happens yet, so I can't learn that one.")
            return
        line = self.life.later.senses.can_sense(trigger_from(trigger)) if trigger.get("event") != "arrives" or trigger.get("who") else ""
        if line:
            await self.speak(line)
            return
        steps = await self._clauses(words, asker)
        if not steps:
            await self.speak(WORD_EMPTY)
            return
        name = name_from(f"when {event_words}")
        record = Record(asker.label, asker.tier, self.clock.now(), intent=f"whenever {event_words}, {words}")
        for step in steps:
            record.add(step, self.clock.now(), "explained")
        making = Making(record, asker, name, [join(steps)], "habit", trigger)
        making.answered = True
        made = Made("habit", name, join(steps))
        problem = await self.allowed(made, asker, making)
        if problem:
            await self.speak(problem)
            return
        self.making = making
        await self._keep(making, True)

    def trigger_of(self, event_words: str, asker: Asker) -> dict | None:
        said = " ".join(str(event_words or "").lower().split())
        said = re.sub(r"^(?:the |a |my |our )", "", said)
        for word in sorted(SOUND_WORDS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(word)}\b", said):
                return {"event": "sound", "thing": sound_kind(word)}
        taught = getattr(getattr(self.life, "house", None), "taught", None)
        for sound in (getattr(taught, "sounds", {}) or {}).values():
            if sound.name.lower() in said:
                return {"event": "sound", "thing": sound_kind(sound.name)}
        found = ARRIVES.match(said)
        if found:
            who = found.group("who")
            return {"event": "arrives", "who": "me" if who == "i" else who}
        found = LEAVES.match(said)
        if found:
            who = found.group("who")
            return {"event": "leaves", "who": "me" if who == "i" else who}
        found = re.match(r"^i (?:come home|get home|come in|get back|arrive)$", said)
        if found:
            return {"event": "arrives", "who": "me"}
        found = SEES.match(said)
        if found and found.group("thing") and len(found.group("thing").split()) <= 2:
            return {"event": "seen", "thing": found.group("thing")}
        return None

    async def way(self, asker: Asker, event_words: str, words: str, session: Session | None) -> None:
        event = SAID_EVENTS.get(event_words)
        if event is None:
            await self.speak(WAY_SENSE.format(event=event_words))
            return
        steps = await self._clauses(words, asker)
        if not steps:
            await self.begin(asker, "", words, "way", trigger_words=event_words)
            return
        tier = self.who_may(asker)
        if not tier or tier == "own":
            await self.speak(STRANGER_NO)
            return
        name = f"{'greeting' if event == 'arrives' else 'goodbye'} for {asker.label.lower()}"
        record = Record(asker.label, asker.tier, self.clock.now(), intent=f"when I {event_words}, {words}")
        for step in steps:
            record.add(step, self.clock.now(), "explained")
        making = Making(record, asker, name, [join(steps)], "way", {"event": event, "who": "me"})
        making.answered = True
        self.making = making
        await self._keep(making, True)

    async def copy_me(self, asker: Asker) -> None:
        tier = self.who_may(asker)
        if not tier or tier == "own":
            await self.speak(STRANGER_NO)
            return
        verdict = self.commands.decide_now(Request("turn", way="left"), asker)
        if not verdict.yes:
            await self.commands._answer(Request("turn", way="left"), asker, verdict, "heard")
            return
        trying = self.commands.trying
        mimic = Mimic(Request("try_new", text="copy me", name="copy me"), asker, None, False, [], "copy me", trying.gate, trying.run_step, seconds=COPY_S)
        mimic.track = self._track_of(asker)
        self.mimic = mimic
        self.copied = None
        self.commands.runner.start(mimic)
        await self.speak(COPY_START)

    def _track_of(self, asker: Asker) -> int | None:
        eyes = self.life.p.eyes
        sight = eyes.latest(1.0) if getattr(eyes, "available", False) else None
        if sight is None or not sight.people:
            return None
        for person in sight.people:
            name = self.kit.name_of(person.track)
            if name and asker.label and name.lower() == asker.label.lower():
                return person.track
        return max(sight.people, key=lambda p: p.height_frac).track

    async def keep_copied(self, asker: Asker, name: str) -> None:
        steps, by = self.copied
        if by.id != asker.id and not self.close(asker):
            return
        self.copied = None
        if not steps:
            await self.speak(COPY_NOTHING)
            return
        record = Record(asker.label, asker.tier, self.clock.now())
        for step in steps:
            record.add(step, self.clock.now(), "copied")
        making = Making(record, asker, name or "", [join(steps)], "")
        making.answered = True
        self.making = making
        if not making.name:
            self.waiting = Waiting("name", asker, self.mono() + NAME_S)
            await self.speak(ASK_NAME)
            return
        await self._keep(making, True)

    async def carry_on(self, asker: Asker, name: str) -> bool:
        drafts = [d for d in self.book.tidy_drafts() if (d.get("teacher") or {}).get("id") == asker.id]
        if not drafts:
            return False
        await self.begin(asker, name or drafts[-1].get("name", ""), "", "carry_on")
        return True

    def listing(self, asker: Asker, taught: bool) -> str:
        mine = [entry for entry in self.book.all() if entry.teacher_id == asker.id] if taught else self.book.all()
        skills = [skill for skill in self.life.skills.all() if (not taught or (skill.taught_by or {}).get("id") == asker.id) and not self.book.get(skill.name)]
        names = [self.spoken(_thing_name(entry)) for entry in mine if entry.person in (None, asker.id)] + [f"the {skill.name}" for skill in skills]
        if not taught:
            scripts = getattr(getattr(self.life, "scripts", None), "book", None)
            if scripts is not None:
                names += [f"the {e['name']}" for e in scripts.live()]
        if not names:
            return NOT_TAUGHT if taught else KNOW_NOTHING
        lead = "You taught me " if taught else "I know "
        if len(names) > 8:
            shown = ", ".join(names[:7]) + f" and {len(names) - 7} more"
        elif len(names) == 1:
            shown = names[0]
        else:
            shown = ", ".join(names[:-1]) + " and " + names[-1]
        return lead + shown + "."

    def bumped(self, label: str) -> None:
        nav = getattr(self.life, "nav", None)
        try:
            if nav is None or not nav.pose.local_usable:
                return
            x, y = nav.pose.pose_rad()[:2]
            remember_careful(nav.chart.careful, x, y, f"where the {label[:40]} bumped")
            nav.charts.dirty = True
        except Exception:
            log.exception("could not mark a careful spot for a taught move")
            return
        self.record("howto_careful", name=label[:40])

    async def forget_entry(self, entry: Entry, asker: Asker) -> None:
        if not self.may_forget(entry.teacher_id, entry.teacher_tier, asker) and entry.person != asker.id:
            await self.speak(FORGET_NO.format(name=entry.taught_by.get("name") or "whoever taught me"))
            return
        self.book.remove(entry.name, f"{asker.label} asked")
        if entry.link.get("skill"):
            self.life.skills.drop(entry.link["skill"])
        if entry.kind == "spot":
            try:
                chart = self.life.nav.chart
                chart.places = [p for p in chart.places if p.name != entry.name]
                self.life.nav.charts.dirty = True
            except Exception:
                log.exception("could not take a taught spot off the map")
        selection = getattr(self.life, "selection", None)
        if selection is not None:
            selection.stale()
        self.record("howto_forgot", name=entry.name, by=asker.id)
        await self.speak(FORGOT.format(what=_thing_name(entry)))

    async def forget_skill(self, skill, asker: Asker) -> None:
        taught = skill.taught_by or {}
        if not self.may_forget(taught.get("id"), str(taught.get("tier") or ""), asker):
            await self.speak(FORGET_NO.format(name=taught.get("name") or "whoever taught me"))
            return
        self.life.skills.drop(skill.name)
        self.book.remove(skill.name, f"{asker.label} asked")
        await self.speak(FORGOT.format(what=f"the {skill.name}"))

    def may_forget(self, teacher_id: str | None, teacher_tier: str, asker: Asker) -> bool:
        from ..activities.gate import rank

        if asker.owner or (teacher_id is not None and asker.id == teacher_id):
            return True
        if asker.tier in (STRANGER, CHILD):
            return False
        mine = rank(asker.tier)
        theirs = rank("inner circle" if teacher_tier == "owner" else (teacher_tier or STRANGER))
        return mine > theirs or teacher_id is None and mine >= rank(TRUSTED)

    async def skip(self, asker: Asker, name: str, what: str) -> bool:
        entry = self._named(name)
        if entry is None or entry.kind not in ("procedure", "way", "habit", "route"):
            return False
        steps = [s for s in entry.steps if what not in [str(v) for v in nouns(s).values()]]
        if len(steps) == len(entry.steps):
            await self.speak(NOTHING_TO_SKIP.format(what=what))
            return True
        await self.speak(SKIPPED.format(what=what))
        await self.run_entry(entry, {}, asker, "heard", name, steps=steps)
        return True

    async def from_now(self, asker: Asker, name: str, what: str) -> bool:
        candidates = [self._named(name)] if name else [e for e in self.book.all() if any(what in [str(v) for v in nouns(s).values()] for s in e.steps)]
        entry = next((e for e in candidates if e is not None), None)
        if entry is None:
            return False
        if self.overrides(entry, asker) or not (asker.id == entry.teacher_id or self.may_forget(entry.teacher_id, entry.teacher_tier, asker)):
            await self.speak(FORGET_NO.format(name=entry.taught_by.get("name") or "whoever taught me"))
            return True
        steps = [s for s in entry.steps if what not in [str(v) for v in nouns(s).values()]]
        if len(steps) == len(entry.steps) or not steps:
            await self.speak(NOTHING_TO_SKIP.format(what=what))
            return True
        self.book.new_version(entry, self.clock.now(), f"skip the {what}")
        entry.steps = steps
        entry.about = said_steps(steps)[:160]
        self._save_entry(entry)
        await self.speak(readback(entry, self.spoken))
        self._window(entry)
        return True

    def matched(self, text: str) -> Request | None:
        try:
            found = self.book.find(text)
        except Exception:
            log.exception("could not look in the how-to book")
            return None
        if found is None:
            return None
        entry, slots = found
        if entry.kind in ("concept", "route"):
            return None
        if entry.kind == "move" and entry.link.get("skill"):
            return None
        return Request("try_new", text=plain_words(text)[:160], name=f"howto:{entry.tag}")

    async def run_request(self, request: Request, asker: Asker, how: str) -> Verdict | None:
        name = request.name or ""
        if not name.startswith("howto:"):
            return None
        found = self.book.find(request.text) if request.text else None
        entry, slots = found if found is not None else (self.book.get(name[len("howto:"):]), {})
        if entry is None:
            line = NOT_FOUND
            if not asker.own:
                await self.speak(line)
            return Verdict("no", "you have no such how-to", line)
        return await self.run_entry(entry, slots, asker, how, request.text)

    def version_for(self, entry: Entry) -> tuple[list, dict]:
        grown = self.grown_up(entry)
        if grown is not None and grown.get("steps"):
            return list(grown["steps"]), dict(grown.get("slots") or {})
        return list(entry.steps), dict(entry.slots)

    def grown_up(self, entry: Entry) -> dict | None:
        if entry.teacher_tier != CHILD:
            return None
        for version in reversed(entry.versions):
            tier = str((version.get("taught_by") or {}).get("tier") or "")
            if tier and tier not in (CHILD, STRANGER):
                return version
        return None

    async def run_entry(self, entry: Entry, slots: dict, asker: Asker, how: str, words: str = "", steps: list | None = None) -> Verdict:
        commands = self.commands
        ctx = commands.context(None, asker)
        if entry.kind == "word":
            grown = self.grown_up(entry)
            meaning = str(grown["words"]) if grown is not None and grown.get("words") else entry.words
            harmful = harmed(meaning, ctx)
            if harmful is not None:
                self.record("howto_refused", name=entry.name, why="harm")
                return await commands.act(harmful, asker, how)
            self.book.used(entry)
            reading, verdict = await commands.request_words(meaning, asker, "heard")
            if verdict is None and not reading.request.action:
                if reading.request.kind == "other" and not asker.own:
                    return await commands._try_new(Request("try_new", text=meaning[:160]), asker, how)
                return Verdict("no", "the word did not lead to anything", "")
            return verdict or Verdict("no", "the word did not lead to anything", "")
        if entry.kind == "concept":
            return await self.ask_concept(entry, asker)
        if entry.kind == "spot":
            return await commands.act(Request("go_back", place=entry.link.get("spot") or entry.name), asker, how)
        if entry.kind == "game":
            return await self.run_game(entry, asker)
        if entry.kind == "move" and entry.link.get("skill") and steps is None:
            return await commands.trying.start(Request("try_new", text=words[:160] or entry.name, name=entry.link["skill"]), asker, how)
        if entry.kind == "route":
            refused = await self.route_refused(entry, asker)
            if refused:
                if not asker.own:
                    await self.speak(refused)
                return Verdict("no", "the way goes somewhere you may not go for them", refused)
            verdict = commands.decide_now(Request("go_to_place", place=entry.name), asker)
            if verdict.answer == "no" and "know where" not in verdict.reason:
                await commands._answer(Request("go_to_place", place=entry.name), asker, verdict, how)
                return verdict
            self.book.used(entry)
            commands.runner.start(Route(Request("go_to_place", place=entry.name), asker, None, False, entry.points, entry.name))
            return Verdict("yes", f"you know the way to the {entry.name}", "")
        chosen, chosen_slots = self.version_for(entry)
        chosen = steps if steps is not None else chosen
        filled = dict(chosen_slots)
        for slot, value in slots.items():
            filled[slot] = value
        values = {k: (v if isinstance(v, str) else (v[0] if v else "")) for k, v in filled.items() if isinstance(v, str)}
        for slot in holes(chosen):
            if slot not in values:
                options = chosen_slots.get(slot) or []
                if len(options) == 1:
                    values[slot] = options[0]
        if holes(chosen) and any(slot not in values for slot in holes(chosen)):
            missing = [slot for slot in holes(chosen) if slot not in values][0]
            options = chosen_slots.get(missing) or []
            line = f"Which {missing.replace('_', ' ')}?" + (f" {' or '.join(f'The {o}' for o in options[:3])}?" if options else "")
            if not asker.own:
                await self.speak(line)
            return Verdict("ask", "it needs a value you didn't say", line)
        for value in values.values():
            harmful = harmed(f"go to the {value}", ctx)
            if harmful is not None:
                return await commands.act(harmful, asker, how)
        verdict = commands.decide_now(Request("try_new", text=(words or entry.name)[:160]), asker)
        if not verdict.yes:
            await commands._answer(Request("try_new", text=(words or entry.name)[:160]), asker, verdict, how)
            return verdict
        self.record("howto_run", name=entry.name, person=asker.id, slots=len(values), shape=entry.kind)
        if not asker.own:
            commands.note(f"{asker.label} asked you to do {_thing_name(entry)}, which you were taught", False)
        self.runs[entry.tag] = (self.mono(), asker.id)
        self.player.start(chosen, asker, entry.name, values, done=lambda played: self._ran(entry, played, asker))
        return Verdict("yes", f"you know how to do the {entry.name}", "")

    async def _ran(self, entry: Entry, played, asker: Asker | None = None) -> None:
        good = bool(played is not None and played.ok)
        try:
            self.book.used(entry, good if played is not None and played.how != "stopped" else False)
        except Exception:
            log.exception("could not count a taught run")
        if played is not None and not played.ok and played.say and played.how == "refused":
            await self.speak(played.say)
        if good and asker is not None and not asker.own and entry.kind in ("procedure", "way", "habit") and (asker.id == entry.teacher_id or self.may_forget(entry.teacher_id, entry.teacher_tier, asker)) and self.waiting is None:
            self.waiting = Waiting("window", asker, self.mono() + WINDOW_S, entry.name, data={"ran": True})

    async def run_game(self, entry: Entry, asker: Asker) -> Verdict:
        scripts = getattr(self.life, "scripts", None)
        words = entry.link.get("words") or ""
        if scripts is not None:
            for item in scripts.book.scripts.values():
                if words and item.get("words") == words:
                    await scripts.go_live(item)
                    return Verdict("yes", f"you started the {entry.name}", "")
        line = "I'm still working out that game."
        if not asker.own:
            await self.speak(line)
        return Verdict("no", "the game's program isn't ready", line)

    async def ask_concept(self, entry: Entry, asker: Asker) -> Verdict:
        answer = await self.concepts.is_this(entry)
        if answer == "alive":
            line = ALIVE_NEVER
        elif entry.look == "thing":
            line = {"yes": THING_YES, "no": THING_NO}.get(answer, LOOKS_UNSURE).format(name=entry.name)
        else:
            line = {"yes": LOOKS_YES, "no": LOOKS_NO}.get(answer, LOOKS_UNSURE).format(name=entry.name)
        if not asker.own:
            await self.speak(line)
        return Verdict("yes", f"you looked to see whether it was {entry.name}", line)

    async def _concept_words(self, text: str, asker: Asker) -> bool:
        flat = bare(text, self.commands.name.lower())
        if not flat:
            return False
        names = self.concepts.names()
        if not names:
            return False
        for pattern in (CONCEPT_IF, CONCEPT_TELL):
            found = pattern.match(flat)
            if found is None:
                continue
            what = name_from(found.group("what"))
            entry = self.concepts.find(what)
            if entry is None:
                continue
            place = name_from(found.group("place"))
            place = "" if place in ("this", "it", "that") else place
            then = found.groupdict().get("then") or ""
            if not then or re.match(r"^(?:tell me|let me know|say so)$", then):
                value = await self.concepts.state(entry.name, place)
                where = f"the {place}" if place else "it"
                if value is None:
                    line = f"I can't tell from here whether {where} looks {entry.name}." if place and self.room() != place else f"I'm not sure whether {where} looks {entry.name}."
                else:
                    line = f"{where[:1].upper() + where[1:]} {'looks' if value else "doesn't look"} {entry.name}."
                self.record("concept_state", name=entry.name, value=value)
                await self.speak(line)
                return True
            reading = await self.commands.read_words(then, asker)
            if not reading.request.action:
                return False
            body = (reading.request,)
            from ..understand.request import Cond

            cond = Cond(state="looks", what=entry.name, place=place)
            request = Request("if", if_=cond, then=body)
            await self.commands.act(request, asker, "heard")
            return True
        found = CONCEPT_ASK.match(flat)
        if found:
            entry = self.concepts.find(name_from(found.group("what")))
            if entry is not None:
                await self.ask_concept(entry, asker)
                return True
        return False

    async def _concept_answer(self, waiting: Waiting, asker: Asker, text: str) -> bool:
        flat = clean(text)
        yes = bool(YES.match(flat))
        no = bool(NO.match(flat))
        if not (yes or no):
            return False
        if not self.who_may(asker) or self.who_may(asker) == "own":
            return False
        self.waiting = None
        entry = self.book.get(waiting.entry)
        if entry is None:
            return True
        from .concepts import Captured

        vector = waiting.data.get("vector")
        if vector:
            self.concepts.add(entry, Captured(tuple(vector), entry.look), yes, asker.id, "")
            self.book.put(entry)
        self.record("concept_answer", name=entry.name, yes=yes, examples=len(entry.prints))
        await self.speak(THANKS)
        return True

    async def _wonder(self) -> None:
        if self.session is not None or self.waiting is not None or self.commands.runner.busy:
            return
        here = self.life.company.here(self.clock.now())
        if not here:
            return
        found = await self.concepts.wonder(True)
        if found is None:
            return
        entry, vector, verdict = found
        local = self.clock.local()
        self.concepts.count_ask(entry, local)
        self.book.put(entry)
        person = here[0]
        asker = self.commands.asker_for(person.id)
        self.waiting = Waiting("concept", asker, self.mono() + QUESTION_S, entry.name, data={"vector": list(vector)})
        self.record("concept_asked", name=entry.name)
        await self.speak((CONCEPT_ASK_THING if entry.look == "thing" else CONCEPT_ASK_PLACE).format(name=entry.name))

    async def _concept_finish(self, entry: Entry, record: Record) -> None:
        said = [e.get("said") for e in entry.examples if e.get("said") and e.get("yes", True)]
        if not said:
            record.forget_words()
            return
        line = await self._one_line(entry, said) if self.inducer.ready() else said[-1]
        if line and not self.commands.words_problem(line):
            entry.line = line[:120]
            self.book.put(entry)
        record.forget_words()

    async def _one_line(self, entry: Entry, said: list) -> str:
        text = f'Concept: "{entry.name}". What the picture model said about each example: ' + "; ".join(f'"{s}"' for s in said[:4]) + '\nWrite one short line, under 12 words, saying what the examples have in common. Reply with JSON only: {"line":"..."}'
        record = Record(entry.taught_by.get("name") or "someone", entry.teacher_tier, self.clock.now())
        record.words = [text]
        data, _, _ = await self.inducer.ask(text, self.card(), [])
        line = str((data or {}).get("line") or (data or {}).get("about") or "").strip()
        return " ".join(line.split())[:120]

    def ended(self, activity, ending) -> None:
        self.player.ended(activity)
        if activity is self.drive:
            self.drive = None
        if activity is self.mimic:
            self.mimic = None
            steps = list(getattr(activity, "copied", []) or [])
            self.copied = (steps, activity.asker) if steps else None
            if self.session is not None and steps:
                self.show()
        session = self.session
        if session is not None and session.leading is not None and activity.kind == "follow" and activity.asker.id == session.teacher.id:
            self._sample(session, force=True)

    def tick(self) -> None:
        now = self.mono()
        session = self.session
        if session is not None:
            current = self.commands.runner.current
            if current is not None and current.moving and current.asker.id == session.teacher.id and current.kind != "wait":
                session.last = now
            if session.leading is not None:
                self._sample(session)
            idle = now - session.last
            if idle > IDLE_S or now - session.started_mono > LONGEST_S:
                self._time_out(session)
        waiting = self.waiting
        if waiting is not None and now > waiting.until:
            self.waiting = None
            self._timed_out(waiting)
        making = self.making
        if making is not None and now - making.ended_at > WORDS_KEEP_S:
            making.record.forget_words()
        if self.offer is not None and now > self.offer[3]:
            self.offer = None
        self._habits()
        if now - self.wondered >= WONDER_EVERY_S:
            self.wondered = now
            self._spawn(self._wonder())
        if now - self.look_at >= LOOK_EVERY_S and self.concepts.all() and (self.looking is None or self.looking.done()):
            self.look_at = now
            self.looking = self._spawn(self._look_round(), wait=False)

    def _time_out(self, session: Session) -> None:
        self.session = None
        self.show()
        record = session.record
        steps = record.steps()
        if steps or record.trail or record.examples:
            self.book.draft(session.name, self._teacher(session.teacher), steps, record.trail, record.examples, record.ways)
            self.say(DRAFT)
        record.forget_words()
        self.record("teach_timed_out", name=session.name, steps=len(steps))

    def _timed_out(self, waiting: Waiting) -> None:
        making = self.making
        if waiting.kind in ("replay", "route") and making is not None:
            making.yes = True
            if waiting.kind == "route":
                self._spawn(self._keep_route(making))
            else:
                self._spawn(self._after_yes(making))
            return
        if waiting.kind == "name" and making is not None:
            making.name = name_from(making.record.intent) or (making.made.name if making.made is not None and making.made.name else "") or "new trick"
            self.say(NAMED_FOR_NOW.format(name=making.name))
            self._spawn(self._finish(making))
            return
        if waiting.kind == "question" and making is not None and making.question is not None:
            making.examples = [making.question.keep]
            making.answered = True
            self._spawn(self._finish(making, plain_only=True))

    def _habits(self) -> None:
        later = getattr(self.life, "later", None)
        happened = list(getattr(later, "happened", None) or [])
        if not happened:
            return
        for entry in self.book.of_kind("habit", "way"):
            try:
                trigger = trigger_from(entry.trigger)
            except BadRequest:
                continue
            if trigger is None:
                continue
            owner = entry.person if entry.kind == "way" else entry.teacher_id
            if owner is None:
                continue
            whom = {"me": owner, "": owner}
            if trigger.who and trigger.who not in ("me", ""):
                person = self.life.company.book.find(trigger.who)
                whom[trigger.who] = person.id if person is not None else None
            hit = next((h for h in happened if match(trigger, h, whom)), None)
            if hit is None:
                continue
            last = self.fired.get(entry.tag, -math.inf)
            if self.mono() - last < HABIT_GAP_S:
                continue
            self.fired[entry.tag] = self.mono()
            asker = self.commands.asker_for(owner)
            if asker.tier == STRANGER and not asker.owner:
                self.record("howto_skipped", name=entry.name, why="the teacher is now a stranger")
                continue
            if self.commands.runner.busy and self.commands.runner.current.asker.id not in (None, owner):
                self.record("howto_skipped", name=entry.name, why="busy")
                continue
            if self.p.permissions.quiet and any(step.get("do") in MOVING for step in entry.steps):
                self.record("howto_skipped", name=entry.name, why="quiet hours")
                continue
            self.record("howto_fired", name=entry.name, event=hit.event)
            self._spawn(self.run_entry(entry, {}, asker, "later", entry.name))

    def offered(self, name: str, words: str, asker: Asker) -> None:
        if asker.own or asker.id is None:
            return
        self.offer = (name, words, asker.id, self.mono() + OFFER_S)

    async def take_route(self, request: Request, asker: Asker, how: str) -> Verdict | None:
        place = request.place or request.thing
        if not place or place in ("there", "start", "before", "home"):
            return None
        for entry in self.book.of_kind("route"):
            if place == entry.name or place in entry.aliases:
                verdict = await self.run_entry(entry, {}, asker, how, place)
                if verdict.yes:
                    self.did(request, asker, how)
                return verdict
        return None

    def register(self, registry) -> None:
        from ..tools.registry import Param, Tool

        async def how_to(args: dict) -> dict:
            return {"howto": self.lookup(str(args.get("about") or ""))}

        registry.register_action(Tool("how_to", "Look up something you were taught or worked out how to do: a move, a way, a word, a habit or a look.", {"about": Param("string", "what to look up", max_length=120)}, how_to))

    def lookup(self, about: str, most: int = 5) -> list[str]:
        here = set(self.life.company.presence.here(self.clock.now()))
        lines = []
        for entry in self.book.closest(about, most + 2):
            if entry.kind == "way" and entry.person not in here:
                continue
            if entry.kind == "move" and entry.link.get("skill"):
                continue
            lines.append(f"{entry.name} ({entry.kind}): {entry.about[:80]}" if entry.about else f"{entry.name} ({entry.kind})")
        for skill in self.life.skills.closest(about):
            if len(lines) >= most:
                break
            lines.append(f"{skill.name} (move): {skill.about[:80]}")
        if lines:
            self.record("how_to_looked", about=len(about), found=len(lines))
        return lines[:most]

    def looks_now(self, what: str, place: str = "", thing: str = "") -> bool | None:
        entry = self.concepts.find(what)
        if entry is None:
            return None
        found = self.looked.get((entry.tag, place or ""))
        if found is not None and self.mono() - found[0] <= LOOKED_KEEP_S:
            return found[1]
        self.look_at = -math.inf
        return None

    async def _look_round(self) -> None:
        if self.session is not None or self.commands.runner.busy:
            return
        room = self.room() or ""
        now = self.mono()
        for entry in self.concepts.all():
            if not self.concepts.sure(entry):
                continue
            value = await self.concepts.state(entry.name, room if entry.look == "place" else "", "")
            if entry.look == "place":
                self.looked[(entry.tag, room)] = (now, value)
            self.looked[(entry.tag, "")] = (now, value)

    def forget(self, person_id: str, names: list) -> None:
        self.book.forget(person_id, names)
        if self.session is not None and self.session.teacher.id == person_id:
            self.session = None
            self.show()
        if self.making is not None and self.making.teacher.id == person_id:
            self.making = None
        if self.waiting is not None and self.waiting.asker.id == person_id:
            self.waiting = None
        for entry in self.book.of_kind("concept"):
            changed_any = False
            for item in entry.prints:
                if item.get("by") == person_id:
                    item["by"] = None
                    changed_any = True
            if changed_any:
                self.book.put(entry)

    async def night(self, local) -> dict:
        merged = []
        entries = self.book.all()
        seen: dict = {}
        for entry in sorted(entries, key=lambda e: (-(e.good - e.bad), e.learned_at)):
            if entry.kind not in ("move", "procedure", "route", "habit", "way"):
                continue
            key = (entry.kind, json.dumps(entry.steps, sort_keys=True) if entry.kind != "route" else json.dumps([[round(p[0], 1), round(p[1], 1)] for p in entry.points]), entry.person, json.dumps(entry.trigger, sort_keys=True))
            keep = seen.get(key)
            if keep is None:
                for other in seen.values():
                    if other.kind == entry.kind and other.person == entry.person and (entry.name in other.name or other.name in entry.name) and _close_steps(other.steps, entry.steps):
                        keep = other
                        break
            if keep is None:
                seen[key] = entry
                continue
            keep.aliases = list(dict.fromkeys(a for a in [entry.name] + entry.aliases + keep.aliases if a and a != keep.name))[:8]
            keep.versions = (list(keep.versions) + [{"steps": entry.steps, "taught_by": entry.taught_by, "at": entry.learned_at, "merged": entry.name}] + list(entry.versions))[-10:]
            keep.good += entry.good
            keep.bad += entry.bad
            keep.examples = (list(keep.examples) + list(entry.examples))[-8:]
            keep.last_used = max(keep.last_used, entry.last_used)
            self.book.remove(entry.name, "merged at night")
            if entry.link.get("skill"):
                self.life.skills.drop(entry.link["skill"])
            self.book.put(keep)
            merged.append((keep.name, entry.name))
        drafts = len(self.book.drafts()) - len(self.book.tidy_drafts())
        self.record("howto_night", merged=len(merged), drafts_dropped=drafts)
        return {"merged": merged, "drafts_dropped": drafts}


def always_private(place: str) -> bool:
    return bool(place) and (place in ALWAYS or place in PRIVATE_NAMES)


def _close_steps(a: list, b: list) -> bool:
    if not a or not b or abs(len(a) - len(b)) > 1:
        return False
    same = sum(1 for x, y in zip(a, b) if x.get("do") == y.get("do") and (x.get("request") or {}).get("kind") == (y.get("request") or {}).get("kind"))
    return same >= max(len(a), len(b)) - 1


def _unit(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(-1.0, min(1.0, number))


def _thing_name(entry: Entry) -> str:
    if entry.kind == "concept":
        return f"what {entry.name} looks like"
    if entry.kind == "word":
        return f"what {entry.name} means"
    if entry.kind == "route":
        return f"the way to the {entry.name}"
    name = shown_name(entry)
    first = name.split(" ", 1)[0]
    if first in ("check", "go", "say", "look", "find", "take", "make", "turn", "spin", "greet", "fetch", "get", "show", "play", "feed", "put", "water"):
        return f"how to {name}"
    return name if name.startswith(("the ", "your ", "my ")) else f"the {name}"


def _called(name: str) -> str:
    first = name.split(" ", 1)[0] if name else ""
    if first in ("check", "go", "say", "look", "find", "take", "make", "turn", "spin", "greet", "fetch", "get", "show", "play", "feed", "put", "water"):
        return f"how to {name}"
    return name if name.startswith(("the ", "your ", "my ")) else f"the {name}"


def _pattern_from_intents(entry: Entry) -> str:
    if not entry.slots:
        return ""
    for example in entry.examples:
        intent = name_from(example.get("intent") or "")
        if intent:
            found = pattern_of(intent, entry.slots)
            if found:
                return found
    return ""


def _changed_requests(steps: list, change: str) -> list | None:
    said = f" {change.lower()} "
    out = json.loads(json.dumps(steps))
    done = False
    swap = {"left": "right", "right": "left", "forward": "back", "back": "forward"}
    if re.search(r" (?:other way|the other way|opposite way|other direction) ", said):
        for step in out:
            target = step["request"] if step.get("do") == "request" else step
            if target.get("way") in swap:
                target["way"] = swap[target["way"]]
                done = True
    if re.search(r" (?:slower|slowly|slow down) ", said):
        for step in out:
            target = step["request"] if step.get("do") == "request" else step
            if target.get("kind") in ("turn", "move") or step.get("do") in ("turn", "move"):
                target["speed"] = "slow"
                done = True
    if re.search(r" (?:faster|quicker|quickly) ", said):
        for step in out:
            target = step["request"] if step.get("do") == "request" else step
            if target.get("kind") in ("turn", "move") or step.get("do") in ("turn", "move"):
                target["speed"] = "quick"
                done = True
    return out if done else None
