import asyncio
import logging
import re
from collections import deque

from ..self.birth import record_of
from ..self.drives import pressing
from ..self.journal import Journal, said
from ..self.mine import Mine, MineRefused
from ..self.tidy import tidy
from ..self.recall.board import BOARD_LINE, DEEP_LINE, Note, block
from ..self.recall.core import SHARE_AFTER_S, Recall, may_share, remembering
from ..self.recall.stream import shown
from ..people.trust import STRANGER
from ..self.registry import PEBBLE, PEOPLE
from ..self.words import SelfWords

log = logging.getLogger(__name__)

SPEAKER_S = 120.0
TOPIC_S = 300.0
LOOK_BACK_S = 14 * 86400.0
POOL_MOST = 12
CHANGED = re.compile(r"\bwhat (?:have you|did you|has) changed\b|\bhave you changed (?:lately|recently|at all)\b|\bwhat'?s (?:new|different) (?:about|with) you\b|\bhow have you been changing\b", re.IGNORECASE)
SINCE_BORN = re.compile(r"\bsince you were born\b|\bhow have you changed since\b|\bhow are you different from (?:other|the other) pebbles\b|\bwhat makes you different\b", re.IGNORECASE)


def unnamed(record) -> str:
    text = shown(record)
    head, quote, rest = text.partition(' said: "')
    return f'Someone said: "{rest}' if quote else text


