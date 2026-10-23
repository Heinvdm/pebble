import json
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from pebble.blackbox import BlackBox
from pebble.chaos.engine import Chaos
from pebble.chaos.replay import main as replay_main
from pebble.seal import (
    AndroidKeystoreHolder,
    FileKeyHolder,
    KeystoreUnavailable,
    Room,
    holder_for,
    locks,
    move_lock,
    open_room,
    open_self,
    seal_self,
    status,
    unseal_self,
)
from pebble.seal import keys
from pebble.seal.cli import Prompts, main
from pebble.seal.errors import DeviceKeyDamaged, SealError
from pebble.selfstore import SelfStore

FAST = {"n": 2**10, "r": 8, "p": 1}
PASSWORD = "correct horse battery"


class FakeKeystore:
    def __init__(self, steady: bool = True, needs_unlock: bool = False, secure: bool = True):
        self.keys = {}
        self.calls = []
        self.steady = steady
        self.needs_unlock = needs_unlock
        self.secure = secure

    def __call__(self, args: list[str], data: bytes = b"") -> bytes:
        self.calls.append((list(args), bytes(data)))
        command = args[0]
        if command == "list":
            return json.dumps([
                {
                    "alias": alias,
                    "algorithm": "RSA",
                    "size": 2048,
                    "inside_secure_hardware": self.secure,
                    "user_authentication": {"required": self.needs_unlock, "enforced_by_secure_hardware": True},
                }
                for alias in self.keys
            ]).encode("utf-8")
        if command == "generate":
            assert args[2:] == ["-a", "RSA", "-s", "2048"] and "-u" not in args
            self.keys[args[1]] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            return b""
        if command == "sign":
            assert args[2] == "SHA256withRSA"
            key = self.keys.get(args[1])
            if key is None:
                return b""
            if self.steady:
                return key.sign(data, padding.PKCS1v15(), hashes.SHA256())
            return key.sign(data, padding.PSS(padding.MGF1(hashes.SHA256()), padding.PSS.MAX_LENGTH), hashes.SHA256())
        if command == "delete":
            self.keys.pop(args[1], None)
            return b""
        raise AssertionError(args)


@pytest.fixture
def keystore(monkeypatch):
    fake = FakeKeystore()
    monkeypatch.setattr(keys, "termux_keystore", fake)
    return fake


@pytest.fixture(autouse=True)
def no_holder_env(monkeypatch):
    monkeypatch.delenv("PEBBLE_KEY_HOLDER", raising=False)
    monkeypatch.delenv("PEBBLE_KEY_FILE", raising=False)


def test_the_keystore_holder_makes_one_rsa_key_and_reuses_it(keystore):
    holder = AndroidKeystoreHolder()
    assert holder.where() == "the phone's keystore (alias pebble-self)"
    assert holder.load() is None
    key = holder.load_or_create()
    assert len(key) == 32 and holder.load() == key and holder.load_or_create() == key
    signs = [(args, data) for args, data in keystore.calls if args[0] == "sign"]
    assert signs and all(args == ["sign", "pebble-self", "SHA256withRSA"] and data == keys.SIGN_TEXT for args, data in signs)
    assert [args for args, _ in keystore.calls if args[0] == "generate"] == [["generate", "pebble-self", "-a", "RSA", "-s", "2048"]]
    assert holder.secure_hardware() is True
    assert AndroidKeystoreHolder("other").load_or_create() != key
    fresh = holder.create()
    assert fresh != key and holder.load() == fresh
    holder.delete()
    assert holder.load() is None


def test_a_keystore_key_that_signs_differently_each_time_is_refused(keystore):
    keystore.steady = False
    with pytest.raises(DeviceKeyDamaged, match="two different answers"):
        AndroidKeystoreHolder().load_or_create()
    assert keystore.keys == {}


def test_a_keystore_key_that_needs_the_screen_unlocked_is_refused(keystore):
    keystore.needs_unlock = True
    keystore("generate pebble-self -a RSA -s 2048".split())
    with pytest.raises(DeviceKeyDamaged, match="screen unlocked"):
        AndroidKeystoreHolder().load()


def test_missing_termux_api_or_no_answer_is_said_plainly(monkeypatch):
    monkeypatch.setattr(keys, "KEYSTORE_PROGRAM", "termux-keystore-that-is-not-here")
    with pytest.raises(KeystoreUnavailable) as missing:
        AndroidKeystoreHolder().load()
    text = str(missing.value)
    assert "pkg install termux-api" in text and "Termux:API app" in text and "postmarketOS" in text and "--key-holder file" in text
    monkeypatch.setattr(keys, "KEYSTORE_PROGRAM", sys.executable)
    with pytest.raises(KeystoreUnavailable, match="termux-keystore list failed"):
        AndroidKeystoreHolder().load()

    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], keys.KEYSTORE_TIMEOUT)

    monkeypatch.setattr(keys.subprocess, "run", hang)
    with pytest.raises(KeystoreUnavailable, match="did not answer.*Termux:API app"):
        AndroidKeystoreHolder().load()


