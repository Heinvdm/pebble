from ..mind.base import CallOptions
from .levers import creative_words, steady_words

CREATIVE_KINDS = frozenset({"talk", "joke", "drawing"})
STEADY_KINDS = frozenset({"tool", "safety", "summary", "job"})
SEED_BITS = 31


def is_creative(kind: str) -> bool:
    return kind in CREATIVE_KINDS


def call_options(kind: str, level: float, seed: int | None = None) -> CallOptions:
    if is_creative(kind):
        words = creative_words(level)
        return CallOptions("creative", round(words.temperature, 3), round(words.top_p, 3), round(words.min_p, 3), seed)
    words = steady_words()
    return CallOptions("steady", words.temperature, words.top_p, words.min_p, seed)
