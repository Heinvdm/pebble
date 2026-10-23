import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from .book import PeopleBook
from .person import Person, Promise
from .presence import Presence
from .qualities import NotScored

EARLY_S = 900.0
LATE_S = 1800.0
MAX_AHEAD_S = 30 * 86400.0
PROMISE_QUALITIES = ("reliability", "trustworthiness")
_CLOCK = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$", re.IGNORECASE)


class BadDue(ValueError):
    pass


@dataclass(frozen=True)
class PromiseNews:
    person_id: str
    promise_id: int
    outcome: str
    text: str


def due_at(local_now: datetime, minutes: float | None = None, clock_time: str | None = None) -> float:
    if minutes is not None:
        if not 1 <= minutes <= MAX_AHEAD_S / 60:
            raise BadDue("a promise is due between a minute and a month from now")
        return local_now.timestamp() + minutes * 60.0
    match = _CLOCK.match(clock_time or "")
    if match is None:
        raise BadDue("say when, as minutes from now or a time like 18:00")
    hour, minute, half = int(match.group(1)), int(match.group(2) or 0), (match.group(3) or "").lower()
    if half == "pm" and hour < 12:
        hour += 12
    if half == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise BadDue("that is not a time of day")
    target = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= local_now:
        target += timedelta(days=1)
    return target.timestamp()


def _window_start(promise: Promise) -> float:
    return promise.due - min(EARLY_S, max(0.0, promise.due - promise.made_at) / 2.0)


def _score(book: PeopleBook, person: Person, kept: bool, promise: Promise, now: float) -> None:
    reason = f"{'kept' if kept else 'broke'} a promise: {promise.what}"
    for quality in PROMISE_QUALITIES:
        try:
            book.evidence(person, quality, kept, "promise", reason, now)
        except NotScored:
            return


def check(book: PeopleBook, presence: Presence, now: float) -> list[PromiseNews]:
    news = []
    for person in list(book.people.values()):
        for promise in person.open_promises():
            if promise.by == "me":
                if now >= promise.due:
                    promise.status = "reminded"
                    promise.closed_at = now
                    news.append(PromiseNews(person.id, promise.id, "due", f"your promise to {person.label} is due now: {promise.what}"))
                continue
            seen_at = presence.last_present(person.id)
            if now >= _window_start(promise) and _window_start(promise) <= seen_at <= promise.due + LATE_S:
                promise.status, promise.closed_at = "kept", now
                _score(book, person, True, promise, now)
                news.append(PromiseNews(person.id, promise.id, "kept", f"{person.label} kept a promise: {promise.what}"))
            elif now > promise.due + LATE_S:
                promise.status, promise.closed_at = "broken", now
                _score(book, person, False, promise, now)
                news.append(PromiseNews(person.id, promise.id, "broken", f"{person.label} did not keep a promise: {promise.what}"))
    return news
