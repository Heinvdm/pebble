import asyncio
import base64
import binascii
import itertools
import json
import logging
import math
import threading
from collections import deque
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable

from ..clock import Clock
from ..seams.sight import CAMERAS, DOCK_TAG_ID, DOCK_TAG_SIZE_M, FloorRay, SeenPerson, SeenTag, SeenThing, Sight
from .fetch import MODELS
from .floor import BINS as FLOOR_BINS
from .floor import EVERY_S as FLOOR_EVERY_S
from .floor import KEEP_S as FLOOR_KEEP_S
from .floor import REACH_M as FLOOR_REACH_M
from .floor import cut
from .geometry import Box, Candidate, Tracker, angles, combine, floor_point, nearest, seen_people, tag_angles, wrap
from .hazards import CLOSE_EVERY_S, SMALL, HazardWatch, cells
from .labels import PERSON, coco_label
from .service import MOTION_SIZE, TILT_REST_DEG, camera_settings
from .slow import SlowFound
from .speaking import MAX_FACES, MIN_FACE_PX, TAIL_S, SpeakingMeter
from .things import Thing, merge, overlap, seen_things

log = logging.getLogger(__name__)

STALE_S = 1.5
BODY_KEEP_S = 1.2
SWITCH_TIMEOUT_S = 12.0
LOOK_CLOSELY_S = 6.0
MAX_ITEMS = 64
POSE_KEEP_S = 0.6
POSE_MATCH = 0.5
POINTS = 17
KNOWN_MAX = 6
SNAPSHOT_S = 1.0
PRINT_SIZE = 140
PROPOSE_SCORE = 0.1
SLOW_DEFAULTS = {"slow": True, "slow_every_s": 1.0, "slow_keep_s": 3.0, "slow_change": 0.06, "slow_score": 0.45, "slow_threads": 1}
HAZARD_DEFAULTS = {"hazards": True, "hazard_every_s": 3.0, "hazard_score": 0.25, "hazard_threads": 1}
SPEAKING_DEFAULTS = {"speaking": True, "speaking_gate": "voice", "speaking_faces": MAX_FACES}
FLOOR_DEFAULTS = {"floor": True, "floor_every_s": FLOOR_EVERY_S, "floor_reach_m": FLOOR_REACH_M, "floor_bins": FLOOR_BINS, "floor_gate": "moving", "floor_threads": 2}
FLOOR_GATES = ("moving", "always", "off")
MOVING_TAIL_S = 1.0
MAX_RAYS = 256
PLACE_BOXES = (Box(0.0, 0.0, 1.0, 1.0, 1.0),) + tuple(Box(x, y, 0.5, 0.5, 1.0) for y in (0.0, 0.5) for x in (0.0, 0.5))
HAZARD_CONTEXT = 32
LOOKALIKE_OVERLAP = 0.4


@dataclass(frozen=True)
class SlowResult:
    camera: str
    captured: float
    at: float
    width: int
    height: int
    found: tuple


@dataclass(frozen=True)
class Snap:
    camera: str
    captured: float
    at: float
    fov: float
    width: int
    height: int
    people: dict
    things: tuple


