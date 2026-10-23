import asyncio
import http.client
import json
import queue
import re
import socket

import pytest
from conftest import run

from pebble.chaos.engine import Chaos
from pebble.screen.elements import ELEMENTS, TEXT_CHARS
from pebble.screen.gallery import Gallery
from pebble.screen.stage import SceneStage
from pebble.screen.director import parse_scene
from pebble.seams.face import FACES, LogFace, Touch
from pebble.seams.voice import LipSyncVoice, TranscriptVoice
from pebble.web.demo import Demo
from pebble.web.hub import CLOSE, Hub
from pebble.web.server import PAGE, REGISTRY_MARK, FaceServer, render_page
from pebble.web.webface import WebFace


class FakeTime:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def served():
    hub = Hub()
    face = WebFace(hub)
    touches = []
    server = FaceServer(hub, "127.0.0.1", 0, touches.append, lambda: {"face": face.state.as_dict()})
    server.start()
    yield server, face, touches
    server.stop()


def get(port: int, path: str, host: str | None = None) -> tuple[int, dict, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Host": host} if host else {}
    connection.request("GET", path, headers=headers)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, dict(response.getheaders()), body


def post(port: int, path: str, body: bytes, content_type: str = "application/json") -> int:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("POST", path, body=body, headers={"Content-Type": content_type})
    status = connection.getresponse().status
    connection.close()
    return status


class SseReader:
    def __init__(self, port: int):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.sock.sendall(f"GET /events HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAccept: text/event-stream\r\n\r\n".encode())
        self.buffer = b""
        self.headers = self._until(b"\r\n\r\n").decode()

    def _until(self, mark: bytes) -> bytes:
        while mark not in self.buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("closed")
            self.buffer += chunk
        head, self.buffer = self.buffer.split(mark, 1)
        return head

    def event(self) -> tuple[str, dict]:
        while True:
            block = self._until(b"\n\n").decode()
            name, data = None, None
            for line in block.splitlines():
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
            if name:
                return name, data

    def close(self):
        self.sock.close()


def test_the_page_is_served_with_the_registry_and_no_outside_requests(served):
    server, face, _ = served
    status, headers, body = get(server.port, "/")
    page = body.decode()
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert "connect-src 'self'" in headers["Content-Security-Policy"] and "default-src 'none'" in headers["Content-Security-Policy"]
    assert REGISTRY_MARK not in page and "<canvas" in page
    registry = json.loads(re.search(r'<script id="registry" type="application/json">(.*?)</script>', page, re.S).group(1))
    assert set(registry["elements"]) == {e.name for e in ELEMENTS}
    assert not re.search(r"https?://", page)
    assert not re.search(r"<(link|img|iframe)\b", page)
    assert get(server.port, "/elements.json")[0] == 200
    assert json.loads(get(server.port, "/state")[2])["face"]["expression"] == "neutral"
    assert get(server.port, "/nope")[0] == 404


def test_the_page_draws_every_element_and_every_letter():
    source = PAGE.read_text(encoding="utf-8")
    drawn = set(re.findall(r"^R\.(\w+) = ", source, re.M))
    assert drawn == {e.name for e in ELEMENTS}
    font = re.search(r'const FONT_SRC = "([^"]+)"', source).group(1)
    glyphs = {item[0] for item in font.split(" ")}
    assert {ch.upper() for ch in TEXT_CHARS if ch != " "} <= glyphs
    expressions = set(re.findall(r"^  (\w+): \{ L: ", source, re.M))
    assert expressions == set(FACES)
    script = source.split("<script>", 1)[1]
    assert not re.search(r"(^|[\s;{}])//", script)
    assert "/*" not in source and "<!--" not in source


def test_server_sends_events_over_a_real_socket(served):
    server, face, _ = served
    reader = SseReader(server.port)
    try:
        assert "text/event-stream" in reader.headers
        name, data = reader.event()
        assert name == "face" and data["expression"] == "neutral"
        face.show("happy")
        name, data = reader.event()
        assert name == "face" and data["expression"] == "happy"
        face.scene_begin("s1", "overlay", 5, "rain")
        face.scene_line("s1", 0, {"element": "sky", "look": "night"}, "sky night")
        face.scene_end("s1")
        assert reader.event() == ("scene", {"op": "begin", "id": "s1", "mode": "overlay", "hold": 5.0, "title": "rain"})
        assert reader.event()[1]["element"] == {"element": "sky", "look": "night"}
        assert reader.event()[1] == {"op": "end", "id": "s1"}
    finally:
        reader.close()
    late = SseReader(server.port)
    try:
        assert late.event()[1]["expression"] == "happy"
        replayed = late.event()[1]
        assert replayed["op"] == "begin" and replayed["id"] == "s1" and 0 < replayed["hold"] <= 5
        assert late.event()[1]["op"] == "line"
        assert late.event()[1]["op"] == "end"
    finally:
        late.close()


def test_touches_come_back_to_the_brain(served):
    server, face, touches = served
    assert post(server.port, "/touch", json.dumps({"x": 0.25, "y": 0.5, "kind": "stroke"}).encode()) == 204
    assert touches == [Touch(0.25, 0.5, "stroke")]
    assert post(server.port, "/touch", b"{not json") == 400
    assert post(server.port, "/touch", json.dumps({"x": "a", "y": 1}).encode()) == 400
    assert post(server.port, "/touch", json.dumps({"x": 1, "y": 1, "kind": "slap"}).encode()) == 400
    assert post(server.port, "/touch", b"x=1", "application/x-www-form-urlencoded") == 415
    assert post(server.port, "/elsewhere", b"{}") == 404
    assert post(server.port, "/touch", json.dumps({"x": 7, "y": -3}).encode()) == 204
    assert touches[-1] == Touch(1.0, 0.0, "tap")


def test_other_hosts_are_refused(served):
    server, _, _ = served
    assert get(server.port, "/", host="evil.example")[0] == 403
    assert get(server.port, "/", host=f"localhost:{server.port}")[0] == 200


def test_a_busy_port_falls_back_to_a_free_one():
    from pebble.web.launch import start_face_server

    hub = Hub()
    first = start_face_server(hub, "127.0.0.1", 0, lambda t: None, lambda: {})
    second = start_face_server(Hub(), "127.0.0.1", first.port, lambda t: None, lambda: {})
    try:
        assert second.port != first.port
        assert get(second.port, "/health")[0] == 200
    finally:
        first.stop()
        second.stop()


def test_webface_pushes_state_only_when_it_changes():
    hub = Hub()
    face = WebFace(hub)
    client = hub.subscribe()
    first = client.get_nowait()
    assert b"event: face" in first
    face.show("curious")
    face.show("curious")
    face.feel(0.5, 0.2, 1.0, False)
    face.feel(0.505, 0.2, 1.0, False)
    face.motion(6.3, {"gaze": 1.2}, 77)
    face.talk(0.8)
    face.gaze(2.0, -0.5)
    face.show("evil")
    messages = []
    while True:
        try:
            messages.append(client.get_nowait())
        except queue.Empty:
            break
    payloads = [json.loads(m.decode().split("data: ", 1)[1]) for m in messages]
    assert [p["expression"] for p in payloads] == ["curious", "curious", "curious", "curious", "curious", "neutral"]
    last = payloads[-2]
    assert last["gaze"] == [1.0, -0.5] and last["talk"] == 0.8 and last["chaos"] == 6.3 and last["noise_seed"] == 77
    assert face.current == "neutral"


def test_scene_replay_expires_after_the_hold():
    clock = FakeTime()
    hub = Hub()
    face = WebFace(hub, clock)
    face.scene_begin("s9", "full", 4, "x")
    face.scene_line("s9", 0, {"element": "dot"}, "dot 1 1")
    assert len(face.replay()) == 3
    face.scene_end("s9")
    clock.now += 2
    begin = face.replay()[1][1]
    assert begin["hold"] == pytest.approx(2.0)
    clock.now += 3
    assert len(face.replay()) == 1
    face.scene_begin("s10", "full", 4)
    clock.now += 60
    assert len(face.replay()) == 1


def test_hub_drops_slow_clients_and_closes_cleanly():
    hub = Hub(max_queue=4)
    slow = hub.subscribe()
    for index in range(10):
        hub.publish("face", {"n": index})
    assert hub.clients == 0
    hub.close()
    assert hub.subscribe().get_nowait() is CLOSE
    hub.publish("face", {})


def test_stage_and_lip_sync_drive_the_face(store, clock):
    face = LogFace()
    stage = SceneStage(face)
    scene = parse_scene("sky night\nstars 10")
    scene_id = run(stage.play(scene, "overlay", 999, "night"))
    assert face.scenes[-1] == {"id": scene_id, "mode": "overlay", "hold": 60.0, "title": "night", "lines": ["sky night", "stars 10 white twinkle"], "ended": True}
    stage.line("other", scene.lines[0])
    assert len(face.scenes[-1]["lines"]) == 2

    async def speak():
        voice = LipSyncVoice(TranscriptVoice(store, clock, echo=False), face)
        await voice.say("hi")
        talking = face.state.talk
        await asyncio.sleep(0.7)
        return talking, face.state.talk, voice.lines

    talking, after, lines = run(speak())
    assert talking == 0.8 and after == 0.0 and lines == ["hi"]


def test_demo_cycles_faces_and_scenes():
    hub = Hub()
    face = WebFace(hub)
    client = hub.subscribe()
    demo = Demo(face, SceneStage(face, prefix="demo"), Gallery.template(), Chaos(seed=3), pace=0.01)

    async def go():
        stop = asyncio.Event()
        asyncio.get_running_loop().call_later(1.5, stop.set)
        await demo.run(stop)

    run(go())
    assert demo.shown >= 12 and demo.scenes >= 2
    events = []
    while True:
        try:
            events.append(client.get_nowait().decode())
        except queue.Empty:
            break
    expressions = {json.loads(e.split("data: ", 1)[1])["expression"] for e in events if e.startswith("event: face")}
    assert expressions == set(FACES)
    assert any('"op":"line"' in e for e in events)
    demo.touched(Touch(0.9, 0.1, "stroke"))
    assert face.current == "love" and face.state.gaze[0] > 0.7


def test_render_page_escapes_the_registry():
    page = render_page("<script>__PEBBLE_REGISTRY__</script>").decode()
    assert "</script>" in page and page.count("</") == 1
