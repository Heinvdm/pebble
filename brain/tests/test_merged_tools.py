import json
from datetime import date

import pytest
from conftest import run

from pebble.activities.tools import actions_of
from pebble.life.turn import NOT_NOW
from pebble.mind.scripted import Act, ScriptedMind
from pebble.people.trust import FRIEND, TRUSTED
from pebble.sim.scene import Scene, Who
from pebble.tools.broad import date_of, due_of, route_face, route_remember, route_self, route_status
from pebble.tools.registry import ToolArgError
from pebble.understand.request import Request, from_dict

OLD_BLOCK_CHARS = 16263


def test_dates_and_times_are_read_from_plain_words():
    assert date_of("12 March") == (3, 12, None)
    assert date_of("March 3rd, 2019") == (3, 3, 2019)
    assert date_of("the twelfth of March") == (3, 12, None)
    assert date_of("twenty-first of June") == (6, 21, None)
    assert date_of("2026-11-05") == (11, 5, 2026)
    assert date_of("next week") is None and date_of("March") is None
    assert date_of("tonight at seven") is None
    assert date_of("tonight at seven", date(2026, 10, 15)) == (10, 15, None)
    assert date_of("tomorrow", date(2026, 12, 31)) == (1, 1, None)
    assert due_of("18:00") == {"at": "18:00"}
    assert due_of("6pm") == {"at": "6:00 pm"}
    assert due_of("in 30 minutes") == {"minutes": 30.0}
    assert due_of("in an hour") == {"minutes": 60.0}
    assert due_of("tomorrow") == {"minutes": 1440}
    with pytest.raises(ToolArgError):
        due_of("some time")


def test_each_broad_call_maps_to_the_real_action_the_gatekeeper_knows():
    assert route_face({"expression": "happy", "tilt": 10}) == [("set_face", {"expression": "happy"}), ("look", {"degrees": 10})]
    assert route_face({"draw": "a dinosaur", "picture": "dino"})[0][0] == "draw_scene"
    assert route_face({"picture": "dino"})[0][0] == "show_scene"
    assert route_remember({"fact": "Ina likes cats", "about": "Ina"}) == [("remember", {"fact": "Ina likes cats", "about": "Ina"})]
    assert route_remember({"fact": "jazz", "kind": "like", "about": "Sam"}) == [("note_person", {"person": "Sam", "kind": "like", "text": "jazz"})]
    assert route_remember({"fact": "Lena", "kind": "name", "about": "Lena", "by": "Ina", "relationship": "friend"}) == [("introduce", {"by": "Ina", "name": "Lena", "who": "Lena", "relationship": "friend"})]
    assert route_remember({"fact": "Sam", "kind": "name", "about": "the visitor p2"})[0][0] == "note_person"
    promise = route_remember({"fact": "a new sticker", "kind": "promise", "about": "Ina", "when": "tomorrow"})
    assert promise == [("note_promise", {"person": "Ina", "who": "them", "what": "a new sticker", "minutes": 1440})]
    assert route_remember({"fact": "bring a new sticker tomorrow", "kind": "promise", "about": "Ina"})[0][1]["minutes"] == 1440
    assert route_remember({"fact": "tell a joke", "kind": "my_promise", "about": "Ina", "when": "18:00"})[0][1]["who"] == "me"
    with pytest.raises(ToolArgError):
        route_remember({"fact": "a sticker", "kind": "promise", "about": "Ina"})
    event = route_remember({"fact": "Sam's birthday", "kind": "birthday", "about": "Sam", "when": "the third of March"})
    assert event == [("add_event", {"title": "Sam's birthday", "month": 3, "day": 3, "kind": "birthday", "person": "Sam"})]
    assert route_remember({"fact": "was gentle with the cat", "kind": "impression", "about": "Tui", "quality": "kindness", "good": True})[0][0] == "note_impression"
    with pytest.raises(ToolArgError):
        route_remember({"fact": "Sam's birthday", "kind": "birthday", "when": "soon"})
    assert route_self({"action": "write", "name": "notes/a", "text": "hi"}) == [("mine", {"action": "write", "name": "notes/a", "text": "hi"})]
    assert route_self({"action": "wonder", "text": "why?"}) == [("wonder", {"action": "add", "text": "why?"})]
    assert route_self({"action": "forget", "person": "Mo", "kind": "memory", "name": "my job"})[0][0] == "request_forget"
    assert route_self({"action": "change", "person": "Ina", "kind": "personality", "name": "playful", "amount": 1})[0][0] == "request_change"
    assert route_self({"action": "standing", "person": "Ina"}) == [("my_standing", {"person": "Ina"})]
    assert route_self({"action": "tune", "name": "mood.resting", "text": "0.3"})[0][0] == "tune"
    assert [a for a, _ in route_status({})] == ["get_battery", "read_sensors", "list_tasks"]
    assert route_status({"task": 3, "mark": "done"}) == [("update_task", {"id": 3, "status": "done"})]


