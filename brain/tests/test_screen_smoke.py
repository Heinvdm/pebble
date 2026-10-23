import http.client
import json
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from pebble.chaos.replay import chaos_records, replay_records

BRAIN = Path(__file__).resolve().parents[1]
URL = re.compile(r"face page: http://127\.0\.0\.1:(\d+)/")


class Running:
    def __init__(self, args: list[str]):
        self.process = subprocess.Popen([sys.executable, "-m", "pebble", *args], cwd=BRAIN, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
        self.lines: queue.Queue = queue.Queue()
        self.seen: list[str] = []
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.process.stderr:
            self.lines.put(line)
        self.lines.put(None)

    def wait_for(self, pattern: re.Pattern, timeout: float = 60.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=0.5)
            except queue.Empty:
                continue
            if line is None:
                break
            self.seen.append(line)
            match = pattern.search(line)
            if match:
                return match
        raise AssertionError("never saw " + pattern.pattern + "\n" + "".join(self.seen[-40:]))

    def finish(self, timeout: float = 90.0) -> int:
        code = self.process.wait(timeout=timeout)
        while True:
            line = self.lines.get(timeout=5)
            if line is None:
                break
            self.seen.append(line)
        return code


def fetch(port: int, path: str) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, body


def first_event(port: int) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", "/events")
    response = connection.getresponse()
    text = ""
    while "\n\n" not in text.split("retry: 1500\n\n", 1)[-1]:
        text += response.fp.readline().decode()
    connection.close()
    return text


def test_the_brain_serves_the_face_page_while_it_runs(tmp_path):
    self_dir = tmp_path / "self"
    running = Running(["--sim", "--mind", "scripted", "--dry-run", "--screen", "--screen-port", "0", "--beats", "6", "--heartbeat", "0.5", "--seed", "4", "--self", str(self_dir)])
    port = int(running.wait_for(URL).group(1))
    status, body = fetch(port, "/")
    assert status == 200 and b"<canvas" in body
    assert "event: face" in first_event(port)
    assert running.finish() == 0, "".join(running.seen[-40:])
    assert "Traceback" not in "".join(running.seen)
    blackbox = self_dir / "logs" / "blackbox.jsonl"
    kinds = [json.loads(line)["kind"] for line in blackbox.read_text(encoding="utf-8").splitlines()]
    assert kinds[0] == "start" and "chaos" in kinds
    start = json.loads(blackbox.read_text(encoding="utf-8").splitlines()[0])
    assert start["chaos_seed"] == 4
    results = replay_records(chaos_records(blackbox))
    assert results and all(result.same for result in results)
    assert (self_dir / "gallery.json").exists() and (self_dir / "ideas.json").exists()


def test_the_screen_demo_runs_without_a_body_or_a_model(tmp_path):
    running = Running(["--screen-demo", "--screen-port", "0", "--seconds", "4", "--self", str(tmp_path / "nobody")])
    port = int(running.wait_for(URL).group(1))
    status, body = fetch(port, "/")
    assert status == 200
    assert json.loads(fetch(port, "/state")[1])["demo"] is True
    assert "event: face" in first_event(port)
    assert running.finish() == 0, "".join(running.seen[-40:])
    assert not (tmp_path / "nobody").exists()
