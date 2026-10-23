import math
import random
from dataclasses import dataclass, field

from .goals import Item
from .inner.mood import Mood
from .inner.needs import Needs

TIER_SAFETY = 0
TIER_PEOPLE = 1
TIER_OWN = 2
TOP_K = 3
WEIGHTS = (0.45, 0.3, 0.25)
SOURCE_RANK = {"owner": 0, "person": 1, "self": 2}
OUTRANKED = "outranked by something more pressing"


@dataclass(frozen=True)
class Option:
    key: str
    title: str
    tier: int
    priority: float = 0.5
    serves: tuple[str, ...] = ()
    values: tuple[str, ...] = ()
    risk: float = 0.0
    effort: int = 2
    energy: float = 0.0
    reason: str = ""
    task_id: int | None = None
    source: str = "self"
    created_at: float = 0.0


@dataclass(frozen=True)
class PickContext:
    needs: Needs
    mood: Mood
    fear: float
    values: dict
    failure_streak: int = 0
    weights: tuple = WEIGHTS


@dataclass(frozen=True)
class SafetyContext:
    low_battery: bool = False
    docked: bool = False
    edge_hold: bool = False
    stuck: bool = False
    hot: bool = False
    quiet: bool = False
    fear: float = 0.0


@dataclass(frozen=True)
class Variety:
    spread: float = 1.0
    top_k: int = TOP_K
    novelty: dict = field(default_factory=dict)


@dataclass
class Choice:
    chosen: Option
    score: float
    tier: int
    reasons: list = field(default_factory=list)
    rejected: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "chosen": self.chosen.key,
            "title": self.chosen.title,
            "tier": self.tier,
            "score": round(self.score, 3),
            "reasons": self.reasons,
            "rejected": [{"option": o.key, "score": round(s, 3), "why": why} for o, s, why in self.rejected],
        }


IDLE = (
    Option("explore", "explore somewhere new nearby", TIER_OWN, 0.3, ("curiosity",), ("curiosity",), 0.4, 2, 0.5),
    Option("look_around", "look around from here", TIER_OWN, 0.2, ("curiosity",), ("curiosity", "caution"), 0.0, 1, 0.0),
    Option("seek_company", "go and find someone to be near", TIER_OWN, 0.3, ("social",), ("kindness", "playfulness"), 0.2, 2, 0.3),
    Option("play", "play a little game", TIER_OWN, 0.25, ("social", "curiosity"), ("playfulness",), 0.2, 2, 0.7),
    Option("nap", "have a nap", TIER_OWN, 0.2, ("rest",), ("caution",), 0.0, 1, -0.8),
    Option("tidy", "tidy up its logs and gallery", TIER_OWN, 0.15, (), ("tidiness",), 0.0, 1, -0.2),
    Option("go_to_dock", "go back to the dock", TIER_OWN, 0.2, ("energy",), ("tidiness", "caution"), 0.0, 2, -0.3),
)


def safety_options(ctx: SafetyContext) -> list[Option]:
    options = []
    if ctx.edge_hold:
        options.append(Option("back_away", "back away from the edge", TIER_SAFETY, 1.0, reason="the edge reflex fired"))
    if ctx.stuck:
        options.append(Option("get_unstuck", "back up and turn to get unstuck", TIER_SAFETY, 0.9, reason="a wheel stalled"))
    if ctx.hot:
        options.append(Option("cool_down", "move away from the heat and rest", TIER_SAFETY, 0.85, reason="the phone is hot"))
    if ctx.low_battery and not ctx.docked:
        options.append(Option("dock", "head for the charger", TIER_SAFETY, 0.8, reason="the battery is low"))
    if ctx.quiet:
        options.append(Option("rest_quietly", "stay quiet and rest", TIER_SAFETY, 0.5, reason="quiet hours"))
    return options


def task_options(items: list[Item]) -> list[Option]:
    options = []
    for item in items:
        tier = TIER_OWN if item.source == "self" else TIER_PEOPLE
        options.append(
            Option(
                key=f"task:{item.id}",
                title=item.title,
                tier=tier,
                priority=item.priority / 5.0,
                serves=tuple(item.serves),
                values=(),
                risk=item.risk,
                effort=item.effort,
                energy=0.2,
                reason=item.reason,
                task_id=item.id,
                source=item.source,
                created_at=item.created_at,
            )
        )
    return options


