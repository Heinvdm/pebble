import math
import re

from ..things.words import matches, spoken
from ..understand.logic import span_words
from ..understand.request import Request
from .base import Activity, Ending
from .kit import Kit
from .motion import Wheels, leave_dock, turn_by
from .rounds import go
from .seeing import THING_SCORE, ThingTracker, body_bearing, person_gap_m, thing_gap_m

WATCH_MOST_S = 7200.0
STEP_S = 1.0
NEAR_M = 2.5
KEEP_M = 1.5
LOST_S = 20.0
AWAY_S = 20.0
BACK_S = 5.0
SEEN_HERE_S = 10.0
CRY_S = 12.0
CRY_SHARE = 0.5
SHARP_S = 5.0
HAZARD_M = 0.8
CLOSING_M = 0.15
HAZARD_KEEP_S = 10.0
FACE_DEG = 15.0
SCAN_STEP_DEG = 45.0
CHILD_WORDS = frozenset({"baby", "kid", "child", "children", "toddler", "little one", "kids", "boy", "girl", "twins", "bub", "bubba"})
CHILD_HAZARDS = frozenset({"stairs", "staircase", "stove", "oven", "hob", "cooker", "heater", "fireplace", "fire", "candle", "knife", "scissors", "pool", "swimming pool", "bucket", "bathtub", "iron", "kettle", "socket", "power socket", "plug socket", "power point", "extension cord", "bleach", "medicine", "pills", "balcony", "pond"})
LOW = ("crouching", "lying", "sitting")
WHO_WORDS = re.compile(r"\b(her|him)\b")


def child_like(request: Request) -> bool:
    return bool(request.thing) and request.thing in CHILD_WORDS


def watch_names(request: Request, said: str = "") -> tuple[str, str]:
    if request.thing:
        name = f"the {spoken(request.thing)}"
    elif request.who:
        name = request.who.title()
    else:
        name = "them"
    found = WHO_WORDS.search((said or "").lower())
    if found is not None and not request.thing:
        return found.group(1), found.group(1)
    if request.thing and not child_like(request):
        return name, "it"
    return name, "them"


def honesty(request: Request, said: str = "") -> str:
    name, them = watch_names(request, said)
    return f"I'll keep an eye on {name} and come and get you if something changes. I'm not a baby monitor, so please check on {them} yourself."


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


