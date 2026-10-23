import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable

from ..activities.card import Card, step_words
from ..mind.base import CallOptions, MindInterrupted, MindUnavailable, options_kwargs
from ..mind.budget import GUIDE, MATCHED, TEACH, WORDS, Prompt
from ..understand.request import BadRequest, from_dict
from .book import SLOT, Entry, shown_name
from .grammar import grammar as teach_grammar
from .record import CARD_KINDS, is_move, join, kind_of, manner, nouns

log = logging.getLogger(__name__)

TEACH_TOKENS = 520
TEACH_WAIT_S = 120.0
RETRIES = 3
KNOWN_CHARS = 420
MADE_KINDS = ("move", "procedure", "route", "concept", "word", "way", "habit")
NAME_MOST = 40
ABOUT_MOST = 160
ALIASES_MOST = 4
SLOT_FIELDS = ("place", "thing", "who", "to", "text", "subject", "until_seen")
HEAD_STOP = frozenset("the a an my your our of to in on at and".split())
TEACH_GUIDE = """You work out what {name}, a small home robot on two wheels with a face screen, has just been taught. You get a short record of what the teacher showed. Reply with JSON only:
{{"think":"a few short notes","kind":"move","name":"...","aliases":["..."],"about":"one plain line on what it does and who it is for","steps":[...],"slots":{{}}}}
kind is move when every step is a block, procedure when any step is a request; route, concept, word, way or habit only when the record says so.
Steps use the blocks below, or {{"do":"request","request":{{...}}}} copied from the record. Write turns, rolls, faces and tilts as blocks. Join small turns and rolls into one step. Leave out false starts. Never add a step the record doesn't show, never make anything faster than shown, and never move towards a person or animal to bump them.
With one example, keep everything as shown. When the examples differ only in a place, thing or person, write that part as {{slot}} (like "{{door}}") and list every value seen in slots. Never make a slot for a way, a speed or a number.
name: what the teacher called it, else two or three plain words."""
TEACH_EXAMPLE = (
    "Taught by Ina (trusted). Ways shown: said.\nThey called it: \"door check\"\n"
    "Example 1:\n1. {\"do\":\"request\",\"request\":{\"kind\":\"go_to_place\",\"place\":\"back door\"}}\n2. {\"do\":\"request\",\"request\":{\"kind\":\"look\",\"thing\":\"handle\"}}\n3. {\"do\":\"request\",\"request\":{\"kind\":\"come\",\"who\":\"me\"}}\n"
    "Example 2:\n1. {\"do\":\"request\",\"request\":{\"kind\":\"go_to_place\",\"place\":\"front door\"}}\n2. {\"do\":\"request\",\"request\":{\"kind\":\"look\",\"thing\":\"handle\"}}\n3. {\"do\":\"request\",\"request\":{\"kind\":\"come\",\"who\":\"me\"}}\n"
    "Work it out.",
    {"think": "the door changed, the rest stayed the same", "kind": "procedure", "name": "door check", "aliases": ["check the door"], "about": "goes to a door, looks at its handle and comes back to the asker", "steps": [{"do": "request", "request": {"kind": "go_to_place", "place": "{door}"}}, {"do": "request", "request": {"kind": "look", "thing": "handle"}}, {"do": "request", "request": {"kind": "come", "who": "me"}}], "slots": {"door": ["back door", "front door"]}},
)
WORK = "Work it out."


@dataclass
class Question:
    text: str
    kind: str
    keep: list = field(default_factory=list)
    other: list = field(default_factory=list)
    words: dict = field(default_factory=dict)


@dataclass
class Unified:
    steps: list
    slots: dict = field(default_factory=dict)
    question: Question | None = None


@dataclass
class Made:
    kind: str
    name: str
    steps: list
    slots: dict = field(default_factory=dict)
    aliases: list = field(default_factory=list)
    about: str = ""
    made_by: str = "plain"
    seconds: float = 0.0
    problems: list = field(default_factory=list)
    calls: int = 0
    failed: str = ""


