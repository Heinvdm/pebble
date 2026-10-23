import base64
import binascii
import hashlib
import json
import os
import secrets
import subprocess
from pathlib import Path
from typing import Callable, Protocol

from .crypto import KEY_BYTES, Aead, hkdf
from .errors import DeviceKeyDamaged, KeystoreUnavailable, SealError

ACCESS = ("pebble", "owner", "cards")
KEY_ENV = "PEBBLE_KEY_FILE"
KEY_HEADER = "pebble-device-key 1"


class SelfKey:
    def __init__(self, secret: bytes, access: str):
        if access not in ACCESS:
            raise ValueError(f"access must be one of {', '.join(ACCESS)}")
        if len(secret) != KEY_BYTES:
            raise ValueError(f"a self key has {KEY_BYTES} bytes")
        self.access = access
        self._secret = bytes(secret)
        self._aead = Aead(self._secret)

    @classmethod
    def generate(cls, access: str = "owner") -> "SelfKey":
        return cls(secrets.token_bytes(KEY_BYTES), access)

    def secret(self) -> bytes:
        return self._secret

    def as_access(self, access: str) -> "SelfKey":
        return SelfKey(self._secret, access)

    def seal(self, data: bytes, aad: bytes) -> bytes:
        return self._aead.seal(data, aad)

    def open(self, blob: bytes, aad: bytes) -> bytes:
        return self._aead.open(blob, aad)

    def __repr__(self) -> str:
        return f"SelfKey(access={self.access!r})"


def fingerprint(device_key: bytes) -> str:
    return hashlib.sha256(b"pebble-device-key-id\x00" + device_key).hexdigest()[:16]


def default_key_path(key_file: str | Path | None = None) -> Path:
    chosen = key_file or os.environ.get(KEY_ENV) or Path.home() / ".pebble" / "self.key"
    return Path(chosen).expanduser()


class KeyHolder(Protocol):
    kind: str

    def where(self) -> str: ...

    def load(self) -> bytes | None: ...

    def load_or_create(self) -> bytes: ...

    def create(self) -> bytes: ...

    def delete(self) -> None: ...


