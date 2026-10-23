import math
import secrets
from pathlib import Path

from ..selfstore.atomic import drop_backup, encode_json, write_bytes_atomic
from ..selfstore.codec import BadSeal
from ..selfstore.rotation import settle
from ..selfstore.sealed import SEAL, b64, key_opens, read_seal, seal_aad, unb64
from . import cards as cardlib
from .crypto import Aead, derive
from .errors import CardError, DeviceKeyDamaged, NoDeviceKey, NoOwnerLock, NotSealed, SealError, WeakPassword, WrongDeviceKey, WrongPassword
from .keys import KeyHolder, SelfKey, fingerprint
from .tries import Tries

SEAL_FORMAT = 1
OWNER_KDF = {"n": 2**17, "r": 8, "p": 1}
MIN_PASSWORD = 12
SALT_BYTES = 16


def load(root: Path) -> dict:
    settle(root)
    seal = read_seal(root)
    if seal is None:
        raise NotSealed(f"Pebble's self at {root} is not sealed.")
    return seal


def save(root: Path, seal: dict) -> None:
    path = Path(root) / SEAL
    write_bytes_atomic(path, encode_json(seal), keep_backup=False)
    drop_backup(path)


def check_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD:
        raise WeakPassword(f"The owner's password needs at least {MIN_PASSWORD} characters.")


def recover_hint(root: Path) -> str:
    return (
        f"To open it on this device, run `python -m pebble.seal recover --self {root}` with two of the three "
        f"recovery cards, or `python -m pebble.seal recover --self {root} --password` with the owner's password "
        "while the owner's lock exists."
    )


def owner_lock(key: SelfKey, recovery: cardlib.Recovery, password: str, kdf: dict | None = None) -> dict:
    check_password(password)
    params = dict(OWNER_KDF if kdf is None else kdf)
    salt = secrets.token_bytes(SALT_BYTES)
    kek = Aead(derive(password, salt, params["n"], params["r"], params["p"]))
    return {
        "kdf": "scrypt",
        "n": params["n"],
        "r": params["r"],
        "p": params["p"],
        "salt": b64(salt),
        "wrapped": b64(kek.seal(key.secret(), seal_aad("lock:owner"))),
        "recovery": b64(kek.seal(recovery.pack(), seal_aad("lock:owner:recovery"))),
    }


def _verified(seal: dict, secret: bytes, access: str) -> SelfKey:
    key = SelfKey(secret, access)
    if not key_opens(seal, key):
        raise SealError(f"the key from the {access} lock does not match this self's check; {SEAL} is damaged")
    return key


def _owner_lock(seal: dict) -> dict:
    lock = seal["locks"].get("owner")
    if not lock:
        if seal.get("thrown_away_at"):
            raise NoOwnerLock(f"The owner's lock was thrown away on {seal['thrown_away_at']}. Only two recovery cards can open this self now.")
        raise NoOwnerLock("This self has no owner's lock.")
    return lock


def open_owner_all(seal: dict, password: str, root: Path) -> tuple[SelfKey, cardlib.Recovery]:
    lock = _owner_lock(seal)
    tries = Tries(root)
    tries.check()
    try:
        if lock.get("kdf") != "scrypt":
            raise SealError(f"unknown key derivation {lock.get('kdf')!r}")
        kek = Aead(derive(str(password or ""), unb64(lock["salt"]), int(lock["n"]), int(lock["r"]), int(lock["p"])))
        secret = kek.open(unb64(lock["wrapped"]), seal_aad("lock:owner"))
    except BadSeal as error:
        wait = tries.failed()
        later = f" Wait {math.ceil(wait)} seconds before the next try." if wait else ""
        raise WrongPassword("That password does not open this self." + later) from error
    except (KeyError, TypeError, ValueError) as error:
        raise SealError(f"the owner's lock in {SEAL} is damaged") from error
    key = _verified(seal, secret, "owner")
    try:
        recovery = cardlib.Recovery.unpack(kek.open(unb64(lock["recovery"]), seal_aad("lock:owner:recovery")))
    except (BadSeal, KeyError, TypeError, ValueError, CardError) as error:
        raise SealError(f"the owner's lock in {SEAL} is damaged (its copy of the recovery secret does not open)") from error
    tries.passed()
    return key, recovery


def open_owner(seal: dict, password: str, root: Path) -> SelfKey:
    return open_owner_all(seal, password, root)[0]


def pebble_lock(key: SelfKey, device_key: bytes, holder: KeyHolder) -> dict:
    wrapped = Aead(device_key).seal(key.secret(), seal_aad("lock:pebble"))
    return {"holder": holder.kind, "fingerprint": fingerprint(device_key), "wrapped": b64(wrapped)}


def open_pebble(seal: dict, holder: KeyHolder, root: Path) -> SelfKey:
    lock = seal["locks"].get("pebble")
    if not lock:
        raise NoDeviceKey(f"Pebble's self at {root} is sealed and has no Pebble's lock. {recover_hint(root)}")
    try:
        device_key = holder.load()
    except DeviceKeyDamaged as error:
        raise WrongDeviceKey(f"Pebble's self at {root} is sealed, and {error}. {recover_hint(root)}") from error
    if device_key is None:
        raise NoDeviceKey(f"Pebble's self at {root} is sealed, and this device has no key for it (looked for {holder.where()}). {recover_hint(root)}")
    try:
        secret = Aead(device_key).open(unb64(lock["wrapped"]), seal_aad("lock:pebble"))
    except BadSeal as error:
        raise WrongDeviceKey(f"Pebble's self at {root} is sealed, and this device's key ({holder.where()}) does not open it. {recover_hint(root)}") from error
    except (KeyError, TypeError, ValueError) as error:
        raise SealError(f"Pebble's lock in {SEAL} is damaged") from error
    return _verified(seal, secret, "pebble")


def card_lock(key: SelfKey, recovery: cardlib.Recovery) -> dict:
    wrapped = Aead(recovery.secret).seal(key.secret(), seal_aad("lock:cards"))
    return {"set_id": recovery.set_id, "threshold": cardlib.THRESHOLD, "count": cardlib.COUNT, "wrapped": b64(wrapped)}


def open_cards_all(seal: dict, cards: list[cardlib.Card]) -> tuple[SelfKey, cardlib.Recovery]:
    lock = seal["locks"].get("cards")
    if not lock:
        raise CardError("This self has no recovery cards.")
    for card in cards:
        if card.set_id != lock["set_id"]:
            raise CardError(
                f"Card {card.number} is from set {cardlib.pretty_set(card.set_id)}, "
                f"but this self's cards are set {cardlib.pretty_set(lock['set_id'])}. "
                "Cards printed before a throw-away stop working when it finishes."
            )
    recovery = cardlib.Recovery.from_cards(cards)
    try:
        secret = Aead(recovery.secret).open(unb64(lock["wrapped"]), seal_aad("lock:cards"))
    except BadSeal as error:
        raise CardError("These cards do not open this self. Check that each card was typed exactly.") from error
    except (KeyError, TypeError, ValueError) as error:
        raise SealError(f"the recovery cards' lock in {SEAL} is damaged") from error
    key = SelfKey(secret, "cards")
    if not key_opens(seal, key):
        raise CardError("These cards do not open this self. Check that each card was typed exactly.")
    return key, recovery


def open_cards(seal: dict, cards: list[cardlib.Card]) -> SelfKey:
    return open_cards_all(seal, cards)[0]
