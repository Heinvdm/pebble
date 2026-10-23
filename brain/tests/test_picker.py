import random

from pebble.goals import GoalBook
from pebble.inner.mood import Mood
from pebble.inner.needs import Needs
from pebble.picker import (
    OUTRANKED,
    TIER_OWN,
    PickContext,
    SafetyContext,
    idle_options,
    pick,
    safety_options,
    score,
    task_options,
)

VALUES = {"honesty": 9, "kindness": 8, "tidiness": 5, "curiosity": 7, "playfulness": 6, "caution": 5, "independence": 4}


def context(fear: float = 0.0, arousal: float = 0.2, curiosity: float = 0.6, failures: int = 0) -> PickContext:
    return PickContext(Needs(curiosity=curiosity, social=0.4, rest=0.2), Mood(0.3, arousal), fear, VALUES, failures)


def test_same_seed_same_choices():
    options = idle_options()
    first = [pick(options, context(), random.Random(42)).chosen.key for _ in range(1)]
    runs = []
    for _ in range(3):
        rng = random.Random(42)
        runs.append([pick(options, context(), rng).chosen.key for _ in range(25)])
    assert runs[0] == runs[1] == runs[2]
    assert first[0] == runs[0][0]


def test_choices_vary_but_stay_in_character():
    rng = random.Random(1)
    seen = {pick(idle_options(), context(), rng).chosen.key for _ in range(200)}
    assert len(seen) >= 2
    top = sorted(idle_options(), key=lambda o: -score(o, context())[0])[:3]
    assert seen <= {o.key for o in top}


def test_safety_comes_first_and_is_not_random():
    options = safety_options(SafetyContext(low_battery=True, quiet=True)) + idle_options()
    for seed in range(20):
        choice = pick(options, context(), random.Random(seed))
        assert choice.chosen.key == "dock"
        assert choice.tier == 0
    edge = safety_options(SafetyContext(edge_hold=True, low_battery=True))
    assert pick(edge, context(), random.Random(0)).chosen.key == "back_away"


def test_docked_robot_has_no_dock_option():
    assert [o.key for o in safety_options(SafetyContext(low_battery=True, docked=True))] == []


def test_people_tasks_come_before_own_ideas_and_owner_before_guests(clock):
    goals = GoalBook({}, clock)
    goals.add("task", "own idea", "the plant has been looked at", "curiosity", "self", 5)
    clock.advance(10)
    guest = goals.add("task", "wave at the guest", "the guest has been waved at", "", "person", 5, requested_by="Sam")
    clock.advance(10)
    owner = goals.add("task", "guard the remote", "the remote has been watched for an hour", "", "owner", 1)
    options = task_options(goals.active()) + idle_options()
    choice = pick(options, context(), random.Random(3))
    assert choice.chosen.task_id == owner.id
    assert any(o.task_id == guest.id and why != OUTRANKED for o, _, why in choice.rejected)


def test_rejected_options_are_logged_with_reasons():
    options = idle_options()
    choice = pick(options, context(), random.Random(5))
    rejected = {o.key: why for o, _, why in choice.rejected}
    assert set(rejected) == {o.key for o in options} - {choice.chosen.key}
    assert all(rejected.values())
    assert choice.as_dict()["rejected"]


def test_fear_penalises_risky_options_but_curiosity_can_still_win():
    explore = next(o for o in idle_options() if o.key == "explore")
    calm, _ = score(explore, context(fear=0.0))
    scared, parts = score(explore, context(fear=9.0))
    assert scared < calm and parts["fear"] > 0
    brave = context(fear=6.0, curiosity=1.0, arousal=0.5)
    wins = sum(pick(idle_options(), brave, random.Random(seed)).chosen.key == "explore" for seed in range(100))
    assert wins > 0


def test_failures_steer_toward_easier_options():
    hard = next(o for o in idle_options() if o.key == "explore")
    easy = next(o for o in idle_options() if o.key == "look_around")
    assert score(hard, context(failures=3))[0] < score(hard, context())[0]
    assert score(easy, context(failures=3))[0] == score(easy, context())[0]


def test_own_tasks_compete_with_idle_life(clock):
    goals = GoalBook({}, clock)
    goals.add("task", "look at the wall", "the front sensor reads under 300 mm", "curiosity", serves=("curiosity",), priority=5)
    options = task_options(goals.active())
    assert options[0].tier == TIER_OWN
    choice = pick(options + idle_options(), context(curiosity=0.9), random.Random(0))
    assert choice.tier == TIER_OWN
