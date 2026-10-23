import json

from conftest import run

from pebble.life.states import LifeState
from pebble.mind.prompt import PRIVATE_MASK
from pebble.people.fake import fake_print
from pebble.people.trust import TRUSTED


def awake(rig):
    rig.context.motion_guard = rig.life.company.blocked
    rig.context.people_near = rig.life.company.anyone_here
    for _ in range(2):
        rig.clock.advance(1)
        run(rig.life.tick(1))
    assert rig.life.state is LifeState.ACTIVE and rig.permissions.can_move


def tick(rig, seconds=1.0):
    rig.clock.advance(seconds)
    run(rig.life.tick(seconds))


def arrive(rig, key, text="hello", name=None):
    rig.life.see(fake_print(key, "face"))
    heard = rig.life.hear(text, fake_print(key, "voice"))
    person = rig.life.company.book.get(heard.person_id)
    if name and not person.name:
        person.set_name(name)
    return person


def test_a_strangers_stop_pauses_then_pebble_decides(rig_factory):
    rig = rig_factory()
    awake(rig)
    arrive(rig, "visitor")
    heard = rig.life.hear("Stop!", fake_print("visitor", "voice"))
    assert heard.stop.kind == "pause"
    assert not rig.permissions.can_move
    assert not run(rig.registry.call("move", {"direction": "forward"}))["ok"]
    tick(rig, 1.0)
    assert not rig.permissions.can_move
    tick(rig, 1.5)
    assert rig.permissions.can_move
    texts = [e.text for e in rig.life.events.peek()]
    assert any("paused" in t for t in texts) and any("decide for yourself" in t for t in texts)
    assert run(rig.registry.call("move", {"direction": "forward", "seconds": 0.5}))["ok"]


def test_a_trusted_stop_sticks_until_they_say_go(rig_factory):
    rig = rig_factory()
    awake(rig)
    tui = arrive(rig, "tui", name="Tui")
    tui.override = TRUSTED
    arrive(rig, "visitor")
    rig.life.hear("stop right there", fake_print("tui", "voice"))
    for _ in range(30):
        tick(rig, 2.0)
        rig.life.see(fake_print("tui", "face"))
    assert not rig.permissions.can_move
    rig.life.hear("go ahead, carry on", fake_print("visitor", "voice"))
    tick(rig)
    assert not rig.permissions.can_move
    assert rig.life.hear("ok, you can move again", fake_print("tui", "voice")).released
    tick(rig)
    assert rig.permissions.can_move


def test_a_sticky_stop_lapses_when_the_person_has_gone(rig_factory):
    rig = rig_factory()
    awake(rig)
    tui = arrive(rig, "tui", name="Tui")
    tui.override = TRUSTED
    rig.life.hear("stop", fake_print("tui", "voice"))
    tick(rig, 300)
    assert not rig.permissions.can_move
    tick(rig, 400)
    assert rig.permissions.can_move
    assert any("has gone" in e.text for e in rig.life.events.peek())


def beat_requests(rig):
    start = len(rig.mind.requests)
    run(rig.life.beat())
    return [r for r in rig.mind.requests[start:] if r["purpose"] == "turn"]


def test_a_secret_is_masked_from_the_next_turn_when_someone_else_is_here(rig_factory):
    rig = rig_factory()
    rig.life._mind_ready = True
    run(rig.life.read_sensors())
    arrive(rig, "ina", "hi", name="Ina")
    rig.life.hear("It's a secret: I'm getting Sam a bike", fake_print("ina", "voice"))
    assert "bike" in json.dumps(beat_requests(rig)[0]["messages"])
    rig.clock.advance(300)
    arrive(rig, "sam", "hello Pebble", name="Sam")
    later = beat_requests(rig)
    sent = json.dumps([r["messages"] for r in later])
    assert later and "bike" not in sent and PRIVATE_MASK in sent
    assert "private" not in {key for r in later for message in r["messages"] for key in message}
    rig.clock.advance(300)
    arrive(rig, "ina", "me again")
    alone = beat_requests(rig)
    assert "bike" in json.dumps(alone[0]["messages"])
    run(rig.history.compact(rig.mind, "2026-10-15T13:00:00+00:00", everything=True))
    kept = list(rig.life.memory.recall.stream.records.values())
    assert kept and not any("bike" in r.text for r in kept)
    assert any(PRIVATE_MASK in r.text and r.mark == "private" for r in kept)


def test_people_tools_are_offered_only_when_someone_is_here(rig_factory):
    rig = rig_factory()
    assert "note_person" not in rig.life.tool_names(True)
    arrive(rig, "ina")
    assert "note_person" in rig.life.tool_names(True)
    rig.clock.advance(600)
    assert "note_person" not in rig.life.tool_names(True)


def test_shaking_counts_against_the_one_holding_pebble(rig_factory):
    rig = rig_factory()
    ina = arrive(rig, "ina", name="Ina")
    rig.life.felt("shaken")
    assert not [e for e in ina.ledger.entries if e.quality == "respect"]
    rig.life.see(fake_print("ina", "face"))
    from pebble.seams.face import Touch

    rig.life.touched(Touch(0.5, 0.5, "hold"))
    assert rig.life.felt("shaken") == ina.id
    assert [e.reason for e in ina.ledger.entries if e.quality == "respect"] == ["shook me while holding me"]


def test_small_tasks_come_from_friends_who_are_here(rig_factory):
    rig = rig_factory()
    rig.context.task_from = rig.life.company.task_refusal
    task = {"title": "Wave at the door", "done_when": "Pebble has waved at the door", "reason": "asked"}
    visitor = arrive(rig, "visitor")
    rig.life.company.asking = {visitor.id: False}
    assert not run(rig.registry.call("add_task", {**task, "requested_by": visitor.label}))["ok"]
    assert not run(rig.registry.call("add_task", {**task, "requested_by": "Nobody"}))["ok"]
    mo = arrive(rig, "mo", name="Mo")
    mo.override = "friend"
    assert not run(rig.registry.call("add_task", {**task, "requested_by": "Mo"}))["ok"]
    rig.life.company.asking = {mo.id: False}
    assert run(rig.registry.call("add_task", {**task, "requested_by": "Mo"}))["ok"]
    assert run(rig.registry.call("add_task", {**task, "title": "Look at the door"}))["ok"]
