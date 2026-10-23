import datetime
import json
import math
import re
from dataclasses import dataclass, field, replace

KINDS = (
    "follow",
    "come",
    "wait",
    "look",
    "back_off",
    "go_home",
    "go_to_place",
    "go_to_thing",
    "find",
    "where_is",
    "what_is",
    "what_see",
    "sight_question",
    "where_am_i",
    "teach",
    "remember_spot",
    "go_back",
    "play",
    "turn",
    "move",
    "stop_activity",
    "adjust",
    "release",
    "find_chirp",
    "climate_round",
    "hide_seek",
    "red_light",
    "statues",
    "say_to",
    "set_rule",
    "end_rule",
    "list_rules",
    "check",
    "watch",
    "again",
    "try_new",
    "list_later",
    "cancel_later",
    "change_later",
    "if",
    "harm",
    "chat",
    "other",
)
ACTIONS = frozenset(KINDS) - {"chat", "other"}
STARTS = frozenset({"follow", "come", "wait", "look", "back_off", "go_home", "go_to_place", "go_to_thing", "find", "play", "turn", "move", "go_back", "find_chirp", "climate_round", "hide_seek", "red_light", "statues"})
MOVING = frozenset({"follow", "come", "back_off", "go_home", "go_to_place", "go_to_thing", "find", "play", "turn", "move", "go_back", "find_chirp", "climate_round", "hide_seek", "check", "watch"})
QUESTIONS = frozenset({"where_is", "what_is", "what_see", "sight_question", "where_am_i", "teach", "remember_spot"})
LATER_KINDS = frozenset({"say_to", "set_rule", "end_rule", "list_rules", "check", "watch", "again", "try_new", "list_later", "cancel_later", "change_later", "if"})
WAYS = ("left", "right", "around", "forward", "back")
AMOUNTS = ("little", "lot")
SPEEDS = ("slow", "quick")
UNTILS = ("back", "called", "seconds", "asked", "told")
OLD_CHANGES = ("slower", "faster", "closer", "further", "enough", "stay", "other_way", "keep_going")
NEW_CHANGES = ("left", "right", "again", "more", "less", "higher", "lower")
CHANGES = OLD_CHANGES + NEW_CHANGES
HARMS = ("hurt", "chase", "scare", "drive")
RULES = ("keep_out", "quiet")
REPORTS = ("back", "shout", "keep")
SCOPES = ("next", "all")
TEXT_SLOTS = ("who", "place", "thing", "name", "to")
WORD_SLOTS = {"way": WAYS, "amount": AMOUNTS, "speed": SPEEDS, "until": UNTILS, "change": CHANGES, "harm": HARMS, "rule": RULES, "report": REPORTS, "scope": SCOPES}
NUMBER_SLOTS = {"metres": (0.0, 30.0), "degrees": (0.0, 720.0), "seconds": (0.0, 7200.0)}
PARTS = ("morning", "midday", "afternoon", "evening", "night", "tonight", "before_bed")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_SETS = {"weekdays": DAYS[:5], "weekends": DAYS[5:]}
DAY_NAMES = {name: day for day in DAYS for name in (day, {"mon": "monday", "tue": "tuesday", "wed": "wednesday", "thu": "thursday", "fri": "friday", "sat": "saturday", "sun": "sunday"}[day])}
EVENTS = ("arrives", "leaves", "sound", "seen", "quiet", "done", "at", "battery", "tv_off", "cannot_tell")
STATES = ("present", "in_room", "time_between", "after", "before", "day_is", "result", "heard_lately", "seen_lately", "battery_below", "doing", "cooking", "quiet_hours", "room_quiet", "looks", "cannot_tell")
DAY_IS = DAYS + ("weekday", "weekend", "holiday", "tomorrow_holiday")
ANSWERS = ("yes", "no", "unsure")
JOINS = ("all", "any", "not")
MAX_THEN = 8
MAX_STEPS = 12
MAX_DEPTH = 3
MAX_PARTS = 4
MAX_FIRST = 4
REPEAT_MAX = 10
TEXT_MAX = 40
WORDS_MAX = 160
IN_S_MAX = 30 * 86400.0
EVERY_S = (60.0, 86400.0)
TIMES_MAX = 100
MINUTES_MAX = 1440.0
TOO_MUCH = "That's a bit much for me in one go; can we do it in parts?"
CLOCK = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?$")


