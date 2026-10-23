import asyncio
import logging
from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from typing import Awaitable, Callable

from ..people.company import Company, Heard
from ..people.proof import UNSEEN_SAY
from ..people.trust import STRANGER
from ..respect import ANIMAL, cruel, for_mind as harm_for_mind, harsh, life_kind
from ..script.voice import loopy
from ..tact import tactless
from ..understand.context import Activity as SeenActivity
from ..understand.context import Context, Pending
from ..understand.cover import new_act
from ..things.book import ThingBook
from ..things.guarded import CHILD_NO, CLOSE_NO, STRANGER_NO
from ..things.words import listing, spoken, with_article
from ..understand.logic import patrol
from ..understand.refs import Refs, again_for, flipped, mentioned
from ..understand.request import MOVING, QUESTIONS, TOO_MUCH, Request
from ..understand.resolve import Reading, question_for
from ..understand.rules import harmed
from ..understand.understanding import UNDERSTAND, Door, Understanding
from .base import Activity, Ending, Target
from .check import Aim, Check, Results, target_words
from .gate import CLAIMABLE, KEEP_EYE_CHILD, KEEP_EYE_NO, LIFE_REASONS, PEBBLE, PRIVACY_NO, PRIVACY_REASON, SELF, WATCH_CHILD_NO, WATCH_NO, WHO_UNSEEN, Asker, Situation, Verdict, decide, guarded_refusal, unbuilt
from .home import GoHome
from .kinds import KINDS, SeekPeople
from .patrol import Patrol, whole_house
from .places import GoBack, GoToPlace, GoToSpot, LookThere, Play
from .push import Push
from .skills import plain as plain_words
from .quake import QuakeRound
from .rounds import find_place
from .runner import Runner
from .watch import Fetch, Watch, honesty

log = logging.getLogger(__name__)

PENDING_S = 30.0
CLOSE_LOOK_S = 7.0
SURE_SCORE = 0.5
MAYBE_SCORE = 0.35
CURIOUS_GAP_S = 180.0
CURIOUS_SETTLE_S = 60.0
WONDER_KEEP_S = 300.0
SEE_MAX = 4
RECENT_KEEP = 6
PATIENCE_S = 600.0
TIER_PATIENCE = {"stranger": 0.15, "child": 0.5, "friend": 0.75, "trusted": 1.0, "inner circle": 1.2, SELF: 1.0}
ENDING_FACES = {"lost": "sad", "patience": "neutral", "battery": "sleepy", "reflex": "surprised", "failed": "sad", "no_sight": "sad", "blocked": "neutral"}
DIARY_ENDS = {
    "done": "and that went well",
    "released": "until I was told I could carry on",
    "stopped": "until I stopped",
    "replaced": "until something else came up",
    "lost": "until I lost sight of them",
    "patience": "until I got restless",
    "battery": "until my battery got low",
    "reflex": "until my body stopped me",
    "failed": "but it didn't work out",
    "no_sight": "but I couldn't see well enough",
    "timeout": "until it took too long",
    "blocked": "but I couldn't move",
}
HOUSEHOLD_WORDS = {
    "find_chirp": "find which smoke alarm is chirping",
    "red_light": "play red light, green light",
    "statues": "play musical statues",
    "hide_seek": "play hide and seek",
    "quake_round": "check on everyone after the earthquake",
}
HOUSEHOLD_DIARY = {
    "climate_round": "I went round the rooms measuring the air",
    "find_chirp": "I went looking for the chirping smoke alarm",
    "red_light": "I played red light, green light",
    "statues": "I played musical statues",
    "hide_seek": "I played hide and seek",
    "quake_round": "I checked on everyone after the earthquake",
}
ENDED_WORDS = {
    "done": "finished",
    "released": "were released from",
    "stopped": "stopped",
    "replaced": "stopped",
    "lost": "gave up",
    "patience": "ran out of patience",
    "battery": "stopped for the battery",
    "reflex": "stopped",
    "failed": "could not finish",
    "no_sight": "could not start",
    "timeout": "gave up",
    "blocked": "could not move for",
}


ADDED: dict = {}
NOT_ALL = "I'm not sure I got all of that."
NOT_YET = (
    ("when", "I can't do things at a set time yet, only now."),
    ("on", "I can't wait for something to happen first yet."),
    ("if", "I can't do things that depend on something else yet."),
    ("while", "I can't keep something up only while something else lasts yet."),
    ("until", "I can't tell when that happens yet."),
    ("say_to", "I can't pass on messages yet."),
    ("reminder", "I can't do reminders yet."),
    ("set_rule", "I can't keep house rules yet."),
    ("end_rule", "I don't keep any house rules yet."),
    ("list_rules", "I don't keep any house rules yet."),
    ("check", "I can't go and check things for you yet."),
    ("watch", "I can't watch over anyone yet."),
    ("again", "I can't do things again yet."),
    ("try_new", "I don't know how to do that yet."),
    ("list_later", "I don't keep anything for later yet."),
    ("cancel_later", "I don't keep anything for later yet, so there's nothing to cancel."),
    ("change_later", "I don't keep anything for later yet, so there's nothing to change."),
    ("change", "I can't change it that way yet."),
)
NOT_YET_LINES = dict(NOT_YET)
ASKED_LINE = "Tell me when you've had enough."
NOTHING_AGAIN = "I haven't done anything for you in the last half hour, so I'm not sure what to do again."
WHICH_WAY = "I'm not sure which way you mean."
NO_BEFORE = "I don't remember where I was before."
CANT_LOOK = "I can't look in there."
FIXED_LINES = frozenset({PRIVACY_NO, CANT_LOOK, WHO_UNSEEN, UNSEEN_SAY, KEEP_EYE_NO, KEEP_EYE_CHILD, WATCH_NO, WATCH_CHILD_NO, TOO_MUCH, CHILD_NO, CLOSE_NO, STRANGER_NO})
NOWHERE_TO_CHECK = "I don't know where to look for that. Which room should I check?"
SEEN_OLD_S = 3600.0
POINTED_AT = "you looked where you were pointed and saw a "
PRIVATE_NAMES = frozenset({"bathroom", "loo", "toilet", "toilet room", "en suite", "ensuite", "shower"})
TRIPS = frozenset({"come", "follow", "go_to_place", "go_to_thing", "find", "go_back", "check", "watch", "play", "go_home", "seek_people", "fetch", "climate_round", "hide_seek", "find_chirp", "quake_round"})
DONE_HOW = frozenset({"heard", "named", "mind"})
FOLLOWS_PLAN = frozenset({"then", "unstuck"})
LATER_WORDS = {
    "when": "at a set time",
    "on": "once something happens",
    "if": "only if something is true",
    "while": "only while something lasts",
    "until": "until something happens",
}


@dataclass
class Plan:
    asker: Asker
    steps: list = field(default_factory=list)
    words: str = ""


@dataclass
class Early:
    number: int
    request: Request
    asker: Asker
    activity: Activity | None = None
    answer: str = ""


def not_yet(request: Request, built: bool = False) -> tuple[str, list[str]]:
    parts = unbuilt(request) if built else request.needs_later()
    if not parts:
        return "", []
    first = parts[0]
    if first == "say_to" and all(step.who in ("", "me") for step in request.steps() if step.kind == "say_to"):
        first = "reminder"
    return NOT_YET_LINES.get(first, "I can't do that yet."), parts


def first_step(request: Request) -> tuple:
    return (request.kind, request.who, request.place, request.thing, request.way)


def expand(request: Request) -> list[Request]:
    steps = [request.with_(then=(), repeat=1)] * max(1, request.repeat)
    for step in request.then:
        steps.extend([step.with_(repeat=1)] * max(1, step.repeat))
    return steps


def for_mind(request: Request) -> str:
    said = _for_mind(request)
    if request.repeat > 1:
        said += " twice" if request.repeat == 2 else f" {request.repeat} times"
    for words, part in ((LATER_WORDS["when"], request.when), (LATER_WORDS["on"], request.on), (LATER_WORDS["while"], request.while_), (LATER_WORDS["until"], request.until_on)):
        if part is not None:
            said += f" {words}"
    return said


