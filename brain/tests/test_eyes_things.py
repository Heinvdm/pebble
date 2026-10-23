import asyncio
import json
import time

import pytest
from conftest import run

from pebble.clock import Clock, FakeClock
from pebble.eyes import fetch as fetching
from pebble.eyes.geometry import Box, Candidate, Tracker
from pebble.eyes.labels import COCO, COCO_NAMES, coco_label
from pebble.eyes.service import CameraEyes
from pebble.eyes.slow import SlowFound, SlowLane
from pebble.eyes.sources import Frame
from pebble.eyes.things import Thing, merge, overlap, seen_things

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2", reason="OpenCV is not installed")

MODELS = fetching.MODELS
DESK = MODELS / "samples" / "desk.jpg"
CAT = MODELS / "samples" / "cat.jpg"
SLOW_MODEL = MODELS / "objects.onnx"
SLOW_VOCAB = MODELS / "objects_vocab.json"


def thing(label, box, lane="fast", depth=8, track=None, animal=False, at=100.0):
    return Thing(Box(*box, 0.8), label, animal, at, lane, depth, track)


def test_everyday_labels_are_plain_and_people_are_not_things():
    assert len(COCO_NAMES) == 80 and COCO["person"] is None
    assert COCO["refrigerator"] == "fridge" and COCO["cell phone"] == "phone" and COCO["sports ball"] == "ball" and COCO["potted plant"] == "plant"
    assert COCO["couch"] == "couch" and COCO["tv"] == "tv" and COCO["cup"] == "cup"
    for gone in ("airplane", "elephant", "giraffe", "stop sign", "surfboard", "baseball bat"):
        assert COCO[gone] is None
    assert coco_label(15) == ("cat", True) and coco_label(16) == ("dog", True) and coco_label(41) == ("cup", False)
    assert coco_label(0) == (None, False) and coco_label(80) == (None, False) and coco_label(-1) == (None, False)


def test_the_two_lanes_agree_on_one_entry_with_the_more_specific_name():
    fast = [thing("cup", (0.1, 0.1, 0.2, 0.2), depth=7, track=4), thing("laptop", (0.5, 0.2, 0.4, 0.4), depth=12, track=5)]
    slow = [
        thing("coffee cup", (0.11, 0.1, 0.19, 0.21), lane="slow", depth=9, track=40, at=99.0),
        thing("gadget", (0.5, 0.21, 0.4, 0.39), lane="slow", depth=6, track=41, at=99.0),
        thing("saucer", (0.05, 0.28, 0.3, 0.08), lane="slow", depth=9, track=42, at=99.0),
    ]
    merged = merge(fast, slow)
    assert [t.label for t in merged] == ["coffee cup", "laptop", "saucer"]
    cup, laptop, saucer = merged
    assert cup.lane == "slow" and cup.track == 4 and cup.at == 100.0 and cup.box == fast[0].box
    assert laptop.lane == "fast" and laptop.track == 5
    assert saucer.lane == "slow" and saucer.at == 99.0
    assert merge(fast, []) == fast and merge([], slow) == slow
    assert overlap(Box(0, 0, 1, 1, 1), Box(0, 0, 1, 1, 1)) == 1.0 and overlap(Box(0, 0, 0.1, 0.1, 1), Box(0.5, 0.5, 0.1, 0.1, 1)) == 0.0


def test_things_turn_into_seen_things_with_box_centre_angles():
    seen = seen_things([thing("cat", (0.4, 0.4, 0.2, 0.2), animal=True, track=7)], 640, 480, 70)[0]
    assert seen.label == "cat" and seen.animal and seen.track == 7 and seen.lane == "fast" and seen.at == 100.0
    assert seen.bearing_deg == pytest.approx(0.0) and seen.elevation_deg == pytest.approx(0.0)
    assert seen.height_frac == 0.2 and seen.width_frac == 0.2


def test_tracks_never_jump_between_different_kinds_of_thing():
    tracker = Tracker()
    first = tracker.update([Candidate(0.5, 0.5, 0.2, 0.2, 0.9, False, label="cup")], 0.0, "front", 4 / 3)
    second = tracker.update([Candidate(0.5, 0.5, 0.2, 0.2, 0.9, False, label="bowl")], 0.1, "front", 4 / 3)
    third = tracker.update([Candidate(0.51, 0.5, 0.2, 0.2, 0.9, False, label="cup")], 0.2, "front", 4 / 3)
    assert first[0].track != second[0].track and third[0].track == first[0].track


class Picture:
    shape = (480, 640, 3)
    ndim = 3


