import random
import re
from typing import Callable

from ..clock import iso
from ..respect import harsh
from ..tact import tactless
from . import words as w
from .holds import MARKS, MOCK, NUMBERS, norm

SOCIAL = "social.json"
MAX_WORDS = 8
MAX_SOUND_S = 3.0
SECONDS_PER_CHAR = 0.065
REPEAT_S = 600.0
REPEAT_MAX = 3
OWN_SHARE = 0.4
WEEK_S = 7 * 86400.0
WRITE_GAP_S = 86400.0
WRITE_WEEK_MAX = 4
OWN_MAX = 6
NAME = "{name}"
SAID = {
    "hello": ("hi", "hello", "hey", "hiya", "howdy", "yo", "morning", "good morning", "good afternoon", "good evening", "gday", "g'day", "hey there", "hi there", "hello there"),
    "how": ("how are you", "how are you doing", "how's it going", "how is it going", "how are things", "you alright", "are you okay", "are you ok", "you okay", "how you doing", "how do you do", "how have you been"),
    "thanks": ("thanks", "thank you", "cheers", "ta", "thank you so much", "thanks a lot", "thanks so much", "much appreciated"),
    "night": ("good night", "goodnight", "night", "night night", "nighty night", "sleep well", "sleep tight"),
    "bye": ("bye", "goodbye", "bye bye", "see you", "see you later", "see ya", "catch you later", "later", "see you soon"),
    "praise": ("good boy", "good girl", "good robot", "good pebble", "well done", "good job", "clever pebble", "clever boy", "you're so cute", "you are so cute", "you're the best", "good one"),
}
STOCK = {
    "hello": ("Hi, {name}!", "Hello, {name}!", "Hey, {name}!"),
    "morning": ("Good morning, {name}!", "Morning, {name}!"),
    "evening": ("Good evening, {name}!", "Hi, {name}!"),
    "how_good": ("I'm good, thanks! How are you?", "Pretty good, thanks.", "Good, thank you!"),
    "how_okay": ("I'm okay, thanks. You?", "Not bad, thanks."),
    "how_low": ("A bit tired, but okay.", "I'm okay. A bit low today."),
    "thanks": ("You're welcome!", "Any time.", "No problem."),
    "night": ("Good night, {name}!", "Sleep well, {name}.", "Night night!"),
    "bye": ("Bye, {name}!", "See you later!", "Bye for now."),
    "praise": ("Thank you!", "Aw, thanks!", "That's nice of you."),
}
SEEDS = {
    "hello": "Hello, {name}!",
    "morning": "Good morning, {name}!",
    "evening": "Good evening, {name}!",
    "how_good": "I'm good, thank you.",
    "how_okay": "I'm okay, thank you.",
    "how_low": "I'm a bit tired, but okay.",
    "thanks": "You're welcome.",
    "night": "Good night, {name}.",
    "bye": "Goodbye, {name}.",
    "praise": "Thank you, that's kind.",
}
SPOKEN_NAME = "Ina"


def kind_of(text: str, name: str = "Pebble") -> str:
    called = name.lower()
    body = " ".join(word for word in w.words(text) if word not in (called, f"{called}'s"))
    if not body:
        return ""
    for kind, forms in SAID.items():
        if body in forms:
            return kind
    return ""


def fence(text: str, kind: str) -> str:
    text = " ".join((text or "").split())
    if not text or not re.search(r"[A-Za-z]", text):
        return "empty"
    if len(w.words(text)) > MAX_WORDS or len(text) * SECONDS_PER_CHAR > MAX_SOUND_S:
        return "too long"
    if MARKS.search(text.replace(NAME, "")) or re.search(r"\d", text) or NUMBERS.search(text.lower()):
        return "not plain words"
    if MOCK.search(text.lower()):
        return "unkind"
    if tactless(text.replace(NAME, SPOKEN_NAME)):
        return "it would remark on someone's looks"
    if harsh(text.replace(NAME, SPOKEN_NAME)):
        return "it would be unkind to something alive"
    if kind not in ("how_good", "how_okay") and "?" in text:
        return "it would ask something back"
    return ""


