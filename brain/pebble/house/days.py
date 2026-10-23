from datetime import date, datetime, timedelta, timezone

from ..things.facts import spoken_fact
from .almanac import clock_changes, moon, sun_times, twilight

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
OFFER_HOURS = (9, 20)
OFFER_DAYS = 7
HOLIDAY_AHEAD_DAYS = 5
CURTAINS_BEFORE_S = 15 * 60.0
CURTAINS_WINDOW_S = 30 * 60.0
EVENING = (18, 21)
CLOCKS_AHEAD_S = 12 * 3600.0
FACT_ASK_GAP_S = 30 * 86400.0
COLD_C = 16.0
SETTLE_S = 60.0
EECA = " EECA, the government's energy agency, says closing curtains before dark keeps the warmth in."
NO_PLACE = "I don't know where home is yet, so I can't work that out. My owner can set our town in my settings."


def spoken_time(moment: datetime) -> str:
    hour = moment.hour % 12 or 12
    tail = "am" if moment.hour < 12 else "pm"
    return f"{hour}:{moment.minute:02d}{tail}" if moment.minute else f"{hour}{tail}"


def spoken_day(day: date, today: date) -> str:
    if day == today:
        return "today"
    if day == today + timedelta(days=1):
        return "tomorrow"
    name = WEEKDAYS[day.weekday()].title()
    if 0 < (day - today).days < 7:
        return f"this {name}"
    return f"{name} {day.day} {day.strftime('%B')}"


