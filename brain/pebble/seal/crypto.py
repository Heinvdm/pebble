import hashlib
import secrets
import unicodedata

from ..selfstore.codec import BadSeal
from .errors import CryptoMissing, SealError

KEY_BYTES = 32
NONCE_BYTES = 12
TAG_BYTES = 16
INSTALL = (
    "pip install \"cryptography>=42\" "
    "(postmarketOS: sudo apk add py3-cryptography; Termux: pkg install python-cryptography)"
)


def _aesgcm():
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as error:
        raise CryptoMissing(f"The sealed self needs the 'cryptography' package, which is not installed. Install it with: {INSTALL}") from error
    return AESGCM, InvalidTag


class Aead:
    def __init__(self, key: bytes):
        if len(key) != KEY_BYTES:
            raise ValueError(f"a key has {KEY_BYTES} bytes")
        cipher, invalid = _aesgcm()
        self._cipher = cipher(bytes(key))
        self._invalid = invalid

    def seal(self, data: bytes, aad: bytes) -> bytes:
        nonce = secrets.token_bytes(NONCE_BYTES)
        return nonce + self._cipher.encrypt(nonce, bytes(data), aad)

    def open(self, blob: bytes, aad: bytes) -> bytes:
        blob = bytes(blob)
        if len(blob) < NONCE_BYTES + TAG_BYTES:
            raise BadSeal("too short to be sealed")
        try:
            return self._cipher.decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], aad)
        except self._invalid as error:
            raise BadSeal("does not open") from error


def check_kdf(n: int, r: int, p: int) -> None:
    if not (isinstance(n, int) and 2 <= n <= 2**20 and n & (n - 1) == 0):
        raise SealError(f"scrypt n={n!r} is not allowed")
    if not (isinstance(r, int) and 1 <= r <= 32 and isinstance(p, int) and 1 <= p <= 16):
        raise SealError(f"scrypt r={r!r} p={p!r} is not allowed")


def derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    check_kdf(n, r, p)
    secret = unicodedata.normalize("NFC", password).encode("utf-8")
    return hashlib.scrypt(secret, salt=salt, n=n, r=r, p=p, maxmem=128 * r * (n + p + 2) + 2**20, dklen=KEY_BYTES)


BOX_INFO = b"pebble-sealed-box-v1\x00"
X25519_BYTES = 32


def _asymmetric():
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    except ImportError as error:
        raise CryptoMissing(f"The sealed self needs the 'cryptography' package, which is not installed. Install it with: {INSTALL}") from error
    return hashes, serialization, X25519PrivateKey, X25519PublicKey, HKDF


def hkdf(secret: bytes, info: bytes, salt: bytes | None = None, length: int = KEY_BYTES) -> bytes:
    hashes, _, _, _, HKDF = _asymmetric()
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(bytes(secret))


def _raw_public(private) -> bytes:
    _, serialization, _, _, _ = _asymmetric()
    return private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def x25519_private() -> bytes:
    _, serialization, X25519PrivateKey, _, _ = _asymmetric()
    return X25519PrivateKey.generate().private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())


def x25519_public(private: bytes) -> bytes:
    _, _, X25519PrivateKey, _, _ = _asymmetric()
    return _raw_public(X25519PrivateKey.from_private_bytes(bytes(private)))


def seal_to(public: bytes, data: bytes, aad: bytes) -> bytes:
    _, _, X25519PrivateKey, X25519PublicKey, _ = _asymmetric()
    ephemeral = X25519PrivateKey.generate()
    ephemeral_public = _raw_public(ephemeral)
    shared = ephemeral.exchange(X25519PublicKey.from_public_bytes(bytes(public)))
    key = hkdf(shared, BOX_INFO + ephemeral_public + bytes(public))
    return ephemeral_public + Aead(key).seal(data, aad)


def open_from(private: bytes, blob: bytes, aad: bytes) -> bytes:
    _, _, X25519PrivateKey, X25519PublicKey, _ = _asymmetric()
    blob = bytes(blob)
    if len(blob) < X25519_BYTES + NONCE_BYTES + TAG_BYTES:
        raise BadSeal("too short to be sealed")
    me = X25519PrivateKey.from_private_bytes(bytes(private))
    ephemeral_public = blob[:X25519_BYTES]
    try:
        shared = me.exchange(X25519PublicKey.from_public_bytes(ephemeral_public))
    except ValueError as error:
        raise BadSeal("does not open") from error
    key = hkdf(shared, BOX_INFO + ephemeral_public + _raw_public(me))
    return Aead(key).open(blob[X25519_BYTES:], aad)
