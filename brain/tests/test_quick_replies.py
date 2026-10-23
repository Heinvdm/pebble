import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import run, small_model

from pebble.life.turn import REPLY_GUIDE
from pebble.link.protocol import Event
from pebble.mind.base import MindInterrupted, MindReply
from pebble.mind.llama import LlamaServerMind
from pebble.mind.profile import ModelProfile
from pebble.mind.prompt import TURN_GUIDE
from pebble.mind.scripted import ScriptedMind
from pebble.self.tidy import tidy

TOOLS = ["look", "set_face", "remember", "read_sensors"]
SHOWN = ["face", "remember", "status"]


def observation(index: int) -> str:
    return f"Time: Thursday 15 October 2026, 12:{index:02d}\nStatus: battery 80%\nEvents: event number {index}"


async def collect(pieces) -> str:
    return "".join([piece async for piece in pieces])


def test_a_reply_starts_like_the_turn_before_it(rig_factory):
    rig = rig_factory(model=small_model(reply_shares_turn=True))
    values = rig.books.values.describe()
    run(rig.turns.run(observation(1), TOOLS, "newborn", values))
    turn = [r for r in rig.mind.requests if r["purpose"] == "turn"][-1]
    said = run(collect(rig.turns.reply('Ina is talking to you: "how are you?"', "newborn", values)))
    reply = [r for r in rig.mind.requests if r["purpose"] == "reply"][-1]
    assert reply["tools"] == turn["tools"] == SHOWN
    assert reply["messages"][: len(turn["messages"])] == turn["messages"]
    assert TURN_GUIDE in reply["messages"][0]["content"] and REPLY_GUIDE not in reply["messages"][0]["content"]
    assert reply["messages"][-1]["content"].startswith(REPLY_GUIDE)
    assert reply["messages"][-1]["content"].endswith('Ina is talking to you: "how are you?"')
    rig.turns.reply_done(said)
    assert not any(REPLY_GUIDE in (m.get("content") or "") for m in rig.history.messages())
    run(rig.turns.run(observation(2), TOOLS, "newborn", values))
    after = [r for r in rig.mind.requests if r["purpose"] == "turn"][-1]
    assert after["messages"][: len(turn["messages"])] == turn["messages"]


def test_without_sharing_a_reply_has_its_own_guide_and_no_tools(rig_factory):
    rig = rig_factory()
    values = rig.books.values.describe()
    run(rig.turns.run(observation(1), TOOLS, "newborn", values))
    run(collect(rig.turns.reply('Ina is talking to you: "hi"', "newborn", values)))
    reply = [r for r in rig.mind.requests if r["purpose"] == "reply"][-1]
    assert reply["tools"] == []
    assert REPLY_GUIDE in reply["messages"][0]["content"] and TURN_GUIDE not in reply["messages"][0]["content"]


def test_a_shared_reply_before_any_turn_falls_back_to_its_own_guide(rig_factory):
    rig = rig_factory(model=small_model(reply_shares_turn=True))
    run(collect(rig.turns.reply('Ina is talking to you: "hi"', "newborn", rig.books.values.describe())))
    reply = [r for r in rig.mind.requests if r["purpose"] == "reply"][-1]
    assert reply["tools"] == [] and REPLY_GUIDE in reply["messages"][0]["content"]


class SlowTurns(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, *args):
        return

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        SlowTurns.seen.append(payload["messages"][-1]["content"])
        if payload["messages"][-1]["content"] == "think about the day":
            time.sleep(4.0)
        body = {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Hello!"}}]}
        if payload.get("stream"):
            data = ("data: " + json.dumps({"choices": [{"delta": {"content": "Hello!"}, "finish_reason": None}]}) + "\n\ndata: [DONE]\n\n").encode()
            content_type = "text/event-stream"
        else:
            data = json.dumps(body).encode()
            content_type = "application/json"
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            return


@pytest.fixture
def slow_llama():
    SlowTurns.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowTurns)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize("streamed", [False, True])
def test_someone_talking_puts_off_a_background_turn(slow_llama, streamed):
    mind = LlamaServerMind(ModelProfile.from_dict({"name": "slow", "endpoint": f"http://127.0.0.1:{slow_llama}", "timeout_s": 20}))

    async def go():
        turn = asyncio.create_task(mind.chat([{"role": "user", "content": "think about the day"}], purpose="turn"))
        await asyncio.sleep(0.4)
        start = time.monotonic()
        if streamed:
            said = await collect(mind.stream([{"role": "user", "content": "hello Pebble"}], purpose="reply"))
        else:
            said = (await mind.chat([{"role": "user", "content": "hello Pebble"}], purpose="reply")).text
        took = time.monotonic() - start
        with pytest.raises(MindInterrupted):
            await turn
        return said, took, time.monotonic() - start

    said, took, until_turn_ended = run(go())
    assert said == "Hello!"
    assert took < 2.0
    assert until_turn_ended < 2.0
    assert SlowTurns.seen[:2] == ["think about the day", "hello Pebble"]


