import math

from ..things.words import spoken
from .base import Activity, Ending
from .kinds import level_head, moved
from .kit import Kit
from .motion import Wheels, leave_dock, roll_by, turn_by, wrap_deg
from .seeing import ThingTracker, Tracker, animal_gap, animals_ahead, body_bearing, life_ahead, life_gap, look, person_gap_m, scan, thing_gap_m

ROUNDS = 8
ARRIVED_M = 0.9
BEHIND_M = 0.35
SIDE_M = 0.45
CLOSE_M = 0.08
NUDGE_MM = 450.0
NUDGE_POWER = 0.45
DRIVE_POWER = 0.4
BACK_MM = 320.0
LOOKS = 3
CENTRE_M = 0.12
PERSON_NEAR_M = 0.7
LINE_UP_DEG = 12.0
IN_THE_WAY_DEG = 35.0


def _front_mm(kit: Kit) -> int | None:
    status = kit.body.telemetry.status
    return status.front_mm if status else None


def _point(kit: Kit, bearing_deg: float, camera: str, gap_m: float) -> tuple[float, float]:
    x, y, heading = kit.odometer.pose()
    angle = math.radians(heading + body_bearing(bearing_deg, camera))
    return x + gap_m * math.cos(angle), y + gap_m * math.sin(angle)


