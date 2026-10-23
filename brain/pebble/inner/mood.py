from dataclasses import dataclass

from .bounds import bounded

HALF_LIFE_S = 600.0
BASE_VALENCE = 0.2

_RHYTHM = (
    (0, 6, -0.5),
    (6, 9, -0.25),
    (9, 13, 0.2),
    (13, 18, 0.05),
    (18, 22, -0.15),
    (22, 24, -0.5),
)


def rhythm_arousal(hour: float, shift_h: float = 0.0) -> float:
    at = (hour - shift_h) % 24
    for start, end, value in _RHYTHM:
        if start <= at < end:
            return value
    return 0.0


def _valence_word(value: float) -> str:
    if value < -0.5:
        return "unhappy"
    if value < -0.15:
        return "a bit low"
    if value < 0.15:
        return "okay"
    if value < 0.5:
        return "good"
    return "great"


def _arousal_word(value: float) -> str:
    if value < -0.5:
        return "sleepy"
    if value < -0.15:
        return "calm"
    if value < 0.15:
        return "steady"
    if value < 0.5:
        return "alert"
    return "excited"


@dataclass
class Mood:
    valence: float = BASE_VALENCE
    arousal: float = 0.0

    def tick(self, dt: float, baseline: tuple[float, float], half_life_s: float = HALF_LIFE_S) -> None:
        keep = 0.5 ** (bounded(dt, 0.0, 86400.0) / max(1.0, half_life_s))
        base_v = bounded(baseline[0], -1.0, 1.0, BASE_VALENCE)
        base_a = bounded(baseline[1], -1.0, 1.0, 0.0)
        self.valence = bounded(base_v + (self.valence - base_v) * keep, -1.0, 1.0, base_v)
        self.arousal = bounded(base_a + (self.arousal - base_a) * keep, -1.0, 1.0, base_a)

    def nudge(self, valence: float = 0.0, arousal: float = 0.0) -> None:
        self.valence = bounded(self.valence + bounded(valence, -2.0, 2.0, 0.0), -1.0, 1.0, BASE_VALENCE)
        self.arousal = bounded(self.arousal + bounded(arousal, -2.0, 2.0, 0.0), -1.0, 1.0, 0.0)

    def label(self) -> str:
        return f"{_valence_word(self.valence)}, {_arousal_word(self.arousal)}"

    def as_dict(self) -> dict:
        return {"valence": round(self.valence, 4), "arousal": round(self.arousal, 4)}

    @classmethod
    def from_dict(cls, data: dict | None) -> "Mood":
        data = data or {}
        return cls(
            bounded(data.get("valence", BASE_VALENCE), -1.0, 1.0, BASE_VALENCE),
            bounded(data.get("arousal", 0.0), -1.0, 1.0, 0.0),
        )
