import logging
import math
import re
from dataclasses import dataclass

from ..clock import iso
from ..respect import PEOPLE_WORDS, is_alive
from ..things.words import canonical, is_animal
from .book import Entry, cosine, pack

log = logging.getLogger(__name__)

SURE_EXAMPLES = 2
ASK_PER_DAY = 3
ASK_GAP_S = 900.0
ALIVE_MATCH = 0.75
CENTRE_DEG = 15.0
PERSON_CENTRE_DEG = 12.0
PERSON_BIG = 0.45
MARGIN = 0.04
TOP = 2
UNSURE_GAP = 0.08
NEAR_MISS = 0.12
OPPOSITES = (("messy", "tidy"), ("open", "shut"), ("open", "closed"), ("locked", "unlocked"), ("on", "off"), ("full", "empty"), ("clean", "dirty"), ("wet", "dry"), ("up", "down"))
ALIVE_NO = "I don't learn names for people or animals that way."
LOOK_AWAY = "Not now — I'm giving someone privacy."
NO_EYES = "I can't see yet, so I can't learn what that looks like."
NOTHING = "I can't see anything there to learn from."
LOOK_QUESTION = "In a few words, what does this look like?"
THING_WORDS = re.compile(r"\b(?:toy|ball|mug|cup|sock|shoe|slipper|book|bowl|plate|bag|box|blanket|pillow|cushion|bottle|key|keys|remote|clicker|teddy|doll|block|car|bone|mouse|stick)\b")


@dataclass(frozen=True)
class Captured:
    vector: tuple = ()
    look: str = ""
    label: str = ""
    problem: str = ""


def names_alive(words: str, people: tuple = ()) -> bool:
    for word in re.findall(r"[a-z']+", str(words or "").lower()):
        if word.endswith("'s") or word.endswith("s'"):
            continue
        if word in people or word in PEOPLE_WORDS or is_animal(canonical(word) or word) or is_alive(word):
            return True
    return False


def opposite(name: str, other: str) -> bool:
    a, b = f" {name} ", f" {other} "
    for left, right in OPPOSITES:
        for x, y in ((left, right), (right, left)):
            if f" {x} " in a and f" {y} " in b and a.replace(f" {x} ", " ") == b.replace(f" {y} ", " "):
                return True
    return False


def judge(entry: Entry, vector, others: list[Entry] = ()) -> tuple[str, float]:
    yes = [v for v, good in entry.vectors() if good]
    no = [v for v, good in entry.vectors() if not good]
    for other in others:
        if other.tag != entry.tag and other.look == entry.look and opposite(entry.name, other.name):
            no.extend(v for v, good in other.vectors() if good)
            yes.extend(v for v, good in other.vectors() if not good)
    if not yes or not vector:
        return "unsure", 0.0
    near_yes = _top(yes, vector)
    spread = min((cosine(a, b) for i, a in enumerate(yes) for b in yes[i + 1:]), default=0.9)
    floor = min(0.95, max(0.5, spread - 0.03))
    if no:
        near_no = _top(no, vector)
        gap = near_yes - near_no
        if near_yes < floor - UNSURE_GAP or gap <= -MARGIN:
            return "no", min(gap, near_yes - floor)
        if gap >= MARGIN:
            return "yes", gap
        return "unsure", gap
    if near_yes >= floor:
        return "yes", near_yes - floor
    if near_yes < floor - UNSURE_GAP:
        return "no", near_yes - floor
    return "unsure", near_yes - floor


def _top(vectors: list, vector) -> float:
    scores = sorted((cosine(v, vector) for v in vectors), reverse=True)[:TOP]
    return sum(scores) / len(scores) if scores else 0.0


