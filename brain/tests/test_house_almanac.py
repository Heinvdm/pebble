from datetime import date, datetime, time, timedelta, timezone, tzinfo

import pytest

import pebble.occasions as occasions
from pebble.clock import FakeClock
from pebble.house.almanac import PHASES, TOWNS, ClockChange, clock_changes, moon, sun_times, town, twilight
from pebble.occasions import MATARIKI, MATARIKI_SOURCE, Calendar, easter, nz_holidays
from pebble.selfstore import read_json
from pebble.selfstore.store import TEMPLATE_DIR

HOUR = timedelta(hours=1)


class NewZealand(tzinfo):
    def _sundays(self, year: int) -> tuple[int, int]:
        first_april = next(d for d in range(1, 8) if date(year, 4, d).weekday() == 6)
        last_september = next(d for d in range(30, 23, -1) if date(year, 9, d).weekday() == 6)
        return first_april, last_september

    def utcoffset(self, dt):
        ends, starts = self._sundays(dt.year)
        wall = dt.replace(tzinfo=None, fold=0)
        edge = 2 if dt.fold else 3
        summer = wall < datetime(dt.year, 4, ends, edge) or wall >= datetime(dt.year, 9, starts, edge)
        return timedelta(hours=13 if summer else 12)

    def dst(self, dt):
        return self.utcoffset(dt) - timedelta(hours=12)

    def tzname(self, dt):
        return "NZDT" if self.dst(dt) else "NZST"

    def fromutc(self, dt):
        utc = dt.replace(tzinfo=None)
        ends, starts = self._sundays(utc.year)
        winter_from = datetime(utc.year, 4, ends, 14) - timedelta(days=1)
        summer_from = datetime(utc.year, 9, starts, 14) - timedelta(days=1)
        summer = utc < winter_from or utc >= summer_from
        fold = 1 if winter_from <= utc < winter_from + HOUR else 0
        return (utc + timedelta(hours=13 if summer else 12)).replace(tzinfo=self, fold=fold)


