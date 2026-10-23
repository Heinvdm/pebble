import asyncio
import json
import math
import time
from pathlib import Path

import pytest
from bodies import view
from conftest import run

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from pebble.clock import Clock, FakeClock
from pebble.eyes import eyes_from_config, fetch as fetching
from pebble.eyes.geometry import Box, Candidate, floor_point, seen_people
from pebble.eyes.hazards import HazardWatch
from pebble.eyes.posture import posture
from pebble.eyes.service import CameraEyes
from pebble.eyes.slow import SlowFound
from pebble.eyes.sources import Frame

MODELS = fetching.MODELS
HAZARDS = Path(__file__).resolve().parent / "data" / "hazards"
W, H, FOV = 640, 480, 70.0


def judge(pose, distance, bearing=0.0, facing=180.0, pitch=8.0, seed=0, noise=0.004, roll=0.0):
    raw, box = view(pose, distance, bearing_deg=bearing, facing_deg=facing, pitch_deg=pitch, noise=noise, seed=seed)
    if roll:
        a = math.radians(roll)
        f = (W / 2) / math.tan(math.radians(FOV) / 2)
        for row in raw:
            x, y = (row[0] - 0.5) * W / f, (row[1] - 0.5) * H / f
            row[0], row[1] = 0.5 + (x * math.cos(a) - y * math.sin(a)) * f / W, 0.5 + (x * math.sin(a) + y * math.cos(a)) * f / H
        us, vs = raw[:, 0], raw[:, 1]
        box = Box(float(us.min()), float(vs.min()), float(us.max() - us.min()), float(vs.max() - vs.min()), 0.9)
    return posture(raw, box, W, H, FOV, 0.14, pitch, roll)


@pytest.mark.parametrize("distance", (2.5, 3.5))
@pytest.mark.parametrize("bearing", (-15.0, 0.0, 15.0))
@pytest.mark.parametrize("facing", (180.0, 140.0, 90.0))
def test_posture_from_the_body_points(distance, bearing, facing):
    for seed in range(2):
        assert judge("standing", distance, bearing, facing, seed=seed)[0] == "standing"
        assert judge("floor_sitting", distance, bearing, facing, seed=seed)[0] == "sitting"
        label, sure = judge("lying_floor", distance, bearing, facing, seed=seed)
        assert label == "lying" and sure >= 0.5
        assert judge("lying_couch", distance, bearing, facing, seed=seed)[0] != "lying"
        assert judge("leaning_back", distance, bearing, facing, seed=seed)[0] != "lying"


def test_posture_corrects_for_the_head_and_the_camera_roll():
    assert judge("standing", 3.0, pitch=20.0)[0] == "standing"
    assert judge("lying_floor", 3.0, pitch=20.0)[0] == "lying"
    assert judge("standing", 3.0, roll=35.0)[0] == "standing"
    assert judge("lying_floor", 3.0, roll=35.0)[0] == "lying"
    raw, box = view("standing", 3.0)
    assert posture(raw, box, W, H, FOV)[0] == "standing"
    blind = raw.copy()
    blind[:, 2] = 0.0
    assert posture(blind, box, W, H, FOV) == (None, 0.0)


def test_posture_on_a_real_photo():
    from pebble.eyes.detect import Detector
    from pebble.eyes.pose import NoPoseModel, PoseModel

    try:
        pose = PoseModel(MODELS / "rtmpose_t_body7_256x192.onnx")
    except NoPoseModel:
        pytest.skip("no pose model")
    image = cv2.imread(str(HAZARDS / "tv_room.jpg"))
    height, width = image.shape[:2]
    bodies, _ = Detector(tags=False).objects(image)
    best = max(bodies, key=lambda b: b.score)
    label, sure = posture(pose.points(image, best), best, width, height, FOV, 1.2, 0.0)
    assert label == "sitting" and sure >= 0.5


def test_people_carry_their_posture():
    person = seen_people([Candidate(0.45, 0.5, 0.3, 0.8, 0.9, False, track=4)], W, H, FOV, {4: ((), 10.0, "lying", 0.8)})[0]
    assert person.posture == "lying" and person.posture_score == 0.8 and person.facing_deg == 10.0
    plain = seen_people([Candidate(0.45, 0.5, 0.3, 0.8, 0.9, False, track=5)], W, H, FOV, {5: ((), None)})[0]
    assert plain.posture is None and plain.posture_score == 0.0


