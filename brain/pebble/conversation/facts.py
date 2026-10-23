import re
from dataclasses import dataclass

from .words import content, words

FILE = "conversation/overheard.json"
DAY_S = 86400.0
KEEP_DAYS = 14
DATED_AFTER_DAYS = 1
PER_PERSON = 20
TEXT_MAX = 120
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
FEELINGS = "nervous|worried|excited|tired|sick|stressed|scared|happy|sad|hungry|cold|lonely|bored|anxious|upset"
KIN = "mum|mom|dad|sister|brother|nan|gran|grandma|grandpa|friend|boss|partner|son|daughter|aunt|uncle|cousin|husband|wife|boyfriend|girlfriend"
VERBS = {"love": "loves", "like": "likes", "hate": "hates", "can't stand": "can't stand", "really like": "really likes", "really love": "really loves"}
FIRST_PERSON = (
    (re.compile(r"^i(?:'m| am) (?:so |really |a bit |very |quite )?(" + FEELINGS + r")(?: about| for)? ?(.*)$"), "feeling", lambda n, g: f"{n} felt {g[0]}" + (f" about {g[1]}" if g[1] else "")),
    (re.compile(r"^i(?:'m| am) (?:going to|gonna) (.+)$"), "plan", lambda n, g: f"{n} is going to {g[0]}"),
    (re.compile(r"^i(?:'ll| will) (.+)$"), "plan", lambda n, g: f"{n} will {g[0]}"),
    (re.compile(r"^i need to (.+)$"), "plan", lambda n, g: f"{n} needs to {g[0]}"),
    (re.compile(r"^i(?:'ve| have) (?:got )?to (.+)$"), "plan", lambda n, g: f"{n} has to {g[0]}"),
    (re.compile(r"^i(?:'ve| have) (?:got )?(my|a|an) (.+)$"), "fact", lambda n, g: f"{n} has {'their' if g[0] == 'my' else g[0]} {g[1]}"),
    (re.compile(r"^i (really like|really love|love|like|hate|can't stand) (.+)$"), "fact", lambda n, g: f"{n} {VERBS[g[0]]} {g[1]}"),
    (re.compile(r"^my (" + KIN + r")(?:'s| is) (.+)$"), "fact", lambda n, g: f"{n}'s {g[0]} is {g[1]}"),
    (re.compile(r"^my (" + KIN + r") (.+)$"), "fact", lambda n, g: f"{n}'s {g[0]} {g[1]}"),
    (re.compile(r"^it's my (birthday|anniversary) (.+)$"), "plan", lambda n, g: f"{n}'s {g[0]} is {g[1]}"),
)
CLAUSE = re.compile(r" (?:so|but|because|cause|and then|which|although|though) ")
TRIM = re.compile(r"(?:^| )(?:anyway|you know|i guess|like|um|uh)(?= |$)")
DATED = ("tomorrow", "tonight", "next week", "weekend", "today")


@dataclass
class Fact:
    id: int
    person: str
    text: str
    kind: str
    learned_at: float
    until: float
    words: tuple = ()
    used: int = 0

    def to_dict(self) -> dict:
        return {"id": self.id, "person": self.person, "text": self.text, "kind": self.kind, "learned_at": self.learned_at, "until": self.until, "words": list(self.words), "used": self.used}

    @classmethod
    def from_dict(cls, data: dict) -> "Fact | None":
        try:
            return cls(int(data["id"]), str(data["person"]), str(data["text"])[:TEXT_MAX], str(data.get("kind", "fact")), float(data["learned_at"]), float(data["until"]), tuple(str(w) for w in data.get("words") or ()), int(data.get("used", 0)))
        except (KeyError, TypeError, ValueError):
            return None


def _tidy(text: str) -> str:
    text = TRIM.sub(" ", text)
    return " ".join(text.split())[:TEXT_MAX].strip()


