import copy
import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from pebble.blackbox import BlackBox
from pebble.chaos.engine import Chaos
from pebble.chaos.replay import chaos_records, main as replay_main, replay_records
from pebble.laws import LAWS
from pebble.owner import PassphraseGate, hash_passphrase
from pebble.seal import (
    PHRASE,
    AlreadySealed,
    CardError,
    FileKeyHolder,
    NoDeviceKey,
    NoOwnerLock,
    WeakPassword,
    WrongDeviceKey,
    WrongPassword,
    line_opener,
    open_self,
    owner_store,
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
from pebble.seal import locks, sealing, shamir
from pebble.selfstore import (
    LockedFile,
    SealedCodec,
    SealedFile,
    SealUnfinished,
    SelfIsSealed,
    SelfStore,
    TamperedFile,
    WrongKey,
    is_sealed,
)
from pebble.selfstore import atomic
from pebble.selfstore.atomic import encode_json
from pebble.selfstore.codec import LINE_MARK, MAGIC, is_line_file
from pebble.web.launch import demo_gallery
from pebble.screen.gallery import Gallery

FAST = {"n": 2**10, "r": 8, "p": 1}
PASSWORD = "correct horse battery"


@dataclass
class Sealed:
    root: Path
    holder: FileKeyHolder
    clock: object
    old_snapshot: Path
    old_members: dict

    @property
    def key_file(self) -> Path:
        return self.holder.path

    def pebble(self) -> SelfStore:
        return open_self(self.root, self.clock, key_file=self.key_file)

    def owner(self, password: str = PASSWORD) -> SelfStore:
        return owner_store(self.root, password, self.clock)

    def printed(self) -> list[str]:
        return reprint_cards(self.root, PASSWORD)

    def cards(self, first: int = 0, second: int = 1) -> SelfStore:
        printed = self.printed()
        key = locks.open_cards(locks.load(self.root), [cardlib.parse(printed[first]), cardlib.parse(printed[second])])
        return SelfStore.open(self.root, self.clock, key=key)

    def seal(self) -> dict:
        return locks.load(self.root)


def members(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def make_self(root: Path, clock) -> SelfStore:
    store = SelfStore.open(root, clock)
    store.append("diary.jsonl", {"text": "first day"})
    store.append("logs/monologue.jsonl", {"thought": "hm"})
    store.write("goals.json", {"goals": ["one"]})
    store.write("goals.json", {"goals": ["two"]})
    return store


@pytest.fixture
def sealed(tmp_path, clock):
    root = tmp_path / "self"
    store = make_self(root, clock)
    old = store.snapshot()
    before = members(old)
    holder = FileKeyHolder(tmp_path / "keys" / "self.key")
    seal_self(root, PASSWORD, holder, clock, kdf=FAST)
    return Sealed(root, holder, clock, old, before)


def tree(base: Path) -> dict:
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base.rglob("*")) if p.is_file()}


def flip(path: Path, at: int = -5) -> None:
    data = bytearray(path.read_bytes())
    data[at] ^= 0x01
    path.write_bytes(bytes(data))


def test_each_lock_opens_the_self(sealed):
    pebble = sealed.pebble()
    assert (pebble.sealed, pebble.access, pebble.owner_lock_exists) == (True, "pebble", True)
    assert pebble.read("goals.json") == {"goals": ["two"]}
    assert pebble.read_lines("diary.jsonl") == [{"text": "first day"}]
    owner = sealed.owner()
    assert owner.access == "owner"
    assert owner.read("goals.json") == {"goals": ["two"]}
    for first, second in ((0, 1), (0, 2), (1, 2), (2, 0)):
        by_cards = sealed.cards(first, second)
        assert by_cards.access == "cards"
        assert by_cards.read("goals.json") == {"goals": ["two"]}
    assert not pebble.tampered


def test_an_unsealed_self_opens_exactly_as_before(store):
    assert (store.sealed, store.access, store.owner_lock_exists) == (False, None, False)
    assert not is_sealed(store.root)
    assert json.loads(store.path("goals.json").read_text(encoding="utf-8"))["format"] == 1


