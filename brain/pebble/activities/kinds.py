import asyncio
import math

from ..understand.request import Request
from ..nav import FollowControl, Lead
from ..people.trust import STRANGER
from .base import Activity, Ending
from .kit import Kit
from .motion import Wheels, clamp, drive_towards, leave_dock, roll_by, turn_by
from ..things.words import is_animal, spoken
from .seeing import ThingTracker, Tracker, animal_gap, animal_slow, animals_ahead, body_bearing, life_ahead, life_gap, life_slow, look, person_gap_m, scan, thing_gap_m

WAIT_STEP_S = 0.5
LOOK_HOLD_S = 20.0
LOOK_LOST_S = 6.0
TILT_GAIN = 0.6
TILT_EVERY_S = 0.4
COME_GAP_M = 0.5
COME_LOST_S = 5.0
COME_MAX_S = 120.0
SLOW_FOLLOW = 0.5
NEAR_KNOWN_M = 1.0
FOLLOW_GAP_M = 0.8
FOLLOW_GAPS = (0.5, 2.0)
THING_GAP_M = 0.3
ANIMAL_FOLLOW_GAP_M = 1.0
FIND_STEP_DEG = 40.0
CLOSE_LOOK_S = 7.0
ANIMAL_WAIT_S = 20.0
FOLLOW_LOST_S = 20.0
FOLLOW_MAX_S = 1200.0
TOPS = {"slow": 0.3, "quick": 0.5, "": 0.42}
BUMP_WINDOW_S = 30.0
BUMP_LIMIT = 3
BUMP_PAUSE_S = 1.5
BACK_OFF_M = 0.2
BACK_POWER = 0.3
MOVE_POWER = 0.4
MOVE_M = {"little": 0.1, "lot": 0.5, "": 0.25}
MOVE_MAX = {"forward": 1.0, "back": 0.2}
TURN_DEG = {"little": 30.0, "lot": 135.0, "": 90.0}


HEAD_SETTLE_S = 0.8
EYES_BACK_STEPS = 30


async def level_head(kit: Kit) -> None:
    rest = kit.body.profile.tilt_rest
    tilt = kit.body.telemetry.tilt
    if tilt is not None and abs(tilt - rest) <= 4.0:
        return
    await kit.body.tilt(rest)
    await kit.pace.sleep(HEAD_SETTLE_S)


def _minutes(seconds: float) -> str:
    if seconds < 90:
        return f"{round(seconds)} seconds"
    return f"{round(seconds / 60)} minutes"


class Wait(Activity):
    kind = "wait"
    moving = False

    def describe(self) -> str:
        return "waiting" + (f" by the {self.request.place}" if self.request.place else "")

    def adjust(self, request: Request) -> tuple[str, Request | None]:
        if request.change == "keep_going":
            return "Okay.", Request("release")
        return "I'm already staying put.", None

    async def run(self, kit: Kit) -> Ending:
        patience = kit.patience(self.asker.tier)
        if self.request.until:
            patience *= 2.0
        if self.request.seconds:
            patience = min(self.request.seconds, max(patience, 60.0) * 3.0)
        start = kit.pace.now()
        gone = False
        while True:
            await kit.pace.sleep(WAIT_STEP_S)
            now = kit.pace.now()
            if kit.battery_low():
                return Ending("battery", "your battery got low while you waited", "My battery's getting low, so I can't wait any longer.")
            if self.request.until == "back" and self.asker.id is not None:
                here = kit.present(self.asker.id)
                if not here:
                    gone = True
                elif gone:
                    return Ending("done", f"{self.asker.label} came back, so you stopped waiting", "You're back!")
            if now - start >= patience:
                if self.request.seconds and patience >= self.request.seconds:
                    return Ending("done", f"you waited {_minutes(now - start)} as asked", "")
                return Ending("patience", f"you waited {_minutes(now - start)} and ran out of patience", "I waited, but I got restless. I'm off to do my own thing.")


def moved(kit: Kit) -> None:
    told = getattr(kit.eyes, "moved", None)
    if told is not None:
        told()


def front_mm(kit: Kit) -> int | None:
    status = kit.body.telemetry.status
    return status.front_mm if status else None


