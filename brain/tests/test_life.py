import asyncio
from datetime import datetime, timezone

import pytest
from conftest import run

from pebble.clock import FakeClock, iso
from pebble.life.battery import LowBatteryRoutine
from pebble.life.loop import ExitReason
from pebble.life.quiet import QuietHours
from pebble.life.states import LifeState, Situation, next_state
from pebble.life.wakeup import wake_note
from pebble.link.protocol import Event


def situation(**overrides) -> Situation:
    values = dict(quiet=False, rest=0.4, energy=0.8, docked=False, low_battery=False, in_state_s=0.0)
    values.update(overrides)
    return Situation(**values)


def tick(rig, seconds: float = 1.0) -> None:
    rig.clock.advance(seconds)
    run(rig.life.tick(seconds))


def test_state_rules():
    assert next_state(LifeState.ACTIVE, situation(low_battery=True))[0] is LifeState.DOCKING
    assert next_state(LifeState.ACTIVE, situation(low_battery=True, docked=True))[0] is LifeState.ACTIVE
    assert next_state(LifeState.DOCKING, situation(low_battery=True, docked=True))[0] is LifeState.RESTING
    assert next_state(LifeState.WAKING, situation(in_state_s=61, waking_s=60))[0] is LifeState.ACTIVE
    assert next_state(LifeState.WAKING, situation(in_state_s=61, waking_s=60, quiet=True))[0] is LifeState.RESTING
    assert next_state(LifeState.ACTIVE, situation(quiet=True))[0] is LifeState.RESTING
    assert next_state(LifeState.RESTING, situation(quiet=True, in_state_s=400))[0] is LifeState.ASLEEP
    assert next_state(LifeState.ASLEEP, situation(quiet=True, strong_event=True))[0] is LifeState.WAKING
    assert next_state(LifeState.ASLEEP, situation(quiet=False, rest=0.2))[0] is LifeState.WAKING
    assert next_state(LifeState.ACTIVE, situation(rest=0.9))[0] is LifeState.RESTING
    assert next_state(LifeState.RESTING, situation(rest=0.2))[0] is LifeState.ACTIVE
    assert next_state(LifeState.RESTING, situation(rest=0.2, docked=True, energy=0.1))[0] is LifeState.RESTING


def test_battery_routine_has_hysteresis():
    routine = LowBatteryRoutine()
    assert routine.assess(50, False, False).low is False
    first = routine.assess(15, False, False)
    assert first.low and first.newly_low and not first.critical
    assert not routine.assess(14, False, False).newly_low
    assert routine.assess(18, False, False).low
    assert not routine.assess(21, False, False).low
    assert routine.assess(4, False, False).critical
    assert not routine.assess(4, True, False).critical
    assert routine.assess(80, None, True).newly_low


def test_quiet_hours_wrap_midnight():
    quiet = QuietHours.from_preferences({"quiet_hours": {"start": "22:00", "end": "07:00"}})
    assert quiet.contains(datetime(2026, 10, 15, 23, 30))
    assert quiet.contains(datetime(2026, 10, 16, 6, 59))
    assert not quiet.contains(datetime(2026, 10, 16, 7, 0))
    assert quiet.night_key(datetime(2026, 10, 16, 3, 0)) == "2026-10-15"
    assert quiet.night_key(datetime(2026, 10, 15, 23, 0)) == "2026-10-15"


def test_low_battery_at_15_saves_and_heads_for_the_dock(rig_factory):
    rig = rig_factory(battery_pct=14.0)
    tick(rig)
    assert rig.life.state is LifeState.DOCKING
    assert rig.life.battery.low
    assert not rig.permissions.can_move
    assert "charger" in rig.voice.lines[-1]
    assert rig.store.read("state.json")["clean_shutdown"] is False
    assert any("battery low" in e.text for e in rig.life.events.peek())
    tick(rig)
    assert len(rig.voice.lines) == 1


def test_low_battery_at_5_says_goodbye_and_shuts_down(rig_factory):
    rig = rig_factory(battery_pct=4.0)
    rig.life._stop = asyncio.Event()
    tick(rig)
    assert rig.life.exit_reason is ExitReason.SHUTDOWN
    assert rig.life._stop.is_set()
    assert "Goodbye" in rig.voice.lines[-1]
    assert any(e["kind"] == "shutdown" for e in rig.store.read_lines("diary.jsonl"))


def test_charging_phone_is_not_low(rig_factory):
    rig = rig_factory(battery_pct=4.0, charging=True)
    tick(rig)
    assert not rig.life.battery.low
    assert rig.life.exit_reason is ExitReason.DONE


def test_pack_lowbat_event_starts_the_routine(rig_factory):
    rig = rig_factory(battery_pct=90.0)
    rig.life.notice(Event("lowbat", ("3290",)))
    tick(rig)
    assert rig.life.state is LifeState.DOCKING
    assert rig.life.trigger.is_set()


def test_body_events_feed_fear_feedback_and_the_next_turn(rig_factory):
    rig = rig_factory()
    rig.life.notice(Event("edge"))
    assert rig.parts.inner.fear.level > 3
    assert rig.books.values.feedback[-1]["kind"] == "near_fall"
    assert rig.life.trigger.is_set()
    assert rig.face.current in ("surprised", "scared")
    rig.life.notice(Event("dock", ("1",)))
    assert rig.life.first_dock_at is not None
    assert any(e["kind"] == "milestone" for e in rig.store.read_lines("diary.jsonl"))