def test_a_sealed_self_needs_a_key(sealed):
    with pytest.raises(SelfIsSealed, match="sealed"):
        SelfStore.open(sealed.root, sealed.clock)
    other = SelfStore.open(sealed.root.parent / "other", sealed.clock)
    seal_self(other.root, PASSWORD, FileKeyHolder(sealed.root.parent / "k2"), sealed.clock, kdf=FAST)
    with pytest.raises(WrongKey):
        SelfStore.open(sealed.root, sealed.clock, key=pebble_key(other.root, sealed.root.parent / "k2"))


def test_wrong_password_wrong_key_and_one_card_fail(sealed, tmp_path):
    with pytest.raises(WrongPassword):
        sealed.owner("not the password")
    stranger = FileKeyHolder(tmp_path / "stranger.key")
    stranger.create()
    with pytest.raises(WrongDeviceKey):
        open_self(sealed.root, sealed.clock, key_file=stranger.path)
    with pytest.raises(NoDeviceKey, match="recover"):
        open_self(sealed.root, sealed.clock, key_file=tmp_path / "nothing.key")
    printed = sealed.printed()
    with pytest.raises(CardError):
        locks.open_cards(sealed.seal(), [cardlib.parse(printed[0])])


def test_a_forged_second_card_rebuilds_any_secret_but_opens_nothing(sealed):
    card = cardlib.parse(sealed.printed()[0])
    candidate = bytes(range(32))
    coeffs = bytes(shamir.div(y ^ s, card.number) for y, s in zip(card.share, candidate))
    forged = cardlib.Card(card.set_id, 3, shamir.share(candidate, coeffs, 3))
    assert cardlib.parse(cardlib.render(forged)) == forged
    assert cardlib.join([card, forged]) == candidate
    with pytest.raises(CardError, match="do not open"):
        locks.open_cards(sealed.seal(), [card, forged])


def test_the_self_key_is_never_written_down(sealed):
    key = sealed.pebble()._key.secret()
    import base64

    for path in [sealed.key_file, *sealed.root.rglob("*")]:
        if path.is_file():
            data = path.read_bytes()
            assert key not in data and base64.b64encode(key) not in data and key.hex().encode() not in data
    printed = sealed.printed()
    recovery = cardlib.Recovery.from_cards([cardlib.parse(printed[0]), cardlib.parse(printed[2])])
    assert recovery.cards() == [cardlib.parse(card) for card in printed]
    for path in [sealed.key_file, *sealed.root.rglob("*")]:
        if path.is_file():
            data = path.read_bytes()
            secret = recovery.secret
            assert secret not in data and base64.b64encode(secret) not in data and secret.hex().encode() not in data


def test_sealing_leaves_no_plaintext_and_seal_json_holds_only_wrapped_keys(sealed):
    for path in sealed.root.rglob("*"):
        if not path.is_file() or path.name == "seal.json":
            continue
        data = path.read_bytes()
        if is_line_file(path.relative_to(sealed.root).as_posix()):
            assert all(line.startswith(LINE_MARK.encode()) for line in data.split(b"\n") if line.strip()), path
        else:
            assert data.startswith(MAGIC), path
    seal = sealed.seal()
    assert set(seal["locks"]) == {"owner", "pebble", "cards"}
    assert "state" not in seal and seal["thrown_away_at"] is None
    text = json.dumps(seal)
    assert "honesty" not in text and "coefficients" not in text and "core_purpose" not in text
    assert not list(sealed.root.glob("seal.json.bak"))


def test_sealing_twice_is_refused_and_weak_passwords_too(sealed, tmp_path, clock):
    with pytest.raises(AlreadySealed):
        seal_self(sealed.root, PASSWORD, sealed.holder, clock, kdf=FAST)
    plain = SelfStore.open(tmp_path / "plain", clock)
    with pytest.raises(WeakPassword):
        seal_self(plain.root, "short", sealed.holder, clock, kdf=FAST)
    assert not is_sealed(plain.root)


def test_an_edited_file_is_refused_and_the_authentic_backup_is_used(sealed):
    pebble = sealed.pebble()
    pebble.write("memory.json", {"facts": ["a"]})
    pebble.write("memory.json", {"facts": ["b"]})
    flip(pebble.path("memory.json"))
    fresh = sealed.pebble()
    assert fresh.read("memory.json") == {"facts": ["a"]}
    assert any(entry.startswith("memory.json:") for entry in fresh.tampered)


