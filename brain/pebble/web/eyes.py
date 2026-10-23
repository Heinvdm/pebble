import asyncio
import logging
import math
import threading
from collections import deque
from dataclasses import asdict
from pathlib import Path

from ..clock import Clock
from ..seams.sight import CAMERAS, DOCK_TAG_ID, DOCK_TAG_SIZE_M, SeenPerson, SeenTag, Sight
from . import fetch_eyes
from .hub import Hub

log = logging.getLogger(__name__)

DEFAULT_CAMERAS = {
    "front": {"fov_h_deg": 70.0, "mirror": False, "rotate": None},
    "rear": {"fov_h_deg": 65.0, "mirror": False, "rotate": None},
}
PEOPLE_MODES = ("both", "faces", "bodies", "none")
MAX_PEOPLE = 12
MAX_TAGS = 8
MAX_TAG_ID = 586
SWITCH_TIMEOUT_S = 6.0
STALE_S = 1.5
RATE_HZ = 10.0
OFFSET_WINDOW = 64
MAX_LATENCY_S = 5.0
REPORT_STATES = ("on", "off", "waiting", "failed", "starting")


def _number(value, low: float, high: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} is not a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} is not finite")
    return max(low, min(high, number))


def _whole(value, low: int, high: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value != int(value):
        raise ValueError(f"{name} is not a whole number")
    number = int(value)
    if not low <= number <= high:
        raise ValueError(f"{name} is out of range")
    return number


def parse_person(data) -> SeenPerson:
    if not isinstance(data, dict):
        raise ValueError("a person is not an object")
    track = data.get("track")
    return SeenPerson(
        bearing_deg=_number(data.get("bearing_deg"), -90.0, 90.0, "bearing_deg"),
        elevation_deg=_number(data.get("elevation_deg"), -90.0, 90.0, "elevation_deg"),
        height_frac=_number(data.get("height_frac"), 0.0, 1.0, "height_frac"),
        width_frac=_number(data.get("width_frac"), 0.0, 1.0, "width_frac"),
        score=_number(data.get("score"), 0.0, 1.0, "score"),
        face=bool(data.get("face", False)),
        track=None if track is None else _whole(track, 0, 2**31 - 1, "track"),
    )


def parse_tag(data) -> SeenTag:
    if not isinstance(data, dict):
        raise ValueError("a tag is not an object")
    return SeenTag(
        id=_whole(data.get("id"), 0, MAX_TAG_ID, "id"),
        bearing_deg=_number(data.get("bearing_deg"), -90.0, 90.0, "bearing_deg"),
        distance_m=_number(data.get("distance_m"), 0.0, 50.0, "distance_m"),
        yaw_deg=_number(data.get("yaw_deg"), -180.0, 180.0, "yaw_deg"),
        score=_number(data.get("score", 1.0), 0.0, 1.0, "score"),
    )


def sight_from_dict(data, at: float) -> Sight:
    if not isinstance(data, dict):
        raise ValueError("not an object")
    camera = data.get("camera")
    if camera not in CAMERAS:
        raise ValueError("unknown camera")
    people = data.get("people", [])
    tags = data.get("tags", [])
    if not isinstance(people, list) or not isinstance(tags, list):
        raise ValueError("people and tags must be lists")
    return Sight(
        at=float(at),
        camera=camera,
        fov_h_deg=_number(data.get("fov_h_deg"), 1.0, 179.0, "fov_h_deg"),
        people=tuple(parse_person(p) for p in people[:MAX_PEOPLE]),
        tags=tuple(parse_tag(t) for t in tags[:MAX_TAGS]),
    )


def camera_settings(cameras: dict | None = None) -> dict:
    merged = {name: dict(values) for name, values in DEFAULT_CAMERAS.items()}
    for name, values in (cameras or {}).items():
        if name not in merged or not isinstance(values, dict):
            continue
        if "fov_h_deg" in values:
            merged[name]["fov_h_deg"] = _number(values["fov_h_deg"], 20.0, 150.0, "fov_h_deg")
        if "mirror" in values:
            merged[name]["mirror"] = bool(values["mirror"])
        if "rotate" in values:
            rotate = values["rotate"]
            merged[name]["rotate"] = None if rotate is None else _whole(rotate, 0, 270, "rotate") // 90 * 90
    return merged


class Latency:
    def __init__(self, window: int = OFFSET_WINDOW):
        self.sid = None
        self.offsets: deque[float] = deque(maxlen=window)

    def measure(self, sid, captured: float, sent: float, received: float) -> float:
        if sid != self.sid:
            self.sid = sid
            self.offsets.clear()
        sent = max(sent, captured)
        self.offsets.append(received - sent)
        captured_here = captured + min(self.offsets)
        return max(0.0, min(MAX_LATENCY_S, received - captured_here))


class BrowserEyes:
    def __init__(
        self,
        hub: Hub,
        clock: Clock | None = None,
        cameras: dict | None = None,
        tag_size_m: float = DOCK_TAG_SIZE_M,
        tag_id: int = DOCK_TAG_ID,
        enabled: bool = True,
        camera: str = "front",
        people: str = "both",
        switch_timeout_s: float = SWITCH_TIMEOUT_S,
        stale_s: float = STALE_S,
        rate_hz: float = RATE_HZ,
        vendor: Path = fetch_eyes.VENDOR,
    ):
        self.hub = hub
        self.clock = clock or Clock()
        self.cameras = camera_settings(cameras)
        self.tag_size_m = _number(tag_size_m, 0.005, 2.0, "tag_size_m")
        self.tag_id = _whole(tag_id, 0, MAX_TAG_ID, "tag_id")
        self.people_mode = people if people in PEOPLE_MODES else "both"
        self.switch_timeout_s = switch_timeout_s
        self.stale_s = stale_s
        self.rate_hz = max(1.0, min(30.0, float(rate_hz)))
        self.vendor = Path(vendor)
        self._lock = threading.Lock()
        self._enabled = bool(enabled)
        self._want = camera if camera in CAMERAS else "front"
        self._seq = 0
        self._latest: Sight | None = None
        self._latest_mono = -math.inf
        self._received_mono = -math.inf
        self._waiters: list[tuple[int, str, asyncio.Future, asyncio.AbstractEventLoop]] = []
        self._latency = Latency()
        self._page: dict = {}
        self._stats: dict = {}
        self.frames = 0
        self._private = False
        self.private_frames = 0
        if not fetch_eyes.ready(self.vendor):
            log.warning("the eye files are missing, so the face page cannot see; run: python -m pebble.web.fetch_eyes")
        hub.add_replay(self.replay)

    @property
    def available(self) -> bool:
        with self._lock:
            return self._enabled and self.clock.monotonic() - self._received_mono <= self.stale_s

    def start(self) -> None:
        pass

    def close(self) -> None:
        with self._lock:
            self._latest = None
            self._settle_all(False)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def latest(self, max_age_s: float = 0.5) -> Sight | None:
        with self._lock:
            if not self._enabled or self._latest is None:
                return None
            if self.clock.monotonic() - self._latest_mono > max_age_s:
                return None
            return self._latest

    def camera(self) -> str | None:
        with self._lock:
            if not self._enabled or self._latest is None or self.clock.monotonic() - self._received_mono > self.stale_s:
                return None
            return self._latest.camera

    def wanted(self) -> str:
        return self._want

    async def use_camera(self, camera: str) -> bool:
        if camera not in CAMERAS or not self._enabled:
            return False
        loop = asyncio.get_running_loop()
        with self._lock:
            fresh = self.clock.monotonic() - self._received_mono <= self.stale_s
            if fresh and self._want == camera and self._latest is not None and self._latest.camera == camera:
                return True
            self._seq += 1
            seq = self._seq
            self._want = camera
            future = loop.create_future()
            waiter = (seq, camera, future, loop)
            self._waiters.append(waiter)
        self._publish()
        try:
            return await asyncio.wait_for(asyncio.shield(future), self.switch_timeout_s)
        except asyncio.TimeoutError:
            log.info("the face page did not switch to the %s camera in time", camera)
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
                self._received_mono = -math.inf
                self._settle_all(False)
        if changed:
            log.info("eyes %s", "on" if on else "off")
            self._publish()

    @property
    def private(self) -> bool:
        return self._private

    def set_privacy(self, on: bool, keep=()) -> None:
        with self._lock:
            changed = bool(on) != self._private
            self._private = bool(on)
            if self._private:
                self._latest = None
                self._received_mono = -math.inf
                self._settle_all(False)
        if changed:
            log.info("eyes: %s", "looking away for privacy" if on else "looking again")
            self._publish()

    def _event(self) -> dict:
        return {"on": self._enabled and not self._private, "camera": self._want, "seq": self._seq}

    def _publish(self) -> None:
        self.hub.publish("eyes", self._event())

    def replay(self) -> list[tuple[str, object]]:
        with self._lock:
            return [("eyes", self._event())]

    def page_config(self) -> dict:
        vendor = {key: "/" + path for key, path in fetch_eyes.paths().items()}
        return {
            "camera": True,
            "assets": fetch_eyes.ready(self.vendor),
            "vendor": vendor,
            "cameras": self.cameras,
            "tag": {"id": self.tag_id, "size_m": self.tag_size_m},
            "people": self.people_mode,
            "rate_hz": self.rate_hz,
        }

    def _settle(self, seq: int, camera: str | None, ok: bool) -> None:
        for waiter in list(self._waiters):
            want_seq, want_camera, future, loop = waiter
            if seq < want_seq:
                continue
            result = ok and camera == want_camera
            self._waiters.remove(waiter)
            loop.call_soon_threadsafe(_resolve, future, result)

    def _settle_all(self, ok: bool) -> None:
        for _, _, future, loop in self._waiters:
            loop.call_soon_threadsafe(_resolve, future, ok)
        self._waiters.clear()

    def seen(self, data: dict) -> bool:
        received = self.clock.monotonic()
        wall = self.clock.now()
        if not isinstance(data, dict):
            raise ValueError("not an object")
        captured = _number(data.get("t"), -1e12, 1e12, "t")
        sent = _number(data.get("sent", captured), -1e12, 1e12, "sent")
        seq = _whole(data.get("seq", 0), 0, 2**31 - 1, "seq")
        sid = str(data.get("sid", ""))[:40]
        with self._lock:
            if not self._enabled:
                return False
            if self._private:
                self.private_frames += 1
                return False
            latency = self._latency.measure(sid, captured, sent, received)
            sight = sight_from_dict(data, wall - latency)
            self._latest = sight
            self._latest_mono = received - latency
            self._received_mono = received
            self.frames += 1
            stats = data.get("stats")
            if isinstance(stats, dict):
                self._stats = {str(k)[:24]: v for k, v in list(stats.items())[:16] if isinstance(v, (int, float, str)) and not isinstance(v, bool)}
            self._stats["latency_ms"] = round(latency * 1000, 1)
            self._settle(seq, sight.camera, True)
        return True

    def report(self, data: dict) -> None:
        if not isinstance(data, dict):
            raise ValueError("not an object")
        state = data.get("state")
        if state not in REPORT_STATES:
            raise ValueError("unknown state")
        camera = data.get("camera")
        if camera is not None and camera not in CAMERAS:
            raise ValueError("unknown camera")
        seq = _whole(data.get("seq", 0), 0, 2**31 - 1, "seq")
        reason = str(data.get("reason", ""))[:200]
        with self._lock:
            previous = self._page.get("state")
            self._page = {"state": state, "camera": camera, "seq": seq, "reason": reason}
            for key in ("width", "height", "source"):
                value = data.get(key)
                if isinstance(value, (int, str)) and not isinstance(value, bool):
                    self._page[key] = value if isinstance(value, int) else value[:40]
            if state == "on":
                self._settle(seq, camera, True)
            elif state != "starting":
                self._settle(seq, camera, False)
        if state != previous:
            if state == "failed" or state == "waiting":
                log.warning("face page eyes: %s%s", state, f" ({reason})" if reason else "")
            else:
                log.info("face page eyes: %s%s", state, f" ({camera})" if camera else "")

    def status(self) -> dict:
        sight = self.latest(self.stale_s)
        with self._lock:
            out = {
                "on": self._enabled,
                "want": self._want,
                "seq": self._seq,
                "page": dict(self._page),
                "frames": self.frames,
                "stats": dict(self._stats),
            }
        out["available"] = self.available
        out["camera"] = self.camera()
        if sight is not None:
            out["sight"] = {
                "camera": sight.camera,
                "fov_h_deg": sight.fov_h_deg,
                "age_s": round(self.clock.now() - sight.at, 3),
                "people": [asdict(p) for p in sight.people],
                "tags": [asdict(t) for t in sight.tags],
            }
        return out


def _resolve(future: asyncio.Future, value: bool) -> None:
    if not future.done():
        future.set_result(value)
