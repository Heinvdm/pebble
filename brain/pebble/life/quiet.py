from dataclasses import dataclass
from datetime import datetime, time, timedelta


def _parse(text: str, fallback: time) -> time:
    try:
        hours, minutes = (int(part) for part in str(text).split(":", 1))
        return time(hours % 24, minutes % 60)
    except (ValueError, TypeError):
        return fallback


@dataclass(frozen=True)
class QuietHours:
    start: time = time(22, 0)
    end: time = time(7, 0)

    @classmethod
    def from_preferences(cls, preferences: dict) -> "QuietHours":
        raw = preferences.get("quiet_hours") or {}
        return cls(_parse(raw.get("start", "22:00"), time(22, 0)), _parse(raw.get("end", "07:00"), time(7, 0)))

    def contains(self, moment: datetime) -> bool:
        now = moment.time()
        if self.start == self.end:
            return False
        if self.start < self.end:
            return self.start <= now < self.end
        return now >= self.start or now < self.end

    def night_key(self, moment: datetime) -> str:
        day = moment.date()
        if self.start > self.end and moment.time() < self.end:
            day -= timedelta(days=1)
        return day.isoformat()