def _private(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _fsync_dir(directory: Path) -> None:
    if os.name != "posix":
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class FileKeyHolder:
    kind = "file"

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def where(self) -> str:
        return str(self.path)

    def load(self) -> bytes | None:
        if not self.path.exists():
            return None
        try:
            text = self.path.read_bytes().decode("ascii")
        except OSError as error:
            raise DeviceKeyDamaged(f"the key file {self.path} cannot be read ({error})") from error
        except UnicodeDecodeError as error:
            raise DeviceKeyDamaged(f"the key file {self.path} is damaged") from error
        try:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            key = base64.b64decode(lines[1].encode("ascii"), validate=True)
        except (ValueError, IndexError, binascii.Error) as error:
            raise DeviceKeyDamaged(f"the key file {self.path} is damaged") from error
        if lines[0] != KEY_HEADER or len(lines) != 2 or len(key) != KEY_BYTES:
            raise DeviceKeyDamaged(f"the key file {self.path} is damaged")
        return key

    def create(self) -> bytes:
        key = secrets.token_bytes(KEY_BYTES)
        directory = self.path.parent
        fresh = not directory.exists()
        directory.mkdir(parents=True, exist_ok=True)
        if fresh:
            _private(directory, 0o700)
        tmp = directory / f".{self.path.name}.{secrets.token_hex(6)}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        fd = os.open(tmp, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(f"{KEY_HEADER}\n{base64.b64encode(key).decode('ascii')}\n".encode("ascii"))
                handle.flush()
                os.fsync(handle.fileno())
            _private(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        _fsync_dir(directory)
        return key

    def load_or_create(self) -> bytes:
        try:
            key = self.load()
        except DeviceKeyDamaged:
            key = None
        return key if key is not None else self.create()

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)


KEYSTORE_PROGRAM = "termux-keystore"
KEYSTORE_TIMEOUT = 30.0
KEYSTORE_ALIAS = "pebble-self"
SIGN_ALGORITHM = "SHA256withRSA"
SIGN_TEXT = b"pebble self device key\x00signed by the phone's keystore\x00v1"
KEYSTORE_SALT = b"pebble-keystore-device-key\x00v1"
NO_TERMUX_API = (
    "termux-keystore is not installed, so the phone's keystore cannot hold Pebble's lock. "
    "On Termux: pkg install termux-api, and install the Termux:API app from the same place as Termux "
    "(F-Droid or GitHub, not a mix). postmarketOS and Droidian have no Android keystore: keep the key file (--key-holder file)."
)
NO_ANSWER = (
    f"termux-keystore did not answer within {int(KEYSTORE_TIMEOUT)} seconds. Is the Termux:API app installed "
    "(from the same place as Termux) and allowed to run in the background?"
)
NOT_STEADY = (
    "the phone's keystore signed the same text twice and gave two different answers, so its key cannot be "
    f"Pebble's lock (it has to be an RSA key that signs with {SIGN_ALGORITHM}, PKCS#1 v1.5)"
)
Runner = Callable[[list[str], bytes], bytes]


def termux_keystore(args: list[str], data: bytes = b"") -> bytes:
    try:
        done = subprocess.run([KEYSTORE_PROGRAM, *args], input=bytes(data), capture_output=True, timeout=KEYSTORE_TIMEOUT)
    except FileNotFoundError as error:
        raise KeystoreUnavailable(NO_TERMUX_API) from error
    except subprocess.TimeoutExpired as error:
        raise KeystoreUnavailable(NO_ANSWER) from error
    except OSError as error:
        raise KeystoreUnavailable(f"termux-keystore could not run ({error}).") from error
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", errors="replace").strip() or f"exit code {done.returncode}"
        raise KeystoreUnavailable(f"termux-keystore {args[0]} failed: {detail}")
    return done.stdout


class AndroidKeystoreHolder:
    kind = "android-keystore"

    def __init__(self, alias: str = KEYSTORE_ALIAS, run: Runner | None = None):
        self.alias = alias
        self._run = run or termux_keystore

    def where(self) -> str:
        return f"the phone's keystore (alias {self.alias})"

    def entry(self) -> dict | None:
        out = self._run(["list"], b"")
        try:
            listed = json.loads(out.decode("utf-8").strip() or "[]")
        except (UnicodeDecodeError, ValueError) as error:
            raise KeystoreUnavailable(
                "termux-keystore list did not give a list of keys. Are the termux-api package and the Termux:API app from the same place?"
            ) from error
        if not isinstance(listed, list):
            raise KeystoreUnavailable("termux-keystore list did not give a list of keys.")
        for found in listed:
            if isinstance(found, dict) and found.get("alias") == self.alias:
                return found
        return None

    def secure_hardware(self) -> bool | None:
        found = self.entry()
        if found is None or "inside_secure_hardware" not in found:
            return None
        return bool(found["inside_secure_hardware"])

    def _check(self, found: dict) -> None:
        algorithm = found.get("algorithm")
        if algorithm is not None and str(algorithm).upper() != "RSA":
            raise DeviceKeyDamaged(f"the keystore key {self.alias} is a {algorithm} key, and Pebble's lock needs an RSA key")
        auth = found.get("user_authentication")
        if isinstance(auth, dict) and auth.get("required"):
            raise DeviceKeyDamaged(
                f"the keystore key {self.alias} needs the screen unlocked before each use, so Pebble could not start by itself after a reboot"
            )

    def _sign(self) -> bytes:
        signature = self._run(["sign", self.alias, SIGN_ALGORITHM], SIGN_TEXT)
        if not signature:
            raise KeystoreUnavailable(f"the phone's keystore gave no signature with the key {self.alias}.")
        return signature

    def load(self) -> bytes | None:
        found = self.entry()
        if found is None:
            return None
        self._check(found)
        first, second = self._sign(), self._sign()
        if first != second:
            raise DeviceKeyDamaged(NOT_STEADY)
        return hkdf(first, b"pebble-device-key\x00" + self.alias.encode("utf-8"), KEYSTORE_SALT)

    def create(self) -> bytes:
        if self.entry() is not None:
            self.delete()
        self._run(["generate", self.alias, "-a", "RSA", "-s", "2048"], b"")
        try:
            key = self.load()
        except SealError:
            self.delete()
            raise
        if key is None:
            raise KeystoreUnavailable(f"the phone's keystore did not keep the new key {self.alias}.")
        return key

    def load_or_create(self) -> bytes:
        try:
            key = self.load()
        except DeviceKeyDamaged:
            key = None
        return key if key is not None else self.create()

    def delete(self) -> None:
        self._run(["delete", self.alias], b"")


APP_KEY_HEADER = "pebble-wrapped-device-key 1"
APP_KIND = "android-app"
NO_APP = (
    "Pebble's lock is in the Pebble app's keystore, which only the Pebble Android app on its own phone can reach. "
    "On a PC or in Termux keep the key file (--key-holder file), or open the self with two recovery cards."
)
APP_KEY_GONE = (
    "the wrapped key file is here, but the keystore key that opens it is gone (the app was reinstalled, its data was cleared, "
    "or the phone was reset), so Pebble's lock cannot be opened on this phone"
)


def _write_wrapped(path: Path, blob: bytes) -> None:
    directory = path.parent
    fresh = not directory.exists()
    directory.mkdir(parents=True, exist_ok=True)
    if fresh:
        _private(directory, 0o700)
    tmp = directory / f".{path.name}.{secrets.token_hex(6)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(f"{APP_KEY_HEADER}\n{base64.b64encode(blob).decode('ascii')}\n".encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        _private(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    _fsync_dir(directory)


def _read_wrapped(path: Path) -> bytes | None:
    if not path.exists():
        return None
    try:
        text = path.read_bytes().decode("ascii")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        blob = base64.b64decode(lines[1].encode("ascii"), validate=True)
    except OSError as error:
        raise DeviceKeyDamaged(f"the wrapped key file {path} cannot be read ({error})") from error
    except (UnicodeDecodeError, ValueError, IndexError, binascii.Error) as error:
        raise DeviceKeyDamaged(f"the wrapped key file {path} is damaged") from error
    if lines[0] != APP_KEY_HEADER or len(lines) != 2 or not blob:
        raise DeviceKeyDamaged(f"the wrapped key file {path} is damaged")
    return blob


class AndroidAppKeyHolder:
    kind = APP_KIND

    def __init__(self, keystore=None, path: str | Path | None = None):
        self._keystore = keystore
        self._path = Path(path) if path is not None else None

    def _store(self):
        if self._keystore is not None:
            return self._keystore
        from ..android.bridge import current

        found = current()
        if found is None:
            raise KeystoreUnavailable(NO_APP)
        return found

    def _call(self, name: str, *args):
        store = self._store()
        try:
            return getattr(store, name)(*args)
        except SealError:
            raise
        except Exception as error:
            raise KeystoreUnavailable(f"the phone's keystore could not {name} ({error})") from error

    def _file(self) -> Path:
        if self._path is None:
            self._path = Path(str(self._call("keyFile")))
        return self._path

    def where(self) -> str:
        try:
            return f"the Pebble app's keystore (its wrapped key is {self._file()})"
        except SealError:
            return "the Pebble app's keystore"

    def info(self) -> dict:
        from ..android.bridge import as_json

        found = as_json(self._call("keyInfo"), {})
        return found if isinstance(found, dict) else {}

    def secure_hardware(self) -> bool | None:
        found = self.info()
        if not found.get("exists") or found.get("secure") is None:
            return None
        return bool(found["secure"])

    def load(self) -> bytes | None:
        from ..android.bridge import as_bytes

        blob = _read_wrapped(self._file())
        if blob is None:
            return None
        if not self._call("keyExists"):
            raise DeviceKeyDamaged(APP_KEY_GONE)
        store = self._store()
        try:
            key = as_bytes(store.keyUnwrap(blob))
        except Exception as error:
            raise DeviceKeyDamaged(f"the phone's keystore could not open the wrapped key in {self._file()} ({error})") from error
        if len(key) != KEY_BYTES:
            raise DeviceKeyDamaged(f"the wrapped key in {self._file()} opened to the wrong length")
        return key

    def create(self) -> bytes:
        from ..android.bridge import as_bytes

        path = self._file()
        self._call("keyCreate")
        key = secrets.token_bytes(KEY_BYTES)
        blob = as_bytes(self._call("keyWrap", key))
        if as_bytes(self._call("keyUnwrap", blob)) != key:
            self._call("keyDelete")
            raise KeystoreUnavailable("the phone's keystore did not give back the key it had just wrapped")
        _write_wrapped(path, blob)
        return key

    def load_or_create(self) -> bytes:
        try:
            key = self.load()
        except DeviceKeyDamaged:
            key = None
        return key if key is not None else self.create()

    def delete(self) -> None:
        self._file().unlink(missing_ok=True)
        self._call("keyDelete")
