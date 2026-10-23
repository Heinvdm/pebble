import math

from ..respect import is_alive
from ..things.words import is_animal, spoken
from ..understand.request import Request
from .base import Activity, Ending
from .kinds import level_head, moved
from .kit import Kit
from .motion import Wheels, clamp, leave_dock, roll_by, turn_by, wrap_deg
from .seeing import ThingTracker, animal_gap, animals_ahead, body_bearing, look, scan, thing_gap_m, thing_lift_m

LEG_M = 0.6
ARRIVE_M = 0.35
THERE_SHORT_M = 0.3
THERE_MAX_M = 3.0
SETTLE_M = 1.0
ASKER_SEEN_S = 600.0
FACE_ASKER_DEG = 20.0
CLEAR_MM = 220
PLACE_MAX_S = 150.0
LOOK_THERE_S = 6.0
POINT_FRESH_S = 12.0
PLAY_S = 75.0
PLAY_TOP = 0.36
NUDGE_GAP_M = 0.14
NUDGE_S = 0.7
NUDGE_POWER = 0.4
NUDGES_MAX = 6
FLOOR_LIFT_M = 0.12
TOY_LOST_S = 6.0
WIGGLE_DEG = 14.0
ANIMAL_PLAY_S = 30.0
ANIMAL_WIGGLE_S = 5.0
ANIMAL_LEFT_S = 6.0
ANIMAL_AWAY_M = 0.7
ANIMAL_PLAY_LIMIT_M = 1.0


def _front_mm(kit: Kit) -> int | None:
    status = kit.body.telemetry.status
    return status.front_mm if status else None


