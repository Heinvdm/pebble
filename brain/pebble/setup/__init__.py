import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..clock import Clock, iso
from ..owner import gate_for
from ..self.birth import preview, redraw
from ..selfstore import SelfIsSealed, SelfStore

SETUP = "setup.json"
PREFERENCES = "preferences.json"
WOKE_UP = "Today I woke up for real."


class SetupRefused(PermissionError):
    pass


@dataclass
class Setup:
    on: bool = False
    since: str | None = None
    ended: str | None = None
    born: str | None = None
    folded: bool = True

    @classmethod
    def from_dict(cls, data) -> "Setup":
        if not isinstance(data, dict):
            return cls()
        on = bool(data.get("on", False))
        return cls(on, data.get("since"), data.get("ended"), data.get("born"), bool(data.get("folded", not on)))

    @classmethod
    def load(cls, store) -> "Setup":
        return cls.from_dict(store.read(SETUP, None))

    def to_dict(self) -> dict:
        return {"format": 1, **asdict(self)}

    def save(self, store) -> None:
        store.write(SETUP, self.to_dict())


def in_setup(root: Path) -> bool:
    path = Path(root) / SETUP
    try:
        return Setup.from_dict(json.loads(path.read_text(encoding="utf-8"))).on
    except (OSError, ValueError):
        return False


def finish(store, clock, passphrase: str | None = None) -> Setup:
    setup = Setup.load(store)
    if not setup.on:
        return setup
    gate = gate_for(store)
    if gate.is_set() and (passphrase is None or gate.verify(passphrase) is None):
        raise SetupRefused("only the owner can finish setup, and the passphrase did not match")
    now = clock.now()
    setup.on = False
    setup.ended = iso(now)
    setup.born = clock.local(now).date().isoformat()
    setup.folded = False
    setup.save(store)
    return setup


def tsunami_zone(store) -> bool | None:
    value = ((store.read(PREFERENCES, {}) or {}).get("safety") or {}).get("tsunami_zone")
    return value if isinstance(value, bool) else None


def set_tsunami_zone(store, value: bool) -> None:
    prefs = dict(store.read(PREFERENCES, {}) or {})
    safety = dict(prefs.get("safety") or {})
    safety["tsunami_zone"] = bool(value)
    prefs["safety"] = safety
    store.write(PREFERENCES, prefs)


def _store(self_dir, clock) -> SelfStore:
    return SelfStore.open(Path(self_dir), clock or Clock())


def finish_setup(self_dir, passphrase: str | None = None, clock=None, tsunami: bool | None = None) -> dict:
    clock = clock or Clock()
    try:
        store = _store(self_dir, clock)
    except SelfIsSealed:
        return {"ok": True, "already": True, "born": None, "error": None}
    before = Setup.load(store)
    if not before.on:
        return {"ok": True, "already": True, "born": before.born, "error": None}
    try:
        after = finish(store, clock, passphrase)
    except SetupRefused as error:
        return {"ok": False, "already": False, "born": None, "error": str(error)}
    if tsunami is not None:
        set_tsunami_zone(store, tsunami)
    return {"ok": True, "already": False, "born": after.born, "error": None}


def setup_status(self_dir, clock=None) -> dict:
    try:
        setup = Setup.load(_store(self_dir, clock))
    except SelfIsSealed:
        return {"on": False, "since": None, "born": None, "sealed": True}
    return {"on": setup.on, "since": setup.since, "born": setup.born, "sealed": False}


def may_draw_again(store) -> bool:
    return Setup.load(store).on and not preview(store).get("born")


def _drawn(found: dict, ok: bool = True, error: str | None = None) -> dict:
    return {"ok": ok, "born": found.get("born"), "draw": found.get("draw"), "line": found.get("line", ""), "error": error}


def birth_draw(self_dir, again: bool = False, passphrase: str | None = None, clock=None) -> dict:
    clock = clock or Clock()
    try:
        store = _store(self_dir, clock)
    except SelfIsSealed:
        return _drawn({}, False, "the self is sealed, so Pebble's birth draw is its own")
    if not again:
        return _drawn(preview(store))
    if not may_draw_again(store):
        return _drawn(preview(store), False, "Pebble's birth draw can only be made again while it is being set up; after that it is its own")
    gate = gate_for(store)
    if gate.is_set() and (passphrase is None or gate.verify(passphrase) is None):
        return _drawn(preview(store), False, "only the owner can ask for a new draw, and the passphrase did not match")
    return _drawn(redraw(store))