class FakeFast:
    can = {"faces": True, "bodies": True, "tags": True}

    def faces(self, image):
        return []

    def objects(self, image):
        from pebble.eyes.detect import Found

        return [Box(0.6, 0.1, 0.2, 0.8, 0.8)], [Found(Box(0.1, 0.6, 0.2, 0.2, 0.7), "cup", False, "cup"), Found(Box(0.4, 0.5, 0.2, 0.2, 0.8), "dog", True, "dog")]

    def tags(self, image, fov):
        return []


def test_the_fast_lane_names_things_and_keeps_people_apart():
    clock = FakeClock()
    eyes = CameraEyes(lambda camera: None, FakeFast(), clock)
    first = eyes.process(Frame(Picture(), "front", clock.monotonic(), 1))
    clock.advance(0.1)
    second = eyes.process(Frame(Picture(), "front", clock.monotonic(), 2))
    assert len(first.people) == 1 and [t.label for t in first.things] == ["cup", "dog"]
    cup, dog = first.things
    assert cup.lane == "fast" and not cup.animal and dog.animal and cup.track != dog.track
    assert cup.bearing_deg < 0 and cup.elevation_deg < 0 and cup.at == pytest.approx(clock.now() - 0.1, abs=1e-6)
    assert [t.track for t in second.things] == [cup.track, dog.track]
    clock.advance(2.0)
    later = eyes.process(Frame(Picture(), "rear", clock.monotonic(), 3))
    assert all(t.label in ("cup", "dog") for t in later.things)


class FakeSlowDetector:
    coco_depth = {"cup": 7}

    def __init__(self, delay=0.0):
        self.cv2, self.np = cv2, np
        self.delay = delay
        self.calls = 0

    def detect(self, image):
        self.calls += 1
        time.sleep(self.delay)
        return [SlowFound(Box(0.1, 0.6, 0.2, 0.2, 0.9), "coffee cup", False, "coffee cup", 9), SlowFound(Box(0.7, 0.7, 0.1, 0.1, 0.8), "slipper", False, "slipper", 9)]


def picture(level: int):
    return np.full((48, 64, 3), level, np.uint8)


async def until(check, seconds=5.0):
    deadline = time.monotonic() + seconds
    while not check():
        if time.monotonic() > deadline:
            return False
        await asyncio.sleep(0.01)
    return True


def test_the_slow_lane_looks_only_when_the_view_changes_and_not_while_busy():
    async def scenario():
        detector = FakeSlowDetector()
        lane = SlowLane(lambda: detector, every_s=0.05, keep_s=3.0, change=0.06, nice=0)
        lane.start()
        try:
            lane.offer(picture(100), "front", time.monotonic(), time.time(), 70)
            assert await until(lambda: lane.passes == 1)
            for _ in range(5):
                lane.offer(picture(102), "front", time.monotonic(), time.time(), 70)
                await asyncio.sleep(0.08)
            assert lane.passes == 1
            lane.offer(picture(180), "front", time.monotonic(), time.time(), 70)
            assert await until(lambda: lane.passes == 2)
            lane.set_busy(True)
            lane.offer(picture(20), "front", time.monotonic(), time.time(), 70)
            await asyncio.sleep(0.3)
            assert lane.passes == 2 and lane.busy
            result = await lane.demand(asyncio.get_running_loop())
            assert lane.passes == 3 and result.camera == "front" and [f.label for f in result.found] == ["coffee cup", "slipper"]
            lane.moved()
            lane.set_busy(False)
            for _ in range(10):
                lane.offer(picture(20), "front", time.monotonic(), time.time(), 70)
                await asyncio.sleep(0.03)
            assert await until(lambda: lane.passes == 4)
            assert lane.current("front", time.monotonic()) is not None and lane.current("rear", time.monotonic()) is None
            assert lane.current("front", time.monotonic() + 5.0) is None
            lane.forget()
            assert lane.current("front", time.monotonic()) is None
            assert await lane.demand(asyncio.get_running_loop()) is None
        finally:
            lane.close()

    run(scenario())


def test_a_slow_lane_without_its_model_says_so_and_answers_nothing():
    async def scenario():
        def broken():
            raise RuntimeError("no model here")

        lane = SlowLane(broken, nice=0)
        lane.start()
        try:
            assert await asyncio.wait_for(lane.demand(asyncio.get_running_loop()), 3.0) is None
            assert "no model here" in lane.problem
        finally:
            lane.close()

    run(scenario())


