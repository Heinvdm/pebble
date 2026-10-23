import asyncio
import json
import statistics
from dataclasses import replace

import test_conversation as tc
from pebble.android.hearing import TURN_CHECK_S, TURN_RETRY_S, AndroidEars
from pebble.clock import FakeClock
from pebble.conversation.eval import load
from pebble.conversation.scripted import Said, ScriptedSpeech
from pebble.conversation.turns import END_S, LONG_S, TurnTaker
from pebble.mind.scripted import ScriptedMind
from pebble.people.trust import TRUSTED
from pebble.speech.events import SpeechEvent, parse
from pebble.speech.phone import PhoneSpeech
from conftest import NOON

STEP = 0.005


def run_taker(found: list[SpeechEvent], until: float = 5.0) -> list:
    closed = []
    taker = TurnTaker(on_close=closed.append)
    t = found[0].t
    for event in found:
        while t < event.t:
            taker.tick(t)
            t += STEP
        taker.feed(event)
    limit = t + until
    while taker.turn is not None and t < limit:
        taker.tick(t)
        t += STEP
    return closed


def riding(found: list[SpeechEvent]) -> list[SpeechEvent]:
    scores = {(e.segment, e.after): e.turn_end for e in found if e.kind == "turn_end"}
    out = []
    for event in found:
        if event.kind == "turn_end":
            continue
        if event.kind in ("pause", "voice_end") and (event.segment, event.kind) in scores:
            event = replace(event, turn_end=scores[(event.segment, event.kind)])
        out.append(event)
    return out


def test_the_phone_score_comes_as_its_own_event_or_riding_on_the_pause():
    alone = parse(json.dumps({"kind": "turn_end", "t": 5.2, "segment": 3, "after": "pause", "turn_end": 0.934, "turn_end_ms": 141.5}))
    assert (alone.kind, alone.segment, alone.after, alone.turn_end, alone.turn_end_ms) == ("turn_end", 3, "pause", 0.934, 141.5)
    assert parse(json.dumps({"kind": "turn_end", "t": 5.2, "segment": 3})) is None
    assert parse(json.dumps({"kind": "turn_end", "t": 5.2, "segment": 3, "turn_end": 7})).turn_end == 1.0
    assert parse(json.dumps({"kind": "turn_end", "t": 5.2, "segment": 3, "after": "sideways", "turn_end": 0.5})).after == ""
    on_end = parse(json.dumps({"kind": "voice_end", "t": 5.3, "segment": 3, "end": 5.05, "turn_end": 0.12}))
    assert on_end.kind == "voice_end" and on_end.turn_end == 0.12
    assert on_end.as_dict()["turn_end"] == 0.12 and "turn_end" not in parse(json.dumps({"kind": "pause", "t": 1, "segment": 1})).as_dict()
    phone = PhoneSpeech()
    phone.event(json.dumps({"kind": "turn_end", "t": 5.2, "segment": 3, "after": "voice_end", "turn_end": 0.9}))
    assert phone.status() == {"received": 1, "bad": 0, "dropped": 1}


def test_a_statement_closes_as_soon_as_its_words_are_in_when_the_phone_hears_an_ending():
    text = "i had a really lovely day at the beach"
    plain, end = ScriptedSpeech().events(Said("ina", text), 0.0)
    scored, _ = ScriptedSpeech().events(Said("ina", text, turn_end=0.95), 0.0)
    final_at = next(e.t for e in plain if e.kind == "final")
    waits = {}
    for name, found in (("plain", plain), ("apart", scored), ("riding", riding(scored))):
        closed = run_taker(found)
        assert [t.text for t in closed] == [text]
        assert closed[0].closed_at >= final_at
        waits[name] = closed[0].closed_at - end
    assert abs(waits["plain"] - END_S) < 0.02
    assert waits["apart"] <= final_at - end + 0.02 and waits["riding"] <= final_at - end + 0.02
    assert waits["plain"] - waits["apart"] >= 0.3


def test_a_low_score_at_a_thinking_pause_keeps_the_turn_open():
    text = "Pebble, can you tell me ... what time it is"
    plain, _ = ScriptedSpeech().events(Said("ina", text), 0.0)
    assert [t.text for t in run_taker(plain)] == ["can you tell me", "what time it is"]
    scored, _ = ScriptedSpeech().events(Said("ina", text, turn_end=0.95), 0.0)
    closed = run_taker(scored)
    assert [t.text for t in closed] == ["can you tell me what time it is"]
    assert closed[0].keyword and closed[0].notes["closed_by"] == "sounded finished"


