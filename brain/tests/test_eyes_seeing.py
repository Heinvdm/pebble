import asyncio
import math
import time
from pathlib import Path

import pytest
from conftest import run

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2", reason="OpenCV is not installed")

from pebble.clock import Clock, FakeClock
from pebble.eyes import fetch as fetching
from pebble.eyes.geometry import Box
from pebble.eyes.pose import INDEX, facing, held_by, wrists
from pebble.eyes.prints import MATCH, PrintBook, dock_box, find
from pebble.eyes.service import CameraEyes
from pebble.eyes.slow import SlowFound
from pebble.eyes.sources import Frame
from pebble.seams.sight import BODY_POINTS, DOCK_TAG_ID

MODELS = fetching.MODELS
DATA = Path(__file__).resolve().parent / "data"
TEAPOTS = DATA / "teapots"
PORTRAIT = MODELS / "samples" / "portrait.jpg"


def pose_raw(**points):
    raw = np.zeros((len(BODY_POINTS), 3), np.float32)
    for name, (u, v) in points.items():
        raw[INDEX[name]] = (u, v, 0.9)
    return raw


def test_facing_reads_the_turn_of_the_head():
    frontal = pose_raw(nose=(0.5, 0.2), left_eye=(0.53, 0.18), right_eye=(0.47, 0.18), left_ear=(0.57, 0.2), right_ear=(0.43, 0.2))
    assert abs(facing(frontal)) < 3
    turned = pose_raw(nose=(0.54, 0.2), left_eye=(0.56, 0.18), right_eye=(0.5, 0.18), left_ear=(0.57, 0.2), right_ear=(0.45, 0.2))
    assert facing(turned) > 20
    other = pose_raw(nose=(0.46, 0.2), left_eye=(0.5, 0.18), right_eye=(0.44, 0.18), left_ear=(0.55, 0.2), right_ear=(0.43, 0.2))
    assert facing(other) < -20
    assert facing(pose_raw(left_shoulder=(0.6, 0.4), right_shoulder=(0.4, 0.4))) == 180.0
    assert facing(pose_raw()) is None
    assert facing(pose_raw(nose=(0.6, 0.2), left_ear=(0.52, 0.2))) == 70.0


def test_a_thing_at_a_wrist_is_held():
    raw = pose_raw(left_wrist=(0.7, 0.5), left_elbow=(0.6, 0.45), right_wrist=(0.2, 0.6))
    hands = wrists(raw)
    assert len(hands) == 2
    assert held_by(Box(0.68, 0.42, 0.08, 0.08, 0.9), hands, 4 / 3)
    assert held_by(Box(0.15, 0.58, 0.06, 0.06, 0.9), hands, 4 / 3)
    assert not held_by(Box(0.4, 0.1, 0.05, 0.05, 0.9), hands, 4 / 3)
    assert wrists(pose_raw()) == []


def test_the_print_book_keeps_views_per_key():
    book = PrintBook(max_views=3)
    a = np.zeros(4, np.float32)
    a[0] = 2.0
    b = np.array([0.0, 1.0, 0.0, 0.0], np.float32)
    assert book.remember("ball", a) == 1 and book.remember("ball", b) == 2
    for _ in range(3):
        book.remember("ball", a)
    assert book.remember("mug", b, replace=True) == 1 and book.remember("mug", a, replace=True) == 1
    scores = book.scores("ball", np.stack([a / 2, b, np.array([0, 0, 1.0, 0], np.float32)]))
    assert scores[0] == pytest.approx(1.0) and scores[1] == pytest.approx(0.0) and scores[2] == pytest.approx(0.0)
    assert book.best(np.stack([b]))[0] == (None, 0.0) and book.best(np.stack([a]))[0] == ("ball", pytest.approx(1.0))
    assert book.forget("ball") and not book.forget("ball") and book.keys() == ["mug"]
    for bad in ([], [float("nan"), 1.0], [0.0, 0.0]):
        with pytest.raises(ValueError):
            book.remember("x", bad)
    with pytest.raises(ValueError):
        book.remember("mug", [1.0, 0.0])


