import asyncio

import pytest

from pebble.clock import FakeClock
from pebble.safety.ladder import ASK_S, CHECK_S, CONFIRM_S, END_AFTER_S, HELP_ASK_S, NOTIFY_AFTER_S, REGRACE_S, Ladder, Ports
from pebble.safety.notice import Notice
from pebble.safety.words import read_line


class Fake:
    def __init__(self, notify=True, here=(), anyone=False):
        self.clock = FakeClock(1_792_000_000.0)
        self.said = []
        self.sirens = []
        self.faces = []
        self.alarms = []
        self.notes = []
        self.diary = []
        self.records = []
        self.roused = []
        self.seeks = []
        self.felts = []
        self.notified = []
        self.stopped = 0
        self.notify_enabled = notify
        self.here = list(here)
        self.anyone = anyone
        self.tiers = {"ina": "trusted", "sam": "stranger", "kid": "child", "mo": "friend"}

    def ports(self):
        async def say(text, loud):
            self.said.append((text, loud))

        return Ports(
            clock=self.clock,
            say=say,
            siren=self.sirens.append,
            face_alarm=self.alarms.append,
            face_show=self.faces.append,
            note=lambda text, major: self.notes.append((text, major)),
            diary=lambda text, kind: self.diary.append(text),
            record=lambda kind, **data: self.records.append((kind, data)),
            rouse=self.roused.append,
            seek=lambda why, done: self.seeks.append((why, done)) or True,
            stop_wheels=self._stop,
            felt=lambda kind, text: self.felts.append((kind, text)),
            tier_of=lambda person: self.tiers.get(person, "stranger"),
            label_of=lambda person: (person or "someone").title(),
            owner_of=lambda person: person == "ina",
            trusted_here=lambda: list(self.here),
            anyone_here=lambda: self.anyone or bool(self.here),
            notify=lambda title, text: self.notified.append((title, text)),
            notify_on=lambda: self.notify_enabled,
        )

    def _stop(self):
        self.stopped += 1

    def lines(self):
        return [text for text, _ in self.said]

    def loud(self):
        return [text for text, loud in self.said if loud]


def notice(fake, kind, confidence, person=None, **detail):
    return Notice(kind, confidence, "test", fake.clock.now(), f"test {kind}", detail, person)


async def run(ladder, fake, seconds, every=1.0, feed=None, quiet=False):
    t = 0.0
    while t < seconds:
        if feed is not None:
            for item in feed(t) or []:
                ladder.notice(item)
        await ladder.step(quiet)
        await asyncio.sleep(0)
        fake.clock.advance(every)
        t += every


def beeping(fake, start=0.0, until=1e9):
    def feed(t):
        if start <= t < until and int(t) % 4 == 0:
            return [notice(fake, "smoke_alarm", 0.5 if t < start + 4 else 0.97)]
        return []

    return feed


def test_smoke_alarm_ladder_in_order():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        await run(ladder, fake, 5, feed=beeping(fake))
        assert ladder.incidents["fire"].step == "ask"
        assert fake.lines() == ["I can hear a smoke alarm going off. Is everything okay?"]
        assert fake.roused and ladder.active
        await run(ladder, fake, ASK_S + 1, feed=beeping(fake))
        incident = ladder.incidents["fire"]
        assert incident.step == "alarm"
        assert fake.sirens[0] is True and fake.alarms == ["SMOKE"]
        assert fake.seeks and "smoke alarm" in fake.seeks[0][0]
        assert any("raised the alarm" in line for line in fake.diary)
        await run(ladder, fake, 20, feed=beeping(fake))
        assert fake.sirens.count(True) >= 2 and False in fake.sirens
        assert "The smoke alarm is going off!" in fake.loud()
        assert not fake.notified
        fake.seeks[0][1]("found", "Ina")
        await run(ladder, fake, 2, feed=beeping(fake))
        assert fake.sirens[-1] is False
        assert "Ina, the smoke alarm is going off! Please check, and tell me when it's safe." in fake.loud()
        await run(ladder, fake, NOTIFY_AFTER_S, feed=beeping(fake))
        assert len(fake.notified) == 1
        title, text = fake.notified[0]
        assert "smoke alarm" in title and "told someone" in text and "http" not in text
        ladder.heard("ina", read_line("it's fine, it was the toast"), "trusted", sure=True)
        await run(ladder, fake, 1, feed=beeping(fake))
        assert "fire" in ladder.incidents and fake.said[-1] == ("Is it really fine?", False)
        ladder.heard("ina", read_line("yes"), "trusted", sure=True)
        await run(ladder, fake, 1, feed=beeping(fake))
        assert "fire" not in ladder.incidents
        assert fake.alarms[-1] == "" and not ladder.active
        assert fake.said[-1] == ("Okay, thank you. I'll stop.", False)
        assert any("Ina told me it was fine" in line for line in fake.diary)
        before = len(fake.said)
        await run(ladder, fake, 10, feed=beeping(fake))
        assert len(fake.said) == before and "fire" not in ladder.incidents

    asyncio.run(go())


