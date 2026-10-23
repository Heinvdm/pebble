import math
import re
from dataclasses import dataclass

PAUSE_S = 2.0
STICKY_GONE_S = 600.0
STOP_WORDS = re.compile(r"\b(stop|halt|freeze|whoa|stay still|don'?t move|stand still)\b", re.IGNORECASE)
GO_WORDS = re.compile(r"\b(go ahead|carry on|keep going|off you go|you can (move|go) (again|now)|you can move|ok(ay)?,? (move|go))\b", re.IGNORECASE)


def says_stop(text: str) -> bool:
    return bool(STOP_WORDS.search(text)) and not GO_WORDS.search(text)


def says_go(text: str) -> bool:
    return bool(GO_WORDS.search(text))


@dataclass(frozen=True)
class StopNote:
    kind: str
    by: str | None
    text: str


class StopGuard:
    def __init__(self, pause_s: float = PAUSE_S, gone_s: float = STICKY_GONE_S):
        self.pause_s = pause_s
        self.gone_s = gone_s
        self.paused_until = -math.inf
        self.sticky_by: str | None = None
        self.sticky_at = -math.inf
        self._pause_reported = True

    def stop(self, person_id: str | None, label: str, sticky: bool, now: float) -> StopNote:
        if sticky:
            self.sticky_by = person_id
            self.sticky_at = now
            return StopNote("sticky", person_id, f"{label} told you to stop; you stopped and stay still until someone you trust says you may move")
        self.paused_until = max(self.paused_until, now + self.pause_s)
        self._pause_reported = False
        return StopNote("pause", person_id, f"{label} said stop; your wheels paused for {self.pause_s:g} seconds")

    def go(self, may_release: bool) -> bool:
        if not self.holding() or not may_release:
            return False
        self.sticky_by = None
        self.sticky_at = -math.inf
        return True

    def holding(self) -> bool:
        return not math.isinf(self.sticky_at)

    def lapse(self, last_present: float, now: float) -> bool:
        if not self.holding() or self.sticky_by is None:
            return False
        if now - max(last_present, self.sticky_at) >= self.gone_s:
            self.sticky_by = None
            self.sticky_at = -math.inf
            return True
        return False

    def blocked(self, now: float) -> str | None:
        if self.holding():
            return "someone you trust told you to stop and has not said you may move yet"
        if now < self.paused_until:
            return "you are pausing because someone said stop"
        return None

    def pause_over(self, now: float) -> bool:
        if self._pause_reported or now < self.paused_until:
            return False
        self._pause_reported = True
        return True
