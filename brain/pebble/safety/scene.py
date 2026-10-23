import argparse
import asyncio
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ..hearing import synth
from ..hearing.alarm import AlarmDetector
from ..hearing.service import Hearing
from ..hearing.sources import MixSource
from ..people.trust import TRUSTED
from ..sim.scene import Scene, Who, household
from .sounder import LogSounder
from .watch import Safety

NIGHT = datetime(2026, 10, 16, 2, 30, tzinfo=timezone.utc)
ROOM_NOISE_DB = -62.0


class SceneNotifier:
    enabled = True

    def __init__(self, trace):
        self.trace = trace
        self.sent = []

    def send(self, title: str, text: str) -> bool:
        self.sent.append((title, text))
        self.trace("notice", f"to the owner's phone: {text}")
        return True

    def info(self) -> dict:
        return {"kind": "scene", "sent": len(self.sent)}


def alarm_in_another_room() -> list[float]:
    return synth.muffle(synth.t3(1, level_db=-18.0, lead_s=0.0), wall_db=-18.0)


class SafetyScene:
    def __init__(self, root: Path, echo: bool = False, night: bool = False, notify: bool = True):
        self.scene = Scene(root, people=[Who("Ina", TRUSTED, 600.0, -1300.0)], echo=echo, things=household(), at=NIGHT if night else Scene.at)
        self.mix: MixSource | None = None
        self.safety: Safety | None = None
        self.notify = notify

    async def setup(self) -> None:
        scene = self.scene
        holder: dict = {}
        clock_ref = lambda: holder["clock"].monotonic()
        self.mix = MixSource(clock_ref, floor=synth.noise(7.0, ROOM_NOISE_DB, "pink", 3))
        hearing = Hearing(self.mix, lambda: holder["clock"].now(), detector=AlarmDetector("plain"))
        self.notifier = SceneNotifier(scene.trace)
        self.safety = Safety(scene_clock(holder), hearing, sounder=LogSounder(scene.trace), notifier=self.notifier if self.notify else None)
        scene.extra = {"safety": self.safety}
        original = scene.setup

        await self._setup(original, holder)

    async def _setup(self, original, holder) -> None:
        scene = self.scene
        task = asyncio.ensure_future(original())
        while not hasattr(scene, "clock"):
            await asyncio.sleep(0)
        holder["clock"] = scene.clock
        await task
        self.safety.attach(scene.life)
        self.mix.start()
        notes = scene.life.events.add

        def noted(at, text, major=False, kind=""):
            if text.startswith(("you noticed", "you are sure", "nobody said", "you found", "the shaking", "you think", "you could not", "Ina said it was fine", "someone said it was fine")) or "stood down" in text:
                scene.trace("thinks", text)
            return notes(at, text, major, kind)

        scene.life.events.add = noted

    async def close(self) -> None:
        if self.safety is not None:
            self.safety.close()
        await self.scene.close()


def scene_clock(holder: dict):
    class Proxy:
        def now(self):
            return holder["clock"].now()

        def monotonic(self):
            return holder["clock"].monotonic()

        def local(self, ts=None):
            return holder["clock"].local(ts)

    return Proxy()


async def smoke_in_another_room(play: SafetyScene) -> None:
    scene, mix = play.scene, play.mix
    scene.trace("sim", f"Ina is in the room, off to Pebble's right; Pebble sits by its charger, {scene.life.state.value}")
    await scene.run(3.0)
    scene.trace("sim", "a smoke alarm starts beeping in the kitchen next door (through a wall, under room noise)")
    mix.play("smoke alarm", alarm_in_another_room(), loop=True)
    for _ in range(120):
        await scene.run(1.0)
        if play.safety.ladder.incidents.get("fire") is not None and play.safety.ladder.incidents["fire"].found:
            break
    await scene.run(3.0)
    scene.trace("sim", f"Pebble's screen shows {scene.life.p.face.state.alarm or 'its face'}")
    await scene.say("Ina", "it's fine, it was just the toast")
    await scene.run(1.0)
    await scene.say("Ina", "yes, really")
    mix.stop_clip("smoke alarm")
    scene.trace("sim", "Ina waves the smoke away; the alarm stops")
    await scene.run(10.0)


async def smoke_with_nobody_home(play: SafetyScene) -> None:
    scene, mix = play.scene, play.mix
    scene.leave("Ina")
    await scene.run(3.0)
    scene.trace("sim", "a smoke alarm starts beeping in the kitchen next door; nobody is home")
    mix.play("smoke alarm", alarm_in_another_room(), loop=True)
    await scene.run(150.0)
    scene.trace("sim", "the smoke alarm stops by itself")
    mix.stop_clip("smoke alarm")
    await scene.run(200.0)


SCENES = {"smoke": smoke_in_another_room, "alone": smoke_with_nobody_home}


async def play(name: str = "smoke", root: Path | None = None, echo: bool = False, night: bool = False) -> SafetyScene:
    holder = None
    if root is None:
        holder = tempfile.TemporaryDirectory(prefix="pebble-safety-scene-")
        root = Path(holder.name) / "self"
    show = SafetyScene(root, echo=echo, night=night)
    try:
        await show.setup()
        await SCENES[name](show)
        pose = show.scene.world.pose
        show.scene.trace("sim", f"end: Pebble at ({pose.x / 1000:.2f}, {pose.y / 1000:.2f}) m")
    finally:
        await show.close()
        if holder is not None:
            holder.cleanup()
    return show


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.safety.scene", description="Play a scripted safety scene against the simulated body and print what happened")
    parser.add_argument("--scene", choices=sorted(SCENES), default="smoke")
    parser.add_argument("--night", action="store_true", help="play it at half past two in the morning, in quiet hours")
    parser.add_argument("--self", dest="self_dir", default=None, help="keep the self folder here (default: a temporary one)")
    args = parser.parse_args(argv)
    show = asyncio.run(play(args.scene, Path(args.self_dir) if args.self_dir else None, echo=True, night=args.night))
    return 0 if show.notifier.sent or not show.notify else 1


if __name__ == "__main__":
    sys.exit(main())
