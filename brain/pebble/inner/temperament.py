from dataclasses import dataclass, replace

from .mood import BASE_VALENCE, HALF_LIFE_S
from .needs import NeedRates

STEADY = frozenset({"edge", "drop"})
MEANT = frozenset({"praise", "touch", "talk", "scold"})


@dataclass(frozen=True)
class Temperament:
    half_life_s: float = HALF_LIFE_S
    resting: float = BASE_VALENCE
    shift_h: float = 0.0
    company: float = 1.0
    curiosity: float = 1.0
    rest: float = 1.0
    startle: float = 1.0
    getting_used: float = 1.0
    praise: float = 1.0
    touch: float = 1.0
    talk: float = 1.0
    scold: float = 1.0

    def meaning(self, event: str) -> float:
        return max(0.0, float(getattr(self, event))) if event in MEANT else 1.0

    def rates(self) -> NeedRates:
        base = NeedRates()
        return replace(
            base,
            curiosity_per_hour=base.curiosity_per_hour * self.curiosity,
            social_per_hour=base.social_per_hour * self.company,
            rest_day_per_hour=base.rest_day_per_hour * self.rest,
            rest_night_per_hour=base.rest_night_per_hour * self.rest,
        )

    def startle_for(self, kind: str | None) -> float:
        return max(1.0, self.startle) if kind in STEADY else self.startle

    def getting_used_for(self, kind: str | None) -> float:
        return min(1.0, self.getting_used) if kind in STEADY else self.getting_used
