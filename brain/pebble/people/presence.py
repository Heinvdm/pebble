import math

PRESENT_S = 120.0
REQUEST_S = 90.0
FAMILY_WORD_S = 300.0
TOUCH_HOLD_S = 15.0


class Presence:
    def __init__(self):
        self._seen: dict[str, float] = {}
        self._heard: dict[str, float] = {}
        self._family: dict[str, float] = {}
        self._touched: dict[str, float] = {}

    def saw(self, person_id: str, at: float) -> None:
        self._seen[person_id] = max(at, self._seen.get(person_id, -math.inf))

    def heard(self, person_id: str, at: float) -> None:
        self._heard[person_id] = max(at, self._heard.get(person_id, -math.inf))

    def touched(self, person_id: str, at: float) -> None:
        self._touched[person_id] = max(at, self._touched.get(person_id, -math.inf))

    def said_family_word(self, person_id: str, at: float) -> None:
        self._family[person_id] = at

    def left(self, person_id: str) -> None:
        for table in (self._seen, self._heard, self._touched):
            table.pop(person_id, None)

    def forget(self, person_id: str) -> None:
        self.left(person_id)
        self._family.pop(person_id, None)

    def last_seen(self, person_id: str) -> float:
        return self._seen.get(person_id, -math.inf)

    def last_heard(self, person_id: str) -> float:
        return self._heard.get(person_id, -math.inf)

    def last_present(self, person_id: str) -> float:
        return max(self.last_seen(person_id), self.last_heard(person_id), self._touched.get(person_id, -math.inf))

    def seen(self, person_id: str, now: float, within: float = REQUEST_S) -> bool:
        return now - self.last_seen(person_id) <= within

    def heard_lately(self, person_id: str, now: float, within: float = REQUEST_S) -> bool:
        return now - self.last_heard(person_id) <= within

    def seen_and_heard(self, person_id: str, now: float, within: float = REQUEST_S) -> bool:
        return self.seen(person_id, now, within) and self.heard_lately(person_id, now, within)

    def family_word(self, person_id: str, now: float, within: float = FAMILY_WORD_S) -> bool:
        return now - self._family.get(person_id, -math.inf) <= within

    def in_hands(self, person_id: str, now: float, within: float = TOUCH_HOLD_S) -> bool:
        return now - self._touched.get(person_id, -math.inf) <= within

    def here(self, now: float, within: float = PRESENT_S) -> list[str]:
        ids = set(self._seen) | set(self._heard) | set(self._touched)
        return sorted(pid for pid in ids if now - self.last_present(pid) <= within)

    def alone_with(self, person_id: str, now: float) -> bool:
        return self.here(now) == [person_id]

    def sole(self, now: float) -> str | None:
        here = self.here(now)
        return here[0] if len(here) == 1 else None
