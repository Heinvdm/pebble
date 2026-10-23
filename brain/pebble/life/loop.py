import asyncio
import logging
import math
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..activities.card import Body as CardBody
from ..activities.card import Card
from ..activities.commands import Commands
from ..activities.gate import FEARED
from ..activities.gate import Situation as Circumstances
from ..activities.home import TagDockSeeker
from ..activities.kit import Kit, Pace
from ..activities.hazards import rough_gap_m
from ..activities.household import Household
from ..activities.picture import TIMEOUT_S as PICTURE_TIMEOUT_S
from ..activities.picture import PictureQuestions
from ..activities.runner import Runner
from ..activities.seeing import animals_ahead, life_ahead as small_life_ahead
from ..activities.skills import Skills
from ..activities.trying import Planner, Trying
from ..activities.unstuck import Unstuck
from ..activities.tools import ACTIVITY_TOOLS, THING_TOOLS, register_activity_tools
from ..age import FEAR_SCALE, age_days, parse_birthday, stage_for
from ..alive.core import Alive
from ..alive.hands import HandWatch
from ..house.core import House
from ..house.rules import HouseRules
from ..nav import Navigator
from ..alive.dream import TodayDecks
from ..blackbox import BlackBox
from ..body.api import Body
from ..body.sensors import PhoneSensors, SensorSnapshot
from ..body.telemetry import pack_fraction
from ..books import Books
from ..chaos.dial import DialInputs
from ..chaos.engine import Chaos
from ..chaos.ideas import IdeaDecks
from ..chaos.whims import WhimContext
from ..clock import Clock, iso
from ..diary import Diary
from ..goals import Item
from ..inner.state import InnerContext, InnerState
from ..link.client import LinkDown, LinkUp
from ..link.protocol import Event, Flags
from ..mind.base import Mind
from ..mind.decisions import OwnWords
from ..mind.budget import REPLY, meter_of
from ..mind.history import History
from ..mind.subconscious import Subconscious
from ..people.company import Company, Heard
from ..people.overnight import Overnight
from ..people.presence import REQUEST_S
from ..people.tools import LIVE_ONLY, PEOPLE_TOOLS
from ..picker import Choice, PickContext, SafetyContext, idle_options, pick, safety_options, score, task_options
from ..privacy.core import Privacy
from ..seams.face import Face, Touch, face_for
from ..seams.later import DockSeeker, Dreamer, NoDockSeeker, NoDreamer
from ..seams.sight import Eyes, NoEyes
from ..things.watch import ThingWatcher
from ..things.words import LANDMARKS, canonical
from ..understand.understanding import Understanding
from ..screen.gallery import Gallery
from ..script.live import Scripts
from ..seams.voice import Voice
from ..self.birth import be_born, ensure_seed, record_of
from ..self.dials import Dials
from ..self.drives import Recent
from ..self.drives import drives as read_drives
from ..self.drives import unmet
from ..self.growth import Growth
from ..self.plasticity import Plasticity
from ..self.registry import PEBBLE, WONDER_WORDS
from ..mind.prompt import ROOM
from ..mind.select import chosen_chars, pack
from ..self.tools import SELF_TOOLS, register_self_tools
from ..self.wonder import Wonder, threshold
from ..selfstore import CorruptFile, LockedFile, SealedFile, SelfStore, TamperedFile
from ..setup import WOKE_UP, Setup, finish
from ..status import Snapshot, format_status
from ..tools.builtin import Permissions
from .battery import LowBatteryRoutine
from .creative import Creative
from .folding import Folding
from .initiative import InitiativeGate
from .later import Later
from .memory import Memory
from .nightly import Nightly
from .observe import EventLog, observation_text
from .quiet import QuietHours
from .selection import Selection
from .states import LifeState, Situation, next_state
from .taskcard import TaskCard, live_of
from .turn import TurnRunner
from .wakeup import wake_note
from .whim_acts import WhimActs

log = logging.getLogger(__name__)

STATE_FILE = "state.json"
HOT_C = 42.0
PACK_RECOVER_MV = 3500
OVERHEAT_GAP_S = 300.0
STUCK_MEMORY_S = 30.0
BASE_TOOLS = ("look", "stop", "set_face", "remember", "add_task", "update_task", "list_tasks", "read_sensors", "get_battery", "add_event", "tune")
BUSY_LINE = "\nYou are busy: {doing}. Use end or do to change it."
DAY_TOOLS = ("draw_scene", "show_scene")
TOUCH_GAP_S = 2.0
GAZE_HOLD_S = 4.0
UPSET_S = 1800.0
LIFE_AHEAD_M = 0.6
PRUNE_EVERY_S = 3600.0
VIEW_SHOWN = 5
TOUCH_WORDS = {"tap": "tapped", "stroke": "stroked", "hold": "held a finger on"}
TRIGGER_EVENTS = frozenset({"obstacle", "dock"})
HEARD_KEEP = 12
CALM_S = 120.0
OTHERS_NEAR_M = 3.0
SETUP_CHECK_S = 30.0
SETUP_WAKE = "You are still being set up, so restarts and stops are normal and nothing is wrong."
FELT_EVENTS = {"shaken": "shake", "dropped": "drop", "tipped": "bump", "quake": "shake", "stairs": "drop"}
FELT_RECENT = {"shaken": "shaken", "dropped": "fall", "tipped": "bump", "quake": "shaken", "stairs": "edge"}
BODY_RECENT = {"bump": "bump", "edge": "edge"}
BUMP_SIDES = {"L": "left", "R": "right", "B": "front"}
FAULTS = {"front": "its front distance sensor", "drop": "its drop sensor", "bump": "its bumper", "battery": "its battery reading"}
VERSION = re.compile(r"^v?[0-9][A-Za-z0-9._+-]{0,23}$")
GROW_EVERY_S = 60.0
SAFE_STRETCH_S = 86400.0
DISCOVERY_EVERY_S = 1800.0
RISKY = frozenset({"bump", "edge", "fall"})
DUE_SOON_S = 1800.0
STUCK_WINDOW_S = 1800.0
TIE_EVERY_S = 900.0
TIE_MARGIN = 0.05
DECISION_S = 60.0
TRY_DRAW_S = 4
TRY_TILT_SPAN = 10.0
OUTCOMES = "outcomes.jsonl"
FAILED = frozenset({"failed", "lost", "blocked", "no_sight"})
PULL_SPAN = 1.5
DOUBT_SPAN = 0.5
DEEP_LINE = "This matters, so take a moment: think it through, with a short plan, before you act."
WHY_LINE = "You stopped to think because: {reasons}."
LOOK_LINE = "You stopped to look at the world, as you do every so often."
CORRECTED = re.compile(r"^\s*(?:what\s*\?|pardon\b|huh\s*\?|sorry\s*\?|no,? i said\b|no,? i meant\b|that'?s not what i (?:said|meant)\b|not that one\b)", re.IGNORECASE)
WONDER_PHRASES = dict(WONDER_WORDS)


class ExitReason(str, Enum):
    DONE = "done"
    STOPPED = "stopped"
    SHUTDOWN = "shutdown"


@dataclass
class LifeSettings:
    heartbeat_s: float = 180.0
    tick_s: float = 1.0
    sensor_every_s: float = 15.0
    save_every_s: float = 30.0
    waking_s: float = 60.0
    settle_s: float = 300.0
    min_turn_gap_s: float = 5.0
    turn_ceiling_s: float = 60.0
    look_floor_s: float = 1800.0
    mind_poll_s: float = 10.0
    mind_wait_s: float = 120.0
    link_wait_s: float = 3.0
    max_beats: int | None = None
    max_seconds: float | None = None


@dataclass
class LifeParts:
    clock: Clock
    store: SelfStore
    books: Books
    body: Body
    sensors: PhoneSensors
    inner: InnerState
    history: History
    turns: TurnRunner
    mind: Mind
    permissions: Permissions
    face: Face
    voice: Voice
    diary: Diary
    blackbox: BlackBox
    dock_seeker: DockSeeker = field(default_factory=NoDockSeeker)
    dreamer: Dreamer = field(default_factory=NoDreamer)
    subconscious: Subconscious = field(default_factory=lambda: Subconscious(None))
    rng: random.Random = field(default_factory=random.Random)
    chaos: Chaos = field(default_factory=Chaos.disabled)
    studio: object | None = None
    company: Company | None = None
    eyes: Eyes = field(default_factory=NoEyes)
    understanding: Understanding | None = None
    pace: Pace | None = None
    phrase: object | None = None
    safety: object | None = None
    conversation: object | None = None
    dials: object | None = None
    embedder: object | None = None
    own_words: bool = False
    script_engine: str = "process"


def energy_level(percent: float | None, pack_mv: int | None) -> float | None:
    levels = []
    if percent is not None:
        levels.append(percent / 100.0)
    fraction = pack_fraction(pack_mv)
    if fraction is not None:
        levels.append(fraction)
    return min(levels) if levels else None


def describe_event(event: Event) -> tuple[str, str | None, str | None, bool]:
    name, arg = event.name, event.arg
    if name == "bump":
        return f"you bumped into something ({BUMP_SIDES.get(arg, 'somewhere')})", "bump", "bump", True
    if name == "edge":
        return "your drop sensor found an edge; your body stopped and backed off", "edge", "near_fall", True
    if name == "stall":
        return f"a wheel stalled ({'left' if arg == 'L' else 'right'})", "stall", "got_stuck", True
    if name == "obstacle":
        return (f"something is {arg} mm in front of you" if str(arg).isdigit() else "something is in front of you"), "obstacle", None, False
    if name == "dock":
        return ("you are on your charger", "docked", None, True) if arg == "1" else ("you left your charger", None, None, False)
    if name == "lowbat":
        return (f"your body's battery pack is low ({arg} mV) and the wheels are slowed" if str(arg).isdigit() else "your body's battery pack is low and the wheels are slowed"), "lowbat", None, True
    if name == "deadman":
        return "your wheels stopped because the link went quiet", None, None, False
    if name == "boot":
        return (f"your body restarted (version {arg})" if VERSION.match(str(arg or "")) else "your body restarted"), None, None, False
    if name == "fault":
        what = FAULTS.get(str(arg or "").strip().lower())
        return (f"your body reports a fault with {what}" if what else "your body reports a fault it did not name"), None, None, what is not None
    return "your body sent a message you do not know", None, None, False