class GoToPlace(Activity):
    kind = "go_to_place"

    def describe(self) -> str:
        return "going over there" if self.request.place == "there" else f"going to the {self.request.place}"

    def _target(self, kit: Kit) -> tuple[float, float, float] | str:
        odometer = kit.odometer
        if self.request.place == "there":
            pointed = kit.pointed()
            if pointed is None or kit.pace.now() - pointed.at > POINT_FRESH_S:
                return "you did not see where they pointed"
            if pointed.world is not None and odometer is not None and odometer.usable:
                return pointed.world[0], pointed.world[1], THERE_SHORT_M
            return "relative"
        room = kit.place_at(self.request.place)
        if room is None:
            return f"you do not know where the {self.request.place} is"
        if odometer is None or not odometer.usable:
            return "you have lost track of where you are"
        return room[0], room[1], min(ARRIVE_M + room[2] * 0.3, 0.8)

    async def _relative(self, kit: Kit, wheels: Wheels) -> Ending:
        pointed = kit.pointed()
        _, problem = await turn_by(kit, wheels, pointed.angle_deg)
        moved(kit)
        if problem and problem != "the turn took too long":
            return Ending("blocked", f"the turn stopped ({problem})", "I can't turn that way just now.")
        distance = clamp(pointed.distance_m - THERE_SHORT_M, 0.0, THERE_MAX_M)
        travelled, problem = await self._roll(kit, wheels, distance)
        moved(kit)
        if problem:
            return Ending("blocked", f"you stopped after {travelled:.1f} m ({problem})", "Something's in the way, so I stopped here.")
        return Ending("done", f"you went where you were pointed, about {pointed.distance_m:.1f} m away", "Here?")

    async def _roll(self, kit: Kit, wheels: Wheels, distance: float) -> tuple[float, str | None]:
        done = 0.0
        while distance - done > 0.05:
            front = _front_mm(kit)
            if front is not None and 0 <= front < CLEAR_MM:
                return done, "something is in the way"
            step = min(LEG_M, distance - done)
            travelled, problem = await roll_by(kit, wheels, step * 1000.0, 0.4)
            done += max(0.0, travelled / 1000.0)
            if problem:
                return done, problem
        return done, None

    async def _door(self, kit: Kit, wheels: Wheels, room: str) -> Ending | None:
        from ..privacy.look import at_door, to_door

        trip = await to_door(kit, room)
        if trip is None:
            return Ending("done", f"the {room} is private, so you did not go in", f"The {room} is private, so I won't go in.")
        if not trip.ok:
            ending = {"stopped": "stopped", "timeout": "timeout", "battery": "battery", "stuck": "reflex", "edge": "reflex", "lost_pose": "failed", "no_way": "blocked"}.get(trip.how, "blocked")
            return Ending(ending, trip.text or f"you could not get to the door of the {room} ({trip.how})", "" if trip.how == "stopped" else "Something's in the way, so I stopped here.")
        moved(kit)
        outcome = await at_door(kit, wheels, room, self.asker)
        if outcome == "in":
            return None
        return Ending("done", f"you went to the door of the {room}, which is private, and stayed outside", "")

    async def _face_asker(self, kit: Kit, wheels: Wheels) -> None:
        last = getattr(kit.nav, "last_person", None)
        spot = last(ASKER_SEEN_S) if last is not None else None
        if spot is None or wheels.why_not() is not None:
            return
        x, y, heading = kit.odometer.pose()
        aim = wrap_deg(math.degrees(math.atan2(spot[1] - y, spot[0] - x)) - heading)
        if abs(aim) > FACE_ASKER_DEG:
            await turn_by(kit, wheels, aim)
            moved(kit)

    async def run(self, kit: Kit) -> Ending:
        target = self._target(kit)
        if isinstance(target, str) and target != "relative":
            return Ending("failed", target, "I've lost track of where I am." if "lost track" in target else "I don't know the way there.")
        wheels = Wheels(kit).open()
        start = kit.pace.now()
        try:
            if wheels.why_not() is None:
                await leave_dock(kit, wheels)
            if target == "relative":
                return await self._relative(kit, wheels)
            tx, ty, close = target
            privacy = getattr(kit, "privacy", None)
            if privacy is not None and self.request.place and privacy.blocks(tx, ty) == self.request.place:
                outside = await self._door(kit, wheels, self.request.place)
                if outside is not None:
                    return outside
            going = getattr(kit.nav, "go_to", None)
            if going is not None:
                trip = await going(kit, tx, ty, stop_m=close, settle_m=SETTLE_M)
                if not trip.ok:
                    ending = {"stopped": "stopped", "timeout": "timeout", "battery": "battery", "stuck": "reflex", "edge": "reflex", "lost_pose": "failed", "no_way": "blocked"}.get(trip.how, "blocked")
                    say = "I've lost track of where I am." if trip.how == "lost_pose" else ("I can't find a way through." if trip.how == "no_way" else "Something's in the way, so I stopped here.")
                    return Ending(ending, trip.text or f"you could not get there ({trip.how})", say if trip.how != "stopped" else "")
                moved(kit)
                tx, ty = kit.odometer.pose()[:2]
            while True:
                if kit.pace.now() - start > PLACE_MAX_S:
                    return Ending("timeout", "it took too long to get there", "That's taking too long. I'll stop here.")
                if kit.battery_low():
                    return Ending("battery", "your battery got low", "My battery's getting low, so I'll stop here.")
                x, y, heading = kit.odometer.pose()
                gap = math.hypot(tx - x, ty - y)
                if gap <= close:
                    break
                aim = math.degrees(math.atan2(ty - y, tx - x))
                _, problem = await turn_by(kit, wheels, wrap_deg(aim - heading))
                moved(kit)
                if problem and problem != "the turn took too long":
                    return Ending("blocked", f"the turn stopped ({problem})", "I can't turn that way just now.")
                _, problem = await self._roll(kit, wheels, min(LEG_M, gap - close + 0.02))
                moved(kit)
                if problem:
                    return Ending("blocked", f"you stopped on the way ({problem})", "Something's in the way, so I stopped here.")
                await kit.pace.sleep(0.3)
            drift = 0.05 + 0.04 * getattr(kit.odometer, "travelled_m", 0.0)
            place = "where you were pointed" if self.request.place == "there" else f"the {self.request.place}"
            if self.request.place == "there":
                await self._face_asker(kit, wheels)
                return Ending("done", f"you went {place}", "Here?")
            if drift > 0.5:
                return Ending("done", f"you went to {place} by dead reckoning, give or take {drift:.1f} m", f"I think this is the {self.request.place}, but I'm not sure exactly.")
            return Ending("done", f"you went to {place} by dead reckoning, give or take {drift:.1f} m", f"Here I am in the {self.request.place}.")
        finally:
            await wheels.halt()
            wheels.close()