class Days:
    def __init__(self, house):
        self.house = house
        self.next_at = house.clock.monotonic() + SETTLE_S
        self.changes_day: date | None = None
        self.changes: list = []

    @property
    def clock(self):
        return self.house.clock

    @property
    def asked(self) -> dict:
        return self.house.book["asked"]

    def place(self) -> tuple[float, float] | None:
        found = self.house.book["place"]
        if not isinstance(found, dict):
            return None
        try:
            return float(found["lat"]), float(found["lon"])
        except (KeyError, TypeError, ValueError):
            return None

    def _local(self, moment: datetime | None) -> datetime | None:
        return None if moment is None else self.clock.local(moment.timestamp())

    def sun(self, day: date) -> tuple[datetime | None, datetime | None] | None:
        place = self.place()
        if place is None:
            return None
        rise, fall = sun_times(day, place[0], place[1], timezone.utc)
        return self._local(rise), self._local(fall)

    def dusk(self, day: date) -> datetime | None:
        place = self.place()
        if place is None:
            return None
        return self._local(twilight(day, place[0], place[1], timezone.utc)[1])

    def _day_of(self, when: str, today: date) -> date:
        if when == "tomorrow":
            return today + timedelta(days=1)
        if when in WEEKDAYS:
            ahead = (WEEKDAYS.index(when) - today.weekday()) % 7
            return today + timedelta(days=ahead)
        return today

    def holidays_on(self, day: date) -> list:
        return [o for o in self.house.p.books.calendar.on(day) if o.kind == "holiday"]

    def next_holiday(self, today: date, title: str = "") -> tuple[object, date] | None:
        wanted = title.replace("kings", "king's").replace("new years", "new year's").lower()
        for offset in range(0, 400):
            day = today + timedelta(days=offset)
            for occasion in self.holidays_on(day):
                name = occasion.title.lower()
                if "(observed)" in name:
                    continue
                if not wanted or wanted in name or name.startswith(wanted):
                    return occasion, day
        return None

    def answer(self, ask, now: float) -> str:
        today = self.clock.local(now).date()
        topic = ask.topic
        if topic in ("sunset", "sunrise"):
            day = self._day_of(ask.when, today)
            times = self.sun(day)
            if times is None:
                return NO_PLACE
            rise, fall = times
            if "dark" in ask.text:
                dusk = self.dusk(day)
                if dusk is None:
                    return "The sun doesn't set here at this time of year."
                return f"It gets dark at about {spoken_time(dusk)} {spoken_day(day, today)}. Sunset is at {spoken_time(fall)}." if fall else f"It gets dark at about {spoken_time(dusk)}."
            moment = rise if topic == "sunrise" else fall
            if moment is None:
                return "The sun doesn't rise or set here at this time of year."
            if "how long" in ask.text:
                left = moment.timestamp() - now
                if left <= 0:
                    return f"The sun has already set today. It set at {spoken_time(moment)}."
                hours, minutes = int(left // 3600), int(left % 3600 // 60)
                span = (f"{hours} hour{'s' if hours != 1 else ''} and " if hours else "") + f"{minutes} minute{'s' if minutes != 1 else ''}"
                return f"About {span}. Sunset is at {spoken_time(moment)}."
            word = "Sunrise" if topic == "sunrise" else "Sunset"
            return f"{word} is at {spoken_time(moment)} {spoken_day(day, today)}."
        if topic == "holiday":
            day = self._day_of(ask.when, today)
            found = self.holidays_on(day)
            when = spoken_day(day, today)
            if not found:
                return f"No, {when} isn't a public holiday."
            return f"Yes, {when} is {found[0].title}, a public holiday."
        if topic in ("next_holiday", "named_holiday"):
            found = self.next_holiday(today, ask.item if topic == "named_holiday" else "")
            if found is None:
                return "I don't know when that is." if topic == "named_holiday" else "I don't know of a public holiday in the next year."
            occasion, day = found
            start = f"The next public holiday is {occasion.title}," if topic == "next_holiday" else f"{occasion.title} is"
            return f"{start} {spoken_day(day, today)}." if (day - today).days < 7 else f"{start} on {spoken_day(day, today)}."
        if topic == "clocks":
            changes = clock_changes(now, 370, self.clock.local)
            if not changes:
                return "I don't know of a clock change here in the next year."
            change = changes[0]
            moment = self.clock.local(change.at)
            way = "forward" if change.forward else "back"
            amount = "an hour" if change.hours == 1.0 else f"{change.hours:g} hours"
            return f"The clocks go {way} {amount} on {spoken_day(moment.date(), today)}, early in the morning."
        if topic == "moon":
            name, lit = moon(today)
            if name == "full moon":
                return "It's a full moon tonight."
            return f"It's a {name} tonight, about {round(lit * 100)} percent lit."
        return ""

    def tick(self, now: float, mono: float, quiet: bool) -> None:
        if mono < self.next_at:
            return
        self.next_at = mono + 60.0
        if quiet or self.house.busy():
            return
        local = self.clock.local(now)
        self._clocks(now, local)
        self._holiday(local)
        self._curtains(now, local)
        if OFFER_HOURS[0] <= local.hour < OFFER_HOURS[1]:
            self._alarm_test_offer(local, mono)
            self._facts(now, mono)
        if EVENING[0] <= local.hour < EVENING[1]:
            self._damp(local)

    def _once(self, key: str) -> bool:
        if key in self.asked:
            return False
        self.asked[key] = True
        self.house.book.touch()
        return True

    def _clocks(self, now: float, local: datetime) -> None:
        if local.hour < 16:
            return
        if self.changes_day != local.date():
            self.changes_day = local.date()
            self.changes = clock_changes(now, 1, self.clock.local)
        change = next((c for c in self.changes if 0 <= c.at - now <= CLOCKS_AHEAD_S), None)
        if change is None or not self.house.household_here(now):
            return
        if self._once(f"clocks:{self.clock.local(change.at).date().isoformat()}"):
            way = "forward" if change.forward else "back"
            self.house.teller.to_household(f"The clocks go {way} an hour tonight.", "clocks", self.house.mono())

    def _holiday(self, local: datetime) -> None:
        if not 8 <= local.hour < 20:
            return
        today = local.date()
        for offset in range(1, HOLIDAY_AHEAD_DAYS + 1):
            day = today + timedelta(days=offset)
            for occasion in self.holidays_on(day):
                if "(observed)" in occasion.title:
                    continue
                key = f"holiday:{occasion.id}:{day.isoformat()}"
                if key in self.asked or not self.house.household_here(self.clock.now()):
                    continue
                if self.house.teller.to_household(f"{occasion.title} is {spoken_day(day, today)}. It's a public holiday.", "holiday", self.house.mono()):
                    self._once(key)
                return

    def _curtains(self, now: float, local: datetime) -> None:
        wanted = self.house.book.settings.get("curtains")
        if not wanted:
            return
        times = self.sun(local.date())
        if times is None or times[1] is None:
            return
        due = times[1].timestamp() - CURTAINS_BEFORE_S
        if not due <= now <= due + CURTAINS_WINDOW_S:
            return
        key = f"curtains:{local.date().isoformat()}"
        if key in self.asked or not self.house.household_here(now):
            return
        line = f"Sunset's at {spoken_time(times[1])}, so it's time to close the curtains, as you asked."
        week = f"eeca:{local.isocalendar()[0]}-{local.isocalendar()[1]}"
        if self._cold(now) and week not in self.asked:
            line += EECA
            self._once(week)
        if self.house.teller.to_household(line, "curtains", self.house.mono()):
            self._once(key)

    def _cold(self, now: float) -> bool:
        air = self.house.damp.reading(now)
        if air is not None:
            return air.temperature_c <= COLD_C
        return self.clock.local(now).month in (5, 6, 7, 8, 9)

    def _alarm_test_offer(self, local: datetime, mono: float) -> None:
        settings = self.house.book.settings
        if settings.get("alarm_test_offers") is False or local.day > OFFER_DAYS:
            return
        month = local.strftime("%Y-%m")
        key = f"alarm_test:{month}"
        last = self.house.book["asked"].get("last_test")
        if key in self.asked or (last and self.clock.local(float(last)).strftime("%Y-%m") == month):
            return
        close = self.house.close_here(self.clock.now())
        ladder = getattr(self.house.safety, "ladder", None)
        if not close or self.house.asks.waiting() or getattr(ladder, "test", None) is not None:
            return
        self._once(key)
        self.house.say("It's a new month. Shall we test the smoke alarms? Fire and Emergency suggests testing them every month.", to=close[0].label, why="monthly alarm test")
        self.house.asks.expect("alarm_test_offer", "", mono, close[0].id)

    def _facts(self, now: float, mono: float) -> None:
        facts = self.house.p.books.things.facts
        due = facts.due(now)
        if not due or self.house.asks.waiting():
            return
        close = self.house.close_here(now)
        if not close:
            return
        fact = due[0]
        key = f"fact:{fact.name}:{self.clock.local(now).strftime('%Y-%m')}"
        if key in self.asked:
            return
        self._once(key)
        who = f"{fact.by_label} told me" if fact.by_label else "I was told"
        self.house.say(f"A year ago {who} the {spoken_fact(fact.name)} is {fact.where}. Is that still right?", to=close[0].label, why="yearly check")
        self.house.asks.expect("fact_check", fact.name, mono, close[0].id)

    def _damp(self, local: datetime) -> None:
        key = f"damp:{local.date().isoformat()}"
        if key in self.asked or not self.house.household_here(self.clock.now()):
            return
        line = self.house.damp.evening_line(self.clock.now())
        if not line:
            return
        if self.house.teller.to_household(line, "damp", self.house.mono()):
            self._once(key)
