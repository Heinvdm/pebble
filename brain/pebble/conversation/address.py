import math
from collections import deque
from dataclasses import dataclass, field

from . import words as w

ADDRESSED = "addressed"
MAYBE = "maybe"
OVERHEARD = "overheard"
LABELS = (ADDRESSED, MAYBE, OVERHEARD)
ADDRESSED_AT = 1.5
MAYBE_AT = 0.0
PRIOR = -1.2
FOLLOW_S = 6.0
ASKED_S = 10.0


@dataclass(frozen=True)
class Cues:
    name: str | None = None
    keyword: bool = False
    looking: bool | None = None
    looking_at_other: bool = False
    since_spoke: float | None = None
    asked: bool = False
    spoke_to_them: bool = False
    alone: bool = False
    others: int = 0
    on_phone: bool = False
    one_sided: bool = False
    you_form: bool = False
    question: bool = False
    command: bool = False
    to_room: bool = False
    other_named: bool = False
    exchange: bool = False
    attentive: bool = False
    backchannel: bool = False
    about_me: bool = False
    busy: bool = False

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, False, 0)}


@dataclass(frozen=True)
class Verdict:
    label: str
    score: float
    reasons: tuple = field(default_factory=tuple)

    @property
    def addressed(self) -> bool:
        return self.label == ADDRESSED

    def as_dict(self) -> dict:
        return {"label": self.label, "score": round(self.score, 2), "reasons": list(self.reasons)}


def weigh(cues: Cues) -> list[tuple[float, str]]:
    parts: list[tuple[float, str]] = [(PRIOR, "most talk near me is not to me")]
    if cues.name == "vocative":
        parts.append((4.0, "my name was called"))
    elif cues.name == "mention":
        parts.append((0.3, "my name came up"))
    if cues.looking is True:
        parts.append((1.6, "they were looking at me"))
    elif cues.looking is False:
        parts.append((-0.8, "they were looking away"))
    if cues.looking_at_other:
        parts.append((-1.2, "they were looking at someone else"))
    if cues.since_spoke is not None:
        if cues.asked and cues.since_spoke <= ASKED_S and (cues.spoke_to_them or cues.alone):
            parts.append((2.8, "they answered my question"))
        elif cues.since_spoke <= FOLLOW_S and (cues.spoke_to_them or cues.alone):
            parts.append((1.8, "we were just talking"))
        elif cues.since_spoke <= FOLLOW_S:
            parts.append((0.6, "I spoke a moment ago"))
    if cues.alone and not cues.on_phone and not cues.one_sided:
        parts.append((0.6 if cues.busy else 1.6, "nobody else is here" if not cues.busy else "nobody else is here, but they are busy with something"))
    if cues.on_phone:
        parts.append((-1.5 if cues.name == "vocative" else -4.0, "they are on the phone"))
    elif cues.one_sided:
        parts.append((-3.0, "it sounds like one side of a phone call"))
    if cues.you_form:
        parts.append((0.8 if cues.alone or cues.looking or cues.attentive else 0.3, "they said 'you' or told someone to do something"))
    if cues.question and (cues.alone or cues.looking):
        parts.append((0.4, "a question"))
    if cues.command and (cues.alone or cues.looking):
        parts.append((0.4, "a request"))
    if cues.to_room and not cues.other_named:
        parts.append((0.5, "a question to the whole room"))
    if cues.other_named:
        parts.append((-3.5, "they called someone else by name"))
    if cues.exchange and cues.name != "vocative":
        parts.append((-0.5 if cues.looking else -1.5, "two people are talking to each other"))
    if cues.attentive:
        parts.append((0.9, "I was already paying attention to them"))
    if cues.about_me and cues.name != "vocative" and not cues.alone:
        parts.append((-1.4, "they talked about me, not to me"))
    if cues.backchannel and not cues.asked:
        parts.append((-0.6, "just 'yeah' or 'mm'"))
    if cues.others >= 2 and cues.name != "vocative" and not cues.looking:
        parts.append((-0.5, "a few people are here"))
    return parts


