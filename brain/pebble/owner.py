import hashlib
import hmac
import secrets
import time
from typing import Callable

ITERATIONS = 200_000
MAX_FAILURES = 5
LOCKOUT_S = 300.0
_MINT = object()


class OwnerGrant:
    def __init__(self, token: object, reason: str):
        if token is not _MINT:
            raise PermissionError("owner grants come only from the passphrase gate")
        self.reason = reason


def normalise(phrase: str) -> str:
    return " ".join(phrase.lower().split())


def hash_passphrase(phrase: str, salt: bytes | None = None, iterations: int = ITERATIONS) -> dict:
    salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", normalise(phrase).encode("utf-8"), salt, iterations)
    return {"algorithm": "pbkdf2_sha256", "iterations": iterations, "salt": salt.hex(), "hash": digest.hex()}


class PassphraseGate:
    def __init__(self, read_core: Callable[[], dict], monotonic: Callable[[], float] = time.monotonic, open_to_owner: Callable[[], bool] = lambda: True):
        self._read_core = read_core
        self._monotonic = monotonic
        self._open_to_owner = open_to_owner
        self._failures = 0
        self._locked_until = 0.0

    def _record(self) -> dict:
        record = self._read_core().get("passphrase") or {}
        return record if record.get("hash") and record.get("salt") else {}

    def is_set(self) -> bool:
        return bool(self._record())

    def locked_out(self) -> bool:
        return self._monotonic() < self._locked_until

    def verify(self, phrase: str) -> OwnerGrant | None:
        record = self._record()
        if not record or self.locked_out() or not self._open_to_owner():
            return None
        candidate = hash_passphrase(phrase, bytes.fromhex(record["salt"]), int(record.get("iterations", ITERATIONS)))
        if hmac.compare_digest(candidate["hash"], record["hash"]):
            self._failures = 0
            return OwnerGrant(_MINT, "passphrase")
        self._failures += 1
        if self._failures >= MAX_FAILURES:
            self._failures = 0
            self._locked_until = self._monotonic() + LOCKOUT_S
        return None


def gate_for(store) -> PassphraseGate:
    return PassphraseGate(lambda: store.read("core.json"), open_to_owner=lambda: not getattr(store, "sealed", False))
