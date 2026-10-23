import time
from typing import Callable

from ..seams.sight import SeenPerson
from .hub import Hub

MIN_GAP_S = 0.1
GAZE_X_DEG = 30.0
GAZE_Y_DEG = 22.0


def gaze_for(bearing_deg: float, elevation_deg: float) -> tuple[float, float]:
    x = max(-1.0, min(1.0, -float(bearing_deg) / GAZE_X_DEG))
    y = max(-1.0, min(1.0, -float(elevation_deg) / GAZE_Y_DEG))
    return x, y


class LookPush:
    def __init__(self, hub: Hub, min_gap_s: float = MIN_GAP_S, monotonic: Callable[[], float] = time.monotonic):
        self.hub = hub
        self.min_gap_s = min_gap_s
        self.monotonic = monotonic
        self._last = -1e9
        self.sent = 0
        self._camera: str | None = None
        hub.add_replay(self.replay)

    def replay(self) -> list[tuple[str, object]]:
        return [("camera", {"on": self._camera is not None, "camera": self._camera})]

    def camera(self, name: str | None) -> None:
        self._camera = name
        self.hub.publish("camera", {"on": name is not None, "camera": name})

    def __call__(self, person: SeenPerson | None) -> None:
        now = self.monotonic()
        if person is None:
            self.hub.publish("look", {"on": False})
            self._last = -1e9
            self.sent += 1
            return
        if now - self._last < self.min_gap_s:
            return
        self._last = now
        self.sent += 1
        self.hub.publish("look", {"on": True, "bearing_deg": round(person.bearing_deg, 2), "elevation_deg": round(person.elevation_deg, 2), "face": bool(person.face), "track": person.track})
