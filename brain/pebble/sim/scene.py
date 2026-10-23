import argparse
import asyncio
import heapq
import itertools
import math
import random
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..activities.kit import Pace
from ..blackbox import BlackBox
from ..body.api import Body
from ..body.profile import BodyProfile, resolve_profile
from ..body.sensors import FakeBattery, FakeValue, NoImu, PhoneSensors
from ..books import Books
from ..clock import Clock, FakeClock
from ..diary import Diary
from ..inner.state import InnerState
from ..life.loop import Life, LifeParts, LifeSettings
from ..life.turn import TurnRunner
from ..link.client import LinkClient
from ..link.transport import LinkClosed, Transport, transport_factory
from ..mind.history import History
from ..mind.profile import ModelProfile
from ..mind.prompt import PromptBuilder
from ..mind.scripted import ScriptedMind
from ..people.fake import fake_print
from ..people.proof import SEEN_SPEAKING
from ..people.trust import CHILD, FRIEND, OVERRIDES, TRUSTED
from ..seams.face import LogFace
from ..seams.sight import NoEyes
from ..seams.voice import SpeechResult, TranscriptVoice
from ..selfstore import SelfStore
from ..tools.builtin import Permissions, ToolContext, build_registry
from .eyes import SimEyes
from .firmware import SimFirmware
from .server import SimServer
from .world import Pose, SimPerson, SimThing, World, room

STEP_S = 0.01
SETTLE_ROUNDS = 40
NOON = datetime(2026, 10, 15, 11, 0, tzinfo=timezone.utc)


def household() -> list[SimThing]:
    return [
        SimThing("couch", 2200.0, 1150.0, width_mm=1800.0, depth_mm=700.0, height_mm=800.0, fast="couch", slow="couch", track=101),
        SimThing("chair", 3300.0, 900.0, width_mm=500.0, depth_mm=500.0, height_mm=900.0, fast="chair", slow="armchair", track=102),
        SimThing("ball", 1200.0, -1000.0, width_mm=200.0, depth_mm=200.0, height_mm=200.0, fast="ball", slow="tennis ball", track=103),
        SimThing("slipper", 1900.0, 650.0, width_mm=250.0, depth_mm=100.0, height_mm=80.0, slow="slipper", track=104),
        SimThing("plant pot", 3700.0, -1200.0, width_mm=300.0, depth_mm=300.0, height_mm=300.0, slow="plant pot", track=105),
        SimThing("cat", 3600.0, -900.0, width_mm=450.0, depth_mm=200.0, height_mm=250.0, fast="cat", animal=True, track=106),
    ]


class LoopbackTransport(Transport):
    label = "loopback:sim"

    def __init__(self, firmware: SimFirmware):
        self.firmware = firmware
        self.queue: asyncio.Queue = asyncio.Queue()
        self.is_open = False

    def feed(self, lines: list[str]) -> None:
        for line in lines:
            self.queue.put_nowait(line)

    async def open(self) -> None:
        self.is_open = True
        self.feed(self.firmware.connected())

    async def read_line(self) -> str:
        if not self.is_open:
            raise LinkClosed("not open")
        line = await self.queue.get()
        if line is None:
            raise LinkClosed("closed")
        return line

    async def write_line(self, line: str) -> None:
        if not self.is_open:
            raise LinkClosed("not open")
        self.feed(self.firmware.receive(line + "\n"))

    async def close(self) -> None:
        if self.is_open:
            self.is_open = False
            self.queue.put_nowait(None)


class VirtualTime(Pace):
    def __init__(self, clock: FakeClock, firmware: SimFirmware, transport: LoopbackTransport):
        super().__init__(clock.monotonic)
        self.clock = clock
        self.firmware = firmware
        self.transport = transport
        self.sleepers: list = []
        self.count = itertools.count()

    async def sleep(self, seconds: float) -> None:
        future = asyncio.get_running_loop().create_future()
        heapq.heappush(self.sleepers, (self.now() + max(0.001, seconds), next(self.count), future))
        await future

    async def settle(self) -> None:
        for _ in range(SETTLE_ROUNDS):
            await asyncio.sleep(0)

    def advance(self, until: float) -> None:
        while self.now() < until - 1e-9:
            dt = min(STEP_S, until - self.now())
            self.transport.feed(self.firmware.step(dt))
            self.clock.advance(dt)

    async def run_until(self, until: float) -> None:
        while True:
            await self.settle()
            while self.sleepers and self.sleepers[0][2].done():
                heapq.heappop(self.sleepers)
            nxt = self.sleepers[0][0] if self.sleepers else until
            target = min(nxt, until)
            self.advance(target)
            while self.sleepers and self.sleepers[0][0] <= self.now() + 1e-9:
                _, _, future = heapq.heappop(self.sleepers)
                if not future.done():
                    future.set_result(None)
            if self.now() >= until - 1e-9:
                await self.settle()
                return


