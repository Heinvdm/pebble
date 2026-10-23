import calendar
import re
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable

from ..understand.request import DAYS, PARTS, When, clock

DEFAULT_PARTS = {"morning": "08:00", "midday": "12:00", "afternoon": "15:00", "evening": "18:00", "night": "19:30", "tonight": "19:30", "before_bed": "21:00"}
PART_WORDS = {"morning": "morning", "midday": "midday", "noon": "midday", "lunchtime": "midday", "afternoon": "afternoon", "evening": "evening", "night": "night", "tonight": "tonight", "bedtime": "before_bed", "before bed": "before_bed"}
DAY_TIME = "morning"
AHEAD_S = 30 * 86400.0
SCAN_DAYS = 400
GAP_MINUTES = 240
WINDOW_S = 86400.0
TONIGHT_SOON_S = 1800.0
LATE_TONIGHT = time(23, 30)
CLOCK_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")
BARE_HOUR = re.compile(r"\b(?:at|by|around|about|from|till|until)\s+(\d{1,2}|" + "|".join(CLOCK_WORDS) + r")(?:\s*o'?clock)?\b(?!\s*(?::|am|pm|a\.m|p\.m|in the|at night|tonight|this (?:morning|afternoon|evening)|tomorrow (?:morning|night)))")
HALF_WORDS = re.compile(r"\b(am|pm|a\.m|p\.m|morning|afternoon|evening|night|tonight|noon|midday|midnight|\d{1,2}:\d{2})\b")
PART_SETTING = re.compile(r"^(?:for me,? |in this house,? |for everyone,? )?(morning|midday|noon|lunchtime|afternoon|evening|night|tonight|bedtime|before bed)(?: time)? (?:means|is) (?:about |around )?([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?|" + "|".join(CLOCK_WORDS) + r")(?: o'?clock)?(?: (?:at night|in the morning|in the evening|in the afternoon))?( for me| for everyone| in this house)?[.!]?$")
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def hm(text: str) -> time:
    hours, minutes = (int(part) for part in text.split(":", 1))
    return time(hours % 24, minutes % 60)


def wall_key(wall: datetime) -> str:
    return wall.replace(tzinfo=None, fold=0).isoformat(timespec="minutes")


def _naive(local: Callable[[float], datetime], ts: float) -> datetime:
    return local(ts).replace(tzinfo=None, fold=0)


def _exact(wall: datetime, local: Callable[[float], datetime]) -> list[float]:
    guess = wall.replace(tzinfo=timezone.utc).timestamp()
    offsets = set()
    for probe in (guess - 86400.0, guess, guess + 86400.0):
        offset = local(probe).utcoffset()
        if offset is not None:
            offsets.add(offset.total_seconds())
    found = []
    for offset in sorted(offsets):
        ts = guess - offset
        if _naive(local, ts) == wall.replace(fold=0):
            found.append(ts)
    return sorted(set(found))


def instant(wall: datetime, local: Callable[[float], datetime]) -> float:
    wall = wall.replace(tzinfo=None, fold=0)
    found = _exact(wall, local)
    if found:
        return found[0]
    for minutes in range(1, GAP_MINUTES + 1):
        later = _exact(wall + timedelta(minutes=minutes), local)
        if later:
            return later[0]
    return wall.replace(tzinfo=timezone.utc).timestamp()


def part_time(part: str, parts: dict) -> str:
    return parts.get(part) or DEFAULT_PARTS.get(part, DEFAULT_PARTS[DAY_TIME])


def time_of(when: When, parts: dict) -> str:
    if when.at:
        return when.at
    if when.part:
        return part_time(when.part, parts)
    return ""


def hour_of(when: When, parts: dict) -> str:
    found = time_of(when, parts)
    if found or when.every_s:
        return found
    return part_time(DAY_TIME, parts) if (when.date or when.days or when.month_day) else ""


def last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _month_day(day: date, wanted: int) -> bool:
    end = last_day(day.year, day.month)
    if wanted < 0:
        return day.day == end
    return day.day == min(wanted, end)


def _week(day: date) -> int:
    return (day.toordinal() - 1) // 7