class LookThere(Activity):
    kind = "look"
    sight = True

    def describe(self) -> str:
        return "looking where you pointed"

    async def run(self, kit: Kit) -> Ending:
        pointed = kit.pointed()
        if pointed is None or kit.pace.now() - pointed.at > POINT_FRESH_S:
            return Ending("lost", "you did not see where they pointed", "Where? I didn't see you point.")
        await kit.eyes.use_camera("front")
        wheels = Wheels(kit).open()
        angle = pointed.angle_deg
        odometer = kit.odometer
        if pointed.world is not None and odometer is not None and odometer.usable:
            x, y, heading = odometer.pose()
            angle = wrap_deg(math.degrees(math.atan2(pointed.world[1] - y, pointed.world[0] - x)) - heading)
        try:
            if wheels.why_not() is None and abs(angle) > 8.0:
                await turn_by(kit, wheels, angle)
                moved(kit)
            down = -math.degrees(math.atan2(0.14, max(0.3, pointed.distance_m)))
            rest = kit.body.profile.tilt_rest
            await kit.body.tilt(clamp(rest + down * 0.6, kit.body.profile.tilt_min, kit.body.profile.tilt_max))
            moved(kit)
            await kit.pace.sleep(LOOK_THERE_S if not self.request.seconds else min(self.request.seconds, 60.0))
            sight = kit.eyes.latest(1.0)
            names = [t for t in (sight.things if sight else ()) if t.score >= 0.5 and abs(t.bearing_deg) <= 20.0]
            if names:
                best = max(names, key=lambda t: t.width_frac * t.height_frac)
                return Ending("done", f"you looked where you were pointed and saw a {spoken(best.label)}", f"Ooh, {('an ' if spoken(best.label)[0] in 'aeiou' else 'a ')}{spoken(best.label)}.")
            return Ending("done", "you looked where you were pointed", "")
        finally:
            await kit.body.tilt(kit.body.profile.tilt_rest)
            await wheels.halt()
            wheels.close()


class Wiggle(Activity):
    kind = "wiggle"
    why = "hello"

    def describe(self) -> str:
        return f"wiggling {self.why}"

    async def run(self, kit: Kit) -> Ending:
        if kit.body.telemetry.docked:
            rest = kit.body.profile.tilt_rest
            for tilt in (rest + 8.0, rest - 4.0, rest + 6.0, rest):
                await kit.body.tilt(tilt)
                await kit.pace.sleep(0.25)
            moved(kit)
            return Ending("done", f"you wiggled your head {self.why}, since you were on your charger", "")
        wheels = Wheels(kit).open()
        try:
            if wheels.why_not() is not None:
                return Ending("blocked", "moving is off right now", "")
            for step in (WIGGLE_DEG, -2 * WIGGLE_DEG, WIGGLE_DEG):
                _, problem = await turn_by(kit, wheels, step, power=0.4, timeout_s=1.5)
                if problem and problem != "the turn took too long":
                    return Ending("blocked", f"the wiggle stopped ({problem})", "")
            moved(kit)
            return Ending("done", f"you wiggled {self.why}", "")
        finally:
            await wheels.halt()
            wheels.close()


class GoBack(Activity):
    kind = "go_back"

    def describe(self) -> str:
        place = self.request.place
        return "going back to where we started" if place in ("", "start") else f"going back to the {place}"

    async def run(self, kit: Kit) -> Ending:
        going = getattr(kit.nav, "go_back", None)
        if going is None:
            return Ending("failed", "you cannot retrace your way yet", "I can't find my way back like that yet.")
        trip = await going(kit, to=self.request.place or "start")
        if getattr(trip, "ok", False):
            return Ending("done", f"you went back ({trip.text})" if getattr(trip, "text", "") else "you went back", "Here we are.")
        how = getattr(trip, "how", "failed")
        ending = {"blocked": "blocked", "stuck": "reflex", "edge": "reflex", "stopped": "stopped", "timeout": "timeout", "battery": "battery", "lost": "lost"}.get(how, "failed")
        return Ending(ending, getattr(trip, "text", "") or "you could not go back", "I couldn't find the way back. I'll stop here.")


class GoToSpot(Activity):
    def __init__(self, request, asker, target=None, battery=False, spot: tuple | None = None):
        super().__init__(request, asker, target, battery)
        self.kind = request.kind
        self.spot = spot

    def describe(self) -> str:
        return f"going to {self.spot[2]}" if self.spot else "going to a spot"

    async def run(self, kit: Kit) -> Ending:
        from .rounds import go

        if self.spot is None:
            return Ending("failed", "you did not know where that was", "I don't know where that was.")
        x, y, words = self.spot
        wheels = Wheels(kit).open()
        try:
            if wheels.why_not() is None:
                await leave_dock(kit, wheels)
            trip = await go(kit, x, y, 0.0)
            if trip.ok:
                moved(kit)
                return Ending("done", f"you went to {words}", "" if self.asker.own else "Here we are.")
            if trip.how in ("private", "kept out"):
                return Ending("done", trip.text, "That's somewhere I keep out of, so I stopped here.")
            ending = {"stopped": "stopped", "timeout": "timeout", "battery": "battery", "stuck": "reflex", "edge": "reflex", "lost_pose": "failed", "no_way": "blocked"}.get(trip.how, "blocked")
            say = "" if trip.how == "stopped" else ("I've lost track of where I am." if trip.how == "lost_pose" else "I couldn't get there. I'll stop here.")
            return Ending(ending, trip.text or f"you could not get to {words}", say)
        finally:
            await wheels.halt()
            wheels.close()


