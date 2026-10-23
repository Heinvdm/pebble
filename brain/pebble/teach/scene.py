import argparse
import asyncio
import json
import math
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ..mind.base import Mind, MindReply
from ..people.trust import CHILD, TRUSTED
from ..sim.scene import Who
from ..sim.world import SimThing
from ..understand.model import ModelReader
from ..understand.understanding import Understanding

UTC = timezone.utc
AT = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
HEARD = re.compile(r'Heard: "(.*)"\s*$', re.S)
PLAIN = re.compile(r'The plain (?:line|question): "(.*)"')
ROOMS = {"lounge": (2.5, 0.0, 1.4), "bathroom": (6.5, 1.9, 1.0), "bedroom": (6.5, -1.9, 1.0), "kitchen": (4.2, 2.2, 0.9), "study": (4.2, -2.2, 0.9)}
TOYS = ("toy car", "sock", "teddy", "block", "shirt")
READINGS = {
    "When I come home, greet me like this.": {"kind": "chat"},
    "Look around.": {"kind": "turn", "way": "around", "degrees": 360},
}


class TeachMind(Mind):
    name = "stand-in for E4B"

    def __init__(self, readings: dict | None = None, taught=(), looks=(), plans=()):
        self.readings = {self.key(text): reading for text, reading in {**READINGS, **(readings or {})}.items()}
        self.taught = list(taught)
        self.looks = list(looks)
        self.plans = list(plans)
        self.asked: list[tuple[str, str]] = []

    @staticmethod
    def key(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9']+", text.lower()))

    async def sees(self) -> bool:
        return bool(self.looks)

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        content = messages[-1]["content"]
        last = content[0]["text"] if isinstance(content, list) else str(content)
        self.asked.append((purpose, last))
        if purpose == "teach":
            reply = self.taught.pop(0) if self.taught else "not now"
            if callable(reply):
                reply = reply(last)
            return MindReply(reply if isinstance(reply, str) else json.dumps(reply))
        if purpose == "look":
            return MindReply(self.looks.pop(0) if len(self.looks) > 1 else (self.looks[0] if self.looks else ""))
        if purpose == "plan":
            return MindReply(json.dumps(self.plans.pop(0) if self.plans else {"cant": "no more ideas"}))
        if purpose == "decision":
            found = PLAIN.search(last)
            return MindReply(found.group(1) if found else "")
        if purpose == "unstuck":
            return MindReply('{"choose":"give_up"}')
        found = HEARD.search(last)
        reading = self.readings.get(self.key(found.group(1)) if found else "")
        return MindReply(json.dumps(reading) if reading is not None else '{"kind":"chat"}')

    async def warm(self, messages, tools=None, purpose="warm"):
        return True

    def purposes(self) -> list[str]:
        return [purpose for purpose, _ in self.asked]


async def staged(root: Path, echo: bool = False, people=None, readings: dict | None = None, taught=(), looks=(), plans=(), rooms=None, things=None):
    from ..activities.picture import PictureQuestions
    from ..life.scene import LaterScene

    mind = TeachMind(readings, taught, looks, plans)
    play = LaterScene(root, people or [Who("Ina", TRUSTED, 1700.0, 600.0)], AT, {}, echo=echo, rooms=rooms or ROOMS)
    play.scene.understanding = Understanding(ModelReader([("conscious", mind)]))
    if things is not None:
        play.scene.things = things
    await play.setup()
    pictures = PictureQuestions(play.scene.eyes, mind)
    pictures.guard = play.life.privacy
    play.life.commands.pictures = pictures
    return play, mind


def teaching(play):
    return play.life.teaching


def quiet(play) -> bool:
    life = play.life
    t = life.teaching
    current = life.commands.runner.current
    idle = current is None or (current.kind in ("wait", "copy_me", "follow", "drive") and not t.player.busy())
    return idle and not life.commands.tasks and not t.player.busy() and (t.making is None or t.waiting is not None)


async def settle(play, limit: float = 300.0, step: float = 0.5) -> None:
    scene = play.scene
    end = scene.clock.monotonic() + limit
    await scene.run(step)
    while scene.clock.monotonic() < end and not quiet(play):
        await scene.run(step)


async def say(play, who: str | None, text: str, limit: float = 300.0, seen: bool = True) -> None:
    await play.scene.say(who, text, seen=seen)
    await settle(play, limit)


async def drive(play, x: float, y: float, seconds: float) -> None:
    scene = play.scene
    end = scene.clock.monotonic() + seconds
    while scene.clock.monotonic() < end:
        play.life.pad({"kind": "drive", "x": x, "y": y})
        await scene.run(0.15)
    play.life.pad({"kind": "drive", "x": 0.0, "y": 0.0})
    await scene.run(1.2)


async def press(play, command: dict) -> None:
    play.life.pad(command)
    await play.scene.run(1.0)


async def carry(play, x: float, y: float, heading_deg: float = 0.0) -> None:
    life = play.life
    world = play.scene.world
    life.felt("lifted", "someone picked you up")
    await play.scene.run(1.0)
    world.pose.x, world.pose.y, world.pose.heading = x * 1000.0, y * 1000.0, math.radians(heading_deg)
    life.odometer.relocate(x, y, heading_deg)
    await play.scene.run(1.0)
    life.odometer.carried = False
    life.odometer._tell("put_down")
    await play.scene.run(1.0)


def scatter(play, near: tuple, count: int, seed: int = 1, kinds=TOYS) -> list:
    import random

    rng = random.Random(seed)
    world = play.scene.world
    out = []
    for n in range(count):
        kind = kinds[n % len(kinds)]
        thing = SimThing(f"{kind} {seed}-{n}", near[0] * 1000.0 + rng.uniform(-500, 500), near[1] * 1000.0 + rng.uniform(-600, 600), width_mm=220.0, depth_mm=220.0, height_mm=120.0, slow=kind, print_id=kind.replace(" ", "_"), track=500 + seed * 20 + n)
        world.things.append(thing)
        out.append(thing)
    return out


def tidy(play, things: list) -> None:
    for thing in things:
        if thing in play.scene.world.things:
            play.scene.world.things.remove(thing)


def face(play, x: float, y: float, heading_deg: float) -> None:
    pose = play.scene.world.pose
    pose.x, pose.y, pose.heading = x * 1000.0, y * 1000.0, math.radians(heading_deg)
    play.life.odometer.relocate(x, y, heading_deg)


def records(play, *kinds) -> list:
    return [r for r in play.records() if r["kind"] in kinds]


def endings(play) -> list:
    return [(activity.kind, ending.how) for activity, ending in play.life.commands.runner.history]


def ran(play, kind: str) -> list:
    return [activity for activity, _ in play.life.commands.runner.history if activity.kind == kind]


async def twirl(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo)
    out = {}
    try:
        await say(play, "Ina", "I'm going to teach you something.")
        out["mark"] = dict(teaching(play).screen)
        await say(play, "Ina", "Spin around.")
        await say(play, "Ina", "Turn left.")
        out["list"] = list(teaching(play).screen["steps"])
        await play.scene.say("Ina", "That's it, call it the twirl.")
        await play.scene.run(1.0)
        out["replaying"] = play.life.commands.runner.current.kind if play.life.commands.runner.current else None
        out["timings"] = list(teaching(play).timings)
        await settle(play)
        out["asked"] = play.said()[-1]
        await say(play, "Ina", "Yes!")
        out["entry"] = teaching(play).book.get("twirl")
        out["skill"] = play.life.skills.get("twirl")
        out["mark_after"] = dict(teaching(play).screen)
        before = len(ran(play, "try_new"))
        await say(play, "Ina", "Do the twirl.")
        out["again"] = ran(play, "try_new")[before:]
        out["said"] = play.said()
        out["records"] = records(play, "teach_started", "teach_step", "teach_ended", "teach_replayed", "howto_kept")
    finally:
        await play.close()
    return play, out


async def rooms_check(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 2600.0, 600.0)])
    out = {"said": []}
    try:
        for room in ("kitchen", "study"):
            face(play, 2.4, 0.0, 0.0)
            await say(play, "Ina", f"Let me show you how to check the {room}.")
            await say(play, "Ina", f"Go to the {room}.")
            await say(play, "Ina", "Turn around.")
            await say(play, "Ina", "Come back to me.")
            await say(play, "Ina", "That's it.")
            await say(play, "Ina", "Yes!")
            out[room] = teaching(play).book.get("check the kitchen")
        out["questions"] = records(play, "teach_question")
        face(play, 2.4, 0.0, 0.0)
        before = len(play.life.commands.runner.history)
        await say(play, "Ina", "Check the lounge.")
        out["new"] = [(a.kind, a.request.as_dict()) for a, e in play.life.commands.runner.history[before:]]
        out["said"] = play.said()
    finally:
        await play.close()
    return play, out


