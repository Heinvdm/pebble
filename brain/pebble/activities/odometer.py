import math

from ..body.api import Body
from ..link.protocol import Status

DOCKED_X_M = 0.08


class Odometer:
    def __init__(self, cpm: float, track_mm: float):
        self.cpm = cpm
        self.track_m = track_mm / 1000.0
        self.x = DOCKED_X_M
        self.y = 0.0
        self.heading = 0.0
        self.known = False
        self.travelled_m = 0.0
        self._last: tuple[int, int] | None = None

    @classmethod
    def for_body(cls, body: Body) -> "Odometer":
        return cls(body.profile.cpm, body.profile.wheel_track_mm)

    @property
    def usable(self) -> bool:
        return self.known and self.cpm > 0

    def reset(self, x: float, y: float, heading_rad: float) -> None:
        self.x, self.y, self.heading = x, y, heading_rad
        self.known = True
        self.travelled_m = 0.0

    def relocate(self, x: float, y: float, heading_deg: float) -> None:
        self.x, self.y, self.heading = x, y, math.radians(heading_deg)
        self.known = True
        self.travelled_m = 0.0

    def anchor(self, x: float, y: float, weight: float) -> None:
        if not self.usable:
            return
        weight = max(0.0, min(1.0, weight))
        self.x += weight * (x - self.x)
        self.y += weight * (y - self.y)
        self.travelled_m *= 1.0 - weight

    def pose(self) -> tuple[float, float, float]:
        return self.x, self.y, math.degrees(self.heading)

    def update(self, status: Status) -> None:
        counts = (status.enc_left, status.enc_right)
        if status.dock == 1:
            self.reset(DOCKED_X_M, 0.0, 0.0)
            self._last = counts
            return
        last, self._last = self._last, counts
        if last is None or self.cpm <= 0:
            return
        left = (counts[0] - last[0]) / self.cpm / 1000.0
        right = (counts[1] - last[1]) / self.cpm / 1000.0
        if abs(left) > 0.5 or abs(right) > 0.5:
            return
        distance = (left + right) / 2.0
        turn = (right - left) / self.track_m
        middle = self.heading + turn / 2.0
        self.x += distance * math.cos(middle)
        self.y += distance * math.sin(middle)
        self.heading = (self.heading + turn + math.pi) % (2 * math.pi) - math.pi
        self.travelled_m += abs(distance)

    async def run(self, body: Body) -> None:
        queue = body.link.subscribe((Status,))
        try:
            while True:
                self.update(await queue.get())
        finally:
            body.link.unsubscribe(queue)
