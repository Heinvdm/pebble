import math
from dataclasses import dataclass

from .bounds import bounded

NEED_NAMES = ("energy", "curiosity", "social", "rest")
DEFAULTS = {"energy": 0.8, "curiosity": 0.3, "social": 0.3, "rest": 0.2}
ENERGY_FOLLOW_S = 30.0


@dataclass(frozen=True)
class NeedRates:
    curiosity_per_hour: float = 0.12
    social_per_hour: float = 0.10
    rest_day_per_hour: float = 0.04
    rest_night_per_hour: float = 0.18
    rest_resting_per_hour: float = -0.35
    rest_asleep_per_hour: float = -0.6


@dataclass(frozen=True)
class NeedContext:
    energy_level: float | None = None
    novelty: bool = False
    company: bool = False
    awake: bool = True
    resting: bool = False
    night: bool = False


@dataclass
class Needs:
    energy: float = DEFAULTS["energy"]
    curiosity: float = DEFAULTS["curiosity"]
    social: float = DEFAULTS["social"]
    rest: float = DEFAULTS["rest"]

    def tick(self, dt: float, ctx: NeedContext, rates: NeedRates = NeedRates()) -> None:
        dt = bounded(dt, 0.0, 3600.0)
        hours = dt / 3600.0
        if ctx.energy_level is not None:
            alpha = 1.0 - math.exp(-dt / ENERGY_FOLLOW_S)
            target = bounded(ctx.energy_level, 0.0, 1.0, self.energy)
            self.energy += (target - self.energy) * alpha
        if not ctx.novelty:
            self.curiosity += rates.curiosity_per_hour * hours
        if not ctx.company:
            self.social += rates.social_per_hour * hours
        if not ctx.awake:
            self.rest += rates.rest_asleep_per_hour * hours
        elif ctx.resting:
            self.rest += rates.rest_resting_per_hour * hours
        else:
            self.rest += (rates.rest_night_per_hour if ctx.night else rates.rest_day_per_hour) * hours
        self._clamp()

    def satisfy(self, name: str, amount: float) -> None:
        if name in ("curiosity", "social", "rest"):
            setattr(self, name, getattr(self, name) - amount)
            self._clamp()

    def urgency(self, name: str) -> float:
        if name == "energy":
            return 1.0 - self.energy
        return getattr(self, name, 0.0)

    def _clamp(self) -> None:
        for name in NEED_NAMES:
            setattr(self, name, bounded(getattr(self, name), 0.0, 1.0, DEFAULTS[name]))

    def as_dict(self) -> dict:
        return {name: round(getattr(self, name), 4) for name in NEED_NAMES}

    def as_percent(self) -> dict:
        return {name: round(getattr(self, name) * 100) for name in NEED_NAMES}

    @classmethod
    def from_dict(cls, data: dict | None) -> "Needs":
        data = data or {}
        needs = cls(**{name: data.get(name, DEFAULTS[name]) for name in NEED_NAMES})
        needs._clamp()
        return needs