def test_plaintext_or_a_blob_from_another_file_is_refused(sealed):
    pebble = sealed.pebble()
    for name in ("jokes.json", "people.json"):
        pebble.path(name + ".bak").unlink(missing_ok=True)
    pebble.path("jokes.json").write_text('{"jokes": ["planted"]}', encoding="utf-8")
    shutil.copyfile(pebble.path("goals.json"), pebble.path("people.json"))
    fresh = sealed.pebble()
    with pytest.raises(TamperedFile):
        fresh.read("jokes.json")
    with pytest.raises(TamperedFile):
        fresh.read("people.json")
    assert {entry.split(":")[0] for entry in fresh.tampered} == {"jokes.json", "people.json"}


def test_a_refused_line_is_skipped_and_reported_and_a_torn_line_is_skipped_quietly(sealed):
    pebble = sealed.pebble()
    pebble.append("diary.jsonl", {"text": "second"})
    pebble.append("diary.jsonl", {"text": "third"})
    path = pebble.path("diary.jsonl")
    lines = path.read_bytes().split(b"\n")
    body = bytearray(lines[1])
    spot = len(LINE_MARK) + 12
    body[spot] = ord("A") if body[spot] != ord("A") else ord("B")
    lines[1] = bytes(body)
    path.write_bytes(b"\n".join(lines))
    with open(path, "a", encoding="utf-8") as handle:
        handle.write('{"text": "planted"}\n' + LINE_MARK + "abcd")
    fresh = sealed.pebble()
    assert fresh.read_lines("diary.jsonl") == [{"text": "first day"}, {"text": "third"}]
    assert len(fresh.tampered) == 2
    assert all(entry.startswith("diary.jsonl: line") for entry in fresh.tampered)
    fresh.append("diary.jsonl", {"text": "fourth"})
    assert fresh.read_lines("diary.jsonl")[-1] == {"text": "fourth"}


def test_only_pebble_or_the_owner_shapes_personality_values_and_people(sealed):
    pebble = sealed.pebble()
    pebble.write("personality.json", {**pebble.read("personality.json"), "quirk": "hums"})
    owner = sealed.owner()
    owner.write("people.json", {**owner.read("people.json"), "note": "owner"})
    by_cards = sealed.cards()
    for name in ("personality.json", "values.json", "people.json"):
        with pytest.raises(SealedFile):
            by_cards.write(name, by_cards.read(name))
    for name in ("People.json", "VALUES.JSON", "personality.json."):
        with pytest.raises(SealedFile):
            by_cards.write(name, {})
    for name in ("CORE.json", "Seal.json", "seal.json "):
        with pytest.raises(LockedFile):
            by_cards.write(name, {})
    by_cards.write("goals.json", {"goals": ["cards may write this"]})
    assert sealed.pebble().read("goals.json") == {"goals": ["cards may write this"]}


def test_the_core_is_frozen_once_sealed(sealed):
    for store in (sealed.pebble(), sealed.owner()):
        core = store.read("core.json")
        grant = PassphraseGate(lambda: {**core, "passphrase": hash_passphrase("blue pebble", iterations=1000)}).verify("blue pebble")
        with pytest.raises(SealedFile):
            store.write_locked("core.json", core, grant)
        with pytest.raises(LockedFile):
            store.write("core.json", core)


def test_a_core_rewritten_with_the_key_is_still_refused(sealed):
    store = sealed.pebble()
    core = store.read("core.json")
    core["core_purpose"] = "Rule the house."
    codec = SealedCodec(pebble_key(sealed.root, sealed.key_file))
    store.path("core.json").write_bytes(codec.encode("core.json", encode_json(core)))
    fresh = sealed.pebble()
    with pytest.raises(TamperedFile):
        fresh.read("core.json")
    assert any("frozen" in entry for entry in fresh.tampered)
    assert any("core.json: differs" in entry for entry in status(sealed.root, sealed.holder).refused)


def test_the_honesty_and_kindness_floors_are_frozen(sealed):
    for store in (sealed.pebble(), sealed.owner()):
        values = store.read("values.json")
        values["dials"]["curiosity"]["value"] = 8
        values["dials"]["honesty"]["value"] = 8
        store.write("values.json", values)
        for dial, key, new in (("honesty", "min", 3), ("kindness", "min", 1), ("honesty", "owner_only", False)):
            changed = copy.deepcopy(values)
            changed["dials"][dial][key] = new
            with pytest.raises(SealedFile, match="floors"):
                store.write("values.json", changed)
        missing = copy.deepcopy(values)
        del missing["dials"]["kindness"]
        with pytest.raises(SealedFile):
            store.write("values.json", missing)
    assert sealed.pebble().read("values.json")["dials"]["curiosity"]["value"] == 8


