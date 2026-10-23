import math

RUN_GAP_M = 0.25
MIN_POINTS = 6
MIN_LENGTH_M = 0.6
MAX_RMS_M = 0.06
SNAP_RAD = math.radians(4.0)
GAIN = 0.08
LEARN_VOTES = 8
LEARN_DRIFT_M = 0.35
QUARTER = math.pi / 2.0


def fold(angle: float) -> float:
    return (angle + QUARTER / 2.0) % QUARTER - QUARTER / 2.0


def fit(points: list[tuple[float, float]]) -> tuple[float, float, float] | None:
    n = len(points)
    if n < MIN_POINTS:
        return None
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mx) ** 2 for p in points)
    syy = sum((p[1] - my) ** 2 for p in points)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in points)
    angle = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    c, s = math.cos(angle), math.sin(angle)
    along = [(p[0] - mx) * c + (p[1] - my) * s for p in points]
    across = [-(p[0] - mx) * s + (p[1] - my) * c for p in points]
    length = max(along) - min(along)
    rms = math.sqrt(sum(a * a for a in across) / n)
    if length < MIN_LENGTH_M or rms > MAX_RMS_M:
        return None
    return angle, length, rms


def lines(points: list[tuple[float, float]]) -> list[tuple[float, float, float]]:
    out = []
    run: list[tuple[float, float]] = []
    for point in points + [None]:
        if point is not None and (not run or math.hypot(point[0] - run[-1][0], point[1] - run[-1][1]) <= RUN_GAP_M):
            run.append(point)
            continue
        found = fit(run)
        if found is not None:
            out.append(found)
        run = [point] if point is not None else []
    return out


class Axis:
    def __init__(self):
        self.angle: float | None = None
        self.votes = 0
        self.corrections = 0
        self.sum_c = 0.0
        self.sum_s = 0.0

    def reset(self) -> None:
        self.angle = None
        self.votes = 0
        self.sum_c = self.sum_s = 0.0

    def _learn(self, angle: float, weight: float) -> None:
        self.sum_c += weight * math.cos(4.0 * angle)
        self.sum_s += weight * math.sin(4.0 * angle)
        self.votes += 1
        if self.votes >= LEARN_VOTES:
            self.angle = fold(math.atan2(self.sum_s, self.sum_c) / 4.0)

    def offer(self, found: list[tuple[float, float, float]], drift_m: float) -> float | None:
        if not found:
            return None
        angle, length, _ = max(found, key=lambda item: item[1])
        if self.angle is None:
            if drift_m <= LEARN_DRIFT_M:
                self._learn(angle, length)
            return None
        delta = fold(angle - self.angle)
        if abs(delta) > SNAP_RAD:
            return None
        self.corrections += 1
        return -delta * GAIN