def ground(u, v, height_m, pitch_deg, width=W, height=H, fov=FOV):
    f = (width / 2) / math.tan(math.radians(fov) / 2)
    x, y = (u - 0.5) * width / f, (v - 0.5) * height / f
    p = math.radians(pitch_deg)
    ray = np.array([0.0, math.cos(p), math.sin(p)]) + x * np.array([1.0, 0, 0]) - y * np.array([0, -math.sin(p), math.cos(p)])
    t = height_m / -ray[2]
    return math.hypot(t * ray[0], t * ray[1]), math.degrees(math.atan2(t * ray[0], t * ray[1]))


def test_floor_point_from_camera_height_and_tilt():
    for u, v, pitch in ((0.5, 0.9, 8.0), (0.8, 0.95, 0.0), (0.2, 0.7, -10.0), (0.6, 0.99, 8.0)):
        got = floor_point(u, v, W, H, FOV, 0.14, pitch)
        want = ground(u, v, 0.14, pitch)
        assert got[0] == pytest.approx(want[0], rel=1e-6) and got[1] == pytest.approx(want[1], abs=1e-6)
    assert floor_point(0.8, 0.95, W, H, FOV, 0.14, 0.0)[1] > 0
    assert floor_point(0.5, 0.3, W, H, FOV, 0.14, 8.0) is None
    assert floor_point(0.5, 0.52, W, H, FOV, 0.14, 0.0) is None
    f = (W / 2) / math.tan(math.radians(FOV) / 2)
    x, y = 0.1 * W / f, 0.4 * H / f
    r = math.radians(20.0)
    u, v = 0.5 + (x * math.cos(r) - y * math.sin(r)) * f / W, 0.5 + (x * math.sin(r) + y * math.cos(r)) * f / H
    level = floor_point(0.6, 0.9, W, H, FOV, 0.14, 8.0)
    rolled = floor_point(u, v, W, H, FOV, 0.14, 8.0, 20.0)
    assert rolled == pytest.approx(level, abs=1e-9)
    assert floor_point(u, v, W, H, FOV, 0.14, 8.0) != pytest.approx(level, abs=1e-3)


class Picture:
    shape = (480, 640, 3)
    ndim = 3


class FloorFast:
    can = {"faces": True, "bodies": True, "tags": True}

    def faces(self, image):
        return []

    def objects(self, image):
        from pebble.eyes.detect import Found

        return [], [Found(Box(0.45, 0.8, 0.1, 0.1, 0.8), "sock", False, "sock"), Found(Box(0.2, 0.1, 0.1, 0.1, 0.8), "clock", False, "clock")]

    def tags(self, image, fov):
        return []


def test_things_on_the_floor_get_a_floor_position():
    clock = FakeClock()
    eyes = CameraEyes(lambda camera: None, FloorFast(), clock)
    sight = eyes.process(Frame(Picture(), "front", clock.monotonic(), 1))
    things = {t.label: t for t in sight.things}
    assert things["clock"].floor_m is None and things["clock"].floor_bearing_deg is None
    sock = things["sock"]
    want = ground(0.5, 0.9, 0.14, 8.0)
    assert sock.floor_m == pytest.approx(want[0], abs=0.002) and abs(sock.floor_bearing_deg) < 0.5
    eyes.set_head(tilt_deg=-10.0)
    nearer = {t.label: t for t in eyes.process(Frame(Picture(), "front", clock.monotonic(), 2)).things}["sock"]
    assert nearer.floor_m < sock.floor_m
    eyes.set_head(tilt_deg=8.0)
    behind = {t.label: t for t in eyes.process(Frame(Picture(), "rear", clock.monotonic(), 3)).things}["sock"]
    assert behind.floor_m == pytest.approx(ground(0.5, 0.9, 0.14, -8.0, fov=65.0)[0], abs=0.002)
    assert eyes.head("rear") == (0.14, -8.0, -0.0) and eyes.status()["head"] == {"tilt_deg": 8.0, "roll_deg": 0.0}


class FakeHazards:
    classes = [{"label": "fire", "role": "fire"}, {"label": "smoke", "role": "smoke"}, {"label": "fireplace", "role": "lookalike"}, {"label": "tv", "role": "lookalike"}, {"label": "lamp", "role": "lookalike"}, {"label": "stove burner", "role": "lookalike"}]

    def __init__(self, found=()):
        self.found = list(found)

    def detect(self, image, score=None):
        return [SlowFound(box, label, False, label, 6) for label, box in self.found]


