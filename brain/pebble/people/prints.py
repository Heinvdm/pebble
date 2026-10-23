import math
from dataclasses import dataclass
from typing import Protocol

KINDS = ("voice", "face")
MATCH_AT = 0.82
PER_KIND = 5
PINNED = 2
MIN_DIMS = 4
MAX_DIMS = 2048
DIGITS = 5


def normalise(vector) -> tuple[float, ...] | None:
    try:
        values = [float(v) for v in vector]
    except (TypeError, ValueError):
        return None
    if not MIN_DIMS <= len(values) <= MAX_DIMS or not all(math.isfinite(v) for v in values):
        return None
    length = math.sqrt(sum(v * v for v in values))
    if length == 0.0:
        return None
    return tuple(round(v / length, DIGITS) for v in values)


def similarity(a, b) -> float:
    if len(a) != len(b):
        return -1.0
    return sum(x * y for x, y in zip(a, b))


@dataclass(frozen=True)
class Match:
    person_id: str
    score: float


class Matcher(Protocol):
    def best(self, vector: tuple[float, ...], candidates: dict[str, list[tuple[float, ...]]]) -> Match | None: ...


class CosineMatcher:
    def __init__(self, threshold: float = MATCH_AT):
        self.threshold = threshold

    def best(self, vector: tuple[float, ...], candidates: dict[str, list[tuple[float, ...]]]) -> Match | None:
        found = None
        for person_id, prints in candidates.items():
            for stored in prints:
                score = similarity(vector, stored)
                if score >= self.threshold and (found is None or score > found.score):
                    found = Match(person_id, score)
        return found


class Recogniser(Protocol):
    available: bool

    def voice_print(self, audio) -> list[float] | None: ...

    def face_print(self, image) -> list[float] | None: ...


class NoRecogniser:
    available = False

    def voice_print(self, audio) -> list[float] | None:
        return None

    def face_print(self, image) -> list[float] | None:
        return None
