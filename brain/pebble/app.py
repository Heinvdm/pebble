import argparse
import asyncio
import logging
import os
import random
import secrets
import signal
from pathlib import Path

from .blackbox import BlackBox
from .body.api import Body
from .body.profile import BodyProfile, resolve_profile
from .body.sensors import PhoneSensors
from .books import Books
from .alive.dream import TodayDecks
from .chaos.engine import Chaos
from .chaos.streams import derive
from .chaos.ideas import IdeaDecks
from .clock import Clock
from .diary import Diary
from .eyes import close_eyes, eyes_from_config
from .inner.state import InnerState
from .life.loop import ExitReason, Life, LifeParts, LifeSettings
from .life.turn import TurnRunner
from .link.client import LinkClient
from .link.transport import transport_factory
from .laws import laws_intact
from .mind.base import Mind
from .mind.history import History
from .mind.budget import guarded
from .mind.lawful import lawful
from .mind.llama import LlamaServerMind
from .mind.profile import ModelProfile
from .mind.prompt import PromptBuilder
from .mind.scripted import APP_ACTS, ScriptedMind
from .mind.subconscious import Subconscious
from .mind.wordsmith import Wordsmith
from .people.company import Company
from .people.fake import FakePresence
from .people.tools import register_people_tools
from .screen.gallery import Gallery
from .screen.generator import SceneGenerator
from .screen.stage import SceneStage
from .screen.studio import Studio
from .screen.tools import register_screen_tools
from .seams.face import LogFace
from .seams.later import power_from
from .seams.sight import NoEyes
from .seams.hearing import hearing_from
from .conversation.build import conversation_from, ears_from
from .safety.build import safety_from
from .seams.voice import LipSyncVoice, voice_from
from .self.birth import ensure_seed, run_seed
from .self.recall.embed import embedder_from
from .tact import TactfulVoice
from .seal.errors import SealError
from .seal.startup import HOLDERS, holder_for, open_self
from .selfstore import LockedFile, SealedFile, SelfIsSealed
from .sim.eyes import SimEyes
from .sim.firmware import SimFirmware
from .sim.server import SimServer
from .sim.scene import household
from .sim.world import Pose, SimPerson, World, room
from .understand.examples import Chooser
from .understand.model import ModelReader
from .understand.understanding import Understanding
from .tools.builtin import Permissions, ToolContext, build_registry
from .web.eyes import BrowserEyes
from .web.hub import Hub
from .web.launch import run_demo, start_face_server, threadsafe
from .web.webface import WebFace

log = logging.getLogger("pebble")

