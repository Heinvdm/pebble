import asyncio
import itertools
import logging
import math
import threading
import time
from dataclasses import asdict, dataclass, replace
from typing import Callable

from ..clock import Clock
from ..seams.sight import CAMERAS, DOCK_TAG_ID, SeenPerson, SeenThing, Sight
from .geometry import Box, Candidate, Tracker, angles, combine, floor_point, nearest, seen_people
from .sources import Frame, FrameSource, SourceError
from .things import Thing, merge, seen_things
from .things import overlap as _overlap

log = logging.getLogger(__name__)

DEFAULT_CAMERAS = {
    "front": {"fov_h_deg": 70.0, "rotate": 0, "mirror": False, "width": 640, "height": 480, "height_m": 0.14},
    "rear": {"fov_h_deg": 65.0, "rotate": 0, "mirror": False, "width": 640, "height": 480, "height_m": 0.14},
}
TILT_REST_DEG = 8.0
MOTION_SIZE = (80, 60)
MAX_FPS = 10.0
SWITCH_TIMEOUT_S = 12.0
FIRST_FRAME_S = 8.0
STALE_S = 1.5
BODY_KEEP_S = 1.2
POSE_HZ = 5.0
POSE_PEOPLE = 3
POSE_KEEP_S = 0.6
KNOWN_MAX = 6
SNAPSHOT_S = 1.0
KEEPS = frozenset({"floor", "tag"})


@dataclass(frozen=True)
class Snapshot:
    image: object
    camera: str
    captured: float
    at: float
    fov_h_deg: float
    people: dict
    things: tuple
RETRY_S = (2.0, 5.0, 10.0, 30.0)


def camera_settings(cameras: dict | None = None) -> dict:
    merged = {name: dict(values) for name, values in DEFAULT_CAMERAS.items()}
    for name, values in (cameras or {}).items():
        if name in merged and isinstance(values, dict):
            merged[name].update(values)
    for values in merged.values():
        values["fov_h_deg"] = max(20.0, min(150.0, float(values["fov_h_deg"])))
        values["rotate"] = int(values.get("rotate") or 0) % 360 // 90 * 90
        values["mirror"] = bool(values.get("mirror"))
        values["width"] = max(64, int(values.get("width") or 640))
        values["height"] = max(48, int(values.get("height") or 480))
        values["height_m"] = max(0.02, min(2.0, float(values.get("height_m") or 0.14)))
    return merged


def orient(image, rotate: int, mirror: bool):
    if not rotate and not mirror:
        return image
    from .detect import opencv

    cv2, _ = opencv()
    turns = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
    if rotate in turns:
        image = cv2.rotate(image, turns[rotate])
    return cv2.flip(image, 1) if mirror else image


class _Ema:
    def __init__(self):
        self.values: dict[str, float] = {}

    def add(self, key: str, ms: float) -> None:
        old = self.values.get(key)
        self.values[key] = ms if old is None else old * 0.8 + ms * 0.2

    def get(self, key: str) -> float:
        return self.values.get(key, 0.0)