def idle_options() -> list[Option]:
    return list(IDLE)


def score(option: Option, ctx: PickContext) -> tuple[float, dict]:
    need_fit = sum(ctx.needs.urgency(n) for n in option.serves) / len(option.serves) if option.serves else 0.2
    value_fit = sum(ctx.values.get(v, 5) / 10.0 for v in option.values) / len(option.values) if option.values else 0.5
    mood_fit = 1.0 - abs(option.energy - ctx.mood.arousal) / 2.0
    curiosity = ctx.values.get("curiosity", 5) / 10.0
    fear_penalty = (ctx.fear / 10.0) * option.risk * (1.0 - 0.5 * curiosity)
    effort_penalty = 0.08 * (option.effort - 1) * min(ctx.failure_streak, 3)
    need_weight, value_weight, mood_weight = ctx.weights
    fit = need_weight * need_fit + value_weight * value_fit + mood_weight * mood_fit
    total = max(0.01, (0.35 + option.priority) * fit - fear_penalty - effort_penalty)
    parts = {
        "need": round(need_fit, 3),
        "values": round(value_fit, 3),
        "mood": round(mood_fit, 3),
        "fear": round(fear_penalty, 3),
        "effort": round(effort_penalty, 3),
    }
    return total, parts


def temperature(mood: Mood) -> float:
    return 0.08 + 0.12 * (mood.arousal + 1.0) / 2.0 + (0.04 if mood.valence > 0.3 else 0.0)


def pick(options: list[Option], ctx: PickContext, rng: random.Random, top_k: int = TOP_K, variety: Variety | None = None) -> Choice | None:
    if not options:
        return None
    tier = min(o.tier for o in options)
    candidates = [o for o in options if o.tier == tier]
    outranked = [(o, 0.0, OUTRANKED) for o in options if o.tier != tier]
    if tier == TIER_SAFETY:
        ordered = sorted(candidates, key=lambda o: (-o.priority, o.key))
        chosen = ordered[0]
        rejected = [(o, o.priority, "a more urgent safety need came first") for o in ordered[1:]]
        return Choice(chosen, chosen.priority, tier, [f"safety first: {chosen.reason}"], rejected + outranked)
    if tier == TIER_PEOPLE:
        ordered = sorted(candidates, key=lambda o: (SOURCE_RANK.get(o.source, 2), -o.priority, o.created_at, o.key))
        chosen = ordered[0]
        rejected = [(o, o.priority, "another request from people ranks higher") for o in ordered[1:]]
        return Choice(chosen, chosen.priority, tier, [f"asked by {chosen.source}: {chosen.reason}".strip(": ")], rejected + outranked)
    bonus = variety.novelty if variety is not None else {}
    if variety is not None:
        top_k = max(1, variety.top_k)
    scored = []
    for option in candidates:
        total, parts = score(option, ctx)
        extra = max(0.0, float(bonus.get(option.key, 0.0)))
        if extra:
            parts = {**parts, "novelty": round(extra, 3)}
        scored.append(((total + extra, parts), option))
    scored.sort(key=lambda pair: (-pair[0][0], pair[1].key))
    top = scored[:top_k]
    heat = temperature(ctx.mood) * (max(0.05, variety.spread) if variety is not None else 1.0)
    best = top[0][0][0]
    weights = [math.exp((s - best) / heat) for (s, _), _ in top]
    index = rng.choices(range(len(top)), weights=weights, k=1)[0]
    (chosen_score, parts), chosen = top[index]
    rejected = []
    for position, ((s, _), option) in enumerate(scored):
        if option is chosen:
            continue
        why = "lost the weighted draw" if position < top_k else "scored lower"
        rejected.append((option, s, why))
    reasons = [f"fits needs {parts['need']}, values {parts['values']}, mood {parts['mood']}"]
    if parts["fear"] > 0:
        reasons.append(f"fear cost {parts['fear']}")
    if parts.get("novelty"):
        reasons.append(f"not done lately (+{parts['novelty']})")
    if chosen.reason:
        reasons.append(chosen.reason)
    return Choice(chosen, chosen_score, tier, reasons, rejected + outranked)