NZ = NewZealand()
SUN_NOAA = {
    "Auckland": {
        date(2026, 3, 21): ("07:24", "19:31"),
        date(2026, 6, 21): ("07:34", "17:12"),
        date(2026, 9, 23): ("06:10", "18:18"),
        date(2026, 12, 22): ("05:58", "20:40"),
    },
    "Christchurch": {
        date(2026, 3, 21): ("07:32", "19:40"),
        date(2026, 6, 21): ("08:03", "16:59"),
        date(2026, 9, 23): ("06:18", "18:27"),
        date(2026, 12, 22): ("05:45", "21:11"),
    },
}
CIVIL_PUBLISHED = {
    "Auckland": {
        date(2026, 3, 21): ("06:59", "19:58"),
        date(2026, 6, 21): ("07:05", "17:41"),
        date(2026, 9, 23): ("05:43", "18:43"),
        date(2026, 12, 22): ("05:28", "21:11"),
    },
    "Christchurch": {
        date(2026, 3, 21): ("07:04", "20:09"),
        date(2026, 6, 21): ("07:30", "17:32"),
        date(2026, 9, 23): ("05:49", "18:55"),
        date(2026, 12, 22): ("05:09", "21:46"),
    },
}
TROMSO = (69.65, 18.96)
CET = timezone(timedelta(hours=1))
CEST = timezone(timedelta(hours=2))
PUBLISHED_2026 = {
    ("New Year's Day", "2026-01-01"),
    ("Day after New Year's Day", "2026-01-02"),
    ("Waitangi Day", "2026-02-06"),
    ("Good Friday", "2026-04-03"),
    ("Easter Monday", "2026-04-06"),
    ("Anzac Day", "2026-04-25"),
    ("Anzac Day (observed)", "2026-04-27"),
    ("King's Birthday", "2026-06-01"),
    ("Matariki", "2026-07-10"),
    ("Labour Day", "2026-10-26"),
    ("Christmas Day", "2026-12-25"),
    ("Boxing Day", "2026-12-26"),
    ("Boxing Day (observed)", "2026-12-28"),
}
PUBLISHED_2027 = {
    ("New Year's Day", "2027-01-01"),
    ("Day after New Year's Day", "2027-01-02"),
    ("Day after New Year's Day (observed)", "2027-01-04"),
    ("Waitangi Day", "2027-02-06"),
    ("Waitangi Day (observed)", "2027-02-08"),
    ("Good Friday", "2027-03-26"),
    ("Easter Monday", "2027-03-29"),
    ("Anzac Day", "2027-04-25"),
    ("Anzac Day (observed)", "2027-04-26"),
    ("King's Birthday", "2027-06-07"),
    ("Matariki", "2027-06-25"),
    ("Labour Day", "2027-10-25"),
    ("Christmas Day", "2027-12-25"),
    ("Christmas Day (observed)", "2027-12-27"),
    ("Boxing Day", "2027-12-26"),
    ("Boxing Day (observed)", "2027-12-28"),
}
OBSERVED_PUBLISHED = {
    2015: {("Anzac Day (observed)", "2015-04-27"), ("Boxing Day (observed)", "2015-12-28")},
    2016: {("Day after New Year's Day (observed)", "2016-01-04"), ("Waitangi Day (observed)", "2016-02-08"), ("Christmas Day (observed)", "2016-12-27")},
    2021: {
        ("Day after New Year's Day (observed)", "2021-01-04"),
        ("Waitangi Day (observed)", "2021-02-08"),
        ("Anzac Day (observed)", "2021-04-26"),
        ("Christmas Day (observed)", "2021-12-27"),
        ("Boxing Day (observed)", "2021-12-28"),
    },
    2022: {
        ("New Year's Day (observed)", "2022-01-03"),
        ("Day after New Year's Day (observed)", "2022-01-04"),
        ("Waitangi Day (observed)", "2022-02-07"),
        ("Christmas Day (observed)", "2022-12-27"),
    },
    2023: {("New Year's Day (observed)", "2023-01-03")},
    2024: set(),
    2025: set(),
}
EASTER_WEEKENDS = {
    2015: ("2015-04-03", "2015-04-06"),
    2016: ("2016-03-25", "2016-03-28"),
    2017: ("2017-04-14", "2017-04-17"),
    2021: ("2021-04-02", "2021-04-05"),
    2022: ("2022-04-15", "2022-04-18"),
    2023: ("2023-04-07", "2023-04-10"),
    2024: ("2024-03-29", "2024-04-01"),
    2025: ("2025-04-18", "2025-04-21"),
    2026: ("2026-04-03", "2026-04-06"),
    2027: ("2027-03-26", "2027-03-29"),
}
OLD_HOLIDAYS = [
    {"id": "nz-new-year", "title": "New Year's Day", "kind": "holiday", "region": "NZ", "month": 1, "day": 1, "mood": "party", "enthusiasm": 0.5},
    {"id": "nz-day-after-new-year", "title": "Day after New Year's Day", "kind": "holiday", "region": "NZ", "month": 1, "day": 2, "mood": "calm", "enthusiasm": 0.2},
    {"id": "nz-waitangi", "title": "Waitangi Day", "kind": "holiday", "region": "NZ", "month": 2, "day": 6, "mood": "calm", "enthusiasm": 0.3},
    {"id": "nz-good-friday-2026", "title": "Good Friday", "kind": "holiday", "region": "NZ", "date": "2026-04-03", "mood": "quiet", "enthusiasm": 0.1},
    {"id": "nz-easter-monday-2026", "title": "Easter Monday", "kind": "holiday", "region": "NZ", "date": "2026-04-06", "mood": "calm", "enthusiasm": 0.3},
    {"id": "nz-good-friday-2027", "title": "Good Friday", "kind": "holiday", "region": "NZ", "date": "2027-03-26", "mood": "quiet", "enthusiasm": 0.1},
    {"id": "nz-easter-monday-2027", "title": "Easter Monday", "kind": "holiday", "region": "NZ", "date": "2027-03-29", "mood": "calm", "enthusiasm": 0.3},
    {"id": "nz-anzac", "title": "Anzac Day", "kind": "holiday", "region": "NZ", "month": 4, "day": 25, "mood": "quiet", "enthusiasm": 0.0},
    {"id": "nz-kings-birthday", "title": "King's Birthday", "kind": "holiday", "region": "NZ", "month": 6, "weekday": "monday", "nth": 1, "mood": "calm", "enthusiasm": 0.2},
    {"id": "nz-matariki-2026", "title": "Matariki", "kind": "holiday", "region": "NZ", "date": "2026-07-10", "mood": "calm", "enthusiasm": 0.6},
    {"id": "nz-matariki-2027", "title": "Matariki", "kind": "holiday", "region": "NZ", "date": "2027-06-25", "mood": "calm", "enthusiasm": 0.6},
    {"id": "nz-labour-day", "title": "Labour Day", "kind": "holiday", "region": "NZ", "month": 10, "weekday": "monday", "nth": 4, "mood": "calm", "enthusiasm": 0.2},
    {"id": "nz-christmas", "title": "Christmas Day", "kind": "holiday", "region": "NZ", "month": 12, "day": 25, "mood": "party", "enthusiasm": 0.7},
    {"id": "nz-boxing-day", "title": "Boxing Day", "kind": "holiday", "region": "NZ", "month": 12, "day": 26, "mood": "calm", "enthusiasm": 0.3},
]