class BadRequest(ValueError):
    pass


def _num(value: float):
    value = round(value, 2)
    return int(value) if value == int(value) else value


class TooMuch(BadRequest):
    pass


def _text(value, most: int = TEXT_MAX) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip().lower()[:most]


def _words(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()[:WORDS_MAX]


def _word(value, words) -> str:
    word = _text(value).replace(" ", "_").replace("-", "_")
    return word if word in words else ""


def _float(name: str, value, low: float, high: float) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, bool):
        raise BadRequest(f"{name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise BadRequest(f"{name} must be a number") from error
    if not math.isfinite(number):
        raise BadRequest(f"{name} must be finite")
    return max(low, min(high, abs(number)))


def _number(name: str, value) -> float:
    low, high = NUMBER_SLOTS[name]
    return _float(name, value, low, high)


def _whole(name: str, value, low: int, high: int) -> int:
    if value is None or value == "":
        return 0
    return int(round(max(low, min(high, _float(name, value, 0.0, float(high))))))


def clock(value) -> str:
    if value is None or value == "":
        return ""
    raw = str(value).strip().lower().replace(".", ":") if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value).strip().lower()
    match = CLOCK.match(raw)
    if match is None:
        raise BadRequest(f"{value!r} is not a time")
    hour, minute, half = int(match.group(1)), int(match.group(2) or 0), (match.group(3) or "").replace(".", "")
    if half == "pm" and hour < 12:
        hour += 12
    elif half == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        raise BadRequest(f"{value!r} is not a time")
    return f"{hour:02d}:{minute:02d}"


def _date(value) -> str:
    if value is None or value == "":
        return ""
    try:
        return datetime.date.fromisoformat(str(value).strip()).isoformat()
    except ValueError as error:
        raise BadRequest(f"{value!r} is not a date") from error


def _days(value) -> tuple:
    if value is None or value == "":
        return ()
    items = value if isinstance(value, list) else [value]
    found = set()
    for item in items:
        word = _text(item).replace(" ", "")
        if word in DAY_SETS:
            found.update(DAY_SETS[word])
        elif word in DAY_NAMES:
            found.add(DAY_NAMES[word])
        elif word.rstrip("s") in DAY_NAMES:
            found.add(DAY_NAMES[word.rstrip("s")])
        else:
            raise BadRequest(f"{item!r} is not a day")
    return tuple(day for day in DAYS if day in found)


@dataclass(frozen=True)
class When:
    in_s: float = 0.0
    at: str = ""
    part: str = ""
    date: str = ""
    days: tuple = ()
    every_weeks: int = 0
    month_day: int = 0
    every_s: float = 0.0
    from_: str = ""
    to: str = ""
    until_date: str = ""
    times: int = 0

    @property
    def repeats(self) -> bool:
        return bool(self.days or self.every_weeks or self.month_day or self.every_s)

    def as_dict(self) -> dict:
        out = {}
        if self.in_s:
            out["in_s"] = int(round(self.in_s))
        if self.at:
            out["at"] = self.at
        if self.part:
            out["part"] = self.part
        if self.date:
            out["date"] = self.date
        if self.days:
            out["days"] = list(self.days)
        if self.every_weeks:
            out["every_weeks"] = self.every_weeks
        if self.month_day:
            out["month_day"] = "last" if self.month_day < 0 else self.month_day
        if self.every_s:
            out["every_s"] = int(round(self.every_s))
        if self.from_:
            out["from"] = self.from_
        if self.to:
            out["to"] = self.to
        if self.until_date:
            out["until_date"] = self.until_date
        if self.times:
            out["times"] = self.times
        return out


def when_from(data) -> When | None:
    if data is None or data == "" or data == {}:
        return None
    if not isinstance(data, dict):
        raise BadRequest("when is an object")
    month_day = data.get("month_day")
    if isinstance(month_day, str) and month_day.strip().lower() == "last":
        day = -1
    else:
        day = _whole("month_day", month_day, 1, 31)
    every = _float("every_s", data.get("every_s"), 0.0, EVERY_S[1])
    when = When(
        in_s=_float("in_s", data.get("in_s"), 0.0, IN_S_MAX),
        at=clock(data.get("at")),
        part=_word(data.get("part"), PARTS),
        date=_date(data.get("date")),
        days=_days(data.get("days")),
        every_weeks=_whole("every_weeks", data.get("every_weeks"), 1, 4),
        month_day=day,
        every_s=max(EVERY_S[0], every) if every else 0.0,
        from_=clock(data.get("from")),
        to=clock(data.get("to")),
        until_date=_date(data.get("until_date")),
        times=_whole("times", data.get("times"), 1, TIMES_MAX),
    )
    return when if when.as_dict() else None


