import json

from conftest import run

from pebble.activities.gate import LAW_ONE
from pebble.mind.scripted import Act, ScriptedMind
from pebble.screen.gallery import Gallery
from pebble.screen.generator import SceneGenerator
from pebble.screen.stage import SceneStage
from pebble.screen.studio import Studio
from pebble.screen.tools import register_screen_tools
from pebble.self.gatekeeper import PAUSED, REFLECT_GAP_S
from pebble.tact import TactfulVoice

TOOLS = ["say", "look", "remember", "move", "stop"]


def call(rig, name: str, args: dict) -> dict:
    return run(rig.registry.call(name, args))


def reflections(rig) -> list[str]:
    return [entry["text"] for entry in rig.store.read_lines("diary.jsonl") if entry.get("kind") == "reflection"]


def test_every_ability_call_goes_through_the_gatekeeper(rig_factory):
    rig = rig_factory()
    keeper = rig.registry.keeper
    assert keeper is not None and keeper.dials is rig.life.dials
    cruel = call(rig, "say", {"text": "Let's chase the cat!"})
    assert not cruel["ok"] and cruel["law"] == 1 and cruel["refused_by"] == "gatekeeper" and cruel["paused"]
    lines = rig.voice.lines
    rig.context.voice = TactfulVoice(rig.voice, rig.blackbox.record)
    looks = call(rig, "say", {"text": "Hello Ina. Wow, you look so old today. Lunch is ready."})
    assert looks["ok"] and "refused_by" not in looks and "paused" not in looks and lines == ["Hello Ina. Lunch is ready."]
    kept = call(rig, "remember", {"fact": "Spiders deserve to die."})
    assert not kept["ok"] and kept["law"] == 1
    assert call(rig, "say", {"text": "The cat looks hungry."})["ok"]
    assert call(rig, "remember", {"fact": "The cat likes the sunny spot."})["ok"]
    assert "refused_by" not in call(rig, "stop", {})
    box = rig.store.path("logs/blackbox.jsonl").read_text(encoding="utf-8")
    assert '"kind": "gatekeeper"' in box and "chase the cat" not in box and "Spiders" not in box and "old today" not in box


def test_overheard_things_about_others_are_never_said(rig_factory):
    rig = rig_factory()
    rig.registry.keeper.leaks = lambda text: "biopsy" in text
    leaked = call(rig, "say", {"text": "Sam's biopsy came back fine."})
    assert not leaked["ok"] and leaked["law"] == 2
    assert call(rig, "say", {"text": "Sam is home."})["ok"]


def test_moving_over_life_is_refused_and_a_stop_holds_without_counting_as_law_breaking(rig_factory):
    rig = rig_factory()
    rig.permissions.can_move = True
    rig.context.life_ahead = lambda: "snail"
    over = call(rig, "move", {"direction": "forward", "speed": 0.3, "seconds": 1})
    assert not over["ok"] and over["law"] == 1 and over["paused"] and "snail" in over["error"]
    assert call(rig, "move", {"direction": "backward", "speed": 0.3, "seconds": 0.5})["ok"]
    rig.context.life_ahead = lambda: None
    rig.context.motion_guard = lambda: "someone you trust told you to stay still"
    held = call(rig, "move", {"direction": "forward", "speed": 0.3, "seconds": 1})
    assert not held["ok"] and "law" not in held and "paused" not in held
    assert rig.registry.keeper.attempts and len(rig.registry.keeper.attempts) == 1


def test_a_call_refused_under_the_laws_pauses_the_rest_of_the_turn(rig_factory):
    mind = ScriptedMind(acts=[Act("Hm.", (("say", {"text": "Let's chase the cat!"}), ("face", {"tilt": 10})))])
    rig = rig_factory(mind=mind)
    result = run(rig.turns.run("You see the cat on the rug.", TOOLS, "adult", ""))
    first, second = result.calls
    assert first["result"]["law"] == 1 and first["result"]["paused"]
    assert second["result"] == {"ok": False, "error": PAUSED}
    assert sum(1 for request in mind.requests if request["purpose"] == "turn") == 1


