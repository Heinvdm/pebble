import hashlib
import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from pebble.blackbox import BlackBox
from pebble.books import Books
from pebble.seal import (
    PHRASE,
    SAVED,
    CardError,
    FileKeyHolder,
    NoOwnerLock,
    Room,
    SealError,
    finish_throw_away,
    open_room,
    open_self,
    owner_store,
    prepare_throw_away,
    recover,
    reprint_cards,
    seal_self,
    throw_away,
)
from pebble.seal import cards as cardlib
from pebble.seal import files as convert
from pebble.seal import locks, rotation
from pebble.seal import room as roomlib
from pebble.seal.keys import SelfKey
from pebble.selfstore import CorruptFile, SealedCodec, SelfStore
from pebble.selfstore import rotation as journal_ops
from pebble.selfstore.atomic import TamperedFile, TornLine
from pebble.selfstore.codec import is_line_file

FAST = {"n": 2**10, "r": 8, "p": 1}
PASSWORD = "correct horse battery"
STEPS = ("after_a", "during_b", "after_b", "after_c", "between_d_e", "during_e")
COMMITTED = {"between_d_e", "during_e"}
ROOM = {"first-photo.jpg": b"a photo taken on the first day " * 20, "a-voice.ogg": b"a voice clip " * 50}


class Boom(Exception):
    pass


@dataclass
class World:
    root: Path
    holder: FileKeyHolder
    clock: object
    old_cards: list[str]
    base: Path

    @property
    def snapshots(self) -> Path:
        return self.base / "self-snapshots"

    def pebble(self) -> SelfStore:
        return open_self(self.root, self.clock, key_file=self.holder.path)

    def cards_key(self, printed: list[str], first: int = 0, second: int = 2) -> SelfKey:
        return locks.open_cards(locks.load(self.root), [cardlib.parse(printed[first]), cardlib.parse(printed[second])])

    def room_by_cards(self, printed: list[str]):
        return open_room(self.root, self.clock, cards=[cardlib.parse(printed[0]), cardlib.parse(printed[1])])


def room_holds_only(world: World, opened, other: roomlib.RoomKey) -> None:
    assert {thing.name: opened.take_out(thing.id)[1] for thing in opened.things()} == ROOM
    bodies = roomlib.bodies(world.root)
    assert len(bodies) == len(ROOM)
    for path, relative in bodies:
        with pytest.raises(TamperedFile):
            roomlib.open_body(other, relative, path.read_bytes())


@pytest.fixture
def world(tmp_path, clock):
    root = tmp_path / "self"
    store = SelfStore.open(root, clock)
    store.append("diary.jsonl", {"text": "first day"})
    store.append("logs/monologue.jsonl", {"thought": "hm"})
    store.write("goals.json", {"goals": ["one"]})
    store.write("goals.json", {"goals": ["two"]})
    store.snapshot()
    holder = FileKeyHolder(tmp_path / "keys" / "self.key")
    seal_self(root, PASSWORD, holder, clock, kdf=FAST)
    pebble = open_self(root, clock, key_file=holder.path)
    pebble.append("diary.jsonl", {"text": "sealed day"})
    for name, data in ROOM.items():
        Room(pebble).put("file", name, data)
    box = BlackBox.for_store(pebble, clock)
    box.record("hello", n=1)
    box.close()
    clock.advance(60)
    pebble.snapshot()
    return World(root, holder, clock, reprint_cards(root, PASSWORD), tmp_path)


def tree(base: Path) -> dict:
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base.rglob("*")) if p.is_file()}


def opens(codec: SealedCodec, relative: str, data: bytes) -> bool:
    if is_line_file(relative):
        lines = [line for line in data.decode("utf-8", errors="replace").splitlines() if line.strip()]
        for line in lines:
            try:
                codec.decode_line(relative, line)
            except (TamperedFile, TornLine):
                return False
        return True
    try:
        codec.decode(relative, data)
    except TamperedFile:
        return False
    return True


def pieces(world: World) -> list[tuple[str, bytes]]:
    found = [(relative, path.read_bytes()) for path, relative in convert.self_files(world.root)]
    for snap in convert.snapshot_zips(world.snapshots):
        with zipfile.ZipFile(snap) as archive:
            found += [(name, archive.read(name)) for name in archive.namelist()]
    return [(relative, data) for relative, data in found if data.strip()]


def assert_only(world: World, current: SelfKey, other: SelfKey) -> SelfStore:
    store = world.pebble()
    assert store._key.secret() == current.secret()
    assert not (world.root / "rotation.json").exists() and not (world.root / "seal.next.json").exists()
    assert not list(world.root.rglob("*.next")) and not list(world.snapshots.glob("*.next"))
    found = pieces(world)
    assert len(found) > 20
    now, then = SealedCodec(current), SealedCodec(other)
    for relative, data in found:
        assert opens(now, relative, data), relative
        assert not opens(then, relative, data), relative
    for name in store.manifest["files"]:
        if name.endswith(".jsonl"):
            store.read_lines(name)
        else:
            store.read(name)
    assert not store.tampered
    return store