def gap_to(seen, sight, kit: Kit) -> float:
    if hasattr(seen, "label"):
        return thing_gap_m(seen, sight, kit.body.telemetry.tilt, front_mm(kit))
    return person_gap_m(seen, sight, front_mm(kit))


class Look(Activity):
    kind = "look"
    moving = False
    sight = True

    def describe(self) -> str:
        if self.request.thing:
            return f"looking at the {spoken(self.request.thing)}"
        return f"looking at {self.who()}"

    def tracker(self):
        return ThingTracker(self.request.thing) if self.request.thing else Tracker()

    async def run(self, kit: Kit) -> Ending:
        if not kit.eyes.available:
            return Ending("no_sight", "you cannot see yet", "I can't see yet, so I can't find you.")
        await kit.eyes.use_camera("front")
        await level_head(kit)
        wheels = Wheels(kit).open()
        tracker = self.tracker()
        hold = self.request.seconds or LOOK_HOLD_S
        name = f"the {spoken(self.request.thing)}" if self.request.thing else ""
        try:
            person, sight = look(kit, tracker)
            if person is None and wheels.why_not() is None:
                person, sight, _ = await scan(kit, wheels, tracker)
            if person is None:
                if name:
                    return Ending("lost", f"you looked around but could not see {name}", f"I can't see {name} from here.")
                return Ending("lost", "you looked but could not see them", "I can't see you from here.")
            if wheels.why_not() is None and kit.body.telemetry.docked and abs(body_bearing(person.bearing_deg, sight.camera)) > 8.0:
                await leave_dock(kit, wheels)
            start = kit.pace.now()
            seen_at = start
            tilt_at = -math.inf
            while kit.pace.now() - start < hold:
                now = kit.pace.now()
                person, sight = look(kit, tracker)
                if person is None:
                    await wheels.halt()
                    if now - seen_at > LOOK_LOST_S:
                        if name:
                            return Ending("lost", f"{name} went out of view", f"Oh, {name} has gone.")
                        return Ending("lost", "the person you were looking at went out of view", "Oh, you've gone.")
                else:
                    seen_at = now
                    if now - tilt_at >= TILT_EVERY_S and abs(person.elevation_deg) > 3.0:
                        tilt = kit.body.telemetry.tilt
                        base = tilt if tilt is not None else kit.body.profile.tilt_rest
                        await kit.body.tilt(base + person.elevation_deg * TILT_GAIN)
                        moved(kit)
                        tilt_at = now
                    angle = body_bearing(person.bearing_deg, sight.camera)
                    if abs(angle) > 8.0 and wheels.why_not() is None:
                        turn = clamp(math.radians(angle) * 0.8, -0.35, 0.35)
                        turn = math.copysign(max(abs(turn), 0.24), turn)
                        await wheels.drive(0.0, turn)
                    else:
                        await wheels.halt()
                await kit.pace.sleep(kit.control_s)
            return Ending("done", f"you looked at {name or self.who()} for a while", "")
        finally:
            await wheels.halt()
            wheels.close()
            await kit.body.tilt(kit.body.profile.tilt_rest)


