import math

KEEP_S = 24 * 3600.0
AWAY_S = 1800.0
SETTLE_S = 20.0
ASK_BACK_S = 6 * 3600.0
PERSONAL_S = 3 * 3600.0
GROUPS_SAID = 4
CAP = 200
HOUSE_KINDS = frozenset({"knock", "doorbell", "microwave", "phone", "kettle", "alarm_clock", "rain", "thunder", "meowing", "dog_crying", "sound", "power", "chirp", "alarm", "door", "bowl", "water_bowl", "told", "child_home"})


class AwayLog:
    def __init__(self, house, entries: list):
        self.house = house
        self.entries = entries
        self.seen_at: dict[str, float] = {}
        self.pending: dict[str, tuple[float, float]] = {}
        self.last_gone: dict[str, tuple[float, float]] = {}
        self.away_s = AWAY_S

    def add(self, kind: str, text: str, at: float, person: str | None = None, for_people: tuple = ()) -> None:
        entry = {"at": round(at, 1), "kind": kind, "text": " ".join(str(text).split())[:120]}
        if person:
            entry["person"] = person
        if for_people:
            entry["for"] = list(for_people)
        self.entries.append(entry)
        del self.entries[:-CAP]
        self.house.book.touch()

    def prune(self, now: float) -> None:
        kept = [e for e in self.entries if now - float(e.get("at", 0.0)) <= KEEP_S]
        if len(kept) != len(self.entries):
            self.entries[:] = kept
            self.house.book.touch()

    def forget_person(self, person_id: str) -> bool:
        kept = [e for e in self.entries if e.get("person") != person_id and person_id not in (e.get("for") or [])]
        changed = len(kept) != len(self.entries)
        self.entries[:] = kept
        self.seen_at.pop(person_id, None)
        self.pending.pop(person_id, None)
        self.last_gone.pop(person_id, None)
        return changed

    def tick(self, now: float, mono: float, quiet: bool) -> None:
        house = self.house
        for person in house.household_here(now):
            before = self.seen_at.get(person.id)
            if before is not None and now - before >= self.away_s:
                self.pending[person.id] = (mono, before)
                self.last_gone[person.id] = (before, now)
                if person.is_child and house.book.settings.get("children_arrivals"):
                    guardians = house.guardians()
                    if guardians:
                        self.add("child_home", f"{person.label} got home", now, for_people=tuple(guardians))
            self.seen_at[person.id] = now
        for person_id, (arrived, gone_since) in list(self.pending.items()):
            if mono - arrived < SETTLE_S:
                continue
            if quiet or house.busy():
                if mono - arrived > 600.0:
                    self.pending.pop(person_id, None)
                continue
            self.pending.pop(person_id, None)
            person = house.person(person_id)
            if person is None or person_id not in {p.id for p in house.household_here(now)}:
                continue
            line = self.summary(person_id, gone_since, now)
            if line:
                house.say(f"Since I last saw you: {line}", to=person.label, why="while you were out")
                house.note(f"you told {person.label} what happened in the house since you last saw them", False)
                self._told(person_id, now)
        if not quiet and not house.busy():
            self._personal(now)

    def _told(self, person_id: str, now: float) -> None:
        for entry in self.entries:
            if entry.get("person") == person_id and float(entry.get("at", 0.0)) <= now:
                entry["told"] = True
        self.house.book.touch()

    def _personal(self, now: float) -> None:
        house = self.house
        for person in house.household_here(now):
            if person.id in self.pending:
                continue
            waiting = [e for e in self.entries if e.get("person") == person.id and not e.get("told") and now - float(e.get("at", 0.0)) <= PERSONAL_S]
            if not waiting:
                continue
            parts = [self._said(e["text"], [float(e["at"])]) for e in waiting[-GROUPS_SAID:]]
            house.say("Earlier, " + (parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]) + ".", to=person.label, why="told when back")
            self._told(person.id, now)

    def summary(self, person_id: str, since: float, now: float) -> str:
        groups: dict[str, list[float]] = {}
        for entry in self.entries:
            at = float(entry.get("at", 0.0))
            if not since < at <= now or entry.get("kind") not in HOUSE_KINDS:
                continue
            if entry.get("person") not in (None, person_id):
                continue
            if entry.get("for") and person_id not in entry["for"]:
                continue
            groups.setdefault(entry["text"], []).append(at)
        if not groups:
            return ""
        ordered = sorted(groups.items(), key=lambda item: item[1][0])
        parts = [self._said(text, times) for text, times in ordered[:GROUPS_SAID]]
        extra = len(ordered) - GROUPS_SAID
        if extra > 0:
            parts.append("and a few other things")
        if len(parts) == 1:
            return parts[0] + "."
        if extra > 0:
            return ", ".join(parts[:-1]) + ", " + parts[-1] + "."
        return ", ".join(parts[:-1]) + " and " + parts[-1] + "."

    def _said(self, text: str, times: list[float]) -> str:
        stamps = [self.house.hhmm(t) for t in times]
        if " from " in text or " for about " in text:
            return text
        if len(stamps) == 1:
            return f"{text} at {stamps[0]}"
        if len(stamps) == 2:
            return f"{text} at {stamps[0]} and again at {stamps[1]}"
        return f"{text} {len(stamps)} times, the last at {stamps[-1]}"

    def asked(self, person_id: str | None, now: float) -> str:
        since = now - ASK_BACK_S
        if person_id is not None and person_id in self.last_gone:
            gone, back = self.last_gone[person_id]
            if now - back <= 12 * 3600.0:
                since = gone
        line = self.summary(person_id or "", since, now)
        if line:
            return f"Since I last saw you: {line}"
        return "Nothing that I noticed. I only know what I could hear or see from where I was."

    def seen_before(self, person_id: str) -> float:
        return self.seen_at.get(person_id, -math.inf)
