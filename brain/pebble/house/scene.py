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
from ..people.trust import CHILD, TRUSTED
from ..safety.scene import ROOM_NOISE_DB, SceneNotifier, scene_clock
from ..safety.sounder import LogSounder
from ..safety.watch import Safety
from ..sim.scene import Scene, Who, household
from ..sim.sounds import ScriptedSounds
from ..sim.world import SimPerson
from .screen import TextLayer

DAY = datetime(2026, 10, 15, 11, 0, tzinfo=timezone.utc)
NIGHT = datetime(2026, 10, 16, 2, 30, tzinfo=timezone.utc)
WASHER = (1047, 1319, 1568, 2093, 1568, 1319, 1047, 1319)
DRYER = (784, 659, 523, 659, 784, 784, 784)


def tune(notes, level_db=-24.0):
    out = []
    for freq in notes:
        out += synth.gated([(0.25, True)], freq, level_db, harmonics=((2, 0.3), (3, 0.15)))
        out += synth.silence(0.08)
    return out


def chirp():
    return synth.gated([(0.08, True)], 3200.0, -34.0, harmonics=((2, 0.08),))


class HouseScene:
    def __init__(self, root: Path, people: list, at: datetime = DAY, echo: bool = False, quick: bool = False):
        self.scene = Scene(root, people=people, echo=echo, things=household(), at=at)
        self.quick = quick
        self.mix: MixSource | None = None
        self.sounds = ScriptedSounds()
        self.safety: Safety | None = None
        self.notifier = None

    @property
    def life(self):
        return self.scene.life

    @property
    def house(self):
        return self.scene.life.house

    def now(self) -> float:
        return self.scene.clock.monotonic()

    async def wait(self, seconds: float, quick: float) -> None:
        await self.scene.run(quick if self.quick else seconds)

    async def setup(self) -> None:
        scene = self.scene
        holder: dict = {}
        self.mix = MixSource(lambda: holder["clock"].monotonic(), floor=synth.noise(7.0, ROOM_NOISE_DB, "pink", 3))
        hearing = Hearing(self.mix, lambda: holder["clock"].now(), detector=AlarmDetector(), model=self.sounds)
        self.notifier = SceneNotifier(scene.trace)
        self.safety = Safety(scene_clock(holder), hearing, sounder=LogSounder(scene.trace), notifier=self.notifier)
        scene.extra = {"safety": self.safety}
        task = asyncio.ensure_future(scene.setup())
        while not hasattr(scene, "clock"):
            await asyncio.sleep(0)
        holder["clock"] = scene.clock
        await task
        self.safety.attach(scene.life)
        self.mix.start()
        house = scene.life.house
        house.layer = TextLayer(self._screen, scene.clock.monotonic)
        if self.quick:
            house.away.away_s = 300.0
        house.book["asked"][f"alarm_test:{scene.clock.local().strftime('%Y-%m')}"] = True
        note = scene.life.events.add

        def noted(at, text, major=False, kind=""):
            if any(word in text for word in ("knock", "cooking", "visitors", "alarm", "chirp", "kitchen", "told you", "you told")):
                scene.trace("thinks", text)
            return note(at, text, major, kind)

        scene.life.events.add = noted

    def _screen(self, event: str, data: dict) -> None:
        if data.get("op") == "show":
            code = f", with a code of {len(data['qr'])} x {len(data['qr'])} squares" if data.get("qr") else ""
            self.scene.trace("screen", f"{data.get('title')}: {', '.join(data.get('lines') or [])}{code}, for {round(float(data.get('hold') or 0))} s")
        elif data.get("op") == "badge":
            self.scene.trace("screen", f"small mark: {data.get('text') or 'gone'}")

    def sound(self, name: str, scores: dict, seconds: float) -> None:
        self.scene.trace("sim", f"sound: {name}")
        self.sounds.play(name, scores, self.now(), seconds)

    def audio(self, name: str, values: list[float], scores: dict | None = None) -> None:
        self.scene.trace("sim", f"sound: {name}")
        self.mix.play(name, values, at=self.now())
        if scores:
            self.sounds.play(name, scores, self.now(), len(values) / 16000.0)

    async def close(self) -> None:
        if self.safety is not None:
            self.safety.close()
        await self.scene.close()


async def door(play: HouseScene) -> None:
    scene = play.scene
    await scene.run(3.0)
    play.sound("a knock at the door", {"Knock": 0.6}, 1.5)
    await scene.run(4.0)
    await scene.say("Ina", "tell me when the microwave's done")
    play.sound("the microwave humming", {"Microwave oven": 0.5}, 30.0)
    await scene.run(31.0)
    play.sound("the microwave's beeps", {"Beep, bleep": 0.6}, 1.5)
    await scene.run(4.0)
    scene.leave("Ina")
    await scene.run(130.0)
    play.sound("a knock at the door", {"Knock": 0.6}, 1.5)
    await scene.run(60.0)
    play.sound("the doorbell", {"Doorbell": 0.7}, 1.5)
    await scene.run(30.0)
    scene.trace("sim", "the dog howls on and off for about three minutes")
    for _ in range(18):
        play.sounds.play("howl", {"Howl": 0.5}, play.now(), 4.0)
        await scene.run(10.0)
    await play.wait(1700.0, 150.0)
    scene.arrive("Ina", 1.3, 0.0)
    await scene.run(30.0)


