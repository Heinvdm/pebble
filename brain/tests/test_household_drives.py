import asyncio
import math

from conftest import run
from pebble.activities.chirp import FindChirp
from pebble.activities.climate import ClimateLog, ClimatePlanner, ClimateRound, answer
from pebble.activities.gate import PEBBLE, Asker, Situation
from pebble.activities.quake import QuakeRound
from pebble.alive.games import HideSeek, RedLight, Statues
from pebble.nav.sim.building import Building, Walker, m, wall
from pebble.nav.sim.rig import Rig
from pebble.people.trust import CHILD, TRUSTED
from pebble.sim.chirps import SimAlarm, SimChirps
from pebble.sim.world import AirZone, Pose, Table
from pebble.understand.request import Request

SAM = Asker("sam", "Sam", CHILD)
INA = Asker("ina", "Ina", TRUSTED, owner=True)
ROOMS = {"lounge": (2.5, 1.5, 1.4), "hallway": (7.5, 1.5, 1.2), "bedroom": (2.5, 4.6, 1.3), "kitchen": (7.5, 4.6, 1.3)}


def house(people=(), start=(1.0, 1.0, 0.0)):
    table = Table(0.0, 10000.0, 0.0, 6000.0, 0.0, frozenset({"x_min", "x_max", "y_min", "y_max"}))
    segments = [wall(0, 3, 1.5, 3), wall(2.5, 3, 6.5, 3), wall(7.5, 3, 10, 3), wall(5, 3, 5, 6)]
    return Building(table, segments, [], [], [], Pose(*m(start[0], start[1]), start[2]), list(people), [])


def at_home(rig, rooms=ROOMS):
    kit = rig.kit
    kit.rooms = lambda: sorted(rooms)
    kit.place_at = lambda name: rooms.get(name)
    kit.battery_pct = lambda: 90.0
    return kit


class Speeds:
    def __init__(self, world):
        self.world = world
        self.fastest = 0.0
        self.near = 0.0
        self.moved = 0.0

    async def watch(self, pace, every=0.5):
        last = (self.world.pose.x, self.world.pose.y)
        while True:
            await pace.sleep(every)
            now = (self.world.pose.x, self.world.pose.y)
            speed = math.hypot(now[0] - last[0], now[1] - last[1]) / 1000.0 / every
            self.moved += speed * every
            self.fastest = max(self.fastest, speed)
            if any(p.home and math.hypot(p.x - now[0], p.y - now[1]) < 2000.0 for p in self.world.people):
                self.near = max(self.near, speed)
            last = now


async def started(world, **kwargs):
    rig = Rig(world, **kwargs)
    await rig.run(4.0)
    x, y, heading = world.pose.x / 1000.0, world.pose.y / 1000.0, world.pose.heading
    rig.nav._use(rig.nav.charts.home())
    rig.nav.pose.reset(x, y, heading)
    rig.odometer.reset(x, y, heading)
    return rig


def test_the_climate_round_measures_each_room_and_the_log_answers():
    world = house()
    world.climate = [AirZone(*m(2.5, 4.6), 1800.0, 18.0, 62.0), AirZone(*m(7.5, 4.6), 1800.0, 23.0, 47.0), AirZone(*m(2.5, 1.5), 1600.0, 21.0, 50.0)]
    rooms = {name: ROOMS[name] for name in ("lounge", "bedroom", "kitchen")}

    async def go():
        rig = await started(world)
        rig.firmware.set_air({"temperature_c": 21.0, "humidity_pct": 50.0})
        kit = at_home(rig, rooms)
        log = ClimateLog(None, rig.clock)
        kit.climate = log
        task = asyncio.ensure_future(ClimateRound(Request("climate_round"), INA).run(kit))
        await rig.until(task, 2400.0, tick_s=5.0)
        await rig.close()
        return task.result(), log

    ending, log = run(go(), 900)
    assert ending.how == "done", ending
    assert set(log.rooms) == {"lounge", "bedroom", "kitchen"}
    bedroom, kitchen = log.latest("bedroom"), log.latest("kitchen")
    assert bedroom.settled and abs(bedroom.celsius - 18.0) < 0.5 and abs(bedroom.humidity_pct - 62.0) < 2.0
    assert kitchen.settled and abs(kitchen.celsius - 23.0) < 0.5
    assert abs(bedroom.dew_c - 10.6) < 0.8
    said = answer(log, "bedroom", "temperature", sorted(rooms))
    assert said.startswith("The bedroom was 18 degrees near the floor when I measured it")


