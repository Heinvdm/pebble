import json
from dataclasses import asdict
from pathlib import Path

from ..seal import sealing
from ..seal.cards import parse
from ..seal.errors import SealError
from ..seal.keys import AndroidAppKeyHolder, FileKeyHolder
from ..selfstore.sealed import SelfIsSealed
from . import bridge as bridges


def _holder(bridge) -> AndroidAppKeyHolder:
    if bridge is not None:
        bridges.install(bridge)
    return AndroidAppKeyHolder()


def _answer(ok: bool, message: str, **extra) -> str:
    return json.dumps({"ok": ok, "message": message, **extra})


def status(self_dir: str, bridge=None) -> str:
    try:
        found = sealing.status(Path(self_dir), _holder(bridge))
    except (SealError, SelfIsSealed, OSError) as error:
        return _answer(False, str(error))
    data = asdict(found)
    data["root"] = str(found.root)
    data["room"] = None if found.room is None else {"things": found.room.things, "locked": found.room.locked}
    data["refused"] = list(found.refused)[:20]
    return _answer(True, "sealed" if found.sealed else "not sealed", status=data)


def seal(self_dir: str, password: str, bridge=None) -> str:
    from .. import setup as setup_mode

    root = Path(self_dir)
    if setup_mode.in_setup(root):
        return _answer(False, "Pebble is still being set up. Press \"Setup finished\" first, once the body is built and tested, then seal.")
    try:
        result = sealing.seal_self(root, str(password), _holder(bridge))
        cards = sealing.reprint_cards(root, str(password))
    except (SealError, SelfIsSealed, OSError) as error:
        return _answer(False, str(error))
    refused = result.refused
    note = f" {len(refused)} files could not be sealed and were left as they were." if refused else ""
    return _answer(True, "Pebble's self is sealed: the owner's password, Pebble's lock in this phone's keystore, or any two of the three cards below open it. Write the cards down now." + note, cards=cards, refused=refused[:20])


def cards(self_dir: str, password: str) -> str:
    try:
        printed = sealing.reprint_cards(Path(self_dir), str(password))
    except (SealError, SelfIsSealed, OSError) as error:
        return _answer(False, str(error))
    return _answer(True, "These are the same three cards as before. Showing them is noted, with the time, in the seal's status.", cards=printed)


def recover(self_dir: str, first: str, second: str, bridge=None) -> str:
    try:
        chosen = [parse(str(first)), parse(str(second))]
        sealing.recover(Path(self_dir), _holder(bridge), chosen, fresh_key=True)
    except (SealError, SelfIsSealed, OSError, ValueError) as error:
        return _answer(False, str(error))
    return _answer(True, "Pebble's lock is made again in this phone's keystore; Pebble can open its self here.")


def recover_with_password(self_dir: str, password: str, bridge=None) -> str:
    try:
        sealing.recover(Path(self_dir), _holder(bridge), None, str(password), fresh_key=True)
    except (SealError, SelfIsSealed, OSError) as error:
        return _answer(False, str(error))
    return _answer(True, "Pebble's lock is made again in this phone's keystore; Pebble can open its self here.")


def move_lock(self_dir: str, key_file: str, bridge=None) -> str:
    try:
        moved = sealing.move_lock(Path(self_dir), FileKeyHolder(key_file), _holder(bridge))
    except (SealError, SelfIsSealed, OSError) as error:
        return _answer(False, str(error))
    if moved.already:
        return _answer(True, "Pebble's lock was already in this phone's keystore; the key file is deleted.")
    return _answer(True, "Pebble's lock moved into this phone's keystore and the key file is deleted.")


def setup_status(self_dir: str) -> str:
    from ..setup import setup_status as status_of

    try:
        found = status_of(Path(self_dir))
    except Exception as error:
        return _answer(False, str(error))
    return _answer(True, "in setup" if found.get("on") else "setup finished", setup=found)


def finish_setup(self_dir: str, passphrase: str = "") -> str:
    from ..setup import finish_setup as finish

    try:
        result = finish(Path(self_dir), passphrase or None)
    except Exception as error:
        return _answer(False, str(error))
    if result.get("already"):
        return _answer(True, "Setup was already finished.", setup=result)
    if not result.get("ok"):
        return _answer(False, result.get("error") or "Setup could not be finished.", setup=result)
    return _answer(True, "Setup is finished. From now on Pebble remembers, learns who it trusts and grows its personality; today is its birthday.", setup=result)


def birth_draw(self_dir: str, again: bool = False, passphrase: str = "") -> str:
    from ..setup import birth_draw as draw

    try:
        found = draw(Path(self_dir), again, passphrase or None)
    except Exception as error:
        return _answer(False, str(error))
    if not found["ok"]:
        return _answer(False, found["error"], birth=found)
    return _answer(True, found["line"], birth=found)
