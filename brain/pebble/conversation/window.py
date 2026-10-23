from collections import deque
from dataclasses import dataclass

KEEP_S = 300.0
CAP = 200


@dataclass(frozen=True)
class Line:
    at: float
    who: str | None
    label: str
    text: str
    label_kind: str
    audience: frozenset
    private: bool = False
    pebble: bool = False

    def shown(self) -> str:
        speaker = "you" if self.pebble else self.label
        return f'{speaker}: "{self.text}"'


def visible(line: Line, audience: frozenset) -> bool:
    if line.private:
        return audience <= {line.who} if line.who else False
    return audience <= line.audience


class Window:
    def __init__(self, keep_s: float = KEEP_S):
        self.keep_s = keep_s
        self.lines: deque = deque()

    def add(self, line: Line) -> None:
        self.lines.append(line)
        self.prune(line.at)

    def prune(self, now: float) -> None:
        while self.lines and (now - self.lines[0].at > self.keep_s or len(self.lines) > CAP):
            self.lines.popleft()

    def since(self, at: float) -> list[Line]:
        return [line for line in self.lines if line.at >= at]

    def recent(self, now: float, within: float) -> list[Line]:
        self.prune(now)
        return [line for line in self.lines if now - line.at <= within]

    def for_audience(self, now: float, audience: frozenset, within: float = KEEP_S, limit: int = 12) -> list[Line]:
        return [line for line in self.recent(now, within) if visible(line, audience)][-limit:]

    def forget(self, person_id: str) -> int:
        before = len(self.lines)
        self.lines = deque(line for line in self.lines if line.who != person_id and person_id not in line.audience)
        return before - len(self.lines)

    def clear(self) -> None:
        self.lines.clear()
