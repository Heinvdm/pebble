import json
import logging
import math
import threading
from pathlib import Path

from .detect import opencv
from .geometry import Box

log = logging.getLogger(__name__)

SIZE = 140
SCREEN = 112
MARGIN = 0.08
BATCH = 16
MAX_VIEWS = 8
MATCH = 0.75
DOCK_RIGHT = (-0.102, 0.102)
DOCK_UP = (-0.120, 0.036)
DOCK_OUT = (-0.0084, 0.1056)
MIN_SIDE_PX = 24
MIN_INSIDE = 0.8


class NoPrintModel(RuntimeError):
    pass


class PrintModel:
    def __init__(self, path: Path, meta: Path | None = None, threads: int = 2, size: int = SIZE):
        self.cv2, self.np = opencv()
        path = Path(path)
        if not path.exists():
            raise NoPrintModel(f"the print model is missing ({path.name}); tools/export_prints.py makes it")
        try:
            import onnxruntime as ort
        except ImportError as error:
            raise NoPrintModel("prints need onnxruntime (Debian: apt install python3-onnxruntime)") from error
        info = json.loads(Path(meta).read_text(encoding="utf-8")) if meta and Path(meta).exists() else {}
        np = self.np
        self.mean = np.array(info.get("mean", (0.485, 0.456, 0.406)), np.float32)
        self.std = np.array(info.get("std", (0.229, 0.224, 0.225)), np.float32)
        self.size = int(size)
        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, int(threads))
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self._session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
        self.backend = f"onnxruntime {ort.__version__}"
        self._lock = threading.Lock()

    def crops(self, image, boxes: list[Box], size: int):
        cv2, np = self.cv2, self.np
        h, w = image.shape[:2]
        out = []
        for box in boxes:
            mx, my = box.w * MARGIN, box.h * MARGIN
            x0, y0 = max(0, int((box.x - mx) * w)), max(0, int((box.y - my) * h))
            x1, y1 = min(w, int(math.ceil((box.x + box.w + mx) * w))), min(h, int(math.ceil((box.y + box.h + my) * h)))
            if x1 - x0 < 2 or y1 - y0 < 2:
                x0, y0, x1, y1 = 0, 0, 2, 2
            part = image[y0:y1, x0:x1]
            shrink = part.shape[0] > size or part.shape[1] > size
            part = cv2.resize(part, (size, size), interpolation=cv2.INTER_AREA if shrink else cv2.INTER_LINEAR)
            out.append(((part[:, :, ::-1].astype(np.float32) / 255.0 - self.mean) / self.std).transpose(2, 0, 1))
        return out

    def embed(self, image, boxes: list[Box], size: int | None = None):
        np = self.np
        if not boxes:
            return np.zeros((0, 384), np.float32)
        crops = self.crops(image, boxes, size or self.size)
        parts = []
        for start in range(0, len(crops), BATCH):
            with self._lock:
                cls, _ = self._session.run(None, {"pixels": np.stack(crops[start:start + BATCH])})
            parts.append(cls)
        vecs = np.concatenate(parts, axis=0)
        return vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9)


class PrintBook:
    def __init__(self, max_views: int = MAX_VIEWS, match: float = MATCH):
        import numpy as np

        self.np = np
        self.max_views = max_views
        self.match = match
        self._views: dict[str, list] = {}
        self._lock = threading.Lock()

    def remember(self, key: str, vec, replace: bool = False) -> int:
        np = self.np
        v = np.asarray(vec, np.float32).reshape(-1)
        norm = float(np.linalg.norm(v))
        if v.size == 0 or not math.isfinite(norm) or norm == 0:
            raise ValueError("a print must be a non-empty vector of numbers")
        v = v / norm
        with self._lock:
            views = [] if replace else list(self._views.get(key, []))
            if views and views[0].size != v.size:
                raise ValueError(f"this print has {v.size} numbers, but {key!r} has {views[0].size}")
            views.append(v)
            self._views[key] = views[-self.max_views:]
            return len(self._views[key])

    def forget(self, key: str) -> bool:
        with self._lock:
            return self._views.pop(key, None) is not None

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._views)

    def __bool__(self) -> bool:
        with self._lock:
            return bool(self._views)

    def scores(self, key: str, vecs):
        np = self.np
        with self._lock:
            views = list(self._views.get(key, []))
        if not views or len(vecs) == 0 or views[0].size != vecs.shape[1]:
            return np.zeros(len(vecs), np.float32)
        vecs = np.asarray(vecs, np.float32)
        vecs = vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9)
        return (vecs @ np.stack(views).T).max(axis=1)

    def best(self, vecs) -> list[tuple[str | None, float]]:
        np = self.np
        out = [(None, 0.0)] * len(vecs)
        for key in self.keys():
            scores = self.scores(key, vecs)
            out = [(key, float(s)) if s > score else (name, score) for (name, score), s in zip(out, scores)]
        return out


