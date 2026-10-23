import math
import re

from ..clock import iso

FILE = "conversation/listening.json"
MUTE_HOURS = 12.0
GUEST_HOURS = 2.0
GUEST_GONE_S = 600.0
HELP_WORDS = ("help", "help me")
STOP = re.compile(r"\b(stop listening|don't listen|do not listen|stop eavesdropping|ears off|turn your ears off|turn off your ears|mute yourself|go deaf|block your ears|cover your ears)\b")
START = re.compile(r"\b(start listening|listen again|you can listen|ears on|turn your ears on|turn on your ears|unmute)\b")
TRUSTED = ("trusted", "inner circle")
STRANGER = "stranger"
NIGHT_WORDS_S = 30.0


class Listening:
    def __init__(self, store=None, clock=None, preferences: dict | None = None):
        self.store = store
        self.clock = clock
        prefs = dict((preferences or {}).get("listening") or {})
        self.mute_hours = float(prefs.get("mute_hours", MUTE_HOURS) or MUTE_HOURS)
        self.night_keywords = prefs.get("night_keywords", True) is not False
        self.enabled = prefs.get("words", True) is not False
        self.barge_on_voice = prefs.get("barge_on_voice", True) is not False
        saved = (store.read(FILE, {}) if store is not None else {}) or {}
        self.muted_by: str | None = saved.get("muted_by")
        self.muted_until = float(saved.get("until", -math.inf) or -math.inf) if saved.get("muted") else -math.inf
        self.guest = bool(saved.get("guest")) and saved.get("muted") is True
        self.guest_seen = self.now()

    def now(self) -> float:
        return self.clock.now() if self.clock is not None else 0.0

    @property
    def muted(self) -> bool:
        return self.now() < self.muted_until

    def policy(self, quiet: bool, awake: bool) -> str:
        if awake:
            return "words"
        if not self.enabled:
            return "off"
        if self.muted:
            return "keywords"
        if quiet:
            return "keywords" if self.night_keywords else "off"
        return "words"

    def mute(self, person_id: str | None, now: float | None = None, guest: bool = False) -> None:
        now = self.now() if now is None else now
        self.muted_by = person_id
        self.guest = guest
        self.guest_seen = now
        hours = min(self.mute_hours, GUEST_HOURS) if guest else self.mute_hours
        self.muted_until = now + hours * 3600.0
        self._save(now)

    def unmute(self, now: float | None = None) -> None:
        now = self.now() if now is None else now
        self.muted_by = None
        self.guest = False
        self.muted_until = -math.inf
        self._save(now)

    def guest_here(self, here: bool, now: float | None = None) -> bool:
        if not self.muted or not self.guest:
            return False
        now = self.now() if now is None else now
        if here:
            self.guest_seen = now
            return False
        if now - self.guest_seen < GUEST_GONE_S:
            return False
        self.unmute(now)
        return True

    def _save(self, now: float) -> None:
        if self.store is None:
            return
        data = {"format": 1, "muted": self.muted, "muted_by": self.muted_by, "guest": self.guest, "until": self.muted_until if self.muted_until > -math.inf else None, "at": iso(now)}
        self.store.write(FILE, data)

    def keywords(self, name: str) -> list[dict]:
        name = (name or "Pebble").strip()
        return [
            {"word": name.lower(), "boost": 2.0, "threshold": 0.15},
            {"word": f"{name.lower()} start listening", "boost": 2.0, "threshold": 0.2},
            {"word": f"{name.lower()} listen again", "boost": 2.0, "threshold": 0.2},
        ] + [{"word": word, "boost": 2.0, "threshold": 0.2} for word in HELP_WORDS]

    def spelled(self, name: str, model_path=None) -> list[dict]:
        from ..speech.fetch import MODELS
        from ..speech.tokens import BadModel, Pieces

        words = self.keywords(name)
        path = model_path or (MODELS / "kws" / "bpe.model")
        try:
            pieces = Pieces.load(path)
        except (OSError, BadModel):
            return words
        return [dict(item, tokens=pieces.keyword_line(item["word"])) for item in words]

    def mark(self, mode: str) -> dict:
        return {"on": mode != "off", "words": mode == "words", "muted": self.muted}


def asks_stop(text: str) -> bool:
    return bool(STOP.search((text or "").lower()))


def asks_start(text: str) -> bool:
    return bool(START.search((text or "").lower()))


def asks_help(word: str) -> bool:
    return " ".join(str(word or "").lower().replace("_", " ").split()) in HELP_WORDS


def is_guest(tier: str, owner: bool = False, relationship: str | None = None) -> bool:
    return not owner and tier not in TRUSTED and tier != "child" and relationship not in ("family", "child")


def may_mute(tier: str, owner: bool = False) -> bool:
    return owner or (bool(tier) and tier != STRANGER)


def may_unmute(tier: str, owner: bool = False, muted_it: bool = False) -> bool:
    return owner or muted_it or tier in TRUSTED
