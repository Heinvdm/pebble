import array
import csv
import importlib.util
import logging
import threading
import wave
from pathlib import Path

from .fetch import MODELS

log = logging.getLogger(__name__)

RATE = 16000
WINDOW = 15600
HOP = 7680
CLASSES = 521
MODEL = "yamnet.onnx"
CLASS_MAP = "yamnet_class_map.csv"
INT16_SCALE = 1.0 / 32768.0
ALIAS_TAPS = 63


class NoYamnet(RuntimeError):
    pass


def read_labels(path: Path) -> list[str]:
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows or [cell.strip() for cell in rows[0][:3]] != ["index", "mid", "display_name"]:
        raise NoYamnet(f"{Path(path).name} is not YAMNet's class map")
    labels = []
    for position, row in enumerate(rows[1:]):
        if len(row) < 3 or not row[0].strip().isdigit() or int(row[0]) != position:
            raise NoYamnet(f"{Path(path).name}: row {position + 2} is out of order")
        labels.append(row[2])
    return labels


def _numpy():
    try:
        import numpy
    except ImportError as error:
        raise NoYamnet("numpy is not installed (Debian: apt install python3-numpy)") from error
    return numpy


def _floats(samples, np):
    if isinstance(samples, array.array) and samples.typecode == "h":
        return np.frombuffer(samples, dtype=np.int16).astype(np.float32) * INT16_SCALE
    values = np.asarray(samples)
    if values.dtype == np.int16:
        return values.astype(np.float32).reshape(-1) * INT16_SCALE
    return values.astype(np.float32).reshape(-1)


def resample(samples, rate: int, target: int = RATE):
    np = _numpy()
    values = np.asarray(samples, dtype=np.float64).reshape(-1)
    if rate == target or values.size == 0:
        return values.astype(np.float32)
    if target < rate:
        cutoff = 0.475 * target / rate
        n = np.arange(ALIAS_TAPS) - (ALIAS_TAPS - 1) / 2.0
        taps = 2.0 * cutoff * np.sinc(2.0 * cutoff * n) * np.hamming(ALIAS_TAPS)
        values = np.convolve(values, taps / taps.sum(), mode="same")
    count = max(1, int(round(values.size * target / rate)))
    positions = np.arange(count) * (rate / target)
    return np.interp(positions, np.arange(values.size), values).astype(np.float32)


