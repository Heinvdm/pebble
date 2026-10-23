import asyncio
import math

import pytest

from pebble.link.protocol import Flags, Status
from pebble.nav.chart import Chart, Charts
from pebble.nav.drive import Driver
from pebble.nav.grid import FREE, OCCUPIED, Clearance, Grid
from pebble.nav.lead import LeadLock, Seen
from pebble.nav.local import Limits, LocalPlanner
from pebble.nav.mapview import page, png, svg
from pebble.nav.pose import HOME, LANDSCAPE, Pose
from pebble.nav.route import plan
from pebble.nav.senses import Senses
from pebble.nav.walls import Axis, lines
from pebble.nav.words import line
from pebble.safety.feeds import ListFeed
from pebble.seams.sight import FLOOR_OPEN_M, FloorRay, SeenPerson, Sight

from conftest import run


def wall(grid: Grid, x0: float, y0: float, x1: float, y1: float) -> None:
    steps = int(math.hypot(x1 - x0, y1 - y0) / 0.02) + 1
    for i in range(steps + 1):
        t = i / steps
        grid.mark(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, 120)


def status(ms: int, left: int, right: int, down: int = 32, dock: int = 0) -> Status:
    return Status(ms=ms, enc_left=left, enc_right=right, front_mm=-1, down_mm=down, bump=0, dock=dock, pack_mv=3900, tilt=8, flags=Flags.NONE)


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def test_grid_rays_mark_free_and_hit_and_bumps_stay():
    grid = Grid()
    grid.ray(0.0, 0.0, 1.0, 0.0, True, 40, 10)
    grid.ray(0.0, 0.0, 1.0, 0.0, True, 40, 10)
    assert grid.free_at(0.5, 0.0)
    assert grid.value(*grid.cell(1.0, 0.0)) > 128
    grid.touch(0.5, 0.5, 1.0)
    for _ in range(30):
        grid.ray(0.0, 0.5, 1.0, 0.5, False, 0, 10)
    assert grid.occupied_at(0.5, 0.5)
    grid.cliff(2.0, 0.0, 0.05)
    assert grid.occupied_at(2.0, 0.0)


def test_grid_caps_camera_evidence_so_old_walls_clear():
    grid = Grid()
    for _ in range(20):
        grid.mark(1.0, 1.0, 22, 190)
    assert grid.value(*grid.cell(1.0, 1.0)) == 190
    for _ in range(5):
        grid.add(*grid.cell(1.0, 1.0), -10)
    assert not grid.occupied_at(1.0, 1.0)


def test_grid_round_trip_and_prune():
    grid = Grid()
    wall(grid, 0.0, 0.0, 3.0, 0.0)
    grid.ray(0.0, 1.0, 2.0, 1.0, False, 0, 30)
    grid.touch(1.0, 2.0, 5.0)
    grid.add(*grid.cell(30.0, 30.0), 3)
    data = grid.to_dict()
    back = Grid.from_dict(data, now=9.0)
    assert back.occupied_at(1.5, 0.0) and back.free_at(1.0, 1.0) and back.occupied_at(1.0, 2.0)
    assert back.prune(100) >= 1
    assert back.occupied_at(1.5, 0.0)


def test_clearance_measures_distance_to_walls():
    grid = Grid()
    wall(grid, -2.0, 1.0, 2.0, 1.0)
    clear = Clearance(grid, 0.0, 0.0, 1.5, cap_m=1.2)
    assert clear.at(0.0, 0.0) == pytest.approx(0.95, abs=0.08)
    assert clear.at(0.0, 0.7) <= 0.36
    near = Clearance(grid, 0.0, 0.0, 1.5, [(0.5, 0.0, 0.2)])
    assert near.at(0.0, 0.0) < 0.4


def test_route_goes_round_a_wall_through_the_gap():
    grid = Grid()
    wall(grid, -3.0, 2.0, 1.0, 2.0)
    wall(grid, 2.0, 2.0, 5.0, 2.0)
    path = plan(grid, (0.0, 0.0), (0.0, 4.0))
    assert path is not None
    assert any(1.0 < x < 2.0 and 1.5 < y < 2.5 for x, y in path) or any(1.0 < x < 2.0 for x, _ in path)
    enclosed = Grid()
    for x0, y0, x1, y1 in ((-1, -1, 1, -1), (1, -1, 1, 1), (1, 1, -1, 1), (-1, 1, -1, -1)):
        wall(enclosed, x0, y0, x1, y1)
    assert plan(enclosed, (0.0, 0.0), (4.0, 0.0)) is None