def _slot_name(field_name: str, values: list) -> str:
    heads = {str(v).split()[-1] for v in values if str(v).split()}
    if len(heads) == 1:
        head = heads.pop()
        if head not in HEAD_STOP and head.isalpha() and 2 < len(head) <= 12:
            return head
    return {"who": "person", "to": "person", "until_seen": "thing", "subject": "thing", "text": "words"}.get(field_name, field_name)


def _set_noun(step: dict, field_name: str, value: str) -> dict:
    out = json.loads(json.dumps(step))
    if out.get("do") == "request":
        out["request"][field_name] = value
    else:
        out[field_name] = value
    return out


def _value(step: dict, field_name: str):
    if step.get("do") == "request":
        return (step.get("request") or {}).get(field_name)
    return step.get(field_name)


def _lcs(a: list, b: list) -> list[tuple[int, int]]:
    rows = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) - 1, -1, -1):
        for j in range(len(b) - 1, -1, -1):
            rows[i][j] = rows[i + 1][j + 1] + 1 if a[i] == b[j] else max(rows[i + 1][j], rows[i][j + 1])
    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            out.append((i, j))
            i, j = i + 1, j + 1
        elif rows[i + 1][j] >= rows[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


def said_step(step: dict) -> str:
    name = step.get("do")
    if name == "route":
        return f"take the way to the {step.get('route', '')}"
    if name == "spot":
        return f"go to the {step.get('spot', '')}"
    if name != "request":
        return step_words(step)
    request = step.get("request") or {}
    kind = request.get("kind")
    place, thing, who, text = request.get("place", ""), request.get("thing", ""), request.get("who", ""), request.get("text", "")
    whom = "you" if who in ("", "me") else who.title()
    if kind == "go_to_place":
        return f"go to the {place}"
    if kind == "go_to_thing":
        return f"go to the {thing}"
    if kind == "look":
        return f"look at the {thing}" if thing else f"look at {whom}"
    if kind == "come":
        return f"come to {whom}"
    if kind == "find":
        return f"look for the {thing}"
    if kind == "check":
        target = thing or place
        return f"check the {target}" if target else "have a look round"
    if kind == "say_to":
        return f'tell {whom} "{text}"' if text else f"tell {whom}"
    if kind == "turn":
        way = request.get("way", "")
        return "spin round" if way == "around" else f"turn {way}".strip()
    if kind == "move":
        return f"roll {request.get('way') or 'forward'}"
    if kind == "wait":
        return "wait"
    if kind == "go_home":
        return "go to my charger"
    if kind == "go_back":
        return f"go back to the {place}" if place and place not in ("start", "before") else "go back"
    if kind == "back_off":
        return "back away"
    if kind == "play":
        return f"push the {thing} to {'you' if request.get('to') in ('', 'me', None) else str(request.get('to')).title()}" if request.get("to") else f"play with the {thing}"
    if kind == "remember_spot":
        return f"remember the spot as the {request.get('name', '')}"
    return str(kind or "").replace("_", " ")


def said_steps(steps: list) -> str:
    parts = []
    for step in steps:
        words = said_step(step)
        words = SLOT.sub(lambda m: m.group(1).replace("_", " "), words)
        if step.get("repeat", 1) > 1:
            words += " twice" if step["repeat"] == 2 else f" {step['repeat']} times"
        if words:
            parts.append(words)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + ", then " + parts[-1]


def unify(examples: list[list[dict]]) -> Unified:
    examples = [join(list(e)) for e in examples if e]
    if not examples:
        return Unified([])
    if len(examples) == 1:
        return Unified(examples[0])
    first = examples[0]
    slots: dict = {}
    question = None
    steps = [json.loads(json.dumps(s)) for s in first]
    for other in examples[1:]:
        if [kind_of(s) for s in other] != [kind_of(s) for s in first]:
            pairs = _lcs([sig_core(s) for s in first], [sig_core(s) for s in other])
            matched_first = {i for i, _ in pairs}
            matched_other = {j for _, j in pairs}
            extra_other = [s for j, s in enumerate(other) if j not in matched_other]
            extra_first = [s for i, s in enumerate(first) if i not in matched_first]
            if question is None and (extra_other or extra_first):
                if extra_other:
                    text = f"The second time you also had me {said_steps(extra_other)}. Should I do that every time?"
                    question = Question(text, "extra", [json.loads(json.dumps(s)) for s in other], steps)
                else:
                    common = [first[i] for i, _ in pairs]
                    text = f"The first time you also had me {said_steps(extra_first)}. Should I still do that?"
                    question = Question(text, "extra", steps, common)
            continue
        for index, (mine, theirs) in enumerate(zip(first, other)):
            for field_name in SLOT_FIELDS:
                a, b = _value(mine, field_name), _value(theirs, field_name)
                if a and b and a != b:
                    current = _value(steps[index], field_name) or ""
                    found = SLOT.fullmatch(str(current))
                    if found:
                        slot = found.group(1)
                    else:
                        slot = _slot_name(field_name, [a, b])
                        base, n = slot, 2
                        while slot in slots and a not in slots[slot]:
                            slot, n = f"{base}{n}", n + 1
                        steps[index] = _set_noun(steps[index], field_name, "{" + slot + "}")
                    values = slots.setdefault(slot, [])
                    for value in (a, b):
                        if value not in values:
                            values.append(value)
            if question is None:
                left, right = manner(mine), manner(theirs)
                if left != right and kind_of(mine) == kind_of(theirs):
                    text = f"The first time you had me {said_step(mine)} and the second time {said_step(theirs)}. Does it matter?"
                    alternative = [json.loads(json.dumps(s)) for s in steps]
                    alternative[index] = _with_manner(alternative[index], right)
                    question = Question(text, "manner", steps, alternative, {"position": index, "first": left, "second": right})
    for index, step in enumerate(steps):
        for field_name in SLOT_FIELDS:
            value = _value(step, field_name)
            found = SLOT.fullmatch(str(value or ""))
            if found and found.group(1) in slots and len(slots[found.group(1)]) < 2:
                steps[index] = _set_noun(step, field_name, slots.pop(found.group(1))[0])
    if question is not None:
        question.keep = _fill_slots(question.keep, steps)
        question.other = _fill_slots(question.other, steps)
    return Unified(steps, slots, question)


def _fill_slots(candidate: list, steps: list) -> list:
    out = []
    for index, step in enumerate(candidate):
        step = json.loads(json.dumps(step))
        if index < len(steps) and kind_of(step) == kind_of(steps[index]):
            for field_name in SLOT_FIELDS:
                value = _value(steps[index], field_name)
                if SLOT.fullmatch(str(value or "")):
                    step = _set_noun(step, field_name, value)
        out.append(step)
    return out


def _with_manner(step: dict, values: dict) -> dict:
    out = json.loads(json.dumps(step))
    target = out["request"] if out.get("do") == "request" else out
    for key in ("way", "degrees", "metres", "speed", "seconds", "repeat", "amount", "expression"):
        target.pop(key, None)
    target.update(values)
    return out


def sig_core(step: dict) -> str:
    if step.get("do") == "request":
        request = step.get("request") or {}
        return f"request:{request.get('kind')}"
    return str(step.get("do"))


def answer_question(question: Question, said: str) -> list:
    words = f" {said.lower()} "
    if question.kind == "manner":
        second = question.words.get("second") or {}
        first = question.words.get("first") or {}
        for key in ("way", "speed", "expression"):
            if second.get(key) and f" {second[key]} " in words:
                return question.other
            if first.get(key) and f" {first[key]} " in words:
                return question.keep
        if re.search(r"\b(?:no|nope|nah|not really|doesn't matter|does not matter|either|any)\b", words):
            return question.keep
        if re.search(r"\b(?:second|last|latest|new|other)\b", words):
            return question.other
        return question.other
    if re.search(r"\b(?:no|nope|nah|not|never|don't|do not)\b", words):
        return question.other
    return question.keep


def readback(entry: Entry, named: Callable[[str], str] = lambda text: text) -> str:
    kind = entry.kind
    name = named(shown_name(entry))
    values = ""
    if entry.slots:
        parts = []
        for slot, items in entry.slots.items():
            shown = [named(v) for v in items[:4]]
            parts.append(" and ".join(f"the {v}" for v in shown) if len(shown) <= 2 else ", ".join(f"the {v}" for v in shown[:-1]) + f" and the {shown[-1]}")
        values = f" ({'; '.join(parts)} so far)"
    if kind == "move":
        return f"Okay, I've learned {_the(name)}: I {named(said_steps(entry.steps))}."
    if kind == "procedure":
        return f"Okay, I've learned {_the(name)}: I {named(said_steps(entry.steps))}{values}."
    if kind == "route":
        through = [r for r in entry.rooms if r]
        metres = max(1, round(_length(entry.points)))
        middle = f" through the {' and the '.join(through[:-1])}" if len(through) > 1 else ""
        return f"Okay, I've learned the way to the {name}{middle}, about {metres} {'metre' if metres == 1 else 'metres'}."
    if kind == "concept":
        line = f" ({entry.line})" if entry.line else ""
        return f"Okay, I know what {name} looks like now{line}."
    if kind == "word":
        return f"Okay: when you say {name}, I'll {named(entry.words)}."
    if kind == "way":
        return f"Okay: when you {_event_words(entry.trigger, True)}, I'll {named(said_steps(entry.steps))}."
    if kind == "habit":
        return f"Okay: whenever {_event_words(entry.trigger, False)}, I'll {named(said_steps(entry.steps))}."
    if kind == "spot":
        return f"Okay, this is the {name}" + (f": {entry.about}." if entry.about else ".")
    if kind == "game":
        return f"Okay, I've learned {_the(name)}."
    return f"Okay, I've learned {_the(name)}."


def _the(name: str) -> str:
    first = name.split(" ", 1)[0] if name else ""
    if first in ("check", "go", "say", "look", "find", "take", "do", "make", "turn", "spin", "come", "greet", "wave", "tell", "fetch", "get", "show", "play", "wake", "feed", "put", "water"):
        return f"how to {name}"
    return f"the {name}" if not name.startswith(("the ", "my ", "your ", "a ")) else name


def _length(points) -> float:
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
    return total


def _event_words(trigger: dict, own: bool) -> str:
    event = trigger.get("event")
    thing = str(trigger.get("thing") or "").replace("_", " ")
    if event == "arrives":
        return "come home" if own else f"{trigger.get('label') or 'someone'} comes home"
    if event == "leaves":
        return "go out" if own else f"{trigger.get('label') or 'someone'} goes out"
    if event == "sound":
        return f"the {thing} {'rings' if thing in ('doorbell', 'phone') else 'goes'}" if thing else "I hear that sound"
    if event == "seen":
        return f"I see the {thing}" if thing else "I see them"
    return trigger.get("words") or "that happens"


def faithful(made_steps: list, slots: dict, examples: list[list[dict]]) -> list[str]:
    shown = [join(list(example)) for example in examples]
    options = [made_steps]
    if slots:
        options = []
        for pick in range(max(len(v) for v in slots.values())):
            text = json.dumps(made_steps)
            for slot, items in slots.items():
                text = text.replace("{" + slot + "}", items[min(pick, len(items) - 1)])
            options.append(json.loads(text))
    options = [join([blockish(step) for step in option]) for option in options]
    shapes = {tuple(kind_of(step) for step in example) for example in shown}
    loose_manner = set()
    if len(shapes) == 1 and len(shown) > 1:
        for position in range(len(shown[0])):
            if len({json.dumps(manner(example[position]), sort_keys=True) for example in shown}) > 1:
                loose_manner.add(position)
    matched = [any(_same_steps(option, example, loose_manner) for option in options) for example in shown]
    if len(shapes) > 1:
        return [] if any(matched) else ["the steps don't match any example"]
    return [f"the steps don't match what example {number} showed" for number, ok in enumerate(matched, 1) if not ok]


def _same_steps(made: list, example: list, loose_manner: set) -> bool:
    if len(made) != len(example):
        return False
    for position, (a, b) in enumerate(zip(made, example)):
        if noun_key(a) != noun_key(b):
            return False
        if position not in loose_manner and _manner_key(a) != _manner_key(b):
            return False
    return True


def _manner_key(step: dict) -> str:
    found = manner(step)
    return json.dumps({k: found[k] for k in ("way", "expression") if k in found}, sort_keys=True)


def noun_key(step: dict) -> str:
    if step.get("do") == "request":
        request = step.get("request") or {}
        return "|".join(str(request.get(k) or "") for k in ("kind", "place", "thing", "who", "to"))
    return "|".join(str(step.get(k) or "") for k in ("do", "place", "thing", "who", "to", "text", "subject"))


def loose(step: dict) -> str:
    return noun_key(step) + "|" + _manner_key(step)


def blockish(step: dict) -> dict:
    if step.get("do") != "request":
        return step
    data = step.get("request") or {}
    if data.get("kind") not in ("turn", "move", "back_off") or any(key in data for key in ("then", "when", "on", "while", "until", "if")):
        return step
    try:
        request = from_dict(data)
    except (BadRequest, ValueError):
        return step
    from .record import card_of

    card = card_of(request)
    if card is None:
        return step
    if request.repeat > 1:
        card["repeat"] = min(4, request.repeat)
    return card


class Inducer:
    def __init__(self, mind_of: Callable[[], object | None], name: str = "Pebble", wait_s: float = TEACH_WAIT_S, monotonic: Callable[[], float] = time.monotonic, sleep=None):
        self.mind_of = mind_of
        self.name = name
        self.wait_s = wait_s
        self.monotonic = monotonic
        self.sleep = sleep or asyncio.sleep
        self.usage: tuple = (None, None)

    def ready(self) -> bool:
        try:
            return self.mind_of() is not None
        except Exception:
            return False

    def messages(self, record_text: str, card: Card, known: list = ()) -> Prompt:
        system = TEACH_GUIDE.format(name=self.name) + "\n\n" + card.text()
        out = [{"role": "system", "content": system}]
        ask, reply = TEACH_EXAMPLE
        out.append({"role": "user", "content": ask})
        out.append({"role": "assistant", "content": json.dumps(reply, separators=(",", ":"))})
        lines, shown, used = [], [], 0
        for entry in known:
            item = f"{entry.name} ({entry.kind}): {entry.about[:80]}"
            if used + len(item) > KNOWN_CHARS:
                break
            shown.append(item)
            used += len(item)
        known_line = ("Things you already know how to do (only for reference; this one is new): " + "; ".join(shown)) if shown else ""
        if known_line:
            lines.append(known_line)
        lines.append(record_text)
        lines.append(WORK)
        out.append({"role": "user", "content": "\n".join(lines)})
        last = len(out) - 1
        parts = [(GUIDE, 0, system), (WORDS, last, record_text)]
        if known_line:
            parts.append((MATCHED, last, known_line))
        return Prompt(out, TEACH, parts)

    async def ask(self, record_text: str, card: Card, known: list = (), seed: int | None = None, kinds: tuple = ()) -> tuple[dict | None, int, str]:
        mind = self.mind_of()
        if mind is None:
            return None, 0, "no model"
        prompt = self.messages(record_text, card, known)
        options = CallOptions("steady", 0.3, 0.9, 0.1, seed=seed, grammar=teach_grammar(card, kinds))
        calls = 0
        for _ in range(RETRIES):
            calls += 1
            try:
                reply = await asyncio.wait_for(mind.chat(prompt, purpose="teach", max_tokens=TEACH_TOKENS, **options_kwargs(options)), self.wait_s)
            except MindInterrupted:
                await self.sleep(2.0)
                continue
            except (MindUnavailable, asyncio.TimeoutError) as error:
                return None, calls, str(error) or "timed out"
            self.usage = (reply.prompt_tokens, reply.completion_tokens)
            data = parse(reply.text or "")
            if data is None:
                return None, calls, "the reply was not JSON"
            return data, calls, ""
        return None, calls, "put off"


def parse(text: str) -> dict | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def checked_steps(raw, card: Card, slots: dict) -> tuple[list, list]:
    if not isinstance(raw, list) or not raw:
        return [], ["there are no steps"]
    out, problems = [], []
    for number, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            problems.append(f"step {number} is not an object")
            continue
        if item.get("do") == "request":
            data = item.get("request")
            if not isinstance(data, dict):
                problems.append(f"step {number} has no request")
                continue
            try:
                filled = json.loads(SLOT.sub(lambda m: (slots.get(m.group(1)) or ["x"])[0], json.dumps(data)))
                from_dict(filled)
            except (BadRequest, ValueError) as error:
                problems.append(f"step {number}: {error}")
                continue
            for value in data.values():
                for found in SLOT.finditer(str(value)):
                    if found.group(1) not in slots:
                        problems.append(f"step {number} uses {found.group(0)}, which has no values")
            out.append(blockish({"do": "request", "request": dict(data)}))
            continue
        if item.get("do") not in CARD_KINDS and item.get("do") not in card.names:
            problems.append(f"step {number}: {item.get('do')!r} is not a block")
            continue
        holes = {k: v for k, v in item.items() if isinstance(v, str) and SLOT.search(v)}
        test = dict(item)
        for key, value in holes.items():
            for found in SLOT.finditer(value):
                if found.group(1) not in slots:
                    problems.append(f"step {number} uses {found.group(0)}, which has no values")
            test[key] = SLOT.sub(lambda m: (slots.get(m.group(1)) or ["x"])[0], value)
        step, problem = card.clean(test)
        if problem:
            problems.append(f"step {number}: {problem}")
            continue
        step.update(holes)
        out.append(step)
    return out, problems


def made_from(data: dict, card: Card, examples: list[list[dict]], seen_values: set) -> Made:
    problems = []
    kind = str(data.get("kind") or "").strip().lower()
    if kind not in MADE_KINDS:
        problems.append(f"{kind!r} is not a kind")
    slots = {}
    for slot, values in (data.get("slots") or {}).items() if isinstance(data.get("slots"), dict) else ():
        name = re.sub(r"[^a-z_]", "", str(slot).lower())[:16]
        items = [" ".join(str(v).lower().split())[:30] for v in values or [] if str(v).strip()] if isinstance(values, list) else []
        if not name or not items:
            problems.append(f"the slot {slot!r} has no values")
            continue
        unseen = [v for v in items if v not in seen_values]
        if unseen:
            problems.append(f"the slot {name} has values nobody showed ({', '.join(unseen)})")
            continue
        slots[name] = items
    steps, step_problems = checked_steps(data.get("steps"), card, slots)
    problems += step_problems
    if steps and not step_problems:
        problems += faithful(steps, slots, examples)
    aliases = [" ".join(str(a).lower().split())[:NAME_MOST] for a in (data.get("aliases") or []) if isinstance(a, str) and a.strip()][:ALIASES_MOST]
    return Made(kind, " ".join(str(data.get("name") or "").lower().split())[:NAME_MOST], steps, slots, aliases, " ".join(str(data.get("about") or "").split())[:ABOUT_MOST], "model", problems=problems)


def values_seen(examples: list[list[dict]]) -> set:
    out = set()
    for example in examples:
        for step in example:
            for value in nouns(step).values():
                out.add(str(value).lower())
    return out


def plain_made(examples: list[list[dict]], name: str) -> tuple[Made, Question | None]:
    unified = unify(examples)
    steps = unified.steps
    kind = "move" if is_move(steps) else "procedure"
    return Made(kind, name, steps, unified.slots), unified.question