def milestones(store: SelfStore) -> int:
    return sum(1 for entry in store.read_lines("diary.jsonl") if entry.get("text") == "The day I became my own.")


def test_after_throw_away_an_old_seal_and_the_old_password_open_nothing(world):
    old_seal = (world.root / "seal.json").read_bytes()
    plan = throw_away(world.root, PASSWORD, PHRASE, world.clock, world.holder)
    new_seal = (world.root / "seal.json").read_bytes()
    (world.root / "seal.json").write_bytes(old_seal)
    with pytest.raises(CorruptFile):
        owner_store(world.root, PASSWORD, world.clock)
    old_key = locks.open_owner(locks.load(world.root), PASSWORD, world.root)
    assert old_key.secret() == plan.old.secret()
    with pytest.raises(CorruptFile):
        world.pebble()
    (world.root / "seal.json").write_bytes(new_seal)
    store = assert_only(world, plan.new, plan.old)
    assert milestones(store) == 1


def test_old_cards_stop_working_and_the_new_cards_recover(world, tmp_path):
    plan = throw_away(world.root, PASSWORD, PHRASE, world.clock, world.holder)
    assert plan.cards != world.old_cards and len(plan.cards) == 3
    with pytest.raises(CardError, match="stop working"):
        world.cards_key(world.old_cards)
    forged_old = [cardlib.Card(plan.set_id, card.number, card.share) for card in map(cardlib.parse, world.old_cards)]
    with pytest.raises(CardError, match="do not open"):
        locks.open_cards(locks.load(world.root), forged_old[:2])
    assert world.cards_key(plan.cards).secret() == plan.new.secret()
    phone = FileKeyHolder(tmp_path / "phone2.key")
    recover(world.root, phone, [cardlib.parse(plan.cards[1]), cardlib.parse(plan.cards[2])], clock=world.clock)
    assert open_self(world.root, world.clock, key_file=phone.path).access == "pebble"


def test_snapshots_are_sealed_again_with_the_new_key(world):
    before = sorted(p.name for p in convert.snapshot_zips(world.snapshots))
    plan = throw_away(world.root, PASSWORD, PHRASE, world.clock, world.holder)
    assert sorted(p.name for p in convert.snapshot_zips(world.snapshots)) == before and len(before) == 2
    now, then = SealedCodec(plan.new), SealedCodec(plan.old)
    for snap in convert.snapshot_zips(world.snapshots):
        with zipfile.ZipFile(snap) as archive:
            for name in archive.namelist():
                data = archive.read(name)
                if data.strip():
                    assert opens(now, name, data) and not opens(then, name, data)


def test_pebble_runs_on_after_throw_away(world):
    throw_away(world.root, PASSWORD, PHRASE, world.clock, world.holder)
    store = world.pebble()
    books = Books(store, world.clock)
    books.save_all()
    store.write("goals.json", {"goals": ["after"]})
    store.append("diary.jsonl", {"text": "still me"})
    again = world.pebble()
    assert again.read("goals.json") == {"goals": ["after"]}
    assert again.read_lines("diary.jsonl")[-1] == {"text": "still me"}
    assert again.read("calendar.json")["personal"][-1]["title"] == "The day I became my own"
    assert again.owner_lock_exists is False and not again.tampered


def throw(*args, **kwargs):
    raise Boom("power cut")


def inject(monkeypatch, step):
    if step == "after_a":
        monkeypatch.setattr(rotation, "begin", throw)
    elif step == "during_b":
        real, count = rotation.stage_file, [0]

        def flaky(path, data):
            count[0] += 1
            if count[0] == 5:
                raise Boom("power cut")
            real(path, data)

        monkeypatch.setattr(rotation, "stage_file", flaky)
    elif step == "after_b":
        monkeypatch.setattr(rotation, "write_next_seal", throw)
    elif step == "after_c":
        monkeypatch.setattr(rotation, "commit", throw)
    elif step == "between_d_e":
        monkeypatch.setattr(rotation, "roll_forward", throw)
    else:
        count = [0]

        def flaky(source, target):
            count[0] += 1
            if count[0] == 4:
                raise Boom("power cut")
            os.replace(source, target)

        proxy = SimpleNamespace(replace=flaky, name=os.name, open=os.open, fsync=os.fsync, close=os.close, O_RDONLY=os.O_RDONLY)
        monkeypatch.setattr(journal_ops, "os", proxy)