EXIT_OK = 0
EXIT_SHUTDOWN = 3
EXIT_SEALED = 4
SIM_START = Pose(80.5, 0.0, 0.0)
SIM_VISITOR = ("sam", 1400.0, 350.0)
SCREEN_PORT = 8765


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pebble", description="Pebble's brain: inner life, memory and the link to its body")
    parser.add_argument("--self", dest="self_dir", default=os.environ.get("PEBBLE_SELF", "self"), help="the self folder (default ./self or $PEBBLE_SELF)")
    parser.add_argument("--snapshots", default=None, help="where nightly snapshots go (default <self>-snapshots)")
    parser.add_argument("--key-file", default=None, help="Pebble's own key for a sealed self (default $PEBBLE_KEY_FILE or ~/.pebble/self.key)")
    parser.add_argument("--key-holder", choices=HOLDERS, default=None, help="where Pebble's lock lives: file or android (the phone's keystore); default $PEBBLE_KEY_HOLDER, else what seal.json says")
    parser.add_argument("--sim", action="store_true", help="start a simulated body in this process and connect to it")
    parser.add_argument("--sim-port", type=int, default=0, help="port for the in-process sim (0 picks a free one)")
    parser.add_argument("--sim-world", choices=("room", "table"), default="room", help="the sim's world: a 4 x 3 m room with a visitor standing in it (default), or the 1 x 0.8 m table")
    parser.add_argument("--link", default=None, help="tcp:host:port, serial:/dev/ttyACM0[@baud] or ble:Pebble (default from the body profile)")
    parser.add_argument("--body", default=None, help="body profile name or path (default pc_sim with --sim, else droidian)")
    parser.add_argument("--no-camera", action="store_true", help="keep the cameras off: Pebble sees nothing")
    parser.add_argument("--mind", choices=("scripted", "llama"), default="llama")
    parser.add_argument("--model", default="gemma4_e4b", help="model profile name or path for the conscious mind")
    parser.add_argument("--sub", default=None, help="model profile for the subconscious (for example lfm25_230m); off by default")
    parser.add_argument("--dry-run", action="store_true", help="keep the wheels off; everything else runs")
    parser.add_argument("--heartbeat", type=float, default=180.0, help="seconds between heartbeats")
    parser.add_argument("--beats", type=int, default=None, help="stop after this many heartbeats")
    parser.add_argument("--seconds", type=float, default=None, help="stop after this many seconds")
    parser.add_argument("--seed", type=int, default=None, help="seed for every random draw (logged, so a run can be replayed)")
    parser.add_argument("--chaos", type=float, default=None, help="pin the chaos dial at 0-10 instead of letting playfulness, mood and age set it")
    parser.add_argument("--screen", action="store_true", help="serve the face page and show the face, scenes and touches there")
    parser.add_argument("--screen-host", default="127.0.0.1", help="address for the face page (default 127.0.0.1)")
    parser.add_argument("--screen-port", type=int, default=SCREEN_PORT, help=f"port for the face page (default {SCREEN_PORT}, 0 picks a free one)")
    parser.add_argument("--screen-demo", action="store_true", help="only serve the face page and cycle faces and gallery scenes (no body, no model)")
    parser.add_argument("--presence", choices=("fake", "none"), default=None, help="who Pebble sees and hears: a scripted visitor (default with --sim) or nobody until real recognisers exist")
    parser.add_argument("--log-level", default="INFO")
    return parser


def life_settings(args: argparse.Namespace) -> LifeSettings:
    heartbeat = max(0.05, args.heartbeat)
    fast = heartbeat < 10
    return LifeSettings(
        heartbeat_s=heartbeat,
        tick_s=min(1.0, heartbeat / 2),
        waking_s=min(60.0, heartbeat * 2),
        min_turn_gap_s=min(5.0, heartbeat),
        turn_ceiling_s=min(60.0, heartbeat),
        look_floor_s=min(1800.0, heartbeat * 10),
        mind_poll_s=min(10.0, max(0.5, heartbeat)),
        mind_wait_s=5.0 if fast else 120.0,
        max_beats=args.beats,
        max_seconds=args.seconds,
    )


def make_mind(kind: str, model: str, store=None, clock=None) -> tuple[Mind, ModelProfile]:
    profile = ModelProfile.load(resolve_profile(model, "model"))
    if kind == "scripted":
        return lawful(guarded(ScriptedMind(APP_ACTS), profile, store, clock)), profile
    inner = LlamaServerMind(profile)
    return lawful(guarded(inner, profile, store, clock, inner.base)), profile


def seed_for_run(store, boots: int) -> int:
    try:
        return run_seed(ensure_seed(store), boots)
    except (LockedFile, SealedFile, OSError) as error:
        log.warning("Pebble's birth seed could not be read (%s); this run draws a fresh seed", error)
        return secrets.randbits(48)


