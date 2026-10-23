import math

RESTING = {"newborn": 0.5, "child": 0.4, "teen": 0.3, "adult": 0.2}
SETTLE_S = 2 * 3600.0
RISE = {"surprise": 0.05, "place": 0.1, "feedback": 0.04}
UNMET_AT = 0.6
UNMET_PER_MIN = 0.01
STEP = (0.02, 0.12)
EVIDENCE = (1.0, 0.25)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class Plasticity:
    def __init__(self, level: float | None = None, stage: str = "adult"):
        self.level = _clamp(level) if _number(level) else RESTING.get(stage, RESTING["adult"])

    def tick(self, dt: float, stage: str, unmet: float = 0.0) -> None:
        resting = RESTING.get(stage, RESTING["adult"])
        dt = max(0.0, float(dt)) if _number(dt) else 0.0
        self.level = resting + (self.level - resting) * 0.5 ** (dt / SETTLE_S)
        if _number(unmet) and unmet > UNMET_AT:
            self.level += (unmet - UNMET_AT) / (1.0 - UNMET_AT) * UNMET_PER_MIN * dt / 60.0
        self.level = _clamp(self.level)

    def rise(self, kind: str) -> None:
        self.level = _clamp(self.level + RISE.get(kind, 0.0))

    def step(self, span: float) -> float:
        low, high = STEP
        return abs(span) * (low + (high - low) * self.level)

    def evidence(self, base: int) -> int:
        share = EVIDENCE[0] + (EVIDENCE[1] - EVIDENCE[0]) * self.level
        return max(1, round(base * share))
