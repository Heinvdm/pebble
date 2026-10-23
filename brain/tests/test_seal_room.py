import base64
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from pebble.seal import (
    PHRASE,
    CardError,
    FileKeyHolder,
    NoOwnerLock,
    OpenRoom,
    Room,
    RoomError,
    SealError,
    WrongPassword,
    open_room,
    open_self,
    pebble_key,
    recover,
    reprint_cards,
    seal_self,
    status,
    throw_away,
    unseal_self,
)
from pebble.seal import cards as cardlib
from pebble.seal import files as convert
from pebble.seal import locks
from pebble.seal import room as roomlib
from pebble.seal.sealing import mend_room_lock, room_status
from pebble.selfstore import CorruptFile, SealedCodec, SelfStore, WrongKey
from pebble.selfstore.atomic import TamperedFile, TornLine
from pebble.selfstore.codec import MAGIC, is_line_file
from pebble.selfstore.sealed import b64, open_sealed_value

FAST = {"n": 2**10, "r": 8, "p": 1}
PASSWORD = "correct horse battery"
THINGS = {
    "grandmas-kitchen-1987.jpg": ("photo", b"\xff\xd8\xff grandmas kitchen in 1987 " * 40),
    "hello.ogg": ("voice", b"OggS a voice saying hello " * 30),
    "pressed flower": ("keepsake", b"a flower from the garden"),
}


@dataclass
class Sealed:
    root: Path
    holder: FileKeyHolder
    clock: object
    ids: dict

    @property
    def snapshots(self) -> Path:
        return self.root.parent / "self-snapshots"

    def pebble(self) -> SelfStore:
        return open_self(self.root, self.clock, key_file=self.holder.path)

    def printed(self) -> list[str]:
        return reprint_cards(self.root, PASSWORD)

    def cards(self, printed: list[str], first: int = 0, second: int = 1) -> list[cardlib.Card]:
        return [cardlib.parse(printed[first]), cardlib.parse(printed[second])]


def put_all(store: SelfStore) -> dict:
    room = Room(store)
    return {name: room.put(kind, name, data).id for name, (kind, data) in THINGS.items()}


@pytest.fixture
def sealed(tmp_path, clock):
    root = tmp_path / "self"
    store = SelfStore.open(root, clock)
    store.append("diary.jsonl", {"text": "first day"})
    holder = FileKeyHolder(tmp_path / "keys" / "self.key")
    seal_self(root, PASSWORD, holder, clock, kdf=FAST)
    pebble = open_self(root, clock, key_file=holder.path)
    ids = put_all(pebble)
    pebble.snapshot()
    return Sealed(root, holder, clock, ids)


def contents(opened: OpenRoom) -> dict:
    found = {}
    for thing in opened.things():
        assert thing.problem is None, thing
        found[thing.name] = (thing.kind, opened.take_out(thing.id)[1])
    return found


def forms(secret: bytes) -> list[bytes]:
    return [secret, base64.b64encode(secret), base64.urlsafe_b64encode(secret), secret.hex().encode()]


