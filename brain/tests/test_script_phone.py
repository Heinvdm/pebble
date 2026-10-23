import json
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from conftest import run

from pebble.android import bridge as bridge_module
from pebble.android.testing import script_dream
from pebble.script import live as live_module
from pebble.script.check import read
from pebble.script.dream import dream
from pebble.script.evaluate import Call, Crash, Done, Finish
from pebble.script.host import Local, Phone, Process
from pebble.script.program import Limits
from pebble.script.scene import ScriptScene

BRAIN = Path(__file__).resolve().parents[1]
STARTERS = BRAIN / "pebble" / "script" / "starters"
CAT = (STARTERS / "cat_counter.py").read_text(encoding="utf-8")
HUNG = 'ABOUT = "a test"\nUSES = ["say"]\nUNTIL = "ongoing"\n\n\ndef on_start():\n    n = 0\n    while True:\n        n += 1\n'
DAY = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)


class PipeLink:
    def __init__(self):
        self.procs = {}
        self.lines = {}
        self.opened = 0
        self.closed = []
        self.sent = []

    def scriptOpen(self, memory_mb):
        self.opened += 1
        handle = f"script-{self.opened}"
        proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", "-m", "pebble.script.host", "--memory-mb", "256"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=str(BRAIN), text=True, encoding="utf-8",
        )
        lines = queue.Queue()

        def read():
            for line in proc.stdout:
                lines.put(line)
            lines.put(None)

        threading.Thread(target=read, daemon=True).start()
        self.procs[handle] = proc
        self.lines[handle] = lines
        return handle

    def scriptAsk(self, handle, line, wait_ms):
        proc = self.procs.get(handle)
        if proc is None:
            return '{"link":"closed"}'
        self.sent.append(json.loads(line).get("op"))
        try:
            proc.stdin.write(line + "\n")
            proc.stdin.flush()
        except OSError:
            self.scriptClose(handle)
            return '{"link":"died"}'
        try:
            answer = self.lines[handle].get(timeout=wait_ms / 1000.0)
        except queue.Empty:
            self.scriptClose(handle)
            return '{"link":"timeout"}'
        if answer is None:
            self.scriptClose(handle)
            return '{"link":"died"}'
        return answer.strip()

    def scriptClose(self, handle):
        proc = self.procs.pop(handle, None)
        self.lines.pop(handle, None)
        if proc is None:
            return
        self.closed.append(handle)
        proc.kill()
        proc.wait(5)

    def close_all(self):
        for handle in list(self.procs):
            self.scriptClose(handle)


class DeadLink:
    def __init__(self, answer):
        self.answer = answer
        self.closed = []

    def scriptOpen(self, memory_mb):
        return "script-1"

    def scriptAsk(self, handle, line, wait_ms):
        return self.answer

    def scriptClose(self, handle):
        self.closed.append(handle)


def test_the_phone_engine_speaks_the_hosts_json_lines():
    link = PipeLink()

    async def go():
        engine = Phone(link=link)
        assert await engine.load(read(CAT).program) is None
        out = await engine.go("on_start", [])
        assert isinstance(out, Call) and out.name == "keep"
        out = await engine.reply(None)
        assert isinstance(out, Done)
        out = await engine.go("on_at", ["21:00"])
        assert isinstance(out, Call) and out.name == "kept"
        out = await engine.reply(3)
        assert isinstance(out, Call) and out.name == "say_to" and out.args["text"] == "The cat came through the lounge 3 times today."
        out = await engine.reply("done")
        assert isinstance(out, Finish)
        handle = engine.pid
        await engine.close()
        return handle, engine.pid

    try:
        handle, after = run(go(), 60.0)
    finally:
        link.close_all()
    assert handle == "script-1" and after is None and link.closed == ["script-1"]
    assert link.sent == ["load", "run", "reply", "run", "reply", "reply"]


def test_a_silent_phone_process_is_stopped_and_counts_as_a_crash():
    link = PipeLink()

    async def go():
        engine = Phone(Limits(ms=None, steps=10**12), wait_s=1.0, link=link)
        assert await engine.load(read(HUNG).program) is None
        started = time.monotonic()
        out = await engine.go("on_start", [])
        return out, time.monotonic() - started, engine.pid

    try:
        out, took, handle = run(go(), 60.0)
    finally:
        link.close_all()
    assert isinstance(out, Crash) and out.kind == "limit" and out.what == "time" and took < 10.0
    assert handle is None and link.closed == ["script-1"]


def test_a_phone_process_that_dies_or_cannot_start_is_a_crash():
    async def go():
        died = Phone(link=DeadLink('{"link":"died"}'))
        first = await died.load(read(CAT).program)
        nobody = Phone(link=DeadLink(""))
        nobody.link.scriptOpen = lambda memory_mb: ""
        second = await nobody.load(read(CAT).program)
        garbled = Phone(link=DeadLink("not json"))
        third = await garbled.load(read(CAT).program)
        return first, second, third, died.pid, garbled.link.closed

    first, second, third, handle, closed = run(go(), 30.0)
    assert isinstance(first, Crash) and first.kind == "error" and "died" in first.text and handle is None
    assert isinstance(second, Crash) and "could not start" in second.text
    assert isinstance(third, Crash) and third.kind == "error" and closed == ["script-1"]


def test_without_the_apps_bridge_the_phone_engine_says_so():
    bridge_module.install(None)

    async def go():
        return await Phone().load(read(CAT).program)

    out = run(go(), 30.0)
    assert isinstance(out, Crash) and "could not start" in out.text


def test_a_starter_dreams_the_same_through_the_phone_engine():
    link = PipeLink()
    try:
        out = json.loads(script_dream(link, "cat_counter"))
    finally:
        link.close_all()
    assert out["passed"] and out["here_passed"] and out["same_calls"] and out["same_said"], out
    assert out["engine"] == "phone" and out["closed"] and link.opened == 1


def test_on_the_phone_the_scripts_choose_the_phone_engine(monkeypatch):
    class Holder:
        engine = "process"

    make = live_module.Scripts.make_engine
    monkeypatch.setattr(live_module, "on_phone", lambda: True)
    assert isinstance(make(Holder()), Phone)
    Holder.engine = "local"
    assert isinstance(make(Holder()), Local)
    monkeypatch.setattr(live_module, "on_phone", lambda: False)
    Holder.engine = "process"
    assert isinstance(make(Holder()), Process)
    Holder.engine = "phone"
    assert isinstance(make(Holder()), Phone)


def test_on_the_phone_programs_go_live_through_the_phone_engine(monkeypatch):
    import tempfile

    monkeypatch.setattr(live_module, "on_phone", lambda: True)
    assert live_module.live_here()
    link = PipeLink()
    bridge_module.install(link)
    holder = tempfile.TemporaryDirectory(prefix="pebble-script-phone-")

    async def go():
        show = ScriptScene(Path(holder.name) / "self", DAY)
        await show.setup()
        try:
            show.scripts.engine = "process"
            entry = await show.deploy("simon_says")
            await show.scene.run(10.0)
            kinds = [s.engine.kind for s in show.scripts.sessions.values()]
            return sorted(show.scripts.sessions), show.said(), entry["status"], kinds
        finally:
            await show.close()

    try:
        live, said, status, kinds = run(go(), 120.0)
    finally:
        bridge_module.install(None)
        link.close_all()
        holder.cleanup()
    assert live == ["simon_says"] and kinds == ["phone"]
    assert any("Simon" in line for line in said), said
    assert link.opened >= 1
