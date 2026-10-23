import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from ..books import Books
from ..clock import Clock
from . import familyword
from .book import PeopleBook
from .person import Person, clean
from .presence import PRESENT_S, Presence
from .proof import WORD_HOLDS_S, Proof, shown
from .promises import check as check_promises
from .prompt import people_text
from .qualities import NotScored
from .requests import Requests
from .stops import StopGuard, StopNote, says_go, says_stop
from .trust import INNER, allowed, at_least, tiers

SECRET = re.compile(r"\b(secret|don'?t tell|do not tell|between (you and me|us)|keep (it|this) to yourself|just for you|private)\b", re.IGNORECASE)
SET_FAMILY_WORD = re.compile(r"\b(?:my|our) family word is\s+(.+?)\s*[.!]?\s*$", re.IGNORECASE)
TOUCH_EVIDENCE = {"stroke": ("kindness", True, "stroked my screen gently")}
FELT_EVIDENCE = {"shaken": ("respect", False, "shook me while holding me"), "dropped": ("kindness", False, "dropped me while holding me")}
UNKNOWN_FACE_S = PRESENT_S


@dataclass(frozen=True)
class Heard:
    person_id: str | None
    label: str
    text: str
    stop: StopNote | None = None
    released: bool = False
    family_word: bool = False
    private: bool = False
    new_person: bool = False
    sure: bool = False
    track: int | None = None
    addressed: bool | None = None

    def line(self) -> str:
        return f'{self.label} said "{self.text}"'


