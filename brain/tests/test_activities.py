import json
import math
from datetime import datetime, timezone

import pytest
from conftest import run

from pebble.link.protocol import Event
from pebble.people.fake import fake_print
from pebble.people.trust import FRIEND, TRUSTED
from pebble.sim.scene import Scene, Who, play
from pebble.understand.request import Request
from pebble.understand.resolve import Reading


def gap(scene: Scene, name: str) -> float:
    person = scene.world.person(name.lower())
    pose = scene.world.pose
    return math.hypot(person.x - pose.x, person.y - pose.y) / 1000.0 - 0.1 - person.radius_mm / 1000.0


def said(scene: Scene) -> list[str]:
    return [line for line in scene.lines if " says " in line]


def thought(scene: Scene) -> list[str]:
    return [line for line in scene.lines if " thinks " in line]


async def staged(tmp_path, **options) -> Scene:
    scene = Scene(tmp_path / "self", **options)
    await scene.setup()
    return scene


def test_the_scripted_scene_follows_waits_comes_looks_and_goes_to_bed(tmp_path):
    scene = run(play("follow", tmp_path / "self"), timeout=120)
    text = "\n".join(scene.lines)
    assert "Okay, I'm right behind you." in text
    assert "Slowing down." in text
    assert "Okay, I'll wait here till you're back." in text
    assert "You're back!" in text
    assert "Here I am!" in text
    assert "Looking at you." in text
    assert "Home again." in text
    assert scene.world.docked()


def test_follow_keeps_its_distance_and_never_lets_the_deadman_fire(tmp_path):
    async def scenario():
        scene = await staged(tmp_path)
        events = scene.body.subscribe_events()
        await scene.say("Ina", "follow me")
        scene.walk("Ina", (2.4, 0.5), speed_mm_s=45.0)
        gaps = []
        for _ in range(12):
            await scene.run(5.0)
            gaps.append(gap(scene, "Ina"))
        await scene.run(20.0)
        settled = gap(scene, "Ina")
        names = []
        while not events.empty():
            message = events.get_nowait()
            if isinstance(message, Event):
                names.append(message.name)
        busy = scene.life.commands.runner.current
        await scene.close()
        return gaps, settled, names, busy

    gaps, settled, names, busy = run(scenario(), timeout=120)
    assert busy is not None and busy.kind == "follow"
    assert all(0.4 < g < 1.6 for g in gaps), gaps
    assert settled == pytest.approx(0.8, abs=0.2)
    assert "deadman" not in names and "bump" not in names


def test_follow_stops_looks_around_once_and_says_so_when_the_person_is_gone(tmp_path):
    async def scenario():
        scene = await staged(tmp_path)
        await scene.say("Ina", "shadow me")
        await scene.run(5.0)
        scene.leave("Ina")
        await scene.until_idle(90.0)
        command = list(scene.firmware.command)
        await scene.close()
        return scene, command

    scene, command = run(scenario(), timeout=120)
    assert "I lost you, so I'll stop here." in "\n".join(said(scene))
    assert any("looked around once" in line for line in thought(scene))
    assert command == [0, 0]


def test_come_turns_to_find_someone_behind_and_stops_about_half_a_metre_away(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, start=(2200.0, 0.0, 0.0), people=[Who("Ina", TRUSTED, 1000.0, 400.0)])
        await scene.say("Ina", "c'mere quick")
        await scene.until_idle(120.0)
        distance = gap(scene, "Ina")
        await scene.close()
        return scene, distance

    scene, distance = run(scenario(), timeout=120)
    assert "Here I am!" in "\n".join(said(scene))
    assert 0.35 < distance < 0.7