async def question(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo)
    out = {}
    try:
        for way in ("left", "right"):
            await say(play, "Ina", "Let me teach you the hello.")
            await say(play, "Ina", "Spin around.")
            await say(play, "Ina", f"Turn {way}.")
            await say(play, "Ina", "That's it.")
            await say(play, "Ina", "Yes!")
        out["asked"] = play.said()[-1]
        await say(play, "Ina", "No, it doesn't matter.")
        out["entry"] = teaching(play).book.get("hello")
        out["said"] = play.said()
        out["questions"] = records(play, "teach_question")
    finally:
        await play.close()
    return play, out


async def pad(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo)
    out = {}
    try:
        await say(play, "Ina", "Watch this.")
        await drive(play, 1.0, 0.0, 2.0)
        await drive(play, 0.0, 1.0, 1.5)
        await press(play, {"kind": "tilt", "way": "up"})
        await press(play, {"kind": "face", "expression": "happy"})
        out["shown"] = [item.step for item in teaching(play).session.record.items]
        await say(play, "Ina", "That's it, call it the shuffle.")
        await say(play, "Ina", "Yes!")
        out["entry"] = teaching(play).book.get("shuffle")
        out["drives"] = ran(play, "drive")
        out["said"] = play.said()
    finally:
        await play.close()
    return play, out


