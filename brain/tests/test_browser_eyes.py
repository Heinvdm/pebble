import asyncio
import http.client
import json
import re

import pytest
from conftest import run

from pebble.clock import FakeClock
from pebble.seams.sight import Sight
from pebble.web.eyes import BrowserEyes, Latency, sight_from_dict
from pebble.web.hub import Hub
from pebble.web.server import PAGE, WORKER, FaceServer, render_page
from pebble.web.webface import WebFace


class RecordingHub(Hub):
    def __init__(self):
        super().__init__()
        self.events = []

    def publish(self, event, data):
        self.events.append((event, data))
        super().publish(event, data)


def frame(camera="front", seq=0, t=10.0, sent=None, people=None, tags=None, **extra):
    body = {"sid": "abc", "seq": seq, "camera": camera, "fov_h_deg": 70, "t": t, "sent": t + 0.05 if sent is None else sent, "people": people or [], "tags": tags or []}
    body.update(extra)
    return body


PERSON = {"bearing_deg": -12.5, "elevation_deg": 4.0, "height_frac": 0.42, "width_frac": 0.2, "score": 0.83, "face": True, "track": 5}
TAG = {"id": 0, "bearing_deg": 3.0, "distance_m": 0.41, "yaw_deg": 19.5, "score": 0.9}


def test_a_page_report_becomes_a_sight():
    sight = sight_from_dict(frame(people=[PERSON], tags=[TAG]), 123.0)
    assert isinstance(sight, Sight) and sight.at == 123.0 and sight.camera == "front" and sight.fov_h_deg == 70
    person = sight.people[0]
    assert (person.bearing_deg, person.elevation_deg, person.height_frac, person.face, person.track) == (-12.5, 4.0, 0.42, True, 5)
    assert sight.tags[0].distance_m == 0.41 and sight.tags[0].yaw_deg == 19.5
    clamped = sight_from_dict(frame(people=[dict(PERSON, height_frac=3, score=-1, bearing_deg=400)]), 1.0).people[0]
    assert clamped.height_frac == 1.0 and clamped.score == 0.0 and clamped.bearing_deg == 90.0
    assert len(sight_from_dict(frame(people=[PERSON] * 40), 1.0).people) == 12


@pytest.mark.parametrize("bad", [
    frame(camera="side"),
    frame(people=[dict(PERSON, bearing_deg="left")]),
    frame(people=[dict(PERSON, score=None)]),
    frame(people=[dict(PERSON, track=1.5)]),
    frame(tags=[dict(TAG, id=-1)]),
    frame(tags=[dict(TAG, distance_m=True)]),
    frame(people="nobody"),
    dict(frame(), fov_h_deg=None),
    [],
])
def test_broken_reports_are_refused(bad):
    with pytest.raises(ValueError):
        sight_from_dict(bad, 1.0)


def test_latency_is_taken_off_using_the_quickest_post_seen():
    latency = Latency()
    assert latency.measure("a", 10.0, 10.08, 500.0) == pytest.approx(0.08)
    assert latency.measure("a", 10.5, 10.55, 500.47) == pytest.approx(0.05)
    assert latency.measure("a", 11.0, 11.06, 501.04) == pytest.approx(0.12)
    assert latency.measure("a", 12.0, 12.01, 501.92) == pytest.approx(0.01)
    assert latency.measure("b", 0.0, 0.01, 600.0) == pytest.approx(0.01)


def test_browser_eyes_keep_the_latest_sight_and_go_stale():
    clock = FakeClock()
    eyes = BrowserEyes(RecordingHub(), clock)
    assert not eyes.available and eyes.latest() is None and eyes.camera() is None
    assert eyes.seen(frame(people=[PERSON], t=50.0, sent=50.1))
    sight = eyes.latest()
    assert sight.people[0].track == 5 and eyes.camera() == "front" and eyes.available
    assert sight.at == pytest.approx(clock.now() - 0.1)
    clock.advance(0.45)
    assert eyes.latest(0.5) is None and eyes.latest(1.0) is sight
    clock.advance(2.0)
    assert not eyes.available and eyes.camera() is None
    with pytest.raises(ValueError):
        eyes.seen(frame(camera="up"))


def test_switching_cameras_waits_for_the_page():
    async def scenario():
        hub = RecordingHub()
        clock = FakeClock()
        eyes = BrowserEyes(hub, clock, switch_timeout_s=2.0)
        eyes.seen(frame())
        asking = asyncio.ensure_future(eyes.use_camera("rear"))
        await asyncio.sleep(0.01)
        assert hub.events[-1] == ("eyes", {"on": True, "camera": "rear", "seq": 1})
        eyes.seen(frame(camera="front", seq=0))
        await asyncio.sleep(0.01)
        assert not asking.done()
        eyes.report({"state": "starting", "camera": "rear", "seq": 1})
        await asyncio.sleep(0.01)
        assert not asking.done()
        eyes.seen(frame(camera="rear", seq=1))
        assert await asking is True and eyes.camera() == "rear"
        published = len(hub.events)
        assert await eyes.use_camera("rear") is True and len(hub.events) == published
        asking = asyncio.ensure_future(eyes.use_camera("front"))
        await asyncio.sleep(0.01)
        eyes.report({"state": "on", "camera": "front", "seq": 2})
        assert await asking is True
        asking = asyncio.ensure_future(eyes.use_camera("rear"))
        await asyncio.sleep(0.01)
        eyes.report({"state": "failed", "camera": "rear", "seq": 3, "reason": "no such camera on this phone"})
        assert await asking is False and eyes.status()["page"]["reason"] == "no such camera on this phone"
        assert await eyes.use_camera("side") is False

    run(scenario())


