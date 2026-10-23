import json
import random

import pytest

from pebble.chaos import levers
from pebble.chaos.dial import QUIET_CAP, DialInputs, dial_level
from pebble.chaos.engine import Chaos
from pebble.chaos.ideas import DECKS, IdeaDecks, card_text
from pebble.chaos.novelty import RecentActions
from pebble.chaos.replay import chaos_records, main as replay_main, replay_records
from pebble.chaos.sampling import call_options
from pebble.chaos.streams import LEVERS, PROTECTED, ProtectedLever, Streams, check, replay
from pebble.chaos.whims import WHIM_KINDS, WhimContext, WhimScheduler, suppressed
from pebble.inner.mood import Mood
from pebble.inner.needs import Needs
from pebble.picker import TIER_OWN, PickContext, SafetyContext, Variety, idle_options, pick, safety_options, task_options
from pebble.selfstore.atomic import read_json
from pebble.selfstore.store import TEMPLATE_DIR

LEVELS = [x / 2 for x in range(0, 21)]
VALUES = {"honesty": 9, "kindness": 8, "tidiness": 5, "curiosity": 7, "playfulness": 6, "caution": 5, "independence": 4}


def records_sink():
    seen = []
    return seen, seen.append


def test_dial_follows_playfulness_mood_age_and_stays_in_bounds():
    calm = dial_level(DialInputs(playfulness=2, valence=-0.5, arousal=-0.5, stage="adult"))
    lively = dial_level(DialInputs(playfulness=9, valence=0.8, arousal=0.8, stage="adult"))
    assert calm < lively
    young = dial_level(DialInputs(playfulness=6, stage="child"))
    old = dial_level(DialInputs(playfulness=6, stage="adult"))
    assert young > old
    scared = dial_level(DialInputs(playfulness=6, fear=8))
    assert scared < dial_level(DialInputs(playfulness=6))
    rng = random.Random(4)
    for _ in range(500):
        inputs = DialInputs(rng.uniform(-50, 50), rng.uniform(-5, 5), rng.uniform(-5, 5), rng.choice(["newborn", "child", "teen", "adult", "x"]), rng.random() < 0.5, rng.uniform(-20, 40))
        assert 0.0 <= dial_level(inputs) <= 10.0
    assert dial_level(DialInputs(playfulness=float("nan"), valence=float("inf"))) <= 10.0


def test_quiet_hours_lower_the_dial_and_the_owner_pin_wins():
    loud = DialInputs(playfulness=10, valence=1, arousal=1, stage="child")
    assert dial_level(loud) == 10.0
    assert dial_level(DialInputs(10, 1, 1, "child", quiet=True)) <= QUIET_CAP
    assert dial_level(DialInputs(10, 1, 1, "child", quiet=True, pinned=7.5)) == 7.5
    assert dial_level(DialInputs(pinned=99)) == 10.0
    assert dial_level(DialInputs(pinned=-3)) == 0.0
    chaos = Chaos(seed=1, pinned=2)
    chaos.update(loud)
    assert chaos.level == 2.0
    chaos.pin(None)
    assert chaos.level == 10.0


@pytest.mark.parametrize("level", LEVELS)
def test_every_lever_stays_inside_its_bounds(level):
    knobs = levers.choice_knobs(level)
    assert levers.SPREAD_MIN <= knobs.spread <= levers.SPREAD_MAX
    assert 0.0 <= knobs.novelty <= levers.NOVELTY_MAX
    assert levers.TOP_K_RANGE[0] <= knobs.top_k <= levers.TOP_K_RANGE[1]
    words = levers.creative_words(level)
    assert 0.55 <= words.temperature <= 1.2
    assert 0.9 <= words.top_p <= 0.98
    assert 0.03 <= words.min_p <= 0.12
    assert 0.25 <= levers.card_chance(level) <= 0.95
    assert 0.0 <= levers.second_card_chance(level) <= 1.0
    assert 0.0 <= levers.whims_per_hour(level) <= levers.WHIMS_MAX_PER_HOUR
    motion = levers.motion_knobs(level)
    assert levers.GAZE_WANDER[0] <= motion.gaze <= levers.GAZE_WANDER[1]
    assert 0.0 <= motion.wheel <= levers.WHEEL_NOISE_CAP
    assert 1 <= levers.mutation_tweaks(level) <= levers.MUTATION_MAX_TWEAKS


def test_levers_rise_with_the_dial():
    assert levers.choice_knobs(0).spread < levers.choice_knobs(10).spread
    assert levers.creative_words(0).temperature < levers.creative_words(10).temperature
    assert levers.creative_words(0).min_p > levers.creative_words(10).min_p
    assert levers.whims_per_hour(0) == 0.0 < levers.whims_per_hour(5)
    assert levers.motion_knobs(1).gaze < levers.motion_knobs(9).gaze


