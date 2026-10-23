class InitiativeGate:
    def __init__(self, min_interval_s: float = 600.0, last_at: float | None = None):
        self.min_interval_s = min_interval_s
        self.last_at = last_at

    def allowed(self, now: float, quiet: bool) -> bool:
        if quiet:
            return False
        return self.last_at is None or now - self.last_at >= self.min_interval_s

    def used(self, now: float) -> None:
        self.last_at = now
