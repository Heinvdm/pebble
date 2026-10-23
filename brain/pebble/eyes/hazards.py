import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, replace

from .geometry import Box
from .things import Thing, overlap

log = logging.getLogger(__name__)

EVERY_S = 3.0
CLOSE_EVERY_S = 0.8
CLOSE_FOR_S = 6.0
KEEP_S = 4.0
SERIES = 40
FLICKER_MIN_S = 1.5
WARM_FRACTION = 0.002
WARM_SWING = 0.12
SMALL = (80, 60)
SCREENS = ("tv", "television", "computer monitor", "computer screen", "crt screen", "monitor", "laptop", "screen", "projection screen", "tablet", "tablet computer", "phone", "smartphone", "cell phone")
FIRE_SPOTS = {
    **{name: "tv" for name in SCREENS},
    "fireplace": "fireplace", "wood-burning stove": "fireplace", "fire pit": "fireplace", "candle": "candle", "birthday candle": "candle",
    "candle holder": "candle", "stove burner": "stove burner", "gas stove": "stove burner", "stove": "stove burner", "oven": "oven",
    "lamp": "lamp", "table lamp": "lamp", "bedside lamp": "lamp", "oil lamp": "lamp", "lantern": "lamp", "paper lantern": "lamp",
    "toaster": "toaster", "sunset": "sunset", "heater": "heater", "bath heater": "heater", "radiator": "heater",
}
SAME_BLOB = {"lamp", "sunset", "candle"}
CONTAINED = 0.6
GREW = 2.0
SMALL_SPOTS = {"stove burner", "oven", "toaster", "heater"}
SMALL_FIRE = 0.15
STEAM_AREA = 4.0
STEAM_SPOTS = {
    "kettle", "cup", "mug", "coffee cup", "teacup", "insulated cup", "paper cup", "coffeepot", "tea pot", "pot", "cooking pot", "crock pot",
    "hotpot", "saucepan", "pan", "frying pan", "stove", "gas stove", "stove burner", "oven", "bath", "shower", "shower head", "sink",
    "kitchen sink", "bathroom sink", "iron", "humidifier", "steam", "fog", "bowl",
}


@dataclass
class _Track:
    label: str
    box: Box
    first: float
    last: float
    first_area: float
    first_centre: tuple
    series: deque


