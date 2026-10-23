import math
from dataclasses import dataclass, field
from datetime import datetime

ALIVE = "alive.json"
DAY_S = 86400.0
FAMILIAR_HALF_LIFE_DAYS = 14.0
TASTE_HALF_LIFE_DAYS = 60.0
TASTE_DAY_CAP = 2.0
TASTE_KEEP = 40
ROUTINE_HALF_LIFE_DAYS = 21.0
KNOWN_CAP = 60
PRINT_CAP = 8
FEELINGS = ("like", "dislike", "fear")
TOY_KINDS = frozenset({"ball", "teddy bear", "toy", "frisbee", "lego", "block", "doll", "stuffed toy", "kite", "skateboard"})
SEEDS = (
    ("playful", 6, ("ball", "frisbee", "toy", "teddy bear"), "like", 2.0),
    ("curious", 6, ("plant", "flower", "plant pot", "book"), "like", 1.0),
    ("affectionate", 6, ("teddy bear", "cushion", "blanket"), "like", 1.0),
    ("cautious", 4, ("vacuum", "vacuum cleaner", "hair dryer", "blender", "lawnmower", "drill"), "fear", 2.0),
    ("cautious", 4, ("toaster", "oven", "kettle"), "dislike", 0.5),
)
SEED_REASON = "part of who you are"
BORN_REASON = "you were born liking it"
BORN_WEIGHT = 1.0


def faded(weight: float, age_s: float, half_life_days: float) -> float:
    return weight * 0.5 ** (max(0.0, age_s) / (half_life_days * DAY_S))


@dataclass
class Known:
    key: str
    label: str
    name: str = ""
    owner: str | None = None
    owner_label: str = ""
    taught_by: str | None = None
    at: float = 0.0
    prints: list = field(default_factory=list)

    def title(self, you: bool = False) -> str:
        if self.name:
            return self.name.title()
        if self.owner == "pebble":
            return f"{'your' if you else 'my'} {self.label}"
        if self.owner_label:
            return f"{self.owner_label}'s {self.label}"
        return f"the {self.label}"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "name": self.name,
            "owner": self.owner,
            "owner_label": self.owner_label,
            "taught_by": self.taught_by,
            "at": self.at,
            "prints": [[round(float(v), 5) for v in vec] for vec in self.prints[-PRINT_CAP:]],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Known | None":
        try:
            known = cls(str(data["key"]), str(data["label"]), str(data.get("name") or ""), data.get("owner"), str(data.get("owner_label") or ""), data.get("taught_by"), float(data.get("at", 0.0)))
        except (KeyError, TypeError, ValueError):
            return None
        known.prints = [[float(v) for v in vec] for vec in data.get("prints") or [] if isinstance(vec, list)][-PRINT_CAP:]
        return known