def test_a_background_call_alone_is_never_put_off(slow_llama):
    mind = LlamaServerMind(ModelProfile.from_dict({"name": "slow", "endpoint": f"http://127.0.0.1:{slow_llama}", "timeout_s": 20}))

    async def go():
        summary = asyncio.create_task(mind.chat([{"role": "user", "content": "notes"}], purpose="summary"))
        drawing = await mind.chat([{"role": "user", "content": "draw"}], purpose="scene")
        return (await summary).text, drawing.text

    assert run(go()) == ("Hello!", "Hello!")
    assert mind.interrupt_background() == 0


class PutOff(ScriptedMind):
    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        if purpose in ("turn", "summary"):
            raise MindInterrupted("put off")
        return await super().chat(messages, tools, purpose, max_tokens, options)


def test_a_put_off_turn_is_not_a_failure_and_keeps_its_events(rig_factory):
    rig = rig_factory(mind=PutOff())
    rig.life._mind_ready = True
    run(rig.life.read_sensors())
    rig.life.notice(Event("obstacle", ("45",)))
    run(rig.life.beat())
    assert rig.life._mind_ready
    assert rig.life.turns_run == 0
    assert rig.life.events.peek()
    result = run(rig.turns.run(observation(3), TOOLS, "newborn", ""))
    assert result.interrupted and result.error is None and not result.ran


def test_a_full_window_never_waits_on_the_mind_and_a_put_off_note_change_waits_for_later(rig_factory):
    rig = rig_factory(mind=PutOff(), model=small_model(compact_at_tokens=1500, keep_tokens_after_compaction=300))
    for index in range(3):
        rig.history.add_turn([{"role": "user", "content": observation(index)}, {"role": "assistant", "content": "ok"}], "2026-10-15T12:00:00+00:00")
    result = run(rig.history.compact(rig.mind, "2026-10-15T12:30:00+00:00"))
    assert result.folded >= 1 and not result.used_mind and rig.history.compactions == 1
    rig.books.memory.remember("The plant by the window likes the morning sun.", "2026-10-15T12:00:00+00:00")
    notes = rig.history.notes
    report = run(tidy(notes, rig.life.memory.recall.stream, rig.life.memory.recall.embedder, rig.mind))
    assert report["looked"] == 0 and notes.items == [] and notes.tidied_t == 0.0


def test_the_profile_flags_load(rig_factory):
    from pebble.body.profile import resolve_profile

    gemma = ModelProfile.load(resolve_profile("gemma4_e4b", "model"))
    assert not gemma.reply_shares_turn
    assert gemma.steady_tools and gemma.people_in_message and gemma.read_ahead
    assert not ModelProfile.from_dict({"name": "x"}).reply_shares_turn
    assert isinstance(MindReply("x"), MindReply)


def test_a_steady_tool_list_is_the_same_every_turn_and_says_what_is_off(rig_factory):
    from pebble.mind.scripted import Act

    mind = ScriptedMind(acts=[Act("Roll a bit.", (("do", {"words": "roll forward a little"}),), "Done.")])
    rig = rig_factory(mind=mind, model=small_model(steady_tools=True))
    values = rig.books.values.describe()
    run(rig.turns.run(observation(1), TOOLS + ["move"], "newborn", values))
    result = run(rig.turns.run(observation(2), TOOLS, "newborn", values))
    turns = [r for r in mind.requests if r["purpose"] == "turn"]
    assert turns[0]["tools"] == turns[-1]["tools"] == rig.registry.names()
    first = turns[-1]["messages"][-1] if turns[-1]["messages"][-1]["role"] == "user" else next(m for m in reversed(turns[-1]["messages"]) if m["role"] == "user")
    assert "Tools you can't use just now: " in first["content"] and "do" in first["content"].split("Tools you can't use just now: ")[1]
    assert result.calls[0]["name"] == "do" and result.calls[0]["result"]["error"] == "move is not something you can do just now"


def test_without_a_steady_list_only_the_allowed_tools_are_shown(rig_factory):
    rig = rig_factory()
    run(rig.turns.run(observation(1), TOOLS, "newborn", rig.books.values.describe()))
    turn = [r for r in rig.mind.requests if r["purpose"] == "turn"][-1]
    assert turn["tools"] == SHOWN
    assert "can't use just now" not in turn["messages"][-1]["content"]


class Trickle(ScriptedMind):
    def __init__(self, pieces, gate=None):
        super().__init__()
        self.pieces = list(pieces)
        self.gate = gate

    async def stream(self, messages, purpose="turn", max_tokens=None, options=None, tools=None):
        self.requests.append({"purpose": purpose, "messages": messages})
        for index, piece in enumerate(self.pieces):
            if index == 1 and self.gate is not None:
                await asyncio.wait_for(self.gate.wait(), 5.0)
            yield piece


def smith(mind):
    from pebble.mind.wordsmith import Wordsmith

    return Wordsmith(mind, lambda kind: None)