def test_a_do_reading_maps_every_step_and_anything_for_later_to_a_kept_action():
    chain = from_dict({"kind": "go_to_place", "place": "kitchen", "then": [{"kind": "turn", "way": "around"}, {"kind": "say_to", "who": "sam", "text": "dinner"}]})
    assert [a for a, _ in actions_of(chain)] == ["add_task", "start_activity", "move", "say"]
    assert [a for a, _ in actions_of(from_dict({"kind": "go_to_place", "place": "kitchen", "then": [{"kind": "turn", "way": "around"}]}))] == ["start_activity", "move"]
    later = from_dict({"kind": "say_to", "who": "me", "text": "stir the soup", "when": {"in_s": 300}})
    assert [a for a, _ in actions_of(later)] == ["add_task", "say"]
    assert actions_of(Request("adjust", change="slower"))[0][0] == "change_activity"
    assert actions_of(Request("release"))[0][0] == "end_activity"
    assert actions_of(Request("move", way="forward"))[0] == ("move", {"direction": "forward"})


def test_the_tool_block_is_steady_and_much_smaller(rig_factory):
    rig = rig_factory(model=None)
    block = rig.registry.schemas()
    assert len(json.dumps(block)) < OLD_BLOCK_CHARS / 3
    rig.turns.history.profile = rig.turns.history.profile.__class__.from_dict({"name": "steady", "context_tokens": 8192, "steady_tools": True})
    mind = ScriptedMind(acts=[Act("Hm.", ())])
    rig.turns.mind = mind
    run(rig.turns.run("Time: noon", ["set_face", "remember"], "adult", ""))
    run(rig.turns.run("Time: noon", ["set_face", "remember", "say", "add_task", "start_activity"], "adult", ""))
    first, second = [r for r in mind.requests if r["purpose"] == "turn"]
    assert first["tools"] == second["tools"] == ["do", "end", "say", "face", "remember", "recall", "self", "status", "stop"]
    assert NOT_NOW.format(names="do, end, say, recall, self, status, stop") in first["messages"][-1]["content"]
    assert NOT_NOW.format(names="end, recall, self, status, stop") in second["messages"][-1]["content"]


def test_the_minds_do_reads_plain_words_and_goes_through_the_same_gate(tmp_path):
    async def scenario():
        scene = Scene(tmp_path / "self", people=[Who("Ina", TRUSTED, 1300.0, 0.0), Who("Rua", None, 900.0, 900.0)])
        await scene.setup()
        registry = scene.life.p.turns.registry
        await scene.say("Ina", "hey Pebble, could you trail behind me round the house")
        outside = await registry.call("do", {"words": "follow me", "for": "Ina"})
        scene.life.company.asking = scene.life._asking(scene.clock.now())
        started = await registry.call("do", {"words": "follow me", "for": "Ina"})
        changed = await registry.call("do", {"words": "slow down", "for": "Ina"})
        stranger = await registry.call("do", {"words": "stop following", "for": "the visitor p2"})
        talk = await registry.call("do", {"words": "Ina likes jazz"})
        harm = await registry.call("do", {"words": "run over the cat"})
        later = await registry.call("do", {"words": "remind Ina at 7 to call Mo"})
        task = await registry.call("do", {"words": "Look at the wall by the dock", "done_when": "the front sensor reads under 300 mm", "hours": 2})
        ended = await registry.call("do", {"words": "stop following"})
        await scene.run(1.0)
        current = scene.life.commands.runner.current
        await scene.close()
        return outside, started, changed, stranger, talk, harm, later, task, ended, current

    outside, started, changed, stranger, talk, harm, later, task, ended, current = run(scenario(), timeout=60)
    assert not outside["ok"]
    assert started["ok"] and started["answer"] == "yes" and started["read_as"] == "follow them"
    assert changed["ok"]
    assert not stranger["ok"]
    assert not talk["ok"] and "use say" in talk["error"]
    assert not harm["ok"] and harm["law"] == 1 and harm["paused"]
    assert not later["ok"]
    assert task["ok"] and task["added"]["title"] == "Look at the wall by the dock"
    assert ended["ok"] and current is None


