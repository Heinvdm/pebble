from dataclasses import dataclass, field

from .prints import KINDS, PER_KIND, PINNED, normalise
from .qualities import Ledger

RELATIONSHIPS = ("owner", "family", "friend", "guest", "child")
LIST_CAP = 30
TEXT_MAX = 120
PROMISE_CAP = 60
DIARY_CAP = 50
SEEN_DAYS = 31


def clean(text: str, limit: int = TEXT_MAX) -> str:
    return " ".join(str(text).split())[:limit]


@dataclass
class Promise:
    id: int
    by: str
    what: str
    due: float
    made_at: float
    status: str = "open"
    closed_at: float | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "by": self.by, "what": self.what, "due": self.due, "made_at": self.made_at, "status": self.status, "closed_at": self.closed_at}

    @classmethod
    def from_dict(cls, data: dict) -> "Promise | None":
        try:
            return cls(int(data["id"]), str(data["by"]), str(data["what"]), float(data["due"]), float(data["made_at"]), str(data.get("status", "open")), data.get("closed_at"))
        except (KeyError, TypeError, ValueError):
            return None


@dataclass
class Person:
    id: str
    first_met: float
    last_seen: float
    names: list = field(default_factory=list)
    nicknames: list = field(default_factory=list)
    relationship: str | None = None
    introduced_by: str | None = None
    override: str | None = None
    meetings: int = 0
    days_met: int = 0
    last_day: str | None = None
    seen_days: list = field(default_factory=list)
    diary: list = field(default_factory=list)
    promises: list = field(default_factory=list)
    likes: list = field(default_factory=list)
    dislikes: list = field(default_factory=list)
    wishes: list = field(default_factory=list)
    private: list = field(default_factory=list)
    family_word: dict | None = None
    prints: dict = field(default_factory=dict)
    ledger: Ledger = field(default_factory=Ledger)
    next_promise: int = 1

    @property
    def name(self) -> str | None:
        return self.names[0] if self.names else None

    @property
    def label(self) -> str:
        return self.name or f"the visitor {self.id}"

    @property
    def is_child(self) -> bool:
        return self.relationship == "child"

    @property
    def is_owner(self) -> bool:
        return self.relationship == "owner"

    def answers_to(self, ref: str) -> bool:
        wanted = clean(ref).lower()
        return bool(wanted) and (wanted == self.id.lower() or wanted in (n.lower() for n in self.names + self.nicknames) or wanted == self.label.lower())

    def add_print(self, kind: str, vector, at: float) -> bool:
        if kind not in KINDS:
            return False
        clean_vector = normalise(vector)
        if clean_vector is None:
            return False
        stored = self.prints.setdefault(kind, [])
        entry = {"vector": list(clean_vector), "at": at}
        if len(stored) < PINNED and all(isinstance(p, dict) and p.get("pinned") for p in stored):
            entry["pinned"] = True
        stored.append(entry)
        pinned = [p for p in stored if isinstance(p, dict) and p.get("pinned")][:PINNED]
        loose = [p for p in stored if not any(p is q for q in pinned)]
        stored[:] = pinned + loose[len(loose) - (PER_KIND - len(pinned)):] if len(loose) > PER_KIND - len(pinned) else pinned + loose
        return True

    def print_vectors(self, kind: str) -> list[tuple[float, ...]]:
        return [tuple(p["vector"]) for p in self.prints.get(kind, []) if isinstance(p, dict) and p.get("vector")]

    def has_prints(self) -> bool:
        return any(self.print_vectors(kind) for kind in KINDS)

    def drop_prints(self) -> None:
        self.prints = {}

    def note(self, kind: str, text: str) -> bool:
        target = {"like": self.likes, "dislike": self.dislikes, "wish": self.wishes, "private": self.private, "nickname": self.nicknames}.get(kind)
        text = clean(text)
        if target is None or not text:
            return False
        if text.lower() in (t.lower() for t in target):
            return True
        target.append(text)
        del target[:-LIST_CAP]
        return True

    def set_name(self, name: str) -> bool:
        name = clean(name, 40)
        if not name:
            return False
        self.names = [name] + [n for n in self.names if n.lower() != name.lower()][: LIST_CAP - 1]
        return True

    def saw_on(self, day: str) -> None:
        if day and (not self.seen_days or self.seen_days[-1] != day):
            self.seen_days.append(day)
            del self.seen_days[:-SEEN_DAYS]

    def link_diary(self, at: str) -> None:
        self.diary.append(at)
        del self.diary[:-DIARY_CAP]

    def add_promise(self, by: str, what: str, due: float, made_at: float) -> Promise:
        promise = Promise(self.next_promise, by, clean(what), due, made_at)
        self.next_promise += 1
        self.promises.append(promise)
        closed = [p for p in self.promises if p.status != "open"]
        if len(self.promises) > PROMISE_CAP and closed:
            self.promises.remove(closed[0])
        return promise

    def open_promises(self) -> list[Promise]:
        return [p for p in self.promises if p.status == "open"]

    def kept_count(self) -> tuple[int, int]:
        theirs = [p for p in self.promises if p.by == "them" and p.status in ("kept", "broken")]
        return sum(1 for p in theirs if p.status == "kept"), len(theirs)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "names": self.names,
            "nicknames": self.nicknames,
            "relationship": self.relationship,
            "introduced_by": self.introduced_by,
            "override": self.override,
            "first_met": self.first_met,
            "last_seen": self.last_seen,
            "meetings": self.meetings,
            "days_met": self.days_met,
            "last_day": self.last_day,
            "seen_days": self.seen_days,
            "diary": self.diary,
            "promises": [p.to_dict() for p in self.promises],
            "next_promise": self.next_promise,
            "likes": self.likes,
            "dislikes": self.dislikes,
            "wishes": self.wishes,
            "private": self.private,
            "family_word": self.family_word,
            "prints": self.prints,
            "evidence": self.ledger.to_list(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Person | None":
        try:
            person = cls(str(data["id"]), float(data["first_met"]), float(data.get("last_seen", data["first_met"])))
        except (KeyError, TypeError, ValueError):
            return None
        for name in ("names", "nicknames", "diary", "likes", "dislikes", "wishes", "private"):
            value = data.get(name)
            if isinstance(value, list):
                setattr(person, name, [str(v) for v in value][-max(LIST_CAP, DIARY_CAP) :])
        relationship = data.get("relationship")
        person.relationship = relationship if relationship in RELATIONSHIPS else None
        person.introduced_by = data.get("introduced_by")
        person.override = data.get("override")
        person.meetings = int(data.get("meetings", 0) or 0)
        person.days_met = int(data.get("days_met", 0) or 0)
        person.last_day = data.get("last_day")
        person.seen_days = [str(d) for d in data.get("seen_days") or [] if isinstance(d, str)][-SEEN_DAYS:]
        person.promises = [p for p in (Promise.from_dict(raw) for raw in data.get("promises") or [] if isinstance(raw, dict)) if p is not None]
        person.next_promise = max([int(data.get("next_promise", 1) or 1)] + [p.id + 1 for p in person.promises])
        person.family_word = data.get("family_word") if isinstance(data.get("family_word"), dict) else None
        prints = data.get("prints")
        person.prints = {kind: list(prints.get(kind) or []) for kind in KINDS if isinstance(prints, dict) and prints.get(kind)}
        person.ledger = Ledger(data.get("evidence") or [])
        return person