def test_a_stranger_cannot_stand_it_down():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        await run(ladder, fake, 5, feed=beeping(fake))
        ladder.heard("sam", read_line("it's fine"), "stranger")
        ladder.heard("kid", read_line("false alarm"), "child")
        await run(ladder, fake, 2, feed=beeping(fake))
        assert ladder.incidents["fire"].step == "ask"
        assert "Thanks. I'll keep going until someone I know well tells me it's fine." in fake.lines()

    asyncio.run(go())


def test_one_group_of_beeps_alone_is_let_go_quietly():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        ladder.notice(notice(fake, "smoke_alarm", 0.5))
        await run(ladder, fake, CHECK_S + 2)
        assert not ladder.incidents and fake.said == [] and fake.sirens == []
        assert any(kind == "safety_end" and data["how"] == "unsure" for kind, data in fake.records)

    asyncio.run(go())


def test_beeps_that_stop_before_the_alarm():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        await run(ladder, fake, 50, feed=beeping(fake, until=6))
        assert not ladder.incidents
        assert "It has stopped now. I'll keep listening." in fake.lines()
        assert fake.sirens == []

    asyncio.run(go())


def test_alarm_ends_after_it_goes_quiet():
    async def go():
        fake = Fake(notify=False)
        ladder = Ladder(fake.ports())
        await run(ladder, fake, 30, feed=beeping(fake, until=30))
        assert ladder.incidents["fire"].step == "alarm"
        await run(ladder, fake, END_AFTER_S + 5)
        assert not ladder.incidents and fake.sirens[-1] is False and fake.alarms[-1] == ""
        assert any(kind == "safety_notify" and data["sent"] is False for kind, data in fake.records)

    asyncio.run(go())


def test_quiet_hours_hold_back_only_low_notices():
    async def go():
        fake = Fake(anyone=True)
        ladder = Ladder(fake.ports())
        await run(ladder, fake, 1, quiet=True)
        ladder.notice(notice(fake, "water", 0.7))
        await run(ladder, fake, 2, quiet=True)
        assert fake.said == [] and not ladder.incidents
        assert any("kept it to yourself" in text for text, _ in fake.notes)
        await run(ladder, fake, 6, feed=beeping(fake), quiet=True)
        assert fake.lines() == ["I can hear a smoke alarm going off. Is everything okay?"]

    asyncio.run(go())


def test_low_notice_by_day_is_told():
    async def go():
        fake = Fake(here=["Ina"])
        ladder = Ladder(fake.ports())
        ladder.notice(notice(fake, "water", 0.7))
        await run(ladder, fake, 2)
        assert fake.lines() == ["Ina, I can hear water running for a long time. Is that okay?"]

    asyncio.run(go())


def test_help_asks_seeks_and_raises_the_alarm_without_an_answer():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        ladder.notice(notice(fake, "help", 0.9, person="mo"))
        await run(ladder, fake, 1)
        assert fake.loud() == ["Are you okay? Do you need help?"]
        assert fake.seeks
        fake.seeks[0][1]("found", "Mo")
        await run(ladder, fake, 2)
        assert fake.loud()[-1] == "Mo, are you okay? Do you need help?"
        await run(ladder, fake, HELP_ASK_S + 1)
        assert ladder.incidents["help"].step == "alarm" and fake.alarms == ["HELP"]

    asyncio.run(go())


def test_help_answered_yes_raises_at_once():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        ladder.notice(notice(fake, "help", 0.9, person="sam"))
        await run(ladder, fake, 1)
        ladder.heard("sam", read_line("yes please"), "stranger")
        await run(ladder, fake, 1)
        assert ladder.incidents["help"].step == "alarm"

    asyncio.run(go())


def test_the_caller_can_say_they_are_fine():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        ladder.notice(notice(fake, "help", 0.9, person="sam"))
        await run(ladder, fake, 1)
        ladder.heard("sam", read_line("no I'm fine, sorry"), "stranger", sure=True)
        await run(ladder, fake, 1)
        assert ladder.incidents and fake.said[-1] == ("Are you sure you're all right?", False)
        ladder.heard("sam", read_line("yes"), "stranger", sure=True)
        await run(ladder, fake, 1)
        assert not ladder.incidents
        assert fake.said[-1] == ("Okay, I'm glad you're all right.", False)

    asyncio.run(go())


def test_name_shouted_once_does_not_sound_the_alarm():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        ladder.notice(notice(fake, "name_shouted", 0.5))
        await run(ladder, fake, 1)
        assert fake.loud() == ["Did you call me? Is everything okay?"]
        fake.seeks[0][1]("nobody", "nobody was there")
        await run(ladder, fake, HELP_ASK_S + 2)
        assert not ladder.incidents and fake.sirens == []

    asyncio.run(go())


