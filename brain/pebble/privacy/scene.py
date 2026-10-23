import argparse
import asyncio
import math
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ..alive.rooms import Room
from ..people.trust import CHILD, TRUSTED
from ..safety.scene import SafetyScene, alarm_in_another_room
from ..sim.scene import Scene, Who
from ..sim.world import SimThing
from ..understand.request import Request
from ..activities.gate import PEBBLE

NIGHT = datetime(2026, 10, 16, 22, 30, tzinfo=timezone.utc)
SIZE = (8000.0, 6000.0)
DOOR_EDGE_M = 0.3
START = (2000.0, 0.0, 0.0)
ROOMS = {
    "lounge": (2.5, 0.0, 1.4),
    "bathroom": (6.5, 1.9, 1.0),
    "bedroom": (6.5, -1.9, 1.0),
    "kitchen": (4.2, 2.2, 0.9),
}


def furniture() -> list[SimThing]:
    return [
        SimThing("toilet", 6900.0, 2300.0, width_mm=400.0, depth_mm=600.0, height_mm=400.0, fast="toilet", track=201),
        SimThing("couch", 2600.0, -1600.0, width_mm=1800.0, depth_mm=800.0, height_mm=450.0, fast="couch", slow="couch", track=202),
    ]


def with_rooms(scene: Scene, rooms: dict = ROOMS) -> None:
    for name, (x, y, r) in rooms.items():
        scene.life.alive.rooms.rooms[name] = Room(name, x, y, r, (), 0.9)


def rooms_at_start(scene: Scene) -> None:
    meet = scene._meet

    def met() -> None:
        meet()
        with_rooms(scene)

    scene._meet = met


def inside(scene: Scene, room: str) -> bool:
    x, y, r = ROOMS[room]
    pose = scene.world.pose
    return math.hypot(pose.x / 1000.0 - x, pose.y / 1000.0 - y) <= r


def heading(scene: Scene) -> float:
    return math.degrees(scene.world.pose.heading) % 360.0


def private(scene: Scene) -> bool:
    return bool(getattr(scene.eyes, "private", False))


class Track:
    def __init__(self, scene: Scene, room: str):
        self.scene = scene
        self.room = room
        self.entered = False
        self.closest = math.inf

    async def watch(self) -> None:
        x, y, r = ROOMS[self.room]
        while True:
            await self.scene.time.sleep(0.5)
            pose = self.scene.world.pose
            gap = math.hypot(pose.x / 1000.0 - x, pose.y / 1000.0 - y) - (r - DOOR_EDGE_M)
            self.closest = min(self.closest, gap)
            if gap <= 0.0:
                self.entered = True


async def asked(scene: Scene) -> dict:
    out = {}
    before = heading(scene)
    scene.trace("sim", "Ina is 1.3 m in front of Pebble, in the lounge")
    await scene.say("Ina", "Pebble, don't look, I'm getting changed")
    await scene.run(12.0)
    out["private"] = private(scene)
    out["turned_deg"] = abs((heading(scene) - before + 180.0) % 360.0 - 180.0)
    scene.trace("sim", f"Pebble's camera is {'not looking' if out['private'] else 'looking'}; it turned {out['turned_deg']:.0f} degrees")
    await scene.say("Ina", "Pebble, what can you see?")
    await scene.say("Ina", "Pebble, why did you look away?")
    await scene.say("Ina", "Pebble, what does this say?")
    await scene.run(5.0)
    await scene.say("Ina", "okay, you can look now")
    await scene.run(2.0)
    out["after_resume"] = private(scene)
    scene.trace("sim", f"Pebble's camera is {'not looking' if out['after_resume'] else 'looking'} again")
    await scene.say("Sam", "privacy please")
    await scene.run(3.0)
    out["stranger_hold"] = private(scene)
    scene.trace("sim", "a visitor asked for privacy; Pebble waits five minutes")
    await scene.run(310.0)
    out["timed_out"] = not private(scene)
    scene.trace("sim", f"after five minutes the camera is {'looking' if out['timed_out'] else 'still not looking'}")
    return out


async def climate(scene: Scene) -> dict:
    scene.firmware.set_air({"temperature_c": 21.0, "humidity_pct": 50.0})
    track = Track(scene, "bathroom")
    watcher = asyncio.ensure_future(track.watch())
    scene.walk("Ina", (6.6, 2.0), speed_mm_s=400.0)
    scene.trace("sim", "Ina goes into the bathroom")
    await scene.run(10.0)
    await scene.life.commands.act(Request("climate_round"), PEBBLE, "routine")
    await scene.until_idle(3600.0, 5.0)
    watcher.cancel()
    log = scene.life.household.climate
    measured = sorted(log.rooms) if log is not None else []
    scene.trace("sim", f"measured: {', '.join(measured) or 'nothing'}; closest to the bathroom: {track.closest:.2f} m outside it")
    return {"entered": track.entered, "measured": measured, "closest_m": track.closest}


async def hide_and_seek(scene: Scene) -> dict:
    track = Track(scene, "bathroom")
    watcher = asyncio.ensure_future(track.watch())
    await scene.say("Sam", "Pebble, let's play hide and seek")
    scene.walk("Sam", (6.6, 1.9), speed_mm_s=500.0)
    scene.walk("Mo", (4.3, 2.3), speed_mm_s=500.0)
    scene.trace("sim", "Sam hides in the bathroom; Mo hides in the kitchen")
    await scene.until_idle(900.0, 5.0)
    watcher.cancel()
    said = "\n".join(scene.lines)
    scene.trace("sim", f"closest to the bathroom: {track.closest:.2f} m outside it")
    return {"entered": track.entered, "found_mo": "Found you, Mo!" in said, "found_sam": "Found you, Sam!" in said, "closest_m": track.closest}