class CameraEyes:
    def __init__(
        self,
        sources: Callable[[str], FrameSource],
        detector=None,
        clock: Clock | None = None,
        cameras: dict | None = None,
        camera: str = "front",
        enabled: bool = True,
        max_fps: float = MAX_FPS,
        switch_timeout_s: float = SWITCH_TIMEOUT_S,
        stale_s: float = STALE_S,
        on_look: Callable[[SeenPerson | None], None] | None = None,
        on_camera: Callable[[str | None], None] | None = None,
        tags_on: tuple[str, ...] = ("rear",),
        people_on: tuple[str, ...] = CAMERAS,
        slow=None,
        pose=None,
        prints=None,
        pose_hz: float = POSE_HZ,
        hazards=None,
        speaking=None,
        floor=None,
        undress=None,
    ):
        self.sources = sources
        self.detector = detector
        self.clock = clock or Clock()
        self.cameras = camera_settings(cameras)
        self.max_fps = max(1.0, min(30.0, float(max_fps)))
        self.switch_timeout_s = switch_timeout_s
        self.stale_s = stale_s
        self.on_look = on_look
        self.on_camera = on_camera
        self._marked: str | None = None
        self.tags_on = tuple(tags_on)
        self.people_on = tuple(people_on)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._enabled = bool(enabled)
        self._want = camera if camera in CAMERAS else "front"
        self._camera: str | None = None
        self._latest: Sight | None = None
        self._latest_mono = -math.inf
        self._waiters: list[tuple[str, asyncio.Future, asyncio.AbstractEventLoop]] = []
        ids = itertools.count(1)
        self._tracker = Tracker(ids=ids)
        self._thing_tracker = Tracker(ids=ids)
        self._slow_tracker = Tracker(ids=ids, keep_s=10.0)
        self.pose = pose
        self.hazards = hazards
        self.speaking = speaking
        self.floor = floor
        self.undress = undress
        self.snapshot_veto = None
        self.on_cue = None
        self._private = False
        self._keep: frozenset = frozenset()
        self.private_frames = 0
        self._motion = None
        self._motion_prev = None
        self._window = None
        self._tilt = TILT_REST_DEG
        self._roll = 0.0
        self.pose_hz = max(0.5, float(pose_hz))
        self._pose_at = -math.inf
        self._poses: dict = {}
        self._make_prints = prints
        self._print_model = None
        self._print_problem = ""
        self._print_lock = threading.Lock()
        from .prints import PrintBook

        self.book = PrintBook()
        self._snapshot: Snapshot | None = None
        if slow is not None and getattr(slow, "recognise", None) is None:
            slow.recognise = self._recognise
        self._fast_things: list[Thing] = []
        self._slow_pass = None
        self._slow_things: list[Thing] = []
        self.slow = slow
        self._fast_camera: str | None = None
        self._things_lock = threading.Lock()
        self._bodies: list[Box] = []
        self._bodies_at = -math.inf
        self._since_body = 99
        self._look_track: int | None = None
        self._looking = False
        self._ms = _Ema()
        self._fps = 0.0
        self._last_frame_mono: float | None = None
        self.frames = 0
        self.problem = ""

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

    async def use_camera(self, camera: str) -> bool:
        if camera not in CAMERAS or not self._enabled or self._thread is None:
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
        self._wake.set()
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
                self._settle(None, False)
        if not on and self.slow is not None:
            self.slow.forget()
        if not on and self.hazards is not None:
            self.hazards.forget()
        if not on and self.speaking is not None:
            self.speaking.forget()
        if not on and self.floor is not None:
            self.floor.forget()
        if not on:
            self._motion = self._motion_prev = None
        if not on:
            with self._things_lock:
                self._snapshot = None
        if not on and self.undress is not None:
            self.undress.forget()
        if changed:
            log.info("eyes %s", "on" if on else "off")
            if not on:
                self._look(None)
        self._wake.set()

    @property
    def private(self) -> bool:
        return self._private

    def set_privacy(self, on: bool, keep=()) -> None:
        keep = frozenset(k for k in keep if k in KEEPS) if on else frozenset()
        with self._lock:
            changed = bool(on) != self._private or keep != self._keep
            self._private, self._keep = bool(on), keep
            if on:
                self._latest = None
        if on:
            for part in (self.slow, self.hazards, self.speaking, self.undress):
                if part is not None:
                    part.forget()
            with self._things_lock:
                self._snapshot = None
                self._fast_things, self._slow_things, self._slow_pass = [], [], None
            self._poses = {}
            self._bodies = []
            self._motion = self._motion_prev = None
            self._look(None)
        if changed:
            log.info("eyes: %s", "looking away for privacy" if on else "looking again")
        self._wake.set()

    def _needed(self) -> bool:
        if not self._private:
            return True
        if "tag" in self._keep:
            return True
        return "floor" in self._keep and self.floor is not None and self.floor.moving()

    def undressed(self, max_age_s: float = 2.5) -> tuple[float, float] | None:
        if self.undress is None or self._private or not self._enabled:
            return None
        return self.undress.current(self.clock.monotonic())

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="pebble-eyes", daemon=True)
        self._thread.start()
        if self.slow is not None:
            self.slow.start()
        if self.hazards is not None:
            self.hazards.start()
        if self.floor is not None:
            self.floor.start()
        if self.undress is not None:
            self.undress.start()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=5.0)
        if self.slow is not None:
            self.slow.close()
        if self.hazards is not None:
            self.hazards.close()
        if self.floor is not None:
            self.floor.close()
        if self.undress is not None:
            self.undress.close()
        with self._things_lock:
            self._snapshot = None
        with self._lock:
            self._latest = None
            self._settle(None, False)

    def _settle(self, camera: str | None, ok: bool) -> None:
        for waiter in list(self._waiters):
            want, future, loop = waiter
            if camera is None or want == camera or ok:
                self._waiters.remove(waiter)
                loop.call_soon_threadsafe(_resolve, future, ok and want == camera)

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

    def _run(self) -> None:
        source: FrameSource | None = None
        current: str | None = None
        opened_at = 0.0
        failures = 0
        retry_at = 0.0
        while not self._stop.is_set():
            with self._lock:
                want = self._want if self._enabled and self._needed() else None
                asked = any(w[0] == want for w in self._waiters)
            if want != current:
                if source is not None:
                    self._close(source)
                    source, current = None, None
                    self._gone()
                if want is None:
                    self._wake.wait(0.5)
                    self._wake.clear()
                    continue
                if time.monotonic() < retry_at and not asked:
                    self._wake.wait(min(0.5, retry_at - time.monotonic()))
                    self._wake.clear()
                    continue
                try:
                    source = self.sources(want)
                    source.open()
                    current, opened_at = want, time.monotonic()
                    self._tracker.reset()
                    self._bodies, self._since_body = [], 99
                    log.info("eyes: the %s camera is open", want)
                except Exception as error:
                    source = None
                    failures += 1
                    retry_at = time.monotonic() + RETRY_S[min(failures, len(RETRY_S)) - 1]
                    self.problem = f"the {want} camera would not open: {error}"
                    log.warning("eyes: %s", self.problem)
                    with self._lock:
                        self._settle(want, False)
                    continue
            if source is None:
                self._wake.wait(0.5)
                self._wake.clear()
                continue
            try:
                frame = source.read(0.5)
            except SourceError as error:
                frame = None
                self.problem = f"the {current} camera stopped: {error}"
                log.warning("eyes: %s", self.problem)
                self._close(source)
                source, current = None, None
                self._gone()
                failures += 1
                retry_at = time.monotonic() + RETRY_S[min(failures, len(RETRY_S)) - 1]
                continue
            if frame is None:
                if self._latest_camera() != current and time.monotonic() - opened_at > FIRST_FRAME_S:
                    self.problem = f"the {current} camera opened but sent no pictures"
                    log.warning("eyes: %s", self.problem)
                    self._close(source)
                    source, current = None, None
                    failures += 1
                    retry_at = time.monotonic() + RETRY_S[min(failures, len(RETRY_S)) - 1]
                    with self._lock:
                        self._settle(want, False)
                continue
            started = time.monotonic()
            try:
                sight = self.process(frame)
            except Exception:
                log.exception("eyes: looking at a picture failed")
                continue
            failures = 0
            self.problem = ""
            self._show(sight, frame)
            spare = 1.0 / self.max_fps - (time.monotonic() - started)
            if spare > 0:
                self._stop.wait(spare)
        if source is not None:
            self._close(source)
        self._gone()

    def _latest_camera(self) -> str | None:
        with self._lock:
            return self._camera

    def _close(self, source: FrameSource) -> None:
        try:
            source.close()
        except Exception:
            log.exception("eyes: closing the camera failed")

    def _gone(self) -> None:
        with self._lock:
            self._camera = None
            self._latest = None
        self._last_frame_mono = None
        self._look(None)
        self._mark(None)

    def _show(self, sight: Sight, frame: Frame) -> None:
        if self._last_frame_mono is not None:
            gap = max(1e-3, frame.captured - self._last_frame_mono)
            self._fps = 1 / gap if not self._fps else self._fps * 0.85 + 0.15 / gap
        self._last_frame_mono = frame.captured
        with self._lock:
            if not self._enabled or sight.camera != self._want:
                return
            self._latest = sight
            self._latest_mono = frame.captured
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

    def _private_process(self, frame: Frame) -> Sight:
        camera = frame.camera
        settings = self.cameras[camera]
        fov = settings["fov_h_deg"]
        at = self.clock.now() - max(0.0, self.clock.monotonic() - frame.captured)
        self.private_frames += 1
        keep = self._keep
        tags, floor, floor_at = [], (), None
        if "tag" in keep and self.detector is not None and camera in self.tags_on:
            image = orient(frame.image, settings["rotate"], settings["mirror"])
            tags = [t.seen for t in self.detector.tags(image, fov)]
        if "floor" in keep and self.floor is not None and self.floor.moving() and self._enabled:
            from .floor import floor_only

            image = floor_only(orient(frame.image, settings["rotate"], settings["mirror"]), fov, *self.head(camera)[1:])
            self.floor.offer(image, camera, frame.captured, at, fov, self.head(camera))
            floor, floor_at = self.floor.current(camera, frame.captured)
        return Sight(at=at, camera=camera, fov_h_deg=fov, tags=tuple(tags), floor=floor, floor_at=floor_at)

    def process(self, frame: Frame) -> Sight:
        if self._private:
            return self._private_process(frame)
        camera = frame.camera
        settings = self.cameras[camera]
        image = orient(frame.image, settings["rotate"], settings["mirror"])
        height, width = image.shape[:2]
        fov = settings["fov_h_deg"]
        age = max(0.0, self.clock.monotonic() - frame.captured)
        at = self.clock.now() - age
        faces: list[Box] = []
        marks: list = []
        tags = []
        detector = self.detector
        people = detector is not None and camera in self.people_on
        if people:
            started = time.perf_counter()
            faces = detector.faces(image)
            marks = list(getattr(detector, "face_marks", None) or [])
            self._ms.add("face", (time.perf_counter() - started) * 1000)
            budget = 1000.0 / self.max_fps - self._ms.get("face") - (self._ms.get("tag") if camera in self.tags_on else 0.0)
            every = max(1, min(8, math.ceil(self._ms.get("body") / max(5.0, budget))))
            self._since_body += 1
            if self._since_body >= every or frame.captured - self._bodies_at > 1.0:
                started = time.perf_counter()
                self._bodies, found = detector.objects(image)
                self._ms.add("body", (time.perf_counter() - started) * 1000)
                self._bodies_at = frame.captured
                self._since_body = 0
                tracked = self._track_things(found, at, frame.captured, camera, width / height)
                with self._things_lock:
                    self._fast_things, self._fast_camera = tracked, camera
        if detector is not None and camera in self.tags_on:
            started = time.perf_counter()
            tags = [t.seen for t in detector.tags(image, fov)]
            self._ms.add("tag", (time.perf_counter() - started) * 1000)
        fresh = people and frame.captured - self._bodies_at <= BODY_KEEP_S
        bodies = self._bodies if fresh else []
        found = self._tracker.update(combine(faces, bodies), frame.captured, camera, width / height)
        poses, hands = self._pose_step(image, found, frame.captured, width, height, fov) if people else ({}, [])
        speaking = self._speak_step(image, found, faces, marks, frame.captured, at, width, height) if people else {}
        with self._things_lock:
            fast = self._fast_things if fresh and self._fast_camera == camera else []
        things = merge(fast, self._slow_now(camera, frame.captured))
        if hands:
            from .pose import held_by

            things = [replace(t, held=held_by(t.box, hands, width / height)) for t in things]
        if self.hazards is not None and self._enabled:
            self.hazards.offer(image, camera, frame.captured, at, fov, things)
        things = self._with_hazards(things, camera, frame.captured)
        with self._things_lock:
            self._snapshot = Snapshot(image, camera, frame.captured, at, fov, {c.track: c.box for c in found if c.box is not None}, tuple(things))
        if self.slow is not None and self._enabled:
            self.slow.offer(image, camera, frame.captured, at, fov)
        if self.undress is not None and self._enabled and found:
            self.undress.offer(image, frame.captured)
        seen = self._on_floor(seen_things(things, width, height, fov), things, camera, width, height, fov)
        self._measure_motion(image, camera, frame.captured, at, fov)
        floor, floor_at = self._floor_step(image, camera, frame.captured, at, fov, seen)
        return Sight(at=at, camera=camera, fov_h_deg=fov, people=seen_people(found, width, height, fov, poses, speaking), tags=tuple(tags), things=seen, floor=floor, floor_at=floor_at)

    def _floor_step(self, image, camera: str, captured: float, at: float, fov: float, seen):
        if self.floor is None or not self._enabled:
            return (), None
        from .floor import cut

        self.floor.offer(image, camera, captured, at, fov, self.head(camera))
        found, found_at = self.floor.current(camera, captured)
        return cut(found, seen, self.floor.reach_m), found_at

    def _measure_motion(self, image, camera: str, captured: float, at: float, fov: float) -> None:
        from .detect import opencv

        try:
            cv2, np = opencv()
            small = cv2.cvtColor(cv2.resize(image, MOTION_SIZE, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
        except Exception:
            return
        prev, self._motion_prev = self._motion_prev, (camera, captured, small)
        if prev is None or prev[0] != camera or captured - prev[1] > 0.5 or captured <= prev[1]:
            return
        if self._window is None:
            self._window = cv2.createHanningWindow(MOTION_SIZE, cv2.CV_32F)
        change = float(np.abs(small - prev[2]).mean() / 255.0)
        (dx, dy), response = cv2.phaseCorrelate(prev[2].copy(), small.copy(), self._window)
        per_px = fov / MOTION_SIZE[0]
        self._motion = {"at": at, "dt": round(captured - prev[1], 3), "shift_deg": (round(dx * per_px, 2), round(dy * per_px, 2)), "sure": round(float(response), 3), "change": round(change, 4), "camera": camera}

    def motion(self) -> dict | None:
        return dict(self._motion) if self._motion is not None else None

    def set_moving(self, on: bool) -> None:
        if self.floor is not None:
            self.floor.set_moving(on)
        if self._private:
            self._wake.set()

    def scan_floor(self) -> None:
        if self.floor is not None and not self._private:
            self.floor.want()

    async def place_print(self, camera: str | None = None) -> tuple[float, ...] | None:
        snap = self._fresh_snapshot()
        if snap is None or (camera is not None and snap.camera != camera):
            return None
        model = await asyncio.to_thread(self._prints)
        if model is None:
            return None
        boxes = [Box(0.0, 0.0, 1.0, 1.0, 1.0)] + [Box(x, y, 0.5, 0.5, 1.0) for y in (0.0, 0.5) for x in (0.0, 0.5)]
        vecs = await asyncio.to_thread(model.embed, snap.image, boxes)
        mean = vecs.mean(axis=0)
        norm = float((mean * mean).sum()) ** 0.5
        if norm <= 1e-9:
            return None
        return tuple(round(float(x) / norm, 6) for x in mean)

    def _with_hazards(self, things, camera: str, captured: float):
        if self.hazards is None or not self._enabled:
            return things
        found = self.hazards.current(camera, captured)
        return things + [h for h in found if h.label in ("fire", "smoke") or not any(o.label == h.label and _overlap(o.box, h.box) >= 0.4 for o in things)]

    def set_head(self, tilt_deg: float | None = None, roll_deg: float | None = None) -> None:
        if tilt_deg is not None:
            self._tilt = float(tilt_deg)
        if roll_deg is not None:
            self._roll = float(roll_deg)

    def head(self, camera: str) -> tuple[float, float, float]:
        sign = 1.0 if camera == "front" else -1.0
        return self.cameras[camera]["height_m"], sign * self._tilt, sign * self._roll

    def _on_floor(self, seen, things, camera: str, width: int, height: int, fov: float):
        height_m, pitch, roll = self.head(camera)
        out = []
        for item, thing in zip(seen, things):
            spot = floor_point(thing.box.cx, thing.box.y + thing.box.h, width, height, fov, height_m, pitch, roll)
            out.append(replace(item, floor_m=round(spot[0], 3), floor_bearing_deg=round(spot[1], 2)) if spot else item)
        return tuple(out)

    def _pose_step(self, image, found, captured: float, width: int, height: int, fov: float):
        if self.pose is None:
            return {}, []
        from .pose import body_points, facing, wrists
        from .posture import posture

        if captured - self._pose_at >= 1.0 / self.pose_hz:
            bodies = sorted((c for c in found if c.body and c.box is not None), key=lambda c: c.box.w * c.box.h, reverse=True)[:POSE_PEOPLE]
            if bodies:
                started = time.perf_counter()
                for c in bodies:
                    self._poses[c.track] = (self.pose.points(image, c.box), captured)
                self._ms.add("pose", (time.perf_counter() - started) * 1000)
                self._pose_at = captured
        tracks = {c.track: c for c in found}
        self._poses = {k: v for k, v in self._poses.items() if k in tracks and captured - v[1] <= POSE_KEEP_S}
        height_m, pitch, roll = self.head(self._camera_of(found))
        out, hands = {}, []
        for track, (raw, _) in self._poses.items():
            box = tracks[track].box
            label, sure = posture(raw, box, width, height, fov, height_m, pitch, roll) if box is not None else (None, 0.0)
            out[track] = (body_points(raw, width, height, fov), facing(raw), label, sure)
            hands.extend(wrists(raw))
        return out, hands

    def _speak_step(self, image, found, faces, marks, captured: float, at: float, width: int, height: int) -> dict:
        if self.speaking is None or len(marks) != len(faces):
            return {}
        where = {(f.cx, f.cy): i for i, f in enumerate(faces)}
        mouths = []
        for c in found:
            i = where.get((c.u, c.v)) if c.face else None
            if i is None or c.track is None:
                continue
            f = faces[i]
            mouths.append((c.track, (f.x * width, f.y * height, f.w * width, f.h * height), [(u * width, v * height) for u, v in marks[i]]))
        started = time.perf_counter()
        out = self.speaking.step(image, mouths, captured, at)
        if mouths and self.speaking.active():
            self._ms.add("mouth", (time.perf_counter() - started) * 1000)
        return out

    def hear_voice(self, on: bool) -> None:
        if self.speaking is not None:
            self.speaking.hear_voice(on)

    def spoke(self, start: float, end: float) -> dict[int, float]:
        return self.speaking.spoke(start, end) if self.speaking is not None else {}

    def _camera_of(self, found) -> str:
        return self._tracker.camera or "front"

    def _track_things(self, found, at: float, captured: float, camera: str, aspect: float) -> list[Thing]:
        candidates = [Candidate(f.box.cx, f.box.cy, f.box.w, f.box.h, f.box.score, False, label=f.label) for f in found]
        self._thing_tracker.update(candidates, captured, camera, aspect)
        return [Thing(f.box, f.label, f.animal, at, "fast", self._depth(f.label), c.track) for f, c in zip(found, candidates)]

    def _depth(self, label: str) -> int:
        lane = self.slow
        detector = getattr(lane, "detector", None) if lane is not None else None
        return int(getattr(detector, "coco_depth", {}).get(label, 6)) if detector is not None else 6

    def _slow_now(self, camera: str, captured: float) -> list[Thing]:
        if self.slow is None:
            return []
        result = self.slow.current(camera, captured)
        if result is None:
            return []
        with self._things_lock:
            if result is not self._slow_pass:
                self._slow_pass = result
                candidates = [Candidate(f.box.cx, f.box.cy, f.box.w, f.box.h, f.box.score, False, label=f.label) for f in result.found]
                self._slow_tracker.update(candidates, result.captured, camera, result.width / max(1, result.height))
                self._slow_things = [Thing(f.box, f.label, f.animal, result.at, "slow", f.depth, c.track, known=getattr(f, "known", None), known_score=getattr(f, "known_score", 0.0)) for f, c in zip(result.found, candidates)]
            return list(self._slow_things)

    def _prints(self):
        with self._print_lock:
            if self._print_model is None and self._make_prints is not None and not self._print_problem:
                try:
                    self._print_model = self._make_prints()
                except Exception as error:
                    self._print_problem = str(error)
                    log.warning("eyes: prints are off: %s", error)
            return self._print_model

    def _recognise(self, image, found):
        if not self.book:
            return found
        model = self._prints()
        if model is None:
            return found
        top = sorted(found, key=lambda f: f.box.w * f.box.h, reverse=True)[:KNOWN_MAX]
        marks = {}
        for f, (key, score) in zip(top, self.book.best(model.embed(image, [f.box for f in top]))):
            if key is not None and score >= self.book.match:
                marks[id(f)] = (key, round(score, 3))
        return [replace(f, known=marks[id(f)][0], known_score=marks[id(f)][1]) if id(f) in marks else f for f in found]

    def _fresh_snapshot(self, max_age_s: float = SNAPSHOT_S) -> Snapshot | None:
        with self._things_lock:
            snap = self._snapshot
        if snap is None or not self._enabled or self._private or self.clock.monotonic() - snap.captured > max_age_s:
            return None
        return snap

    def remember_print(self, key: str, vec, replace: bool = False) -> int:
        return self.book.remember(str(key), vec, replace)

    def forget_print(self, key: str) -> bool:
        return self.book.forget(str(key))

    async def fingerprint(self, track: int) -> tuple[float, ...] | None:
        snap = self._fresh_snapshot()
        if snap is None:
            return None
        box = snap.people.get(track) or next((t.box for t in snap.things if t.track == track), None)
        if box is None:
            return None
        model = await asyncio.to_thread(self._prints)
        if model is None:
            return None
        vecs = await asyncio.to_thread(model.embed, snap.image, [box])
        return tuple(round(float(x), 6) for x in vecs[0])

    async def dock_print(self) -> tuple[float, ...] | None:
        snap = self._fresh_snapshot()
        if snap is None or self.detector is None:
            return None
        from .prints import dock_box

        found = await asyncio.to_thread(self.detector.tags, snap.image, snap.fov_h_deg)
        tag = next((t for t in found if t.seen.id == DOCK_TAG_ID and t.rotation is not None), None)
        if tag is None:
            return None
        height, width = snap.image.shape[:2]
        box = dock_box(tag.rotation, tag.translation, width, height, snap.fov_h_deg)
        model = await asyncio.to_thread(self._prints)
        if box is None or model is None:
            return None
        vecs = await asyncio.to_thread(model.embed, snap.image, [box])
        return tuple(round(float(x), 6) for x in vecs[0])

    def _vetoed(self, snap: Snapshot) -> bool:
        undressed = None
        if self.undress is not None:
            try:
                undressed = self.undress.check(snap.image)
            except Exception:
                log.exception("eyes: the privacy cue model failed on a picture for a question")
                return True
        veto = self.snapshot_veto
        if veto is None:
            return False
        try:
            return bool(veto(list(snap.people.values()), [(t.label, t.box) for t in snap.things], undressed))
        except Exception:
            log.exception("eyes: the privacy check on a picture failed")
            return True

    async def snapshot(self, max_side: int = 768, camera: str | None = None) -> bytes | None:
        if not self._enabled or self._private:
            return None
        if camera is not None and camera != self.camera():
            if not await self.use_camera(camera):
                return None
            started = self.clock.monotonic()
            while self.clock.monotonic() - started < 2.0:
                snap = self._fresh_snapshot(0.5)
                if snap is not None and snap.camera == camera:
                    break
                await asyncio.sleep(0.05)
        snap = self._fresh_snapshot()
        if snap is None or (camera is not None and snap.camera != camera):
            return None
        if await asyncio.to_thread(self._vetoed, snap):
            if self.on_cue is not None:
                self.on_cue()
            return None
        if self._private:
            return None
        return await asyncio.to_thread(_jpeg, snap.image, max(64, int(max_side)))

    async def look_for(self, key: str, camera: str | None = None) -> SeenThing | None:
        if not self._enabled or key not in self.book.keys():
            return None
        if camera is not None and camera != self.camera():
            if not await self.use_camera(camera):
                return None
            started = self.clock.monotonic()
            while self.clock.monotonic() - started < 2.0:
                snap = self._fresh_snapshot(0.5)
                if snap is not None and snap.camera == camera:
                    break
                await asyncio.sleep(0.05)
        snap = self._fresh_snapshot()
        if snap is None or (camera is not None and snap.camera != camera):
            return None
        model = await asyncio.to_thread(self._prints)
        if model is None:
            return None
        hit = await asyncio.to_thread(self._search, model, snap, key)
        if hit is None:
            return None
        box, score = hit
        height, width = snap.image.shape[:2]
        bearing, elevation = angles(box.cx, box.cy, width, height, snap.fov_h_deg)
        return SeenThing(label=key, bearing_deg=round(bearing, 2), elevation_deg=round(elevation, 2), height_frac=round(box.h, 4), width_frac=round(box.w, 4), score=round(score, 3), at=snap.at, lane="slow", known=key, known_score=round(score, 3))

    def _search(self, model, snap: Snapshot, key: str):
        from .prints import find

        proposals = [t.box for t in snap.things] + list(snap.people.values())
        detector = getattr(self.slow, "detector", None) if self.slow is not None else None
        if detector is not None:
            try:
                proposals += [f.box for f in detector.detect(snap.image, score=0.1)]
            except Exception:
                log.exception("eyes: the slow lane could not propose places to look")
        height, width = snap.image.shape[:2]
        started = time.perf_counter()
        hit = find(model, self.book, key, snap.image, proposals, frame_aspect=width / height)
        self._ms.add("look_for", (time.perf_counter() - started) * 1000)
        if hit is None or hit[1] < self.book.match:
            return None
        return hit[0], hit[1]

    def set_busy(self, busy: bool) -> None:
        if self.slow is not None:
            self.slow.set_busy(busy)

    def moved(self) -> None:
        if self.slow is not None:
            self.slow.moved()

    async def look_closely(self, timeout_s: float = 6.0) -> Sight | None:
        base = self.latest(self.stale_s)
        if base is None or self.slow is None or not self._enabled or self._private:
            return base
        loop = asyncio.get_running_loop()
        future = self.slow.demand(loop)
        try:
            result = await asyncio.wait_for(asyncio.shield(future), timeout_s)
        except asyncio.TimeoutError:
            result = None
        latest = self.latest(self.stale_s) or base
        if result is None or result.camera != latest.camera or self._private:
            return None if self._private else latest
        with self._things_lock:
            fast = list(self._fast_things) if self._fast_camera == latest.camera else []
        settings = self.cameras[latest.camera]
        width, height = result.width, result.height
        things = self._with_hazards(merge(fast, self._slow_now(latest.camera, result.captured)), latest.camera, result.captured)
        seen = self._on_floor(seen_things(things, width, height, settings["fov_h_deg"]), things, latest.camera, width, height, settings["fov_h_deg"])
        return Sight(at=latest.at, camera=latest.camera, fov_h_deg=settings["fov_h_deg"], people=latest.people, tags=latest.tags, things=seen)

    def status(self) -> dict:
        sight = self.latest(self.stale_s)
        out = {
            "on": self._enabled,
            "want": self._want,
            "camera": self.camera(),
            "available": self.available,
            "fps": round(self._fps, 1),
            "ms": {key: round(value, 1) for key, value in self._ms.values.items()},
            "frames": self.frames,
            "problem": self.problem,
            "can": self.detector.can if self.detector is not None else {},
        }
        out["prints"] = {"keys": self.book.keys(), "problem": self._print_problem, "loaded": self._print_model is not None}
        if self.hazards is not None:
            out["hazards"] = self.hazards.status()
        if self.speaking is not None:
            out["speaking"] = self.speaking.status()
        if self.floor is not None:
            out["floor"] = self.floor.status()
        if self.undress is not None:
            out["privacy_cue"] = self.undress.status()
        out["looking_away"] = self._private
        out["motion"] = self.motion()
        out["head"] = {"tilt_deg": self._tilt, "roll_deg": self._roll}
        if self.slow is not None:
            detector = self.slow.detector
            out["slow"] = {"busy": self.slow.busy, "passes": self.slow.passes, "ms": round(self.slow.last_ms, 1), "problem": self.slow.problem, "backend": getattr(detector, "backend", None)}
        if sight is not None:
            out["sight"] = {"camera": sight.camera, "people": [asdict(p) for p in sight.people], "tags": [asdict(t) for t in sight.tags], "things": [asdict(t) for t in sight.things]}
        return out


def _jpeg(image, max_side: int) -> bytes | None:
    from .detect import opencv

    cv2, _ = opencv()
    height, width = image.shape[:2]
    k = min(1.0, max_side / max(height, width))
    small = cv2.resize(image, (max(1, round(width * k)), max(1, round(height * k))), interpolation=cv2.INTER_AREA) if k < 1 else image
    ok, data = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return bytes(data) if ok else None


def _resolve(future: asyncio.Future, value: bool) -> None:
    if not future.done():
        future.set_result(value)