def wall(day: date, text: str) -> datetime:
    hours, minutes = (int(part) for part in text.split(":"))
    return datetime.combine(day, time(hours, minutes), NZ)


def near(found: datetime, expected: datetime, minutes: float = 2.0) -> bool:
    return abs((found - expected).total_seconds()) <= minutes * 60


def nz_local(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, NZ)


def utc(*parts) -> float:
    return datetime(*parts, tzinfo=timezone.utc).timestamp()


def pairs(year: int) -> set[tuple[str, str]]:
    return {(entry["title"], entry["date"]) for entry in nz_holidays(year)}


def titles(cal: Calendar, day: date) -> list[str]:
    return [o.title for o in cal.on(day)]


def template_calendar() -> Calendar:
    return Calendar(read_json(TEMPLATE_DIR / "calendar.json"), date(2026, 10, 1), "Pebble")


@pytest.mark.parametrize("name", sorted(SUN_NOAA))
def test_sunrise_and_sunset_match_noaa_on_the_2026_solstices_and_equinoxes(name):
    lat, lon = town(name)
    for day, (rise, fall) in SUN_NOAA[name].items():
        sunrise, sunset = sun_times(day, lat, lon, NZ)
        assert near(sunrise, wall(day, rise)), (name, day, sunrise)
        assert near(sunset, wall(day, fall)), (name, day, sunset)
        assert sunrise.date() == day and sunset.date() == day
        assert sunrise.utcoffset() == timedelta(hours=13 if day.month in (3, 12) else 12)


@pytest.mark.parametrize("name", sorted(CIVIL_PUBLISHED))
def test_civil_twilight_matches_the_published_times(name):
    lat, lon = town(name)
    for day, (dawn_at, dusk_at) in CIVIL_PUBLISHED[name].items():
        dawn, dusk = twilight(day, lat, lon, NZ)
        sunrise, sunset = sun_times(day, lat, lon, NZ)
        assert near(dawn, wall(day, dawn_at)), (name, day, dawn)
        assert near(dusk, wall(day, dusk_at)), (name, day, dusk)
        assert timedelta(minutes=20) < sunrise - dawn < timedelta(minutes=40)
        assert timedelta(minutes=20) < dusk - sunset < timedelta(minutes=40)


