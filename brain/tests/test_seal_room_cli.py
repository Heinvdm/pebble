import pytest

from pebble.seal import PHRASE, SAVED, Room, locks, open_self
from pebble.seal import room as roomlib
from pebble.seal.cli import Prompts, main
from pebble.selfstore import SelfStore
from pebble.selfstore.sealed import b64

PASSWORD = "correct horse battery"


class Script:
    def __init__(self, *answers):
        self.answers = list(answers)

    def __call__(self, question):
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)


def prompts(*answers) -> Prompts:
    script = Script(*answers)
    return Prompts(secret=script, line=script)


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    monkeypatch.setitem(locks.OWNER_KDF, "n", 2**10)
    monkeypatch.delenv("PEBBLE_KEY_HOLDER", raising=False)


@pytest.fixture
def paths(tmp_path, clock):
    root = tmp_path / "self"
    SelfStore.open(root, clock).append("diary.jsonl", {"text": "hello"})
    return root, tmp_path / "keys" / "self.key"


def run(paths, clock, *argv, answers=()):
    root, key = paths
    return main([*argv, "--self", str(root), "--key-file", str(key)], prompts(*answers), clock)


def room(paths, clock, action, *rest, answers=()):
    root, key = paths
    return main(["room", action, "--self", str(root), "--key-file", str(key), *rest], prompts(*answers), clock)


def sealed(paths, clock, capsys):
    assert run(paths, clock, "seal", answers=(PASSWORD, PASSWORD)) == 0
    out = capsys.readouterr().out
    assert "The locked room (room/ in the self) opens only with the owner's password or two recovery cards" in out


def cards(paths, clock, capsys) -> list[str]:
    assert run(paths, clock, "cards", answers=(PASSWORD,)) == 0
    out = capsys.readouterr().out
    return ["PEBBLE RECOVERY CARD" + part for part in out.split("PEBBLE RECOVERY CARD")[1:]]


def id_of(out: str, name: str) -> str:
    return next(line.split()[0] for line in out.splitlines() if line.rstrip().endswith(name) and roomlib.is_id(line.split()[0]))


def test_the_room_through_the_cli(paths, clock, capsys, tmp_path):
    sealed(paths, clock, capsys)
    printed = cards(paths, clock, capsys)
    assert "its locked room" in printed[0]
    photo = tmp_path / "beach-day.jpg"
    photo.write_bytes(b"\xff\xd8 a day at the beach " * 50)
    note = tmp_path / "note.txt"
    note.write_bytes(b"from Ina, with love")
    assert room(paths, clock, "put", str(photo)) == 0
    out = capsys.readouterr().out
    assert "Put beach-day.jpg in the locked room (photo " in out and "Pebble cannot open it again" in out
    assert room(paths, clock, "put", str(note), "--kind", "keepsake", "--name", "a note from Ina") == 0
    capsys.readouterr()
    assert room(paths, clock, "status") == 0
    out = capsys.readouterr().out
    assert "holds:       2 things (1 photo, 1 keepsake" in out and "2026-10-15" in out
    assert "opens with:  the owner's password or two recovery cards; Pebble only puts things in" in out
    assert run(paths, clock, "status") == 0
    assert "locked room:       2 things (1 photo, 1 keepsake" in capsys.readouterr().out
    assert room(paths, clock, "list", answers=("wrong password",)) == 1
    assert "does not open" in capsys.readouterr().err
    assert room(paths, clock, "list", answers=(PASSWORD,)) == 0
    out = capsys.readouterr().out
    assert "The room holds 2 things:" in out and "beach-day.jpg" in out and "a note from Ina" in out
    photo_id, note_id = id_of(out, "beach-day.jpg"), id_of(out, "a note from Ina")
    outbox = tmp_path / "out"
    outbox.mkdir()
    assert room(paths, clock, "take-out", photo_id[:6], "--to", str(outbox), answers=(PASSWORD,)) == 0
    assert "It is still in the room" in capsys.readouterr().out
    assert (outbox / "beach-day.jpg").read_bytes() == photo.read_bytes()
    assert room(paths, clock, "take-out", photo_id, "--to", str(outbox), answers=(PASSWORD,)) == 1
    assert "already exists" in capsys.readouterr().err
    assert room(paths, clock, "delete", note_id, answers=(PASSWORD, "no")) == 1
    assert "Nothing was deleted" in capsys.readouterr().err
    assert room(paths, clock, "delete", note_id, "--cards", answers=(printed[0], printed[2], "yes")) == 0
    assert 'Deleted "a note from Ina"' in capsys.readouterr().out
    assert room(paths, clock, "list", "--cards", answers=(printed[1], printed[2])) == 0
    out = capsys.readouterr().out
    assert "The room holds 1 thing:" in out and "a note from Ina" not in out


