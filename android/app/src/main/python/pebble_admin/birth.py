import json
from pathlib import Path

from pebble import setup as setup_mode
from pebble.android import seal
from pebble.clock import Clock
from pebble.owner import gate_for
from pebble.self.birth import preview, template
from pebble.selfstore import SelfIsSealed, SelfStore, is_sealed

MANIFEST = "manifest.json"


def _answer(ok: bool, message: str, **extra) -> str:
    return json.dumps({"ok": ok, "message": message, **extra})


def _details(self_dir: str) -> dict | None:
    root = Path(self_dir)
    if is_sealed(root) or not (root / MANIFEST).exists():
        return None
    store = SelfStore.open(root, Clock())
    found = preview(store)
    drawn = found.get("drawn") or {}
    base = template()[0].get("traits") or {}
    return {
        "setup": setup_mode.Setup.load(store).on,
        "born": found.get("born"),
        "draw": found.get("draw"),
        "line": found.get("line") or "",
        "traits": drawn.get("traits") or {},
        "usual": {name: base[name] for name in drawn.get("traits") or {} if name in base},
        "values": drawn.get("values") or {},
        "tastes": list(drawn.get("tastes") or []),
        "passphrase_set": gate_for(store).is_set(),
    }


def _missing(self_dir: str) -> str:
    if is_sealed(Path(self_dir)):
        return _answer(False, "Pebble's self is sealed, so its birth draw is its own.")
    return _answer(False, "Pebble has no self yet. Start Pebble once, then come back here.")


def status(self_dir: str, bridge=None) -> str:
    try:
        found = _details(self_dir)
    except (SelfIsSealed, OSError) as error:
        return _answer(False, str(error))
    if found is None:
        return _missing(self_dir)
    return _answer(True, found["line"], birth=found)


def again(self_dir: str, passphrase: str = "", bridge=None) -> str:
    try:
        answer = json.loads(str(seal.birth_draw(str(self_dir), True, str(passphrase) if passphrase else "")))
    except (TypeError, ValueError) as error:
        return _answer(False, f"The draw could not be read: {error}")
    try:
        found = _details(self_dir)
    except (SelfIsSealed, OSError) as error:
        return _answer(False, str(error))
    if found is None:
        return _missing(self_dir)
    return _answer(bool(answer.get("ok")), str(answer.get("message") or ""), birth=found)
