from dataclasses import dataclass, field

from .prints import PER_KIND, Matcher, normalise

SEEN_CAP = 200


@dataclass
class Sighting:
    id: str
    first_seen: float
    last_seen: float
    visits: int = 1
    days: int = 1
    last_day: str | None = None
    prints: list = field(default_factory=list)

    def add_print(self, vector, at: float) -> bool:
        clean_vector = normalise(vector)
        if clean_vector is None:
            return False
        self.prints.append({"vector": list(clean_vector), "at": at})
        del self.prints[:-PER_KIND]
        return True

    def vectors(self) -> list[tuple[float, ...]]:
        return [tuple(p["vector"]) for p in self.prints if isinstance(p, dict) and p.get("vector")]

    def to_dict(self) -> dict:
        return {"id": self.id, "first_seen": self.first_seen, "last_seen": self.last_seen, "visits": self.visits, "days": self.days, "last_day": self.last_day, "prints": self.prints}

    @classmethod
    def from_dict(cls, data: dict) -> "Sighting | None":
        try:
            sighting = cls(str(data["id"]), float(data["first_seen"]), float(data.get("last_seen", data["first_seen"])), int(data.get("visits", 1) or 1), int(data.get("days", 1) or 1), data.get("last_day"))
            for raw in data.get("prints") or []:
                if isinstance(raw, dict):
                    sighting.add_print(raw.get("vector"), float(raw.get("at", sighting.last_seen)))
        except (KeyError, TypeError, ValueError):
            return None
        return sighting if sighting.vectors() else None


class Sightings:
    def __init__(self, items: list | None = None, next_id: int = 1):
        self.next_id = max(1, int(next_id or 1))
        self.items: dict[str, Sighting] = {}
        for raw in items or []:
            sighting = Sighting.from_dict(raw) if isinstance(raw, dict) else None
            if sighting is None:
                continue
            self.items[sighting.id] = sighting
            if sighting.id[1:].isdigit():
                self.next_id = max(self.next_id, int(sighting.id[1:]) + 1)

    def best(self, vector: tuple[float, ...], matcher: Matcher) -> Sighting | None:
        found = matcher.best(vector, {sid: s.vectors() for sid, s in self.items.items() if s.vectors()})
        return self.items.get(found.person_id) if found is not None else None

    def add(self, vector, at: float, day: str) -> Sighting | None:
        sighting = Sighting(f"s{self.next_id}", at, at, last_day=day)
        if not sighting.add_print(vector, at):
            return None
        self.next_id += 1
        self.items[sighting.id] = sighting
        if len(self.items) > SEEN_CAP:
            for old in sorted(self.items.values(), key=lambda s: s.last_seen)[: len(self.items) - SEEN_CAP]:
                del self.items[old.id]
        return sighting

    def refresh(self, sighting: Sighting, vector, at: float, day: str, new_visit_s: float) -> None:
        if at - sighting.last_seen >= new_visit_s:
            sighting.visits += 1
            sighting.add_print(vector, at)
        if sighting.last_day != day:
            sighting.days += 1
            sighting.last_day = day
        sighting.last_seen = max(sighting.last_seen, at)

    def take(self, vector: tuple[float, ...], matcher: Matcher) -> Sighting | None:
        found = self.best(vector, matcher)
        if found is not None:
            del self.items[found.id]
        return found

    def drop_like(self, vectors, matcher: Matcher) -> list[str]:
        gone = []
        for vector in vectors:
            while (found := self.take(vector, matcher)) is not None:
                gone.append(found.id)
        return gone

    def expire(self, now: float, after_s: float) -> list[str]:
        gone = [s.id for s in self.items.values() if now - s.last_seen >= after_s]
        for sid in gone:
            del self.items[sid]
        return gone

    def to_list(self) -> list:
        return [s.to_dict() for s in sorted(self.items.values(), key=lambda s: s.first_seen)]
