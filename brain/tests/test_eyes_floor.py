import asyncio
import math
import time

import pytest
from conftest import run
from floor_render import Scene

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from pebble.clock import Clock, FakeClock
from pebble.eyes import fetch as fetching
from pebble.eyes.floor import DepthModel, FloorScan, NoDepthModel, cut, rays
from pebble.eyes.service import CameraEyes
from pebble.eyes.sources import Frame
from pebble.seams.sight import FLOOR_OPEN_M, SeenThing

MODELS = fetching.MODELS


def true_depth(scene, pitch=8.0, width=238, rows=182):
    scene.render(pitch_deg=pitch, width=width, rows=rows)
    return (3.0 / scene.depth + 0.2).astype(np.float32)


def check(found, truth, tolerance, allowed=2):
    wrong = []
    for ray, want in zip(found, truth):
        if want is None:
            if ray.distance_m != FLOOR_OPEN_M and ray.distance_m < 1.9:
                wrong.append((ray, want))
        elif abs(ray.distance_m - want) > tolerance:
            wrong.append((ray, want))
    assert len(wrong) <= allowed, wrong


@pytest.mark.parametrize("pitch", (8.0, 0.0, -6.0))
def test_floor_rays_from_exact_depth(pitch):
    for scene in (Scene(wall_x=0.9), Scene(boxes=[(1.2, 1.6, -0.6, -0.2, 0, 0.4)], wall_x=1.9), Scene(wall_x=6.0, side_y=(-0.7, 0.7)), Scene(boxes=[(0.9, 1.0, -0.05, 0.05, 0, 0.06)], wall_x=6.0)):
        found, quality = rays(true_depth(scene, pitch), 70.0, 0.14, pitch)
        assert quality > 0.99 and len(found) == 32
        check(found, scene.truth([r.bearing_deg for r in found], reach=2.0), 0.05)
    drop = Scene(drop_x=1.2, wall_x=4.0)
    found, _ = rays(true_depth(drop, pitch), 70.0, 0.14, pitch)
    assert all(abs(r.distance_m - want) < 0.1 for r, want in zip(found, drop.truth([r.bearing_deg for r in found], reach=2.0)))
    bearings = [r.bearing_deg for r in found]
    assert bearings == sorted(bearings) and bearings[0] < -30 and bearings[-1] > 30


def test_no_floor_no_rays():
    wall = np.ones((182, 238), np.float32)
    assert rays(wall, 70.0, 0.14, 8.0) == (None, 0.0)


def test_low_things_cut_the_rays():
    found, _ = rays(true_depth(Scene(wall_x=6.0)), 70.0, 0.14, 8.0)
    cable = SeenThing("cable", 0.0, -20.0, 0.05, 0.4, 0.7, 0.0, floor_m=0.8, floor_bearing_deg=0.0)
    lamp = SeenThing("lamp", 10.0, -20.0, 0.05, 0.1, 0.9, 0.0, floor_m=0.5, floor_bearing_deg=10.0)
    out = cut(found, (cable, lamp))
    near = [r for r in out if abs(r.bearing_deg) <= 2.0]
    assert near and all(r.distance_m == 0.8 for r in near)
    assert all(r.distance_m == FLOOR_OPEN_M for r in out if abs(r.bearing_deg) > 12)


@pytest.fixture(scope="module")
def depth_model():
    try:
        return DepthModel(MODELS / "depth_anything_v2_small.onnx", 2)
    except NoDepthModel:
        pytest.skip("no depth model (python -m pebble.eyes.fetch)")


def test_floor_scan_on_rendered_rooms(depth_model):
    near = Scene(wall_x=0.9)
    found, _ = rays(depth_model(near.render()), 70.0, 0.14, 8.0)
    check(found, near.truth([r.bearing_deg for r in found], reach=2.0), 0.08)
    toy = Scene(boxes=[(0.9, 1.0, -0.05, 0.05, 0, 0.06, (40, 180, 230))], wall_x=3.0)
    found, _ = rays(depth_model(toy.render()), 70.0, 0.14, 8.0)
    middle = min(found, key=lambda r: abs(r.bearing_deg))
    assert middle.distance_m == pytest.approx(0.91, abs=0.1)
    corridor = Scene(wall_x=6.0, side_y=(-0.7, 0.7))
    found, _ = rays(depth_model(corridor.render()), 70.0, 0.14, 8.0)
    truth = corridor.truth([r.bearing_deg for r in found], reach=2.0)
    early = sum(1 for r, want in zip(found, truth) if r.distance_m < FLOOR_OPEN_M and (want is None or r.distance_m < want - 0.3))
    assert early <= 1
    drop = Scene(drop_x=1.2, wall_x=4.0)
    found, _ = rays(depth_model(drop.render()), 70.0, 0.14, 8.0)
    assert sum(1 for r in found if r.distance_m < 2.0) >= 16


class Flat:
    def __init__(self):
        self.calls = 0

    def __call__(self, image):
        self.calls += 1
        return true_depth(Scene(wall_x=0.9))


