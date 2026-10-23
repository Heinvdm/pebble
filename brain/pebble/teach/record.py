import json
import math
from dataclasses import dataclass, field

from ..activities.card import REPEAT_MOST, step_words
from ..understand.request import BadRequest, Request, from_dict

RECORD_CHARS = 1700
WORDS_CHARS = 360
WORDS_MOST = 12
SEEN_MOST = 12
TRAIL_GAP_M = 0.25
TRAIL_MOST = 240
STEPS_MOST = 12
MOVES_MOST = 8
TURN_LEAST = 3.0
ROLL_LEAST = 0.02
TURN_MOST = 720.0
ROLL_MOST = 1.0
BACK_MOST = 0.2
CARD_KINDS = frozenset({"turn", "move", "wiggle", "back_off", "tilt", "face", "say", "wait", "draw"})
GOES = frozenset({"come", "look", "go_to_place", "go_to_thing", "find", "push"})
MANNER = ("way", "degrees", "metres", "speed", "seconds", "repeat", "expression")
NOUNS = ("place", "thing", "who", "to", "text", "subject", "until_seen", "route")


@dataclass
class Shown:
    step: dict
    at: float
    way: str


@dataclass
class Record:
    teacher: str
    tier: str
    started: float
    intent: str = ""
    name: str = ""
    items: list = field(default_factory=list)
    trail: list = field(default_factory=list)
    seen: list = field(default_factory=list)
    words: list = field(default_factory=list)
    examples: list = field(default_factory=list)
    ways: list = field(default_factory=list)
    answers: list = field(default_factory=list)

    def add(self, step: dict, at: float, way: str) -> None:
        self.items.append(Shown(dict(step), round(max(0.0, at - self.started), 1), way))
        if way not in self.ways:
            self.ways.append(way)

    def undo(self) -> Shown | None:
        if self.items:
            return self.items.pop()
        if self.examples:
            self.examples.pop()
        return None

    def clear(self) -> None:
        self.items.clear()
        self.trail.clear()
        self.examples.clear()

    def heard(self, text: str) -> None:
        words = " ".join(str(text or "").split())[:120]
        if words:
            self.words.append(words)
            del self.words[:-WORDS_MOST]

    def saw(self, labels) -> None:
        for label in labels:
            if label and label not in self.seen:
                self.seen.append(label)
        del self.seen[:-SEEN_MOST]

    def walked(self, x: float, y: float, room: str | None, force: bool = False) -> bool:
        if self.trail:
            last = self.trail[-1]
            gap = math.hypot(x - last[0], y - last[1])
            if gap < TRAIL_GAP_M and not (force and gap >= 0.03):
                return False
        self.trail.append([round(x, 2), round(y, 2), room or ""])
        del self.trail[:-TRAIL_MOST]
        return True

    def steps(self) -> list[dict]:
        return join([item.step for item in self.items], [item.way for item in self.items])

    def forget_words(self) -> None:
        self.words.clear()

    def text(self, most: int = RECORD_CHARS, examples: list | None = None) -> str:
        lines = [f"Taught by {self.teacher} ({self.tier}). Ways shown: {', '.join(self.ways) or 'none yet'}."]
        if self.intent:
            lines.append(f'They started with: "{self.intent[:80]}"')
        if self.name:
            lines.append(f'They called it: "{self.name}"')
        if examples and len(examples) > 1:
            for count, example in enumerate(examples, 1):
                lines.append(f"Example {count}:")
                for number, step in enumerate(example, 1):
                    lines.append(f"{number}. {json.dumps(step, separators=(',', ':'))}")
        else:
            for number, item in enumerate(self.items, 1):
                lines.append(f"{number}. ({item.at:g}s, {item.way}) {json.dumps(item.step, separators=(',', ':'))}")
        if self.trail:
            rooms = [room for _, _, room in self.trail if room]
            passed = list(dict.fromkeys(rooms))
            lines.append(f"Led along {len(self.trail)} map points, {length(self.trail):.1f} m" + (f", through {', '.join(passed)}" if passed else "") + ".")
        if self.examples:
            for number, example in enumerate(self.examples, 1):
                said = example.get("said") or ""
                lines.append(f"Example {number}: {'yes' if example.get('yes', True) else 'not'} {example.get('name', '')}" + (f', looked like "{said}"' if said else ""))
        if self.seen:
            lines.append(f"Seen: {', '.join(self.seen)}.")
        if self.words:
            shown, used = [], 0
            for words in reversed(self.words):
                if used + len(words) > WORDS_CHARS:
                    break
                shown.insert(0, f'"{words}"')
                used += len(words)
            if shown:
                lines.append("Their words: " + " ".join(shown))
        text = "\n".join(lines)
        while len(text) > most and len(lines) > 2:
            lines.pop(-2 if lines[-1].startswith("Their words") else -1)
            text = "\n".join(lines)
        return text[:most]


