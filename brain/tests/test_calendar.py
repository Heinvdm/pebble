from datetime import date

import pytest

from pebble.age import age_days, stage_for
from pebble.occasions import BadDate, Calendar, nth_weekday
from pebble.selfstore import read_json
from pebble.selfstore.store import TEMPLATE_DIR


def calendar(birthday=date(2026, 10, 1)) -> Calendar:
    return Calendar(read_json(TEMPLATE_DIR / "calendar.json"), birthday, "Pebble")


def titles(cal: Calendar, day: date) -> list[str]:
    return [o.title for o in cal.on(day)]


def test_ada_lovelace_day_is_the_second_tuesday_of_october():
    assert nth_weekday(2026, 10, "tuesday", 2) == date(2026, 10, 13)
    assert nth_weekday(2027, 10, "tuesday", 2) == date(2027, 10, 12)
    assert "Ada Lovelace Day" in titles(calendar(), date(2026, 10, 13))
    assert "Ada Lovelace Day" not in titles(calendar(), date(2026, 10, 14))


def test_robot_days_from_the_spec():
    cal = calendar()
    assert "R.U.R. Day" in titles(cal, date(2027, 1, 25))
    assert "Alan Turing's birthday" in titles(cal, date(2027, 6, 23))
    assert "Curiosity Day" in titles(cal, date(2027, 8, 6))
    assert "ChatGPT's birthday" in titles(cal, date(2026, 11, 30))
    assert "Isaac Asimov's birthday" in titles(cal, date(2027, 1, 2))


def test_solemn_days_are_quiet():
    anzac = next(o for o in calendar().on(date(2027, 4, 25)) if o.title == "Anzac Day")
    assert anzac.mood == "quiet" and anzac.enthusiasm == 0.0


def test_moving_holidays_only_on_their_year():
    cal = calendar()
    assert "Matariki" in titles(cal, date(2026, 7, 10))
    assert "Matariki" not in titles(cal, date(2027, 7, 10))
    assert "Labour Day" in titles(cal, date(2026, 10, 26))


def test_its_own_birthday_from_the_next_year():
    cal = calendar(date(2026, 10, 1))
    assert "Pebble's birthday" not in titles(cal, date(2026, 10, 1))
    assert "Pebble's birthday" in titles(cal, date(2027, 10, 1))


def test_personal_events_and_leap_days():
    cal = calendar()
    cal.add_personal("Ina's birthday", 2, 29, "birthday", "2026-10-15T00:00:00+00:00", person="Ina")
    assert "Ina's birthday" in titles(cal, date(2027, 2, 28))
    assert "Ina's birthday" in titles(cal, date(2028, 2, 29))
    with pytest.raises(BadDate):
        cal.add_personal("nonsense", 2, 30, "event", "x")
    with pytest.raises(BadDate):
        cal.add_personal("nonsense", 1, 1, "party", "x")
    cal.add_personal("Vet visit", 11, 3, "event", "x", year=2026)
    assert "Vet visit" in titles(cal, date(2026, 11, 3))
    assert "Vet visit" not in titles(cal, date(2027, 11, 3))


def test_upcoming_counts_down():
    soon = calendar().upcoming(date(2026, 11, 27), 5)
    assert ("ChatGPT's birthday", 3) in [(o.title, d) for o, d in soon]


def test_age_stages():
    born = date(2026, 10, 1)
    assert stage_for(age_days(born, date(2026, 10, 3))) == "newborn"
    assert stage_for(age_days(born, date(2026, 10, 20))) == "child"
    assert stage_for(age_days(born, date(2026, 12, 1))) == "teen"
    assert stage_for(age_days(born, date(2027, 2, 1))) == "adult"
    assert age_days(None, date(2026, 10, 3)) == 0
