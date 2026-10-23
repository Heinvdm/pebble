from dataclasses import dataclass

from .owner import OwnerGrant
from .self.checker import check
from .self.registry import OWNER, PEBBLE
from .self.stability import held

FEEDBACK_KEEP = 200
FEEDBACK_MAP = {
    "praised_tidy": ("tidiness", 1),
    "storage_full": ("tidiness", 1),
    "fun_discovery": ("curiosity", 1),
    "got_stuck": ("curiosity", -1),
    "game_joined": ("playfulness", 1),
    "shushed": ("playfulness", -1),
    "bump": ("caution", 1),
    "fall": ("caution", 1),
    "near_fall": ("caution", 1),
    "safe_stretch": ("caution", -1),
    "own_idea_went_well": ("independence", 1),
    "refusal_annoyed": ("independence", -1),
}


class NudgeRefused(ValueError):
    pass


class OwnerOnly(PermissionError):
    pass


@dataclass
class Dial:
    name: str
    start: int
    value: int
    minimum: int
    maximum: int
    owner_only: bool
    nudged_by: str

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "value": self.value,
            "min": self.minimum,
            "max": self.maximum,
            "owner_only": self.owner_only,
            "nudged_by": self.nudged_by,
        }


def _int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _level_word(value: int) -> str:
    if value >= 8:
        return "a lot"
    if value >= 6:
        return "quite a bit"
    if value >= 4:
        return "somewhat"
    return "a little"