def length(points) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def _num(value: float):
    value = round(float(value), 2)
    return int(value) if value == int(value) else value


def _round_to(value: float, step: float) -> float:
    return round(round(float(value) / step) * step, 2)


def card_of(request: Request) -> dict | None:
    kind = request.kind
    if request.then or request.when is not None or request.on is not None or request.while_ is not None or request.until_on is not None or request.until:
        return None
    if kind == "turn":
        step = {"do": "turn", "way": request.way or "left"}
        if request.degrees:
            step["degrees"] = _num(request.degrees)
        elif request.way == "around":
            step["degrees"] = 180
        else:
            step["degrees"] = 45 if request.amount == "little" else 90
        if request.speed:
            step["speed"] = request.speed
        return step
    if kind == "move":
        way = "back" if request.way == "back" else "forward"
        metres = request.metres or (0.1 if request.amount == "little" else (0.5 if request.amount == "lot" else 0.25))
        step = {"do": "move", "way": way, "metres": _num(min(BACK_MOST if way == "back" else ROLL_MOST, metres))}
        if request.speed:
            step["speed"] = request.speed
        return step
    if kind == "back_off":
        return {"do": "back_off"}
    if kind == "wait" and request.seconds and request.seconds <= 30:
        return {"do": "wait", "seconds": _num(request.seconds)}
    if kind == "say_to" and request.who in ("", "me") and request.text:
        return {"do": "say", "text": request.text[:60]}
    return None


def step_of(request: Request) -> dict:
    card = card_of(request)
    if card is not None:
        if request.repeat > 1:
            card["repeat"] = min(REPEAT_MOST, request.repeat)
        return card
    return {"do": "request", "request": request.as_dict()}


def request_of(step: dict) -> Request | None:
    if step.get("do") != "request":
        return None
    try:
        return from_dict(step.get("request") or {})
    except BadRequest:
        return None


def join(steps: list[dict], ways: list | None = None) -> list[dict]:
    out: list[dict] = []
    joinable: list[bool] = []
    for index, raw in enumerate(steps):
        step = dict(raw)
        name = step.get("do")
        driven = bool(ways is not None and index < len(ways) and ways[index] == "drive")
        last = out[-1] if out else None
        merge = driven and last is not None and joinable[-1]
        if name == "turn" and step.get("way") in ("left", "right"):
            degrees = float(step.get("degrees") or 0.0) * max(1, int(step.get("repeat", 1)))
            if merge and last.get("do") == "turn" and last.get("way") in ("left", "right") and "repeat" not in last:
                signed = (float(last.get("degrees") or 0.0) if last["way"] == "left" else -float(last.get("degrees") or 0.0)) + (degrees if step["way"] == "left" else -degrees)
                out.pop()
                joinable.pop()
                if abs(signed) >= TURN_LEAST:
                    merged = {"do": "turn", "way": "left" if signed > 0 else "right", "degrees": _num(min(TURN_MOST, max(5.0, _round_to(abs(signed), 5.0))))}
                    if last.get("speed") or step.get("speed"):
                        merged["speed"] = step.get("speed") or last.get("speed")
                    out.append(merged)
                    joinable.append(True)
                continue
            if driven and degrees < TURN_LEAST:
                continue
            if driven:
                step.pop("repeat", None)
                step["degrees"] = _num(min(TURN_MOST, max(5.0, _round_to(degrees, 5.0))))
            out.append(step)
            joinable.append(driven)
            continue
        if name == "move":
            metres = float(step.get("metres") or 0.0)
            top = BACK_MOST if step.get("way") == "back" else ROLL_MOST
            if merge and last.get("do") == "move" and last.get("way") == step.get("way") and "repeat" not in last and "repeat" not in step:
                last["metres"] = _num(min(top, _round_to(float(last.get("metres") or 0.0) + metres, 0.05)))
                if step.get("speed"):
                    last["speed"] = step["speed"]
                continue
            if driven and metres < ROLL_LEAST:
                continue
            step["metres"] = _num(min(top, max(0.05, _round_to(metres, 0.05)))) if driven else _num(min(top, metres))
            out.append(step)
            joinable.append(driven)
            continue
        if last is not None and _same(last, step) and name in CARD_KINDS and name not in ("say", "wait"):
            last["repeat"] = min(REPEAT_MOST, int(last.get("repeat", 1)) + max(1, int(step.get("repeat", 1))))
            continue
        out.append(step)
        joinable.append(driven)
    return out