def test_after_throw_away_the_room_asks_for_the_new_cards(paths, clock, capsys, tmp_path):
    sealed(paths, clock, capsys)
    old = cards(paths, clock, capsys)
    clip = tmp_path / "hello.ogg"
    clip.write_bytes(b"OggS hello")
    assert room(paths, clock, "put", str(clip)) == 0
    capsys.readouterr()
    assert run(paths, clock, "throw-away", answers=(PASSWORD, PASSWORD, PHRASE, SAVED)) == 0
    out = capsys.readouterr().out
    assert "The locked room gets a new lock as well" in out and "only the new cards open what is in it" in out
    new = ["PEBBLE RECOVERY CARD" + part for part in out.split("PEBBLE RECOVERY CARD")[1:]]
    assert room(paths, clock, "list", answers=(old[0], old[1])) == 1
    assert "stop working" in capsys.readouterr().err
    assert room(paths, clock, "list", answers=(new[0], new[1])) == 0
    out = capsys.readouterr().out
    assert "two recovery cards open the room" in out and "hello.ogg" in out and "voice clip" in out
    assert room(paths, clock, "status") == 0
    assert "two recovery cards (the owner's lock was thrown away)" in capsys.readouterr().out


def test_a_swapped_room_lock_is_reported_and_put_right(paths, clock, capsys, tmp_path):
    sealed(paths, clock, capsys)
    seal = locks.load(paths[0])
    seal["room"]["public"] = b64(roomlib.RoomKey.generate().public)
    locks.save(paths[0], seal)
    Room(open_self(paths[0], clock, key_file=paths[1])).put("photo", "after the swap.jpg", b"x")
    assert room(paths, clock, "status") == 0
    assert room(paths, clock, "list", answers=(PASSWORD,)) == 1
    out = capsys.readouterr().out
    assert "WARNING: the room's lock in seal.json was not the room's own" in out
    assert "cannot be opened: room/" in out and "lock this room does not have" in out
    assert room(paths, clock, "status") == 1
    assert "sealed to a lock this room does not have" in capsys.readouterr().out


def test_the_room_of_an_unsealed_self_is_plain_and_needs_no_password(paths, clock, capsys, tmp_path):
    thing = tmp_path / "drawing.png"
    thing.write_bytes(b"PNG drawing")
    assert room(paths, clock, "put", str(thing)) == 0
    assert "the room is not locked" in capsys.readouterr().out
    assert room(paths, clock, "status") == 0
    assert "is not sealed, so its room is not locked: 1 thing" in capsys.readouterr().out
    assert room(paths, clock, "list") == 0
    assert "drawing.png" in capsys.readouterr().out
    assert room(paths, clock, "put", str(tmp_path / "missing.png")) == 1
    assert "cannot be read" in capsys.readouterr().err
    root, key = paths
    assert main(["room", "status", "--self", str(tmp_path / "nowhere")], prompts(), clock) == 1
    assert main(["room", "put", str(thing), "--self", str(tmp_path / "nowhere"), "--key-file", str(key)], prompts(), clock) == 1
    assert not (tmp_path / "nowhere").exists()
