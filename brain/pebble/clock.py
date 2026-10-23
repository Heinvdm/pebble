import time
from datetime import datetime, timezone, tzinfo


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def from_iso(text: str) -> float:
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


class Clock:
    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()

    def local(self, ts: float | None = None) -> datetime:
        return datetime.fromtimestamp(self.now() if ts is None else ts).astimezone()


class FakeClock(Clock):
    def __init__(self, start: float = 1_792_000_000.0, tz: tzinfo = timezone.utc):
        self._now = float(start)
        self._mono = 1000.0
        self._tz = tz

    @classmethod
    def at(cls, moment: datetime) -> "FakeClock":
        tz = moment.tzinfo or timezone.utc
        return cls(moment.replace(tzinfo=tz).timestamp(), tz)

    def now(self) -> float:
        return self._now

    def monotonic(self) -> float:
        return self._mono

    def local(self, ts: float | None = None) -> datetime:
        return datetime.fromtimestamp(self._now if ts is None else ts, self._tz)

    def advance(self, seconds: float) -> None:
        self._now += seconds
        self._mono += seconds

    def set(self, ts: float) -> None:
        self._now = float(ts)