class Picture:
    shape = (480, 640, 3)
    ndim = 3


class FakeFast:
    can = {"faces": True, "bodies": True, "tags": True}

    def faces(self, image):
        return []

    def objects(self, image):
        from pebble.eyes.detect import Found

        return [Box(0.3, 0.1, 0.4, 0.85, 0.9)], [Found(Box(0.66, 0.42, 0.08, 0.08, 0.7), "cup", False, "cup"), Found(Box(0.05, 0.05, 0.08, 0.08, 0.7), "book", False, "book")]

    def tags(self, image, fov):
        return []


class FakePose:
    def __init__(self):
        self.calls = 0

    def points(self, image, box):
        self.calls += 1
        return pose_raw(nose=(0.52, 0.2), left_eye=(0.54, 0.18), right_eye=(0.49, 0.18), left_ear=(0.57, 0.2), right_ear=(0.45, 0.2), left_wrist=(0.7, 0.46), left_elbow=(0.62, 0.42), left_shoulder=(0.58, 0.3), right_shoulder=(0.42, 0.3))


def test_people_get_body_points_and_held_things_are_marked():
    clock = FakeClock()
    pose = FakePose()
    eyes = CameraEyes(lambda camera: None, FakeFast(), clock, pose=pose, pose_hz=5)
    sights = []
    for n in range(6):
        clock.advance(0.1)
        sights.append(eyes.process(Frame(Picture(), "front", clock.monotonic(), n)))
    assert pose.calls == 3
    person = sights[-1].people[0]
    assert [p.name for p in person.points] == list(BODY_POINTS)
    assert person.facing_deg is not None and person.facing_deg > 5
    nose = person.points[0]
    assert nose.score == pytest.approx(0.9) and nose.elevation_deg > 0
    things = {t.label: t for t in sights[-1].things}
    assert things["cup"].held and not things["book"].held
    ids = [person.track] + [t.track for t in sights[-1].things]
    assert len(set(ids)) == len(ids)
    lonely = CameraEyes(lambda camera: None, type("NoOne", (FakeFast,), {"objects": lambda self, image: ([], [])})(), clock, pose=pose)
    lonely.process(Frame(Picture(), "front", clock.monotonic(), 9))
    assert pose.calls == 3


def test_body_points_on_a_real_photo():
    from pebble.eyes.detect import Detector
    from pebble.eyes.pose import NoPoseModel, PoseModel

    if not PORTRAIT.exists():
        pytest.skip("run python -m pebble.eyes.fetch --samples first")
    try:
        pose = PoseModel(MODELS / "rtmpose_t_body7_256x192.onnx")
    except NoPoseModel:
        pytest.skip("no pose model")
    detector = Detector(tags=False)
    image = cv2.imread(str(PORTRAIT))
    image = cv2.resize(image, (512, 640), interpolation=cv2.INTER_AREA)
    bodies, _ = detector.objects(image)
    raw = pose.points(image, bodies[0])
    nose, left_eye, right_eye = raw[INDEX["nose"]], raw[INDEX["left_eye"]], raw[INDEX["right_eye"]]
    left_shoulder, right_shoulder = raw[INDEX["left_shoulder"]], raw[INDEX["right_shoulder"]]
    assert min(nose[2], left_eye[2], right_eye[2], left_shoulder[2], right_shoulder[2]) > 0.5
    assert right_eye[0] < nose[0] < left_eye[0] and nose[1] < left_shoulder[1] - 0.1
    assert right_shoulder[0] < 0.4 < 0.6 < left_shoulder[0]
    assert abs(facing(raw)) < 15


def prints_model():
    from pebble.eyes.prints import NoPrintModel, PrintModel

    try:
        return PrintModel(MODELS / "prints.onnx", MODELS / "prints.json")
    except NoPrintModel:
        pytest.skip("no print model (tools/export_prints.py)")


def whole(path):
    return cv2.imread(str(path)), Box(0.05, 0.1, 0.9, 0.8, 1.0)