def test_the_scan_runs_while_moving_or_when_asked():
    now = [0.0]
    flat = Flat()
    scan = FloorScan(lambda: flat, lambda: now[0])
    scan.model = flat
    assert not scan._due(0.0)
    scan.set_moving(True)
    assert scan._due(0.0)
    found = scan.look(np.zeros((480, 640, 3), np.uint8), "front", 1.0, 100.0, 70.0, (0.14, 8.0, 0.0))
    assert found and min(r.distance_m for r in found) == pytest.approx(0.91, abs=0.03)
    now[0] = 0.1
    assert not scan._due(now[0])
    now[0] = 0.3
    assert scan._due(now[0])
    scan.set_moving(False)
    now[0] = 1.0
    assert scan._due(now[0])
    now[0] = 1.5
    assert not scan._due(now[0])
    scan.want()
    assert scan._due(now[0])
    rays_now, at = scan.current("front", 1.5)
    assert rays_now == found and at == 100.0
    assert scan.current("rear", 1.5) == ((), None) and scan.current("front", 9.0) == ((), None)
    assert scan.status()["passes"] == 1
    assert FloorScan(lambda: flat, lambda: now[0], gate="always")._due(now[0])
    assert not FloorScan(lambda: flat, lambda: now[0], gate="off")._due(now[0])


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


def test_floor_rays_reach_the_sight():
    flat = Flat()
    images = {"front": np.zeros((480, 640, 3), np.uint8), "rear": np.zeros((480, 640, 3), np.uint8)}

    async def scenario():
        scan = FloorScan(lambda: flat, every_s=0.05, nice=0)
        eyes = CameraEyes(lambda camera: Still(camera, images), Quiet(), Clock(), floor=scan, max_fps=20)
        eyes.start()
        try:
            deadline = time.monotonic() + 10
            while not eyes.available and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
            await asyncio.sleep(0.3)
            assert flat.calls == 0 and eyes.latest().floor == ()
            eyes.set_moving(True)
            sight = None
            while time.monotonic() < deadline:
                await asyncio.sleep(0.05)
                sight = eyes.latest()
                if sight and sight.floor:
                    break
            assert len(sight.floor) == 32 and sight.floor_at is not None and sight.floor_at <= sight.at
            assert min(r.distance_m for r in sight.floor) == pytest.approx(0.91, abs=0.03)
            assert eyes.status()["floor"]["moving"]
            eyes.set_moving(False)
            await asyncio.sleep(1.5)
            settled = flat.calls
            await asyncio.sleep(0.4)
            assert flat.calls == settled
            eyes.scan_floor()
            await asyncio.sleep(0.4)
            assert flat.calls == settled + 1
            eyes.set_enabled(False)
            assert scan.current("front", time.monotonic()) == ((), None)
        finally:
            eyes.close()

    run(scenario(), timeout=30)


def test_camera_motion_is_measured():
    rng = np.random.default_rng(0)
    texture = cv2.GaussianBlur((rng.random((480, 720, 3)) * 255).astype(np.uint8), (0, 0), 3)
    clock = FakeClock()
    eyes = CameraEyes(lambda camera: None, Quiet(), clock)
    assert eyes.motion() is None
    eyes.process(Frame(texture[:, :640].copy(), "front", clock.monotonic(), 1))
    clock.advance(0.1)
    eyes.process(Frame(texture[:, 40:680].copy(), "front", clock.monotonic(), 2))
    moved = eyes.motion()
    assert moved["shift_deg"][0] == pytest.approx(-40 * 70.0 / 640, abs=0.6) and abs(moved["shift_deg"][1]) < 0.6 and moved["change"] > 0
    clock.advance(0.1)
    eyes.process(Frame(texture[:, 40:680].copy(), "front", clock.monotonic(), 3))
    still = eyes.motion()
    assert abs(still["shift_deg"][0]) < 0.3 and still["change"] < 0.01


def test_place_prints():
    from pebble.eyes.prints import PrintModel

    if not (MODELS / "prints.onnx").exists():
        pytest.skip("no print model")
    near = Scene(wall_x=0.9).render()
    room = Scene(boxes=[(1.2, 1.6, -0.6, -0.2, 0, 0.4, (160, 120, 90))], wall_x=2.5, floor_colour=(60, 90, 160)).render()
    images = {"front": near, "rear": room}

    async def scenario():
        eyes = CameraEyes(lambda camera: Still(camera, images), Quiet(), Clock(), prints=lambda: PrintModel(MODELS / "prints.onnx", MODELS / "prints.json"), max_fps=20)
        eyes.start()
        try:
            deadline = time.monotonic() + 10
            while not eyes.available and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
            first = await eyes.place_print()
            again = await eyes.place_print()
            assert first is not None and len(first) == 384 and abs(math.sqrt(sum(x * x for x in first)) - 1) < 1e-3
            assert sum(a * b for a, b in zip(first, again)) > 0.99
            assert await eyes.place_print(camera="rear") is None
            assert await eyes.use_camera("rear")
            await asyncio.sleep(0.2)
            other = await eyes.place_print(camera="rear")
            assert sum(a * b for a, b in zip(first, other)) < 0.95
        finally:
            eyes.close()

    run(scenario(), timeout=60)
