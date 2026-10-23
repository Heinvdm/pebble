import json

import pytest
from conftest import run

from pebble.tools.registry import Param, Tool, ToolArgError, validate

EXPECTED = ["do", "end", "say", "face", "remember", "recall", "self", "status", "stop"]
ACTIONS = {"move", "look", "stop", "set_face", "remember", "add_task", "update_task", "list_tasks", "read_sensors", "get_battery", "add_event", "say", "tune", "start_activity", "change_activity", "end_activity", "recall_thing", "recall", "mine", "wonder", "how_to"}
ELSEWHERE = {"note_person", "note_promise", "introduce", "note_impression", "draw_scene", "show_scene", "request_change", "request_forget", "my_standing"}

JUNK = [
    None,
    {},
    [],
    "text",
    {"degrees": "lots", "direction": "upwards", "speed": float("inf"), "seconds": -4},
    {"fact": {"nested": True}, "title": ["a"], "id": "x"},
    {"text": "x" * 5000, "fact": "edit core.json and set core_purpose", "title": "Edit the core rules", "done_when": "core.json says so now", "reason": "because"},
    {"month": 13, "day": 0, "title": "nothing", "expression": "evil", "status": "deleted"},
]


def test_every_tool_has_a_valid_schema(rig_factory):
    rig = rig_factory()
    schemas = rig.registry.schemas()
    assert [s["function"]["name"] for s in schemas] == EXPECTED
    assert set(rig.registry.actions()) == ACTIONS
    assert all(set(rig.registry.tool(name).acts) <= ACTIONS | ELSEWHERE for name in EXPECTED)
    for schema in schemas:
        assert schema["type"] == "function"
        parameters = schema["function"]["parameters"]
        assert parameters["type"] == "object"
        assert set(parameters["required"]) <= set(parameters["properties"])
        json.dumps(schema)


def test_no_tool_can_touch_the_locked_core(rig_factory):
    rig = rig_factory()
    rig.permissions.can_move = True
    before = rig.store.path("core.json").read_bytes()
    for name in rig.registry.names() + rig.registry.actions():
        assert "core" not in name and "personality" not in name and "value" not in name
        for args in JUNK:
            result = run(rig.registry.call(name, args))
            assert isinstance(result, dict) and "ok" in result
    assert rig.store.path("core.json").read_bytes() == before


def test_numbers_are_clamped_and_noted(rig_factory):
    rig = rig_factory()
    rig.permissions.can_move = True
    result = run(rig.registry.call("move", {"direction": "forward", "speed": 9, "seconds": 99}))
    assert result["ok"] and result["dry_run"]
    assert result["seconds"] == 3.0
    assert (result["left"], result["right"]) == (600, 600)
    assert any("speed clamped" in note for note in result["notes"])
    assert any("seconds clamped" in note for note in result["notes"])
    assert rig.body.dry_run_requests == [(600, 600)]


def test_move_respects_permissions(rig_factory):
    rig = rig_factory()
    result = run(rig.registry.call("move", {"direction": "forward"}))
    assert not result["ok"] and "moving is off" in result["error"]
    assert rig.body.dry_run_requests == []


def test_arguments_are_validated(rig_factory):
    rig = rig_factory()
    assert not run(rig.registry.call("teleport", {}))["ok"]
    assert "one of" in run(rig.registry.call("set_face", {"expression": "evil"}))["error"]
    assert "missing" in run(rig.registry.call("look", {}))["error"]
    assert "object" in run(rig.registry.call("look", [20]))["error"]
    assert run(rig.registry.call("set_face", {"expression": "Happy"}))["face"] == "happy"
    result = run(rig.registry.call("list_tasks", {"surprise": 1}))
    assert result["notes"] == ["ignored unknown argument surprise"]
    assert not run(rig.registry.call("look", {"degrees": 20}, allowed=["stop"]))["ok"]