def day_matches(when: When, day: date, anchor: date | None) -> bool:
    if when.date and day.isoformat() != when.date:
        return False
    if when.days and DAYS[day.weekday()] not in when.days:
        return False
    if when.month_day and not _month_day(day, when.month_day):
        return False
    if when.every_weeks and anchor is not None and (_week(day) - _week(anchor)) % when.every_weeks:
        return False
    return True


def repeats(when: When) -> bool:
    return when.repeats


def one_shot_in(when: When) -> bool:
    return bool(when.in_s) and not (when.at or when.part or when.date or when.repeats)


def _ends(when: When, made: float, local: Callable[[float], datetime]) -> float | None:
    if when.until_date:
        return instant(datetime.combine(date.fromisoformat(when.until_date) + timedelta(days=1), time(0)), local)
    return None


def _end_wall(day: date, start: time, end: time | None) -> datetime:
    if end is None:
        return datetime.combine(day, start) + timedelta(seconds=WINDOW_S - 1)
    return datetime.combine(day + timedelta(days=1 if end <= start else 0), end)


def _every(when: When, after: float, made: float, anchor_ts: float, local: Callable[[float], datetime], parts: dict, last_key: str, anchor: date | None = None) -> tuple[float, str] | None:
    step = when.every_s
    stop = _ends(when, made, local)
    begin = when.from_ or (part_time(when.part, parts) if when.part else "")
    end = hm(when.to) if when.to else None
    if not begin:
        anchor = _naive(local, anchor_ts)
        last = instant(_end_wall(anchor.date(), anchor.time(), end), local) if end is not None or not (when.days or when.until_date or when.times) else None
        ts = anchor_ts
        while ts <= after + 2 * AHEAD_S:
            if (last is not None and ts > last + 1.0) or (stop is not None and ts > stop):
                return None
            wall = _naive(local, ts)
            key = wall_key(wall)
            if ts > after and key != last_key and (not when.days or DAYS[wall.weekday()] in when.days):
                return ts, key
            ts += step
        return None
    start = hm(begin)
    first = _naive(local, after).date()
    for offset in range(-1, SCAN_DAYS):
        day = first + timedelta(days=offset)
        if when.days and DAYS[day.weekday()] not in when.days:
            continue
        if anchor is not None and not (when.days or when.until_date or when.times) and day != anchor:
            if day > anchor:
                return None
            continue
        wall = datetime.combine(day, start)
        limit = _end_wall(day, start, end)
        while wall <= limit:
            ts = instant(wall, local)
            if stop is not None and ts > stop:
                return None
            key = wall_key(wall)
            if ts > after and key != last_key:
                return ts, key
            wall += timedelta(seconds=step)
    return None


def next_time(when: When, after: float, made: float, local: Callable[[float], datetime], parts: dict, anchor: date | None = None, anchor_ts: float | None = None, last_key: str = "") -> tuple[float, str] | None:
    if when.every_s:
        return _every(when, after, made, anchor_ts if anchor_ts is not None else made + when.every_s, local, parts, last_key, anchor)
    if one_shot_in(when):
        due = made + when.in_s
        if due <= after:
            return None
        return due, f"in:{round(made)}"
    hour = hour_of(when, parts)
    if not hour:
        return None
    at = hm(hour)
    stop = _ends(when, made, local)
    start = _naive(local, max(after, made + when.in_s) if when.in_s else after)
    if when.part == "tonight" and not (when.at or when.date or when.repeats or last_key):
        tonight = datetime.combine(_naive(local, made).date(), at)
        if _naive(local, made) >= tonight and _naive(local, made).time() < LATE_TONIGHT:
            soon = made + TONIGHT_SOON_S
            return (soon, wall_key(_naive(local, soon))) if soon > after else None
    for offset in range(0, SCAN_DAYS):
        day = start.date() + timedelta(days=offset)
        if not day_matches(when, day, anchor):
            continue
        wall = datetime.combine(day, at)
        ts = instant(wall, local)
        if stop is not None and ts > stop:
            return None
        if ts <= after:
            continue
        key = wall_key(wall)
        if key == last_key:
            continue
        return ts, key
    return None