def watch(found=()):
    now = [0.0]
    w = HazardWatch(lambda: FakeHazards(found), lambda: now[0])
    w.detector = FakeHazards(found)
    return w, now


def blank():
    return np.zeros((480, 640, 3), np.uint8)


def labels(w, at=0.0):
    return {(t.label, round(t.box.score, 3)) for t in w.current("front", at)}


def test_fire_inside_a_lookalike_is_named_after_it():
    fire = Box(0.4, 0.4, 0.1, 0.1, 0.7)
    cases = (
        ([("fire", fire), ("tv", Box(0.3, 0.3, 0.3, 0.3, 0.6))], "tv"),
        ([("fire", fire), ("fireplace", Box(0.3, 0.3, 0.3, 0.3, 0.4))], "fireplace"),
        ([("fire", fire), ("lamp", Box(0.39, 0.39, 0.12, 0.12, 0.5))], "fire"),
        ([("fire", fire), ("lamp", Box(0.39, 0.39, 0.12, 0.12, 0.8))], "lamp"),
        ([("fire", Box(0.25, 0.1, 0.5, 0.6, 0.7)), ("fireplace", Box(0.35, 0.4, 0.3, 0.3, 0.6))], "fire"),
        ([("fire", Box(0.4, 0.3, 0.2, 0.3, 0.7)), ("stove burner", Box(0.2, 0.25, 0.6, 0.6, 0.6))], "fire"),
        ([("fire", Box(0.45, 0.5, 0.08, 0.05, 0.7)), ("stove burner", Box(0.2, 0.25, 0.6, 0.6, 0.6))], "stove burner"),
    )
    for found, want in cases:
        w, _ = watch(found)
        w._pass((blank(), "front", 0.0, 0.0, FOV), [])
        names = [t.label for t in w.current("front", 0.0)]
        assert names[0] == want, (found, names)
    w, _ = watch([("fire", fire)])
    from pebble.eyes.things import Thing

    w._pass((blank(), "front", 0.0, 0.0, FOV), [Thing(Box(0.3, 0.3, 0.3, 0.3, 0.6), "computer monitor", False, 0.0, "fast")])
    assert [t.label for t in w.current("front", 0.0)] == ["tv"]


def test_flames_flicker_and_a_steady_glow_does_not():
    box = Box(0.4, 0.4, 0.2, 0.2, 0.6)

    def frame(k):
        image = blank()
        image[200:280, 260:380] = (0, int(120 * k), int(255 * k))
        return image

    results = {}
    for name, level in (("flicker", lambda n: 1.0 if (n * 0.1 * 4) % 1 < 0.5 else 0.55), ("steady", lambda n: 1.0)):
        w, now = watch([("fire", box)])
        w.offer(frame(1.0), "front", 0.0, 0.0, FOV)
        w._pass(w._offer[:5], [])
        for n in range(1, 31):
            now[0] = n * 0.1
            w.offer(frame(level(n)), "front", n * 0.1, n * 0.1, FOV)
        w._pass(w._offer[:5], [])
        results[name] = (dict(labels(w, 3.0)), w.status())
    flicker, steady = results["flicker"], results["steady"]
    assert flicker[1]["tracks"][0]["flicker"] >= 0.8 and flicker[0]["fire"] >= 0.85
    assert steady[1]["tracks"][0]["flicker"] == 0.0 and steady[0]["fire"] == pytest.approx(0.6)
    assert flicker[1]["close_watch"]
    assert w.current("rear", 3.0) == [] and w.current("front", 9.0) == []
    w.forget()
    assert w.current("front", 3.0) == [] and w.status()["tracks"] == []


def test_a_warm_flicker_brings_the_next_look_sooner():
    w, now = watch()
    for n in range(12):
        image = blank()
        if n % 2:
            image[200:280, 260:380] = (0, 120, 255)
        w.offer(image, "front", n * 0.1, n * 0.1, FOV)
    assert w._close_until > now[0]
    quiet, _ = watch()
    for n in range(12):
        quiet.offer(blank(), "front", n * 0.1, n * 0.1, FOV)
    assert quiet._close_until < 0


