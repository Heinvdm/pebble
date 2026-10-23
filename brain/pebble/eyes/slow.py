import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .detect import opencv
from .geometry import Box

log = logging.getLogger(__name__)

PAD = 114
SAME_THING = 0.6


@dataclass(frozen=True)
class SlowFound:
    box: Box
    label: str
    animal: bool
    raw: str
    depth: int
    known: str | None = None
    known_score: float = 0.0


class NoSlowModel(RuntimeError):
    pass


def load_vocab(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    classes = data.get("classes")
    if not isinstance(classes, list) or not classes:
        raise NoSlowModel(f"{path} lists no classes")
    return data


def letterbox(image, size: int, np, cv2):
    h, w = image.shape[:2]
    k = min(size / w, size / h)
    rw, rh = max(1, round(w * k)), max(1, round(h * k))
    left, top = (size - rw) // 2, (size - rh) // 2
    canvas = np.full((size, size, 3), PAD, np.uint8)
    canvas[top:top + rh, left:left + rw] = cv2.resize(image, (rw, rh), interpolation=cv2.INTER_AREA)
    blob = canvas[:, :, ::-1].astype(np.float32).transpose(2, 0, 1)[None] / 255.0
    return np.ascontiguousarray(blob), k, left, top


class SlowDetector:
    def __init__(self, model: Path, vocab: Path, backend: str = "auto", threads: int = 1, score: float = 0.45):
        self.cv2, self.np = opencv()
        model, vocab = Path(model), Path(vocab)
        if not model.exists() or not vocab.exists():
            raise NoSlowModel(f"the slow-lane model is missing ({model.name}); see tools/export_objects.py")
        self.vocab = load_vocab(vocab)
        self.classes = self.vocab["classes"]
        self.size = int(self.vocab.get("imgsz") or 320)
        self.score = float(score)
        self.threads = max(1, int(threads))
        self.coco_depth = {str(k): int(v) for k, v in (self.vocab.get("coco_depth") or {}).items()}
        self.backend = None
        self._session = None
        self._net = None
        if backend in ("auto", "onnxruntime"):
            try:
                import onnxruntime as ort

                options = ort.SessionOptions()
                options.intra_op_num_threads = self.threads
                options.inter_op_num_threads = 1
                options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                options.log_severity_level = 3
                self._session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
                self._input = self._session.get_inputs()[0].name
                self.backend = f"onnxruntime {ort.__version__}"
            except ImportError:
                if backend == "onnxruntime":
                    raise NoSlowModel("onnxruntime is not installed (Debian: apt install python3-onnxruntime)")
        if self._session is None:
            try:
                self._net = self.cv2.dnn.readNetFromONNX(str(model))
            except self.cv2.error as error:
                raise NoSlowModel(f"OpenCV cannot run the slow-lane model: {str(error).strip()[:160]}") from error
            self.backend = f"opencv {self.cv2.__version__}"
        log.info("eyes: slow lane ready (%s, %d words, %d px, %s)", Path(model).name, len(self.classes), self.size, self.backend)

    def _run(self, blob):
        if self._session is not None:
            return self._session.run(None, {self._input: blob})[0]
        self._net.setInput(blob)
        return self._net.forward()

    def detect(self, image, score: float | None = None) -> list[SlowFound]:
        cv2, np = self.cv2, self.np
        floor = self.score if score is None else float(score)
        h, w = image.shape[:2]
        blob, k, left, top = letterbox(image, self.size, np, cv2)
        out = self._run(blob)
        out = out.reshape(out.shape[-2], out.shape[-1])
        count = len(self.classes)
        scores = out[4:4 + count]
        best = scores.argmax(axis=0)
        top_scores = scores[best, np.arange(scores.shape[1])]
        keep = np.nonzero(top_scores > floor)[0]
        if keep.size == 0:
            return []
        cx, cy, bw, bh = out[0, keep], out[1, keep], out[2, keep], out[3, keep]
        x1 = (cx - bw / 2 - left) / k
        y1 = (cy - bh / 2 - top) / k
        rects = [[float(x1[i]), float(y1[i]), float(bw[i] / k), float(bh[i] / k)] for i in range(keep.size)]
        confidences = [float(top_scores[j]) for j in keep]
        picked = cv2.dnn.NMSBoxes(rects, confidences, floor, SAME_THING)
        found = []
        for i in np.array(picked).reshape(-1):
            entry = self.classes[int(best[keep[i]])]
            x, y, rw, rh = rects[i]
            x0, y0 = max(0.0, x / w), max(0.0, y / h)
            x2, y2 = min(1.0, (x + rw) / w), min(1.0, (y + rh) / h)
            if x2 <= x0 or y2 <= y0:
                continue
            box = Box(x0, y0, x2 - x0, y2 - y0, confidences[i])
            found.append(SlowFound(box, str(entry["label"]), bool(entry.get("animal")), str(entry.get("raw", entry["label"])), int(entry.get("depth", 6))))
        return found


@dataclass(frozen=True)
class SlowPass:
    camera: str
    captured: float
    at: float
    fov_h_deg: float
    width: int
    height: int
    found: tuple


@dataclass
class _Offer:
    image: object
    camera: str
    captured: float
    at: float
    fov_h_deg: float


class SlowLane:
    def __init__(
        self,
        make_detector,
        monotonic=None,
        every_s: float = 1.0,
        keep_s: float = 3.0,
        change: float = 0.06,
        nice: int = 10,
        on_pass=None,
        recognise=None,
    ):
        import threading
        import time

        self.make_detector = make_detector
        self.monotonic = monotonic or time.monotonic
        self.every_s = float(every_s)
        self.keep_s = float(keep_s)
        self.change = float(change)
        self.nice = int(nice)
        self.on_pass = on_pass
        self.recognise = recognise
        self.detector = None
        self.problem = ""
        self.passes = 0
        self.last_ms = 0.0
        self._cond = threading.Condition()
        self._offer: _Offer | None = None
        self._offered = 0
        self._seen = 0
        self._busy = False
        self._moved = False
        self._demands: list = []
        self._result: SlowPass | None = None
        self._last_pass = -1e9
        self._thumb = None
        self._thumb_camera = None
        self._stop = threading.Event()
        self._thread = None

    def start(self) -> None:
        import threading

        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="pebble-eyes-slow", daemon=True)
            self._thread.start()

    def close(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
            self._fail_demands()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=10.0)

    def set_busy(self, busy: bool) -> None:
        with self._cond:
            self._busy = bool(busy)
            self._cond.notify_all()

    @property
    def busy(self) -> bool:
        return self._busy

    def moved(self) -> None:
        with self._cond:
            self._moved = True
            self._cond.notify_all()

    def offer(self, image, camera: str, captured: float, at: float, fov_h_deg: float) -> None:
        with self._cond:
            self._offer = _Offer(image, camera, captured, at, fov_h_deg)
            self._offered += 1
            self._cond.notify_all()

    def forget(self) -> None:
        with self._cond:
            self._offer = None
            self._result = None
            self._thumb = None
            self._fail_demands()

    def demand(self, loop):
        future = loop.create_future()
        with self._cond:
            self._demands.append((future, loop))
            self._cond.notify_all()
        return future

    def current(self, camera: str, now: float) -> SlowPass | None:
        with self._cond:
            result = self._result
        if result is None or result.camera != camera or now - result.captured > self.keep_s:
            return None
        return result

    def _fail_demands(self) -> None:
        demands, self._demands = self._demands, []
        for future, loop in demands:
            loop.call_soon_threadsafe(_settle, future, None)

    def _lower_priority(self) -> None:
        import os
        import threading

        if self.nice > 0 and hasattr(os, "setpriority"):
            try:
                os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), self.nice)
            except OSError:
                pass

    def _changed(self, offer: _Offer) -> bool:
        cv2, np = self.detector.cv2, self.detector.np
        gray = cv2.cvtColor(offer.image, cv2.COLOR_BGR2GRAY) if offer.image.ndim == 3 else offer.image
        thumb = cv2.resize(gray, (32, 24), interpolation=cv2.INTER_AREA).astype(np.float32)
        if self._thumb is None or self._thumb_camera != offer.camera:
            return True
        return float(np.mean(np.abs(thumb - self._thumb))) / 255.0 > self.change

    def _remember(self, offer: _Offer) -> None:
        cv2, np = self.detector.cv2, self.detector.np
        gray = cv2.cvtColor(offer.image, cv2.COLOR_BGR2GRAY) if offer.image.ndim == 3 else offer.image
        self._thumb = cv2.resize(gray, (32, 24), interpolation=cv2.INTER_AREA).astype(np.float32)
        self._thumb_camera = offer.camera

    def _run(self) -> None:
        self._lower_priority()
        try:
            self.detector = self.make_detector()
        except Exception as error:
            self.problem = f"the slow lane is off: {error}"
            log.warning("eyes: %s", self.problem)
            with self._cond:
                self._fail_demands()
            while not self._stop.is_set():
                with self._cond:
                    self._cond.wait(1.0)
                    self._fail_demands()
            return
        while not self._stop.is_set():
            with self._cond:
                self._cond.wait_for(lambda: self._stop.is_set() or self._demands or (self._offered > self._seen and not self._busy), timeout=1.0)
                if self._stop.is_set():
                    break
                offer = self._offer
                demands, self._demands = self._demands, []
                fresh = self._offered > self._seen
                self._seen = self._offered
                moved, busy = self._moved, self._busy
            if offer is None:
                for future, loop in demands:
                    loop.call_soon_threadsafe(_settle, future, None)
                continue
            if not demands:
                if busy or not fresh or self.monotonic() - self._last_pass < self.every_s:
                    continue
                if not (moved or self._changed(offer)):
                    continue
            result = self._pass(offer)
            for future, loop in demands:
                loop.call_soon_threadsafe(_settle, future, result)

    def _pass(self, offer: _Offer) -> SlowPass | None:
        import time

        started = time.perf_counter()
        try:
            found = self.detector.detect(offer.image)
            if self.recognise is not None and found:
                found = self.recognise(offer.image, found)
        except Exception:
            log.exception("eyes: the slow lane failed on a picture")
            return None
        self.last_ms = (time.perf_counter() - started) * 1000
        height, width = offer.image.shape[:2]
        result = SlowPass(offer.camera, offer.captured, offer.at, offer.fov_h_deg, width, height, tuple(found))
        with self._cond:
            self._result = result
            self._moved = False
            self._last_pass = self.monotonic()
            self.passes += 1
        self._remember(offer)
        if self.on_pass is not None:
            self.on_pass(result)
        return result


def _settle(future, value) -> None:
    if not future.done():
        future.set_result(value)