def extract(text: str, name: str) -> tuple[str, str] | None:
    said = " ".join(words(text))
    for cut in CLAUSE.finditer(said):
        if len(said[: cut.start()].split()) >= 4:
            said = said[: cut.start()]
            break
    for pattern, kind, make in FIRST_PERSON:
        match = pattern.match(said)
        if match is None:
            continue
        groups = [_tidy(g or "") for g in match.groups()]
        if not groups[-1] and kind != "feeling":
            continue
        line = _tidy(make(name, groups))
        if len(words(line)) < 3:
            return None
        if kind == "fact" and any(day in said for day in DAYS + DATED):
            kind = "plan"
        return line, kind
    return None


def when_until(text: str, now: float, local) -> float:
    said = words(text)
    today = local(now)
    for offset in range(1, 8):
        day = DAYS[(today.weekday() + offset) % 7]
        if day in said:
            return now + (offset + DATED_AFTER_DAYS) * DAY_S
    if "tomorrow" in said:
        return now + (1 + DATED_AFTER_DAYS) * DAY_S
    if "tonight" in said or "today" in said:
        return now + DATED_AFTER_DAYS * DAY_S
    return now + KEEP_DAYS * DAY_S


class Overheard:
    def __init__(self, store, clock):
        self.store = store
        self.clock = clock
        data = store.read(FILE, {}) or {}
        self.facts: list[Fact] = [f for f in (Fact.from_dict(raw) for raw in data.get("facts") or [] if isinstance(raw, dict)) if f is not None]
        self.next_id = max([f.id for f in self.facts] + [0]) + 1
        self.dirty = False

    def learn(self, person_id: str, name: str, text: str, now: float | None = None) -> Fact | None:
        now = self.clock.now() if now is None else now
        found = extract(text, name)
        if found is None:
            return None
        line, kind = found
        if any(f.person == person_id and f.text.lower() == line.lower() for f in self.facts):
            return None
        fact = Fact(self.next_id, person_id, line, kind, now, when_until(text, now, self.clock.local), tuple(sorted(set(content(line)) - set(words(name)))))
        self.next_id += 1
        self.facts.append(fact)
        mine = [f for f in self.facts if f.person == person_id]
        for old in mine[:-PER_PERSON]:
            self.facts.remove(old)
        self.dirty = True
        return fact

    def expire(self, now: float | None = None) -> int:
        now = self.clock.now() if now is None else now
        before = len(self.facts)
        self.facts = [f for f in self.facts if f.until > now]
        if len(self.facts) != before:
            self.dirty = True
        return before - len(self.facts)

    def about(self, person_id: str, now: float | None = None) -> list[Fact]:
        now = self.clock.now() if now is None else now
        return [f for f in self.facts if f.person == person_id and f.until > now]

    def others(self, allowed: set[str], now: float | None = None) -> list[Fact]:
        now = self.clock.now() if now is None else now
        return [f for f in self.facts if f.person not in allowed and f.until > now]

    def drop_person(self, person_id: str) -> int:
        before = len(self.facts)
        self.facts = [f for f in self.facts if f.person != person_id]
        if len(self.facts) != before:
            self.dirty = True
        return before - len(self.facts)

    def to_dict(self) -> dict:
        return {"format": 1, "facts": [f.to_dict() for f in self.facts]}

    def save(self, backup: bool = True) -> None:
        if self.dirty:
            self.store.write(FILE, self.to_dict(), keep_backup=backup)
            self.dirty = False


def forget(store, person_id: str, names: list[str]) -> int:
    data = store.read(FILE, {}) or {}
    raw = data.get("facts") or []
    patterns = [re.compile(r"\b" + re.escape(n.lower()) + r"\b") for n in names if n and n.strip()]
    kept = [f for f in raw if isinstance(f, dict) and f.get("person") != person_id and not any(p.search(str(f.get("text", "")).lower()) for p in patterns)]
    if len(kept) != len(raw):
        store.write(FILE, {"format": 1, "facts": kept}, keep_backup=False)
    return len(raw) - len(kept)


def leaks(text: str, facts: list[Fact]) -> list[Fact]:
    said = set(content(text))
    out = []
    for fact in facts:
        key = set(fact.words)
        if key and len(said & key) >= max(1, min(2, len(key))):
            out.append(fact)
    return out
