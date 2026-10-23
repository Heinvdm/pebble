from ..clock import Clock
from ..owner import OwnerGrant
from .familyword import make as make_family_word
from .person import Person, clean
from .prints import KINDS, CosineMatcher, Match, Matcher, normalise
from .qualities import DAY_S, Evidence, NotScored
from .sightings import Sighting, Sightings

PEOPLE = "people.json"
STRANGER_PRINT_DAYS = 30
PEOPLE_CAP = 500
MEETING_GAP_S = 1800.0


class PeopleBook:
    def __init__(self, data: dict | None, clock: Clock, matcher: Matcher | None = None):
        data = data or {}
        self.clock = clock
        self.matcher = matcher or CosineMatcher()
        self.thresholds: dict[str, float] = {}
        self.setup = False
        self.next_id = int(data.get("next_id", 1) or 1)
        self.people: dict[str, Person] = {}
        for raw in data.get("people") or []:
            person = Person.from_dict(raw) if isinstance(raw, dict) else None
            if person is not None:
                self.people[person.id] = person
                if person.id[1:].isdigit():
                    self.next_id = max(self.next_id, int(person.id[1:]) + 1)
        self.sightings = Sightings(data.get("seen"), data.get("next_seen", 1))

    def day(self, at: float | None = None) -> str:
        return self.clock.local(self.clock.now() if at is None else at).date().isoformat()

    def get(self, person_id: str | None) -> Person | None:
        return self.people.get(person_id) if person_id else None

    def find(self, ref: str | None) -> Person | None:
        if not ref:
            return None
        if ref in self.people:
            return self.people[ref]
        hits = [p for p in self.people.values() if p.answers_to(ref)]
        return hits[0] if len(hits) == 1 else None

    def owner(self) -> Person | None:
        return next((p for p in self.people.values() if p.is_owner), None)

    def meet(self, at: float, voice=None, face=None) -> Person:
        person = Person(f"p{self.next_id}", at, at)
        self.next_id += 1
        if voice is not None:
            person.add_print("voice", voice, at)
        if face is not None:
            clean_face = normalise(face)
            seen = self.sightings.take(clean_face, self._matcher("face")) if clean_face is not None else None
            for earlier in seen.prints if seen is not None else []:
                if tuple(earlier["vector"]) != clean_face:
                    person.add_print("face", earlier["vector"], earlier["at"])
            person.add_print("face", face, at)
        self.people[person.id] = person
        self._cap()
        self.visit(person, at)
        return person

    def _cap(self) -> None:
        if len(self.people) <= PEOPLE_CAP:
            return
        loose = sorted((p for p in self.people.values() if not p.names and not p.relationship), key=lambda p: p.last_seen)
        for person in loose[: len(self.people) - PEOPLE_CAP]:
            del self.people[person.id]

    def match(self, kind: str, vector) -> Match | None:
        clean_vector = normalise(vector)
        if clean_vector is None or kind not in KINDS:
            return None
        candidates = {pid: p.print_vectors(kind) for pid, p in self.people.items()}
        return self._matcher(kind).best(clean_vector, {pid: prints for pid, prints in candidates.items() if prints})

    def _matcher(self, kind: str) -> Matcher:
        return CosineMatcher(self.thresholds[kind]) if kind in self.thresholds else self.matcher

    def sighted(self, face, at: float, learn: bool = True) -> tuple[Sighting | None, bool]:
        clean_face = normalise(face)
        if clean_face is None:
            return None, False
        found = self.sightings.best(clean_face, self._matcher("face"))
        learn = learn and not self.setup
        if found is None:
            return (self.sightings.add(clean_face, at, self.day(at)) if learn else None), False
        before = found.visits > 1 or at - found.last_seen >= MEETING_GAP_S
        if learn:
            self.sightings.refresh(found, clean_face, at, self.day(at), MEETING_GAP_S)
        return found, before

    def visit(self, person: Person, at: float) -> bool:
        day = self.day(at)
        if person.meetings == 0 or at - person.last_seen >= MEETING_GAP_S:
            person.meetings += 1
        person.last_seen = max(person.last_seen, at)
        person.saw_on(day)
        if person.last_day == day:
            return False
        person.last_day = day
        person.days_met += 1
        if not person.is_child and not self.setup:
            person.ledger.add("familiarity", True, "senses", "we met again on a new day", at, day)
        return True

    def evidence(self, person: Person, quality: str, good: bool, source: str, reason: str, at: float | None = None) -> Evidence:
        if person.is_child:
            raise NotScored("children are never scored")
        if self.setup:
            raise NotScored("nothing about people counts while you are being set up")
        at = self.clock.now() if at is None else at
        return person.ledger.add(quality, good, source, reason, at, self.day(at))

    def make_owner(self, person: Person, grant: OwnerGrant) -> None:
        if not isinstance(grant, OwnerGrant):
            raise PermissionError("only the owner's passphrase names the owner")
        for other in self.people.values():
            if other.is_owner:
                other.relationship = "family"
        person.relationship = "owner"
        person.override = None

    def set_family_word(self, person: Person, phrase: str) -> None:
        person.family_word = make_family_word(phrase)

    def forget(self, person: Person) -> bool:
        self.sightings.drop_like(person.print_vectors("face"), self._matcher("face"))
        return self.people.pop(person.id, None) is not None

    def expire_prints(self, now: float, strangers: set[str]) -> list[str]:
        gone = []
        for person in list(self.people.values()):
            if person.id not in strangers or now - person.last_seen < STRANGER_PRINT_DAYS * DAY_S:
                continue
            if person.has_prints():
                person.drop_prints()
                gone.append(person.id)
            if not person.names and not person.relationship:
                del self.people[person.id]
        gone.extend(self.sightings.expire(now, STRANGER_PRINT_DAYS * DAY_S))
        return gone

    def prune(self, now: float) -> int:
        return sum(p.ledger.prune(now) for p in self.people.values())

    def to_dict(self) -> dict:
        kept = [p for p in self.people.values() if not self.setup or p.names or p.nicknames or p.relationship]
        seen = [] if self.setup else self.sightings.to_list()
        return {"format": 1, "next_id": self.next_id, "people": [p.to_dict() for p in kept], "seen": seen, "next_seen": self.sightings.next_id}


def name_or_label(person: Person | None) -> str:
    return "someone" if person is None else clean(person.label, 60)