def test_go_to_bed_finds_the_tag_with_the_rear_camera_and_docks(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, start=(2000.0, 600.0, 40.0))
        switches = scene.eyes.switches
        await scene.say("Ina", "ok, off to bed with you")
        await scene.until_idle(240.0)
        await scene.run(1.0)
        camera = scene.eyes.camera()
        await scene.close()
        return scene, camera, scene.eyes.switches - switches

    scene, camera, switches = run(scenario(), timeout=120)
    assert scene.world.docked()
    assert camera == "front" and switches >= 2
    assert "Home again." in "\n".join(said(scene))


def test_far_from_a_charger_it_never_saw_it_gives_up_gracefully(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, start=(3000.0, 900.0, 0.0), knows_way=False)
        await scene.say("Ina", "go to bed")
        await scene.until_idle(240.0)
        camera = scene.eyes.camera()
        await scene.close()
        return scene, camera

    scene, camera = run(scenario(), timeout=120)
    assert not scene.world.docked() and camera == "front"
    assert "I can't get onto my charger by myself. Could someone put me on it?" in "\n".join(said(scene))
    assert any("could not see the charger's tag" in line for line in thought(scene))


def test_the_low_battery_routine_steers_home_by_the_tag(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, start=(1500.0, -400.0, 170.0), battery=12.0)
        await scene.run(1.0)
        await scene.until_idle(240.0)
        await scene.run(1.0)
        await scene.close()
        return scene

    scene = run(scenario(), timeout=120)
    assert "Heading to my charger." in "\n".join(said(scene))
    assert scene.world.docked()
    diary = scene.store.read_lines("diary.jsonl")
    assert any(entry["kind"] == "activity" and "headed home" in entry["text"] for entry in diary)


def test_back_off_reverses_at_most_twenty_centimetres_then_waits(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, start=(2000.0, 0.0, 0.0), people=[Who("Ina", TRUSTED, 2650.0, 0.0)])
        before = scene.world.pose.x
        await scene.say("Ina", "voetsek")
        await scene.run(15.0)
        moved = (before - scene.world.pose.x) / 1000.0
        current = scene.life.commands.runner.current
        await scene.close()
        return moved, current

    moved, current = run(scenario(), timeout=60)
    assert 0.12 < moved <= 0.21
    assert current is not None and current.kind == "wait"


def test_a_strangers_wait_runs_out_of_patience_quickly(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, people=[Who("Ina", None, 1300.0, 0.0)])
        await scene.say("Ina", "stay put")
        await scene.run(30.0)
        early = scene.life.commands.runner.current
        await scene.run(90.0)
        late = scene.life.commands.runner.current
        await scene.close()
        return scene, early, late

    scene, early, late = run(scenario(), timeout=60)
    assert early is not None and early.kind == "wait" and late is None
    assert any("ran out of patience" in line for line in thought(scene))


def test_stop_ends_the_walk_at_once_and_a_strangers_words_alone_cannot(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, people=[Who("Ina", TRUSTED, 1300.0, 0.0), Who("Rua", None, 600.0, -900.0)])
        await scene.say("Ina", "follow me")
        await scene.run(3.0)
        await scene.say("Rua", "quit following her")
        still = scene.life.commands.runner.current
        await scene.say("Rua", "stop!")
        ended = scene.life.commands.runner.current
        await scene.run(1.0)
        command = list(scene.firmware.command)
        await scene.close()
        return scene, still, ended, command

    scene, still, ended, command = run(scenario(), timeout=60)
    assert still is not None and still.kind == "follow"
    assert ended is None and command == [0, 0]
    assert any("Say stop if you need me to stop." in line for line in said(scene))
    assert any("said stop, so you stopped following Ina" in line for line in thought(scene))


def test_stop_in_the_same_breath_keeps_pebble_still(tmp_path):
    async def scenario():
        scene = await staged(tmp_path)
        await scene.say("Ina", "stop, come here")
        current = scene.life.commands.runner.current
        await scene.close()
        return scene, current

    scene, current = run(scenario(), timeout=60)
    assert current is None
    assert any("same breath" in line for line in thought(scene))


