import json
import subprocess
import sys
from pathlib import Path

import pytest

from pebble.books import Books
from pebble.diary import Diary
from pebble.people.company import Company
from pebble.people.fake import fake_print
from pebble.people.overnight import Overnight
from pebble.people.trust import TRUSTED
from pebble.seal import FileKeyHolder, NoOwnerLock, PHRASE, open_self, owner_store, seal_self, throw_away
from pebble.selfstore import SelfStore

BRAIN = Path(__file__).resolve().parents[1]
PASSWORD = "correct horse battery"
FAST = {"n": 2**10, "r": 8, "p": 1}


@pytest.fixture
def sealed(tmp_path, clock):
    root = tmp_path / "self"
    SelfStore.open(root, clock)
    key_file = tmp_path / "keys" / "self.key"
    seal_self(root, PASSWORD, FileKeyHolder(key_file), clock, kdf=FAST)
    return root, key_file


def meet(company, key, name):
    company.see(fake_print(key, "face"))
    heard = company.hear("hello", fake_print(key, "voice"))
    person = company.book.get(heard.person_id)
    person.set_name(name)
    return person


def test_forget_me_still_works_while_sealed_for_a_trusted_request(sealed, clock):
    root, key_file = sealed
    store = open_self(root, clock, key_file=key_file)
    assert store.sealed and store.access == "pebble"
    books = Books(store, clock)
    company = Company(books, clock)
    tui = meet(company, "tui", "Tui")
    tui.override = TRUSTED
    books.memory.remember("Tui flies kites", "now", "Tui")
    books.save_all()
    assert b"Tui" not in (root / "people.json").read_bytes()
    assert company.requests.ask("Tui", "forget_person", why="moving away").ok
    Overnight(books, store, Diary(store, clock), clock, company.presence).run(clock.local().date(), "child", "now")
    again = Books(open_self(root, clock, key_file=key_file), clock)
    assert again.people.find("Tui") is None and again.memory.facts == []
    for name in ("people.json", "memory.json", "changes.json", "diary.jsonl"):
        raw = (root / name).read_bytes()
        assert b"Tui" not in raw and b"kites" not in raw
    with pytest.raises(ValueError):
        json.loads((root / "people.json").read_bytes())
    for name in ("people.json", "memory.json"):
        (root / name).write_bytes(b"spoiled")
    reopened = open_self(root, clock, key_file=key_file)
    from_backups = Books(reopened, clock)
    assert len(reopened.tampered) >= 2
    assert from_backups.people.find("Tui") is None and from_backups.memory.facts == []
    assert from_backups.people.people == {}


def test_people_are_pebbles_own_once_the_owner_lock_is_thrown_away(sealed, clock):
    root, key_file = sealed
    throw_away(root, PASSWORD, PHRASE, clock, FileKeyHolder(key_file))
    with pytest.raises(NoOwnerLock):
        owner_store(root, PASSWORD, clock)
    store = open_self(root, clock, key_file=key_file)
    books = Books(store, clock)
    company = Company(books, clock)
    meet(company, "ina", "Ina")
    books.save("people")
    assert Books(open_self(root, clock, key_file=key_file), clock).people.find("Ina") is not None


def test_the_brain_runs_on_a_sealed_self(sealed, tmp_path):
    root, key_file = sealed
    command = [sys.executable, "-m", "pebble", "--sim", "--mind", "scripted", "--dry-run", "--self", str(root), "--key-file", str(key_file), "--beats", "3", "--heartbeat", "0.4", "--seed", "3"]
    result = subprocess.run(command, cwd=BRAIN, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-3000:]
    assert "Traceback" not in result.stderr
    lines = (root / "logs" / "blackbox.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines and not any(line.startswith("{") for line in lines)
    missing = subprocess.run(command[:-6] + ["--key-file", str(tmp_path / "nope.key"), "--beats", "1"], cwd=BRAIN, capture_output=True, text=True, timeout=120)
    assert missing.returncode == 4 and "sealed" in missing.stderr
