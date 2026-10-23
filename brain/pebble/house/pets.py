import math

from ..alive.caring import bowl_in_view, floor_xy
from ..things.words import canonical, is_animal

DOOR_KINDS = frozenset({"door", "front door", "back door", "cat flap"})
BY_DOOR_M = 1.2
BY_DOOR_DEG = 20.0
TOLD_GAP_S = 1800.0
SPELL_MIN_S = 30.0
WATER_HOURS = (15, 18)
WATER_QUESTION = "Is there a pet's water bowl on the floor here, and does it look empty?"


def by_door(sight) -> str | None:
    if sight is None:
        return None
    doors = [t for t in sight.things if canonical(t.label) in DOOR_KINDS or t.label in DOOR_KINDS]
    for animal in sight.things:
        if not (animal.animal or is_animal(animal.label)):
            continue
        spot = floor_xy(animal)
        for door in doors:
            near = floor_xy(door)
            if spot is not None and near is not None and math.hypot(spot[0] - near[0], spot[1] - near[1]) <= BY_DOOR_M:
                return canonical(animal.label)
            if abs(animal.bearing_deg - door.bearing_deg) <= BY_DOOR_DEG:
                return canonical(animal.label)
    return None


class PetCare:
    def __init__(self, house):
        self.house = house
        self.door_told = -math.inf
        self.water_day = ""
        self.busy = False

    def spell(self, event: str, detail: dict, mono: float, now: float) -> None:
        house = self.house
        phase = detail.get("phase")
        if event == "meowing" and phase == "start":
            animal = by_door(house.sight())
            if animal is not None and mono - self.door_told >= TOLD_GAP_S:
                self.door_told = mono
                line = f"The {animal}'s meowing by the door."
                if house.teller.to_household(line, "cat_door", mono):
                    house.note(f"the {animal} is meowing by the door, so you said so", False)
                else:
                    house.away.add("meowing", f"the {animal} was meowing by the door", now)
            return
        if phase != "end":
            return
        seconds = float(detail.get("seconds") or 0.0)
        if seconds < SPELL_MIN_S:
            return
        wall_began = house.wall(float(detail.get("began", mono)))
        wall_ended = house.wall(float(detail.get("ended", mono)))
        if event == "meowing":
            text = f"the cat meowed on and off from {house.hhmm(wall_began)} to {house.hhmm(wall_ended)}"
        else:
            text = f"the dog howled or whimpered on and off from {house.hhmm(wall_began)} to {house.hhmm(wall_ended)}"
        house.away.add(event, text, wall_began)
        if not house.household_here(now):
            house.note(f"while nobody was here, {text}", False)

    def water_due(self, sight) -> bool:
        local = self.house.clock.local()
        return not self.busy and self.water_day != local.date().isoformat() and WATER_HOURS[0] <= local.hour < WATER_HOURS[1] and bowl_in_view(sight)

    async def water(self, sight) -> None:
        house = self.house
        if not self.water_due(sight):
            return
        day = house.clock.local().date().isoformat()
        commands = getattr(house.life, "commands", None)
        pictures = getattr(commands, "pictures", None)
        if pictures is None or house.busy() or commands.runner.current is not None:
            return
        self.busy = True
        try:
            if not await pictures.can_look():
                return
            self.water_day = day
            empty = await pictures.yes(WATER_QUESTION)
            house.record("water_bowl_checked", empty=empty)
            if empty:
                caring = getattr(getattr(house.life, "alive", None), "caring", None)
                line = "The pet's water bowl looks empty."
                if caring is not None:
                    caring.tell_trusted("water", line, day)
                house.away.add("water_bowl", "the water bowl looked empty", house.clock.now())
        finally:
            self.busy = False
