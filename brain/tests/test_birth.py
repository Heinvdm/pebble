import json

import pytest

from pebble.android import seal as android_seal
from pebble.owner import hash_passphrase
from pebble.self.birth import FIRST_TASTES, BirthFixed, describe, draw, ensure_seed, preview, record_of, redraw, run_seed, seed_of, template
from pebble.self.registry import BETWEEN, REGISTRY, born_with
from pebble.selfstore import LockedFile, SelfStore
from pebble.setup import Setup, birth_draw
from pebble.setup.cli import main as setup_main

PASSPHRASE = "blue kettle seven"


def test_every_pebble_keeps_its_own_seed_in_its_self(tmp_path, clock):
    first, second = SelfStore.open(tmp_path / "a", clock), SelfStore.open(tmp_path / "b", clock)
    seed = ensure_seed(first)
    assert seed != ensure_seed(second)
    assert ensure_seed(SelfStore.open(tmp_path / "a", clock)) == seed_of(first) == seed
    with pytest.raises(LockedFile):
        first.write("birth.json", {**record_of(first), "seed": "00"})


def test_each_run_draws_from_the_birth_seed_and_the_boot_count():
    assert run_seed(7, 1) == run_seed(7, 1)
    assert len({run_seed(7, 1), run_seed(7, 2), run_seed(8, 1), run_seed(7, 1, "talk")}) == 4
    assert all(0 <= run_seed(seed, boots) < 2**48 for seed in range(20) for boots in range(5))


def test_the_birth_draw_stays_inside_the_templates_ranges_and_replays_exactly():
    personality, values = template()
    drawn_dials = {e.name for e in born_with() if e.home == "dials.json"}
    seen = set()
    for seed in range(300):
        drawn = draw(seed, 1)
        assert drawn == draw(seed, 1)
        seen.add(json.dumps(drawn, sort_keys=True))
        for name, value in drawn["traits"].items():
            low, high = personality["ranges"][name]
            assert max(low, 3 if name == "cautious" else low) <= value <= high
            assert abs(value - personality["traits"][name]) <= 2
        assert set(drawn["values"]) == {"tidiness", "curiosity", "playfulness", "caution", "independence"}
        for name, value in drawn["values"].items():
            raw = values["dials"][name]
            assert raw["min"] <= value <= raw["max"] and abs(value - raw["start"]) <= 1
        assert drawn["values"]["caution"] >= 3
        assert set(drawn["dials"]) == drawn_dials
        for name, value in drawn["dials"].items():
            found = REGISTRY[name]
            how, low, high = found.birth
            span = (low, high) if how == BETWEEN else (found.default * low, found.default * high)
            assert span[0] - 0.01 <= value <= span[1] + 0.01, name
        assert 1 <= len(drawn["tastes"]) <= 2 and set(drawn["tastes"]) <= set(FIRST_TASTES)
    assert len(seen) == 300
    assert draw(5, 1) != draw(5, 2)


def test_plain_words_say_what_it_was_born_like():
    drawn = {"traits": {"curious": 10, "chatty": 1}, "dials": {"rhythm.shift_h": 1.2}, "tastes": ["round things"]}
    line, words = describe(drawn)
    assert line == "I think I'm very curious, quiet and a bit of a night owl, and I like round things."
    assert words == "I'm a small robot, very curious, quiet and a bit of a night owl, and I like round things."
    assert describe({"traits": {}, "dials": {}, "tastes": []})[0] == "I think I'm a lot like other Pebbles so far."


@pytest.mark.setup_mode
def test_pebble_is_born_when_setup_ends_and_the_draw_is_its_own(rig_factory):
    rig = rig_factory()
    store = rig.store
    seed = seed_of(store)
    assert seed is not None and record_of(store).get("born") is None
    expected = draw(seed, 1)
    assert rig.life.finish_setup()
    born = record_of(store)
    assert born["born"] == "2026-10-15" and born["drawn"] == expected and born["draw"] == 1 and not born["late"] and born["kept"] == []
    assert store.read("personality.json")["traits"] == expected["traits"]
    values = store.read("values.json")["dials"]
    for name, value in expected["values"].items():
        assert values[name]["value"] == values[name]["start"] == value
    assert values["honesty"]["value"] == 9 and values["kindness"]["value"] == 8
    assert store.read("dials.json")["values"] == expected["dials"]
    temperament = rig.parts.inner.temperament
    assert temperament.half_life_s == pytest.approx(expected["dials"]["mood.half_life_min"] * 60.0)
    assert temperament.shift_h == expected["dials"]["rhythm.shift_h"] and temperament.startle == expected["dials"]["startle"]
    diary = [entry["text"] for entry in store.read_lines("diary.jsonl")]
    assert diary[-2:] == ["Today I woke up for real.", born["line"]]
    book, now = rig.life.alive.book, rig.clock.now()
    for taste in expected["tastes"]:
        assert all(book.liking(kind, now) > 0 for kind in FIRST_TASTES[taste])
    if "round things" not in expected["tastes"]:
        assert (book.liking("frisbee", now) > 0) == (expected["traits"]["playful"] >= 6)
    assert (book.fear("vacuum", now) > 0) == (expected["traits"]["cautious"] >= 4)
    with pytest.raises(BirthFixed):
        redraw(store)
    with pytest.raises(LockedFile):
        store.write("birth.json", {**born, "draw": 2})
    rig.life._be_born()
    assert record_of(store) == born