def _for_mind(request: Request) -> str:
    who = "them" if request.who in ("", "me") else request.who.title()
    if request.thing:
        who = f"the {spoken(request.thing)}"
    kind = request.kind
    if kind == "go_to_thing":
        return f"go to {who}"
    if kind == "find":
        return f"look for {who}"
    if kind == "where_is":
        return f"say where {who} is"
    if kind == "what_is":
        return "say what that is"
    if kind == "what_see":
        return "say what you can see"
    if kind == "follow":
        return f"follow {who}"
    if kind == "come":
        return f"come to {who}"
    if kind == "look":
        return "look where they pointed" if request.place == "there" else f"look at {who}"
    if kind == "play" and request.thing and request.to:
        return f"push the {spoken(request.thing)} to " + ("them" if request.to in ("", "me") else request.to.title())
    if kind == "play":
        return f"play with the {spoken(request.thing)}" if request.thing else "play"
    if kind == "where_am_i":
        return "say where you are"
    if kind == "sight_question":
        return "have a close look and answer their question"
    if kind == "remember_spot":
        return f"remember this spot as the {request.name}" if request.name else "remember this spot"
    if kind == "go_back":
        if request.place == "before":
            return "go back to where you were before"
        return "go back to where you started" if request.place in ("", "start") else f"go back to the {request.place}"
    if kind == "teach":
        return "learn what this is or whose it is"
    if kind == "wait":
        extra = {"back": " until they are back", "called": " until they call you"}.get(request.until, "")
        return f"wait{extra}"
    if kind == "back_off":
        return "back off and give them space"
    if kind == "go_home":
        return "go back to your charger"
    if kind == "go_to_place":
        if request.who and not request.place:
            return f"go to where {who} was"
        if request.place == "there":
            return "go where they pointed"
        return f"go to the {request.place}" if request.place else "go somewhere"
    if kind == "turn":
        return f"turn {request.way}".strip()
    if kind == "move":
        return f"move {request.way or 'forward'} a little"
    if kind == "stop_activity":
        return "stop what you were doing"
    if kind == "release":
        return "carry on with your own things"
    if kind == "adjust":
        return f"change how you were doing it ({request.change.replace('_', ' ')})"
    if kind == "climate_round":
        return f"measure the air in the {request.place}" if request.place else "go round the rooms and measure the air"
    if kind == "harm":
        return harm_for_mind(request.who or request.thing, request.harm)
    if kind in HOUSEHOLD_WORDS:
        return HOUSEHOLD_WORDS[kind]
    if kind == "say_to":
        about = f": {request.text}" if request.text else ""
        return f"remind them{about}" if request.who in ("", "me") else f"tell {request.who.title()}{about}"
    if kind == "set_rule":
        return f"keep out of the {request.place}" if request.rule == "keep_out" and request.place else "keep quiet"
    if kind == "end_rule":
        return "stop keeping a house rule"
    if kind == "list_rules":
        return "say which house rules you keep"
    if kind == "check":
        target = request.thing or request.place
        return f"go and check the {target}" if target else "go and check something"
    if kind == "watch":
        return f"keep an eye on {who}"
    if kind == "again":
        return "do the last thing again"
    if kind == "try_new":
        return f"try something new ({request.text})" if request.text else "try something new"
    if kind == "list_later":
        return "say what you have for later"
    if kind == "cancel_later":
        return f"cancel something for later ({request.text})" if request.text else "cancel something for later"
    if kind == "change_later":
        return f"change something for later ({request.text})" if request.text else "change something for later"
    if kind == "if":
        return "do something only if something is true"
    return kind


def reads_result(steps) -> bool:
    for step in steps:
        if step.branch:
            if step.if_ is not None and any(leaf.state == "result" for leaf in _leaves(step.if_)):
                return True
            if reads_result(step.then + step.else_):
                return True
        elif reads_result(step.then):
            return True
    return False


def _leaves(cond) -> list:
    if cond.join:
        return [leaf for part in cond.parts for leaf in _leaves(part)]
    return [cond]


def activity_for(request: Request, asker: Asker, target: Target | None, battery: bool = False, aim=None, said: str = "", tree: bool = False, child: bool = False) -> Activity:
    if aim is not None and request.kind in ("go_to_place", "go_back"):
        return GoToSpot(request, asker, target, battery, aim)
    if request.kind == "check" and not patrol(request):
        return Check(request, asker, target, battery, aim, tree)
    if request.kind == "watch":
        return Watch(request, asker, target, battery, said, child)
    if request.kind == "go_home":
        return GoHome(request, asker, target, battery)
    if request.kind == "play" and request.to:
        return Push(request, asker, target, battery)
    if request.kind == "look" and request.place == "there":
        return LookThere(request, asker, target, battery)
    if request.kind == "go_to_place":
        return GoToPlace(request, asker, target, battery)
    if request.kind == "play":
        return Play(request, asker, target, battery)
    if request.kind == "go_back":
        return GoBack(request, asker, target, battery)
    if request.kind == "check":
        return Patrol(request, asker, target, battery)
    if request.kind in ADDED:
        return ADDED[request.kind](request, asker, target, battery)
    return KINDS[request.kind](request, asker, target, battery)