def test_the_wordsmith_speaks_its_first_sentence_before_it_has_finished():
    async def go():
        gate = asyncio.Event()
        heard = []

        async def speak(part):
            heard.append(part)
            gate.set()

        phrased = await smith(Trickle(["Sure thing. ", "I'll be right there.\nAnd more."], gate)).phrase("I am coming", speak=speak)
        return phrased, heard

    phrased, heard = run(go())
    assert heard == ["Sure thing.", "I'll be right there."]
    assert phrased.spoken and phrased.source == "creative" and phrased.text == "Sure thing. I'll be right there."


def test_the_wordsmith_falls_back_to_the_draft_when_it_cannot_stream_safely():
    heard = []

    async def speak(part):
        heard.append(part)

    numbers = ScriptedMind(words=["It is 20 past."])
    phrased = run(smith(numbers).phrase("It is 12:20.", speak=speak))
    assert heard == [] and not phrased.spoken
    assert numbers.requests[-1]["purpose"] == "talk"
    invented = run(smith(Trickle(["Back in 5 minutes."])).phrase("Back soon.", speak=speak))
    assert heard == [] and not invented.spoken and invented.text == "Back soon."
    empty = run(smith(Trickle([])).phrase("Hello.", speak=speak))
    assert not empty.spoken and empty.text == "Hello."


def test_the_say_tool_and_activity_lines_stream_through_the_voice(rig_factory):
    rig = rig_factory()
    rig.context.phrase = smith(Trickle(["Hello there. ", "Nice to see you."])).phrase
    result = run(rig.registry.call("say", {"text": "hello"}))
    assert result["phrasing"] == "creative" and result["engine"] == "transcript-only"
    assert result["words"] == "Hello there. Nice to see you."
    assert rig.voice.lines[-2:] == ["Hello there.", "Nice to see you."]
    rig.parts.phrase = smith(Trickle(["Not now, ", "I'm a bit busy."])).phrase
    run(rig.life._speak("I can't right now", True))
    assert rig.voice.lines[-1] == "Not now, I'm a bit busy."
    count = len(rig.voice.lines)
    rig.parts.phrase = smith(Trickle([])).phrase
    run(rig.life._speak("I can't right now", True))
    assert rig.voice.lines[count:] == ["I can't right now"]


def test_no_turn_runs_during_a_live_conversation_and_the_thought_comes_back(rig_factory, clock):
    import test_conversation as tc
    from pebble.people.trust import TRUSTED

    talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED),))
    life = talk.rig.life
    gave = []
    life.p.mind.give_way = lambda: gave.append(clock.monotonic()) or 1

    async def go():
        run_turns = life.turns_run
        await talk.say("ina", "Pebble, how are you today?")
        assert gave
        life.notice(Event("obstacle", ("45",)))
        await life.beat()
        assert life.turns_run == run_turns and life.skips.get("someone is talking with Pebble") == 1
        assert life.events.peek()
        await talk.settle(31.0)
        assert not talk.conv.live()
        await life.beat()
        assert life.turns_run == run_turns + 1

    asyncio.run(go())


def test_who_is_here_rides_in_the_message_and_the_household_in_the_system_text(rig_factory, clock):
    from pebble.people.fake import fake_print

    rig = rig_factory(model=small_model(reply_shares_turn=True, people_in_message=True))
    for name, relation in (("Ina", "owner"), ("Sam", "friend")):
        person = rig.books.people.meet(clock.now(), voice=fake_print(name.lower(), "voice"), face=fake_print(name.lower(), "face"))
        person.set_name(name)
        person.relationship = relation
    rig.books.save("people")
    values = rig.books.values.describe()
    alone = "People here now:\n- Ina (owner); may ask you for anything"
    both = alone + "\n- Sam (friend); may ask you for small things"
    run(rig.turns.run(observation(1), TOOLS, "newborn", values, people=alone))
    first = [r for r in rig.mind.requests if r["purpose"] == "turn"][-1]
    run(rig.turns.run(observation(2), TOOLS, "newborn", values, people=both))
    second = [r for r in rig.mind.requests if r["purpose"] == "turn"][-1]
    assert first["messages"][0] == second["messages"][0]
    system = first["messages"][0]["content"]
    assert "People you know: Ina (owner), Sam (friend)." in system and "People here now" not in system
    asked = next(m for m in reversed(second["messages"]) if m["role"] == "user")
    assert asked["content"].startswith(both) and asked["content"].endswith(observation(2))
    assert not any("People here now" in (m.get("content") or "") for m in rig.history.messages())
    run(collect(rig.turns.reply('Sam is talking to you: "hi"', "newborn", values, people=both)))
    reply = [r for r in rig.mind.requests if r["purpose"] == "reply"][-1]
    assert reply["messages"][0] == second["messages"][0]
    assert reply["messages"][-1]["content"].startswith(both) and reply["messages"][-1]["content"].endswith('Sam is talking to you: "hi"')
