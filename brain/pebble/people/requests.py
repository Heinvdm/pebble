from dataclasses import dataclass
from typing import Callable

from ..clock import Clock
from ..values import Values
from .book import STRANGER_PRINT_DAYS, PeopleBook
from .changes import FORGET_KINDS, KINDS, SELF_KINDS, Change, ChangeBook
from .person import Person, clean
from .presence import Presence
from .trust import INNER, RANK, STRANGER, TRUSTED, at_least, tiers
from .weigh import refusal

NEEDS = {
    "personality": INNER,
    "value": INNER,
    "favourite": TRUSTED,
    "preference": TRUSTED,
    "joke": TRUSTED,
    "forget_person": TRUSTED,
    "delete_memory": TRUSTED,
    "delete_drawing": TRUSTED,
    "delete_photo": TRUSTED,
    "trust": "owner",
}
NOT_YET = {
    STRANGER: "I'm happy to talk and play, but that is something I only do for people I know well.",
}


@dataclass(frozen=True)
class Answer:
    ok: bool
    text: str
    change: Change | None = None

    def as_dict(self) -> dict:
        out = {"ok": self.ok, "answer": self.text}
        if self.change is not None:
            out["request"] = {"id": self.change.id, "status": self.change.status}
        return out


def forget_refusal(asker: Person, asker_tier: str, target: Person | None, target_tier: str) -> str | None:
    if target is None:
        return "I don't know who you mean"
    if target.is_owner:
        return "I can't forget my owner; only a full reset does that"
    if target.id == asker.id or asker.is_owner:
        return None
    if RANK.get(target_tier, 0) >= RANK.get(asker_tier, 0):
        return f"I won't forget someone I trust as much as you on your word alone"
    return None


class Requests:
    def __init__(self, book: PeopleBook, changes: ChangeBook, presence: Presence, clock: Clock, values: Callable[[], Values], personality: Callable[[], dict]):
        self.book = book
        self.changes = changes
        self.presence = presence
        self.clock = clock
        self.values = values
        self.personality = personality

    def _gate(self, asker: Person | None, kind: str, now: float, table: dict) -> str | None:
        if kind not in KINDS:
            return "I don't know that kind of request"
        if asker is None:
            return "I need to know who is asking first"
        if not self.presence.seen_and_heard(asker.id, now):
            return f"I need to see and hear {asker.label} to take a request like that"
        tier = table.get(asker.id, STRANGER)
        needed = NEEDS[kind]
        if needed == "owner":
            return None if asker.is_owner else "only my owner decides how I count people"
        if not at_least(tier, needed):
            if kind == "forget_person" and tier in (STRANGER, "child", "friend"):
                return f"I don't forget people on request until I know them well; a visitor's voice and face fade from me after {STRANGER_PRINT_DAYS} days anyway"
            return NOT_YET.get(tier, "that is something I only do for people I trust more")
        if needed == INNER and not self.presence.family_word(asker.id, now):
            return "for a change to who I am, I need to hear your family word first"
        return None

    def ask(self, asker_ref: str, kind: str, target: str = "", amount: int = 0, text: str = "", why: str = "") -> Answer:
        now = self.clock.now()
        table = tiers(self.book, now)
        asker = self.book.find(asker_ref)
        problem = self._gate(asker, kind, now, table)
        if problem:
            return Answer(False, problem)
        target, text, why = clean(target, 40), clean(text, 200), clean(why, 160)
        if kind == "forget_person":
            person = self.book.find(target) if target else asker
            problem = forget_refusal(asker, table.get(asker.id, STRANGER), person, table.get(person.id, STRANGER) if person else STRANGER)
            if problem:
                return Answer(False, problem)
            target = person.id
        elif kind == "trust":
            person = self.book.find(target)
            if person is None:
                return Answer(False, "I don't know who you mean")
            target = person.id
        if kind in SELF_KINDS:
            amount = int(amount)
        problem = refusal(kind, target, amount, text, self.values(), self.personality())
        if problem:
            return Answer(False, problem)
        change = Change(0, kind, target, amount, text, asker.id, asker.label, why or "they asked", now, "queued")
        if change.big:
            partner = self.changes.waiting_partner(change, now)
            if partner is None:
                change.status = "waiting_second"
                self.changes.add(change)
                return Answer(True, "That is a big change, so I'll wait until someone else close to me asks for it too, then sleep on it.", change)
            self.changes.close(partner, "merged", f"seconded by {asker.label}", now)
            change.seconded_by = partner.asked_by
        self.changes.add(change)
        if kind in FORGET_KINDS:
            return Answer(True, "I'll think it over tonight and decide.", change)
        return Answer(True, "I'll sleep on it tonight.", change)
