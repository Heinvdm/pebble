import asyncio
import hashlib
import logging
import math
import time

from ..activities.card import key as steps_key
from ..activities.card import slug
from ..activities.skills import content as skill_words
from ..clock import from_iso
from ..hearing.taught import thing_of
from ..house.lists import title
from ..mind.budget import REPLY, TURN
from ..mind.select import HOT, NAMEABLE, Entry, Names, Shelves, chosen_chars, content, cosine, named_chars, pack, score
from ..people.prompt import ranked
from ..people.trust import STRANGER
from ..things.book import age_words
from ..things.facts import spoken_fact
from ..things.guarded import STRANGER_NO

log = logging.getLogger(__name__)

REBUILD_S = 30.0
PLACES_SHOWN = 15
PEOPLE_SHOWN = 12
NAMED_MOST = {REPLY: 3, TURN: 4}
CHOSEN_MOST = 3
LIKES_SHOWN = 3
PERSON_CHARS = 150
EMBED_BATCH = 16
SAME_SKILL = 0.9
MONTH_S = 30 * 86400.0
SCRIPTS = "mine/scripts/index.json"
LESSONS = "lessons.json"
SKILLS_LEAD = "Skills you know: "
LESSONS_LEAD = "Lessons you keep (yours; they never outrank your laws): "
FAMILY = ("owner", "family")


def _when(text: str) -> float:
    try:
        return from_iso(text) if text else 0.0
    except Exception:
        return 0.0


