import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Protocol

log = logging.getLogger(__name__)

KINDS = ("accel", "gyro", "pressure", "light", "proximity", "magnet")
MAX_ROWS = 4096
LATEST = 1 << 62


@dataclass(frozen=True)
class Sample:
    at: float
    values: tuple

    @property
    def value(self) -> float:
        return self.values[0]


class Feed(Protocol):
    def read(self) -> list[Sample]: ...


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


class BridgeFeed:
    def __init__(self, kind: str, bridge=None, monotonic: Callable[[], float] = time.monotonic, max_rows: int = MAX_ROWS):
        self.kind = kind
        self._bridge = bridge
        self.monotonic = monotonic
        self.max_rows = max_rows
        self.position: int | None = None
        self.skipped = 0
        self.problem = ""

    def bridge(self):
        if self._bridge is not None:
            return self._bridge
        from ..android.bridge import require

        return require("the phone's sensors")

    def read(self) -> list[Sample]:
        try:
            raw = self.bridge().sensorRead(self.kind, LATEST if self.position is None else self.position, self.max_rows)
            data = json.loads(str(raw)) if raw else {}
        except Exception as error:
            if not self.problem:
                log.warning("safety: the %s sensor could not be read: %s", self.kind, error)
            self.problem = str(error)
            return []
        self.problem = ""
        total = int(data.get("total") or 0)
        rows = data.get("rows") or []
        now_ms = _number(data.get("now_ms"))
        if self.position is None:
            self.position = total
            return []
        first = total - len(rows)
        if first > self.position:
            self.skipped += first - self.position
        self.position = total
        mono = self.monotonic()
        out = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 2:
                continue
            values = tuple(_number(v) for v in row[1:])
            stamp = _number(row[0])
            if stamp is None or any(v is None for v in values):
                continue
            at = mono - max(0.0, (now_ms - stamp) / 1000.0) if now_ms is not None else mono
            out.append(Sample(at, values))
        return out


class BridgeSensors:
    def __init__(self, bridge=None, monotonic: Callable[[], float] = time.monotonic):
        self._bridge = bridge
        self.monotonic = monotonic
        self.feeds = {kind: BridgeFeed(kind, bridge, monotonic) for kind in KINDS}
        self.on = False
        self.details: dict = {}

    def bridge(self):
        if self._bridge is not None:
            return self._bridge
        from ..android.bridge import require

        return require("the phone's sensors")

    def start(self) -> None:
        try:
            self.bridge().sensorTap(True)
            self.on = True
            self.details = json.loads(str(self.bridge().sensorInfo() or "{}"))
        except Exception as error:
            log.warning("safety: the phone's sensors would not start: %s", error)

    def stop(self) -> None:
        if not self.on:
            return
        try:
            self.bridge().sensorTap(False)
        except Exception as error:
            log.warning("safety: the phone's sensors would not stop: %s", error)
        self.on = False

    def feed(self, kind: str) -> BridgeFeed:
        return self.feeds[kind]

    def has(self, kind: str) -> bool:
        return kind in self.details

    def max_range(self, kind: str) -> float | None:
        entry = self.details.get(kind) or {}
        return _number(entry.get("max_range"))


class ListFeed:
    def __init__(self):
        self.pending: deque = deque()

    def push(self, at: float, *values: float) -> None:
        self.pending.append(Sample(at, tuple(values)))

    def extend(self, samples) -> None:
        self.pending.extend(samples)

    def read(self) -> list[Sample]:
        out = list(self.pending)
        self.pending.clear()
        return out


class NoFeed:
    def read(self) -> list[Sample]:
        return []
