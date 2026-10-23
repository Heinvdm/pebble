import json
import re
from dataclasses import dataclass

from ..respect import is_alive
from ..seams.face import FACES
from ..things.words import canonical, is_animal
from ..understand.request import Request

PLAN_MOST = 8
REPEAT_MOST = 4
SAY_MOST = 60
DRAW_MOST = 40
THINK_CHARS = 700
TEXT_CHARS = "a-z' -"
TEXT_MOST = 24
WORDS_CHARS = "a-zA-Z0-9' ,.?!-"
THINK_SET = "a-zA-Z0-9' ,.?!;:()/+-"
TILT_MOST = 40.0
BACK_MOST = 0.2
MOVE = "moves"
SIGHT = "sight"
PLACES = "places"
HEAD = "head"
SCREEN = "screen"
DRAWS = "draws"


@dataclass(frozen=True)
class Field:
    name: str
    kind: str
    low: float = 0.0
    high: float = 0.0
    choices: tuple = ()
    about: str = ""


@dataclass(frozen=True)
class Block:
    name: str
    about: str
    fields: tuple = ()
    needs: str = ""
    becomes: str = ""


BLOCKS = (
    Block("turn", "turn on the spot", (Field("way", "word", choices=("left", "right", "around")), Field("degrees", "number", 10.0, 720.0, about="360 is a full spin"), Field("speed", "word", choices=("slow", "quick"))), MOVE, "turn"),
    Block("move", "roll a little", (Field("way", "word", choices=("forward", "back")), Field("metres", "number", 0.05, 1.0, about="back at most 0.2"), Field("speed", "word", choices=("slow", "quick"))), MOVE, "move"),
    Block("wiggle", "a quick wiggle on the spot", (), MOVE, ""),
    Block("back_off", "back away a little", (), MOVE, "back_off"),
    Block("tilt", "tilt the head with the face", (Field("way", "word", choices=("up", "down")), Field("degrees", "number", 5.0, TILT_MOST)), HEAD, ""),
    Block("face", "show a face", (Field("expression", "word", choices=FACES),), SCREEN, ""),
    Block("draw", "draw a small picture on the face screen", (Field("subject", "words", high=DRAW_MOST),), DRAWS, ""),
    Block("say", "say a few words", (Field("text", "words", high=SAY_MOST),), "", ""),
    Block("wait", "keep still", (Field("seconds", "number", 1.0, 30.0), Field("until_seen", "text", about="a thing or person to wait for")), "", ""),
    Block("come", "go to a person", (Field("who", "who"),), MOVE + SIGHT, "come"),
    Block("look", "turn to look at a person or thing", (Field("who", "who"), Field("thing", "text"), Field("seconds", "number", 1.0, 20.0)), SIGHT, "look"),
    Block("go_to_place", "go to a room", (Field("place", "place"),), MOVE + PLACES, "go_to_place"),
    Block("go_to_thing", "go up to a thing", (Field("thing", "text"),), MOVE + SIGHT, "go_to_thing"),
    Block("find", "look around for a thing", (Field("thing", "text"),), MOVE + SIGHT, "find"),
    Block("push", "nudge a toy on the floor towards a person", (Field("thing", "text"), Field("to", "who")), MOVE + SIGHT, "play"),
)
BY_NAME = {block.name: block for block in BLOCKS}
MOVES = frozenset(block.name for block in BLOCKS if MOVE in block.needs)
EXPRESSIVE = frozenset({"turn", "move", "wiggle", "tilt", "face", "draw", "say", "push", "come", "look", "go_to_place", "go_to_thing", "find", "back_off"})


@dataclass(frozen=True)
class Body:
    wheels: bool = True
    eyes: bool = True
    head: bool = True
    screen: bool = True
    draws: bool = False
    places: tuple = ()
    people: tuple = ()


def _has(body: Body, needs: str) -> bool:
    if MOVE in needs and not body.wheels:
        return False
    if SIGHT in needs and not body.eyes:
        return False
    if PLACES in needs and not body.places:
        return False
    if needs == HEAD and not body.head:
        return False
    if needs == SCREEN and not body.screen:
        return False
    if needs == DRAWS and not body.draws:
        return False
    return True


def _num(value: float):
    value = round(float(value), 2)
    return int(value) if value == int(value) else value


def _words(words) -> str:
    return " | ".join(f'"\\"{w}\\""' for w in words)


def _key(name: str) -> str:
    return f'"\\"{name}\\":" ws'


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:48]


