import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import run

import test_conversation as tc
from pebble.mind.lawful import LawfulMind
from pebble.mind.llama import LlamaServerMind
from pebble.mind.profile import ModelProfile
from pebble.people.trust import TRUSTED

TOOLS = ["look", "set_face", "remember", "read_sensors"]


def tokens_of(payload: dict) -> list[str]:
    out = []
    for tool in payload.get("tools") or []:
        out += json.dumps(tool, sort_keys=True).split()
    for message in payload.get("messages") or []:
        content = message.get("content")
        if isinstance(content, list):
            content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
        out += [f"<{message.get('role')}>"] + str(content or "").split() + [f"</{message.get('role')}>"]
        for call in message.get("tool_calls") or []:
            out += json.dumps(call, sort_keys=True).split()
    return out + ["<model>"]


class OneSlot(BaseHTTPRequestHandler):
    cached: list = []
    log: list = []
    lock = threading.Lock()

    def log_message(self, *args):
        return

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        prompt = tokens_of(payload)
        with OneSlot.lock:
            same = 0
            for a, b in zip(OneSlot.cached, prompt):
                if a != b:
                    break
                same += 1
            last = (payload.get("messages") or [{}])[-1].get("content") or ""
            OneSlot.log.append({"read": len(prompt) - same, "tokens": len(prompt), "warm": payload.get("max_tokens") == 1, "stream": bool(payload.get("stream")), "speech": "is talking to you:" in str(last)})
            OneSlot.cached = prompt + [f"<written {len(OneSlot.log)}>"]
        if payload.get("stream"):
            data = ("data: " + json.dumps({"choices": [{"delta": {"content": "Something calm, I think."}, "finish_reason": None}]}) + "\n\ndata: [DONE]\n\n").encode()
            kind = "text/event-stream"
        else:
            data = json.dumps({"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Hmm."}}]}).encode()
            kind = "application/json"
        try:
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            return


@pytest.fixture
def one_slot():
    OneSlot.cached = []
    OneSlot.log = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), OneSlot)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def conversation_with(rig_factory, clock, port: int, read_ahead: bool):
    talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED),))
    profile = ModelProfile.from_dict({
        "name": "one-slot",
        "endpoint": f"http://127.0.0.1:{port}",
        "context_tokens": 8192,
        "compact_at_tokens": 3500,
        "keep_tokens_after_compaction": 1000,
        "timeout_s": 20,
        "reply_shares_turn": True,
        "people_in_message": True,
        "read_ahead": read_ahead,
    })
    mind = LawfulMind(LlamaServerMind(profile))
    talk.rig.history.profile = profile
    talk.rig.turns.mind = mind
    talk.rig.life.p.mind = mind
    return talk


async def caught_up(talk) -> None:
    task = talk.conv.warm_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), 10.0)


async def settle(talk, seconds: float) -> None:
    await talk.settle(seconds)
    await caught_up(talk)


async def logged(talk, start: int, wanted, bound_s: float = 10.0) -> None:
    deadline = time.monotonic() + bound_s
    while not any(wanted(entry) for entry in OneSlot.log[start:]) and time.monotonic() < deadline:
        talk.clock.advance(0.05)
        talk.conv.tick()
        await asyncio.sleep(0.01)


async def say(talk, who: str, text: str) -> None:
    for person_id in talk.ids.values():
        talk.rig.life.company.presence.saw(person_id, talk.clock.now())
    found, _ = talk.speech.events(tc.Said(who, text), talk.clock.monotonic(), speaking=talk.conv.mouth.speaking)
    for event in found:
        while talk.clock.monotonic() < event.t:
            talk.clock.advance(0.05)
            talk.conv.tick()
            await asyncio.sleep(0)
        await caught_up(talk)
        talk.conv.on_speech(event)
    await settle(talk, 1.5)


def reads_after_speech(rig_factory, clock, port: int, read_ahead: bool) -> tuple[int, list]:
    talk = conversation_with(rig_factory, clock, port, read_ahead)

    async def go():
        for index in range(3):
            await talk.rig.turns.run(f"Time: 12:0{index}\nEvents: event number {index}", TOOLS, "newborn", talk.rig.books.values.describe())
        await settle(talk, 3.0)
        start = len(OneSlot.log)
        await say(talk, "ina", "Pebble, what is your favourite kind of music to listen to on a rainy afternoon?")
        await settle(talk, 3.0)
        await logged(talk, start, lambda entry: entry["stream"])
        return OneSlot.log[start:]

    during = asyncio.run(go())
    reply = [entry for entry in during if entry["stream"]]
    assert len(reply) == 1
    return reply[0]["read"], during


def test_reading_ahead_leaves_only_the_last_words_to_read_after_they_stop(rig_factory, clock, one_slot):
    cold, cold_log = reads_after_speech(rig_factory, clock, one_slot, False)
    assert not any(entry["warm"] for entry in cold_log)
    OneSlot.cached = []
    warm, warm_log = reads_after_speech(rig_factory, clock, one_slot, True)
    warms = [entry for entry in warm_log if entry["warm"] and entry["speech"]]
    assert len(warms) >= 2
    assert warm <= 12 < cold
    assert cold - warm >= 30


def test_reading_ahead_warms_the_next_reply_in_idle_time(rig_factory, clock, one_slot):
    talk = conversation_with(rig_factory, clock, one_slot, True)

    async def go():
        await talk.rig.turns.run("Time: 12:00\nEvents: Ina came in", TOOLS, "newborn", talk.rig.books.values.describe())
        start = len(OneSlot.log)
        await settle(talk, 2.0)
        return OneSlot.log[start:]

    after = asyncio.run(go())
    assert [entry["warm"] for entry in after] == [True]
    assert after[0]["read"] > 0


def test_speech_not_for_pebble_is_never_read_ahead(rig_factory, clock, one_slot):
    talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED), ("Sam", TRUSTED)))
    profile = ModelProfile.from_dict({"name": "x", "endpoint": f"http://127.0.0.1:{one_slot}", "read_ahead": True, "reply_shares_turn": True})
    mind = LawfulMind(LlamaServerMind(profile))
    talk.rig.history.profile = profile
    talk.rig.turns.mind = mind
    talk.rig.life.p.mind = mind

    async def go():
        await say(talk, "ina", "sam did you see where i left the car keys this morning before work")
        await settle(talk, 2.0)

    asyncio.run(go())
    assert not any(entry["warm"] and entry["speech"] for entry in OneSlot.log)
