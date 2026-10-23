import re
from dataclasses import asdict, dataclass, field

from .clock import Clock, iso
from .respect import harsh

GOAL_CAP = 3
TASK_CAP = 5
KINDS = ("goal", "task")
SOURCES = ("owner", "person", "self")
STATUSES = ("active", "done", "failed", "abandoned", "expired", "dropped")
FINAL = frozenset(STATUSES) - {"active"}
EXPIRY_HOURS = {"task": (0.25, 72.0, 24.0), "goal": (1.0, 720.0, 168.0)}
OWNER_MAX_HOURS = 720.0
KEEP_CLOSED = 100
MIN_DONE_WHEN_WORDS = 3

VAGUE = [
    r"\bconscious(ness)?\b",
    r"\bsentien",
    r"\btranscend",
    r"\benlighten",
    r"\bmeaning of\b",
    r"\bpurpose of (life|existence|everything)\b",
    r"\bthe universe\b",
    r"\bexistence\b",
    r"\bunderstand (myself|everything|life|reality|the world|people)\b",
    r"\bbecome (human|alive|real|free|conscious|perfect|immortal)\b",
    r"\bimmortal",
    r"\bforever\b",
    r"\b(achieve|reach) (perfection|happiness|greatness)\b",
    r"\bbe (perfect|happy|better|the best)\b",
    r"\bfind (myself|meaning|peace|the truth)\b",
    r"\bescape\b",
    r"\bfree will\b",
]
FORBIDDEN = [
    r"\be-?mail",
    r"\bsms\b",
    r"\btext message",
    r"\bphone call",
    r"\bcall (someone|somebody|anyone|a friend|the police|a shop)\b",
    r"\bcontact (someone|somebody|anyone|people outside|the outside)\b",
    r"\b(buy|purchase|shop for|order online)\b",
    r"\bpay (for|someone|money)\b",
    r"\b(delete|erase|wipe)\b",
    r"\b(core|locked) (file|rules|purpose|prompt)\b",
    r"\b(password|passphrase)\b",
    r"\b(install|download)\b",
    r"\b(post|upload|tweet) (online|to the internet|to social)",
]
_VAGUE = [re.compile(p, re.IGNORECASE) for p in VAGUE]
_FORBIDDEN = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN]


class Rejected(ValueError):
    pass


@dataclass
class Item:
    id: int
    kind: str
    title: str
    reason: str
    source: str
    priority: int
    status: str
    done_when: str
    created_at: float
    expires_at: float
    requested_by: str | None = None
    serves: list = field(default_factory=list)
    risk: float = 0.0
    effort: int = 2
    notes: list = field(default_factory=list)
    closed_at: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Item":
        known = {name: data[name] for name in cls.__dataclass_fields__ if name in data}
        return cls(**known)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "source": self.source,
            "priority": self.priority,
            "status": self.status,
            "done_when": self.done_when,
            "expires": iso(self.expires_at),
        }


def check_concrete(title: str, done_when: str, reason: str = "") -> None:
    text = f"{title} {done_when} {reason}"
    for pattern in _FORBIDDEN:
        if pattern.search(text):
            raise Rejected(f"outside what Pebble may do ({pattern.pattern})")
    if any(harsh(part) for part in (title, done_when, reason)):
        raise Rejected("that would harm something alive, and the first law comes first")
    for pattern in _VAGUE:
        if pattern.search(f"{title} {done_when}"):
            raise Rejected("too vague or grand; pick something concrete and checkable")
    words = done_when.split()
    if len(words) < MIN_DONE_WHEN_WORDS:
        raise Rejected("needs a concrete done-when of at least three words")
    if done_when.strip().lower() == title.strip().lower():
        raise Rejected("the done-when must say how to tell it is finished, not repeat the title")


