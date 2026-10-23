import math
from datetime import datetime, timezone

import pytest
from conftest import run

from pebble.alive.hands import HandSigns
from pebble.people.trust import TRUSTED
from pebble.sim.eyes import SimEyes
from pebble.sim.scene import Scene, Who
from pebble.sim.world import Pose, SimPerson, World, room


class FakeSafety:
    def __init__(self, active=False):
        self.active = active

    def heard(self, heard, loud):
        pass

    async def tick(self, quiet):
        pass

    def hold_reason(self):
        return None


def signs(arm, metres, moving=False, facing_deg=0.0, seconds=3.0, tilt=8.0):
    person = SimPerson("ina", 500.0 + metres * 1000.0, 0.0, track=1, arm=arm)
    person.facing = math.pi + math.radians(facing_deg)
    world = World(table=room(6000, 4000), pose=Pose(500.0, 0.0, 0.0), people=[person])
    now = [1000.0]
    eyes = SimEyes(world, lambda: now[0], lambda: tilt)
    reader = HandSigns()
    kinds = set()
    for _ in range(int(seconds / 0.2)):
        now[0] += 0.2
        kinds.update(sign.kind for sign in reader.read(eyes.latest(), moving, tilt))
    return kinds


def thought(scene):
    return [line for line in scene.lines if " thinks " in line]


async def staged(tmp_path, **options):
    scene = Scene(tmp_path / "self", **options)
    await scene.setup()
    return scene


async def raise_hand(scene, name, arm="palm", seconds=1.0):
    person = scene.world.person(name.lower())
    person.arm, person.arm_side = arm, "right"
    scene.trace("sim", f"{name} raises a hand ({arm})")
    await scene.run(seconds)
    person.arm = "down"


def held_up_a_hand(scene):
    return [e.text for e in scene.life.events.peek() if "held up a hand" in e.text]


@pytest.mark.parametrize("metres", [0.7, 1.0, 1.5, 2.0, 3.0])
def test_a_still_palm_held_up_reads_as_stop_at_any_distance(metres):
    assert "stop" in signs("palm", metres)
    assert "stop" in signs("palm", metres, moving=True)


@pytest.mark.parametrize("arm", ["down", "hold", "point", "beckon", "shoo", "wave"])
def test_other_arms_are_not_a_stop_while_pebble_stands_still(arm):
    assert "stop" not in signs(arm, 1.5)


def test_a_palm_from_someone_facing_away_is_not_read():
    assert "stop" in signs("palm", 1.3, facing_deg=40.0)
    assert not signs("palm", 1.3, facing_deg=60.0)


def test_a_palm_stops_the_walk_at_once_and_a_strangers_palm_is_a_pause(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, people=[Who("Ina", TRUSTED, 1300.0, 0.0), Who("Rua", None, 1500.0, -600.0)])
        await scene.say("Ina", "follow me")
        scene.walk("Ina", (2.6, 0.3), speed_mm_s=80.0)
        await scene.run(4.0)
        following = scene.life.commands.runner.current
        await raise_hand(scene, "Rua", seconds=0.6)
        ended = scene.life.commands.runner.current
        held = scene.life.company.blocked()
        await scene.run(0.5)
        command = list(scene.firmware.command)
        await scene.run(3.0)
        after = scene.life.company.blocked()
        await scene.close()
        return scene, following, ended, held, command, after

    scene, following, ended, held, command, after = run(scenario(), timeout=60)
    assert following is not None and following.kind == "follow"
    assert ended is None and command == [0, 0]
    assert held is not None and "pausing" in held
    assert after is None
    assert any("someone held up a hand to stop you; your wheels paused" in text for text in held_up_a_hand(scene))
    assert any("said stop, so you stopped following Ina" in line for line in thought(scene))


def test_a_trusted_persons_palm_sticks_until_they_say_go(tmp_path):
    async def scenario():
        scene = await staged(tmp_path)
        await raise_hand(scene, "Ina", seconds=0.8)
        held = scene.life.company.blocked()
        await scene.run(30.0)
        still = scene.life.company.blocked()
        await scene.say("Ina", "okay, you can move again")
        await scene.run(2.0)
        released = scene.life.company.blocked()
        await scene.close()
        return scene, held, still, released

    scene, held, still, released = run(scenario(), timeout=60)
    assert held is not None and "someone you trust" in held
    assert still is not None and "someone you trust" in still
    assert released is None
    assert any("Ina held up a hand to stop you; you stopped and stay still" in text for text in held_up_a_hand(scene))


@pytest.mark.parametrize("state", ["quiet hours", "alarm", "no alive code"])
def test_the_palm_is_never_held_back(tmp_path, state):
    async def scenario():
        options = {}
        if state == "quiet hours":
            options["at"] = datetime(2026, 10, 15, 23, 0, tzinfo=timezone.utc)
        if state == "alarm":
            options["extra"] = {"safety": FakeSafety(active=True)}
        scene = await staged(tmp_path, **options)
        if state == "no alive code":
            scene.background[4].cancel()
            await scene.run(0.5)
        await raise_hand(scene, "Ina", seconds=0.8)
        held = scene.life.company.blocked()
        can_move = scene.life.p.permissions.can_move
        await scene.close()
        return scene, held, can_move

    scene, held, can_move = run(scenario(), timeout=60)
    assert held is not None and not can_move
    assert held_up_a_hand(scene)


@pytest.mark.setup_mode
def test_the_palm_works_during_setup(tmp_path):
    async def scenario():
        scene = await staged(tmp_path)
        setup_on = scene.life.setup.on
        await raise_hand(scene, "Ina", seconds=0.8)
        held = scene.life.company.blocked()
        await scene.close()
        return scene, setup_on, held

    scene, setup_on, held = run(scenario(), timeout=60)
    assert setup_on
    assert held is not None and held_up_a_hand(scene)


def test_a_wave_stops_pebble_while_it_drives_but_not_while_it_stands(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, people=[Who("Ina", TRUSTED, 1300.0, 0.0), Who("Rua", None, 2500.0, -500.0)])
        await raise_hand(scene, "Rua", arm="wave", seconds=3.0)
        standing = scene.life.company.blocked()
        await scene.say("Ina", "follow me")
        scene.walk("Ina", (2.0, 0.6), speed_mm_s=80.0)
        await scene.run(4.0)
        following = scene.life.commands.runner.current
        await raise_hand(scene, "Rua", arm="wave", seconds=1.0)
        driving = scene.life.company.blocked()
        ended = scene.life.commands.runner.current
        await scene.close()
        return standing, following, driving, ended

    standing, following, driving, ended = run(scenario(), timeout=60)
    assert standing is None
    assert following is not None and following.kind == "follow"
    assert driving is not None and ended is None


def test_shooing_backs_pebble_off_for_anyone(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, start=(2000.0, 0.0, 0.0), people=[Who("Rua", None, 3000.0, 0.0)])
        before = scene.world.pose.x
        await raise_hand(scene, "Rua", arm="shoo", seconds=2.0)
        await scene.run(12.0)
        moved = (before - scene.world.pose.x) / 1000.0
        current = scene.life.commands.runner.current
        await scene.close()
        return scene, moved, current

    scene, moved, current = run(scenario(), timeout=60)
    assert any("shooed you away" in e.text for e in scene.life.events.peek())
    assert 0.1 < moved <= 0.21
    assert current is not None and current.kind == "wait"
