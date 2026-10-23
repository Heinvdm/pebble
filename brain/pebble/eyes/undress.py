import logging
import threading
import time
from pathlib import Path

from .detect import opencv

log = logging.getLogger(__name__)

CLASSES = (
    "FEMALE_GENITALIA_COVERED",
    "FACE_FEMALE",
    "BUTTOCKS_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_BREAST_EXPOSED",
    "ANUS_EXPOSED",
    "FEET_EXPOSED",
    "BELLY_COVERED",
    "FEET_COVERED",
    "ARMPITS_COVERED",
    "ARMPITS_EXPOSED",
    "FACE_MALE",
    "BELLY_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "ANUS_COVERED",
    "FEMALE_BREAST_COVERED",
    "BUTTOCKS_COVERED",
)
EXPOSED = frozenset({"BUTTOCKS_EXPOSED", "FEMALE_BREAST_EXPOSED", "FEMALE_GENITALIA_EXPOSED", "MALE_GENITALIA_EXPOSED", "ANUS_EXPOSED"})
BARE = frozenset({"MALE_BREAST_EXPOSED", "BELLY_EXPOSED"})
SIZE = 320
EVERY_S = 1.0
KEEP_S = 2.5
MODEL = "nudenet_320n.onnx"


class NoUndressModel(Exception):
    pass


class UndressModel:
    def __init__(self, path: Path, threads: int = 1, backend: str = "auto"):
        self.cv2, self.np = opencv()
        path = Path(path)
        if not path.exists():
            raise NoUndressModel(f"the undress model is missing ({path.name}); run python -m pebble.eyes.fetch")
        self.backend = None
        self._session = None
        self._net = None
        if backend in ("auto", "onnxruntime"):
            try:
                import onnxruntime as ort

                options = ort.SessionOptions()
                options.intra_op_num_threads = max(1, int(threads))
                options.inter_op_num_threads = 1
                options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                options.log_severity_level = 3
                self._session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
                self._input = self._session.get_inputs()[0].name
                self.backend = f"onnxruntime {ort.__version__}"
            except ImportError:
                if backend == "onnxruntime":
                    raise NoUndressModel("onnxruntime is not installed")
        if self._session is None:
            try:
                self._net = self.cv2.dnn.readNetFromONNX(str(path))
            except self.cv2.error as error:
                raise NoUndressModel(f"OpenCV cannot run the undress model: {str(error).strip()[:160]}") from error
            self.backend = f"opencv {self.cv2.__version__}"

    def _blob(self, image):
        cv2, np = self.cv2, self.np
        h, w = image.shape[:2]
        side = max(h, w)
        square = cv2.copyMakeBorder(image, 0, side - h, 0, side - w, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        return cv2.dnn.blobFromImage(square, 1 / 255.0, (SIZE, SIZE), (0, 0, 0), swapRB=True, crop=False)

    def scores(self, image) -> tuple[float, float]:
        blob = self._blob(image)
        if self._session is not None:
            out = self._session.run(None, {self._input: blob})[0]
        else:
            self._net.setInput(blob)
            out = self._net.forward()
        out = out.reshape(out.shape[-2], out.shape[-1])
        best = out[4:4 + len(CLASSES)].max(axis=1)
        exposed = max(float(best[CLASSES.index(name)]) for name in EXPOSED)
        bare = max(float(best[CLASSES.index(name)]) for name in BARE)
        return round(exposed, 3), round(bare, 3)


class UndressWatch:
    def __init__(self, make_model, monotonic=time.monotonic, every_s: float = EVERY_S, keep_s: float = KEEP_S, nice: int = 5):
        self.make_model = make_model
        self.monotonic = monotonic
        self.every_s = float(every_s)
        self.keep_s = float(keep_s)
        self.nice = int(nice)
        self.model = None
        self.problem = ""
        self.passes = 0
        self.last_ms = 0.0
        self._cond = threading.Condition()
        self._model_lock = threading.Lock()
        self._lock = threading.Lock()
        self._offer = None
        self._offered = 0
        self._seen = 0
        self._last = -1e9
        self._result: tuple | None = None
        self._stop = threading.Event()
        self._thread = None

    def start(self) -> None:
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="pebble-eyes-privacy", daemon=True)
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

    def offer(self, image, captured: float) -> None:
        with self._cond:
            self._offer = (image, captured)
            self._offered += 1
            self._cond.notify_all()

    def _load(self):
        with self._model_lock:
            if self.model is None and not self.problem:
                try:
                    self.model = self.make_model()
                except Exception as error:
                    self.problem = f"the privacy cue model is off: {error}"
                    log.warning("eyes: %s", self.problem)
            return self.model

    def check(self, image) -> tuple[float, float] | None:
        model = self._load()
        if model is None:
            return None
        started = time.perf_counter()
        with self._model_lock:
            found = model.scores(image)
        self.last_ms = (time.perf_counter() - started) * 1000
        self.passes += 1
        return found

    def _run(self) -> None:
        import os

        if self.nice > 0 and hasattr(os, "setpriority"):
            try:
                os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), self.nice)
            except OSError:
                pass
        if self._load() is None:
            return
        while not self._stop.is_set():
            with self._cond:
                self._cond.wait(timeout=0.25)
                if self._stop.is_set():
                    break
                fresh = self._offered > self._seen
                offer = self._offer
                go = fresh and offer is not None and self.monotonic() - self._last >= self.every_s
                if go:
                    self._seen = self._offered
                    self._offer = None
            if not go:
                continue
            image, captured = offer
            try:
                found = self.check(image)
            except Exception:
                log.exception("eyes: the privacy cue model failed on a picture")
                found = None
            self._last = self.monotonic()
            if found is not None:
                with self._lock:
                    self._result = (captured, found[0], found[1])

    def current(self, now: float) -> tuple[float, float] | None:
        with self._lock:
            result = self._result
        if result is None or now - result[0] > self.keep_s:
            return None
        return result[1], result[2]

    def status(self) -> dict:
        return {"passes": self.passes, "ms": round(self.last_ms, 1), "problem": self.problem}