async def run(args: argparse.Namespace, stop: asyncio.Event | None = None) -> int:
    clock = Clock()
    snapshots = Path(args.snapshots) if args.snapshots else None
    try:
        root = Path(args.self_dir)
        store = open_self(root, clock, snapshot_dir=snapshots, holder=holder_for(root, args.key_file, args.key_holder))
    except (SelfIsSealed, SealError) as error:
        log.error("the self is sealed and cannot be opened here: %s", error)
        return EXIT_SEALED
    profile = BodyProfile.load(resolve_profile(args.body or ("pc_sim" if args.sim else "droidian"), "body"))
    sim = None
    eyes = NoEyes()
    link_spec = args.link or profile.link
    if args.sim:
        world = sim_world(args.sim_world)
        sim = SimServer(SimFirmware(world), "127.0.0.1", args.sim_port)
        link_spec = f"tcp:127.0.0.1:{await sim.start()}"
        eyes = SimEyes(world, clock.now, lambda: sim.firmware.tilt)
    mind, model_profile = make_mind(args.mind, args.model, store, clock)
    sub_mind = None
    if args.sub:
        sub_profile = ModelProfile.load(resolve_profile(args.sub, "model"))
        sub_inner = LlamaServerMind(sub_profile)
        sub_mind = lawful(guarded(sub_inner, sub_profile, store, clock, sub_inner.base))
    books = Books(store, clock)
    saved = store.read("state.json", {}) or {}
    link = LinkClient(transport_factory(link_spec))
    body = Body(link, clock, profile, dry_run=args.dry_run)
    sensors = PhoneSensors.from_config(profile.sensors, clock.now, clock.monotonic)
    blackbox = BlackBox.for_store(store, clock)
    if not laws_intact(store.read("core.json")):
        log.warning("core.json does not carry Pebble's laws word for word; the prompts use the laws built into the code")
        blackbox.record("laws_mismatch")
    seed = args.seed if args.seed is not None else seed_for_run(store, int(saved.get("boots") or 0) + 1)
    chaos = Chaos(seed=seed, sink=lambda record: blackbox.record("chaos", **record), pinned=args.chaos)
    hub = Hub() if args.screen else None
    if not args.sim and not args.no_camera:
        eyes = eyes_from_config(profile.eyes, clock, hub=hub)
    face = WebFace(hub) if hub is not None else LogFace()
    voice = voice_from(profile.voice, store, clock)
    if hub is not None:
        voice = LipSyncVoice(voice, face)
    voice = TactfulVoice(voice, blackbox.record)
    permissions = Permissions()
    history = History(store, model_profile, books.name)
    builder = PromptBuilder(store)
    company = Company(books, clock)
    words = Wordsmith(mind, chaos.call_options, builder.personality_text, lambda kind: life.creative.idea_line(kind), books.name)
    context = ToolContext(
        clock,
        body,
        books,
        face,
        voice,
        permissions,
        sensors=lambda: None,
        motion_guard=company.blocked,
        people_near=company.anyone_here,
        phrase=words.phrase,
        task_from=company.task_refusal,
    )
    registry = build_registry(context)
    studio = make_studio(store, clock, face, chaos, blackbox, [("subconscious", sub_mind), ("conscious", mind)], today=lambda: life.alive.cards("drawing"))
    register_screen_tools(registry, studio)
    register_people_tools(registry, company)
    turns = TurnRunner(mind, history, builder, registry, store, clock, options=lambda: chaos.call_options("tool"))
    safety = safety_from(profile.safety, clock, books.name)
    conversation = conversation_from(profile.hearing, clock, books, store, voice, face, random.Random(derive(seed, "talk")))
    embedder = embedder_from("auto")
    chooser = Chooser(embedder, model_profile.reader_examples) if model_profile.reader_examples > 0 else None
    reader = ModelReader([("conscious", mind if args.mind == "llama" else None)], chaos.call_options, books.name, chooser=chooser)
    parts = LifeParts(
        clock=clock,
        store=store,
        books=books,
        body=body,
        sensors=sensors,
        inner=InnerState.from_dict(saved.get("inner")),
        history=history,
        turns=turns,
        mind=mind,
        permissions=permissions,
        face=face,
        voice=voice,
        diary=Diary(store, clock),
        blackbox=blackbox,
        subconscious=Subconscious(sub_mind, books.name, options=chaos.call_options),
        rng=random.Random(derive(seed, "life")),
        chaos=chaos,
        studio=studio,
        company=company,
        eyes=eyes,
        understanding=Understanding(reader),
        phrase=words.phrase,
        safety=safety,
        conversation=conversation,
        embedder=embedder,
        own_words=True,
    )
    life = Life(parts, life_settings(args))
    if safety is not None:
        safety.attach(life)
    context.motion_guard = lambda: life.blocked() or life.commands.runner.busy_reason()
    context.people_near = life.beings_near
    context.sensors = lambda: life.sensors
    context.on_spoke = life.spoke
    context.on_task_closed = life.task_closed
    context.joking_ok = lambda: life.creative.upset_until <= clock.now()
    context.life_ahead = life.life_ahead
    stop = stop or asyncio.Event()
    loop = asyncio.get_running_loop()
    ears = hearing_from(profile.hearing, clock) or ears_from(profile.hearing, clock)
    if safety is not None:
        safety.ears = ears
    if conversation is not None:
        conversation.attach(life, safety=safety, ears=ears, hub=hub)
    server = None
    if hub is not None:
        try:
            server = start_face_server(
                hub,
                args.screen_host,
                args.screen_port,
                threadsafe(loop, life.touched),
                lambda: {"face": face.state.as_dict(), "chaos": chaos.explain(), "eyes": eyes_status(eyes), "ears": ears.status() if ears is not None else None, "safety": safety.status() if safety is not None else None, "talk": conversation.status() if conversation is not None else None},
                eyes=eyes if isinstance(eyes, BrowserEyes) else None,
                routes=life.nav.routes() if getattr(life, "nav", None) is not None else None,
                on_pad=threadsafe(loop, life.pad),
            )
        except OSError as error:
            log.error("the face page could not start (%s); carrying on without it", error)
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
        except (NotImplementedError, RuntimeError, ValueError):
            pass
    log.info("Pebble starting: self=%s link=%s mind=%s dry_run=%s", store.root, link_spec, mind.name, args.dry_run)
    visitors = None
    if (args.presence or ("fake" if args.sim else "none")) == "fake":
        visitors = asyncio.create_task(FakePresence().run(life), name="pebble-visitors")
    listening = asyncio.create_task(ears.run(life), name="pebble-ears") if ears is not None else None
    talking = asyncio.create_task(conversation.run(), name="pebble-conversation") if conversation is not None else None
    try:
        reason = await life.run(stop)
    finally:
        if visitors is not None:
            visitors.cancel()
            await asyncio.gather(visitors, return_exceptions=True)
        if listening is not None:
            listening.cancel()
            await asyncio.gather(listening, return_exceptions=True)
        if talking is not None:
            talking.cancel()
            await asyncio.gather(talking, return_exceptions=True)
        if server is not None:
            server.stop()
        await mind.close()
        if sub_mind is not None:
            await sub_mind.close()
        if sim is not None:
            await sim.stop()
        close_eyes(eyes)
        if safety is not None:
            safety.close()
        blackbox.close()
    if reason is ExitReason.SHUTDOWN:
        power_from(profile.power).shutdown()
        return EXIT_SHUTDOWN
    return EXIT_OK