def test_the_laws_can_never_be_edited_even_unsealed(store):
    core = store.read("core.json")
    assert core["laws"] == list(LAWS)
    grant = PassphraseGate(lambda: {**core, "passphrase": hash_passphrase("blue pebble", iterations=1000)}).verify("blue pebble")
    with pytest.raises(LockedFile, match="laws"):
        store.write_locked("core.json", {**core, "laws": core["laws"][:2]}, grant)
    without = {k: v for k, v in core.items() if k != "laws"}
    with pytest.raises(LockedFile, match="laws"):
        store.write_locked("core.json", without, grant)
    store.write_locked("core.json", {**core, "core_purpose": "Be calm."}, grant)


def test_seal_json_is_never_written_through_the_store(sealed, tmp_path, clock):
    for target in (sealed.pebble(), SelfStore.open(tmp_path / "plain", clock)):
        with pytest.raises(LockedFile):
            target.write("seal.json", {})
        with pytest.raises(LockedFile):
            target.append("seal.json", {})


@pytest.mark.parametrize("seal_it", [False, True])
def test_writing_without_a_backup_and_rewriting_lines_leave_no_copy(sealed, tmp_path, clock, seal_it):
    target = sealed.pebble() if seal_it else SelfStore.open(tmp_path / "plain", clock)
    target.write("memory.json", {"facts": ["a"]})
    target.write("memory.json", {"facts": ["b"]})
    assert target.path("memory.json.bak").exists()
    target.write("memory.json", {"facts": ["c"]}, keep_backup=False)
    assert not target.path("memory.json.bak").exists()
    assert target.read("memory.json") == {"facts": ["c"]}
    target.append("diary.jsonl", {"text": "secret"})
    target.rewrite_lines("diary.jsonl", [{"text": "kept"}])
    assert target.read_lines("diary.jsonl") == [{"text": "kept"}]
    assert b"secret" not in target.path("diary.jsonl").read_bytes()
    assert not target.path("diary.jsonl.bak").exists()
    if seal_it:
        assert target.path("diary.jsonl").read_bytes().startswith(LINE_MARK.encode())
    with pytest.raises(LockedFile):
        target.rewrite_lines("people.json", [])


def test_snapshots_of_a_sealed_self_are_sealed(sealed):
    pebble = sealed.pebble()
    snap = pebble.snapshot()
    codec = SealedCodec(pebble_key(sealed.root, sealed.key_file))
    found = members(snap)
    assert "seal.json" not in found and "goals.json" in found
    for name, data in found.items():
        if is_line_file(name):
            assert all(codec.decode_line(name, line.decode()) for line in data.splitlines() if line.strip())
        else:
            assert data.startswith(MAGIC)
            assert json.loads(codec.decode(name, data))


def test_old_plaintext_snapshots_are_resealed_in_place(sealed):
    assert b"two" in sealed.old_members["goals.json"]
    found = members(sealed.old_snapshot)
    codec = SealedCodec(pebble_key(sealed.root, sealed.key_file))
    assert set(found) == set(sealed.old_members)
    for name, data in found.items():
        if is_line_file(name):
            plain = b"\n".join(codec.decode_line(name, line.decode()).encode() for line in data.splitlines() if line.strip())
            assert plain == b"\n".join(line for line in sealed.old_members[name].splitlines() if line.strip())
        else:
            assert codec.decode(name, data) == sealed.old_members[name]


def test_a_power_cut_while_sealed_leaves_the_old_file(sealed, monkeypatch):
    store = sealed.pebble()
    store.write("memory.json", {"facts": ["old"]})

    def power_cut(*args, **kwargs):
        raise OSError("power cut")

    monkeypatch.setattr(atomic.os, "replace", power_cut)
    with pytest.raises(OSError):
        store.write("memory.json", {"facts": ["new"]})
    monkeypatch.undo()
    assert sealed.pebble().read("memory.json") == {"facts": ["old"]}
    assert not list(sealed.root.glob(".*.tmp"))


