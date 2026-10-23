import json
from pathlib import Path

from pebble import setup as setup_mode
from pebble.android import bridge as bridges
from pebble.clock import Clock
from pebble.house import settings
from pebble.house.almanac import TOWNS
from pebble.house.book import HouseBook
from pebble.house.settings import Refused, change, owner_ok
from pebble.owner import gate_for
from pebble.seal.errors import SealError
from pebble.seal.keys import AndroidAppKeyHolder
from pebble.seal.startup import open_self
from pebble.selfstore import SelfIsSealed, is_sealed

MANIFEST = "manifest.json"
ANSWERS = {"yes": True, "no": False}
KNOWN = ("town", "lat", "lon", "wifi", "children_arrivals", "guardians", "cooking_watch")
NO_SELF = "Pebble has no self yet. Start Pebble once, then come back here."


def _answer(ok: bool, message: str, **extra) -> str:
    return json.dumps({"ok": ok, "message": message, **extra})


def _exists(self_dir: str, bridge) -> bool:
    root = Path(self_dir)
    if not (root / MANIFEST).exists() and not is_sealed(root):
        return False
    if bridge is not None:
        bridges.install(bridge)
    return True


def _open(self_dir: str, bridge):
    if not _exists(self_dir, bridge):
        return None
    return open_self(Path(self_dir), Clock(), holder=AndroidAppKeyHolder())


def _light(self_dir: str, bridge):
    if not _exists(self_dir, bridge):
        return None
    return settings.light_store(Path(self_dir), holder=AndroidAppKeyHolder())


def _shown(store) -> dict:
    book = HouseBook(store)
    place = book["place"]
    wifi = book["guest_wifi"]
    found = book.settings
    sealed = bool(getattr(store, "sealed", False))
    return {
        "place": {"name": place.get("name") or "", "lat": place.get("lat"), "lon": place.get("lon")} if place else None,
        "guest_wifi": {"ssid": wifi.get("ssid") or "", "security": wifi.get("security") or ""} if wifi else None,
        "children_arrivals": bool(found.get("children_arrivals")),
        "guardians": len(found.get("guardians") or []),
        "cooking_watch": bool(found.get("cooking_watch")),
        "tsunami_zone": setup_mode.tsunami_zone(store),
        "passphrase_set": gate_for(store).is_set(),
        "sealed": sealed,
        "password_works": sealed and bool(getattr(store, "owner_lock_exists", False)),
        "waiting": len(settings.waiting(store)),
    }


def _wanted(changes_json: str) -> tuple[dict, object] | None:
    try:
        wanted = json.loads(str(changes_json) or "{}")
    except ValueError:
        return None
    if not isinstance(wanted, dict):
        return None
    tsunami = wanted.pop("tsunami", None)
    return {key: wanted[key] for key in KNOWN if key in wanted}, tsunami


def status(self_dir: str, bridge=None) -> str:
    try:
        store = _light(self_dir, bridge)
        if store is None:
            return _answer(False, NO_SELF)
        return _answer(True, "read", house=_shown(store), towns=sorted(TOWNS))
    except (SealError, SelfIsSealed, OSError) as error:
        return _answer(False, str(error))


def save(self_dir: str, passphrase: str, password: str, changes_json: str, bridge=None) -> str:
    found = _wanted(changes_json)
    if found is None:
        return _answer(False, "The settings could not be read.")
    changes, tsunami = found
    if not changes and tsunami is None:
        return _answer(True, "Nothing to change.")
    try:
        store = _open(self_dir, bridge)
    except (SealError, SelfIsSealed, OSError) as error:
        return _answer(False, str(error))
    if store is None:
        return _answer(False, NO_SELF)
    phrase = str(passphrase) if passphrase else None
    secret = str(password) if password else None
    if not owner_ok(store, phrase, secret):
        return _answer(False, "Only the owner can change these, and the owner's password did not open the self." if secret else "Only the owner can change these, and the passphrase did not match.")
    try:
        if changes:
            change(store, phrase, password=secret, **changes)
        if tsunami is not None:
            setup_mode.set_tsunami_zone(store, bool(tsunami))
    except Refused as error:
        return _answer(False, str(error))
    except (KeyError, TypeError, ValueError) as error:
        return _answer(False, f"That setting is not right: {error}")
    return _answer(True, "Saved.", house=_shown(store))


def post(self_dir: str, passphrase: str, password: str, changes_json: str, bridge=None) -> str:
    if _wanted(changes_json) is None:
        return _answer(False, "The settings could not be read.")
    try:
        if not _exists(self_dir, bridge):
            return _answer(False, NO_SELF)
        answer = json.loads(settings.post(str(self_dir), str(passphrase or ""), str(password or ""), str(changes_json), AndroidAppKeyHolder()))
        store = _light(self_dir, None)
        return _answer(bool(answer.get("ok")), str(answer.get("message") or ""), house=_shown(store), sent=answer.get("house"))
    except (SealError, SelfIsSealed, OSError, ValueError) as error:
        return _answer(False, str(error))


def finish_setup(self_dir: str, passphrase: str = "", tsunami: str = "", bridge=None) -> str:
    from pebble.setup import finish_setup as finish

    value = ANSWERS.get(str(tsunami or "").strip().lower())
    try:
        result = finish(Path(self_dir), str(passphrase) if passphrase else None, tsunami=value)
    except Exception as error:
        return _answer(False, str(error))
    if result.get("already"):
        return _answer(True, "Setup was already finished.", setup=result, tsunami_saved=False)
    if not result.get("ok"):
        return _answer(False, result.get("error") or "Setup could not be finished.", setup=result, tsunami_saved=False)
    return _answer(True, "Setup is finished. From now on Pebble remembers, learns who it trusts and grows its personality; today is its birthday.", setup=result, tsunami_saved=value is not None)