def test_the_shortest_day_is_shorter_in_the_south():
    day = date(2026, 6, 21)
    lengths = {}
    for name in ("Kerikeri", "Auckland", "Wellington", "Christchurch", "Invercargill"):
        sunrise, sunset = sun_times(day, *town(name), NZ)
        lengths[name] = sunset - sunrise
    assert list(lengths.values()) == sorted(lengths.values(), reverse=True)
    assert timedelta(hours=8, minutes=50) < lengths["Christchurch"] < timedelta(hours=9)


def test_times_come_back_in_the_zone_asked_for():
    day = date(2026, 6, 21)
    in_nz = sun_times(day, *town("Wellington"), NZ)
    in_utc = sun_times(day, *town("Wellington"), timezone.utc)
    assert [moment.timestamp() for moment in in_nz] == [moment.timestamp() for moment in in_utc]
    assert in_utc[0].tzinfo is timezone.utc


def test_no_sunrise_in_the_midnight_sun_or_the_polar_night():
    assert sun_times(date(2026, 6, 21), *TROMSO, CEST) == (None, None)
    assert twilight(date(2026, 6, 21), *TROMSO, CEST) == (None, None)
    assert sun_times(date(2026, 12, 21), *TROMSO, CET) == (None, None)
    dawn, dusk = twilight(date(2026, 12, 21), *TROMSO, CET)
    assert dawn is not None and dusk is not None
    assert datetime(2026, 12, 21, 8, 30, tzinfo=CET) < dawn < datetime(2026, 12, 21, 11, 0, tzinfo=CET)
    assert datetime(2026, 12, 21, 12, 30, tzinfo=CET) < dusk < datetime(2026, 12, 21, 15, 0, tzinfo=CET)
    sunrise, sunset = sun_times(date(2026, 1, 20), *TROMSO, CET)
    assert near(sunrise, datetime(2026, 1, 20, 10, 36, tzinfo=CET)) and near(sunset, datetime(2026, 1, 20, 13, 15, tzinfo=CET))


def test_the_moon_on_eclipse_days():
    for day in (date(2026, 3, 3), date(2026, 8, 28)):
        name, lit = moon(day)
        assert name == "full moon" and lit > 0.95, day
    name, lit = moon(date(2026, 8, 12))
    assert name == "new moon" and lit < 0.05


def test_the_moon_goes_through_its_phases_in_order():
    start = date(2026, 8, 12)
    names = [moon(start + timedelta(days=round(step * 29.53 / 8)))[0] for step in range(8)]
    assert names == list(PHASES)
    lit = [moon(start + timedelta(days=offset))[1] for offset in range(1, 16)]
    assert lit == sorted(lit)


def test_clocks_go_back_on_the_first_sunday_of_april():
    changes = clock_changes(wall(date(2026, 4, 1), "00:00").timestamp(), 10, nz_local)
    assert changes == [ClockChange(utc(2026, 4, 4, 14), timedelta(hours=13), timedelta(hours=12))]
    change = changes[0]
    assert not change.forward and change.hours == 1.0
    assert nz_local(change.at - 1).strftime("%H:%M:%S %Z") == "02:59:59 NZDT"
    assert nz_local(change.at).strftime("%H:%M %Z") == "02:00 NZST"


def test_clocks_go_forward_on_the_last_sunday_of_september():
    clock = FakeClock.at(datetime(2026, 9, 20, 9, 30, tzinfo=NZ))
    changes = clock_changes(clock.now() + 1234.5, 14, clock.local)
    assert len(changes) == 1
    change = changes[0]
    assert change.at == utc(2026, 9, 26, 14)
    assert change.forward and change.hours == 1.0
    assert (change.before, change.after) == (timedelta(hours=12), timedelta(hours=13))
    assert clock.local(change.at - 1).strftime("%H:%M:%S") == "01:59:59"
    assert clock.local(change.at).strftime("%H:%M %Z") == "03:00 NZDT"


