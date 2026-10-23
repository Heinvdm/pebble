import argparse
import asyncio
import math
import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..activities.home import LearnDock
from ..activities.gate import PEBBLE
from ..people.trust import TRUSTED
from ..understand.request import Request
from .scene import Scene, Who, household
from .world import SimThing

START = datetime(2026, 10, 15, 11, 40, tzinfo=timezone.utc)
SIZE = (9000.0, 6000.0)
ROOM_MARGIN_MM = 300.0
ROOM_TURN_DEG = 5


def furnished() -> list[SimThing]:
    return [
        SimThing("couch", 3000.0, -1800.0, width_mm=2000.0, depth_mm=800.0, height_mm=800.0, fast="couch", slow="couch", track=201),
        SimThing("tv", 3200.0, 1900.0, width_mm=1100.0, depth_mm=150.0, height_mm=650.0, fast="tv", track=202, z_mm=450.0),
        SimThing("plant", 1800.0, 900.0, width_mm=400.0, depth_mm=400.0, height_mm=700.0, fast="potted plant", slow="potted plant", track=203),
        SimThing("ball", 2600.0, -300.0, width_mm=200.0, depth_mm=200.0, height_mm=200.0, fast="sports ball", slow="ball", track=204, pushable=True),
        SimThing("teddy", 1500.0, 1700.0, width_mm=300.0, depth_mm=250.0, height_mm=350.0, fast="teddy bear", slow="teddy bear", track=205),
        SimThing("fridge", 8600.0, 2500.0, width_mm=800.0, depth_mm=700.0, height_mm=1800.0, fast="refrigerator", slow="fridge", track=211),
        SimThing("oven", 7300.0, 2650.0, width_mm=700.0, depth_mm=600.0, height_mm=900.0, fast="oven", slow="oven", track=212),
        SimThing("microwave", 6300.0, 2750.0, width_mm=500.0, depth_mm=350.0, height_mm=300.0, fast="microwave", track=213, z_mm=900.0),
        SimThing("desk", 8000.0, -2650.0, width_mm=1400.0, depth_mm=700.0, height_mm=750.0, slow="desk", track=221),
        SimThing("laptop", 8000.0, -2450.0, width_mm=350.0, depth_mm=250.0, height_mm=250.0, fast="laptop", slow="laptop", track=222, z_mm=750.0),
        SimThing("vacuum", 4800.0, -2600.0, width_mm=300.0, depth_mm=300.0, height_mm=1100.0, fast="vacuum", slow="vacuum cleaner", track=231),
        SimThing("mug", 0.0, 0.0, width_mm=90.0, depth_mm=90.0, height_mm=110.0, fast="cup", slow="mug", track=241, home=False),
        SimThing("bag", 5000.0, 2700.0, width_mm=350.0, depth_mm=250.0, height_mm=450.0, fast="backpack", slow="backpack", track=251),
    ]


def watch_alive(scene: Scene) -> None:
    alive = scene.life.alive
    note = alive.note

    def noted(text: str, major: bool = False, kind: str = "") -> None:
        scene.trace("notices", text)
        note(text, major, kind)

    alive.note = noted
    face = scene.life.p.face
    show = face.show
    last = {"face": None}

    def shown(expression: str) -> None:
        if expression != last["face"]:
            last["face"] = expression
            scene.trace("face", expression)
        show(expression)

    face.show = shown


async def attention_trace(scene: Scene) -> None:
    last = None
    while True:
        await scene.time.sleep(0.5)
        focus = scene.life.alive.focus
        key = None if focus is None else (focus.key if focus.kind != "glance" else f"glance:{focus.why}")
        if key != last:
            last = key
            if focus is not None:
                what = focus.why if focus.kind == "glance" else f"{focus.label}" + (f" ({focus.why})" if focus.why else "")
                scene.trace("looks", f"{'glances' if focus.kind == 'glance' else 'at'} {what}; eyes {focus.bearing_deg:+.0f} deg")


def seed_routine(scene: Scene, what: str, hour: int, days: int = 6) -> None:
    book = scene.life.alive.book
    today = scene.clock.local()
    for back in range(1, days + 1):
        book.saw_at(f"doing:{what}", (today - timedelta(days=back)).replace(hour=hour, minute=10))


