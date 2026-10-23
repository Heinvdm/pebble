import math
import random

import pytest

from pebble.inner.fear import MAX_FEAR, NERVOUS, Fear, battery_unease
from pebble.inner.mood import Mood
from pebble.inner.needs import NeedContext, Needs
from pebble.inner.state import EFFECTS, InnerContext, InnerState

NOW = 1_792_000_000.0


def check_bounds(inner: InnerState) -> None:
    for name in ("energy", "curiosity", "social", "rest"):
        value = getattr(inner.needs, name)
        assert 0.0 <= value <= 1.0 and math.isfinite(value)
    assert -1.0 <= inner.mood.valence <= 1.0
    assert -1.0 <= inner.mood.arousal <= 1.0
    assert 0.0 <= inner.fear.level <= MAX_FEAR


def test_everything_stays_bounded_under_a_storm():
    rng = random.Random(1234)
    inner = InnerState()
    names = list(EFFECTS) + ["nonsense", ""]
    now = NOW
    for _ in range(20_000):
        if rng.random() < 0.4:
            inner.on_event(rng.choice(names), now, rng.uniform(0, 5))
        dt = rng.choice([0.0, 0.5, 1.0, 30.0, 3600.0, 1e9, -5.0, float("nan"), float("inf")])
        context = InnerContext(
            now=now,
            local_hour=rng.randrange(24),
            energy_level=rng.choice([None, -1.0, 0.0, 0.5, 2.0, float("nan")]),
            battery_percent=rng.choice([None, 0.0, 3.0, 50.0, 120.0, float("nan")]),
            awake=rng.random() < 0.8,
            resting=rng.random() < 0.3,
            night=rng.random() < 0.3,
            waking=rng.random() < 0.1,
            novelty=rng.random() < 0.2,
            comfort=rng.random() < 0.1,
            hot=rng.random() < 0.05,
        )
        inner.tick(dt, context)
        now += 1.0
        check_bounds(inner)


def test_mood_drifts_back_to_its_baseline():
    mood = Mood(valence=-1.0, arousal=1.0)
    for _ in range(360):
        mood.tick(10.0, (0.2, 0.0))
    assert mood.valence == pytest.approx(0.2, abs=0.02)
    assert mood.arousal == pytest.approx(0.0, abs=0.02)


def test_fear_rises_then_fades_within_minutes():
    fear = Fear()
    rise, _ = fear.stimulus("edge", NOW)
    assert rise == pytest.approx(4.0)
    for _ in range(600):
        fear.tick(1.0)
    assert fear.level < 0.5


def test_getting_used_to_things():
    fear = Fear()
    rises = []
    milestones = []
    now = NOW
    for _ in range(10):
        rise, used_to = fear.stimulus("loud", now)
        rises.append(rise)
        milestones.append(used_to)
        fear.tick(600.0)
        now += 600.0
    assert rises[-1] < rises[0] * 0.4
    assert rises == sorted(rises, reverse=True)
    assert milestones.count(True) == 1


def test_familiarity_fades_over_days():
    fear = Fear()
    for _ in range(5):
        fear.stimulus("bump", NOW)
    assert fear.familiarity("bump", NOW + 30 * 86400) < 0.5


def test_low_battery_unease_is_capped_at_nervous():
    fear = Fear()
    for _ in range(3600):
        fear.tick(1.0, floor=battery_unease(1.0))
    assert NERVOUS - 0.2 <= fear.level <= NERVOUS
    assert battery_unease(50.0) == 0.0
    assert battery_unease(0.0) == NERVOUS


def test_needs_rise_with_time_and_fall_when_met():
    needs = Needs(curiosity=0.2, social=0.2, rest=0.1)
    needs.tick(3600.0, NeedContext())
    needs.tick(3600.0, NeedContext())
    assert needs.curiosity == pytest.approx(0.44, abs=0.01)
    assert needs.social == pytest.approx(0.4, abs=0.01)
    needs.tick(3600.0, NeedContext(novelty=True, company=True))
    assert needs.curiosity == pytest.approx(0.44, abs=0.01)
    needs.satisfy("curiosity", 1.0)
    assert needs.curiosity == 0.0


def test_rest_rises_at_night_and_recovers_asleep():
    needs = Needs(rest=0.2)
    needs.tick(3600.0, NeedContext(night=True))
    assert needs.rest > 0.35
    needs.tick(3600.0, NeedContext(awake=False))
    assert needs.rest < 0.1


def test_energy_follows_the_battery():
    needs = Needs(energy=0.9)
    for _ in range(300):
        needs.tick(1.0, NeedContext(energy_level=0.2))
    assert needs.energy == pytest.approx(0.2, abs=0.01)
    assert needs.urgency("energy") == pytest.approx(0.8, abs=0.01)


def test_events_move_mood_and_fear():
    inner = InnerState()
    outcome = inner.on_event("edge", NOW)
    assert outcome.fear_rise > 0
    assert inner.mood.arousal > 0.3
    inner.on_event("touch", NOW)
    assert inner.fear.level < outcome.fear_rise
    before = inner.mood.valence
    inner.on_event("task_done", NOW)
    assert inner.mood.valence > before


def test_restore_from_garbage_falls_back_to_defaults():
    inner = InnerState.from_dict({"needs": {"energy": "lots", "rest": float("nan")}, "mood": {"valence": 9}, "fear": {"level": -3, "habits": {"edge": "x"}}})
    check_bounds(inner)
    assert inner.mood.valence == 1.0
    assert inner.fear.level == 0.0
    round_trip = InnerState.from_dict(inner.to_dict())
    assert round_trip.to_dict() == inner.to_dict()