class RealTime(Pace):
    async def settle(self) -> None:
        await asyncio.sleep(0.05)

    async def run_until(self, until: float) -> None:
        await asyncio.sleep(max(0.0, until - self.now()))


class RecordingVoice:
    def __init__(self, inner: TranscriptVoice, trace):
        self.inner = inner
        self.trace = trace

    async def say(self, text: str, whisper: bool = False) -> SpeechResult:
        self.trace("says", f'"{" ".join(text.split())}"')
        return await self.inner.say(text, whisper)


@dataclass
class Who:
    name: str
    tier: str | None = None
    x: float = 1200.0
    y: float = 0.0


@dataclass
class Scene:
    root: Path
    people: list = field(default_factory=lambda: [Who("Ina", TRUSTED, 1300.0, 0.0)])
    seed: int = 7
    lines: list = field(default_factory=list)
    echo: bool = False
    start: tuple = (80.5, 0.0, 0.0)
    battery: float = 80.0
    blind: bool = False
    at: datetime = NOON
    real: bool = False
    knows_way: bool = True
    understanding: object | None = None
    things: list | None = None
    extra: dict | None = None
    size: tuple | None = None

    def trace(self, what: str, text: str) -> None:
        line = f"{self.clock.monotonic() - self.t0:6.1f}s  {what:<8} {text}"
        self.lines.append(line)
        if self.echo:
            print(line, flush=True)

    async def setup(self) -> None:
        self.clock = Clock() if self.real else FakeClock.at(self.at)
        self.t0 = self.clock.monotonic()
        self.store = SelfStore.open(self.root, self.clock)
        self.books = Books(self.store, self.clock)
        profile = BodyProfile.load(resolve_profile("pc_sim", "body"))
        persons = [SimPerson(w.name.lower(), w.x, w.y, track=i + 1) for i, w in enumerate(self.people)]
        x, y, heading = self.start
        self.world = World(table=room(*self.size) if self.size else room(), pose=Pose(x, y, math.radians(heading)), people=persons, things=list(self.things or []))
        self.firmware = SimFirmware(self.world)
        self.server = None
        if self.real:
            self.server = SimServer(self.firmware, "127.0.0.1", 0)
            port = await self.server.start()
            self.time = RealTime(self.clock.monotonic)
            self.link = LinkClient(transport_factory(f"tcp:127.0.0.1:{port}"))
        else:
            self.transport = LoopbackTransport(self.firmware)
            self.time = VirtualTime(self.clock, self.firmware, self.transport)
            self.link = LinkClient(lambda: self.transport, ping_every_s=3600.0, stale_s=1e9)
        self.body = Body(self.link, self.clock, profile)
        self.eyes = NoEyes() if self.blind else SimEyes(self.world, self.clock.now, lambda: self.firmware.tilt, seed=self.seed)
        self.phone_battery = FakeBattery(self.battery, False, 0.0, self.clock.monotonic)
        battery = self.phone_battery
        sensors = PhoneSensors(battery, FakeValue(30.0), FakeValue(150.0), NoImu(), self.clock.now)
        mind = ScriptedMind(acts=[])
        model = ModelProfile.from_dict({"name": "scene", "context_tokens": 4096, "compact_at_tokens": 2500, "keep_tokens_after_compaction": 1000})
        history = History(self.store, model, self.books.name)
        face = LogFace()
        voice = RecordingVoice(TranscriptVoice(self.store, self.clock, echo=False), self.trace)
        permissions = Permissions()
        context = ToolContext(self.clock, self.body, self.books, face, voice, permissions, sensors=lambda: None)
        registry = build_registry(context)
        turns = TurnRunner(mind, history, PromptBuilder(self.store), registry, self.store, self.clock)
        self.blackbox = BlackBox(self.store.path("logs/blackbox.jsonl"), self.clock)
        parts = LifeParts(
            clock=self.clock,
            store=self.store,
            books=self.books,
            body=self.body,
            sensors=sensors,
            inner=InnerState(),
            history=history,
            turns=turns,
            mind=mind,
            permissions=permissions,
            face=face,
            voice=voice,
            diary=Diary(self.store, self.clock),
            blackbox=self.blackbox,
            rng=random.Random(self.seed),
            eyes=self.eyes,
            pace=self.time,
            understanding=self.understanding,
            **(self.extra or {}),
        )
        settings = LifeSettings(heartbeat_s=3600.0, tick_s=1.0, waking_s=0.0, sensor_every_s=30.0, mind_wait_s=5.0) if self.real else LifeSettings(waking_s=0.0, sensor_every_s=1e9)
        self.life = Life(parts, settings)
        context.motion_guard = lambda: self.life.blocked() or self.life.commands.runner.busy_reason()
        context.people_near = self.life.company.anyone_here
        note = self.life.commands.note

        def noted(text: str, major: bool) -> None:
            self.trace("thinks", text)
            note(text, major)

        self.life.commands.note = noted
        self._meet()
        if self.real:
            self.stop = asyncio.Event()
            self.background = [asyncio.ensure_future(self.life.run(self.stop)), asyncio.ensure_future(self._eyes()), asyncio.ensure_future(self._watch())]
        else:
            self.body.start()
            await self.life.read_sensors()
            self.background = [
                asyncio.ensure_future(self._ticker()),
                asyncio.ensure_future(self._eyes()),
                asyncio.ensure_future(self._watch()),
                asyncio.ensure_future(self.life.nav.run()),
                asyncio.ensure_future(self.life.alive.run()),
                asyncio.ensure_future(self.life.hands.run()),
            ]
        if self.knows_way and not self.world.docked():
            self.life.odometer.reset(x / 1000.0, y / 1000.0, math.radians(heading))
        await self.time.run_until(self.clock.monotonic() + 2.5)
        for _ in range(100):
            if self.life.state.value == "active" or self.real:
                break
            await self.time.run_until(self.clock.monotonic() + 0.5)
        self.t0 = self.clock.monotonic()

    def _meet(self) -> None:
        now = self.clock.now()
        for who in self.people:
            person = self.books.people.meet(now, voice=fake_print(who.name.lower(), "voice"), face=fake_print(who.name.lower(), "face"))
            person.set_name(who.name)
            if who.tier == CHILD:
                person.relationship = "child"
            elif who.tier in OVERRIDES:
                person.override = who.tier
            elif who.tier == FRIEND:
                person.relationship = "friend"

    async def _ticker(self) -> None:
        while True:
            await self.time.sleep(1.0)
            await self.life.tick(1.0)

    async def _eyes(self) -> None:
        while True:
            for person in self.world.people:
                if person.home:
                    self.life.see(fake_print(person.name, "face"))
            await self.time.sleep(2.0)

    async def _watch(self) -> None:
        while True:
            await self.time.sleep(5.0)
            current = self.life.commands.runner.current
            if current is None or current.kind == "wait":
                continue
            pose = self.world.pose
            where = f"Pebble at ({pose.x / 1000:.2f}, {pose.y / 1000:.2f}) m facing {math.degrees(pose.heading) % 360:.0f} deg"
            target = self.world.person(current.target.label.lower()) if current.target else None
            if target is None and current.request.thing:
                target = next((t for t in self.world.things if t.home and current.request.thing in (t.fast or "", t.slow or "", t.name)), None)
            if target is not None:
                gap = math.hypot(target.x - pose.x, target.y - pose.y) / 1000.0 - 0.1 - target.radius_mm / 1000.0
                where += f"; {target.name.title()} at ({target.x / 1000:.2f}, {target.y / 1000:.2f}), gap {gap:.2f} m"
            cat = self.world.thing("cat")
            if cat is not None and cat.home and math.hypot(cat.x - pose.x, cat.y - pose.y) < 1500.0:
                where += f"; the cat is {math.hypot(cat.x - pose.x, cat.y - pose.y) / 1000.0:.2f} m away"
            self.trace("sim", f"{current.describe()}: {where}")

    async def say(self, name: str | None, text: str, seen: bool = True) -> None:
        self.trace("hears", f'{name or "someone"}: "{text}"' + ("" if seen else " (not seen)"))
        person = self.world.person(name.lower()) if name else None
        shown = seen and person is not None and person.home
        self.life.hear(text, fake_print(name.lower(), "voice") if name else None, proof=SEEN_SPEAKING if shown else None)
        await self.time.settle()
        while self.life.commands.tasks:
            await self.time.run_until(self.clock.monotonic() + 0.05)

    def walk(self, name: str, *points, speed_mm_s: float = 60.0) -> None:
        person = self.world.person(name.lower())
        person.walk_to(*[(x * 1000.0, y * 1000.0) for x, y in points], speed_mm_s=speed_mm_s)
        self.trace("sim", f"{name} walks to " + " then ".join(f"({x:.1f}, {y:.1f})" for x, y in points))

    def move_thing(self, name: str, *points, speed_mm_s: float = 150.0) -> None:
        thing = self.world.thing(name)
        thing.walk_to(*[(x * 1000.0, y * 1000.0) for x, y in points], speed_mm_s=speed_mm_s)
        self.trace("sim", f"the {name} walks to " + " then ".join(f"({x:.1f}, {y:.1f})" for x, y in points))

    def leave(self, name: str) -> None:
        self.world.person(name.lower()).home = False
        self.trace("sim", f"{name} leaves the room")

    def arrive(self, name: str, x: float, y: float) -> None:
        person = self.world.person(name.lower())
        person.home, person.x, person.y = True, x * 1000.0, y * 1000.0
        self.trace("sim", f"{name} comes back in at ({x:.1f}, {y:.1f})")

    async def run(self, seconds: float) -> None:
        await self.time.run_until(self.clock.monotonic() + seconds)

    async def until_idle(self, limit_s: float, step_s: float = 1.0) -> None:
        end = self.clock.monotonic() + limit_s
        while self.clock.monotonic() < end and (self.life.commands.runner.busy or self.life.commands.tasks):
            await self.run(step_s)

    async def close(self) -> None:
        if self.real:
            self.stop.set()
            await asyncio.gather(self.background[0], return_exceptions=True)
            for task in self.background[1:]:
                task.cancel()
            await asyncio.gather(*self.background[1:], return_exceptions=True)
            await self.server.stop()
        else:
            await self.life.commands.close()
            for task in self.background:
                task.cancel()
            await asyncio.gather(*self.background, return_exceptions=True)
            await self.body.close()
        self.blackbox.close()