def test_garbage_from_the_keystore_is_not_taken_for_a_key():
    holder = AndroidKeystoreHolder(run=lambda args, data=b"": b"<html>not json</html>")
    with pytest.raises(KeystoreUnavailable, match="did not give a list of keys"):
        holder.load()
    silent = FakeKeystore()
    silent("generate pebble-self -a RSA -s 2048".split())
    holder = AndroidKeystoreHolder(run=lambda args, data=b"": b"" if args[0] == "sign" else silent(args, data))
    with pytest.raises(KeystoreUnavailable, match="gave no signature"):
        holder.load()


@pytest.fixture
def plain_self(tmp_path, clock):
    root = tmp_path / "self"
    store = SelfStore.open(root, clock)
    store.append("diary.jsonl", {"text": "hello"})
    return root


def test_pebble_seals_and_starts_with_its_lock_in_the_keystore(plain_self, clock, keystore, capsys):
    seal_self(plain_self, PASSWORD, AndroidKeystoreHolder(), clock, kdf=FAST)
    assert locks.load(plain_self)["locks"]["pebble"]["holder"] == "android-keystore"
    assert isinstance(holder_for(plain_self), AndroidKeystoreHolder)
    store = open_self(plain_self, clock)
    assert store.access == "pebble" and store.read_lines("diary.jsonl") == [{"text": "hello"}]
    Room(store).put("photo", "keystore.jpg", b"picture")
    assert main(["status", "--self", str(plain_self)], Prompts(), clock) == 0
    out = capsys.readouterr().out
    assert "Pebble's lock:     yes (the key in the phone's keystore (alias pebble-self) opens it)" in out
    assert "secure hardware" in out and "locked room:       1 thing (1 photo" in out
    assert main(["status", "--self", str(plain_self), "--key-holder", "file", "--key-file", str(plain_self.parent / "none.key")], Prompts(), clock) == 0
    assert "seal.json says Pebble's lock lives in the phone's keystore" in capsys.readouterr().out
    unseal_self(plain_self, PASSWORD, AndroidKeystoreHolder())
    assert keystore.keys == {}


def test_the_brain_and_replay_follow_the_keystore(plain_self, clock, keystore, monkeypatch):
    seal_self(plain_self, PASSWORD, AndroidKeystoreHolder(), clock, kdf=FAST)
    store = open_self(plain_self, clock)
    box = BlackBox.for_store(store, clock)
    chaos = Chaos(seed=3, sink=lambda record: box.record("chaos", **record))
    chaos.stream("whims").random()
    box.close()
    path = store.path("logs/blackbox.jsonl")
    assert replay_main([str(path)]) == 0
    assert replay_main([str(path), "--key-holder", "android"]) == 0
    assert replay_main([str(path), "--key-holder", "file", "--key-file", str(plain_self.parent / "none.key")]) == 2
    monkeypatch.setenv("PEBBLE_KEY_HOLDER", "file")
    assert isinstance(holder_for(plain_self), FileKeyHolder)
    from pebble.app import build_parser

    assert build_parser().parse_args(["--key-holder", "android"]).key_holder == "android"


def test_move_lock_takes_pebbles_lock_from_the_file_into_the_keystore(plain_self, clock, keystore, capsys, tmp_path):
    key_file = tmp_path / "keys" / "self.key"
    seal_self(plain_self, PASSWORD, FileKeyHolder(key_file), clock, kdf=FAST)
    Room(open_self(plain_self, clock, key_file=key_file)).put("voice", "hi.ogg", b"hi")
    assert main(["move-lock", "--self", str(plain_self), "--key-file", str(key_file)], Prompts(), clock) == 0
    out = capsys.readouterr().out
    assert "Pebble's lock is in the phone's keystore" in out and "key file" in out and "did not change" in out
    assert not key_file.exists()
    assert locks.load(plain_self)["locks"]["pebble"]["holder"] == "android-keystore"
    assert open_self(plain_self, clock).access == "pebble"
    assert open_room(plain_self, clock, password=PASSWORD).take_out(Room(open_self(plain_self, clock)).items()[0].id)[1] == b"hi"
    assert not status(plain_self, AndroidKeystoreHolder()).refused


def test_move_lock_finishes_after_a_power_cut_and_refuses_an_unsteady_keystore(plain_self, clock, keystore, monkeypatch, tmp_path):
    key_file = tmp_path / "keys" / "self.key"
    seal_self(plain_self, PASSWORD, FileKeyHolder(key_file), clock, kdf=FAST)
    keystore.steady = False
    before = (plain_self / "seal.json").read_bytes()
    with pytest.raises(DeviceKeyDamaged):
        move_lock(plain_self, FileKeyHolder(key_file), AndroidKeystoreHolder())
    assert (plain_self / "seal.json").read_bytes() == before and key_file.exists() and keystore.keys == {}
    keystore.steady = True

    def power_cut(self):
        raise OSError("power cut")

    monkeypatch.setattr(FileKeyHolder, "delete", power_cut)
    with pytest.raises(OSError):
        move_lock(plain_self, FileKeyHolder(key_file), AndroidKeystoreHolder())
    monkeypatch.undo()
    monkeypatch.setattr(keys, "termux_keystore", keystore)
    assert key_file.exists() and open_self(plain_self, clock).access == "pebble"
    again = move_lock(plain_self, FileKeyHolder(key_file), AndroidKeystoreHolder())
    assert again.already and not key_file.exists()
    stranger = FakeKeystore()
    with pytest.raises(SealError):
        move_lock(plain_self, FileKeyHolder(key_file), AndroidKeystoreHolder(run=stranger))
