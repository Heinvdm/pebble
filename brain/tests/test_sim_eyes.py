import math

import pytest
from conftest import run

from pebble.activities.home import pose_from_tag
from pebble.activities.seeing import body_bearing, person_gap_m
from pebble.seams.sight import DOCK_TAG_ID, NoEyes
from pebble.sim.eyes import SimEyes
from pebble.sim.world import Pose, SimPerson, World, room


def eyes_for(pose: Pose, people=(), tilt: float = 8.0, noise: bool = False) -> SimEyes:
    world = World(table=room(), pose=pose, people=list(people))
    return SimEyes(world, lambda: 123.0, lambda: tilt, noise=noise)


def test_front_camera_bearing_is_positive_to_pebbles_right():
    right = SimPerson("ina", 1500.0, -400.0, track=1)
    eyes = eyes_for(Pose(500.0, 0.0, 0.0), [right])
    sight = eyes.latest()
    assert sight.camera == "front" and sight.at == 123.0 and sight.fov_h_deg == 70.0
    person = sight.people[0]
    assert person.bearing_deg > 15
    assert body_bearing(person.bearing_deg, "front") < 0
    assert person.track == 1


def test_rear_camera_bearing_is_positive_to_pebbles_left():
    behind_left = SimPerson("sam", 200.0, 400.0)
    eyes = eyes_for(Pose(1500.0, 0.0, 0.0), [behind_left])
    run(eyes.use_camera("rear"))
    sight = eyes.latest()
    assert sight.camera == "rear" and sight.fov_h_deg == 65.0
    person = sight.people[0]
    assert person.bearing_deg > 10
    angle = body_bearing(person.bearing_deg, "rear")
    assert 90 < angle < 180


def test_people_out_of_the_field_of_view_are_not_seen():
    eyes = eyes_for(Pose(500.0, 0.0, 0.0), [SimPerson("ina", 500.0, 1200.0), SimPerson("mo", 100.0, 0.0)])
    assert eyes.latest().people == ()


def test_box_width_gives_back_the_distance_and_tilt_moves_elevation():
    ina = SimPerson("ina", 2000.0, 0.0)
    level = eyes_for(Pose(500.0, 0.0, 0.0), [ina], tilt=0.0).latest()
    up = eyes_for(Pose(500.0, 0.0, 0.0), [ina], tilt=30.0).latest()
    gap = person_gap_m(level.people[0], level, None)
    assert gap == pytest.approx(1.5 - 0.087 - 0.15 - 0.02, abs=0.03)
    assert up.people[0].elevation_deg < level.people[0].elevation_deg
    assert 0 < level.people[0].height_frac <= 1 and 0 < level.people[0].width_frac < 1


def test_the_dock_tag_is_seen_only_by_the_rear_camera_and_gives_back_the_pose():
    pose = Pose(900.0, 180.0, math.radians(-12.0))
    eyes = eyes_for(pose)
    assert eyes.latest().tags == ()
    run(eyes.use_camera("rear"))
    tag = eyes.latest().tags[0]
    assert tag.id == DOCK_TAG_ID
    found = pose_from_tag(tag)
    assert found.x == pytest.approx(0.9, abs=0.01)
    assert found.y == pytest.approx(0.18, abs=0.01)
    assert found.heading_deg == pytest.approx(-12.0, abs=0.5)


def test_tag_yaw_is_positive_when_the_camera_stands_to_its_own_left():
    eyes = eyes_for(Pose(1000.0, -200.0, math.atan2(200.0, -1000.0) - math.pi))
    run(eyes.use_camera("rear"))
    tag = eyes.latest().tags[0]
    assert tag.yaw_deg > 5
    assert abs(tag.bearing_deg) < 3


def test_the_tag_is_found_out_to_about_two_metres_and_yaw_is_steady_within_about_a_metre():
    def tag_at(metres: float, noise: bool = False):
        eyes = eyes_for(Pose(metres * 1000.0 + 35.0, 0.0, 0.0), noise=noise)
        run(eyes.use_camera("rear"))
        tags = eyes.latest().tags
        return tags[0] if tags else None

    assert tag_at(2.6) is None
    assert 0.05 <= tag_at(1.8).score < 0.3
    assert tag_at(0.8).score >= 0.5
    steady = [tag_at(0.35, noise=True).yaw_deg for _ in range(3)]
    assert max(abs(y) for y in steady) < 10


def test_no_eyes_sees_nothing():
    eyes = NoEyes()
    assert not eyes.available and eyes.latest() is None and eyes.camera() is None
    assert run(eyes.use_camera("rear")) is False