async def lead(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 2800.0, 0.0)])
    out = {}
    try:
        face(play, 2.2, 0.0, 0.0)
        scene = play.scene
        for name in ("cat", "plant pot"):
            scene.world.thing(name).home = False
        await say(play, "Ina", "Follow me and learn the way to the study.", limit=5.0)
        scene.walk("Ina", (3.3, -0.4), (4.0, -1.4), (4.3, -2.6), speed_mm_s=120.0)
        await scene.run(120.0)
        out["trail"] = [list(p) for p in teaching(play).session.record.trail] if teaching(play).session else []
        track = []
        await scene.say("Ina", "That's it.")
        for _ in range(240):
            await scene.run(0.5)
            pose = scene.world.pose
            track.append((pose.x / 1000.0, pose.y / 1000.0))
            if quiet(play):
                break
        out["back_track"] = track
        out["asked"] = play.said()[-1]
        await say(play, "Ina", "Yes!")
        out["entry"] = teaching(play).book.get("study")
        scene.walk("Ina", (3.0, -0.8), (2.4, 0.9), speed_mm_s=300.0)
        await scene.run(20.0)
        face(play, 2.2, 0.0, 0.0)
        track = []
        last = (ran(play, "route") or [None])[-1]
        await scene.say("Ina", "Go to the study.")
        for _ in range(240):
            await scene.run(0.5)
            pose = scene.world.pose
            track.append((pose.x / 1000.0, pose.y / 1000.0))
            if quiet(play) or (ran(play, "route") or [None])[-1] is not last:
                break
        out["track"] = track
        out["routes"] = ran(play, "route")
        out["endings"] = endings(play)
        out["said"] = play.said()
    finally:
        await play.close()
    return play, out


async def spot(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo)
    out = {}
    try:
        await say(play, "Ina", "Let me show you something.")
        await carry(play, 3.2, 1.0, 90.0)
        await say(play, "Ina", "This is where you sit when we watch TV.")
        await say(play, "Ina", "That's it.")
        out["entry"] = teaching(play).book.get("tv spot")
        face(play, 2.0, -0.5, 0.0)
        await say(play, "Ina", "Go to the tv spot.")
        pose = play.scene.world.pose
        out["gap"] = math.hypot(pose.x / 1000.0 - 3.2, pose.y / 1000.0 - 1.0)
        out["said"] = play.said()
    finally:
        await play.close()
    return play, out


async def messy(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, looks=["toys and clothes on the floor"])
    out = {}
    try:
        face(play, 1.0, 0.0, 0.0)
        mess = scatter(play, (2.4, 0.0), 5, 1)
        await say(play, "Ina", "Let me teach you something.")
        await say(play, "Ina", "This is what messy looks like.")
        tidy(play, mess)
        mess = scatter(play, (2.4, 0.2), 4, 2)
        await say(play, "Ina", "This is messy too.")
        tidy(play, mess)
        await say(play, "Ina", "This is not messy.")
        await say(play, "Ina", "That's it.")
        await settle(play, 30.0)
        entry = teaching(play).book.get("messy")
        out["entry"] = entry
        mess = scatter(play, (2.4, -0.2), 5, 7)
        out["messy_now"] = await teaching(play).concepts.is_this(entry)
        tidy(play, mess)
        out["tidy_now"] = await teaching(play).concepts.is_this(entry)
        face(play, 1.3, 0.0, 0.0)
        mess = scatter(play, (2.5, 0.0), 5, 8)
        await play.scene.run(12.0)
        before = len(play.said())
        await say(play, "Ina", "If the lounge is messy, tell me.")
        out["looks_said"] = play.said()[before:]
        tidy(play, mess)
        await play.scene.run(12.0)
        before = len(play.said())
        await say(play, "Ina", "If the lounge is messy, tell me.")
        out["tidy_said"] = play.said()[before:]
        out["said"] = play.said()
    finally:
        await play.close()
    return play, out


