import logging
from typing import Callable

from ..clock import from_iso, iso
from ..values import FEEDBACK_MAP, NudgeRefused
from .registry import PEBBLE

log = logging.getLogger(__name__)

VALUE_EVIDENCE = 4
TRAIT_EVIDENCE = 8
WINDOW_S = 7 * 86400.0
TRAIT_SIGNALS = {
    "game_joined": ("playful", 1),
    "shushed": ("chatty", -1),
    "fun_discovery": ("curious", 1),
    "got_stuck": ("curious", -1),
    "bump": ("cautious", 1),
    "fall": ("cautious", 1),
    "near_fall": ("cautious", 1),
    "safe_stretch": ("cautious", -1),
}
WORDS = {
    "praised_tidy": "I was praised for tidying up",
    "storage_full": "my storage ran full",
    "fun_discovery": "I found fun new things",
    "got_stuck": "I kept getting stuck",
    "game_joined": "people joined my games",
    "shushed": "I was shushed",
    "bump": "I bumped into things",
    "fall": "I fell",
    "near_fall": "I nearly fell",
    "safe_stretch": "I've been safe for a long stretch",
    "own_idea_went_well": "my own ideas went well",
    "refusal_annoyed": "saying no annoyed people",
}
MORE = {"playful": "more playful", "chatty": "chattier", "curious": "more curious", "cautious": "more careful", "affectionate": "cuddlier"}
LESS = {"playful": "less playful", "chatty": "quieter", "curious": "less curious", "cautious": "bolder", "affectionate": "less cuddly"}
TIMES = {1: "once", 2: "twice"}


def _seconds(at) -> float | None:
    try:
        return from_iso(str(at))
    except (TypeError, ValueError):
        return None


def because(kinds: dict[str, int]) -> str:
    parts = [f"{WORDS.get(kind, kind)} {TIMES.get(count, f'{count} times')}" for kind, count in sorted(kinds.items(), key=lambda item: -item[1])[:2]]
    return " and ".join(parts)


class Growth:
    def __init__(self, store, books, dials, diary, clock, record: Callable[..., None] | None = None):
        self.store = store
        self.books = books
        self.dials = dials
        self.diary = diary
        self.clock = clock
        self.record = record or (lambda kind, **data: None)

    def _signals(self, mapping: dict, name: str, since: float | None, now: float) -> tuple[int, dict[str, int]]:
        net, kinds = 0, {}
        for item in self.books.values.feedback:
            target = mapping.get(item.get("kind"))
            at = _seconds(item.get("at"))
            if target is None or target[0] != name or at is None or now - at > WINDOW_S or (since is not None and at <= since):
                continue
            net += target[1]
            kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
        return net, kinds

    def consider(self, plasticity) -> list[dict]:
        found = []
        for step in (self._value, self._trait):
            try:
                moved = step(plasticity)
            except (OSError, ValueError, KeyError) as error:
                log.warning("could not grow: %s", error)
                moved = None
            if moved is not None:
                found.append(moved)
        return found

    def _value(self, plasticity) -> dict | None:
        values = self.books.values
        now = self.clock.now()
        need = plasticity.evidence(VALUE_EVIDENCE)
        ranked = []
        for dial in values.nudgeable():
            net, kinds = self._signals(FEEDBACK_MAP, dial.name, _seconds(values.last_change(dial.name)), now)
            if abs(net) >= need:
                ranked.append((abs(net), dial.name, net, kinds))
        for _, name, net, kinds in sorted(ranked, key=lambda item: (-item[0], item[1])):
            why = because(kinds)
            try:
                record = values.step(name, net > 0, why, iso(now), now, PEBBLE)
            except NudgeRefused as error:
                self.record("value_held", value=name, why=str(error))
                continue
            self.books.save("values")
            line = f"My {record['raise']} grew a little and my {record['lower']} eased off, because {why}."
            self.diary(line, "value_nudge")
            self.record("value_moved", up=record["raise"], down=record["lower"], plasticity=round(plasticity.level, 2))
            return {**record, "you": f'you wrote in your diary: "{line}"'}
        return None

    def _trait_since(self, history: list, name: str) -> float | None:
        times = [_seconds(h.get("at")) for h in history if isinstance(h, dict) and h.get("trait") == name]
        times = [t for t in times if t is not None]
        return max(times) if times else None

    def _trait(self, plasticity) -> dict | None:
        personality = self.store.read("personality.json", {}) or {}
        traits = personality.get("traits") or {}
        history = personality.get("history") or []
        now = self.clock.now()
        need = plasticity.evidence(TRAIT_EVIDENCE)
        ranked = []
        for name in sorted({target for target, _ in TRAIT_SIGNALS.values()}):
            if name not in traits:
                continue
            net, kinds = self._signals(TRAIT_SIGNALS, name, self._trait_since(history, name), now)
            if abs(net) >= need:
                ranked.append((abs(net), name, net, kinds))
        for _, name, net, kinds in sorted(ranked, key=lambda item: (-item[0], item[1])):
            why = because(kinds)
            after = int(traits[name]) + (1 if net > 0 else -1)
            ruling = self.dials.propose(f"trait.{name}", after, PEBBLE, why)
            if not ruling.ok:
                self.record("trait_held", trait=name, why=ruling.reason)
                continue
            line = f"I feel a little {(MORE if net > 0 else LESS)[name]} than I was, because {why}."
            self.diary(line, "trait")
            self.record("trait_moved", trait=name, to=after, plasticity=round(plasticity.level, 2))
            return {"trait": name, "to": after, "why": why, "you": f'you wrote in your diary: "{line}"'}
        return None