class _Approach(Activity):
    sight = True
    gap_m = COME_GAP_M
    lost_s = COME_LOST_S
    max_s = COME_MAX_S
    arrive = True

    def __init__(self, request, asker, target=None, battery=False):
        super().__init__(request, asker, target, battery)
        self.gap = clamp(request.metres, *FOLLOW_GAPS) if request.metres else self.gap_m
        if request.thing:
            floor = animal_gap(request.thing) if is_animal(request.thing) else (life_gap(request.thing) or THING_GAP_M)
            self.gap = max(floor, clamp(request.metres, *FOLLOW_GAPS) if request.metres else self.thing_gap(request.thing))
        self.top = TOPS.get(request.speed, TOPS[""])
        self.cautious = False

    def thing_gap(self, thing: str) -> float:
        return animal_gap(thing) if is_animal(thing) else (life_gap(thing) or THING_GAP_M)

    def tracker(self):
        return ThingTracker(self.request.thing) if self.request.thing else Tracker()

    def named(self) -> str:
        return f"the {spoken(self.request.thing)}" if self.request.thing else self.whom("them")

    def lost(self, kit: Kit) -> Ending:
        return Ending("lost", f"you lost sight of {self.whom('them')}", "I lost you. I'll stop here.")

    def arrived(self) -> Ending:
        return Ending("done", f"you came to {self.whom('them')}", "Here I am!")

    async def run(self, kit: Kit) -> Ending:
        if not kit.eyes.available and self.urgent:
            for _ in range(EYES_BACK_STEPS):
                await kit.pace.sleep(0.1)
                if kit.eyes.available:
                    break
        if not kit.eyes.available:
            what = "follow you" if self.kind == "follow" else "find you"
            return Ending("no_sight", "you cannot see yet", f"I can't see yet, so I can't {what}.")
        await kit.eyes.use_camera("front")
        await level_head(kit)
        wheels = Wheels(kit, exempt=self.request.thing).open()
        tracker = self.tracker()
        bumps: list[float] = []
        pause_until = -math.inf
        held_since = None
        try:
            person, sight = look(kit, tracker)
            if person is None and self.request.thing and not is_animal(self.request.thing) and wheels.why_not() is None:
                spot = kit.thing_at(self.request.thing)
                if spot is not None:
                    await leave_dock(kit, wheels)
                    trip = await drive_towards(kit, wheels, spot[0], spot[1], NEAR_KNOWN_M)
                    moved(kit)
                    kit.note(f"you drove over to where you last saw {self.named()}" + (f" but stopped ({trip})" if trip else ""))
                    person, sight = look(kit, tracker)
            if person is None:
                person, sight, problem = await scan(kit, wheels, tracker)
                if person is None:
                    if problem and problem not in ("the turn took too long",):
                        return Ending("blocked", f"you could not look around ({problem})", "I can't turn to look just now.")
                    if self.request.thing:
                        return Ending("lost", f"you looked all around and could not see {self.named()}", f"I looked all around but I can't see {self.named()}.")
                    return Ending("lost", "you looked all around and could not see them", "I looked all around but I can't see you.")
            if wheels.why_not() is None and kit.body.telemetry.docked:
                await leave_dock(kit, wheels)
            start = kit.pace.now()
            seen_at = start
            scanned = False
            goal = None
            while True:
                now = kit.pace.now()
                if now - start > self.max_s:
                    return Ending("timeout", f"you gave up after {_minutes(now - start)}", "That's taking too long. I'll stop here.")
                if kit.battery_low():
                    return Ending("battery", "your battery got low", "My battery's getting low, so I'll stop here.")
                for reflex in wheels.reflexes():
                    if reflex == "edge":
                        return Ending("reflex", "your drop sensor found an edge and your body stopped", "Whoa, there's an edge. I'll stop here.")
                    if reflex == "fault":
                        return Ending("reflex", "your body reported a sensor fault", "Something's wrong with my sensors, so I'm stopping.")
                    if reflex in ("bump", "stall"):
                        bumps.append(now)
                        pause_until = now + BUMP_PAUSE_S
                bumps = [at for at in bumps if now - at <= BUMP_WINDOW_S]
                if len(bumps) >= BUMP_LIMIT:
                    return Ending("reflex", "you kept bumping into things", "I keep bumping into things, so I'll stop here.")
                held = wheels.held()
                if held == "edge":
                    return Ending("reflex", "your body is holding at an edge", "There's an edge here, so I'll stop.")
                if held or now < pause_until:
                    await wheels.halt()
                    await kit.pace.sleep(kit.control_s)
                    continue
                person, sight = look(kit, tracker)
                if person is None:
                    if goal is not None and now - seen_at <= self.lost_s:
                        await self.drive(kit, wheels, 0.0, 0.0, self.top, goal)
                    else:
                        await wheels.halt()
                    if now - seen_at > self.lost_s:
                        if scanned:
                            return self.lost(kit)
                        scanned = True
                        goal = None
                        found, sight, _ = await scan(kit, wheels, tracker)
                        if found is None:
                            return self.lost(kit)
                        seen_at = kit.pace.now()
                        continue
                    await kit.pace.sleep(kit.control_s)
                    continue
                seen_at = now
                scanned = False
                angle = body_bearing(person.bearing_deg, sight.camera)
                gap = gap_to(person, sight, kit)
                if self.arrive and gap <= self.gap + 0.05 and abs(angle) < 20.0:
                    await wheels.halt()
                    return self.arrived()
                top = self.top
                blocked_by = None
                for animal, gap_m in animals_ahead(sight, kit.body.telemetry.tilt):
                    if gap_m < animal_slow(animal.label):
                        top = min(top, self.top * 0.5)
                    if gap_m < animal_gap(animal.label) + 0.05:
                        blocked_by = animal
                if getattr(kit, "nav", None) is None:
                    for life, gap_m in life_ahead(sight, kit.body.telemetry.tilt, self.request.thing):
                        if gap_m < life_slow(life.label):
                            top = min(top, self.top * 0.5)
                        if gap_m < (life_gap(life.label) or THING_GAP_M) + 0.05:
                            blocked_by = blocked_by or life
                if top < self.top and not self.cautious:
                    self.cautious = True
                    near = next((a for a, _ in animals_ahead(sight, kit.body.telemetry.tilt)), None) or next((a for a, _ in life_ahead(sight, kit.body.telemetry.tilt, self.request.thing)), None)
                    kit.note(f"the {spoken(near.label) if near else 'animal'} is close ahead, so you slowed right down and keep your distance")
                elif top >= self.top:
                    self.cautious = False
                if blocked_by is None:
                    held_since = None
                elif held_since is None:
                    held_since = now
                elif now - held_since > ANIMAL_WAIT_S and not (self.request.thing and is_animal(self.request.thing)):
                    await wheels.halt()
                    return Ending("blocked", f"the {spoken(blocked_by.label)} stayed in your way", f"The {spoken(blocked_by.label)} is in my way, so I'll stop here.")
                if self.arrive and blocked_by is not None and self.request.thing and hasattr(person, "label") and person.animal:
                    await wheels.halt()
                    return self.arrived()
                turn = 0.0 if abs(angle) < 3.0 else clamp(math.radians(angle) * 0.9, -0.4, 0.4)
                forward = 0.0
                if abs(angle) <= 30.0 and gap > self.gap + 0.05 and blocked_by is None:
                    forward = clamp((gap - self.gap) * 0.9 + 0.12, 0.0, top)
                if forward == 0.0 and abs(angle) > 6.0:
                    turn = math.copysign(max(abs(turn), 0.24), turn)
                goal = None
                pointing = getattr(kit.nav, "point_at", None)
                if pointing is not None and blocked_by is None and gap > self.gap + 0.05:
                    goal = pointing(angle, gap - self.gap)
                privacy = getattr(kit, "privacy", None)
                room = privacy.fence(goal) if privacy is not None and forward > 0.0 else None
                if room is not None:
                    await wheels.halt()
                    ending = await self.private_door(kit, wheels, room)
                    if ending is not None:
                        return ending
                    continue
                rules = getattr(kit, "rules", None)
                kept = rules.fence(goal) if rules is not None and forward > 0.0 and not self.urgent else None
                if kept is not None:
                    await wheels.halt()
                    return Ending("done", f"you stopped outside the {kept[0]}: {kept[1]}", "" if self.asker.own else f"I'll wait out here. {kept[1]}")
                await self.drive(kit, wheels, forward, turn, top, goal)
                await kit.pace.sleep(kit.control_s)
        finally:
            await wheels.halt()
            wheels.close()

    async def private_door(self, kit: Kit, wheels: Wheels, room: str) -> Ending | None:
        if self.urgent:
            self.door = room
            return Ending("done", f"you stopped at the door of the {room}, which is private", "")
        if self.kind == "come" and self.target is not None and self.target.id is not None and self.target.id == self.asker.id:
            from ..privacy.look import at_door

            outcome = await at_door(kit, wheels, room, self.asker)
            if outcome == "in":
                return None
            return Ending("done", f"you stopped at the door of the {room}, which is private, and stayed outside", "")
        if self.asker.own:
            return Ending("done", f"you stopped at the door of the {room}, which is private", "")
        if self.request.thing:
            return Ending("done", f"you stopped at the door of the {room}, which is private", f"That's in the {room}, and it's private, so I'll stay out here.")
        return Ending("done", f"you stopped at the door of the {room}, which is private", "I'll wait out here.")

    async def drive(self, kit: Kit, wheels: Wheels, forward: float, turn: float, top: float, goal: tuple[float, float] | None = None) -> None:
        driving = getattr(kit.nav, "drive", None)
        if driving is None:
            await wheels.drive(forward, turn, top)
            return
        lead = Lead(self.target.id, self.target.label, None) if self.target is not None and not self.request.thing else None
        await driving(kit, wheels, forward, turn, top, exempt=self.request.thing, lead=lead, goal=goal)


