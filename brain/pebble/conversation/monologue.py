from collections import deque

from .gist import Thought

KEEP_S = 1800.0
CAP = 60
SHOWN = 5
DIARY_PICKS = 3
DIARY_MIN_WEIGHT = 0.45


def visible(thought: Thought, audience: frozenset) -> bool:
    if not thought.private:
        return True
    if thought.kind == "fact":
        return bool(thought.about) and audience == frozenset(thought.about)
    return audience <= thought.audience if thought.audience else not audience


class Monologue:
    def __init__(self, keep_s: float = KEEP_S):
        self.keep_s = keep_s
        self.thoughts: deque = deque()
        self.day: list[Thought] = []
        self.last_feeling = ""

    def add(self, thought: Thought) -> Thought:
        self.thoughts.append(thought)
        while self.thoughts and (thought.at - self.thoughts[0].at > self.keep_s or len(self.thoughts) > CAP):
            self.thoughts.popleft()
        if thought.kind in ("gist", "seen", "felt", "said") and thought.weight >= DIARY_MIN_WEIGHT:
            self.day.append(thought)
            del self.day[:-50]
        return thought

    def feel(self, now: float, label: str) -> Thought | None:
        if not label or label == self.last_feeling:
            return None
        self.last_feeling = label
        return self.add(Thought(now, f"I feel {label}.", "felt", (), frozenset(), 0.3, False))

    def recent(self, now: float, audience: frozenset, within: float | None = None, limit: int = SHOWN) -> list[Thought]:
        within = self.keep_s if within is None else within
        out = [t for t in self.thoughts if now - t.at <= within and visible(t, audience)]
        return out[-limit:]

    def best_of_day(self) -> list[Thought]:
        picked = sorted(self.day, key=lambda t: -t.weight)[:DIARY_PICKS]
        self.day = []
        return sorted(picked, key=lambda t: t.at)

    def forget(self, person_id: str) -> None:
        self.thoughts = deque(t for t in self.thoughts if person_id not in t.about and person_id not in t.audience)
        self.day = [t for t in self.day if person_id not in t.about and person_id not in t.audience]
