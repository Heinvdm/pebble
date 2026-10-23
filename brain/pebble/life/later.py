import logging
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ..activities.commands import Plan
from ..activities.gate import PEBBLE, Asker, Verdict, decide, decide_later, may_cancel
from ..people.trust import STRANGER
from ..tact import private_matter
from ..understand.logic import (
    DAY_NAMES,
    tidy,
    clock_short,
    clock_words,
    cond_words,
    event_words,
    first_words,
    happened_words,
    missed_words,
    moment_words,
    reminder_words,
    step_words,
    tree_words,
    wake_up,
    when_words,
    whole_words,
)
from ..understand.request import DAY_NAMES as DAY_CODES
from ..understand.request import MOVING, Request, When, from_dict
from ..understand.resolve import Reading
from .agenda import LATE_BY_S, TRIGGER_MOST_S, TRIGGER_S, Agenda, Item, kind_of, words_of
from .conditions import choose, evaluate, spoken_to_asker, watched
from .events import Feed, LifeSenses, match
from .messages import Messenger
from .times import hour_of, instant, part_setting, settle_clock, spoken_clock, time_of

log = logging.getLogger(__name__)

WINDOW_S = 30.0
QUESTION_S = 20.0
PAUSE_S = 20.0
JUMP_S = 120.0
OFF_S = 120.0
SWEEP_S = 60.0
WHILE_EVERY_S = 3.0
CHECK_IN_S = 300.0
WAKE_EVERY_S = 60.0
WAKE_TRIES = 10
WAKE_GENTLE = 3
MATCHED_S = 3600.0
MATCHED_MOST = 3
SCREEN_S = 600.0
SCREEN_HOLD_S = 30.0
BUILT = frozenset({"when", "on", "if", "while", "until", "list_later", "cancel_later", "change_later"})
NO = re.compile(r"^(?:no|nope|nah|no thanks|no thank you|cancel(?: it| that)?|never mind|nevermind|forget it|forget that|scrap that|don'?t|leave it)$")
YES = re.compile(r"^(?:yes|yeah|yep|yup|sure|please|ok|okay|alright|go on|go ahead|do it|change it|change|move it|instead|the new one|new one|just the new one|the new time)\b")
BOTH = re.compile(r"^(?:both|keep both|both of them|all of them|all|keep them both|the two of them)\b")
UP = re.compile(r"^(?:i'?m up|i am up|i'?m awake|i am awake|i'?m getting up|ok(?:ay)?|stop|thanks|thank you|alright|yes|yeah|enough|morning|good morning|all right)\b")
GO_ON = re.compile(r"^(?:go on|tell me|yes|yeah|what is it|what's that|okay|ok|sure|what)\b")
ABOUT_ME = re.compile(r"^(?:what (?:have|did) (?:people|anyone|someone) asked? you about me|(?:are you|is anyone|is someone|is somebody) keeping tabs on me|who (?:has )?asked you about me|has anyone asked you (?:about|to keep an eye on|to watch) me|what are you watching (?:for )?(?:about )?me)\b")
FOUND = re.compile(r"^(?:so |well |and )?(?:what did you (?:find|see|find out)|what's the answer|what is the answer|did you check(?: it)?|what did it look like)$")
CANCEL_THAT = re.compile(r"^(?:cancel|stop|drop|delete) (?:it|that|them|those|that one)\b")
INSTEAD = re.compile(r"^(?:no,? |actually,? |sorry,? |oh,? )?(?:make it |make that |change it to |at |on )?(?P<what>.+?)(?: instead| please)?(?:,? not (?P<old>[a-z' ]+))?$")
DAYS_ONLY = re.compile(r"^(?:on |every )?(?:mon|tues|wednes|thurs|fri|satur|sun)days?(?:,? (?:and |or )?(?:mon|tues|wednes|thurs|fri|satur|sun)days?)*$")
CORRECTION_WORDS = 7
LIST = re.compile(r"^(?:(?:what|which) (?:reminders|alarms|wake ?ups?|things) (?:do i have|have i got|have i set|are (?:there|set))|what (?:have i asked you|did i ask you) to do later|what are you (?:keeping|going to do) (?:for me )?later|(?:list|tell me|read me) (?:all )?my reminders)$")
CANCEL_ALL = re.compile(r"^(?:(?:stop|cancel|clear|delete|drop) (?:all )?(?:of )?my reminders|cancel everything(?: you were going to do)? later)$")
CANCEL_ONE = re.compile(r"^(?:(?:cancel|stop|delete|drop|forget) (?:the |my )(?P<what>.+?) (?:reminder|one|wake ?up|alarm)|don'?t remind me about (?P<what2>.+?)(?: any ?more)?)$")
CANCEL_BARE = re.compile(r"^(?:cancel|stop|delete|drop|forget) (?:my|the|that) (?:reminder|wake ?up|alarm)$")
SKIP = re.compile(r"^(?:(?:no|skip(?: the)?) (?P<what>.+?) reminder (?:this|next) (?:week|time)|skip (?:the |my )(?P<what2>.+?) (?:reminder|one) (?:this|next) (?:week|time))$")
CANCEL_MESSAGE = re.compile(r"^(?:(?:cancel|forget|drop|delete|scrap) (?:my |the |that )?messages?(?: (?:to|for) (?P<who>[a-z]+))?|don'?t tell (?P<who2>[a-z]+)(?: after all| any ?more| anything)?)$")
CHANGE = re.compile(r"^(?:change|move|make) (?:the |my )(?P<what>.+?) (?:reminder|one) (?:to|at|for) (?P<when>.+)$")
ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "last": -1}
NUMBERS = {2: "Two", 3: "Three", 4: "Four", 5: "Five"}
USEFUL_MORNING = datetime.min.time().replace(hour=7)


def plain(text: str) -> str:
    out = " ".join((text or "").lower().replace("’", "'").split())
    return re.sub(r"^(?:hey |oi |um |uh |ok |okay )?(?:pebble,? )?", "", out).strip(" .!?,")


@dataclass
class Due:
    item: int
    person: str | None
    label: str
    text: str
    due: float
    useful: float
    private: bool = False
    late: str = ""
    sought: float = -math.inf
    offered: bool = False
    holiday: str = ""
    note: str = ""
    kind: str = "reminder"
    by: str | None = None
    by_label: str = ""
    remind: bool = False


@dataclass
class Move:
    item: int
    steps: list
    by: str | None
    label: str
    due: float
    late_by: float
    why: str = ""
    made: float | None = None


@dataclass
class Watch:
    activity: object
    kind: str
    asker: Asker
    cond: object = None
    trigger: object = None
    since: float = 0.0
    checked: float = 0.0


@dataclass
class Wake:
    person: str | None
    label: str
    item: int
    next_at: float
    tries: int = 0


@dataclass
class Question:
    kind: str
    person: str | None
    until: float
    options: list = field(default_factory=list)
    request: Request | None = None
    asker: Asker | None = None