@pytest.mark.setup_mode
def test_a_trait_people_changed_while_it_was_set_up_is_kept(rig_factory):
    rig = rig_factory()
    personality = rig.store.read("personality.json")
    personality["traits"]["playful"] = 9
    rig.store.write("personality.json", personality)
    assert rig.life.finish_setup()
    assert rig.store.read("personality.json")["traits"]["playful"] == 9
    assert record_of(rig.store)["kept"] == ["trait.playful"]


@pytest.mark.setup_mode
def test_the_owner_may_ask_for_a_new_draw_only_while_pebble_is_being_set_up(rig_factory, capsys):
    rig = rig_factory()
    store, root = rig.store, str(rig.store.root)
    core = store.read("core.json")
    core["passphrase"] = hash_passphrase(PASSPHRASE, iterations=1000)
    store.path("core.json").write_text(json.dumps(core), encoding="utf-8")
    first = preview(store)
    assert setup_main(["draw", "--self", root], clock=rig.clock) == 0
    assert first["line"] in capsys.readouterr().out
    assert setup_main(["draw", "--again", "--self", root], clock=rig.clock, ask=lambda prompt: "wrong") != 0
    assert preview(store)["draw"] == 1
    assert setup_main(["draw", "--again", "--self", root], clock=rig.clock, ask=lambda prompt: PASSPHRASE) == 0
    second = preview(store)
    assert second["draw"] == 2 and second["drawn"] == draw(seed_of(store), 2)
    assert setup_main(["done", "--self", root], clock=rig.clock, ask=lambda prompt: PASSPHRASE, answer=lambda prompt: "no") == 0
    rig.life._check_setup()
    born = record_of(store)
    assert born["draw"] == 2 and born["drawn"] == second["drawn"]
    assert setup_main(["draw", "--again", "--self", root], clock=rig.clock, ask=lambda prompt: PASSPHRASE) != 0
    assert record_of(store)["draw"] == 2
    assert setup_main(["status", "--self", root], clock=rig.clock) == 0
    assert born["line"] in capsys.readouterr().out


@pytest.mark.setup_mode
def test_setup_ended_while_the_brain_was_off_is_born_at_the_next_start(tmp_path, clock, rig_factory):
    root = tmp_path / "self"
    SelfStore.open(root, clock)
    assert setup_main(["done", "--self", str(root)], clock=clock, answer=lambda prompt: "no") == 0
    clock.advance(2 * 86400)
    rig = rig_factory()
    assert not Setup.load(rig.store).on and record_of(rig.store).get("born") is None
    rig.life._begin()
    born = record_of(rig.store)
    assert born["born"] == "2026-10-15" and born["late"] and born["drawn"] == draw(seed_of(rig.store), 1)
    assert rig.parts.inner.temperament.resting == born["drawn"]["dials"]["mood.resting"]
    texts = [entry["text"] for entry in rig.store.read_lines("diary.jsonl")]
    assert texts[-1] == born["line"] and "Today I woke up for real." not in texts


@pytest.mark.setup_mode
def test_setup_ended_the_same_day_while_the_brain_was_off_wakes_up_and_is_born_at_the_start(tmp_path, clock, rig_factory):
    root = tmp_path / "self"
    SelfStore.open(root, clock)
    assert setup_main(["done", "--self", str(root)], clock=clock, answer=lambda prompt: "no") == 0
    rig = rig_factory()
    rig.life._begin()
    born = record_of(rig.store)
    assert born["born"] == "2026-10-15" and not born["late"]
    texts = [entry["text"] for entry in rig.store.read_lines("diary.jsonl")]
    assert texts[-2:] == ["Today I woke up for real.", born["line"]]
    rig.life._begin()
    assert [entry["text"] for entry in rig.store.read_lines("diary.jsonl")].count("Today I woke up for real.") == 1


def test_a_self_whose_setup_never_ended_is_not_drawn(rig_factory):
    rig = rig_factory()
    rig.life._begin()
    assert record_of(rig.store).get("born") is None
    assert rig.parts.inner.temperament.resting == 0.2


@pytest.mark.setup_mode
def test_the_admin_screen_shows_the_draw_and_the_owner_may_draw_again_while_setting_up(tmp_path, clock):
    root = tmp_path / "self"
    SelfStore.open(root, clock)
    shown = json.loads(android_seal.birth_draw(str(root)))
    assert shown["ok"] and shown["birth"]["draw"] == 1 and shown["message"].startswith("I think I'm")
    again = json.loads(android_seal.birth_draw(str(root), True))
    assert again["ok"] and again["birth"]["draw"] == 2
    store = SelfStore.open(root, clock)
    core = store.read("core.json")
    core["passphrase"] = hash_passphrase(PASSPHRASE, iterations=1000)
    store.path("core.json").write_text(json.dumps(core), encoding="utf-8")
    assert not birth_draw(root, True, "wrong", clock)["ok"] and birth_draw(root, False, None, clock)["draw"] == 2
    assert birth_draw(root, True, PASSPHRASE, clock)["draw"] == 3
    assert setup_main(["done", "--self", str(root)], clock=clock, ask=lambda prompt: PASSPHRASE, answer=lambda prompt: "no") == 0
    refused = json.loads(android_seal.birth_draw(str(root), True, PASSPHRASE))
    assert not refused["ok"] and refused["birth"]["draw"] == 3
