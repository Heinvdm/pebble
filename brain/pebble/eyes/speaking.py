import math
import threading
import time
from collections import deque
from pathlib import Path

from .detect import opencv

SIDE = 256
SCALE = 3.0
CENTRE = 0.4
WINDOW_S = 0.8
MIN_SPAN_S = 0.4
MIN_SAMPLES = 4
GAP_S = 0.3
HISTORY_S = 15.0
MIN_FACE_PX = 32
MAX_FACES = 2
TAIL_S = 2.0
LIPS = (13, 14)
CORNERS = (78, 308)
EYES = (33, 263)
QUIET = 0.06
BUSY = 0.20
OPEN_FROM = 0.02
OPEN_SPAN = 0.05
SMILE_FROM = 0.60
SMILE_SPAN = 0.08
STEP = 0.012
TURNS_FROM = 1.0
TURNS_SPAN = 2.0


class NoMouthModel(Exception):
    pass


class MouthModel:
    def __init__(self, path: Path, threads: int = 1):
        self.cv2, self.np = opencv()
        path = Path(path)
        if not path.exists():
            raise NoMouthModel(f"the face mesh model is missing ({path.name}); run python -m pebble.eyes.fetch")
        try:
            self._net = self.cv2.dnn.readNetFromTFLite(str(path))
        except (AttributeError, self.cv2.error) as error:
            raise NoMouthModel(f"this OpenCV cannot run the face mesh model: {error}")
        self.cv2.setNumThreads(max(1, int(threads)))
        self._names = self._net.getUnconnectedOutLayersNames()
        self.backend = f"opencv {self.cv2.__version__}"

    def read(self, image, box, marks):
        cv2, np = self.cv2, self.np
        (rx, ry), (lx, ly), _, (ax, ay), (bx, by) = marks
        ex, ey, mx, my = (rx + lx) / 2, (ry + ly) / 2, (ax + bx) / 2, (ay + by) / 2
        span = max(math.hypot(lx - rx, ly - ry), math.hypot(mx - ex, my - ey))
        if span < 1:
            return None
        angle = math.degrees(math.atan2(ly - ry, lx - rx))
        cx, cy = ex + (mx - ex) * CENTRE, ey + (my - ey) * CENTRE
        m = cv2.getRotationMatrix2D((float(cx), float(cy)), float(angle), SIDE / (span * SCALE))
        m[0, 2] += SIDE / 2 - cx
        m[1, 2] += SIDE / 2 - cy
        crop = cv2.warpAffine(image, m, (SIDE, SIDE), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        blob = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32).transpose(2, 0, 1)[None] / 255.0
        self._net.setInput(blob)
        outs = self._net.forward(self._names)
        points = next((o for o in outs if o.size == 478 * 3), None)
        sure = next((float(o.ravel()[0]) for n, o in zip(self._names, outs) if o.size == 1 and o.ndim == 4), None)
        if points is None or sure is None or sure < 0:
            return None
        return shape(points.reshape(478, 3))


def shape(points):
    eyes = math.dist(points[EYES[0]][:2], points[EYES[1]][:2])
    if eyes < 1e-6:
        return None
    return math.dist(points[LIPS[0]][:2], points[LIPS[1]][:2]) / eyes, math.dist(points[CORNERS[0]][:2], points[CORNERS[1]][:2]) / eyes


def clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def score(samples) -> float | None:
    if len(samples) < MIN_SAMPLES:
        return None
    span = samples[-1][0] - samples[0][0]
    if span < MIN_SPAN_S:
        return None
    gaps = [s[1] for s in samples]
    steps = [b - a for a, b in zip(gaps, gaps[1:])]
    activity = sum(abs(d) for d in steps) / span
    moves = [d for d in steps if abs(d) >= STEP]
    rhythm = clip((sum(1 for a, b in zip(moves, moves[1:]) if a * b < 0) / span - TURNS_FROM) / TURNS_SPAN)
    opened = clip((max(gaps) - OPEN_FROM) / OPEN_SPAN)
    smile = clip((sum(s[2] for s in samples) / len(samples) - SMILE_FROM) / SMILE_SPAN)
    return round(clip((activity - QUIET) / BUSY) * (0.4 + 0.6 * opened) * (1 - 0.5 * smile) * (0.3 + 0.7 * rhythm), 3)


class SpeakingMeter:
    def __init__(self, make_model=None, gate: str = "voice", max_faces: int = MAX_FACES, min_face_px: float = MIN_FACE_PX, window_s: float = WINDOW_S, tail_s: float = TAIL_S, monotonic=time.monotonic):
        self.make_model = make_model
        self.model = None
        self.problem = ""
        self.gate = gate
        self.max_faces = int(max_faces)
        self.min_face_px = float(min_face_px)
        self.window_s = float(window_s)
        self.tail_s = float(tail_s)
        self.monotonic = monotonic
        self.reads = 0
        self.last_ms = 0.0
        self._voice = False
        self._voice_until = -1e9
        self._mouths: dict[int, deque] = {}
        self._said: dict[int, deque] = {}
        self._lock = threading.Lock()

    def hear_voice(self, on: bool) -> None:
        self._voice = bool(on)
        if not on:
            self._voice_until = self.monotonic() + self.tail_s

    def active(self) -> bool:
        return self.gate == "always" or self._voice or self.monotonic() < self._voice_until

    def step(self, image, faces, captured: float, at: float) -> dict[int, float | None]:
        if not self.active() or not faces:
            self._drop(set())
            return {}
        if self.model is None and not self.problem:
            try:
                self.model = self.make_model()
            except Exception as error:
                self.problem = f"no speaking: {error}"
        if self.model is None:
            return {}
        big = sorted((f for f in faces if f[1][2] >= self.min_face_px), key=lambda f: -f[1][2])[: self.max_faces]
        out = {}
        for track, box, marks in big:
            started = time.perf_counter()
            mouth = self.model.read(image, box, marks)
            self.last_ms = (time.perf_counter() - started) * 1000
            self.reads += 1
            out[track] = self.note(track, captured, at, *mouth) if mouth else None
        self._drop({f[0] for f in faces})
        return out

    def note(self, track: int, captured: float, at: float, gap: float, width: float) -> float | None:
        with self._lock:
            mouth = self._mouths.setdefault(track, deque(maxlen=64))
            if mouth and (captured - mouth[-1][0] > GAP_S or captured <= mouth[-1][0]):
                mouth.clear()
            mouth.append((captured, float(gap), float(width)))
            while mouth and captured - mouth[0][0] > self.window_s + 1e-6:
                mouth.popleft()
            value = score(list(mouth))
            if value is not None:
                said = self._said.setdefault(track, deque())
                said.append((at, value))
                while said and at - said[0][0] > HISTORY_S:
                    said.popleft()
                for old in [k for k, v in self._said.items() if not v or at - v[-1][0] > HISTORY_S]:
                    del self._said[old]
            return value

    def _drop(self, keep: set) -> None:
        with self._lock:
            for track in [t for t in self._mouths if t not in keep]:
                del self._mouths[track]

    def spoke(self, start: float, end: float) -> dict[int, float]:
        with self._lock:
            out = {}
            for track, said in self._said.items():
                values = [v for at, v in said if start <= at <= end]
                if values:
                    out[track] = round(sum(values) / len(values), 3)
            return out

    def forget(self) -> None:
        with self._lock:
            self._mouths.clear()
            self._said.clear()

    def status(self) -> dict:
        return {"gate": self.gate, "listening": self.active(), "reads": self.reads, "ms": round(self.last_ms, 1), "problem": self.problem}