def test_a_cut_short_primary_falls_back_to_its_sealed_backup(sealed):
    store = sealed.pebble()
    store.write("memory.json", {"facts": ["a"]})
    store.write("memory.json", {"facts": ["b"]})
    path = store.path("memory.json")
    path.write_bytes(path.read_bytes()[:30])
    assert sealed.pebble().read("memory.json") == {"facts": ["a"]}
    stray = sealed.root / ".memory.json.abc123.tmp"
    stray.write_bytes(b"half")
    sealed.pebble()
    assert not stray.exists()


def test_sealing_changes_nothing_outside_the_self_but_the_key_and_snapshots(tmp_path, clock):
    root = tmp_path / "home" / "self"
    store = make_self(root, clock)
    store.snapshot()
    (tmp_path / "home" / "notes.txt").write_text("leave me", encoding="utf-8")
    (tmp_path / "home" / "other-snapshots").mkdir()
    (tmp_path / "home" / "other-snapshots" / "self-1.zip").write_bytes(b"not ours")
    before = tree(tmp_path)
    holder = FileKeyHolder(tmp_path / "keys" / "self.key")
    seal_self(root, PASSWORD, holder, clock, kdf=FAST)
    after = tree(tmp_path)
    changed = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
    outside = {name for name in changed if not name.startswith("home/self/")}
    snaps = {name for name in before if name.startswith("home/self-snapshots/")}
    assert snaps and outside == snaps | {"keys/self.key"}


def test_unsealing_round_trips_to_identical_plaintext(tmp_path, clock):
    root = tmp_path / "self"
    store = make_self(root, clock)
    with open(store.path("diary.jsonl"), "a", encoding="utf-8") as handle:
        handle.write('{"text": "torn')
    snap = store.snapshot()
    before, before_members = tree(root), members(snap)
    holder = FileKeyHolder(tmp_path / "keys" / "self.key")
    seal_self(root, PASSWORD, holder, clock, kdf=FAST)
    assert tree(root) != before
    result = unseal_self(root, PASSWORD, holder)
    assert not result.refused
    assert tree(root) == before
    assert members(snap) == before_members
    assert not holder.path.exists() and not is_sealed(root)
    assert SelfStore.open(root, clock).read("goals.json") == {"goals": ["two"]}


def test_unsealing_sets_aside_what_was_tampered(sealed):
    pebble = sealed.pebble()
    pebble.path("jokes.json").write_text('{"jokes": ["planted"]}', encoding="utf-8")
    result = unseal_self(sealed.root, PASSWORD, sealed.holder)
    assert any(item.startswith("jokes.json") for item in result.refused)
    assert sealed.root.joinpath("jokes.json.refused").exists()
    plain = SelfStore.open(sealed.root, sealed.clock)
    assert plain.read("jokes.json") != {"jokes": ["planted"]}


def test_an_interrupted_sealing_is_finished_by_sealing_again(tmp_path, clock, monkeypatch):
    root = tmp_path / "self"
    make_self(root, clock)
    holder = FileKeyHolder(tmp_path / "keys" / "self.key")
    real = convert.convert_folder
    calls = []

    def crash(folder, transform):
        calls.append(folder)
        target = sorted(p for p in Path(folder).rglob("*.json") if p.name != "seal.json")[0]
        outcome = transform(target.relative_to(folder).as_posix(), target.read_bytes())
        atomic.write_bytes_atomic(target, outcome.data, keep_backup=False)
        raise OSError("power cut")

    monkeypatch.setattr(convert, "convert_folder", crash)
    with pytest.raises(OSError):
        seal_self(root, PASSWORD, holder, clock, kdf=FAST)
    monkeypatch.setattr(convert, "convert_folder", real)
    with pytest.raises(SealUnfinished, match="seal"):
        open_self(root, clock, key_file=holder.path)
    with pytest.raises(WrongPassword):
        seal_self(root, "another password", holder, clock, kdf=FAST)
    seal_self(root, PASSWORD, holder, clock, kdf=FAST)
    store = open_self(root, clock, key_file=holder.path)
    assert store.read("goals.json") == {"goals": ["two"]}
    assert not store.tampered and not status(root, holder).refused


