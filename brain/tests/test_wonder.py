import asyncio

import pytest
import test_conversation as tc
from conftest import run, small_model

from pebble.life.loop import DEEP_LINE, LOOK_LINE, WONDER_PHRASES
from pebble.life.turn import DEEP_ROUNDS, DEEP_TOKENS
from pebble.link.protocol import Event
from pebble.mind.base import CallOptions, MindReply, ToolCall
from pebble.mind.llama import BACKGROUND, LlamaServerMind, parse_completion
from pebble.mind.scripted import Act, ScriptedMind
from pebble.mind.subconscious import Subconscious, doubt_of, letter_chances
from pebble.people.trust import TRUSTED
from pebble.self.drives import Drive
from pebble.self.wonder import DEEP_AT, FADE_S, MIDDLE, Wonder, threshold

QUIET_ACT = Act("Nothing to do.", ())
SMILE_ACT = Act("That was nice.", (("face", {"expression": "happy"}),))


def turns(mind) -> list[dict]:
    return [r for r in mind.requests if r["purpose"] == "turn"]


class Keen:
    def __init__(self):
        self.requests = []

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        self.requests.append({"purpose": purpose, "max_tokens": max_tokens})
        return MindReply("Let me look again.", (ToolCall(f"keen_{len(self.requests)}", "set_face", {"expression": "curious"}, '{"expression": "curious"}'),))


def awake(rig_factory, **kwargs):
    rig = rig_factory(**kwargs)
    rig.life._mind_ready = True
    run(rig.life.read_sensors())
    run(rig.life.beat())
    assert rig.life.turns_run == 1
    rig.clock.advance(61)
    return rig


def test_the_wonder_score_adds_up_what_matters_and_fades():
    wonder = Wonder()
    assert wonder.quiet() and wonder.score(0.0) == 0.0
    wonder.noticed(2.0, "a cup moved", 0.0)
    small = wonder.score(0.0)
    assert 0.0 < small < threshold(0.5)
    wonder.push("surprise", 0.6, "the plant is gone", 0.0)
    both = wonder.score(0.0)
    assert both > small and both > threshold(0.5)
    assert wonder.score(FADE_S) < both
    assert wonder.reasons(0.0)[0] == "the plant is gone"
    assert wonder.score(0.0, {"surprise": 0.5}) < both
    lonely = Drive("company", 0.95, "nobody has talked with me for a while")
    wonder.feel((lonely, Drive("rest", 0.99, "I'm getting tired")))
    assert wonder.parts(0.0)["drives"] == (pytest.approx(0.875), "nobody has talked with me for a while")
    wonder.looked()
    assert wonder.score(0.0) == 0.0 and wonder.quiet()
    wonder.feel((Drive("company", 0.99, lonely.why),))
    assert wonder.parts(0.0)["drives"][0] == pytest.approx(0.1)
    wonder.feel((lonely, Drive("energy", 1.0, "my battery is getting low")))
    assert wonder.parts(0.0)["drives"] == (pytest.approx(1.0), "my battery is getting low")
    assert threshold(1.0) < threshold(0.5) < threshold(0.0)


def test_deep_means_more_thinking_for_stakes_stuck_refusals_and_doubt():
    wonder = Wonder()
    wonder.noticed(12.0, "lots happened", 0.0)
    assert not wonder.deep(0.0)
    wonder.push("stuck", DEEP_AT, "the same thing keeps going wrong", 0.0)
    assert wonder.deep(0.0)


def test_a_small_thing_waits_and_a_big_one_is_thought_about(rig_factory):
    rig = awake(rig_factory)
    life = rig.life
    run(life.beat())
    assert life.skips["nothing changed"] == 1
    life.notice(Event("obstacle", ("45",)))
    run(life.beat())
    assert life.turns_run == 1 and life.skips["not enough to think about yet"] == 1
    life.notice(Event("obstacle", ("40",)))
    life.notice(Event("obstacle", ("35",)))
    run(life.beat())
    assert life.turns_run == 2
    rig.clock.advance(61)
    life.notice(Event("bump", ("L",)))
    run(life.beat())
    assert life.turns_run == 3
    assert "You stopped to think because:" in [m for m in turns(rig.mind)[-1]["messages"] if m["role"] == "user"][-1]["content"]


