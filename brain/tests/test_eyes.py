import asyncio
import hashlib
import io
import math
import threading
import time
from pathlib import Path

import pytest
from conftest import run

from pebble.clock import Clock, FakeClock
from pebble.eyes import CameraEyes, eyes_from_config, make_sources
from pebble.eyes import fetch as fetching
from pebble.eyes.geometry import Box, Candidate, Tracker, angles, combine, nearest, tag_angles
from pebble.eyes.service import camera_settings
from pebble.eyes.sources import Frame, LatestFrame, SourceError
from pebble.seams.sight import DOCK_TAG_ID, NoEyes, SeenPerson
from pebble.web.hub import Hub
from pebble.web.look import LookPush

MODELS = fetching.MODELS
PORTRAIT = MODELS / "samples" / "portrait.jpg"


def person(bearing=0.0, height=0.5, face=False, track=None):
    return SeenPerson(bearing, 0.0, height, height / 2, 0.9, face, track)


def test_angles_follow_the_field_of_view():
    assert angles(0.5, 0.5, 640, 480, 70) == (0.0, 0.0)
    right, up = angles(1.0, 0.0, 640, 480, 70)
    assert right == pytest.approx(35.0)
    assert up == pytest.approx(math.degrees(math.atan(240 / (320 / math.tan(math.radians(35))))))
    assert angles(0.25, 0.75, 640, 480, 70)[0] < 0 < angles(0.75, 0.75, 640, 480, 70)[0]
    assert angles(0.5, 0.75, 640, 480, 70)[1] < 0


@pytest.mark.parametrize("bearing,yaw", [(0, 0), (10, 0), (-15, 30), (20, -40), (0, 60)])
def test_tag_yaw_is_measured_against_the_line_back_to_the_camera(bearing, yaw):
    b, a = math.radians(bearing), math.radians(yaw - bearing)
    t = (0.8 * math.sin(b), 0.0, 0.8 * math.cos(b))
    normal = (math.sin(a), 0.0, -math.cos(a))
    for n in (normal, tuple(-v for v in normal)):
        got_bearing, distance, got_yaw = tag_angles(t, n)
        assert got_bearing == pytest.approx(bearing)
        assert distance == pytest.approx(0.8)
        assert got_yaw == pytest.approx(yaw)


def test_faces_join_their_bodies_and_aim_at_the_face():
    body = Box(0.4, 0.2, 0.2, 0.7, 0.8)
    inside = Box(0.46, 0.22, 0.08, 0.1, 0.9)
    alone = Box(0.05, 0.1, 0.1, 0.12, 0.7)
    found = combine([inside, alone], [body, Box(0.8, 0.3, 0.1, 0.5, 0.6)])
    assert len(found) == 3
    joined, headless, lone = found
    assert joined.face and joined.u == pytest.approx(inside.cx) and joined.bh == pytest.approx(0.7) and joined.score == pytest.approx(0.9)
    assert not headless.face and headless.v == pytest.approx(0.3 + 0.5 * 0.12)
    assert lone.face and lone.bh == pytest.approx(0.12)


def test_tracks_stay_put_while_people_move_a_little():
    tracker = Tracker()
    first = tracker.update([Candidate(0.3, 0.4, 0.2, 0.6, 0.9, True), Candidate(0.8, 0.4, 0.1, 0.3, 0.9, False)], 0.0, "front", 4 / 3)
    ids = {round(c.u, 1): c.track for c in first}
    later = tracker.update([Candidate(0.33, 0.41, 0.21, 0.6, 0.9, True), Candidate(0.78, 0.42, 0.1, 0.31, 0.9, False)], 0.1, "front", 4 / 3)
    assert {round(c.u, 1): c.track for c in later} == {0.3: ids[0.3], 0.8: ids[0.8]}
    jumped = tracker.update([Candidate(0.05, 0.9, 0.05, 0.1, 0.9, True)], 0.2, "front", 4 / 3)
    assert jumped[0].track not in ids.values()
    assert tracker.update([Candidate(0.33, 0.41, 0.21, 0.6, 0.9, True)], 2.0, "front", 4 / 3)[0].track not in ids.values()
    other = tracker.update([Candidate(0.33, 0.41, 0.21, 0.6, 0.9, True)], 2.1, "rear", 4 / 3)
    assert other[0].track != jumped[0].track


def test_the_nearest_person_wins_and_is_kept_until_someone_much_closer_comes():
    a, b = person(-10, 0.4, True, 1), person(10, 0.5, False, 2)
    assert nearest([a, b]) is a
    assert nearest([a, person(10, 0.6, False, 2)], keep=1).track == 1
    assert nearest([a, person(10, 2.0, False, 2)], keep=1).track == 2
    assert nearest([]) is None


