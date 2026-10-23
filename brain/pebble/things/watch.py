import math
import time
from dataclasses import dataclass
from typing import Callable

from ..activities.seeing import THING_SCORE, body_bearing, thing_gap_m
from ..seams.sight import Sight
from .book import ThingBook
from .words import LANDMARKS, canonical, spoken, with_article

NOTE_EVERY_S = 5.0
NOVEL_SCORE = 0.5
ANIMAL_NEAR_S = 8.0
NEAR_DEG = 25.0
SIGHT_AGE_S = 1.0
PERSON_DEPTH_M = 0.1


@dataclass(frozen=True)
class Sighting:
    label: str
    kind: str
    animal: bool
    where: str

    def text(self) -> str:
        if self.kind == "new":
            return f"something new on camera: {with_article(self.label)}, {self.where}"
        return f"the {spoken(self.label)} is somewhere new, {self.where}"


def where_words(angle: float) -> str:
    if abs(angle) <= 20:
        return "ahead of you"
    if abs(angle) >= 135:
        return "behind you"
    return "to your left" if angle > 0 else "to your right"


class ThingWatcher:
    def __init__(
        self,
        book: ThingBook,
        eyes,
        odometer=None,
        tilt: Callable[[], float | None] = lambda: None,
        front_mm: Callable[[], int | None] = lambda: None,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.book = book
        self.eyes = eyes
        self.odometer = odometer
        self.tilt = tilt
        self.front_mm = front_mm
        self.monotonic = monotonic
        self.animal_at = -math.inf
        self._noted: dict[str, float] = {}
        self._last_sight: float | None = None

    def sight(self) -> Sight | None:
        if not getattr(self.eyes, "available", False):
            return None
        return self.eyes.latest(SIGHT_AGE_S)

    def animal_near(self) -> bool:
        sight = self.sight()
        if sight is not None and any(t.animal and t.score >= THING_SCORE for t in sight.things):
            self.animal_at = self.monotonic()
        return self.monotonic() - self.animal_at <= ANIMAL_NEAR_S

    def in_view(self) -> list[str]:
        sight = self.sight()
        if sight is None:
            return []
        ranked = sorted((t for t in sight.things if t.score >= THING_SCORE), key=lambda t: (not t.animal, -t.width_frac * t.height_frac))
        return list(dict.fromkeys(spoken(t.label) for t in ranked))

    def place(self, angle: float, gap: float) -> tuple[float | None, float | None]:
        odometer = self.odometer
        if odometer is None or not getattr(odometer, "usable", False):
            return None, None
        x, y, heading = odometer.pose()
        reach = gap + 0.1
        aim = math.radians(heading + angle)
        return x + reach * math.cos(aim), y + reach * math.sin(aim)

    def look(self) -> list[Sighting]:
        sight = self.sight()
        if sight is None or not sight.things or sight.at == self._last_sight:
            return []
        self._last_sight = sight.at
        mono = self.monotonic()
        found = []
        things = [t for t in sight.things if t.score >= THING_SCORE]
        for thing in things:
            if thing.animal:
                self.animal_at = mono
            if mono - self._noted.get(thing.label, -math.inf) < NOTE_EVERY_S:
                continue
            self._noted[thing.label] = mono
            angle = body_bearing(thing.bearing_deg, sight.camera)
            gap = thing_gap_m(thing, sight, self.tilt(), self.front_mm())
            x, y = self.place(angle, gap)
            others = [o for o in things if o is not thing and abs(body_bearing(o.bearing_deg, sight.camera) - angle) <= NEAR_DEG]
            others.sort(key=lambda o: (canonical(o.label) not in LANDMARKS, o.lane != "slow", -o.width_frac))
            near = [o.label for o in others if not o.animal]
            noted = self.book.note(thing.label, thing.at, sight.camera, x, y, round(gap, 2), near, thing.score, thing.lane, thing.animal)
            if noted.new_kind and thing.score >= NOVEL_SCORE:
                found.append(Sighting(thing.label, "new", thing.animal, where_words(angle)))
            elif noted.new_place and not noted.animal:
                found.append(Sighting(thing.label, "moved", thing.animal, where_words(angle)))
        return found
