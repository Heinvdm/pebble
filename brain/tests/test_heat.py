import asyncio
import json

import pytest

import test_conversation as tc
import test_holds as th
from conftest import Rig
from pebble.android.heat import Heat, PhoneHeat
from pebble.conversation.pace import COOL, HOT, WARM, pace_for
from pebble.mind.scripted import ScriptedMind
from pebble.people.trust import TRUSTED


class Fixed:
    def __init__(self, level: str = "cool", slow: bool = False):
        self.level = level
        self.slow = slow

    def now(self) -> Heat:
        return Heat(self.level, self.slow)


class HeatPhone:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def phoneHeat(self):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def test_the_phone_heat_is_read_now_and_then_and_a_failed_read_keeps_the_last(clock):
    phone = HeatPhone(json.dumps({"headroom": 0.66, "status": 2, "level": "warm", "slow": False, "eyes": 0.6, "at": 1}))
    heat = PhoneHeat(clock.monotonic, bridge=phone, every_s=5.0)
    assert heat.now() == Heat("warm", False, 0.66)
    phone.reply = json.dumps({"level": "hot", "slow": True})
    assert heat.now().level == "warm" and phone.calls == 1
    clock.advance(5.0)
    assert heat.now() == Heat("hot", True, None)
    phone.reply = RuntimeError("the keeper is not running")
    clock.advance(5.0)
    assert heat.now().level == "hot" and "keeper" in heat.status()["problem"]
    phone.reply = json.dumps({"level": "molten"})
    clock.advance(5.0)
    assert heat.now().level == "cool" and heat.status()["problem"] == ""
    phone.reply = "[]"
    clock.advance(5.0)
    assert heat.now() == Heat()
    assert PhoneHeat(clock.monotonic).now() == Heat()


def test_the_ladder_only_steps_down_as_the_phone_heats_up():
    assert pace_for("cool") is COOL and pace_for("warm") is WARM and pace_for("hot") is HOT
    assert pace_for("cool", slow=True) is WARM and pace_for("hot", slow=True) is HOT and pace_for("molten") is COOL
    rungs = [COOL, WARM, HOT]
    assert [p.turns for p in rungs] == [True, True, False]
    assert COOL.reply_tokens > WARM.reply_tokens > HOT.reply_tokens >= 40
    assert COOL.quiet_s <= WARM.quiet_s <= HOT.quiet_s and COOL.turn_gap_s <= WARM.turn_gap_s
    assert [p.small_first for p in rungs] == [False, False, True]
    assert COOL.answer == "" and WARM.answer and HOT.answer


def test_background_turns_wait_longer_when_warm_and_pause_when_hot(rig_factory, clock):
    talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED),))
    life = talk.rig.life
    assert life.dials.propose("thoughtfulness", 1.0, why="this Pebble stops to think about anything").ok
    heat = Fixed("warm")
    talk.conv.heat = heat

    async def go():
        await talk.say("ina", "Pebble, what did you do this morning?")
        await talk.settle(31.0)
        assert not talk.conv.live()
        before = life.turns_run
        life.events.add(clock.now(), "a door closed")
        await life.beat()
        assert life.turns_run == before and life.skips.get("the phone is warm, so turns wait for a longer quiet") == 1
        await talk.settle(30.0)
        await life.beat()
        assert life.turns_run == before + 1
        life.events.add(clock.now(), "a cup moved")
        await life.beat()
        assert life.turns_run == before + 1 and life.skips.get("the phone is warm, so turns are spaced out") == 1
        heat.level = "hot"
        await talk.settle(61.0)
        await life.beat()
        assert life.turns_run == before + 1 and life.skips.get("the phone is hot") == 1 and life.events.peek()
        life.events.add(clock.now(), "someone asked you to stop", major=True)
        await life.beat()
        assert life.turns_run == before + 2
        heat.level = "cool"
        await talk.settle(60.0)
        life.events.add(clock.now(), "a bird sang")
        await life.beat()
        assert life.turns_run == before + 3

    asyncio.run(go())


def test_when_hot_the_talk_beat_waits_until_the_phone_cools(rig_factory, clock):
    talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED),))
    life = talk.rig.life
    heat = Fixed("hot")
    talk.conv.heat = heat

    async def go():
        await talk.say("ina", "Pebble, what did you do this morning?")
        life.trigger.clear()
        await talk.settle(90.0)
        assert talk.conv.beat_due and not life.trigger.is_set()
        heat.level = "cool"
        await talk.settle(0.2)
        assert life.trigger.is_set()

    asyncio.run(go())


class Lengths(ScriptedMind):
    def __init__(self):
        super().__init__(replies=["Fine, thanks."] * 10)
        self.asked: list = []

    async def stream(self, messages, purpose="turn", max_tokens=None, options=None, tools=None):
        self.asked.append((max_tokens, messages[-1]["content"]))
        async for piece in super().stream(messages, purpose, max_tokens, options, tools):
            yield piece


@pytest.mark.parametrize("level,tokens,answer", [
    ("cool", 90, "out loud now.\n"),
    ("warm", 70, "out loud now, in one or two short sentences.\n"),
    ("hot", 50, "out loud now, in one short sentence.\n"),
])
def test_replies_get_a_little_shorter_as_the_phone_heats_up(rig_factory, clock, level, tokens, answer):
    talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED),))
    talk.conv.heat = Fixed(level)
    mind = Lengths()
    talk.rig.turns.mind = mind
    asyncio.run(talk.say("ina", "Pebble, what did you do this morning?"))
    assert "Fine, thanks." in talk.spoken() and talk.conv.stats.replies == 1
    assert mind.asked and all(asked == tokens and answer in content for asked, content in mind.asked)


def test_when_hot_the_small_model_writes_the_holds(rig_factory, clock):
    sub = ScriptedMind(holds=["Ooh, the song question.", "Still on the song."])
    talk, lines, holds = th.asked(rig_factory, clock, 4.0, sub=sub, prepare=lambda t: setattr(t.conv, "heat", Fixed("hot")))
    assert [r["purpose"] for r in sub.requests][:1] == ["hold"]
    assert lines[0] == "Ooh, the song question." and th.ANSWER in lines
    cool = ScriptedMind(holds=["Ooh, the song question."])
    talk, lines, holds = th.asked(rig_factory, clock, 4.0, sub=cool)
    assert lines[0] != "Ooh, the song question."


def test_heat_never_slows_a_stop(tmp_path, clock):
    lines, waits, rigs = {}, {}, []
    for level in ("cool", "hot"):
        def make(level=level):
            rig = Rig(tmp_path / level, clock)
            rigs.append(rig)
            return rig

        talk = tc.Talk(make, clock, people=(("Ina", TRUSTED),))
        talk.conv.heat = Fixed(level)
        asyncio.run(talk.say("ina", "Pebble, stop listening"))
        lines[level] = talk.spoken()
        waits[level] = talk.conv.stats.latencies
    for rig in rigs:
        rig.close()
    assert lines["hot"] == lines["cool"] and lines["hot"][0] == "Okay."
    assert len(waits["hot"]) == len(waits["cool"]) == 1 and abs(waits["hot"][0] - waits["cool"][0]) < 1e-6