class Later:
    def __init__(self, life):
        self.life = life
        clock = life.p.clock
        self.clock = clock
        self.agenda = Agenda(life.p.store, clock)
        self.feed = Feed(clock.now())
        self.senses = LifeSenses(life, self.feed)
        self.windows: dict = {}
        self.question: Question | None = None
        self.out: list[Due] = []
        self.moves: list[Move] = []
        self.watches: list[Watch] = []
        self.wakes: list[Wake] = []
        self.wall = clock.now()
        self.mono = clock.monotonic()
        self.swept = -math.inf
        self.started = False
        self.happened: list = []
        self.messenger = Messenger(self)
        self.hush = False

    @property
    def commands(self):
        return self.life.commands

    @property
    def company(self):
        return self.life.company

    def record(self, kind: str, **data) -> None:
        self.life.p.blackbox.record(kind, **data)

    def note(self, text: str, major: bool = False) -> None:
        if self.hush:
            return
        self.commands.note(text, major)

    def say(self, text: str) -> None:
        if not text or self.hush:
            return
        self.commands.recent.append(f"pebble: {text[:160]}")
        del self.commands.recent[:-6]
        self.commands._spawn(self.commands.speak(text, False))

    def shout(self, text: str) -> None:
        self.commands._spawn(self.life.p.voice.say(text, whisper=False))

    def names(self) -> tuple:
        return tuple(self.life.known_names())

    def local(self, ts: float | None = None) -> datetime:
        return self.clock.local(self.clock.now() if ts is None else ts)

    def asker_of(self, item: Item) -> Asker:
        if item.by is None:
            return PEBBLE
        return self.commands.asker_for(item.by)

    def label_of(self, person_id: str | None, fallback: str = "") -> str:
        person = self.company.book.get(person_id) if person_id else None
        return person.label if person is not None else fallback

    def whom(self, item: Item) -> dict:
        out = {"me": item.by, "": item.by}
        request = item.req()
        for trigger in [request.on] + [step.until_on for step in request.steps()]:
            if trigger is None:
                continue
            for one in trigger.first_of or (trigger,):
                if one.who and one.who not in out:
                    person = self.company.book.find(one.who)
                    out[one.who] = person.id if person is not None else None
        return out

    def read(self, asker_id: str | None):
        answers = self.commands.checks.answers(asker_id, self.clock.now())
        return lambda cond: self.senses.state(cond, asker_id, answers)

    def _told(self, choice, asker: Asker) -> bool:
        if not choice.unsure or any(leaf.state != "result" for leaf in choice.unsure):
            return False
        now = self.clock.now()
        for leaf in choice.unsure:
            found = self.commands.checks.last(asker.id, now, leaf.name) or self.commands.checks.last(asker.id, now)
            if found is None or not found.told:
                return False
        return True

    async def route(self, request: Request, asker: Asker, how: str) -> Verdict | None:
        request = tidy(request)
        if how not in ("then", "later"):
            problem = self.messenger.refusal(request, asker, self.commands.question_text)
            if problem is not None:
                return await self._refuse(request, asker, *problem)
        if request.kind in ("list_later", "cancel_later", "change_later"):
            return await self._manage(request, asker)
        if request.when is not None or request.on is not None:
            if how == "later":
                return None
            return await self.keep(request, asker, how)
        if request.branch:
            return await self._branch(request, asker, how)
        if request.kind == "say_to" and request.who in ("", "me"):
            if how not in ("then", "later"):
                said = "When should I remind you? Say it again with a time, like: remind me at six to call Mum."
                self.say(said)
                return Verdict("ask", "a reminder needs a time or something to wait for", said)
            return await self._say_now(request, asker, how)
        if request.kind == "say_to":
            return await self.messenger.now(request, asker, how)
        if request.while_ is not None or request.until_on is not None or request.until == "asked":
            return await self._watched(request, asker, how)
        return None

    async def keep(self, request: Request, asker: Asker, how: str) -> Verdict:
        now = self.clock.now()
        if asker.own and any(step.kind == "say_to" for step in request.steps()):
            return Verdict("no", "reminders are for the people who ask for them", "")
        first = decide_later(request, asker)
        if not first.yes:
            return await self._refuse(request, asker, first.reason, first.say)
        line = self.senses.can_sense(request.on) if request.on is not None else ""
        for step in request.steps():
            if not line and step.until_on is not None:
                line = self.senses.can_sense(step.until_on)
        if line:
            return await self._refuse(request, asker, "you can't sense that happening", line)
        seen = watched(request, asker.id, self.company.book.find)
        if seen.unknown:
            who = seen.unknown[0].title()
            return await self._refuse(request, asker, f"you don't know who {who} is", f"I don't know who {who} is, so I can't tell when they come and go.")
        seen.names = [p for p in seen.names if not self.messenger.only_told(request, p)]
        adults = [p for p in seen.names if not p.is_child]
        children = [p for p in seen.names if p.is_child]
        verdict = decide_later(request, asker, bool(adults), bool(children))
        if not verdict.yes:
            return await self._refuse(request, asker, verdict.reason, verdict.say)
        full = self.agenda.full(asker.id)
        if full:
            return await self._refuse(request, asker, "you are keeping as much for later as you can", full)
        if request.when is not None:
            request = request.with_(when=settle_clock(request.when, self.commands.question_text, self.local(now).replace(tzinfo=None)))
        kind = kind_of(request)
        text = " ".join(step.text for step in request.steps() if step.text)
        aimed = asker.id
        if kind == "message":
            told = {step.who for step in self.messenger.told(request)}
            found = self.company.book.find(next(iter(told))) if len(told) == 1 else None
            aimed = found.id if found is not None else None
        item = self.agenda.new(request, asker.id, asker.label, asker.tier, kind, aimed, [p.id for p in seen.names], private_matter(text), words_of(request), asker.family)
        item.remind = kind == "message" and bool(re.search(r"\bremind\b", (self.commands.question_text or "").lower()))
        problem = self.agenda.plan(item, now)
        if problem:
            return await self._refuse(request, asker, "the time does not work", problem)
        same, other = self.agenda.same(item)
        if same is not None:
            said = f"You already have that one: {self._short_when(same)}."
            self.say(said)
            self.record("later_same", item=same.id, person=asker.id)
            return Verdict("yes", "they already had that one", said)
        if other is not None:
            said = f"You've already got that one, {self._short_when(other)}. Do you want it {self._short_when(item)} instead, or both?"
            self.question = Question("keep_both", asker.id, now + QUESTION_S, [other, item], request, asker)
            self.say(said)
            return Verdict("ask", "the same words at a different time", said)
        return self._store(item, asker)

    def for_whom(self, request: Request, asker: Asker) -> tuple[Asker, Request]:
        if not asker.own or (request.when is None and request.on is None):
            return asker, request
        asking = self.company.asking or {}
        for step in request.steps():
            if step.kind != "say_to" or step.who in ("", "me"):
                continue
            person = self.company.book.find(step.who)
            if person is not None and person.id in asking:
                return self.commands.asker_for(person.id, bool(asking[person.id])), _with_me(request, step.who)
        return asker, request

    def _store(self, item: Item, asker: Asker) -> Verdict:
        now = self.clock.now()
        self.agenda.add(item)
        self.agenda.save(force=True)
        said = self.read_back(item)
        self.windows[asker.id] = (item.id, now + WINDOW_S)
        self.record("later_added", item=item.id, what=item.kind, person=asker.id, tier=asker.tier, repeats=item.repeats, on=bool(item.req().on), at=round(item.next_at, 1) if item.next_at else None)
        if asker.own:
            self.note(f"you kept something for later yourself: {said}")
            return Verdict("yes", "your own idea, kept for later", said)
        self.note(f"{asker.label} asked you to keep something for later ({item.kind}); you read it back: {said}")
        self.say(said)
        return Verdict("yes", f"{asker.label} may leave things for later", said)

    async def _refuse(self, request: Request, asker: Asker, reason: str, say: str) -> Verdict:
        self.record("later_refused", person=asker.id, tier=asker.tier, reason=reason)
        if not asker.own:
            what = "pass on a message" if self.messenger.told(request) else "keep something for later"
            self.note(f"{asker.label} asked you to {what}; you said no ({reason})")
            self.life.p.face.show("thinking")
            self.say(say)
            if not self.hush:
                self.commands.refused_to(asker, say, what)
        return Verdict("no", reason, say)

    def lead(self, item: Item) -> str:
        request = item.req()
        when = request.when
        now = self.local()
        first = self.local(item.next_at) if item.next_at is not None and request.on is None else None
        parts = self.agenda.parts_for(item.by)
        lead = when_words(when, first, now.replace(tzinfo=None), hour_of(when, parts)) if when is not None else ""
        if when is not None and request.on is not None:
            armed = self.local(item.armed) if item.armed else None
            lead = moment_words(armed.replace(tzinfo=None), now.replace(tzinfo=None)) if armed and not when.repeats else lead
            lead = f"{lead}, {event_words(request.on)}" if lead else event_words(request.on)
        elif request.on is not None:
            lead = event_words(request.on)
        return lead

    def read_back(self, item: Item) -> str:
        request = item.req()
        core = request.with_(when=None, on=None)
        if item.kind == "message" and not core.branch:
            sentence = self.messenger.read_back(item, self.lead(item))
        else:
            sentence = whole_words(core, self.lead(item), self.names())
        out = f"Okay: {sentence[:1].lower() + sentence[1:]}."
        now = self.local().replace(tzinfo=None)
        when = request.when
        if request.on is not None:
            span = (item.runs_out or 0) - (item.armed or 0)
            if abs(span - TRIGGER_S) < 120:
                out += " I'll watch for that until this time tomorrow."
            elif span >= TRIGGER_MOST_S - 120:
                out += " I'll watch for that for up to a week."
        elif when is not None and when.repeats and item.next_at is not None:
            out += " " + first_words(self.local(item.next_at).replace(tzinfo=None), now)
        if item.next_at is not None and item.key[10:11] == "T" and item.key[11:16] != self.local(item.next_at).strftime("%H:%M"):
            out += f" The clocks go forward that night, so {clock_short(item.key[11:16])} doesn't happen; it'll be at {clock_short(self.local(item.next_at).strftime('%H:%M'))}."
        if item.kind == "action":
            quiet = self.life.quiet_hours
            if item.next_at is not None and quiet.contains(self.local(item.next_at)):
                out += f" That's in my quiet time, so I'll do it when my quiet time ends at {clock_words(quiet.end.strftime('%H:%M'))}."
            elif when is not None and when.repeats:
                out += f" I don't move about in my quiet time ({clock_short(quiet.start.strftime('%H:%M'))} to {clock_short(quiet.end.strftime('%H:%M'))}), so I'll skip any that fall in it."
        if item.kind == "message" and item.next_at is not None and self.life.quiet_hours.contains(self.local(item.next_at)):
            out += f" That's in my quiet time, so I'll pass it on when my quiet time ends at {clock_words(self.life.quiet_hours.end.strftime('%H:%M'))}."
        return out

    def _short_when(self, item: Item) -> str:
        request = item.req()
        if request.on is not None:
            return event_words(request.on)
        return self.lead(item)

    async def _manage(self, request: Request, asker: Asker) -> Verdict:
        now = self.clock.now()
        if asker.own:
            return Verdict("no", "only the people who asked look after their own things for later", "")
        if asker.tier == STRANGER:
            said = "I'm not keeping anything for you."
            self.say(said)
            return Verdict("no", "a stranger keeps nothing for later", said)
        if request.kind == "list_later":
            said = self.listing(asker)
            self.say(said)
            self.note(f"{asker.label} asked what you have for later; you told them")
            return Verdict("yes", "they may hear their own things for later", said)
        window = self.windows.get(asker.id)
        fresh = window[0] if window and window[1] >= now else None
        mine = [item for item in self.agenda.waiting() if may_cancel(item, asker)]
        if not request.text and fresh is not None and request.scope != "all":
            found = [item for item in mine if item.id == fresh]
        elif request.scope == "all" and not request.text:
            found = [item for item in mine if item.by == asker.id]
        else:
            found = self.agenda.match(request.text, mine)
        if not found:
            others = self.agenda.match(request.text, self.agenda.waiting()) if request.text else []
            if others:
                owner = others[0].by_label
                said = f"That one's {owner}'s, so only they or the person it's for can change it."
            else:
                said = "I can't find one like that." + (" " + self.listing(asker) if self.agenda.mine(asker.id) else " I'm not keeping anything for you just now.")
            self.say(said)
            return Verdict("no", "no item matched", said)
        if len(found) > 1 and not (request.kind == "cancel_later" and request.scope == "all"):
            said = "Which one: " + self._choices(found) + "?"
            self.question = Question("which", asker.id, now + QUESTION_S, found, request, asker)
            self.say(said)
            return Verdict("ask", "two or more items matched", said)
        return self._apply(request, asker, found)

    def _choices(self, items: list[Item]) -> str:
        said = [(f"{reminder_words(item.words, self.names())} " if item.words else "the one ") + self._short_when(item) for item in items]
        return ", ".join(said[:-1]) + ", or " + said[-1] if len(said) > 1 else said[0]

    def _apply(self, request: Request, asker: Asker, items: list[Item]) -> Verdict:
        now = self.clock.now()
        if request.kind == "change_later":
            item = items[0]
            if request.when is None:
                said = "What should I change it to?"
                self.say(said)
                return Verdict("ask", "no new time", said)
            self._change(item, request.when, now)
            self.agenda.save(force=True)
            said = self.read_back(item).replace("Okay: ", "Okay, now: ", 1)
            self.windows[asker.id] = (item.id, now + WINDOW_S)
            self.record("later_changed", item=item.id, person=asker.id)
            self.say(said)
            return Verdict("yes", "changed", said)
        if request.scope == "next" and len(items) == 1 and items[0].repeats:
            item = items[0]
            self.agenda.skip_next(item, now)
            self.agenda.save(force=True)
            following = f" The next one is {moment_words(self.local(item.next_at).replace(tzinfo=None), self.local().replace(tzinfo=None))}." if item.next_at else ""
            said = f"Okay, I'll skip that one this time.{following}"
            self.record("later_skipped", item=item.id, person=asker.id, asked=True)
            self.say(said)
            return Verdict("yes", "skipped once", said)
        for item in items:
            self.agenda.remove(item)
            self.windows = {k: v for k, v in self.windows.items() if v[0] != item.id}
            self.out = [d for d in self.out if d.item != item.id]
            self.moves = [m for m in self.moves if m.item != item.id]
            self.record("later_cancelled", item=item.id, person=asker.id, by=item.by)
            if item.by and item.by != asker.id:
                self.agenda.owe(item.by, f"{asker.label} cancelled the one {self._short_when(item)}" + (f" about {item.words}." if item.words else "."), now)
        self.agenda.save(force=True)
        said = "Okay, I've cancelled it." if len(items) == 1 else f"Okay, I've cancelled all {len(items)} of them."
        self.say(said)
        return Verdict("yes", "cancelled", said)

    def _change(self, item: Item, new: When, now: float) -> None:
        request = item.req()
        old = (request.when.as_dict() if request.when is not None else {})
        update = new.as_dict()
        if "at" in update or "part" in update:
            old.pop("at", None)
            old.pop("part", None)
        if "days" in update:
            old.pop("date", None)
        if "date" in update:
            for key in ("days", "month_day", "every_weeks"):
                old.pop(key, None)
        if "in_s" in update:
            old = {}
            item.made = now
        old.update(update)
        data = request.as_dict()
        data["when"] = old
        item.request = from_dict(data).as_dict()
        item.last_key = ""
        self.agenda.plan(item, now)

    def listing(self, asker: Asker) -> str:
        own = self.agenda.mine(asker.id)
        others = [item for item in self.agenda.waiting() if item.by != asker.id] if asker.owner else []
        aimed = [item for item in self.agenda.waiting() if item.aimed == asker.id and item.by != asker.id and item not in others]
        if not own and not others and not aimed:
            return "I'm not keeping anything for later for you."
        out = []
        shown = asker.id is not None and self._only_family(asker.id, self.clock.now())
        if own:
            count = "one thing" if len(own) == 1 else f"{len(own)} things"
            said = [self._item_words(item, shown) for item in own]
            said = [line[:1].lower() + line[1:] for line in said]
            out.append(f"You've got {count} for later: " + "; ".join(said) + ".")
        for item in aimed:
            what = "a reminder" if item.remind else "a message"
            lead = self._short_when(item)
            out.append(f"{item.by_label} has {what} for you" + (f", {lead}." if lead else " that I'm keeping for when I see you."))
        if others:
            by = {}
            for item in others:
                by.setdefault(item.by_label, []).append(item)
            for label, items in by.items():
                said = [f"{self._short_when(item)}" + (", a private one" if item.private else (f" about {item.words}" if item.words else "")) for item in items]
                out.append(f"{label} has {len(items)}: " + "; ".join(said) + ".")
        return " ".join(out)

    def _item_words(self, item: Item, shown: bool) -> str:
        if self.messenger.held(item):
            person = self.company.book.get(item.aimed) if item.aimed else None
            label = person.label if person is not None else "someone"
            text = item.req().text
            return f"a message for {label}" + ("" if item.private and not shown or not text else f": {text}")
        if item.private and not shown:
            return f"{self.lead(item)}, a private reminder"
        if item.kind == "message" and not item.req().branch:
            return self.messenger.read_back(item, self.lead(item))
        return whole_words(item.req().with_(when=None, on=None), self.lead(item), self.names())

    def about_me(self, person_id: str, label: str) -> str:
        items = [item for item in self.agenda.waiting() if person_id in item.about]
        if not items:
            return "Nobody has asked me to keep an eye on your comings and goings."
        out = []
        for item in items:
            out.append(f"{item.by_label} has one that depends on whether you're around: {self._short_when(item)}")
        return ". ".join(out) + ". You can ask me to cancel it."

    async def _branch(self, request: Request, asker: Asker, how: str) -> Verdict:
        choice = choose(request, self.read(asker.id))
        self.record("later_branch", value=choice.value, unsure=len(choice.unsure), person=asker.id)
        if choice.held:
            held = choice.held_words(request, lambda steps: step_words_all(steps, self.names()))
            said = f"{held[:1].upper() + held[1:]}." if self._told(choice, asker) else f"{choice.couldnt()}, {held}."
            if not asker.own:
                self.say(said)
            self.note(f"you could not tell part of what {asker.label} asked about, so you did not act on it: {said}")
            await self._next(asker)
            return Verdict("no", "you could not tell, and you never guess for a step that moves you", said)
        if choice.both:
            said = self._hedged(request, choice, asker)
            self.say(said)
            await self._next(asker)
            return Verdict("yes", "you could not tell, so you said both", said)
        steps = flatten(choice.steps)
        if not steps:
            said = ""
            if not asker.own and request.then:
                reason = cond_words(request.if_, True)
                said = f"{reason[:1].upper() + reason[1:]}, so I won't {step_words_all(request.then, self.names())}."
                self.say(said)
            self.note(f"{asker.label}'s condition ({cond_words(request.if_)}) was {'false' if choice.value is False else 'true'}, so there was nothing to do")
            await self._next(asker)
            return Verdict("yes", "nothing to do", said)
        return await self._chain(steps, asker, how)

    async def _chain(self, steps: list, asker: Asker, how: str) -> Verdict:
        if not steps:
            await self._next(asker)
            return Verdict("yes", "nothing more to do", "")
        first, rest = steps[0], list(steps[1:])
        if first.branch:
            if rest:
                plan = self.commands.plan
                kept = plan.steps if plan is not None and how == "then" else []
                self.commands.plan = Plan(asker, rest + kept)
            return await self.commands.act(first, asker, "then")
        return await self.commands.act(first.with_(then=tuple(rest)), asker, "then" if how == "then" else how)

    def _hedged(self, request: Request, choice, asker: Asker) -> str:
        cond = request.if_
        then = "; ".join(_spoken(step, self.names()) for step in request.then)
        other = "; ".join(_spoken(step, self.names()) for step in request.else_)
        out = f"{choice.couldnt()}."
        if then:
            out += f" If {cond_words(cond)}: {then}."
        if other:
            out += f" If not: {other}."
        return out

    async def _next(self, asker: Asker) -> None:
        plan = self.commands.plan
        if plan is None or not plan.steps or self.commands.runner.busy:
            return
        step = plan.steps.pop(0)
        if not plan.steps:
            self.commands.plan = None
        self.commands._spawn(self.commands.act(step, self.commands.fresh(asker), "then"))

    async def _say_now(self, request: Request, asker: Asker, how: str) -> Verdict:
        said = _spoken(request, self.names()) or "Here I am."
        said = said[:1].upper() + said[1:]
        said = said if said.endswith((".", "!", "?")) else said + "."
        self.say(said)
        self.note(f"you told {asker.label}: {said}" if not asker.own else f"you said: {said}")
        if request.then:
            return await self._chain(list(request.then), asker, "then")
        await self._next(asker)
        return Verdict("yes", "you said it", said)

    async def _watched(self, request: Request, asker: Asker, how: str) -> Verdict:
        now = self.clock.now()
        if request.until_on is not None:
            line = self.senses.can_sense(request.until_on)
            if line:
                self.say(line)
                return Verdict("no", "you can't sense that happening", line)
        if request.while_ is not None:
            value = evaluate(request.while_, self.read(asker.id))
            if value is False or (value is None and request.kind in MOVING):
                said = f"It isn't true now that {cond_words(request.while_)}, so I won't start." if value is False else f"I can't tell whether {cond_words(request.while_)}, so I won't start."
                self.say(said)
                return Verdict("no", "the condition does not hold now", said)
        plain_step = request.with_(while_=None, until_on=None)
        verdict = await self.commands.act(plain_step, asker, how, routed=True)
        current = self.commands.runner.current
        if verdict.yes and current is not None and current.request.kind == request.kind:
            if request.while_ is not None:
                self.watches.append(Watch(current, "while", asker, cond=request.while_, since=now, checked=now))
            if request.until_on is not None:
                self.watches.append(Watch(current, "until", asker, trigger=request.until_on, since=now, checked=now))
            if request.until == "asked" and not asker.own:
                self.watches.append(Watch(current, "asked", asker, since=now, checked=now))
        return verdict

    async def heard(self, heard) -> Reading | None:
        text = plain(heard.text)
        person = heard.person_id
        now = self.clock.now()
        if not text:
            return None
        done = Reading(Request("chat"), source="rules", answered=True)
        for wake in list(self.wakes):
            if person is not None and wake.person == person:
                self.wakes.remove(wake)
                self.record("later_wake_answered", item=wake.item, tries=wake.tries)
                if UP.match(text):
                    self.say("Good morning!")
                    return done
        setting = part_setting(text)
        if setting is not None and person is not None:
            return self._set_part(person, heard, *setting)
        offered = [due for due in self.out if due.person == person and due.offered]
        if offered and GO_ON.match(text):
            for due in offered:
                due.offered = False
                due.private = False
            self._deliver(now, force=person)
            return done
        question = self.question
        if question is not None and question.until < now:
            self._expire_question()
            question = None
        if question is not None and person is not None and question.person == person:
            answered = await self._answer(question, text)
            if answered:
                return done
        window = self.windows.get(person)
        if window is not None and window[1] >= now:
            fixed = await self._correct(person, window[0], text)
            if fixed:
                return done
        managed = managing(text)
        if managed is not None and person is not None:
            await self._manage(managed, self.commands.asker_for(person, bool(getattr(heard, "sure", False))))
            return done
        found = self.commands.checks.last(person, now) if person is not None and FOUND.match(text) else None
        if found is not None:
            found.told = True
            self.say(found.line)
            self.record("check_told", person=person, answer=found.answer)
            return done
        if person is not None and ABOUT_ME.match(text):
            label = self.label_of(person, "you")
            said = self.about_me(person, label)
            items = [item for item in self.agenda.waiting() if person in item.about]
            if items:
                self.question = Question("about_me", person, now + QUESTION_S, items, None, self.commands.asker_for(person))
            self.say(said)
            self.record("later_about_me", person=person, items=len(items))
            return done
        return None

    def _set_part(self, person: str, heard, part: str, at: str, everyone: bool) -> Reading:
        asker = self.commands.asker_for(person)
        word = part.replace("_", " ")
        if asker.tier == STRANGER:
            self.say("I only keep times like that for people I know.")
        elif everyone and not asker.owner:
            self.agenda.set_part(person, part, at, False)
            self.say(f"Okay, {word} means {clock_words(at)} for you. Only the owner can change it for everyone.")
        else:
            self.agenda.set_part(person, part, at, everyone)
            self.say(f"Okay, {word} means {clock_words(at)} {'for everyone here' if everyone else 'for you'} now.")
        self.agenda.save(force=True)
        self.record("later_part", person=person, part=part, everyone=everyone)
        return Reading(Request("chat"), source="rules", answered=True)

    async def _answer(self, question: Question, text: str) -> bool:
        if question.kind == "keep_both":
            old, new = question.options
            asker = question.asker
            if NO.match(text):
                self.question = None
                self.say("Okay, I'll leave it as it was.")
                return True
            if BOTH.match(text):
                self.question = None
                self._store(new, asker)
                return True
            if YES.match(text):
                self.question = None
                self._change(old, new.req().when or When(), self.clock.now())
                self.agenda.save(force=True)
                said = self.read_back(old).replace("Okay: ", "Okay, now: ", 1)
                self.windows[asker.id] = (old.id, self.clock.now() + WINDOW_S)
                self.say(said)
                return True
            return False
        if question.kind == "checkin":
            watch = question.options[0]
            if NO.match(text) or re.match(r"^(?:no|nah|nope|enough|that's enough|i'?m done|i'?ve had enough|stop)\b", text):
                self.question = None
                if self.commands.runner.current is watch.activity:
                    self.commands.runner.end("done", f"{watch.asker.label} said they had had enough", "Okay, that was fun!")
                return True
            if YES.match(text) or re.match(r"^(?:yes|yeah|keep going|more)\b", text):
                self.question = None
                self.say("Yay!")
                return True
            return False
        if question.kind == "about_me":
            if CANCEL_THAT.match(text) or NO.match(text) and text.startswith("cancel"):
                self.question = None
                self._apply(Request("cancel_later"), question.asker, list(question.options))
                return True
            return False
        if question.kind == "which":
            options = question.options
            chosen = None
            if NO.match(text):
                self.question = None
                self.say("Okay, I'll leave them as they are.")
                return True
            if BOTH.match(text):
                chosen = list(options)
            else:
                for word, index in ORDINALS.items():
                    if re.search(rf"\b{word}\b", text):
                        chosen = [options[index]]
                        break
                if chosen is None:
                    found = self.agenda.match(text, options)
                    if 0 < len(found) < len(options):
                        chosen = found
            if chosen is None:
                return False
            self.question = None
            self._apply(question.request, question.asker, chosen if question.request.kind == "cancel_later" else chosen[:1])
            return True
        return False

    def _expire_question(self) -> None:
        question = self.question
        self.question = None
        if question is None or question.kind in ("checkin", "about_me"):
            return
        self.say("I'll leave it, then.")
        self.record("later_question_expired", what=question.kind, person=question.person)

    async def _correct(self, person: str, item_id: int, text: str) -> bool:
        item = next((i for i in self.agenda.waiting() if i.id == item_id), None)
        if item is None:
            return False
        asker = self.commands.asker_for(person)
        if NO.match(text):
            self.windows.pop(person, None)
            self._apply(Request("cancel_later"), asker, [item])
            return True
        new = self._spoken_change(item, text)
        if new is None:
            return False
        self._apply(Request("change_later", when=new), asker, [item])
        return True

    def _spoken_change(self, item: Item, text: str) -> When | None:
        found = INSTEAD.match(text)
        if found is None:
            return None
        what = found.group("what").strip(" ,")
        if len(text.split()) > CORRECTION_WORDS:
            return None
        if DAYS_ONLY.match(what):
            return When(days=_days_in(what))
        clock = spoken_clock(what, self._old_time(item))
        if clock:
            return When(at=clock)
        return None

    def _old_time(self, item: Item) -> str:
        when = item.when
        if when is None:
            return ""
        return time_of(when, self.agenda.parts_for(item.by))

    def tick(self, quiet: bool) -> None:
        now = self.clock.now()
        mono = self.clock.monotonic()
        jump = (now - self.wall) - (mono - self.mono)
        self.wall, self.mono = now, mono
        if not self.started:
            self.started = True
            self._missed(now)
            self.messenger.restore(now)
        elif abs(jump) > JUMP_S:
            self._jumped(jump, now)
        if mono - self.swept >= SWEEP_S:
            self.swept = mono
            self._sweep(now)
        happened = self._sense(now)
        self.happened = happened
        if self.question is not None and self.question.until < now:
            self._expire_question()
        self.windows = {k: v for k, v in self.windows.items() if v[1] >= now}
        self._triggers(now, happened)
        for item in self.agenda.due(now):
            self._due(item, now, quiet)
        self._watch(now, happened)
        self._wake(now)
        self._deliver(now)
        self._move(now, quiet)
        self._owed(now)
        self.agenda.save()

    def _sense(self, now: float) -> list:
        life = self.life
        seen = []
        presence = self.company.presence
        for person in self.company.book.people.values():
            seen.append((person.id, person.label, presence.last_present(person.id)))
        happened = self.feed.people(now, seen)
        try:
            labels = life.watcher.in_view()
        except Exception:
            labels = []
        happened += self.feed.seen(now, labels)
        happened += self.feed.drain()
        unique = []
        for item in happened:
            if item not in unique:
                unique.append(item)
        return unique

    def talked(self, now: float | None = None) -> None:
        self.feed.talk(self.clock.now() if now is None else now)

    def sound(self, kind: str) -> None:
        self.feed.sound(self.clock.now(), kind)

    def ended(self, activity, ending) -> None:
        now = self.clock.now()
        self.feed.done(now, activity.kind)
        self.watches = [w for w in self.watches if w.activity is not activity]
        who = getattr(activity, "report_to", None)
        if who and ending.say and not self.senses.with_pebble(who, now):
            said = ending.say if ending.say.startswith(("I ", "I'")) else ending.say[:1].lower() + ending.say[1:]
            self.agenda.owe(who, said, now)

    def forget(self, person_id: str, names: list) -> None:
        gone = self.agenda.forget(person_id, names)
        self.feed.forget(person_id)
        self.out = [d for d in self.out if d.person != person_id and d.by != person_id]
        self.moves = [m for m in self.moves if m.by != person_id]
        self.wakes = [w for w in self.wakes if w.person != person_id]
        self.windows.pop(person_id, None)
        self.agenda.save(force=True)
        self.record("later_forgotten", items=len(gone))

    def save(self, force: bool = False) -> None:
        self.agenda.save(force=force)

    def _missed(self, now: float) -> None:
        seen = self.agenda.seen_at
        if seen is None or now - seen <= OFF_S:
            for item in self.agenda.waiting():
                if item.next_at is None and item.req().on is None:
                    self.agenda.schedule(item, now)
            return
        for item in self.agenda.waiting():
            if item.next_at is not None and seen < item.next_at <= now - 1.0:
                self.record("later_missed", item=item.id, what=item.kind)
                self._fire(item, now, missed=True)
        self.record("later_off", seconds=round(now - seen))

    def _jumped(self, jump: float, now: float) -> None:
        self.agenda.shift(jump)
        if jump < 0:
            self.agenda.recompute(now)
        self.record("clock_jump", seconds=round(jump))
        self.note(f"your clock jumped by about {round(abs(jump) / 60)} minutes; you worked out your things for later again and nothing will happen twice")

    def _sweep(self, now: float) -> None:
        for item in list(self.agenda.waiting()):
            if item.by is None:
                continue
            person = self.company.book.get(item.by)
            tier = self.company.tier(person, now) if person is not None else STRANGER
            if tier == STRANGER:
                self.agenda.remove(item, "dropped")
                self.record("later_dropped", item=item.id, why="the asker is now a stranger")
        kept = {item.id for item in self.agenda.waiting()}
        self.out = [due for due in self.out if due.kind != "message" or due.item in kept]

    def _triggers(self, now: float, happened: list) -> None:
        for item in list(self.agenda.waiting()):
            request = item.req()
            trigger = request.on
            if trigger is None:
                continue
            if item.runs_out is not None and now > item.runs_out:
                self._ran_out(item, now)
                continue
            if item.armed is not None and now < item.armed:
                continue
            whom = self.whom(item)
            hit = next((h for h in happened if match(trigger, h, whom)), None)
            if hit is None:
                for one in trigger.first_of or (trigger,):
                    if one.event in ("quiet", "battery", "tv_off") and self.senses.edge(one, item.armed or item.made):
                        hit = one
                        break
            if hit is not None:
                self.record("later_triggered", item=item.id, event=getattr(hit, "event", ""))
                self._fire(item, now, happened=hit)

    def _ran_out(self, item: Item, now: float) -> None:
        request = item.req()
        steps = request.with_(when=None, on=None)
        said = f"{missed_words(request.on)}, so I didn't {step_words_all([steps], self.names())}."
        said = said[:1].upper() + said[1:]
        self.agenda.remove(item, "expired")
        self.agenda.owe(item.by, said, now)
        self.record("later_ran_out", item=item.id, what=item.kind)

    def _due(self, item: Item, now: float, quiet: bool) -> None:
        if item.skip > 0:
            item.skip -= 1
            self.agenda.skip_next(item, now)
            self.record("later_skipped", item=item.id, asked=True)
            return
        self._fire(item, now)

    def _fire(self, item: Item, now: float, missed: bool = False, happened=None) -> None:
        request = item.req()
        due = item.next_at if item.next_at is not None else now
        asker = self.asker_of(item)
        self.agenda.advance(item, now)
        if item.by is not None and asker.tier == STRANGER:
            self.agenda.remove(item, "dropped")
            self.record("later_dropped", item=item.id, why="the asker is now a stranger")
            return
        if item.about:
            people = [self.company.book.get(pid) for pid in item.about]
            adults = any(p is not None and not p.is_child for p in people)
            children = any(p is not None and p.is_child for p in people)
            verdict = decide_later(request, asker, adults, children)
            if not verdict.yes:
                self.agenda.remove(item, "dropped")
                self.agenda.owe(item.by, f"I dropped the one {self._short_when(item)}: {verdict.say[:1].lower() + verdict.say[1:]}", now)
                self.record("later_dropped", item=item.id, why="trust")
                return
        core = request.with_(when=None, on=None)
        note = ""
        if happened is not None and getattr(happened, "guess", False):
            note = f"I think {self.label_of(happened.who, 'they')} has gone out (that's my guess)"
        if core.branch:
            choice = choose(core, self.read(item.by))
            self.record("later_branch", item=item.id, value=choice.value, unsure=len(choice.unsure))
            if choice.held:
                said = f"{choice.couldnt()}, {choice.held_words(core, lambda steps: step_words_all(steps, self.names()))}."
                self._speak_to(item, said[:1].upper() + said[1:], due, now)
                return
            if choice.both:
                self._speak_to(item, self._hedged(core, choice, asker), due, now)
                return
            if choice.value is False and not choice.steps:
                self.note(f"one of {item.by_label}'s things for later did not apply this time ({cond_words(core.if_, True)})")
                return
            steps = flatten(choice.steps)
        else:
            steps = flatten([core])
        if not steps:
            return
        if all(spoken_to_asker(step) for step in steps):
            if item.kind == "wake" or all(wake_up(step.text) for step in steps):
                self._start_wake(item, now)
                return
            text = "; ".join(_spoken(step, self.names()) for step in steps if _spoken(step, self.names()))
            late = ""
            if missed:
                moment = self.local(due)
                late = f"I was meant to remind you at {clock_short(moment.strftime('%H:%M'))}"
            self._queue(item, text, due, now, late, note)
            return
        if all(step.kind == "say_to" and not step.branch for step in steps):
            mine = [step for step in steps if step.who in ("", "me")]
            if mine:
                self._queue(item, "; ".join(_spoken(step, self.names()) for step in mine if _spoken(step, self.names())), due, now, "", note, item.by)
            for step in steps:
                if step.who not in ("", "me"):
                    self.messenger.fired(item, step, happened, now)
            return
        what = step_words_all(steps, self.names())
        if missed and now - due > LATE_BY_S:
            self.agenda.owe(item.by, f"I couldn't {what} at {clock_short(self.local(due).strftime('%H:%M'))}; I was switched off then.", now)
            return
        quiet = self.life.quiet_hours.contains(self.local(now))
        if quiet and request.when is not None and request.when.repeats:
            self.record("later_skipped", item=item.id, asked=False, why="quiet hours")
            return
        late_by = max(due, now) + LATE_BY_S
        if quiet:
            late_by = self._quiet_ends(now) + LATE_BY_S
        self.moves = [m for m in self.moves if m.item != item.id]
        self.moves.append(Move(item.id, steps, item.by, item.by_label, due, late_by, made=item.made))

    def _speak_to(self, item: Item, text: str, due: float, now: float) -> None:
        self.out.append(Due(item.id, item.aimed or item.by, item.by_label, text, due, due + item.useful_s, item.private, ""))

    def _queue(self, item: Item, text: str, due: float, now: float, late: str, note: str, person: str | None = None) -> None:
        useful = useful_until(text, due, self.clock.local, item.useful_s)
        if now > useful:
            self.record("later_too_late", item=item.id)
            return
        holiday = self._holiday_line(text, self.local(due).date())
        self.out.append(Due(item.id, person or item.aimed or item.by, item.by_label, text, due, useful, item.private, late, holiday=holiday, note=note))

    def _holiday_line(self, text: str, day: date) -> str:
        words = re.findall(r"[a-z]+", text.lower())
        for offset in range(0, 7):
            moment = day + timedelta(days=offset)
            name = moment.strftime("%A").lower()
            if name in words or (offset == 1 and "tomorrow" in words) or (offset == 0 and "today" in words):
                if self.senses.holiday(moment):
                    what = "the bins are still being collected" if re.search(r"\b(?:bins?|rubbish|recycling|collection)\b", text.lower()) else "it's still happening"
                    return f"{moment.strftime('%A')}'s a public holiday, so check {what}."
                return ""
        return ""

    def _start_wake(self, item: Item, now: float) -> None:
        person = item.aimed or item.by
        self.wakes = [w for w in self.wakes if w.person != person]
        self.wakes.append(Wake(person, item.by_label, item.id, now))
        self.record("later_wake", item=item.id)

    def _wake(self, now: float) -> None:
        for wake in list(self.wakes):
            if now < wake.next_at:
                continue
            if self.life.alarm():
                continue
            wake.tries += 1
            wake.next_at = now + WAKE_EVERY_S
            hhmm = clock_short(self.local(now).strftime("%H:%M"))
            if wake.tries <= WAKE_GENTLE:
                self.say(f"{wake.label}, it's {hhmm}. Time to wake up.")
            else:
                self.shout(f"{wake.label}! It's {hhmm}. Time to get up!")
            self.record("later_wake_try", item=wake.item, tries=wake.tries)
            if wake.tries >= WAKE_TRIES:
                self.wakes.remove(wake)
                self.note(f"you tried to wake {wake.label} ten times and they didn't answer, so you stopped")

    def _deliver(self, now: float, force: str | None = None) -> None:
        if not self.out:
            return
        if self.life.alarm():
            return
        talking = self.life.house.talking() if getattr(self.life, "house", None) is not None else False
        rules = getattr(self.life, "rules", None)
        hushed = rules is not None and rules.quiet_now()
        night = self.life.quiet_hours.contains(self.local(now))
        by_person: dict = {}
        for due in list(self.out):
            if now > due.useful:
                self.out.remove(due)
                if due.kind == "message":
                    self.messenger.expired(due, now)
                    continue
                self.agenda.owe(due.person, f"I was meant to remind you {_clock_of(self, due)}: {reminder_words(due.text, self.names())}, but I couldn't find you in time.", now, 6 * 3600.0)
                self.record("later_undelivered", item=due.item)
                continue
            by_person.setdefault(due.person, []).append(due)
        for person, dues in by_person.items():
            if person is None:
                continue
            if not self.senses.with_pebble(person, now):
                self._seek(person, dues, now)
                continue
            if talking and force != person and min(now - due.due for due in dues) < PAUSE_S:
                continue
            ready = [due for due in dues if not due.offered]
            waiting = [due for due in ready if due.kind == "message" and (night or hushed)]
            if waiting and hushed and not night and self._only_family(person, now):
                shown = [due for due in waiting if now >= due.useful - SCREEN_S]
                if shown:
                    self._on_screen(person, shown, now)
            ready = [due for due in ready if due not in waiting]
            if not ready:
                continue
            private = any(due.private for due in ready)
            if private and not self._only_family(person, now):
                for due in ready:
                    due.offered = True
                messages = [due for due in ready if due.kind == "message"]
                self.say(self.messenger.offer(messages) if messages else f"{dues[0].label}, I've got a reminder for you.")
                self.record("later_offered", items=[d.item for d in ready])
                continue
            for due in ready:
                self.out.remove(due)
            said = self._line(dues[0].label, ready)
            self.say(said)
            if hushed:
                self._show(dues[0].label, said)
            self.record("later_said", items=[d.item for d in ready], person=person, late=any(d.late for d in ready), soft=hushed or None)
            if all(due.kind != "message" for due in ready):
                self.note(f"you gave {dues[0].label} {'their reminder' if len(ready) == 1 else f'{len(ready)} reminders'}")
            else:
                self.note(f"you passed on a message to {dues[0].label}")
            self.messenger.delivered([due for due in ready if due.kind == "message"], now)

    def _on_screen(self, person: str, dues: list[Due], now: float) -> None:
        for due in dues:
            self.out.remove(due)
        said = " ".join(self.messenger.line(due) for due in dues)
        self._show(dues[0].label, said)
        self.record("later_shown", items=[d.item for d in dues], person=person)
        self.note(f"a house rule asked you to keep quiet, so you showed {dues[0].label} a message on your screen instead of saying it")
        self.messenger.delivered(dues, now)

    def _show(self, label: str, text: str) -> None:
        layer = getattr(getattr(self.life, "house", None), "layer", None)
        if layer is None:
            return
        try:
            layer.show("card", f"For {label}", [text], SCREEN_HOLD_S)
        except Exception:
            log.exception("the screen could not show a reminder")

    def _line(self, label: str, dues: list[Due]) -> str:
        reminders = [due for due in dues if due.kind != "message"]
        lines = [self.messenger.line(due) for due in dues if due.kind == "message"]
        if reminders:
            lines.insert(0, self._reminder_line(label, reminders))
        return " ".join(lines)

    def _reminder_line(self, label: str, dues: list[Due]) -> str:
        names = self.names()
        if len(dues) == 1:
            due = dues[0]
            text = reminder_words(due.text, names)
            if due.late:
                line = f"{label}, {due.late} {_to_or_that_text(due.text, names)}; I was switched off then."
            elif due.note:
                line = f"{label}, {due.note}. You asked me to remind you: {text}." if due.text.strip() else f"{label}, {due.note}. You asked me to tell you."
            elif not due.text.strip():
                line = f"{label}, you asked me to give you a reminder now."
            elif due.text.startswith("I couldn't"):
                line = f"{label}, {due.text}"
            else:
                line = f"{label}, you asked me to remind you: {text}."
            return f"{line} {due.holiday}".strip()
        count = NUMBERS.get(len(dues), str(len(dues)))
        parts = [reminder_words(due.text, names) or "a reminder" for due in dues]
        parts = [parts[0]] + [part[:1].lower() + part[1:] if part.split(" ")[0].lower() not in {n.lower() for n in DAY_NAMES.values()} and part.split(" ")[0].lower() not in names else part for part in parts[1:]]
        joined = ", ".join(parts[:-1]) + ", and " + parts[-1]
        holidays = " ".join(dict.fromkeys(due.holiday for due in dues if due.holiday))
        return f"{count} things, {label}: {joined}. {holidays}".strip()

    def _only_family(self, person: str, now: float) -> bool:
        if self.company.someone_new(now):
            return False
        for other in self.company.here(now):
            if other.id == person:
                continue
            if other.relationship not in ("family", "owner", "child"):
                return False
        return True

    def _seek(self, person: str, dues: list[Due], now: float) -> None:
        if any(due.sought > -math.inf for due in dues):
            return
        for due in dues:
            due.sought = now
        commands = self.commands
        sit = self.life.situation()
        if commands.runner.busy or sit.quiet or not sit.can_move or self.life.alarm():
            return
        label = self.label_of(person)
        if not label:
            return
        self.record("later_seek", person=person)
        commands._spawn(commands.act(Request("come", who=label.lower()), PEBBLE, "later", routed=True))

    def _move(self, now: float, quiet: bool) -> None:
        for move in list(self.moves):
            if now > move.late_by:
                self.moves.remove(move)
                what = step_words_all(move.steps, self.names())
                why = move.why or "something else came first"
                self.agenda.owe(move.by, f"I couldn't {what} at {clock_short(self.local(move.due).strftime('%H:%M'))}; {why}.", now)
                self.record("later_skipped", item=move.item, asked=False)
                continue
            if self.life.alarm():
                move.why = "there was an alarm"
                continue
            if quiet:
                move.why = "it was my quiet time"
                continue
            current = self.commands.runner.current
            if current is not None and not current.asker.own:
                move.why = "I was busy with something else you asked for" if current.asker.id == move.by else f"I was helping {current.asker.label}"
                continue
            asker = self.commands.asker_for(move.by) if move.by else PEBBLE
            step = move.steps[0]
            rules = getattr(self.life, "rules", None)
            ruled = rules.blocking(step, asker, move.made) if rules is not None and not step.branch else None
            if ruled is not None:
                move.why = rules.line(ruled).rstrip(".")
                continue
            if not step.branch and step.kind not in ("say_to",):
                verdict = decide(step, asker, self.life.situation(refusals_left=3))
                if not verdict.yes:
                    move.why = _reason(verdict)
                    continue
            self.moves.remove(move)
            self.record("later_moved", item=move.item, what=step.kind)
            self.note(f"it was time for something {move.label} asked for earlier: {step_words_all(move.steps, self.names())}")
            self.commands._spawn(self._run_move(move, asker))

    async def _run_move(self, move: Move, asker: Asker) -> None:
        verdict = await self._chain(list(move.steps), asker, "later")
        current = self.commands.runner.current
        if move.by and verdict is not None and verdict.yes and current is not None and current.asker.id == move.by:
            current.report_to = move.by

    def _quiet_ends(self, now: float) -> float:
        quiet = self.life.quiet_hours
        day = self.local(now).date()
        end = instant(datetime.combine(day, quiet.end), self.clock.local)
        if end <= now:
            end = instant(datetime.combine(day + timedelta(days=1), quiet.end), self.clock.local)
        return end

    def _owed(self, now: float) -> None:
        if not self.agenda.owed or self.life.alarm():
            return
        talking = self.life.house.talking() if getattr(self.life, "house", None) is not None else False
        if talking:
            return
        for person in {o.get("to") for o in self.agenda.owed}:
            if person is None or not self.senses.with_pebble(person, now):
                continue
            lines = self.agenda.owed_to(person, now, self.company.presence.last_seen(person))
            if not lines:
                continue
            label = self.label_of(person)
            self.say(f"{label}, " + " ".join(lines))
            self.record("later_told", person=person, lines=len(lines))

    def _watch(self, now: float, happened: list) -> None:
        runner = self.commands.runner
        for watch in list(self.watches):
            if runner.current is not watch.activity:
                self.watches.remove(watch)
                continue
            activity = watch.activity
            if watch.kind == "while" and now - watch.checked >= WHILE_EVERY_S:
                watch.checked = now
                value = evaluate(watch.cond, self.read(watch.asker.id))
                if value is False:
                    self.watches.remove(watch)
                    runner.end("done", f"{cond_words(watch.cond, True)} now, so you stopped {activity.describe()}", f"Okay, {cond_words(watch.cond, True)} now, so I'll stop.")
                elif value is None and activity.moving:
                    self.watches.remove(watch)
                    runner.end("stopped", f"you could no longer tell whether {cond_words(watch.cond)}, so you stopped {activity.describe()}", f"I can't tell whether {cond_words(watch.cond)} any more, so I'll stop.")
            elif watch.kind == "until":
                whom = {"me": watch.asker.id, "": watch.asker.id}
                for one in watch.trigger.first_of or (watch.trigger,):
                    if one.who and one.who not in whom:
                        person = self.company.book.find(one.who)
                        whom[one.who] = person.id if person is not None else None
                hit = next((h for h in happened if match(watch.trigger, h, whom)), None)
                if hit is None:
                    hit = next((one for one in watch.trigger.first_of or (watch.trigger,) if one.event in ("quiet", "battery", "tv_off") and self.senses.edge(one, watch.since)), None)
                if hit is not None:
                    self.watches.remove(watch)
                    part = hit if hasattr(hit, "first_of") else next((one for one in watch.trigger.first_of or (watch.trigger,) if match(one, hit, whom)), watch.trigger)
                    words = happened_words(part)
                    runner.end("done", f"{words}, so you stopped {activity.describe()}", f"{words[:1].upper() + words[1:]}, so I'll stop.")
            elif watch.kind == "asked" and now - watch.checked >= CHECK_IN_S:
                watch.checked = now
                if watch.asker.id is not None and not self.senses.with_pebble(watch.asker.id, now):
                    self.watches.remove(watch)
                    runner.end("done", f"{watch.asker.label} went away, so you stopped {activity.describe()}", "")
                    continue
                self.question = Question("checkin", watch.asker.id, now + QUESTION_S, [watch], None, watch.asker)
                self.say(f"Still having fun, {watch.asker.label}?")

    def matched(self) -> str:
        now = self.clock.now()
        soon = [item for item in self.agenda.waiting() if item.next_at is not None and 0 <= item.next_at - now <= MATCHED_S]
        soon.sort(key=lambda item: item.next_at)
        if not soon:
            return ""
        out = []
        for item in soon[:MATCHED_MOST]:
            hhmm = clock_short(self.local(item.next_at).strftime("%H:%M"))
            what = "a private reminder" if item.private else step_words_all([item.req().with_(when=None, on=None)], self.names())
            out.append(f"{hhmm}, for {item.by_label}: {what}")
        return "Due within the hour: " + "; ".join(out) + "."