def test_steam_over_a_kettle_until_it_spreads():
    from pebble.eyes.things import Thing

    kettle = Thing(Box(0.4, 0.6, 0.15, 0.2, 0.7), "kettle", False, 0.0, "slow")
    w, now = watch()
    for n, grow in enumerate((1.0, 1.0, 1.0, 1.0)):
        w.detector = FakeHazards([("smoke", Box(0.42, 0.4, 0.1 * grow, 0.15 * grow, 0.6))])
        now[0] = n
        w._pass((blank(), "front", float(n), float(n), FOV), [kettle])
    assert [t.label for t in w.current("front", 3.0)] == ["steam"]
    w, now = watch()
    for n, grow in enumerate((1.0, 1.3, 1.7, 2.2)):
        w.detector = FakeHazards([("smoke", Box(0.42 - 0.05 * n, 0.4 - 0.05 * n, 0.1 * grow, 0.15 * grow, 0.6))])
        now[0] = n
        w._pass((blank(), "front", float(n), float(n), FOV), [kettle])
    found = w.current("front", 3.0)
    assert [t.label for t in found] == ["smoke"] and found[0].box.score >= 0.75
    assert w.status()["tracks"][0]["spread"] == 1.0


def test_a_fire_that_grows_out_of_the_fireplace_is_a_fire():
    w, now = watch()
    place = Box(0.2, 0.2, 0.6, 0.6, 0.6)
    for n, size in enumerate((0.1, 0.12, 0.16, 0.22)):
        w.detector = FakeHazards([("fire", Box(0.5 - size / 2, 0.5 - size / 2, size, size, 0.6)), ("fireplace", place)])
        now[0] = n
        w._pass((blank(), "front", float(n), float(n), FOV), [])
        names = {t.label for t in w.current("front", float(n))}
        assert ("fire" in names) == (size * size >= 2.0 * 0.01), (size, names)


def photo(name):
    return cv2.imread(str(HAZARDS / f"{name}.jpg"))


@pytest.fixture(scope="module")
def hazard_model():
    from pebble.eyes.slow import NoSlowModel, SlowDetector

    try:
        return SlowDetector(MODELS / "hazards.onnx", MODELS / "hazards_vocab.json", "auto", 2, 0.2)
    except NoSlowModel:
        pytest.skip("no hazard model (tools/export_hazards.py makes it)")


def alarm(model, image):
    w = HazardWatch(lambda: model)
    w.detector = model
    w._pass((image, "front", 0.0, 0.0, FOV), [])
    found = w.current("front", 0.0)
    return max((t.box.score for t in found if t.label in ("fire", "smoke")), default=0.0), {t.label for t in found}