def test_a_year_of_clock_changes_and_none_without_daylight_saving():
    year = clock_changes(wall(date(2026, 1, 1), "00:00").timestamp(), 365, nz_local)
    assert [(change.at, change.forward) for change in year] == [(utc(2026, 4, 4, 14), False), (utc(2026, 9, 26, 14), True)]
    fixed = timezone(timedelta(hours=12))
    assert clock_changes(utc(2026, 1, 1), 365, lambda ts: datetime.fromtimestamp(ts, fixed)) == []


def test_a_half_hour_change_is_half_an_hour():
    switch = utc(2026, 10, 3, 15, 30)

    def lord_howe(ts: float) -> datetime:
        return datetime.fromtimestamp(ts, timezone(timedelta(hours=11 if ts >= switch else 10.5)))

    changes = clock_changes(utc(2026, 10, 1), 5, lord_howe)
    assert [(change.at, change.forward, change.hours) for change in changes] == [(switch, True, 0.5)]


def test_towns_match_with_or_without_macrons():
    assert len(TOWNS) == 25
    assert town("Whangārei") == town("whangarei") == TOWNS["whangarei"]
    assert town("TAUPŌ") == town("Taupo") == TOWNS["taupo"]
    assert town("  palmerston   North ") == TOWNS["palmerston north"]
    assert town("Ōamaru") == TOWNS["oamaru"]
    assert town("Atlantis") is None
    for name, (lat, lon) in TOWNS.items():
        assert -47.0 < lat < -34.0 and 166.0 < lon < 179.0, name
        assert (round(lat, 2), round(lon, 2)) == (lat, lon), name


def test_published_public_holidays_2026_and_2027():
    assert pairs(2026) == PUBLISHED_2026
    assert pairs(2027) == PUBLISHED_2027


@pytest.mark.parametrize("year", sorted(OBSERVED_PUBLISHED))
def test_weekend_holidays_move_like_the_published_lists(year):
    observed = {pair for pair in pairs(year) if pair[0].endswith("(observed)")}
    assert observed == OBSERVED_PUBLISHED[year]


def test_new_year_and_waitangi_on_a_weekend_in_2028():
    observed = {pair for pair in pairs(2028) if pair[0].endswith("(observed)")}
    assert observed == {
        ("New Year's Day (observed)", "2028-01-03"),
        ("Day after New Year's Day (observed)", "2028-01-04"),
        ("Waitangi Day (observed)", "2028-02-07"),
    }


def test_easter_for_many_years():
    for year, (friday, monday) in EASTER_WEEKENDS.items():
        found = {entry["title"]: entry["date"] for entry in nz_holidays(year)}
        assert (found["Good Friday"], found["Easter Monday"]) == (friday, monday), year
    known = {1943: date(1943, 4, 25), 2008: date(2008, 3, 23), 2011: date(2011, 4, 24), 2019: date(2019, 4, 21), 2038: date(2038, 4, 25), 2285: date(2285, 3, 22)}
    for year, sunday in known.items():
        assert easter(year) == sunday


def test_matariki_follows_the_act_to_2052_and_stops():
    assert MATARIKI_SOURCE == "Te Kāhui o Matariki Public Holiday Act 2022, Schedule 1"
    assert sorted(MATARIKI) == list(range(2022, 2053))
    for year, (month, day) in MATARIKI.items():
        assert date(year, month, day).weekday() == 4 and month in (6, 7), year
    for year, expected in ((2022, "2022-06-24"), (2026, "2026-07-10"), (2027, "2027-06-25"), (2052, "2052-06-21")):
        found = [entry for entry in nz_holidays(year) if entry["title"] == "Matariki"]
        assert [entry["date"] for entry in found] == [expected]
        assert found[0]["source"] == MATARIKI_SOURCE
    for year in (2021, 2053):
        assert not [entry for entry in nz_holidays(year) if entry["title"] == "Matariki"]