def test_latest_frame_hands_out_each_picture_once_and_reports_failures():
    latest = LatestFrame()
    assert latest.take(0.01) is None
    latest.put("a", "front", 1.0)
    latest.put("b", "front", 2.0)
    frame = latest.take(0.01)
    assert frame.image == "b" and frame.number == 2
    assert latest.take(0.01) is None
    latest.fail(OSError("unplugged"))
    with pytest.raises(SourceError):
        latest.take(0.01)


def test_camera_settings_fill_in_and_clean_up():
    cameras = camera_settings({"front": {"fov_h_deg": 500, "rotate": 450, "mirror": 1}, "side": {"fov_h_deg": 1}})
    assert cameras["front"]["fov_h_deg"] == 150 and cameras["front"]["rotate"] == 90 and cameras["front"]["mirror"] is True
    assert cameras["rear"]["fov_h_deg"] == 65 and set(cameras) == {"front", "rear"}


class FakeSource:
    def __init__(self, camera, log, picture="pic", fail_open=False, silent=False, die_after=None):
        self.camera = camera
        self.log = log
        self.picture = picture
        self.fail_open = fail_open
        self.silent = silent
        self.die_after = die_after
        self.count = 0
        self.closed = False

    def open(self):
        self.log.append(("open", self.camera))
        if self.fail_open:
            raise SourceError(f"no {self.camera} camera")

    def read(self, timeout_s):
        if self.silent:
            time.sleep(min(timeout_s, 0.02))
            return None
        self.count += 1
        if self.die_after is not None and self.count > self.die_after:
            raise SourceError("gone")
        time.sleep(0.005)
        return Frame(self.picture, self.camera, time.monotonic(), self.count)

    def close(self):
        self.closed = True
        self.log.append(("close", self.camera))


class FakeDetector:
    can = {"faces": True, "bodies": True, "tags": True}

    def __init__(self):
        self.calls = {"faces": 0, "bodies": 0, "tags": 0}

    def faces(self, image):
        self.calls["faces"] += 1
        return [Box(0.6, 0.2, 0.1, 0.13, 0.95)]

    def objects(self, image):
        from pebble.eyes.detect import Found

        self.calls["bodies"] += 1
        return [Box(0.55, 0.15, 0.2, 0.8, 0.8)], [Found(Box(0.1, 0.6, 0.2, 0.2, 0.7), "cup", False, "cup"), Found(Box(0.3, 0.5, 0.3, 0.3, 0.8), "cat", True, "cat")]

    def tags(self, image, fov):
        from pebble.eyes.detect import TagFound
        from pebble.seams.sight import SeenTag

        self.calls["tags"] += 1
        return [TagFound(SeenTag(DOCK_TAG_ID, -4.0, 0.5, 12.0, 0.9), 60.0, 0.0, 0.1)]


class Picture:
    shape = (480, 640, 3)


def fake_eyes(**settings):
    log = []
    plan = settings.pop("plan", {})
    looks, marks = [], []

    def sources(camera):
        return FakeSource(camera, log, Picture(), **plan.get(camera, {}))

    eyes = CameraEyes(sources, FakeDetector(), Clock(), on_look=looks.append, on_camera=marks.append, max_fps=50, **settings)
    return eyes, log, looks, marks


async def until(check, seconds=5.0):
    deadline = time.monotonic() + seconds
    while not check():
        if time.monotonic() > deadline:
            return False
        await asyncio.sleep(0.01)
    return True


def test_camera_eyes_see_switch_and_look():
    async def scenario():
        eyes, log, looks, marks = fake_eyes()
        eyes.start()
        try:
            assert await until(lambda: eyes.available)
            sight = eyes.latest()
            assert sight.camera == "front" and eyes.camera() == "front" and sight.tags == ()
            assert len(sight.people) == 1 and sight.people[0].face and sight.people[0].bearing_deg > 0
            assert looks and looks[-1].track == sight.people[0].track and marks[-1] == "front"
            assert abs(sight.at - time.time()) < 1.0
            assert await eyes.use_camera("rear") is True
            sight = eyes.latest()
            assert sight.camera == "rear" and sight.tags[0].distance_m == 0.5
            assert looks[-1] is None and marks[-1] == "rear"
            assert ("close", "front") in log and ("open", "rear") in log
            opened = len(log)
            assert await eyes.use_camera("rear") is True and len(log) == opened
            assert await eyes.use_camera("side") is False
            eyes.set_enabled(False)
            assert await until(lambda: ("close", "rear") in log)
            assert eyes.latest() is None and not eyes.available and eyes.camera() is None
            assert await eyes.use_camera("front") is False
            eyes.set_enabled(True)
            assert await until(lambda: eyes.available)
            assert eyes.status()["camera"] == "rear"
        finally:
            eyes.close()
        assert marks[-1] is None

    run(scenario())