class Card:
    def __init__(self, body: Body):
        self.body = body
        self.places = tuple(dict.fromkeys(p.strip().lower() for p in body.places if p and p.strip()))
        self.people = tuple(dict.fromkeys(["me"] + [p.strip().lower() for p in body.people if p and p.strip() and p.strip().lower() != "me"]))
        self.blocks = tuple(block for block in BLOCKS if _has(body, block.needs))
        self.names = frozenset(block.name for block in self.blocks)

    def has(self, name: str) -> bool:
        return name in self.names

    def text(self) -> str:
        lines = [f"Blocks (each step is one block; any step may have repeat 2 to {REPEAT_MOST}):"]
        for block in self.blocks:
            parts = []
            for field in block.fields:
                if field.kind == "word":
                    parts.append(f"{field.name} {' or '.join(field.choices) if len(field.choices) <= 3 else ', '.join(field.choices)}")
                elif field.kind == "number":
                    parts.append(f"{field.name} {_num(field.low)} to {_num(field.high)}" + (f" ({field.about})" if field.about else ""))
                elif field.kind == "who":
                    parts.append(f"{field.name} ({', '.join(self.people)})")
                elif field.kind == "place":
                    parts.append(f"{field.name} ({', '.join(self.places)})")
                elif field.kind == "words":
                    parts.append(f"{field.name}, at most {int(field.high)} letters")
                else:
                    parts.append(field.name + (f", {field.about}" if field.about else ""))
            lines.append(f"{block.name}: {block.about}" + (f"; {'; '.join(parts)}" if parts else ""))
        return "\n".join(lines)

    def grammar(self) -> str:
        rules = {
            "root": '"{" ws (cant | plan) ws "}"',
            "cant": f'{_key("cant")} words',
            "plan": f'{_key("think")} think "," ws {_key("steps")} steps',
            "steps": f'"[" ws step (ws "," ws step){{0,{PLAN_MOST - 1}}} ws "]"',
            "step": " | ".join(f"b{index}" for index in range(len(self.blocks))),
            "think": '"\\"" [' + THINK_SET + "]{0," + str(THINK_CHARS) + '} "\\""',
            "text": '"\\"" [' + TEXT_CHARS + "]{1," + str(TEXT_MOST) + '} "\\""',
            "words": '"\\"" [' + WORDS_CHARS + "]{1," + str(SAY_MOST) + '} "\\""',
            "num": '[0-9]{1,3} ("." [0-9]{1,2})?',
            "repeat": "[2-" + str(REPEAT_MOST) + "]",
            "ws": '" "?',
            "who": _words(self.people),
        }
        if self.places:
            rules["place"] = _words(self.places)
        for index, block in enumerate(self.blocks):
            parts = [f'"{{" ws {_key("do")} "\\"{block.name}\\""']
            for field in block.fields:
                if field.kind == "word":
                    value = _words(field.choices)
                    value = f"({value})"
                elif field.kind == "number":
                    value = "num"
                else:
                    value = {"who": "who", "place": "place", "text": "text", "words": "words"}[field.kind]
                parts.append(f'("," ws {_key(field.name)} {value})?')
            parts.append(f'("," ws {_key("repeat")} repeat)?')
            parts.append('ws "}"')
            rules[f"b{index}"] = " ".join(parts)
        return "\n".join(f"{name} ::= {body}" for name, body in rules.items()) + "\n"

    def check(self, steps) -> tuple[list[dict], list[str]]:
        if not isinstance(steps, list) or not steps:
            return [], ["the plan has no steps"]
        out, errors = [], []
        if len(steps) > PLAN_MOST:
            errors.append(f"the plan has {len(steps)} steps; at most {PLAN_MOST}")
            steps = steps[:PLAN_MOST]
        for index, raw in enumerate(steps, 1):
            step, problem = self.clean(raw)
            if problem:
                errors.append(f"step {index}: {problem}")
            elif step is not None:
                out.append(step)
        return out, errors

    def clean(self, raw) -> tuple[dict | None, str]:
        if not isinstance(raw, dict):
            return None, "a step is an object"
        name = str(raw.get("do") or "").strip().lower()
        block = BY_NAME.get(name)
        if block is None or name not in self.names:
            return None, f"{name or 'that'} is not a block this body has"
        step = {"do": name}
        for field in block.fields:
            value = raw.get(field.name)
            if value is None or value == "":
                continue
            if field.kind == "word":
                word = str(value).strip().lower()
                if word not in field.choices:
                    return None, f"{field.name} {word!r} is not one of {', '.join(field.choices)}"
                step[field.name] = word
            elif field.kind == "number":
                try:
                    number = abs(float(value))
                except (TypeError, ValueError):
                    return None, f"{field.name} must be a number"
                step[field.name] = _num(max(field.low, min(field.high, number)))
            elif field.kind == "who":
                who = str(value).strip().lower()
                if who not in self.people:
                    return None, f"{who!r} is not someone you know ({', '.join(self.people)})"
                step[field.name] = who
            elif field.kind == "place":
                place = str(value).strip().lower()
                if place not in self.places:
                    return None, f"{place!r} is not a place you know ({', '.join(self.places)})"
                step[field.name] = place
            else:
                most = int(field.high) if field.high else TEXT_MOST
                text = " ".join(str(value).split())[:most]
                step[field.name] = text if field.kind == "words" else text.lower()
        problem = self._sense(step)
        if problem:
            return None, problem
        repeat = raw.get("repeat")
        if repeat not in (None, "", 1, "1"):
            try:
                times = int(round(float(repeat)))
            except (TypeError, ValueError):
                return None, "repeat must be a number"
            if times > 1:
                step["repeat"] = min(REPEAT_MOST, times)
        return step, ""

    def _sense(self, step: dict) -> str:
        name = step["do"]
        if name == "move" and step.get("way") == "back" and float(step.get("metres") or 0.0) > BACK_MOST:
            step["metres"] = BACK_MOST
        if name == "say" and not step.get("text"):
            return "say needs the words to say"
        if name == "draw" and not step.get("subject"):
            return "draw needs what to draw"
        if name == "face" and not step.get("expression"):
            return "face needs an expression"
        if name in ("go_to_thing", "find") and not step.get("thing"):
            return f"{name} needs a thing"
        if name == "go_to_place" and not step.get("place"):
            return "go_to_place needs a place"
        if name == "come" and not step.get("who"):
            step["who"] = "me"
        if name == "look" and not step.get("who") and not step.get("thing"):
            step["who"] = "me"
        if name == "push":
            thing = step.get("thing") or ""
            if not thing:
                return "push needs a toy"
            if is_alive(thing) or is_animal(canonical(thing) or thing):
                return f"{thing} is alive, and you never push anything alive"
            if not step.get("to"):
                step["to"] = "me"
        if name == "tilt" and not step.get("way"):
            step["way"] = "down"
        if name == "turn" and not step.get("way"):
            step["way"] = "around" if float(step.get("degrees") or 0.0) >= 180.0 else "left"
        if name == "move" and not step.get("way"):
            step["way"] = "forward"
        return ""