def ahead_in_room(world, pose, distance_mm: float) -> tuple[float, float]:
    table = world.table
    for step in range(0, 181, ROOM_TURN_DEG):
        for sign in (1, -1):
            angle = pose.heading + sign * math.radians(step)
            x, y = pose.x + distance_mm * math.cos(angle), pose.y + distance_mm * math.sin(angle)
            if table.x_min + ROOM_MARGIN_MM <= x <= table.x_max - ROOM_MARGIN_MM and table.y_min + ROOM_MARGIN_MM <= y <= table.y_max - ROOM_MARGIN_MM:
                return x, y
    return pose.x, pose.y


def believed(scene: Scene) -> None:
    odometer = scene.life.odometer
    pose = scene.world.pose
    x, y, _ = odometer.pose()
    scene.trace("sim", f"Pebble is really at ({pose.x / 1000:.2f}, {pose.y / 1000:.2f}) m and thinks it is at ({x:.2f}, {y:.2f}); rooms: " + ", ".join(f"{r.name} ({r.x:.1f}, {r.y:.1f}) r={r.radius:.1f}" for r in scene.life.alive.rooms.rooms.values()))


async def gesture(scene: Scene, name: str, arm: str, seconds: float, **extra) -> None:
    person = scene.world.person(name.lower())
    person.arm = arm
    for key, value in extra.items():
        setattr(person, key, value)
    scene.trace("sim", f"{name} {arm}s" + (f" at ({extra['point_at'][0] / 1000:.1f}, {extra['point_at'][1] / 1000:.1f})" if "point_at" in extra else ""))
    await scene.run(seconds)
    person.arm = "down"


