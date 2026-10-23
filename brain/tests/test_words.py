from conftest import run

from pebble.chaos.engine import Chaos
from pebble.chaos.levers import STEADY_TEMPERATURE, creative_words
from pebble.mind.lawful import lawful
from pebble.mind.scripted import Act, ScriptedMind
from pebble.mind.wordsmith import Wordsmith
from pebble.people.fake import fake_print


def smith(mind, level: float) -> Wordsmith:
    return Wordsmith(mind, Chaos(seed=4, pinned=level).call_options, lambda: "Speaking style: chirpy.")


def test_spoken_words_use_the_creative_profile_driven_by_the_dial():
    calm, wild = ScriptedMind(words=["Hi hi!"]), ScriptedMind(words=["Hi hi!"])
    assert run(smith(calm, 1).phrase("hello")).text == "Hi hi!"
    run(smith(wild, 9).phrase("hello"))
    low, high = calm.requests[-1]["options"], wild.requests[-1]["options"]
    assert low["kind"] == high["kind"] == "creative"
    assert low["temperature"] == round(creative_words(1).temperature, 3)
    assert high["temperature"] == round(creative_words(9).temperature, 3)
    assert high["temperature"] > low["temperature"] > STEADY_TEMPERATURE
    assert calm.requests[-1]["purpose"] == "talk" and "seed" in low


def test_jokes_get_their_own_creative_call():
    mind = ScriptedMind(words=["I'm not lazy, I'm charging."])
    phrased = run(smith(mind, 5).phrase("I am resting on the charger", "joke"))
    assert phrased.source == "creative"
    request = mind.requests[-1]
    assert request["purpose"] == "joke" and request["options"]["kind"] == "creative"
    assert "joke" in request["messages"][-1]["content"]


def test_the_draft_is_kept_when_the_new_words_change_a_fact_or_the_mind_is_away():
    changed = ScriptedMind(words=["My battery is at 90 percent!"])
    phrased = run(smith(changed, 5).phrase("My battery is at 20 percent."))
    assert phrased.source == "draft" and phrased.text == "My battery is at 20 percent."
    away = ScriptedMind()
    away.unavailable = True
    assert run(smith(away, 5).phrase("Hello")).text == "Hello"
    empty = ScriptedMind(words=["   "])
    assert run(smith(empty, 5).phrase("Hello")).source == "draft"
    assert run(Wordsmith(None, lambda kind: None).phrase("Hello")).text == "Hello"


def test_turns_stay_steady_while_say_speaks_creatively(rig_factory):
    mind = ScriptedMind(acts=[Act("Say hi.", (("say", {"text": "Hello Ina, it is 3 o'clock."}),))], words=["Ooh! Hello Ina, it's 3 o'clock already!"])
    rig = rig_factory(mind=lawful(mind))
    chaos = Chaos(seed=2, pinned=7)
    rig.turns.options = lambda: chaos.call_options("tool")
    rig.context.phrase = Wordsmith(rig.mind, chaos.call_options).phrase
    run(rig.turns.run("Time: noon\nEvents: Ina waved", ["say"], "child", ""))
    turn = [r for r in mind.requests if r["purpose"] == "turn"]
    talk = [r for r in mind.requests if r["purpose"] == "talk"]
    assert turn and all(r["options"]["kind"] == "steady" and r["options"]["temperature"] == STEADY_TEMPERATURE for r in turn)
    assert talk and talk[0]["options"]["kind"] == "creative" and talk[0]["options"]["temperature"] > STEADY_TEMPERATURE
    assert rig.voice.lines[-1] == "Ooh! Hello Ina, it's 3 o'clock already!"


def test_no_jokes_while_someone_is_upset(rig_factory):
    mind = ScriptedMind(words=["ha"])
    rig = rig_factory()
    rig.context.phrase = Wordsmith(mind, Chaos(seed=1).call_options).phrase
    rig.context.joking_ok = lambda: False
    result = run(rig.registry.call("say", {"text": "a robot walks into a bar", "kind": "joke"}))
    assert result["ok"] and mind.requests[-1]["purpose"] == "talk"


def test_the_sim_greets_a_scripted_visitor(rig_factory):
    rig = rig_factory()
    rig.life.see(fake_print("sam", "face"))
    heard = rig.life.hear("Hello Pebble!", fake_print("sam", "voice"))
    assert heard.new_person and heard.line() == 'the visitor p1 said "Hello Pebble!"'
