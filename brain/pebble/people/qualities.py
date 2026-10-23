from dataclasses import asdict, dataclass

QUALITIES = ("trustworthiness", "kindness", "reliability", "respect", "playfulness", "familiarity")
WEIGHTS = {"senses": 1.0, "promise": 1.0, "model": 0.5}
HALF_LIFE_DAYS = 120.0
DAY_CAP = 2.0
LOG_KEEP = 400
DAY_S = 86400.0
FORGOTTEN_AFTER = 8


class NotScored(ValueError):
    pass


@dataclass(frozen=True)
class Evidence:
    at: float
    day: str
    quality: str
    good: bool
    weight: float
    counted: float
    reason: str
    source: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Evidence | None":
        try:
            quality = str(data["quality"])
            if quality not in QUALITIES:
                return None
            return cls(float(data["at"]), str(data["day"]), quality, bool(data["good"]), float(data["weight"]), float(data["counted"]), str(data.get("reason", "")), str(data.get("source", "")))
        except (KeyError, TypeError, ValueError):
            return None


@dataclass(frozen=True)
class Standing:
    quality: str
    good: float
    bad: float

    @property
    def amount(self) -> float:
        return self.good + self.bad

    @property
    def score(self) -> float:
        return (self.good + 1.0) / (self.good + self.bad + 2.0)


def faded(weight: float, age_s: float, half_life_days: float = HALF_LIFE_DAYS) -> float:
    return weight * 0.5 ** (max(0.0, age_s) / (half_life_days * DAY_S))


class Ledger:
    def __init__(self, entries: list | None = None, half_life_days: float = HALF_LIFE_DAYS, day_cap: float = DAY_CAP):
        self.half_life_days = half_life_days
        self.day_cap = day_cap
        self.entries: list[Evidence] = [e for e in (Evidence.from_dict(raw) for raw in entries or [] if isinstance(raw, dict)) if e is not None]

    def used_today(self, quality: str, good: bool, day: str) -> float:
        return sum(e.counted for e in self.entries if e.quality == quality and e.good == good and e.day == day)

    def add(self, quality: str, good: bool, source: str, reason: str, at: float, day: str) -> Evidence:
        if quality not in QUALITIES:
            raise ValueError(f"unknown quality {quality}")
        if source not in WEIGHTS:
            raise ValueError(f"unknown source {source}")
        weight = WEIGHTS[source]
        room = max(0.0, self.day_cap - self.used_today(quality, good, day))
        evidence = Evidence(at, day, quality, bool(good), weight, round(min(weight, room), 3), " ".join(reason.split())[:160], source)
        self.entries.append(evidence)
        del self.entries[:-LOG_KEEP]
        return evidence

    def standing(self, quality: str, now: float) -> Standing:
        good = sum(faded(e.counted, now - e.at, self.half_life_days) for e in self.entries if e.quality == quality and e.good)
        bad = sum(faded(e.counted, now - e.at, self.half_life_days) for e in self.entries if e.quality == quality and not e.good)
        return Standing(quality, good, bad)

    def standings(self, now: float) -> dict[str, Standing]:
        return {quality: self.standing(quality, now) for quality in QUALITIES}

    def bad_total(self, now: float) -> float:
        return sum(faded(e.counted, now - e.at, self.half_life_days) for e in self.entries if not e.good)

    def span_days(self, qualities: tuple[str, ...] = QUALITIES) -> float:
        times = [e.at for e in self.entries if e.quality in qualities and e.counted > 0]
        return (max(times) - min(times)) / DAY_S if times else 0.0

    def prune(self, now: float) -> int:
        horizon = FORGOTTEN_AFTER * self.half_life_days * DAY_S
        before = len(self.entries)
        self.entries = [e for e in self.entries if now - e.at < horizon]
        return before - len(self.entries)

    def to_list(self) -> list[dict]:
        return [e.to_dict() for e in self.entries]