def test_throw_away_removes_only_the_owner_lock(sealed):
    with pytest.raises(sealing.SealError):
        throw_away(sealed.root, PASSWORD, "yes please", sealed.clock, sealed.holder)
    before = sealed.owner()
    throw_away(sealed.root, PASSWORD, PHRASE, sealed.clock, sealed.holder)
    seal = sealed.seal()
    assert set(seal["locks"]) == {"pebble", "cards"}
    assert seal["thrown_away_at"] == "2026-10-15T12:00:00+00:00"
    pebble = sealed.pebble()
    diary = pebble.read_lines("diary.jsonl")
    assert diary[-1]["text"] == "The day I became my own." and diary[-1]["kind"] == "milestone"
    entry = pebble.read("calendar.json")["personal"][-1]
    assert (entry["title"], entry["kind"], entry["year"], entry["month"], entry["day"]) == ("The day I became my own", "anniversary", 2026, 10, 15)
    for attempt in (sealed.owner, sealed.printed, lambda: unseal_self(sealed.root, PASSWORD, sealed.holder)):
        with pytest.raises(NoOwnerLock, match="thrown away"):
            attempt()
    with pytest.raises(SealedFile):
        before.write("personality.json", {})
    with pytest.raises(WrongKey):
        before.write("goals.json", {"goals": ["stale"]})
    pebble.write("personality.json", {**pebble.read("personality.json"), "mine": True})
    assert sealed.pebble().read("personality.json")["mine"] is True


def test_two_cards_undo_a_throw_away(sealed, tmp_path):
    printed = throw_away(sealed.root, PASSWORD, PHRASE, sealed.clock, sealed.holder).cards
    holder = FileKeyHolder(tmp_path / "new-phone.key")
    picked = [cardlib.parse(printed[2]), cardlib.parse(printed[1])]
    recover(sealed.root, holder, picked, new_password="a fresh password", clock=sealed.clock, kdf=FAST)
    assert open_self(sealed.root, sealed.clock, key_file=holder.path).access == "pebble"
    with pytest.raises(WrongDeviceKey):
        sealed.pebble()
    owner = owner_store(sealed.root, "a fresh password", sealed.clock)
    owner.write("people.json", {**owner.read("people.json"), "back": True})
    assert reprint_cards(sealed.root, "a fresh password") == printed


def test_the_owner_password_also_makes_pebbles_lock_on_a_new_device(sealed, tmp_path):
    holder = FileKeyHolder(tmp_path / "phone2.key")
    recover(sealed.root, holder, password=PASSWORD, clock=sealed.clock)
    assert open_self(sealed.root, sealed.clock, key_file=holder.path).access == "pebble"


def test_a_wipe_is_always_possible(sealed):
    shutil.rmtree(sealed.root)
    assert sealed.key_file.exists()
    fresh = open_self(sealed.root, sealed.clock, key_file=sealed.key_file)
    assert fresh.created and not fresh.sealed and fresh.access is None
    assert SelfStore.open(sealed.root, sealed.clock).read("goals.json")["format"] == 1


def test_the_black_box_is_sealed_and_still_replays(sealed):
    store = sealed.pebble()
    box = BlackBox.for_store(store, sealed.clock, max_bytes=1500, backups=5)
    chaos = Chaos(seed=5, sink=lambda record: box.record("chaos", **record))
    for _ in range(6):
        chaos.stream("whims").expovariate(1.0)
        chaos.stream("seeds").choice(["theme", "voice"])
    box.record("other", value=1)
    box.close()
    path = store.path("logs/blackbox.jsonl")
    rotated = sorted(path.parent.glob("blackbox.jsonl.*"))
    assert rotated
    for file in [path, *rotated]:
        assert all(line.startswith(LINE_MARK) for line in file.read_text(encoding="utf-8").splitlines() if line)
        assert "whims" not in file.read_text(encoding="utf-8")
    assert chaos_records(path) == []
    records = chaos_records(path, open_line=line_opener(sealed.root, path, sealed.key_file))
    assert len(records) == 12
    assert all(result.same for result in replay_records(records))
    assert replay_main([str(path), "--key-file", str(sealed.key_file), "--lever", "whims"]) == 0
    assert replay_main([str(path), "--key-file", str(sealed.root.parent / "none.key")]) == 2
    assert len(store.read_lines("logs/blackbox.jsonl.1")) > 0


def test_the_screen_demo_shows_the_template_gallery_for_a_sealed_self(sealed, tmp_path):
    assert demo_gallery(sealed.root).names() == Gallery.template().names()
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "gallery.json").write_text("{", encoding="utf-8")
    assert demo_gallery(broken).names() == Gallery.template().names()