def eyes_status(eyes) -> dict:
    status = getattr(eyes, "status", None)
    return status() if callable(status) else {"available": bool(getattr(eyes, "available", False))}


def sim_world(kind: str) -> World:
    start = Pose(SIM_START.x, SIM_START.y, SIM_START.heading)
    if kind == "table":
        return World(pose=start)
    name, x, y = SIM_VISITOR
    things = household()
    for thing in things:
        if thing.animal:
            thing.speed_mm_s = 60.0
            thing.roam = [(3600.0, -900.0), (2600.0, -200.0), (1500.0, -1100.0), (3000.0, 400.0)]
    return World(table=room(), pose=start, people=[SimPerson(name, x, y, track=1)], things=things)


def make_studio(store, clock, face, chaos: Chaos, blackbox: BlackBox, minds, today=None) -> Studio:
    decks = IdeaDecks.open(store) if today is None else TodayDecks(IdeaDecks.open(store), today)
    stage = SceneStage(face)
    generator = SceneGenerator(minds, stage, chaos.call_options, lambda kind: chaos.cards(decks, kind))
    return Studio(Gallery.open(store), stage, generator, clock, chaos.stream, lambda: chaos.level, blackbox.record)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        if args.screen_demo:
            return asyncio.run(run_demo(Path(args.self_dir), args.screen_host, args.screen_port, args.seed, args.seconds, args.chaos))
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return EXIT_OK
