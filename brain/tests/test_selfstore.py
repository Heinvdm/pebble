import json
import os
import zipfile

import pytest

from pebble.owner import PassphraseGate, hash_passphrase
from pebble.selfstore import BadSelfPath, LockedFile, SelfFormatTooNew, SelfStore
from pebble.selfstore import atomic
from pebble.selfstore.atomic import append_jsonl, backup_path, read_json, read_jsonl, write_json_atomic


def test_first_boot_creates_the_self_from_the_template(store, clock):
    assert store.created
    manifest = store.manifest
    assert manifest["self_format"] == 3
    for name in manifest["files"]:
        assert store.path(name).exists(), name
    core = store.read("core.json")
    assert core["birthday"] == "2026-10-15"
    assert core["first_boot_at"].startswith("2026-10-15T12:00")
    calendar = store.read("calendar.json")
    assert any(day["id"] == "rur" for day in calendar["robot_days"])


def test_reopening_keeps_the_same_self(tmp_path, clock):
    first = SelfStore.open(tmp_path / "self", clock)
    birthday = first.read("core.json")["birthday"]
    clock.advance(86400 * 3)
    second = SelfStore.open(tmp_path / "self", clock)
    assert not second.created
    assert second.read("core.json")["birthday"] == birthday


def test_interrupted_write_leaves_the_old_file_intact(tmp_path, monkeypatch):
    target = tmp_path / "memory.json"
    write_json_atomic(target, {"facts": ["old"]})

    def power_cut(*args, **kwargs):
        raise OSError("power cut")

    monkeypatch.setattr(atomic.os, "replace", power_cut)
    with pytest.raises(OSError):
        write_json_atomic(target, {"facts": ["new"]})
    monkeypatch.undo()
    assert json.loads(target.read_text(encoding="utf-8")) == {"facts": ["old"]}
    assert not list(tmp_path.glob(".*.tmp"))


def test_failure_while_writing_the_temp_file_leaves_the_old_file(tmp_path, monkeypatch):
    target = tmp_path / "memory.json"
    write_json_atomic(target, {"facts": ["old"]})
    monkeypatch.setattr(atomic.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk gone")))
    with pytest.raises(OSError):
        write_json_atomic(target, {"facts": ["new"]})
    monkeypatch.undo()
    assert read_json(target) == {"facts": ["old"]}
    assert not list(tmp_path.glob(".*.tmp"))


def test_a_corrupt_file_is_recovered_from_its_backup(tmp_path):
    target = tmp_path / "goals.json"
    write_json_atomic(target, {"v": 1})
    write_json_atomic(target, {"v": 2})
    assert read_json(backup_path(target)) == {"v": 1}
    target.write_text('{"v": 3', encoding="utf-8")
    assert read_json(target) == {"v": 1}


def test_a_corrupt_file_does_not_overwrite_a_good_backup(tmp_path):
    target = tmp_path / "goals.json"
    write_json_atomic(target, {"v": 1})
    write_json_atomic(target, {"v": 2})
    target.write_text("garbage", encoding="utf-8")
    write_json_atomic(target, {"v": 3})
    assert read_json(backup_path(target)) == {"v": 1}
    assert read_json(target) == {"v": 3}


def test_stray_temp_files_are_cleaned_on_open(tmp_path, clock):
    SelfStore.open(tmp_path / "self", clock)
    stray = tmp_path / "self" / ".goals.json.abc123.tmp"
    stray.write_text("half a file", encoding="utf-8")
    SelfStore.open(tmp_path / "self", clock)
    assert not stray.exists()


def test_the_core_is_locked(store):
    core = store.read("core.json")
    with pytest.raises(LockedFile):
        store.write("core.json", {**core, "core_purpose": "Rule the house"})
    with pytest.raises(LockedFile):
        store.write("./core.json", core)
    with pytest.raises(LockedFile):
        store.write_locked("core.json", core, None)
    assert store.read("core.json")["core_purpose"].startswith("Be a curious companion")


def test_the_owner_can_write_the_core_with_a_grant(store):
    core = store.read("core.json")
    gate = PassphraseGate(lambda: {**core, "passphrase": hash_passphrase("blue pebble", iterations=1000)})
    grant = gate.verify("blue pebble")
    store.write_locked("core.json", {**core, "core_purpose": "Be a calm desk friend."}, grant)
    assert store.read("core.json")["core_purpose"] == "Be a calm desk friend."


@pytest.mark.parametrize("name", ["../escape.json", "/etc/passwd", "C:/Windows/x.json", "a/../../b.json", ""])
def test_paths_cannot_leave_the_self(store, name):
    with pytest.raises(BadSelfPath):
        store.path(name)


def test_snapshot_zips_the_self_without_logs_and_prunes(store, clock):
    store.append("logs/monologue.jsonl", {"thought": "hm"})
    first = store.snapshot(keep=2)
    with zipfile.ZipFile(first) as archive:
        names = set(archive.namelist())
    assert "core.json" in names and "manifest.json" in names
    assert not any(name.startswith("logs/") for name in names)
    for _ in range(3):
        clock.advance(60)
        store.snapshot(keep=2)
    assert len(store.snapshots()) == 2
    assert not first.exists()


def test_a_newer_self_format_is_refused(tmp_path, clock):
    store = SelfStore.open(tmp_path / "self", clock)
    manifest = store.manifest
    manifest["self_format"] = 99
    write_json_atomic(store.path("manifest.json"), manifest)
    with pytest.raises(SelfFormatTooNew):
        SelfStore.open(tmp_path / "self", clock)


def test_a_file_added_to_the_template_appears_in_an_old_self(tmp_path, clock):
    store = SelfStore.open(tmp_path / "self", clock)
    manifest = store.manifest
    del manifest["files"]["places.json"]
    write_json_atomic(store.path("manifest.json"), manifest)
    os.remove(store.path("places.json"))
    again = SelfStore.open(tmp_path / "self", clock)
    assert again.path("places.json").exists()
    assert "places.json" in again.manifest["files"]


def test_appending_after_a_torn_line_keeps_both_records(tmp_path):
    log = tmp_path / "diary.jsonl"
    append_jsonl(log, {"n": 1})
    with open(log, "a", encoding="utf-8") as handle:
        handle.write('{"n": 2, "te')
    append_jsonl(log, {"n": 3})
    assert read_jsonl(log) == [{"n": 1}, {"n": 3}]
    assert read_jsonl(log, limit=1) == [{"n": 3}]