def test_a_silent_page_means_no_switch():
    async def scenario():
        eyes = BrowserEyes(RecordingHub(), FakeClock(), switch_timeout_s=0.05)
        assert await eyes.use_camera("rear") is False
        assert eyes.wanted() == "rear"

    run(scenario())


def test_turning_the_eyes_off_tells_the_page_and_forgets_what_was_seen():
    async def scenario():
        hub = RecordingHub()
        eyes = BrowserEyes(hub, FakeClock(), switch_timeout_s=5.0)
        eyes.seen(frame())
        asking = asyncio.ensure_future(eyes.use_camera("rear"))
        await asyncio.sleep(0.01)
        eyes.set_enabled(False)
        assert await asking is False
        assert hub.events[-1][1]["on"] is False and eyes.latest() is None and not eyes.available
        assert eyes.seen(frame()) is False and await eyes.use_camera("front") is False
        eyes.set_enabled(True)
        assert hub.events[-1][1]["on"] is True

    run(scenario())


def test_a_new_page_hears_what_the_eyes_should_do():
    hub = Hub()
    WebFace(hub)
    eyes = BrowserEyes(hub, FakeClock(), camera="rear")
    client = hub.subscribe()
    messages = [client.get_nowait().decode() for _ in range(2)]
    assert messages[0].startswith("event: face")
    assert messages[1].startswith("event: eyes") and '"camera":"rear"' in messages[1] and '"on":true' in messages[1]
    assert eyes.page_config()["camera"] is True


@pytest.fixture
def served():
    hub = Hub()
    WebFace(hub)
    eyes = BrowserEyes(hub, FakeClock())
    server = FaceServer(hub, "127.0.0.1", 0, eyes=eyes)
    server.start()
    yield server, eyes
    server.stop()


def call(port, method, path, body=None, content_type="application/json", host=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Content-Type": content_type}
    if host:
        headers["Host"] = host
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, dict(response.getheaders()), data


def test_the_server_takes_sight_only_from_this_phone(served):
    server, eyes = served
    body = json.dumps(frame(people=[PERSON], tags=[TAG])).encode()
    assert call(server.port, "POST", "/see", body)[0] == 204
    assert eyes.latest().tags[0].yaw_deg == 19.5
    assert call(server.port, "POST", "/see", body, host="evil.example")[0] == 403
    assert call(server.port, "POST", "/eyes", b'{"state":"on","camera":"front","seq":0}', host="evil.example:8765")[0] == 403
    assert call(server.port, "POST", "/see", b"camera=front", "text/plain")[0] == 415
    assert call(server.port, "POST", "/see", b"{oops")[0] == 400
    assert call(server.port, "POST", "/see", json.dumps(frame(camera="side")).encode())[0] == 400
    assert call(server.port, "POST", "/see", b"{" + b" " * 20000 + b"}")[0] == 413
    assert call(server.port, "POST", "/eyes", b'{"state":"on","camera":"front","seq":0}')[0] == 204
    assert call(server.port, "POST", "/eyes", b'{"state":"dancing"}')[0] == 400
    eyes.set_enabled(False)
    assert call(server.port, "POST", "/see", body)[0] == 409


def test_without_eyes_there_is_nothing_to_post_or_fetch():
    hub = Hub()
    WebFace(hub)
    server = FaceServer(hub, "127.0.0.1", 0)
    server.start()
    try:
        assert call(server.port, "POST", "/see", json.dumps(frame()).encode())[0] == 404
        assert call(server.port, "GET", "/eyes_worker.js")[0] == 404
        page = call(server.port, "GET", "/")[2].decode()
        config = json.loads(re.search(r'<script id="eyes" type="application/json">(.*?)</script>', page, re.S).group(1))
        assert config == {"camera": False}
    finally:
        server.stop()


def test_the_worker_and_vendor_files_are_served_safely(served, tmp_path):
    server, eyes = served
    eyes.vendor = tmp_path
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "m.tflite").write_bytes(b"model")
    (tmp_path / "secret.txt").write_text("no")
    status, headers, body = call(server.port, "GET", "/eyes_worker.js")
    assert status == 200 and headers["Content-Type"].startswith("text/javascript") and "connect-src 'self'" in headers["Content-Security-Policy"]
    assert body == WORKER.read_bytes()
    status, headers, body = call(server.port, "GET", "/vendor/models/m.tflite")
    assert status == 200 and body == b"model" and "immutable" in headers["Cache-Control"]
    for path in ("/vendor/../server.py", "/vendor/%2e%2e/server.py", "/vendor/secret.txt", "/vendor/models/", "/vendor/models/../m.tflite", "/vendor//etc/passwd", "/vendor/C:/x.js"):
        assert call(server.port, "GET", path)[0] == 404, path
    page = call(server.port, "GET", "/")
    config = json.loads(re.search(r'<script id="eyes" type="application/json">(.*?)</script>', page[2].decode(), re.S).group(1))
    assert config["camera"] is True and config["vendor"]["vision_wasm"].startswith("/vendor/") and config["tag"] == {"id": 0, "size_m": 0.048}
    assert "'wasm-unsafe-eval'" in page[1]["Content-Security-Policy"] and "connect-src 'self'" in page[1]["Content-Security-Policy"]


def test_the_page_and_worker_load_nothing_from_outside_and_carry_no_comments():
    page = PAGE.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    for source in (page.split("<script>", 1)[1], worker):
        assert not re.search(r"(^|[\s;{}])//", source)
        assert "/*" not in source
        assert not re.search(r"https?://", source)
    assert "importScripts" in worker and "Pebble's eyes only load files from Pebble" in worker
    rendered = render_page(eyes={"camera": True, "vendor": {"x": "</script>"}}).decode()
    assert "</script>\"" not in rendered
