import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from .codec import BadSeal
from .past import older_forms

SEAL = "seal.json"
NEXT_SEAL = "seal.next.json"
JOURNAL = "rotation.json"
TRIES = "owner-tries.json"
RESERVED = (SEAL, NEXT_SEAL, JOURNAL, TRIES)
NEXT = ".next"
SEAL_AAD = b"pebble-seal\x00"
CHECK_TEXT = b"pebble self key check"
BIRTH = "birth.json"
PROTECTED = frozenset({"personality.json", "values.json", "people.json", "dials.json", BIRTH})
VALUES = "values.json"
FLOOR_DIALS = ("honesty", "kindness")
FLOOR_KEYS = ("min", "owner_only")
UNFINISHED = ("sealing", "unsealing")


class SelfIsSealed(PermissionError):
    pass


class WrongKey(SelfIsSealed):
    pass


class SealUnfinished(SelfIsSealed):
    pass


class SealDamaged(SelfIsSealed):
    pass


class SealedFile(PermissionError):
    pass


def is_reserved(relative: str) -> bool:
    text = str(relative).replace("\\", "/").rstrip(". ").lower()
    if text.endswith(NEXT):
        return True
    return "/" not in text and any(text.startswith(name) for name in RESERVED)


def seal_aad(purpose: str) -> bytes:
    return SEAL_AAD + purpose.encode("utf-8")


def is_sealed(root: Path) -> bool:
    return (Path(root) / SEAL).exists()


def read_seal(root: Path) -> dict | None:
    path = Path(root) / SEAL
    if not path.exists():
        return None
    try:
        seal = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise SealDamaged(f"{path} is damaged ({error}); the self cannot be opened") from error
    if not isinstance(seal, dict) or not isinstance(seal.get("locks"), dict):
        raise SealDamaged(f"{path} is damaged; the self cannot be opened")
    return seal


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(text: str) -> bytes:
    return base64.b64decode(str(text).encode("ascii"), validate=True)


def open_sealed_value(seal: dict, field: str, key: Any) -> Any:
    try:
        return json.loads(key.open(unb64(seal[field]), seal_aad(field)).decode("utf-8"))
    except (KeyError, ValueError, TypeError) as error:
        raise SealDamaged(f"the {field} record in {SEAL} does not open") from error


def seal_value(value: Any, field: str, key: Any) -> str:
    return b64(key.seal(json.dumps(value, sort_keys=True).encode("utf-8"), seal_aad(field)))


def key_opens(seal: dict, key: Any) -> bool:
    try:
        return key.open(unb64(seal["check"]), seal_aad("check")) == CHECK_TEXT
    except (KeyError, ValueError, TypeError, BadSeal):
        return False


def check_value(key: Any) -> str:
    return b64(key.seal(CHECK_TEXT, seal_aad("check")))


def core_digest(core: Any) -> str:
    return hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def core_matches(core: Any, frozen: str) -> bool:
    if core_digest(core) == frozen:
        return True
    return any(core_digest(older) == frozen for older in older_forms(core))


def floors_of(values: Any) -> dict:
    dials = values.get("dials") if isinstance(values, dict) else None
    dials = dials if isinstance(dials, dict) else {}
    found = {}
    for dial in FLOOR_DIALS:
        entry = dials.get(dial)
        entry = entry if isinstance(entry, dict) else {}
        found[dial] = {key: entry.get(key) for key in FLOOR_KEYS}
    return found


def frozen_record(core: Any, values: Any) -> dict:
    return {"core": core_digest(core), "floors": floors_of(values)}
