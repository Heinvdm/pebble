import logging
import math
from pathlib import Path

from ..seams.sight import BODY_POINTS, BodyPoint
from .detect import opencv
from .geometry import Box, angles

log = logging.getLogger(__name__)

INPUT = (192, 256)
PADDING = 1.25
SPLIT = 2.0
MEAN = (123.675, 116.28, 103.53)
STD = (58.395, 57.12, 57.375)
SEEN = 0.3
INDEX = {name: i for i, name in enumerate(BODY_POINTS)}


class NoPoseModel(RuntimeError):
    pass


class PoseModel:
    def __init__(self, path: Path, backend: str = "auto", threads: int = 1):
        self.cv2, self.np = opencv()
        path = Path(path)
        if not path.exists():
            raise NoPoseModel(f"the pose model is missing ({path.name}); run python -m pebble.eyes.fetch")
        self._session = None
        self._net = None
        if backend in ("auto", "onnxruntime"):
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
                if backend == "onnxruntime":
                    raise NoPoseModel("onnxruntime is not installed")
        if self._session is None:
            try:
                self._net = self.cv2.dnn.readNetFromONNX(str(path))
            except self.cv2.error as error:
                raise NoPoseModel(f"OpenCV cannot run the pose model: {str(error).strip()[:160]}") from error
            self.backend = f"opencv {self.cv2.__version__}"
        np = self.np
        self._mean = np.array(MEAN, np.float32)
        self._std = np.array(STD, np.float32)

    def _run(self, blob):
        if self._session is not None:
            return self._session.run(None, {self._input: blob})
        self._net.setInput(blob)
        return self._net.forward(self._net.getUnconnectedOutLayersNames())

    def points(self, image, box: Box):
        cv2, np = self.cv2, self.np
        h, w = image.shape[:2]
        x0, y0, x1, y1 = box.x * w, box.y * h, (box.x + box.w) * w, (box.y + box.h) * h
        centre = np.array([(x0 + x1) / 2, (y0 + y1) / 2], np.float32)
        bw, bh = (x1 - x0) * PADDING, (y1 - y0) * PADDING
        aspect = INPUT[0] / INPUT[1]
        if bw > bh * aspect:
            bh = bw / aspect
        else:
            bw = bh * aspect
        scale = np.array([bw, bh], np.float32)
        k = INPUT[0] / bw
        warp = np.array([[k, 0.0, INPUT[0] / 2 - k * centre[0]], [0.0, k, INPUT[1] / 2 - k * centre[1]]], np.float32)
        crop = cv2.warpAffine(image, warp, INPUT, flags=cv2.INTER_LINEAR)
        blob = ((crop[:, :, ::-1].astype(np.float32) - self._mean) / self._std).transpose(2, 0, 1)[None]
        simcc_x, simcc_y = self._run(np.ascontiguousarray(blob))[:2]
        sx, sy = simcc_x.reshape(len(BODY_POINTS), -1), simcc_y.reshape(len(BODY_POINTS), -1)
        px = sx.argmax(axis=1) / SPLIT
        py = sy.argmax(axis=1) / SPLIT
        score = np.minimum(sx.max(axis=1), sy.max(axis=1))
        ux = px / INPUT[0] * scale[0] + centre[0] - scale[0] / 2
        uy = py / INPUT[1] * scale[1] + centre[1] - scale[1] / 2
        return np.stack([ux / w, uy / h, score], axis=1)


def body_points(raw, width: int, height: int, fov_h_deg: float) -> tuple[BodyPoint, ...]:
    out = []
    for name, (u, v, score) in zip(BODY_POINTS, raw):
        bearing, elevation = angles(float(u), float(v), width, height, fov_h_deg)
        out.append(BodyPoint(name, round(bearing, 2), round(elevation, 2), round(float(max(0.0, min(1.0, score))), 3)))
    return tuple(out)


def facing(raw, seen: float = SEEN) -> float | None:
    def point(name):
        u, v, s = raw[INDEX[name]]
        return (float(u), float(v)) if s >= seen else None

    nose, left_eye, right_eye = point("nose"), point("left_eye"), point("right_eye")
    left_ear, right_ear = point("left_ear"), point("right_ear")
    left_shoulder, right_shoulder = point("left_shoulder"), point("right_shoulder")
    if nose is None and left_eye is None and right_eye is None:
        if left_shoulder and right_shoulder or left_ear or right_ear:
            return 180.0
        return None
    if left_ear and right_ear and nose:
        middle, half = (left_ear[0] + right_ear[0]) / 2, abs(left_ear[0] - right_ear[0]) / 2
        if half > 1e-4:
            return round(math.degrees(math.atan2(nose[0] - middle, half)), 1)
    if left_eye and right_eye and nose:
        middle, half = (left_eye[0] + right_eye[0]) / 2, abs(left_eye[0] - right_eye[0]) / 2
        if half > 1e-4:
            return round(max(-80.0, min(80.0, math.degrees(math.atan2(nose[0] - middle, half * 1.6)))), 1)
    if nose and (left_ear or right_ear):
        ear = left_ear or right_ear
        return 70.0 if nose[0] > ear[0] else -70.0
    return None


def wrists(raw, seen: float = SEEN) -> list[tuple[float, float, float]]:
    out = []
    for hand, elbow in (("left_wrist", "left_elbow"), ("right_wrist", "right_elbow")):
        wu, wv, ws = raw[INDEX[hand]]
        if ws < seen:
            continue
        eu, ev, es = raw[INDEX[elbow]]
        reach = math.hypot(float(wu - eu), float(wv - ev)) if es >= seen else 0.0
        out.append((float(wu), float(wv), reach))
    return out


def held_by(box: Box, hands, aspect: float) -> bool:
    for u, v, reach in hands:
        margin = max(0.3 * max(box.w, box.h), 0.5 * reach)
        dx = max(box.x - u, 0.0, u - (box.x + box.w))
        dy = max(box.y - v, 0.0, v - (box.y + box.h)) / max(aspect, 1e-6)
        if math.hypot(dx, dy) <= margin:
            return True
    return False