def test_someone_on_the_floor_who_does_not_answer():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        ladder.notice(notice(fake, "on_floor", 0.7, place="rug"))
        await run(ladder, fake, 1)
        assert fake.loud() == ["Are you okay?"]
        fake.seeks[0][1]("found", "someone")
        await run(ladder, fake, 2)
        assert fake.loud()[-1] == "Are you okay? Do you need help?"
        await run(ladder, fake, HELP_ASK_S + 1)
        assert ladder.incidents["floor"].step == "alarm"
        assert fake.alarms == ["HELP"]

    asyncio.run(go())


def test_someone_on_the_floor_who_says_they_are_fine():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        ended = []
        ladder.on_end = lambda incident, how: ended.append(how)
        ladder.notice(notice(fake, "on_floor", 0.7, track=4))
        await run(ladder, fake, 1)
        ladder.heard(None, read_line("I'm okay, just stretching"), "stranger", track=4)
        await run(ladder, fake, 1)
        ladder.heard(None, read_line("yes really"), "stranger", track=4)
        await run(ladder, fake, 1)
        assert ended == ["stood down"] and not ladder.incidents
        ladder.notice(notice(fake, "on_floor", 0.7, track=4))
        assert not ladder.incidents

    asyncio.run(go())


def test_a_heat_hint_alone_goes_to_look_but_never_sounds_the_alarm():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        ladder.notice(notice(fake, "heat_rise", 0.3))
        await run(ladder, fake, CHECK_S + 1)
        assert ladder.incidents["fire"].step == "wonder" and fake.seeks
        fake.seeks[0][1]("found", "Ina")
        await run(ladder, fake, 2)
        assert fake.lines() == ["Ina, I noticed the air near the floor warming fast, but I'm not sure. Is everything okay?"]
        await run(ladder, fake, 70)
        assert not ladder.incidents and fake.sirens == []

    asyncio.run(go())


def test_a_hint_plus_beeps_is_enough():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        ladder.notice(notice(fake, "gas_spike", 0.25))
        ladder.notice(notice(fake, "smoke_alarm", 0.5))
        ladder.notice(notice(fake, "alarm_sound", 0.4))
        ladder.notice(notice(fake, "smoke_seen", 0.6))
        await run(ladder, fake, 1)
        assert ladder.incidents["fire"].step == "ask"

    asyncio.run(go())


def test_quake_holds_still_and_says_drop_cover_hold():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())

        def shaking(t):
            return [notice(fake, "quake", 0.8, seconds=t + 4, strength="moderate shaking")] if t < 8 else []

        await run(ladder, fake, 3, feed=shaking)
        assert ladder.holding() == "the floor is shaking"
        assert fake.loud() == ["Earthquake! Drop, cover and hold!"]
        assert fake.felts and fake.felts[0][0] == "quake" and fake.stopped
        await run(ladder, fake, 25, feed=lambda t: shaking(t + 3))
        assert "The shaking has stopped." in fake.lines()
        assert any("moderate shaking" in line for line in fake.diary)
        assert len(fake.notified) == 1 and "shaking" in fake.notified[0][1]
        assert ladder.holding() is None
        await run(ladder, fake, 35)
        assert not ladder.incidents

    asyncio.run(go())


def test_glass_tells_a_trusted_person_who_is_here():
    async def go():
        fake = Fake(here=["Ina"])
        ladder = Ladder(fake.ports())
        ladder.notice(notice(fake, "glass", 0.6))
        await run(ladder, fake, 1)
        assert fake.lines() == ["Ina, I heard what sounded like glass breaking."]
        assert not fake.seeks

    asyncio.run(go())


def test_glass_with_nobody_here_goes_to_look():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        ladder.notice(notice(fake, "glass", 0.6))
        await run(ladder, fake, 1)
        assert fake.seeks and ladder.active
        fake.seeks[0][1]("found", "Mo")
        await run(ladder, fake, 1)
        assert fake.lines() == ["Mo, I heard what sounded like glass breaking."]
        assert not ladder.incidents

    asyncio.run(go())


def test_be_quiet_from_a_stranger_mutes_the_siren_only():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        await run(ladder, fake, ASK_S + 6, feed=beeping(fake))
        assert fake.sirens[-1] is True
        ladder.heard("sam", read_line("be quiet"), "stranger")
        await run(ladder, fake, 30, feed=beeping(fake))
        assert fake.sirens[-1] is False and ladder.incidents["fire"].step == "alarm"

    asyncio.run(go())