class HazardWatch:
    def __init__(self, make_detector, monotonic=time.monotonic, every_s: float = EVERY_S, keep_s: float = KEEP_S, nice: int = 5):
        self.make_detector = make_detector
        self.monotonic = monotonic
        self.every_s = float(every_s)
        self.keep_s = float(keep_s)
        self.nice = int(nice)
        self.detector = None
        self.problem = ""
        self.passes = 0
        self.last_ms = 0.0
        self._cond = threading.Condition()
        self._offer = None
        self._offered = 0
        self._seen = 0
        self._last_pass = -1e9
        self._close_until = -1e9
        self._warm = deque(maxlen=12)
        self._tracks: list[_Track] = []
        self._result: tuple | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._context: list = []

    def start(self) -> None:
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="pebble-eyes-hazards", daemon=True)
            self._thread.start()

    def close(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=10.0)

    def forget(self) -> None:
        with self._cond:
            self._offer = None
        with self._lock:
            self._result = None
            self._tracks = []

    def offer(self, image, camera: str, captured: float, at: float, fov_h_deg: float, context=()) -> None:
        cv2 = self._cv2()
        if cv2 is None:
            return
        small = cv2.resize(image, SMALL, interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        warm = ((hue <= 22) | (hue >= 170)) & (sat >= 110) & (val >= 190)
        value = small.max(axis=2)
        levels = []
        for box in self.fire_boxes():
            x0, y0, x1, y1 = cells(box)
            patch = value[y0:y1, x0:x1]
            if patch.size:
                levels.append((box, float(patch.mean())))
        self.note(captured, float(warm.mean()), levels)
        with self._cond:
            self._offer = (image, camera, captured, at, fov_h_deg)
            self._context = list(context)
            self._offered += 1
            self._cond.notify_all()

    def fire_boxes(self) -> list[Box]:
        with self._lock:
            return [t.box for t in self._tracks if t.label == "fire"]

    def note(self, captured: float, warm: float, levels=()) -> None:
        self._warm.append(float(warm))
        with self._lock:
            tracks = [t for t in self._tracks if t.label == "fire"]
        for box, level in levels:
            track = next((t for t in tracks if t.box is box), None) or max(tracks, key=lambda t: overlap(t.box, box), default=None)
            if track is not None and (track.box is box or overlap(track.box, box) > 0.5):
                track.series.append((captured, float(level)))
        if self._flickering():
            with self._cond:
                self._close_until = max(self._close_until, self.monotonic() + CLOSE_FOR_S)

    def _cv2(self):
        try:
            import cv2

            return cv2
        except ImportError:
            return None

    def _flickering(self) -> bool:
        if len(self._warm) < 6:
            return False
        values = list(self._warm)
        mean = sum(values) / len(values)
        if mean < WARM_FRACTION:
            return False
        swing = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5 / mean
        return swing >= WARM_SWING

    def _run(self) -> None:
        import os

        if self.nice > 0 and hasattr(os, "setpriority"):
            try:
                os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), self.nice)
            except OSError:
                pass
        try:
            self.detector = self.make_detector()
        except Exception as error:
            self.problem = f"the hazard watch is off: {error}"
            log.warning("eyes: %s", self.problem)
            return
        while not self._stop.is_set():
            with self._cond:
                self._cond.wait(timeout=0.25)
                if self._stop.is_set():
                    break
                offer, context = self._offer, list(self._context)
                fresh = self._offered > self._seen
                now = self.monotonic()
                gap = CLOSE_EVERY_S if now < self._close_until else self.every_s
                due = fresh and now - self._last_pass >= gap
                if due:
                    self._seen = self._offered
            if not due or offer is None:
                continue
            self._pass(offer, context)

    def _pass(self, offer, context) -> None:
        image, camera, captured, at, fov = offer
        started = time.perf_counter()
        try:
            found = self.detector.detect(image)
        except Exception:
            log.exception("eyes: the hazard watch failed on a picture")
            return
        self.last_ms = (time.perf_counter() - started) * 1000
        self._last_pass = self.monotonic()
        self.passes += 1
        roles = {c["label"]: c.get("role", "lookalike") for c in getattr(self.detector, "classes", [])}
        lookalikes = [(f.box, f.label) for f in found if roles.get(f.label) == "lookalike"]
        lookalikes += [(t.box, t.label) for t in context]
        hot = [(roles.get(f.label), f.box) for f in found if roles.get(f.label) in ("fire", "smoke")]
        with self._lock:
            self._tracks = _match(self._tracks, [(role, box) for role, box in hot], captured)
            tracks = list(self._tracks)
        things = []
        for f in found:
            label = role = roles.get(f.label, "lookalike")
            if role == "life":
                things.append(Thing(f.box, f.label, bool(getattr(f, "animal", False)), at, "hazard"))
                continue
            if role == "lookalike":
                things.append(Thing(f.box, f.label, False, at, "hazard"))
                continue
            box = f.box
            track = next((t for t in tracks if t.label == role and t.box is box), None)
            evidence = (_flicker(track) if role == "fire" else _spread(track)) if track else 0.0
            if role == "fire" and not _grew(track):
                label = _contained(box, lookalikes) or label
            elif role == "smoke" and evidence < 0.5:
                label = _steam(box, lookalikes) or label
            score = box.score
            if label == role:
                score = 1 - (1 - box.score) * (1 - (0.7 if role == "fire" else 0.5) * evidence)
            if role == "fire" or evidence > 0:
                with self._cond:
                    self._close_until = max(self._close_until, self.monotonic() + CLOSE_FOR_S)
            things.append(Thing(replace(box, score=round(min(1.0, score), 3)), label, False, at, "hazard"))
        with self._lock:
            self._result = (camera, captured, tuple(things))

    def look(self, image, camera: str, captured: float, at: float, fov_h_deg: float, context=()) -> list[Thing]:
        if self.detector is None:
            self.detector = self.make_detector()
        self._pass((image, camera, captured, at, fov_h_deg), list(context))
        return self.current(camera, captured)

    def current(self, camera: str, now: float) -> list[Thing]:
        with self._lock:
            result = self._result
        if result is None or result[0] != camera or now - result[1] > self.keep_s:
            return []
        return list(result[2])

    def status(self) -> dict:
        with self._lock:
            tracks = [{"label": t.label, "flicker": round(_flicker(t), 2) if t.label == "fire" else None, "spread": round(_spread(t), 2) if t.label == "smoke" else None} for t in self._tracks]
        return {"passes": self.passes, "ms": round(self.last_ms, 1), "problem": self.problem, "close_watch": self.monotonic() < self._close_until, "tracks": tracks}