class AliveBook:
    def __init__(self, data: dict | None = None):
        data = data or {}
        self.familiar: dict[str, dict] = {k: dict(v) for k, v in (data.get("familiar") or {}).items() if isinstance(v, dict)}
        self.taste: dict[str, list] = {k: [list(e) for e in v if isinstance(e, list) and len(e) >= 4] for k, v in (data.get("taste") or {}).items() if isinstance(v, list)}
        self.routine: dict[str, dict] = {k: dict(v) for k, v in (data.get("routine") or {}).items() if isinstance(v, dict)}
        self.known: dict[str, Known] = {}
        for raw in data.get("known") or []:
            known = Known.from_dict(raw) if isinstance(raw, dict) else None
            if known is not None:
                self.known[known.key] = known
        self.dock: dict = dict(data.get("dock") or {})
        self.where: dict = {str(k): str(v) for k, v in (data.get("where") or {}).items()}
        self.met_in: dict = {str(k): dict(v) for k, v in (data.get("met_in") or {}).items() if isinstance(v, dict)}
        self.seeded = bool(data.get("seeded", False))
        self.dirty = False
        self.setup = False

    def seed(self, personality: dict, now: float) -> None:
        if self.seeded:
            return
        traits = personality.get("traits") or {}
        for trait, least, kinds, feeling, weight in SEEDS:
            if float(traits.get(trait, 5)) >= least:
                for kind in kinds:
                    self.taste.setdefault(kind, []).append([now, feeling, weight, f"{SEED_REASON} ({trait})"])
        self.seeded = True
        self.dirty = True

    def reborn(self, traits: dict, liked: list[str], now: float) -> None:
        for kind in list(self.taste):
            kept = [e for e in self.taste[kind] if not str(e[3]).startswith(SEED_REASON)]
            if kept:
                self.taste[kind] = kept
            else:
                del self.taste[kind]
        self.seeded = False
        self.seed({"traits": traits}, now)
        for kind in liked:
            self.taste.setdefault(kind, []).append([now, "like", BORN_WEIGHT, BORN_REASON])
        self.dirty = True

    def familiarity(self, key: str, now: float) -> float:
        entry = self.familiar.get(key)
        if not entry:
            return 0.0
        return faded(float(entry.get("n", 0.0)), now - float(entry.get("at", now)), FAMILIAR_HALF_LIFE_DAYS)

    def novelty(self, key: str, now: float) -> float:
        return 1.0 / (1.0 + 0.6 * self.familiarity(key, now))

    def expose(self, key: str, now: float, amount: float = 1.0) -> float:
        before = self.familiarity(key, now)
        self.familiar[key] = {"n": round(before + amount, 4), "at": now}
        self.dirty = True
        return before

    def unsettle(self, key: str, now: float, keep: float = 0.4) -> None:
        if key in self.familiar:
            self.familiar[key] = {"n": round(self.familiarity(key, now) * keep, 4), "at": now}
            self.dirty = True

    def feel(self, kind: str, feeling: str, weight: float, reason: str, now: float) -> float:
        if feeling not in FEELINGS:
            raise ValueError(f"unknown feeling {feeling}")
        if self.setup and feeling != "like":
            return 0.0
        entries = self.taste.setdefault(kind, [])
        day = int(now // DAY_S)
        used = sum(e[2] for e in entries if e[1] == feeling and int(e[0] // DAY_S) == day and not str(e[3]).startswith("part of who"))
        counted = round(max(0.0, min(weight, TASTE_DAY_CAP - used)), 3)
        entries.append([now, feeling, counted, " ".join(reason.split())[:100]])
        del entries[:-TASTE_KEEP]
        self.dirty = True
        return counted

    def feelings(self, kind: str, now: float) -> dict[str, float]:
        out = {feeling: 0.0 for feeling in FEELINGS}
        for at, feeling, weight, _ in self.taste.get(kind, []):
            if feeling in out:
                out[feeling] += faded(float(weight), now - float(at), TASTE_HALF_LIFE_DAYS)
        return out

    def liking(self, kind: str, now: float) -> float:
        counts = self.feelings(kind, now)
        good, bad = counts["like"], counts["dislike"]
        return 2.0 * ((good + 1.0) / (good + bad + 2.0) - 0.5)

    def fear(self, kind: str, now: float) -> float:
        counts = self.feelings(kind, now)
        return counts["fear"] / (counts["fear"] + 2.0)

    def reasons(self, kind: str, now: float) -> list[str]:
        return [str(e[3]) for e in self.taste.get(kind, []) if faded(float(e[2]), now - float(e[0]), TASTE_HALF_LIFE_DAYS) > 0.2][-3:]

    def saw_at(self, kind: str, moment: datetime) -> bool:
        slots = self.routine.setdefault(kind, {})
        key = f"{moment.weekday()}-{moment.hour}"
        day = moment.date().isoformat()
        if slots.get("_last_" + key) == day:
            return False
        entry = slots.get(key) or {"n": 0.0, "at": moment.timestamp()}
        slots[key] = {"n": round(faded(float(entry["n"]), moment.timestamp() - float(entry["at"]), ROUTINE_HALF_LIFE_DAYS) + 1.0, 4), "at": moment.timestamp()}
        slots["_last_" + key] = day
        self.dirty = True
        return True

    def usual(self, kind: str, moment: datetime) -> float:
        slots = self.routine.get(kind) or {}
        total = 0.0
        for weekday in range(7):
            entry = slots.get(f"{weekday}-{moment.hour}")
            if isinstance(entry, dict):
                weight = 1.0 if weekday == moment.weekday() else 0.5
                total += weight * faded(float(entry["n"]), moment.timestamp() - float(entry["at"]), ROUTINE_HALF_LIFE_DAYS)
        return total

    def met(self, person_id: str, room: str, now: float) -> None:
        rooms = self.met_in.setdefault(person_id, {})
        entry = rooms.get(room) or {"n": 0.0, "at": now}
        rooms[room] = {"n": round(faded(float(entry["n"]), now - float(entry["at"]), ROUTINE_HALF_LIFE_DAYS) + 1.0, 3), "at": now}
        self.dirty = True

    def usual_room(self, person_id: str, now: float, least: float = 3.0) -> str | None:
        rooms = self.met_in.get(person_id) or {}
        scored = [(faded(float(e["n"]), now - float(e["at"]), ROUTINE_HALF_LIFE_DAYS), room) for room, e in rooms.items()]
        scored = [(n, room) for n, room in scored if n >= least]
        return max(scored)[1] if scored else None

    def teach(self, known: Known) -> Known:
        old = self.known.get(known.key)
        if old is not None:
            known.prints = (old.prints + known.prints)[-PRINT_CAP:]
        self.known[known.key] = known
        if len(self.known) > KNOWN_CAP:
            oldest = min(self.known.values(), key=lambda k: k.at)
            del self.known[oldest.key]
        self.dirty = True
        return known

    def known_of(self, label: str | None = None, owner: str | None = None) -> list[Known]:
        out = []
        for known in self.known.values():
            if label is not None and known.label != label and label not in known.key:
                continue
            if owner is not None and known.owner != owner:
                continue
            out.append(known)
        return out

    def to_dict(self) -> dict:
        return {
            "format": 1,
            "seeded": self.seeded,
            "familiar": self.familiar,
            "taste": self.taste,
            "routine": self.routine,
            "known": [k.to_dict() for k in self.known.values()],
            "dock": self.dock,
            "where": self.where,
            "met_in": self.met_in,
        }


def toy(label: str) -> bool:
    return label in TOY_KINDS or any(label.endswith(" " + kind) for kind in TOY_KINDS)


def unit(vec) -> list[float]:
    values = [float(v) for v in vec]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]