class Come(_Approach):
    kind = "come"

    def describe(self) -> str:
        return f"coming to {self.who()}"

    def arrived(self) -> Ending:
        if self.target is not None and self.asker.id is not None and self.target.id != self.asker.id:
            return Ending("done", f"you went to {self.target.label}", f"Hello {self.target.label}!")
        return Ending("done", f"you came to {self.whom('them')}", "Here I am!")

    def adjust(self, request: Request) -> tuple[str, Request | None]:
        if request.change == "slower":
            self.top = max(0.2, self.top - 0.1)
        elif request.change == "faster":
            self.top = min(0.5, self.top + 0.1)
        elif request.change == "closer":
            self.gap = max(FOLLOW_GAPS[0], self.gap - 0.2)
        elif request.change == "further":
            self.gap = min(FOLLOW_GAPS[1], self.gap + 0.3)
        elif request.change in ("enough", "stay"):
            return "Okay, I'll stay here.", Request("wait")
        return "", None


SEEK_GAP_M = 0.8
SEEK_MAX_S = 180.0


class SeekPeople(Come):
    kind = "seek_people"
    urgent = True
    gap_m = SEEK_GAP_M
    max_s = SEEK_MAX_S

    def __init__(self, request, asker, target=None, battery=False, why: str = "", done=None):
        super().__init__(request, asker, target, battery)
        self.gap = SEEK_GAP_M
        self.why = why
        self.done = done

    def describe(self) -> str:
        return "looking for someone" + (f" ({self.why})" if self.why else "")

    def arrived(self) -> Ending:
        return Ending("done", "you found someone", "")

    def lost(self, kit: Kit) -> Ending:
        return Ending("lost", "you lost sight of them", "")

    def adjust(self, request: Request) -> tuple[str, Request | None]:
        return "", None