def test_a_camera_that_will_not_open_or_stays_dark_is_a_no():
    async def scenario():
        eyes, log, _, _ = fake_eyes(plan={"rear": {"fail_open": True}}, switch_timeout_s=3.0)
        eyes.start()
        try:
            assert await until(lambda: eyes.available)
            started = time.monotonic()
            assert await eyes.use_camera("rear") is False
            assert time.monotonic() - started < 2.0
            assert "would not open" in eyes.problem
            assert await eyes.use_camera("front") is True
        finally:
            eyes.close()
        dark, _, _, _ = fake_eyes(plan={"front": {"silent": True}}, switch_timeout_s=0.3)
        dark.start()
        try:
            assert await dark.use_camera("front") is False
            assert not dark.available
        finally:
            dark.close()

    run(scenario())


def test_a_camera_that_dies_is_opened_again():
    async def scenario():
        eyes, log, _, _ = fake_eyes(plan={"front": {"die_after": 3}})
        eyes.start()
        try:
            assert await until(lambda: log.count(("open", "front")) >= 2, 8.0)
            assert "stopped" in eyes.problem or eyes.available
        finally:
            eyes.close()

    run(scenario())


def test_use_camera_is_a_no_before_the_eyes_start():
    eyes, _, _, _ = fake_eyes()
    assert run(eyes.use_camera("rear")) is False


def test_latest_respects_its_age_limit():
    clock = FakeClock()
    eyes = CameraEyes(lambda camera: None, FakeDetector(), clock)
    sight = eyes.process(Frame(Picture(), "front", clock.monotonic(), 1))
    eyes._show(sight, Frame(Picture(), "front", clock.monotonic(), 1))
    assert eyes.latest(0.5) is sight and eyes.available
    clock.advance(0.6)
    assert eyes.latest(0.5) is None and eyes.latest(1.0) is sight
    clock.advance(1.0)
    assert not eyes.available and eyes.camera() is None


class SlowBodies(FakeDetector):
    def objects(self, image):
        time.sleep(0.12)
        return super().objects(image)


def test_slow_body_detection_is_spread_over_frames():
    clock = FakeClock()
    detector = SlowBodies()
    eyes = CameraEyes(lambda camera: None, detector, clock, max_fps=30)
    for n in range(20):
        clock.advance(0.033)
        sight = eyes.process(Frame(Picture(), "front", clock.monotonic(), n))
        assert len(sight.people) == 1 and sight.people[0].face
    assert detector.calls["faces"] == 20 and 3 <= detector.calls["bodies"] <= 7


def test_eyes_from_config_picks_the_right_kind():
    assert isinstance(eyes_from_config(None), NoEyes)
    assert isinstance(eyes_from_config({"source": "none"}), NoEyes)
    assert isinstance(eyes_from_config({"source": "browser"}), NoEyes)
    assert isinstance(eyes_from_config({"source": "telepathy"}), NoEyes)
    from pebble.web.eyes import BrowserEyes

    browser = eyes_from_config({"source": "browser", "rear": {"fov_h_deg": 60}}, hub=Hub())
    assert isinstance(browser, BrowserEyes) and browser.cameras["rear"]["fov_h_deg"] == 60 and browser.cameras["rear"]["rotate"] is None


def test_look_push_throttles_and_says_when_nobody_is_there():
    hub = Hub()
    client = hub.subscribe()
    now = [0.0]
    push = LookPush(hub, min_gap_s=0.1, monotonic=lambda: now[0])
    push.camera("front")
    push(person(12.0, 0.5, True, 3))
    push(person(13.0, 0.5, True, 3))
    now[0] = 0.2
    push(person(14.0, 0.5, True, 3))
    push(None)
    messages = []
    while not client.empty():
        messages.append(client.get_nowait().decode())
    assert messages[0].startswith("event: face") or messages[0].startswith("event: camera")
    looks = [m for m in messages if m.startswith("event: look")]
    assert len(looks) == 3 and '"bearing_deg":12.0' in looks[0] and '"bearing_deg":14.0' in looks[1] and '"on":false' in looks[2]
    assert any(m.startswith("event: camera") and '"camera":"front"' in m for m in messages)
    assert hub.subscribe().get_nowait().decode().startswith("event: camera")


class Served:
    def __init__(self, data: bytes):
        self.stream = io.BytesIO(data)

    def __enter__(self):
        return self.stream

    def __exit__(self, *exc):
        return False


