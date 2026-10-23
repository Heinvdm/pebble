import asyncio
import json
import math
import urllib.request

import pytest

from pebble.nav.follow import Follower
from pebble.nav.lead import LeadLock, Seen
from pebble.nav.navigator import FollowControl, Lead
from pebble.nav.sim.building import Building, Strip, Walker, m, wall
from pebble.seams.sight import SeenThing, Sight
from pebble.nav.sim.rig import Rig
from pebble.sim.world import Pose, Table

from conftest import run


def corridor(segments=(), boxes=(), cliffs=(), strips=(), start=(1.0, 1.0, 0.0), people=()):
    table = Table(0.0, 12000.0, 0.0, 4000.0, 0.0, frozenset({"x_min", "x_max", "y_min", "y_max"}))
    return Building(table, list(segments), list(boxes), list(strips), list(cliffs), Pose(*m(start[0], start[1]), start[2]), list(people), [])


def test_follows_a_slow_walker_down_a_corridor_and_keeps_the_gap():
    lead = Walker("ina", *m(2.2, 1.0), speed_mm_s=200.0, height_mm=1650.0, track=1)
    lead.go([m(2.2, 1.0), m(7.0, 1.0)], 200.0)
    world = corridor(people=[lead])

    async def go():
        rig = Rig(world)
        await rig.run(2.0)
        rig.visit()
        task = asyncio.ensure_future(rig.nav.follow(rig.kit, Lead("ina", "Ina", 1), FollowControl(1.0)))
        await rig.until(task, 40.0)
        gap = math.hypot(lead.x - world.pose.x, lead.y - world.pose.y) / 1000.0
        position, heading = rig.error()
        follower = rig.nav.following
        state = follower.lock.track if follower else None
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await rig.close()
        return gap, position, state, rig.said

    gap, position, track, said = run(go(), 120)
    assert 0.7 <= gap <= 1.8
    assert position < 0.15
    assert track == 1
    assert not any("stuck" in text for _, text in said)


def test_go_to_finds_the_way_round_a_wall_and_back_to_the_start():
    world = corridor([wall(3.0, 0.0, 3.0, 2.6)], start=(1.0, 1.0, 0.0))

    async def go():
        rig = Rig(world, eyes=True)
        await rig.run(2.0)
        rig.visit()
        trip = asyncio.ensure_future(rig.nav.go_to(rig.kit, 5.0, 1.0, 0.3))
        await rig.until(trip, 150.0)
        there = trip.result()
        x, y = world.pose.x / 1000.0, world.pose.y / 1000.0
        back = asyncio.ensure_future(rig.nav.go_back(rig.kit, "start"))
        await rig.until(back, 200.0)
        home = back.result()
        hx, hy = world.pose.x / 1000.0, world.pose.y / 1000.0
        await rig.close()
        return there, (x, y), home, (hx, hy)

    there, (x, y), home, (hx, hy) = run(go(), 180)
    assert there.ok and there.how == "arrived", there
    assert math.hypot(x - 5.0, y - 1.0) < 0.6
    assert home.ok, home
    assert math.hypot(hx - 1.0, hy - 1.0) < 0.7


def test_glass_is_bumped_once_marked_and_driven_round():
    world = corridor([wall(3.0, 0.0, 3.0, 2.6, "glass")], start=(1.0, 1.0, 0.0))

    async def go():
        rig = Rig(world)
        await rig.run(2.0)
        rig.visit()
        trip = asyncio.ensure_future(rig.nav.go_to(rig.kit, 5.0, 1.0, 0.3))
        await rig.until(trip, 200.0)
        result = trip.result()
        glass = rig.nav.stats.glass
        notes = rig.nav.take_notes()
        await rig.close()
        return result, glass, notes, world.bumps

    result, glass, notes, bumps = run(go(), 240)
    assert glass >= 1 and any("glass" in n for n in notes)
    assert bumps <= 5
    assert result.ok or result.how == "stuck", result


