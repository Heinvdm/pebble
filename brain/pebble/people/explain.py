from .person import Person
from .qualities import QUALITIES
from .trust import WHAT_THEY_MAY_ASK


def _times(count: int) -> str:
    return "once" if count == 1 else f"{count} times"


def explain(person: Person, now: float) -> list[str]:
    label = person.label
    if person.is_child:
        return [f"{label} is a child: I keep them warm and safe, and I never score children."]
    lines = []
    kept, total = person.kept_count()
    if total:
        lines.append(f"{label} has kept {kept} of {total} promises.")
    for quality in QUALITIES:
        items = [e for e in person.ledger.entries if e.quality == quality and e.counted > 0]
        if not items:
            continue
        good = [e for e in items if e.good]
        bad = [e for e in items if not e.good]
        standing = person.ledger.standing(quality, now)
        parts = []
        if good:
            parts.append(f"good {_times(len(good))}")
        if bad:
            parts.append(f"not so good {_times(len(bad))}")
        latest = items[-1]
        lines.append(f"{label}'s {quality}: {' and '.join(parts)}, about {round(standing.score * 100)}% after fading (latest: {latest.reason}, from my {latest.source}).")
    capped = sum(1 for e in person.ledger.entries if e.counted < e.weight)
    if capped:
        lines.append(f"{_times(capped).capitalize()} I stopped counting for the day, so no one day can buy or break trust.")
    if not lines:
        lines.append(f"I don't know {label} well enough yet to say anything.")
    return lines


TIER_WORDS = {"stranger": "new to me", "child": "a child I look after", "friend": "a friend", "trusted": "someone I trust", "inner circle": "in my inner circle"}


def standing_text(person: Person, tier: str, now: float) -> str:
    may = WHAT_THEY_MAY_ASK.get(tier, WHAT_THEY_MAY_ASK["stranger"])
    return " ".join([f"You are {TIER_WORDS.get(tier, 'new to me')}, so you may ask for {may}."] + explain(person, now))