async def follow_wait_come_bed(scene: Scene) -> None:
    await scene.say("Ina", "Pebble, follow me")
    await scene.run(3.0)
    scene.walk("Ina", (2.2, 0.4), (2.9, -0.3), speed_mm_s=45.0)
    cat = scene.world.thing("cat")
    if cat is not None:
        cat.x, cat.y = 1650.0, -1300.0
        await scene.run(12.0)
        scene.move_thing("cat", (1.65, 1.3), speed_mm_s=110.0)
        await scene.run(48.0)
    else:
        await scene.run(60.0)
    await scene.say("Ina", "a bit slower")
    await scene.run(25.0)
    await scene.say("Ina", "good, stay there")
    await scene.run(2.0)
    await scene.say("Ina", "wait here till I'm back")
    await scene.run(2.0)
    scene.leave("Ina")
    await scene.run(150.0)
    scene.arrive("Ina", 1.6, 0.9)
    await scene.run(4.0)
    await scene.say("Ina", "come here")
    await scene.until_idle(90.0)
    await scene.say("Ina", "now look at me")
    await scene.run(6.0)
    if scene.world.things:
        await scene.say("Ina", "where's my slipper?")
        await scene.run(2.0)
        await scene.say("Ina", "can you find the ball")
        await scene.until_idle(90.0)
        await scene.say("Ina", "what's that?")
        await scene.run(2.0)
        await scene.say("Ina", "what can you see?")
        await scene.run(2.0)
    await scene.say("Ina", "ok, time for bed")
    await scene.until_idle(240.0)
    await scene.run(2.0)