def test_holiday_entries_have_the_calendar_shape_and_moods():
    for entry in nz_holidays(2027):
        assert set(entry) >= {"id", "title", "kind", "region", "date", "mood", "enthusiasm", "source"}
        assert entry["kind"] == "holiday" and entry["region"] == "NZ" and entry["source"]
        date.fromisoformat(entry["date"])
    found = {entry["title"]: entry for entry in nz_holidays(2027)}
    assert (found["Good Friday"]["mood"], found["Good Friday"]["enthusiasm"]) == ("quiet", 0.1)
    assert (found["Anzac Day"]["mood"], found["Anzac Day"]["enthusiasm"]) == ("quiet", 0.0)
    assert (found["Anzac Day (observed)"]["mood"], found["Anzac Day (observed)"]["enthusiasm"]) == ("quiet", 0.0)
    assert (found["Christmas Day"]["mood"], found["Christmas Day"]["enthusiasm"]) == ("party", 0.7)
    assert (found["Matariki"]["mood"], found["Matariki"]["enthusiasm"]) == ("calm", 0.6)
    assert all(entry["mood"] != "party" for title, entry in found.items() if title.endswith("(observed)"))
    assert "Saturday" in found["Christmas Day (observed)"]["why"] and "Monday" in found["Christmas Day (observed)"]["why"]
    assert len({entry["id"] for entry in nz_holidays(2027)}) == len(nz_holidays(2027))
    assert "Queen's Birthday" in {title for title, _ in pairs(2022)}
    assert "King's Birthday" in {title for title, _ in pairs(2023)}


def test_the_template_computes_holidays_every_year():
    data = read_json(TEMPLATE_DIR / "calendar.json")
    assert data["holiday_rules"] == "nz"
    assert not [entry for entry in data["holidays"] if "date" in entry]
    assert "2052" in data["holidays_note"] and "anniversary" in data["holidays_note"]
    cal = template_calendar()
    assert titles(cal, date(2026, 4, 3)) == ["Good Friday"]
    assert titles(cal, date(2026, 12, 25)) == ["Christmas Day"]
    assert titles(cal, date(2027, 2, 8)) == ["Waitangi Day (observed)"]
    assert "Matariki" in titles(cal, date(2030, 6, 21))
    assert "Easter Monday" in titles(cal, date(2031, 4, 14))
    assert ("Waitangi Day (observed)", 5) in [(o.title, d) for o, d in cal.upcoming(date(2027, 2, 3), 7)]


def test_an_old_calendar_gains_computed_holidays_without_duplicates():
    cal = Calendar({"holidays": OLD_HOLIDAYS, "personal": []})
    assert cal.holiday_rules is None
    assert titles(cal, date(2026, 4, 3)) == ["Good Friday"]
    assert titles(cal, date(2026, 7, 10)) == ["Matariki"]
    assert titles(cal, date(2026, 4, 27)) == ["Anzac Day (observed)"]
    assert "Matariki" in titles(cal, date(2028, 7, 14))
    day = date(2026, 1, 1)
    while day < date(2028, 1, 1):
        found = titles(cal, day)
        assert len(found) == len(set(found)), (day, found)
        day += timedelta(days=1)
    assert "holiday_rules" not in cal.to_dict()


def test_no_rules_and_no_new_zealand_holidays_means_no_computed_ones():
    assert Calendar({"holidays": []}).on(date(2026, 12, 25)) == []
    assert Calendar({"holidays": [], "holiday_rules": "nz"}).on(date(2026, 12, 25))[0].title == "Christmas Day"


def test_a_saved_calendar_keeps_its_rules():
    cal = template_calendar()
    saved = cal.to_dict()
    assert saved["holiday_rules"] == "nz"
    again = Calendar({**saved, "holidays": []})
    assert titles(again, date(2027, 12, 28)) == ["Boxing Day (observed)"]


def test_holidays_are_worked_out_once_a_year(monkeypatch):
    calls = []
    real = occasions.nz_holidays

    def counting(year):
        calls.append(year)
        return real(year)

    monkeypatch.setattr(occasions, "nz_holidays", counting)
    cal = template_calendar()
    day = date(2026, 12, 1)
    for _ in range(62):
        cal.on(day)
        day += timedelta(days=1)
    assert calls == [2026, 2027]