def dock_box(rotation, translation, width: int, height: int, fov_h_deg: float) -> Box | None:
    import numpy as np

    f = (width / 2) / math.tan(math.radians(fov_h_deg) / 2)
    rotation = np.asarray(rotation, np.float64).reshape(3, 3)
    t = np.asarray(translation, np.float64).reshape(3)
    right, up, out = -rotation[:, 0], -rotation[:, 1], rotation[:, 2]
    if out @ t > 0:
        right, up, out = -right, -up, -out
    corners = np.array([t + a * right + b * up + c * out for a in DOCK_RIGHT for b in DOCK_UP for c in DOCK_OUT])
    if (corners[:, 2] <= 0.02).any():
        return None
    u = width / 2 + f * corners[:, 0] / corners[:, 2]
    v = height / 2 + f * corners[:, 1] / corners[:, 2]
    x0, x1, y0, y1 = u.min(), u.max(), v.min(), v.max()
    area = (x1 - x0) * (y1 - y0)
    inside = max(0.0, min(x1, width) - max(x0, 0)) * max(0.0, min(y1, height) - max(y0, 0))
    if area <= 0 or inside / area < MIN_INSIDE or min(x1 - x0, y1 - y0) < MIN_SIDE_PX:
        return None
    x0, y0 = max(0.0, x0), max(0.0, y0)
    x1, y1 = min(float(width), x1), min(float(height), y1)
    return Box(x0 / width, y0 / height, (x1 - x0) / width, (y1 - y0) / height, 1.0)


def grid(aspect: float = 1.2, frame_aspect: float = 4 / 3) -> list[Box]:
    out = []
    for height in (0.2, 0.32):
        width = height * aspect / frame_aspect
        step_x, step_y = width * 0.6, height * 0.6
        y = 0.25
        while y + height <= 0.95:
            x = 0.0
            while x + width <= 1.0 + 1e-9:
                out.append(Box(x, y, width, height, 0.0))
                x += step_x
            y += step_y
    return out


def unique(boxes: list[Box]) -> list[Box]:
    out: list[Box] = []
    for box in boxes:
        if box.w <= 0.005 or box.h <= 0.005:
            continue
        if any(abs(box.x - b.x) < 0.01 and abs(box.y - b.y) < 0.01 and abs(box.w - b.w) < 0.01 and abs(box.h - b.h) < 0.01 for b in out):
            continue
        out.append(box)
    return out


def around(box: Box) -> list[Box]:
    out = []
    for scale, dx, dy in ((0.85, 0, 0), (1.2, 0, 0), (1.0, -0.12, 0), (1.0, 0.12, 0), (1.0, 0, -0.12), (1.0, 0, 0.12), (0.85, 0, 0.08), (1.2, 0, -0.08)):
        w, h = box.w * scale, box.h * scale
        x = box.cx - w / 2 + dx * box.w
        y = box.cy - h / 2 + dy * box.h
        x0, y0 = max(0.0, x), max(0.0, y)
        out.append(Box(x0, y0, min(1.0, x + w) - x0, min(1.0, y + h) - y0, 0.0))
    return out


def find(model: PrintModel, book: PrintBook, key: str, image, proposals: list[Box], frame_aspect: float = 4 / 3, top: int = 3):
    np = model.np
    boxes = unique(list(proposals) + grid(frame_aspect=frame_aspect))
    if not boxes:
        return None
    rough = book.scores(key, model.embed(image, boxes, SCREEN))
    picked = [boxes[i] for i in np.argsort(-rough)[:top]]
    candidates = picked + around(picked[0])
    fine = book.scores(key, model.embed(image, candidates, SIZE))
    best = int(np.argmax(fine))
    return candidates[best], float(fine[best]), len(boxes) + len(candidates)
