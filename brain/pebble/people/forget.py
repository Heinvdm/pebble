import logging
import re

from ..books import FILES, Books
from ..diary import DIARY
from ..selfstore import SelfStore
from .person import Person
from .presence import Presence

log = logging.getLogger(__name__)

FORGET_LETTERS = 4
FORGET_MOST = 5


def forget_phrase(text: str) -> re.Pattern | None:
    words = re.findall(r"[a-z0-9']+", str(text or "").lower())
    if sum(len(word) for word in words) < FORGET_LETTERS:
        return None
    return re.compile(r"\b" + r"\W+".join(re.escape(word) for word in words) + r"\b")


def _mentions(names: list[str]):
    patterns = [re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE) for name in names if name]
    return lambda text: any(p.search(str(text or "")) for p in patterns)


def scrub(store: SelfStore, name: str, data) -> None:
    store.write(name, data, keep_backup=False)


def forget_person(books: Books, store: SelfStore, person: Person, presence: Presence | None, now: float, forgetters=()) -> dict:
    names = [n for n in person.names + person.nicknames if n.strip()]
    for forget in forgetters:
        try:
            forget(person.id, names)
        except Exception:
            log.exception("a part of Pebble could not forget %s", person.id)
    mentions = _mentions(names)
    linked = set(person.diary)
    books.people.forget(person)
    books.changes.drop_person(person.id, now)
    for change in books.changes.items:
        if mentions(change.why) or mentions(change.text) or mentions(change.note):
            change.why, change.text, change.note = "", "", "about someone forgotten"
    if presence is not None:
        presence.forget(person.id)
    for other in books.people.people.values():
        for field in ("likes", "dislikes", "wishes", "private"):
            setattr(other, field, [note for note in getattr(other, field) if not mentions(note)])
        for promise in other.promises:
            if mentions(promise.what):
                promise.what = "something about someone forgotten"
    facts_before = len(books.memory.facts)
    books.memory.facts = [f for f in books.memory.facts if not mentions(f.get("about")) and not mentions(f.get("text"))]
    events_before = len(books.calendar.personal)
    books.calendar.personal = [e for e in books.calendar.personal if not mentions(e.get("person")) and not mentions(e.get("title"))]
    diary = store.read_lines(DIARY)
    kept = [entry for entry in diary if entry.get("at") not in linked and not mentions(entry.get("text"))]
    if len(kept) != len(diary):
        store.rewrite_lines(DIARY, kept)
    for key in ("people", "changes", "memory", "calendar"):
        scrub(store, FILES[key], getattr(books, key).to_dict())
    return {"facts": facts_before - len(books.memory.facts), "events": events_before - len(books.calendar.personal), "diary": len(diary) - len(kept)}