class Company:
    def __init__(self, books: Books, clock: Clock, presence: Presence | None = None, guard: StopGuard | None = None):
        self.books = books
        self.clock = clock
        self.presence = presence or Presence()
        self.guard = guard or StopGuard()
        self.requests = Requests(books.people, books.changes, self.presence, clock, lambda: books.values, lambda: books.store.read("personality.json", {}))
        self.dirty = False
        self._unknown_face: tuple | None = None
        self._unknown_at = -math.inf
        self._unknown_before = False
        self.visitors = None
        self.asking: dict | None = None
        self.focus: Callable[[], tuple] = lambda: ((), "")

    @property
    def book(self) -> PeopleBook:
        return self.books.people

    def visiting(self) -> bool:
        return bool(getattr(self.visitors, "on", False))

    def tiers(self, now: float | None = None) -> dict[str, str]:
        return tiers(self.book, self.clock.now() if now is None else now)

    def tier(self, person: Person | None, now: float | None = None) -> str:
        return "stranger" if person is None else self.tiers(now).get(person.id, "stranger")

    def here(self, now: float | None = None) -> list[Person]:
        now = self.clock.now() if now is None else now
        return [p for p in (self.book.get(pid) for pid in self.presence.here(now)) if p is not None]

    def someone_new(self, now: float) -> bool:
        return self._unknown_face is not None and now - self._unknown_at <= UNKNOWN_FACE_S

    def seen_before(self, now: float) -> bool:
        return self._unknown_before and self.someone_new(now)

    def anyone_here(self, now: float | None = None) -> bool:
        now = self.clock.now() if now is None else now
        return bool(self.presence.here(now)) or self.someone_new(now)

    def _known(self, person: Person, at: float) -> None:
        self.book.visit(person, at)
        self.dirty = True

    def see(self, face, at: float | None = None) -> str | None:
        at = self.clock.now() if at is None else at
        match = self.book.match("face", face)
        if match is None:
            if face is not None:
                self._unknown_face, self._unknown_at = tuple(face), at
                sighting, self._unknown_before = self.book.sighted(face, at, learn=not self.visiting())
                self.dirty = self.dirty or (sighting is not None and not self.visiting())
            return None
        person = self.book.get(match.person_id)
        self.presence.saw(person.id, at)
        self._known(person, at)
        return person.id

    def claim_new_face(self, at: float) -> tuple | None:
        if not self.someone_new(at):
            return None
        face, self._unknown_face, self._unknown_before = self._unknown_face, None, False
        return face

    def _speaker(self, voice, at: float, meet: bool = True, speaker: str | None = None) -> tuple[Person | None, bool, bool]:
        if speaker is not None and self.book.get(speaker) is not None:
            return self.book.get(speaker), False, False
        match = self.book.match("voice", voice)
        if match is not None:
            return self.book.get(match.person_id), False, True
        if voice is not None and (not meet or self.visiting()):
            return None, False, False
        if voice is not None:
            face = self.claim_new_face(at)
            person = self.book.meet(at, voice=voice, face=face)
            if face is not None:
                self.presence.saw(person.id, at)
            return person, True, False
        sole = self.presence.sole(at)
        return (self.book.get(sole), False, False) if sole else (None, False, False)

    def _screen(self, person: Person | None, text: str, at: float) -> tuple[str, bool]:
        own = False
        for other in self.book.people.values():
            text, found = familyword.screen(text, other.family_word)
            if found and person is not None and other.id == person.id:
                own = True
        if own:
            self.presence.said_family_word(person.id, at)
        return text, own

    def _set_family_word(self, person: Person | None, text: str, at: float) -> str:
        match = SET_FAMILY_WORD.search(text)
        if match is None:
            return text
        masked = text[: match.start(1)] + familyword.MASK
        if person is None or not self.presence.seen_and_heard(person.id, at) or not at_least(self.tier(person, at), INNER):
            return masked
        try:
            self.book.set_family_word(person, match.group(1))
        except familyword.BadFamilyWord:
            return masked
        self.dirty = True
        return masked

    def hear(self, text: str, voice=None, at: float | None = None, loud: bool = False, meet: bool = True, speaker: str | None = None, proof: Proof | None = None, addressed: bool | None = None) -> Heard:
        at = self.clock.now() if at is None else at
        text = clean(text, 400)
        person, new, matched = self._speaker(voice, at, meet, speaker)
        if person is not None:
            self.presence.heard(person.id, at)
            if not new:
                self._known(person, at)
            self.dirty = True
        text = self._set_family_word(person, text, at)
        text, word = self._screen(person, text, at)
        label = "someone" if person is None else person.label
        tier = self.tier(person, at)
        stop = None
        released = False
        if says_stop(text):
            stop = self.guard.stop(person.id if person else None, label, allowed(tier).sticky_stop and person is not None, at)
        elif says_go(text):
            released = self.guard.go(allowed(tier).sticky_stop and person is not None)
        if loud and person is not None:
            self._evidence(person, "respect", False, "shouted at me", at)
        sure = person is not None and (word or self.presence.family_word(person.id, at, WORD_HOLDS_S) or shown(person, proof, matched, self.presence, at))
        track = proof.track if proof is not None and proof.lips else None
        return Heard(person.id if person else None, label, text, stop, released, word, bool(SECRET.search(text)) and person is not None, new, bool(sure), track, addressed)

    def _evidence(self, person: Person, quality: str, good: bool, reason: str, at: float) -> None:
        try:
            self.book.evidence(person, quality, good, "senses", reason, at)
        except NotScored:
            return
        self.dirty = True

    def touched(self, kind: str, at: float | None = None) -> str | None:
        at = self.clock.now() if at is None else at
        sole = self.presence.sole(at)
        person = self.book.get(sole) if sole else None
        if person is None:
            if self.presence.here(at) or self.visiting():
                return None
            face = self.claim_new_face(at)
            if face is None:
                return None
            person = self.book.meet(at, face=face)
            self.presence.saw(person.id, at)
        else:
            self._known(person, at)
        self.presence.touched(person.id, at)
        if kind in TOUCH_EVIDENCE:
            self._evidence(person, *TOUCH_EVIDENCE[kind], at)
        self.dirty = True
        return person.id

    def felt(self, kind: str, at: float | None = None) -> str | None:
        at = self.clock.now() if at is None else at
        sole = self.presence.sole(at)
        if sole is None or kind not in FELT_EVIDENCE or not self.presence.in_hands(sole, at):
            return None
        person = self.book.get(sole)
        if person is None:
            return None
        self._evidence(person, *FELT_EVIDENCE[kind], at)
        return person.id

    def task_refusal(self, ref: str) -> str | None:
        now = self.clock.now()
        person = self.book.find(ref)
        if person is None or person.id not in self.presence.here(now):
            return f"I take tasks from people I can see or hear, and I can't place {clean(ref, 40)}"
        if self.asking is None or person.id not in self.asking:
            return f"I take tasks only from someone who has just asked me, and {person.label} hasn't"
        if not allowed(self.tier(person, now)).small_tasks:
            return f"I'm happy to play with {person.label}, but I take tasks from people I know a little better"
        return None

    def blocked(self, now: float | None = None) -> str | None:
        return self.guard.blocked(self.clock.now() if now is None else now)

    def tick(self, now: float | None = None) -> list[str]:
        now = self.clock.now() if now is None else now
        notes = [news.text for news in check_promises(self.book, self.presence, now)]
        if notes:
            self.dirty = True
        if self.guard.pause_over(now):
            notes.append("your pause after someone said stop is over; decide for yourself whether to keep still, and when in doubt stay still")
        if self.guard.sticky_by is not None and self.guard.lapse(self.presence.last_present(self.guard.sticky_by), now):
            notes.append("the person who told you to stop has gone; you may decide to move again")
        return notes

    def prompt_text(self, now: float, local) -> str:
        try:
            focus, talk = self.focus()
        except Exception:
            focus, talk = (), ""
        return people_text(self.book, self.presence, now, local, self.someone_new(now), self.seen_before(now), tuple(focus), str(talk or ""))

    def private_to(self, now: float) -> str | None:
        here = self.presence.here(now)
        return here[0] if len(here) == 1 and not self.someone_new(now) else None

    def flush(self) -> bool:
        if not self.dirty:
            return False
        self.books.save("people", "changes")
        self.dirty = False
        return True

    def local(self, ts: float) -> datetime:
        return self.clock.local(ts)