def test_route_widens_its_search_for_far_detours():
    grid = Grid()
    wall(grid, 0.0, -10.0, 0.0, 9.0)
    path = plan(grid, (-1.0, 0.0), (1.0, 0.0))
    assert path is not None and max(y for _, y in path) > 9.0


def test_local_planner_drives_on_and_never_into_a_wall():
    grid = Grid()
    planner = LocalPlanner()
    clear = Clearance(grid, 0.0, 0.0, 1.25)
    choice = planner.choose(clear, 0.0, 0.0, 0.0, 0.2, 0.0, (2.0, 0.0), Limits(0.25, 0.25))
    assert choice.v > 0.15 and abs(choice.w) < 0.6
    wall(grid, 0.3, -1.0, 0.3, 1.0)
    clear = Clearance(grid, 0.0, 0.0, 1.25)
    choice = planner.choose(clear, 0.0, 0.0, 0.0, 0.2, 0.0, (2.0, 0.0), Limits(0.25, 0.25))
    free, _ = planner.free_along(clear, 0.0, 0.0, 0.0, choice.v, choice.w, 1.6)
    assert choice.v < 0.15
    assert free == math.inf or choice.v * 0.2 + choice.v ** 2 / 1.0 <= max(0.0, free - 0.03) + 1e-6


def test_local_planner_can_back_out_of_a_squeeze():
    grid = Grid()
    wall(grid, -1.0, 0.1, 1.0, 0.1)
    clear = Clearance(grid, 0.0, 0.0, 1.25)
    planner = LocalPlanner()
    choice = planner.choose(clear, 0.0, 0.0, 0.0, 0.0, 0.0, (1.0, -1.0), Limits(0.2, 0.25))
    assert not choice.blocked


def test_pose_takes_the_landscape_gyro_after_a_turn_and_keeps_heading_straight():
    clock = Clock()
    gyro = ListFeed()
    pose = Pose(20.7, 165.0, gyro=gyro, tilt=lambda: 8.0, monotonic=clock, prior=LANDSCAPE)
    pose.reset(0.0, 0.0, 0.0)
    pose.start_visit("v", 0.0, 0.0, 0.0)
    left = right = 0
    ms = 0
    tilt = math.radians(8.0)

    def step(rate: float, dl: float, dr: float, n: int):
        nonlocal left, right, ms
        for _ in range(n):
            for k in range(5):
                gyro.push(clock.t + 0.01 * (k + 1), rate * math.cos(tilt) + 0.004, 0.0, rate * math.sin(tilt))
            clock.t += 0.05
            ms += 50
            left += int(round(dl * 20.7))
            right += int(round(dr * 20.7))
            pose.update(status(ms, left, right))

    step(0.0, 0.0, 0.0, 30)
    assert pose.bias_known
    step(1.0, -6.9, 6.9, 30)
    assert pose.axis is not None
    before = pose.heading
    step(0.02, 10.0, 10.0, 40)
    assert abs(math.degrees(pose.heading - before) - math.degrees(0.02 * 2.0)) < 1.0
    assert pose.local_usable and not pose.usable


def test_pose_docked_is_home_and_relocate_returns_home():
    clock = Clock()
    pose = Pose(20.7, 165.0, monotonic=clock)
    said = []
    pose.listeners.append(said.append)
    pose.update(status(50, 0, 0, dock=1))
    assert pose.usable and pose.frame == HOME
    pose.start_visit("abc")
    assert not pose.usable and pose.local_usable
    pose.relocate(1.0, 0.0, 90.0)
    assert pose.usable and "home" in said
    x, y, heading = pose.pose()
    assert (x, y, heading) == (1.0, 0.0, 90.0)
    pose.anchor(2.0, 0.0, 0.5)
    assert pose.x == pytest.approx(1.5)