def cells(box: Box, size=SMALL) -> tuple[int, int, int, int]:
    w, h = size
    x0, y0 = max(0, int(box.x * w)), max(0, int(box.y * h))
    return x0, y0, max(x0 + 1, min(w, int(math.ceil((box.x + box.w) * w)))), max(y0 + 1, min(h, int(math.ceil((box.y + box.h) * h))))


def _within(box: Box, other: Box, grow: float = 0.15) -> float:
    x0, x1 = other.x - other.w * grow, other.x + other.w * (1 + grow)
    y0, y1 = other.y - other.h * grow, other.y + other.h * (1 + grow)
    w = max(0.0, min(box.x + box.w, x1) - max(box.x, x0))
    h = max(0.0, min(box.y + box.h, y1) - max(box.y, y0))
    return w * h / max(1e-9, box.w * box.h)


def _contained(box: Box, spots) -> str | None:
    for other, label in sorted(spots, key=lambda s: -s[0].score):
        name = FIRE_SPOTS.get(label)
        if name is None or _within(box, other) < CONTAINED:
            continue
        if label in SAME_BLOB and other.score < box.score:
            continue
        if name in SMALL_SPOTS and box.w * box.h > SMALL_FIRE * other.w * other.h:
            continue
        return name
    return None


def _steam(box: Box, spots) -> str | None:
    for other, label in spots:
        if label not in STEAM_SPOTS or box.w * box.h > STEAM_AREA * max(1e-9, other.w * other.h):
            continue
        above = Box(other.x - other.w * 0.25, other.y - other.h * 1.5, other.w * 1.5, other.h * 2.5, other.score)
        if _within(box, above, 0.0) >= CONTAINED or (above.x <= box.cx <= above.x + above.w and above.y <= box.cy <= above.y + above.h):
            return "steam"
    return None


def _grew(track) -> bool:
    return track is not None and track.box.w * track.box.h >= GREW * track.first_area


def _match(tracks: list[_Track], found, now: float) -> list[_Track]:
    out = []
    free = list(tracks)
    for label, box in found:
        best = max((t for t in free if t.label == label), key=lambda t: overlap(t.box, box), default=None)
        if best is not None and overlap(best.box, box) > 0.2:
            free.remove(best)
            best.box, best.last = box, now
            out.append(best)
        else:
            out.append(_Track(label, box, now, now, box.w * box.h, (box.cx, box.cy), deque(maxlen=SERIES)))
    out.extend(t for t in free if now - t.last < CLOSE_FOR_S)
    return out


def _flicker(track: _Track | None) -> float:
    series = list(track.series) if track is not None else []
    if len(series) < 12:
        return 0.0
    times = [t for t, _ in series]
    values = [v for _, v in series]
    if times[-1] - times[0] < FLICKER_MIN_S:
        return 0.0
    mean = sum(values) / len(values)
    if mean <= 1:
        return 0.0
    steps = [b - a for a, b in zip(values, values[1:])]
    swing = (sum(s * s for s in steps) / len(steps)) ** 0.5 / mean
    turns = sum(1 for a, b in zip(steps, steps[1:]) if a * b < 0)
    rate = turns / 2 / max(1e-3, times[-1] - times[0])
    if rate < 0.8:
        return 0.0
    return max(0.0, min(1.0, (swing - 0.01) / 0.05))


def _spread(track: _Track | None) -> float:
    if track is None or track.last - track.first < 2.5:
        return 0.0
    area = track.box.w * track.box.h
    grow = area / max(1e-6, track.first_area)
    drift = math.hypot(track.box.cx - track.first_centre[0], track.box.cy - track.first_centre[1]) / max(1e-3, math.sqrt(track.first_area))
    return max(0.0, min(1.0, max((grow - 1.1) / 0.4, drift / 0.5)))