class Concepts:
    def __init__(self, teaching):
        self.teaching = teaching
        self.asking: dict | None = None
        self.asked_at = -math.inf

    @property
    def life(self):
        return self.teaching.life

    @property
    def book(self):
        return self.teaching.book

    def all(self) -> list[Entry]:
        return self.book.of_kind("concept")

    def find(self, name: str) -> Entry | None:
        name = " ".join(str(name or "").lower().split())
        for entry in self.all():
            if name and (name == entry.name or name in entry.aliases):
                return entry
        return None

    def names(self) -> list[str]:
        return [entry.name for entry in self.all()]

    def _people(self) -> tuple:
        return tuple(n.lower() for person in self.life.company.book.people.values() for n in person.names + person.nicknames if n)

    def _privacy(self) -> str:
        privacy = getattr(self.life, "privacy", None)
        try:
            return privacy.refusal() or "" if privacy is not None else ""
        except Exception:
            return LOOK_AWAY

    def _subject(self, sight, thingish: bool):
        held = [t for t in sight.things if t.held]
        if held:
            return held[0]
        if not thingish:
            return None
        middle = [t for t in sight.things if abs(t.bearing_deg) <= CENTRE_DEG]
        if not middle:
            return None
        return min(middle, key=lambda t: abs(t.bearing_deg) - 0.01 * t.width_frac * t.height_frac)

    async def capture(self, name: str, words: str = "") -> Captured:
        eyes = self.life.p.eyes
        if names_alive(name, self._people()) or names_alive(words, self._people()):
            return Captured(problem=ALIVE_NO)
        refused = self._privacy()
        if refused:
            return Captured(problem=refused)
        if not getattr(eyes, "available", False):
            return Captured(problem=NO_EYES)
        sight = eyes.latest(1.5)
        if sight is None:
            return Captured(problem=NO_EYES)
        if any(abs(p.bearing_deg) <= PERSON_CENTRE_DEG and p.height_frac >= PERSON_BIG for p in sight.people):
            return Captured(problem=ALIVE_NO)
        thingish = bool(THING_WORDS.search(f"{name} {words}"))
        subject = self._subject(sight, thingish)
        if subject is not None and (subject.animal or is_animal(canonical(subject.label) or subject.label) or is_alive(subject.label)):
            return Captured(problem=ALIVE_NO)
        vector = None
        look = "place"
        label = ""
        if subject is not None and subject.track is not None and getattr(eyes, "fingerprint", None) is not None:
            vector = await eyes.fingerprint(subject.track)
            look, label = "thing", subject.label
        if vector is None:
            if thingish:
                return Captured(problem=NOTHING)
            placing = getattr(eyes, "place_print", None)
            vector = await placing() if placing is not None else None
            look = "place"
        if not vector:
            return Captured(problem=NOTHING)
        for animal in sight.things:
            if animal.track is None or not (animal.animal or is_animal(canonical(animal.label) or animal.label)):
                continue
            seen = await eyes.fingerprint(animal.track) if getattr(eyes, "fingerprint", None) is not None else None
            if seen and cosine(seen, vector) >= ALIVE_MATCH:
                return Captured(problem=ALIVE_NO)
        return Captured(tuple(float(v) for v in vector), look, label)

    async def describe(self) -> str:
        pictures = getattr(self.life.commands, "pictures", None)
        if pictures is None or self._privacy():
            return ""
        try:
            if not await pictures.can_look():
                return ""
            answer, sure = await pictures.ask(LOOK_QUESTION)
        except Exception:
            log.exception("could not ask the picture model what an example looks like")
            return ""
        answer = " ".join(str(answer or "").split())[:80]
        return answer if sure and answer else ""

    def add(self, entry: Entry, captured: Captured, yes: bool, by: str | None, said: str = "") -> Entry:
        entry.look = entry.look or captured.look
        entry.prints = (list(entry.prints) + [{"v": pack(captured.vector), "yes": bool(yes), "by": by, "at": iso(self.life.p.clock.now()), "said": said[:80], "label": captured.label}])[-24:]
        return entry

    def sure(self, entry: Entry) -> bool:
        return sum(1 for _, good in entry.vectors() if good) >= SURE_EXAMPLES

    async def view(self, entry: Entry) -> tuple | None:
        eyes = self.life.p.eyes
        if self._privacy() or not getattr(eyes, "available", False):
            return None
        if entry.look == "thing":
            return None
        placing = getattr(eyes, "place_print", None)
        found = await placing() if placing is not None else None
        return tuple(found) if found else None

    async def things_in_view(self, entry: Entry) -> list[tuple]:
        eyes = self.life.p.eyes
        if self._privacy() or not getattr(eyes, "available", False) or getattr(eyes, "fingerprint", None) is None:
            return []
        sight = eyes.latest(1.5)
        if sight is None:
            return []
        out = []
        for thing in sight.things:
            if thing.track is None:
                continue
            alive = thing.animal or is_animal(canonical(thing.label) or thing.label) or is_alive(thing.label)
            vector = None if alive else await eyes.fingerprint(thing.track)
            out.append((thing, vector, alive))
        return out

    async def state(self, name: str, place: str = "", thing: str = "") -> bool | None:
        entry = self.find(name)
        if entry is None or not self.sure(entry):
            return None
        others = self.all()
        if entry.look == "thing":
            seen = await self.things_in_view(entry)
            if not seen:
                return None
            verdicts = [judge(entry, vector, others)[0] for _, vector, alive in seen if not alive and vector]
            if "yes" in verdicts:
                return True
            return False if verdicts and all(v == "no" for v in verdicts) else None
        if place:
            here = self.teaching.room()
            if here != place:
                return None
        vector = await self.view(entry)
        if vector is None:
            return None
        verdict, _ = judge(entry, vector, others)
        if verdict == "unsure" and entry.line:
            return await self._close_look(entry)
        return {"yes": True, "no": False}.get(verdict)

    async def _close_look(self, entry: Entry) -> bool | None:
        pictures = getattr(self.life.commands, "pictures", None)
        if pictures is None:
            return None
        try:
            if not await pictures.can_look():
                return None
            answer, sure = await pictures.ask(f"Does this look like this: {entry.line}? Answer yes or no.")
        except Exception:
            return None
        said = str(answer or "").lower()
        if not sure:
            return None
        if re.match(r"^\s*yes\b", said):
            return True
        if re.match(r"^\s*no\b", said):
            return False
        return None

    async def is_this(self, entry: Entry) -> str:
        if entry.look == "thing":
            seen = await self.things_in_view(entry)
            middle = [(t, v, alive) for t, v, alive in seen if abs(t.bearing_deg) <= CENTRE_DEG or t.held]
            if not middle:
                return "unsure"
            thing, vector, alive = min(middle, key=lambda item: abs(item[0].bearing_deg))
            if alive:
                return "alive"
            return judge(entry, vector, self.all())[0] if vector else "unsure"
        vector = await self.view(entry)
        return judge(entry, vector, self.all())[0] if vector else "unsure"

    def may_ask(self, entry: Entry, now_local) -> bool:
        day = now_local.date().isoformat()
        asked = entry.asked if entry.asked.get("day") == day else {"day": day, "count": 0}
        return int(asked.get("count") or 0) < ASK_PER_DAY

    def count_ask(self, entry: Entry, now_local) -> None:
        day = now_local.date().isoformat()
        asked = entry.asked if entry.asked.get("day") == day else {"day": day, "count": 0}
        asked["count"] = int(asked.get("count") or 0) + 1
        entry.asked = asked

    async def wonder(self, asker_here: bool) -> tuple[Entry, tuple, str] | None:
        if not asker_here:
            return None
        local = self.life.p.clock.local()
        for entry in self.all():
            if not self.sure(entry) or not self.may_ask(entry, local) or entry.look != "place":
                continue
            vector = await self.view(entry)
            if vector is None:
                continue
            verdict, gap = judge(entry, vector, self.all())
            if verdict == "unsure" or abs(gap) <= NEAR_MISS:
                return entry, vector, verdict
        return None