def decide(cues: Cues) -> Verdict:
    parts = weigh(cues)
    score = sum(v for v, _ in parts)
    if cues.on_phone and cues.name != "vocative":
        score = min(score, MAYBE_AT - 0.5)
    if cues.other_named and cues.name != "vocative":
        score = min(score, MAYBE_AT - 0.5)
    label = ADDRESSED if score >= ADDRESSED_AT else (MAYBE if score >= MAYBE_AT else OVERHEARD)
    reasons = tuple(why for value, why in sorted(parts[1:], key=lambda p: -abs(p[0])))
    return Verdict(label, score, reasons)


ALONE_S = 60.0
EXCHANGE_S = 20.0
CALL_S = 90.0
ATTENTIVE_S = 8.0
KEEP_S = 300.0


@dataclass(frozen=True)
class Said:
    at: float
    who: str
    label: str
    text: str


class Room:
    def __init__(self, name: str = "Pebble", aliases: tuple = ("robot",)):
        self.name = name
        self.aliases = aliases
        self.said: deque = deque()
        self.spoke_at = -math.inf
        self.spoke_to: str | None = None
        self.asked = False
        self.attentive: dict[str, float] = {}

    def heard(self, at: float, who: str, verdict: Verdict, text: str = "") -> None:
        self.said.append(Said(at, who, verdict.label, text))
        while self.said and at - self.said[0].at > KEEP_S:
            self.said.popleft()
        if verdict.label == MAYBE or verdict.addressed:
            self.attentive[who] = at + ATTENTIVE_S

    def spoke(self, at: float, to: str | None, asked: bool) -> None:
        self.spoke_at = at
        self.spoke_to = to
        self.asked = asked
        if to is not None:
            self.attentive[to] = max(self.attentive.get(to, -math.inf), at + ATTENTIVE_S)

    def voices(self, at: float, within: float) -> set[str]:
        return {s.who for s in self.said if at - s.at <= within}

    def exchange(self, at: float, who: str) -> bool:
        recent = [s for s in self.said if at - s.at <= EXCHANGE_S and s.label != ADDRESSED and s.at > self.spoke_at]
        speakers = [s.who for s in recent]
        others = {s for s in speakers if s != who}
        if not others:
            return False
        switches = sum(1 for a, b in zip(speakers, speakers[1:]) if a != b)
        return switches >= 1 or who not in speakers

    def one_sided(self, at: float, who: str, text: str, alone: bool) -> bool:
        if not alone:
            return False
        mine = [s for s in self.said if s.who == who and at - s.at <= CALL_S and s.label != ADDRESSED]
        if at - self.spoke_at <= CALL_S:
            return False
        if w.call_words(text) and not mine:
            return w.words(text)[:1] in (["hello"], ["hi"]) and len(w.words(text)) <= 3
        if len(mine) < 2:
            return False
        talky = [s for s in mine if w.call_words(s.text) or w.backchannel(s.text)]
        return bool(talky) or w.call_words(text) or w.backchannel(text)

    def cues(self, at: float, who: str, text: str, keyword: bool, people: int, looking: bool | None = None, at_other: bool = False, on_phone: bool = False, names: tuple = (), busy: bool = False, name_alone: bool = False) -> Cues:
        voices = self.voices(at, ALONE_S) - {who}
        core = w.body(text, (self.name,) + tuple(names))
        alone = people <= 1 and not voices
        since = at - self.spoke_at if self.spoke_at > -math.inf else None
        others = [n for n in names if n and n.lower() != self.name.lower()]
        return Cues(
            name=w.name_use(text, self.name, keyword, name_alone) or ("vocative" if any(w.name_use(text, alias) == "vocative" for alias in self.aliases) else None),
            keyword=keyword,
            looking=looking,
            looking_at_other=at_other,
            since_spoke=since,
            asked=self.asked,
            spoke_to_them=self.spoke_to is None and self.asked or self.spoke_to == who,
            alone=alone,
            others=max(0, people - 1),
            on_phone=on_phone,
            one_sided=self.one_sided(at, who, text, alone),
            you_form=w.you_form(core),
            question=w.is_question(core),
            command=w.is_command(core),
            to_room=w.to_room(core),
            other_named=w.other_vocative(text, others) is not None,
            exchange=self.exchange(at, who),
            attentive=self.attentive.get(who, -math.inf) >= at,
            backchannel=w.backchannel(core),
            about_me=w.about_it(core),
            busy=busy,
        )
