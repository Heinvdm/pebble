import json

import pytest
from conftest import run

from pebble.alive.book import AliveBook
from pebble.books import Books
from pebble.owner import hash_passphrase
from pebble.people.qualities import NotScored
from pebble.seal.cli import main as seal_main
from pebble.selfstore import SelfStore
from pebble.setup import Setup, finish, finish_setup, in_setup, setup_status
from pebble.setup.cli import main as setup_main

pytestmark = pytest.mark.setup_mode


def test_a_new_self_starts_in_setup_and_says_so_kindly(rig_factory):
    rig = rig_factory()
    life = rig.life
    assert life.setup.on and life.setup.since
    assert Setup.load(rig.store).on
    system = rig.turns.builder.system_text("newborn", "", "")
    assert "being built and set up" in system and "You are safe" in system
    entry = rig.parts.diary.write("I looked at the room.", "note")
    assert entry["setup"] is True


def test_nothing_about_people_counts_and_strangers_are_not_kept(rig_factory, store):
    rig = rig_factory()
    book = rig.books.people
    stranger = book.meet(rig.clock.now(), voice=[0.1] * 8)
    with pytest.raises(NotScored):
        book.evidence(stranger, "kindness", True, "senses", "smiled")
    named = book.meet(rig.clock.now(), voice=[0.2] * 8)
    named.set_name("Alex")
    saved = json.dumps(book.to_dict())
    assert named.id in saved and stranger.id not in saved


def test_fears_are_not_learned_while_being_set_up():
    book = AliveBook()
    book.setup = True
    assert book.feel("vacuum", "fear", 2.0, "it roared", 0.0) == 0.0
    assert book.fear("vacuum", 1.0) == 0.0
    assert book.feel("ball", "like", 1.0, "fun", 0.0) == 1.0
    book.setup = False
    assert book.feel("vacuum", "fear", 1.0, "it roared", 0.0) == 1.0


def test_restarts_during_setup_are_calm(tmp_path, clock):
    from conftest import Rig

    first = Rig(tmp_path, clock)
    first.parts.inner.fear.level = 7.0
    first.life.save(clean=False)
    first.close()
    second = Rig(tmp_path, clock)
    assert second.parts.inner.fear.level == 0.0
    assert "still being set up" in second.life.wake and "power loss" not in second.life.wake
    second.close()


def test_no_value_nudges_at_night_while_being_set_up(rig_factory):
    rig = rig_factory()
    rig.books.values.log_feedback("own_idea_went_well", "2026-10-15T10:00:00+00:00", "a drawing")
    report = run(rig.life.nightly.run("2026-10-15", "newborn", rig.mind))
    assert report["values"] == "no nudges while being set up" and "nudge" not in report


def test_sealing_waits_for_setup_to_finish(tmp_path, clock):
    root = tmp_path / "self"
    SelfStore.open(root, clock)
    assert in_setup(root)
    assert seal_main(["seal", "--self", str(root)]) != 0
    assert in_setup(root)


def test_only_the_owner_ends_setup_and_pebble_wakes_up_for_real(rig_factory):
    rig = rig_factory()
    store = rig.store
    core = store.read("core.json")
    core["passphrase"] = hash_passphrase("blue kettle seven", iterations=1000)
    store.path("core.json").write_text(json.dumps(core), encoding="utf-8")
    assert setup_main(["done", "--self", str(store.root)], clock=rig.clock, ask=lambda prompt: "wrong") != 0
    assert Setup.load(store).on
    assert setup_main(["done", "--self", str(store.root)], clock=rig.clock, ask=lambda prompt: "blue kettle seven") == 0
    setup = Setup.load(store)
    assert not setup.on and setup.born == "2026-10-15"
    assert finish_setup(store.root, clock=rig.clock) == {"ok": True, "already": True, "born": "2026-10-15", "error": None}
    assert setup_status(store.root, rig.clock)["on"] is False
    rig.life._check_setup()
    assert not rig.life.setup.on and rig.books.birthday.isoformat() == "2026-10-15"
    assert not rig.books.people.setup and not rig.turns.builder.setup
    diary = store.read_lines("diary.jsonl")
    assert diary[-2]["text"] == "Today I woke up for real." and "setup" not in diary[-2]
    born = store.read("birth.json")
    assert born["born"] == "2026-10-15" and diary[-1]["text"] == born["line"] and born["line"].startswith("I think I'm")
    assert Books(store, rig.clock).birthday.isoformat() == "2026-10-15"


def test_the_setup_days_fold_into_one_first_memory(rig_factory):
    rig = rig_factory()
    rig.parts.diary.write("I was lifted up.", "note")
    assert rig.life.finish_setup()
    report = run(rig.life.nightly.run("2026-10-15", "newborn", rig.mind))
    assert report["setup_folded"] == 1
    memory = rig.books.memory.facts[-1]
    assert memory["text"] == "My first memory: I was put together and tested; it felt strange, but I'm okay." and memory["pinned"]
    texts = [entry["text"] for entry in rig.store.read_lines("diary.jsonl")]
    assert "My first memory: I was put together and tested. It felt strange, but I'm okay." in texts
    again = run(rig.life.nightly.run("2026-10-16", "newborn", rig.mind))
    assert "setup_folded" not in again


def test_finishing_needs_no_passphrase_until_one_is_set(tmp_path, clock):
    store = SelfStore.open(tmp_path / "self", clock)
    setup = finish(store, clock)
    assert not setup.on and setup.ended and not setup.folded