def test_fetch_checks_every_byte(tmp_path):
    body = b"pebble model"
    good = fetching.Asset("m", "sub/model.onnx", "https://example.invalid/m", hashlib.sha256(body).hexdigest(), len(body), "MIT")
    bad = fetching.Asset("b", "bad.onnx", "https://example.invalid/b", "0" * 64, len(body), "MIT")
    big = fetching.Asset("g", "big.onnx", "https://example.invalid/g", hashlib.sha256(body).hexdigest(), 3, "MIT")
    said = []
    assert fetching.fetch((good,), tmp_path, opener=lambda url: Served(body), say=said.append)
    assert (tmp_path / "sub" / "model.onnx").read_bytes() == body and fetching.ready((good,), tmp_path)
    assert fetching.fetch((good,), tmp_path, opener=lambda url: pytest.fail("fetched twice"), say=said.append)
    assert not fetching.fetch((bad, big), tmp_path, opener=lambda url: Served(body), say=said.append)
    assert not (tmp_path / "bad.onnx").exists() and not (tmp_path / "big.onnx").exists()
    assert not list(tmp_path.glob(".part-*"))
    assert any("FAILED bad.onnx" in line for line in said) and any("bigger" in line for line in said)


def test_every_pinned_file_has_a_hash_and_a_licence():
    from pebble.web import fetch_eyes

    for asset in fetching.ASSETS + fetch_eyes.ASSETS:
        assert len(asset.sha256) == 64 and int(asset.sha256, 16) >= 0 and asset.size > 0 and asset.licence
        assert asset.url.startswith("https://") or (asset.made and not asset.url)
    assert fetching.total(fetching.ASSETS) < 250_000_000
    assert fetching.total(fetch_eyes.ASSETS) < 20_000_000


cv2 = pytest.importorskip("cv2", reason="OpenCV is not installed")


@pytest.fixture(scope="module")
def detector():
    from pebble.eyes.detect import Detector

    return Detector(faces=PORTRAIT.parent.parent.joinpath(fetching.ASSETS[0].path).exists(), bodies=PORTRAIT.parent.parent.joinpath(fetching.ASSETS[2].path).exists())


@pytest.mark.parametrize("distance,bearing,yaw", [(0.3, 0, 0), (0.5, 5, 20), (0.6, -10, -25), (0.4, 15, 40), (0.8, 0, 0)])
def test_a_drawn_dock_tag_comes_back_where_it_was_put(detector, distance, bearing, yaw):
    from pebble.eyes.scene import TagPlacement, tag_scene

    found = detector.tags(tag_scene(1280, 960, 65, TagPlacement(distance, bearing, 0, yaw)), 65)
    assert len(found) == 1
    tag = found[0].seen
    assert tag.id == DOCK_TAG_ID
    assert tag.bearing_deg == pytest.approx(bearing, abs=0.5)
    assert tag.distance_m == pytest.approx(distance, rel=0.03)
    assert tag.yaw_deg == pytest.approx(yaw, abs=4.0)
    assert abs(found[0].roll_deg) < 3


def test_a_far_tag_is_found_but_its_turn_is_not_trusted(detector):
    from pebble.eyes.scene import TagPlacement, tag_scene

    found = detector.tags(tag_scene(640, 480, 65, TagPlacement(1.4, 0, 0, 10)), 65)
    assert len(found) == 1 and found[0].seen.distance_m == pytest.approx(1.4, rel=0.05) and found[0].seen.score < 0.3


def test_a_mirrored_tag_is_not_the_dock(detector):
    from pebble.eyes.scene import TagPlacement, tag_scene

    picture = tag_scene(640, 480, 65, TagPlacement(0.4, 0, 0, 0))
    assert detector.tags(picture[:, ::-1].copy(), 65) == []


def test_the_scene_source_feeds_the_eyes_a_tag():
    from pebble.eyes.detect import Detector

    async def scenario():
        cameras = camera_settings({})
        sources = make_sources("scene", cameras, {"scene": {"rear": {"distance_m": 0.5, "yaw_deg": -20}}})
        eyes = CameraEyes(sources, Detector(faces=False, bodies=False), Clock(), cameras, camera="rear")
        eyes.start()
        try:
            assert await until(lambda: eyes.available)
            tag = eyes.latest().tags[0]
            assert tag.distance_m == pytest.approx(0.5, rel=0.03) and tag.yaw_deg == pytest.approx(-20, abs=4)
        finally:
            eyes.close()

    run(scenario())


@pytest.mark.skipif(not PORTRAIT.exists(), reason="run python -m pebble.eyes.fetch --samples first")
def test_a_photo_of_a_person_gives_a_person_with_a_face(detector):
    if not (detector.can["faces"] and detector.can["bodies"]):
        pytest.skip("models not fetched")
    picture = cv2.imread(str(PORTRAIT))
    eyes = CameraEyes(lambda camera: None, detector, Clock())
    sight = eyes.process(Frame(picture, "front", time.monotonic(), 1))
    assert len(sight.people) == 1
    seen = sight.people[0]
    assert seen.face and seen.score > 0.8 and seen.height_frac > 0.7
    assert abs(seen.bearing_deg) < 3 and seen.elevation_deg > 15
    assert detector.faces(picture[:, ::-1].copy())
