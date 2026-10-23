import logging
import re
from dataclasses import dataclass

from ..activities.card import step_words
from ..activities.commands import for_mind

log = logging.getLogger(__name__)

CARD_FILE = "conversation/taskcard.json"
DECIDED_S = 3600.0
PROMISE_S = 86400.0
WORDS_MOST = 100
QUOTE_MOST = 120
LINE_MOST = 240
CARD_CHARS = 560
READER_CHARS = 110
TRIES_SHOWN = 3
STEPS_SHOWN = 4
PLAN_SHOWN = 4
DECIDED_SHOWN = 4
PROMISES_SHOWN = 3
DECIDED_KEEP = 20
PROMISES_KEEP = 20
HEAD = "Your task card (from what is happening now, not from memory). "
IDLE = "Doing now: nothing for anyone."
WORD = re.compile(r"[a-z0-9']+")


def _short(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _words(text: str) -> set:
    return {w for w in WORD.findall((text or "").lower()) if len(w) > 2}


@dataclass(frozen=True)
class Live:
    doing: str = ""
    words: str = ""
    asker: str = ""
    steps: tuple = ()
    trying: str = ""
    question: str = ""
    due: str = ""


def _hearers(audience) -> list[str]:
    return sorted(str(a) for a in audience or ())


def heard_by(entry: dict, audience: frozenset) -> bool:
    return frozenset(audience) <= frozenset(entry.get("audience") or ())


class TaskCard:
    def __init__(self, store, clock, record=None):
        self.store = store
        self.clock = clock
        self.record = record or (lambda kind, **data: None)
        data = {}
        try:
            data = store.read(CARD_FILE, {}) or {}
        except Exception:
            log.exception("could not read the task card")
        self.decided: list[dict] = [d for d in data.get("decided") or [] if isinstance(d, dict) and d.get("text")]
        self.promises: list[dict] = [p for p in data.get("promises") or [] if isinstance(p, dict) and p.get("text")]
        self.tick(clock.now())

    def save(self) -> None:
        try:
            self.store.write(CARD_FILE, {"decided": self.decided, "promises": self.promises})
        except Exception:
            log.exception("could not keep the task card")

    def _hhmm(self, t: float) -> str:
        local = self.clock.local(t)
        hour = local.hour % 12 or 12
        return f"{hour}:{local.minute:02d} {'am' if local.hour < 12 else 'pm'}"

    def corrected(self, who: str | None, label: str, text: str, audience) -> dict | None:
        return self._decided("correction", who, label, text, audience)

    def refused(self, who: str | None, label: str, text: str, audience, what: str = "") -> dict | None:
        return self._decided("refusal", who, label, text, audience, what)

    def _decided(self, kind: str, who, label: str, text: str, audience, what: str = "") -> dict | None:
        text = _short(text, QUOTE_MOST)
        if not text or who is None:
            return None
        now = self.clock.now()
        for entry in self.decided:
            if entry.get("who") == who and entry.get("kind") == kind and entry.get("text") == text and now - float(entry.get("t") or 0.0) < DECIDED_S:
                entry["t"] = now
                self.save()
                return entry
        entry = {"t": now, "kind": kind, "who": who, "label": label, "text": text, "audience": _hearers(audience)}
        if what:
            entry["what"] = _short(what, 80)
        self.decided.append(entry)
        del self.decided[:-DECIDED_KEEP]
        self.record("card_decided", what=kind, person=who)
        self.save()
        return entry

    def promised(self, who: str | None, label: str, text: str, audience) -> dict | None:
        text = _short(text, QUOTE_MOST)
        if not text or who is None:
            return None
        now = self.clock.now()
        if self.promise_for(who, text) is not None:
            return None
        entry = {"t": now, "who": who, "label": label, "text": text, "audience": _hearers(audience), "until": now + PROMISE_S}
        self.promises.append(entry)
        del self.promises[:-PROMISES_KEEP]
        self.record("card_promise", person=who)
        self.save()
        return entry

    def promise_for(self, who: str | None, text: str) -> dict | None:
        wanted = _words(text)
        for entry in self.promises:
            if entry.get("who") != who:
                continue
            have = _words(entry.get("text"))
            if wanted and len(wanted & have) * 2 >= len(wanted):
                return entry
        return None

    def kept(self, who: str | None, text: str) -> bool:
        entry = self.promise_for(who, text)
        if entry is None:
            return False
        self.promises.remove(entry)
        self.save()
        return True

    def tick(self, now: float) -> None:
        decided = [d for d in self.decided if now - float(d.get("t") or 0.0) <= DECIDED_S]
        promises = [p for p in self.promises if now <= float(p.get("until") or 0.0)]
        if len(decided) != len(self.decided) or len(promises) != len(self.promises):
            for entry in self.promises:
                if entry not in promises:
                    self.record("card_promise_ended", person=entry.get("who"))
            self.decided, self.promises = decided, promises
            self.save()

    def forget(self, person_id: str, names: list) -> None:
        lowered = {n.lower() for n in names or [] if n and len(n) > 1}

        def about(entry: dict) -> bool:
            words = set(WORD.findall(str(entry.get("text") or "").lower()))
            return entry.get("who") == person_id or person_id in (entry.get("audience") or []) or bool(lowered & words)

        self.decided = [d for d in self.decided if not about(d)]
        self.promises = [p for p in self.promises if not about(p)]
        self.save()

    def lines(self, live: Live, audience: frozenset, now: float) -> list[str]:
        self.tick(now)
        audience = frozenset(audience)
        first = live.doing and f"Doing now: {live.doing}"
        if first and live.words:
            first += f', because {live.asker} said: "{_short(live.words, WORDS_MOST)}"'
        rest = []
        if live.trying:
            rest.append(live.trying)
        if live.steps:
            rest.append("Next in the plan: " + ", then ".join(live.steps[:PLAN_SHOWN]) + (", and more" if len(live.steps) > PLAN_SHOWN else "") + ".")
        if live.question:
            rest.append(live.question)
        for entry in sorted(self.promises, key=lambda p: -float(p.get("t") or 0.0))[:PROMISES_SHOWN]:
            if heard_by(entry, audience):
                rest.append(f'You promised {entry["label"]} ({self._hhmm(float(entry["t"]))}): "{entry["text"]}"')
        shown = 0
        for entry in sorted(self.decided, key=lambda d: -float(d.get("t") or 0.0)):
            if shown >= DECIDED_SHOWN or not heard_by(entry, audience):
                continue
            shown += 1
            when = self._hhmm(float(entry["t"]))
            if entry["kind"] == "correction":
                rest.append(f'{entry["label"]} corrected you ({when}): "{entry["text"]}"')
            else:
                asked = f' when asked to {entry["what"]}' if entry.get("what") else ""
                rest.append(f'You said no to {entry["label"]}{asked} ({when}): "{entry["text"]}"')
        if live.due:
            rest.append(live.due)
        if not first and not rest:
            return []
        out = [HEAD + _short(first or IDLE, LINE_MOST)]
        used = len(out[0])
        for line in rest:
            line = _short(line, LINE_MOST)
            if used + len(line) + 1 > CARD_CHARS:
                continue
            out.append(line)
            used += len(line) + 1
        return out

    def text(self, live: Live, audience: frozenset, now: float) -> str:
        return "\n".join(self.lines(live, audience, now))

    def short(self, live: Live, audience: frozenset, now: float) -> str:
        parts = []
        if live.steps:
            parts.append("next " + ", then ".join(live.steps[:2]))
        if live.trying:
            parts.append(live.trying.split(".", 1)[0].lower())
        for entry in self.promises[-1:]:
            if heard_by(entry, audience):
                parts.append(f'promised {entry["label"]}: "{_short(entry["text"], 50)}"')
        if not parts:
            return ""
        return _short("Task card: " + "; ".join(parts), READER_CHARS)


def _try_line(loop) -> str:
    label = loop.asker.label if not loop.asker.own else ""
    head = f'Trying something new{" for " + label if label else ""}: "{_short(loop.words, 60)}".'
    tries = []
    for number, item in enumerate(loop.tries, 1):
        if number <= len(loop.tries) - TRIES_SHOWN:
            continue
        steps = [step_words(step) for step in (item.get("steps") or [])[:STEPS_SHOWN]]
        more = ", ..." if len(item.get("steps") or []) > STEPS_SHOWN else ""
        answer = item.get("answer") or ""
        said = f' ({label or "they"} said "{_short(answer, 40)}")' if answer else ""
        tries.append(f"try {number}: {', '.join(steps)}{more}{said}")
    out = head + (" " + "; ".join(tries) + "." if tries else "")
    if loop.waiting_since is not None:
        out += " Waiting for their answer."
    elif loop.planning:
        out += " Working out the next try."
    return out


def live_of(life, audience: frozenset) -> Live:
    commands = life.commands
    current = commands.runner.current
    doing, words, asker = "", "", ""
    if current is not None:
        doing = commands.describe() or ""
        said = getattr(current, "words", "") or ""
        heard = frozenset(getattr(current, "heard_by", ()) or ())
        if said and not current.asker.own and frozenset(audience) <= heard | {current.asker.id}:
            words, asker = said, current.asker.label
    steps = ()
    plan = commands.plan
    if plan is not None and plan.steps:
        steps = tuple(_short(for_mind(step), 60) for step in plan.steps)
    trying = ""
    loop = getattr(getattr(commands, "trying", None), "loop", None)
    if loop is not None:
        trying = _try_line(loop)
        if not doing:
            doing = f'trying "{_short(loop.words, 60)}"' + ("" if loop.asker.own else f" for {loop.asker.label}")
    question = ""
    pending = commands.pending
    if pending is not None and pending.question:
        person = life.company.book.get(pending.asker) if pending.asker else None
        whom = person.label if person is not None else "someone"
        question = f'Waiting for {whom} to answer: "{_short(pending.question, 100)}"'
    due = ""
    later = getattr(life, "later", None)
    if later is not None:
        try:
            due = later.matched()
        except Exception:
            log.exception("could not list what is due soon")
    return Live(doing, words, asker, steps, trying, question, due)