def test_an_own_round_gives_way_when_someone_starts_talking():
    world = house()
    talking = [False]

    async def go():
        rig = await started(world)
        kit = at_home(rig, {"bedroom": ROOMS["bedroom"]})
        kit.climate = ClimateLog(None, rig.clock)
        kit.talking = lambda: talking[0]
        task = asyncio.ensure_future(ClimateRound(Request("climate_round"), PEBBLE).run(kit))
        await rig.until(task, 120.0, tick_s=1.0, check=lambda: math.hypot(world.pose.x - 2500.0, world.pose.y - 4600.0) < 1200.0)
        talking[0] = True
        await rig.until(task, 30.0, tick_s=1.0)
        await rig.close()
        return task.result()

    ending = run(go(), 300)
    assert ending.how == "stopped" and "started talking" in ending.text


class Busy:
    def __init__(self, sit):
        self.runner = type("R", (), {"current": None})()
        self.tasks = set()
        self.sit = sit

    def situation(self, **kwargs):
        return self.sit


def test_the_planner_waits_for_a_good_time():
    class Kit:
        body = type("B", (), {"telemetry": type("T", (), {"air": object()})()})()
        talking = staticmethod(lambda: False)
        battery_pct = staticmethod(lambda: 90.0)
        rooms = staticmethod(lambda: ["bedroom"])
        place_at = staticmethod(lambda name: (1.0, 1.0, 1.0))
        odometer = type("O", (), {"usable": True, "pose": staticmethod(lambda: (0.0, 0.0, 0.0))})()

    log = ClimateLog(None, None)
    assert ClimatePlanner(Busy(Situation()), Kit(), log).why_not() is None
    assert ClimatePlanner(Busy(Situation(quiet=True)), Kit(), log).why_not() == "this is not a good time"
    assert ClimatePlanner(Busy(Situation()), Kit(), log, hushed=lambda: True).why_not() == "someone nearby is busy"
    low = Kit()
    low.battery_pct = lambda: 45.0
    assert ClimatePlanner(Busy(Situation()), low, log).why_not() == "your battery is not charged enough"
    chatty = Kit()
    chatty.talking = lambda: True
    assert ClimatePlanner(Busy(Situation()), chatty, log).why_not() == "someone is talking to you"
    lost = Kit()
    lost.odometer = type("O", (), {"usable": False})()
    assert ClimatePlanner(Busy(Situation()), lost, log).why_not() == "you have lost track of where you are"


def test_the_chirp_finder_goes_room_to_room_and_names_the_loudest():
    world = house()
    alarms = [SimAlarm("hall", *m(8.8, 1.0), period_s=30.0, level_db=-30.0, phase_s=3.0), SimAlarm("bed", *m(1.0, 5.4), chirping=False)]

    async def go():
        rig = await started(world)
        kit = at_home(rig)
        chirps = SimChirps(world, rig.clock.now, alarms)
        pump = asyncio.ensure_future(chirps.run(rig.pace))
        kit.chirps = chirps.chirps
        await rig.run(65.0)
        task = asyncio.ensure_future(FindChirp(Request("find_chirp"), INA).run(kit))
        await rig.until(task, 2000.0, tick_s=5.0)
        pump.cancel()
        await asyncio.gather(pump, return_exceptions=True)
        await rig.close()
        return task.result(), (world.pose.x / 1000.0, world.pose.y / 1000.0)

    ending, (x, y) = run(go(), 900)
    assert ending.how == "done", ending
    assert ending.say.startswith("I think it's the one in the hallway. It was loudest there."), ending.say
    assert "battery is low" in ending.say
    assert math.hypot(x - 7.5, y - 1.5) < 1.5


def test_the_chirp_finder_says_so_when_there_is_nothing_to_hear():
    world = house()

    async def go():
        rig = await started(world)
        kit = at_home(rig)
        kit.chirps = SimChirps(world, rig.clock.now, []).chirps
        task = asyncio.ensure_future(FindChirp(Request("find_chirp"), INA).run(kit))
        await rig.until(task, 200.0, tick_s=2.0)
        await rig.close()
        return task.result(), list(rig.said)

    ending, said = run(go(), 300)
    assert ending.say == "I listened for a minute and didn't hear any chirping. Tell me when you hear it again."
    assert any("listen here for a minute" in text for _, text in said)


