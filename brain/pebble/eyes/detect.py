import logging
import math
import threading
from dataclasses import dataclass
from pathlib import Path

from ..seams.sight import DOCK_TAG_ID, DOCK_TAG_SIZE_M, SeenTag
from .fetch import ASSETS, MODELS
from .geometry import Box, focal, tag_angles, wrap
from .labels import COCO_NAMES, PERSON, coco_label

log = logging.getLogger(__name__)

FACE_MIN_OPENCV = (4, 8)
BODY_SIZE = 416
BODY_STRIDES = (8, 16, 32)
BODY_BINS = 8
BODY_MEAN = (103.53, 116.28, 123.675)
BODY_STD = (57.375, 57.12, 58.395)
OPENCV_TAG_TURN = 180.0


class NoOpenCV(RuntimeError):
    pass


def opencv():
    try:
        import cv2
        import numpy
    except ImportError as error:
        raise NoOpenCV("OpenCV for Python is not installed (Debian: apt install python3-opencv; a PC: pip install opencv-python-headless)") from error
    return cv2, numpy


def opencv_version(cv2) -> tuple[int, int]:
    parts = (cv2.__version__.split(".") + ["0", "0"])[:2]
    try:
        return int(parts[0]), int("".join(ch for ch in parts[1] if ch.isdigit()) or 0)
    except ValueError:
        return (0, 0)


def model_path(key: str, models: Path = MODELS) -> Path:
    asset = next(a for a in ASSETS if a.key == key)
    return Path(models) / asset.path


@dataclass(frozen=True)
class Found:
    box: Box
    label: str
    animal: bool
    raw: str


def nms_by_class(cv2, np, rects, confidences, classes, overlap: float) -> list[int]:
    picked: list[int] = []
    for kind in sorted(set(classes)):
        members = [i for i, c in enumerate(classes) if c == kind]
        kept = cv2.dnn.NMSBoxes([rects[i] for i in members], [confidences[i] for i in members], 0.0, overlap)
        picked.extend(members[int(j)] for j in np.array(kept).reshape(-1))
    return picked


@dataclass(frozen=True)
class TagFound:
    seen: SeenTag
    px: float
    roll_deg: float
    error_px: float
    rotation: tuple | None = None
    translation: tuple | None = None