class Push(Activity):
    kind = "play"
    sight = True

    def __init__(self, request, asker, target=None, battery=False):
        super().__init__(request, asker, target, battery)
        self.nudges = 0
        self.thing = request.thing

    def describe(self) -> str:
        return f"pushing the {spoken(self.thing)} to {self.whom('you')}"

    async def _person(self, kit: Kit, wheels: Wheels) -> tuple[float, float] | None:
        tracker = Tracker()
        wanted = self.target.label.lower() if self.target is not None else ""
        for _ in range(2):
            sight = kit.eyes.latest(1.0)
            people = list(sight.people) if sight is not None else []
            chosen = None
            for person in people:
                named = kit.name_of(person.track)
                if named and wanted and named.lower() == wanted:
                    chosen = person
            if chosen is None and len(people) == 1:
                chosen = people[0]
            if chosen is not None:
                gap = person_gap_m(chosen, sight, _front_mm(kit)) + CENTRE_M
                return _point(kit, chosen.bearing_deg, sight.camera, gap)
            if wheels.why_not() is not None:
                break
            found, sight, _ = await scan(kit, wheels, tracker)
            if found is None:
                break
        if self.target is not None and self.target.id is not None:
            spot = kit.where_was(self.target.id)
            if spot is not None:
                return spot[0], spot[1]
        return None

    async def _ball(self, kit: Kit, wheels: Wheels, aim: tuple[float, float] | None = None) -> tuple[float, float] | None:
        tracker = ThingTracker(self.thing)
        if aim is not None:
            x, y, heading = kit.odometer.pose()
            await turn_by(kit, wheels, wrap_deg(math.degrees(math.atan2(aim[1] - y, aim[0] - x)) - heading))
        seen, sight = None, None
        for _ in range(LOOKS):
            await kit.pace.sleep(0.4)
            seen, sight = look(kit, tracker)
            if seen is not None:
                break
        if seen is None and wheels.why_not() is None:
            seen, sight, _ = await scan(kit, wheels, tracker)
        if seen is None:
            return None
        gap = thing_gap_m(seen, sight, kit.body.telemetry.tilt, _front_mm(kit)) + CENTRE_M
        return _point(kit, seen.bearing_deg, sight.camera, gap)

    def _life_in_way(self, kit: Kit, within: float) -> str:
        sight = kit.eyes.latest(1.0)
        tilt = kit.body.telemetry.tilt
        for thing, gap in animals_ahead(sight, tilt):
            if gap < max(within, animal_gap(thing.label) + 0.2):
                return spoken(thing.label)
        for thing, gap in life_ahead(sight, tilt, self.thing):
            if gap < max(within, (life_gap(thing.label) or 0.3) + 0.1):
                return spoken(thing.label)
        return ""

    async def _go(self, kit: Kit, wheels: Wheels, x: float, y: float) -> str | None:
        px, py, heading = kit.odometer.pose()
        gap = math.hypot(x - px, y - py)
        if gap <= CLOSE_M:
            return None
        _, problem = await turn_by(kit, wheels, wrap_deg(math.degrees(math.atan2(y - py, x - px)) - heading))
        if problem and problem != "the turn took too long":
            return problem
        alive = self._life_in_way(kit, gap + 0.2)
        if alive:
            return f"the {alive} is in the way"
        _, problem = await roll_by(kit, wheels, gap * 1000.0, DRIVE_POWER)
        moved(kit)
        return problem if problem in ("edge", "stall", "fault") or (problem and wheels.why_not()) else None

    async def _behind(self, kit: Kit, wheels: Wheels, ball: tuple[float, float], person: tuple[float, float]) -> str | None:
        gap = math.hypot(ball[0] - person[0], ball[1] - person[1]) or 1.0
        ux, uy = (ball[0] - person[0]) / gap, (ball[1] - person[1]) / gap
        target = (ball[0] + ux * BEHIND_M, ball[1] + uy * BEHIND_M)
        px, py, _ = kit.odometer.pose()
        to_target = math.degrees(math.atan2(target[1] - py, target[0] - px))
        to_ball = math.degrees(math.atan2(ball[1] - py, ball[0] - px))
        if math.hypot(ball[0] - px, ball[1] - py) < math.hypot(target[0] - px, target[1] - py) and abs(wrap_deg(to_target - to_ball)) < IN_THE_WAY_DEG:
            side = 1.0 if wrap_deg(to_target - to_ball) >= 0 else -1.0
            problem = await self._go(kit, wheels, ball[0] - uy * SIDE_M * side + ux * 0.1, ball[1] + ux * SIDE_M * side + uy * 0.1)
            if problem:
                return problem
        return await self._go(kit, wheels, *target)

    async def run(self, kit: Kit) -> Ending:
        name = f"the {spoken(self.thing)}"
        who = self.whom("you")
        if not kit.eyes.available:
            return Ending("no_sight", "you cannot see yet", "I can't see yet, so I can't push it.")
        if not kit.toy(self.thing):
            return Ending("failed", f"the {spoken(self.thing)} is not a toy", f"I only push toys on the floor, and {name} isn't one.")
        odometer = kit.odometer
        if odometer is None or not getattr(odometer, "usable", False):
            return Ending("failed", "you have lost track of where you are", "I've lost track of where I am.")
        await kit.eyes.use_camera("front")
        await level_head(kit)
        wheels = Wheels(kit, exempt=self.thing).open()
        try:
            if wheels.why_not() is None:
                await leave_dock(kit, wheels)
            person = await self._person(kit, wheels)
            if person is None:
                return Ending("lost", f"you could not see {who} to push {name} to", f"I can't see {who}.")
            closest = None
            ball = None
            for _ in range(ROUNDS):
                reason = wheels.why_not()
                if reason:
                    return Ending("blocked", reason, "")
                if kit.battery_low():
                    return Ending("battery", "your battery got low", "My battery's getting low, so I'll stop.")
                ball = await self._ball(kit, wheels, ball)
                if ball is None:
                    return Ending("lost", f"you lost sight of {name}", f"Where did {name} go?")
                gap = math.hypot(ball[0] - person[0], ball[1] - person[1])
                closest = gap if closest is None else min(closest, gap)
                if gap <= ARRIVED_M:
                    kit.face.show("happy")
                    return Ending("done", f"you pushed {name} to {who} in {self.nudges} nudges", f"There you go, {who}!" if who != "you" else "There you go!")
                problem = await self._behind(kit, wheels, ball, person)
                if problem:
                    return Ending("blocked", f"you could not get behind {name} ({problem})", "Something's in the way, so I stopped here.")
                ball = await self._ball(kit, wheels, ball)
                if ball is None:
                    return Ending("lost", f"you lost sight of {name}", f"Where did {name} go?")
                tracker = ThingTracker(self.thing)
                seen, sight = look(kit, tracker)
                if seen is not None:
                    angle = body_bearing(seen.bearing_deg, sight.camera)
                    if abs(angle) > LINE_UP_DEG:
                        await turn_by(kit, wheels, angle)
                if self._near_person(kit):
                    return Ending("done", f"you stopped pushing {name} because {who} was close", "There you go!")
                alive = self._life_in_way(kit, 1.0)
                if alive:
                    return Ending("blocked", f"the {alive} was in the way of the push", f"The {alive} is in the way, so I'll stop here.")
                self.nudges += 1
                kit.face.show("mischief" if self.nudges % 2 else "happy")
                await roll_by(kit, wheels, NUDGE_MM, NUDGE_POWER)
                await roll_by(kit, wheels, -BACK_MM, 0.3)
                moved(kit)
                await kit.pace.sleep(1.0)
            return Ending("done", f"you pushed {name} towards {who} in {self.nudges} nudges; it got within {closest or 0.0:.1f} m", f"I got {name} most of the way to {who}.")
        finally:
            await wheels.halt()
            wheels.close()

    def _near_person(self, kit: Kit) -> bool:
        sight = kit.eyes.latest(1.0)
        if sight is None:
            return False
        for person in sight.people:
            if abs(body_bearing(person.bearing_deg, sight.camera)) <= 30.0 and person_gap_m(person, sight, _front_mm(kit)) < PERSON_NEAR_M:
                return True
        return False
