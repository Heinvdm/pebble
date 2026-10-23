import math
from dataclasses import dataclass

from .geometry import BODY_CENTRE_M, BODY_RADIUS_M, TRACK_M, wrap
from .grid import Clearance

HORIZON_S = 1.6
STEP_S = 0.1
WINDOW_S = 0.35
V_SAMPLES = 7
W_SAMPLES = 13
BRAKE = 0.5
LATENCY_S = 0.2
EASE_V = 0.04
EASE_K = 0.6
SAFE_M = 0.03
WANT_CLEAR_M = 0.30
PURSUE = 0.6
HUG_M = 0.2
HUG = 1.2
SQUEEZE_SLACK_M = 0.03
ARRIVE_SLACK_M = 0.02


@dataclass(frozen=True)
class Limits:
    v_max: float
    wheel_max: float
    v_back: float = 0.05
    w_max: float = 2.6
    accel: float = 0.7
    turn_accel: float = 6.0


@dataclass(frozen=True)
class Choice:
    v: float
    w: float
    clear_m: float
    free_m: float
    blocked: bool
    score: float = 0.0


def wheels_ok(v: float, w: float, wheel_max: float) -> bool:
    return abs(v) + abs(w) * TRACK_M / 2.0 <= wheel_max + 1e-9


def roll(x: float, y: float, th: float, v: float, w: float, seconds: float, step: float = STEP_S):
    points = []
    t = 0.0
    while t < seconds - 1e-9:
        t += step
        if abs(w) < 1e-6:
            px, py, pth = x + v * t * math.cos(th), y + v * t * math.sin(th), th
        else:
            r = v / w
            pth = th + w * t
            px = x + r * (math.sin(pth) - math.sin(th))
            py = y - r * (math.cos(pth) - math.cos(th))
        points.append((px, py, pth, abs(v) * t))
    return points


def spread(low: float, high: float, n: int) -> list[float]:
    if high - low < 1e-6 or n <= 1:
        return [low]
    return [low + (high - low) * i / (n - 1) for i in range(n)]


class LocalPlanner:
    def __init__(self, radius: float = BODY_RADIUS_M, safe: float = SAFE_M):
        self.radius = radius
        self.safe = safe

    def free_along(self, clearance: Clearance, x: float, y: float, th: float, v: float, w: float, seconds: float) -> tuple[float, float]:
        if abs(v) < 1e-9 and self.here(clearance, x, y, th) >= self.radius + self.safe * 0.5:
            return math.inf, self.here(clearance, x, y, th)
        least = clearance.cap
        offset = BODY_CENTRE_M if v >= 0 else -BODY_CENTRE_M
        limit = self.radius + self.safe * 0.5
        start = clearance.at(x + offset * math.cos(th), y + offset * math.sin(th))
        if start < limit:
            limit = max(0.0, start - SQUEEZE_SLACK_M)
        for px, py, pth, s in roll(x, y, th, v, w, seconds):
            cx, cy = px + offset * math.cos(pth), py + offset * math.sin(pth)
            room = clearance.at(cx, cy)
            if room < least:
                least = room
            if room < limit:
                return s, least
            if room > limit and limit < self.radius:
                limit = min(self.radius + self.safe * 0.5, room)
        return math.inf, least

    def here(self, clearance: Clearance, x: float, y: float, th: float) -> float:
        return clearance.at(x + BODY_CENTRE_M * math.cos(th), y + BODY_CENTRE_M * math.sin(th))

    def choose(self, clearance: Clearance, x: float, y: float, th: float, v0: float, w0: float, goal: tuple[float, float] | None, limits: Limits, arrive_m: float = 0.0, face: float | None = None, want_clear: float = WANT_CLEAR_M) -> Choice:
        v_low = max(-limits.v_back, v0 - limits.accel * WINDOW_S)
        v_high = min(limits.v_max, v0 + limits.accel * WINDOW_S)
        if v_high < v_low:
            v_high = v_low
        w_low = max(-limits.w_max, w0 - limits.turn_accel * WINDOW_S)
        w_high = min(limits.w_max, w0 + limits.turn_accel * WINDOW_S)
        vs = sorted(set(spread(v_low, v_high, V_SAMPLES) + ([0.0] if v_low <= 0.0 <= v_high else [])))
        ws = sorted(set(spread(w_low, w_high, W_SAMPLES) + ([0.0] if w_low <= 0.0 <= w_high else [])))
        if goal is not None:
            gx, gy = goal
            start_gap = math.hypot(gx - x, gy - y)
            aim = math.atan2(gy - y, gx - x)
        else:
            start_gap = 0.0
            aim = th if face is None else face
        if face is not None:
            aim = face
        best: Choice | None = None
        reach = max(0.05, limits.v_max * HORIZON_S)
        for v in vs:
            for w in ws:
                if not wheels_ok(v, w, limits.wheel_max):
                    continue
                free, least = self.free_along(clearance, x, y, th, v, w, HORIZON_S)
                travel = abs(v) * HORIZON_S
                if free < math.inf:
                    room = free - self.safe
                    if room <= 0.0 and abs(v) > 1e-3:
                        continue
                    if abs(v) * LATENCY_S + v * v / (2.0 * BRAKE) > max(0.0, room) and abs(v) > 1e-3:
                        continue
                    if abs(v) > EASE_V + EASE_K * room:
                        continue
                if abs(v) < 1e-3 and self.here(clearance, x, y, th) < self.radius:
                    least = self.here(clearance, x, y, th)
                end = roll(x, y, th, v, w, HORIZON_S)[-1]
                ex, ey, eth, _ = end
                if goal is not None:
                    gap = math.hypot(gx - ex, gy - ey)
                    progress = (start_gap - gap) / reach
                    if arrive_m > 0.0 and start_gap <= arrive_m + ARRIVE_SLACK_M:
                        progress = -abs(v) * 2.0
                    turn_to = math.cos(wrap(math.atan2(gy - ey, gx - ex) - eth)) if gap > 0.05 else 1.0
                else:
                    progress = 0.0
                    turn_to = math.cos(wrap(aim - eth))
                if face is not None:
                    turn_to = math.cos(wrap(face - eth))
                clear = min(least, want_clear) / want_clear
                speed = v / max(1e-3, limits.v_max)
                smooth = abs(w - w0) / max(1e-3, limits.w_max)
                back = 0.6 if v < 0 else 0.0
                pursue = 0.0
                if goal is not None and face is None and v > 0.02 and start_gap > 0.05:
                    alpha = wrap(aim - th)
                    curve = 2.0 * v * math.sin(alpha) / max(0.3, start_gap)
                    pursue = abs(w - curve) / max(1e-3, limits.w_max)
                hug = max(0.0, HUG_M - least) / HUG_M
                score = 3.0 * progress + 0.9 * turn_to + 0.8 * clear + 0.35 * speed - 0.15 * smooth - back - PURSUE * pursue - HUG * hug
                if best is None or score > best.score:
                    best = Choice(v, w, least, free, False, score)
        if best is None:
            return Choice(0.0, 0.0, self.here(clearance, x, y, th), 0.0, True, -math.inf)
        return best
