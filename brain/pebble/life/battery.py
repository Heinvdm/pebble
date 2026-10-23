from dataclasses import dataclass

SEEK_PCT = 15.0
SHUTDOWN_PCT = 5.0
RECOVER_PCT = 20.0


@dataclass(frozen=True)
class BatteryVerdict:
    low: bool
    critical: bool
    newly_low: bool


class LowBatteryRoutine:
    def __init__(self, seek_pct: float = SEEK_PCT, shutdown_pct: float = SHUTDOWN_PCT, recover_pct: float = RECOVER_PCT):
        self.seek_pct = seek_pct
        self.shutdown_pct = shutdown_pct
        self.recover_pct = recover_pct
        self.low = False

    def assess(self, percent: float | None, charging: bool | None, pack_low: bool) -> BatteryVerdict:
        draining = charging is not True
        phone_low = percent is not None and percent <= self.seek_pct and draining
        critical = percent is not None and percent <= self.shutdown_pct and draining
        was_low = self.low
        if self.low:
            recovered = not pack_low and (percent is None or percent >= self.recover_pct or charging is True)
            if recovered:
                self.low = False
        elif phone_low or pack_low:
            self.low = True
        return BatteryVerdict(self.low, critical, self.low and not was_low)