def managing(text: str) -> Request | None:
    if LIST.match(text):
        return Request("list_later")
    if CANCEL_ALL.match(text):
        return Request("cancel_later", scope="all")
    if CANCEL_BARE.match(text):
        return Request("cancel_later")
    found = CANCEL_MESSAGE.match(text)
    if found is not None:
        who = found.group("who") or found.group("who2") or ""
        return Request("cancel_later", text=f"message {who}".strip())
    found = SKIP.match(text)
    if found is not None:
        return Request("cancel_later", text=(found.group("what") or found.group("what2") or "")[:40], scope="next")
    found = CANCEL_ONE.match(text)
    if found is not None:
        return Request("cancel_later", text=(found.group("what") or found.group("what2") or "")[:40])
    found = CHANGE.match(text)
    if found is not None:
        when = found.group("when")
        days = _days_in(when)
        clock = spoken_clock(when)
        if days or clock:
            return Request("change_later", text=found.group("what")[:40], when=When(days=days, at=clock))
    return None


def flatten(steps) -> list[Request]:
    out = []
    for step in steps:
        if step.branch:
            out.append(step)
            continue
        out.append(step.with_(then=()))
        out.extend(step.then)
    return out


def step_words_all(steps, names: tuple = ()) -> str:
    said = [tree_words(step, names) if step.branch else step_words(step, names) for step in steps]
    return ", then ".join(said)