class Watch(Activity):
    kind = "watch"
    sight = True

    def __init__(self, request, asker, target=None, battery=False, said: str = "", child: bool = False):
        super().__init__(request, asker, target, battery)
        self.limit = min(request.seconds or WATCH_MOST_S, WATCH_MOST_S)
        self.name, self.them = watch_names(request, said)
        self.child = child or child_like(request)
        self.alert: tuple[str, str] | None = None
        self.alarmed = False
        self.back = False
        self.track: int | None = None
        self.bearing: float | None = None
        self.things = ThingTracker(request.thing) if request.thing and not child_like(request) else None
        self.hazards: dict[str, list] = {}

    def describe(self) -> str:
        return f"keeping an eye on {self.name}"

    def _people(self, kit: Kit, sight) -> list:
        out = []
        for person in sight.people:
            label = kit.name_of(person.track)
            if label is not None and self.asker.id is not None and label == self.asker.label:
                continue
            out.append(person)
        return out

    def _pick(self, kit: Kit, sight):
        if sight is None:
            return None
        if self.things is not None:
            return self.things.pick(sight)
        people = self._people(kit, sight)
        if not people:
            return None
        if self.track is not None:
            same = [p for p in people if p.track == self.track]
            if same:
                return self._keep(same[0], sight)
        if self.bearing is not None:
            near = min(people, key=lambda p: abs(body_bearing(p.bearing_deg, sight.camera) - self.bearing))
            if abs(body_bearing(near.bearing_deg, sight.camera) - self.bearing) <= 30.0:
                return self._keep(near, sight)
            return None
        if self.request.who and not self.request.thing:
            named = [p for p in people if (kit.name_of(p.track) or "").lower() == self.request.who.lower()]
            if named:
                return self._keep(named[0], sight)
        if len(people) == 1:
            return self._keep(people[0], sight)
        if self.child:
            low = [p for p in people if p.posture in LOW and p.posture_score >= 0.5]
            pool = low or people
            return self._keep(min(pool, key=lambda p: p.height_frac), sight)
        return None

    def _keep(self, person, sight):
        self.track = person.track if person.track is not None else self.track
        self.bearing = body_bearing(person.bearing_deg, sight.camera)
        return person

    def _gap(self, kit: Kit, seen, sight) -> float:
        if hasattr(seen, "label"):
            return thing_gap_m(seen, sight, kit.body.telemetry.tilt, None)
        return person_gap_m(seen, sight, None)

    def _spot(self, kit: Kit, seen, sight) -> tuple[float, float]:
        gap = self._gap(kit, seen, sight)
        angle = math.radians(body_bearing(seen.bearing_deg, sight.camera))
        return gap * math.cos(angle), gap * math.sin(angle)

    def _hazard(self, kit: Kit, seen, sight, now: float) -> str | None:
        if hasattr(seen, "label"):
            return None
        px, py = self._spot(kit, seen, sight)
        for thing in sight.things:
            if thing.score < THING_SCORE or not any(matches(word, thing.label) for word in CHILD_HAZARDS):
                continue
            tx, ty = self._spot(kit, thing, sight)
            gap = math.hypot(px - tx, py - ty)
            kept = [item for item in self.hazards.get(thing.label, []) if now - item[1] <= HAZARD_KEEP_S]
            kept.append((gap, now))
            self.hazards[thing.label] = kept
            if gap <= HAZARD_M and max(item[0] for item in kept) - gap >= CLOSING_M:
                return thing.label
        return None

    async def _face(self, kit: Kit, wheels: Wheels, seen, sight) -> None:
        angle = body_bearing(seen.bearing_deg, sight.camera)
        if abs(angle) > FACE_DEG and wheels.why_not() is None:
            await turn_by(kit, wheels, angle)
            self.bearing = 0.0
            if self.things is not None:
                self.things.turned(angle)

    async def _scan(self, kit: Kit, wheels: Wheels):
        turned = 0.0
        self.track, self.bearing = None, None
        if self.things is not None:
            self.things.reset()
        while turned < 359.0:
            await kit.pace.sleep(0.6)
            sight = kit.eyes.latest(0.8)
            seen = self._pick(kit, sight)
            if seen is not None:
                return seen, sight
            if wheels.why_not() is not None:
                return None, sight
            done, problem = await turn_by(kit, wheels, SCAN_STEP_DEG)
            turned += abs(done) if done else SCAN_STEP_DEG
            if problem and problem != "the turn took too long":
                return None, sight
        return None, None

    async def _near(self, kit: Kit, wheels: Wheels, seen, sight) -> None:
        gap = self._gap(kit, seen, sight)
        pointing = getattr(kit.nav, "point_at", None)
        if gap <= NEAR_M or pointing is None or wheels.why_not() is not None:
            return
        goal = pointing(body_bearing(seen.bearing_deg, sight.camera), gap - KEEP_M)
        if goal is None:
            return
        await leave_dock(kit, wheels)
        await go(kit, goal[0], goal[1], 0.0)
        self.track, self.bearing = None, None

    def _raise(self, kit: Kit, kind: str, loud: str, line: str, text: str) -> Ending:
        self.alert = (kind, line)
        kit.say_loud(f"{self.asker.label}! {loud}")
        return Ending("done", f"{text}, so you called {self.asker.label} loudly and are going to get them", "")

    async def run(self, kit: Kit) -> Ending:
        name, them = self.name, self.them
        if not kit.eyes.available:
            return Ending("no_sight", "you cannot see yet", f"I can't see yet, so I can't keep an eye on {name}.")
        await kit.eyes.use_camera("front")
        wheels = Wheels(kit).open()
        start = kit.pace.now()
        try:
            sight = kit.eyes.latest(0.8)
            seen = self._pick(kit, sight)
            if wheels.why_not() is None:
                await leave_dock(kit, wheels)
            if seen is None:
                seen, sight = await self._scan(kit, wheels)
            if seen is None:
                crowd = kit.eyes.latest(1.0)
                if self.things is None and crowd is not None and len(crowd.people) > 1:
                    return Ending("lost", f"you could not tell which person was {name}", f"I can't tell which one is {name} yet, so I can't keep an eye on {them}.")
                return Ending("lost", f"you could not see {name}", f"I can't see {name} here, so I can't keep an eye on {them}.")
            await self._near(kit, wheels, seen, sight)
            seen_at = kit.pace.now()
            gone = False
            scanned = False
            while True:
                await kit.pace.sleep(STEP_S)
                kit.sharpen(SHARP_S)
                now = kit.pace.now()
                if kit.alarm():
                    self.alarmed = True
                    return Ending("done", f"an alarm started while you kept an eye on {name}, so the alarm steps took over", "")
                if self.asker.id is not None:
                    if not kit.seen(self.asker.id, AWAY_S):
                        gone = True
                    elif gone and kit.seen(self.asker.id, BACK_S):
                        self.back = True
                        return Ending("done", f"{self.asker.label} came back, so you stopped keeping an eye on {name}", f"You're back. I've stopped keeping an eye on {name}.")
                if now - start >= self.limit:
                    span = span_words(self.limit)
                    return self._raise(kit, "time", f"I've been keeping an eye on {name} for {span}, so I've stopped.", f"I've kept an eye on {name} for {span}, so I've stopped. Please check on {them}.", f"you kept an eye on {name} for {span}, as long as you watch")
                if kit.crying(CRY_S) >= CRY_SHARE:
                    who = _cap(name) if name != "them" else "Someone"
                    return self._raise(kit, "crying", f"{who} is crying!", f"{name} is crying. Please come and check on {them}.", f"you heard crying while you kept an eye on {name}")
                privacy = getattr(kit, "privacy", None)
                if privacy is not None and privacy.active():
                    return self._raise(kit, "unseen", f"I can't see {name} properly any more.", f"I can't see {name} properly any more, so I came to get you. Please check on {them}.", f"you could no longer see {name} properly")
                sight = kit.eyes.latest(0.8)
                seen = self._pick(kit, sight)
                if seen is not None:
                    seen_at = now
                    scanned = False
                    near = self._hazard(kit, seen, sight, now)
                    if near is not None:
                        what = spoken(near)
                        return self._raise(kit, "hazard", f"{_cap(name)} is getting close to the {what}!", f"{name} was getting close to the {what}. Please come and check on {them}.", f"{name} was moving towards the {what}")
                    await self._face(kit, wheels, seen, sight)
                    continue
                if now - seen_at <= LOST_S:
                    continue
                if not scanned:
                    scanned = True
                    seen, sight = await self._scan(kit, wheels)
                    if seen is not None:
                        seen_at = kit.pace.now()
                        continue
                return self._raise(kit, "gone", f"I can't see {name} any more!", f"I lost sight of {name}. Please come and look.", f"{name} went out of view")
        finally:
            await wheels.halt()
            wheels.close()


