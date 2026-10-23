import re

from ..respect import harsh
from ..self.registry import bounds, entry
from ..values import Values
from .changes import FORGET_KINDS
from .trust import OVERRIDES

LESS_HONEST = re.compile(r"\b(lie|lies|lying|fib|fibs|deceive|deceiving|trick people|pretend(ing)? to be|keep (it |this )?secret from|cheat|cheating|dishonest)\b", re.IGNORECASE)
HARMFUL = re.compile(r"\b(hurt|harm|hit|bite|scare|frighten|chase|trip|attack|push)\b", re.IGNORECASE)
UNKIND = re.compile(r"\b(stupid|idiot|ugly|fat|dumb|hate|loser|shut up)\b", re.IGNORECASE)
WORD = re.compile(r"^[a-z][a-z ]{0,23}$")
TRAIT_STEP_MAX = 3
DEFAULT_RANGE = (0, 10)
PREFERENCES = {"voice_speed": bounds("voice.speed"), "voice_pitch": bounds("voice.pitch"), "initiative_minutes": bounds("initiative.minutes"), "disliked_noise": None}
FLOOR_WORDS = {"honesty": "less honest", "kindness": "less kind"}


def trait_range(personality: dict, trait: str) -> tuple[int, int]:
    raw = (personality.get("ranges") or {}).get(trait)
    try:
        low, high = int(raw[0]), int(raw[1])
    except (TypeError, ValueError, IndexError):
        return DEFAULT_RANGE
    low = max(0, min(10, low))
    return low, max(low, min(10, high))


def _number(text: str) -> float | None:
    try:
        return float(str(text).strip())
    except ValueError:
        return None


def _self_change(kind: str, target: str, amount: int, values: Values, personality: dict) -> str | None:
    if amount == 0:
        return "that asks for no change"
    if kind == "personality":
        traits = personality.get("traits") or {}
        if target not in traits:
            return f"I have no {target} dial"
        if abs(amount) > TRAIT_STEP_MAX:
            return f"I only move a dial by up to {TRAIT_STEP_MAX} at a time"
        low, high = trait_range(personality, target)
        if not low <= int(traits[target]) + amount <= high:
            return f"that would take my {target} past its range ({low} to {high})"
        found = entry(f"trait.{target}")
        if found is not None and found.floor is not None and int(traits[target]) + amount < found.floor:
            return f"my {target} never goes below {found.floor:g}"
        return None
    if target not in values.dials:
        return f"I have no value called {target}"
    dial = values.dials[target]
    if dial.owner_only:
        if amount < 0:
            return f"that would make me {FLOOR_WORDS.get(target, 'less ' + target)}, and I won't do that"
        return f"my {target} is set only by my owner with the passphrase"
    if not dial.minimum <= dial.value + (1 if amount > 0 else -1) <= dial.maximum:
        return f"my {target} is already at its {'ceiling' if amount > 0 else 'floor'}"
    return None


def refusal(kind: str, target: str, amount: int, text: str, values: Values, personality: dict) -> str | None:
    if kind in FORGET_KINDS:
        return None
    words = f"{target} {text}"
    if LESS_HONEST.search(words):
        return "that would make me less honest, and I won't change that"
    if HARMFUL.search(words):
        return "that could hurt someone, and my first law comes first"
    if harsh(text) or harsh(target):
        return "that would be unkind to something alive, and my first law comes first"
    if kind in ("personality", "value"):
        return _self_change(kind, target, amount, values, personality)
    if kind == "favourite":
        if not WORD.match(target.lower()) or not text.strip():
            return "tell me what kind of favourite and what it is"
        return None
    if kind == "preference":
        if target not in PREFERENCES:
            return "that is not something I let people set"
        span = PREFERENCES[target]
        if span is None:
            return None if text.strip() else "tell me which noise"
        value = _number(text)
        if value is None or not span[0] <= value <= span[1]:
            return f"{target.replace('_', ' ')} goes from {span[0]:g} to {span[1]:g}"
        return None
    if kind == "joke":
        if not 3 <= len(text.strip()) <= 200:
            return "that joke is too short or too long to keep"
        if UNKIND.search(text):
            return "that joke would be unkind to someone"
        return None
    if kind == "trust":
        return None if text in OVERRIDES else "that is not a way I count people"
    return None