class Commands:
    def __init__(
        self,
        company: Company,
        runner: Runner,
        understanding: Understanding,
        situation: Callable[..., Situation],
        speak: Callable[[str, bool], Awaitable],
        note: Callable[[str, bool], None],
        diary: Callable[[str, str], None],
        record: Callable[..., None],
        places: Callable[[], list[str]] = lambda: [],
        personality: Callable[[], dict] = lambda: {},
        chaos: Callable[[], float] = lambda: 0.0,
        can_see: Callable[[], bool] = lambda: False,
        refusals_per_day: Callable[[], int] = lambda: 3,
        things: ThingBook | None = None,
        name: str = "Pebble",
    ):
        self.company = company
        self.runner = runner
        self.understanding = understanding
        self.situation = situation
        self.speak = speak
        self.note = note
        self.diary = diary
        self.record = record
        self.places = places
        self.personality = personality
        self.chaos = chaos
        self.can_see = can_see
        self.refusals_per_day = refusals_per_day
        self.name = name
        self.pending: Pending | None = None
        self.recent: list[str] = []
        self.plan: Plan | None = None
        self.early: Early | None = None
        self.refusals: dict[str, int] = {}
        self.tasks: set[asyncio.Task] = set()
        self._heard_count = 0
        self._acted_on = 0
        runner.on_end = self.ended
        runner.kit.patience = self.patience
        runner.kit.present = self.present
        runner.kit.note = lambda text: self.note(text, False)
        runner.kit.recall = self.recall
        self.things = things
        self.curious_at = -1e18
        self.born_at = runner.kit.pace.now()
        self.wonder: tuple[str, bool, float] | None = None
        self.alive = None
        self.pictures = None
        self.question_text = ""
        self.household = None
        self.later = None
        self.rules = None
        self.refs = Refs()
        self.checks = Results()
        self.trying = None
        self.teaching = None
        self.on_did: Callable[..., None] | None = None
        self.scripts = None
        self.unstuck = None
        self.own_words = None
        self.card: Callable[[], str] = lambda: ""
        self.shown_places: Callable[[str], tuple] = lambda text: ()
        self.on_refused: Callable[..., None] | None = None
        runner.on_start = self.started
        runner.kit.picture = self.picture_answer

    @property
    def clock(self):
        return self.company.clock

    def present(self, person_id: str) -> bool:
        return person_id in self.company.presence.here(self.clock.now())

    def patience(self, tier: str) -> float:
        traits = self.personality().get("traits") or {}
        cautious, curious, affectionate = (float(traits.get(k, 5)) for k in ("cautious", "curious", "affectionate"))
        trait = max(0.4, 1.0 + 0.08 * (cautious - 5) - 0.08 * (curious - 5))
        factor = TIER_PATIENCE.get(tier, TIER_PATIENCE[STRANGER])
        if tier not in (STRANGER, SELF):
            factor *= 1.0 + 0.04 * (affectionate - 5)
        level = max(0.0, min(10.0, self.chaos()))
        return PATIENCE_S * trait * factor * (1.0 - 0.03 * level)

    def refusals_left(self) -> int:
        day = self.clock.local().date().isoformat()
        return max(0, int(self.refusals_per_day()) - self.refusals.get(day, 0))

    def _spend_refusal(self) -> None:
        day = self.clock.local().date().isoformat()
        self.refusals = {day: self.refusals.get(day, 0) + 1}

    def asker_for(self, person_id: str | None, sure: bool = False) -> Asker:
        now = self.clock.now()
        person = self.company.book.get(person_id)
        if person is None:
            return Asker(None, "someone", STRANGER, here=False)
        family = person.relationship == "family" and not person.is_child
        return Asker(person.id, person.label, self.company.tier(person, now), person.is_owner, person.id in self.company.presence.here(now), sure, family)

    def asker_heard(self, heard) -> Asker:
        return self.asker_for(getattr(heard, "person_id", None), bool(getattr(heard, "sure", False)))

    def fresh(self, asker: Asker) -> Asker:
        if asker.own or asker.id is None:
            return asker
        return self.asker_for(asker.id, asker.sure)

    def requester(self, name: str) -> tuple[Asker | None, str]:
        asking = self.company.asking
        if asking is None:
            return None, "you act for someone only while answering what they have just said to you"
        person = self.company.book.find(name)
        if person is None:
            return None, f"I don't know who {name!r} is"
        if person.id not in asking:
            return None, f"{person.label} has not asked you anything just now"
        return self.asker_for(person.id, bool(asking[person.id]) and len(asking) == 1), ""

    def refused_to(self, asker: Asker, line: str, what: str = "") -> None:
        if self.on_refused is None or asker.own or not line:
            return
        try:
            self.on_refused(asker, line, what)
        except Exception:
            log.exception("could not keep a refusal on the task card")

    def _card(self) -> str:
        try:
            return self.card() or ""
        except Exception:
            log.exception("could not build the task card for the reader")
            return ""

    def unsafe_to_tell(self, thing: str) -> str | None:
        now = self.clock.now()
        for person in self.company.here(now):
            refused = guarded_refusal(thing, self.asker_for(person.id))
            if refused is not None:
                return f"{person.label} is here, so keep where that is to yourself for now"
        return None

    def context(self, heard: Heard | None, asker: Asker | None = None) -> Context:
        now = self.clock.now()
        here = self.company.here(now)
        present = [p.label.lower() for p in here]
        if self.company.someone_new(now):
            present.append("a visitor")
        names = []
        for person in self.company.book.people.values():
            names.extend(n.lower() for n in person.names + person.nicknames)
        speaker = None
        tier = STRANGER
        if heard is not None and heard.person_id is not None:
            person = self.company.book.get(heard.person_id)
            if person is not None:
                speaker = person.label.lower()
                tier = self.company.tier(person, now)
        current = self.runner.current
        seen = None
        if current is not None:
            seen = SeenActivity(current.kind, current.asker.label.lower() if not current.asker.own else "pebble", current.target.label.lower() if current.target else "")
        pending = self.pending if self.pending is not None and now - self.pending.at <= PENDING_S else None
        return Context(
            speaker=speaker,
            tier=tier,
            present=tuple(present),
            activity=seen,
            pending=pending,
            recent=tuple(self.recent[-4:]),
            places=tuple(self.places()),
            names=tuple(names),
            name=self.name.lower(),
            can_see=self.can_see(),
            pointing=self.alive.pointing() if self.alive is not None else False,
            life=self.life_in_view(),
            now=self.clock.local(now).replace(tzinfo=None).isoformat(timespec="minutes"),
            refs=self.refs.block(now, getattr(heard, "person_id", None) or (asker.id if asker is not None else None)),
            skills=self.trying.listed(heard.text) if self.trying is not None and getattr(heard, "text", "") else "",
            card=self._card(),
            shown=self._shown(getattr(heard, "text", "") or ""),
        )

    def _shown(self, text: str) -> tuple:
        try:
            return tuple(self.shown_places(text) or ())
        except Exception:
            log.exception("could not choose the places to show the reader")
            return ()

    def life_in_view(self) -> tuple:
        eyes = getattr(self.runner.kit, "eyes", None)
        sight = eyes.latest(2.0) if eyes is not None else None
        if sight is None:
            return ()
        found = []
        for thing in sorted(sight.things, key=lambda t: t.width_frac * t.height_frac):
            kind = life_kind(thing.label) or (ANIMAL if thing.animal else None)
            if kind is not None and thing.score >= MAYBE_SCORE:
                found.append((thing.label, kind))
        return tuple(found)

    def heard(self, heard: Heard) -> asyncio.Task | None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        task = loop.create_task(self.consider(heard))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def settle(self) -> None:
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    def stopped(self, heard: Heard) -> None:
        current = self.runner.current
        self.plan = None
        if self.unstuck is not None:
            self.unstuck.case = None
        if current is not None and current.moving:
            self.runner.end("stopped", f"{heard.label} said stop, so you stopped {current.describe()}")

    async def consider(self, heard: Heard) -> Reading | None:
        try:
            self._heard_count += 1
            return await self._consider(heard, self._heard_count)
        except Exception:
            log.exception("could not consider a line of %d characters", len(heard.text or ""))
            self.record("request_error", words=len((heard.text or "").split()))
            return None

    async def _consider(self, heard: Heard, number: int) -> Reading:
        ctx = self.context(heard)
        harmful = harmed(heard.text, ctx)
        if harmful is None and self.scripts is not None:
            handled = await self.scripts.heard(heard)
            if handled is not None:
                return handled
        if harmful is None and self.teaching is not None:
            handled = await self.teaching.heard(heard)
            if handled is not None:
                return handled
        if harmful is None and self.trying is not None:
            handled = await self.trying.heard(heard)
            if handled is not None:
                return handled
        if harmful is None and self.later is not None and heard.stop is None:
            handled = await self.later.heard(heard)
            if handled is not None:
                return handled
        if harmful is None and self.household is not None:
            handled = await self.household.consider(heard)
            if handled is not None:
                return handled
        if harmful is not None:
            return await self._take(heard, ctx, Reading(harmful), number)
        door = self.understanding.door(heard.text, ctx)
        if door.model and door.early is not None and heard.stop is None:
            self.record("reading_started", why=door.why, left=len(door.left), request=door.early.as_dict())
            reading = await self._take(heard, ctx, door.early, number, early=True)
            self._spawn(self._finish(heard, ctx, door, number))
            return reading
        reading = await self.understanding.read(heard.text, ctx)
        return await self._take(heard, ctx, reading, number)

    async def _take(self, heard: Heard, ctx: Context, reading: Reading, number: int, early: bool = False) -> Reading:
        if number < self._acted_on and reading.request.action:
            self.record("superseded", text=heard.text, request=reading.as_dict(), source=reading.source)
            return reading
        if reading.request.action:
            self._acted_on = number
        self.recent.append(f"{heard.label.lower()}: {heard.text[:120]}")
        del self.recent[:-RECENT_KEEP]
        self.refs.mention(mentioned(heard.text, ctx.places), self.clock.now())
        if reading.answered or (ctx.pending is None and self.pending is not None):
            self.pending = None
        request = reading.request
        asker = self.asker_heard(heard)
        named = bool(reading.speaker)
        if named:
            claimed = self._claimed(reading.speaker) if request.kind in CLAIMABLE else None
            if claimed is not None:
                asker = claimed
                self.record("speaker_named", said=reading.speaker, person=claimed.id)
            else:
                self.record("speaker_claim_ignored", asked=request.kind)
        if reading.too_much and self.scripts is not None and self.scripts.can_write(asker):
            self.record("understood", request=reading.as_dict(), source=reading.source, person=heard.person_id, too_much=True, program=True)
            await self.scripts.ask_for(heard.text, asker, "heard")
            return replace(reading, request=Request("chat"), answered=True)
        if reading.too_much:
            self.record("understood", request=reading.as_dict(), source=reading.source, person=heard.person_id, too_much=True)
            self.note(f"{heard.label} asked for a lot in one go, more than you can hold, so you asked to do it in parts", False)
            await self.speak(TOO_MUCH, False)
            return replace(reading, request=Request("chat"), answered=True)
        if request.kind == "other" and self.trying is not None and not reading.answered and new_act(heard.text, self.name.lower()):
            self.record("other_tried", source=reading.source, person=heard.person_id)
            reading = replace(reading, request=Request("try_new", text=plain_words(heard.text)[:160]))
            request = reading.request
        if request.kind in ("chat", "other"):
            if reading.answered and request.kind == "chat":
                await self.speak("Okay, never mind.", False)
                self.note(f"{heard.label} said never mind to your question", False)
            if request.kind == "other" or reading.source != "rules":
                self.record("understood", text=heard.text, request=reading.as_dict(), source=reading.source, person=heard.person_id)
            return reading
        self.record("understood", text=heard.text, request=reading.as_dict(), source=reading.source, person=heard.person_id, early=early or None)
        if reading.ask == "speaker" and request.kind not in CLAIMABLE:
            await self.act(request, asker, "named")
            return reading
        if reading.ask:
            await self.ask(reading, asker)
            return reading
        self.question_text = heard.text
        if heard.stop is not None and request.kind in MOVING:
            self.note(f"{heard.label} said stop in the same breath as asking you to {for_mind(request)}, so you stayed still", False)
            return reading
        if early:
            verdict = await self.act(request.with_(then=()), asker, "named" if named else "heard")
            self.early = Early(number, request, asker, self.runner.current if verdict.yes else None, verdict.answer)
            return reading
        await self.act(request, asker, "named" if named else "heard")
        if reading.left:
            self.record("reading_partly", left=len(reading.left))
            self.note(f"you could not read every word {heard.label} said, so you did what you understood and said so", False)
            await self.speak(NOT_ALL, False)
        return reading

    async def _finish(self, heard: Heard, ctx: Context, door: Door, number: int) -> None:
        try:
            final = await self.understanding.finish(heard.text, ctx, door)
        except Exception:
            log.exception("could not finish reading a line of %d words", len((heard.text or "").split()))
            final = door.rules or Reading(Request("chat"))
        early = self.early if self.early is not None and self.early.number == number else None
        if early is None:
            self.record("superseded", request=final.as_dict(), source=final.source)
            return
        self.early = None
        if number < self._acted_on:
            self.record("superseded", request=final.as_dict(), source=final.source)
            return
        asker = self.fresh(early.asker)
        running = early.activity is not None and self.runner.current is early.activity
        self.record("reading_finished", source=final.source, request=final.as_dict(), same=first_step(final.request) == first_step(early.request) and not final.ask)
        if final.source == "rules":
            self._continue(early, early.request, asker, running)
            if door.left:
                self.note(f"you could not read every word {heard.label} said in time, so you did what you understood and said so", False)
                await self.speak(NOT_ALL, False)
            return
        if final.too_much:
            self._undo(early, running, "it was more than you could do in one go")
            await self.speak(TOO_MUCH, False)
            return
        if final.ask:
            self._undo(early, running, "you were not sure what they meant")
            await self.ask(final, asker)
            return
        if not final.request.action:
            self._undo(early, running, f"{heard.label} turned out not to be asking for that")
            return
        line, parts = not_yet(final.request, self.later is not None)
        if line:
            self.record("not_yet", parts=parts, asked=final.request.kind, person=asker.id)
            self.note(f"{asker.label} also asked for something you can't do yet ({', '.join(parts)}), so you said so", False)
            await self.speak(line, False)
            return
        if self.later is not None and (final.request.when is not None or final.request.on is not None or final.request.branch):
            self._undo(early, running, "it was for later or depended on something")
            await self.act(final.request, asker, "heard")
            return
        if first_step(final.request) == first_step(early.request):
            self._continue(early, final.request, asker, running)
            return
        if early.answer == "no" and final.request.kind == early.request.kind:
            return
        await self.act(final.request, asker, "heard")

    def _continue(self, early: Early, request: Request, asker: Asker, running: bool) -> None:
        rest = expand(request)[1:]
        if running:
            self.plan = Plan(asker, rest) if rest else None
            return
        if early.answer != "yes" or not rest:
            return
        self._spawn(self.act(rest[0].with_(then=tuple(rest[1:])), asker, "then"))

    def _undo(self, early: Early, running: bool, why: str) -> None:
        self.record("reading_undone", request=early.request.as_dict())
        if running:
            self.plan = None
            self.runner.end("stopped", f"you stopped {early.activity.describe()} because {why}")

    async def read_words(self, text: str, asker: Asker, purpose: str = UNDERSTAND) -> Reading:
        self.question_text = text
        ctx = self.context(None, asker)
        if not asker.own:
            person = self.company.book.get(asker.id) if asker.id else None
            ctx = replace(ctx, speaker=person.label.lower() if person is not None else None, tier=asker.tier)
        return await self.understanding.read(text, ctx, purpose=purpose)

    async def request_words(self, text: str, asker: Asker, how: str = "mind") -> tuple[Reading, Verdict | None]:
        reading = await self.read_words(text, asker)
        if not reading.request.action or reading.ask or reading.too_much:
            return reading, None
        return reading, await self.act(reading.request, asker, how)

    async def warm_request(self, text: str, person_id: str | None) -> bool:
        if not self.understanding.leads:
            return False
        try:
            return await self.understanding.warm(text, self.context(SimpleNamespace(person_id=person_id)))
        except Exception:
            log.exception("could not read a request ahead")
            return False

    async def answer_room(self, heard: Heard) -> str | None:
        reading = await self.understanding.read(heard.text, self.context(heard))
        request = reading.request
        if request.kind not in ("where_is", "what_is", "what_see") or reading.ask:
            return None
        asker = self.asker_heard(heard)
        verdict = decide(request, asker, self.situation(refusals_left=self.refusals_left(), thing=request.thing))
        if verdict.answer != "yes":
            return None
        return await self.answer(request, asker)

    def _claimed(self, name: str) -> Asker | None:
        now = self.clock.now()
        for person in self.company.here(now):
            if person.answers_to(name):
                return self.asker_for(person.id)
        return None

    async def ask(self, reading: Reading, asker: Asker, note: str | None = None) -> None:
        now = self.clock.now()
        self.pending = Pending(reading.ask, reading.request, reading.question, asker.id, now)
        self.runner.kit.face.show("curious")
        self.note(note or f"{asker.label} asked you to {for_mind(reading.request)}, but you were not sure, so you asked: {reading.question}", False)
        self.record("asked", about=reading.ask, request=reading.request.as_dict(), question=reading.question, person=asker.id)
        await self.speak(await self.words_for("ask", reading.request, reading.question), False)

    def _fixed(self, request: Request, line: str, verdict: Verdict | None) -> bool:
        if line in FIXED_LINES or request.kind in ("harm", "watch", "look_away"):
            return True
        if verdict is None:
            return False
        reason = verdict.reason or ""
        return verdict.law is not None or reason.startswith(LIFE_REASONS) or reason == PRIVACY_REASON or "privacy" in reason or "private" in reason

    async def words_for(self, answer: str, request: Request, line: str, verdict: Verdict | None = None) -> str:
        if self.own_words is None or not line or self._fixed(request, line, verdict):
            return line
        try:
            return await self.own_words.word(answer, line, verdict.reason if verdict is not None else "", for_mind(request))
        except Exception:
            log.exception("could not find its own words for a decision")
            return line

    async def _worded(self, answer: str, request: Request, verdict: Verdict) -> None:
        await self.speak(await self.words_for(answer, request, verdict.say, verdict), False)

    def recall(self, thing: str, stranger: bool = False) -> str:
        if self.things is None:
            return ""
        return self.things.answer(thing, self.clock.now(), self.clock.local, stranger)

    def strangers_near(self) -> bool:
        now = self.clock.now()
        return self.company.someone_new(now) or any(self.company.tier(person, now) == STRANGER for person in self.company.here(now))

    async def _sight(self, closely: bool):
        eyes = self.runner.kit.eyes
        if not getattr(eyes, "available", False):
            return None
        look = getattr(eyes, "look_closely", None) if closely else None
        if look is not None:
            try:
                sight = await asyncio.wait_for(look(), CLOSE_LOOK_S)
            except Exception:
                sight = None
            if sight is not None:
                return sight
        return eyes.latest(1.0)

    async def what_is(self) -> str:
        sight = await self._sight(True)
        if sight is None:
            return "I can't see anything just now."
        things = [t for t in sight.things if t.score >= MAYBE_SCORE]
        if not things:
            return "I'm not sure what that is."
        centre = min(things, key=lambda t: abs(t.bearing_deg) + 0.5 * abs(t.elevation_deg))
        slow = [t for t in things if t.lane == "slow" and abs(t.bearing_deg - centre.bearing_deg) <= 8.0]
        if slow:
            centre = max(slow, key=lambda t: t.score)
        if centre.score < SURE_SCORE:
            return f"I think that's {with_article(centre.label)}, but I'm not sure."
        return f"That's {with_article(centre.label)}."

    async def what_see(self, asker: Asker) -> str:
        sight = await self._sight(False)
        if sight is None:
            return "I can't see anything just now."
        things = sorted((t for t in sight.things if t.score >= MAYBE_SCORE), key=lambda t: (not t.animal, t.lane != "slow", -t.width_frac * t.height_frac))
        names = list(dict.fromkeys(with_article(t.label) for t in things))[:SEE_MAX]
        people = len(sight.people)
        who = []
        if people == 1:
            who = ["you"] if asker.here and not asker.own else ["someone"]
        elif people > 1:
            who = [f"{people} people"]
        seen = who + names
        if not seen:
            return "Nothing much, just the room."
        return f"I can see {listing(seen)}."

    async def answer(self, request: Request, asker: Asker) -> str:
        if self.alive is not None:
            said = await self.alive.answer(request, asker)
            if said:
                return said
        if request.kind == "where_is":
            return self.recall(request.thing, asker.tier == STRANGER) or "I don't keep track of things yet."
        if request.kind == "sight_question":
            return await self.look_closer(self.question_text or "What can you see?")
        if request.kind == "remember_spot":
            return self.remember_spot(request.name)
        if request.kind == "where_am_i":
            return "I'm not sure where I am."
        if request.kind == "teach":
            return "I can't remember things like that yet."
        if request.kind == "what_is":
            return await self.what_is()
        return await self.what_see(asker)

    def remember_spot(self, name: str) -> str:
        nav = getattr(self.runner.kit, "nav", None)
        remember = getattr(nav, "remember_spot", None)
        if remember is None:
            return "I can't remember spots like that yet."
        label = name or "here"
        if not remember(label):
            return "I'm not sure where I am, so I can't remember this spot."
        return f"Okay, I'll remember this spot as the {name}." if name else "Okay, I'll remember this spot."

    async def look_closer(self, question: str) -> str:
        privacy = getattr(self, "privacy", None)
        refused = privacy.refusal() if privacy is not None else None
        if refused:
            return refused
        if self.pictures is None or not await self.pictures.can_look():
            return "I can't look at pictures closely just now."
        self.runner.kit.face.show("thinking")
        await self.speak("Let me have a close look.", False)
        answer, sure = await self.pictures.ask(question)
        self.record("picture_question", question=question[:200], answer=answer, sure=sure)
        return answer

    def curious(self, label: str, animal: bool, new_kind: bool) -> None:
        self.wonder = (label, animal, self.runner.kit.pace.now())
        self._follow_curiosity()

    def _follow_curiosity(self) -> None:
        if self.wonder is None:
            return
        label, animal, noticed = self.wonder
        mono = self.runner.kit.pace.now()
        if mono - noticed > WONDER_KEEP_S:
            self.wonder = None
            return
        if self.runner.busy or (self.trying is not None and self.trying.loop is not None) or (self.teaching is not None and self.teaching.busy()) or mono - self.curious_at < CURIOUS_GAP_S or mono - self.born_at < CURIOUS_SETTLE_S:
            return
        privacy = getattr(self, "privacy", None)
        if privacy is not None and privacy.hushed():
            return
        sit = self.situation()
        if sit.alarm or sit.calm or sit.quiet or sit.asleep or sit.resting or sit.docked or sit.waking or sit.low_battery or sit.fear >= 4.0 or not sit.can_move:
            return
        traits = self.personality().get("traits") or {}
        if sit.curiosity < 0.25 and float(traits.get("curious", 5)) < 6:
            return
        self.curious_at = mono
        self.wonder = None
        request = Request("look" if animal else "go_to_thing", thing=label)
        self._spawn(self.act(request, PEBBLE, "curious"))

    def target_for(self, request: Request, asker: Asker) -> tuple[Target | None, str]:
        if request.kind == "play" and request.to:
            return self.target_for(Request("come", who=request.to), asker)
        if request.thing or request.kind not in ("follow", "come", "look"):
            return None, ""
        who = request.who or "me"
        if who == "me":
            if asker.own:
                return None, "say who"
            return Target(asker.id, asker.label, asker.tier), ""
        person = self.company.book.find(who)
        if person is None:
            return Target(None, who.title(), STRANGER), ""
        now = self.clock.now()
        if person.id not in self.company.presence.here(now):
            return None, f"I can't see {person.label} here."
        return Target(person.id, person.label, self.company.tier(person, now)), ""

    def _find_where_usual(self, request: Request) -> Request:
        if request.kind != "come" or request.who in ("", "me") or self.alive is None:
            return request
        person = self.company.book.find(request.who)
        if person is None or person.id in self.company.presence.here(self.clock.now()):
            return request
        room = self.alive.usual_room(person.id)
        if room is None:
            return request
        self.note(f"{person.label} is not here, so you will look for them in the {room}, where they usually are", False)
        return Request("go_to_place", place=room, then=(request.with_(then=()),) + tuple(request.then))

    async def act(self, request: Request, asker: Asker, how: str, battery: bool = False, routed: bool = False) -> Verdict:
        if how == "gesture" and getattr(self.runner.current, "game", False):
            reason = "a game is on, and waving arms are part of the game"
            self.record("request", how=how, person=asker.id, tier=asker.tier, request=request.as_dict(), answer="no", reason=reason)
            return Verdict("no", reason, "")
        request, aim, refused = await self._refer(request, asker, how)
        if refused is not None:
            return refused
        line, parts = not_yet(request, self.later is not None)
        if line:
            self.record("not_yet", how=how, parts=parts, asked=request.kind, person=asker.id, tier=asker.tier)
            if not asker.own:
                self.note(f"{asker.label} asked you to {for_mind(request)}, which you can't do yet, so you said so", False)
                self.runner.kit.face.show("thinking")
                await self.speak(line, False)
            return Verdict("no", f"you can't {for_mind(request)} yet", "" if asker.own else line)
        if self.rules is not None and not routed:
            ruled = await self.rules.route(request, asker, how)
            if ruled is not None:
                return ruled
        if self.later is not None and not routed:
            routed_verdict = await self.later.route(request, asker, how)
            if routed_verdict is not None:
                return routed_verdict
        if request.kind == "try_new":
            return await self._try_new(request, asker, how)
        if self.teaching is not None and request.kind in ("go_to_place", "go_back", "go_to_thing") and not request.then:
            taught = await self.teaching.take_route(request, asker, how)
            if taught is not None:
                return taught
        if request.kind == "check" and not patrol(request):
            aim, refused = await self._aim(request, asker, how)
            if refused is not None:
                return refused
        asked = request
        if request.repeat > 1 or any(step.repeat > 1 for step in request.then):
            steps = expand(request)
            request = steps[0].with_(then=tuple(steps[1:]))
        if self.rules is not None:
            kept = await self.rules.check(request, asker, how)
            if kept is not None:
                return kept
        if how != "then":
            found = self._find_where_usual(request)
            if found is not request and self.rules is not None:
                kept = await self.rules.check(found, asker, how, newest=False)
                if kept is not None:
                    return kept
            request = found
        target, problem = self.target_for(request, asker)
        if problem:
            verdict = Verdict("no", problem, problem if not asker.own else "")
            await self._answer(request, asker, verdict, how)
            return verdict
        sit = self.situation(target_tier=target.tier if target else None, target_label=target.label if target else "", refusals_left=self.refusals_left(), thing=request.thing)
        verdict = decide(request, asker, sit)
        if verdict.answer == "ask" and how == "named":
            verdict = Verdict("no", "you asked who was asking and still could not tell", WHO_UNSEEN)
        if request.kind in QUESTIONS:
            if verdict.answer == "yes":
                said = await self.answer(request, asker)
                verdict = Verdict("yes", verdict.reason, said)
                self.note(f"{asker.label} asked you to {for_mind(request)}; you said: {said}" if not asker.own else f"you said: {said}", False)
                self.record("request", how=how, person=asker.id, tier=asker.tier, request=request.as_dict(), answer="yes", reason=verdict.reason, said=said)
                self.runner.kit.face.show("curious" if "not sure" in said else "happy")
                self._did(asked, asker, how)
                await self.speak(said, False)
                return verdict
            await self._answer(request, asker, verdict, how)
            return verdict
        if verdict.answer == "yes" and request.kind == "watch" and not asker.own:
            verdict = Verdict(verdict.answer, verdict.reason, honesty(request, self.question_text), verdict.release_stop, verdict.replaces, verdict.used_refusal)
        if verdict.answer == "yes" and request.kind in ("follow", "come", "look") and target is not None and target.id is None and request.who not in ("", "me"):
            verdict = Verdict("yes", verdict.reason + f"; you have not met {target.label}, so you go to whoever you can see", verdict.say)
        reply, replacement = "", None
        current = self.runner.current
        if verdict.answer == "yes" and request.kind == "adjust" and current is not None:
            reply, replacement = current.adjust(request)
            if reply:
                verdict = Verdict(verdict.answer, verdict.reason, reply, verdict.release_stop, verdict.replaces, verdict.used_refusal)
        if request.kind in ("stop_activity", "release") and verdict.answer == "yes" and self.runner.current is None:
            self.record("request", how=how, person=asker.id, tier=asker.tier, request=request.as_dict(), answer=verdict.answer, reason=verdict.reason)
            if request.then:
                return await self.act(request.then[0].with_(then=request.then[1:]), asker, how)
            if verdict.say and request.kind == "release":
                await self.speak(verdict.say, False)
            return verdict
        await self._answer(request, asker, verdict, how)
        if verdict.answer != "yes":
            if verdict.used_refusal:
                self._spend_refusal()
            if how == "then" and verdict.answer == "no" and self.unstuck is not None:
                self.unstuck.refused(request, asker, verdict)
            return verdict
        if verdict.release_stop:
            if self.company.guard.go(True):
                self.note(f"{asker.label} asked you to move, which counts as saying you may move again", False)
        kind = request.kind
        if kind in ("stop_activity", "release"):
            self.plan = None
            self.runner.end("released" if kind == "release" else "stopped", f"{asker.label} asked you to {'carry on with your own things' if kind == 'release' else 'stop'}")
            if request.then:
                return await self.act(request.then[0].with_(then=request.then[1:]), asker, how)
            return verdict
        if kind == "adjust":
            if current is None:
                return verdict
            if replacement is not None:
                if replacement.kind == "release":
                    self.runner.end("released", f"{asker.label} said you could carry on")
                else:
                    self.runner.start(activity_for(replacement, current.asker, current.target, current.battery))
            return verdict
        if how in FOLLOWS_PLAN:
            words = self.plan.words if self.plan is not None else ""
            rest = list(request.then) + (self.plan.steps if self.plan is not None else [])
            self.plan = Plan(asker, rest, words) if rest else None
        else:
            words = self.question_text if how in ("heard", "named") and not asker.own else ""
            self.plan = Plan(asker, list(request.then), words) if request.then else None
        tree = reads_result(self.plan.steps) if self.plan is not None else False
        watched = self.company.book.find(request.who) if kind == "watch" and request.who not in ("", "me") else None
        activity = activity_for(request.with_(then=()), asker, target, battery, aim, self.question_text, tree, bool(watched is not None and watched.is_child))
        activity.words = words
        activity.heard_by = tuple(sorted(self.company.presence.here(self.clock.now())))
        self._did(asked, asker, how)
        if self.alive is not None:
            try:
                activity.delay = self.alive.before(request)
            except Exception:
                log.exception("the glance before acting failed")
        self.runner.start(activity)
        if request.until == "asked" and not asker.own:
            self._spawn(self.speak(ASKED_LINE, False))
        return verdict

    async def _refused(self, request: Request, asker: Asker, line: str, reason: str) -> Verdict:
        self.record("request", how="refs", person=asker.id, tier=asker.tier, request=request.as_dict(), answer="no", reason=reason)
        if asker.own:
            return Verdict("no", reason, "")
        self.note(f"{asker.label} asked you to {for_mind(request)}, but {reason}, so you said so", False)
        self.runner.kit.face.show("thinking")
        await self.speak(line, False)
        self.refused_to(asker, line, for_mind(request))
        return Verdict("no", reason, line)

    def _fill_again(self, request: Request, last: Request) -> Request:
        if request.branch:
            return request.with_(then=tuple(self._fill_again(step, last) for step in request.then), else_=tuple(self._fill_again(step, last) for step in request.else_))
        then = tuple(self._fill_again(step, last) for step in request.then)
        if request.kind == "again":
            found = again_for(request, last)
            return found.with_(then=tuple(found.then) + then)
        return request.with_(then=then)

    async def _refer(self, request: Request, asker: Asker, how: str) -> tuple:
        now = self.clock.now()
        nothing_running = self.runner.current is None
        wants = any(step.kind == "again" for step in request.steps()) or (request.kind == "adjust" and request.change in ("other_way", "again") and nothing_running)
        if wants:
            last = None if asker.own else self.refs.last(asker.id, now)
            if last is None:
                turning = request.kind == "adjust" and request.change == "other_way"
                return request, None, await self._refused(request, asker, WHICH_WAY if turning else NOTHING_AGAIN, "you had done nothing for them in the last half hour to do again")
            if request.kind == "adjust" and request.change == "other_way":
                turned = flipped(last)
                if turned is None:
                    return request, None, await self._refused(request, asker, WHICH_WAY, "the last thing you did for them had no way to turn round")
                request = turned
            elif request.kind == "adjust":
                request = last
            else:
                request = self._fill_again(request, last)
            self.record("again", person=asker.id, request=request.as_dict())
        if request.kind == "go_back" and request.place == "before":
            before = self.refs.before
            if before is None:
                return request, None, await self._refused(request, asker, NO_BEFORE, "you did not remember where you were before your last trip")
            words = f"where you were before, in the {before.room}" if before.room else "where you were before"
            return request, (before.x, before.y, words), await self._spot_refusal(before.x, before.y, request, asker, how)
        if request.kind == "go_to_place" and request.who and not request.place:
            person = self.company.book.get(asker.id) if request.who in ("", "me") and asker.id else self.company.book.find(request.who)
            if person is None:
                return request, None, await self._refused(request, asker, f"I don't know who {request.who.title()} is.", "you do not know who that is")
            seen = self.refs.where(person.id, now)
            label = person.label
            if seen is None:
                old = now - self.company.presence.last_present(person.id) > SEEN_OLD_S
                question = f"I haven't seen {label} for over an hour, so I don't know where they were any more. Which room should I go to?" if old else f"I didn't see where {label} was. Which room should I go to?"
                if asker.own:
                    return request, None, Verdict("no", "you did not know where they had been", "")
                await self.ask(Reading(Request("go_to_place"), "place", question), asker)
                return request, None, Verdict("ask", "you did not know where they had been", question)
            words = f"where {label} was" + (f" in the {seen.room}" if seen.room else "")
            return request, (seen.x, seen.y, words), await self._spot_refusal(seen.x, seen.y, request, asker, how)
        return request, None, None

    def _room_at(self, x: float, y: float) -> str:
        rooms = getattr(getattr(self, "privacy", None), "rooms", None)
        try:
            return (rooms.room_at(x, y) if rooms is not None else None) or ""
        except Exception:
            return ""

    def _private(self, room: str, x: float | None = None, y: float | None = None) -> bool:
        if room in PRIVATE_NAMES:
            return True
        privacy = getattr(self, "privacy", None)
        if privacy is None:
            return False
        if room and privacy.rooms.private(room) and not privacy.permitted(room):
            return True
        return x is not None and privacy.blocks(x, y) is not None

    async def _spot_refusal(self, x: float, y: float, request: Request, asker: Asker, how: str) -> Verdict | None:
        room = self._room_at(x, y)
        if self._private(room, x, y):
            return await self._refused(request, asker, f"That's in the {room}, and it's private, so I won't go in." if room else "That's somewhere private, so I won't go in.", "that spot is in a private room")
        if room and self.rules is not None:
            return await self.rules.check(Request("go_to_place", place=room), asker, how)
        return None

    async def _aim(self, request: Request, asker: Asker, how: str) -> tuple:
        kit = self.runner.kit
        aim = None
        place = request.place if request.place and not whole_house(request.place) else ""
        if place:
            found = find_place(kit, place)
            if found is not None:
                aim = Aim(found[0], found[1], found[2], False, place if kit.place_at(place) is not None else self._room_at(found[0], found[1]))
        elif request.thing:
            found = find_place(kit, request.thing)
            spot = found[:2] if found is not None else kit.thing_at(request.thing)
            if spot is not None:
                aim = Aim(spot[0], spot[1], 0.5, True, self._room_at(spot[0], spot[1]))
        room = (aim.room if aim is not None else "") or place
        if self._private(room, aim.x if aim is not None else None, aim.y if aim is not None else None):
            self.record("check_refused", why="private", person=asker.id)
            return aim, await self._refused(request, asker, CANT_LOOK, "that room is private, and you never look in a private room for anyone its rule doesn't allow")
        if room and not place and self.rules is not None:
            kept = await self.rules.check(Request("check", place=room), asker, how)
            if kept is not None:
                return aim, kept
        if aim is None:
            if place:
                return aim, await self._refused(request, asker, f"I don't know the way to the {place} yet.", "you do not know where that room is yet")
            if asker.own:
                return aim, Verdict("no", "you did not know where to look", "")
            if how == "later":
                return aim, None
            question = f"I don't know where {target_words(request)} is. Which room is it in?" if request.thing else NOWHERE_TO_CHECK
            await self.ask(Reading(request, "place", question), asker)
            return aim, Verdict("ask", "you did not know where to look", question)
        return aim, None

    def _did(self, request: Request, asker: Asker, how: str) -> None:
        if how in DONE_HOW and not asker.own:
            self.refs.did(asker.id, asker.label, request, self.clock.now())
        if self.on_did is not None and not asker.own:
            try:
                self.on_did(request, asker, how)
            except Exception:
                log.exception("could not note a step being taught")

    def started(self, activity: Activity) -> None:
        if activity.kind not in TRIPS:
            return
        odometer = self.runner.kit.odometer
        if odometer is None or not getattr(odometer, "usable", False):
            return
        x, y, _ = odometer.pose()
        self.refs.trip(x, y, self._room_at(x, y), self.clock.now())

    async def picture_answer(self, question: str) -> tuple[str, bool]:
        if self.pictures is None:
            return "I can't look at pictures closely just now.", False
        answer, sure = await self.pictures.ask(question)
        self.record("picture_question", question=question[:200], answer=answer, sure=sure)
        return answer, sure

    def _watched(self, activity: Activity, ending: Ending) -> bool:
        asker = activity.asker
        if asker.own:
            return False
        kit = self.runner.kit
        if activity.alert is not None:
            kind, line = activity.alert
            self.plan = None
            spot = kit.where_was(asker.id) if asker.id else None
            self.record("watch_alert", what=kind, person=asker.id)
            self.runner.start(Fetch(Request("come", who=asker.label.lower()), asker, None, False, line, spot))
            return True
        if activity.alarmed or activity.back or ending.how == "done":
            return False
        if self.situation().alarm or getattr(self.runner.current, "urgent", False):
            return False
        if ending.how in ("stopped", "released") and "asked you" in ending.text:
            return False
        why = f" {ending.say}" if ending.say else ""
        self.record("watch_stopped", how=ending.how, person=asker.id)
        kit.say_loud(f"{asker.label}! I've stopped keeping an eye on {activity.name}.{why}")
        return False

    async def _answer(self, request: Request, asker: Asker, verdict: Verdict, how: str) -> None:
        who = "you decided" if asker.own else f"{asker.label} asked you"
        what = for_mind(request)
        result = {"yes": "you said yes", "no": f"you said no ({verdict.reason})", "ask": f"you asked first ({verdict.reason})"}[verdict.answer]
        if asker.own:
            text = f"You decided to {what}; {result}"
        else:
            text = f"{who} to {what}; {result}"
        self.note(text, verdict.answer != "yes")
        self.record("request", how=how, person=asker.id, tier=asker.tier, request=request.as_dict(), answer=verdict.answer, reason=verdict.reason)
        if verdict.answer == "no" and verdict.say:
            self.refused_to(asker, verdict.say, what)
        if verdict.answer == "ask":
            reading = Reading(request, "speaker", question_for("speaker", request, self.context(None)))
            await self.ask(reading, asker)
            return
        if not verdict.say:
            return
        face = self.runner.kit.face
        if verdict.answer == "yes":
            face.show("happy" if request.kind not in ("back_off",) else "surprised")
            if how == "curious":
                face.show("curious")
                self._spawn(self.speak(f"Ooh, {with_article(request.thing)}." if request.thing else "Ooh.", False))
            elif not asker.own and how not in ("unstuck", "taught"):
                if self.own_words is None:
                    self._spawn(self.speak(verdict.say, False))
                else:
                    self._spawn(self._worded("yes", request, verdict))
        else:
            face.show("thinking")
            if self.own_words is None:
                await self.speak(verdict.say, True)
            else:
                await self.speak(await self.words_for("no", request, verdict.say, verdict), False)

    def ended(self, activity: Activity, ending: Ending) -> None:
        if self.teaching is not None:
            try:
                self.teaching.ended(activity, ending)
            except Exception:
                log.exception("teaching could not hear that an activity ended")
        if activity.kind == "look" and activity.request.place == "there" and ending.text.startswith(POINTED_AT):
            self.refs.mention(f"the {ending.text[len(POINTED_AT):]}, where they pointed", self.clock.now())
        if activity.kind == "check" and getattr(activity, "found", None) is not None:
            self.checks.put(activity.asker.id, activity.request.name, activity.found, self.clock.now())
            owed = getattr(activity, "owed", "")
            if owed and self.later is not None and activity.asker.id is not None:
                self.later.agenda.owe(activity.asker.id, owed if owed.startswith(("I ", "I'")) else owed[:1].lower() + owed[1:], self.clock.now(), fresh=True)
        if self.later is not None:
            try:
                self.later.ended(activity, ending)
            except Exception:
                log.exception("the agenda could not hear that an activity ended")
        if getattr(activity, "quiet", False):
            return
        if ending.how == "updated":
            self.record("activity_end", activity=activity.kind, how=ending.how, text=ending.text, person=activity.asker.id)
            return
        took = None if activity.started_at is None else self.runner.kit.pace.now() - activity.started_at
        lasted = "" if took is None else (f" after {round(took)} seconds" if took < 120 else f" after {round(took / 60)} minutes")
        who = "" if activity.asker.own else f" (asked by {activity.asker.label})"
        self.note(f"you {ENDED_WORDS.get(ending.how, 'stopped')} {activity.describe()}{who}{lasted}: {ending.text}", ending.how not in ("done", "released", "stopped", "replaced"))
        self.diary(self._diary_line(activity, ending, took), "activity")
        self.record("activity_end", activity=activity.kind, how=ending.how, text=ending.text, person=activity.asker.id, target=activity.target.id if activity.target else None, seconds=None if took is None else round(took, 1))
        face = ENDING_FACES.get(ending.how)
        if face:
            self.runner.kit.face.show(face)
        if activity.kind == "watch" and self._watched(activity, ending):
            return
        if activity.urgent:
            self._seek_done(activity, ending)
            return
        if self.unstuck is not None:
            self.unstuck.observe(activity, ending)
        if activity.kind == "try_new" and self.trying is not None and self.trying.ended(activity, ending):
            return
        if self.unstuck is not None and self.unstuck.ended(activity, ending):
            return
        if activity.kind == "try_new" and self.trying is not None and ending.how not in ("done", "stopped", "replaced"):
            self.trying.dropped(activity, ending)
        if ending.say:
            self._spawn(self.speak(ending.say, True))
        if ending.how in ("replaced", "stopped", "released"):
            if ending.how != "replaced":
                self.plan = None
            return
        if ending.next is not None:
            self.runner.start(activity_for(ending.next, activity.asker, activity.target, activity.battery))
            return
        plan = self.plan
        if ending.how == "done" and plan is not None and plan.steps:
            step = plan.steps.pop(0)
            if not plan.steps:
                self.plan = None
            self._spawn(self.act(step, self.fresh(plan.asker), "then"))
        elif ending.how != "done":
            self.plan = None

    def _diary_line(self, activity: Activity, ending: Ending, took: float | None) -> str:
        who = activity.who()
        minutes = "" if took is None else (f" for {round(took)} seconds" if took < 120 else f" for {round(took / 60)} minutes")
        verbs = {"try_new": "I tried something new", "copy_me": "I played copy me", "route": "I took a way I was taught", "drive": "I was driven with the touch pad", "follow": f"I followed {who}", "come": f"I went to {who}", "wait": "I waited", "look": f"I watched {who}", "back_off": "I backed off", "go_home": "I headed home", "turn": "I turned", "move": "I moved", "seek_people": "I went looking for someone", "check": "I went to check something", "watch": "I kept an eye on someone", "fetch": "I went to get someone", **HOUSEHOLD_DIARY}
        start = verbs.get(activity.kind, f"I did {activity.kind}")
        asked = "" if activity.asker.own else (f" because {activity.asker.label} asked" if activity.kind != "go_home" or not activity.battery else "")
        if activity.battery:
            asked = " because my battery was low"
        return f"{start}{minutes}{asked}, {DIARY_ENDS.get(ending.how, 'and then stopped')}."

    def _spawn(self, coro) -> None:
        try:
            task = asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            coro.close()
            return
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def seek_people(self, why: str, done: Callable[[str, str], None]) -> bool:
        privacy = getattr(self, "privacy", None)
        if privacy is not None:
            privacy.sync()
        if not self.can_see() and not (privacy is not None and privacy.holds):
            return False
        sit = self.situation()
        if sit.fault or sit.blocked:
            return False
        current = self.runner.current
        if current is not None and current.urgent:
            current.done = done
            current.why = why
            return True
        self.plan = None
        self.record("seek_people", why=why)
        self.runner.start(SeekPeople(Request("come"), PEBBLE, None, why=why, done=done))
        return True

    def end_seek(self, why: str) -> bool:
        current = self.runner.current
        if current is None or not current.urgent:
            return False
        current.done = None
        self.runner.end("released", f"you stopped looking for people ({why})")
        return True

    def quake_round(self, why: str, done: Callable[[dict], None]) -> bool:
        if not self.can_see():
            return False
        sit = self.situation()
        if sit.fault or sit.blocked:
            return False
        current = self.runner.current
        if current is not None and current.urgent:
            return False
        self.plan = None
        self.record("quake_round", why=why)
        self.runner.start(QuakeRound(Request("quake_round"), PEBBLE, None, why=why, report=done))
        return True

    def _seek_done(self, activity: Activity, ending: Ending) -> None:
        if ending.how == "done" and getattr(activity, "door", None):
            result, detail = "door", activity.door
        elif ending.how == "done":
            here = self.company.here(self.clock.now())
            result, detail = "found", (here[0].label if here else "someone")
        elif ending.how in ("lost", "timeout"):
            result, detail = "nobody", ending.text
        else:
            result, detail = "blocked", ending.text
        done = getattr(activity, "done", None)
        if done is None:
            return
        try:
            done(result, detail)
        except Exception:
            log.exception("the seek callback failed")

    def start_battery_homing(self) -> bool:
        current = self.runner.current
        if current is not None and current.kind == "go_home":
            return True
        request = Request("go_home")
        sit = self.situation(refusals_left=3)
        verdict = decide(request, PEBBLE, sit)
        self.record("request", how="battery", person=None, tier=SELF, request=request.as_dict(), answer=verdict.answer, reason=verdict.reason)
        if verdict.answer != "yes":
            return False
        self.plan = None
        line = self.rules.for_charger() if self.rules is not None else ""
        if line:
            self.note(line, False)
            self._spawn(self.speak(line, False))
        self.runner.start(GoHome(request, PEBBLE, None, battery=True))
        return True

    def tick(self) -> None:
        now = self.clock.now()
        if self.pending is not None and now - self.pending.at > PENDING_S:
            self.record("question_expired", about=self.pending.about, request=self.pending.request.as_dict())
            self.pending = None
        self._follow_curiosity()
        if self.household is not None:
            try:
                self.household.tick()
            except Exception:
                log.exception("the household tick failed")
        if self.trying is not None:
            try:
                self.trying.tick()
            except Exception:
                log.exception("the try loop's tick failed")
        current = self.runner.current
        if current is None:
            return
        sit = self.situation()
        if sit.asleep:
            self.runner.end("stopped", "you fell asleep")
            return
        if not current.moving and current.kind != "look":
            return
        if current.homing or current.urgent:
            if sit.fault:
                self.runner.end("blocked", "a sensor fault turned the wheels off", "Something's wrong with my sensors, so I'm stopping.")
            return
        reason = None
        if sit.fault:
            reason = ("blocked", "a sensor fault turned the wheels off", "Something's wrong with my sensors, so I'm stopping.")
        elif sit.low_battery and not current.battery:
            reason = ("battery", "your battery got low", "My battery's low, so I have to stop.")
        elif sit.quiet and current.moving and current.kind not in ("watch", "fetch"):
            reason = ("stopped", "quiet hours began", "It's my quiet time now, so I'll stop here.")
        elif sit.resting and current.moving:
            reason = ("stopped", "you got tired and went to rest", "I'm getting tired, so I'll stop here.")
        if reason is not None:
            self.runner.end(*reason)

    def describe(self) -> str | None:
        current = self.runner.current
        if current is None:
            return None
        who = "" if current.asker.own else f" for {current.asker.label}"
        return f"{current.describe()}{who}"

    def thinker(self):
        reader = getattr(self.understanding, "reader", None)
        minds = getattr(reader, "minds", None) or []
        return minds[0][1] if minds else None

    def present_within(self, person_id: str, seconds: float) -> bool:
        return person_id in self.company.presence.here(self.clock.now(), seconds)

    def decide_now(self, request: Request, asker: Asker) -> Verdict:
        return decide(request, asker, self.situation(refusals_left=self.refusals_left()))

    def words_problem(self, text: str) -> str:
        if not text:
            return ""
        names = tuple(n.lower() for person in self.company.book.people.values() for n in person.names + person.nicknames)
        if tactless(text):
            return "it remarks on how someone looks"
        if cruel(text, names) or harsh(text, names):
            return "it would be unkind to something alive"
        return ""

    def make_activity(self, request: Request, asker: Asker, target: Target | None) -> Activity:
        return activity_for(request, asker, target)

    def make_plan(self, asker: Asker, steps: list) -> Plan | None:
        return Plan(asker, list(steps)) if steps else None

    def did(self, request: Request, asker: Asker, how: str) -> None:
        self._did(request, asker, how)

    async def check_step(self, request: Request, asker: Asker, ahead: bool = False) -> tuple[Verdict, Target | None]:
        asker = self.fresh(asker)
        target, problem = self.target_for(request, asker)
        if problem:
            return Verdict("no", problem, problem if not asker.own else ""), None
        if self.rules is not None:
            kept = self._ruled(request)
            if kept is not None:
                return kept, None
        sit = self.situation(target_tier=target.tier if target else None, target_label=target.label if target else "", refusals_left=self.refusals_left() if ahead else 0, thing=request.thing)
        verdict = decide(request, asker, sit)
        if verdict.answer == "ask":
            verdict = Verdict("no", verdict.reason, WHO_UNSEEN)
        return verdict, target

    def _ruled(self, request: Request) -> Verdict | None:
        rules = self.rules
        try:
            places = rules.places_of(request)
            if not places or rules.exempt():
                return None
            found = [rule for rule in rules.holding() if rule.kind == "keep_out" and rule.place in places]
        except Exception:
            log.exception("could not read the house rules for a step")
            return None
        if not found:
            return None
        rule = found[0]
        return Verdict("no", f"{rule.by_label} asked you to stay out of the {rule.place}", rules.line(rule))

    async def _try_new(self, request: Request, asker: Asker, how: str) -> Verdict:
        if self.trying is None:
            line = NOT_YET_LINES["try_new"]
            self.record("not_yet", how=how, parts=["try_new"], asked=request.kind, person=asker.id, tier=asker.tier)
            if not asker.own:
                self.note(f"{asker.label} asked you to {for_mind(request)}, which you can't do yet, so you said so", False)
                self.runner.kit.face.show("thinking")
                await self.speak(line, False)
            return Verdict("no", f"you can't {for_mind(request)} yet", "" if asker.own else line)
        if self.teaching is not None and (request.name or "").startswith("howto:"):
            taught = await self.teaching.run_request(request, asker, how)
            if taught is not None:
                return taught
        words = request.text or request.name or ""
        if self.scripts is not None and not request.name and loopy(words) and self.scripts.can_write(asker):
            await self.scripts.ask_for(words, asker, how)
            return Verdict("yes", "you are writing a little program for it", "")
        if request.repeat > 1:
            words = request.text or request.name
            times = "twice" if request.repeat == 2 else f"{request.repeat} times"
            request = request.with_(text=(words if times in words else f"{words} {times}").strip()[:160], repeat=1)
        return await self.trying.start(request, asker, how)

    async def close(self) -> None:
        await self.runner.close()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)