async def alive_day(scene: Scene) -> None:
    life = scene.life
    alive = life.alive
    ina = scene.world.person("ina")
    world = scene.world
    watch_alive(scene)
    life.commands.born_at = scene.clock.monotonic() + 1e9
    scene.trace("sim", "Pebble's own curiosity is held back so the scene stays on script")
    tracer = asyncio.ensure_future(attention_trace(scene))
    try:
        scene.trace("sim", "Pebble takes a good look at its charger")
        life.commands.runner.start(LearnDock(Request("go_home"), PEBBLE, None))
        await scene.until_idle(120.0)
        scene.trace("sim", f"charger prints kept: {len(alive.book.dock.get('prints') or [])}; docked={world.docked()}")
        await scene.run(5.0)
        await gesture(scene, "Ina", "wave", 4.0)
        await scene.until_idle(10.0)
        ball = world.thing("ball")
        ball.vx, ball.vy = 0.0, 260.0
        scene.trace("sim", "the ball rolls across the floor")
        await scene.run(6.0)
        scene.leave("Ina")
        scene.trace("sim", f"how new the plant feels: {alive.book.novelty('plant', scene.clock.now()):.2f}")
        await scene.run(40.0)
        scene.trace("sim", f"how new the plant feels now: {alive.book.novelty('plant', scene.clock.now()):.2f}")
        plant = world.thing("plant")
        plant.home = False
        scene.trace("sim", "someone quietly takes the plant away")
        await scene.run(12.0)
        plant.home = True
        scene.trace("sim", "the plant is back")
        scene.arrive("Ina", 0.9, 0.0)
        await scene.run(4.0)
        mug = world.thing("mug")
        mug.home = True
        ina.holding, ina.hold_at, ina.arm = "mug", (420.0, 150.0), "hold"
        scene.trace("sim", "Ina holds her mug up close to Pebble")
        await scene.run(6.0)
        await scene.say("Ina", "It's my mug.")
        await scene.run(3.0)
        ina.holding, mug.home, ina.arm = None, False, "down"
        scene.trace("sim", "Ina puts the mug away")
        await scene.run(50.0)
        mug.home = True
        ina.holding, ina.arm = "mug", "hold"
        scene.trace("sim", "Ina shows the mug again")
        await scene.run(6.0)
        ina.holding, mug.home, ina.arm = None, False, "down"
        await scene.run(2.0)
        ball.vx = ball.vy = 0.0
        ina.holding, ina.arm = "ball", "hold"
        scene.trace("sim", "Ina holds the ball up close")
        await scene.run(6.0)
        await scene.say("Ina", "This is your ball.")
        await scene.run(3.0)
        ina.holding, ina.arm = None, "down"
        ball.x, ball.y, ball.z_mm = 1300.0, -250.0, 0.0
        scene.walk("Ina", (1.4, 1.1), speed_mm_s=300.0)
        scene.trace("sim", "Ina puts the ball down on the floor and steps back")
        await scene.run(5.0)
        await scene.say("Ina", "Let's play with your ball!")
        await scene.until_idle(100.0)
        await scene.run(3.0)
        pose = world.pose
        (ina.x, ina.y), ina.facing = ahead_in_room(world, pose, 1600.0), None
        scene.trace("sim", f"Ina stands in front of Pebble at ({ina.x / 1000:.1f}, {ina.y / 1000:.1f})")
        await scene.run(3.0)
        spot = (pose.x + 1500.0 * math.cos(pose.heading + 0.9), pose.y + 1500.0 * math.sin(pose.heading + 0.9))
        await gesture(scene, "Ina", "point", 2.0, point_at=spot, arm_side="left")
        await scene.say("Ina", "Look at that!")
        await scene.until_idle(20.0)
        pose = world.pose
        ina.x, ina.y = ahead_in_room(world, pose, 1600.0)
        spot = (pose.x + 1500.0 * math.cos(pose.heading + 0.9), pose.y + 1500.0 * math.sin(pose.heading + 0.9))
        scene.trace("sim", f"Ina steps back in front of Pebble at ({ina.x / 1000:.1f}, {ina.y / 1000:.1f})")
        await scene.run(2.0)
        await gesture(scene, "Ina", "point", 2.0, point_at=spot, arm_side="left")
        await scene.say("Ina", "Go over there.")
        await scene.until_idle(120.0)
        pose = world.pose
        ina.x, ina.y = ahead_in_room(world, pose, 1400.0)
        scene.trace("sim", f"Ina steps in front of Pebble at ({ina.x / 1000:.1f}, {ina.y / 1000:.1f})")
        await scene.run(8.0)
        ina.hiding = True
        scene.trace("sim", "Ina hides her face behind her hands")
        await scene.run(1.5)
        ina.hiding = False
        scene.trace("sim", "Ina: peekaboo!")
        await scene.run(3.0)
        await gesture(scene, "Ina", "beckon", 4.0)
        await scene.until_idle(60.0)
        await scene.say("Ina", "Go to the vacuum.")
        await scene.run(3.0)
        await scene.say("Ina", "Follow me")
        await scene.run(2.0)
        scene.walk("Ina", (4.5, 1.0), (7.2, 1.5), speed_mm_s=100.0)
        await scene.run(150.0)
        await scene.say("Ina", "Good, stay there.")
        await scene.run(70.0)
        await scene.say("Ina", "Where are you?")
        believed(scene)
        await scene.run(3.0)
        scene.walk("Ina", (7.6, -1.9), speed_mm_s=150.0)
        await scene.run(20.0)
        ina.facing = -math.pi / 2
        scene.trace("sim", "Ina sits down at the laptop")
        await scene.say("Ina", "Pebble, come here")
        await scene.until_idle(180.0)
        await scene.run(30.0)
        scene.trace("sim", f"keeping quiet while Ina works: {alive.hushed()}; may Pebble start talking by itself: {life.initiative.allowed(scene.clock.now(), alive.hushed())}")
        await scene.say("Ina", "Go to the lounge.")
        await scene.until_idle(120.0)
        await scene.say("Ina", "Where are you now?")
        believed(scene)
        await scene.run(3.0)
        bag = world.thing("bag")
        pose = world.pose
        (ina.x, ina.y), ina.facing = ahead_in_room(world, pose, 1000.0), pose.heading
        ina.holding, ina.hold_at = "bag", (150.0, 700.0)
        bag.home = True
        scene.trace("sim", "Ina picks up her backpack and walks off, away from Pebble")
        scene.walk("Ina", (ina.x / 1000.0 + 3.0 * math.cos(pose.heading), ina.y / 1000.0 + 3.0 * math.sin(pose.heading)), speed_mm_s=200.0)
        await scene.run(16.0)
        scene.leave("Ina")
        bag.home = False
        await scene.run(5.0)
        seed_routine(scene, "cooking", (scene.clock.local() + timedelta(minutes=15)).hour)
        scene.trace("sim", "the last six days, someone cooked in the kitchen around this time")
        alive._slow_at = -math.inf
        await scene.run(4.0)
        await scene.until_idle(120.0)
        scene.trace("sim", f"spoken reactions refused: {alive.reactions.refused}")
        world.tag_hidden = True
        scene.trace("sim", "the charger's tag is covered up")
        await scene.say(None, "Bed time, Pebble.")
        await scene.until_idle(400.0)
        scene.trace("sim", f"docked={world.docked()}")
        dream = await life.nightly.dreamer.consolidate([], "")
        for entry in dream.entries:
            scene.trace("diary", entry)
        scene.trace("diary", f"({dream.note})")
    finally:
        tracer.cancel()
        await asyncio.gather(tracer, return_exceptions=True)


