import calendar as stdcal
from dataclasses import dataclass
from datetime import date, timedelta

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
YEARLY_KINDS = frozenset({"birthday", "anniversary"})
PERSONAL_KINDS = ("birthday", "anniversary", "event")
PERSONAL_CAP = 200
NZ_RULES = "nz"
NZ_REGION = "NZ"
HOLIDAYS_ACT = "Holidays Act 2003"
EASTER_SOURCE = "Easter by the Western church rule"
MATARIKI_SOURCE = "Te Kāhui o Matariki Public Holiday Act 2022, Schedule 1"
MATARIKI = {
    2022: (6, 24), 2023: (7, 14), 2024: (6, 28), 2025: (6, 20), 2026: (7, 10), 2027: (6, 25), 2028: (7, 14), 2029: (7, 6),
    2030: (6, 21), 2031: (7, 11), 2032: (7, 2), 2033: (6, 24), 2034: (7, 7), 2035: (6, 29), 2036: (7, 18), 2037: (7, 10),
    2038: (6, 25), 2039: (7, 15), 2040: (7, 6), 2041: (7, 19), 2042: (7, 11), 2043: (7, 3), 2044: (6, 24), 2045: (7, 7),
    2046: (6, 29), 2047: (7, 19), 2048: (7, 3), 2049: (6, 25), 2050: (7, 15), 2051: (6, 30), 2052: (6, 21),
}
NZ_DAYS = {
    "new-year": ("New Year's Day", "party", 0.5, f"{HOLIDAYS_ACT}, s 44(1)(c)"),
    "day-after-new-year": ("Day after New Year's Day", "calm", 0.2, f"{HOLIDAYS_ACT}, s 44(1)(d)"),
    "waitangi": ("Waitangi Day", "calm", 0.3, f"{HOLIDAYS_ACT}, s 44(1)(e)"),
    "good-friday": ("Good Friday", "quiet", 0.1, f"{HOLIDAYS_ACT}, s 44(1)(f); {EASTER_SOURCE}"),
    "easter-monday": ("Easter Monday", "calm", 0.3, f"{HOLIDAYS_ACT}, s 44(1)(g); {EASTER_SOURCE}"),
    "anzac": ("Anzac Day", "quiet", 0.0, f"{HOLIDAYS_ACT}, s 44(1)(h)"),
    "queens-birthday": ("Queen's Birthday", "calm", 0.2, f"{HOLIDAYS_ACT}, s 44(1)(i), the first Monday in June"),
    "kings-birthday": ("King's Birthday", "calm", 0.2, f"{HOLIDAYS_ACT}, s 44(1)(i), the first Monday in June"),
    "matariki": ("Matariki", "calm", 0.6, MATARIKI_SOURCE),
    "labour-day": ("Labour Day", "calm", 0.2, f"{HOLIDAYS_ACT}, s 44(1)(j), the fourth Monday in October"),
    "christmas": ("Christmas Day", "party", 0.7, f"{HOLIDAYS_ACT}, s 44(1)(a)"),
    "boxing-day": ("Boxing Day", "calm", 0.3, f"{HOLIDAYS_ACT}, s 44(1)(b)"),
}
SUMMER_DAYS = frozenset({"new-year", "day-after-new-year", "christmas", "boxing-day"})
MONDAY_DAYS = frozenset({"waitangi", "anzac"})
MONDAY_FROM = 2014
KINGS_BIRTHDAY_FROM = 2023


class BadDate(ValueError):
    pass


@dataclass(frozen=True)
class Occasion:
    id: str
    title: str
    kind: str
    day: date
    mood: str
    enthusiasm: float
    why: str = ""


def nth_weekday(year: int, month: int, weekday: str, nth: int) -> date | None:
    target = WEEKDAYS.index(weekday)
    days = [d for d in range(1, stdcal.monthrange(year, month)[1] + 1) if date(year, month, d).weekday() == target]
    try:
        return date(year, month, days[nth - 1 if nth > 0 else nth])
    except IndexError:
        return None