def test_wake_note_after_power_loss_and_clean_shutdown():
    local = lambda ts: datetime.fromtimestamp(ts, timezone.utc)
    saved = datetime(2026, 10, 15, 14, 2, tzinfo=timezone.utc).timestamp()
    note = wake_note({"saved_at": iso(saved), "clean_shutdown": False}, saved + 3 * 3600, local, False)
    assert note.startswith("You restarted after power loss; last saved at 14:02 on 15 Oct 2026.")
    assert "3 hours" in note
    clean = wake_note({"saved_at": iso(saved), "clean_shutdown": True}, saved + 60, local, False)
    assert clean.startswith("You woke up after a clean shutdown at 14:02")
    reset = wake_note({"saved_at": iso(saved), "clean_shutdown": False}, saved - 86400 * 400, local, False)
    assert "clock reads earlier" in reset
    assert wake_note(None, saved, local, True).startswith("This is your very first boot")


def test_restart_reads_the_last_save(rig_factory, tmp_path):
    rig = rig_factory()
    rig.life.save(clean=False)
    rig.clock.advance(7200)
    again = rig_factory()
    assert again.life.wake.startswith("You restarted after power loss")
    assert again.life.boots == 2


def test_beats_skip_when_nothing_changed(rig_factory):
    rig = rig_factory()
    rig.life._mind_ready = True
    run(rig.life.read_sensors())
    run(rig.life.beat())
    assert rig.life.turns_run == 1 and rig.life.wake is None
    run(rig.life.beat())
    assert rig.life.skips == {"you thought a moment ago": 1}
    rig.clock.advance(61)
    run(rig.life.beat())
    assert rig.life.skips["nothing changed"] == 1
    rig.life.notice(Event("obstacle", ("45",)))
    run(rig.life.beat())
    assert rig.life.turns_run == 1 and rig.life.skips["not enough to think about yet"] == 1
    rig.life.notice(Event("bump", ("L",)))
    run(rig.life.beat())
    assert rig.life.turns_run == 2
    observation = [r for r in rig.mind.requests if r["purpose"] == "turn"][-1]["messages"][-1]
    assert "Events:" in observation["content"] or observation["role"] == "tool"


def test_no_turns_while_asleep_or_without_a_mind(rig_factory):
    rig = rig_factory()
    run(rig.life.beat())
    assert rig.life.skips == {"the mind is not ready": 1}
    rig.life._mind_ready = True
    rig.life.state = LifeState.ASLEEP
    run(rig.life.beat())
    assert rig.life.skips["asleep"] == 1
    assert not [r for r in rig.mind.requests if r["purpose"] == "turn"]


def test_quiet_hours_take_away_moving_and_speaking(tmp_path):
    from conftest import Rig

    clock = FakeClock.at(datetime(2026, 10, 15, 23, 0, tzinfo=timezone.utc))
    rig = Rig(tmp_path, clock)
    try:
        rig.life._mind_ready = True
        tick(rig)
        assert rig.permissions.quiet and not rig.permissions.can_move
        assert not rig.life.initiative.allowed(clock.now(), True)
        run(rig.life.beat())
        request = [r for r in rig.mind.requests if r["purpose"] == "turn"][0]
        assert "move" not in request["tools"] and "say" not in request["tools"]
        assert "quiet hours" in request["messages"][-1]["content"]
    finally:
        rig.close()


def test_daytime_offers_moving_and_speaking(rig_factory):
    rig = rig_factory()
    rig.life._mind_ready = True
    tick(rig)
    tick(rig)
    assert rig.life.state is LifeState.ACTIVE
    run(rig.life.beat())
    request = [r for r in rig.mind.requests if r["purpose"] == "turn"][0]
    assert "do" in request["tools"] and "say" in request["tools"]
    assert {"move", "say"} <= set(rig.life.tool_names(True)) and "Not just now: moving" not in request["messages"][-1]["content"]


def test_nightly_routine_nudges_snapshots_and_compacts(rig_factory):
    rig = rig_factory()
    rig.life._mind_ready = True
    run(rig.life.beat())
    for _ in range(3):
        rig.books.values.log_feedback("fun_discovery", iso(rig.clock.now()))
    report = run(rig.life.nightly.run("2026-10-15", "newborn", rig.mind))
    assert report["nudge"]["raise"] == "curiosity"
    assert rig.books.values.value("curiosity") == 8
    assert rig.store.snapshots()
    kept = [r.text for r in rig.life.memory.recall.stream.records.values()]
    assert rig.history.turns == [] and report["folded_turns"] >= 1
    assert any("you thought" in text for text in kept) and any("curiosity grew" in text for text in kept)
    second = run(rig.life.nightly.run("2026-10-15", "newborn", rig.mind))
    assert "nudge" not in second


def test_party_days_lift_the_mood_once(tmp_path):
    from conftest import Rig

    clock = FakeClock.at(datetime(2027, 1, 25, 12, 0, tzinfo=timezone.utc))
    rig = Rig(tmp_path, clock)
    try:
        before = rig.parts.inner.mood.valence
        tick(rig)
        assert rig.parts.inner.mood.valence > before
        assert rig.life.celebrated == "2027-01-25"
        assert any("R.U.R. Day" in e.text for e in rig.life.events.peek())
    finally:
        rig.close()


def test_status_snapshot_reads_the_whole_body(rig_factory):
    rig = rig_factory(battery_pct=62.0)
    run(rig.life.read_sensors())
    snapshot = rig.life.snapshot(rig.clock.now(), rig.clock.local())
    assert snapshot.battery_pct == 62.0 and snapshot.battery_trend == "draining"
    assert snapshot.stage == "newborn" and snapshot.age_days == 0
    assert snapshot.light_lux == 150.0 and snapshot.temperature_c == 30.0
    assert snapshot.link_up is False
