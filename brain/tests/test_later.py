import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from conftest import run

from pebble.activities.commands import not_yet
from pebble.activities.gate import Asker, Situation, decide, decide_later, may_cancel, unbuilt
from pebble.clock import FakeClock
from pebble.life.agenda import IN_ALL, PER_PERSON, Agenda, kind_of, words_of
from pebble.life.conditions import choose, evaluate, watched
from pebble.life.events import Feed, Happened, match, sound_kind
from pebble.life.later import managing
from pebble.life.scene import NZ, CannedReader, LaterScene, play, who
from pebble.life.times import bare_clock, instant, nearest_hour, next_time, part_setting, settle_clock, spoken_clock
from pebble.people.trust import CHILD, FRIEND, INNER, STRANGER, TRUSTED
from pebble.selfstore import SelfStore
from pebble.sim.scene import Scene, Who
from pebble.tact import private_matter
from pebble.understand.cover import for_later
from pebble.understand.context import context_from
from pebble.understand.logic import cond_words, event_words, patrol, tidy, unsensed, whole_words
from pebble.understand.model import ModelReader, ModelReading
from pebble.understand.request import TOO_MUCH, When, from_dict, too_big
from pebble.understand.understanding import Understanding

UTC = timezone.utc
ALEX = Asker("alex", "Alex", TRUSTED, here=True)
WEDNESDAY = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)


def at(moment: datetime) -> float:
    return moment.timestamp()