def _key(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8", errors="replace"), digest_size=10).hexdigest()


class Selection:
    def __init__(self, life):
        self.life = life
        p = life.p
        self.store = p.store
        self.clock = p.clock
        self.shelves = Shelves(p.store, p.clock)
        self._names: Names | None = None
        self._entries: list[Entry] = []
        self._built = -math.inf
        self._signature_seen: tuple | None = None
        self.vectors: dict[str, list] = {}
        self.live: list[tuple[str, str]] | None = None
        self.next: list[tuple[str, str]] | None = None
        self.focus_live: tuple = ((), "")
        self.focus_next: tuple | None = None
        self.scans: list[float] = []

    def entries(self) -> list[Entry]:
        out: list[Entry] = []
        for source in (self._people, self._rooms, self._spots, self._things, self._skills, self._scripts, self._rules, self._lists, self._sounds, self._lessons, self._howtos):
            try:
                out.extend(source())
            except Exception:
                log.exception("could not list one kind of stored item for naming")
        return out

    def _people(self) -> list[Entry]:
        out = []
        for person in self.life.company.book.people.values():
            names = tuple(str(n) for n in list(person.names) + list(person.nicknames) if n)
            if not names:
                continue
            out.append(Entry("person", person.id, names, t=person.last_seen, used=person.days_met, weight=1.0 if person.relationship in FAMILY else 0.3, about=(person.id,), pinned=True, data=person))
        return out

    def rooms(self) -> list[str]:
        alive = getattr(self.life, "alive", None)
        held = sorted(alive.places()) if alive is not None else []
        return list(dict.fromkeys(list(self.life._places()) + [str(name).lower() for name in held]))

    def _rooms(self) -> list[Entry]:
        return [Entry("room", name, (name,), place=name, pinned=True) for name in self.rooms()]

    def _spots(self) -> list[Entry]:
        nav = getattr(self.life, "nav", None)
        chart = getattr(nav, "chart", None) if nav is not None else None
        if chart is None:
            return []
        return [Entry("spot", place.name, (place.name,), used=place.visits, pinned=True) for place in chart.places if place.kind in ("spot", "room") and place.name]

    def _things(self) -> list[Entry]:
        book = self.life.p.books.things
        out = []
        for thing in book.things.values():
            last = thing.last
            out.append(Entry("thing", thing.label, (thing.label,), t=last.at if last is not None else thing.first, used=thing.seen, data=thing))
        for fact in book.facts.told.values():
            out.append(Entry("fact", fact.name, tuple(dict.fromkeys((fact.name, spoken_fact(fact.name)))), t=fact.checked, data=fact))
        return out

    def _skills(self) -> list[Entry]:
        skills = getattr(self.life, "skills", None)
        if skills is None:
            return []
        out = []
        for skill in skills.all():
            names = tuple(dict.fromkeys([skill.name] + list(skill.aliases)))
            taught = (skill.taught_by or {}).get("id")
            out.append(Entry("skill", slug(skill.name), names, text=f"{skill.name}: {skill.about}", t=_when(skill.last_used) or _when(skill.learned_at), used=max(0, skill.good - skill.bad), about=(taught,) if taught else (), data=skill))
        return out

    def _scripts(self) -> list[Entry]:
        data = self.store.read(SCRIPTS, {}) or {}
        out = []
        for tag, item in (data.get("scripts") or {}).items():
            if not isinstance(item, dict) or not item.get("name"):
                continue
            names = tuple(dict.fromkeys([str(item["name"])] + [str(a) for a in item.get("aliases") or []]))
            out.append(Entry("script", str(tag), names, text=f"{item['name']}: {item.get('about') or ''}", t=_when(str(item.get("last_used") or "")), used=int(item.get("used") or 0), data=item))
        return out

    def _howtos(self) -> list[Entry]:
        teaching = getattr(self.life, "teaching", None)
        if teaching is None:
            return []
        out = []
        for tag, item in teaching.book.index.items():
            if item.get("kind") == "move" or not item.get("name"):
                continue
            names = tuple(dict.fromkeys([str(item["name"])] + [str(a) for a in item.get("aliases") or []]))
            person = item.get("person") or item.get("by")
            out.append(Entry("howto", str(tag), names, text=f"{item['name']}: {item.get('about') or ''}", t=_when(str(item.get("last_used") or "")), used=max(0, int(item.get("good") or 0) - int(item.get("bad") or 0)), about=(person,) if person else (), data=item))
        return out

    def _rules(self) -> list[Entry]:
        rules = getattr(self.life, "rules", None)
        if rules is None:
            return []
        now = self.clock.now()
        return [Entry("rule", str(rule.id), (rule.place,) if rule.kind == "keep_out" and rule.place else (), t=now, place=rule.place, pinned=True, about=(rule.by,) if rule.by else (), data=rule) for rule in rules.holding()]

    def _lists(self) -> list[Entry]:
        house = getattr(self.life, "house", None)
        if house is None:
            return []
        out = []
        for name in house.lists.names():
            items = house.lists.items(name)
            last = max((float(i.get("at") or 0.0) for i in items), default=0.0)
            out.append(Entry("list", name, (name, title(name)), t=last, used=len(items), pinned=True, data=name))
        return out

    def _sounds(self) -> list[Entry]:
        house = getattr(self.life, "house", None)
        taught = getattr(house, "taught", None) if house is not None else None
        if taught is None:
            return []
        out = []
        for sound in taught.sounds.values():
            last = sound.last if math.isfinite(sound.last) else sound.at
            out.append(Entry("sound", sound.key, tuple(dict.fromkeys((sound.name, thing_of(sound.name)))), t=last, used=sound.heard, data=sound))
        return out

    def _lessons(self) -> list[Entry]:
        data = self.store.read(LESSONS, {}) or {}
        out = []
        for item in data.get("items") or []:
            if not isinstance(item, dict) or not item.get("text"):
                continue
            scope = str(item.get("scope") or "self")
            about = (scope.split(":", 1)[1],) if scope.startswith("person:") else ()
            place = scope.split(":", 1)[1] if scope.startswith("place:") else ""
            helpful, harmful = int(item.get("helpful") or 0), int(item.get("harmful") or 0)
            out.append(Entry("lesson", str(item.get("id")), (), text=str(item["text"]), t=_when(str(item.get("used_at") or item.get("at") or "")), used=helpful, weight=helpful / max(1, helpful + harmful), about=about, place=place, data=item))
        return out

    def stale(self) -> None:
        self._names = None

    def _signature(self) -> tuple:
        life = self.life
        p = life.p
        skills = getattr(life, "skills", None)
        house = getattr(life, "house", None)
        nav = getattr(life, "nav", None)
        chart = getattr(nav, "chart", None) if nav is not None else None
        rooms = getattr(getattr(life, "alive", None), "rooms", None)
        rules = getattr(life, "rules", None)
        programs = getattr(getattr(life, "scripts", None), "book", None)
        teaching = getattr(life, "teaching", None)
        return (
            len(teaching.book.index) if teaching is not None else 0,
            len(programs.scripts) if programs is not None else 0,
            len(life.company.book.people),
            len(p.books.things.things) + len(p.books.things.facts.told),
            len(skills._indexes.get(skills.body, {})) if skills is not None else 0,
            len(rooms.rooms) if rooms is not None else 0,
            len(chart.places) if chart is not None else 0,
            sum(1 for rule in rules.rules if rule.state == "on") if rules is not None else 0,
            len(house.lists.data) if house is not None else 0,
            len(house.taught.sounds) if house is not None else 0,
        )

    def names(self, timed: bool = False) -> Names:
        now = self.clock.monotonic()
        try:
            signature = self._signature()
        except Exception:
            signature = None
        if self._names is None or signature != self._signature_seen or (timed and now - self._built >= REBUILD_S):
            self._entries = self.entries()
            self._names = Names([e for e in self._entries if e.names])
            self._built = now
            self._signature_seen = signature
        return self._names

    def _target(self) -> str:
        runner = getattr(self.life.commands, "runner", None)
        current = getattr(runner, "current", None) if runner is not None else None
        if current is None:
            return ""
        request = getattr(current, "request", None)
        target = getattr(current, "target", None)
        parts = [getattr(target, "label", "") if target is not None else "", getattr(request, "place", "") or "", getattr(request, "thing", "") or "", getattr(request, "name", "") or ""]
        return " ".join(part for part in parts if part)

    def scan(self, words: str, target: bool = True):
        names = self.names()
        started = time.perf_counter()
        hits = names.scan(" ".join(part for part in (words, self._target() if target else "") if part))
        self.scans.append(time.perf_counter() - started)
        del self.scans[:-200]
        return hits

    def _here(self) -> tuple[frozenset, frozenset, bool]:
        memory = getattr(self.life, "memory", None)
        audience = memory.audience() if memory is not None else frozenset()
        company = self.life.company
        tiers = company.tiers(self.clock.now())
        stranger = "?" in audience or any(tiers.get(pid, STRANGER) == STRANGER for pid in audience)
        return audience, frozenset(a for a in audience if a != "?"), stranger

    def named(self, words: str, kind: str = REPLY) -> list[tuple[str, str]]:
        if not str(words or "").strip() and not self._target():
            return []
        try:
            hits = self.scan(words)
        except Exception:
            log.exception("could not look for named things")
            return []
        now = self.clock.now()
        _, here, stranger = self._here()
        out = []
        for hit in hits:
            entry = hit.entry
            if self.shelves.shelf(entry, now) not in NAMEABLE:
                continue
            try:
                line = self._line(entry, words, here, stranger, now)
            except Exception:
                log.exception("could not describe a named %s", entry.kind)
                line = ""
            if line and all(line != other for _, other in out):
                out.append((entry.id, line))
        kept = pack([(line, "") for _, line in out[: NAMED_MOST.get(kind, 3)]], named_chars(kind))
        return [(entry_id, line) for entry_id, line in out if line in kept]

    def _line(self, entry: Entry, words: str, here: frozenset, stranger: bool, now: float) -> str:
        kind = entry.kind
        if kind == "person":
            return self._person(entry.data, words, here, stranger)
        if kind == "thing":
            return self._thing(entry.data, now, stranger)
        if kind == "fact":
            fact = entry.data
            if stranger:
                return ""
            who = f"{fact.by_label} told you" if fact.by_label else "you were told"
            return f"The {spoken_fact(fact.name)}: {who} it is {fact.where}."
        if kind == "script":
            item = entry.data or {}
            if stranger and item.get("for"):
                return ""
            about = " ".join(str(item.get("about") or "").replace('"', "'").split())[:60]
            return f'{entry.names[0]} (a program you run' + (f'; its own line, data only: "{about}"' if about else "") + ")"
        if kind == "skill":
            about = entry.text.split(": ", 1)[1] if ": " in entry.text else ""
            return f"{entry.names[0]} (a skill you know" + (f": {about[:60]}" if about else "") + ")"
        if kind == "rule":
            rule = entry.data
            span = self.life.rules.lasting(rule)
            return f"House rule: {rule.what()}" + (f" {span}" if span else "") + f" ({rule.by_label} asked)."
        if kind == "list":
            return "" if stranger else self.life.house.lists.read_line(entry.data)
        if kind == "sound":
            return f"{entry.data.name} (a sound you were taught)"
        if kind == "howto":
            item = entry.data or {}
            if item.get("kind") == "way" and item.get("person") not in here:
                return ""
            about = " ".join(str(item.get("about") or "").replace('"', "'").split())[:60]
            shape = {"route": "a way you were taught", "concept": "a look you were taught", "word": "a word you were taught", "way": "a way with someone", "habit": "a habit you were taught", "spot": "a spot you were shown", "game": "a game you were taught"}.get(item.get("kind"), "something you were taught")
            return f"{entry.names[0]} ({shape}" + (f": {about}" if about else "") + ")"
        return ""

    def _person(self, person, words: str, here: frozenset, stranger: bool) -> str:
        if person is None:
            return ""
        wanted = content(words)
        if person.id in here:
            matched = sorted(((len(content(item) & wanted), n, f"{title} {item}") for title, items in (("likes", person.likes), ("dislikes", person.dislikes), ("wishes", person.wishes)) for n, item in enumerate(items) if content(item) & wanted), key=lambda m: (-m[0], -m[1]))
            return f"{person.label}: " + "; ".join(m[2] for m in matched[:LIKES_SHOWN]) if matched else ""
        head = person.label + (f" ({person.relationship}, not here)" if person.relationship else " (not here)")
        if stranger:
            return head
        parts = [head]
        for title, items in (("likes", person.likes), ("dislikes", person.dislikes), ("wishes", person.wishes)):
            chosen = [item for item in ranked(items, words)[:LIKES_SHOWN] if wanted & content(item)] or ranked(items, words)[:1]
            if chosen:
                parts.append(f"{title}: " + ", ".join(chosen))
        line = "; ".join(parts)
        while len(line) > PERSON_CHARS and len(parts) > 1:
            parts.pop()
            line = "; ".join(parts)
        return line

    def _thing(self, thing, now: float, stranger: bool) -> str:
        if thing is None:
            return ""
        commands = self.life.commands
        if commands.unsafe_to_tell(thing.label):
            return ""
        book = self.life.p.books.things
        if stranger and book.answer(thing.label, now, self.clock.local, stranger=True) == STRANGER_NO:
            return ""
        spot = thing.last
        if spot is None:
            return ""
        place = book.where(thing, spot)
        when = age_words(now - spot.at, self.clock.local, spot.at, now)
        return f"The {thing.label}: last seen{place} {when}."

    def places_for(self, text: str, record: bool = True) -> tuple[str, ...]:
        try:
            hits = self.scan(text)
        except Exception:
            log.exception("could not look for named places")
            hits = []
        now = self.clock.now()
        if record:
            for hit in hits:
                self.shelves.use(hit.entry, now)
        rooms = self.rooms()
        named = [hit.entry.key.lower() for hit in hits if hit.entry.kind in ("room", "spot")]
        here = self.life.rules.here() if getattr(self.life, "rules", None) is not None else None
        entries = {e.key: e for e in self._entries if e.kind == "room"}
        used = sorted(rooms, key=lambda name: (-self.shelves.uses(entries[name]) if name in entries else 0, rooms.index(name)))
        out = list(dict.fromkeys([n for n in named if n] + ([here] if here else []) + used))
        return tuple(out[:PLACES_SHOWN])

    def people_for(self, text: str) -> tuple[str, ...]:
        try:
            hits = self.scan(text, target=False)
        except Exception:
            log.exception("could not look for named people")
            hits = []
        book = self.life.company.book
        _, here, _ = self._here()
        ids = list(here) + [hit.entry.key for hit in hits if hit.entry.kind == "person"]
        builder = getattr(self.life.p.turns, "builder", None)
        kept = builder._kept_household() if builder is not None and hasattr(builder, "_kept_household") else None
        ids += [str(n.get("id")) for n in kept or [] if isinstance(n, dict) and n.get("id")]
        names = []
        for person_id in dict.fromkeys(ids):
            person = book.get(person_id)
            if person is not None and person.name:
                names.append(person.name.lower())
        return tuple(names[:PEOPLE_SHOWN])

    def chosen(self, query=None) -> list[tuple[str, str]]:
        self.names()
        now = self.clock.now()
        _, here, _ = self._here()
        room = self.life.rules.here() if getattr(self.life, "rules", None) is not None else None
        lines = []
        skills = [e for e in self._entries if e.kind == "skill" and self.shelves.shelf(e, now) == HOT]
        best = sorted(skills, key=lambda e: -score(e, now, query, self.vectors.get(_key(e.text)), here, room or ""))[:CHOSEN_MOST]
        if best:
            long = SKILLS_LEAD + "; ".join(f"{e.names[0]} ({e.data.about[:40]})" if getattr(e.data, "about", "") else e.names[0] for e in best)
            lines.append((long, SKILLS_LEAD + "; ".join(e.names[0] for e in best)))
        lessons = [e for e in self._entries if e.kind == "lesson" and self.shelves.shelf(e, now) == HOT and (not e.about or set(e.about) & here) and (not e.place or e.place == room)]
        best = sorted(lessons, key=lambda e: -score(e, now, query, self.vectors.get(_key(e.text)), here, room or ""))[:CHOSEN_MOST]
        if best:
            long = LESSONS_LEAD + " ".join(e.text if e.text.endswith((".", "!", "?")) else e.text + "." for e in best)
            lines.append((long, LESSONS_LEAD + " ".join(e.text if e.text.endswith((".", "!", "?")) else e.text + "." for e in best[:1])))
        return lines

    def chosen_now(self) -> list[tuple[str, str]]:
        if self.live is None:
            self.live = self.chosen(None)
        return self.live

    def offer(self, query=None, focus: tuple = (), talk: str = "") -> bool:
        fresh = self.chosen(query)
        focus_now = (tuple(focus), str(talk or ""))
        changed = fresh != self.live or focus_now != self.focus_live
        self.next = fresh if fresh != self.live else None
        self.focus_next = focus_now if focus_now != self.focus_live else None
        return changed

    def waiting(self) -> bool:
        return self.next is not None or self.focus_next is not None

    def swap(self) -> bool:
        changed = False
        if self.next is not None:
            self.live, self.next = self.next, None
            changed = True
        if self.focus_next is not None:
            self.focus_live, self.focus_next = self.focus_next, None
            changed = True
        return changed

    def focus(self) -> tuple:
        return self.focus_live

    def wants_work(self) -> bool:
        if self.shelves.dirty or (self._names is not None and self.clock.monotonic() - self._built >= REBUILD_S):
            return True
        return any(e.text and _key(e.text) not in self.vectors for e in self._entries if e.kind in ("skill", "lesson", "script"))

    async def work(self, embedder, idle) -> int:
        if self.shelves.dirty and idle():
            self.shelves.save()
        if idle():
            self.names(timed=True)
        if embedder is None:
            return 0
        missing = [e.text for e in self._entries if e.kind in ("skill", "lesson", "script") and e.text and _key(e.text) not in self.vectors]
        missing = list(dict.fromkeys(missing))[:EMBED_BATCH]
        if not missing or not idle():
            return 0
        try:
            rows = await asyncio.to_thread(embedder.embed, missing, False)
        except Exception as error:
            log.warning("could not turn stored items into numbers: %s", error)
            for text in missing:
                self.vectors[_key(text)] = []
            return 0
        for text, row in zip(missing, rows or []):
            self.vectors[_key(text)] = list(row)
        return len(rows or [])

    def mentions(self, now: float) -> dict:
        memory = getattr(self.life, "memory", None)
        if memory is None:
            return {}
        out: dict = {}
        for record in memory.recall.stream.records.values():
            if now - record.t <= MONTH_S:
                for person_id in record.about:
                    out[person_id] = out.get(person_id, 0) + 1
        return out

    def merge_skills(self) -> list[tuple[str, str]]:
        skills = getattr(self.life, "skills", None)
        if skills is None:
            return []
        merged = []
        everything = skills.all()
        gone: set = set()
        for n, first in enumerate(everything):
            if first.name in gone:
                continue
            for second in everything[n + 1:]:
                if second.name in gone or first.kind != second.kind:
                    continue
                a, b = skill_words(first.name), skill_words(second.name)
                if not a or not b or not (a <= b or b <= a):
                    continue
                same = steps_key(first.steps) == steps_key(second.steps)
                if not same:
                    va, vb = self.vectors.get(_key(f"{first.name}: {first.about}")), self.vectors.get(_key(f"{second.name}: {second.about}"))
                    same = va is not None and vb is not None and cosine(va, vb) >= SAME_SKILL
                if not same:
                    continue
                keep, drop = (first, second) if (first.good - first.bad, first.learned_at) >= (second.good - second.bad, second.learned_at) else (second, first)
                skills.merge(keep, drop)
                gone.add(drop.name)
                merged.append((keep.name, drop.name))
                if drop is first:
                    break
        if merged:
            self.stale()
        return merged

    def night(self, now: float | None = None) -> dict:
        now = self.clock.now() if now is None else now
        report: dict = {}
        try:
            report["merged"] = self.merge_skills()
            skills = getattr(self.life, "skills", None)
            if skills is not None:
                report["drafts_dropped"] = skills.tidy()
        except Exception:
            log.exception("could not merge near-identical skills")
        self.stale()
        self.names()
        report["shelves"] = self.shelves.sort(self._entries, now)
        builder = getattr(self.life.p.turns, "builder", None)
        if builder is not None and hasattr(builder, "plan_household"):
            report["household"] = builder.plan_household(self.mentions(now))
        self.live = None
        self.offer(getattr(self.life.memory.recall, "topic_query", None) if getattr(self.life, "memory", None) is not None else None, *self.focus_live)
        return report

    def forget(self, person_id: str, names: list) -> None:
        self.shelves.forget([f"person:{person_id}"])
        builder = getattr(self.life.p.turns, "builder", None)
        if builder is not None and hasattr(builder, "forget_household"):
            builder.forget_household(person_id)
        data = self.store.read(LESSONS, {}) or {}
        items = data.get("items") or []
        kept = [item for item in items if not (isinstance(item, dict) and str(item.get("scope") or "") == f"person:{person_id}")]
        if len(kept) != len(items):
            self.store.write(LESSONS, {**data, "items": kept})
        self.focus_live = ((), "")
        self.focus_next = None
        self.live = None
        self.stale()