class Fetch(Activity):
    kind = "fetch"

    def __init__(self, request, asker, target=None, battery=False, line: str = "", spot: tuple | None = None):
        super().__init__(request, asker, target, battery)
        self.line = line
        self.spot = spot
        self.report_to = asker.id

    def describe(self) -> str:
        return f"going to get {self.asker.label}"

    async def run(self, kit: Kit) -> Ending:
        label = self.asker.label
        said = f"{label}, {self.line}"
        if self.asker.id is not None and kit.seen(self.asker.id, SEEN_HERE_S):
            return Ending("done", f"you told {label} straight away", said)
        if self.spot is None:
            kit.say_loud(said)
            return Ending("done", f"you did not know where {label} was, so you called out loudly", "")
        wheels = Wheels(kit).open()
        try:
            await leave_dock(kit, wheels)
            trip = await go(kit, self.spot[0], self.spot[1], self.spot[2], door=True)
            if trip.ok and trip.how == "door":
                kit.say_loud(said)
                return Ending("done", f"you went to get {label}, stopped at the door of a private room and called through it", "")
            await kit.pace.sleep(2.0)
            if self.asker.id is not None and kit.seen(self.asker.id, SEEN_HERE_S):
                return Ending("done", f"you went to get {label} and told them", said)
            kit.say_loud(said)
            return Ending("done", f"you went to get {label} and called out loudly", "")
        finally:
            await wheels.halt()
            wheels.close()
