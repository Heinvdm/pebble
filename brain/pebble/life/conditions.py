from dataclasses import dataclass, field
from typing import Callable

from ..understand.logic import cond_words, events, leaves
from ..understand.request import MOVING, Cond, Request

WATCHING_STATES = frozenset({"present", "in_room"})
WATCHING_EVENTS = frozenset({"arrives", "leaves"})


def evaluate(cond: Cond, read: Callable[[Cond], bool | None]) -> bool | None:
    if cond.join == "not":
        value = evaluate(cond.parts[0], read)
        return None if value is None else not value
    if cond.join in ("all", "any"):
        values = [evaluate(part, read) for part in cond.parts]
        if cond.join == "all":
            if any(value is False for value in values):
                return False
            return None if any(value is None for value in values) else True
        if any(value is True for value in values):
            return True
        return None if any(value is None for value in values) else False
    try:
        value = read(cond)
    except Exception:
        return None
    return value if value is None else bool(value)


def unsure_parts(cond: Cond, read: Callable[[Cond], bool | None]) -> list[Cond]:
    out = []
    for leaf in leaves(cond):
        try:
            value = read(leaf)
        except Exception:
            value = None
        if value is None:
            out.append(leaf)
    return out


def spoken_to_asker(step: Request) -> bool:
    if step.branch:
        return all(spoken_to_asker(inner) for inner in step.then + step.else_)
    return step.kind == "say_to" and step.who in ("", "me") and all(spoken_to_asker(inner) for inner in step.then)


def moves(steps) -> bool:
    for step in steps:
        if step.branch:
            if moves(step.then + step.else_):
                return True
            continue
        if step.kind in MOVING or moves(step.then):
            return True
    return False


@dataclass(frozen=True)
class Choice:
    steps: tuple = ()
    value: bool | None = True
    unsure: tuple = ()
    held: tuple = ()
    both: bool = False

    def couldnt(self) -> str:
        if not self.unsure:
            return ""
        if all(leaf.state == "result" for leaf in self.unsure):
            return "I couldn't find that out"
        parts = [cond_words(leaf) for leaf in self.unsure]
        said = " or ".join(dict.fromkeys(_whether(part) for part in parts))
        return f"I couldn't tell {said}"

    def held_words(self, branch: Request, words: Callable[[list], str]) -> str:
        if branch.then and branch.else_:
            return "so I didn't do either"
        return f"so I didn't {words(list(self.held))}"


def _whether(clause: str) -> str:
    return f"whether {clause}"


def choose(branch: Request, read: Callable[[Cond], bool | None]) -> Choice:
    value = evaluate(branch.if_, read)
    if value is True:
        return Choice(branch.then, True)
    if value is False:
        return Choice(branch.else_, False)
    unknown = tuple(unsure_parts(branch.if_, read))
    every = branch.then + branch.else_
    if every and all(spoken_to_asker(step) for step in every):
        return Choice(every, None, unknown, (), True)
    return Choice((), None, unknown, every)


@dataclass
class Watched:
    names: list = field(default_factory=list)
    unknown: list = field(default_factory=list)


def watched(request: Request, asker_id: str | None, find: Callable[[str], object]) -> Watched:
    out = Watched()
    found = [leaf.who for leaf in _conds(request) if leaf.state in WATCHING_STATES and leaf.who]
    found += [event.who for event in events(request) if (event.event in WATCHING_EVENTS or (event.event == "seen" and not event.thing)) and event.who]
    for who in dict.fromkeys(found):
        if who == "me":
            continue
        person = find(who)
        if person is None:
            out.unknown.append(who)
        elif getattr(person, "id", None) != asker_id:
            out.names.append(person)
    return out


def _conds(request: Request) -> list[Cond]:
    out = []
    for step in request.steps():
        for cond in (step.if_, step.while_):
            if cond is not None:
                out.extend(leaves(cond))
    return out
