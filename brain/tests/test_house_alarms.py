import asyncio

from test_safety_ladder import Fake, notice, run

from pebble.safety.ladder import TEST_REAL_S, TEST_S, Ladder


def beeping(start, stop, every=4.0, kind="smoke_alarm"):
    def feed(t):
        if start <= t < stop and (t - start) % every < 1.0:
            return [notice_of(kind)]
        return []

    return feed


FAKE = {}


def notice_of(kind):
    fake = FAKE["fake"]
    return notice(fake, kind, 0.9, freq_hz=3100.0, level_db=-30.0)


def make():
    fake = Fake(here=["Ina"])
    FAKE["fake"] = fake
    ladder = Ladder(fake.ports())
    ended = []
    ladder.listeners.append(lambda incident, how: ended.append(how))
    return fake, ladder, ended


def test_a_short_test_press_is_counted_and_never_raises_the_alarm():
    fake, ladder, ended = make()
    assert ladder.start_test("Ina")
    asyncio.run(run(ladder, fake, 40.0, feed=beeping(2.0, 10.0)))
    assert ended == ["tested"] and len(ladder.test.heard) == 1
    assert ladder.test.heard[0]["freq_hz"] == 3100.0
    assert fake.sirens == [] and fake.alarms == [] and not any("Is everything okay" in line for line in fake.lines())
    assert ladder.start_test("Ina") is False


def test_an_alarm_that_keeps_going_past_half_a_minute_is_real_even_in_a_test():
    fake, ladder, ended = make()
    ladder.start_test("Ina")
    asyncio.run(run(ladder, fake, TEST_REAL_S + 40.0, feed=beeping(1.0, 200.0)))
    assert "That alarm has kept going for more than half a minute, so I'm treating it as real." in fake.lines()
    assert any("Is everything okay" in line for line in fake.lines())
    assert ended == [] and ladder.incidents["fire"].step in ("ask", "alarm")


def test_smoke_seen_during_a_test_makes_it_real_at_once():
    fake, ladder, ended = make()
    ladder.start_test("Ina")

    def feed(t):
        out = beeping(1.0, 60.0)(t)
        if t == 6.0:
            out.append(notice(fake, "smoke_seen", 0.6))
        return out

    asyncio.run(run(ladder, fake, 30.0, feed=feed))
    assert not ladder.incidents["fire"].test
    assert any("Is everything okay" in line for line in fake.lines())


def test_the_test_ends_by_itself_after_ten_minutes_and_an_alarm_after_it_is_real():
    fake, ladder, ended = make()
    ladder.start_test("Ina")
    asyncio.run(run(ladder, fake, TEST_S + 2.0))
    assert ladder.test is None and ladder.last_test is not None and ladder.last_test.ended == "ten minutes went by"
    asyncio.run(run(ladder, fake, 20.0, feed=beeping(0.0, 20.0)))
    assert any("Is everything okay" in line for line in fake.lines())


def test_a_test_cannot_start_while_an_alarm_is_going_and_an_alarm_already_heard_stays_real():
    fake, ladder, ended = make()
    asyncio.run(run(ladder, fake, 12.0, feed=beeping(0.0, 100.0)))
    assert ladder.active
    assert ladder.start_test("Ina") is False


def test_an_incident_from_before_the_test_is_never_turned_into_a_test():
    fake, ladder, ended = make()
    ladder.notice(notice(fake, "smoke_alarm", 0.5, freq_hz=3100.0))
    asyncio.run(run(ladder, fake, 2.0))
    assert ladder.incidents["fire"].step == "check" and ladder.start_test("Ina")
    asyncio.run(run(ladder, fake, 3.0, feed=beeping(0.0, 100.0)))
    assert not ladder.incidents["fire"].test
    assert any("Is everything okay" in line for line in fake.lines())
