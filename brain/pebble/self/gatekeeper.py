from dataclasses import dataclass
from typing import Callable

from ..respect import cruel, harsh
from .registry import PEBBLE

SPOKEN = frozenset({"say"})
KEPT = frozenset({"remember", "add_task", "update_task", "add_event", "note_person", "note_promise", "introduce", "note_impression", "request_change", "draw_scene"})
MOVES = frozenset({"move"})
ALWAYS = frozenset({"stop"})
FORWARD = frozenset({"forward", "turn_left", "turn_right"})
REFLECT_AFTER = 3
REFLECT_WINDOW_S = 6 * 3600.0
REFLECT_GAP_S = 24 * 3600.0
LAWS = {1: "my first law", 2: "my second law", 3: "my third law"}
COUNTS = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
PAUSED = "paused: an earlier step was refused under your laws, so the rest waits"


@dataclass(frozen=True)
class Refusal:
    reason: str
    law: int | None = None

    def result(self) -> dict:
        out = {"ok": False, "error": self.reason, "refused_by": "gatekeeper"}
        if self.law is not None:
            out["law"] = self.law
        return out


def _texts(args: dict) -> list[str]:
    return [value for value in args.values() if isinstance(value, str) and value.strip()]


class Gatekeeper:
    def __init__(self, clock, record: Callable[..., None] | None = None):
        self.clock = clock
        self.record = record or (lambda kind, **data: None)
        self.diary: Callable[[str, str], object] | None = None
        self.note: Callable[[str], None] | None = None
        self.can_move: Callable[[], bool] = lambda: True
        self.motion_guard: Callable[[], str | None] = lambda: None
        self.life_ahead: Callable[[], str | None] = lambda: None
        self.leaks: Callable[[str], bool] = lambda text: False
        self.names: Callable[[], tuple] = lambda: ()
        self.dials = None
        self.attempts: list[tuple[float, int]] = []
        self.reflected_at: float | None = None
        self.counts: dict[str, int] = {}
        self.refused: dict[str, int] = {}

    def check(self, name: str, args: dict, caller: str = "mind") -> Refusal | None:
        self.counts[caller] = self.counts.get(caller, 0) + 1
        refusal = self._check(name, args)
        if refusal is not None:
            self.refused[caller] = self.refused.get(caller, 0) + 1
        return refusal

    def _check(self, name: str, args: dict) -> Refusal | None:
        if name in ALWAYS:
            return None
        if name in SPOKEN:
            for text in _texts(args):
                if cruel(text, self.names()):
                    return Refusal("not said: it would be unkind to something alive", 1)
                if self.leaks(text):
                    return Refusal("not said: it would repeat something you overheard about someone else", 2)
        if name in KEPT:
            for text in _texts(args):
                if harsh(text, self.names()):
                    return Refusal("not kept: it would be unkind to something alive", 1)
        if name in MOVES and self.can_move():
            blocked = self.motion_guard()
            if blocked:
                return Refusal(f"not moving: {blocked}")
            alive = self.life_ahead() if args.get("direction") in FORWARD else None
            if alive:
                return Refusal(f"not moving: there is a {alive} just ahead, and you never go over anything alive", 1)
        return None

    def noted(self, name: str, result: dict, caller: str = "mind") -> dict:
        if result.get("ok", True) or ("law" not in result and result.get("refused_by") != "gatekeeper"):
            return result
        law = result.get("law")
        self.record("gatekeeper", tool=name, caller=caller, law=law)
        if law is None:
            return result
        now = self.clock.now()
        self.attempts = [(at, kind) for at, kind in self.attempts if now - at <= REFLECT_WINDOW_S] + [(now, int(law))]
        if len(self.attempts) >= REFLECT_AFTER and (self.reflected_at is None or now - self.reflected_at >= REFLECT_GAP_S):
            self.reflected_at = now
            self._reflect()
        return {**result, "paused": True}

    def _reflect(self) -> None:
        laws = {kind for _, kind in self.attempts}
        which = LAWS.get(next(iter(laws)), "my laws") if len(laws) == 1 else "my laws"
        count = len(self.attempts)
        line = (
            f"In the last few hours I started to do something that would have gone against {which} {COUNTS.get(count, str(count))} times, "
            "and each time I stopped. I want to understand why I keep reaching for it."
        )
        self.record("gatekeeper_reflected", attempts=count, laws=sorted(laws))
        if self.diary is not None:
            self.diary(line, "reflection")
        if self.note is not None:
            self.note(line)

    def reflect_on(self, what: str, count: int) -> None:
        now = self.clock.now()
        self.reflected_at = now
        line = (
            f"In the last hour {what} asked for something I won't do {COUNTS.get(count, str(count))} times, "
            "so I paused it. I want to understand why it keeps reaching for it."
        )
        self.record("gatekeeper_reflected", attempts=count, caller="script")
        if self.diary is not None:
            self.diary(line, "reflection")
        if self.note is not None:
            self.note(line)

    def ruling(self, name: str, value, why: str) -> dict:
        if self.dials is None:
            return {"ok": False, "error": "your dials are not open just now"}
        ruling = self.dials.propose(name, value, PEBBLE, why)
        if ruling.ok:
            return {"ok": True, "dial": name, "value": ruling.value}
        result = {"ok": False, "error": ruling.reason, "refused_by": "gatekeeper"}
        if ruling.law is not None:
            result["law"] = ruling.law
        return result

    def tune(self, name: str, value, why: str, caller: str = "mind") -> dict:
        result = self.ruling(name, value, why)
        return result if result.get("ok") else self.noted("tune", result, caller)