def test_prints_know_the_same_teapot_from_its_other_side():
    model = prints_model()
    names = ("painted_front", "painted_back", "white", "pewter")
    vecs = {}
    for name in names:
        image, box = whole(TEAPOTS / f"{name}.jpg")
        vecs[name] = model.embed(image, [box])[0]
    assert all(abs(float(np.linalg.norm(v)) - 1.0) < 1e-4 for v in vecs.values())
    same = float(vecs["painted_front"] @ vecs["painted_back"])
    others = [float(vecs["painted_front"] @ vecs[n]) for n in ("white", "pewter")] + [float(vecs["painted_back"] @ vecs[n]) for n in ("white", "pewter")]
    assert same > 0.85 and max(others) < MATCH < same


@pytest.fixture(scope="module")
def dock_world():
    from dock_render import COLOURS, box_mesh, load_dock, looking_at, render, room

    dock = load_dock()
    target = np.array([-0.1, 0.0, 0.07])
    grey = box_mesh(-0.16, -0.04, -0.06, 0.06, 0.0, 0.15)

    def scene(distance, bearing, seed=3, with_dock=True, extras=(), aim=0.0):
        camera = looking_at(target, distance, bearing, 0.15, 1280, 960, 65.0, aim_offset_deg=aim)
        meshes = [(v, f, COLOURS[n]) for n, (v, f) in dock["parts"].items()] if with_dock else []
        meshes += [(v + offset, f, COLOURS["wall"]) for (v, f), offset in extras]
        image = render(meshes, camera, room(camera, seed), dock["tag"] if with_dock else None)
        return np.ascontiguousarray(np.clip(image, 0, 255).astype(np.uint8)[:, :, ::-1]), camera

    corners = np.array([[x, y, z] for x in (-0.1065, 0.0075) for y in (-0.102, 0.102) for z in (0.0, 0.156)])

    def truth(camera):
        c = camera.to_cam(corners)
        u = camera.w / 2 + camera.f * c[:, 0] / c[:, 2]
        v = camera.h / 2 + camera.f * c[:, 1] / c[:, 2]
        return (u.min() + u.max()) / 2 / camera.w, (v.min() + v.max()) / 2 / camera.h

    return scene, truth, (grey, np.array([0.0, 0.45, 0.0]))


def test_the_dock_box_comes_from_its_tag(dock_world):
    from pebble.eyes.detect import Detector

    scene, truth, _ = dock_world
    detector = Detector(faces=False, bodies=False)
    image, camera = scene(0.6, 12)
    tag = next(t for t in detector.tags(image, 65.0) if t.seen.id == DOCK_TAG_ID)
    box = dock_box(tag.rotation, tag.translation, 1280, 960, 65.0)
    cx, cy = truth(camera)
    assert box is not None and abs(box.cx - cx) < 0.02 and abs(box.cy - cy) < 0.02
    near, _ = scene(0.12, 0)
    close = [t for t in detector.tags(near, 65.0) if t.seen.id == DOCK_TAG_ID]
    assert not close or dock_box(close[0].rotation, close[0].translation, 1280, 960, 65.0) is None


def test_look_for_finds_the_charger_across_the_room_and_nothing_else(dock_world):
    from pebble.eyes.detect import Detector
    from pebble.eyes.slow import SlowDetector

    if not (MODELS / "objects.onnx").exists():
        pytest.skip("no slow-lane model")
    scene, truth, grey = dock_world
    model = prints_model()
    detector = Detector(faces=False, bodies=False)
    slow = SlowDetector(MODELS / "objects.onnx", MODELS / "objects_vocab.json", threads=2)
    book = PrintBook()
    for distance, bearing in ((0.35, 0), (0.6, 12), (1.0, -10)):
        image, _ = scene(distance, bearing, seed=1)
        tag = next(t for t in detector.tags(image, 65.0) if t.seen.id == DOCK_TAG_ID)
        book.remember("charger", model.embed(image, [dock_box(tag.rotation, tag.translation, 1280, 960, 65.0)])[0])
    cat = cv2.imread(str(MODELS / "samples" / "cat.jpg")) if (MODELS / "samples" / "cat.jpg").exists() else None
    for distance, bearing, aim in ((1.5, 20, 8), (2.0, -15, -10), (2.5, 0, 12), (3.0, 25, -6)):
        image, camera = scene(distance, bearing, seed=5, extras=[grey], aim=aim)
        if cat is not None:
            image[560:755, 60:320] = cv2.resize(cat, (260, 195), interpolation=cv2.INTER_AREA)
        box, score, _ = find(model, book, "charger", image, [f.box for f in slow.detect(image, score=0.1)])
        cx, cy = truth(camera)
        assert score >= MATCH, (distance, bearing, score)
        assert abs(box.cx - cx) < 0.05 and abs(box.cy - cy) < 0.06, (distance, bearing, box, cx, cy)
    empty, _ = scene(2.0, 10, seed=11, with_dock=False, extras=[(grey[0], np.zeros(3)), (grey[0], np.array([0.2, -0.4, 0.0]))])
    for image in (empty, cv2.imread(str(TEAPOTS / "white.jpg"))):
        image = np.ascontiguousarray(image)
        _, score, _ = find(model, book, "charger", image, [f.box for f in slow.detect(image, score=0.1)])
        assert score < MATCH


