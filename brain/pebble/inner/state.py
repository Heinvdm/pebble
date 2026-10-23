from dataclasses import dataclass

from .bounds import bounded
from .fear import Fear, battery_unease
from .mood import Mood, rhythm_arousal
from .needs import NeedContext, Needs
from .temperament import Temperament


@dataclass(frozen=True)
class Effect:
    valence: float = 0.0
    arousal: float = 0.0
    fear: str | None = None
    satisfy: tuple[tuple[str, float], ...] = ()
    soothe: float = 0.0


EFFECTS = {
    "bump": Effect(-0.15, 0.3, "bump"),
    "edge": Effect(-0.1, 0.4, "edge"),
    "stall": Effect(-0.1, 0.2, "stall"),
    "drop": Effect(-0.3, 0.6, "drop"),
    "shake": Effect(-0.15, 0.4, "shake"),
    "overheat": Effect(-0.2, 0.1, "overheat"),
    "loud": Effect(-0.05, 0.3, "loud"),
    "stranger": Effect(0.0, 0.2, "stranger"),
    "lowbat": Effect(-0.1, -0.1),
    "docked": Effect(0.1, -0.1, soothe=2.0),
    "obstacle": Effect(0.0, 0.05, satisfy=(("curiosity", 0.05),)),
    "novelty": Effect(0.05, 0.15, satisfy=(("curiosity", 0.3),)),
    "praise": Effect(0.3, 0.1, satisfy=(("social", 0.3),)),
    "scold": Effect(-0.3, 0.1, satisfy=(("social", 0.1),)),
    "touch": Effect(0.25, -0.05, satisfy=(("social", 0.3),), soothe=2.0),
    "talk": Effect(0.05, 0.1, satisfy=(("social", 0.25),)),
    "task_done": Effect(0.2, 0.1),
    "task_failed": Effect(-0.15, -0.05),
    "celebration": Effect(0.25, 0.2),
}


@dataclass(frozen=True)
class InnerContext:
    now: float
    local_hour: int
    energy_level: float | None = None
    battery_percent: float | None = None
    awake: bool = True
    resting: bool = False
    night: bool = False
    waking: bool = False
    novelty: bool = False
    company: bool = False
    comfort: bool = False
    hot: bool = False
    local_hours: float | None = None


@dataclass(frozen=True)
class EventOutcome:
    effect: Effect | None
    fear_rise: float = 0.0
    became_used_to: str | None = None


class InnerState:
    def __init__(self, needs: Needs | None = None, mood: Mood | None = None, fear: Fear | None = None, temperament: Temperament | None = None):
        self.needs = needs or Needs()
        self.mood = mood or Mood()
        self.fear = fear or Fear()
        self.temperament = temperament or Temperament()

    def on_event(self, name: str, now: float, fear_scale: float = 1.0) -> EventOutcome:
        effect = EFFECTS.get(name)
        if effect is None:
            return EventOutcome(None)
        t = self.temperament
        weight = t.meaning(name)
        self.mood.nudge(effect.valence * weight, effect.arousal * weight)
        for need, amount in effect.satisfy:
            self.needs.satisfy(need, amount * weight)
        if effect.soothe:
            self.fear.soothe(effect.soothe * weight)
        rise, used_to = (0.0, False)
        if effect.fear:
            rise, used_to = self.fear.stimulus(effect.fear, now, fear_scale, t.startle_for(effect.fear), t.getting_used_for(effect.fear))
        return EventOutcome(effect, rise, effect.fear if used_to else None)

    def baseline(self, ctx: InnerContext) -> tuple[float, float]:
        t = self.temperament
        valence = t.resting
        if self.needs.energy < 0.2:
            valence -= 0.25
        if ctx.hot:
            valence -= 0.1
        if self.needs.social > 0.8:
            valence -= 0.1
        arousal = rhythm_arousal(ctx.local_hours if ctx.local_hours is not None else ctx.local_hour, t.shift_h)
        if ctx.waking:
            arousal -= 0.3
        if not ctx.awake:
            arousal -= 0.4
        return bounded(valence, -1.0, 1.0), bounded(arousal, -1.0, 1.0)

    def tick(self, dt: float, ctx: InnerContext) -> None:
        self.needs.tick(
            dt,
            NeedContext(
                energy_level=ctx.energy_level,
                novelty=ctx.novelty,
                company=ctx.company,
                awake=ctx.awake,
                resting=ctx.resting,
                night=ctx.night,
            ),
            self.temperament.rates(),
        )
        self.mood.tick(dt, self.baseline(ctx), self.temperament.half_life_s)
        self.fear.tick(dt, battery_unease(ctx.battery_percent), ctx.comfort)

    def to_dict(self) -> dict:
        return {"needs": self.needs.as_dict(), "mood": self.mood.as_dict(), "fear": self.fear.as_dict()}

    @classmethod
    def from_dict(cls, data: dict | None) -> "InnerState":
        data = data or {}
        return cls(Needs.from_dict(data.get("needs")), Mood.from_dict(data.get("mood")), Fear.from_dict(data.get("fear")))