async def night(play: HouseScene) -> None:
    scene = play.scene
    scene.leave("Ina")
    await scene.run(5.0)
    play.sound("one knock at the door", {"Knock": 0.7}, 1.5)
    await play.wait(600.0, 150.0)
    for gap in (30.0, 30.0, 5.0):
        play.sound("knocking at the door", {"Knock": 0.7}, 1.5)
        await scene.run(gap)


async def cooking(play: HouseScene) -> None:
    scene = play.scene
    scene.leave("Ina")
    scene.trace("sim", "a pan is sizzling in the kitchen and nobody is there")
    for _ in range(16 * 6):
        play.sounds.play("sizzle", {"Sizzle": 0.6, "Frying (food)": 0.4}, play.now(), 10.0)
        await scene.run(10.0)
    scene.arrive("Ina", 1.3, 0.0)
    await scene.run(3.0)
    await scene.say("Ina", "I'm watching it")
    for _ in range(4 * 6):
        play.sounds.play("sizzle", {"Sizzle": 0.6}, play.now(), 10.0)
        await scene.run(10.0)
    scene.trace("sim", "the cooking stops")
    await scene.run(300.0)


async def alarms(play: HouseScene) -> None:
    scene = play.scene
    await scene.run(2.0)
    await scene.say("Ina", "we're testing the smoke alarms")
    for freq in (3100.0, 3300.0, 2900.0):
        play.audio(f"a test press: the {freq / 1000:g} kHz alarm sounds for a few seconds", synth.t3(2, freq=freq, level_db=-24.0, lead_s=0.0))
        await scene.run(25.0)
    await scene.say("Ina", "we're done testing")
    await scene.run(5.0)
    scene.trace("sim", "an alarm with a low battery chirps every 40 seconds")
    for _ in range(3):
        play.audio("chirp", chirp())
        await scene.run(40.0 if _ < 2 else 6.0)
    await scene.say("Ina", "no thanks")
    await scene.run(30.0)


async def lists(play: HouseScene) -> None:
    scene = play.scene
    play.house.change_settings(None, wifi={"ssid": "Kahu guests", "password": "made-up-guest-pass", "security": "WPA"})
    await scene.run(2.0)
    await scene.say("Mo", "add milk and bread to the shopping list")
    await scene.say("Guest", "what's on the list?")
    await scene.say("Ina", "the water shut-off is under the laundry sink")
    await scene.say("Mo", "where's the water shut-off?")
    await scene.say("Ina", "I'm going to the shop")
    scene.trace("sim", "three people Pebble has never met come in")
    for index, (x, y) in enumerate(((1500.0, -600.0), (1700.0, 300.0), (1600.0, 700.0))):
        scene.world.people.append(SimPerson(f"guest{index}", x, y, track=40 + index))
    await scene.run(30.0)
    await scene.say("Ina", "yes")
    await scene.say("Guest", "what do you keep?")
    await scene.say("Guest", "what's the wifi password?")
    await scene.run(35.0)
    await scene.say("Ina", "the guests have gone")
    await scene.say("Ina", "is the light on?")


async def teach(play: HouseScene) -> None:
    scene = play.scene
    kind = {"Beep, bleep": 0.55, "Music": 0.3}
    await scene.run(2.0)
    play.audio("the washing machine's tune", tune(WASHER), kind)
    await scene.run(4.0)
    await scene.say("Ina", "that's the washing machine finishing")
    await play.wait(600.0, 130.0)
    play.audio("the washing machine's tune", tune(WASHER, -28.0), kind)
    await scene.run(4.0)
    await scene.say("Ina", "that's the washing machine finishing")
    await play.wait(600.0, 130.0)
    play.audio("the washing machine's tune", tune(WASHER, -30.0), kind)
    await scene.run(8.0)
    await play.wait(300.0, 10.0)
    play.audio("the dryer's tune", tune(DRYER), kind)
    await scene.run(8.0)
    await scene.say("Ina", "what sounds do you know?")


SCENES = {
    "door": (door, DAY, [Who("Ina", TRUSTED, 1300.0, 0.0)]),
    "night": (night, NIGHT, [Who("Ina", TRUSTED, 1300.0, 0.0)]),
    "cooking": (cooking, DAY, [Who("Ina", TRUSTED, 1300.0, 0.0)]),
    "alarms": (alarms, DAY, [Who("Ina", TRUSTED, 1300.0, 0.0)]),
    "lists": (lists, DAY, [Who("Ina", TRUSTED, 1300.0, 0.0), Who("Mo", CHILD, 1500.0, -400.0)]),
    "teach": (teach, DAY, [Who("Ina", TRUSTED, 1300.0, 0.0)]),
}


async def play(name: str = "door", root: Path | None = None, echo: bool = False, quick: bool = False) -> HouseScene:
    holder = None
    if root is None:
        holder = tempfile.TemporaryDirectory(prefix="pebble-house-scene-")
        root = Path(holder.name) / "self"
    script, at, people = SCENES[name]
    show = HouseScene(root, people, at=at, echo=echo, quick=quick)
    try:
        await show.setup()
        await script(show)
    finally:
        await show.close()
        if holder is not None:
            holder.cleanup()
    return show


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.house.scene", description="Play a scripted household scene against the simulated body and print what happened")
    parser.add_argument("--scene", choices=sorted(SCENES), default="door")
    parser.add_argument("--self", dest="self_dir", default=None, help="keep the self folder here (default: a temporary one)")
    args = parser.parse_args(argv)
    asyncio.run(play(args.scene, Path(args.self_dir) if args.self_dir else None, echo=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
