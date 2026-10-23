import asyncio
import hashlib
import hmac
import os
import re
import secrets
import time
from abc import ABC, abstractmethod
from pathlib import Path

LABEL = "pebble-link-1"
KEY_BYTES = 32
NONCE_BYTES = 16
PROOF_BYTES = 16
TAG_BYTES = 6
KEY_FILE_ENV = "PEBBLE_LINK_KEY_FILE"
KEYSTORE_CLASS = "nz.pebble.robot.link.BodyKey"
HANDSHAKE_S = 3.0

_SUFFIX = re.compile(r"^(.*) #([0-9]{1,10}) ([0-9a-fA-F]{12})$")
_HEX = re.compile(r"^[0-9a-fA-F]+$")


class AuthError(ConnectionError):
    pass


class LinkKey(ABC):
    @abstractmethod
    def mac(self, message: bytes) -> bytes: ...


class RawKey(LinkKey):
    def __init__(self, key: bytes):
        if len(key) != KEY_BYTES:
            raise ValueError(f"a link key is {KEY_BYTES} bytes")
        self._key = bytes(key)

    def mac(self, message: bytes) -> bytes:
        return hmac.new(self._key, message, hashlib.sha256).digest()

    def hex(self) -> str:
        return self._key.hex()

    @classmethod
    def new(cls) -> "RawKey":
        return cls(secrets.token_bytes(KEY_BYTES))

    @classmethod
    def from_hex(cls, text: str) -> "RawKey":
        text = text.strip()
        if len(text) != KEY_BYTES * 2 or not _HEX.match(text):
            raise ValueError(f"a link key is {KEY_BYTES * 2} hex digits")
        return cls(bytes.fromhex(text))


class KeystoreKey(LinkKey):
    def __init__(self, holder):
        self._holder = holder

    def mac(self, message: bytes) -> bytes:
        answer = self._holder.mac(message)
        if answer is None:
            raise AuthError("the phone's keystore would not use the body key")
        return bytes(answer)


def read_key_file(path: Path) -> RawKey:
    return RawKey.from_hex(Path(path).read_text(encoding="ascii"))


def write_key_file(path: Path, key: RawKey) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as out:
        out.write(key.hex() + "\n")


def find_key() -> LinkKey | None:
    try:
        from java import jclass
    except ImportError:
        jclass = None
    if jclass is not None:
        try:
            holder = jclass(KEYSTORE_CLASS)
        except Exception:
            return None
        return KeystoreKey(holder) if holder.has() else None
    path = os.environ.get(KEY_FILE_ENV, "").strip()
    return read_key_file(Path(path)) if path else None


def session_message(phone_nonce: str, body_nonce: str) -> bytes:
    return f"{LABEL} {phone_nonce.lower()} {body_nonce.lower()}".encode("ascii")


def _mac(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode("ascii"), hashlib.sha256).digest()


class Session:
    def __init__(self, session_key: bytes):
        self._key = bytes(session_key)
        self.sent = 0
        self.received = 0
        self.rejected = 0

    def proof(self, who: str) -> str:
        return _mac(self._key, who)[:PROOF_BYTES].hex()

    def tag(self, direction: str, counter: int, text: str) -> str:
        return _mac(self._key, f"{direction}{counter} {text}")[:TAG_BYTES].hex()

    def seal(self, text: str) -> str:
        self.sent += 1
        return f"{text} #{self.sent} {self.tag('p', self.sent, text)}"

    def open(self, line: str) -> str | None:
        found = _SUFFIX.match(line.rstrip())
        if found is None:
            self.rejected += 1
            return None
        text, counter, given = found.group(1), int(found.group(2)), found.group(3).lower()
        if counter <= self.received or counter > 0xFFFFFFFF:
            self.rejected += 1
            return None
        if not hmac.compare_digest(self.tag("b", counter, text), given):
            self.rejected += 1
            return None
        self.received = counter
        return text


async def prove(transport, key: LinkKey, timeout: float = HANDSHAKE_S) -> tuple[Session, list[str]]:
    nonce = secrets.token_hex(NONCE_BYTES)
    await transport.write_line(f"H {nonce}")
    deadline = time.monotonic() + timeout
    held: list[str] = []

    async def next_line() -> str:
        left = deadline - time.monotonic()
        if left <= 0:
            raise AuthError("the body did not answer the handshake (old firmware, or not Pebble's body)")
        try:
            return (await asyncio.wait_for(transport.read_line(), left)).strip()
        except asyncio.TimeoutError as error:
            raise AuthError("the body did not answer the handshake (old firmware, or not Pebble's body)") from error

    while True:
        line = await next_line()
        if line.startswith("h "):
            parts = line.split()
            if len(parts) == 3 and len(parts[1]) == NONCE_BYTES * 2 and _HEX.match(parts[1]) and len(parts[2]) == PROOF_BYTES * 2 and _HEX.match(parts[2]):
                break
            raise AuthError("the body's handshake answer was malformed")
        if line.startswith("err H"):
            reason = line.split()[-1]
            if reason == "key":
                raise AuthError("the body has no link key yet; pair it over USB")
            raise AuthError(f"the body refused the handshake ({reason}); its firmware may be too old")
        if line.startswith("E boot"):
            held.append(line)
    body_nonce, body_proof = parts[1].lower(), parts[2].lower()
    session_key = await asyncio.to_thread(key.mac, session_message(nonce, body_nonce))
    session = Session(session_key)
    if not hmac.compare_digest(session.proof("body"), body_proof):
        raise AuthError("the body did not prove the shared key; it is not Pebble's body, or its key changed")
    await transport.write_line(f"V {session.proof('phone')}")
    while True:
        line = await next_line()
        if line == "ok":
            return session, held
        if line.startswith("err V"):
            raise AuthError("the body did not accept Pebble's proof; its key differs from the phone's")
        if line.startswith("E boot"):
            held.append(line)