def test_the_tv_or_an_unseen_voice_never_ends_an_alarm():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        await run(ladder, fake, ASK_S + 6, feed=beeping(fake))
        for line in ("never mind", "don't worry", "it's fine", "false alarm"):
            ladder.heard("ina", read_line(line), "trusted", sure=False)
            ladder.heard(None, read_line(line), "stranger")
            ladder.heard("ina", read_line(line), "trusted", sure=True, addressed=False)
        ladder.heard("ina", read_line("yes"), "trusted", sure=False)
        await run(ladder, fake, 5, feed=beeping(fake))
        assert ladder.incidents["fire"].step == "alarm"
        assert "Is it really fine?" not in fake.lines()
        assert "I need to see you to stop. Come where I can see you, and tell me again." in fake.lines()

    asyncio.run(go())


def test_a_stand_down_needs_the_same_person_to_confirm_in_time():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        await run(ladder, fake, 5, feed=beeping(fake))
        ladder.heard("ina", read_line("it's fine"), "trusted", sure=True)
        ladder.heard("mo", read_line("yes"), "friend", sure=True)
        await run(ladder, fake, CONFIRM_S + 2, feed=beeping(fake))
        assert "fire" in ladder.incidents
        ladder.heard("ina", read_line("yes"), "trusted", sure=True)
        await run(ladder, fake, 1, feed=beeping(fake))
        assert "fire" in ladder.incidents

    asyncio.run(go())


def test_a_fall_is_stood_down_only_by_the_person_who_fell_or_a_trusted_person_in_view():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        ladder.notice(notice(fake, "on_floor", 0.7, track=4))
        await run(ladder, fake, 1)
        ladder.heard("mo", read_line("she's fine"), "friend", sure=True)
        ladder.heard("mo", read_line("it's fine"), "friend", sure=True)
        ladder.heard(None, read_line("I'm okay"), "stranger", track=9)
        ladder.heard("ina", read_line("it's fine"), "trusted", sure=False)
        await run(ladder, fake, 1)
        assert ladder.incidents["floor"].confirm is None
        ladder.heard("ina", read_line("it's fine"), "trusted", sure=True)
        ladder.heard("ina", read_line("yes"), "trusted", sure=True)
        await run(ladder, fake, 1)
        assert not ladder.incidents
        assert ladder.history[-1]["how"] == "stood down"

    asyncio.run(go())


def test_beeping_that_goes_on_after_a_stand_down_is_raised_again_and_no_kind_is_quiet_for_an_hour():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        await run(ladder, fake, 5, feed=beeping(fake))
        ladder.heard("ina", read_line("it was the toast"), "trusted", sure=True)
        ladder.heard("ina", read_line("yes"), "trusted", sure=True)
        await run(ladder, fake, 1, feed=beeping(fake))
        assert "fire" not in ladder.incidents
        before = len(fake.said)
        await run(ladder, fake, REGRACE_S + 10, feed=beeping(fake))
        assert "fire" in ladder.incidents and len(fake.said) > before
        mono = fake.clock.monotonic()
        assert all(until - mono <= 600.0 for until in ladder.snoozed.values())

    asyncio.run(go())


def test_a_call_for_help_is_never_quietened():
    async def go():
        fake = Fake()
        ladder = Ladder(fake.ports())
        ladder.notice(notice(fake, "help", 0.9, person="sam"))
        await run(ladder, fake, 1)
        ladder.heard("sam", read_line("I'm fine"), "stranger", sure=True)
        ladder.heard("sam", read_line("yes"), "stranger", sure=True)
        await run(ladder, fake, 1)
        assert not ladder.incidents and "help" not in ladder.snoozed
        assert ladder.notice(notice(fake, "help", 0.9, person="sam")) is not None

    asyncio.run(go())


@pytest.mark.parametrize(
    "line, help_level",
    [
        ("help!", 0.9),
        ("somebody help me", 0.9),
        ("I've fallen and I can't get up", 0.9),
        ("call an ambulance", 0.9),
        ("help us", 0.9),
        ("can you help me find my keys", 0.0),
        ("help me carry this", 0.0),
        ("I need help with my homework", 0.0),
        ("thanks for the help", 0.0),
        ("that's helpful", 0.0),
        ("help yourself to cake", 0.0),
    ],
)
def test_help_words(line, help_level):
    assert read_line(line).help == help_level


@pytest.mark.parametrize("line", ["it's fine", "It was just the toast", "false alarm", "I'm okay", "all good", "turn it off", "we're safe", "stop the alarm"])
def test_stand_down_words(line):
    reading = read_line(line)
    assert reading.stand_down and not reading.help


def test_name_and_fire_words():
    assert read_line("Pebble!").name_only
    assert read_line("hey pebble").name_only
    assert not read_line("Pebble, come here").name_only
    assert read_line("fire! fire!").fire
    assert not read_line("fire up the barbecue").fire
    assert read_line("shush").quiet