async def boop(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo)
    out = {}
    try:
        await say(play, "Ina", "When I say boop, spin around.")
        out["entry"] = teaching(play).book.get("boop")
        before = len(play.life.commands.runner.history)
        await say(play, "Ina", "Boop!")
        out["ran"] = [(a.kind, a.request.as_dict()) for a, e in play.life.commands.runner.history[before:]]
        await say(play, "Ina", "When I say zap, run at the cat.")
        out["zap"] = teaching(play).book.get("zap")
        out["said"] = play.said()
    finally:
        await play.close()
    return play, out


async def doorbell(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 3000.0, 800.0)])
    out = {}
    try:
        await say(play, "Ina", "Whenever the doorbell rings, come and get me.")
        out["entry"] = teaching(play).book.get("when the doorbell rings") or next(iter(teaching(play).book.of_kind("habit")), None)
        face(play, 1.2, -0.8, 0.0)
        before = len(play.life.commands.runner.history)
        play.life.later.sound("doorbell")
        await play.scene.run(2.0)
        await settle(play)
        out["ran"] = [(a.kind, a.request.as_dict()) for a, e in play.life.commands.runner.history[before:]]
        out["fired"] = records(play, "howto_fired")
        out["said"] = play.said()
    finally:
        await play.close()
    return play, out


async def greet(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, [Who("Mo", TRUSTED, 1700.0, 600.0)])
    out = {}
    try:
        await say(play, "Mo", "When I come home, greet me like this.")
        await say(play, "Mo", "Spin around.")
        await say(play, "Mo", "That's it.")
        await say(play, "Mo", "Yes!")
        out["entry"] = next(iter(teaching(play).book.of_kind("way")), None)
        play.scene.leave("Mo")
        await play.later_skip(900.0) if hasattr(play, "later_skip") else await play.skip(900.0)
        before = len(play.life.commands.runner.history)
        play.scene.arrive("Mo", 1.8, 0.5)
        for _ in range(6):
            play.seen()
            await play.scene.run(2.0)
        await settle(play)
        out["ran"] = [(a.kind, a.request.as_dict()) for a, e in play.life.commands.runner.history[before:]]
        out["fired"] = records(play, "howto_fired")
        out["said"] = play.said()
    finally:
        await play.close()
    return play, out


async def copy_me(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1500.0, 0.0)])
    out = {}
    try:
        face(play, 0.3, 0.0, 0.0)
        ina = play.scene.world.person("ina")
        await play.scene.say("Ina", "Copy me.")
        await play.scene.run(2.0)
        ina.arm, ina.arm_side = "wave", "right"
        await play.scene.run(4.0)
        ina.arm = "down"
        await play.scene.run(6.0)
        ina.facing = math.atan2(ina.y - 0.0, ina.x - 1000.0)
        await play.scene.run(2.0)
        ina.facing = None
        await play.scene.run(22.0)
        ina.posture = "crouching"
        await play.scene.run(3.0)
        ina.posture = None
        await play.scene.run(6.0)
        ina.nod = True
        await play.scene.run(3.0)
        ina.nod = False
        await play.scene.run(8.0)
        await say(play, "Ina", "That's enough.")
        await settle(play, 90.0)
        out["mimic"] = ran(play, "copy_me")
        await say(play, "Ina", "Remember that.")
        await say(play, "Ina", "Call it the copycat.")
        out["entry"] = teaching(play).book.get("copycat")
        out["skill"] = play.life.skills.get("copycat")
        out["said"] = play.said()
    finally:
        await play.close()
    return play, out


async def explain(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 2600.0, 600.0)])
    out = {}
    try:
        await say(play, "Ina", "To do the evening round, you go to the kitchen, then go to the study, then come back to me.")
        out["entry"] = teaching(play).book.get("evening round")
        out["said_back"] = play.said()[-1]
        face(play, 2.4, 0.0, 0.0)
        before = len(play.life.commands.runner.history)
        await say(play, "Ina", "Do the evening round.")
        out["ran"] = [(a.kind, a.request.as_dict()) for a, e in play.life.commands.runner.history[before:]]
        await say(play, "Ina", "From now on, skip the study.")
        out["after"] = teaching(play).book.get("evening round")
        out["said"] = play.said()
    finally:
        await play.close()
    return play, out


