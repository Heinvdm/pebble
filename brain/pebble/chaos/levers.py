from dataclasses import dataclass

from .dial import clamp_level

SPREAD_MIN, SPREAD_MAX = 0.6, 1.8
NOVELTY_MAX = 0.12
TOP_K_RANGE = (2, 4)
CREATIVE_TEMPERATURE = (0.55, 1.2)
CREATIVE_TOP_P = (0.90, 0.98)
CREATIVE_MIN_P = (0.12, 0.03)
STEADY_TEMPERATURE = 0.3
STEADY_TOP_P = 0.9
STEADY_MIN_P = 0.1
CARD_CHANCE = (0.25, 0.95)
SECOND_CARD_FROM = 7.0
WHIMS_PER_HOUR_AT_TEN = 3.5
WHIMS_MAX_PER_HOUR = 4
WHIM_MIN_GAP_S = 600.0
WHIM_SPIN_POWER = 0.3
GAZE_WANDER = (0.3, 2.5)
SWAY = (0.0, 1.2)
BLINK_JITTER = (0.1, 0.6)
NOISE_SPEED = (0.3, 1.2)
WHEEL_NOISE_CAP = 0.08
MUTATION_MAX_TWEAKS = 3


def _along(level: float, span: tuple[float, float]) -> float:
    t = clamp_level(level) / 10.0
    value = span[0] + (span[1] - span[0]) * t
    return max(min(span), min(max(span), value))


@dataclass(frozen=True)
class ChoiceKnobs:
    spread: float
    novelty: float
    top_k: int


@dataclass(frozen=True)
class WordKnobs:
    temperature: float
    top_p: float
    min_p: float


@dataclass(frozen=True)
class MotionKnobs:
    gaze: float
    sway: float
    blink: float
    speed: float
    wheel: float

    def as_dict(self) -> dict:
        return {name: round(getattr(self, name), 3) for name in ("gaze", "sway", "blink", "speed", "wheel")}


def choice_knobs(level: float) -> ChoiceKnobs:
    level = clamp_level(level)
    top_k = 2 if level < 3 else (3 if level < 7 else 4)
    return ChoiceKnobs(_along(level, (SPREAD_MIN, SPREAD_MAX)), _along(level, (0.0, NOVELTY_MAX)), top_k)


def creative_words(level: float) -> WordKnobs:
    return WordKnobs(_along(level, CREATIVE_TEMPERATURE), _along(level, CREATIVE_TOP_P), _along(level, CREATIVE_MIN_P))


def steady_words() -> WordKnobs:
    return WordKnobs(STEADY_TEMPERATURE, STEADY_TOP_P, STEADY_MIN_P)


def card_chance(level: float) -> float:
    return _along(level, CARD_CHANCE)


def second_card_chance(level: float) -> float:
    level = clamp_level(level)
    return 0.0 if level < SECOND_CARD_FROM else min(1.0, (level - SECOND_CARD_FROM + 1.0) / 4.0)


def whims_per_hour(level: float) -> float:
    return min(float(WHIMS_MAX_PER_HOUR), _along(level, (0.0, WHIMS_PER_HOUR_AT_TEN)))


def motion_knobs(level: float) -> MotionKnobs:
    return MotionKnobs(
        _along(level, GAZE_WANDER),
        _along(level, SWAY),
        _along(level, BLINK_JITTER),
        _along(level, NOISE_SPEED),
        min(WHEEL_NOISE_CAP, _along(level, (0.0, WHEEL_NOISE_CAP))),
    )


def mutation_tweaks(level: float) -> int:
    return max(1, min(MUTATION_MAX_TWEAKS, 1 + int(clamp_level(level) // 4)))


def mutation_jitter(level: float) -> int:
    return 2 if clamp_level(level) >= 6 else 1


def dream_allowed(night: bool, docked: bool) -> bool:
    return bool(night and docked)
