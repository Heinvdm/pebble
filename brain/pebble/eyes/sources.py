import logging
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .scene import TagPlacement, tag_scene

log = logging.getLogger(__name__)

GRAB_FAILURES = 30
OPEN_TRIES = 3


@dataclass(frozen=True)
class Frame:
    image: object
    camera: str
    captured: float
    number: int


class SourceError(Exception):
    pass


class FrameSource(Protocol):
    camera: str

    def open(self) -> None: ...

    def read(self, timeout_s: float) -> Frame | None: ...

    def close(self) -> None: ...


class LatestFrame:
    def __init__(self):
        self._cond = threading.Condition()
        self._frame: Frame | None = None
        self._number = 0
        self._taken = 0
        self._error: Exception | None = None

    def put(self, image, camera: str, captured: float) -> None:
        with self._cond:
            self._number += 1
            self._frame = Frame(image, camera, captured, self._number)
            self._cond.notify_all()

    def fail(self, error: Exception) -> None:
        with self._cond:
            self._error = error
            self._cond.notify_all()

    def reset(self) -> None:
        with self._cond:
            self._frame, self._error, self._taken = None, None, self._number

    def take(self, timeout_s: float) -> Frame | None:
        with self._cond:
            self._cond.wait_for(lambda: self._error is not None or self._number > self._taken, timeout=timeout_s)
            if self._error is not None:
                raise SourceError(str(self._error))
            if self._number <= self._taken or self._frame is None:
                return None
            self._taken = self._number
            return self._frame


class GrabbingSource:
    def __init__(self, camera: str, monotonic: Callable[[], float] = time.monotonic):
        self.camera = camera
        self.monotonic = monotonic
        self._latest = LatestFrame()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _start_device(self) -> None:
        raise NotImplementedError

    def _grab(self):
        raise NotImplementedError

    def _stop_device(self) -> None:
        pass

    def open(self) -> None:
        self._latest.reset()
        self._stop.clear()
        self._start_device()
        self._thread = threading.Thread(target=self._run, name=f"pebble-eyes-{self.camera}", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                image = self._grab()
                if image is not None and not self._stop.is_set():
                    self._latest.put(image, self.camera, self.monotonic())
        except Exception as error:
            if not self._stop.is_set():
                log.warning("the %s camera stopped: %s", self.camera, error)
                self._latest.fail(error)

    def read(self, timeout_s: float) -> Frame | None:
        return self._latest.take(timeout_s)

    def close(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=3.0)
        self._stop_device()


class OpenCVSource(GrabbingSource):
    def __init__(self, camera: str, device=0, width: int = 640, height: int = 480, fps: int = 30, monotonic: Callable[[], float] = time.monotonic):
        super().__init__(camera, monotonic)
        self.device = device
        self.width, self.height, self.fps = int(width), int(height), int(fps)
        self._cap = None
        self._misses = 0

    def _start_device(self) -> None:
        from .detect import opencv

        cv2, _ = opencv()
        backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
        device = int(self.device) if str(self.device).isdigit() else str(self.device)
        cap = cv2.VideoCapture(device, backend)
        if not cap.isOpened():
            cap.release()
            raise SourceError(f"cannot open the {self.camera} camera ({self.device})")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        for _ in range(OPEN_TRIES * 10):
            ok, image = cap.read()
            if ok and image is not None:
                self._cap, self._misses = cap, 0
                return
        cap.release()
        raise SourceError(f"the {self.camera} camera ({self.device}) opened but gave no picture")

    def _grab(self):
        ok, image = self._cap.read()
        if ok and image is not None:
            self._misses = 0
            return image
        self._misses += 1
        if self._misses > GRAB_FAILURES:
            raise SourceError("the camera gives no pictures any more")
        time.sleep(0.02)
        return None

    def _stop_device(self) -> None:
        cap, self._cap = self._cap, None
        if cap is not None:
            cap.release()


class PacedSource(GrabbingSource):
    def __init__(self, camera: str, fps: float = 15.0, monotonic: Callable[[], float] = time.monotonic):
        super().__init__(camera, monotonic)
        self.fps = max(0.5, float(fps))
        self._image = None
        self._next = 0.0

    def _picture(self):
        raise NotImplementedError

    def _start_device(self) -> None:
        self._image = self._picture()
        self._next = time.monotonic()

    def _grab(self):
        wait = self._next - time.monotonic()
        if wait > 0:
            self._stop.wait(wait)
        self._next = max(self._next + 1 / self.fps, time.monotonic())
        return self._image


class StillSource(PacedSource):
    def __init__(self, camera: str, picture, fps: float = 15.0, monotonic: Callable[[], float] = time.monotonic, size: tuple[int, int] | None = None):
        super().__init__(camera, fps, monotonic)
        self.picture = picture
        self.size = size

    def _picture(self):
        if not isinstance(self.picture, (str, Path)):
            return self.picture
        from .detect import opencv

        cv2, _ = opencv()
        image = cv2.imread(str(self.picture), cv2.IMREAD_COLOR)
        if image is None:
            raise SourceError(f"cannot read the picture {self.picture}")
        if self.size:
            h, w = image.shape[:2]
            k = min(self.size[0] / w, self.size[1] / h)
            if k < 1:
                image = cv2.resize(image, (max(1, round(w * k)), max(1, round(h * k))), interpolation=cv2.INTER_AREA)
        return image


class SceneSource(PacedSource):
    def __init__(self, camera: str, width: int = 640, height: int = 480, fov_h_deg: float = 65.0, tag: TagPlacement | None = None, fps: float = 15.0, monotonic: Callable[[], float] = time.monotonic):
        super().__init__(camera, fps, monotonic)
        self.width, self.height, self.fov_h_deg, self.tag = int(width), int(height), float(fov_h_deg), tag

    def _picture(self):
        if self.tag is None:
            import numpy as np

            return np.full((self.height, self.width, 3), 110, np.uint8)
        return tag_scene(self.width, self.height, self.fov_h_deg, self.tag)
