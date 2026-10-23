import math
from dataclasses import dataclass, field

from .bounds import bounded

MAX_FEAR = 10.0
NERVOUS = 4.0
HALF_LIFE_S = 90.0
RISE_TO_FLOOR_S = 60.0
HABIT_HALF_LIFE_DAYS = 4.0
HABITUATION = 0.35
USED_TO_FACTOR = 0.35
STIMULI = {
    "edge": 4.0,
    "bump": 2.0,
    "drop": 6.0,
    "shake": 3.5,
    "stall": 2.0,
    "overheat": 3.0,
    "loud": 3.0,
    "stranger": 1.5,
}


@dataclass
class Habit:
    count: float = 0.0
    last_at: float = 0.0


def battery_unease(percent: float | None) -> float:
    if percent is None or not math.isfinite(percent) or percent >= 25:
        return 0.0
    return min(NERVOUS, (25.0 - max(0.0, percent)) / 20.0 * NERVOUS)


def _label(level: float) -> str:
    if level < 2:
        return "calm"
    if level < 4:
        return "wary"
    if level < 6:
        return "nervous"
    if level < 8:
        return "scared"
    return "frightened"


@dataclass
class Fear:
    level: float = 0.0
    habits: dict = field(default_factory=dict)

    def familiarity(self, kind: str, now: float) -> float:
        habit = self.habits.get(kind)
        if habit is None:
            return 0.0
        days = max(0.0, now - habit.last_at) / 86400.0
        return habit.count * 0.5 ** (days / HABIT_HALF_LIFE_DAYS)

    def factor(self, kind: str, now: float, getting_used: float = 1.0) -> float:
        return 1.0 / (1.0 + HABITUATION * bounded(getting_used, 0.0, 4.0, 1.0) * self.familiarity(kind, now))

    def stimulus(self, kind: str, now: float, scale: float = 1.0, startle: float = 1.0, getting_used: float = 1.0) -> tuple[float, bool]:
        base = STIMULI.get(kind)
        if base is None:
            return 0.0, False
        was_used_to = self.factor(kind, now, getting_used) <= USED_TO_FACTOR
        rise = base * bounded(scale, 0.0, 3.0, 1.0) * bounded(startle, 0.0, 3.0, 1.0) * self.factor(kind, now, getting_used)
        self.level = bounded(self.level + rise, 0.0, MAX_FEAR)
        self.habits[kind] = Habit(self.familiarity(kind, now) + 1.0, now)
        became_used_to = not was_used_to and self.factor(kind, now, getting_used) <= USED_TO_FACTOR
        return rise, became_used_to

    def tick(self, dt: float, floor: float = 0.0, comfort: bool = False) -> None:
        dt = bounded(dt, 0.0, 86400.0)
        floor = bounded(floor, 0.0, NERVOUS)
        if self.level > floor:
            half = HALF_LIFE_S / (3.0 if comfort else 1.0)
            self.level = floor + (self.level - floor) * 0.5 ** (dt / half)
        else:
            self.level += (floor - self.level) * (1.0 - math.exp(-dt / RISE_TO_FLOOR_S))
        self.level = bounded(self.level, 0.0, MAX_FEAR)

    def soothe(self, amount: float) -> None:
        self.level = bounded(self.level - bounded(amount, 0.0, MAX_FEAR, 0.0), 0.0, MAX_FEAR)

    def label(self) -> str:
        return _label(self.level)

    def as_dict(self) -> dict:
        return {
            "level": round(self.level, 3),
            "habits": {kind: {"count": round(h.count, 3), "last_at": h.last_at} for kind, h in self.habits.items()},
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "Fear":
        data = data or {}
        habits = {}
        for kind, raw in (data.get("habits") or {}).items():
            try:
                habits[str(kind)] = Habit(max(0.0, float(raw.get("count", 0))), float(raw.get("last_at", 0)))
            except (TypeError, ValueError, AttributeError):
                continue
        return cls(bounded(data.get("level", 0.0), 0.0, MAX_FEAR, 0.0), habits)
