from collections import deque

WINDOW_S = 3 * 3600.0
KEEP = 32


class RecentActions:
    def __init__(self, window_s: float = WINDOW_S, keep: int = KEEP):
        self.window_s = window_s
        self._done: deque[tuple[str, float]] = deque(maxlen=keep)

    def did(self, key: str, now: float) -> None:
        self._done.append((key, now))

    def last(self, key: str) -> float | None:
        for done, at in reversed(self._done):
            if done == key:
                return at
        return None

    def freshness(self, key: str, now: float) -> float:
        at = self.last(key)
        if at is None:
            return 1.0
        return max(0.0, min(1.0, (now - at) / self.window_s))

    def bonuses(self, keys, now: float, novelty: float) -> dict[str, float]:
        return {key: round(novelty * self.freshness(key, now), 4) for key in keys}

    def recent(self) -> list[str]:
        return [key for key, _ in self._done]