def test_pose_counts_carry_steps_and_knows_when_put_down():
    clock = Clock()
    accel = ListFeed()
    pose = Pose(20.7, 165.0, accel=accel, monotonic=clock)
    pose.start_visit("v")
    pose.update(status(50, 0, 0))
    pose.felt("lifted")
    assert pose.carried
    for i in range(40):
        clock.t += 0.05
        accel.push(clock.t, 0.0, 0.0, 9.81 + (4.0 if i % 10 == 0 else 0.0))
        pose.update(status(100 + 50 * i, 0, 0, down=-1))
    assert pose.steps >= 3 and pose.x > 1.0 and pose.drift_m() > 0.5
    for i in range(30):
        clock.t += 0.05
        pose.update(status(3000 + 50 * i, 0, 0, down=32))
    assert not pose.carried


def person(track, bearing, width, score=0.9):
    return SeenPerson(bearing, 5.0, 0.6, width, score, True, track)


def seen(track, x, y, height=1.65):
    return Seen(track, x, y, math.hypot(x, y), 0.0, height, True, None, person(track, 0.0, 0.1), 0.0)


def test_lead_lock_keeps_its_person_and_drops_crumbs():
    lock = LeadLock("Ina", 1)
    lock.start([seen(1, 2.0, 0.0)], 0.0, 1)
    for i in range(1, 20):
        lock.update([seen(1, 2.0 + 0.1 * i, 0.0), seen(2, 2.0, 2.0, 1.85)], 0.1 * i)
    assert lock.track == 1 and len(lock.trail) >= 10
    assert lock.speed() == pytest.approx(1.0, abs=0.2)
    lock.consume(2.5, 0.0)
    assert lock.trail[0][0] >= 2.3


def test_lead_lock_never_takes_a_lookalike_without_an_answer():
    lock = LeadLock("Ina", 1)
    lock.start([seen(1, 2.0, 0.0)], 0.0, 1)
    for i in range(6):
        lock.took_print(1, (1.0, 0.0, 0.0), 2.5 + 0.1 * i)
    lock.track_since = 0.0
    lock.update([seen(1, 2.0, 0.0)], 3.0)
    lock.took_print(3, (0.8, 0.6, 0.0), 3.1)
    assert lock.update([seen(3, 2.2, 0.3)], 5.0) is None
    assert lock.maybe is not None and lock.track == 1
    assert lock.update([seen(3, 2.2, 0.3)], 5.2, heard_from=3) is not None


def test_lead_lock_rejects_a_different_height():
    lock = LeadLock("Ina", 1)
    lock.start([seen(1, 2.0, 0.0)], 0.0, 1)
    for i in range(1, 8):
        lock.update([seen(1, 2.0, 0.0)], 0.1 * i)
    assert lock.update([seen(5, 2.1, 0.0, 1.95)], 1.5) is None


def test_senses_floor_scan_and_glass():
    grid = Grid()
    senses = Senses(grid, floor_reach_m=2.0)
    rays = (FloorRay(0.0, 1.5, 0.8), FloorRay(20.0, FLOOR_OPEN_M, 0.8))
    sight = Sight(1.0, "front", 70.0, floor=rays)
    for _ in range(3):
        senses.floor(sight, 0.0, 0.0, 0.0)
    assert grid.occupied_at(1.5 + 0.087, 0.0)
    assert grid.free_at(1.0, 0.0)
    assert not grid.known(*grid.cell(2.6, -0.95))
    assert not senses.looked_clear(5.0, 5.0, 0.0)
    for _ in range(3):
        grid.ray(4.0, 5.0, 6.0, 5.0, False, 0, 10)
    assert senses.looked_clear(5.0, 5.0, 0.0)
    senses.bump("B", 5.0, 5.0, 0.0, 1.0, unseen=True)
    assert grid.occupied_at(5.13, 5.4) and grid.occupied_at(5.13, 4.6)


def test_walls_square_the_heading_up():
    axis = Axis()
    straight = [(1.0 + 0.1 * i, 2.0) for i in range(10)]
    for _ in range(8):
        assert axis.offer(lines(straight), 0.1) is None
    assert axis.angle == pytest.approx(0.0, abs=1e-6)
    tilted = [(1.0 + 0.1 * i, 2.0 + 0.1 * i * math.tan(math.radians(2.0))) for i in range(10)]
    turn = axis.offer(lines(tilted), 1.0)
    assert turn is not None and turn < 0
    skew = [(1.0 + 0.1 * i, 2.0 + 0.1 * i * math.tan(math.radians(30.0))) for i in range(10)]
    assert axis.offer(lines(skew), 1.0) is None