def test_a_life_turns_do_reads_as_background_work_that_gives_way(tmp_path):
    from pebble.mind.budget import READER, kind_of
    from pebble.mind.llama import BACKGROUND
    from pebble.understand.model import ModelReader

    async def scenario():
        scene = Scene(tmp_path / "self", people=[Who("Ina", TRUSTED, 1300.0, 0.0)])
        await scene.setup()
        heard = ScriptedMind()
        scene.life.commands.understanding.reader = ModelReader([("conscious", heard)])
        await scene.life.p.turns.registry.call("do", {"words": "go and do a little dance by the window"})
        await scene.close()
        return [r["purpose"] for r in heard.requests]

    purposes = run(scenario(), timeout=60)
    assert purposes == ["understand_quietly"]
    assert "understand_quietly" in BACKGROUND and kind_of("understand_quietly") == READER


async def asked(scene, who: str, words: str) -> None:
    await scene.say(who, words)
    scene.life.company.asking = scene.life._asking(scene.clock.now())


def test_end_finishes_a_follow_a_wait_or_a_look_for_whoever_may_end_it(tmp_path):
    async def scenario():
        scene = Scene(tmp_path / "self", people=[Who("Ina", TRUSTED, 1300.0, 0.0)])
        await scene.setup()
        registry = scene.life.p.turns.registry
        found = []
        for words in ("follow me", "wait here", "look at me"):
            await asked(scene, "Ina", "hey Pebble")
            started = await registry.call("do", {"words": words, "for": "Ina"})
            running = scene.life.commands.runner.current
            ended = await registry.call("end", {"for": "Ina"})
            await scene.run(0.5)
            found.append((started["ok"], running.kind if running else None, ended, scene.life.commands.runner.current))
        await scene.close()
        return found

    for (started, kind, ended, after), wanted in zip(run(scenario(), timeout=90), ("follow", "wait", "look")):
        assert started and kind == wanted
        assert ended["ok"] and ended["answer"] == "yes" and after is None


def test_end_is_refused_through_the_gate_and_the_gatekeeper_sees_end_activity(tmp_path):
    async def scenario():
        scene = Scene(tmp_path / "self", people=[Who("Ina", TRUSTED, 1300.0, 0.0), Who("Sam", FRIEND, 1500.0, 400.0)])
        await scene.setup()
        registry = scene.life.p.turns.registry
        seen = []
        check = registry.keeper.check
        registry.keeper.check = lambda name, args, caller="mind": seen.append(name) or check(name, args, caller)
        await asked(scene, "Ina", "hey Pebble")
        await registry.call("do", {"words": "follow me", "for": "Ina"})
        await asked(scene, "Sam", "hey Pebble")
        refused = await registry.call("end", {"for": "Sam"})
        still = scene.life.commands.runner.current
        await asked(scene, "Ina", "thanks Pebble")
        ended = await registry.call("end", {"for": "Ina"})
        await scene.close()
        return seen, refused, still, ended

    seen, refused, still, ended = run(scenario(), timeout=60)
    assert not refused["ok"] and refused["answer"] == "no" and "cannot end it" in refused["reason"]
    assert still is not None and still.kind == "follow"
    assert ended["ok"]
    assert seen.count("end_activity") == 2 and "end" not in seen


def test_stop_still_means_stop_all_motion_and_end_is_not_a_safety_stop(rig_factory):
    rig = rig_factory()
    stop, end = rig.registry.tool("stop"), rig.registry.tool("end")
    assert stop.acts == ("stop",) and end.acts == ("end_activity",)
    stopped = run(rig.registry.call("stop", {}, allowed=["stop"]))
    assert "stopped" in stopped and "refused_by" not in stopped
    assert run(rig.registry.call("end", {}, allowed=["stop"]))["error"] == "end activity is not something you can do just now"
    assert run(rig.registry.call("end", {}))["note"] == "you were not doing anything"
