from datetime import datetime, timedelta

STEP_S = 10.0
KEEP_HOURS = 7 * 24
LOUD_OVER_DB = 15.0
NIGHT = (22, 7)
TOLD = "My microphone isn't calibrated, so these are rough levels, not evidence for a noise complaint, and I never keep any sound."


class NoiseDiary:
    def __init__(self, house, hours: list):
        self.house = house
        self.hours = hours
        self.next_at = 0.0

    def tick(self, now: float, mono: float) -> None:
        if mono < self.next_at:
            return
        self.next_at = mono + STEP_S
        meter = getattr(self.house.hearing, "meter", None)
        if meter is None:
            return
        levels = meter.snapshot()
        last = levels[-1][0] if levels else None
        recent = [level for at, level, own in levels if last is not None and last - at <= STEP_S and not own]
        if len(recent) < 3:
            return
        floor = meter.floor(levels)
        peak = max(recent) - floor
        key = self.house.clock.local(now).strftime("%Y-%m-%dT%H")
        bucket = self.hours[-1] if self.hours and self.hours[-1].get("h") == key else None
        if bucket is None:
            bucket = {"h": key, "peak": 0.0, "loud": 0, "floor": round(floor, 1)}
            self.hours.append(bucket)
            del self.hours[:-KEEP_HOURS]
        rounded = round(max(float(bucket["peak"]), peak), 1)
        changed = rounded != bucket["peak"]
        bucket["peak"] = rounded
        if peak >= LOUD_OVER_DB:
            bucket["loud"] = int(bucket["loud"]) + 1
            changed = True
        if changed:
            self.house.book.touch()

    def _span(self, start: datetime, end: datetime) -> list[dict]:
        keys = set()
        hour = start.replace(minute=0, second=0, microsecond=0)
        while hour < end:
            keys.add(hour.strftime("%Y-%m-%dT%H"))
            hour += timedelta(hours=1)
        return [b for b in self.hours if b.get("h") in keys]

    def answer(self, text: str, now: float) -> str:
        local = self.house.clock.local(now)
        if "night" in text:
            midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
            start = midnight - timedelta(hours=24 - NIGHT[0])
            end = local if local.hour < NIGHT[1] else midnight + timedelta(hours=NIGHT[1])
            span = "last night"
        else:
            start = local.replace(hour=0, minute=0, second=0, microsecond=0)
            end = local
            span = "today"
        buckets = self._span(start, end)
        if not buckets:
            return f"I wasn't listening {span}, so I can't say."
        loudest = max(buckets, key=lambda b: float(b["peak"]))
        minutes = sum(int(b["loud"]) for b in buckets) * STEP_S / 60.0
        if float(loudest["peak"]) < LOUD_OVER_DB:
            return f"It was quiet {span}, as far as I could hear. {TOLD}"
        hour = int(loudest["h"][-2:])
        clock = f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'}"
        return f"{span[:1].upper()}{span[1:]}, the loudest hour began at {clock}, about {round(float(loudest['peak']))} decibels above the usual quiet, and it was loud for about {max(1, round(minutes))} minutes in all. {TOLD}"
