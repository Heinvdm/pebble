from dataclasses import asdict, dataclass

from ..clock import Clock

CHANGES = "changes.json"
SELF_KINDS = ("personality", "value")
SUGGESTION_KINDS = ("favourite", "preference", "joke")
FORGET_KINDS = ("forget_person", "delete_memory", "delete_drawing", "delete_photo")
KINDS = SELF_KINDS + SUGGESTION_KINDS + FORGET_KINDS + ("trust",)
OPEN = ("waiting_second", "queued")
SECOND_WINDOW_S = 7 * 86400.0
KEEP_CLOSED = 100


@dataclass
class Change:
    id: int
    kind: str
    target: str
    amount: int
    text: str
    asked_by: str
    asked_by_label: str
    why: str
    asked_at: float
    status: str
    seconded_by: str | None = None
    note: str = ""
    closed_at: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Change | None":
        known = {name: data[name] for name in cls.__dataclass_fields__ if name in data}
        try:
            change = cls(**known)
        except TypeError:
            return None
        return change if change.kind in KINDS else None

    @property
    def big(self) -> bool:
        return self.kind == "value" or (self.kind == "personality" and abs(self.amount) > 1)

    def same_as(self, other: "Change") -> bool:
        if self.kind != other.kind or self.target.lower() != other.target.lower():
            return False
        if self.kind in SELF_KINDS:
            return (self.amount > 0) == (other.amount > 0) and abs(self.amount) == abs(other.amount)
        return self.text.lower() == other.text.lower()

    def summary(self) -> str:
        if self.kind == "personality":
            return f"make my {self.target} {'higher' if self.amount > 0 else 'lower'} by {abs(self.amount)}"
        if self.kind == "value":
            return f"{'raise' if self.amount > 0 else 'lower'} how much I care about {self.target}"
        if self.kind == "favourite":
            return f"make {self.text} my favourite {self.target}"
        if self.kind == "preference":
            return f"set my {self.target.replace('_', ' ')} to {self.text}"
        if self.kind == "joke":
            return f"learn the joke: {self.text}"
        if self.kind == "forget_person":
            return "forget someone"
        if self.kind == "trust":
            return f"count {self.target} as {self.text}"
        return f"{self.kind.replace('_', ' ')}: {self.text or self.target}"


class ChangeBook:
    def __init__(self, data: dict | None, clock: Clock):
        data = data or {}
        self.clock = clock
        self.next_id = int(data.get("next_id", 1) or 1)
        self.items: list[Change] = [c for c in (Change.from_dict(raw) for raw in data.get("items") or [] if isinstance(raw, dict)) if c is not None]
        self.last_personality_night: str | None = data.get("last_personality_night")

    def waiting_partner(self, change: Change, now: float) -> Change | None:
        for other in self.items:
            if other.status == "waiting_second" and other.asked_by != change.asked_by and now - other.asked_at <= SECOND_WINDOW_S and other.same_as(change):
                return other
        return None

    def add(self, change: Change) -> Change:
        change.id = self.next_id
        self.next_id += 1
        self.items.append(change)
        self._trim()
        return change

    def open_items(self) -> list[Change]:
        return [c for c in self.items if c.status in OPEN]

    def queued(self) -> list[Change]:
        return [c for c in self.items if c.status == "queued"]

    def close(self, change: Change, status: str, note: str, now: float) -> None:
        change.status = status
        change.note = note[:200]
        change.closed_at = now

    def expire(self, now: float) -> list[Change]:
        gone = [c for c in self.items if c.status == "waiting_second" and now - c.asked_at > SECOND_WINDOW_S]
        for change in gone:
            self.close(change, "expired", "no second voice from the inner circle in time", now)
        return gone

    def drop_person(self, person_id: str, now: float) -> None:
        for change in self.items:
            if person_id not in (change.asked_by, change.target, change.seconded_by):
                continue
            if change.status in OPEN:
                self.close(change, "dropped", "someone was forgotten", now)
            if change.asked_by == person_id:
                change.asked_by, change.asked_by_label, change.why = "", "someone", ""
            if change.target == person_id:
                change.target = ""
            if change.seconded_by == person_id:
                change.seconded_by = None

    def _trim(self) -> None:
        closed = [c for c in self.items if c.status not in OPEN]
        if len(closed) > KEEP_CLOSED:
            drop = {c.id for c in sorted(closed, key=lambda c: c.closed_at or 0)[: len(closed) - KEEP_CLOSED]}
            self.items = [c for c in self.items if c.id not in drop]

    def to_dict(self) -> dict:
        self._trim()
        return {"format": 1, "next_id": self.next_id, "last_personality_night": self.last_personality_night, "items": [c.to_dict() for c in self.items]}