class Detector:
    def __init__(
        self,
        models: Path = MODELS,
        tag_id: int = DOCK_TAG_ID,
        tag_size_m: float = DOCK_TAG_SIZE_M,
        faces: bool = True,
        bodies: bool = True,
        tags: bool = True,
        threads: int = 2,
        face_width: int = 320,
        face_score: float = 0.6,
        body_score: float = 0.4,
        thing_score: float = 0.45,
    ):
        self.cv2, self.np = opencv()
        cv2, np = self.cv2, self.np
        if threads > 0:
            cv2.setNumThreads(int(threads))
        self.tag_id = int(tag_id)
        self.tag_size_m = float(tag_size_m)
        self.face_width = max(80, int(face_width))
        self.face_score = float(face_score)
        self.body_score = float(body_score)
        self.thing_score = float(thing_score)
        self.problems: list[str] = []
        self._face = None
        self._face_size = None
        self.face_marks: list = []
        self._body = None
        self._tags = None
        self._tags_lock = threading.Lock()
        self._legacy_tags = False
        if faces:
            self._face = self._load_face(Path(models))
        if bodies:
            self._body = self._load_body(Path(models))
        if tags:
            self._tags = self._load_tags()
        self._mean = np.array(BODY_MEAN, np.float32)
        self._std = np.array(BODY_STD, np.float32)
        self._anchors = []
        for stride in BODY_STRIDES:
            side = BODY_SIZE // stride
            ys, xs = np.mgrid[0:side, 0:side]
            centres = np.stack([xs.ravel() * stride + 0.5 * (stride - 1), ys.ravel() * stride + 0.5 * (stride - 1)], axis=1).astype(np.float32)
            self._anchors.append(centres)
        self._bins = np.arange(BODY_BINS, dtype=np.float32)
        for problem in self.problems:
            log.warning("eyes: %s", problem)

    @property
    def can(self) -> dict:
        return {"faces": self._face is not None, "bodies": self._body is not None, "tags": self._tags is not None}

    def _load_face(self, models: Path):
        cv2 = self.cv2
        path = model_path("face", models)
        if opencv_version(cv2) < FACE_MIN_OPENCV or not hasattr(cv2, "FaceDetectorYN"):
            self.problems.append(f"faces need OpenCV 4.8 or newer (this is {cv2.__version__}); faces are off")
            return None
        if not path.exists():
            self.problems.append("the face model is missing (python -m pebble.eyes.fetch); faces are off")
            return None
        try:
            return cv2.FaceDetectorYN.create(str(path), "", (320, 240), self.face_score, 0.3, 50)
        except cv2.error as error:
            self.problems.append(f"the face model would not load ({str(error).strip()[:120]}); faces are off")
            return None

    def _load_body(self, models: Path):
        cv2 = self.cv2
        path = model_path("body", models)
        if not path.exists():
            self.problems.append("the person model is missing (python -m pebble.eyes.fetch); bodies are off")
            return None
        try:
            return cv2.dnn.readNet(str(path))
        except cv2.error as error:
            self.problems.append(f"the person model would not load ({str(error).strip()[:120]}); bodies are off")
            return None

    def _load_tags(self):
        cv2 = self.cv2
        aruco = getattr(cv2, "aruco", None)
        if aruco is None or not hasattr(aruco, "DICT_APRILTAG_36h11"):
            self.problems.append("this OpenCV has no AprilTag support (cv2.aruco); dock tags are off")
            return None
        dictionary = aruco.getPredefinedDictionary(aruco.DICT_APRILTAG_36h11)
        if hasattr(aruco, "ArucoDetector"):
            params = aruco.DetectorParameters()
            params.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
            return aruco.ArucoDetector(dictionary, params)
        params = aruco.DetectorParameters_create()
        params.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
        self._legacy_tags = True
        return (dictionary, params)

    def faces(self, image) -> list[Box]:
        if self._face is None:
            return []
        cv2 = self.cv2
        h, w = image.shape[:2]
        k = min(1.0, self.face_width / w)
        small = cv2.resize(image, (max(1, round(w * k)), max(1, round(h * k))), interpolation=cv2.INTER_AREA) if k < 1 else image
        sh, sw = small.shape[:2]
        if self._face_size != (sw, sh):
            self._face.setInputSize((sw, sh))
            self._face_size = (sw, sh)
        _, found = self._face.detect(small)
        self.face_marks = []
        if found is None:
            return []
        out = []
        for row in found:
            x, y, bw, bh = (float(v) for v in row[:4])
            x0, y0 = max(0.0, x / sw), max(0.0, y / sh)
            out.append(Box(x0, y0, min(1 - x0, bw / sw), min(1 - y0, bh / sh), float(row[14])))
            self.face_marks.append(tuple((float(row[4 + 2 * i]) / sw, float(row[5 + 2 * i]) / sh) for i in range(5)))
        return out

    def objects(self, image) -> tuple[list[Box], list[Found]]:
        if self._body is None:
            return [], []
        cv2, np = self.cv2, self.np
        h, w = image.shape[:2]
        k = min(BODY_SIZE / w, BODY_SIZE / h)
        rw, rh = max(1, round(w * k)), max(1, round(h * k))
        canvas = np.zeros((BODY_SIZE, BODY_SIZE, 3), np.float32)
        canvas[:rh, :rw] = (cv2.resize(image, (rw, rh), interpolation=cv2.INTER_AREA).astype(np.float32) - self._mean) / self._std
        self._body.setInput(cv2.dnn.blobFromImage(canvas))
        outs = self._body.forward(self._body.getUnconnectedOutLayersNames())
        scores = {o.shape[-2]: o.reshape(-1, o.shape[-1]) for o in outs if o.shape[-1] == len(COCO_NAMES)}
        boxes = {o.shape[-2]: o.reshape(-1, o.shape[-1]) for o in outs if o.shape[-1] == 4 * BODY_BINS}
        floor = min(self.body_score, self.thing_score)
        rects, confidences, classes = [], [], []
        for stride, anchors in zip(BODY_STRIDES, self._anchors):
            n = anchors.shape[0]
            if n not in scores or n not in boxes:
                continue
            best = scores[n].argmax(axis=1)
            top = scores[n][np.arange(n), best]
            keep = np.nonzero(top > floor)[0]
            if keep.size == 0:
                continue
            raw = boxes[n][keep].reshape(-1, 4, BODY_BINS)
            raw = np.exp(raw - raw.max(axis=2, keepdims=True))
            dist = (raw / raw.sum(axis=2, keepdims=True)) @ self._bins * stride
            centre = anchors[keep]
            x1 = np.clip(centre[:, 0] - dist[:, 0], 0, rw)
            y1 = np.clip(centre[:, 1] - dist[:, 1], 0, rh)
            x2 = np.clip(centre[:, 0] + dist[:, 2], 0, rw)
            y2 = np.clip(centre[:, 1] + dist[:, 3], 0, rh)
            for i in range(keep.size):
                kind = int(best[keep[i]])
                score = float(top[keep[i]])
                if score < (self.body_score if kind == PERSON else self.thing_score):
                    continue
                rects.append([float(x1[i]), float(y1[i]), float(x2[i] - x1[i]), float(y2[i] - y1[i])])
                confidences.append(score)
                classes.append(kind)
        people: list[Box] = []
        things: list[Found] = []
        for i in nms_by_class(cv2, np, rects, confidences, classes, 0.5):
            x, y, bw, bh = rects[i]
            x0, y0 = x / rw, y / rh
            box = Box(x0, y0, min(1 - x0, bw / rw), min(1 - y0, bh / rh), confidences[i])
            if classes[i] == PERSON:
                people.append(box)
                continue
            label, animal = coco_label(classes[i])
            if label is not None:
                things.append(Found(box, label, animal, COCO_NAMES[classes[i]]))
        return people, things

    def bodies(self, image) -> list[Box]:
        return self.objects(image)[0]

    def tags(self, image, fov_h_deg: float) -> list[TagFound]:
        if self._tags is None:
            return []
        cv2, np = self.cv2, self.np
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        with self._tags_lock:
            if self._legacy_tags:
                corners, ids, _ = cv2.aruco.detectMarkers(gray, self._tags[0], parameters=self._tags[1])
            else:
                corners, ids, _ = self._tags.detectMarkers(gray)
        if ids is None:
            return []
        h, w = gray.shape[:2]
        f = focal(w, fov_h_deg)
        camera = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], np.float64)
        half = self.tag_size_m / 2
        square = np.array([[-half, half, 0], [half, half, 0], [half, -half, 0], [-half, -half, 0]], np.float64)
        out = []
        for quad, tag_id in zip(corners, ids.reshape(-1)):
            if int(tag_id) != self.tag_id:
                continue
            points = quad.reshape(4, 2).astype(np.float64)
            try:
                found, rvecs, tvecs, errors = cv2.solvePnPGeneric(square, points, camera, None, flags=cv2.SOLVEPNP_IPPE_SQUARE)
            except cv2.error:
                continue
            if not found:
                continue
            poses, rotations = [], []
            for rvec, tvec in zip(rvecs, tvecs):
                rotation, _ = cv2.Rodrigues(rvec)
                rotations.append(rotation)
                poses.append(tag_angles(tvec.reshape(3), rotation[:, 2]))
            bearing, distance, yaw = poses[0]
            errs = [float(e) for e in np.array(errors).reshape(-1)] if errors is not None else []
            px = float(np.mean([np.linalg.norm(points[i] - points[(i + 1) % 4]) for i in range(4)]))
            score = max(0.05, min(1.0, (px - 20) / 60))
            if len(poses) > 1 and len(errs) > 1 and abs(wrap(poses[1][2] - yaw)) > 8 and errs[1] > 0:
                score *= max(0.05, min(1.0, 1 - errs[0] / errs[1]))
            top = points[1] - points[0]
            roll = wrap(math.degrees(math.atan2(top[1], top[0])) - OPENCV_TAG_TURN)
            seen = SeenTag(id=int(tag_id), bearing_deg=round(bearing, 2), distance_m=round(distance, 4), yaw_deg=round(yaw, 2), score=round(score, 3))
            pose = (tuple(float(x) for x in rotations[0].reshape(-1)), tuple(float(x) for x in np.asarray(tvecs[0]).reshape(3)))
            out.append(TagFound(seen, px, roll, errs[0] if errs else 0.0, *pose))
        return out
