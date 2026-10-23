from dataclasses import dataclass

from .book import PeopleBook
from .person import Person

STRANGER = "stranger"
CHILD = "child"
FRIEND = "friend"
TRUSTED = "trusted"
INNER = "inner circle"
TIERS = (STRANGER, CHILD, FRIEND, TRUSTED, INNER)
OVERRIDES = (STRANGER, FRIEND, TRUSTED, INNER)
RANK = {STRANGER: 0, CHILD: 0, FRIEND: 1, TRUSTED: 2, INNER: 3}
FRIEND_DAYS = 3
FRIEND_BAD_LIMIT = 1.0
TRUSTED_SCORE = 0.75
TRUSTED_AMOUNT = 4.0
TRUSTED_SPAN_DAYS = 14.0
INNER_MAX = 3
FRIENDLY_RELATIONSHIPS = frozenset({"family", "friend"})


@dataclass(frozen=True)
class Allowed:
    talk_and_play: bool = True
    small_tasks: bool = False
    teach_self: bool = False
    add_birthday: bool = False
    sticky_stop: bool = False
    forget_and_delete: bool = False
    suggest: bool = False
    change_self: bool = False


ALLOWED = {
    STRANGER: Allowed(),
    CHILD: Allowed(teach_self=True),
    FRIEND: Allowed(small_tasks=True, teach_self=True, add_birthday=True),
    TRUSTED: Allowed(small_tasks=True, teach_self=True, add_birthday=True, sticky_stop=True, forget_and_delete=True, suggest=True),
    INNER: Allowed(small_tasks=True, teach_self=True, add_birthday=True, sticky_stop=True, forget_and_delete=True, suggest=True, change_self=True),
}
WHAT_THEY_MAY_ASK = {
    STRANGER: "talk and play",
    CHILD: "talk and play, and tell you their name and what they like",
    FRIEND: "talk and play, small tasks, tell you their name, likes and birthday",
    TRUSTED: "small tasks, a stop that holds, suggestions for favourites and jokes, and asking you to forget or delete things (you decide)",
    INNER: "everything a trusted person may, and asking you to change your personality or values (you sleep on it and may say no)",
}


def at_least(tier: str, wanted: str) -> bool:
    return tier != CHILD and RANK.get(tier, 0) >= RANK[wanted]


def _trusted_by_evidence(person: Person, now: float) -> bool:
    trust = person.ledger.standing("trustworthiness", now)
    kind = person.ledger.standing("kindness", now)
    return (
        trust.score >= TRUSTED_SCORE
        and kind.score >= TRUSTED_SCORE
        and trust.amount >= TRUSTED_AMOUNT
        and kind.amount >= TRUSTED_AMOUNT
        and person.ledger.span_days(("trustworthiness", "kindness")) >= TRUSTED_SPAN_DAYS
    )


def _friend(person: Person, now: float, inner_ids: set[str]) -> bool:
    if person.relationship in FRIENDLY_RELATIONSHIPS:
        return True
    if person.introduced_by and person.introduced_by in inner_ids:
        return True
    return person.days_met >= FRIEND_DAYS and person.ledger.bad_total(now) < FRIEND_BAD_LIMIT


def tiers(book: PeopleBook, now: float) -> dict[str, str]:
    result: dict[str, str] = {}
    owner_ids = {p.id for p in book.people.values() if p.is_owner}
    for person in book.people.values():
        if person.is_owner:
            result[person.id] = INNER
        elif person.is_child:
            result[person.id] = CHILD
        elif person.override in OVERRIDES and person.override != INNER:
            result[person.id] = person.override
        elif person.override == INNER or _trusted_by_evidence(person, now):
            result[person.id] = TRUSTED
        else:
            result[person.id] = STRANGER
    promoted = sorted((p for p in book.people.values() if p.override == INNER and not p.is_owner and not p.is_child), key=lambda p: (p.first_met, p.id))
    for person in promoted[:INNER_MAX]:
        result[person.id] = INNER
    inner_ids = {pid for pid, tier in result.items() if tier == INNER} | owner_ids
    for person in book.people.values():
        if result[person.id] == STRANGER and person.override is None and _friend(person, now, inner_ids):
            result[person.id] = FRIEND
    return result


def tier_of(book: PeopleBook, person: Person | None, now: float) -> str:
    if person is None:
        return STRANGER
    return tiers(book, now).get(person.id, STRANGER)


def allowed(tier: str) -> Allowed:
    return ALLOWED.get(tier, ALLOWED[STRANGER])
