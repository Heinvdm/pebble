import math
from datetime import timedelta

from ..people.trust import INNER, TRUSTED
from ..seams.sight import Sight
from ..things.words import canonical, is_animal, spoken

BOWL_KINDS = frozenset({"bowl", "pet bowl", "dog bowl", "cat bowl", "dog food", "cat food"})
EATING_NEAR_M = 0.6
FEEDING_COUNT = 2.5
FEEDING_AHEAD_MIN = 30
DOOR_EVERY_S = 1800.0
NIGHT_HOURS = (23, 5)
DOOR_KINDS = frozenset({"door", "front door", "back door"})


def floor_xy(thing) -> tuple[float, float] | None:
    if thing.floor_m is None or thing.floor_bearing_deg is None:
        return None
    angle = math.radians(-thing.floor_bearing_deg)
    return thing.floor_m * math.cos(angle), thing.floor_m * math.sin(angle)


def eating(sight: Sight | None) -> str | None:
    if sight is None:
        return None
    bowls = [floor_xy(t) for t in sight.things if canonical(t.label) in BOWL_KINDS or t.label in BOWL_KINDS]
    bowls = [b for b in bowls if b is not None]
    for animal in sight.things:
        if not (animal.animal or is_animal(animal.label)):
            continue
        spot = floor_xy(animal)
        if spot is None:
            continue
        if any(math.hypot(spot[0] - b[0], spot[1] - b[1]) <= EATING_NEAR_M for b in bowls):
            return canonical(animal.label)
    return None


def bowl_in_view(sight: Sight | None) -> bool:
    return sight is not None and sight.camera == "front" and any((canonical(t.label) in BOWL_KINDS or t.label in BOWL_KINDS) and t.floor_m is not None for t in sight.things)


def door_in_view(sight: Sight | None) -> bool:
    return sight is not None and sight.camera == "front" and any(canonical(t.label) in DOOR_KINDS or t.label in DOOR_KINDS for t in sight.things)


def late_night(hour: int) -> bool:
    return hour >= NIGHT_HOURS[0] or hour < NIGHT_HOURS[1]


class Caring:
    def __init__(self, alive):
        self.alive = alive
        self.pending: dict[str, str] = {}
        self.told: dict[str, str] = {}
        self.asked: dict[str, str] = {}
        self.door_at = -math.inf
        self.busy = False

    @property
    def p(self):
        return self.alive.p

    def tell_trusted(self, key: str, text: str, day: str) -> bool:
        if self.told.get(key) == day:
            return False
        self.told[key] = day
        self.pending[key] = text
        self.alive.note(f"{text} You want to tell someone you trust.", True)
        self.p.blackbox.record("tell_trusted", about=key)
        owner = getattr(self.p.safety, "tell_owner", None)
        if owner is not None:
            try:
                owner("Pebble noticed something", text)
            except Exception:
                pass
        self.deliver()
        return True

    def deliver(self) -> None:
        if not self.pending:
            return
        company = self.alive.life.company
        now = self.p.clock.now()
        trusted = [person for person in company.here(now) if company.tier(person, now) in (TRUSTED, INNER)]
        if not trusted:
            return
        for key, text in list(self.pending.items()):
            self.pending.pop(key)
            self.alive.life.commands._spawn(self.alive.life.commands.speak(text, False))
            self.p.blackbox.record("told", about=key, person=trusted[0].id)

    def watch(self, sight: Sight | None) -> None:
        animal = eating(sight)
        if animal is not None:
            local = self.p.clock.local()
            if self.alive.book.saw_at("pet:eating", local):
                self.alive.book.where["pet"] = animal
                self.alive.note(f"the {spoken(animal)} is eating from its bowl")

    async def tick(self, sight: Sight | None) -> None:
        if self.busy:
            return
        self.busy = True
        try:
            self.deliver()
            await self._bowl(sight)
            await self._door(sight)
        finally:
            self.busy = False

    async def _bowl(self, sight: Sight | None) -> None:
        pictures = self.alive.life.commands.pictures
        local = self.p.clock.local()
        day = local.date().isoformat()
        if pictures is None or self.asked.get("bowl") == day or not bowl_in_view(sight):
            return
        book = self.alive.book
        soon = local + timedelta(minutes=FEEDING_AHEAD_MIN)
        if book.usual("pet:eating", local) < FEEDING_COUNT and book.usual("pet:eating", soon) < FEEDING_COUNT:
            return
        if self.alive.quiet() or self.alive.life.commands.runner.current is not None or not await pictures.can_look():
            return
        self.asked["bowl"] = day
        empty = await pictures.yes("Is the pet food bowl on the floor empty?")
        self.p.blackbox.record("bowl_checked", empty=empty)
        if empty:
            pet = spoken(book.where.get("pet", "pet"))
            self.tell_trusted("bowl", f"The {pet}'s bowl looks empty, and it's about the time it usually eats.", day)

    async def _door(self, sight: Sight | None) -> None:
        pictures = self.alive.life.commands.pictures
        local = self.p.clock.local()
        mono = self.alive.mono
        if pictures is None or not late_night(local.hour) or mono - self.door_at < DOOR_EVERY_S:
            return
        if not self.p.body.telemetry.docked or not door_in_view(sight) or not await pictures.can_look():
            return
        self.door_at = mono
        night = (local - timedelta(hours=12)).date().isoformat()
        if self.told.get("door") == night:
            return
        open_ = await pictures.yes("Is the door in this picture open?")
        self.p.blackbox.record("door_checked", open=open_)
        if open_:
            self.tell_trusted("door", "The door I can see from my charger looks open, and it's late.", night)