async def show_me(root: Path, echo: bool) -> tuple:
    first = {"think": "a happy face and a turn", "steps": [{"do": "face", "expression": "happy"}, {"do": "turn", "way": "left", "degrees": 90}]}
    play, mind = await staged(root, echo, readings={"Do a little dance.": {"kind": "try_new", "text": "do a little dance"}}, plans=[first, first, first])
    out = {}
    try:
        await say(play, "Ina", "Do a little dance.")
        await say(play, "Ina", "No.")
        out["asked"] = play.said()[-1]
        await say(play, "Ina", "Yes, watch this.")
        out["lesson"] = teaching(play).session.name if teaching(play).session else None
        await say(play, "Ina", "Spin around.")
        await say(play, "Ina", "Turn right.")
        await say(play, "Ina", "That's it.")
        await say(play, "Ina", "Yes!")
        out["skill"] = play.life.skills.get("little dance")
        out["entry"] = teaching(play).book.get("little dance")
        out["draft"] = play.life.skills.drafted("little dance")
        out["said"] = play.said()
    finally:
        await play.close()
    return play, out


async def open_book(root: Path, echo: bool) -> tuple:
    from .book import Entry

    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1600.0, 900.0), Who("Mo", TRUSTED, 1600.0, -900.0), Who("Sam", CHILD, 500.0, 1600.0)])
    life = play.life
    out = {}
    try:
        await say(play, "Ina", "When I say boop, spin around.")
        await say(play, "Ina", "I'm going to teach you something.")
        await say(play, "Ina", "Turn left.")
        await say(play, "Ina", "That's it, call it the twirl.")
        await say(play, "Ina", "Yes!")
        await say(play, "Mo", "When I come home, turn around.")
        before = len(play.said())
        await say(play, "Ina", "What have I taught you?")
        await say(play, "Mo", "What do you know how to do?")
        await say(play, "Sam", "Forget the twirl.")
        out["asked"] = play.said()[before:]
        before = len(play.said())
        await say(play, "Ina", "Forget the twirl.")
        out["forgot"] = play.said()[before:]
        out["twirl"] = (teaching(play).book.get("twirl"), life.skills.get("twirl"))
        texts = []
        for path in life.p.store.root.joinpath("mine", "howto").rglob("*.json"):
            texts.append(path.read_text(encoding="utf-8"))
        out["stored"] = " ".join(texts)
        steps = [{"do": "request", "request": {"kind": "go_to_place", "place": "kitchen"}}, {"do": "turn", "way": "around", "degrees": 360}]
        ina = life.company.book.find("ina")
        for name, good in (("garden tour", 4), ("little garden tour", 1)):
            teaching(play).book.put(Entry(name, "procedure", steps=steps, good=good, taught_by={"id": ina.id, "name": "Ina", "tier": TRUSTED}))
        out["night"] = await teaching(play).night(play.local())
        out["merged"] = teaching(play).book.get("garden tour")
        mo = life.company.book.find("mo")
        out["way_before"] = [e.name for e in teaching(play).book.of_kind("way")]
        teaching(play).forget(mo.id, ["Mo"])
        out["way_after"] = [e.name for e in teaching(play).book.of_kind("way")]
        out["boop"] = teaching(play).book.get("boop")
    finally:
        await play.close()
    return play, out


TEACHING = {
    "open_book": open_book,
    "show_me": show_me,
    "twirl": twirl,
    "rooms_check": rooms_check,
    "question": question,
    "pad": pad,
    "lead": lead,
    "spot": spot,
    "messy": messy,
    "boop": boop,
    "doorbell": doorbell,
    "greet": greet,
    "copy_me": copy_me,
    "explain": explain,
}


async def play(name: str, root: Path | None = None, echo: bool = False):
    holder = None
    if root is None:
        holder = tempfile.TemporaryDirectory(prefix="pebble-teach-scene-", ignore_cleanup_errors=True)
        root = Path(holder.name) / "self"
    try:
        return await TEACHING[name](root, echo)
    finally:
        if holder is not None:
            holder.cleanup()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.teach.scene", description="Play a scripted teaching scene against the simulated body and print what happened")
    parser.add_argument("--scene", choices=sorted(TEACHING), default="twirl")
    args = parser.parse_args(argv)
    asyncio.run(play(args.scene, echo=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