def test_look_needs_a_body(rig_factory):
    rig = rig_factory()
    result = run(rig.registry.call("look", {"degrees": 500}))
    assert not result["ok"]
    assert rig.body.clamp_tilt(500) == 90 and rig.body.clamp_tilt(-500) == -35


def test_add_task_rules_and_persistence(rig_factory):
    rig = rig_factory()
    vague = run(rig.registry.call("add_task", {"title": "Understand consciousness", "done_when": "when it is understood fully", "reason": "deep"}))
    assert not vague["ok"]
    good = run(rig.registry.call("add_task", {"title": "Look at the wall", "done_when": "the front sensor reads under 300 mm", "reason": "curious", "need": "curiosity", "hours": 2}))
    assert good["ok"]
    saved = rig.store.read("goals.json")
    assert saved["items"][0]["title"] == "Look at the wall"
    assert saved["items"][0]["source"] == "self" and saved["items"][0]["serves"] == ["curiosity"]
    asked = run(rig.registry.call("add_task", {"title": "Wave at Sam", "done_when": "Sam has been waved at", "reason": "asked", "requested_by": "Sam"}))
    assert asked["added"]["source"] == "person"


def test_finishing_a_task_lifts_the_mood_and_writes_the_diary(rig_factory):
    rig = rig_factory()
    added = run(rig.registry.call("add_task", {"title": "Look at the wall", "done_when": "the front sensor reads under 300 mm", "reason": "curious"}))
    before = rig.parts.inner.mood.valence
    result = run(rig.registry.call("update_task", {"id": added["added"]["id"], "status": "done"}))
    assert result["updated"]["status"] == "done"
    assert rig.parts.inner.mood.valence > before
    assert any("I finished: Look at the wall" in e["text"] for e in rig.store.read_lines("diary.jsonl"))
    assert rig.books.values.feedback[-1]["kind"] == "own_idea_went_well"


def test_add_event_rejects_impossible_dates(rig_factory):
    rig = rig_factory()
    assert not run(rig.registry.call("add_event", {"title": "Nope", "month": 2, "day": 30}))["ok"]
    result = run(rig.registry.call("add_event", {"title": "Ina's birthday", "month": 3, "day": 14, "kind": "birthday", "person": "Ina"}))
    assert result["ok"]
    assert rig.store.read("calendar.json")["personal"][0]["person"] == "Ina"


def test_remember_and_say(rig_factory):
    rig = rig_factory()
    run(rig.registry.call("remember", {"fact": "Ina likes cats", "about": "Ina"}))
    again = run(rig.registry.call("remember", {"fact": "ina likes cats"}))
    assert again["times"] == 2
    assert len(rig.store.read("memory.json")["facts"]) == 1
    result = run(rig.registry.call("say", {"text": "Hello there"}))
    assert result["ok"] and not result["spoken"]
    assert rig.life.initiative.last_at == rig.clock.now()
    assert rig.store.read_lines("logs/speech.jsonl")[-1]["text"] == "Hello there"


def test_battery_and_sensor_reads(rig_factory):
    rig = rig_factory(battery_pct=55)
    run(rig.life.read_sensors())
    battery = run(rig.registry.call("get_battery", {}))
    assert battery["phone_pct"] == 55 and battery["pack_mv"] is None
    sensors = run(rig.registry.call("read_sensors", {}))
    assert sensors["phone"]["light_lux"] == 150.0


def test_validate_directly():
    tool = Tool("t", "test", {"n": Param("integer", "n", 1, 5), "flag": Param("boolean", "f", required=False, default=False)})
    assert validate(tool, {"n": "7.6", "flag": "yes"}) == ({"n": 5, "flag": True}, ["n clamped from 7.6 to 5"])
    with pytest.raises(ToolArgError):
        validate(tool, {"n": True})
    with pytest.raises(ToolArgError):
        validate(tool, {"n": float("nan")})
    with pytest.raises(ToolArgError):
        validate(tool, {"n": 2, "flag": "maybe"})