class Life:
    def __init__(self, parts: LifeParts, settings: LifeSettings | None = None):
        self.p = parts
        self.s = settings or LifeSettings()
        clock = parts.clock
        self.saved = parts.store.read(STATE_FILE, {}) or {}
        meta = self.saved.get("life") or {}
        self.state = LifeState.WAKING
        self.state_since = clock.monotonic()
        self.battery = LowBatteryRoutine()
        self.events = EventLog()
        self.quiet_hours = QuietHours.from_preferences(parts.books.preferences)
        minutes = float(parts.books.preferences.get("initiative_minutes", 10))
        self.initiative = InitiativeGate(minutes * 60.0, meta.get("last_spoke_at"))
        self.company = parts.company or Company(parts.books, clock)
        overnight = Overnight(parts.books, parts.store, parts.diary, clock, self.company.presence, self._drawing_remover())
        self.overnight = overnight
        self.nightly = Nightly(parts.store, parts.books, parts.history, parts.diary, parts.dreamer, clock, parts.blackbox, overnight)
        self._heard: list[tuple[str, dict | None]] = []
        self._asked: list[tuple[float, str | None, bool]] = []
        self._asked_cut = -math.inf
        self._new_face_noted = False
        self.trigger = asyncio.Event()
        self.exit_reason = ExitReason.DONE
        self.beats = 0
        self.turns_run = 0
        self.skips: dict[str, int] = {}
        self.last_night = meta.get("last_night")
        self.first_dock_at = meta.get("first_dock_at")
        self.celebrated = meta.get("celebrated")
        self.boots = int(self.saved.get("boots") or 0) + 1
        self.started_at = clock.now()
        previous = self.saved if self.saved.get("saved_at") else None
        self.wake: str | None = wake_note(previous, clock.now(), clock.local, parts.store.created)
        self.unclean_restart = previous is not None and not previous.get("clean_shutdown", True)
        self.setup = Setup.load(parts.store)
        if self.setup.on:
            if self.setup.since is None:
                self.setup.since = iso(clock.now())
                self.setup.save(parts.store)
            parts.inner.fear.level = 0.0
            if not parts.store.created and self.wake:
                self.wake = self.wake.replace("You restarted after power loss", "You restarted without a clean shutdown") + " " + SETUP_WAKE
        self.dials = parts.dials or Dials(parts.store, clock, parts.blackbox.record, parts.books.name)
        try:
            ensure_seed(parts.store)
        except (LockedFile, SealedFile, OSError) as error:
            log.warning("Pebble's birth seed could not be kept: %s", error)
        self.dials.on_change = self._dials_changed
        self._dials_changed("start")
        self.recent = Recent()
        self.wonder = Wonder()
        self.plasticity = Plasticity(meta.get("plasticity"), self.stage(clock.local(clock.now())))
        self.growth = Growth(parts.store, parts.books, self.dials, parts.diary.write, clock, self._record)
        self.drives: tuple = ()
        self.events.on_add = lambda item: self._quietly("wonder", self._noticed, item)
        self.nightly.grow = self._grow
        meter = meter_of(parts.mind)
        if meter is not None:
            self.nightly.budget = meter.write_day
        self._grown_at = clock.monotonic()
        self._safe_since = clock.now()
        self._discovered_at = -math.inf
        self._last_look = clock.monotonic()
        self._sensed: tuple[float, float | None] | None = None
        self._due_told: set = set()
        self._fails: list[tuple[float, str]] = []
        self._tie_at = -math.inf
        self._wonder_was = 0.0
        self._reasons: list[str] = []
        self._setup_checked = clock.monotonic()
        self.sensors: SensorSnapshot | None = None
        self._sensors_at = -math.inf
        self._last_save = clock.monotonic()
        self._last_turn = -math.inf
        self._last_overheat = -math.inf
        self._stuck_until = -math.inf
        self._pack_low = False
        self._strong_event = False
        self._novelty = False
        self._mind_ready = False
        self._stop: asyncio.Event | None = None
        self._in_turn = False
        self._last_touch = -math.inf
        self._gaze_held = False
        self._calm_until = -math.inf
        self.considering: asyncio.Task | None = None
        self._alarm_was = False
        pin = (parts.books.preferences.get("chaos") or {}).get("pinned")
        if parts.chaos.pinned is None and isinstance(pin, (int, float)) and not isinstance(pin, bool):
            parts.chaos.pin(pin)
        self.nav = Navigator.for_life(parts.body, parts.eyes, parts.store, parts.pace or Pace(clock.monotonic), now_text=lambda: iso(clock.now()), wall=clock.now)
        self.odometer = self.nav.pose
        tel = parts.body.telemetry
        self.watcher = ThingWatcher(
            parts.books.things,
            parts.eyes,
            self.odometer,
            tilt=lambda: tel.tilt,
            front_mm=lambda: tel.status.front_mm if tel.status else None,
            monotonic=clock.monotonic,
        )
        self._pruned_at = -math.inf
        self.commands = self._commands()
        self.commands.understanding.mode_of = lambda: self.dials.values.get("reading.mode")
        self.commands.understanding.cool = self._reading_cool
        self.commands.understanding.sleep = self.commands.runner.kit.pace.sleep
        self.nav.urgent = lambda: bool(getattr(self.commands.runner.current, "urgent", False))
        self.nav.on_life = self._life_accident
        self.dock_seeker = parts.dock_seeker if not isinstance(parts.dock_seeker, NoDockSeeker) else TagDockSeeker(parts.eyes, self.commands.start_battery_homing)
        acts = WhimActs(parts.body, parts.voice, parts.face, parts.permissions, parts.studio, parts.chaos.stream if parts.chaos.enabled else None)
        self._moved: list[str] = []
        self.alive = Alive(self)
        self.hands = HandWatch(self)
        self.household = Household(self)
        self.commands.pictures = PictureQuestions(parts.eyes, parts.mind, float(parts.books.preferences.get("picture_timeout_s", PICTURE_TIMEOUT_S)))
        self.house = House(self)
        self.privacy = Privacy(self)
        self.later = Later(self)
        self.commands.later = self.later
        self.overnight.forgetters.append(self.later.forget)
        self.rules = HouseRules(self)
        self.commands.rules = self.rules
        self.privacy.rules = self.rules
        self.commands.runner.kit.kept_out = self.rules.kept_out
        self.commands.runner.kit.rules = self.rules
        self.overnight.forgetters.append(self.rules.forget)
        kit = self.commands.runner.kit
        kit.alarm = self.alarm
        kit.crying = self._crying
        kit.sharpen = self._sharpen
        kit.where_was = self._where_was
        kit.seen = self._seen_lately
        self.overnight.forgetters.append(self._forget_refs)
        if getattr(parts.turns, "matched", None) is not None:
            parts.turns.matched = self.matched
        self.overnight.forgetters.append(self.alive.forget)
        if getattr(parts.conversation, "forget", None) is not None:
            self.overnight.forgetters.append(parts.conversation.forget)
        if isinstance(parts.dreamer, NoDreamer):
            self.nightly.dreamer = self.alive.dreamer
        decks = TodayDecks(IdeaDecks.open(parts.store), lambda: self.alive.cards("drawing"))
        self.creative = Creative(parts.chaos, parts.face, decks, parts.blackbox, clock.now(), acts, parts.studio)
        self._apply_setup()
        self._wire_keeper()
        self._wire_trying()
        self._wire_scripts()
        self._wire_teaching()
        self.dials.record = self._record
        self.memory = Memory(self)
        self._wire_folding()
        self._wire_selection()
        registry = getattr(parts.turns, "registry", None)
        if registry is not None and registry.action(SELF_TOOLS[0]) is None:
            register_self_tools(registry, self.memory)

    def _wire_folding(self) -> None:
        p = self.p
        self.taskcard = TaskCard(p.store, p.clock, p.blackbox.record)
        self.overnight.forgetters.append(self.taskcard.forget)
        self.folding = Folding(self)
        p.history.mover = self.folding.moved
        p.history.talker = self.folding.talker
        if getattr(p.turns, "card", None) is not None:
            p.turns.card = self.task_card
            p.turns.after_reply = self.folding.replied
            p.turns.folding = self.folding.fold
        self.commands.card = self.reader_card
        self.commands.on_refused = self._refused

    def _wire_selection(self) -> None:
        p = self.p
        self.selection = Selection(self)
        if getattr(p.turns, "named", None) is not None:
            p.turns.named = self.named
        self.commands.shown_places = self.selection.places_for
        self.company.focus = self.selection.focus
        self.overnight.forgetters.append(self.selection.forget)

    def named(self, words: str, kind: str = REPLY) -> list:
        return self._quietly("named items", self.selection.named, words, kind) or []

    def task_card(self, kind: str = "reply") -> str:
        audience = self.memory.audience()
        return self.taskcard.text(live_of(self, audience), audience, self.p.clock.now())

    def reader_card(self) -> str:
        audience = self.memory.audience()
        return self.taskcard.short(live_of(self, audience), audience, self.p.clock.now())

    def _refused(self, asker, line: str, what: str = "") -> None:
        self.taskcard.refused(asker.id, asker.label, line, self.memory.audience(), what)

    def matched(self, kind: str = REPLY) -> str:
        lines = []
        rules = self._quietly("house rules", self.rules.matched)
        if rules:
            first = rules.split("; ", 1)[0]
            lines.append((rules, first if first.endswith(".") or first == rules else first + "."))
        selection = getattr(self, "selection", None)
        if selection is not None:
            lines.extend(self._quietly("chosen items", selection.chosen_now) or [])
        else:
            skills = self._quietly("kept skills", self.commands.trying.listed, "")
            if skills:
                lines.append((skills, ""))
        return "\n".join(pack(lines, chosen_chars(kind)))

    def _wire_trying(self) -> None:
        p = self.p
        commands = self.commands
        clock = p.clock
        self.skills = Skills(p.store, p.body.profile.name, clock, self._record, p.embedder)
        trying = Trying(commands, self.skills, self._card, Planner(commands.thinker, p.books.name, monotonic=clock.monotonic))
        trying.fence = self._try_fence
        trying.card_for = self._plan_card
        studio = p.studio
        if studio is not None:
            trying.draw = lambda subject: studio.draw(subject, None, "overlay", TRY_DRAW_S)
        would_leak = getattr(p.conversation, "would_leak", None)
        if would_leak is not None:
            trying.leaks = would_leak
        commands.trying = trying
        commands.understanding.skills = trying.matched
        self.overnight.forgetters.append(self.skills.forget)
        unstuck = Unstuck(commands, commands.thinker, p.books.name, monotonic=clock.monotonic)
        unstuck.keep = lambda record: p.store.append(OUTCOMES, record)
        commands.unstuck = unstuck
        if p.own_words:
            persona = getattr(getattr(p.turns, "builder", None), "personality_text", None)
            words = OwnWords(commands.thinker, p.books.name, persona or (lambda: ""), sleep=commands.runner.kit.pace.sleep, record=self._record)
            words.names = self.known_names
            words.places = lambda: tuple(self.alive.places())
            if would_leak is not None:
                words.leaks = would_leak
            commands.own_words = words

    def _wire_scripts(self) -> None:
        self.scripts = Scripts(self, self.p.script_engine)
        self.commands.scripts = self.scripts
        self.overnight.forgetters.append(self.scripts.forget)

    def _wire_teaching(self) -> None:
        from ..teach.session import Teaching

        teaching = Teaching(self)
        self.teaching = teaching
        commands = self.commands
        commands.teaching = teaching
        commands.on_did = teaching.did
        trying = commands.trying
        commands.understanding.skills = lambda text: teaching.matched(text) or trying.matched(text)
        trying.on_show = teaching.offered
        self.overnight.forgetters.append(teaching.forget)
        listeners = getattr(getattr(self.nav, "pose", None), "listeners", None)
        if listeners is not None:
            listeners.append(teaching.lifted)
        registry = getattr(self.p.turns, "registry", None)
        if registry is not None and registry.action("how_to") is None:
            teaching.register(registry)

    def pad(self, command: dict) -> None:
        teaching = getattr(self, "teaching", None)
        if teaching is not None:
            self._quietly("the touch pad", teaching.pad, command)

    def _teaching(self) -> bool:
        teaching = getattr(self, "teaching", None)
        return teaching is not None and (teaching.session is not None or teaching.making is not None)

    def _card(self) -> Card:
        p = self.p
        profile = p.body.profile
        return Card(CardBody(
            wheels=True,
            eyes=bool(getattr(p.eyes, "available", False)),
            head=profile.tilt_max - profile.tilt_min >= TRY_TILT_SPAN,
            screen=True,
            draws=p.studio is not None,
            places=tuple(self.alive.places()),
            people=self.known_names(),
        ))

    def _plan_card(self, words: str = "") -> Card:
        selection = getattr(self, "selection", None)
        if selection is None:
            return self._card()
        p = self.p
        profile = p.body.profile
        return Card(CardBody(
            wheels=True,
            eyes=bool(getattr(p.eyes, "available", False)),
            head=profile.tilt_max - profile.tilt_min >= TRY_TILT_SPAN,
            screen=True,
            draws=p.studio is not None,
            places=selection.places_for(words, record=False),
            people=selection.people_for(words),
        ))

    def _trying(self) -> bool:
        trying = getattr(self.commands, "trying", None)
        return trying is not None and trying.loop is not None

    def _try_fence(self) -> str:
        if self.battery.low:
            return "battery"
        if self._hot() or self._rung() == "hot":
            return "heat"
        return ""

    def _crying(self, seconds: float) -> float:
        safety = self.p.safety
        return safety.crying(seconds) if safety is not None and hasattr(safety, "crying") else 0.0

    def _sharpen(self, seconds: float) -> None:
        safety = self.p.safety
        if safety is not None and hasattr(safety, "sharpen"):
            safety.sharpen(seconds)

    def _seen_lately(self, person_id: str, within: float) -> bool:
        return self.company.presence.seen(person_id, self.p.clock.now(), within)

    def _where_was(self, person_id: str) -> tuple | None:
        seen = self.commands.refs.where(person_id, self.p.clock.now())
        if seen is not None:
            return seen.x, seen.y, 0.4
        room = self.alive.usual_room(person_id)
        return self.alive.place_at(room) if room else None

    def _forget_refs(self, person_id: str, names: list) -> None:
        self.commands.refs.forget(person_id)
        self.commands.checks.forget(person_id)

    def _sightings(self, now: float) -> None:
        eyes = self.p.eyes
        if not getattr(eyes, "available", False) or self.privacy.active():
            return
        sight = self.privacy.screen(eyes.latest(1.0))
        if sight is None or not sight.people:
            return
        for person in sight.people:
            who = self.hands.who(person.track, sight, now)
            spot = self.alive._place_of(person, sight) if who is not None else None
            if spot is None:
                continue
            self.commands.refs.saw(who.id, who.label, spot[0], spot[1], self.privacy.rooms.room_at(*spot), person.posture if person.posture_score >= 0.5 else "", now)

    def rule_quiet(self) -> bool:
        rules = getattr(self, "rules", None)
        if rules is None:
            return False
        return bool(self._quietly("house rules", rules.quiet_now))

    def _dials_changed(self, name: str) -> None:
        self.p.inner.temperament = self.dials.temperament()
        memory = getattr(self, "memory", None)
        if memory is not None and name == "words.self":
            memory.words.reload()

    def _quietly(self, where: str, step, *args):
        try:
            return step(*args)
        except Exception:
            log.exception("%s failed", where)
            self.p.blackbox.record("error", where=where)
            return None

    def _record(self, kind: str, **data) -> None:
        self.p.blackbox.record(kind, **data)
        self._quietly("wonder", self._weigh, kind, data)
        memory = getattr(self, "memory", None)
        if memory is not None:
            self._quietly("journal", memory.journal.take, kind, data)

    def _weigh(self, kind: str, data: dict) -> None:
        now = self.p.clock.now()
        if kind == "activity_end" and data.get("how") in FAILED:
            what = str(data.get("activity") or "something")
            self._fails = [(at, done) for at, done in self._fails if now - at <= STUCK_WINDOW_S] + [(now, what)]
            again = sum(1 for _, done in self._fails if done == what)
            self.wonder.push("stuck", 0.3 * again, "the same thing keeps going wrong" if again > 1 else "something I tried didn't work out", now)
        elif kind == "request" and data.get("answer") == "no" and data.get("person") is None and data.get("tier") == "self":
            self.wonder.push("invalid", 0.3, "one of my own ideas was refused", now)
        elif kind == "gatekeeper":
            self.wonder.push("invalid", 0.4, "a step I tried was refused", now)

    def _noticed(self, item) -> None:
        importance = (6.0 if item.major else 2.0) + (2.0 if item.kind in ("stakes", "surprise") else 0.0)
        self.wonder.noticed(importance, item.text, item.at)
        if item.kind in ("stakes", "surprise"):
            self.wonder.push(item.kind, 0.6 if item.major else 0.35, item.text, item.at)
        if item.kind in ("surprise", "place"):
            self.plasticity.rise(item.kind)

    def _grow(self) -> list:
        if self.setup.on:
            return []
        moved = self.growth.consider(self.plasticity)
        now = self.p.clock.now()
        for item in moved:
            self.events.add(now, item["you"] if "you" in item else "you changed a little")
        return moved

    def _wire_keeper(self) -> None:
        p = self.p
        keeper = getattr(getattr(p.turns, "registry", None), "keeper", None)
        if keeper is None:
            return
        keeper.record = self._record
        keeper.diary = p.diary.write
        keeper.note = lambda text: self.events.add(p.clock.now(), text, major=True)
        keeper.dials = self.dials
        keeper.names = self.known_names
        would_leak = getattr(p.conversation, "would_leak", None)
        if would_leak is not None:
            keeper.leaks = would_leak

    def known_names(self) -> tuple:
        names = []
        for person in self.company.book.people.values():
            names.extend(n.lower() for n in person.names + person.nicknames)
        return tuple(names)

    def _commands(self) -> Commands:
        p = self.p
        kit = Kit(
            body=p.body,
            permissions=p.permissions,
            guard=self.blocked,
            people_near=self.beings_near,
            face=p.face,
            pace=p.pace or Pace(p.clock.monotonic),
            eyes=p.eyes,
            battery_low=lambda: self.battery.low,
            odometer=self.odometer,
        )
        commands = Commands(
            self.company,
            Runner(kit),
            p.understanding or Understanding(),
            self.situation,
            self._speak,
            self._activity_note,
            p.diary.write,
            self._record,
            places=self._places,
            things=p.books.things,
            personality=lambda: p.store.read("personality.json", {}) or {},
            chaos=lambda: p.chaos.level if p.chaos.enabled else 0.0,
            can_see=lambda: bool(getattr(p.eyes, "available", False)),
            refusals_per_day=lambda: int((p.store.read("core.json", {}) or {}).get("refusals_per_day", 3) or 0),
            name=p.books.name,
        )
        kit.say = lambda text: commands._spawn(self._speak(text, False))
        kit.say_loud = lambda text: commands._spawn(self._shout(text))
        kit.others_near = self.others_near
        kit.nav = self.nav
        registry = getattr(p.turns, "registry", None)
        if registry is not None and registry.action(ACTIVITY_TOOLS[0]) is None:
            register_activity_tools(registry, commands)
        return commands

    def _reading_cool(self) -> bool:
        pace = getattr(self.p.conversation, "pace", None)
        return pace is None or pace().rung == "cool"

    async def warm_request(self, text: str, person_id: str | None) -> bool:
        return await self.commands.warm_request(text, person_id)

    def _places(self) -> list[str]:
        data = self.p.store.read("places.json", {}) or {}
        names = []
        for place in data.get("places") or []:
            name = place.get("name") if isinstance(place, dict) else place
            if isinstance(name, str) and name.strip():
                names.append(name.strip().lower())
        return names

    async def _speak(self, text: str, phrase: bool) -> None:
        p = self.p
        words = text
        privacy = getattr(self, "privacy", None)
        whisper = p.permissions.quiet or (privacy is not None and privacy.whisper()) or self.rule_quiet()
        spoken = False
        if phrase and p.phrase is not None:
            try:
                phrased = await p.phrase(text, "talk", speak=lambda part: p.voice.say(part, whisper=whisper))
                words, spoken = phrased.text, phrased.spoken
            except Exception:
                log.exception("could not find words for a line of %d characters", len(text or ""))
                words = text
        if not spoken:
            await p.voice.say(words, whisper=whisper)
        if words.rstrip().endswith("?"):
            self.alive.asked()

    async def _shout(self, text: str) -> None:
        await self.p.voice.say(text, whisper=False)

    def _activity_note(self, text: str, major: bool) -> None:
        self.events.add(self.p.clock.now(), text, major)
        if major:
            self.trigger.set()

    async def reply(self, observation: str, private: list | None = None, max_tokens: int = 90, speaker: str | None = None):
        p = self.p
        replying = getattr(p.turns, "reply", None)
        if replying is None or not self._mind_ready:
            return
        now = p.clock.now()
        local = p.clock.local(now)
        person = self.company.book.get(speaker) if speaker else None
        extra = {"speaker": speaker, "tier": self.company.tier(person, now) if person is not None else None} if speaker else {}
        busy = getattr(p.eyes, "set_busy", None)
        self._in_turn = True
        if busy is not None:
            busy(True)
        try:
            async for piece in replying(
                observation,
                self.stage(local),
                p.books.values.describe(),
                people=self.company.prompt_text(now, p.clock.local),
                private=list(private or []),
                private_to=self.company.private_to(now),
                max_tokens=max_tokens,
                options=p.chaos.call_options("talk"),
                **extra,
            ):
                yield piece
        finally:
            self._in_turn = False
            if busy is not None:
                busy(False)

    async def warm_reply(self, observation: str, private: list | None = None, purpose: str = "warm") -> bool:
        p = self.p
        warm = getattr(p.turns, "warm", None)
        if warm is None or not self._mind_ready:
            return False
        now = p.clock.now()
        local = p.clock.local(now)
        return await warm(
            observation,
            self.stage(local),
            p.books.values.describe(),
            people=self.company.prompt_text(now, p.clock.local),
            private=list(private or []),
            private_to=self.company.private_to(now),
            purpose=purpose,
        )

    def reply_done(self, said: str) -> None:
        done = getattr(self.p.turns, "reply_done", None)
        if done is not None:
            done(said)

    def watcher_moved(self) -> list[str]:
        moved, self._moved = self._moved, []
        return moved

    def alarm(self) -> bool:
        return self.p.safety is not None and bool(getattr(self.p.safety, "active", False))

    def blocked(self, now: float | None = None) -> str | None:
        held = self.company.blocked(now)
        if held is None and self.p.safety is not None:
            held = self.p.safety.hold_reason()
        return held

    def _apply_setup(self) -> None:
        on = self.setup.on
        p = self.p
        p.books.people.setup = on
        p.diary.setup = on
        self.nightly.setup = on
        self.alive.book.setup = on
        builder = getattr(p.turns, "builder", None)
        if builder is not None:
            builder.setup = on

    def _check_setup(self) -> None:
        was = self.setup.on
        self.setup = Setup.load(self.p.store)
        if was and not self.setup.on:
            self._setup_ended()

    def finish_setup(self, passphrase: str | None = None) -> bool:
        if not self.setup.on:
            return False
        self.setup = finish(self.p.store, self.p.clock, passphrase)
        self._setup_ended()
        return True

    def _setup_ended(self) -> None:
        p = self.p
        self._apply_setup()
        born = parse_birthday(self.setup.born)
        if born is not None:
            p.books.birthday = born
            p.books.calendar.birthday = born
        p.diary.write(WOKE_UP, "milestone")
        p.blackbox.record("setup_done", born=self.setup.born)
        self.events.add(p.clock.now(), "you are not being set up any more: today you woke up for real", major=True)
        self._be_born()
        self.trigger.set()

    def _be_born(self) -> None:
        p = self.p
        now = p.clock.now()
        try:
            record = be_born(p.store, p.books, self.dials, self.alive.book, self.setup.born, now, p.clock.local(now).date().isoformat())
        except (LockedFile, SealedFile, CorruptFile, TamperedFile, OSError, ValueError) as error:
            log.warning("Pebble's birth draw could not be made: %s", error)
            return
        if record is None:
            return
        self.alive.save()
        self.memory.words.reload()
        p.diary.write(record["line"], "milestone")
        p.blackbox.record("born", draw=record["draw"], late=record["late"], kept=record["kept"])
        self.events.add(now, f"you know a little more about what you were born like: {record['line']}", major=True)

    def calming(self) -> bool:
        return self.p.clock.monotonic() < self._calm_until

    def calm_down(self, seconds: float = CALM_S, why: str = "") -> None:
        self._calm_until = max(self._calm_until, self.p.clock.monotonic() + seconds)
        self.p.blackbox.record("calm_down", seconds=seconds, why=why)
        self.events.add(self.p.clock.now(), "you are settling down after a scare" + (f" ({why})" if why else "") + "; stay close and quiet for a bit", kind="stakes")
        self.alive.calm_down()

    def rouse(self, why: str) -> None:
        if self.state is not LifeState.ACTIVE:
            self.enter(LifeState.ACTIVE, why)

    def others_near(self, person_id: str | None) -> bool:
        if self.watcher.animal_near():
            return True
        sight = self.watcher.sight()
        if sight is None:
            return False
        near = [person for person in sight.people if rough_gap_m(person, sight) <= OTHERS_NEAR_M]
        lead_here = person_id is not None and person_id in self.company.presence.here(self.p.clock.now())
        return len(near) - (1 if lead_here and near else 0) > 0

    def beings_near(self) -> bool:
        privacy = getattr(self, "privacy", None)
        return self.company.anyone_here() or self.watcher.animal_near() or (privacy is not None and (privacy.active() or privacy.hushed()))

    def situation(self, target_tier: str | None = None, target_label: str = "", refusals_left: int = 3, thing: str = "") -> Circumstances:
        p = self.p
        now = p.clock.now()
        tel = p.body.telemetry
        guard = self.company.guard
        traits = (p.store.read("personality.json", {}) or {}).get("traits") or {}
        return Circumstances(
            asleep=self.state is LifeState.ASLEEP,
            resting=self.state is LifeState.RESTING,
            waking=self.state is LifeState.WAKING,
            quiet=p.permissions.quiet,
            low_battery=self.battery.low,
            can_move=p.permissions.can_move,
            homing=getattr(p.permissions, "homing", False),
            blocked=self.blocked(now),
            sticky_by=guard.sticky_by if guard.holding() else None,
            fault=Flags.SENSOR_FAULT in tel.flags,
            valence=p.inner.mood.valence,
            fear=p.inner.fear.level,
            curiosity=p.inner.needs.curiosity,
            curious=int(traits.get("curious", 5) or 5),
            rest=p.inner.needs.rest,
            running=self.commands.runner.running(),
            can_see=bool(getattr(p.eyes, "available", False)),
            refusals_left=refusals_left,
            target_tier=target_tier,
            target_label=target_label,
            docked=tel.docked,
            people_here=len(self.company.presence.here(now)) + (1 if self.company.someone_new(now) else 0),
            thing_in_view=bool(thing) and any(thing in seen or seen in thing for seen in self.watcher.in_view()),
            alarm=self.alarm(),
            calm=self.calming(),
            later=getattr(self, "later", None) is not None,
            **self._privacy_extras(),
            **self.dials.gate(),
            **(self.alive.situation_extras(thing) if getattr(self, "alive", None) is not None else {}),
        )

    def _privacy_extras(self) -> dict:
        privacy = getattr(self, "privacy", None)
        if privacy is None:
            return {}
        try:
            return {"privacy": privacy.active(), "private_view": privacy.private_view(), "private_places": privacy.private_places()}
        except Exception:
            log.exception("privacy: could not read the situation")
            return {"privacy": True}

    def _drawing_remover(self):
        studio = self.p.studio
        if studio is not None and getattr(studio, "gallery", None) is not None:
            return studio.gallery.remove
        return lambda name: Gallery.open(self.p.store).remove(name)

    def stage(self, local: datetime) -> str:
        return stage_for(age_days(self.p.books.birthday, local.date()))

    def fear_scale(self) -> float:
        caution = self.p.books.values.scores().get("caution", 5)
        return FEAR_SCALE.get(self.stage(self.p.clock.local()), 1.0) * (0.6 + caution / 12.5)

    def save(self, clean: bool) -> None:
        p = self.p
        state = {
            "format": 1,
            "saved_at": iso(p.clock.now()),
            "clean_shutdown": clean,
            "boots": self.boots,
            "started_at": iso(self.started_at),
            "inner": p.inner.to_dict(),
            "life": {
                "state": self.state.value,
                "last_spoke_at": self.initiative.last_at,
                "last_night": self.last_night,
                "first_dock_at": self.first_dock_at,
                "celebrated": self.celebrated,
                "turns": self.turns_run,
                "plasticity": round(self.plasticity.level, 3),
            },
        }
        p.store.write(STATE_FILE, state)
        p.books.save("values")
        self.company.flush()
        things = p.books.things
        if p.clock.monotonic() - self._pruned_at >= PRUNE_EVERY_S:
            self._pruned_at = p.clock.monotonic()
            things.prune(p.clock.now())
        if things.dirty:
            p.books.save("things")
            things.dirty = False
        if self.alive.book.dirty:
            self.alive.save()
        self.house.save(force=clean)
        later = getattr(self, "later", None)
        if later is not None:
            later.save(force=clean)
        if clean or self.memory.idle():
            self.memory.save()
        self._last_save = p.clock.monotonic()

    def spoke(self) -> None:
        self.initiative.used(self.p.clock.now())

    def task_closed(self, item: Item) -> None:
        p = self.p
        now = p.clock.now()
        if item.status == "done":
            p.inner.on_event("task_done", now)
            p.diary.write(f"I finished: {item.title}.", "task")
            if item.source == "self":
                self._feedback("own_idea_went_well", now, item.title)
        elif item.status == "failed":
            p.inner.on_event("task_failed", now)
            p.diary.write(f"I tried and failed: {item.title}.", "task")

    def _begin(self) -> None:
        p = self.p
        if p.store.created:
            p.diary.write("My first boot. Everything is new.", "milestone")
        elif self.unclean_restart:
            p.diary.write("I restarted while I was being set up. That's normal right now." if self.setup.on else "I restarted after losing power.", "restart")
        if not self.setup.on and self.setup.born and not record_of(p.store).get("born"):
            if self.setup.born == p.clock.local(p.clock.now()).date().isoformat():
                self._setup_ended()
            else:
                self._be_born()
        self.save(clean=False)
        p.blackbox.record("start", boots=self.boots, wake=self.wake, chaos_seed=p.chaos.seed if p.chaos.enabled else None, chaos_pinned=p.chaos.pinned)
        log.info("awake (boot %d, %s)", self.boots, "first boot" if p.store.created else ("after losing power" if self.unclean_restart else "after a clean shutdown"))

    async def run(self, stop: asyncio.Event) -> ExitReason:
        self._stop = stop
        self._begin()
        self.p.body.start()
        background = [
            asyncio.create_task(self._intake(), name="pebble-intake"),
            asyncio.create_task(self._ticker(), name="pebble-ticker"),
            asyncio.create_task(self._watch_mind(), name="pebble-mind"),
            asyncio.create_task(self.nav.run(), name="pebble-nav"),
            asyncio.create_task(self.alive.run(), name="pebble-alive"),
            asyncio.create_task(self.hands.run(), name="pebble-hands"),
        ]
        try:
            await self._await_body()
            await self.read_sensors()
            await self._await_mind()
            await self._heartbeats()
        finally:
            for task in background:
                task.cancel()
            await asyncio.gather(*background, return_exceptions=True)
            await self._end()
        return self.exit_reason

    async def _await_body(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.s.link_wait_s
        if not await self.p.body.link.wait_connected(self.s.link_wait_s):
            log.warning("no link to the body yet; carrying on and retrying in the background")
            return
        while self.p.body.telemetry.status is None and loop.time() < deadline and not self._stop.is_set():
            await asyncio.sleep(0.02)

    async def _await_mind(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.s.mind_wait_s
        while not self._stop.is_set() and loop.time() < deadline:
            if await self._probe_mind():
                return
            await self._sleep(min(2.0, max(0.0, deadline - loop.time())))
        if not self._mind_ready:
            log.warning("the mind is not ready; plain-code life carries on and turns are skipped until it is")

    async def _probe_mind(self) -> bool:
        try:
            ready = await self.p.mind.ready()
        except Exception:
            ready = False
        if ready and not self._mind_ready:
            log.info("mind ready: %s", self.p.mind.name)
            self.trigger.set()
        self._mind_ready = ready
        return ready

    async def _watch_mind(self) -> None:
        while True:
            await asyncio.sleep(self.s.mind_poll_s)
            if not self._mind_ready:
                await self._probe_mind()

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), max(0.0, seconds))
        except asyncio.TimeoutError:
            pass

    async def _wait_beat(self, timeout: float) -> bool:
        trigger = asyncio.create_task(self.trigger.wait())
        stopper = asyncio.create_task(self._stop.wait())
        done, pending = await asyncio.wait({trigger, stopper}, timeout=max(0.0, timeout), return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        return trigger in done

    async def _heartbeats(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = None if self.s.max_seconds is None else loop.time() + self.s.max_seconds
        self.trigger.set()
        while not self._stop.is_set():
            timeout = self.s.heartbeat_s
            if deadline is not None:
                timeout = min(timeout, deadline - loop.time())
                if timeout <= 0:
                    break
            triggered = await self._wait_beat(timeout)
            if self._stop.is_set():
                break
            if triggered:
                await self._hold_off()
                if self._stop.is_set():
                    break
            self.trigger.clear()
            self.beats += 1
            try:
                await self.beat()
            except Exception:
                log.exception("heartbeat failed")
                self.p.blackbox.record("error", where="beat")
            if self.s.max_beats is not None and self.beats >= self.s.max_beats:
                break

    def _gap(self) -> float:
        wait = self.s.min_turn_gap_s if self.events.has_major() else max(self.s.min_turn_gap_s, self.s.turn_ceiling_s)
        return wait - (self.p.clock.monotonic() - self._last_turn)

    async def _hold_off(self) -> None:
        loop = asyncio.get_running_loop()
        end = loop.time() + self._gap()
        while not self._stop.is_set():
            if self.events.has_major():
                end = min(end, loop.time() + self._gap())
            left = end - loop.time()
            if left <= 0:
                return
            self.trigger.clear()
            if not await self._wait_beat(left):
                return

    def _skip(self, reason: str) -> None:
        self.skips[reason] = self.skips.get(reason, 0) + 1
        self.p.blackbox.record("skip", reason=reason, beat=self.beats)
        log.info("beat %d skipped: %s", self.beats, reason)

    def snapshot(self, now: float, local: datetime) -> Snapshot:
        p = self.p
        tel = p.body.telemetry
        sensors = self.sensors
        battery = sensors.battery if sensors else None
        trend = None if battery is None or battery.charging is None else ("charging" if battery.charging else "draining")
        current = p.books.goals.current()
        today = local.date()
        return Snapshot(
            battery_pct=battery.percent if battery else None,
            battery_trend=trend,
            pack_mv=tel.pack_mv,
            docked=tel.docked if tel.status else None,
            tilt_deg=tel.tilt,
            light_lux=sensors.light_lux if sensors else None,
            temperature_c=sensors.temperature_c if sensors else None,
            last_motion_s=None if tel.last_motion_at is None else now - tel.last_motion_at,
            needs=p.inner.needs.as_percent(),
            mood=p.inner.mood.label(),
            fear=p.inner.fear.level,
            fear_label=p.inner.fear.label(),
            task=current.title if current else None,
            age_days=age_days(p.books.birthday, today),
            stage=self.stage(local),
            today=tuple(o.title for o in p.books.calendar.on(today)),
            soon=tuple((o.title, days) for o, days in p.books.calendar.upcoming(today, 7))[:3],
            state=self.state.value,
            link_up=tel.link_up,
        )

    def _hot(self) -> bool:
        return self.sensors is not None and self.sensors.temperature_c is not None and self.sensors.temperature_c >= HOT_C

    def choose(self, quiet: bool) -> Choice | None:
        p = self.p
        tel = p.body.telemetry
        safety = SafetyContext(
            low_battery=self.battery.low,
            docked=tel.docked,
            edge_hold=Flags.EDGE_HOLD in tel.flags,
            stuck=p.clock.monotonic() < self._stuck_until,
            hot=self._hot(),
            quiet=quiet,
            fear=p.inner.fear.level,
        )
        options = safety_options(safety) + task_options(p.books.goals.active()) + idle_options()
        context = PickContext(p.inner.needs, p.inner.mood, p.inner.fear.level, p.books.values.scores(), p.books.goals.failure_streak, self.dials.idea_weights())
        now = p.clock.now()
        choice = pick(options, context, self.creative.rng(p.rng), variety=self.creative.variety(options, now))
        self.creative.chose(choice, now)
        if choice is not None and choice.chosen.task_id is not None and choice.chosen.task_id != p.books.goals.current_id:
            p.books.goals.set_current(choice.chosen.task_id)
            p.books.save("goals")
        return choice

    def tool_names(self, initiative: bool, quiet: bool = False) -> list[str]:
        names = list(BASE_TOOLS)
        if self.p.turns.registry.action(SELF_TOOLS[0]) is not None:
            names.extend(SELF_TOOLS)
        if not quiet:
            names.extend(DAY_TOOLS)
        if self.company.anyone_here():
            live = self._live_sure()
            names.extend(name for name in PEOPLE_TOOLS if live or name not in LIVE_ONLY)
        busy = self.commands.runner.busy
        if self.p.permissions.can_move and not busy:
            names.append("move")
        if self.p.turns.registry.action(ACTIVITY_TOOLS[0]) is not None:
            names.extend(ACTIVITY_TOOLS if busy else ACTIVITY_TOOLS[:1])
            names.extend(THING_TOOLS)
        if self.p.turns.registry.action("how_to") is not None:
            names.append("how_to")
        if initiative:
            names.append("say")
        return names

    def _asking(self, now: float) -> dict:
        self._asked = [entry for entry in self._asked if now - entry[0] <= REQUEST_S]
        asking: dict = {}
        for at, person_id, sure in self._asked:
            if at > self._asked_cut:
                asking[person_id] = sure
        return asking

    def _live_sure(self) -> bool:
        asking = self.company.asking or {}
        return len(asking) == 1 and None not in asking and all(asking.values())

    async def beat(self) -> None:
        p = self.p
        now = p.clock.now()
        local = p.clock.local(now)
        if self.state is LifeState.ASLEEP:
            return self._skip("asleep")
        if not self._mind_ready:
            return self._skip("the mind is not ready")
        hold = getattr(p.conversation, "hold_turns", None)
        held = hold(self._last_turn, self.events.has_major()) if hold is not None else None
        if held:
            return self._skip(held)
        mono = p.clock.monotonic()
        if mono - self._last_turn < self.s.turn_ceiling_s and not self.events.has_major():
            return self._skip("you thought a moment ago")
        quiet = self.quiet_hours.contains(local)
        try:
            why = await self._why_think(now, mono, quiet)
        except Exception:
            log.exception("could not weigh what to think about")
            p.blackbox.record("error", where="wonder")
            why = (LOOK_LINE, False, None)
        if why is None:
            return
        reason, deep, strongest = why
        snapshot = self.snapshot(now, local)
        choice = self.choose(quiet)
        conversation = p.conversation
        talk_lines, talk_private = conversation.mind_lines(now) if conversation is not None else ([], [])
        holding = conversation is not None and conversation.hold_tongue(now)
        initiative = self.initiative.allowed(now, quiet or self.alive.hushed() or holding or self.rule_quiet())
        p.permissions.initiative = initiative
        events = self.events.drain()
        heard, self._heard = self._heard, []
        lines = [line for line, _ in heard]
        observation = self._with_extras(observation_text(local, format_status(snapshot), events, choice, self.wake, initiative, quiet, lines), initiative, quiet)
        doing = self.commands.describe()
        if doing:
            observation += BUSY_LINE.format(doing=doing)
        view = self.watcher.in_view()
        if view:
            observation += "\nYou can see: " + ", ".join(view[:VIEW_SHOWN]) + "."
        if talk_lines:
            observation += "\n" + "\n".join(talk_lines)
        private = [item for _, item in heard if item] + list(talk_private)
        try:
            remembered = await self.memory.for_turn(" ".join([reason] + [item.text for item in events] + lines))
        except Exception:
            log.exception("could not bring memories to mind")
            remembered = ""
        if remembered:
            observation += "\n" + remembered
            private.append({"to": ROOM, "text": remembered})
        looking_away = self.privacy.observation()
        if looking_away:
            observation += "\n" + looking_away
        if deep:
            observation += "\n" + DEEP_LINE
        observation += "\n" + reason
        people = self.company.prompt_text(now, p.clock.local)
        self._in_turn = True
        self.company.asking = self._asking(now)
        busy = getattr(p.eyes, "set_busy", None)
        if busy is not None:
            busy(True)
        try:
            result = await p.turns.run(
                observation,
                self.tool_names(initiative, quiet),
                self.stage(local),
                p.books.values.describe(),
                people=people,
                private=private,
                private_to=self.company.private_to(now),
                deep=deep,
            )
        finally:
            self._in_turn = False
            self.company.asking = None
            if busy is not None:
                busy(False)
        self._last_turn = p.clock.monotonic()
        if getattr(result, "interrupted", False):
            self.events.put_back(events)
            self._heard = heard + self._heard
            log.info("turn put off: someone is talking to Pebble")
        elif result.error:
            self._mind_ready = False
            self.events.put_back(events)
            self._heard = heard + self._heard
            log.warning("turn failed: %s", result.error)
        else:
            self._asked_cut = now
            self.wake = None
            self.turns_run += 1
            if deep:
                self._quietly("wondering", self.memory.deep_turn, list(self._reasons), strongest)
            self._quietly("pace", self._looked, p.clock.now(), strongest, result)
            log.info("beat %d thought %d characters | tools: %s", self.beats, len(result.thought or ""), ", ".join(c["name"] for c in result.calls) or "-")
        p.blackbox.record(
            "turn",
            beat=self.beats,
            state=self.state.value,
            choice=choice.as_dict() if choice else None,
            tools=[{"name": c["name"], "args": c["args"], "ok": c["result"].get("ok")} for c in result.calls],
            thought=result.thought,
            error=result.error,
            compacted=result.compacted,
            why=reason,
            deep=deep,
        )

    async def _why_think(self, now: float, mono: float, quiet: bool) -> tuple[str, bool, str | None] | None:
        pulls = self.dials.pulls()
        self._habit_doubt(now, quiet)
        if self.wake is not None:
            return WHY_LINE.format(reasons="you have just woken up"), False, None
        line = threshold(self.dials.thoughtfulness())
        score = self.wonder.score(now, pulls)
        strongest = self.wonder.strongest(now, pulls)
        reasons = self.wonder.reasons(now, pulls)
        if score < line:
            if mono - self._last_look >= self.s.look_floor_s:
                return LOOK_LINE, False, None
            quiet_now = self.wonder.quiet() and not self.events.peek() and not self._heard
            self._skip("nothing changed" if quiet_now else "not enough to think about yet")
            return None
        deep = self.wonder.deep(now, pulls) and not quiet and self._rung() == "cool"
        reason = WHY_LINE.format(reasons="; ".join(reasons)) if reasons else LOOK_LINE
        self._reasons = list(reasons)
        return reason, deep, strongest

    def _rung(self) -> str:
        pace = getattr(self.p.conversation, "pace", None)
        try:
            return str(pace().rung) if pace is not None else "cool"
        except Exception:
            return "cool"

    def _habit_doubt(self, now: float, quiet: bool) -> None:
        if quiet or now - self._tie_at < TIE_EVERY_S:
            return
        p = self.p
        context = PickContext(p.inner.needs, p.inner.mood, p.inner.fear.level, p.books.values.scores(), p.books.goals.failure_streak, self.dials.idea_weights())
        scores = sorted((score(option, context)[0] for option in idle_options()), reverse=True)
        if len(scores) >= 2 and scores[0] > 0 and (scores[0] - scores[1]) / scores[0] < TIE_MARGIN:
            self._tie_at = now
            self.wonder.push("doubt", 0.3, "two of my own ideas pulled different ways", now)

    def _looked(self, now: float, strongest: str | None, result) -> None:
        self.wonder.looked()
        self._last_look = self.p.clock.monotonic()
        if strongest is None:
            return
        useful = any(call["result"].get("ok") for call in result.calls)
        step = self.plasticity.step(PULL_SPAN)
        name = f"wonder.{strongest}"
        before = float(self.dials.value(name))
        after = round(before + (step if useful else -step), 2)
        words = WONDER_PHRASES.get(strongest, strongest)
        self.dials.propose(name, after, PEBBLE, f"stopping to think about {words} {'led somewhere' if useful else 'led to nothing'}")

    def _calibrate(self, corrected: bool) -> None:
        step = self.plasticity.step(DOUBT_SPAN)
        before = self.dials.doubt_at()
        after = round(before - step if corrected else before + step / 2.0, 2)
        why = "someone corrected me just after a quick choice" if corrected else "a choice I was unsure of went fine"
        self.dials.propose("doubt.at", after, PEBBLE, why)

    def _with_extras(self, observation: str, initiative: bool, quiet: bool) -> str:
        if quiet:
            return observation
        extras = []
        studio = self.p.studio
        if studio is not None:
            line = studio.gallery_line()
            if line:
                extras.append(line)
        if initiative:
            idea = self.creative.idea_line("talk")
            if idea:
                extras.append(idea)
        return "\n".join([observation] + extras)

    async def _ticker(self) -> None:
        last = self.p.clock.monotonic()
        while True:
            await asyncio.sleep(self.s.tick_s)
            now = self.p.clock.monotonic()
            dt, last = now - last, now
            try:
                await self.tick(dt)
            except Exception:
                log.exception("tick failed")
                self.p.blackbox.record("error", where="tick")

    async def read_sensors(self) -> None:
        self.sensors = await asyncio.to_thread(self.p.sensors.read)
        self._sensors_at = self.p.clock.monotonic()
        temperature = self.sensors.temperature_c
        if temperature is not None and temperature >= HOT_C and self._sensors_at - self._last_overheat >= OVERHEAT_GAP_S:
            self._last_overheat = self._sensors_at
            now = self.p.clock.now()
            self.p.inner.on_event("overheat", now, self.fear_scale())
            self.events.add(now, f"the phone is hot ({round(temperature)} C)", major=True)
            self.trigger.set()

    def _celebrate(self, local: datetime) -> None:
        day = local.date().isoformat()
        if self.celebrated == day:
            return
        parties = [o for o in self.p.books.calendar.on(local.date()) if o.mood == "party" and o.enthusiasm >= 0.5]
        if not parties:
            return
        self.celebrated = day
        self.p.inner.on_event("celebration", self.p.clock.now())
        self.events.add(self.p.clock.now(), f"today is {parties[0].title}" + (f": {parties[0].why}" if parties[0].why else ""), major=False)

    async def tick(self, dt: float) -> None:
        p = self.p
        clock = p.clock
        now = clock.now()
        local = clock.local(now)
        mono = clock.monotonic()
        if self.sensors is None or mono - self._sensors_at >= self.s.sensor_every_s:
            await self.read_sensors()
        quiet = self.quiet_hours.contains(local)
        battery = self.sensors.battery if self.sensors else None
        percent = battery.percent if battery else None
        charging = battery.charging if battery else None
        tel = p.body.telemetry
        if self._pack_low and (tel.docked or (tel.pack_mv or 0) >= PACK_RECOVER_MV):
            self._pack_low = False
        verdict = self.battery.assess(percent, charging, self._pack_low)
        p.inner.tick(
            dt,
            InnerContext(
                now=now,
                local_hour=local.hour,
                local_hours=local.hour + local.minute / 60.0,
                energy_level=energy_level(percent, tel.pack_mv),
                battery_percent=percent,
                awake=self.state is not LifeState.ASLEEP,
                company=self.company.anyone_here(now),
                resting=self.state in (LifeState.RESTING, LifeState.DOCKING),
                night=quiet,
                waking=self.state is LifeState.WAKING,
                novelty=self._novelty,
                comfort=tel.docked,
                hot=self._hot(),
            ),
        )
        self._novelty = False
        if not quiet:
            self._celebrate(local)
        self._quietly("inner life", self._inner_life, dt, now, local, mono)
        self._quietly("memory", self.memory.tick, now)
        situation = Situation(
            quiet=quiet,
            rest=p.inner.needs.rest,
            energy=p.inner.needs.energy,
            docked=tel.docked,
            low_battery=verdict.low,
            in_state_s=mono - self.state_since,
            strong_event=self._strong_event,
            alarm=self.alarm(),
            waking_s=self.s.waking_s,
            settle_s=self.s.settle_s,
        )
        self._strong_event = False
        state, why = next_state(self.state, situation)
        if state is not self.state:
            self.enter(state, why)
        for note in self.company.tick(now):
            self.events.add(now, note, major=True, kind="stakes")
            self.trigger.set()
        if mono - self._setup_checked >= SETUP_CHECK_S:
            self._setup_checked = mono
            self._check_setup()
        alarm = self.alarm()
        if alarm and not self._alarm_was:
            self.recent.add("alarm", now)
        if self._alarm_was and not alarm:
            self.calm_down(why="the alarm is over")
        self._alarm_was = alarm
        p.permissions.quiet = quiet
        p.permissions.can_move = (
            self.state is LifeState.ACTIVE
            and (not quiet or alarm)
            and not (verdict.critical if alarm else verdict.low)
            and Flags.SENSOR_FAULT not in tel.flags
            and self.blocked(now) is None
        )
        p.permissions.homing = (
            self.state in (LifeState.ACTIVE, LifeState.DOCKING)
            and (not quiet or self.state is LifeState.DOCKING)
            and Flags.SENSOR_FAULT not in tel.flags
            and self.blocked(now) is None
        )
        if p.safety is not None:
            await p.safety.tick(quiet)
        self.house.tick(now, quiet or self.rule_quiet())
        self.commands.tick()
        self._quietly("later", self.later.tick, quiet)
        self._quietly("scripts", self.scripts.tick)
        self._quietly("teaching", self.teaching.tick)
        self._quietly("house rules", self.rules.tick, now, self.later.happened)
        self._quietly("references", self._sightings, now)
        self._quietly("folding", self.folding.tick)
        self._look_at_things(now)
        if verdict.critical:
            await self._battery_shutdown(percent)
            return
        if verdict.newly_low:
            await self._battery_low(percent)
        self._creative_tick(now, local, mono, quiet, verdict.low)
        if mono - self._last_save >= self.s.save_every_s:
            self.save(clean=False)
        if self.state is LifeState.ASLEEP and quiet:
            await self._maybe_nightly(local)

    def _inner_life(self, dt: float, now: float, local: datetime, mono: float) -> None:
        p = self.p
        temperature = self.sensors.temperature_c if self.sensors else None
        self.drives = read_drives(p.inner.needs, p.inner.fear.level, temperature, self._rung(), self.recent, now)
        self.wonder.feel(self.drives)
        self.plasticity.tick(dt, self.stage(local), unmet(self.drives))
        if not self.setup.on and mono - self._grown_at >= GROW_EVERY_S:
            self._grown_at = mono
            self._grow()
        self._due_soon(now)
        self._safe_stretch(now)
        if self._sensed is not None and mono - self._sensed[0] > DECISION_S:
            doubt = self._sensed[1]
            self._sensed = None
            if doubt is not None and doubt >= self.dials.doubt_at():
                self._calibrate(corrected=False)
        score = self.wonder.score(now, self.dials.pulls())
        if score >= threshold(self.dials.thoughtfulness()) > self._wonder_was:
            self.trigger.set()
        self._wonder_was = score

    def _feedback(self, kind: str, now: float, note: str = "") -> None:
        if self.setup.on:
            return
        self.p.books.values.log_feedback(kind, iso(now), note)
        self.plasticity.rise("feedback")

    def _safe_stretch(self, now: float) -> None:
        risky = [at for kind, at in self.recent.seen if kind in RISKY]
        self._safe_since = max([self._safe_since] + risky)
        if now - self._safe_since >= SAFE_STRETCH_S:
            self._safe_since = now
            self._feedback("safe_stretch", now, "a day without a bump, an edge or a fall")

    def _due_soon(self, now: float) -> None:
        for item in self.p.books.goals.active():
            if item.id in self._due_told or not item.expires_at or item.expires_at - now > DUE_SOON_S:
                continue
            self._due_told.add(item.id)
            self.wonder.push("stakes", 0.5, f"{item.title} is due soon", now)

    def _look_at_things(self, now: float) -> None:
        for seen in self.watcher.look():
            self._novelty = True
            self.p.blackbox.record("thing_seen", label=seen.label, sighting=seen.kind, animal=seen.animal, where=seen.where)
            self.events.add(now, seen.text(), kind="surprise" if seen.kind in ("new", "moved") else "")
            if seen.kind == "new" and now - self._discovered_at >= DISCOVERY_EVERY_S:
                self._discovered_at = now
                self._feedback("fun_discovery", now, seen.label)
            if seen.kind == "moved":
                self._moved.append(seen.label)
                del self._moved[:-20]
            if seen.animal or (canonical(seen.label) not in LANDMARKS and self.alive.book.fear(seen.label, now) < FEARED):
                self.commands.curious(seen.label, seen.animal, seen.kind == "new")

    def _creative_tick(self, now: float, local: datetime, mono: float, quiet: bool, low_battery: bool) -> None:
        p = self.p
        mood, fear = p.inner.mood, p.inner.fear.level
        asleep = self.state is LifeState.ASLEEP
        p.face.feel(mood.valence, mood.arousal, fear, asleep)
        if self._gaze_held and mono - self._last_touch >= GAZE_HOLD_S:
            self._gaze_held = False
            p.face.gaze(0.0, 0.0)
        playfulness = p.books.values.scores().get("playfulness", 5)
        self.creative.update(DialInputs(playfulness, mood.valence, mood.arousal, self.stage(local), quiet, fear, mood_weight=self.dials.chaos_mood()), mono)
        self.creative.maybe_whim(
            WhimContext(
                now=now,
                quiet=quiet or self.rule_quiet(),
                active=self.state is LifeState.ACTIVE,
                low_battery=low_battery,
                fear=fear,
                valence=mood.valence,
                busy=self._in_turn or self.commands.runner.busy or self._trying() or self._teaching() or self.alarm() or self.calming(),
            )
        )

    def life_ahead(self) -> str | None:
        _, stop = self.nav.life_guard()
        if stop:
            return stop
        sight = self.p.eyes.latest(1.0)
        tilt = self.p.body.telemetry.tilt
        for thing, gap in small_life_ahead(sight, tilt) + animals_ahead(sight, tilt):
            if gap < LIFE_AHEAD_M:
                return thing.label
        return None

    def _life_accident(self, event: dict) -> None:
        p = self.p
        now = p.clock.now()
        label = event.get("label") or "little thing"
        p.blackbox.record("life_accident", how=event.get("how"), label=label, life=event.get("kind"), x=event.get("x"), y=event.get("y"))
        if event.get("how") == "bumped":
            line = f"I bumped the {label} by accident. I'll go more slowly there from now on."
        else:
            line = f"I may have gone over a little {label} by accident. I'm sorry. I'll go more slowly there from now on."
        p.diary.write(line, "life")
        self.events.add(now, event.get("note") or line, major=True)
        self.trigger.set()

    def someone_upset(self, seconds: float = UPSET_S) -> None:
        self.creative.someone_upset(self.p.clock.now() + seconds)
        self.p.blackbox.record("someone_upset", seconds=seconds)

    def hint(self, kind: str) -> None:
        trying = getattr(self.commands, "trying", None)
        if trying is not None:
            self._quietly("a hint for a try", trying.hint, kind)

    def touched(self, touch: Touch) -> None:
        p = self.p
        mono = p.clock.monotonic()
        if mono - self._last_touch < TOUCH_GAP_S:
            return
        self._last_touch = mono
        now = p.clock.now()
        p.inner.on_event("touch", now)
        who = self.company.touched(touch.kind, now)
        p.blackbox.record("touch", touch=touch.kind, x=round(touch.x, 3), y=round(touch.y, 3), person=who)
        where = "left" if touch.x < 0.4 else ("right" if touch.x > 0.6 else "middle")
        self.recent.add("handled", now)
        self.events.add(now, f"someone {TOUCH_WORDS.get(touch.kind, 'touched')} your face screen ({where})", kind="stakes")
        p.face.gaze(touch.x * 2 - 1, touch.y * 2 - 1)
        self._gaze_held = True
        self._novelty = True
        if self.state is not LifeState.ASLEEP:
            p.face.show("love" if touch.kind != "tap" else "happy")
        self.trigger.set()

    def hear(self, text: str, voice=None, loud: bool = False, addressed: bool | None = None, speaker: str | None = None, proof=None) -> Heard:
        p = self.p
        now = p.clock.now()
        heard = self.company.hear(text, voice, now, loud, meet=addressed is not False, speaker=speaker, proof=proof, addressed=addressed)
        if addressed is not False and (text or "").strip():
            self._asked.append((now, heard.person_id, heard.sure))
            self._asked = [entry for entry in self._asked if now - entry[0] <= REQUEST_S]
        if p.safety is not None:
            try:
                p.safety.heard(heard, loud)
            except Exception:
                log.exception("safety could not take what was heard")
        p.blackbox.record("heard", person=heard.person_id, new=heard.new_person, stop=heard.stop.kind if heard.stop else None, released=heard.released, private=heard.private)
        p.inner.on_event("loud" if loud else "talk", now)
        self.later.talked(now)
        if heard.stop is not None:
            self._stopped(heard, now)
        person = self.company.book.get(heard.person_id) if heard.person_id else None
        self._quietly("memory", self.memory.heard, heard.person_id, heard.label, self.company.tier(person, now) if person is not None else "stranger", "" if heard.private else text)
        if addressed is not False:
            self._quietly("folding", self.folding.heard)
        if loud:
            self.recent.add("loud", now)
        if self._sensed is not None and CORRECTED.match(text or "") and p.clock.monotonic() - self._sensed[0] <= DECISION_S:
            self._sensed = None
            self._quietly("doubt", self._calibrate, True)
        if heard.released:
            self.events.add(now, f"{heard.label} said you may move again")
        self._novelty = True
        if addressed is None:
            line = heard.line()
            self._heard.append((line, {"to": heard.person_id, "text": line} if heard.private else None))
            del self._heard[:-HEARD_KEEP]
            self._quietly("wonder", self.wonder.push, "stakes", 0.8, "someone said something", now)
            self.trigger.set()
        self.alive.heard(text)
        private = self._quietly("privacy", self.privacy.heard, heard, addressed)
        if private is not None:
            self.considering = private
            return heard
        house = self.house.heard(heard, addressed)
        self.considering = house if house is not None else (self.commands.heard(heard) if addressed is not False else None)
        return heard

    def _stopped(self, heard: Heard, now: float) -> None:
        p = self.p
        p.permissions.can_move = False
        if p.body.connected:
            asyncio.ensure_future(p.body.stop())
        self.events.add(now, heard.stop.text, major=True, kind="stakes")
        self.commands.stopped(heard)

    def see(self, face) -> str | None:
        now = self.p.clock.now()
        before = set(self.company.presence.here(now))
        who = self.company.see(face, now)
        if who is not None and who not in before:
            person = self.company.book.get(who)
            self.events.add(now, f"{person.label} is here", kind="stakes")
            self.trigger.set()
        if who is None and self.company.someone_new(now) and not self._new_face_noted:
            self._new_face_noted = True
            seen = "someone you have seen before but never met is in view" if self.company.seen_before(now) else "someone you have not met is in view"
            self.events.add(now, seen, kind="surprise")
            self.trigger.set()
        if not self.company.someone_new(now):
            self._new_face_noted = False
        return who

    def felt(self, kind: str, text: str | None = None) -> str | None:
        now = self.p.clock.now()
        if kind in FELT_EVENTS:
            self.p.inner.on_event(FELT_EVENTS[kind], now, self.fear_scale())
        who = self.company.felt(kind, now)
        nav = getattr(self, "nav", None)
        if nav is not None and getattr(nav, "felt", None) is not None:
            nav.felt(kind)
        if kind in FELT_RECENT:
            self.recent.add(FELT_RECENT[kind], now)
        self.events.add(now, text or f"you were {kind}", major=True, kind="surprise")
        self.trigger.set()
        return who

    def _update_face(self) -> None:
        mood = self.p.inner.mood
        self.p.face.show(face_for(mood.valence, mood.arousal, self.p.inner.fear.level, self.state is LifeState.ASLEEP))

    def enter(self, state: LifeState, why: str) -> None:
        p = self.p
        old, self.state = self.state, state
        self.state_since = p.clock.monotonic()
        log.info("state %s -> %s (%s)", old.value, state.value, why)
        p.blackbox.record("state", old=old.value, new=state.value, why=why)
        self.events.add(p.clock.now(), f"you went from {old.value} to {state.value} because {why}")
        if state in (LifeState.RESTING, LifeState.ASLEEP, LifeState.DOCKING) and p.body.connected:
            asyncio.ensure_future(p.body.stop())
        self._update_face()
        self.trigger.set()

    async def _battery_low(self, percent: float | None) -> None:
        p = self.p
        now = p.clock.now()
        p.blackbox.record("battery_low", phone_pct=percent, pack_mv=p.body.telemetry.pack_mv, pack_low=self._pack_low)
        self.save(clean=False)
        p.books.save_all()
        p.face.show("sleepy")
        if p.body.connected:
            await p.body.stop()
        attempt = await self.dock_seeker.seek()
        if attempt.started:
            line = "My battery is getting low. Heading to my charger."
        else:
            line = "My battery is getting low and I can't find my charger by myself yet. Could someone put me on it?"
        await p.voice.say(line, whisper=p.permissions.quiet)
        detail = "" if attempt.started else f" ({attempt.reason})"
        self.events.add(now, f"battery low: your body saved everything and is heading for the charger{detail}", major=True, kind="stakes")
        self.trigger.set()

    async def _battery_shutdown(self, percent: float | None) -> None:
        if self.exit_reason is ExitReason.SHUTDOWN:
            return
        p = self.p
        p.blackbox.record("battery_shutdown", phone_pct=percent)
        p.face.show("sleepy")
        if p.body.connected:
            await p.body.stop()
        await p.voice.say("I'm nearly out of battery. Going to sleep now. Goodbye for now.", whisper=p.permissions.quiet)
        p.diary.write("My battery ran very low, so I said goodbye and went to sleep.", "shutdown")
        self.exit_reason = ExitReason.SHUTDOWN
        if self._stop is not None:
            self._stop.set()

    async def _maybe_nightly(self, local: datetime) -> None:
        key = self.quiet_hours.night_key(local)
        if key == self.last_night:
            return
        self.last_night = key
        await self.nightly.run(key, self.stage(local), self.p.mind if self._mind_ready else None)
        try:
            await self.scripts.night(local)
        except Exception:
            log.exception("the programs' night failed")
        try:
            await self.teaching.night(local)
        except Exception:
            log.exception("the how-to book's night failed")
        dream = self.creative.dream(key, quiet=True, docked=self.p.body.telemetry.docked)
        if dream:
            self.recent.add("dream", self.p.clock.now())
            self.p.diary.write(f"I dreamt a picture out of {dream['from'][0]} and {dream['from'][1]}.", "dream")
        self.save(clean=False)

    async def _intake(self) -> None:
        queue = self.p.body.subscribe_events()
        while True:
            message = await queue.get()
            try:
                self.notice(message)
            except Exception:
                log.exception("could not take in %r", message)

    def notice(self, message) -> None:
        p = self.p
        now = p.clock.now()
        if isinstance(message, LinkUp):
            self.events.add(now, "the link to your body is up")
            p.blackbox.record("link", up=True, label=message.label)
            return
        if isinstance(message, LinkDown):
            self.events.add(now, f"lost contact with your body ({message.reason})", major=True)
            p.blackbox.record("link", up=False, reason=message.reason)
            self.trigger.set()
            return
        if not isinstance(message, Event):
            return
        p.blackbox.record("body_event", event=message.text())
        text, inner_event, feedback, major = describe_event(message)
        if message.name == "lowbat":
            self._pack_low = True
        if message.name == "stall":
            self._stuck_until = p.clock.monotonic() + STUCK_MEMORY_S
        if message.name == "dock" and message.arg == "1" and not self.first_dock_at:
            self.first_dock_at = iso(now)
            p.diary.write("The first time I settled onto my charger.", "milestone")
        if inner_event:
            outcome = p.inner.on_event(inner_event, now, self.fear_scale())
            if outcome.became_used_to:
                p.diary.write(f"I'm not so startled by {outcome.became_used_to} any more.", "milestone")
        if feedback:
            self._feedback(feedback, now, message.text())
        if message.name in BODY_RECENT:
            self.recent.add(BODY_RECENT[message.name], now)
        self._novelty = True
        if major:
            self._strong_event = True
        self.events.add(now, text, major, kind="surprise" if message.name in BODY_RECENT or message.name == "stall" else "")
        self._update_face()
        if major and p.subconscious.available:
            asyncio.ensure_future(self._subconscious_face(text))
        if major or message.name in TRIGGER_EVENTS:
            self.trigger.set()

    async def _subconscious_face(self, what: str) -> None:
        expression = await self.p.subconscious.pick_expression(self.p.inner.mood.label(), what)
        if expression:
            self.p.face.show(expression)

    async def _end(self) -> None:
        p = self.p
        await self.creative.close()
        await self.folding.close()
        try:
            await self.scripts.close()
        except Exception:
            log.exception("programs did not close cleanly")
        try:
            await self.commands.close()
        except Exception:
            log.exception("activities did not close cleanly")
        try:
            await p.body.close()
        except Exception:
            log.exception("body close failed")
        self.save(clean=True)
        p.books.save_all()
        self.nav.save()
        p.blackbox.record("end", reason=self.exit_reason.value, beats=self.beats, turns=self.turns_run, skips=self.skips)
        log.info("stopped (%s) after %d beats, %d turns", self.exit_reason.value, self.beats, self.turns_run)