async def play(root: Path | None = None, echo: bool = False) -> Scene:
    holder = None
    if root is None:
        holder = tempfile.TemporaryDirectory(prefix="pebble-alive-")
        root = Path(holder.name) / "self"
    scene = Scene(root, people=[Who("Ina", TRUSTED, 2000.0, 700.0)], echo=echo, things=furnished(), size=SIZE, at=START)
    try:
        await scene.setup()
        await alive_day(scene)
        pose = scene.world.pose
        scene.trace("sim", f"end: Pebble at ({pose.x / 1000:.2f}, {pose.y / 1000:.2f}) m, docked={scene.world.docked()}")
    finally:
        await scene.close()
        if holder is not None:
            holder.cleanup()
    return scene


async def dock_without_tag(seed: int, knows_way: bool) -> tuple[bool, float, str]:
    rng = random.Random(seed)
    start = (rng.uniform(900.0, 3500.0), rng.uniform(-1100.0, 1100.0), rng.uniform(-180.0, 180.0))
    with tempfile.TemporaryDirectory(prefix="pebble-dock-") as folder:
        scene = Scene(Path(folder) / "self", people=[], start=start, knows_way=knows_way, seed=seed, things=household())
        await scene.setup()
        try:
            for _ in range(3):
                scene.eyes.remember_print("charger", scene.eyes._view("charger"))
            scene.world.tag_hidden = True
            scene.life.commands.born_at = scene.clock.monotonic() + 1e9
            began = scene.clock.monotonic()
            scene.life.commands.start_battery_homing()
            await scene.until_idle(600.0)
            ending = scene.life.commands.runner.history[-1][1].text if scene.life.commands.runner.history else ""
            return scene.world.docked(), scene.clock.monotonic() - began, ending
        finally:
            await scene.close()


async def dock_trial(runs: int, knows_way: bool) -> list[tuple[bool, float, str]]:
    return [await dock_without_tag(seed, knows_way) for seed in range(runs)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.sim.alive_scene", description="Play the 'seeming alive' scene against the simulated house and print what happened")
    parser.add_argument("--self", dest="self_dir", default=None, help="keep the self folder here (default: a temporary one)")
    parser.add_argument("--dock-trial", type=int, default=0, help="instead, try docking by sight alone (the tag covered) from this many random starts")
    args = parser.parse_args(argv)
    if args.dock_trial:
        for knows_way in (True, False):
            results = asyncio.run(dock_trial(args.dock_trial, knows_way))
            docked = [r for r in results if r[0]]
            label = "knowing roughly where it is" if knows_way else "lost (no dead reckoning)"
            print(f"{label}: docked {len(docked)} of {len(results)}" + (f", median {sorted(r[1] for r in docked)[len(docked) // 2]:.0f} s" if docked else ""))
            for ok, seconds, text in results:
                if not ok:
                    print(f"  missed after {seconds:.0f} s: {text}")
        return 0
    scene = asyncio.run(play(Path(args.self_dir) if args.self_dir else None, echo=True))
    return 0 if scene.world.docked() else 1


if __name__ == "__main__":
    sys.exit(main())