class FaceTo(Activity):
    kind = "face_to"

    def __init__(self, request, asker, target=None, battery=False, angle_deg: float = 0.0):
        super().__init__(request, asker, target, battery)
        self.angle_deg = angle_deg

    def describe(self) -> str:
        return "turning to face whoever is talking"

    async def run(self, kit: Kit) -> Ending:
        wheels = Wheels(kit).open()
        try:
            if wheels.why_not() is not None:
                return Ending("blocked", "moving is off right now", "")
            _, problem = await turn_by(kit, wheels, self.angle_deg, power=0.3, timeout_s=4.0)
            moved(kit)
            if problem and problem != "the turn took too long":
                return Ending("blocked", f"the turn stopped ({problem})", "")
            return Ending("done", "you turned to face whoever was talking", "")
        finally:
            await wheels.halt()
            wheels.close()


class Play(Activity):
    kind = "play"
    sight = True

    def __init__(self, request, asker, target=None, battery=False):
        super().__init__(request, asker, target, battery)
        self.nudges = 0
        self.top = PLAY_TOP
        self.thing = request.thing

    def describe(self) -> str:
        return f"playing with the {spoken(self.thing)}" if self.thing else "playing"

    def _pick(self, kit: Kit) -> str:
        sight = kit.eyes.latest(1.0)
        if sight is None:
            return ""
        toys = [t for t in sight.things if t.score >= 0.5 and not t.animal and not is_alive(t.label) and (kit.toy(t.label) or (t.known and kit.toy(t.known)))]
        if not toys:
            return ""
        best = max(toys, key=lambda t: t.width_frac * t.height_frac)
        return best.label

    async def _animal(self, kit: Kit, name: str) -> Ending:
        await level_head(kit)
        wheels = Wheels(kit).open()
        kind = spoken(self.request.thing)
        try:
            tracker = ThingTracker(self.request.thing)
            seen, sight = look(kit, tracker)
            if seen is None and wheels.why_not() is None:
                seen, sight, _ = await scan(kit, wheels, tracker)
            if seen is None:
                return Ending("lost", f"you could not see {name}", f"I can't see {name}.")
            if animal_gap(self.request.thing) > ANIMAL_PLAY_LIMIT_M:
                kit.face.show("happy")
                return Ending("done", f"you gave {name} plenty of room instead of playing", f"Hello, {kind}! I'll give you some room.")
            start_gap = thing_gap_m(seen, sight, kit.body.telemetry.tilt, None)
            start = kit.pace.now()
            last_seen = start
            wiggles = 0
            while kit.pace.now() - start < ANIMAL_PLAY_S:
                await kit.pace.sleep(ANIMAL_WIGGLE_S)
                seen, sight = look(kit, tracker)
                now = kit.pace.now()
                if seen is None:
                    if now - last_seen > ANIMAL_LEFT_S:
                        return Ending("done", f"you played gently with {name} until it wandered off", f"Bye, {kind}.")
                    continue
                last_seen = now
                if thing_gap_m(seen, sight, kit.body.telemetry.tilt, None) > start_gap + ANIMAL_AWAY_M:
                    return Ending("done", f"you played gently with {name} until it moved away", f"Bye, {kind}.")
                if wheels.why_not() is None:
                    for step in (10.0, -20.0, 10.0):
                        await turn_by(kit, wheels, step, power=0.3, timeout_s=1.5)
                    wiggles += 1
                kit.face.show("happy" if wiggles % 2 else "mischief")
            return Ending("done", f"you played gently with {name} from a distance, without chasing", f"That was nice, {kind}.")
        finally:
            await wheels.halt()
            wheels.close()

    async def run(self, kit: Kit) -> Ending:
        if not kit.eyes.available:
            return Ending("no_sight", "you cannot see yet", "I can't see yet, so I can't play.")
        await kit.eyes.use_camera("front")
        await level_head(kit)
        if self.request.thing and is_animal(self.request.thing):
            return await self._animal(kit, f"the {spoken(self.request.thing)}")
        thing = self.request.thing or self._pick(kit)
        self.thing = thing
        if not thing:
            return Ending("lost", "you could not see a toy on the floor", "I can't see a toy on the floor. Roll me the ball?")
        if not kit.toy(thing):
            return Ending("failed", f"the {spoken(thing)} is not a toy", f"I only play with toys on the floor, and the {spoken(thing)} isn't one.")
        name = f"the {spoken(thing)}"
        wheels = Wheels(kit, exempt=thing).open()
        tracker = ThingTracker(thing)
        start = kit.pace.now()
        seen_at = start
        try:
            seen, sight = look(kit, tracker)
            if seen is None and wheels.why_not() is None:
                seen, sight, problem = await scan(kit, wheels, tracker)
            if seen is None:
                return Ending("lost", f"you looked around but could not see {name}", f"I can't see {name}.")
            if thing_lift_m(seen, sight, kit.body.telemetry.tilt) > FLOOR_LIFT_M:
                return Ending("failed", f"{name} is up off the floor", f"{name[0].upper()}{name[1:]} is up high. I only play with things on the floor.")
            if wheels.why_not() is None:
                await leave_dock(kit, wheels)
            while True:
                now = kit.pace.now()
                if now - start > PLAY_S or self.nudges >= NUDGES_MAX:
                    return Ending("done", f"you played with {name} and nudged it {self.nudges} times", "That was fun!")
                if kit.battery_low():
                    return Ending("battery", "your battery got low", "My battery's getting low, so I'll stop playing.")
                reason = wheels.why_not()
                if reason:
                    return Ending("blocked", reason, "")
                hits = [r for r in wheels.reflexes() if r in ("edge", "fault")]
                if hits:
                    return Ending("reflex", f"your body stopped ({hits[0]})", "Whoa, there's an edge. I'll stop playing.")
                seen, sight = look(kit, tracker)
                if seen is None:
                    await wheels.halt()
                    if now - seen_at > TOY_LOST_S:
                        seen, sight, _ = await scan(kit, wheels, tracker, max_deg=180.0)
                        if seen is None:
                            return Ending("lost", f"you lost {name}", f"Where did {name} go?")
                        seen_at = kit.pace.now()
                    await kit.pace.sleep(kit.control_s)
                    continue
                seen_at = now
                if any(gap < animal_gap(animal.label) + 0.2 for animal, gap in animals_ahead(sight, kit.body.telemetry.tilt)):
                    await wheels.halt()
                    await kit.pace.sleep(0.5)
                    continue
                angle = body_bearing(seen.bearing_deg, sight.camera)
                gap = thing_gap_m(seen, sight, kit.body.telemetry.tilt, _front_mm(kit))
                turn = 0.0 if abs(angle) < 3.0 else clamp(math.radians(angle) * 0.9, -0.4, 0.4)
                if gap <= NUDGE_GAP_M + 0.04 and abs(angle) < 12.0:
                    await self._nudge(kit, wheels)
                    continue
                forward = clamp((gap - NUDGE_GAP_M) * 0.9 + 0.12, 0.0, self.top) if abs(angle) <= 30.0 else 0.0
                if forward == 0.0 and abs(angle) > 6.0:
                    turn = math.copysign(max(abs(turn), 0.24), turn)
                await wheels.drive(forward, turn, self.top)
                await kit.pace.sleep(kit.control_s)
        finally:
            await wheels.halt()
            wheels.close()

    async def _nudge(self, kit: Kit, wheels: Wheels) -> None:
        self.nudges += 1
        kit.face.show("mischief" if self.nudges % 2 else "happy")
        end = kit.pace.now() + NUDGE_S
        while kit.pace.now() < end:
            if await wheels.drive(NUDGE_POWER, 0.0, NUDGE_POWER):
                break
            if any(r in ("edge", "fault") for r in wheels.reflexes()):
                break
            await kit.pace.sleep(kit.control_s)
        await wheels.halt()
        await roll_by(kit, wheels, -60.0, 0.3, timeout_s=2.0)
        moved(kit)
        kit.note(f"you nudged the {spoken(self.thing or 'toy')} and watched it roll")

    def adjust(self, request: Request) -> tuple[str, Request | None]:
        if request.change in ("enough", "stay"):
            return "Okay, I'll stop playing.", Request("wait")
        if request.change == "slower":
            self.top = max(0.2, self.top - 0.08)
        elif request.change == "faster":
            self.top = min(0.45, self.top + 0.08)
        return "", None
