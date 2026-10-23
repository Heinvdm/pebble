import math

LONGEST_S = 12 * 3600.0
GONE_S = 3 * 3600.0
STRANGERS_TO_OFFER = 3
OFFER_AFTER_S = 20.0
OFFER_GAP_S = 2 * 3600.0


class Visitors:
    def __init__(self, data: dict | None = None):
        data = dict(data or {})
        self.on = bool(data.get("on"))
        self.since = data.get("since")
        self.by = data.get("by")
        self.strangers_since: float | None = None
        self.strangers_last = -math.inf
        self.offered_at = -math.inf

    def start(self, at: float, by: str | None) -> bool:
        if self.on:
            return False
        self.on, self.since, self.by = True, at, by
        self.strangers_last = at
        return True

    def stop(self) -> bool:
        if not self.on:
            return False
        self.on, self.since, self.by = False, None, None
        return True

    def learning(self) -> bool:
        return not self.on

    def saw(self, unknown: int, at: float) -> bool:
        if unknown >= 1:
            self.strangers_last = at
        if unknown >= STRANGERS_TO_OFFER:
            if self.strangers_since is None:
                self.strangers_since = at
        else:
            self.strangers_since = None
        if self.on or self.strangers_since is None:
            return False
        return at - self.strangers_since >= OFFER_AFTER_S and at - self.offered_at >= OFFER_GAP_S

    def offered(self, at: float) -> None:
        self.offered_at = at

    def stale(self, at: float) -> str:
        if not self.on or self.since is None:
            return ""
        if at - float(self.since) >= LONGEST_S:
            return "twelve hours have gone by"
        if at - max(self.strangers_last, float(self.since)) >= GONE_S:
            return "I haven't seen anyone I don't know for three hours"
        return ""

    def to_dict(self) -> dict:
        return {"on": self.on, "since": self.since, "by": self.by}
