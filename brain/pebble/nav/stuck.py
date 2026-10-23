import math
from collections import deque

NO_MOTION_S = 1.0
BUMP_WINDOW_S = 20.0
BUMP_LIMIT = 3
FLIP_WINDOW_S = 4.0
FLIPS = 6
FLIP_SPAN_M = 0.15
PROGRESS_S = 6.0
PROGRESS_M = 0.15
SLIP_S = 0.6


class StuckWatch:
    def __init__(self):
        self.commanded_since: float | None = None
        self.bumps: deque = deque()
        self.turns: deque = deque()
        self.places: deque = deque()
        self.slip_since: float | None = None
        self.calm_until = -math.inf

    def reset(self, now: float) -> None:
        self.commanded_since = None
        self.bumps.clear()
        self.turns.clear()
        self.places.clear()
        self.slip_since = None
        self.calm_until = now + 1.5

    def bumped(self, now: float) -> None:
        self.bumps.append(now)

    def tick(self, now: float, x: float, y: float, v: float, w: float, speed: float, wheel_rate: float, slipping: bool, trying: bool) -> str | None:
        while self.bumps and now - self.bumps[0] > BUMP_WINDOW_S:
            self.bumps.popleft()
        if now < self.calm_until:
            self.places.clear()
            return None
        if len(self.bumps) >= BUMP_LIMIT:
            return "bumps"
        pushing = abs(v) > 0.03 or abs(w) > 0.5
        moving = abs(speed) > 0.01 or abs(wheel_rate) > 0.1
        if pushing and not moving:
            if self.commanded_since is None:
                self.commanded_since = now
            elif now - self.commanded_since >= NO_MOTION_S:
                return "no_motion"
        else:
            self.commanded_since = None
        if slipping:
            if self.slip_since is None:
                self.slip_since = now
            elif now - self.slip_since >= SLIP_S:
                return "slipping"
        else:
            self.slip_since = None
        if abs(w) > 0.3:
            sign = 1 if w > 0 else -1
            if not self.turns or self.turns[-1][1] != sign:
                self.turns.append((now, sign, x, y))
        while self.turns and now - self.turns[0][0] > FLIP_WINDOW_S:
            self.turns.popleft()
        if len(self.turns) >= FLIPS:
            xs = [t[2] for t in self.turns]
            ys = [t[3] for t in self.turns]
            if max(xs) - min(xs) < FLIP_SPAN_M and max(ys) - min(ys) < FLIP_SPAN_M:
                return "oscillating"
        if trying:
            self.places.append((now, x, y))
            while self.places and now - self.places[0][0] > PROGRESS_S:
                self.places.popleft()
            if self.places and now - self.places[0][0] >= PROGRESS_S * 0.95:
                span = max(math.hypot(px - x, py - y) for _, px, py in self.places)
                if span < PROGRESS_M:
                    return "no_progress"
        else:
            self.places.clear()
        return None