def _same(a: dict, b: dict) -> bool:
    return {k: v for k, v in a.items() if k != "repeat"} == {k: v for k, v in b.items() if k != "repeat"}


def sig(step: dict) -> str:
    name = step.get("do")
    if name == "request":
        request = request_of(step)
        if request is None:
            return "request ?"
        return " ".join(part for part in (request.kind, request.way, request.place or request.who or request.thing, request.text[:30]) if part)
    if name == "route":
        return f"route {step.get('route', '')}"
    words = step_words(step)
    if step.get("repeat", 1) > 1:
        words += f" x{step['repeat']}"
    if name == "turn" and step.get("degrees"):
        words += f" {_num(step['degrees'])}"
    return words


def is_move(steps: list[dict]) -> bool:
    return bool(steps) and all(step.get("do") in CARD_KINDS for step in steps)


def nouns(step: dict) -> dict:
    if step.get("do") == "request":
        request = step.get("request") or {}
        return {k: v for k, v in request.items() if k in ("place", "thing", "who", "to", "text", "name") and v}
    return {k: v for k, v in step.items() if k in NOUNS and v}


def manner(step: dict) -> dict:
    if step.get("do") == "request":
        request = step.get("request") or {}
        return {k: v for k, v in request.items() if k in ("way", "degrees", "metres", "speed", "seconds", "repeat", "amount")}
    return {k: v for k, v in step.items() if k in MANNER}


def kind_of(step: dict) -> str:
    if step.get("do") == "request":
        return "request:" + str((step.get("request") or {}).get("kind"))
    return str(step.get("do"))


def sample(started: float = 0.0) -> "Record":
    record = Record("Ina", "trusted", started, intent="let me show you how to check the back door", name="door check")
    shown = (
        ("said", {"do": "request", "request": {"kind": "go_to_place", "place": "hallway"}}),
        ("said", {"do": "request", "request": {"kind": "go_to_thing", "thing": "back door"}}),
        ("said", {"do": "request", "request": {"kind": "look", "thing": "handle"}}),
        ("drive", {"do": "turn", "way": "left", "degrees": 40}),
        ("drive", {"do": "turn", "way": "left", "degrees": 45}),
        ("drive", {"do": "tilt", "way": "up", "degrees": 15}),
        ("said", {"do": "request", "request": {"kind": "come", "who": "me"}}),
        ("said", {"do": "say", "text": "the back door is locked"}),
    )
    for number, (way, step) in enumerate(shown):
        record.add(step, started + 4.0 * (number + 1), way)
    record.saw(["door", "handle", "mat", "shoe", "umbrella"])
    for words in ("let me show you how to check the back door", "go to the hallway", "go to the back door", "look at the handle", "come back to me", "say the back door is locked", "that's it, call it the door check"):
        record.heard(words)
    return record