def request_of(step: dict) -> Request | None:
    name = step.get("do")
    block = BY_NAME.get(name)
    if block is None or not block.becomes:
        return None
    if name == "push":
        return Request("play", thing=step.get("thing", ""), to=step.get("to", "me"))
    values = {key: step[key] for key in ("way", "degrees", "speed", "metres", "who", "thing", "place", "seconds") if key in step}
    if name == "turn" and "degrees" not in values and values.get("way") == "around":
        values["degrees"] = 360.0
    return Request(block.becomes, **values)


def key(steps) -> str:
    return json.dumps([dict(sorted(step.items())) for step in steps], sort_keys=True, separators=(",", ":"))


def said(steps) -> str:
    out = []
    for step in steps:
        out.append(step_words(step) + (f" {_times(step['repeat'])}" if step.get("repeat", 1) > 1 else ""))
    return ", ".join(part for part in out if part)


def _times(count: int) -> str:
    return "twice" if count == 2 else f"{count} times"


def step_words(step: dict) -> str:
    name = step.get("do")
    who = step.get("who") or ""
    whom = "you" if who in ("", "me") else who.title()
    if name == "turn":
        degrees = float(step.get("degrees") or 0.0)
        if step.get("way") == "around" or degrees >= 300:
            return "spin round" if degrees in (0.0, 360.0) else f"turn {_num(degrees)} degrees"
        return f"turn {step.get('way', 'left')}" + (f" {_num(degrees)} degrees" if degrees else "")
    if name == "move":
        return f"roll {step.get('way', 'forward')}"
    if name == "wiggle":
        return "wiggle"
    if name == "back_off":
        return "back away"
    if name == "tilt":
        return f"tilt my head {step.get('way', 'down')}"
    if name == "face":
        return f"make a {step.get('expression', 'happy')} face"
    if name == "draw":
        return f"draw {step.get('subject', 'something')}"
    if name == "say":
        return f"say \"{step.get('text', '')}\""
    if name == "wait":
        if step.get("until_seen"):
            return f"wait for the {step['until_seen']}"
        return "keep still"
    if name == "come":
        return f"come to {whom}"
    if name == "look":
        return f"look at the {step['thing']}" if step.get("thing") else f"look at {whom}"
    if name == "go_to_place":
        return f"go to the {step.get('place', '')}"
    if name == "go_to_thing":
        return f"go to the {step.get('thing', '')}"
    if name == "find":
        return f"look for the {step.get('thing', '')}"
    if name == "push":
        to = step.get("to") or ""
        return f"push the {step.get('thing', '')} to {'you' if to in ('', 'me') else to.title()}"
    return name or ""


def kind_of(steps) -> str:
    return "move" if all(step.get("do") not in ("come", "look", "go_to_place", "go_to_thing", "find", "push") for step in steps) else "procedure"