def test_fire_and_its_lookalikes_in_photos(hazard_model):
    sources = json.loads((HAZARDS / "sources.json").read_text(encoding="utf-8"))
    assert all(v["licence"] in ("CC0", "Public domain") for v in sources.values())
    for name in ("fire_campfire", "fire_chip_pan_2", "fire_grease", "smoke_fire"):
        score, _ = alarm(hazard_model, photo(name))
        assert score >= 0.6, name
    for name in ("candle_flames", "fireplace", "gas_burner", "gas_stove", "steam_kettle", "sunset_boats", "sunset_lake", "tv_room", "woodstove"):
        score, _ = alarm(hazard_model, photo(name))
        assert score < 0.5, name
    assert "candle" in alarm(hazard_model, photo("candle_flames"))[1]
    room = photo("tv_room")
    tv = next(f.box for f in hazard_model.detect(room) if f.label == "tv")
    height, width = room.shape[:2]
    x0, y0 = int((tv.x + tv.w * 0.12) * width), int((tv.y + tv.h * 0.12) * height)
    x1, y1 = int((tv.x + tv.w * 0.88) * width), int((tv.y + tv.h * 0.8) * height)
    room[y0:y1, x0:x1] = cv2.resize(photo("fire_campfire"), (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
    score, names = alarm(hazard_model, room)
    assert score < 0.5 and "tv" in names


class Still:
    def __init__(self, camera, images):
        self.camera = camera
        self.images = images
        self.count = 0

    def open(self):
        pass

    def read(self, timeout_s):
        self.count += 1
        time.sleep(0.02)
        return Frame(self.images[self.camera], self.camera, time.monotonic(), self.count)

    def close(self):
        pass


class Quiet:
    can = {"faces": False, "bodies": False, "tags": False}

    def faces(self, image):
        return []

    def objects(self, image):
        return [], []

    def tags(self, image, fov):
        return []


def test_hazards_reach_the_sight_and_leave_when_the_eyes_close():
    images = {"front": blank(), "rear": blank()}

    async def scenario():
        hazards = HazardWatch(lambda: FakeHazards([("fire", Box(0.4, 0.4, 0.2, 0.2, 0.7)), ("tv", Box(0.0, 0.0, 0.1, 0.1, 0.6))]), every_s=0.1, nice=0)
        eyes = CameraEyes(lambda camera: Still(camera, images), Quiet(), Clock(), hazards=hazards, max_fps=20)
        eyes.start()
        try:
            deadline = time.monotonic() + 10
            sight = None
            while time.monotonic() < deadline:
                await asyncio.sleep(0.05)
                sight = eyes.latest()
                if sight and any(t.lane == "hazard" for t in sight.things):
                    break
            things = {t.label: t for t in sight.things}
            assert things["fire"].lane == "hazard" and things["fire"].score >= 0.7 and things["tv"].lane == "hazard"
            assert things["fire"].floor_m is None
            assert eyes.status()["hazards"]["passes"] >= 1
            eyes.set_enabled(False)
            assert hazards.current("front", time.monotonic()) == []
        finally:
            eyes.close()

    run(scenario(), timeout=30)


def test_snapshot_hands_over_one_jpeg_and_keeps_nothing():
    front = np.zeros((480, 640, 3), np.uint8)
    front[:, :320] = (0, 0, 255)
    rear = np.zeros((960, 1280, 3), np.uint8)
    rear[:] = (255, 0, 0)
    images = {"front": front, "rear": rear}

    async def scenario():
        eyes = CameraEyes(lambda camera: Still(camera, images), Quiet(), Clock(), max_fps=20)
        assert await eyes.snapshot() is None
        eyes.start()
        try:
            deadline = time.monotonic() + 10
            while not eyes.available and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
            data = await eyes.snapshot()
            assert isinstance(data, bytes) and data[:2] == b"\xff\xd8"
            picture = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            assert picture.shape == (480, 640, 3) and picture[240, 100, 2] > 200 and picture[240, 500, 2] < 50
            small = cv2.imdecode(np.frombuffer(await eyes.snapshot(max_side=200), np.uint8), cv2.IMREAD_COLOR)
            assert max(small.shape[:2]) == 200
            behind = cv2.imdecode(np.frombuffer(await eyes.snapshot(camera="rear"), np.uint8), cv2.IMREAD_COLOR)
            assert max(behind.shape[:2]) == 768 and behind[100, 100, 0] > 200
            assert eyes.camera() == "rear"
            assert not [k for k, v in vars(eyes).items() if isinstance(v, (bytes, bytearray))]
            eyes.set_enabled(False)
            assert await eyes.snapshot() is None
        finally:
            eyes.close()

    run(scenario(), timeout=30)


def test_the_hazard_watch_is_built_from_config(tmp_path):
    from pebble.eyes import hazard_watch

    assert hazard_watch({"hazards": False}, MODELS, Clock()) is None
    assert hazard_watch({}, tmp_path, Clock()) is None
    if (MODELS / "hazards.onnx").exists():
        built = hazard_watch({"hazard_every_s": 4.0}, MODELS, Clock())
        assert isinstance(built, HazardWatch) and built.every_s == 4.0


def test_the_watch_runs_on_numbers_alone():
    w, now = watch([("fire", Box(0.4, 0.4, 0.2, 0.2, 0.6))])
    assert [t.label for t in w.look(None, "front", 0.0, 0.0, FOV)] == ["fire"]
    box = w.fire_boxes()[0]
    for n in range(1, 31):
        now[0] = n * 0.1
        w.note(n * 0.1, 0.05 if n % 2 else 0.0, [(box, 250.0 if n % 2 else 140.0)])
    assert w.status()["close_watch"]
    found = w.look(None, "front", 3.0, 3.0, FOV)
    assert found[0].label == "fire" and found[0].box.score >= 0.85


def test_speaking_score_from_lip_shapes():
    from pebble.eyes.speaking import SpeakingMeter, score

    talk = [(i * 0.1, 0.1 if i % 2 else 0.01, 0.45) for i in range(9)]
    still = [(i * 0.1, 0.01, 0.45) for i in range(9)]
    grin = [(i * 0.1, 0.1 if i % 2 else 0.01, 0.75) for i in range(9)]
    chew = [(i * 0.1, 0.0, 0.5) for i in range(9)]
    slow = [(i * 0.1, (0.0, 0.03, 0.06, 0.09, 0.12, 0.09, 0.06, 0.03, 0.0)[i], 0.45) for i in range(9)]
    assert score(talk) >= 0.9 and score(still) == 0.0 and score(chew) == 0.0
    assert score(grin) == pytest.approx(score(talk) / 2, abs=0.01)
    assert 0 < score(slow) < 0.45 < score(talk)
    assert score(talk[:3]) is None and score([(0.0, 0.1, 0.4), (0.1, 0.0, 0.4), (0.15, 0.1, 0.4), (0.2, 0.0, 0.4)]) is None
    now = [0.0]
    meter = SpeakingMeter(None, monotonic=lambda: now[0])
    values = [meter.note(7, t, 100 + t, gap, width) for t, gap, width in talk]
    assert values[:4] == [None] * 4 and values[-1] >= 0.9
    assert meter.note(7, 2.0, 102.0, 0.01, 0.45) is None
    known = [v for v in values if v is not None]
    assert meter.spoke(100.3, 100.9) == {7: pytest.approx(sum(known) / len(known), abs=1e-3)}
    assert meter.spoke(50, 60) == {}
    for t, gap, width in talk:
        meter.note(8, 200 + t, 300 + t, gap, width)
    assert set(meter._said) == {8}
    assert not meter.active()
    meter.hear_voice(True)
    assert meter.active()
    meter.hear_voice(False)
    now[0] = 1.0
    assert meter.active()
    now[0] = 3.0
    assert not meter.active()
    meter.forget()
    assert meter.spoke(0, 1e9) == {}


MOUTHS = Path(__file__).resolve().parent / "data" / "mouths"


def test_speaking_on_real_faces():
    from pebble.eyes.detect import Detector
    from pebble.eyes.speaking import MouthModel, NoMouthModel, SpeakingMeter

    try:
        MouthModel(MODELS / "face_landmarks_detector.tflite")
    except NoMouthModel:
        pytest.skip("no face mesh model (python -m pebble.eyes.fetch)")
    sources = json.loads((MOUTHS / "sources.json").read_text(encoding="utf-8"))
    assert all(v["licence"] in ("CC0", "Public domain") for v in sources.values())
    detector = Detector(tags=False)
    results = {}
    for kind, meta in sources.items():
        meter = SpeakingMeter(lambda: MouthModel(MODELS / "face_landmarks_detector.tflite"), gate="always")
        values = []
        for n, path in enumerate(sorted((MOUTHS / kind).glob("*.jpg"))):
            image = cv2.imread(str(path))
            height, width = image.shape[:2]
            faces = detector.faces(image)
            f, marks = faces[0], detector.face_marks[0]
            t = n / meta["pictures_per_s"]
            out = meter.step(image, [(1, (f.x * width, f.y * height, f.w * width, f.h * height), [(u * width, v * height) for u, v in marks])], t, t)
            values.append(out.get(1))
        known = [v for v in values if v is not None]
        assert len(known) >= len(values) - 6, kind
        results[kind] = sum(known) / len(known)
    assert results["talk"] >= 0.5
    assert results["still"] < 0.1
    assert results["chew"] < 0.2


def test_speaking_reaches_the_sight_only_while_a_voice_is_heard():
    class Mouths:
        def __init__(self):
            self.n = 0

        def read(self, image, box, marks):
            self.n += 1
            return (0.1 if self.n % 2 else 0.01), 0.45

    class FaceFast(Quiet):
        can = {"faces": True, "bodies": False, "tags": False}

        def __init__(self):
            self.face_marks = []

        def faces(self, image):
            self.face_marks = [((0.45, 0.3), (0.55, 0.3), (0.5, 0.35), (0.46, 0.4), (0.54, 0.4))]
            return [Box(0.4, 0.2, 0.2, 0.25, 0.9)]

    from pebble.eyes.speaking import SpeakingMeter

    clock = FakeClock()
    meter = SpeakingMeter(Mouths, monotonic=clock.monotonic)
    eyes = CameraEyes(lambda camera: None, FaceFast(), clock, speaking=meter)
    picture = blank()
    for n in range(8):
        clock.advance(0.1)
        sight = eyes.process(Frame(picture, "front", clock.monotonic(), n))
    assert sight.people[0].speaking is None and meter.reads == 0
    eyes.hear_voice(True)
    for n in range(8, 16):
        clock.advance(0.1)
        sight = eyes.process(Frame(picture, "front", clock.monotonic(), n))
    person = sight.people[0]
    assert person.face and person.speaking is not None and person.speaking >= 0.9
    assert eyes.spoke(clock.now() - 1.0, clock.now())[person.track] >= 0.9
    assert eyes.status()["speaking"]["listening"]
    eyes.set_enabled(False)
    assert eyes.spoke(0, 1e12) == {}