@dataclass(frozen=True)
class Trigger:
    event: str = ""
    who: str = ""
    thing: str = ""
    what: str = ""
    at: str = ""
    minutes: float = 0.0
    level: float = 0.0
    first_of: tuple = ()

    def as_dict(self) -> dict:
        if self.first_of:
            return {"first_of": [one.as_dict() for one in self.first_of]}
        out = {"event": self.event}
        for name in ("who", "thing", "what", "at"):
            value = getattr(self, name)
            if value:
                out[name] = value
        if self.minutes:
            out["minutes"] = _num(self.minutes)
        if self.level:
            out["level"] = _num(self.level)
        return out


def trigger_from(data, nested: bool = False) -> Trigger | None:
    if data is None or data == "" or data == {}:
        return None
    if not isinstance(data, dict):
        raise BadRequest("an event is an object")
    if "first_of" in data:
        if nested:
            raise BadRequest("first_of holds single events")
        items = data.get("first_of")
        if not isinstance(items, list) or not items:
            raise BadRequest("first_of is a list of events")
        if len(items) > MAX_FIRST:
            raise TooMuch(f"first_of holds at most {MAX_FIRST} events")
        found = tuple(t for t in (trigger_from(item, True) for item in items) if t is not None)
        if len(found) == 1:
            return found[0]
        return Trigger(first_of=found) if found else None
    event = _word(data.get("event"), EVENTS)
    if not event:
        raise BadRequest(f"unknown event {data.get('event')!r}")
    return Trigger(
        event=event,
        who=_text(data.get("who")),
        thing=_text(data.get("thing")),
        what=_text(data.get("what")),
        at=clock(data.get("at")),
        minutes=_float("minutes", data.get("minutes"), 0.0, MINUTES_MAX),
        level=_float("level", data.get("level"), 0.0, 100.0),
    )


@dataclass(frozen=True)
class Cond:
    state: str = ""
    who: str = ""
    place: str = ""
    thing: str = ""
    name: str = ""
    what: str = ""
    is_: str = ""
    at: str = ""
    from_: str = ""
    to: str = ""
    day: str = ""
    minutes: float = 0.0
    level: float = 0.0
    join: str = ""
    parts: tuple = ()

    def leaves(self) -> int:
        return sum(part.leaves() for part in self.parts) if self.join else 1

    def as_dict(self) -> dict:
        if self.join == "not":
            return {"not": self.parts[0].as_dict()}
        if self.join:
            return {self.join: [part.as_dict() for part in self.parts]}
        out = {"state": self.state}
        for key, name in (("who", "who"), ("place", "place"), ("thing", "thing"), ("name", "name"), ("what", "what"), ("is", "is_"), ("at", "at"), ("from", "from_"), ("to", "to"), ("day", "day")):
            value = getattr(self, name)
            if value:
                out[key] = value
        if self.minutes:
            out["minutes"] = _num(self.minutes)
        if self.level:
            out["level"] = _num(self.level)
        return out


def cond_from(data, depth: int = 0) -> Cond:
    if not isinstance(data, dict):
        raise BadRequest("a condition is an object")
    if depth > 3:
        raise TooMuch("a condition nests too deep")
    for join in JOINS:
        if join in data:
            inner = data[join]
            if join == "not":
                part = cond_from(inner, depth + 1)
                if part.join == "not":
                    return part.parts[0]
                return Cond(join="not", parts=(part,))
            if not isinstance(inner, list) or not inner:
                raise BadRequest(f"{join} is a list of conditions")
            parts = tuple(cond_from(item, depth + 1) for item in inner)
            if len(parts) == 1:
                return parts[0]
            return Cond(join=join, parts=parts)
    state = _word(data.get("state"), STATES)
    if not state:
        raise BadRequest(f"unknown state {data.get('state')!r}")
    day = _text(data.get("day")).replace(" ", "_")
    day = DAY_NAMES.get(day, day)
    return Cond(
        state=state,
        who=_text(data.get("who")),
        place=_text(data.get("place")),
        thing=_text(data.get("thing")),
        name=_text(data.get("name")),
        what=_text(data.get("what")),
        is_=_word(data.get("is"), ANSWERS),
        at=clock(data.get("at")),
        from_=clock(data.get("from")),
        to=clock(data.get("to")),
        day=day if day in DAY_IS else "",
        minutes=_float("minutes", data.get("minutes"), 0.0, MINUTES_MAX),
        level=_float("level", data.get("level"), 0.0, 100.0),
    )