class Swap:
    def __init__(self, camera, holder):
        self.camera = camera
        self.holder = holder
        self.count = 0

    def open(self):
        pass

    def read(self, timeout_s):
        self.count += 1
        time.sleep(0.02)
        return Frame(self.holder[self.camera], self.camera, time.monotonic(), self.count)

    def close(self):
        pass


class TeapotFast(FakeFast):
    def objects(self, image):
        from pebble.eyes.detect import Found

        return [], [Found(Box(0.1, 0.15, 0.8, 0.7, 0.8), "teapot", False, "teapot")]


def test_fingerprints_remembered_prints_and_known_things_through_the_eyes():
    from pebble.eyes.prints import NoPrintModel, PrintModel
    from pebble.eyes.slow import SlowLane

    if not (MODELS / "prints.onnx").exists():
        pytest.skip("no print model")

    class FakeSlow:
        coco_depth = {}

        def __init__(self):
            self.cv2, self.np = cv2, np

        def detect(self, image, score=None):
            return [SlowFound(Box(0.1, 0.15, 0.8, 0.7, 0.9), "teapot", False, "teapot", 9)]

    async def scenario():
        holder = {"front": cv2.imread(str(TEAPOTS / "painted_front.jpg")), "rear": cv2.imread(str(TEAPOTS / "pewter.jpg"))}
        lane = SlowLane(FakeSlow, every_s=0.05, nice=0)
        eyes = CameraEyes(lambda camera: Swap(camera, holder), TeapotFast(), Clock(), slow=lane, prints=lambda: PrintModel(MODELS / "prints.onnx", MODELS / "prints.json"), max_fps=20)
        eyes.start()
        try:
            deadline = time.monotonic() + 10
            while not (eyes.available and eyes.latest().things) and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
            track = eyes.latest().things[0].track
            vec = await eyes.fingerprint(track)
            assert vec is not None and len(vec) == 384 and abs(math.sqrt(sum(x * x for x in vec)) - 1) < 1e-3
            assert await eyes.fingerprint(99999) is None
            assert eyes.remember_print("my teapot", vec) == 1
            holder["front"] = cv2.imread(str(TEAPOTS / "painted_back.jpg"))
            eyes.moved()
            deadline = time.monotonic() + 10
            known = None
            while time.monotonic() < deadline and known is None:
                await asyncio.sleep(0.1)
                sight = eyes.latest()
                known = next((t for t in (sight.things if sight else ()) if t.known == "my teapot"), None)
            assert known is not None and known.known_score >= MATCH
            found = await eyes.look_for("my teapot")
            assert found is not None and found.known == "my teapot" and found.lane == "slow" and found.label == "my teapot"
            assert await eyes.look_for("never seen") is None
            assert await eyes.look_for("my teapot", camera="rear") is None
            assert eyes.camera() == "rear"
            assert eyes.forget_print("my teapot") and await eyes.look_for("my teapot") is None
            assert eyes.status()["prints"]["loaded"]
        finally:
            eyes.close()

    run(scenario(), timeout=90)