class Social:
    def __init__(self, store=None, rng: random.Random | None = None, clock=None):
        self.store = store
        self.rng = rng or random.Random()
        self.clock = clock
        data = (store.read(SOCIAL, {}) if store is not None else {}) or {}
        self.own: dict = {kind: list(lines) for kind, lines in (data.get("own") or {}).items() if kind in STOCK}
        self.made: list = list(data.get("made") or [])
        self.recent: list = []
        self.dirty = False
        self.diary: Callable[[str], None] = lambda text: None

    def which(self, kind: str, mood: float, hour: int) -> str:
        if kind == "how":
            return "how_good" if mood >= 0.2 else "how_low" if mood <= -0.3 else "how_okay"
        if kind == "hello" and hour < 11:
            return "morning"
        if kind == "hello" and hour >= 18:
            return "evening"
        return kind

    def line(self, text: str, label: str | None, mood: float, hour: int, now: float, name: str = "Pebble") -> str:
        kind = kind_of(text, name)
        if not kind:
            return ""
        slot = self.which(kind, mood, hour)
        stock = list(STOCK.get(slot, ()))
        mine = list(self.own.get(slot, ()))
        if not label or label in ("someone", "you") or label.startswith("the visitor"):
            stock = [line for line in stock if NAME not in line] or [line.replace(", {name}", "") for line in stock]
            mine = [line for line in mine if NAME not in line]
        options = [line for line in (mine if mine and self.rng.random() < OWN_SHARE else []) + stock if not self._too_soon(line, now)]
        if not options:
            options = [line for line in stock + mine if not self.recent or norm(line) != self.recent[-1][1]] or stock
        picked = self.rng.choice(options)
        self.recent.append((now, norm(picked)))
        self.recent = [(at, said) for at, said in self.recent if now - at <= REPEAT_S]
        return picked.replace(NAME, label or "").replace(" ,", ",").strip()

    def _too_soon(self, line: str, now: float) -> bool:
        key = norm(line)
        if self.recent and self.recent[-1][1] == key:
            return True
        return sum(1 for at, said in self.recent if said == key and now - at <= REPEAT_S) >= REPEAT_MAX

    def may_write(self, now_s: float) -> bool:
        times = [t for t in self.made if isinstance(t, (int, float)) and now_s - t <= WEEK_S]
        return len(times) < WRITE_WEEK_MAX and (not times or now_s - max(times) >= WRITE_GAP_S)

    async def write(self, phrase, now_s: float) -> str | None:
        if not self.may_write(now_s):
            return None
        slot = self.rng.choice(sorted(SEEDS))
        seed = SEEDS[slot]
        self.made.append(now_s)
        self.dirty = True
        try:
            phrased = await phrase(seed.replace(NAME, SPOKEN_NAME), "talk")
        except Exception:
            return None
        words = " ".join(str(getattr(phrased, "text", phrased) or "").split())
        if getattr(phrased, "source", "creative") != "creative":
            return None
        if NAME in seed and SPOKEN_NAME not in words:
            return None
        words = words.replace(SPOKEN_NAME, NAME)
        if fence(words, slot) or norm(words) in {norm(line) for line in list(STOCK.get(slot, ())) + self.own.get(slot, [])}:
            return None
        lines = self.own.setdefault(slot, [])
        lines.append(words)
        dropped = lines.pop(0) if len(lines) > OWN_MAX else None
        self.diary(f"I've started saying \"{words.replace(NAME, 'your name')}\"" + (f" instead of \"{dropped.replace(NAME, 'your name')}\"." if dropped else "."))
        self.save()
        return words

    def to_dict(self) -> dict:
        return {"format": 1, "own": self.own, "made": self.made, "at": iso(self.clock.now()) if self.clock is not None else ""}

    def save(self) -> None:
        if self.store is None or not self.dirty:
            return
        self.store.write(SOCIAL, self.to_dict(), keep_backup=False)
        self.dirty = False