def test_hide_and_seek_counts_then_finds_everyone_slowly():
    sam = Walker("sam", *m(2.0, 5.2), speed_mm_s=0.0, height_mm=1150.0, track=1, posture="crouching")
    mia = Walker("mia", *m(8.4, 5.1), speed_mm_s=0.0, height_mm=1250.0, track=2)
    world = house([sam, mia])

    async def go():
        rig = await started(world)
        kit = at_home(rig)
        kit.here = lambda within: [("sam", "Sam"), ("mia", "Mia")]
        kit.name_of = lambda track: {1: "Sam", 2: "Mia"}.get(track)
        speeds = Speeds(world)
        watching = asyncio.ensure_future(speeds.watch(rig.pace))
        task = asyncio.ensure_future(HideSeek(Request("hide_seek"), SAM).run(kit))
        await rig.until(task, 1500.0, tick_s=5.0)
        watching.cancel()
        await asyncio.gather(watching, return_exceptions=True)
        await rig.close()
        return task.result(), [text for _, text in rig.said], speeds

    ending, said, speeds = run(go(), 900)
    assert ending.say == "I found everyone! That was fun.", (ending, said)
    assert said[:4] == ["One, two, three, four, five.", "Six, seven, eight, nine, ten.", "Eleven, twelve, thirteen, fourteen, fifteen.", "Sixteen, seventeen, eighteen, nineteen, twenty!"]
    assert "Found you, Sam!" in said and "Found you, Mia!" in said
    assert speeds.fastest <= 0.07 and speeds.near <= 0.07


def test_hide_and_seek_is_not_played_in_the_dark():
    async def go():
        rig = await started(house())
        kit = at_home(rig)
        kit.dark = lambda: True
        ending = await HideSeek(Request("hide_seek"), SAM).run(kit)
        await rig.close()
        return ending

    ending = run(go(), 60)
    assert ending.say == "It's too dark for me to play hide and seek. Maybe with the lights on?"


def test_the_quake_round_asks_each_person_and_reports_who_it_could_not_find():
    sam = Walker("sam", *m(2.2, 5.0), speed_mm_s=0.0, height_mm=1700.0, track=1)
    mia = Walker("mia", *m(8.0, 5.1), speed_mm_s=0.0, height_mm=1650.0, track=2)
    world = house([sam, mia])
    reports = []

    async def go():
        rig = await started(world)
        kit = at_home(rig)
        kit.here = lambda within: [("sam", "Sam"), ("mia", "Mia"), ("jo", "Jo")]
        kit.usual_room = lambda pid: {"sam": "bedroom", "mia": "kitchen", "jo": "lounge"}.get(pid)
        kit.name_of = lambda track: {1: "Sam", 2: "Mia"}.get(track)
        speeds = Speeds(world)
        watching = asyncio.ensure_future(speeds.watch(rig.pace))
        activity = QuakeRound(Request("quake_round"), PEBBLE, why="test", report=reports.append)
        task = asyncio.ensure_future(activity.run(kit))
        await rig.until(task, 1500.0, tick_s=5.0)
        activity.done("found", "")
        watching.cancel()
        await asyncio.gather(watching, return_exceptions=True)
        await rig.close()
        return task.result(), [text for _, text in rig.said], speeds

    ending, said, speeds = run(go(), 900)
    assert ending.how == "done", ending
    report = reports[0]
    assert [label for _, label in report["found"]] == ["Mia", "Sam"]
    assert [label for _, label in report["missing"]] == ["Jo"]
    assert "Sam, are you okay?" in said and "Mia, are you okay?" in said and "Jo, are you okay?" in said
    assert speeds.fastest <= 0.08


def players(rig, world, cheat_s):
    said_at = {}

    async def referee():
        seen = 0
        while True:
            await rig.pace.sleep(0.1)
            for _, text in rig.said[seen:]:
                said_at[text] = rig.clock.monotonic()
                if text == "Red light!":
                    for walker in world.people:
                        walker.waiting_until = -math.inf
                    asyncio.ensure_future(freeze(world.people[0], 0.4))
                    asyncio.ensure_future(freeze(world.people[1], cheat_s))
                elif text == "Green light!":
                    for walker in world.people:
                        walker.hold = False
                elif "I saw you move" in text and "Mia" in text:
                    mia = world.people[1]
                    mia.x, mia.y, mia.leg = 3800.0, 1500.0, 0
                    mia.route = [mia.plan[0]]
            seen = len(rig.said)

    async def freeze(walker, after):
        await rig.pace.sleep(after)
        walker.hold = True

    return referee