def test_chart_spots_doorways_rooms_and_saving(store):
    charts = Charts(store)
    chart = charts.visit()
    chart.remember_spot("car", 1.0, 2.0)
    assert chart.place("car") is not None and "car" in chart.spots()
    wall(chart.grid, 3.0, -2.0, 3.0, -0.45)
    wall(chart.grid, 3.0, 0.45, 3.0, 2.0)
    for x in (2.0, 2.4, 2.8, 3.0, 3.2, 3.6, 4.0, 4.6):
        chart.moved(x, 0.0, math.pi / 2.0 * 0.0)
    for x in (2.0, 2.4, 2.8, 3.0, 3.2, 3.6, 4.0, 4.6):
        chart.moved(x, 0.0, math.pi / 2.0)
    chart.width_at(3.0, 0.0, 0.0)
    for _ in range(4):
        chart.saw("fridge", 6.0, 6.0)
        chart.saw("oven", 6.5, 6.0)
    made = chart.name_rooms()
    assert any(p.name == "kitchen" for p in made)
    assert chart.place_at(6.2, 6.0) == "kitchen"
    charts.save()
    again = Charts(store)
    loaded = again.charts[chart.id]
    assert loaded.place("car") is not None and loaded.place("kitchen") is not None
    assert loaded.grid.occupied_at(3.0, 1.0)


def test_chart_finds_a_doorway_when_passing_a_narrow_gap():
    chart = Chart("x")
    wall(chart.grid, 3.0, -3.0, 3.0, -0.45)
    wall(chart.grid, 3.0, 0.45, 3.0, 3.0)
    wall(chart.grid, 2.9, -3.0, 2.9, -0.45)
    wall(chart.grid, 2.9, 0.45, 2.9, 3.0)
    for i in range(30):
        chart.moved(2.0 + 0.1 * i, 0.0, 0.0)
    assert any(p.kind == "doorway" for p in chart.places)


def test_map_view_draws_svg_page_and_png(tmp_path):
    chart = Chart("x")
    wall(chart.grid, 0.0, 0.0, 2.0, 0.0)
    chart.grid.ray(0.0, 1.0, 2.0, 1.0, False, 0, 30)
    chart.remember_spot("start", 0.5, 0.5, "start")
    chart.path = [(0.0, 0.5), (1.0, 0.5)]
    text = svg(chart, (1.0, 0.5, 0.0), [(1.5, 0.5), (2.0, 0.8)])
    assert text.startswith("<svg") and "polyline" in text and "start" in text
    html = page(chart, None, [])
    assert "<meta name=\"viewport\"" in html and "http" not in html.replace("http-equiv", "").replace("http://www.w3.org/2000/svg", "")
    target = tmp_path / "map.png"
    png(chart, str(target), (1.0, 0.5, 0.0), [(1.5, 0.5), (2.0, 0.8)])
    assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_words():
    assert line("waiting", "Ina") == "I'll wait here for you, Ina."
    assert line("stuck", where="by the chair") == "I'm stuck by the chair. Could you help me?"
    assert line("call") == "Hello?"


class FakeProfile:
    max_speed_mm_s = 250
    max_power = 600
    cpm = 20.7


class FakeBody:
    profile = FakeProfile()

    def __init__(self):
        self.sent = []
        self.telemetry = type("T", (), {"encoders": lambda self: None})()

    async def drive(self, left, right):
        self.sent.append((left, right))
        return True


def test_driver_obeys_the_people_law_and_sprints_only_when_allowed():
    driver = Driver(FakeBody())
    assert driver.wheel_cap(False, True, False) == pytest.approx(0.25)
    assert driver.wheel_cap(False, False, False) == pytest.approx(driver.cruise)
    near = driver.wheel_cap(True, True, False)
    assert near == pytest.approx(driver.speed_of(300))
    assert driver.wheel_cap(False, True, True) <= 0.03
    run(driver.send(0.25, 0.0, near, 1.0))
    left, right = driver.body.sent[-1]
    assert left <= 300 + 1 and right <= 300 + 1
