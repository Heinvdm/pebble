import logging
from dataclasses import dataclass

from .bridge import as_json, current, number

log = logging.getLogger(__name__)

READ_EVERY_S = 5.0
LEVELS = ("cool", "warm", "hot")


@dataclass(frozen=True)
class Heat:
    level: str = "cool"
    slow: bool = False
    headroom: float | None = None


class PhoneHeat:
    def __init__(self, monotonic, bridge=None, every_s: float = READ_EVERY_S):
        self.monotonic = monotonic
        self._bridge = bridge
        self.every_s = every_s
        self.read_at = float("-inf")
        self.last = Heat()
        self.problem = ""

    def now(self) -> Heat:
        at = self.monotonic()
        if at - self.read_at < self.every_s:
            return self.last
        self.read_at = at
        bridge = self._bridge if self._bridge is not None else current()
        if bridge is None:
            return self.last
        try:
            data = as_json(bridge.phoneHeat(), {})
        except Exception as error:
            if str(error) != self.problem:
                log.warning("heat: the phone would not say how warm it is: %s", error)
            self.problem = str(error)
            return self.last
        self.problem = ""
        data = data if isinstance(data, dict) else {}
        level = str(data.get("level") or "cool")
        reading = Heat(level if level in LEVELS else "cool", bool(data.get("slow")), number(data.get("headroom")))
        if (reading.level, reading.slow) != (self.last.level, self.last.slow):
            log.info("heat: the phone is %s%s", reading.level, ", and slower than its bench" if reading.slow else "")
        self.last = reading
        return reading

    def status(self) -> dict:
        return {"level": self.last.level, "slow": self.last.slow, "headroom": self.last.headroom, "problem": self.problem}