def everything_pebble_reads(sealed: Sealed) -> list[bytes]:
    key = pebble_key(sealed.root, sealed.holder.path)
    codec = SealedCodec(key)
    seen = [sealed.holder.path.read_bytes(), sealed.holder.load(), key.secret()]
    for path in sorted(sealed.root.parent.rglob("*")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        seen.append(data)
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                seen += [archive.read(name) for name in archive.namelist()]
        try:
            relative = path.relative_to(sealed.root).as_posix()
        except ValueError:
            continue
        if is_line_file(relative):
            for line in data.decode("utf-8", errors="replace").splitlines():
                try:
                    seen.append(codec.decode_line(relative, line).encode("utf-8"))
                except (TamperedFile, TornLine):
                    pass
        elif data.startswith(MAGIC):
            seen.append(codec.decode(relative, data))
    seal = locks.load(sealed.root)
    seen.append(json.dumps(open_sealed_value(seal, "frozen", key)).encode("utf-8"))
    return seen


def test_pebbles_lock_alone_cannot_open_the_room(sealed):
    key = pebble_key(sealed.root, sealed.holder.path)
    device_key = sealed.holder.load()
    seal = locks.load(sealed.root)
    _, recovery = locks.open_owner_all(seal, PASSWORD, sealed.root)
    room_key = roomlib.open_key(seal, recovery)
    seen = everything_pebble_reads(sealed)
    assert len(seen) > 30
    for blob in seen:
        for secret in (room_key.secret(), recovery.secret):
            assert not any(form in blob for form in forms(secret))
        for name, (_, data) in THINGS.items():
            assert name.encode("utf-8") not in blob and data[:24] not in blob
    for guess in (key.secret(), device_key):
        stranger = OpenRoom(sealed.pebble(), roomlib.RoomKey(guess), roomlib.public_key(seal))
        assert stranger.things() and all(thing.problem for thing in stranger.things())
        for path, relative in roomlib.bodies(sealed.root):
            with pytest.raises(TamperedFile):
                roomlib.open_body(roomlib.RoomKey(guess), relative, path.read_bytes())
        fake = cardlib.Recovery(guess, bytes(32), recovery.set_id)
        with pytest.raises(SealError, match="does not open with the recovery secret"):
            roomlib.open_key(seal, fake)
        with pytest.raises(CardError):
            locks.open_cards(seal, fake.cards()[:2])
    pebble = sealed.pebble()
    items = Room(pebble).items()
    assert sorted(item.kind for item in items) == ["keepsake", "photo", "voice"]
    assert all(item.listed and item.present for item in items)
    assert not hasattr(items[0], "name")


def test_the_owner_password_opens_the_room(sealed):
    opened = open_room(sealed.root, sealed.clock, password=PASSWORD)
    assert opened.locked and not opened.swapped
    assert contents(opened) == THINGS
    thing, data = opened.take_out(sealed.ids["grandmas-kitchen-1987.jpg"][:6])
    assert (thing.name, thing.kind, data) == ("grandmas-kitchen-1987.jpg", "photo", THINGS["grandmas-kitchen-1987.jpg"][1])
    with pytest.raises(WrongPassword):
        open_room(sealed.root, sealed.clock, password="not the password")
    with pytest.raises(SealError, match="password or two recovery cards"):
        open_room(sealed.root, sealed.clock)


@pytest.mark.parametrize("pair", [(0, 1), (0, 2), (1, 2)])
def test_any_two_cards_open_the_room(sealed, pair):
    printed = sealed.printed()
    opened = open_room(sealed.root, sealed.clock, cards=sealed.cards(printed, *pair))
    assert contents(opened) == THINGS
    with pytest.raises(CardError):
        open_room(sealed.root, sealed.clock, cards=[cardlib.parse(printed[pair[0]])])


def test_after_throw_away_only_the_new_cards_open_the_room(sealed):
    old_printed = sealed.printed()
    old_seal_bytes = (sealed.root / "seal.json").read_bytes()
    old_seal = json.loads(old_seal_bytes)
    _, old_recovery = locks.open_owner_all(old_seal, PASSWORD, sealed.root)
    old_room = roomlib.open_key(old_seal, old_recovery)
    plan = throw_away(sealed.root, PASSWORD, PHRASE, sealed.clock, sealed.holder)
    assert contents(open_room(sealed.root, sealed.clock, cards=sealed.cards(plan.cards, 2, 0))) == THINGS
    with pytest.raises(CardError, match="stop working"):
        open_room(sealed.root, sealed.clock, cards=sealed.cards(old_printed))
    forged = [cardlib.Card(plan.set_id, card.number, card.share) for card in sealed.cards(old_printed)]
    with pytest.raises(CardError, match="do not open"):
        open_room(sealed.root, sealed.clock, cards=forged)
    with pytest.raises(NoOwnerLock, match="thrown away"):
        open_room(sealed.root, sealed.clock, password=PASSWORD)
    _, by_old_cards = locks.open_cards_all(old_seal, sealed.cards(old_printed, 1, 2))
    assert roomlib.open_key(old_seal, by_old_cards).secret() == old_room.secret()
    bodies = roomlib.bodies(sealed.root)
    assert len(bodies) == 3
    for path, relative in bodies:
        with pytest.raises(TamperedFile, match="lock this room does not have"):
            roomlib.open_body(old_room, relative, path.read_bytes())
    (sealed.root / "seal.json").write_bytes(old_seal_bytes)
    with pytest.raises(CorruptFile):
        open_room(sealed.root, sealed.clock, password=PASSWORD)
    for snap in convert.snapshot_zips(sealed.snapshots):
        with zipfile.ZipFile(snap) as archive:
            assert not [name for name in archive.namelist() if name.startswith("room/")]


def test_two_new_cards_put_an_owner_lock_back_on_the_room(sealed, tmp_path):
    plan = throw_away(sealed.root, PASSWORD, PHRASE, sealed.clock, sealed.holder)
    phone = FileKeyHolder(tmp_path / "phone2.key")
    recover(sealed.root, phone, sealed.cards(plan.cards, 1, 2), new_password="a fresh password", clock=sealed.clock, kdf=FAST)
    assert contents(open_room(sealed.root, sealed.clock, password="a fresh password")) == THINGS
    assert reprint_cards(sealed.root, "a fresh password") == plan.cards


def test_the_room_survives_restoring_a_snapshot(sealed):
    pebble = sealed.pebble()
    later = Room(pebble).put("file", "later.txt", b"put in after the snapshot")
    snap = convert.snapshot_zips(sealed.snapshots)[-1]
    with zipfile.ZipFile(snap) as archive:
        assert not [name for name in archive.namelist() if name.startswith("room")]
        archive.extractall(sealed.root)
    shutil.rmtree(sealed.root / "logs", ignore_errors=True)
    restored = sealed.pebble()
    assert {item.id for item in Room(restored).items()} == set(sealed.ids.values()) | {later.id}
    opened = open_room(sealed.root, sealed.clock, password=PASSWORD)
    assert contents(opened) == {**THINGS, "later.txt": ("file", b"put in after the snapshot")}
    assert not restored.tampered


def test_unseal_leaves_the_room_plain_and_sealing_locks_it_again(sealed, tmp_path):
    first_public = roomlib.public_key(locks.load(sealed.root))
    result = unseal_self(sealed.root, PASSWORD, sealed.holder)
    assert result.room.changed == 3 and not result.refused
    for path, _ in roomlib.bodies(sealed.root):
        assert path.read_bytes().startswith(roomlib.PLAIN)
    plain = open_room(sealed.root, sealed.clock)
    assert not plain.locked and contents(plain) == THINGS
    Room(SelfStore.open(sealed.root, sealed.clock)).put("keepsake", "drawing", b"a drawing")
    holder = FileKeyHolder(tmp_path / "keys" / "again.key")
    again = seal_self(sealed.root, "another password", holder, sealed.clock, kdf=FAST)
    assert again.room.changed == 4
    for path, _ in roomlib.bodies(sealed.root):
        data = path.read_bytes()
        assert data.startswith(roomlib.SEALED) and b"drawing" not in data and b"grandmas" not in data
    assert roomlib.public_key(locks.load(sealed.root)) != first_public
    opened = open_room(sealed.root, sealed.clock, password="another password")
    assert contents(opened) == {**THINGS, "drawing": ("keepsake", b"a drawing")}
    assert not status(sealed.root, holder).refused


def test_a_room_filled_before_sealing_is_locked_by_sealing(tmp_path, clock):
    root = tmp_path / "self"
    store = SelfStore.open(root, clock)
    room = Room(store)
    assert not room.locked
    ids = put_all(store)
    assert {item.id for item in room.items()} == set(ids.values())
    holder = FileKeyHolder(tmp_path / "self.key")
    result = seal_self(root, PASSWORD, holder, clock, kdf=FAST)
    assert result.room.changed == 3
    for path in (root / "room").iterdir():
        data = path.read_bytes()
        assert b"grandmas" not in data and (data.startswith(roomlib.SEALED) or data.startswith(MAGIC))
    assert contents(open_room(root, clock, password=PASSWORD)) == THINGS


def test_a_swapped_room_lock_is_caught_and_put_right(sealed):
    seal = locks.load(sealed.root)
    stranger = roomlib.RoomKey.generate()
    seal["room"]["public"] = b64(stranger.public)
    locks.save(sealed.root, seal)
    late = Room(sealed.pebble()).put("photo", "taken after the swap.jpg", b"seen by the stranger")
    assert roomlib.open_body(stranger, roomlib.body_name(late.id), sealed.root.joinpath(roomlib.body_name(late.id)).read_bytes()).endswith(b"seen by the stranger")
    for item_id in sealed.ids.values():
        with pytest.raises(TamperedFile):
            roomlib.open_body(stranger, roomlib.body_name(item_id), sealed.root.joinpath(roomlib.body_name(item_id)).read_bytes())
    opened = open_room(sealed.root, sealed.clock, password=PASSWORD)
    assert opened.swapped
    problems = {thing.id: thing.problem for thing in opened.things()}
    assert "lock this room does not have" in problems[late.id]
    assert sum(1 for problem in problems.values() if problem is None) == 3
    mend_room_lock(sealed.root, opened)
    assert not open_room(sealed.root, sealed.clock, password=PASSWORD).swapped
    after = Room(sealed.pebble()).put("file", "after.txt", b"owner only again")
    assert open_room(sealed.root, sealed.clock, password=PASSWORD).take_out(after.id)[1] == b"owner only again"
    refused = status(sealed.root, sealed.holder).refused
    assert any(late.id in problem and "lock this room does not have" in problem for problem in refused)


def test_room_things_are_bound_to_their_place(sealed):
    photo, voice, keepsake = (sealed.root / roomlib.body_name(sealed.ids[name]) for name in THINGS)
    shutil.copyfile(photo, voice)
    data = bytearray(keepsake.read_bytes())
    data[-3] ^= 0x01
    keepsake.write_bytes(bytes(data))
    planted = sealed.root / roomlib.body_name("0123456789abcdef")
    planted.write_bytes(roomlib.PLAIN + roomlib.pack("0123456789abcdef", "planted", "file", "now", b"x"))
    things = {thing.id: thing for thing in open_room(sealed.root, sealed.clock, password=PASSWORD).things()}
    assert things[sealed.ids["grandmas-kitchen-1987.jpg"]].problem is None
    assert "edited or moved" in things[sealed.ids["hello.ogg"]].problem
    assert "edited or moved" in things[sealed.ids["pressed flower"]].problem
    assert "not sealed" in things["0123456789abcdef"].problem
    refused = status(sealed.root, sealed.holder).refused
    assert any("0123456789abcdef" in problem and "not sealed" in problem for problem in refused)


def test_putting_needs_a_kind_and_a_name_and_a_current_key(sealed):
    pebble = sealed.pebble()
    room = Room(pebble)
    with pytest.raises(RoomError, match="photo, voice, keepsake or file"):
        room.put("video", "clip", b"x")
    with pytest.raises(RoomError, match="needs a name"):
        room.put("photo", "  ", b"x")
    throw_away(sealed.root, PASSWORD, PHRASE, sealed.clock, sealed.holder)
    before = sorted(path.name for path in (sealed.root / "room").iterdir())
    with pytest.raises(WrongKey):
        room.put("photo", "stale.jpg", b"from a stale store")
    assert sorted(path.name for path in (sealed.root / "room").iterdir()) == before


def test_status_counts_the_room_without_a_secret(sealed, tmp_path):
    found = status(sealed.root, sealed.holder)
    assert found.room.things == 3 and found.room.kinds == {"photo": 1, "voice": 1, "keepsake": 1}
    assert found.room.size == sum(len(data) for _, data in THINGS.values())
    assert found.room.first.startswith("2026-10-15") and not found.refused
    elsewhere = room_status(sealed.root, FileKeyHolder(tmp_path / "no.key"))
    assert elsewhere.summary.things == 3 and elsewhere.summary.unread == 3 and not elsewhere.summary.kinds


def test_deleting_removes_the_thing_for_good(sealed):
    opened = open_room(sealed.root, sealed.clock, password=PASSWORD)
    target = sealed.ids["hello.ogg"]
    gone = opened.delete(target[:8])
    assert gone.name == "hello.ogg"
    assert not list((sealed.root / "room").glob(f"{target}*"))
    assert "hello.ogg" not in contents(open_room(sealed.root, sealed.clock, password=PASSWORD))
    with pytest.raises(RoomError, match="Nothing in the room"):
        opened.take_out(target)
    with pytest.raises(RoomError, match="at least 4"):
        opened.take_out("ab")
