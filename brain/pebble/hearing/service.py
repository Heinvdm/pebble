import logging
import math
import threading
import time
from collections import deque
from typing import Callable

from ..safety.notice import Notice
from .alarm import AlarmDetector, AlarmHeard
from .audio import Block
from .chirp import CAP as CHIRP_CAP
from .chirp import KEEP_S as CHIRP_KEEP_S
from .chirp import Chirp, to_wall
from .events import KEEP_VECTORS, SoundEvents
from .level import LevelMeter, Loudness

log = logging.getLogger(__name__)

MAX_READS = 40
READ_S = 1.0
UNMUTE_S = 1.0


class Hearing:
    def __init__(self, source, now: Callable[[], float] = time.time, detector: AlarmDetector | None = None, meter: LevelMeter | None = None, model=None, events: SoundEvents | None = None):
        self.source = source
        self.now = now
        self.detector = detector or AlarmDetector()
        self.meter = meter or LevelMeter()
        self.model = model
        self.events = events if events is not None else (SoundEvents(model.labels) if model is not None else None)
        self.muted = False
        self.mute_until = -math.inf
        self.started = False
        self.seconds = 0.0
        self.cpu_s = 0.0
        self.problem = ""
        self.last_end: float | None = None
        self.taps: list = []
        self.block_taps: list = []
        self.vector_taps: list = []
        self.chirp_log: deque = deque(maxlen=CHIRP_CAP)
        self.vectors: deque = deque(maxlen=KEEP_VECTORS)
        self.profiler = None
        self.profiles: deque = deque(maxlen=KEEP_VECTORS)
        self.lock = threading.Lock()

    @property
    def want_vectors(self) -> bool:
        return bool(getattr(self.model, "want_vectors", False))

    @want_vectors.setter
    def want_vectors(self, on: bool) -> None:
        if self.model is not None and hasattr(self.model, "want_vectors"):
            self.model.want_vectors = bool(on)

    def chirps(self, since: float = -math.inf) -> list[Chirp]:
        with self.lock:
            return [chirp for chirp in self.chirp_log if chirp.at > since]

    def recent_vectors(self, seconds: float | None = None) -> list:
        with self.lock:
            found = list(self.vectors)
        if seconds is None or not found:
            return found
        last = found[-1][0]
        return [(at, vector) for at, vector in found if last - at <= seconds]

    def recent_profiles(self, since: float = -math.inf) -> list:
        with self.lock:
            return [item for item in self.profiles if item[0] > since]

    def start(self) -> None:
        if self.started:
            return
        try:
            self.source.start()
            self.started = True
        except Exception as error:
            self.problem = str(error)
            log.warning("hearing: could not start listening: %s", error)

    def stop(self) -> None:
        if not self.started:
            return
        self.started = False
        try:
            self.source.stop()
        except Exception as error:
            log.warning("hearing: could not stop listening: %s", error)

    def mute(self, on: bool, at: float) -> None:
        if on:
            self.muted = True
        elif self.muted:
            self.muted = False
            self.mute_until = at + UNMUTE_S

    def pump(self) -> list[Notice]:
        if not self.started:
            return []
        started = time.perf_counter()
        notices: list[Notice] = []
        for _ in range(MAX_READS):
            try:
                block = self.source.read(READ_S)
            except Exception as error:
                if not self.problem:
                    log.warning("hearing: could not read the microphone: %s", error)
                self.problem = str(error)
                break
            if block is None:
                break
            self.problem = ""
            notices.extend(self._take(block))
            if not len(block.samples) and not block.skipped:
                break
        self.cpu_s += time.perf_counter() - started
        return notices

    def _take(self, block: Block) -> list[Notice]:
        self.seconds += block.seconds
        self.last_end = block.end
        muted = self.muted or block.start < self.mute_until
        self.meter.feed(block, muted)
        for tap in list(self.block_taps):
            try:
                tap(block, muted)
            except Exception:
                log.exception("hearing: a listener of the sound failed")
        if muted:
            self.detector.gap(block.end)
            self._chirps(block)
            if self.model is not None:
                self.model.gap()
            if self.profiler is not None:
                self.profiler.gap()
            return []
        out = [self._alarm(item) for item in self.detector.feed(block)]
        self._chirps(block)
        self._profiles(block)
        if self.model is not None and self.events is not None:
            try:
                rows = self.model.feed(block)
            except Exception as error:
                if not self.problem:
                    log.warning("hearing: the sound model failed: %s", error)
                self.problem = str(error)
                rows = []
            for tap in list(self.taps):
                try:
                    tap(rows)
                except Exception:
                    log.exception("hearing: a listener of the sound model failed")
            self._vectors()
            for heard in self.events.feed(rows):
                out.append(Notice(heard.event, heard.confidence, "sound model", self.now(), heard.text, {"score": heard.score}))
        return out

    def _chirps(self, block: Block) -> None:
        found = self.detector.take_chirps() if hasattr(self.detector, "take_chirps") else []
        if not found:
            return
        now = self.now()
        with self.lock:
            for heard in found:
                self.chirp_log.append(to_wall(heard, block.end, now))
            while self.chirp_log and now - self.chirp_log[0].at > CHIRP_KEEP_S:
                self.chirp_log.popleft()

    def _profiles(self, block: Block) -> None:
        if self.profiler is None:
            return
        try:
            found = self.profiler.feed(block)
        except Exception:
            log.exception("hearing: the pitch profile failed")
            self.profiler = None
            return
        if found:
            with self.lock:
                self.profiles.extend(found)

    def _vectors(self) -> None:
        take = getattr(self.model, "take_vectors", None)
        if take is None:
            return
        try:
            found = take()
        except Exception:
            log.exception("hearing: the sound model's numbers could not be read")
            return
        if not found:
            return
        with self.lock:
            self.vectors.extend(found)
        for tap in list(self.vector_taps):
            try:
                tap(found)
            except Exception:
                log.exception("hearing: a listener of the sound model's numbers failed")

    def _alarm(self, item: AlarmHeard) -> Notice:
        return Notice(item.kind, item.confidence, "beeps", self.now(), item.text(), {"freq_hz": round(item.freq), "level_db": round(item.level_db, 1), "groups": item.groups, "pattern": item.pattern})

    def loudness(self, now: float | None = None) -> Loudness:
        return self.meter.recent(self.last_end if now is None and self.last_end is not None else (now or 0.0))

    def talk_db(self) -> float | None:
        return self.meter.talk_level(self.meter.floor())

    def status(self) -> dict:
        model = self.model.status() if self.model is not None and hasattr(self.model, "status") else None
        return {
            "listening": self.started,
            "muted": self.muted,
            "heard_s": round(self.seconds, 1),
            "cpu_ms_per_s": round(1000 * self.cpu_s / self.seconds, 2) if self.seconds else None,
            "beeps": self.detector.status(),
            "level_db": round(self.meter.now_db(), 1),
            "floor_db": round(self.meter.floor(), 1),
            "model": model,
            "source": self.source.info() if hasattr(self.source, "info") else {},
            "problem": self.problem,
        }