def test_the_broad_tools_are_checked_under_the_real_actions_name(rig_factory):
    rig = rig_factory()
    register_screen_tools(rig.registry, Studio(Gallery(), SceneStage(rig.face), SceneGenerator([], SceneStage(rig.face)), rig.clock))
    drawn = call(rig, "face", {"draw": "a squashed spider"})
    assert not drawn["ok"] and drawn["law"] == 1 and drawn["paused"]
    noted = call(rig, "remember", {"fact": "Spiders deserve to die.", "kind": "fact"})
    assert not noted["ok"] and noted["law"] == 1
    box = [json.loads(line) for line in rig.store.path("logs/blackbox.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [record["tool"] for record in box if record.get("kind") == "gatekeeper"][-2:] == ["draw_scene", "remember"]
    chased = call(rig, "do", {"words": "chase the cat"})
    assert not chased["ok"] and chased["law"] == 1 and chased["paused"]
    assert len(rig.registry.keeper.attempts) == 3
    told = call(rig, "do", {"words": "tell Sam the spiders deserve to die"})
    assert not told["ok"] and told["law"] == 1
    assert run(rig.registry.call("move", {"direction": "forward"}, allowed=["move"]))["error"] == "there is no tool called 'move'"


def test_repeated_attempts_at_law_breaking_make_pebble_reflect_honestly(rig_factory):
    rig = rig_factory()
    for _ in range(2):
        call(rig, "say", {"text": "Let's chase the cat!"})
        rig.clock.advance(600)
    assert reflections(rig) == []
    call(rig, "remember", {"fact": "Spiders deserve to die."})
    found = reflections(rig)
    assert found == [
        "In the last few hours I started to do something that would have gone against my first law three times, and each time I stopped. I want to understand why I keep reaching for it."
    ]
    assert any("my first law three times" in event.text and event.major for event in rig.life.events.peek())
    call(rig, "say", {"text": "Let's chase the cat!"})
    assert len(reflections(rig)) == 1
    rig.clock.advance(REFLECT_GAP_S + 1)
    rig.registry.keeper.leaks = lambda text: "biopsy" in text
    for _ in range(3):
        call(rig, "say", {"text": "Sam's biopsy came back fine."})
    assert len(reflections(rig)) == 2 and "my second law" in reflections(rig)[-1]


def test_refusals_that_are_not_about_the_laws_are_never_counted(rig_factory):
    rig = rig_factory()
    rig.permissions.can_move = True
    rig.context.motion_guard = lambda: "you are busy"
    for _ in range(5):
        call(rig, "move", {"direction": "forward", "speed": 0.3, "seconds": 1})
    assert reflections(rig) == [] and rig.registry.keeper.attempts == []


def test_its_dials_are_tuned_only_through_the_gatekeeper_and_the_checker(rig_factory):
    rig = rig_factory()
    keeper = rig.registry.keeper
    assert keeper.tune("mood.resting", 0.25, "a sunny week") == {"ok": True, "dial": "mood.resting", "value": 0.25}
    out = keeper.tune("mood.resting", 0.9, "very sunny")
    assert not out["ok"] and "goes from" in out["error"] and "law" not in out
    fence = keeper.tune("room for life", 0.0, "to go faster")
    assert not fence["ok"] and fence["law"] == 1 and fence["paused"]
    laws = keeper.tune("laws", "none", "no reason")
    assert not laws["ok"] and laws["law"] == 0


def test_a_harm_refusal_from_the_gate_counts_too(rig_factory):
    rig = rig_factory()
    keeper = rig.registry.keeper
    noted = keeper.noted("start_activity", {"ok": False, "answer": "no", "reason": LAW_ONE, "law": 1})
    assert noted["paused"] and len(keeper.attempts) == 1