def test_a_name_an_unknown_voice_claims_counts_for_come_here_only(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, people=[Who("Ina", TRUSTED, 1300.0, 0.0), Who("Mo", FRIEND, 1300.0, 800.0)])
        await scene.run(2.0)
        await scene.say(None, "follow me")
        asked = scene.life.commands.pending
        await scene.say(None, "it's Ina")
        following = scene.life.commands.runner.current
        commands = scene.life.commands
        heard = scene.life.company.hear("it's Ina", None)
        reading = Reading(Request("come", who="me"), speaker="ina", source="rules", answered=True)
        commands.understanding.read = lambda text, ctx, _r=reading: _done(_r)
        await commands.consider(heard)
        coming = scene.life.commands.runner.current
        await scene.close()
        return scene, asked, following, coming

    scene, asked, following, coming = run(scenario(), timeout=60)
    assert asked is None and following is None
    assert "Sorry, I can't tell who's asking. Say it again where I can see you." in "\n".join(said(scene))
    assert coming is not None and coming.kind == "come" and coming.asker.label == "Ina" and not coming.asker.sure


async def _done(value):
    return value


def test_a_friend_is_told_no_to_follow_and_pebble_does_not_move(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, people=[Who("Mo", FRIEND, 1300.0, 0.0)])
        await scene.say("Mo", "tag along with me")
        await scene.run(3.0)
        current = scene.life.commands.runner.current
        x = scene.world.pose.x
        await scene.close()
        return scene, current, x

    scene, current, x = run(scenario(), timeout=60)
    assert current is None and x == pytest.approx(80.5, abs=1.0)
    assert "Sorry, I only follow people I know really well." in "\n".join(said(scene))


def test_without_eyes_it_says_so_and_still_waits_and_turns(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, blind=True, start=(2000.0, 0.0, 0.0))
        await scene.say("Ina", "follow me")
        heading = scene.world.pose.heading
        await scene.say("Ina", "turn left")
        await scene.until_idle(30.0)
        turned = math.degrees(scene.world.pose.heading - heading)
        await scene.say("Ina", "wait here")
        current = scene.life.commands.runner.current
        await scene.close()
        return scene, turned, current

    scene, turned, current = run(scenario(), timeout=60)
    assert "I can't see yet, so I can't follow you." in "\n".join(said(scene))
    assert turned == pytest.approx(90.0, abs=8.0)
    assert current is not None and current.kind == "wait"


def test_quiet_hours_keep_the_wheels_off(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, at=datetime(2026, 10, 15, 23, 0, tzinfo=timezone.utc))
        await scene.run(2.0)
        sent = scene.body.wheel_commands_sent
        await scene.say("Ina", "come here")
        await scene.run(5.0)
        current = scene.life.commands.runner.current
        await scene.close()
        return scene, current, scene.body.wheel_commands_sent - sent

    scene, current, sent = run(scenario(), timeout=60)
    assert current is None and sent == 0
    assert "It's my quiet time, so I'm staying put." in "\n".join(said(scene))


def test_while_busy_whims_wait_and_the_mind_gets_activity_tools(tmp_path):
    async def scenario():
        scene = await staged(tmp_path)
        seen = []
        original = scene.life.creative.maybe_whim
        scene.life.creative.maybe_whim = lambda ctx: seen.append(ctx.busy) or original(ctx)
        idle_tools = scene.life.tool_names(True)
        await scene.say("Ina", "look at me")
        await scene.run(3.0)
        busy_tools = scene.life.tool_names(True)
        guard = scene.life.commands.runner.busy_reason()
        await scene.close()
        return seen, idle_tools, busy_tools, guard

    seen, idle_tools, busy_tools, guard = run(scenario(), timeout=60)
    assert seen and seen[-1] is True
    assert "start_activity" in idle_tools and "end_activity" not in idle_tools
    assert "move" not in busy_tools and {"change_activity", "end_activity"} <= set(busy_tools)
    assert guard and "looking at Ina" in guard