def test_a_more_thoughtful_pebble_stops_for_smaller_things(rig_factory):
    rig = awake(rig_factory)
    assert rig.life.dials.propose("thoughtfulness", 1.0, why="it likes to mull things over").ok
    rig.life.notice(Event("obstacle", ("45",)))
    run(rig.life.beat())
    assert rig.life.turns_run == 2


def test_at_most_one_background_turn_a_minute_and_a_look_every_half_hour(rig_factory):
    rig = awake(rig_factory)
    life = rig.life
    rig.clock.advance(-60)
    life.alive.note("the plant is not where it usually is", kind="surprise")
    life.alive.note("the lamp is not where it usually is", kind="surprise")
    assert life._gap() == pytest.approx(life.s.turn_ceiling_s - 1)
    run(life.beat())
    assert life.turns_run == 1 and life.skips["you thought a moment ago"] == 1
    rig.clock.advance(60)
    run(life.beat())
    assert life.turns_run == 2
    life.notice(Event("bump", ("L",)))
    assert life._gap() == pytest.approx(life.s.min_turn_gap_s)
    run(life.beat())
    assert life.turns_run == 3
    rig.clock.advance(1799)
    run(life.beat())
    assert life.turns_run == 3
    rig.clock.advance(2)
    run(life.beat())
    assert life.turns_run == 4
    assert LOOK_LINE in [r for r in turns(rig.mind) if r["messages"][-1]["role"] == "user"][-1]["messages"][-1]["content"]


def test_in_between_no_model_is_asked_and_it_waits_for_more(rig_factory):
    rig = awake(rig_factory)
    life = rig.life
    sub = ScriptedMind(senses=["A", "A", "A"])
    rig.parts.subconscious = Subconscious(sub)
    life.notice(Event("obstacle", ("45",)))
    life.notice(Event("obstacle", ("44",)))
    score = life.wonder.score(rig.clock.now(), life.dials.pulls())
    assert MIDDLE * threshold(0.5) <= score < threshold(0.5)
    before = life.turns_run
    run(life.beat())
    run(life.beat())
    assert life.turns_run == before and life.skips["not enough to think about yet"] >= 2
    life.notice(Event("obstacle", ("40",)))
    life.notice(Event("obstacle", ("35",)))
    run(life.beat())
    assert life.turns_run == before + 1
    assert not [r for r in sub.requests if r["purpose"] == "sense"] and life._sensed is None
    box = rig.store.path("logs/blackbox.jsonl").read_text(encoding="utf-8")
    assert '"kind": "sense"' not in box


def test_doubt_is_read_from_token_odds_never_from_words():
    body = {"choices": [{"message": {"content": "B"}, "logprobs": {"content": [{"token": "B", "logprob": -0.4, "top_logprobs": [{"token": "B", "logprob": -0.4}, {"token": " A", "logprob": -1.2}, {"token": "x", "logprob": -3.0}]}]}}]}
    reply = parse_completion(body)
    chances = letter_chances(reply.extra["probs"], "AB")
    assert set(chances) == {"A", "B"} and chances["B"] > chances["A"] and sum(chances.values()) == pytest.approx(1.0)
    assert doubt_of({"A": 0.95, "B": 0.05}, 2) == pytest.approx(0.1)
    assert doubt_of({"A": 0.5, "B": 0.5}, 2) == pytest.approx(1.0)
    assert doubt_of({"A": 1.0}, 2) == pytest.approx(0.0)
    assert doubt_of({}, 2) is None
    sensed = run(Subconscious(ScriptedMind(senses=["A"])).ask("Sure?", ["yes, I'm completely certain", "no"]))
    assert sensed.choice == "yes, I'm completely certain" and sensed.doubt is None
    mind = LlamaServerMind(small_model())
    payload = mind.payload([{"role": "user", "content": "A or B?"}], None, 1, CallOptions(grammar='root ::= "A" | "B"', probs=5))
    assert payload["logprobs"] is True and payload["top_logprobs"] == 5 and payload["grammar"]
    assert "probs" not in payload and "sense" in BACKGROUND
    assert "logprobs" not in mind.payload([{"role": "user", "content": "hi"}], None, 1, CallOptions(probs=5), stream=True)


