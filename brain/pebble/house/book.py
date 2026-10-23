import copy
import logging

log = logging.getLogger(__name__)

HOUSE = "house.json"
SAVE_EVERY_S = 300.0
DEFAULTS = {
    "format": 1,
    "lists": {},
    "visitors": {"on": False, "since": None, "by": None},
    "place": None,
    "guest_wifi": None,
    "settings": {"cooking_watch": True, "children_arrivals": False, "guardians": [], "curtains": None},
    "alarm_log": [],
    "away": [],
    "noise": [],
    "asked": {},
    "watchers": [],
}


class HouseBook:
    def __init__(self, store=None, data: dict | None = None):
        self.store = store
        raw = data if data is not None else ((store.read(HOUSE, {}) or {}) if store is not None else {})
        self.data = copy.deepcopy(DEFAULTS)
        for key, default in DEFAULTS.items():
            value = (raw or {}).get(key)
            if value is not None and (default is None or isinstance(value, type(default))):
                self.data[key] = value
        settings = dict(DEFAULTS["settings"])
        settings.update(self.data.get("settings") or {})
        self.data["settings"] = settings
        self.dirty = False
        self.saved_at = -1e18

    def __getitem__(self, key: str):
        return self.data[key]

    def __setitem__(self, key: str, value) -> None:
        self.data[key] = value
        self.dirty = True

    @property
    def settings(self) -> dict:
        return self.data["settings"]

    def touch(self) -> None:
        self.dirty = True

    def save(self, mono: float | None = None, force: bool = False, keep_backup: bool = True) -> bool:
        if self.store is None or not (self.dirty or force):
            return False
        if mono is not None and not force and mono - self.saved_at < SAVE_EVERY_S:
            return False
        try:
            self.store.write(HOUSE, self.data, keep_backup=keep_backup)
        except Exception:
            log.exception("house: could not save %s", HOUSE)
            return False
        self.dirty = False
        if mono is not None:
            self.saved_at = mono
        return True
