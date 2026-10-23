import asyncio
import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

from ..clock import Clock
from .engine import Engine, Models, NoEngine, Settings
from .events import MODES, SpeechEvent
from .fetch import MODELS

log = logging.getLogger(__name__)

CHECK_S = 1.0
QUEUE_S = 10.0
RATE = 16000


def _copy(samples):
    copy = getattr(samples, "copy", None)
    return copy() if callable(copy) else samples[:]


class SherpaEars:
    def __init__(self, clock: Clock | None = None, folder: Path = MODELS, source=None, threads: int = 1, listen: bool = True, check_s: float = CHECK_S, models=None):
        self.clock = clock or Clock()
        self.folder = Path(folder)
        self.source = source
        self.threads = threads
        self.enabled = bool(listen)
        self.check_s = check_s
        self.models = models
        self.policy: Callable[[bool, bool], str] | None = None
        self.sink: Callable[[SpeechEvent], None] | None = None
        self.speaking: Callable[[], bool] = lambda: False
        self.life = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.mode = "off"
        self.listening = False
        self.problem = ""
        self.events = 0
        self._awake_until = float("-inf")
        self._settings: dict = {}
        self._queue: deque = deque()
        self._queued_s = 0.0
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.engine: Engine | None = None
        self.dropped_s = 0.0

    def tap(self, block, muted: bool = False) -> None:
        if muted:
            self.push(None, block.end, gap=True)
            return
        self.push(block.samples, block.end, gap=bool(getattr(block, "skipped", 0)))

    def push(self, samples, end: float, gap: bool = False) -> None:
        if self.mode == "off" and not gap:
            return
        seconds = 0.0 if samples is None else len(samples) / RATE
        with self._lock:
            self._queue.append((None if samples is None else _copy(samples), end, gap))
            self._queued_s += seconds
            while self._queued_s > QUEUE_S and len(self._queue) > 1:
                old = self._queue.popleft()
                lost = 0.0 if old[0] is None else len(old[0]) / RATE
                self._queued_s -= lost
                self.dropped_s += lost
                self._queue.appendleft((None, old[1], True))
                break
        self._wake.set()

    def wanted_mode(self) -> str:
        if not self.enabled or self.life is None:
            return "off"
        awake = self.clock.monotonic() < self._awake_until
        if awake:
            return "words"
        quiet = self.life.quiet_hours.contains(self.clock.local())
        if self.policy is not None:
            try:
                chosen = str(self.policy(quiet, awake))
            except Exception as error:
                log.warning("ears: the listening policy failed (%s); keeping words off in quiet hours", error)
                chosen = "off" if quiet else "words"
            return chosen if chosen in MODES else "off"
        return "off" if quiet else "words"

    def wake_for(self, seconds: float) -> None:
        self._awake_until = max(self._awake_until, self.clock.monotonic() + max(0.0, float(seconds)))
        self._call(self.update)

    def set_enabled(self, on: bool) -> None:
        self.enabled = bool(on)
        self._call(self.update)

    def configure(self, **settings) -> None:
        with self._lock:
            self._settings.update(settings)
        self._wake.set()

    def _call(self, fn) -> None:
        loop = self.loop
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(fn)
            except RuntimeError:
                pass

    def update(self) -> None:
        mode = self.wanted_mode()
        if mode != self.mode:
            self.mode = mode
            self.configure(mode=mode)
            log.info("ears: listening mode %s", mode)
        self.listening = mode != "off"

    def _deliver(self, event: SpeechEvent) -> None:
        self.events += 1
        if self.sink is not None:
            try:
                self.sink(event)
            except Exception:
                log.exception("ears: the conversation could not take a speech event")

    def _post(self, events: list[SpeechEvent]) -> None:
        loop = self.loop
        if not events or loop is None or loop.is_closed():
            return
        for event in events:
            try:
                loop.call_soon_threadsafe(self._deliver, event)
            except RuntimeError:
                return

    def _build(self) -> Engine | None:
        try:
            models = self.models or Models(self.folder, self.threads)
        except NoEngine as error:
            self.problem = str(error)
            log.warning("ears: %s; Pebble hears no words", error)
            return None
        return Engine(models, Settings(threads=self.threads), speaking=lambda: bool(self.speaking()))

    def _work(self) -> None:
        engine = self._build()
        self.engine = engine
        if engine is None:
            return
        import numpy

        scale = 1.0 / 32768.0
        while not self._stop.is_set():
            with self._lock:
                settings, self._settings = self._settings, {}
                item = self._queue.popleft() if self._queue else None
                if item is not None and item[0] is not None:
                    self._queued_s -= len(item[0]) / RATE
            if settings:
                engine.configure(**settings)
            if self.source is not None and item is None:
                block = self._read_source()
                if block is not None:
                    item = (block.samples, block.end, bool(block.skipped))
            if item is None:
                self._wake.wait(0.05)
                self._wake.clear()
                continue
            samples, end, gap = item
            if gap:
                engine.gap()
            if samples is None or not len(samples):
                continue
            values = numpy.asarray(samples)
            values = values.astype(numpy.float32) if values.dtype.kind == "f" else values.astype(numpy.float32) * scale
            try:
                self._post(engine.feed(values, end))
            except Exception as error:
                self.problem = str(error)
                log.exception("ears: the speech engine failed on a block")
                engine.gap()

    def _read_source(self):
        try:
            return self.source.read(0.2)
        except Exception as error:
            self.problem = str(error)
            time.sleep(0.2)
            return None

    def start(self) -> None:
        if self._thread is not None:
            return
        if self.source is not None:
            try:
                self.source.start()
            except Exception as error:
                self.problem = str(error)
        self._stop.clear()
        self._thread = threading.Thread(target=self._work, name="pebble-speech", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=5)
        if self.source is not None:
            try:
                self.source.stop()
            except Exception:
                pass

    async def run(self, life) -> None:
        self.life = life
        self.loop = asyncio.get_running_loop()
        self.start()
        try:
            while True:
                self.update()
                await asyncio.sleep(self.check_s)
        finally:
            self.stop()
            self.listening = False

    def status(self) -> dict:
        engine = self.engine
        return {
            "kind": "sherpa",
            "enabled": self.enabled,
            "listening": self.listening,
            "mode": self.mode,
            "awake_for_s": round(max(0.0, self._awake_until - self.clock.monotonic()), 1),
            "events": self.events,
            "queued_s": round(self._queued_s, 2),
            "dropped_s": round(self.dropped_s, 2),
            "engine": engine.status() if engine is not None else None,
            "problem": self.problem,
        }