def _spoken(step: Request, names: tuple) -> str:
    if step.branch:
        return ""
    if step.kind == "say_to":
        return reminder_words(step.text, names) if step.text else ""
    return ""


def _to_or_that_text(text: str, names: tuple) -> str:
    said = step_words(Request("say_to", who="me", text=text), names)
    return said[len("remind you "):] if said.startswith("remind you ") else said


def _clock_of(later: Later, due: Due) -> str:
    return f"at {clock_short(later.local(due.due).strftime('%H:%M'))}"


def _with_me(request: Request, who: str) -> Request:
    data = request.as_dict()

    def swap(step: dict) -> dict:
        if step.get("kind") == "say_to" and step.get("who") == who:
            step = {**step, "who": "me"}
        for key in ("then", "else"):
            if key in step:
                step[key] = [swap(dict(inner)) for inner in step[key]]
        return step

    return from_dict(swap(data))


def _days_in(text: str) -> tuple:
    found = []
    for word in re.findall(r"[a-z]+", text.lower()):
        word = word[:-1] if word.endswith("s") and word[:-1] in DAY_CODES else word
        if word in DAY_CODES and len(word) > 3 and DAY_CODES[word] not in found:
            found.append(DAY_CODES[word])
    return tuple(found)


def _reason(verdict: Verdict) -> str:
    if verdict.say:
        said = verdict.say.rstrip(".")
        return said[:1].lower() + said[1:]
    return verdict.reason


def useful_until(text: str, due: float, local, useful_s: float) -> float:
    words = re.findall(r"[a-z]+", text.lower())
    day = local(due).date()
    for offset in range(0, 7):
        moment = day + timedelta(days=offset)
        name = moment.strftime("%A").lower()
        if name in words or (offset == 1 and "tomorrow" in words):
            if moment > day:
                return instant(datetime.combine(moment, USEFUL_MORNING), local)
            break
    return due + useful_s
