import array
import logging
import subprocess
import sys
import threading
import time
import wave
from collections import deque
from pathlib import Path
from typing import Callable

from .audio import RATE, Block, pcm_to_samples, resample, to_floats, to_samples

log = logging.getLogger(__name__)

RING_S = 10.0
ARECORD = ("arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(RATE), "-c", "1")
PARECORD = ("parecord", "--raw", "--format=s16le", f"--rate={RATE}", "--channels=1")
RECORDERS = (ARECORD, PARECORD)


def _decode(data: bytes, width: int) -> list[float]:
    if width == 2:
        return to_floats(pcm_to_samples(data))
    if width == 1:
        return [(b - 128) / 128.0 for b in data]
    if width == 3:
        out = []
        for i in range(0, len(data) - 2, 3):
            value = data[i] | (data[i + 1] << 8) | (data[i + 2] << 16)
            out.append((value - (1 << 24) if value >= 1 << 23 else value) / float(1 << 23))
        return out
    if width == 4:
        values = array.array("i")
        values.frombytes(data[: len(data) // 4 * 4])
        if sys.byteorder == "big":
            values.byteswap()
        return [v / float(1 << 31) for v in values]
    raise ValueError(f"{width * 8}-bit samples are not supported")


def read_wav(path) -> list[float]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        data = handle.readframes(handle.getnframes())
    values = _decode(data, width)
    if channels > 1:
        values = [sum(values[i : i + channels]) / channels for i in range(0, len(values) - channels + 1, channels)]
    return resample(values, rate)


class ArraySource:
    def __init__(self, samples, monotonic: Callable[[], float] | None = None, loop: bool = False, start_at: float | None = None):
        self.samples = samples if isinstance(samples, array.array) else to_samples(samples)
        self.monotonic = monotonic
        self.loop = loop
        self.position = 0
        self.started_at = start_at
        self.running = False

    def start(self) -> None:
        self.running = True
        if self.started_at is None and self.monotonic is not None:
            self.started_at = self.monotonic()

    def stop(self) -> None:
        self.running = False

    def _available(self) -> int:
        if self.monotonic is None or self.started_at is None:
            return len(self.samples) * (1000 if self.loop else 1) - self.position
        due = int((self.monotonic() - self.started_at) * RATE)
        if not self.loop:
            due = min(due, len(self.samples))
        return max(0, due - self.position)

    def read(self, max_seconds: float = 1.0) -> Block | None:
        count = min(self._available(), int(max_seconds * RATE))
        if count <= 0 or not len(self.samples):
            return None
        out = array.array("h")
        while len(out) < count:
            offset = self.position % len(self.samples) if self.loop else self.position
            if offset >= len(self.samples):
                break
            take = min(count - len(out), len(self.samples) - offset)
            out.extend(self.samples[offset : offset + take])
            self.position += take
        if not out:
            return None
        if self.monotonic is not None and self.started_at is not None:
            end = self.started_at + self.position / RATE
        else:
            end = self.position / RATE
        return Block(out, end)

    def done(self) -> bool:
        return not self.loop and self.position >= len(self.samples)

    def info(self) -> dict:
        return {"kind": "samples", "seconds": round(len(self.samples) / RATE, 2), "position_s": round(self.position / RATE, 2), "running": self.running}


class WavSource(ArraySource):
    def __init__(self, path, monotonic: Callable[[], float] | None = None, loop: bool = False):
        self.path = Path(path)
        super().__init__(read_wav(self.path), monotonic, loop)

    def info(self) -> dict:
        return dict(super().info(), kind="wav", path=self.path.name)


class AndroidTapSource:
    def __init__(self, tap=None, monotonic: Callable[[], float] = time.monotonic):
        if tap is None:
            from ..android.sounds import SoundTap

            tap = SoundTap()
        self.tap = tap
        self.monotonic = monotonic
        self.running = False
        self._skipped = 0
        self._speaking = False
        self._info: dict = {}

    def start(self) -> None:
        self.tap.start()
        self.running = True
        self._skipped = int(getattr(self.tap, "skipped", 0) or 0)

    def stop(self) -> None:
        self.running = False
        try:
            self.tap.stop()
        except Exception as error:
            log.warning("hearing: the sound tap would not stop: %s", error)

    def read(self, max_seconds: float = 1.0) -> Block | None:
        if not self.running:
            return None
        data = self.tap.read(max_seconds)
        try:
            self._info = self.tap.info()
        except Exception:
            self._info = {}
        skipped = int(getattr(self.tap, "skipped", 0) or 0)
        gap, self._skipped = max(0, skipped - self._skipped), skipped
        if not data:
            return Block(array.array("h"), self.monotonic(), gap, bool(self._info.get("speaking"))) if gap else None
        return Block(pcm_to_samples(data), self.monotonic(), gap, bool(self._info.get("speaking")))

    def info(self) -> dict:
        return dict(self._info, kind="android", skipped=self._skipped)


class CommandSource:
    def __init__(self, command=ARECORD, monotonic: Callable[[], float] = time.monotonic, ring_s: float = RING_S):
        self.command = tuple(command)
        self.monotonic = monotonic
        self.ring: deque = deque()
        self.ring_bytes = 0
        self.limit = int(ring_s * RATE * 2)
        self.lock = threading.Lock()
        self.process: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None
        self.dropped = 0
        self.problem = ""

    def start(self) -> None:
        if self.process is not None:
            return
        try:
            self.process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        except OSError as error:
            self.problem = f"could not start {self.command[0]}: {error}"
            log.warning("hearing: %s", self.problem)
            return
        self.thread = threading.Thread(target=self._pump, name="pebble-hearing-mic", daemon=True)
        self.thread.start()

    def _pump(self) -> None:
        stream = self.process.stdout
        while True:
            chunk = stream.read(RATE // 5)
            if not chunk:
                self.problem = f"{self.command[0]} stopped"
                return
            with self.lock:
                self.ring.append(chunk)
                self.ring_bytes += len(chunk)
                while self.ring_bytes > self.limit:
                    old = self.ring.popleft()
                    self.ring_bytes -= len(old)
                    self.dropped += len(old) // 2

    def stop(self) -> None:
        process, self.process = self.process, None
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

    def read(self, max_seconds: float = 1.0) -> Block | None:
        limit = int(max_seconds * RATE) * 2
        with self.lock:
            dropped, self.dropped = self.dropped, 0
            parts = []
            size = 0
            while self.ring and size < limit:
                chunk = self.ring.popleft()
                if size + len(chunk) > limit:
                    keep = limit - size
                    self.ring.appendleft(chunk[keep:])
                    chunk = chunk[:keep]
                parts.append(chunk)
                size += len(chunk)
            self.ring_bytes -= size
        if not parts and not dropped:
            return None
        return Block(pcm_to_samples(b"".join(parts)), self.monotonic(), dropped)

    def info(self) -> dict:
        return {"kind": "command", "command": self.command[0], "running": self.process is not None and self.process.poll() is None, "problem": self.problem}


class NoAudio:
    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def read(self, max_seconds: float = 1.0) -> None:
        return None

    def info(self) -> dict:
        return {"kind": "none"}


class MixSource:
    def __init__(self, monotonic: Callable[[], float], floor: list[float] | None = None):
        self.monotonic = monotonic
        self.clips: dict[str, tuple[list[float], float, bool]] = {}
        self.floor = floor or []
        self.last: float | None = None
        self.running = False

    def play(self, name: str, values: list[float], loop: bool = False, at: float | None = None) -> None:
        self.clips[name] = (values, self.monotonic() if at is None else at, loop)

    def stop_clip(self, name: str) -> None:
        self.clips.pop(name, None)

    def start(self) -> None:
        self.running = True
        self.last = self.monotonic()

    def stop(self) -> None:
        self.running = False

    def read(self, max_seconds: float = 1.0) -> Block | None:
        if not self.running:
            return None
        now = self.monotonic()
        begin = self.last if self.last is not None else now
        begin = max(begin, now - max_seconds)
        first = int(round(begin * RATE))
        last = int(round(now * RATE))
        if last <= first:
            return None
        self.last = last / RATE
        out = [0.0] * (last - first)
        if self.floor:
            size = len(self.floor)
            for i in range(len(out)):
                out[i] = self.floor[(first + i) % size]
        for values, at, loop in list(self.clips.values()):
            offset = int(round(at * RATE))
            size = len(values)
            if not size:
                continue
            for i in range(len(out)):
                k = first + i - offset
                if k < 0:
                    continue
                if loop:
                    k %= size
                elif k >= size:
                    break
                out[i] += values[k]
        return Block(to_samples(out), last / RATE)

    def info(self) -> dict:
        return {"kind": "mix", "playing": sorted(self.clips)}


def source_from(config: dict | None, monotonic: Callable[[], float] = time.monotonic):
    config = dict(config or {})
    kind = config.get("kind", "none")
    if kind == "android":
        return AndroidTapSource(monotonic=monotonic)
    if kind == "command":
        command = tuple(str(part) for part in (config.get("command") or ARECORD))
        if command not in RECORDERS:
            log.warning("hearing: a profile may name only a known recorder, so %r is not run", command[:1])
            return NoAudio()
        return CommandSource(command, monotonic)
    if kind == "wav":
        return WavSource(config["path"], monotonic, bool(config.get("loop", False)))
    return NoAudio()