def first_anchor(when: When, made: float, local: Callable[[float], datetime], parts: dict) -> date | None:
    if not when.every_weeks:
        return None
    found = next_time(When(at=when.at, part=when.part, days=when.days, month_day=when.month_day), made, made, local, parts)
    return _naive(local, found[0]).date() if found else None


def nearest_hour(at: str, now: datetime) -> str:
    moment = hm(at)
    hour = moment.hour % 12
    best = None
    for choice in (hour, hour + 12):
        wall = datetime.combine(now.date(), time(choice, moment.minute))
        if wall <= now:
            wall += timedelta(days=1)
        if best is None or wall < best:
            best = wall
    return f"{best.hour:02d}:{best.minute:02d}"


def bare_clock(words: str) -> bool:
    text = " ".join((words or "").lower().split())
    return bool(BARE_HOUR.search(text)) and not HALF_WORDS.search(text)


def settle_clock(when: When, words: str, now: datetime) -> When:
    if not when.at or when.date or when.repeats or not bare_clock(words):
        return when
    return replace(when, at=nearest_hour(when.at, now))


def part_setting(text: str) -> tuple[str, str, bool] | None:
    plain = " ".join((text or "").lower().replace(",", " ").split()).strip(" .!")
    plain = re.sub(r"^(?:pebble )", "", plain)
    found = PART_SETTING.match(plain)
    if found is None:
        return None
    part = PART_WORDS.get(found.group(1))
    raw = found.group(2).strip()
    if raw in CLOCK_WORDS:
        raw = str(CLOCK_WORDS.index(raw) + 1)
    try:
        at = clock(raw)
    except ValueError:
        return None
    hour = int(at[:2])
    if "am" not in raw and "pm" not in raw and hour < 12 and part in ("evening", "night", "tonight", "before_bed", "afternoon") and hour != 0:
        at = f"{hour + 12:02d}{at[2:]}"
    everyone = (found.group(3) or "").strip() in ("for everyone", "in this house") or plain.startswith(("in this house", "for everyone"))
    return part, at, everyone


def known_part(word: str) -> bool:
    return word in PARTS


SPOKEN = re.compile(r"^(?:at |by |around |about )?(?:(?P<frac>half past|quarter past|quarter to) )?(?P<hour>\d{1,2}|" + "|".join(CLOCK_WORDS) + r"|noon|midday|midnight)(?::(?P<minute>\d{2})| (?P<thirty>thirty|fifteen|forty five|forty-five))?(?: ?o'?clock)?(?: ?(?P<half>am|pm|a\.m\.?|p\.m\.?|in the morning|in the afternoon|in the evening|at night|tonight|this evening|this morning))?$")


def spoken_clock(text: str, old: str = "") -> str:
    found = SPOKEN.match(" ".join((text or "").lower().split()).strip(" .!?,"))
    if found is None:
        return ""
    raw = found.group("hour")
    if raw in ("noon", "midday"):
        return "12:00"
    if raw == "midnight":
        return "00:00"
    hour = CLOCK_WORDS.index(raw) + 1 if raw in CLOCK_WORDS else int(raw)
    if hour > 23:
        return ""
    minute = int(found.group("minute") or 0)
    minute = {"thirty": 30, "fifteen": 15, "forty five": 45, "forty-five": 45}.get(found.group("thirty") or "", minute)
    frac = found.group("frac") or ""
    if frac == "half past":
        minute = 30
    elif frac == "quarter past":
        minute = 15
    elif frac == "quarter to":
        hour, minute = (hour - 1) % 24, 45
    half = (found.group("half") or "").replace(".", "")
    if hour <= 12:
        if half in ("pm", "in the afternoon", "in the evening", "at night", "tonight", "this evening") and hour < 12:
            hour += 12
        elif half in ("am", "in the morning", "this morning") and hour == 12:
            hour = 0
        elif not half and old:
            if hm(old).hour >= 12 and hour < 12:
                hour += 12
    return f"{hour:02d}:{minute:02d}"