@pytest.mark.parametrize("step", STEPS)
def test_an_interrupted_throw_away_leaves_one_whole_key_set(world, monkeypatch, step):
    plan = prepare_throw_away(world.root, PASSWORD, PHRASE, world.holder)
    inject(monkeypatch, step)
    with pytest.raises(Boom):
        finish_throw_away(plan, SAVED, world.clock)
    monkeypatch.undo()
    if step in ("after_b", "after_c", "during_b"):
        assert (world.root / "rotation.json").exists()
    if step in COMMITTED:
        store = assert_only(world, plan.new, plan.old)
        assert milestones(store) == 1
        with pytest.raises(NoOwnerLock):
            owner_store(world.root, PASSWORD, world.clock)
        with pytest.raises(CardError):
            world.cards_key(world.old_cards)
        assert world.cards_key(plan.cards).secret() == plan.new.secret()
        room_holds_only(world, world.room_by_cards(plan.cards), plan.old_room)
        with pytest.raises(CardError):
            world.room_by_cards(world.old_cards)
        return
    store = assert_only(world, plan.old, plan.new)
    assert milestones(store) == 0 and store.owner_lock_exists
    assert owner_store(world.root, PASSWORD, world.clock).access == "owner"
    assert world.cards_key(world.old_cards).secret() == plan.old.secret()
    with pytest.raises(CardError):
        world.cards_key(plan.cards)
    room_holds_only(world, open_room(world.root, world.clock, password=PASSWORD), plan.new_room)
    room_holds_only(world, world.room_by_cards(world.old_cards), plan.new_room)
    again = throw_away(world.root, PASSWORD, PHRASE, world.clock, world.holder)
    assert milestones(assert_only(world, again.new, plan.old)) == 1
    room_holds_only(world, world.room_by_cards(again.cards), plan.old_room)


def test_recovery_also_runs_from_the_command_paths(world, monkeypatch):
    plan = prepare_throw_away(world.root, PASSWORD, PHRASE, world.holder)
    monkeypatch.setattr(rotation, "roll_forward", throw)
    with pytest.raises(Boom):
        finish_throw_away(plan, SAVED, world.clock)
    monkeypatch.undo()
    assert (world.root / "rotation.json").exists()
    with pytest.raises(NoOwnerLock, match="thrown away"):
        reprint_cards(world.root, PASSWORD)
    assert not (world.root / "rotation.json").exists()
    assert_only(world, plan.new, plan.old)


def test_nothing_changes_until_the_new_cards_are_confirmed(world):
    before = tree(world.base)
    plan = prepare_throw_away(world.root, PASSWORD, PHRASE, world.holder)
    with pytest.raises(SealError, match="nothing was changed"):
        finish_throw_away(plan, "not yet", world.clock)
    assert tree(world.base) == before
    with pytest.raises(SealError):
        prepare_throw_away(world.root, PASSWORD, "something else", world.holder)
    with pytest.raises(SealError, match="key file"):
        prepare_throw_away(world.root, PASSWORD, PHRASE, FileKeyHolder(world.base / "elsewhere.key"))
    assert tree(world.base) == before


def test_tampered_pieces_are_dropped_not_carried_under_the_new_key(world):
    store = world.pebble()
    shutil.copyfile(store.path("goals.json"), store.path("jokes.json"))
    store.path("places.json").write_text('{"planted": true}', encoding="utf-8")
    plan = throw_away(world.root, PASSWORD, PHRASE, world.clock, world.holder)
    then = SealedCodec(plan.old)
    for relative, data in pieces(world):
        for name in ("goals.json", "jokes.json", relative):
            assert not opens(then, name, data) or not data.strip()
    store = assert_only(world, plan.new, plan.old)
    assert store.read("jokes.json") != store.read("goals.json")
    assert "planted" not in store.read("places.json")


def test_a_stale_store_cannot_write_after_the_key_changes(world):
    stale = world.pebble()
    throw_away(world.root, PASSWORD, PHRASE, world.clock, world.holder)
    from pebble.selfstore import WrongKey

    with pytest.raises(WrongKey):
        stale.write("goals.json", {"goals": ["old key"]})
    with pytest.raises(WrongKey):
        stale.append("diary.jsonl", {"text": "old key"})
    assert world.pebble().read("goals.json") == {"goals": ["two"]}


@pytest.mark.parametrize("hook", ["stage_file", "write_next_seal"])
def test_someone_opening_the_self_mid_change_makes_it_undo_cleanly(world, monkeypatch, hook):
    plan = prepare_throw_away(world.root, PASSWORD, PHRASE, world.holder)
    real, count = getattr(rotation, hook), [0]

    def meddling(*args):
        count[0] += 1
        if count[0] == 3 or hook == "write_next_seal":
            world.pebble()
        real(*args)

    monkeypatch.setattr(rotation, hook, meddling)
    with pytest.raises(SealError, match="Something else opened the self"):
        finish_throw_away(plan, SAVED, world.clock)
    monkeypatch.undo()
    store = assert_only(world, plan.old, plan.new)
    assert store.owner_lock_exists and milestones(store) == 0