def _number(value, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _box(row) -> Box | None:
    if not isinstance(row, (list, tuple)) or len(row) < 5:
        return None
    x, y, w, h, score = (_number(v) for v in row[:5])
    x0, y0 = max(0.0, min(1.0, x)), max(0.0, min(1.0, y))
    w, h = max(0.0, min(1.0 - x0, w)), max(0.0, min(1.0 - y0, h))
    if w <= 0 or h <= 0:
        return None
    return Box(x0, y0, w, h, max(0.0, min(1.0, score)))


def _rows(data, key: str) -> list:
    rows = data.get(key) if isinstance(data, dict) else None
    return rows[:MAX_ITEMS] if isinstance(rows, list) else []


def _points(raw) -> list | None:
    if not isinstance(raw, list) or len(raw) != POINTS * 3:
        return None
    values = [_number(v) for v in raw]
    return [tuple(values[i * 3:i * 3 + 3]) for i in range(POINTS)]


def glow_grid(text) -> bytes | None:
    if not isinstance(text, str):
        return None
    try:
        grid = base64.b64decode(text)
    except (binascii.Error, ValueError):
        return None
    return grid if len(grid) == SMALL[0] * SMALL[1] else None


def glow_level(grid: bytes, box: Box) -> float | None:
    width, height = SMALL
    x0, y0, x1, y1 = cells(box)
    x1, y1 = min(x1, width), min(y1, height)
    if x1 <= x0 or y1 <= y0:
        return None
    total = sum(sum(grid[y * width + x0:y * width + x1]) for y in range(y0, y1))
    return total / ((x1 - x0) * (y1 - y0))


class HazardRows:
    def __init__(self, classes: list):
        self.classes = classes
        self.found: list = []

    def detect(self, image, score: float | None = None) -> list:
        return list(self.found)


def tag_seen(tag_id: int, poses: list, px: float) -> SeenTag | None:
    solved = []
    for pose in poses[:2]:
        if not isinstance(pose, dict):
            continue
        t, n = pose.get("t"), pose.get("n")
        if not isinstance(t, list) or not isinstance(n, list) or len(t) != 3 or len(n) != 3:
            continue
        solved.append((tag_angles([_number(v) for v in t], [_number(v) for v in n]), _number(pose.get("err"))))
    if not solved:
        return None
    (bearing, distance, yaw), first_error = solved[0]
    if distance <= 0:
        return None
    score = max(0.05, min(1.0, (px - 20) / 60))
    if len(solved) > 1:
        other_yaw, other_error = solved[1][0][2], solved[1][1]
        if abs(wrap(other_yaw - yaw)) > 8 and other_error > 0:
            score *= max(0.05, min(1.0, 1 - first_error / other_error))
    return SeenTag(id=int(tag_id), bearing_deg=round(bearing, 2), distance_m=round(distance, 4), yaw_deg=round(yaw, 2), score=round(score, 3))


def load_words(path: Path | None) -> dict:
    if path is None or not Path(path).exists():
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        log.warning("eyes: the slow-lane words cannot be read (%s); the slow lane names nothing", error)
        return {}
    return data if isinstance(data, dict) and isinstance(data.get("classes"), list) else {}


def print_book():
    try:
        from .prints import PrintBook

        return PrintBook()
    except ImportError as error:
        log.warning("eyes: prints need numpy (%s); Pebble cannot learn what things look like", error)
        return None


class HeldPicture:
    def __init__(self, bridge, held: dict):
        import numpy

        self.np = numpy
        self.bridge = bridge
        self.id = int(held["id"])
        self.width = int(held.get("w", 0))
        self.height = int(held.get("h", 0))
        self.camera = held.get("camera")
        self.fov = _number(held.get("fov"), 65.0)
        self.tags = held.get("tags") or []

    def embed(self, image, boxes: list[Box], size: int | None = None):
        np = self.np
        if not boxes:
            return np.zeros((0, 384), np.float32)
        text = self.bridge.eyesEmbed(self.id, json.dumps([[b.x, b.y, b.w, b.h] for b in boxes]), int(size or PRINT_SIZE))
        vecs = json.loads(str(text))
        if len(vecs) != len(boxes):
            raise RuntimeError("the phone gave back the wrong number of prints")
        return np.asarray(vecs, np.float32)

    def propose(self, score: float = PROPOSE_SCORE) -> list[Box]:
        rows = json.loads(str(self.bridge.eyesPropose(self.id, float(score))))
        return [b for b in (_box(r) for r in rows[:MAX_ITEMS]) if b is not None]

    def release(self) -> None:
        try:
            self.bridge.eyesRelease(self.id)
        except Exception:
            pass


class PhoneFloor:
    def __init__(self, monotonic: Callable[[], float], every_s: float = FLOOR_EVERY_S, keep_s: float = FLOOR_KEEP_S, bins: int = FLOOR_BINS, reach_m: float = FLOOR_REACH_M, gate: str = "moving"):
        self.monotonic = monotonic
        self.every_s = float(every_s)
        self.keep_s = float(keep_s)
        self.bins = int(bins)
        self.reach_m = float(reach_m)
        self.gate = gate
        self.problem = ""
        self.passes = 0
        self.last_ms = 0.0
        self.quality = 0.0
        self._moving = False
        self._moving_until = -1e9
        self._lock = threading.Lock()
        self._result = None

    def set_moving(self, on: bool) -> None:
        self._moving = bool(on)
        if not on:
            self._moving_until = self.monotonic() + MOVING_TAIL_S

    def moving(self) -> bool:
        return self._moving or self.monotonic() < self._moving_until

    def forget(self) -> None:
        with self._lock:
            self._result = None

    def took(self, camera: str, captured: float, at: float, rays: tuple, quality: float, ms: float) -> None:
        with self._lock:
            self._result = (camera, captured, at, rays)
            self.passes += 1
            self.quality = quality
            self.last_ms = ms
            self.problem = ""

    def current(self, camera: str, now: float):
        with self._lock:
            result = self._result
        if result is None or result[0] != camera or now - result[1] > self.keep_s:
            return (), None
        return result[3], result[2]

    def status(self) -> dict:
        return {"gate": self.gate, "moving": self.moving(), "passes": self.passes, "ms": round(self.last_ms, 1), "quality": round(self.quality, 2), "problem": self.problem, "reach_m": self.reach_m}


class PhoneMouths:
    backend = "phone"

    def __init__(self):
        self.shapes: dict = {}

    def read(self, image, box, row):
        return self.shapes.get(row)


class AndroidEyes:
    def __init__(
        self,
        clock: Clock | None = None,
        cameras: dict | None = None,
        camera: str = "front",
        enabled: bool = True,
        tag_id: int = DOCK_TAG_ID,
        tag_size_m: float = DOCK_TAG_SIZE_M,
        max_fps: float = 10.0,
        slow: dict | None = None,
        words: dict | None = None,
        on_look: Callable[[SeenPerson | None], None] | None = None,
        on_camera: Callable[[str | None], None] | None = None,
        tags_on: tuple[str, ...] = ("rear",),
        people_on: tuple[str, ...] = CAMERAS,
        switch_timeout_s: float = SWITCH_TIMEOUT_S,
        stale_s: float = STALE_S,
        detect: dict | None = None,
        bridge=None,
        hazards: dict | None = None,
        hazard_words: dict | None = None,
        speaking: dict | None = None,
        floor: dict | None = None,
    ):
        self.clock = clock or Clock()
        self.cameras = camera_settings(cameras)
        self.hazard_settings = {**HAZARD_DEFAULTS, **(hazards or {})}
        if hazard_words is None:
            hazard_words = load_words(MODELS / "hazards_vocab.json") if self.hazard_settings.get("hazards") else {}
        self.hazard_words = hazard_words
        self.hazard_classes = self.hazard_words.get("classes") or []
        self._hazard_rows = HazardRows(self.hazard_classes)
        self.hazards = self._watch()
        self._hazard_lock = threading.Lock()
        self._hazard_every: float | None = None
        self._recent: deque = deque(maxlen=HAZARD_CONTEXT)
        self.speaking_settings = {**SPEAKING_DEFAULTS, **(speaking or {})}
        self._mouths = PhoneMouths()
        self.speaking = self._meter()
        self.floor_settings = {**FLOOR_DEFAULTS, **(floor or {})}
        self.floor = self._floor()
        self._motion: dict | None = None
        self._head_told: dict | None = None
        self._tilt = TILT_REST_DEG
        self._roll = 0.0
        self.tag_id = int(tag_id)
        self.tag_size_m = float(tag_size_m)
        self.max_fps = max(1.0, min(30.0, float(max_fps)))
        self.slow_settings = {**SLOW_DEFAULTS, **(slow or {})}
        self.words = words or {}
        self.classes = self.words.get("classes") or []
        self.coco_depth = {str(k): int(v) for k, v in (self.words.get("coco_depth") or {}).items()}
        self.detect = dict(detect or {})
        self.on_look = on_look
        self.on_camera = on_camera
        self.tags_on = tuple(tags_on)
        self.people_on = tuple(people_on)
        self.switch_timeout_s = switch_timeout_s
        self.stale_s = stale_s
        self._bridge = bridge
        self._lock = threading.Lock()
        self._enabled = bool(enabled)
        self._want = camera if camera in CAMERAS else "front"
        self._camera: str | None = None
        self._latest: Sight | None = None
        self._latest_mono = -math.inf
        self._waiters: list[tuple[str, asyncio.Future, asyncio.AbstractEventLoop]] = []
        self._demands: dict[int, tuple[asyncio.Future, asyncio.AbstractEventLoop]] = {}
        self._demand_ids = itertools.count(1)
        ids = itertools.count(1)
        self._tracker = Tracker(ids=ids)
        self._thing_tracker = Tracker(ids=ids)
        self._slow_tracker = Tracker(ids=ids, keep_s=10.0)
        self._bodies: list[Box] = []
        self._bodies_at = -math.inf
        self._fast_things: list[Thing] = []
        self._fast_camera: str | None = None
        self._slow_result: SlowResult | None = None
        self._slow_used: SlowResult | None = None
        self._slow_things: list[Thing] = []
        self._poses: dict = {}
        self._snap: Snap | None = None
        self.book = print_book()
        self._look_track: int | None = None
        self._looking = False
        self._marked: str | None = None
        self._started = False
        self._fps = 0.0
        self._last_frame: float | None = None
        self._ms: dict = {}
        self._phone: dict = {}
        self.frames = 0
        self.slow_passes = 0
        self.problem = ""
        self._private = False
        self._keep: frozenset = frozenset()
        self._undress: tuple | None = None
        self.private_frames = 0
        self.snapshot_veto = None
        self.on_cue = None

    def bridge(self):
        if self._bridge is not None:
            return self._bridge
        from ..android.bridge import require

        return require("the phone's cameras")

    def _watch(self) -> HazardWatch | None:
        if not self.hazard_settings.get("hazards") or not self.hazard_classes:
            return None
        rows = self._hazard_rows
        watch = HazardWatch(lambda: rows, self.clock.monotonic, every_s=_number(self.hazard_settings.get("hazard_every_s"), HAZARD_DEFAULTS["hazard_every_s"]), nice=0)
        watch.detector = rows
        return watch

    def _meter(self) -> SpeakingMeter | None:
        if not self.speaking_settings.get("speaking"):
            return None
        gate = "always" if str(self.speaking_settings.get("speaking_gate")) == "always" else "voice"
        faces = max(1, int(_number(self.speaking_settings.get("speaking_faces"), MAX_FACES)))
        mouths = self._mouths
        return SpeakingMeter(lambda: mouths, gate=gate, max_faces=faces, monotonic=self.clock.monotonic)

    def _floor(self) -> PhoneFloor | None:
        if not self.floor_settings.get("floor"):
            return None
        gate = str(self.floor_settings.get("floor_gate"))
        return PhoneFloor(
            self.clock.monotonic,
            every_s=_number(self.floor_settings.get("floor_every_s"), FLOOR_EVERY_S),
            bins=int(_number(self.floor_settings.get("floor_bins"), FLOOR_BINS)),
            reach_m=_number(self.floor_settings.get("floor_reach_m"), FLOOR_REACH_M),
            gate=gate if gate in FLOOR_GATES else "moving",
        )

    def _heads(self) -> dict:
        return {name: list(self.head(name)) for name in CAMERAS}

    def config(self) -> dict:
        return {
            "camera": self._want,
            "enabled": self._enabled,
            "cameras": self.cameras,
            "tag_id": self.tag_id,
            "tag_size_m": self.tag_size_m,
            "max_fps": self.max_fps,
            "tags_on": list(self.tags_on),
            "people_on": list(self.people_on),
            "slow": {
                "on": bool(self.slow_settings.get("slow")) and bool(self.classes),
                "every_s": _number(self.slow_settings.get("slow_every_s"), 1.0),
                "change": _number(self.slow_settings.get("slow_change"), 0.06),
                "score": _number(self.slow_settings.get("slow_score"), 0.45),
                "threads": int(_number(self.slow_settings.get("slow_threads"), 1)),
                "classes": len(self.classes),
            },
            "detect": {**self.detect, "prints": bool(self.detect.get("prints", True)) and self.book is not None},
            "hazards": {
                "on": self.hazards is not None,
                "every_s": self.hazards.every_s if self.hazards is not None else HAZARD_DEFAULTS["hazard_every_s"],
                "score": _number(self.hazard_settings.get("hazard_score"), HAZARD_DEFAULTS["hazard_score"]),
                "threads": int(_number(self.hazard_settings.get("hazard_threads"), 1)),
                "classes": len(self.hazard_classes),
            },
            "speaking": {
                "on": self.speaking is not None,
                "faces": self.speaking.max_faces if self.speaking is not None else MAX_FACES,
                "min_face_px": self.speaking.min_face_px if self.speaking is not None else MIN_FACE_PX,
            },
            "floor": {
                "on": self.floor is not None,
                "every_s": self.floor.every_s if self.floor is not None else FLOOR_EVERY_S,
                "gate": self.floor.gate if self.floor is not None else "moving",
                "threads": int(_number(self.floor_settings.get("floor_threads"), 2)),
                "bins": self.floor.bins if self.floor is not None else FLOOR_BINS,
                "reach_m": self.floor.reach_m if self.floor is not None else FLOOR_REACH_M,
            },
            "head": self._heads(),
        }

    @property
    def available(self) -> bool:
        with self._lock:
            return self._enabled and self._latest is not None and self.clock.monotonic() - self._latest_mono <= self.stale_s

    @property
    def enabled(self) -> bool:
        return self._enabled

    def latest(self, max_age_s: float = 0.5) -> Sight | None:
        with self._lock:
            if not self._enabled or self._latest is None or self.clock.monotonic() - self._latest_mono > max_age_s:
                return None
            return self._latest

    def camera(self) -> str | None:
        with self._lock:
            fresh = self._enabled and self._latest is not None and self.clock.monotonic() - self._latest_mono <= self.stale_s
            return self._latest.camera if fresh else None

    def wanted(self) -> str:
        return self._want

    def start(self) -> None:
        if self._started:
            return
        bridge = self.bridge()
        bridge.eyesSink(self)
        config = self.config()
        bridge.eyesStart(json.dumps(config))
        self._hazard_every = config["hazards"]["every_s"]
        self._head_told = config["head"]
        self._started = True
        if self.speaking is not None and self.speaking.gate == "always":
            self._read_mouths(True)

    def _read_mouths(self, on: bool) -> None:
        if not self._started:
            return
        try:
            self.bridge().eyesMouths(bool(on), float(self.speaking.tail_s if self.speaking is not None else TAIL_S))
        except Exception as error:
            log.debug("eyes: the phone would not read mouths: %s", error)

    def hear_voice(self, on: bool) -> None:
        if self.speaking is None:
            return
        self.speaking.hear_voice(on)
        if self.speaking.gate != "always":
            self._read_mouths(on)

    def spoke(self, start: float, end: float) -> dict[int, float]:
        return self.speaking.spoke(start, end) if self.speaking is not None else {}

    def close(self) -> None:
        if self._started:
            try:
                self.bridge().eyesStop()
            except Exception as error:
                log.warning("eyes: closing the cameras failed: %s", error)
            self._started = False
        with self._lock:
            self._latest = None
            self._camera = None
            self._snap = None
            self._motion = None
            self._recent.clear()
            self._settle(None, False)
        if self.floor is not None:
            self.floor.forget()
        self._forget_hazards()
        self._fail_demands()
        self._look(None)
        self._mark(None)

    async def use_camera(self, camera: str) -> bool:
        if camera not in CAMERAS or not self._enabled or not self._started:
            return False
        loop = asyncio.get_running_loop()
        with self._lock:
            fresh = self._latest is not None and self.clock.monotonic() - self._latest_mono <= self.stale_s
            if fresh and self._camera == camera and self._latest.camera == camera:
                self._want = camera
                return True
            self._want = camera
            future = loop.create_future()
            waiter = (camera, future, loop)
            self._waiters.append(waiter)
        try:
            self.bridge().eyesUse(camera)
        except Exception as error:
            log.warning("eyes: the %s camera could not be asked for: %s", camera, error)
            with self._lock:
                if waiter in self._waiters:
                    self._waiters.remove(waiter)
            return False
        try:
            return await asyncio.wait_for(asyncio.shield(future), self.switch_timeout_s)
        except asyncio.TimeoutError:
            log.info("the %s camera did not start in time", camera)
            return False
        finally:
            with self._lock:
                if waiter in self._waiters:
                    self._waiters.remove(waiter)

    def set_enabled(self, on: bool) -> None:
        with self._lock:
            changed = bool(on) != self._enabled
            self._enabled = bool(on)
            if not self._enabled:
                self._latest = None
                self._camera = None
                self._slow_result = None
                self._snap = None
                self._motion = None
                self._recent.clear()
                self._settle(None, False)
        if not on:
            self._forget_hazards()
            self._fail_demands()
            if self.speaking is not None:
                self.speaking.forget()
            if self.floor is not None:
                self.floor.forget()
        if self._started:
            try:
                bridge = self.bridge()
                blind = self._private and getattr(bridge, "eyesPrivacy", None) is None
                bridge.eyesEnable(bool(on) and not blind)
            except Exception as error:
                log.warning("eyes: switching the cameras %s failed: %s", "on" if on else "off", error)
        if changed:
            log.info("eyes %s", "on" if on else "off")
            if not on:
                self._look(None)
                self._mark(None)

    @property
    def private(self) -> bool:
        return self._private

    def set_privacy(self, on: bool, keep=()) -> None:
        keep = frozenset(k for k in keep if k in ("floor", "tag")) if on else frozenset()
        with self._lock:
            changed = bool(on) != self._private or keep != self._keep
            self._private, self._keep = bool(on), keep
            if on:
                self._latest = None
                self._slow_result = None
                self._snap = None
                self._motion = None
                self._undress = None
                self._fast_things = []
                self._bodies = []
                self._poses = {}
                self._recent.clear()
        if on:
            self._forget_hazards()
            self._fail_demands()
            if self.speaking is not None:
                self.speaking.forget()
            self._look(None)
        if self._started and changed:
            bridge = self.bridge()
            told = getattr(bridge, "eyesPrivacy", None)
            try:
                if told is not None:
                    told(json.dumps({"on": bool(on), "keep": sorted(keep)}))
                else:
                    bridge.eyesEnable(bool(self._enabled and not on))
            except Exception as error:
                log.warning("eyes: the phone would not look away: %s", error)
        if changed:
            log.info("eyes: %s", "looking away for privacy" if on else "looking again")

    def undressed(self, max_age_s: float = 2.5) -> tuple[float, float] | None:
        found = self._undress
        if found is None or self._private or self.clock.monotonic() - found[0] > max_age_s:
            return None
        return found[1], found[2]

    def _private_feed(self, data: dict) -> bool:
        camera = data["camera"]
        captured = _number(data.get("t"), self.clock.monotonic())
        at = self.clock.now() - max(0.0, self.clock.monotonic() - captured)
        self.private_frames += 1
        tags = []
        if "tag" in self._keep and camera in self.tags_on:
            for item in _rows(data, "tags"):
                if isinstance(item, dict) and int(_number(item.get("id"), -1)) == self.tag_id:
                    seen = tag_seen(self.tag_id, item.get("poses") or [], _number(item.get("px")))
                    if seen is not None:
                        tags.append(seen)
        floor, floor_at = ((), None)
        if "floor" in self._keep and self.floor is not None:
            found, floor_at = self.floor.current(camera, captured)
            floor = tuple(found)
        if not tags and not floor:
            return False
        self._show(Sight(at=at, camera=camera, fov_h_deg=self.cameras[camera]["fov_h_deg"], tags=tuple(tags), floor=floor, floor_at=floor_at), captured)
        return True

    def set_head(self, tilt_deg: float | None = None, roll_deg: float | None = None) -> None:
        if tilt_deg is not None:
            self._tilt = float(tilt_deg)
        if roll_deg is not None:
            self._roll = float(roll_deg)
        self._tell_head()

    def head(self, camera: str) -> tuple[float, float, float]:
        sign = 1.0 if camera == "front" else -1.0
        return self.cameras[camera]["height_m"], sign * self._tilt, sign * self._roll

    def _tell_head(self) -> None:
        if not self._started:
            return
        heads = self._heads()
        if heads == self._head_told:
            return
        try:
            self.bridge().eyesHead(json.dumps(heads))
        except Exception as error:
            log.debug("eyes: the phone would not take the head's tilt: %s", error)
            return
        self._head_told = heads

    def set_moving(self, on: bool) -> None:
        if self.floor is None:
            return
        self.floor.set_moving(on)
        if self._started:
            try:
                self.bridge().eyesMoving(bool(on))
            except Exception as error:
                log.debug("eyes: the phone would not hear that Pebble is moving: %s", error)

    def scan_floor(self) -> None:
        if self.floor is None or not self._started:
            return
        try:
            self.bridge().eyesScanFloor()
        except Exception as error:
            log.debug("eyes: the phone would not scan the floor: %s", error)

    def floor_seen(self, text) -> bool:
        try:
            data = json.loads(str(text))
        except ValueError:
            return False
        scan = self.floor
        if scan is None or not isinstance(data, dict):
            return False
        if self._private and "floor" not in self._keep:
            return False
        if data.get("failed"):
            if data.get("problem"):
                scan.problem = str(data.get("problem"))[:300]
            return False
        camera, rows = data.get("camera"), data.get("rays")
        if camera not in CAMERAS or not isinstance(rows, list):
            return False
        rays = []
        for row in rows[:MAX_RAYS]:
            values = [_number(v, math.nan) for v in row[:3]] if isinstance(row, list) and len(row) >= 3 else [math.nan]
            if not all(math.isfinite(v) for v in values):
                return False
            rays.append(FloorRay(round(values[0], 2), round(values[1], 3), round(values[2], 3)))
        captured = _number(data.get("t"), self.clock.monotonic())
        at = self.clock.now() - max(0.0, self.clock.monotonic() - captured)
        with self._lock:
            if not self._enabled:
                return False
            scan.took(camera, captured, at, tuple(rays), _number(data.get("quality")), _number(data.get("ms")))
        return True

    def _floor_now(self, camera: str, captured: float, seen) -> tuple:
        if self.floor is None or not self._enabled:
            return (), None
        found, found_at = self.floor.current(camera, captured)
        return cut(found, seen, self.floor.reach_m), found_at

    def _motion_step(self, data: dict, camera: str, at: float) -> None:
        raw = data.get("motion")
        shift = raw.get("shift") if isinstance(raw, dict) else None
        if not isinstance(shift, list) or len(shift) != 2:
            return
        values = [_number(raw.get("dt"), math.nan), _number(shift[0], math.nan), _number(shift[1], math.nan), _number(raw.get("sure"), math.nan), _number(raw.get("change"), math.nan)]
        if not all(math.isfinite(v) for v in values):
            return
        dt, dx, dy, sure, change = values
        per_px = self.cameras[camera]["fov_h_deg"] / MOTION_SIZE[0]
        self._motion = {"at": at, "dt": round(dt, 3), "shift_deg": (round(dx * per_px, 2), round(dy * per_px, 2)), "sure": round(sure, 3), "change": round(change, 4), "camera": camera}

    def motion(self) -> dict | None:
        found = self._motion
        return dict(found) if found is not None else None

    def set_busy(self, busy: bool) -> None:
        if self._started:
            try:
                self.bridge().eyesBusy(bool(busy))
            except Exception:
                pass

    def moved(self) -> None:
        if self._started:
            try:
                self.bridge().eyesMoved()
            except Exception:
                pass

    async def look_closely(self, timeout_s: float = LOOK_CLOSELY_S) -> Sight | None:
        base = self.latest(self.stale_s)
        if base is None or not self.config()["slow"]["on"] or not self._enabled or not self._started or self._private:
            return base
        loop = asyncio.get_running_loop()
        demand = next(self._demand_ids)
        future = loop.create_future()
        with self._lock:
            self._demands[demand] = (future, loop)
        try:
            self.bridge().eyesLookClosely(demand)
            result = await asyncio.wait_for(asyncio.shield(future), timeout_s)
        except asyncio.TimeoutError:
            result = None
        except Exception as error:
            log.warning("eyes: looking closely failed: %s", error)
            result = None
        finally:
            with self._lock:
                self._demands.pop(demand, None)
        if self._private:
            return None
        latest = self.latest(self.stale_s) or base
        if result is None or result.camera != latest.camera:
            return latest
        with self._lock:
            fast = list(self._fast_things) if self._fast_camera == latest.camera else []
        fov = self.cameras[latest.camera]["fov_h_deg"]
        things = self._with_hazards(merge(fast, self._slow_now(latest.camera, result.captured)), latest.camera, result.captured)
        seen = self._on_floor(seen_things(things, result.width, result.height, fov), things, latest.camera, result.width, result.height, fov)
        return Sight(at=latest.at, camera=latest.camera, fov_h_deg=fov, people=latest.people, tags=latest.tags, things=seen)

    def feed(self, text) -> bool:
        try:
            data = json.loads(str(text))
        except ValueError:
            return False
        if not isinstance(data, dict) or data.get("camera") not in CAMERAS:
            return False
        if self._private:
            return self._private_feed(data)
        undress = data.get("undress")
        if isinstance(undress, list) and len(undress) >= 2:
            self._undress = (_number(data.get("t"), self.clock.monotonic()), max(0.0, min(1.0, _number(undress[0]))), max(0.0, min(1.0, _number(undress[1]))))
        try:
            sight = self.process(data)
        except Exception:
            log.exception("eyes: a picture's results could not be read")
            return False
        if sight is None:
            return False
        self._show(sight, _number(data.get("t"), self.clock.monotonic()))
        return True

    def process(self, data: dict) -> Sight | None:
        camera = data["camera"]
        width, height = int(_number(data.get("w"))), int(_number(data.get("h")))
        if width <= 0 or height <= 0:
            return None
        captured = _number(data.get("t"), self.clock.monotonic())
        age = max(0.0, self.clock.monotonic() - captured)
        at = self.clock.now() - age
        fov = self.cameras[camera]["fov_h_deg"]
        people = camera in self.people_on
        face_rows = [(i, b) for i, b in enumerate(_box(r) for r in _rows(data, "faces")) if b is not None] if people else []
        faces = [b for _, b in face_rows]
        if people and isinstance(data.get("objects"), list):
            bodies, found = [], []
            for row in _rows(data, "objects"):
                box = _box(row)
                if box is None or len(row) < 6:
                    continue
                kind = int(_number(row[5], -1))
                if kind == PERSON:
                    bodies.append(box)
                    continue
                label, animal = coco_label(kind)
                if label is not None:
                    found.append((box, label, animal))
            tracked = self._track_things(found, at, captured, camera, width / height)
            with self._lock:
                self._bodies, self._bodies_at = bodies, captured
                self._fast_things, self._fast_camera = tracked, camera
        tags = []
        if camera in self.tags_on:
            for item in _rows(data, "tags"):
                if not isinstance(item, dict) or int(_number(item.get("id"), -1)) != self.tag_id:
                    continue
                seen = tag_seen(self.tag_id, item.get("poses") or [], _number(item.get("px")))
                if seen is not None:
                    tags.append(seen)
        with self._lock:
            fresh = people and captured - self._bodies_at <= BODY_KEEP_S
            bodies = list(self._bodies) if fresh else []
            fast = list(self._fast_things) if fresh and self._fast_camera == camera else []
        found_people = self._tracker.update(combine(faces, bodies), captured, camera, width / height)
        poses, hands = self._pose_step(data, found_people, captured, width, height, fov, camera) if people else ({}, [])
        speaking = self._speak_step(data, found_people, face_rows, captured, at, width, height) if people else {}
        things = merge(fast, self._slow_now(camera, captured))
        if hands:
            from .pose import held_by

            things = [replace(t, held=held_by(t.box, hands, width / height)) for t in things]
        if self.hazards is not None and self._enabled:
            self._note(data, camera, captured, things)
        things = self._with_hazards(things, camera, captured)
        with self._lock:
            self._snap = Snap(camera, captured, at, fov, width, height, {c.track: c.box for c in found_people if c.box is not None}, tuple(things))
        ms = data.get("ms")
        if isinstance(ms, dict):
            kept = {k: v for k, v in self._ms.items() if k in ("slow", "hazards")}
            self._ms = {**{str(k)[:24]: round(_number(v), 1) for k, v in list(ms.items())[:12]}, **kept}
        seen = self._on_floor(seen_things(things, width, height, fov), things, camera, width, height, fov)
        self._motion_step(data, camera, at)
        floor, floor_at = self._floor_now(camera, captured, seen)
        return Sight(at=at, camera=camera, fov_h_deg=fov, people=seen_people(found_people, width, height, fov, poses, speaking), tags=tuple(tags), things=seen, floor=floor, floor_at=floor_at)

    def _speak_step(self, data: dict, found: list[Candidate], face_rows: list, captured: float, at: float, width: int, height: int) -> dict:
        if self.speaking is None:
            return {}
        shapes = {}
        for item in _rows(data, "mouths"):
            if not isinstance(item, list) or not item:
                continue
            row = int(_number(item[0], -1))
            gap, wide = (_number(item[1], math.nan), _number(item[2], math.nan)) if len(item) >= 3 else (math.nan, math.nan)
            shapes[row] = (gap, wide) if math.isfinite(gap) and math.isfinite(wide) else None
        self._mouths.shapes = shapes
        boxes = dict(face_rows)
        where = {(f.cx, f.cy): row for row, f in face_rows}
        mouths = []
        for c in found:
            row = where.get((c.u, c.v)) if c.face else None
            if row is None or c.track is None:
                continue
            f = boxes[row]
            mouths.append((c.track, (f.x * width, f.y * height, f.w * width, f.h * height), row))
        return self.speaking.step(None, mouths, captured, at)

    def _note(self, data: dict, camera: str, captured: float, things: list[Thing]) -> None:
        with self._lock:
            self._recent.append((camera, captured, tuple(things)))
        if "warm" not in data:
            return
        levels = []
        boxes = self.hazards.fire_boxes()
        grid = glow_grid(data.get("glow")) if boxes else None
        if grid is not None:
            for box in boxes:
                level = glow_level(grid, box)
                if level is not None:
                    levels.append((box, level))
        self.hazards.note(captured, max(0.0, min(1.0, _number(data.get("warm")))), levels)
        self._pace_hazards()

    def _with_hazards(self, things: list[Thing], camera: str, captured: float) -> list[Thing]:
        if self.hazards is None or not self._enabled:
            return things
        found = self.hazards.current(camera, captured)
        return list(things) + [h for h in found if h.label in ("fire", "smoke") or not any(o.label == h.label and overlap(o.box, h.box) >= LOOKALIKE_OVERLAP for o in things)]

    def _on_floor(self, seen, things, camera: str, width: int, height: int, fov: float) -> tuple:
        height_m, pitch, roll = self.head(camera)
        out = []
        for item, thing in zip(seen, things):
            spot = floor_point(thing.box.cx, thing.box.y + thing.box.h, width, height, fov, height_m, pitch, roll)
            out.append(replace(item, floor_m=round(spot[0], 3), floor_bearing_deg=round(spot[1], 2)) if spot else item)
        return tuple(out)

    def _context(self, camera: str, captured: float) -> list[Thing]:
        with self._lock:
            recent = [entry for entry in self._recent if entry[0] == camera and entry[1] <= captured + 1e-6]
        if not recent:
            return []
        return list(max(recent, key=lambda entry: entry[1])[2])

    def _pace_hazards(self) -> None:
        watch = self.hazards
        if watch is None or not self._started:
            return
        every = CLOSE_EVERY_S if watch.status()["close_watch"] else watch.every_s
        if every == self._hazard_every:
            return
        self._hazard_every = every
        try:
            self.bridge().eyesHazardsEvery(float(every))
        except Exception as error:
            log.warning("eyes: the phone would not change how often it looks for fire: %s", error)

    def _forget_hazards(self) -> None:
        if self.hazards is None:
            return
        with self._hazard_lock:
            self._hazard_rows.found = []
            self.hazards.forget()

    def hazards_seen(self, text) -> bool:
        try:
            data = json.loads(str(text))
        except ValueError:
            return False
        watch = self.hazards
        if watch is None or not isinstance(data, dict) or self._private:
            return False
        if data.get("failed"):
            if data.get("problem"):
                watch.problem = str(data.get("problem"))[:300]
            return False
        camera = data.get("camera")
        width, height = int(_number(data.get("w"))), int(_number(data.get("h")))
        if camera not in CAMERAS or width <= 0 or height <= 0:
            return False
        captured = _number(data.get("t"), self.clock.monotonic())
        at = self.clock.now() - max(0.0, self.clock.monotonic() - captured)
        found = []
        for row in _rows(data, "found"):
            box = _box(row)
            if box is None or len(row) < 6:
                continue
            index = int(_number(row[5], -1))
            if not 0 <= index < len(self.hazard_classes):
                continue
            entry = self.hazard_classes[index]
            found.append(SlowFound(box, str(entry.get("label")), bool(entry.get("animal")), str(entry.get("raw", entry.get("label"))), int(entry.get("depth", 6))))
        context = self._context(camera, captured)
        with self._hazard_lock:
            if not self._enabled:
                return False
            self._hazard_rows.found = found
            try:
                watch.look(None, camera, captured, at, self.cameras[camera]["fov_h_deg"], context)
            except Exception:
                log.exception("eyes: the hazard watch could not read the phone's finds")
                return False
            finally:
                self._hazard_rows.found = []
            watch.last_ms = round(_number(data.get("ms")), 1)
            watch.problem = ""
        self._ms["hazards"] = watch.last_ms
        self._pace_hazards()
        return True

    def _pose_step(self, data: dict, found: list[Candidate], captured: float, width: int, height: int, fov: float, camera: str):
        from .pose import body_points, facing, wrists
        from .posture import posture

        incoming = []
        for item in _rows(data, "poses"):
            if not isinstance(item, dict):
                continue
            box, raw = _box(list(item.get("box") or []) + [1.0]), _points(item.get("points"))
            if box is not None and raw is not None:
                incoming.append((box, raw))
        for c in found:
            if not c.body or c.box is None or not incoming:
                continue
            best = max(incoming, key=lambda pair: overlap(pair[0], c.box))
            if overlap(best[0], c.box) >= POSE_MATCH:
                self._poses[c.track] = (best[1], captured)
        tracks = {c.track: c for c in found}
        self._poses = {k: v for k, v in self._poses.items() if k in tracks and captured - v[1] <= POSE_KEEP_S}
        height_m, pitch, roll = self.head(camera)
        out, hands = {}, []
        for track, (raw, _) in self._poses.items():
            box = tracks[track].box
            label, sure = posture(raw, box, width, height, fov, height_m, pitch, roll) if box is not None else (None, 0.0)
            out[track] = (body_points(raw, width, height, fov), facing(raw), label, sure)
            hands.extend(wrists(raw))
        return out, hands

    def slow(self, text) -> bool:
        try:
            data = json.loads(str(text))
        except ValueError:
            return False
        if not isinstance(data, dict):
            return False
        raw = data.get("demand")
        demands = [int(_number(d, -1)) for d in raw] if isinstance(raw, list) else []
        result = None
        camera = data.get("camera")
        width, height = int(_number(data.get("w"))), int(_number(data.get("h")))
        if camera in CAMERAS and width > 0 and height > 0 and not data.get("failed") and not self._private:
            captured = _number(data.get("t"), self.clock.monotonic())
            at = self.clock.now() - max(0.0, self.clock.monotonic() - captured)
            marks = self._known_marks(data)
            found = []
            for row_number, row in enumerate(_rows(data, "found")):
                box = _box(row)
                if box is None or len(row) < 6:
                    continue
                index = int(_number(row[5], -1))
                if not 0 <= index < len(self.classes):
                    continue
                entry = self.classes[index]
                known, known_score = marks.get(row_number, (None, 0.0))
                found.append((box, str(entry.get("label")), bool(entry.get("animal")), int(entry.get("depth", 6)), known, known_score))
            result = SlowResult(camera, captured, at, width, height, tuple(found))
            with self._lock:
                if self._enabled:
                    self._slow_result = result
                    self.slow_passes += 1
                    if "ms" in data:
                        self._ms["slow"] = round(_number(data.get("ms")), 1)
        for demand in demands:
            with self._lock:
                waiting = self._demands.pop(demand, None)
            if waiting is not None:
                future, loop = waiting
                loop.call_soon_threadsafe(_resolve, future, result)
        return result is not None

    def _known_marks(self, data: dict) -> dict:
        rows, prints = data.get("print_rows"), data.get("prints")
        if not self.book or not isinstance(rows, list) or not isinstance(prints, list) or len(rows) != len(prints) or not prints:
            return {}
        try:
            import numpy as np

            vecs = np.asarray(prints, np.float32)
            best = self.book.best(vecs)
        except Exception as error:
            log.warning("eyes: the slow lane's prints could not be read: %s", error)
            return {}
        return {int(row): (key, round(score, 3)) for row, (key, score) in zip(rows, best) if key is not None and score >= self.book.match}

    def state(self, text) -> None:
        data = text if isinstance(text, dict) else (json.loads(str(text)) if text else {})
        if not isinstance(data, dict):
            return
        what = data.get("state")
        camera = data.get("camera")
        problem = str(data.get("problem") or "")[:300]
        self._phone = {str(k)[:24]: v for k, v in data.items() if isinstance(v, (str, int, float, bool))}
        if what == "failed":
            self.problem = problem or f"the {camera} camera failed"
            log.warning("eyes: %s", self.problem)
            with self._lock:
                self._settle(camera, False)
        elif what == "closed":
            with self._lock:
                if camera is None or self._camera == camera:
                    self._camera = None
                    self._latest = None
            self._look(None)
            self._mark(None)
        elif what == "open":
            self.problem = ""
            log.info("eyes: the %s camera is open", camera)

    def remember_print(self, key: str, vec, replace: bool = False) -> int:
        if self.book is None:
            raise ValueError("this phone cannot keep prints (numpy is missing)")
        count = self.book.remember(str(key), vec, replace)
        self._want_prints()
        return count

    def forget_print(self, key: str) -> bool:
        if self.book is None:
            return False
        gone = self.book.forget(str(key))
        self._want_prints()
        return gone

    def _want_prints(self) -> None:
        if self._started:
            try:
                self.bridge().eyesPrints(KNOWN_MAX if self.book else 0)
            except Exception as error:
                log.warning("eyes: the phone would not mark known things: %s", error)

    def _fresh_snap(self, max_age_s: float = SNAPSHOT_S) -> Snap | None:
        with self._lock:
            snap = self._snap
        if snap is None or not self._enabled or self._private or self.clock.monotonic() - snap.captured > max_age_s:
            return None
        return snap

    def _hold(self) -> HeldPicture | None:
        if not self._started or self.book is None or self._private:
            return None
        try:
            held = json.loads(str(self.bridge().eyesHold()))
        except Exception as error:
            log.warning("eyes: the phone kept no picture to look at: %s", error)
            return None
        if not isinstance(held, dict) or "id" not in held:
            return None
        return HeldPicture(self.bridge(), held)

    async def fingerprint(self, track: int) -> tuple[float, ...] | None:
        snap = self._fresh_snap()
        if snap is None:
            return None
        box = snap.people.get(track) or next((t.box for t in snap.things if t.track == track), None)
        if box is None:
            return None
        held = await asyncio.to_thread(self._hold)
        if held is None:
            return None
        try:
            vecs = await asyncio.to_thread(held.embed, None, [box])
        except Exception as error:
            log.warning("eyes: no print: %s", error)
            return None
        finally:
            held.release()
        return tuple(round(float(x), 6) for x in vecs[0])

    async def dock_print(self) -> tuple[float, ...] | None:
        if self._fresh_snap() is None:
            return None
        from .prints import dock_box

        held = await asyncio.to_thread(self._hold)
        if held is None:
            return None
        try:
            box = None
            for item in held.tags:
                if not isinstance(item, dict) or int(_number(item.get("id"), -1)) != DOCK_TAG_ID:
                    continue
                poses = item.get("poses") or []
                if poses and isinstance(poses[0].get("r"), list) and isinstance(poses[0].get("t"), list):
                    box = dock_box(poses[0]["r"], poses[0]["t"], held.width, held.height, held.fov)
                    break
            if box is None:
                return None
            vecs = await asyncio.to_thread(held.embed, None, [box])
        except Exception as error:
            log.warning("eyes: no dock print: %s", error)
            return None
        finally:
            held.release()
        return tuple(round(float(x), 6) for x in vecs[0])

    async def place_print(self, camera: str | None = None) -> tuple[float, ...] | None:
        snap = self._fresh_snap()
        if snap is None or (camera is not None and snap.camera != camera):
            return None
        held = await asyncio.to_thread(self._hold)
        if held is None:
            return None
        try:
            if camera is not None and held.camera != camera:
                return None
            vecs = await asyncio.to_thread(held.embed, None, list(PLACE_BOXES))
        except Exception as error:
            log.warning("eyes: no place print: %s", error)
            return None
        finally:
            held.release()
        mean = vecs.mean(axis=0)
        norm = float((mean * mean).sum()) ** 0.5
        if norm <= 1e-9:
            return None
        return tuple(round(float(x) / norm, 6) for x in mean)

    def _vetoed(self, snap: Snap) -> bool:
        veto = self.snapshot_veto
        if veto is None:
            return False
        try:
            return bool(veto(list(snap.people.values()), [(t.label, t.box) for t in snap.things], self.undressed()))
        except Exception:
            log.exception("eyes: the privacy check on a picture failed")
            return True

    async def snapshot(self, max_side: int = 768, camera: str | None = None) -> bytes | None:
        if not self._enabled or not self._started or self._private:
            return None
        if camera is not None and camera != self.camera():
            if not await self.use_camera(camera):
                return None
            started = self.clock.monotonic()
            while self.clock.monotonic() - started < 2.0:
                snap = self._fresh_snap(0.5)
                if snap is not None and snap.camera == camera:
                    break
                await asyncio.sleep(0.05)
        snap = self._fresh_snap()
        if snap is None or (camera is not None and snap.camera != camera):
            return None
        if self._vetoed(snap):
            if self.on_cue is not None:
                self.on_cue()
            return None
        picture = await asyncio.to_thread(self._jpeg, camera or "", max(64, int(max_side)))
        return None if self._private else picture

    def _jpeg(self, camera: str, max_side: int) -> bytes | None:
        from ..android.bridge import as_bytes

        try:
            data = as_bytes(self.bridge().eyesSnapshot(camera, max_side, SNAPSHOT_S))
        except Exception as error:
            log.warning("eyes: the phone gave no picture: %s", error)
            return None
        return data if data[:2] == b"\xff\xd8" else None

    async def look_for(self, key: str, camera: str | None = None) -> SeenThing | None:
        if not self._enabled or self.book is None or key not in self.book.keys():
            return None
        if camera is not None and camera != self.camera():
            if not await self.use_camera(camera):
                return None
            started = self.clock.monotonic()
            while self.clock.monotonic() - started < 2.0:
                snap = self._fresh_snap(0.5)
                if snap is not None and snap.camera == camera:
                    break
                await asyncio.sleep(0.05)
        snap = self._fresh_snap()
        if snap is None or (camera is not None and snap.camera != camera):
            return None
        held = await asyncio.to_thread(self._hold)
        if held is None:
            return None
        try:
            hit = await asyncio.to_thread(self._search, held, snap, key)
        finally:
            held.release()
        if hit is None:
            return None
        box, score = hit
        bearing, elevation = angles(box.cx, box.cy, snap.width, snap.height, snap.fov)
        return SeenThing(label=key, bearing_deg=round(bearing, 2), elevation_deg=round(elevation, 2), height_frac=round(box.h, 4), width_frac=round(box.w, 4), score=round(score, 3), at=snap.at, lane="slow", known=key, known_score=round(score, 3))

    def _search(self, held: HeldPicture, snap: Snap, key: str):
        from .prints import find

        proposals = [t.box for t in snap.things] + list(snap.people.values())
        try:
            proposals += held.propose(PROPOSE_SCORE)
        except Exception as error:
            log.warning("eyes: the slow lane could not propose places to look: %s", error)
        try:
            hit = find(held, self.book, key, None, proposals, frame_aspect=held.width / max(1, held.height))
        except Exception as error:
            log.warning("eyes: looking for %s failed: %s", key, error)
            return None
        if hit is None or hit[1] < self.book.match:
            return None
        return hit[0], hit[1]

    def _track_things(self, found: list, at: float, captured: float, camera: str, aspect: float) -> list[Thing]:
        candidates = [Candidate(box.cx, box.cy, box.w, box.h, box.score, False, label=label, box=box) for box, label, _ in found]
        self._thing_tracker.update(candidates, captured, camera, aspect)
        return [Thing(box, label, animal, at, "fast", self.coco_depth.get(label, 6), c.track) for (box, label, animal), c in zip(found, candidates)]

    def _slow_now(self, camera: str, captured: float) -> list[Thing]:
        keep = _number(self.slow_settings.get("slow_keep_s"), 3.0)
        with self._lock:
            result = self._slow_result
            if result is None or result.camera != camera or captured - result.captured > keep:
                return []
            if result is not self._slow_used:
                self._slow_used = result
                candidates = [Candidate(f[0].cx, f[0].cy, f[0].w, f[0].h, f[0].score, False, label=f[1], box=f[0]) for f in result.found]
                self._slow_tracker.update(candidates, result.captured, camera, result.width / max(1, result.height))
                self._slow_things = [Thing(box, label, animal, result.at, "slow", depth, c.track, known=known, known_score=known_score) for (box, label, animal, depth, known, known_score), c in zip(result.found, candidates)]
            return list(self._slow_things)

    def _show(self, sight: Sight, captured: float) -> None:
        if self._last_frame is not None:
            gap = max(1e-3, captured - self._last_frame)
            self._fps = 1 / gap if not self._fps else self._fps * 0.85 + 0.15 / gap
        self._last_frame = captured
        with self._lock:
            if not self._enabled or sight.camera != self._want:
                return
            self._latest = sight
            self._latest_mono = captured
            self._camera = sight.camera
            self.frames += 1
            self._settle(sight.camera, True)
        self._mark(sight.camera)
        if sight.camera == "front":
            person = nearest(sight.people, self._look_track)
            self._look_track = person.track if person is not None else None
            self._look(person)
        else:
            self._look(None)

    def _settle(self, camera: str | None, ok: bool) -> None:
        for waiter in list(self._waiters):
            want, future, loop = waiter
            if camera is None or want == camera or ok:
                self._waiters.remove(waiter)
                loop.call_soon_threadsafe(_resolve, future, ok and want == camera)

    def _fail_demands(self) -> None:
        with self._lock:
            demands, self._demands = self._demands, {}
        for future, loop in demands.values():
            try:
                loop.call_soon_threadsafe(_resolve, future, None)
            except RuntimeError:
                pass

    def _look(self, person: SeenPerson | None) -> None:
        if self.on_look is None or (person is None and not self._looking):
            return
        self._looking = person is not None
        try:
            self.on_look(person)
        except Exception:
            log.exception("passing the gaze on failed")

    def _mark(self, camera: str | None) -> None:
        if camera == self._marked or self.on_camera is None:
            self._marked = camera
            return
        self._marked = camera
        try:
            self.on_camera(camera)
        except Exception:
            log.exception("telling the face page about the camera failed")

    def status(self) -> dict:
        sight = self.latest(self.stale_s)
        out = {
            "on": self._enabled,
            "want": self._want,
            "camera": self.camera(),
            "available": self.available,
            "fps": round(self._fps, 1),
            "ms": dict(self._ms),
            "frames": self.frames,
            "problem": self.problem,
            "looking_away": self._private,
            "slow": {"passes": self.slow_passes, "on": self.config()["slow"]["on"]},
            "prints": {"keys": self.book.keys() if self.book is not None else [], "on": self.book is not None},
            "head": {"tilt_deg": self._tilt, "roll_deg": self._roll},
            "source": "android",
        }
        if self.hazards is not None:
            out["hazards"] = self.hazards.status()
        if self.speaking is not None:
            out["speaking"] = self.speaking.status()
        if self.floor is not None:
            out["floor"] = self.floor.status()
        out["motion"] = self.motion()
        if self._started:
            try:
                from ..android.bridge import as_json

                out["phone"] = as_json(self.bridge().eyesStatus(), {})
            except Exception as error:
                out["phone"] = {"problem": str(error)}
        if sight is not None:
            out["sight"] = {"camera": sight.camera, "people": [asdict(p) for p in sight.people], "tags": [asdict(t) for t in sight.tags], "things": [asdict(t) for t in sight.things]}
        return out


def _resolve(future: asyncio.Future, value) -> None:
    if not future.done():
        future.set_result(value)