def test_stairs_stop_pebble_and_it_says_so():
    lead = Walker("ina", *m(2.4, 1.0), speed_mm_s=250.0, height_mm=1650.0, track=1)
    lead.go([m(2.4, 1.0), m(5.0, 1.0), m(7.0, 1.0)], 250.0)
    world = corridor(cliffs=[m(4.5, 0.0, 5.5, 4.0)], people=[lead])

    async def go():
        rig = Rig(world)
        await rig.run(2.0)
        rig.visit()
        task = asyncio.ensure_future(rig.nav.follow(rig.kit, Lead("ina", "Ina", 1), FollowControl(1.0)))
        await rig.until(task, 45.0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await rig.close()
        return world.fallen, world.pose.x / 1000.0, rig.said

    fallen, x, said = run(go(), 120)
    assert not fallen and x < 4.6
    assert any("stairs" in text for _, text in said)


def test_carried_then_put_down_keeps_a_rough_pose():
    world = corridor(start=(1.0, 1.0, 0.0))

    async def go():
        rig = Rig(world)
        await rig.run(2.0)
        rig.visit()
        rig.nav.felt("lifted")
        world.lift([m(2.0, 1.0), m(3.5, 1.0)], 800.0)
        await rig.run(1.0)
        carried = rig.nav.pose.carried
        await rig.run(6.0)
        await rig.run(2.0)
        pose = rig.nav.pose
        result = (carried, pose.carried, pose.steps, pose.x, pose.drift_m())
        await rig.close()
        return result

    carried, still, steps, x, drift = run(go(), 60)
    assert carried and not still
    assert steps >= 2 and x > 1.5 and drift > 0.3


def test_threshold_is_crossed_slowly_and_without_getting_caught():
    world = corridor(strips=[Strip(*m(3.0, 0.0, 3.0, 4.0), 15.0)], start=(1.0, 1.0, 0.0))

    async def go():
        rig = Rig(world)
        await rig.run(2.0)
        rig.visit()
        rig.nav.chart.grid.ray(1.0, 1.0, 5.0, 1.0, False, 0, 40)
        trip = asyncio.ensure_future(rig.nav.go_to(rig.kit, 5.0, 1.0, 0.3))
        await rig.until(trip, 120.0)
        result = trip.result()
        await rig.close()
        return result, world.catches

    result, catches = run(go(), 120)
    assert result.ok, result
    assert catches <= 1


def test_spots_and_the_map_page_are_served(tmp_path):
    from pebble.web.hub import Hub
    from pebble.web.server import FaceServer

    world = corridor()

    async def go():
        rig = Rig(world)
        await rig.run(1.0)
        rig.visit()
        assert rig.nav.remember_spot("car")
        spot = rig.nav.spot("car")
        server = FaceServer(Hub(), "127.0.0.1", 0, routes=rig.nav.routes())
        server.start()
        try:
            page = await asyncio.to_thread(lambda: urllib.request.urlopen(f"http://127.0.0.1:{server.port}/map", timeout=5).read().decode())
            data = await asyncio.to_thread(lambda: json.loads(urllib.request.urlopen(f"http://127.0.0.1:{server.port}/map.json", timeout=5).read()))
        finally:
            server.stop()
            await rig.close()
        return spot, page, data, rig.nav.spots()

    spot, page, data, spots = run(go(), 60)
    assert spot is not None and "car" in spots
    assert "<svg" in page and "Pebble's map" in page
    assert data["frame"] and "map" in data


def test_a_lead_who_turns_a_corner_out_of_sight_is_followed_round_it_and_found_again():
    lead = Walker("ina", *m(2.4, 1.0), speed_mm_s=300.0, height_mm=1650.0, track=1)
    lead.go([m(2.4, 1.0), m(5.0, 1.0), m(5.0, 3.3), m(8.5, 3.3)], 300.0)
    world = corridor([wall(5.6, 0.0, 5.6, 2.7)], people=[lead])

    async def go():
        rig = Rig(world)
        await rig.run(2.0)
        rig.visit()
        task = asyncio.ensure_future(rig.nav.follow(rig.kit, Lead("ina", "Ina", 1), FollowControl(1.0)))
        await rig.until(task, 60.0)
        follower = rig.nav.following
        result = (task.done(), world.pose.x / 1000.0, world.pose.y / 1000.0, follower.lost_episodes if follower else 0, follower.lock.lost_for(rig.clock.monotonic()) if follower else None, list(rig.said))
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await rig.close()
        return result

    done, x, y, lost, unseen_s, said = run(go(), 120)
    assert not done
    assert lost >= 1
    assert x > 5.6 and y > 2.7
    assert unseen_s is not None and unseen_s < 1.0
    assert not said


def test_a_detour_the_lead_walked_is_cut_short_through_space_already_seen_clear():
    lead = Walker("ina", *m(2.4, 1.0), speed_mm_s=250.0, height_mm=1650.0, track=1)
    lead.go([m(2.4, 1.0), m(3.6, 3.2), m(4.8, 1.0), m(7.5, 1.0)], 250.0)
    world = corridor(people=[lead])

    async def go():
        rig = Rig(world)
        await rig.run(2.0)
        rig.visit()
        start = rig.nav.pose.total_m
        task = asyncio.ensure_future(rig.nav.follow(rig.kit, Lead("ina", "Ina", 1), FollowControl(1.0)))
        top = 0.0
        for _ in range(100):
            await rig.run(0.5)
            top = max(top, world.pose.y / 1000.0)
        result = (rig.nav.stats.shortcuts, top, rig.nav.pose.total_m - start, world.pose.x / 1000.0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await rig.close()
        return result

    shortcuts, top, travelled, x = run(go(), 120)
    assert shortcuts >= 1
    assert top < 2.6
    assert x > 5.5 and travelled < 6.5


def test_being_carried_keeps_the_map_untouched_and_the_way_back_still_works():
    world = corridor([wall(4.7, 0.0, 4.7, 2.2)], start=(1.0, 1.0, 0.0))

    async def go():
        rig = Rig(world)
        await rig.run(2.0)
        rig.visit()
        leg = asyncio.ensure_future(rig.nav.go_to(rig.kit, 3.2, 1.0, 0.3))
        await rig.until(leg, 60.0)
        grid = rig.nav.chart.grid
        chart = rig.nav.chart.id
        snapshots = {}
        rig.nav.pose.listeners.append(lambda what: snapshots.setdefault(what, {key: bytes(chunk) for key, chunk in grid.chunks.items()}))
        rig.nav.felt("lifted")
        lifted = {key: bytes(chunk) for key, chunk in grid.chunks.items()}
        world.lift([m(3.7, 1.0), m(4.1, 1.0)], 1000.0)
        await rig.run(6.0)
        error, _ = rig.error()
        same_chart = rig.nav.chart.id == chart
        back = asyncio.ensure_future(rig.nav.go_back(rig.kit, "start"))
        await rig.until(back, 90.0)
        home = back.result() if back.done() else None
        hx, hy = world.pose.x / 1000.0, world.pose.y / 1000.0
        await rig.close()
        return snapshots, lifted, same_chart, error, home, (hx, hy)

    snapshots, lifted, same_chart, error, home, (hx, hy) = run(go(), 180)
    assert "put_down" in snapshots and snapshots["put_down"] == lifted
    assert same_chart
    assert error < 0.4
    assert home is not None and home.ok, home
    assert math.hypot(hx - 1.0, hy - 1.0) < 0.7


def person_at(track, x, y, now):
    return Seen(track, x, y, 0.0, 0.0, None, False, None, None, now)


def test_following_goes_past_half_power_only_while_the_person_is_over_1_2_m_ahead_and_nobody_else_is_close():
    world = corridor()

    async def go():
        rig = Rig(world)
        await rig.run(1.0)
        rig.visit()
        nav, kit = rig.nav, rig.kit
        lead = Lead("ina", "Ina", 1)
        follower = Follower(nav, kit, lead, FollowControl(0.8))
        nav.following = follower
        x, y, _ = nav.pose.pose_rad()

        def cap(ahead=None, other=None, track=1, seen_ago=0.0, unsure=False, state="follow", sighted=None):
            now = nav.pace.now()
            follower.lock = LeadLock("Ina", 1)
            follower.state = state
            follower.seen_gap = ahead if ahead is not None else 0.0
            people = []
            if ahead is not None:
                ina = person_at(track, x + ahead, y, now - seen_ago)
                follower.lock.start([ina], now - seen_ago, track)
                follower.lock.unsure = unsure
                if not seen_ago:
                    people.append(ina)
            if other is not None:
                people.append(person_at(9, x + other[0], y + other[1], now))
            if sighted is not None:
                people.append(person_at(track, x + sighted, y, now))
            nav.people, nav.people_at = people, now
            return nav.speed_cap(kit, lead, True), nav.speed_cap(kit, lead, False)

        caps = {
            "close": cap(1.0),
            "just inside": cap(1.19),
            "just outside": cap(1.21),
            "far": cap(2.5),
            "far, other close": cap(2.5, (0.3, 1.0)),
            "far, other just inside": cap(2.5, (0.0, 1.19)),
            "far, other at 1.5 m": cap(2.5, (0.0, 1.5)),
            "far, other at 2.5 m": cap(2.5, (0.0, 2.5)),
            "far on a new track": cap(2.5, track=5),
            "not seen yet": cap(),
            "unsure who": cap(2.5, unsure=True),
            "just lost while close": cap(1.4, seen_ago=1.0, state="chase"),
            "lost a while ago while close": cap(1.4, seen_ago=3.5, state="chase"),
            "lost a while ago, seen again close but not picked out": cap(1.4, seen_ago=3.5, state="chase", sighted=1.1),
            "lost while far, on their trail": cap(2.5, seen_ago=1.0, state="chase"),
            "lost while far, seen again close but not picked out": cap(2.5, seen_ago=1.0, state="chase", sighted=1.1),
            "lost while far, looking round": cap(2.5, seen_ago=1.0, state="look"),
            "lost while far, waiting": cap(2.5, seen_ago=1.0, state="wait"),
        }
        half = nav.driver.wheel_cap(True, True, False)
        driver = nav.driver
        nav.following = None
        await rig.close()
        return caps, half, driver

    caps, half, driver = run(go(), 60)
    assert half == pytest.approx(driver.speed_of(0.5 * driver.cruise_power))
    for case in ("close", "just inside", "far, other close", "far, other just inside", "far, other at 1.5 m", "not seen yet", "unsure who", "just lost while close", "lost a while ago, seen again close but not picked out", "lost while far, seen again close but not picked out", "lost while far, looking round", "lost while far, waiting"):
        assert caps[case] == (pytest.approx(half), pytest.approx(half)), case
    for case in ("just outside", "far", "far, other at 2.5 m", "far on a new track", "lost a while ago while close", "lost while far, on their trail"):
        sprint, cruise = caps[case]
        assert sprint == pytest.approx(driver.sprint) and cruise == pytest.approx(driver.cruise) and cruise > half, case


def test_following_keeps_its_gap_and_is_at_half_power_inside_1_2_m_of_the_person():
    lead = Walker("ina", *m(2.1, 1.0), speed_mm_s=100.0, height_mm=1650.0, track=1)
    lead.go([m(2.1, 1.0), m(9.0, 1.0)], 100.0)
    world = corridor(people=[lead])

    async def go():
        rig = Rig(world)
        await rig.run(2.0)
        rig.visit()
        half = rig.nav.driver.wheel_cap(True, True, False)
        task = asyncio.ensure_future(rig.nav.follow(rig.kit, Lead("ina", "Ina", 1), FollowControl(0.5)))
        closest = math.inf
        inside, outside = 0.0, 0.0
        for tick in range(600):
            if tick == 200:
                lead.speed_mm_s = 500.0
            await rig.run(0.1)
            gap = math.hypot(lead.x - world.pose.x, lead.y - world.pose.y) / 1000.0
            closest = min(closest, gap)
            speed = abs(rig.nav.driver.v)
            if gap <= 1.1:
                inside = max(inside, speed)
            elif gap >= 1.6:
                outside = max(outside, speed)
        gap = math.hypot(lead.x - world.pose.x, lead.y - world.pose.y) / 1000.0
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await rig.close()
        return half, inside, outside, closest, gap, world.bumps, rig.said

    half, inside, outside, closest, gap, bumps, said = run(go(), 120)
    assert 0.0 < inside <= half + 1e-6
    assert outside > half * 1.5
    assert 0.6 <= gap <= 1.1
    assert closest >= 0.45
    assert bumps == 0
    assert not any("stuck" in text for _, text in said)


def test_an_animal_at_the_edge_of_a_wide_camera_is_cautioned_and_one_out_of_view_as_before():
    world = corridor()

    def cat(bearing):
        return SeenThing("cat", bearing, 0.0, 0.2, 0.25, 0.9, 0.0, animal=True, track=4)

    async def go():
        rig = Rig(world)
        await rig.run(1.0)
        rig.visit()
        nav = rig.nav
        x, y, th = nav.pose.pose_rad()
        out = {}
        for name, fov, bearing in (("38 on 80", 80.0, 38.0), ("-38 on 80", 80.0, -38.0), ("38 on 70", 70.0, 38.0), ("45 on 80", 80.0, 45.0)):
            nav.animals = []
            nav.sight, nav.sight_at = Sight(nav.pace.now(), "front", fov, (), (), (cat(bearing),)), nav.pace.now()
            out[name] = nav.animal_guard()
        nav.sight = None
        for name, angle in (("kept at 60", 60.0), ("kept at 75", 75.0)):
            a = th + math.radians(angle)
            nav.animals = [(x + 1.0 * math.cos(a), y + 1.0 * math.sin(a), nav.pace.now(), "cat")]
            out[name] = nav.animal_guard()
        nav.animals = []
        await rig.close()
        return out

    out = run(go(), 60)
    assert out["38 on 80"][0] == "cat" and out["-38 on 80"][0] == "cat"
    assert out["38 on 70"] == (None, None)
    assert out["45 on 80"] == (None, None)
    assert out["kept at 60"][0] == "cat"
    assert out["kept at 75"] == (None, None)