def test_safety_levers_are_untouched_by_chaos():
    for name in PROTECTED:
        with pytest.raises(ProtectedLever):
            Streams(1).stream(name)
    assert not set(LEVERS) & PROTECTED
    for kind in ("tool", "safety", "summary", "job", "turn"):
        profiles = {(o.temperature, o.top_p, o.min_p) for o in (call_options(kind, level) for level in LEVELS)}
        assert profiles == {(levers.STEADY_TEMPERATURE, levers.STEADY_TOP_P, levers.STEADY_MIN_P)}
    creative = {call_options("drawing", level).temperature for level in LEVELS}
    assert len(creative) > 5
    assert levers.WHIM_SPIN_POWER <= 0.3
    assert levers.dream_allowed(True, True) and not levers.dream_allowed(True, False) and not levers.dream_allowed(False, True)


def test_chaos_never_moves_safety_or_people_choices():
    options = safety_options(SafetyContext(low_battery=True, quiet=True)) + idle_options()
    ctx = PickContext(Needs(), Mood(0.3, 0.2), 0.0, VALUES)
    for level in (0, 5, 10):
        knobs = levers.choice_knobs(level)
        variety = Variety(knobs.spread, knobs.top_k, {o.key: 5.0 for o in options})
        chaos = Chaos(seed=level)
        for _ in range(20):
            choice = pick(options, ctx, chaos.stream("choices"), variety=variety)
            assert choice.chosen.key == "dock"
    assert Chaos(seed=1).streams.counts() == {}


def test_novelty_bonus_favours_things_not_done_lately():
    recent = RecentActions(window_s=3600)
    recent.did("play", 1000.0)
    bonuses = recent.bonuses(["play", "nap"], 1000.0, 0.12)
    assert bonuses["play"] == 0.0 and bonuses["nap"] == 0.12
    assert recent.freshness("play", 1000.0 + 1800) == pytest.approx(0.5)
    ctx = PickContext(Needs(curiosity=0.6, social=0.4, rest=0.2), Mood(0.3, 0.2), 0.0, VALUES)
    options = idle_options()
    plain = pick(options, ctx, random.Random(1))
    boosted = pick(options, ctx, random.Random(1), variety=Variety(1.0, 3, {"tidy": 0.5}))
    assert boosted.chosen.key == "tidy"
    assert any("not done lately" in reason for reason in boosted.reasons)
    assert plain.as_dict().keys() == boosted.as_dict().keys()


def test_every_draw_is_logged_and_replays_exactly():
    seen, sink = records_sink()
    chaos = Chaos(seed=1234, sink=sink)
    whims = chaos.stream("whims")
    outcomes = [whims.random(), whims.uniform(1, 3), whims.randint(1, 6), whims.choice(["a", "b", "c"]), whims.choices([0, 1, 2], [0.1, 0.2, 0.7], 2), whims.gauss(0, 1), whims.expovariate(2.0), whims.getrandbits(31), whims.randrange(9)]
    assert len(seen) == len(outcomes)
    for record, outcome in zip(seen, outcomes):
        assert record["lever"] == "whims" and record["id"].startswith("whims:")
        back = json.loads(json.dumps(record))
        assert check(back)
        assert json.loads(json.dumps(replay(back))) == json.loads(json.dumps(outcome))
    tampered = dict(seen[0], outcome=-1)
    assert not check(tampered)


def test_same_seed_same_draws_and_levers_are_independent():
    first, second = Chaos(seed=99), Chaos(seed=99)
    assert [first.stream("choices").random() for _ in range(5)] == [second.stream("choices").random() for _ in range(5)]
    a, b = Chaos(seed=7), Chaos(seed=7)
    for _ in range(10):
        a.stream("words").random()
    assert a.stream("whims").random() == b.stream("whims").random()
    assert Chaos(seed=1).stream("whims").random() != Chaos(seed=2).stream("whims").random()


def test_replay_reads_the_black_box(tmp_path, clock):
    from pebble.blackbox import BlackBox

    box = BlackBox(tmp_path / "logs" / "blackbox.jsonl", clock)
    chaos = Chaos(seed=5, sink=lambda record: box.record("chaos", **record))
    chaos.stream("whims").expovariate(1.0)
    chaos.stream("seeds").choice(["theme", "voice"])
    box.record("other", value=1)
    box.close()
    records = chaos_records(tmp_path / "logs" / "blackbox.jsonl")
    assert [r["lever"] for r in records] == ["whims", "seeds"]
    assert all(result.same for result in replay_records(records))
    assert replay_main([str(tmp_path / "logs" / "blackbox.jsonl"), "--lever", "whims"]) == 0