def test_look_closely_brings_in_the_slow_names_and_set_busy_reaches_the_lane():
    async def scenario():
        detector = FakeSlowDetector(delay=0.05)
        lane = SlowLane(lambda: detector, every_s=0.05, nice=0)
        eyes = CameraEyes(lambda camera: Still(camera), FakeFast(), Clock(), slow=lane, max_fps=30)
        eyes.start()
        try:
            assert await until(lambda: eyes.available)
            eyes.set_busy(True)
            assert lane.busy
            await asyncio.sleep(0.2)
            passes = lane.passes
            sight = await eyes.look_closely()
            assert lane.passes == passes + 1
            await asyncio.sleep(0.3)
            assert lane.passes == passes + 1
            labels = {t.label: t for t in sight.things}
            assert labels["coffee cup"].lane == "slow" and labels["dog"].lane == "fast" and labels["slipper"].lane == "slow"
            assert "cup" not in labels and labels["slipper"].at <= time.time()
            assert eyes.status()["slow"]["busy"] is True
            eyes.set_busy(False)
            assert await until(lambda: any(t.lane == "slow" for t in (eyes.latest() or sight).things))
            eyes.set_enabled(False)
            assert await eyes.look_closely() is None
        finally:
            eyes.close()
        plain = CameraEyes(lambda camera: Still(camera), FakeFast(), Clock())
        plain.start()
        try:
            assert await until(lambda: plain.available)
            assert all(t.lane == "fast" for t in (await plain.look_closely()).things)
            plain.set_busy(True)
        finally:
            plain.close()

    run(scenario())


class Still:
    def __init__(self, camera):
        self.camera = camera
        self.count = 0

    def open(self):
        pass

    def read(self, timeout_s):
        self.count += 1
        time.sleep(0.01)
        return Frame(picture(90 + self.count % 2), self.camera, time.monotonic(), self.count)

    def close(self):
        pass


def test_the_home_vocabulary_has_no_people_and_matches_its_hash():
    if not SLOW_VOCAB.exists():
        pytest.skip("no slow-lane vocabulary (tools/export_objects.py)")
    asset = next(a for a in fetching.ASSETS if a.key == "slow_vocab")
    assert fetching.present(asset, MODELS, deep=True)
    vocab = json.loads(SLOW_VOCAB.read_text(encoding="utf-8"))
    labels = {c["label"] for c in vocab["classes"]}
    assert "AGPL" in vocab["licence"] and vocab["imgsz"] == 416 and len(vocab["classes"]) == vocab["layout"]["classes"]
    assert {"cup", "smartphone", "slipper", "cat", "dog", "remote control"} <= labels
    assert not labels & {"person", "man", "woman", "child", "boy", "girl", "baby", "room", "floor", "wall", "white", "screenshot"}
    assert all(c["label"] == c["label"].lower() for c in vocab["classes"])
    assert {c["label"] for c in vocab["classes"] if c["animal"]} >= {"cat", "dog"} and not any(c["animal"] for c in vocab["classes"] if c["label"] in ("teddy bear", "stuffed animal"))
    assert vocab["coco_depth"]["cup"] > 0


def load(path):
    if not path.exists():
        pytest.skip("run python -m pebble.eyes.fetch --samples first")
    image = cv2.imread(str(path))
    h, w = image.shape[:2]
    return cv2.resize(image, (640, round(h * 640 / w)), interpolation=cv2.INTER_AREA)


def test_the_fast_lane_finds_a_laptop_a_cup_and_a_cat():
    from pebble.eyes.detect import Detector

    detector = Detector(tags=False)
    if not detector.can["bodies"]:
        pytest.skip("models not fetched")
    _, things = detector.objects(load(DESK))
    assert {"laptop", "cup"} <= {t.label for t in things}
    _, things = detector.objects(load(CAT))
    cats = [t for t in things if t.label == "cat"]
    assert cats and cats[0].animal


def test_the_slow_lane_names_more_than_the_fast_lane_can():
    pytest.importorskip("onnxruntime")
    if not SLOW_MODEL.exists():
        pytest.skip("no slow-lane model (tools/export_objects.py)")
    from pebble.eyes.slow import SlowDetector

    detector = SlowDetector(SLOW_MODEL, SLOW_VOCAB, threads=2)
    found = {f.label: f for f in detector.detect(load(DESK))}
    assert {"laptop", "saucer", "smartphone"} <= set(found)
    assert set(found) - set(COCO.values())
    assert all(0 <= f.box.x <= 1 and 0 <= f.box.y <= 1 and f.box.w > 0 for f in found.values())
    cat = {f.label: f for f in detector.detect(load(CAT))}
    assert cat["cat"].animal and not any(f.animal for name, f in cat.items() if name != "cat")
