import math
from dataclasses import dataclass

LOW = 0.0
HIGH = 10.0
DEFAULT_PLAYFULNESS = 5
YOUTH = {"newborn": 1.5, "child": 2.0, "teen": 0.75, "adult": 0.0}
QUIET_FACTOR = 0.4
QUIET_CAP = 2.5
MOOD_WEIGHT = (0.5, 1.5)


@dataclass(frozen=True)
class DialInputs:
    playfulness: float = DEFAULT_PLAYFULNESS
    valence: float = 0.0
    arousal: float = 0.0
    stage: str = "adult"
    quiet: bool = False
    fear: float = 0.0
    pinned: float | None = None
    mood_weight: float = 1.0


def _finite(value, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def clamp_level(value) -> float:
    return max(LOW, min(HIGH, _finite(value, LOW)))


def parts(inputs: DialInputs) -> dict:
    playfulness = max(0.0, min(10.0, _finite(inputs.playfulness, DEFAULT_PLAYFULNESS)))
    valence = max(-1.0, min(1.0, _finite(inputs.valence, 0.0)))
    arousal = max(-1.0, min(1.0, _finite(inputs.arousal, 0.0)))
    fear = max(0.0, min(10.0, _finite(inputs.fear, 0.0)))
    weight = max(MOOD_WEIGHT[0], min(MOOD_WEIGHT[1], _finite(inputs.mood_weight, 1.0)))
    return {
        "playfulness": 1.0 + 0.6 * playfulness,
        "mood": weight * (1.5 * arousal + 1.0 * valence),
        "youth": YOUTH.get(inputs.stage, 0.0),
        "fear": -0.4 * fear,
    }


def dial_level(inputs: DialInputs) -> float:
    if inputs.pinned is not None:
        return clamp_level(inputs.pinned)
    level = sum(parts(inputs).values())
    if inputs.quiet:
        level = min(level * QUIET_FACTOR, QUIET_CAP)
    return clamp_level(level)