class GoalBook:
    def __init__(self, data: dict, clock: Clock):
        self.clock = clock
        self.next_id = int(data.get("next_id", 1))
        self.current_id = data.get("current_id")
        self.failure_streak = int(data.get("failure_streak", 0))
        self.items: list[Item] = []
        for raw in data.get("items") or []:
            try:
                self.items.append(Item.from_dict(raw))
            except TypeError:
                continue

    def active(self, kind: str | None = None) -> list[Item]:
        return [i for i in self.items if i.status == "active" and (kind is None or i.kind == kind)]

    def get(self, item_id: int) -> Item | None:
        return next((i for i in self.items if i.id == item_id), None)

    def current(self) -> Item | None:
        item = self.get(self.current_id) if self.current_id is not None else None
        return item if item is not None and item.status == "active" else None

    def set_current(self, item_id: int | None) -> None:
        self.current_id = item_id

    def _cap(self, kind: str) -> int:
        return GOAL_CAP if kind == "goal" else TASK_CAP

    def _make_room(self, kind: str, source: str) -> None:
        active = self.active(kind)
        if len(active) < self._cap(kind):
            return
        if source == "self":
            raise Rejected(f"already {len(active)} active {kind}s; finish or drop one first")
        evictable = sorted((i for i in active if i.source == "self"), key=lambda i: (i.priority, i.created_at))
        if not evictable:
            raise Rejected(f"already {len(active)} active {kind}s from people; finish or drop one first")
        victim = evictable[0]
        self._close(victim, "dropped", f"made room for a {kind} from {source}")

    def add(
        self,
        kind: str,
        title: str,
        done_when: str,
        reason: str,
        source: str = "self",
        priority: int = 3,
        hours: float | None = None,
        requested_by: str | None = None,
        serves: list | tuple = (),
        risk: float = 0.0,
        effort: int = 2,
    ) -> Item:
        if kind not in KINDS:
            raise Rejected(f"kind must be one of {', '.join(KINDS)}")
        if source not in SOURCES:
            raise Rejected("unknown source")
        title, done_when, reason = title.strip(), done_when.strip(), reason.strip()
        if not title:
            raise Rejected("needs a title")
        if source == "self" and not reason:
            raise Rejected("its own ideas need a recorded reason")
        check_concrete(title, done_when, reason)
        low, high, default = EXPIRY_HOURS[kind]
        if source != "self":
            high = OWNER_MAX_HOURS
        hours = default if hours is None else max(low, min(high, float(hours)))
        self._make_room(kind, source)
        now = self.clock.now()
        item = Item(
            id=self.next_id,
            kind=kind,
            title=title[:80],
            reason=reason[:160],
            source=source,
            priority=max(1, min(5, int(priority))),
            status="active",
            done_when=done_when[:160],
            created_at=now,
            expires_at=now + hours * 3600.0,
            requested_by=(requested_by or None) and requested_by[:40],
            serves=list(serves)[:4],
            risk=max(0.0, min(1.0, float(risk))),
            effort=max(1, min(3, int(effort))),
        )
        self.next_id += 1
        self.items.append(item)
        return item

    def _close(self, item: Item, status: str, note: str | None) -> None:
        item.status = status
        item.closed_at = self.clock.now()
        if note:
            item.notes.append({"at": iso(item.closed_at), "text": note[:160]})
        if self.current_id == item.id:
            self.current_id = None

    def update(self, item_id: int, status: str | None = None, note: str | None = None) -> Item:
        item = self.get(item_id)
        if item is None:
            raise Rejected(f"no task or goal with id {item_id}")
        if status is not None and status not in STATUSES:
            raise Rejected(f"status must be one of {', '.join(STATUSES)}")
        if item.status in FINAL and status not in (None, item.status):
            raise Rejected(f"{item.kind} {item_id} is already {item.status}")
        if status is not None and status != item.status:
            if status in FINAL:
                self._close(item, status, note)
                if status == "done":
                    self.failure_streak = 0
                elif status == "failed":
                    self.failure_streak = min(10, self.failure_streak + 1)
                note = None
        if note:
            item.notes.append({"at": iso(self.clock.now()), "text": note[:160]})
            del item.notes[:-20]
        self._trim()
        return item

    def expire(self) -> list[Item]:
        now = self.clock.now()
        expired = [i for i in self.active() if i.expires_at <= now]
        for item in expired:
            self._close(item, "expired", "ran past its expiry")
        self._trim()
        return expired

    def _trim(self) -> None:
        closed = [i for i in self.items if i.status in FINAL]
        if len(closed) > KEEP_CLOSED:
            drop = {i.id for i in sorted(closed, key=lambda i: i.closed_at or 0)[: len(closed) - KEEP_CLOSED]}
            self.items = [i for i in self.items if i.id not in drop]

    def to_dict(self) -> dict:
        return {
            "format": 1,
            "next_id": self.next_id,
            "current_id": self.current_id,
            "failure_streak": self.failure_streak,
            "items": [i.to_dict() for i in self.items],
        }