def test_a_low_score_waits_longer_but_not_for_ever():
    text = "so i was thinking that"
    found, end = ScriptedSpeech().events(Said("ina", text, turn_end=0.1), 0.0)
    closed = run_taker(found)
    assert len(closed) == 1 and closed[0].notes["closed_by"] == "sounded unfinished"
    assert abs(closed[0].closed_at - end - LONG_S) < 0.02


def test_a_score_for_an_older_pause_or_another_turn_is_ignored():
    taker = TurnTaker()
    taker.feed(SpeechEvent("voice_start", 0.1, 1, start=0.0))
    taker.feed(SpeechEvent("partial", 0.5, 1, text="so i was"))
    taker.feed(SpeechEvent("pause", 1.0, 1))
    taker.feed(SpeechEvent("partial", 1.2, 1, text="so i was thinking"))
    taker.feed(SpeechEvent("pause", 1.6, 1))
    turn = taker.turn
    taker.feed(SpeechEvent("turn_end", 1.7, 1, turn_end=0.95, turn_end_ms=600.0, after="pause"))
    assert turn.done_chance is None
    taker.feed(SpeechEvent("turn_end", 1.75, 1, turn_end=0.2, turn_end_ms=100.0, after="pause"))
    assert turn.done_chance == 0.2
    taker.feed(SpeechEvent("turn_end", 1.76, 1, turn_end=0.9, after="voice_end"))
    assert turn.done_chance == 0.2
    taker.feed(SpeechEvent("voice_end", 1.85, 1, end=1.6))
    taker.feed(SpeechEvent("turn_end", 2.0, 1, turn_end=0.9, turn_end_ms=100.0, after="voice_end"))
    assert turn.done_chance == 0.9
    taker.feed(SpeechEvent("turn_end", 2.05, 1, turn_end=0.1, turn_end_ms=50.0, after="pause"))
    taker.feed(SpeechEvent("turn_end", 2.06, 99, turn_end=0.1, after="voice_end"))
    assert turn.done_chance == 0.9
    taker.feed(SpeechEvent("final", 2.1, 1, text="so i was thinking", start=0.0, end=1.6))
    assert taker.tick(2.2) is turn
    taker.feed(SpeechEvent("turn_end", 2.3, 1, turn_end=0.1, after="voice_end"))
    assert taker.turn is None and turn.done_chance == 0.9


def test_a_name_alone_never_closes_early_on_a_high_score():
    found = [
        SpeechEvent("voice_start", 0.1, 1, start=0.0),
        SpeechEvent("pause", 0.44, 1),
        SpeechEvent("keyword", 0.51, 1, word="pebble"),
        SpeechEvent("voice_end", 0.65, 1, end=0.4),
        SpeechEvent("final", 0.71, 1, text="", start=0.0, end=0.4, keyword=True),
        SpeechEvent("turn_end", 0.77, 1, turn_end=0.97, turn_end_ms=120.0, after="voice_end"),
    ]
    closed = run_taker(found)
    assert closed[0].notes["closed_by"] == "silence" and closed[0].closed_at - 0.4 >= END_S - STEP


def test_across_the_scripted_scenes_turns_close_sooner_and_never_later():
    lines = [line["say"] for scene in load() for line in scene["lines"] if line["who"] != "pebble"]
    before, after = [], []
    for text in lines:
        for score, waits in ((None, before), (0.95, after)):
            found, end = ScriptedSpeech().events(Said("ina", text, turn_end=score), 0.0)
            closed = run_taker(found)
            finals = [e.t for e in found if e.kind == "final"]
            assert closed[-1].closed_at >= finals[-1]
            waits.append(closed[-1].closed_at - end)
    assert len(lines) >= 90
    assert all(b + 1e-6 >= a for b, a in zip(before, after))
    assert statistics.mean(before) - statistics.mean(after) >= 0.2
    assert statistics.mean(after) <= 0.35


class TurnPhone:
    def __init__(self, state: str, nested: bool = True):
        self.state = state
        self.nested = nested
        self.configs: list[dict] = []

    def hearingInfo(self) -> str:
        found = {"turn_model": self.state}
        return json.dumps({"speech_engine": "sherpa-onnx", "engine": found} if self.nested else found)

    def speechConfig(self, text: str) -> None:
        self.configs.append(json.loads(text))

    def listen(self, on: bool) -> None:
        pass