def test_red_light_catches_who_moved_names_them_and_never_drives():
    sam = Walker("sam", *m(4.4, 0.7), speed_mm_s=250.0, height_mm=1250.0, track=1, polite=False, hold=True)
    mia = Walker("mia", *m(4.4, 1.3), speed_mm_s=250.0, height_mm=1300.0, track=2, polite=False, hold=True)
    sam.go([m(4.4, 0.7), m(1.5, 0.9)], 250.0)
    mia.go([m(3.8, 1.5), m(1.5, 1.1)], 250.0)
    world = house([sam, mia])

    async def go():
        rig = await started(world)
        kit = rig.kit
        kit.name_of = lambda track: {1: "Sam", 2: "Mia"}.get(track)
        referee = asyncio.ensure_future(players(rig, world, cheat_s=2.6)())
        start = (world.pose.x, world.pose.y, world.pose.heading)
        drives = []
        real = kit.body.drive

        async def drive(left, right):
            drives.append((left, right))
            return await real(left, right)

        kit.body.drive = drive
        task = asyncio.ensure_future(RedLight(Request("red_light"), SAM).run(kit))
        await rig.until(task, 600.0, tick_s=1.0)
        referee.cancel()
        await asyncio.gather(referee, return_exceptions=True)
        moved = math.hypot(world.pose.x - start[0], world.pose.y - start[1])
        await rig.close()
        return task.result(), [text for _, text in rig.said], drives, moved, kit.face

    ending, said, drives, moved, face = run(go(), 600)
    assert "Mia, I saw you move! Back to the start." in said, said
    assert not any("Sam, I saw you move" in text for text in said)
    assert ending.say == "You made it, Sam! You win!", (ending, said)
    assert not drives and moved < 1.0
    assert any("eyes 16 12 closed white" in line for scene in face.scenes for line in scene["lines"])


def test_musical_statues_puts_out_whoever_moves_and_never_drives():
    sam = Walker("sam", *m(3.2, 0.6), speed_mm_s=200.0, height_mm=1250.0, track=1, polite=False)
    mia = Walker("mia", *m(3.2, 1.5), speed_mm_s=200.0, height_mm=1300.0, track=2, polite=False)
    sam.go([m(3.2, 0.6), m(3.6, 0.6)], 200.0, loop=True)
    mia.go([m(3.2, 1.5), m(3.6, 1.5)], 200.0, loop=True)
    world = house([sam, mia])

    async def go():
        rig = await started(world)
        kit = rig.kit
        kit.name_of = lambda track: {1: "Sam", 2: "Mia"}.get(track)
        state = {"freeze_at": None}

        async def referee():
            seen = 0
            while True:
                await rig.pace.sleep(0.1)
                for _, text in rig.said[seen:]:
                    if text == "Freeze!":
                        state["freeze_at"] = rig.clock.monotonic()
                    elif text != "Freeze!" and state["freeze_at"] is not None and "!" in text and "statue" not in text:
                        sam.hold = mia.hold = False
                        state["freeze_at"] = None
                seen = len(rig.said)
                if state["freeze_at"] is not None:
                    gone = rig.clock.monotonic() - state["freeze_at"]
                    if gone >= 0.4:
                        sam.hold = True
                    if gone >= 3.0:
                        mia.hold = True

        ref = asyncio.ensure_future(referee())
        drives = []
        real = kit.body.drive

        async def drive(left, right):
            drives.append((left, right))
            return await real(left, right)

        kit.body.drive = drive
        task = asyncio.ensure_future(Statues(Request("statues"), SAM).run(kit))
        await rig.until(task, 400.0, tick_s=1.0)
        ref.cancel()
        await asyncio.gather(ref, return_exceptions=True)
        await rig.close()
        return task.result(), [text for _, text in rig.said], drives

    ending, said, drives = run(go(), 600)
    assert "Mia, you moved! You're out." in said, said
    assert ending.say == "Sam wins! Well done, statue!", (ending, said)
    assert not drives