class GoToThing(_Approach):
    kind = "go_to_thing"
    max_s = COME_MAX_S

    def describe(self) -> str:
        return f"going to the {spoken(self.request.thing)}"

    def lost(self, kit: Kit) -> Ending:
        return Ending("lost", f"you lost sight of {self.named()}", f"I lost sight of {self.named()}.")

    def arrived(self) -> Ending:
        name = self.named()
        if is_animal(self.request.thing):
            return Ending("done", f"you went close to {name}, but not too close", f"Hello, {spoken(self.request.thing)}. I'll stay back a little.")
        return Ending("done", f"you went to {name}", f"Here's {name}.")

    def adjust(self, request: Request) -> tuple[str, Request | None]:
        if request.change in ("enough", "stay"):
            return "Okay, I'll stop here.", Request("wait")
        if request.change == "slower":
            self.top = max(0.2, self.top - 0.1)
        elif request.change == "faster":
            self.top = min(0.5, self.top + 0.1)
        return "", None


class Find(Activity):
    kind = "find"
    sight = True

    def describe(self) -> str:
        return f"looking for the {spoken(self.request.thing)}"

    async def _close_look(self, kit: Kit, tracker: ThingTracker):
        closely = getattr(kit.eyes, "look_closely", None)
        if closely is None:
            return None, None
        try:
            sight = await asyncio.wait_for(closely(), CLOSE_LOOK_S)
        except (asyncio.TimeoutError, Exception):
            return None, None
        return tracker.pick(sight), sight

    async def run(self, kit: Kit) -> Ending:
        name = f"the {spoken(self.request.thing)}"
        if not kit.eyes.available:
            return Ending("no_sight", "you cannot see yet", f"I can't see yet, so I can't look for {name}.")
        await kit.eyes.use_camera("front")
        await level_head(kit)
        wheels = Wheels(kit, exempt=self.request.thing).open()
        tracker = ThingTracker(self.request.thing)
        turned = 0.0
        try:
            if wheels.why_not() is None:
                await leave_dock(kit, wheels)
            while True:
                await kit.pace.sleep(0.5)
                seen, sight = look(kit, tracker)
                if seen is None:
                    seen, sight = await self._close_look(kit, tracker)
                if seen is not None:
                    angle = body_bearing(seen.bearing_deg, sight.camera)
                    if abs(angle) > 8.0 and wheels.why_not() is None:
                        await turn_by(kit, wheels, angle)
                    return Ending("done", f"you found {name}", f"There's {name}!")
                if turned >= 359.0:
                    break
                if wheels.why_not() is not None:
                    break
                done, problem = await turn_by(kit, wheels, FIND_STEP_DEG)
                moved(kit)
                turned += abs(done) if done else FIND_STEP_DEG
                if problem and problem not in ("the turn took too long",):
                    break
            memory = kit.recall(self.request.thing, self.asker.tier == STRANGER)
            return Ending("lost", f"you looked all around and could not see {name}", f"I looked all around but I can't see {name}. {memory}".strip())
        finally:
            await wheels.halt()
            wheels.close()