def local_utc(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def local_nz(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, NZ)


def when(**data) -> When:
    return from_dict({"kind": "say_to", "who": "me", "when": data}).when


def nxt(data: dict, now: datetime, local=local_utc, parts=None, **extra) -> datetime | None:
    found = next_time(when(**data), now.timestamp(), now.timestamp(), local, parts or {}, **extra)
    return local(found[0]) if found else None


def test_times_cover_the_when_fields_and_the_parts_of_the_day():
    assert nxt({"days": ["mon"], "part": "night"}, WEDNESDAY) == datetime(2026, 10, 26, 19, 30, tzinfo=UTC)
    assert nxt({"days": ["mon"], "part": "night"}, WEDNESDAY, parts={"night": "20:00"}) == datetime(2026, 10, 26, 20, 0, tzinfo=UTC)
    assert nxt({"days": ["weekdays"], "at": "07:00"}, WEDNESDAY) == datetime(2026, 10, 22, 7, 0, tzinfo=UTC)
    assert nxt({"month_day": 1}, WEDNESDAY) == datetime(2026, 11, 1, 8, 0, tzinfo=UTC)
    assert nxt({"month_day": "last"}, datetime(2027, 2, 3, tzinfo=UTC)) == datetime(2027, 2, 28, 8, 0, tzinfo=UTC)
    assert nxt({"month_day": 31}, datetime(2026, 11, 2, tzinfo=UTC)) == datetime(2026, 11, 30, 8, 0, tzinfo=UTC)
    assert nxt({"date": "2026-10-23"}, WEDNESDAY) == datetime(2026, 10, 23, 8, 0, tzinfo=UTC)
    assert nxt({"part": "before_bed"}, WEDNESDAY) == datetime(2026, 10, 21, 21, 0, tzinfo=UTC)
    assert nxt({"at": "07:00"}, datetime(2026, 10, 21, 7, 5, tzinfo=UTC)) == datetime(2026, 10, 22, 7, 0, tzinfo=UTC)
    assert nxt({"every_s": 3600, "to": "17:00"}, WEDNESDAY) == datetime(2026, 10, 21, 16, 0, tzinfo=UTC)
    assert nxt({"every_s": 3600, "to": "17:00"}, datetime(2026, 10, 21, 17, 0, 1, tzinfo=UTC), anchor_ts=at(datetime(2026, 10, 21, 16, 0, tzinfo=UTC))) is None
    assert nxt({"every_s": 3600, "from": "22:00", "to": "06:00"}, WEDNESDAY) == datetime(2026, 10, 21, 22, 0, tzinfo=UTC)
    assert nxt({"every_s": 3600, "from": "22:00", "to": "06:00"}, datetime(2026, 10, 22, 5, 30, tzinfo=UTC)) == datetime(2026, 10, 22, 6, 0, tzinfo=UTC)
    assert nxt({"days": ["mon"], "at": "19:00", "until_date": "2026-10-30"}, datetime(2026, 10, 27, tzinfo=UTC)) is None
    assert nxt({"part": "tonight"}, datetime(2026, 10, 21, 21, 0, tzinfo=UTC)) == datetime(2026, 10, 21, 21, 30, tzinfo=UTC)


def test_every_other_week_counts_from_the_first_one():
    agenda_when = when(days=["fri"], every_weeks=2)
    first = date(2026, 10, 23)
    found = [next_time(agenda_when, at(WEDNESDAY + timedelta(days=7 * n)), at(WEDNESDAY), local_utc, {}, first) for n in range(4)]
    days = [local_utc(f[0]).date() for f in found]
    assert days == [date(2026, 10, 23), date(2026, 11, 6), date(2026, 11, 6), date(2026, 11, 20)]


def test_ambiguous_clock_times_take_the_next_one_and_a_time_just_gone_means_tomorrow():
    assert nearest_hour("07:00", datetime(2026, 10, 21, 15, 0)) == "19:00"
    assert nearest_hour("19:00", datetime(2026, 10, 21, 21, 0)) == "07:00"
    assert nearest_hour("07:00", datetime(2026, 10, 21, 19, 5)) == "07:00"
    assert bare_clock("remind me at 7 to call mo") and bare_clock("wake me at seven")
    assert not bare_clock("remind me at 7pm") and not bare_clock("at 7 in the morning remind me") and not bare_clock("at 19:00 please")
    assert settle_clock(When(at="07:00"), "remind me at seven to call Mo", datetime(2026, 10, 21, 15, 0)).at == "19:00"
    assert settle_clock(When(at="07:00"), "remind me at 7am", datetime(2026, 10, 21, 15, 0)).at == "07:00"
    assert settle_clock(When(at="19:00", days=("mon",)), "every monday at seven", datetime(2026, 10, 21, 15, 0)).at == "19:00"


def test_spoken_times_and_parts_of_the_day_set_by_voice():
    assert spoken_clock("eight", "19:30") == "20:00" and spoken_clock("eight", "07:30") == "08:00"
    assert spoken_clock("half past seven") == "07:30" and spoken_clock("quarter to nine", "20:00") == "20:45"
    assert spoken_clock("9pm") == "21:00" and spoken_clock("noon") == "12:00" and spoken_clock("the big one") == ""
    assert part_setting("night means eight for me") == ("night", "20:00", False)
    assert part_setting("in this house, morning means 7") == ("morning", "07:00", True)
    assert part_setting("tell me a story") is None


def test_daylight_saving_gap_fires_at_three_and_the_repeated_hour_fires_once():
    gap_night = datetime(2026, 9, 26, 22, 0, tzinfo=NZ)
    assert local_nz(instant(datetime(2026, 9, 27, 2, 30), local_nz)) == datetime(2026, 9, 27, 3, 0, tzinfo=NZ)
    assert nxt({"at": "02:30"}, gap_night, local_nz).strftime("%d %H:%M") == "27 03:00"
    fold = datetime(2026, 4, 4, 22, 0, tzinfo=NZ)
    daily = when(at="02:30", days=["weekdays", "weekends"])
    first = next_time(daily, at(fold), at(fold), local_nz, {})
    assert local_nz(first[0]).strftime("%d %H:%M") == "05 02:30" and first[1] == "2026-04-05T02:30"
    again = next_time(daily, first[0], at(fold), local_nz, {}, last_key=first[1])
    assert local_nz(again[0]).strftime("%d %H:%M") == "06 02:30"
    assert again[0] - first[0] == 25 * 3600


def test_the_read_back_says_the_whole_tree_in_plain_words():
    branch = from_dict({"kind": "if", "on": {"event": "arrives", "who": "sam"}, "if": {"state": "after", "at": "20:00"}, "then": [{"kind": "say_to", "who": "me", "text": "send sam to bed"}], "else": [{"kind": "say_to", "who": "me", "text": "tell sam dinner's in the oven"}]})
    said = whole_words(branch.with_(on=None), event_words(branch.on), ("sam",))
    assert said == "When Sam gets home, if it's after 8 in the evening, I'll remind you to send Sam to bed; if not, I'll remind you to tell Sam dinner's in the oven"
    unless = from_dict({"kind": "if", "if": {"not": {"state": "day_is", "day": "tomorrow_holiday"}}, "then": [{"kind": "say_to", "who": "me", "text": "it's bin day"}]})
    assert whole_words(unless, "every Monday at 7:30 in the evening") == "Every Monday at 7:30 in the evening, unless tomorrow's a public holiday, I'll remind you that it's bin day"
    first = from_dict({"kind": "say_to", "who": "me", "on": {"first_of": [{"event": "at", "at": "19:00"}, {"event": "arrives", "who": "ina"}]}})
    assert event_words(first.on) == "at 7 in the evening or when Ina gets home, whichever comes first"
    assert "my guess" in event_words(from_dict({"kind": "say_to", "who": "me", "on": {"event": "leaves", "who": "ina"}}).on)
    assert cond_words(from_dict({"kind": "if", "if": {"all": [{"state": "present", "who": "ina"}, {"state": "after", "at": "18:00"}]}, "then": [{"kind": "wait"}]}).if_) == "Ina is home and it's after 6 in the evening"
    assert cond_words(from_dict({"kind": "if", "if": {"not": {"state": "in_room", "place": "lounge"}}, "then": [{"kind": "wait"}]}).if_) == "nobody is in the lounge"


def test_plain_code_tidies_the_slips_e4b_made_with_later_requests():
    noisy = tidy(from_dict({"kind": "say_to", "who": "me", "text": "Tuesday is bin day", "when": {"part": "night", "days": ["mon"], "every_s": 60}}))
    assert noisy.when.every_s == 0 and noisy.when.part == "night" and noisy.when.days == ("mon",)
    assert tidy(from_dict({"kind": "say_to", "who": "me", "text": "remind me", "when": {"at": "19:00"}})).text == ""
    assert tidy(from_dict({"kind": "say_to", "who": "me", "text": "remind me to call mum", "when": {"at": "19:00"}})).text == "call mum"
    nobody = tidy(from_dict({"kind": "if", "if": {"state": "present", "who": "nobody", "place": "kitchen"}, "then": [{"kind": "wait"}]})).if_
    assert cond_words(nobody) == "nobody is in the kitchen"
    negated = tidy(from_dict({"kind": "if", "if": {"state": "present", "place": "kitchen", "is": "no"}, "then": [{"kind": "wait"}]})).if_
    assert cond_words(negated) == "nobody is in the kitchen"
    assert patrol(from_dict({"kind": "check", "place": "house", "text": "have a look round the house"}))
    assert not patrol(from_dict({"kind": "check", "place": "study", "text": "is the window open"}))
    seen = from_dict({"kind": "say_to", "who": "me", "on": {"event": "seen", "who": "ina"}}).on
    assert event_words(seen) == "when I see Ina" and match(seen, Happened("arrives", 1.0, "p1"), {"ina": "p1"})
    ctx = context_from({"speaker": "ina", "present": ["ina"], "names": ["ina", "mo"]})
    reader = Understanding(ModelReader([("conscious", CannedReader({}))]))
    for_mo = reader.from_model(ModelReading(from_dict({"kind": "say_to", "who": "mo", "text": "call", "when": {"at": "19:00"}}), "conscious", 0.1), ctx, "Remind me at 7 to call Mo.")
    assert for_mo.request.who == "me" and for_mo.request.text == "call mo"
    told = reader.from_model(ModelReading(from_dict({"kind": "say_to", "who": "mo", "text": "dinner's ready", "on": {"event": "arrives", "who": "mo"}}), "conscious", 0.1), ctx, "When Mo gets home tell him dinner's ready.")
    assert told.request.who == "mo"
    listed = reader.from_model(ModelReading(from_dict({"kind": "list_later"}), "conscious", 0.1), ctx, "Remind me at seven or when Ina gets home, whichever comes first.")
    assert listed.request.kind == "other"


def test_the_tree_has_limits_and_what_pebble_cannot_sense_is_said_honestly():
    deep = {"kind": "come", "then": [{"kind": "if", "if": {"state": "cooking"}, "then": [{"kind": "wait"}] * 6, "else": [{"kind": "turn"}] * 6}]}
    with pytest.raises(Exception):
        from_dict(deep)
    assert TOO_MUCH.startswith("That's a bit much")
    assert not too_big(from_dict({"kind": "if", "if": {"state": "cooking"}, "then": [{"kind": "wait"}]}))
    assert unsensed(from_dict({"kind": "if", "if": {"state": "cannot_tell"}, "then": [{"kind": "say_to", "who": "me"}]})) == "I can't tell that."
    assert unsensed(from_dict({"kind": "say_to", "who": "me", "on": {"event": "cannot_tell"}})) == "I can't tell when that happens."


def test_conditions_have_three_values_and_unsure_never_moves_pebble():
    present = {("present", "ina"): True, ("present", "mo"): None, ("after", ""): False}

    def read(cond):
        return present[(cond.state, cond.who)]

    both = from_dict({"kind": "if", "if": {"all": [{"state": "present", "who": "ina"}, {"state": "present", "who": "mo"}]}, "then": [{"kind": "go_to_place", "place": "kitchen"}]})
    assert evaluate(both.if_, read) is None
    either = from_dict({"kind": "if", "if": {"any": [{"state": "present", "who": "ina"}, {"state": "present", "who": "mo"}]}, "then": [{"kind": "wait"}]})
    assert evaluate(either.if_, read) is True
    nope = from_dict({"kind": "if", "if": {"all": [{"state": "after", "at": "20:00"}, {"state": "present", "who": "mo"}]}, "then": [{"kind": "wait"}]})
    assert evaluate(nope.if_, read) is False
    moving = choose(both, read)
    assert moving.steps == () and moving.held and moving.couldnt() == "I couldn't tell whether Mo is home"
    spoken = choose(from_dict({"kind": "if", "if": {"not": {"state": "present", "who": "mo"}}, "then": [{"kind": "say_to", "who": "me", "text": "call mo"}]}), read)
    assert spoken.both and spoken.steps and spoken.value is None


def test_conditions_about_another_grown_ups_comings_and_goings_need_trust():
    people = {"ina": type("P", (), {"id": "ina", "is_child": False})(), "sam": type("P", (), {"id": "sam", "is_child": True})()}
    request = from_dict({"kind": "if", "when": {"at": "18:00"}, "if": {"not": {"state": "present", "who": "ina"}}, "then": [{"kind": "say_to", "who": "me"}]})
    seen = watched(request, "alex", people.get)
    assert [p.id for p in seen.names] == ["ina"]
    friend = Asker("rua", "Rua", FRIEND)
    assert not decide_later(request, friend, adults=True).yes and decide_later(request, ALEX, adults=True).yes
    family = Asker("mo", "Mo", FRIEND, family=True)
    assert decide_later(request, family, children=True).yes and not decide_later(request, friend, children=True).yes
    assert not decide_later(request, Asker(None, "someone", STRANGER)).yes
    assert decide_later(request, Asker("sam", "Sam", CHILD)).yes


def test_the_gate_keeps_unbuilt_parts_honest_and_only_the_right_people_may_cancel():
    message = from_dict({"kind": "say_to", "who": "sam", "text": "come here", "when": {"in_s": 60}})
    assert unbuilt(message) == [] and not_yet(message, True) == ("", [])
    new = from_dict({"kind": "adjust", "change": "higher", "when": {"in_s": 60}})
    assert unbuilt(new) == ["change"] and not_yet(new, True)[0] == "I can't change it that way yet."
    reminder = from_dict({"kind": "say_to", "who": "me", "when": {"in_s": 60}})
    assert unbuilt(reminder) == [] and not_yet(reminder, True) == ("", [])
    assert not_yet(reminder)[0] == "I can't do things at a set time yet, only now."
    assert unbuilt(from_dict({"kind": "check", "place": "house", "when": {"every_s": 3600}})) == []
    assert unbuilt(from_dict({"kind": "check", "thing": "door"})) == [] and unbuilt(from_dict({"kind": "watch", "thing": "baby"})) == []
    assert unbuilt(from_dict({"kind": "set_rule", "rule": "quiet", "while": {"state": "cooking"}})) == []
    timed = from_dict({"kind": "come", "when": {"in_s": 600}})
    assert decide(timed, ALEX, Situation()).answer == "no"
    assert decide(timed, ALEX, Situation(later=True)).answer == "yes"
    assert decide(timed, Asker(None, "someone", STRANGER), Situation(later=True)).answer == "no"
    item = type("I", (), {"by": "alex", "aimed": "alex", "about": ["ina"]})()
    assert may_cancel(item, ALEX) and may_cancel(item, Asker("ina", "Ina", FRIEND)) and not may_cancel(item, Asker("mo", "Mo", TRUSTED))
    assert may_cancel(item, Asker("o", "Owner", INNER, owner=True))


def test_the_event_feed_counts_an_arrival_only_after_ten_minutes_away_and_guesses_leaving():
    feed = Feed(0.0)
    assert feed.people(5.0, [("ina", "Ina", 5.0)]) == []
    assert feed.people(300.0, [("ina", "Ina", 300.0)]) == []
    out = feed.people(1000.0, [("ina", "Ina", 300.0)])
    assert [h.event for h in out] == ["leaves"] and out[0].guess
    assert [h.event for h in feed.people(1001.0, [("ina", "Ina", 1001.0)])] == ["arrives"]
    assert feed.people(1300.0, [("ina", "Ina", 1300.0)]) == []
    assert feed.people(1500.0, [("ina", "Ina", 1500.0)]) == []
    late = Feed(0.0)
    assert [h.event for h in late.people(900.0, [("mo", "Mo", 900.0)])] == ["arrives"]
    assert [h.thing for h in feed.seen(10.0, ["cat"])] == ["cat"] and feed.seen(20.0, ["cat"]) == []
    assert feed.sound(30.0, "Door bell").thing == "doorbell" and sound_kind("knocking") == "knock"
    assert feed.heard("doorbell", 0.0) and not feed.heard("kettle", 0.0)
    trigger = from_dict({"kind": "say_to", "who": "me", "on": {"first_of": [{"event": "arrives", "who": "ina"}, {"event": "sound", "thing": "doorbell"}]}}).on
    assert match(trigger, Happened("sound", 1.0, thing="doorbell"), {})
    assert match(trigger, Happened("arrives", 1.0, "p1"), {"ina": "p1"}) and not match(trigger, Happened("arrives", 1.0, "p2"), {"ina": "p1"})


def test_the_agenda_survives_a_restart_and_keeps_its_limits(tmp_path):
    clock = FakeClock.at(WEDNESDAY)
    store = SelfStore.open(tmp_path / "self", clock)
    agenda = Agenda(store, clock)
    request = from_dict({"kind": "say_to", "who": "me", "text": "tuesday is bin day", "when": {"days": ["mon"], "part": "night"}})
    item = agenda.new(request, "alex", "Alex", TRUSTED, kind_of(request), "alex", [], False, words_of(request))
    assert agenda.plan(item, clock.now()) == ""
    agenda.add(item)
    agenda.save(force=True)
    again = Agenda(store, clock)
    assert len(again.waiting()) == 1 and again.waiting()[0].req() == request
    assert local_utc(again.waiting()[0].next_at) == datetime(2026, 10, 26, 19, 30, tzinfo=UTC)
    far = from_dict({"kind": "say_to", "who": "me", "when": {"date": "2026-12-25"}})
    assert "30 days" in again.plan(again.new(far, "alex", "Alex", TRUSTED, "reminder", "alex", [], False, ""), clock.now())
    for n in range(PER_PERSON - 1):
        again.add(again.new(from_dict({"kind": "say_to", "who": "me", "text": f"thing {n}", "when": {"in_s": 600}}), "alex", "Alex", TRUSTED, "reminder", "alex", [], False, f"thing {n}"))
    assert "20 things" in again.full("alex") and again.full("sam") == ""
    for n in range(IN_ALL - PER_PERSON):
        again.add(again.new(from_dict({"kind": "say_to", "who": "me", "when": {"in_s": 600}}), f"p{n}", "P", TRUSTED, "reminder", f"p{n}", [], False, ""))
    assert "100 things" in again.full("sam")
    gone = again.forget("alex", ["Alex"])
    assert len(gone) == PER_PERSON and not again.mine("alex")


def test_a_trigger_runs_out_after_a_day_unless_asked_for_longer_and_never_past_a_week(tmp_path):
    clock = FakeClock.at(WEDNESDAY)
    agenda = Agenda(SelfStore.open(tmp_path / "self", clock), clock)
    day = agenda.new(from_dict({"kind": "say_to", "who": "me", "on": {"event": "arrives", "who": "ina"}}), "alex", "Alex", TRUSTED, "reminder", "alex", [], False, "")
    assert agenda.plan(day, clock.now()) == "" and day.runs_out - clock.now() == 86400.0
    week = agenda.new(from_dict({"kind": "say_to", "who": "me", "on": {"event": "arrives", "who": "ina"}, "when": {"until_date": "2026-10-24"}}), "alex", "Alex", TRUSTED, "reminder", "alex", [], False, "")
    assert agenda.plan(week, clock.now()) == "" and round((week.runs_out - clock.now()) / 3600) == 81
    long = agenda.new(from_dict({"kind": "say_to", "who": "me", "on": {"event": "arrives", "who": "ina"}, "when": {"until_date": "2026-11-20"}}), "alex", "Alex", TRUSTED, "reminder", "alex", [], False, "")
    agenda.plan(long, clock.now())
    assert long.runs_out - clock.now() <= 7 * 86400.0


def test_items_are_matched_by_their_words_and_their_time():
    clock = FakeClock.at(WEDNESDAY)
    agenda = Agenda(type("S", (), {"read": lambda self, name, default=None: default, "write": lambda self, name, data: None})(), clock)
    made = []
    for data in ({"kind": "say_to", "who": "me", "text": "tuesday is bin day", "when": {"days": ["mon"], "part": "night"}}, {"kind": "say_to", "who": "me", "text": "take the washing out", "when": {"at": "19:00"}}):
        request = from_dict(data)
        item = agenda.new(request, "alex", "Alex", TRUSTED, kind_of(request), "alex", [], False, words_of(request))
        agenda.plan(item, clock.now())
        agenda.add(item)
        made.append(item)
    assert agenda.match("bin", agenda.waiting()) == [made[0]]
    assert agenda.match("bins", agenda.waiting()) == [made[0]]
    assert agenda.match("the seven o'clock one", agenda.waiting()) == [made[1]]
    assert agenda.match("washing", agenda.waiting()) == [made[1]]
    assert agenda.match("the dentist", agenda.waiting()) == []
    same, other = agenda.same(agenda.new(made[0].req(), "alex", "Alex", TRUSTED, "reminder", "alex", [], False, made[0].words))
    assert same is made[0] and other is None


def test_plain_words_manage_the_agenda():
    assert managing("what reminders do i have").kind == "list_later"
    assert managing("stop all my reminders").scope == "all"
    skip = managing("no bin reminder this week")
    assert skip.kind == "cancel_later" and skip.scope == "next" and skip.text == "bin"
    assert managing("cancel the washing reminder").text == "washing"
    assert managing("cancel my reminder").kind == "cancel_later" and managing("cancel my reminder").text == ""
    changed = managing("change the bin reminder to tuesdays")
    assert changed.kind == "change_later" and changed.when.days == ("tue",)
    assert managing("i'm going to the shop later") is None


def test_private_matters_are_spotted_by_the_tact_checks():
    assert private_matter("take my tablets") and private_matter("pay the rent") and private_matter("dentist at three")
    assert not private_matter("tuesday is bin day") and not private_matter("feed the cat")


def test_rules_first_hands_lines_for_later_to_the_model_but_not_plain_talk():
    assert for_later("Remind me in ten minutes to take the washing out.") and for_later("When Ina gets home, remind me to call Mo.")
    assert for_later("At five, come to the lounge.") and for_later("Wake me up at half past six.")
    assert not for_later("I'm going to the shop tomorrow") and not for_later("The man on the radio said every Monday is bin day.")
    assert not for_later("We're having fish tonight")


def scene(name: str, tmp_path):
    return asyncio.run(play(name, tmp_path / "self"))


def test_scene_bin_day_with_a_correction_a_holiday_an_absence_and_a_skip(tmp_path):
    show, out = scene("bin", tmp_path)
    said = out["said"]
    assert said[0] == "Okay: every Monday at 7:30 in the evening, I'll remind you that Tuesday is bin day. The first one is this Monday."
    assert said[1] == "Okay, now: every Monday at 8 in the evening, I'll remind you that Tuesday is bin day. The first one is this Monday."
    assert out["at"] == "Mon 27 20:00"
    reminder = "Ina, you asked me to remind you: Tuesday is bin day. Tuesday's a public holiday, so check the bins are still being collected."
    assert reminder not in said[: out["while_out"]] and reminder in said
    assert "Okay, I'll skip that one this time. The next one is on Monday 10 January at 8 in the evening." in said
    assert out["next"] == "Mon 10 Jan 20:00"
    assert not any("bin day" in line for line in out["skipped_week"])


def test_scene_a_reminder_in_ten_minutes(tmp_path):
    show, out = scene("ten", tmp_path)
    assert "Okay: in 10 minutes, I'll remind you to take the washing out." in out["before"]
    assert "Ina, you asked me to remind you: take the washing out." not in out["before"]
    assert "Ina, you asked me to remind you: take the washing out." in out["said"]


def test_scene_a_wake_up_in_quiet_hours_gentle_then_louder_and_stops_on_im_up(tmp_path):
    show, out = scene("wake", tmp_path)
    assert out["quiet"]
    tries = [line for line in out["tries"] if "wake up" in line.lower() or "get up" in line.lower()]
    assert tries[0].startswith("Ina, it's 6:30") and tries[0].endswith("Time to wake up.")
    assert len(tries) >= 4 and tries[3].startswith("Ina! It's") and tries[3].endswith("Time to get up!")
    assert out["said"][-1] == "Good morning!"


def test_scene_patrol_every_hour_skips_the_private_room(tmp_path):
    show, out = scene("patrol", tmp_path)
    assert out["said"][0].startswith("Okay: every hour from 7 in the evening until 8 in the evening, I'll have a look round the house. The first one is today.")
    assert len(out["rounds"]) == 2 and all("you had a look round the" in text and "skipped the bathroom" in text for text in out["rounds"])
    assert out["left"] == 0


def test_scene_a_self_reminder_on_a_trigger(tmp_path):
    show, out = scene("trigger", tmp_path)
    assert "Okay: when Ina gets home, I'll remind you to call the plumber. I'll watch for that until this time tomorrow." in out["before"]
    assert not any("remind you: call the plumber" in line for line in out["before"])
    assert "Mo, you asked me to remind you: call the plumber." in out["said"]


def test_scene_two_items_due_together_become_one_turn(tmp_path):
    show, out = scene("two", tmp_path)
    assert "Two things, Ina: feed the cat, and Tuesday is bin day." in out["said"]


def test_scene_a_reminder_while_following_someone(tmp_path):
    show, out = scene("follow", tmp_path)
    assert "Ina, you asked me to remind you: turn the oven off." in out["said"] and out["following"]


def test_scene_logic_with_unsure_states(tmp_path):
    show, out = scene("logic", tmp_path)
    now = out["now"]
    assert now[:3] == ["Okay, I'll go and check the door.", "I couldn't get a good look, so I couldn't tell whether the door is open.", "Someone is in the lounge, so I won't have a look round the house."]
    assert "I couldn't tell whether someone is in the kitchen, so I didn't go to the kitchen." in now
    assert now[-2:] == ["I couldn't get a good look, so I couldn't tell whether the back door is open.", "So I didn't do either."]
    assert out["following"] == "follow" and out["after_cat"] != "follow"
    assert "There's the cat, so I'll stop." in out["said"]
    assert "Okay: at 6 tonight, unless Ina is home, I'll remind you to call Ina." in out["said"]
    assert "Mo, you asked me to remind you: call Ina." in out["at_six"]
    assert out["said"].count("Mo, you asked me to remind you: ring the plumber.") == 1


def test_scene_arrivals_that_keep_flapping_fire_once(tmp_path):
    show, out = scene("flapping", tmp_path)
    assert out["said"].count("Ina, you asked me to remind you: ask Mo about school.") == 1


def test_scene_a_trigger_that_runs_out_is_told(tmp_path):
    show, out = scene("runs_out", tmp_path)
    assert out["left"] == 0
    assert "Ina, Sam didn't come home while I was watching, so I didn't remind you to ask Sam about the bus." in out["said"]


def test_scene_a_stranger_cannot_leave_a_timed_order(tmp_path):
    show, out = scene("stranger", tmp_path)
    assert out["said"] == ["Sorry, I only keep things for later for people I know."] and out["kept"] == 0


def test_scene_a_trust_drop_before_an_item_fires_drops_it(tmp_path):
    show, out = scene("trust_drop", tmp_path)
    assert out["kept"] == 1 and out["left"] == 0
    assert [r["kind"] for r in out["records"]] == ["later_dropped"]


def test_scene_a_daylight_saving_night(tmp_path):
    show, out = scene("dst", tmp_path)
    assert out["said"][0].startswith("Okay: tomorrow at 3 at night, I'll remind you to check the oven. The clocks go forward that night, so 2:30 doesn't happen; it'll be at 3.")
    assert out["fired"] == ["03:00"] and out["said"].count("Ina, you asked me to remind you: check the oven.") == 1


def test_scene_a_clock_jump_never_fires_twice(tmp_path):
    show, out = scene("jump", tmp_path)
    assert out["first"] == 1 and out["told"] == 1 and out["jumps"] == 2


def test_scene_watching_someone_needs_trust_and_is_never_hidden(tmp_path):
    show, out = scene("watching", tmp_path)
    assert out["by_friend"] == 0 and out["by_trusted"] == 1 and out["left"] == 0
    said = out["said"]
    assert "I only keep an eye on someone's comings and goings for people I know really well." in said
    assert any(line.startswith("Mo has one that depends on whether you're around") for line in said)
    assert "Okay, I've cancelled it." in said
    assert any(line.startswith("Mo, Ina cancelled the one") for line in said)


def test_scene_a_private_reminder_with_a_guest_waits_for_go_on(tmp_path):
    show, out = scene("private", tmp_path)
    assert out["offered"][-1] == "Ina, I've got a reminder for you."
    assert out["said"][-1] == "Ina, you asked me to remind you: take your tablets."


def test_scene_until_they_have_had_enough_checks_in_and_stops_on_a_no(tmp_path):
    show, out = scene("checking_in", tmp_path)
    assert "Still having fun, Ina?" in out["asked"] and out["doing"] is None


def test_scene_a_while_ends_the_activity_when_it_stops_being_true(tmp_path):
    show, out = scene("while", tmp_path)
    assert out["waiting"] == "wait" and out["doing"] is None
    assert "Okay, it's after 3:05 in the afternoon now, so I'll stop." in out["said"]


def test_scene_a_missed_reminder_is_told_honestly_after_a_restart(tmp_path):
    show, out = scene("restart", tmp_path)
    assert "Ina, I was meant to remind you at 7 to put the bins out; I was switched off then." in out["said"] and out["left"] == 0


def test_scene_a_moving_item_waits_for_a_live_request_then_is_skipped_and_told(tmp_path):
    show, out = scene("ladder", tmp_path)
    assert out["doing"] == "wait" and out["left"] == 0
    assert "Ina, I couldn't go to the lounge at 5; I was helping Mo." in out["said"]


def test_scene_pebble_asks_instead_of_guessing_which_one_and_whether_to_keep_both(tmp_path):
    show, out = scene("asking", tmp_path)
    said = out["said"]
    assert "You've already got that one, at 8 tonight. Do you want it at 9 tonight instead, or both?" in said
    assert out["both"] == 2
    assert any(line.startswith("Which one: ") and "take the washing out in 10 minutes" in line for line in said)
    assert out["left"] == ["feed the cat", "feed the cat"]
    assert said[-1] == "I'll leave it, then." and out["after"] == 2


def test_the_minds_do_takes_a_reminder_for_the_person_who_asked_end_to_end(tmp_path):
    readings = {"remind alex at 7 to call mo": {"kind": "say_to", "who": "alex", "text": "call mo", "when": {"at": "07:00"}}}

    async def scenario():
        reader = Understanding(ModelReader([("conscious", CannedReader(readings))]))
        stage = Scene(tmp_path / "self", people=[Who("Alex", TRUSTED, 1300.0, 0.0)], at=WEDNESDAY, understanding=reader)
        await stage.setup()
        registry = stage.life.p.turns.registry
        await stage.say("Alex", "can you remind me at 7 to call Mo")
        stage.life.company.asking = stage.life._asking(stage.clock.now())
        named = await registry.call("do", {"words": "remind Alex at 7 to call Mo", "for": "Alex"})
        unnamed = await registry.call("do", {"words": "remind Alex at 7 to call Mo"})
        await stage.run(2.0)
        items = stage.life.later.agenda.waiting()
        matched = stage.life.later.matched()
        await stage.close()
        return named, unnamed, items, matched, stage

    named, unnamed, items, matched, stage = run(scenario(), timeout=120)
    assert named["ok"] and named["you_said"] == "Okay: at 7 tonight, I'll remind you to call mo."
    assert unnamed["ok"] and unnamed["you_said"] == "You already have that one: at 7 tonight."
    assert len(items) == 1 and items[0].by_label == "Alex" and local_utc(items[0].next_at).hour == 19
    assert matched == ""


def test_items_due_within_the_hour_reach_the_matched_section_three_at_most(tmp_path):
    readings = {f"remind me in {n} minutes to do thing {n}": {"kind": "say_to", "who": "me", "text": f"do thing {n}", "when": {"in_s": 60 * n}} for n in (10, 20, 30, 40, 90)}

    async def scenario():
        reader = Understanding(ModelReader([("conscious", CannedReader(readings))]))
        stage = LaterScene(tmp_path / "self", [who("Ina", TRUSTED)], WEDNESDAY, {})
        stage.scene.understanding = reader
        await stage.setup()
        for n in (10, 20, 30, 40, 90):
            await stage.scene.say("Ina", f"remind me in {n} minutes to do thing {n}")
            await stage.scene.run(40.0)
        matched = stage.later.matched()
        turns = stage.life.p.turns
        _, messages, _ = turns._reply_messages("Ina said hello", "adult", "", "", None, None)
        await stage.close()
        return matched, messages

    matched, messages = run(scenario(), timeout=180)
    assert matched.startswith("Due within the hour: ") and matched.count("for Ina") == 3 and "thing 40" not in matched and "thing 90" not in matched
    assert any(matched in (message.get("content") or "") for message in messages)
