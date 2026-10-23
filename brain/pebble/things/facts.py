from dataclasses import dataclass

from .words import canonical, matches

FACT_CAP = 40
WHERE_MAX = 60
YEAR_S = 365 * 86400.0
SAME = {
    "water shut off valve": "water shut off",
    "water main": "water shut off",
    "water mains": "water shut off",
    "mains water tap": "water shut off",
    "mains tap": "water shut off",
    "water toby": "water shut off",
    "toby": "water shut off",
    "stopcock": "water shut off",
    "water shutoff": "water shut off",
    "switch board": "switchboard",
    "fuse box": "switchboard",
    "fuses": "switchboard",
    "circuit breakers": "switchboard",
    "gas valve": "gas shut off",
    "gas bottle valve": "gas shut off",
    "grab bag": "getaway bag",
    "go bag": "getaway bag",
    "emergency bag": "getaway bag",
    "civil defence kit": "emergency kit",
    "survival kit": "emergency kit",
    "extinguisher": "fire extinguisher",
    "first aid box": "first aid kit",
    "torches": "torch",
}
SPOKEN = {"water shut off": "water shut-off", "gas shut off": "gas shut-off"}
EMERGENCY = frozenset({"water shut off", "switchboard", "meter box", "gas shut off", "getaway bag", "emergency kit", "fire extinguisher", "fire blanket", "first aid kit", "torch", "spare batteries", "emergency water", "emergency radio"})
FACT_PHRASES = frozenset(SAME) | EMERGENCY


def fact_name(text: str) -> str:
    words = " ".join(str(text or "").lower().replace("-", " ").split())
    words = SAME.get(words, words)
    return SAME.get(canonical(words), words)


def spoken_fact(name: str) -> str:
    return SPOKEN.get(name, name)


@dataclass
class Told:
    name: str
    where: str
    by: str | None
    by_label: str
    at: float
    checked: float

    def to_dict(self) -> dict:
        return {"name": self.name, "where": self.where, "by": self.by, "by_label": self.by_label, "at": self.at, "checked": self.checked}

    @classmethod
    def from_dict(cls, data: dict) -> "Told | None":
        try:
            return cls(str(data["name"]), str(data["where"])[:WHERE_MAX], data.get("by"), str(data.get("by_label", "")), float(data["at"]), float(data.get("checked", data["at"])))
        except (KeyError, TypeError, ValueError):
            return None


class Facts:
    def __init__(self, data: list | None = None):
        self.told: dict[str, Told] = {}
        for raw in data or []:
            fact = Told.from_dict(raw) if isinstance(raw, dict) else None
            if fact is not None:
                self.told[fact.name] = fact

    def tell(self, name: str, where: str, by: str | None, by_label: str, at: float) -> Told:
        key = fact_name(name)
        where = " ".join(str(where).split())[:WHERE_MAX]
        fact = Told(key, where, by, by_label, at, at)
        self.told[key] = fact
        if len(self.told) > FACT_CAP:
            oldest = min(self.told.values(), key=lambda f: f.checked)
            self.told.pop(oldest.name, None)
        return fact

    def find(self, wanted: str) -> Told | None:
        key = fact_name(wanted)
        if key in self.told:
            return self.told[key]
        hits = [f for f in self.told.values() if matches(key, f.name) or matches(f.name, key)]
        return hits[0] if len(hits) == 1 else None

    def answer(self, wanted: str, now: float) -> str:
        fact = self.find(wanted)
        if fact is None:
            return ""
        who = f"{fact.by_label} told me" if fact.by_label else "I was told"
        line = f"{who} the {spoken_fact(fact.name)} is {fact.where}."
        if now - fact.checked > YEAR_S:
            line = line[:-1] + ", but that was over a year ago, so it may have moved."
        return line

    def due(self, now: float) -> list[Told]:
        return [f for f in self.told.values() if now - f.checked > YEAR_S]

    def confirm(self, name: str, now: float) -> None:
        fact = self.told.get(fact_name(name))
        if fact is not None:
            fact.checked = now

    def forget_teller(self, person_id: str) -> bool:
        changed = False
        for fact in self.told.values():
            if fact.by == person_id:
                fact.by, fact.by_label = None, ""
                changed = True
        return changed

    def to_list(self) -> list:
        return [f.to_dict() for f in sorted(self.told.values(), key=lambda f: f.name)]