class Values:
    def __init__(self, data: dict):
        self.dials: dict[str, Dial] = {}
        for name, raw in (data.get("dials") or {}).items():
            minimum = max(0, min(10, _int(raw.get("min"), 0)))
            maximum = max(minimum, min(10, _int(raw.get("max"), 10)))
            start = max(minimum, min(maximum, _int(raw.get("start"), minimum)))
            value = max(minimum, min(maximum, _int(raw.get("value"), start)))
            self.dials[name] = Dial(name, start, value, minimum, maximum, bool(raw.get("owner_only")), str(raw.get("nudged_by", "")))
        self.nudges: list[dict] = list(data.get("nudges") or [])
        self.drifts: list[dict] = list(data.get("drifts") or [])
        self.owner_changes: list[dict] = list(data.get("owner_changes") or [])
        self.feedback: list[dict] = list(data.get("feedback") or [])
        self.record = lambda kind, **data: None

    def value(self, name: str) -> int:
        return self.dials[name].value

    def scores(self) -> dict[str, int]:
        return {name: dial.value for name, dial in self.dials.items()}

    def nudgeable(self) -> list[Dial]:
        return [dial for dial in self.dials.values() if not dial.owner_only]

    def budget(self) -> int:
        return sum(dial.value for dial in self.nudgeable())

    def log_feedback(self, kind: str, at: str, note: str = "") -> bool:
        if kind not in FEEDBACK_MAP:
            return False
        self.feedback.append({"kind": kind, "at": at, "note": note[:120]})
        del self.feedback[:-FEEDBACK_KEEP]
        return True

    def take_feedback(self) -> list[dict]:
        taken, self.feedback = self.feedback, []
        return taken

    def last_change(self, name: str) -> str | None:
        times = [str(n.get("at")) for n in self.nudges if name in (n.get("raise"), n.get("lower")) and n.get("at")]
        times += [str(c.get("at")) for c in self.owner_changes if c.get("value") == name and c.get("at")]
        return max(times) if times else None

    def _guard_changes(self) -> list[dict]:
        out = []
        for record in self.nudges:
            at = record.get("t")
            if not isinstance(at, (int, float)) or isinstance(at, bool):
                continue
            if "raise_to" in record:
                out.append({"name": f"value.{record['raise']}", "from": record["raise_to"] - 1, "to": record["raise_to"], "at": at})
            if "lower_to" in record:
                out.append({"name": f"value.{record['lower']}", "from": record["lower_to"] + 1, "to": record["lower_to"], "at": at})
        return out

    def _check_pair(self, raise_name: str, lower_name: str) -> tuple[Dial, Dial]:
        if raise_name == lower_name:
            raise NudgeRefused("raise and lower must be different values")
        if raise_name not in self.dials or lower_name not in self.dials:
            raise NudgeRefused("unknown value")
        up, down = self.dials[raise_name], self.dials[lower_name]
        if up.owner_only or down.owner_only:
            raise NudgeRefused("only the owner can change honesty and kindness")
        if up.value + 1 > up.maximum:
            raise NudgeRefused(f"{up.name} is at its ceiling")
        if down.value - 1 < down.minimum:
            raise NudgeRefused(f"{down.name} is at its floor")
        return up, down

    def nudge(self, raise_name: str, lower_name: str, reason: str, at: str, now: float = 0.0, who: str = PEBBLE) -> dict:
        if not reason.strip():
            raise NudgeRefused("a nudge needs a reason")
        up, down = self._check_pair(raise_name, lower_name)
        changes = self._guard_changes()
        for dial, after in ((up, up.value + 1), (down, down.value - 1)):
            ruling = check(f"value.{dial.name}", after, who)
            if not ruling.ok:
                raise NudgeRefused(ruling.reason)
            hold = held(changes, f"value.{dial.name}", dial.value, after, now)
            if hold:
                raise NudgeRefused(f"my {dial.name}: {hold}")
        up.value += 1
        down.value -= 1
        record = {"at": at, "t": now, "raise": up.name, "lower": down.name, "raise_to": up.value, "lower_to": down.value, "reason": reason.strip()[:200], "who": who}
        self.nudges.append(record)
        self.record("value_changed", up=up.name, down=down.name, up_to=up.value, down_to=down.value, who=who, why=record["reason"])
        return record

    def propose(self, feedback: list[dict]) -> tuple[str, str, str] | None:
        tally: dict[str, int] = {}
        counts: dict[str, int] = {}
        for item in feedback:
            mapped = FEEDBACK_MAP.get(item.get("kind"))
            if mapped is None or mapped[0] not in self.dials or self.dials[mapped[0]].owner_only:
                continue
            tally[mapped[0]] = tally.get(mapped[0], 0) + mapped[1]
            counts[item["kind"]] = counts.get(item["kind"], 0) + 1
        signals = sorted(((abs(net), name, net) for name, net in tally.items() if net), key=lambda x: (-x[0], x[1]))
        if not signals:
            return None
        _, name, net = signals[0]
        evidence = ", ".join(f"{count} x {kind}" for kind, count in sorted(counts.items()))
        partners = [d for d in self.nudgeable() if d.name != name]
        if net > 0:
            if self.dials[name].value >= self.dials[name].maximum:
                return None
            options = [d for d in partners if d.value > d.minimum]
            if not options:
                return None
            partner = min(options, key=lambda d: (tally.get(d.name, 0), -(d.value - d.start), d.name))
            return name, partner.name, f"{evidence}; {partner.name} gives up a point"
        if self.dials[name].value <= self.dials[name].minimum:
            return None
        options = [d for d in partners if d.value < d.maximum]
        if not options:
            return None
        partner = min(options, key=lambda d: (-tally.get(d.name, 0), d.value - d.start, d.name))
        return partner.name, name, f"{evidence}; {partner.name} takes the point"

    def partner_for(self, name: str, up: bool) -> str | None:
        options = [d for d in self.nudgeable() if d.name != name and (d.value > d.minimum if up else d.value < d.maximum)]
        if not options:
            return None
        if up:
            return max(options, key=lambda d: (d.value - d.start, d.value, d.name)).name
        return min(options, key=lambda d: (d.value - d.start, d.value, d.name)).name

    def step(self, name: str, up: bool, reason: str, at: str, now: float = 0.0, who: str = PEBBLE) -> dict:
        partner = self.partner_for(name, up)
        if partner is None:
            raise NudgeRefused("no other value can give or take the point")
        return self.nudge(name, partner, reason, at, now, who) if up else self.nudge(partner, name, reason, at, now, who)

    def owner_set(self, name: str, value: int, grant: OwnerGrant, at: str, floor: int | None = None) -> dict:
        if not isinstance(grant, OwnerGrant):
            raise OwnerOnly("setting a value directly needs the owner's passphrase")
        if name not in self.dials:
            raise NudgeRefused("unknown value")
        dial = self.dials[name]
        if floor is not None:
            dial.minimum = max(0, min(10, int(floor)))
            dial.maximum = max(dial.minimum, dial.maximum)
        before = dial.value
        dial.value = max(dial.minimum, min(dial.maximum, int(value)))
        dial.start = dial.value
        record = {"at": at, "value": name, "set_to": dial.value, "floor": dial.minimum}
        self.owner_changes.append(record)
        self.record("value_set", value=name, before=before, after=dial.value, who=OWNER, why="my owner set it")
        return record

    def describe(self) -> str:
        parts = [f"{name} {_level_word(d.value)} ({d.value}/10)" for name, d in self.dials.items()]
        return "You care about " + ", ".join(parts) + "."

    def to_dict(self) -> dict:
        return {
            "format": 1,
            "dials": {name: dial.to_dict() for name, dial in self.dials.items()},
            "nudges": self.nudges,
            "drifts": self.drifts,
            "owner_changes": self.owner_changes,
            "feedback": self.feedback,
        }