def test_the_ears_switch_the_phone_model_on_only_while_it_is_there():
    clock = FakeClock.at(NOON)
    phone = TurnPhone("off")
    ears = AndroidEars(clock, bridge=phone)
    ears.update()
    ears.update()
    assert phone.configs == [{"turn_model": True}]
    phone.state = "on"
    clock.advance(TURN_CHECK_S)
    ears.update()
    assert phone.configs == [{"turn_model": True}] and ears.turn_state == "on"
    phone.state = "failed: no session"
    clock.advance(TURN_CHECK_S)
    ears.update()
    assert phone.configs[-1] == {"turn_model": False}
    phone.state = "off"
    clock.advance(TURN_CHECK_S)
    ears.update()
    assert len(phone.configs) == 2
    clock.advance(TURN_RETRY_S)
    ears.update()
    assert phone.configs[-1] == {"turn_model": True} and len(phone.configs) == 3
    absent = TurnPhone("missing")
    quiet = AndroidEars(clock, bridge=absent)
    for _ in range(3):
        quiet.update()
        clock.advance(TURN_CHECK_S)
    assert absent.configs == [] and quiet.turn_state == "missing"
    flat = TurnPhone("off", nested=False)
    AndroidEars(clock, bridge=flat).update()
    assert flat.configs == [{"turn_model": True}]
    none = TurnPhone("none")
    AndroidEars(clock, bridge=none).update()
    assert none.configs == []


class Compute(ScriptedMind):
    def __init__(self, clock, sleep, first_s: float, text: str):
        super().__init__(replies=[text] * 10)
        self.clock = clock
        self.pause = sleep
        self.first_s = first_s

    async def stream(self, messages, purpose="turn", max_tokens=None, options=None, tools=None):
        reply = await self.chat(messages, tools, purpose, max_tokens, options)
        ready = self.clock.monotonic() + self.first_s
        while self.clock.monotonic() < ready:
            await self.pause(0.05)
        yield reply.text


ANSWER = "That sounds like a lovely day."


async def say(talk, who: str, text: str, score) -> None:
    for person_id in talk.ids.values():
        talk.rig.life.company.presence.saw(person_id, talk.clock.now())
    found, _ = talk.speech.events(Said(who, text, turn_end=score), talk.clock.monotonic(), speaking=talk.conv.mouth.speaking)
    for event in found:
        while talk.clock.monotonic() < event.t:
            talk.clock.advance(0.01)
            talk.conv.tick()
            await asyncio.sleep(0)
        talk.conv.on_speech(event)
    await talk.settle(4.0)


def answered(rig_factory, clock, text: str, score) -> tuple:
    talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED),))
    mind = Compute(clock, talk.conv.sleep, 1.0, ANSWER)
    talk.rig.turns.mind = mind
    asyncio.run(say(talk, "ina", text, score))
    return talk, mind


def test_pebble_answers_a_statement_sooner_when_the_phone_hears_its_end(rig_factory, clock):
    text = "Pebble, i had a really lovely day at the beach"
    plain, _ = answered(rig_factory, clock, text, None)
    scored, _ = answered(rig_factory, clock, text, 0.95)
    for talk in (plain, scored):
        assert ANSWER in talk.spoken() and talk.conv.stats.replies == 1
    slow = plain.conv.stats.answer_latencies[0]
    quick = scored.conv.stats.answer_latencies[0]
    assert slow - quick >= 0.3
    assert scored.conv.stats.closed_by == {"sounded finished": 1}
    assert plain.conv.stats.closed_by == {"silence": 1}


def test_a_thinking_pause_gets_one_answer_to_the_whole_question(rig_factory, clock):
    text = "Pebble, can you tell me ... what time it is"
    plain, plain_mind = answered(rig_factory, clock, text, None)
    scored, scored_mind = answered(rig_factory, clock, text, 0.95)
    asked = [r["messages"][-1]["content"] for r in scored_mind.requests if r["purpose"] == "reply"]
    assert scored.conv.stats.replies == 1 and asked[-1].endswith('"can you tell me what time it is"')
    assert plain.conv.stats.replies + plain.conv.stats.barge_ins >= 2