def easter(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    n = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * n) // 451
    month, day = divmod(h + n - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nz_entry(key: str, day: date) -> dict:
    title, mood, enthusiasm, source = NZ_DAYS[key]
    return {
        "id": f"nz-{key}-{day.year}",
        "title": title,
        "kind": "holiday",
        "region": NZ_REGION,
        "date": day.isoformat(),
        "mood": mood,
        "enthusiasm": enthusiasm,
        "source": source,
    }


def _moved_to(key: str, day: date) -> date | None:
    if day.weekday() < 5:
        return None
    if key in SUMMER_DAYS:
        return day + timedelta(days=2)
    if key in MONDAY_DAYS and day.year >= MONDAY_FROM:
        return day + timedelta(days=7 - day.weekday())
    return None


def _nz_observed(key: str, day: date, moved: date) -> dict:
    title, mood, enthusiasm, _ = NZ_DAYS[key]
    entry = _nz_entry(key, moved)
    weekday, new_weekday = WEEKDAYS[day.weekday()].title(), WEEKDAYS[moved.weekday()].title()
    entry.update(
        id=f"nz-{key}-observed-{day.year}",
        title=f"{title} (observed)",
        mood="quiet" if mood == "quiet" else "calm",
        enthusiasm=min(enthusiasm, 0.2),
        source=f"{HOLIDAYS_ACT}, s {'45A' if key in MONDAY_DAYS else '45'}",
        why=f"{title} falls on a {weekday}, so the day off moves to {new_weekday} for people who don't usually work on {weekday}s",
    )
    return entry


def nz_holidays(year: int) -> list[dict]:
    sunday = easter(year)
    days = [
        ("new-year", date(year, 1, 1)),
        ("day-after-new-year", date(year, 1, 2)),
        ("waitangi", date(year, 2, 6)),
        ("good-friday", sunday - timedelta(days=2)),
        ("easter-monday", sunday + timedelta(days=1)),
        ("anzac", date(year, 4, 25)),
        ("kings-birthday" if year >= KINGS_BIRTHDAY_FROM else "queens-birthday", nth_weekday(year, 6, "monday", 1)),
        ("labour-day", nth_weekday(year, 10, "monday", 4)),
        ("christmas", date(year, 12, 25)),
        ("boxing-day", date(year, 12, 26)),
    ]
    if year in MATARIKI:
        days.append(("matariki", date(year, *MATARIKI[year])))
    found = []
    for key, day in days:
        found.append(_nz_entry(key, day))
        moved = _moved_to(key, day)
        if moved is not None:
            found.append(_nz_observed(key, day, moved))
    return sorted(found, key=lambda entry: (entry["date"], entry["title"]))


def _yearly(year: int, month: int, day: int) -> date | None:
    if month == 2 and day == 29 and not stdcal.isleap(year):
        return date(year, 2, 28)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def date_in_year(entry: dict, year: int) -> date | None:
    try:
        if "date" in entry:
            fixed = date.fromisoformat(entry["date"])
            if entry.get("kind") in YEARLY_KINDS:
                return _yearly(year, fixed.month, fixed.day)
            return fixed if fixed.year == year else None
        if "weekday" in entry:
            return nth_weekday(year, int(entry["month"]), entry["weekday"], int(entry.get("nth", 1)))
        if entry.get("year") and entry.get("kind") not in YEARLY_KINDS:
            return date(int(entry["year"]), int(entry["month"]), int(entry["day"])) if int(entry["year"]) == year else None
        return _yearly(year, int(entry["month"]), int(entry["day"]))
    except (KeyError, ValueError, TypeError):
        return None


def occurs(entry: dict, day: date) -> bool:
    return date_in_year(entry, day.year) == day


def _occasion(entry: dict, day: date) -> Occasion:
    return Occasion(
        id=str(entry.get("id", entry.get("title", "?"))),
        title=str(entry.get("title", "?")),
        kind=str(entry.get("kind", "event")),
        day=day,
        mood=str(entry.get("mood", "calm")),
        enthusiasm=float(entry.get("enthusiasm", 0.5)),
        why=str(entry.get("why", "")),
    )


def _same(title: str) -> str:
    return " ".join(str(title).casefold().split())


class Calendar:
    def __init__(self, data: dict, birthday: date | None = None, name: str = "Pebble"):
        self.robot_days = list(data.get("robot_days") or [])
        self.holidays = list(data.get("holidays") or [])
        self.personal = list(data.get("personal") or [])
        self.holidays_note = data.get("holidays_note", "")
        self.holiday_rules = data.get("holiday_rules")
        self.birthday = birthday
        self.name = name
        self._computed = {}

    def rules(self) -> str | None:
        if self.holiday_rules:
            return self.holiday_rules
        return NZ_RULES if any(entry.get("region") == NZ_REGION for entry in self.holidays) else None

    def computed(self, year: int) -> dict[date, list[dict]]:
        found = self._computed.get(year)
        if found is None:
            found = {}
            if self.rules() == NZ_RULES:
                for entry in nz_holidays(year):
                    found.setdefault(date.fromisoformat(entry["date"]), []).append(entry)
            self._computed[year] = found
        return found

    def entries(self) -> list[dict]:
        found = self.robot_days + self.holidays + self.personal
        if self.birthday is not None:
            found.append({
                "id": "own-birthday",
                "title": f"{self.name}'s birthday",
                "kind": "milestone",
                "month": self.birthday.month,
                "day": self.birthday.day,
                "mood": "party",
                "enthusiasm": 1.0,
                "why": f"first booted on {self.birthday.isoformat()}",
                "from_year": self.birthday.year + 1,
            })
        return found

    def on(self, day: date) -> list[Occasion]:
        result = []
        for entry in self.entries():
            if entry.get("from_year") and day.year < entry["from_year"]:
                continue
            if occurs(entry, day):
                result.append(_occasion(entry, day))
        seen = {_same(occasion.title) for occasion in result}
        for entry in self.computed(day.year).get(day, ()):
            title = _same(entry["title"])
            if title not in seen:
                seen.add(title)
                result.append(_occasion(entry, day))
        return sorted(result, key=lambda o: (-o.enthusiasm, o.title))

    def upcoming(self, today: date, within_days: int = 14) -> list[tuple[Occasion, int]]:
        found = []
        for offset in range(1, within_days + 1):
            day = today + timedelta(days=offset)
            found.extend((occasion, offset) for occasion in self.on(day))
        return found

    def add_personal(self, title: str, month: int, day: int, kind: str, at: str, year: int | None = None, person: str | None = None) -> dict:
        if kind not in PERSONAL_KINDS:
            raise BadDate(f"kind must be one of {', '.join(PERSONAL_KINDS)}")
        check_year = year or 2024
        try:
            date(check_year, month, day)
        except ValueError as error:
            raise BadDate(f"{month}/{day} is not a real date") from error
        if len(self.personal) >= PERSONAL_CAP:
            raise BadDate("the calendar is full")
        entry = {
            "id": f"personal-{len(self.personal) + 1}-{month:02d}{day:02d}",
            "title": title.strip()[:60],
            "kind": kind,
            "month": month,
            "day": day,
            "mood": "party" if kind in ("birthday", "anniversary") else "calm",
            "enthusiasm": 0.8 if kind == "birthday" else 0.5,
            "added_at": at,
        }
        if year:
            entry["year"] = year
        if person:
            entry["person"] = person.strip()[:40]
        self.personal.append(entry)
        return entry

    def to_dict(self) -> dict:
        data = {
            "format": 1,
            "robot_days": self.robot_days,
            "holidays": self.holidays,
            "holidays_note": self.holidays_note,
            "personal": self.personal,
        }
        if self.holiday_rules:
            data["holiday_rules"] = self.holiday_rules
        return data
