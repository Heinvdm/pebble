from datetime import datetime
from typing import Callable

from ..mind.select import chars, content
from .book import PeopleBook
from .person import Person
from .presence import Presence
from .trust import WHAT_THEY_MAY_ASK, tiers

FAIRNESS = (
    "Be equally warm and kind to everyone. How well you know someone only changes what they may ask of you, never how you treat them. "
    "Never tell anyone how you rate them unless they ask about themselves, and never pass on what someone told you in private."
)
SHOWN = 5
FULL_MOST = 4
PERSON_TOKENS = 60
PEOPLE_TOKENS = 250
HEAD = "People here now:"
ALSO = "Also here: "


def _promises(person: Person, local: Callable[[float], datetime]) -> list[str]:
    out = []
    for promise in person.open_promises()[-SHOWN:]:
        when = local(promise.due).strftime("%a %H:%M")
        if promise.by == "them":
            out.append(f"promised you: {promise.what} (by {when})")
        else:
            out.append(f"you promised them: {promise.what} (by {when})")
    return out


def ranked(items: list[str], talk: str) -> list[str]:
    wanted = content(talk) if talk else set()
    order = sorted(range(len(items)), key=lambda n: (-len(content(items[n]) & wanted) if wanted else 0, -n))
    return [items[n] for n in order]


def _render(head: list[str], groups: list[tuple[str, list[str]]]) -> str:
    parts = list(head)
    for title, items in groups:
        if not items:
            continue
        if title:
            parts.append(f"{title}: " + ", ".join(items))
        else:
            parts.extend(items)
    return "; ".join(parts)


def describe(person: Person, tier: str, private: bool, local: Callable[[float], datetime], talk: str = "", limit: int | None = None, asks: bool = True) -> str:
    limit = chars(PERSON_TOKENS) if limit is None else limit
    head = [person.label + (f" ({person.relationship})" if person.relationship else "")]
    if person.nicknames:
        head.append("also called " + ", ".join(person.nicknames[-3:]))
    tail = "may ask you for " + WHAT_THEY_MAY_ASK.get(tier, WHAT_THEY_MAY_ASK["stranger"]) if asks else ""
    pools = [("likes", person.likes), ("dislikes", person.dislikes), ("wishes", person.wishes), ("", _promises(person, local))]
    if private and person.private:
        pools.append(("told you in private, only for them", person.private))
    choices = [(title, ranked(items, talk)[:SHOWN]) for title, items in pools]
    picked: list[list[str]] = [[] for _ in choices]
    room = limit - (len(tail) + 2 if tail else 0)
    growing = True
    while growing:
        growing = False
        for n, (title, items) in enumerate(choices):
            if len(picked[n]) >= len(items):
                continue
            picked[n].append(items[len(picked[n])])
            if len(_render(head, [(t, p) for (t, _), p in zip(choices, picked)])) > room:
                picked[n].pop()
                continue
            growing = True
    groups = []
    for (title, items), chosen in zip(pools, picked):
        keep = set(chosen)
        groups.append((title, [item for item in items if item in keep]))
    body = _render(head, groups)
    return f"{body}; {tail}" if tail else body


def legend(asking: dict) -> list[str]:
    out = []
    for tier, names in asking.items():
        who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        out.append(f"{who} may ask you for {WHAT_THEY_MAY_ASK.get(tier, WHAT_THEY_MAY_ASK['stranger'])}.")
    return out


def people_text(
    book: PeopleBook,
    presence: Presence,
    now: float,
    local: Callable[[float], datetime],
    someone_new: bool = False,
    seen_before: bool = False,
    focus: tuple = (),
    talk: str = "",
    budget: int | None = None,
) -> str:
    here = [book.get(pid) for pid in presence.here(now)]
    here = [person for person in here if person is not None]
    if not here and not someone_new:
        return ""
    budget = chars(PEOPLE_TOKENS) if budget is None else budget
    table = tiers(book, now)
    alone = len(here) == 1 and not someone_new
    first = [pid for pid in dict.fromkeys(focus) if any(p.id == pid for p in here)]
    order = sorted(here, key=lambda p: (first.index(p.id) if p.id in first else len(first), here.index(p)))
    asking: dict = {}
    for person in here:
        asking.setdefault(table.get(person.id, "stranger"), []).append(person.label)
    new = []
    if someone_new and seen_before:
        new.append("- someone you have not met yet is in view; you have seen them before, but you don't know them, so they are still new to you")
    elif someone_new:
        new.append("- someone you have not met yet is in view")
    rules = legend(asking)
    fixed = len(HEAD) + sum(len(line) + 1 for line in new + rules) + len(FAIRNESS) + 1
    described: dict = {}
    named: list[Person] = []
    for person in order:
        line = "- " + describe(person, table.get(person.id, "stranger"), alone, local, talk, asks=False)
        also = len(ALSO) + sum(len(p.label) + 2 for p in named + [person]) + 1 if named or len(described) >= FULL_MOST else 0
        used = fixed + sum(len(x) + 1 for x in described.values()) + also
        if len(described) < FULL_MOST and used + len(line) + 1 <= budget:
            described[person.id] = line
        else:
            named.append(person)
    lines = [HEAD] + [described[p.id] for p in here if p.id in described]
    if named:
        lines.append(ALSO + ", ".join(p.label for p in here if p in named) + ".")
    lines.extend(new)
    lines.extend(rules)
    lines.append(FAIRNESS)
    return "\n".join(lines)
