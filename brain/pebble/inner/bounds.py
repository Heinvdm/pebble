import math


def bounded(value: float, low: float, high: float, fallback: float | None = None) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return low if fallback is None else fallback
    return max(low, min(high, float(value)))