class Follow(_Approach):
    kind = "follow"
    gap_m = FOLLOW_GAP_M
    lost_s = FOLLOW_LOST_S
    max_s = FOLLOW_MAX_S
    arrive = False
    control = None

    async def run(self, kit: Kit) -> Ending:
        following = getattr(kit.nav, "follow", None)
        if following is None or self.request.thing:
            return await super().run(kit)
        if not kit.eyes.available:
            return Ending("no_sight", "you cannot see yet", "I can't see yet, so I can't follow you.")
        await kit.eyes.use_camera("front")
        await level_head(kit)
        seen, _ = look(kit, Tracker())
        lead = Lead(self.target.id if self.target else None, self.target.label if self.target else "", seen.track if seen is not None else None)
        self.control = FollowControl(gap_m=self.gap, top=None)
        if kit.body.telemetry.docked:
            wheels = Wheels(kit).open()
            try:
                if wheels.why_not() is None:
                    await leave_dock(kit, wheels)
            finally:
                await wheels.halt()
                wheels.close()
        trip = await following(kit, lead, self.control)
        if trip.ok:
            return Ending("done", trip.text or f"you followed {self.whom('them')}", "I'll wait out here." if trip.how == "private" else (f"I'll wait out here. {trip.text.split(': ', 1)[-1]}" if trip.how == "kept out" else ""))
        ending = {"lost": "lost", "stuck": "reflex", "edge": "reflex", "stopped": "stopped", "battery": "battery", "timeout": "timeout", "no_sight": "no_sight", "lost_pose": "failed"}.get(trip.how, "failed")
        say = {"lost": "I lost you, so I'll stop here.", "timeout": "That's taking too long. I'll stop here.", "battery": "My battery's getting low, so I'll stop here."}.get(trip.how, "")
        return Ending(ending, trip.text or f"you stopped following ({trip.how})", say)

    def thing_gap(self, thing: str) -> float:
        return max(ANIMAL_FOLLOW_GAP_M, animal_gap(thing)) if is_animal(thing) else FOLLOW_GAP_M

    def describe(self) -> str:
        if self.request.thing:
            return f"following the {spoken(self.request.thing)}"
        return f"following {self.who()}"

    def lost(self, kit: Kit) -> Ending:
        return Ending("lost", f"you lost sight of {self.named()} for {round(self.lost_s)} seconds and looked around once", "I lost you, so I'll stop here." if not self.request.thing else f"I lost {self.named()}, so I'll stop here.")

    def adjust(self, request: Request) -> tuple[str, Request | None]:
        change = request.change
        reply, replacement = self._adjust(request)
        if self.control is not None:
            self.control.gap_m = clamp(self.gap, *FOLLOW_GAPS)
            if change == "slower":
                self.control.top = SLOW_FOLLOW
            elif change == "faster":
                self.control.top = None
        return reply, replacement

    def _adjust(self, request: Request) -> tuple[str, Request | None]:
        change = request.change
        if change == "slower":
            self.top = max(0.2, self.top - 0.1)
        elif change == "faster":
            self.top = min(0.5, self.top + 0.1)
            if self.top >= 0.5:
                return "This is as fast as I go near people.", None
        elif change == "closer":
            floor = max(ANIMAL_FOLLOW_GAP_M, animal_gap(self.request.thing)) if self.request.thing and is_animal(self.request.thing) else FOLLOW_GAPS[0]
            self.gap = max(floor, self.gap - 0.3)
            if self.gap <= floor:
                return "This is as close as I go.", None
        elif change == "further":
            self.gap = min(FOLLOW_GAPS[1], self.gap + 0.3)
        elif change in ("enough", "stay"):
            return "Okay, I'll stay here.", Request("wait")
        elif change == "other_way":
            return "I go where you go, so I'll keep following.", None
        return "", None