class Memory:
    def __init__(self, life):
        p = life.p
        self.life = life
        self.journal = Journal(p.store, p.clock)
        self.recall = Recall(p.store, p.clock, getattr(p, "embedder", None), life.dials.recall_weights, p.books.name)
        self.mine = Mine(p.store, p.clock, life._record, self.names)
        self.notes = p.history.notes
        self.notes.record = life._record
        self.words = SelfWords(p.store, life.dials, self.names, p.books.name)
        p.history.mover = self.recall.from_turns
        if hasattr(p.turns, "audience"):
            p.turns.audience = lambda: sorted(self.audience() - {"?"})
        builder = getattr(p.turns, "builder", None)
        if builder is not None:
            builder.words = self.words.text
        p.books.values.record = life._record
        p.diary.on_write = self.diary_kept
        p.books.memory.on_remember = self.fact_kept
        life.overnight.record = life._record
        life.overnight.forgetters.append(self.forget)
        life.overnight.unremember.append(self.recall.stream.unremember)
        life.overnight.matching.append(self.recall.stream.matching)
        life.nightly.memory = self.night
        self.speaker: tuple | None = None
        self.said: deque = deque(maxlen=3)
        self.consents: list[tuple[str, float]] = []
        self._scene: tuple | None = None
        self._task: asyncio.Task | None = None
        self._refresh: asyncio.Task | None = None
        self._migrate()

    def _migrate(self) -> None:
        stream = self.recall.stream
        if len(stream) or not self.life.p.books.memory.facts:
            return
        for fact in self.life.p.books.memory.facts:
            stream.add(str(fact.get("text") or ""), "fact", mark="private", pinned=bool(fact.get("pinned")), weight=5)
        try:
            stream.save()
        except OSError as error:
            log.warning("could not keep the old facts in the memory stream: %s", error)

    def names(self) -> list[str]:
        book = self.life.company.book
        out = []
        for person in book.people.values():
            out.extend(str(n) for n in list(person.names) + list(person.nicknames) if n)
        return out

    def named(self, text: str) -> tuple:
        lowered = str(text or "").lower()
        found = []
        for person in self.life.company.book.people.values():
            for name in list(person.names) + list(person.nicknames):
                if name and len(name) > 1 and re.search(rf"\b{re.escape(str(name).lower())}\b", lowered):
                    found.append(person.id)
                    break
        return tuple(found)

    def audience(self, now: float | None = None) -> frozenset:
        company = self.life.company
        now = self.life.p.clock.now() if now is None else now
        here = set(company.presence.here(now))
        if company.someone_new(now):
            here.add("?")
        return frozenset(here)

    def heard(self, person_id: str | None, label: str, tier: str | None, text: str = "") -> None:
        now = self.life.p.clock.now()
        self.speaker = (person_id, label if person_id is not None else "Someone", tier if person_id is not None else "stranger", now)
        if text.strip():
            self.said.append((now, " ".join(text.split())[:200]))
        if person_id is not None and may_share(text):
            self.consents.append((person_id, now))
            self.life.p.blackbox.record("memory_shared", person=person_id)
            self._mark_consents(now)

    def _mark_consents(self, now: float) -> None:
        history = self.life.p.history
        marked = 0
        for person_id, at in self.consents:
            marked += self.recall.share(person_id, at, history.turns)
        if marked:
            history.save()
        self.consents = [(person_id, at) for person_id, at in self.consents if now - at <= SHARE_AFTER_S]

    def _speaker(self) -> tuple | None:
        if self.speaker is None or self.life.p.clock.now() - self.speaker[3] > SPEAKER_S:
            return None
        return self.speaker[:3]

    def diary_kept(self, entry: dict) -> None:
        if entry.get("setup"):
            return
        text = str(entry.get("text") or "")
        self.recall.from_diary(entry, tuple(sorted(self.audience() - {"?"})), self.named(text))

    def fact_kept(self, fact: dict, new: bool) -> None:
        if not new:
            return
        text = str(fact.get("text") or "")
        about = self.named(" ".join([text, str(fact.get("about") or "")]))
        self.recall.from_fact(text, tuple(sorted(self.audience() - {"?"})), about, self._speaker())

    def stranger(self, now: float):
        company = self.life.company
        book = company.book
        tiers = company.tiers(now)

        def names(person_id: str) -> list[str] | None:
            person = book.get(person_id)
            if person is None:
                return []
            if person.is_owner or tiers.get(person_id, STRANGER) != STRANGER:
                return None
            return [str(n) for n in list(person.names) + list(person.nicknames) if n]

        return names

    def forget(self, person_id: str, names: list[str]) -> None:
        self.recall.stream.forget(person_id, names)
        self.notes.forget(person_id, names)
        self.mine.forget(person_id, names)

    def idle(self) -> bool:
        life = self.life
        if getattr(life, "_in_turn", False):
            return False
        hold = getattr(life.p.conversation, "hold_turns", None)
        return hold is None or hold() is None

    def tick(self, now: float) -> None:
        if self.consents:
            self._mark_consents(now)
        if not self.idle():
            return
        if self._task is None or self._task.done():
            selection = getattr(self.life, "selection", None)
            if self.recall.busy() or (selection is not None and selection.wants_work()):
                self._task = asyncio.ensure_future(self._quietly(self._work()))
        scene = self.scene(now)
        if scene != self._scene and (self._refresh is None or self._refresh.done()):
            self._scene = scene
            self._refresh = asyncio.ensure_future(self._quietly(self.refresh(now)))
        if self.life.p.conversation is None:
            self.swap_ahead()

    async def _work(self) -> int:
        done = await self.recall.work(self.idle)
        selection = getattr(self.life, "selection", None)
        if selection is not None and self.idle():
            done += await selection.work(self.recall.embedder, self.idle)
        return done

    async def _quietly(self, job):
        try:
            return await job
        except Exception:
            log.exception("memory work failed")
            self.life.p.blackbox.record("error", where="memory")
            return None

    def scene(self, now: float) -> tuple:
        runner = getattr(self.life.commands, "runner", None)
        current = getattr(runner, "current", None)
        doing = getattr(current, "name", "") if current is not None else ""
        topic = " ".join(sorted(set(re.findall(r"[a-z]{4,}", self.topic().lower()))))
        return (self.audience(now), doing, topic)

    def topic(self) -> str:
        now = self.life.p.clock.now()
        return " ".join(text for at, text in self.said if now - at <= TOPIC_S)

    def extras(self, now: float) -> list[Note]:
        life = self.life
        out = [Note(f"You feel: {d.why}", "drive") for d in pressing(getattr(life, "drives", ()))[:1]]
        wonderings = self.mine.open_wonderings()
        if wonderings:
            out.append(Note(f"You wonder: {wonderings[-1]['text']}", "wondering"))
        projects = sorted(self.mine.files("projects/"), key=lambda f: f.get("at") or "")
        if projects:
            title = projects[-1]["name"].split("/", 1)[1].rsplit(".", 1)[0].replace("-", " ")
            out.append(Note(f"One of your projects: {title}", "wondering"))
        reasons = life.wonder.reasons(now, life.dials.pulls())
        if reasons:
            out.append(Note(f"Just now: {reasons[0]}", "surprise"))
        return out

    async def refresh(self, now: float | None = None) -> bool:
        now = self.life.p.clock.now() if now is None else now
        audience = self.audience(now)
        here = tuple(sorted(audience - {"?"}))
        topic = self.topic()
        changed = await self.recall.refresh(audience, here, topic, self.extras(now), self.life.dials.board_weights(), now)
        selection = getattr(self.life, "selection", None)
        if selection is not None:
            speaker = self._speaker()
            focus = tuple(dict.fromkeys(([speaker[0]] if speaker and speaker[0] else []) + list(self.named(topic))))
            changed = selection.offer(self.recall.topic_query, focus, topic) or changed
        return changed

    def ahead_mark(self) -> tuple:
        board = self.recall.board
        selection = getattr(self.life, "selection", None)
        builder = getattr(self.life.p.turns, "builder", None)
        waiting = (selection is not None and selection.waiting()) or bool(getattr(builder, "household_next", None))
        return (board.offers, board.waiting(), self.notes.waiting(), self.words.waiting(), waiting)

    def swap_ahead(self) -> bool:
        changed = self.recall.board.swap()
        changed = self.notes.swap() or changed
        changed = self.words.swap() or changed
        selection = getattr(self.life, "selection", None)
        if selection is not None:
            changed = selection.swap() or changed
        builder = getattr(self.life.p.turns, "builder", None)
        if builder is not None and hasattr(builder, "swap_household"):
            changed = builder.swap_household() or changed
        return changed

    def board_text(self, audience: frozenset | None = None) -> str:
        now = self.life.p.clock.now()
        audience = self.audience(now) if audience is None else audience
        return self.recall.board.text(audience, now)

    async def think_back(self, text: str, audience: frozenset | None = None) -> list[str]:
        audience = self.audience() if audience is None else audience
        return await self.recall.think_back(text, audience, tuple(sorted(audience - {"?"})))

    async def for_turn(self, text: str) -> str:
        audience = self.audience()
        notes = await self.recall.for_turn(text, audience, tuple(sorted(audience - {"?"})))
        return block([Note(n) for n in notes], BOARD_LINE)

    async def remember_about(self, text: str) -> list[str]:
        audience = self.audience()
        return await self.recall.search(text, audience, tuple(sorted(audience - {"?"})))

    def answers(self, text: str) -> bool:
        return bool(SINCE_BORN.search(text or "") or CHANGED.search(text or ""))

    def about_change(self, text: str) -> str:
        if SINCE_BORN.search(text or ""):
            return self.since_birth()
        if CHANGED.search(text or ""):
            return self.journal.lately()
        return ""

    def since_birth(self) -> str:
        p = self.life.p
        traits = (p.store.read("personality.json", {}) or {}).get("traits") or {}
        return self.journal.since_birth(record_of(p.store), traits, p.books.values.scores(), self.words.current())

    def deep_turn(self, reasons: list[str], strongest: str | None) -> None:
        if not reasons or strongest not in ("surprise", "stuck", "invalid"):
            return
        try:
            self.mine.wonder(f"{reasons[0]}: why?", "it made me stop and think hard")
        except MineRefused:
            pass

    def pool(self, now: float) -> list[dict]:
        out = []
        for n, entry in enumerate(self.journal.entries(now - LOOK_BACK_S)):
            if entry.get("kind") in ("trait", "value") and entry.get("by") in (PEBBLE, PEOPLE):
                line = said(entry)
                if line:
                    out.append({"id": f"j{n}", "t": float(entry.get("t") or 0.0), "by": "self", "text": line})
        records = [r for r in self.recall.stream.records.values() if now - r.t <= LOOK_BACK_S and (r.mark == "" or (r.shared and r.kind == "said")) and r.kind in ("said", "happened", "feeling") and r.importance >= 4]
        for record in sorted(records, key=lambda r: -r.t)[:POOL_MOST]:
            out.append({"id": record.id, "t": record.t, "by": record.by, "tier": record.tier, "text": unnamed(record) if record.shared else shown(record)})
        return out[-POOL_MOST * 2 :]

    async def night(self, mind) -> dict:
        p = self.life.p
        now = p.clock.now()
        stream = self.recall.stream
        report = {"faded": stream.fade(now, self.stranger(now))}
        await self.recall.work(lambda: True, save=True)
        report["merged"] = stream.dedupe()
        report["shelves"] = stream.shelve(now)
        labels = {person.id: person.label for person in self.life.company.book.people.values() if person.names}
        selection = getattr(self.life, "selection", None)
        rooms = selection.rooms() if selection is not None else self.life._places()
        report["folded"] = len(stream.fold(now, labels, rooms))
        stream.save()
        await self.recall.work(lambda: True, save=True)
        if not self.life.setup.on:
            report["notes"] = await tidy(self.notes, stream, self.recall.embedder, mind, self.known_names)
            report["words"] = await self.words.reflect(mind, self.pool(now))
        if selection is not None:
            report["items"] = selection.night(now)
        stream.save()
        return report

    def known_names(self) -> list[str]:
        names = self.names()
        selection = getattr(self.life, "selection", None)
        names.extend(selection.rooms() if selection is not None else self.life._places())
        things = self.life.p.books.things
        names.extend(things.things)
        names.extend(things.facts.told)
        skills = getattr(self.life, "skills", None)
        if skills is not None:
            names.extend(skills.names())
        names.append(self.life.p.books.name)
        return names

    def save(self) -> None:
        try:
            self.recall.stream.save()
        except OSError as error:
            log.warning("could not save the memory stream: %s", error)

    def deep_line(self, notes: list[str]) -> str:
        return block([Note(n) for n in notes], DEEP_LINE)

    def remembering(self, text: str) -> bool:
        return remembering(text)