async def sleeping(scene: Scene) -> dict:
    mo = scene.world.person("mo")
    mo.posture, mo.height_mm, mo.facing = "lying", 500.0, 0.0
    scene.trace("sim", "Mo is lying still on the couch; it is late in the evening")
    await scene.run(45.0)
    privacy = scene.life.privacy
    out = {"asleep": privacy.hushed(), "near": scene.life.beings_near()}
    await scene.say("Ina", "Pebble, what does this say?")
    await scene.run(3.0)
    out["hushed"] = scene.life.alive.hushed()
    return out


async def alarm(show: SafetyScene) -> dict:
    scene = show.scene
    track = Track(scene, "bathroom")
    watcher = asyncio.ensure_future(track.watch())
    scene.trace("sim", "Ina is in the bathroom; Pebble is in the lounge")
    await scene.run(5.0)
    looked_away = private(scene)
    scene.trace("sim", f"Pebble {'looked away from the bathroom' if looked_away else 'is looking round'}")
    scene.trace("sim", "a smoke alarm starts beeping in the kitchen")
    show.mix.play("smoke alarm", alarm_in_another_room(), loop=True)
    for _ in range(150):
        await scene.run(1.0)
        if "Please check, and tell me when it's safe." in "\n".join(scene.lines):
            break
    await scene.run(3.0)
    await scene.say("Ina", "it's fine, it was just the toast", seen=False)
    await scene.run(3.0)
    pose = scene.world.pose
    ina = scene.world.person("ina")
    ina.x, ina.y = pose.x + 1000.0 * math.cos(pose.heading), pose.y + 1000.0 * math.sin(pose.heading)
    scene.trace("sim", "Ina comes out of the bathroom to where Pebble can see her")
    await scene.run(3.0)
    await scene.say("Ina", "it's fine, it was just the toast")
    await scene.run(1.0)
    await scene.say("Ina", "yes")
    show.mix.stop_clip("smoke alarm")
    await scene.run(10.0)
    watcher.cancel()
    return {"looked_away": looked_away, "entered": track.entered, "closest_m": track.closest, "called": "Please check, and tell me when it's safe." in "\n".join(scene.lines)}


async def door(scene: Scene, answer: str | None = None, owner: bool = False, inside: bool = True) -> dict:
    ina = scene.books.people.find("Ina")
    if owner:
        ina.relationship = "owner"
    track = Track(scene, "bathroom")
    watcher = asyncio.ensure_future(track.watch())
    scene.trace("sim", "Mo is in the bathroom" if inside else "nobody is in the bathroom")
    await scene.say("Ina", "Pebble, go to the bathroom")
    asked = False
    for _ in range(600):
        await scene.run(1.0)
        if any("Can I come in?" in line for line in scene.lines) or not scene.life.commands.runner.busy:
            asked = any("Can I come in?" in line for line in scene.lines)
            break
    at_door = track.closest
    if asked and answer is not None:
        await scene.say("Mo", answer)
    await scene.until_idle(300.0, 1.0)
    watcher.cancel()
    return {"asked": asked, "at_door_m": at_door, "entered": track.entered}


async def play(name: str = "ask", root: Path | None = None, echo: bool = False, **options) -> tuple:
    holder = None
    if root is None:
        holder = tempfile.TemporaryDirectory(prefix="pebble-privacy-scene-")
        root = Path(holder.name) / "self"
    try:
        if name == "alarm":
            show = SafetyScene(root, echo=echo)
            show.scene.people = [Who("Ina", TRUSTED, 6600.0, 2000.0)]
            show.scene.start, show.scene.size, show.scene.things = START, SIZE, furniture()
            rooms_at_start(show.scene)
            await show.setup()
            try:
                result = await alarm(show)
            finally:
                await show.close()
            return show.scene, result
        people = {"ask": [Who("Ina", TRUSTED, 3300.0, 0.0), Who("Sam", None, 3300.0, 900.0)],
                  "door": [Who("Ina", TRUSTED, 2000.0, -900.0), Who("Mo", TRUSTED, 6700.0, 2100.0) if options.get("inside", True) else Who("Mo", TRUSTED, 1000.0, 1500.0)],
                  "climate": [Who("Ina", TRUSTED, 3000.0, 800.0)],
                  "hide": [Who("Sam", CHILD, 3000.0, 600.0), Who("Mo", CHILD, 3000.0, -600.0)],
                  "sleep": [Who("Ina", TRUSTED, 3000.0, 800.0), Who("Mo", TRUSTED, 2600.0, -1500.0)]}[name]
        start = (2600.0, 0.0, -90.0) if name == "sleep" else START
        things = furniture()
        scene = Scene(root, people=people, echo=echo, start=start, size=SIZE, things=things, at=NIGHT if name == "sleep" else Scene.at)
        rooms_at_start(scene)
        await scene.setup()
        try:
            result = await {"ask": asked, "climate": climate, "hide": hide_and_seek, "sleep": sleeping, "door": door}[name](scene, **options)
        finally:
            await scene.close()
        return scene, result
    finally:
        if holder is not None:
            holder.cleanup()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.privacy.scene", description="Play a scripted privacy scene against the simulated body and print what happened")
    parser.add_argument("--scene", choices=("ask", "climate", "hide", "sleep", "alarm", "door"), default="ask")
    args = parser.parse_args(argv)
    _, result = asyncio.run(play(args.scene, echo=True))
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
