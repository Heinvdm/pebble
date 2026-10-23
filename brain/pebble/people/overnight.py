import re
from datetime import date
from typing import Callable

from ..books import Books
from ..clock import Clock
from ..diary import Diary
from ..self.registry import PEOPLE
from ..selfstore import SelfStore
from ..values import NudgeRefused
from .changes import Change
from .forget import FORGET_MOST, forget_person, forget_phrase
from .presence import Presence
from .requests import forget_refusal
from .trust import STRANGER, tiers
from .weigh import refusal

PERSONALITY = "personality.json"
JOKES = "jokes.json"
SUGGESTIONS_PER_NIGHT = 3
FAVOURITE_KEYS = {"song": "favourite_song", "spot": "favourite_spot"}


class Overnight:
    def __init__(self, books: Books, store: SelfStore, diary: Diary, clock: Clock, presence: Presence | None = None, remove_drawing: Callable[[str], bool] | None = None):
        self.books = books
        self.store = store
        self.diary = diary
        self.clock = clock
        self.presence = presence
        self.remove_drawing = remove_drawing
        self.forgetters: list[Callable[[str, list[str]], None]] = []
        self.unremember: list[Callable[[str], int]] = []
        self.matching: list[Callable[[str], int]] = []
        self.record = lambda kind, **data: None

    def run(self, night: date, stage: str, at: str) -> dict:
        now = self.clock.now()
        changes = self.books.changes
        report: dict = {"applied": [], "refused": [], "waiting": [], "expired": []}
        for change in changes.expire(now):
            report["expired"].append(change.id)
            self._write(change, f"No one else close to me asked to {change.summary()} as well, so I let {change.asked_by_label}'s request go.")
        suggestions = 0
        for change in sorted(changes.queued(), key=lambda c: c.asked_at):
            if change.status != "queued":
                continue
            asker = self.books.people.get(change.asked_by)
            if asker is None:
                changes.close(change, "dropped", "the person who asked is no longer known", now)
                continue
            if change.kind in ("favourite", "preference", "joke"):
                if suggestions >= SUGGESTIONS_PER_NIGHT:
                    report["waiting"].append(change.id)
                    continue
                suggestions += 1
            outcome = self._decide(change, night, stage, at)
            if outcome is None:
                report["waiting"].append(change.id)
                continue
            status, note = outcome
            changes.close(change, status, note, now)
            report["applied" if status == "applied" else "refused"].append(change.id)
            self._record(change, status, note)
        strangers = {pid for pid, tier in tiers(self.books.people, now).items() if tier == STRANGER}
        report["prints_expired"] = self.books.people.expire_prints(now, strangers)
        report["evidence_pruned"] = self.books.people.prune(now)
        self.books.save("people", "changes", "values", "memory", "calendar")
        return report

    def _write(self, change: Change, text: str) -> None:
        entry = self.diary.write(text, "change")
        asker = self.books.people.get(change.asked_by)
        if asker is not None and change.kind != "forget_person":
            asker.link_diary(entry["at"])

    def _record(self, change: Change, status: str, note: str) -> None:
        who = change.asked_by_label
        if change.kind == "forget_person":
            text = "Overnight I forgot someone, as I was asked to." if status == "applied" else f"I thought about a request to forget someone and said no: {note}."
            self.diary.write(text, "change")
            return
        why = f" ({change.why})" if change.why else ""
        if status == "applied":
            seconded = self.books.people.get(change.seconded_by) if change.seconded_by else None
            also = f" and {seconded.label}" if seconded is not None else ""
            self._write(change, f"Overnight I decided to {change.summary()}, because {who}{also} asked{why}. {note}".strip())
        else:
            self._write(change, f"I thought about {who}'s request to {change.summary()} and said no: {note}.")

    def _decide(self, change: Change, night: date, stage: str, at: str) -> tuple[str, str] | None:
        if change.kind not in ("forget_person",) and not change.kind.startswith("delete_"):
            problem = refusal(change.kind, change.target, change.amount, change.text, self.books.values, self.store.read(PERSONALITY, {}))
            if problem:
                return "refused", problem
        handler = getattr(self, f"_{change.kind}")
        return handler(change, night, stage, at)

    def _personality(self, change: Change, night: date, stage: str, at: str) -> tuple[str, str] | None:
        if self.books.changes.last_personality_night == night.isoformat():
            return None
        personality = self.store.read(PERSONALITY, {})
        traits = personality.setdefault("traits", {})
        before = int(traits[change.target])
        traits[change.target] = before + change.amount
        personality.setdefault("history", []).append({"at": at, "trait": change.target, "from": before, "to": traits[change.target], "asked_by": change.asked_by_label, "why": change.why})
        del personality["history"][:-100]
        self.store.write(PERSONALITY, personality)
        self.books.changes.last_personality_night = night.isoformat()
        self.record("trait_changed", trait=change.target, before=before, after=traits[change.target], who=PEOPLE, why=change.why or "")
        return "applied", f"My {change.target} went from {before} to {traits[change.target]}."

    def _value(self, change: Change, night: date, stage: str, at: str) -> tuple[str, str] | None:
        values = self.books.values
        try:
            record = values.step(change.target, change.amount > 0, f"{change.asked_by_label} asked: {change.why}", at, self.clock.now(), PEOPLE)
        except NudgeRefused as error:
            return "refused", str(error)
        return "applied", f"My {record['raise']} grew a little and my {record['lower']} eased off."

    def _favourite(self, change: Change, night: date, stage: str, at: str) -> tuple[str, str]:
        prefs = self.books.preferences
        prefs.setdefault("favourites", {})[change.target.lower()] = change.text
        key = FAVOURITE_KEYS.get(change.target.lower())
        if key:
            prefs[key] = change.text
        self.books.save_preferences()
        return "applied", ""

    def _preference(self, change: Change, night: date, stage: str, at: str) -> tuple[str, str]:
        prefs = self.books.preferences
        if change.target == "disliked_noise":
            noises = prefs.setdefault("disliked_noises", [])
            if change.text.lower() not in (n.lower() for n in noises):
                noises.append(change.text)
        elif change.target == "initiative_minutes":
            prefs["initiative_minutes"] = float(change.text)
        else:
            voice = prefs.setdefault("voice", {})
            voice["speed" if change.target == "voice_speed" else "pitch_shift"] = float(change.text)
        self.books.save_preferences()
        return "applied", ""

    def _joke(self, change: Change, night: date, stage: str, at: str) -> tuple[str, str]:
        jokes = self.store.read(JOKES, {}) or {}
        curated = jokes.setdefault("curated", [])
        if any(str(j.get("text", "")).lower() == change.text.lower() for j in curated):
            return "applied", "I already knew that one."
        slug = re.sub(r"[^a-z0-9]+", "-", change.text.lower()).strip("-")[:24] or f"taught-{change.id}"
        curated.append({"id": f"taught-{change.id}-{slug}", "text": change.text, "style": "taught", "taught_by": change.asked_by_label, "uses": 0, "landed": 0, "flopped": 0, "retired": False})
        self.store.write(JOKES, jokes)
        return "applied", ""

    def _trust(self, change: Change, night: date, stage: str, at: str) -> tuple[str, str]:
        person = self.books.people.get(change.target)
        if person is None:
            return "refused", "I no longer know who that was"
        person.override = change.text
        return "applied", ""

    def _forget_person(self, change: Change, night: date, stage: str, at: str) -> tuple[str, str]:
        now = self.clock.now()
        table = tiers(self.books.people, now)
        asker = self.books.people.get(change.asked_by)
        target = self.books.people.get(change.target)
        problem = forget_refusal(asker, table.get(asker.id, STRANGER), target, table.get(target.id, STRANGER) if target else STRANGER)
        if problem:
            return "refused", problem
        self.books.changes.close(change, "applied", "", now)
        forget_person(self.books, self.store, target, self.presence, now, self.forgetters)
        return "applied", ""

    def _delete_memory(self, change: Change, night: date, stage: str, at: str) -> tuple[str, str]:
        wanted = change.text or change.target
        pattern = forget_phrase(wanted)
        if pattern is None:
            return "refused", "that was too short to tell which memory they meant"
        facts = [f for f in self.books.memory.facts if not f.get("pinned") and pattern.search(str(f.get("text") or "").lower())]
        if len(facts) + sum(count(wanted) for count in self.matching) > FORGET_MOST:
            return "refused", f"that would match more than {FORGET_MOST} memories, so I need more of the words to know which one"
        self.books.memory.facts = [f for f in self.books.memory.facts if f not in facts]
        removed = len(facts)
        for forget in self.unremember:
            removed += forget(wanted)
        if not removed:
            return "refused", "I could not find that memory"
        self.store.write("memory.json", self.books.memory.to_dict(), keep_backup=False)
        return "applied", f"I let go of {removed} memor{'y' if removed == 1 else 'ies'}."

    def _delete_drawing(self, change: Change, night: date, stage: str, at: str) -> tuple[str, str]:
        name = change.target or change.text
        if self.remove_drawing is None or not self.remove_drawing(name):
            return "refused", f"I have no drawing called {name}"
        return "applied", ""

    def _delete_photo(self, change: Change, night: date, stage: str, at: str) -> tuple[str, str]:
        return "applied", "I keep no photos, so there was nothing to delete."