async def come_and_bed(scene: Scene) -> None:
    scene.world.person("ina").x, scene.world.person("ina").y = 1800.0, -700.0
    await scene.run(3.0)
    await scene.say("Ina", "hey Pebble, come say hi")
    await scene.until_idle(90.0)
    await scene.say("Ina", "that's it, now off to bed")
    await scene.until_idle(240.0)
    await scene.run(2.0)


SCENES = {"follow": follow_wait_come_bed, "short": come_and_bed}


async def play(name: str = "follow", root: Path | None = None, echo: bool = False, real: bool = False) -> Scene:
    holder = None
    if root is None:
        holder = tempfile.TemporaryDirectory(prefix="pebble-scene-")
        root = Path(holder.name) / "self"
    scene = Scene(root, echo=echo, real=real, things=household())
    try:
        await scene.setup()
        await SCENES[name](scene)
        pose = scene.world.pose
        scene.trace("sim", f"end: Pebble at ({pose.x / 1000:.2f}, {pose.y / 1000:.2f}) m, docked={scene.world.docked()}")
    finally:
        await scene.close()
        if holder is not None:
            holder.cleanup()
    return scene


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.sim.scene", description="Play a scripted scene against the simulated body and print what happened")
    parser.add_argument("--scene", choices=sorted(SCENES), default="follow")
    parser.add_argument("--self", dest="self_dir", default=None, help="keep the self folder here (default: a temporary one)")
    parser.add_argument("--real", action="store_true", help="run in real time over TCP with the whole brain loop, as python -m pebble --sim does (the follow scene takes about 6 minutes)")
    args = parser.parse_args(argv)
    scene = asyncio.run(play(args.scene, Path(args.self_dir) if args.self_dir else None, echo=True, real=args.real))
    return 0 if scene.world.docked() else 1


if __name__ == "__main__":
    sys.exit(main())