def read_wav(path, rate: int | None = RATE):
    np = _numpy()
    with wave.open(str(path), "rb") as handle:
        channels, width, source = handle.getnchannels(), handle.getsampwidth(), handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    if width == 1:
        values = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        values = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        bytes3 = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        joined = bytes3[:, 0] | (bytes3[:, 1] << 8) | (bytes3[:, 2] << 16)
        values = np.where(joined >= 1 << 23, joined - (1 << 24), joined).astype(np.float32) / float(1 << 23)
    elif width == 4:
        values = np.frombuffer(raw, dtype="<i4").astype(np.float64).astype(np.float32) / float(1 << 31)
    else:
        raise ValueError(f"{Path(path).name}: {width * 8}-bit samples are not supported")
    values = values[: values.size // channels * channels].reshape(-1, channels).mean(axis=1)
    if rate is None or rate == source:
        return source, values.astype(np.float32)
    return rate, resample(values, source, rate)


def _onnxruntime(model: Path, threads: int):
    try:
        import onnxruntime as ort
    except ImportError as error:
        raise NoYamnet("onnxruntime is not installed (Debian: apt install python3-onnxruntime)") from error
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.log_severity_level = 3
    try:
        session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
    except Exception as error:
        raise NoYamnet(f"onnxruntime cannot run the sound model: {str(error).strip()[:160]}") from error
    feed = session.get_inputs()[0]
    window = feed.shape[-1] if isinstance(feed.shape[-1], int) else WINDOW
    outputs = [o.name for o in session.get_outputs()]
    wanted = ["scores"] if "scores" in outputs else outputs[:1]
    if "embeddings" in outputs:
        wanted.append("embeddings")

    def run(blob):
        found = session.run(wanted, {feed.name: blob})
        return found[0], (found[1] if len(found) > 1 else None)

    return run, window, f"onnxruntime {ort.__version__}"


def _opencv(model: Path, threads: int):
    try:
        import cv2
        import numpy as np
    except ImportError as error:
        raise NoYamnet("OpenCV is not installed (Debian: apt install python3-opencv)") from error
    try:
        net = cv2.dnn.readNetFromONNX(str(model))
    except cv2.error as error:
        raise NoYamnet(f"OpenCV cannot run the sound model: {str(error).strip()[:160]}") from error
    names = list(net.getUnconnectedOutLayersNames())
    target = "scores" if "scores" in names else names[0]
    lock = threading.Lock()
    both = [target, "embeddings"]
    try:
        net.setInput(np.zeros((1, WINDOW), np.float32))
        net.forward(both)
    except cv2.error:
        both = None

    def run(blob):
        with lock:
            net.setInput(blob)
            if both is None:
                return np.array(net.forward(target)), None
            scores, embedding = net.forward(both)
            return np.array(scores), np.array(embedding)

    return run, WINDOW, f"opencv {cv2.__version__}"


class Yamnet:
    rate = RATE
    hop = HOP

    def __init__(self, run, labels: list[str], window: int, backend: str, path: Path):
        self._run = run
        self.labels = labels
        self.window = int(window)
        self.backend = backend
        self.path = Path(path)
        self._np = _numpy()

    @staticmethod
    def files(folder: Path = MODELS) -> tuple[Path, Path]:
        return Path(folder) / MODEL, Path(folder) / CLASS_MAP

    @classmethod
    def available(cls, folder: Path = MODELS) -> bool:
        model, classes = cls.files(folder)
        if not model.exists() or not classes.exists():
            return False
        if importlib.util.find_spec("numpy") is None:
            return False
        return any(importlib.util.find_spec(name) is not None for name in ("onnxruntime", "cv2"))

    @classmethod
    def load(cls, folder: Path = MODELS, threads: int = 1, backend: str = "auto") -> "Yamnet":
        if backend not in ("auto", "onnxruntime", "opencv"):
            raise NoYamnet(f"unknown backend {backend!r} (auto, onnxruntime or opencv)")
        _numpy()
        model, classes = cls.files(folder)
        if not model.exists():
            raise NoYamnet(f"the sound model is missing ({model}); see tools/export_yamnet.py")
        if not classes.exists():
            raise NoYamnet(f"the class map is missing ({classes}); run python -m pebble.hearing.fetch")
        labels = read_labels(classes)
        reasons = []
        for name, opener in (("onnxruntime", _onnxruntime), ("opencv", _opencv)):
            if backend not in ("auto", name):
                continue
            try:
                run, window, label = opener(model, max(1, int(threads)))
                found = cls(run, labels, window, label, model)
                found._check()
            except NoYamnet as error:
                reasons.append(str(error))
                continue
            log.info("hearing: YAMNet ready (%s, %d sounds, %s)", model.name, len(labels), found.backend)
            return found
        raise NoYamnet("; ".join(reasons))

    def _check(self) -> None:
        out = self._infer(self._np.zeros(self.window, self._np.float32))
        if out.size != len(self.labels):
            raise NoYamnet(f"the sound model gives {out.size} scores but the class map has {len(self.labels)} names")

    def _both(self, values):
        np = self._np
        blob = np.ascontiguousarray(values, dtype=np.float32).reshape(1, self.window)
        scores, embedding = self._run(blob)
        scores = np.asarray(scores, dtype=np.float32).reshape(-1)
        return scores, None if embedding is None else np.asarray(embedding, dtype=np.float32).reshape(-1)

    def _infer(self, values):
        return self._both(values)[0]

    def fit(self, samples):
        np = self._np
        values = _floats(samples, np)
        if values.size >= self.window:
            return values[values.size - self.window:]
        return np.concatenate([values, np.zeros(self.window - values.size, np.float32)])

    def scores(self, samples) -> list[float]:
        return self._infer(self.fit(samples)).tolist()

    def both(self, samples):
        scores, embedding = self._both(self.fit(samples))
        return scores.tolist(), embedding

    def embedding(self, samples):
        return self._both(self.fit(samples))[1]

    def frames(self, samples) -> list[list[float]]:
        np = self._np
        values = _floats(samples, np)
        extra = max(0, values.size - self.window)
        count = 1 + -(-extra // self.hop)
        length = (count - 1) * self.hop + self.window
        if values.size < length:
            values = np.concatenate([values, np.zeros(length - values.size, np.float32)])
        return [self._infer(values[i * self.hop:i * self.hop + self.window]).tolist() for i in range(count)]

    def top(self, scores, n: int = 5) -> list[tuple[int, str, float]]:
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:n]
        return [(i, self.labels[i], float(scores[i])) for i in order]
