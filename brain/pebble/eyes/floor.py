import logging
import math
import threading
import time
from pathlib import Path

from ..seams.sight import FLOOR_OPEN_M, FloorRay
from .detect import opencv
from .geometry import floor_point

log = logging.getLogger(__name__)

SIZE = (182, 238)
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
BINS = 32
REACH_M = 2.0
SEED_NEAR_M = 0.0
SEED_FAR_M = 1.3
UP = 0.35
DOWN = 0.5
DROP_REACH_M = 1.5
RUN = 2
EVERY_S = 0.2
KEEP_S = 1.0
SLOPE_ROWS = 3
PLATEAU = 0.35
LOW = 0.1
HORIZON_ABOVE_DEG = 12.0
BLANK = 128
LOW_THINGS = {
    "cable", "extension cord", "wire", "charger", "plug", "lego", "building block", "toy", "toy car", "soft toy", "stuffed toy",
    "teddy bear", "sock", "shoe", "slipper", "boot", "sandal", "flip-flop", "bowl", "dog food", "cat food", "marble", "ball",
    "crayon", "puzzle", "towel", "clothes", "rope", "string", "leash", "hose", "book", "bag", "backpack", "remote control",
}


class NoDepthModel(Exception):
    pass


class DepthModel:
    def __init__(self, path: Path, threads: int = 1, size=SIZE):
        self.cv2, self.np = opencv()
        path = Path(path)
        if not path.exists():
            raise NoDepthModel(f"the depth model is missing ({path.name}); run python -m pebble.eyes.fetch")
        self.size = (int(size[0]) // 14 * 14, int(size[1]) // 14 * 14)
        self._session = None
        try:
            import onnxruntime as ort

            options = ort.SessionOptions()
            options.intra_op_num_threads = max(1, int(threads))
            options.inter_op_num_threads = 1
            options.log_severity_level = 3
            self._session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
            self._input = self._session.get_inputs()[0].name
            self.backend = f"onnxruntime {ort.__version__}"
        except ImportError:
            self._net = self.cv2.dnn.readNetFromONNX(str(path))
            self.backend = f"opencv {self.cv2.__version__}"
        self._mean = self.np.array(MEAN, self.np.float32)
        self._std = self.np.array(STD, self.np.float32)

    def __call__(self, image):
        cv2, np = self.cv2, self.np
        h, w = self.size
        rgb = cv2.cvtColor(cv2.resize(image, (w, h), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        blob = ((rgb - self._mean) / self._std).transpose(2, 0, 1)[None]
        if self._session is not None:
            out = self._session.run(None, {self._input: blob})[0]
        else:
            self._net.setInput(blob)
            out = self._net.forward()
        return out.reshape(out.shape[-2], out.shape[-1]).astype(np.float32)


def level(image, roll_deg: float):
    if abs(roll_deg) < 0.5:
        return image
    cv2, _ = opencv()
    h, w = image.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), roll_deg, 1.0)
    return cv2.warpAffine(image, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def horizon_row(rows: int, cols: int, fov_h_deg: float, pitch_deg: float, roll_deg: float = 0.0, above_deg: float = HORIZON_ABOVE_DEG) -> int:
    f = (cols / 2) / math.tan(math.radians(fov_h_deg) / 2)
    angle = math.radians(pitch_deg + above_deg)
    row = rows / 2 - f * math.tan(angle) - abs(math.tan(math.radians(roll_deg))) * cols / 2
    return max(0, min(rows, int(math.floor(row))))


def floor_only(image, fov_h_deg: float, pitch_deg: float, roll_deg: float = 0.0):
    rows, cols = image.shape[:2]
    top = horizon_row(rows, cols, fov_h_deg, pitch_deg, roll_deg)
    out = image.copy()
    if top > 0:
        out[:top] = BLANK
    return out


def rays(depth, fov_h_deg: float, camera_height_m: float, pitch_deg: float, bins: int = BINS, reach_m: float = REACH_M):
    found, quality, _ = scan(depth, fov_h_deg, camera_height_m, pitch_deg, bins, reach_m)
    return found, quality


def scan(depth, fov_h_deg: float, camera_height_m: float, pitch_deg: float, bins: int = BINS, reach_m: float = REACH_M):
    np = opencv()[1]
    rows, cols = depth.shape
    f = (cols / 2) / math.tan(math.radians(fov_h_deg) / 2)
    p = math.radians(pitch_deg)
    y = (np.arange(rows) + 0.5 - rows / 2) / f
    down = y * math.cos(p) - math.sin(p)
    ahead = math.cos(p) + y * math.sin(p)
    with np.errstate(divide="ignore", invalid="ignore"):
        ground = np.where(down > 1e-4, camera_height_m * ahead / down, np.inf)
    nearest = float(ground[-1]) if math.isfinite(ground[-1]) else SEED_FAR_M
    seed_rows = (ground >= SEED_NEAR_M) & (ground <= max(SEED_FAR_M, 1.6 * nearest))
    if seed_rows.sum() < 4:
        return None, 0.0, []
    c0, c1 = int(cols * 0.2), int(cols * 0.8)
    seed = depth[seed_rows, c0:c1]
    g = np.repeat(down[seed_rows, None], c1 - c0, axis=1)
    fit = _fit(g.ravel(), seed.ravel())
    if fit is None:
        return None, 0.0, []
    alpha, beta, quality = fit
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(depth - beta > 1e-6, alpha * camera_height_m / (depth - beta), np.inf)
    height = camera_height_m - z * down[:, None]
    edges = np.linspace(0, cols, bins + 1)
    out = []
    feet = []
    for b in range(bins):
        a, e = int(edges[b]), max(int(edges[b]) + 1, int(edges[b + 1]))
        tall = np.median(height[:, a:e], axis=1)
        far = np.median(z[:, a:e], axis=1)
        u = (a + e) / 2 / cols
        x = (u - 0.5) * cols / f
        with np.errstate(divide="ignore", invalid="ignore"):
            gq = np.where(np.isfinite(far) & (far > 0), camera_height_m / far, 0.0)
        rise = np.ones(rows)
        rise[:-SLOPE_ROWS] = (gq[SLOPE_ROWS:] - gq[:-SLOPE_ROWS]) / np.maximum(down[SLOPE_ROWS:] - down[:-SLOPE_ROWS], 1e-9)
        foot, kind = _foot(tall / camera_height_m, far * np.hypot(ahead, x), ground, reach_m, rise)
        feet.append((u, None if foot is None else (foot + 0.5) / rows, kind))
        distance = None
        if foot is not None:
            if kind == "up":
                distance = float(far[foot]) * math.hypot(ahead[foot], x)
                bearing = math.degrees(math.atan2(x, ahead[foot]))
            else:
                spot = floor_point(u, (foot + 1.5) / rows, cols, rows, fov_h_deg, camera_height_m, pitch_deg, 0.0, reach_m=1e9)
                if spot is not None:
                    distance, bearing = spot
        if distance is None or not math.isfinite(distance) or distance > reach_m:
            last = np.nonzero(ground <= reach_m)[0]
            row = int(last.min()) if len(last) else rows - 1
            out.append(FloorRay(round(math.degrees(math.atan2(x, ahead[row])), 2), FLOOR_OPEN_M, round(quality * 0.8, 3)))
            continue
        sure = quality * (1.0 if kind == "up" else 0.7) * max(0.4, 1.0 - distance / (2 * reach_m))
        out.append(FloorRay(round(bearing, 2), round(distance, 3), round(sure, 3)))
    return tuple(out), quality, feet


def _fit(g, d):
    np = opencv()[1]
    keep = np.isfinite(d)
    g, d = g[keep], d[keep]
    if len(g) < 20 or g.max() - g.min() < 1e-3:
        return None
    for _ in range(3):
        a, b = np.polyfit(g, d, 1)
        res = d - (a * g + b)
        spread = np.median(np.abs(res)) * 1.4826 + 1e-6
        inside = np.abs(res) <= 2.5 * spread
        if inside.sum() < 20:
            break
        g, d = g[inside], d[inside]
    a, b = np.polyfit(g, d, 1)
    if a * (g.max() - g.min()) <= 1e-3 * (abs(float(np.median(d))) + 1e-6):
        return None
    res = d - (a * g + b)
    span = a * (g.max() - g.min())
    quality = float(max(0.0, min(1.0, 1.0 - 4.0 * np.median(np.abs(res)) / max(span, 1e-6))))
    return float(a), float(b), quality


def _foot(column, away, ground, reach_m: float, rise=None):
    np = opencv()[1]
    run_up = run_down = 0
    for r in range(len(column) - 1, -1, -1):
        value = column[r]
        upright = rise is not None and rise[r] < PLATEAU and value > LOW
        if not np.isfinite(value) or value > UP or upright:
            run_up += 1
            run_down = 0
        elif value < -DOWN:
            run_down += 1
            run_up = 0
        else:
            run_up = run_down = 0
            if away[r] > reach_m:
                return None, ""
        if run_up >= RUN:
            return r + RUN - 1, "up"
        if run_down >= RUN and ground[r + RUN - 1] <= min(reach_m, DROP_REACH_M):
            return r + RUN - 1, "down"
    return None, ""


def cut(scan, things, reach_m: float = REACH_M):
    if not scan:
        return scan
    out = list(scan)
    for thing in things:
        if thing.floor_m is None or thing.label not in LOW_THINGS or thing.floor_m > reach_m:
            continue
        half = max(2.0, math.degrees(math.atan2(thing.width_frac * 0.5, 1.0)) * 1.0)
        for i, ray in enumerate(out):
            if abs(ray.bearing_deg - thing.floor_bearing_deg) <= half and thing.floor_m < ray.distance_m:
                out[i] = FloorRay(ray.bearing_deg, round(thing.floor_m, 3), round(max(ray.score, min(0.9, thing.score)), 3))
    return tuple(out)


class FloorScan:
    def __init__(self, make_model, monotonic=time.monotonic, every_s: float = EVERY_S, keep_s: float = KEEP_S, bins: int = BINS, reach_m: float = REACH_M, gate: str = "moving", nice: int = 5):
        self.make_model = make_model
        self.monotonic = monotonic
        self.every_s = float(every_s)
        self.keep_s = float(keep_s)
        self.bins = int(bins)
        self.reach_m = float(reach_m)
        self.gate = gate
        self.nice = int(nice)
        self.model = None
        self.problem = ""
        self.passes = 0
        self.last_ms = 0.0
        self.quality = 0.0
        self._moving = False
        self._moving_until = -1e9
        self._cond = threading.Condition()
        self._offer = None
        self._offered = 0
        self._seen = 0
        self._last = -1e9
        self._wanted = False
        self._result = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def set_moving(self, on: bool) -> None:
        self._moving = bool(on)
        if not on:
            self._moving_until = self.monotonic() + 1.0

    def moving(self) -> bool:
        return self._moving or self.monotonic() < self._moving_until

    def start(self) -> None:
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="pebble-eyes-floor", daemon=True)
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

    def want(self) -> None:
        with self._cond:
            self._wanted = True
            self._cond.notify_all()

    def offer(self, image, camera: str, captured: float, at: float, fov_h_deg: float, head) -> None:
        with self._cond:
            self._offer = (image, camera, captured, at, fov_h_deg, head)
            self._offered += 1
            self._cond.notify_all()

    def _due(self, now: float) -> bool:
        if self._wanted:
            return True
        if self.gate == "off" or (self.gate == "moving" and not self.moving()):
            return False
        return now - self._last >= self.every_s

    def _run(self) -> None:
        import os

        if self.nice > 0 and hasattr(os, "setpriority"):
            try:
                os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), self.nice)
            except OSError:
                pass
        try:
            self.model = self.make_model()
        except Exception as error:
            self.problem = f"no floor scan: {error}"
            log.warning("eyes: %s", self.problem)
            return
        while not self._stop.is_set():
            with self._cond:
                self._cond.wait(timeout=0.1)
                if self._stop.is_set():
                    break
                fresh = self._offered > self._seen
                offer = self._offer
                go = fresh and offer is not None and self._due(self.monotonic())
                if go:
                    self._seen = self._offered
                    self._wanted = False
            if go:
                self.look(*offer)

    def look(self, image, camera: str, captured: float, at: float, fov_h_deg: float, head):
        height_m, pitch, roll = head
        if self.model is None:
            self.model = self.make_model()
        started = time.perf_counter()
        try:
            depth = self.model(level(image, roll))
            found, quality = rays(depth, fov_h_deg, height_m, pitch, self.bins, self.reach_m)
        except Exception:
            log.exception("eyes: the floor scan failed on a picture")
            return None
        self.last_ms = (time.perf_counter() - started) * 1000
        self._last = self.monotonic()
        self.passes += 1
        self.quality = quality
        with self._lock:
            self._result = (camera, captured, at, found or ())
        return found

    def current(self, camera: str, now: float):
        with self._lock:
            result = self._result
        if result is None or result[0] != camera or now - result[1] > self.keep_s:
            return (), None
        return result[3], result[2]

    def status(self) -> dict:
        return {"gate": self.gate, "moving": self.moving(), "passes": self.passes, "ms": round(self.last_ms, 1), "quality": round(self.quality, 2), "problem": self.problem, "reach_m": self.reach_m}
