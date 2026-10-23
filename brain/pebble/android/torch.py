import json
import logging
import time

from .bridge import as_json, current, require

log = logging.getLogger(__name__)

DEFAULT_S = 600.0
LONGEST_S = 3600.0


def torch_seconds(asked: float) -> float:
    try:
        value = float(asked)
    except (TypeError, ValueError):
        return DEFAULT_S
    return min(LONGEST_S, value) if value > 0 and value == value else DEFAULT_S


class PhoneTorch:
    def __init__(self, bridge=None):
        self._bridge = bridge
        self._has: bool | None = None
        self.problem = ""

    def bridge(self):
        return self._bridge if self._bridge is not None else require("the torch")

    def info(self) -> dict:
        try:
            found = as_json(self.bridge().torchInfo(), {})
        except Exception as error:
            self.problem = str(error)
            return {"has_torch": False, "problem": str(error)}
        return found if isinstance(found, dict) else {}

    def has(self) -> bool:
        if self._has is None:
            self._has = bool(self.info().get("has_torch"))
        return self._has

    def set(self, on: bool, level: float = 1.0, seconds: float = DEFAULT_S) -> dict:
        try:
            found = as_json(self.bridge().torch(bool(on), float(level), float(seconds)), {})
        except Exception as error:
            self.problem = str(error)
            log.warning("torch: the phone would not switch its light %s: %s", "on" if on else "off", error)
            return {"has_torch": self._has is True, "wanted": False, "on": False, "problem": str(error)}
        found = found if isinstance(found, dict) else {}
        self.problem = str(found.get("problem") or "")
        if "has_torch" in found:
            self._has = bool(found["has_torch"])
        return found


class SimTorch:
    def __init__(self, monotonic=time.monotonic, has: bool = True, hot=lambda: False, refuse: str = ""):
        self.monotonic = monotonic
        self.has_torch = has
        self.hot = hot
        self.refuse = refuse
        self.wanted = False
        self.level = 1.0
        self.until = 0.0
        self.ended = ""
        self.problem = ""
        self.calls: list = []

    def _update(self) -> None:
        if self.wanted and self.monotonic() >= self.until:
            self.wanted = False
            self.ended = "its time ran out"
        if self.wanted and self.hot():
            self.wanted = False
            self.ended = "the phone got hot"

    def torch(self, on: bool, level: float, seconds: float) -> str:
        self.calls.append((bool(on), float(level), float(seconds)))
        self.ended = ""
        self.problem = ""
        if on and not self.has_torch:
            self.problem = "this phone has no light on its back"
        elif on and self.refuse:
            self.problem = f"the torch could not be switched on: {self.refuse}"
        else:
            self.wanted = bool(on)
            self.level = max(0.0, min(1.0, float(level)))
            self.until = self.monotonic() + torch_seconds(seconds)
        if not on:
            self.wanted = False
        return self.torchInfo()

    def torchInfo(self) -> str:
        self._update()
        left = max(0.0, self.until - self.monotonic()) if self.wanted else 0.0
        return json.dumps({"has_torch": self.has_torch, "wanted": self.wanted, "on": self.wanted, "level": self.level, "steps": 1, "through": "the sim", "left_s": round(left, 1), "free": True, "ended": self.ended, "problem": self.problem})


def torch_for(bridge=None):
    found = bridge if bridge is not None else current()
    if found is None or not hasattr(found, "torch"):
        return None
    return PhoneTorch(found)