def test_call_options_carry_a_logged_seed():
    seen, sink = records_sink()
    chaos = Chaos(seed=3, sink=sink, pinned=8)
    creative = chaos.call_options("drawing")
    steady = chaos.call_options("tool")
    assert creative.kind == "creative" and steady.kind == "steady"
    assert creative.temperature > steady.temperature
    assert creative.seed == seen[0]["outcome"] and seen[0]["lever"] == "words"
    assert steady.seed == seen[1]["outcome"] and seen[1]["lever"] == "steady"
    assert Chaos.disabled().call_options("drawing") is None


def ctx(now: float, **overrides) -> WhimContext:
    return WhimContext(now=now, **overrides)


def run_whims(scheduler: WhimScheduler, hours: float, rate: float, step: float = 10.0, start: float = 0.0, **overrides) -> list:
    fired = []
    now = start
    while now < start + hours * 3600:
        whim = scheduler.check(ctx(now, **overrides), rate)
        if whim is not None:
            fired.append(whim)
        now += step
    return fired


def test_whims_are_rate_limited():
    chaos = Chaos(seed=11)
    scheduler = WhimScheduler(chaos.stream("whims"), 0.0)
    fired = run_whims(scheduler, 24, 50.0)
    times = [whim.at for whim in fired]
    assert len(fired) > 10
    for index, at in enumerate(times):
        assert sum(1 for other in times if at - 3600 < other <= at) <= levers.WHIMS_MAX_PER_HOUR
        if index:
            assert at - times[index - 1] >= levers.WHIM_MIN_GAP_S
    assert {whim.kind for whim in fired} <= set(WHIM_KINDS)
    assert run_whims(WhimScheduler(chaos.stream("whims"), 0.0), 5, 0.0) == []


def test_no_whims_in_quiet_hours_or_while_someone_is_upset():
    chaos = Chaos(seed=12)
    for overrides in ({"quiet": True}, {"someone_upset": True}, {"active": False}, {"low_battery": True}, {"fear": 6.0}, {"valence": -0.8}, {"busy": True}, {"available": ()}):
        scheduler = WhimScheduler(chaos.stream("whims"), 0.0)
        assert run_whims(scheduler, 6, 50.0, **overrides) == [], overrides
        assert suppressed(ctx(0.0, **overrides)) is not None
    scheduler = WhimScheduler(chaos.stream("whims"), 0.0)
    assert run_whims(scheduler, 4, 50.0, quiet=True) == []
    after = run_whims(scheduler, 0.2, 50.0, start=4 * 3600)
    assert all(whim.at - 4 * 3600 >= levers.WHIM_MIN_GAP_S for whim in after)


def test_whims_replay_from_their_logged_draws():
    seen, sink = records_sink()
    chaos = Chaos(seed=21, sink=sink)
    fired = run_whims(WhimScheduler(chaos.stream("whims"), 0.0), 6, 4.0)
    assert fired and seen
    assert all(check(json.loads(json.dumps(record))) for record in seen)
    kinds = [r["outcome"] for r in seen if r["op"] == "choice"]
    assert kinds == [whim.kind for whim in fired]


def test_idea_decks_are_curated_and_drawn_by_the_dial():
    data = read_json(TEMPLATE_DIR / "ideas.json")
    decks = IdeaDecks.from_dict(data)
    assert set(decks.decks) == set(DECKS)
    assert all(len(cards) >= 10 for cards in decks.decks.values())
    texts = {card.text for cards in decks.decks.values() for card in cards}
    low, high = Chaos(seed=1, pinned=0), Chaos(seed=1, pinned=10)
    drawn_low = sum(bool(low.cards(decks, "drawing")) for _ in range(300))
    drawn_high = sum(bool(high.cards(decks, "drawing")) for _ in range(300))
    assert drawn_low < drawn_high
    for _ in range(100):
        cards = high.cards(decks, "drawing")
        assert {card.deck for card in cards} <= {"theme", "constraint"}
        assert all(card.text in texts for card in cards)
        assert len({card.deck for card in cards}) == len(cards)
    for _ in range(50):
        assert {card.deck for card in high.cards(decks, "talk")} <= {"theme", "voice"}
    assert card_text([]) == ""
    assert IdeaDecks.from_dict({"decks": {"theme": [{"text": ""}, "junk"], "evil": [{"text": "x"}]}}).size() == 0
    assert Chaos.disabled().cards(decks, "drawing") == []


def test_disabled_chaos_leaves_the_picker_alone():
    chaos = Chaos.disabled()
    assert chaos.level == 0.0 and chaos.choices() is None and chaos.whim_rate() == 0.0
    ctx_ = PickContext(Needs(curiosity=0.6), Mood(0.3, 0.2), 0.0, VALUES)
    options = idle_options() + task_options([])
    assert pick(options, ctx_, random.Random(5)).chosen.key == pick(options, ctx_, random.Random(5), variety=None).chosen.key
    assert all(o.tier == TIER_OWN for o in idle_options())