class BackOff(Activity):
    kind = "back_off"

    def describe(self) -> str:
        return "backing off"

    async def run(self, kit: Kit) -> Ending:
        wheels = Wheels(kit).open()
        then = Request("wait")
        try:
            if wheels.why_not():
                return Ending("blocked", "you were asked for space but moving is off, so you kept still", "I'll keep still right here.", then)
            want = self.request.metres or (0.1 if self.request.amount == "little" else BACK_OFF_M)
            want = min(BACK_OFF_M, want)
            done, problem = await roll_by(kit, wheels, -want * 1000.0, BACK_POWER)
            moved = abs(done) / 1000.0
            if problem and moved < want * 0.5:
                return Ending("done", f"you backed off only {round(moved * 100)} cm ({problem})", "I can't back up much further. I'll stay here.", then)
            return Ending("done", f"you backed off {round(moved * 100)} cm to give space", "", then)
        finally:
            await wheels.halt()
            wheels.close()


class Turn(Activity):
    kind = "turn"

    def describe(self) -> str:
        return f"turning {self.request.way}".strip()

    def degrees(self) -> float:
        request = self.request
        if request.degrees:
            return request.degrees
        if request.way == "around":
            return 180.0
        return TURN_DEG.get(request.amount, TURN_DEG[""])

    def adjust(self, request: Request) -> tuple[str, Request | None]:
        if request.change == "other_way":
            way = {"left": "right", "right": "left"}.get(self.request.way, "right")
            return "Other way, got it.", self.request.with_(way=way)
        return super().adjust(request)

    async def run(self, kit: Kit) -> Ending:
        wheels = Wheels(kit).open()
        try:
            target = self.degrees()
            sign = -1.0 if self.request.way == "right" else 1.0
            await leave_dock(kit, wheels)
            done, problem = await turn_by(kit, wheels, sign * target, 0.4 if self.request.speed == "quick" else 0.35)
            if problem and abs(done) < target * 0.8:
                return Ending("failed", f"you turned only {round(abs(done))} degrees ({problem})", "I couldn't turn all the way.")
            return Ending("done", f"you turned {round(abs(done))} degrees", "")
        finally:
            await wheels.halt()
            wheels.close()


class Move(Activity):
    kind = "move"

    def describe(self) -> str:
        return f"moving {self.request.way or 'forward'} a bit"

    async def run(self, kit: Kit) -> Ending:
        wheels = Wheels(kit).open()
        way = "back" if self.request.way == "back" else "forward"
        want = self.request.metres or MOVE_M.get(self.request.amount, MOVE_M[""]) * (0.6 if way == "back" else 1.0)
        want = min(MOVE_MAX[way], want)
        try:
            done, problem = await roll_by(kit, wheels, (want if way == "forward" else -want) * 1000.0, MOVE_POWER if way == "forward" else BACK_POWER)
            moved = abs(done) / 1000.0
            if problem and moved < want * 0.7:
                say = "There's an edge, so I stopped." if problem == "edge" else ("Something's in the way." if problem in ("bump", "the wheels stopped making progress") else "I stopped early.")
                return Ending("failed", f"you moved only {round(moved * 100)} cm ({problem})", say)
            return Ending("done", f"you moved {way} {round(moved * 100)} cm", "")
        finally:
            await wheels.halt()
            wheels.close()


KINDS = {"wait": Wait, "look": Look, "come": Come, "follow": Follow, "back_off": BackOff, "turn": Turn, "move": Move, "go_to_thing": GoToThing, "find": Find}