def test_deep_thinking_gets_more_rounds_and_words_on_the_same_model(rig_factory):
    rig = awake(rig_factory, mind=ScriptedMind(acts=[QUIET_ACT]))
    life = rig.life
    runner = life.p.turns
    life.notice(Event("bump", ("L",)))
    assert not life.wonder.deep(rig.clock.now(), life.dials.pulls())
    run(life.beat())
    plain = turns(rig.mind)[-1]
    assert plain["max_tokens"] is None and DEEP_LINE not in plain["messages"][-1]["content"]
    rig.clock.advance(61)
    life._record("activity_end", activity="go_to_thing", how="failed")
    life._record("activity_end", activity="go_to_thing", how="failed")
    assert life.wonder.deep(rig.clock.now(), life.dials.pulls())
    run(life.beat())
    deep = turns(rig.mind)[-1]
    assert deep["max_tokens"] == runner.history.profile.max_reply_tokens * DEEP_TOKENS
    assert DEEP_LINE in deep["messages"][-1]["content"] and "the same thing keeps going wrong" in deep["messages"][-1]["content"]
    keen = Keen()
    runner.mind = keen
    run(runner.run("Look around.", ["set_face"], "child", ""))
    assert len(keen.requests) == runner.max_rounds
    run(runner.run("Look around.", ["set_face"], "child", "", deep=True))
    assert len(keen.requests) == 2 * runner.max_rounds + DEEP_ROUNDS
    life._record("gatekeeper", tool="say", caller="mind", law=1)
    assert life.wonder.parts(rig.clock.now())["invalid"][0] > 0


def test_it_learns_its_own_pace_from_what_its_turns_led_to(rig_factory):
    mind = ScriptedMind(acts=[QUIET_ACT])
    rig = awake(rig_factory, mind=mind)
    life = rig.life
    life.notice(Event("bump", ("L",)))
    strongest = life.wonder.strongest(rig.clock.now(), life.dials.pulls())
    words = WONDER_PHRASES[strongest]
    run(life.beat())
    assert life.dials.value(f"wonder.{strongest}") < 1.0
    assert life.dials.changes[-1]["why"] == f"stopping to think about {words} led to nothing"
    mind.acts = [SMILE_ACT]
    rig.clock.advance(3700)
    life.notice(Event("bump", ("R",)))
    strongest = life.wonder.strongest(rig.clock.now(), life.dials.pulls())
    before = life.dials.value(f"wonder.{strongest}")
    run(life.beat())
    assert life.dials.value(f"wonder.{strongest}") > before
    assert life.dials.changes[-1]["why"] == f"stopping to think about {WONDER_PHRASES[strongest]} led somewhere"


def test_a_correction_after_a_quick_choice_makes_it_doubt_more_readily(rig_factory):
    rig = awake(rig_factory)
    life = rig.life
    life._sensed = (rig.clock.monotonic(), 0.1)
    life.hear("What? No, I said the kitchen.")
    assert life.dials.doubt_at() < 0.5
    assert life.dials.changes[-1]["why"] == "someone corrected me just after a quick choice"


def test_a_fault_in_its_wondering_never_blocks_a_stop_a_note_or_the_tick(rig_factory):
    rig = awake(rig_factory)
    life = rig.life

    def broken(*args, **kwargs):
        raise ValueError("broken")

    life.wonder.push = life.wonder.noticed = life.wonder.feel = broken
    life.dials.propose = broken
    life._sensed = (rig.clock.monotonic(), 0.1)
    heard = life.hear("No, I said stop!")
    assert heard.stop is not None and not rig.permissions.can_move
    assert any(e.text == heard.stop.text for e in life.events.peek())
    run(life.tick(1.0))
    life._record("activity_end", activity="go_to_thing", how="failed")
    box = rig.store.path("logs/blackbox.jsonl").read_text(encoding="utf-8")
    assert '"where": "wonder"' in box and '"where": "inner life"' in box and '"where": "doubt"' in box
    assert '"kind": "activity_end"' in box


def test_background_turns_still_give_way_to_talk(rig_factory, clock):
    talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED),))
    life = talk.rig.life

    async def go():
        await talk.say("ina", "Pebble, how are you?")
        life.notice(Event("bump", ("L",)))
        await life.beat()
        assert life.skips.get("someone is talking with Pebble") == 1
        await talk.settle(10.0)
        await life.beat()
        assert life.skips.get("someone is talking with Pebble") == 2

    asyncio.run(go())
