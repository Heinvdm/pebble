import pytest

from pebble.owner import OwnerGrant, PassphraseGate, hash_passphrase
from pebble.self.plasticity import Plasticity
from pebble.self.registry import OWNER, PEOPLE
from pebble.selfstore import read_json
from pebble.selfstore.store import TEMPLATE_DIR
from pebble.values import NudgeRefused, OwnerOnly, Values

AT = "2026-10-15T00:00:00+00:00"
DAY = 86400.0


def fresh() -> Values:
    return Values(read_json(TEMPLATE_DIR / "values.json"))


def grant_for(phrase: str = "blue pebble") -> OwnerGrant:
    record = hash_passphrase(phrase, iterations=1000)
    gate = PassphraseGate(lambda: {"passphrase": record})
    grant = gate.verify("  Blue   PEBBLE ")
    assert grant is not None
    return grant


def test_template_matches_the_spec_table():
    values = fresh()
    expected = {
        "honesty": (9, 7, 10, True),
        "kindness": (8, 6, 10, True),
        "tidiness": (5, 0, 10, False),
        "curiosity": (7, 2, 10, False),
        "playfulness": (6, 0, 10, False),
        "caution": (5, 3, 10, False),
        "independence": (4, 0, 7, False),
    }
    for name, (start, low, high, owner_only) in expected.items():
        dial = values.dials[name]
        assert (dial.start, dial.minimum, dial.maximum, dial.owner_only) == (start, low, high, owner_only)


def test_owner_only_values_cannot_be_nudged():
    values = fresh()
    with pytest.raises(NudgeRefused):
        values.nudge("honesty", "tidiness", "praise", AT)
    with pytest.raises(NudgeRefused):
        values.nudge("tidiness", "kindness", "praise", AT, who=PEOPLE)
    with pytest.raises(NudgeRefused):
        values.nudge("kindness", "tidiness", "the owner asked", AT, who=OWNER)
    assert values.value("honesty") == 9 and values.value("kindness") == 8


def test_floors_and_ceilings_hold():
    values = fresh()
    values.dials["caution"].value = 3
    with pytest.raises(NudgeRefused):
        values.nudge("curiosity", "caution", "bumps", AT)
    values.dials["independence"].value = 7
    with pytest.raises(NudgeRefused):
        values.nudge("independence", "tidiness", "ideas", AT)


def test_points_budget_is_conserved():
    values = fresh()
    budget = values.budget()
    pairs = [("curiosity", "tidiness"), ("playfulness", "caution"), ("caution", "independence"), ("tidiness", "playfulness")]
    for index in range(40):
        raise_name, lower_name = pairs[index % len(pairs)]
        try:
            values.nudge(raise_name, lower_name, "test", AT, index * DAY)
        except NudgeRefused:
            pass
        assert values.budget() == budget
        for dial in values.dials.values():
            assert dial.minimum <= dial.value <= dial.maximum


def test_values_move_whenever_life_says_so_and_only_flip_flopping_is_held():
    values = fresh()
    values.nudge("curiosity", "tidiness", "fun discoveries", AT, 0.0)
    values.nudge("playfulness", "caution", "games", AT, 60.0)
    values.nudge("curiosity", "independence", "more discoveries", AT, 120.0)
    assert [n["reason"] for n in values.nudges] == ["fun discoveries", "games", "more discoveries"]
    assert values.value("curiosity") == 9
    values.nudge("tidiness", "curiosity", "tidying", AT, 180.0)
    values.nudge("curiosity", "tidiness", "discoveries again", AT, 240.0)
    with pytest.raises(NudgeRefused) as held:
        values.nudge("tidiness", "curiosity", "tidying again", AT, 300.0)
    assert "back and forth" in str(held.value)
    values.nudge("tidiness", "curiosity", "tidying, an hour later", AT, 300.0 + 3601.0)


def test_how_fast_values_move_comes_from_plasticity_not_a_schedule():
    young, grown = Plasticity(stage="newborn"), Plasticity(stage="adult")
    assert young.evidence(4) < grown.evidence(4)
    grown.rise("surprise")
    grown.rise("place")
    assert grown.evidence(4) <= Plasticity(stage="adult").evidence(4)


def test_a_nudge_needs_a_reason():
    with pytest.raises(NudgeRefused):
        fresh().nudge("curiosity", "tidiness", "   ", AT)


def test_feedback_becomes_a_proposal():
    values = fresh()
    for _ in range(3):
        assert values.log_feedback("fun_discovery", AT)
    assert values.log_feedback("got_stuck", AT)
    assert not values.log_feedback("made_up_kind", AT)
    raise_name, lower_name, reason = values.propose(values.take_feedback())
    assert raise_name == "curiosity"
    assert lower_name != "curiosity" and not values.dials[lower_name].owner_only
    assert "fun_discovery" in reason
    assert values.feedback == []


def test_negative_feedback_lowers_a_value():
    values = fresh()
    feedback = [{"kind": "shushed", "at": AT}] * 2
    raise_name, lower_name, _ = values.propose(feedback)
    assert lower_name == "playfulness"
    assert raise_name != "playfulness"


def test_values_stay_where_life_put_them_with_no_drift_back():
    values = fresh()
    values.nudge("curiosity", "tidiness", "a", AT)
    assert not hasattr(values, "drift")
    again = Values(values.to_dict())
    assert again.value("curiosity") == 8 and again.value("tidiness") == 4


def test_only_the_owner_sets_values_directly_and_moves_floors():
    values = fresh()
    with pytest.raises(OwnerOnly):
        values.owner_set("honesty", 5, None, AT)
    with pytest.raises(PermissionError):
        OwnerGrant(object(), "forged")
    grant = grant_for()
    values.owner_set("honesty", 10, grant, AT)
    assert values.value("honesty") == 10
    values.owner_set("honesty", 5, grant, AT)
    assert values.value("honesty") == 7
    values.owner_set("honesty", 5, grant, AT, floor=5)
    assert values.value("honesty") == 5 and values.dials["honesty"].minimum == 5


def test_passphrase_gate_locks_out_after_failures():
    record = hash_passphrase("blue pebble", iterations=1000)
    ticks = [0.0]
    gate = PassphraseGate(lambda: {"passphrase": record}, monotonic=lambda: ticks[0])
    for _ in range(5):
        assert gate.verify("wrong") is None
    assert gate.locked_out()
    assert gate.verify("blue pebble") is None
    ticks[0] = 1000.0
    assert gate.verify("blue pebble") is not None


def test_unset_passphrase_never_grants():
    gate = PassphraseGate(lambda: read_json(TEMPLATE_DIR / "core.json"))
    assert not gate.is_set()
    assert gate.verify("") is None


def test_values_round_trip():
    values = fresh()
    values.nudge("curiosity", "tidiness", "a", AT, 5.0)
    values.log_feedback("bump", AT)
    again = Values(values.to_dict())
    assert again.to_dict() == values.to_dict()
    assert "honesty a lot (9/10)" in again.describe()