def unless(cond: Cond) -> Cond:
    if cond.join == "not":
        return cond.parts[0]
    return Cond(join="not", parts=(cond,))


@dataclass(frozen=True)
class Request:
    kind: str
    who: str = ""
    place: str = ""
    thing: str = ""
    name: str = ""
    way: str = ""
    amount: str = ""
    metres: float = 0.0
    degrees: float = 0.0
    speed: str = ""
    seconds: float = 0.0
    until: str = ""
    change: str = ""
    harm: str = ""
    then: tuple = field(default_factory=tuple)
    sure: bool = True
    text: str = ""
    to: str = ""
    rule: str = ""
    report: str = ""
    scope: str = ""
    repeat: int = 1
    while_: Cond | None = None
    when: When | None = None
    on: Trigger | None = None
    until_on: Trigger | None = None
    if_: Cond | None = None
    else_: tuple = field(default_factory=tuple)

    @property
    def action(self) -> bool:
        return self.kind in ACTIONS

    @property
    def starts(self) -> bool:
        return self.kind in STARTS

    @property
    def moving(self) -> bool:
        return self.kind in MOVING

    @property
    def branch(self) -> bool:
        return self.kind == "if"

    def slots(self) -> dict:
        out = {}
        for name in ("who", "place", "thing", "name"):
            value = getattr(self, name)
            if value:
                out[name] = value
        if self.text:
            out["text"] = self.text
        if self.to:
            out["to"] = self.to
        for name in ("way", "amount"):
            value = getattr(self, name)
            if value:
                out[name] = value
        for name in ("metres", "degrees"):
            value = getattr(self, name)
            if value:
                out[name] = _num(value)
        if self.speed:
            out["speed"] = self.speed
        if self.seconds:
            out["seconds"] = _num(self.seconds)
        if self.repeat > 1:
            out["repeat"] = self.repeat
        if self.until_on is not None:
            out["until"] = self.until_on.as_dict()
        elif self.until:
            out["until"] = self.until
        for name in ("change", "harm", "rule", "report", "scope"):
            value = getattr(self, name)
            if value:
                out[name] = value
        return out

    def as_dict(self) -> dict:
        if self.branch:
            out = {"kind": "if", "if": self.if_.as_dict() if self.if_ is not None else {}}
            if self.then:
                out["then"] = [step.as_dict() for step in self.then]
            if self.else_:
                out["else"] = [step.as_dict() for step in self.else_]
            if self.when is not None:
                out["when"] = self.when.as_dict()
            if self.on is not None:
                out["on"] = self.on.as_dict()
            if not self.sure:
                out["sure"] = False
            return out
        out = {"kind": self.kind, **self.slots()}
        if self.while_ is not None:
            out["while"] = self.while_.as_dict()
        if self.when is not None:
            out["when"] = self.when.as_dict()
        if self.on is not None:
            out["on"] = self.on.as_dict()
        if self.if_ is not None:
            out["if"] = self.if_.as_dict()
        if self.then:
            out["then"] = [step.as_dict() for step in self.then]
        if self.else_:
            out["else"] = [step.as_dict() for step in self.else_]
        if not self.sure:
            out["sure"] = False
        return out

    def with_(self, **changes) -> "Request":
        return replace(self, **changes)

    def steps(self) -> list["Request"]:
        if self.branch:
            return [replace(self, then=(), else_=())] + [step for later in self.then + self.else_ for step in later.steps()]
        return [replace(self, then=())] + [step for later in self.then for step in later.steps()]

    def count(self) -> int:
        return len(self.steps())

    def depth(self) -> int:
        inner = self.then + self.else_
        return 1 + max((step.depth() for step in inner), default=0)

    def needs_later(self) -> list[str]:
        out = []
        if self.when is not None:
            out.append("when")
        if self.on is not None:
            out.append("on")
        if self.while_ is not None:
            out.append("while")
        if self.until_on is not None:
            out.append("until")
        for step in self.steps():
            if step.kind in LATER_KINDS and step.kind not in out:
                out.append(step.kind)
            if step.kind == "adjust" and step.change in NEW_CHANGES and "change" not in out:
                out.append("change")
            if step.while_ is not None and "while" not in out:
                out.append("while")
            if step.until_on is not None and "until" not in out:
                out.append("until")
        return out

    def text_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False)