def test_the_mind_can_start_change_and_end_activities_through_the_same_gate(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, people=[Who("Ina", TRUSTED, 1300.0, 0.0), Who("Rua", None, 900.0, 900.0)])
        registry = scene.life.p.turns.registry
        await scene.say("Ina", "hey Pebble, could you trail behind me round the house")
        outside = await registry.call("start_activity", {"kind": "follow", "asked_by": "Ina"})
        scene.life.company.asking = scene.life._asking(scene.clock.now())
        started = await registry.call("start_activity", {"kind": "follow", "asked_by": "Ina"})
        changed = await registry.call("change_activity", {"change": "slower", "asked_by": "Ina"})
        stranger = await registry.call("end_activity", {"asked_by": "the visitor p2"})
        unheard = await registry.call("start_activity", {"kind": "come", "asked_by": "Tui"})
        own = await registry.call("start_activity", {"kind": "follow", "person": "the visitor p2"})
        ended = await registry.call("end_activity", {})
        await scene.run(1.0)
        current = scene.life.commands.runner.current
        await scene.close()
        return outside, started, changed, stranger, unheard, own, ended, current

    outside, started, changed, stranger, unheard, own, ended, current = run(scenario(), timeout=60)
    assert not outside["ok"]
    assert started["ok"] and started["answer"] == "yes"
    assert changed["ok"]
    assert not stranger["ok"]
    assert not unheard["ok"]
    assert not own["ok"]
    assert ended["ok"] and current is None


def test_a_slow_model_never_holds_up_a_clear_request_and_its_late_answer_is_dropped(tmp_path):
    from pebble.mind.base import Mind, MindReply
    from pebble.understand.model import ModelReader
    from pebble.understand.understanding import Understanding

    class SlowMind(Mind):
        def __init__(self):
            self.pace = None

        async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
            await self.pace.sleep(4.0)
            return MindReply('{"kind":"come","who":"me"}')

    slow = SlowMind()

    async def scenario():
        scene = Scene(tmp_path / "self", understanding=Understanding(ModelReader([("subconscious", slow)])))
        await scene.setup()
        slow.pace = scene.time
        scene.trace("hears", "Ina: mumbling")
        scene.life.hear("mmh pebble yonder by the couch thing", None)
        await scene.time.settle()
        scene.life.hear("wait here", fake_print("ina", "voice"))
        await scene.time.run_until(scene.clock.monotonic() + 0.3)
        first = scene.life.commands.runner.current
        await scene.run(6.0)
        later = scene.life.commands.runner.current
        await scene.close()
        return scene, first, later

    scene, first, later = run(scenario(), timeout=60)
    assert first is not None and first.kind == "wait"
    assert later is not None and later.kind == "wait"
    kinds = [json.loads(line)["kind"] for line in scene.store.path("logs/blackbox.jsonl").read_text(encoding="utf-8").splitlines()]
    assert "superseded" in kinds


def test_requests_reach_the_mind_the_diary_and_the_black_box(tmp_path):
    async def scenario():
        scene = await staged(tmp_path)
        await scene.say("Ina", "follow me")
        await scene.run(3.0)
        await scene.say("Ina", "that's all, thanks")
        await scene.run(1.0)
        events = [item.text for item in scene.life.events.peek()]
        await scene.close()
        return scene, events

    scene, events = run(scenario(), timeout=60)
    assert any(text == "Ina asked you to follow them; you said yes" for text in events)
    assert any("were released from following Ina" in text for text in events)
    diary = scene.store.read_lines("diary.jsonl")
    assert any(entry["kind"] == "activity" and "followed Ina" in entry["text"] for entry in diary)
    kinds = [json.loads(line)["kind"] for line in scene.store.path("logs/blackbox.jsonl").read_text(encoding="utf-8").splitlines()]
    assert "request" in kinds and "activity_end" in kinds and "understood" in kinds