CHAT = Request("chat")


def _steps(name: str, items, depth: int) -> tuple:
    if items is None or items == []:
        return ()
    if not isinstance(items, list):
        raise BadRequest(f"{name} is a list")
    if len(items) > MAX_THEN:
        raise TooMuch(f"{name} holds at most {MAX_THEN} steps")
    return tuple(_step(item, depth) for item in items)


def _step(data, depth: int) -> Request:
    if not isinstance(data, dict):
        raise BadRequest("a request is an object")
    if depth > MAX_DEPTH:
        raise TooMuch(f"requests nest at most {MAX_DEPTH} deep")
    kind = _text(data.get("kind")).replace(" ", "_").replace("-", "_")
    if not kind and ("if" in data or "unless" in data):
        kind = "if"
    if kind not in KINDS:
        raise BadRequest(f"unknown kind {kind!r}")
    if depth > 1 and ("when" in data or "on" in data) and (data.get("when") or data.get("on")):
        raise BadRequest("when and on belong to the whole request")
    values = {"kind": kind}
    if kind == "if":
        if "if" in data:
            values["if_"] = cond_from(data.get("if"))
        elif "unless" in data:
            values["if_"] = unless(cond_from(data.get("unless")))
        else:
            raise BadRequest("an if needs a condition")
        if depth >= MAX_DEPTH:
            raise TooMuch(f"requests nest at most {MAX_DEPTH} deep")
        values["then"] = _steps("then", data.get("then"), depth + 1)
        values["else_"] = _steps("else", data.get("else"), depth + 1)
        if not values["then"] and not values["else_"]:
            raise BadRequest("an if needs something to do")
    else:
        for name in TEXT_SLOTS:
            values[name] = _text(data.get(name))
        values["text"] = _words(data.get("text"))
        for name, words in WORD_SLOTS.items():
            if name == "until" and isinstance(data.get("until"), dict):
                values["until_on"] = trigger_from(data.get("until"))
                values["until"] = ""
                continue
            values[name] = _word(data.get(name), words)
        for name in NUMBER_SLOTS:
            values[name] = _number(name, data.get(name))
        repeat = _whole("repeat", data.get("repeat"), 1, REPEAT_MAX)
        values["repeat"] = repeat or 1
        if data.get("while"):
            values["while_"] = cond_from(data.get("while"))
        then = data.get("then") or []
        if then and depth > 1:
            raise BadRequest("then goes one level deep")
        values["then"] = _steps("then", then, depth + 1)
        if data.get("else"):
            raise BadRequest("else belongs to an if")
    if depth == 1:
        values["when"] = when_from(data.get("when"))
        values["on"] = trigger_from(data.get("on"))
    sure = data.get("sure", True)
    values["sure"] = sure if isinstance(sure, bool) else str(sure).strip().lower() not in ("false", "no", "0")
    return Request(**values)


def _parts(request: Request) -> int:
    most = 0
    for step in request.steps():
        for cond in (step.if_, step.while_):
            if cond is not None:
                most = max(most, cond.leaves())
    return most


def from_dict(data, depth: int = 0) -> Request:
    request = _step(data, depth + 1)
    if depth == 0:
        if request.count() > MAX_STEPS:
            raise TooMuch(f"a request holds at most {MAX_STEPS} steps")
        if _parts(request) > MAX_PARTS:
            raise TooMuch(f"a condition holds at most {MAX_PARTS} parts")
    return request


def too_big(request: Request) -> bool:
    if request.count() > MAX_STEPS or request.depth() > MAX_DEPTH or _parts(request) > MAX_PARTS:
        return True
    return any(len(step.then) > MAX_THEN or len(step.else_) > MAX_THEN for step in [request] + [s for s in request.steps()])


def from_json(text: str) -> Request:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise BadRequest("no JSON object")
    try:
        data = json.loads(text[start : end + 1])
    except ValueError as error:
        raise BadRequest("not JSON") from error
    return from_dict(data)
