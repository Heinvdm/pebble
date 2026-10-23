import re
from datetime import date, timedelta

from ..people.person import RELATIONSHIPS
from ..people.qualities import QUALITIES
from ..seams.face import FACES
from ..things.words import THING_WORDS, canonical
from .registry import Call, Param, Tool, ToolArgError, ToolRegistry

NOTE_KINDS = ("name", "nickname", "like", "dislike", "wish", "private")
EVENT_KINDS = ("birthday", "anniversary", "event")
REMEMBER_KINDS = ("fact",) + NOTE_KINDS + ("promise", "my_promise", "impression") + EVENT_KINDS
INTRODUCED = tuple(r for r in RELATIONSHIPS if r != "owner")
MINE_ACTIONS = ("list", "read", "write", "rename", "tag", "pin", "unpin", "delete")
SELF_ACTIONS = MINE_ACTIONS + ("wonder", "answered", "wonderings", "tune", "change", "forget", "standing")
CHANGE_KINDS = ("personality", "value", "favourite", "preference", "joke", "trust")
FORGET_KINDS = ("person", "memory", "drawing", "photo")
STATUS_PARTS = ("all", "battery", "sensors", "tasks")
MARKS = ("done", "failed", "abandoned", "active")
ME = frozenset({"me", "you", "myself", "pebble", "i"})
MONTHS = {name: n for n, names in enumerate((("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",), ("june", "jun"), ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"), ("december", "dec")), 1) for name in names}
UNITS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth")
TEENS = ("tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth", "nineteenth")
ORDINALS = {word: n for n, word in enumerate(UNITS, 1)} | {word: n for n, word in enumerate(TEENS, 10)} | {"twentieth": 20, "thirtieth": 30, "thirty-first": 31, "thirty first": 31} | {f"twenty{sep}{word}": 20 + n for n, word in enumerate(UNITS, 1) for sep in ("-", " ")}
TODAY = re.compile(r"\b(today|tonight|this (?:morning|afternoon|evening)|tomorrow)\b")
ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
YEAR = re.compile(r"\b(19\d{2}|20\d{2}|2100)\b")
DAY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\b")
CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b|\b(\d{1,2}):(\d{2})\b", re.IGNORECASE)
SPAN = re.compile(r"\b(\d+(?:\.\d+)?|an?|half an?)\s*(minute|min|hour|hr|day)s?\b", re.IGNORECASE)
SHOWN_S = 8
WHEN_HELP = "say when, like 18:00 or in 30 minutes"
DATE_HELP = "say the date, like 12 March"


def date_of(text: str, today: date | None = None) -> tuple[int, int, int | None] | None:
    words = " ".join((text or "").lower().replace(",", " ").split())
    found = ISO_DATE.search(words)
    if found:
        return int(found.group(2)), int(found.group(3)), int(found.group(1))
    if today is not None:
        near = TODAY.search(words)
        if near:
            day = today + timedelta(days=1 if near.group(1) == "tomorrow" else 0)
            return day.month, day.day, None
    month = next((MONTHS[w] for w in re.findall(r"[a-z]+", words) if w in MONTHS), None)
    if month is None:
        return None
    year_found = YEAR.search(words)
    year = int(year_found.group(1)) if year_found else None
    rest = YEAR.sub(" ", words)
    day = None
    for word, number in sorted(ORDINALS.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b{word}\b", rest):
            day = number
            break
    if day is None:
        found = DAY.search(rest)
        day = int(found.group(1)) if found else None
    if day is None or not 1 <= day <= 31:
        return None
    return month, day, year


def due_of(text: str) -> dict:
    words = (text or "").strip().lower()
    clock = CLOCK.search(words)
    if clock:
        if clock.group(4):
            return {"at": f"{int(clock.group(4))}:{clock.group(5)}"}
        return {"at": f"{int(clock.group(1))}:{clock.group(2) or '00'} {clock.group(3)}"}
    if "tomorrow" in words:
        return {"minutes": 1440}
    span = SPAN.search(words)
    if span:
        amount = span.group(1)
        number = 0.5 if amount.startswith("half") else 1.0 if amount in ("a", "an") else float(amount)
        unit = span.group(2)
        scale = 1440 if unit.startswith("day") else 60 if unit.startswith("h") else 1
        return {"minutes": number * scale}
    raise ToolArgError(WHEN_HELP)


def _need(args: dict, name: str, what: str) -> str:
    value = (args.get(name) or "").strip() if isinstance(args.get(name), str) else args.get(name)
    if not value:
        raise ToolArgError(f"say {what}")
    return value


def route_face(args: dict) -> list[tuple[str, dict]]:
    if args.get("draw"):
        return [("draw_scene", {"subject": args["draw"], "name": args.get("picture") or "", "mode": "full", "seconds": SHOWN_S})]
    if args.get("picture"):
        return [("show_scene", {"name": args["picture"], "mode": "full", "seconds": SHOWN_S, "vary": False})]
    out = []
    if args.get("expression"):
        out.append(("set_face", {"expression": args["expression"]}))
    if args.get("tilt") is not None:
        out.append(("look", {"degrees": args["tilt"]}))
    if not out:
        raise ToolArgError("say which expression, what to draw, which kept drawing, or how far to tilt")
    return out


def route_remember(args: dict, today: date | None = None) -> list[tuple[str, dict]]:
    kind = args.get("kind") or "fact"
    fact = _need(args, "fact", "what to keep")
    about = (args.get("about") or "").strip()
    by = (args.get("by") or "").strip()
    if kind == "fact":
        return [("remember", {"fact": fact, "about": about})]
    if kind in EVENT_KINDS:
        found = date_of(args.get("when") or "", today) or date_of(fact, today)
        if found is None:
            raise ToolArgError(DATE_HELP)
        month, day, year = found
        event = {"title": fact, "month": month, "day": day, "kind": kind}
        if year:
            event["year"] = year
        if about:
            event["person"] = about
        return [("add_event", event)]
    person = _need(args, "about", "who it is about")
    if kind == "name" and by and by.lower() not in ME and by.lower() != person.lower():
        out = {"by": by, "name": fact, "who": person}
        if args.get("relationship"):
            out["relationship"] = args["relationship"]
        return [("introduce", out)]
    if kind in NOTE_KINDS:
        return [("note_person", {"person": person, "kind": kind, "text": fact})]
    if kind in ("promise", "my_promise"):
        when = args.get("when") or ""
        try:
            due = due_of(when)
        except ToolArgError:
            if when:
                raise
            due = due_of(fact)
        return [("note_promise", {"person": person, "who": "me" if kind == "my_promise" else "them", "what": fact, **due})]
    if not args.get("quality") or args.get("good") is None:
        raise ToolArgError("say which quality, and whether it speaks for them (good) or against them")
    return [("note_impression", {"person": person, "quality": args["quality"], "good": args["good"], "reason": fact})]


def route_self(args: dict) -> list[tuple[str, dict]]:
    action = args["action"]
    name = (args.get("name") or "").strip()
    text = args.get("text") or ""
    if action in MINE_ACTIONS:
        out = {"action": action, "name": name}
        if action == "write":
            out["text"] = text
        elif action == "rename":
            out["to"] = text
        elif action in ("tag", "list"):
            out["tags"] = text
        return [("mine", out)]
    if action == "wonder":
        return [("wonder", {"action": "add", "text": _need(args, "text", "the wondering")})]
    if action == "answered":
        return [("wonder", {"action": "answered", "id": _need(args, "name", "which wondering (its id)"), "text": text})]
    if action == "wonderings":
        return [("wonder", {"action": "list"})]
    if action == "tune":
        return [("tune", {"name": _need(args, "name", "which setting"), "value": _need(args, "text", "the new value"), "why": args.get("why") or ""})]
    person = _need(args, "person", "who asked")
    if action == "standing":
        return [("my_standing", {"person": person})]
    kind = args.get("kind") or ""
    if action == "forget":
        what = kind if kind in FORGET_KINDS else "memory"
        return [("request_forget", {"person": person, "what": what, "target": name, "why": args.get("why") or ""})]
    if kind not in CHANGE_KINDS:
        raise ToolArgError("say what kind of change: " + ", ".join(CHANGE_KINDS))
    return [("request_change", {"person": person, "kind": kind, "target": name, "amount": args.get("amount") or 0, "text": text, "why": args.get("why") or ""})]


def route_status(args: dict) -> list[tuple[str, dict]]:
    if args.get("task"):
        update = {"id": args["task"]}
        if args.get("mark"):
            update["status"] = args["mark"]
        if args.get("note"):
            update["note"] = args["note"]
        return [("update_task", update)]
    part = args.get("about") or "all"
    chosen = {"battery": "get_battery", "sensors": "read_sensors", "tasks": "list_tasks"}
    return [(chosen[part], {})] if part in chosen else [(action, {}) for action in chosen.values()]


def route_say(args: dict) -> list[tuple[str, dict]]:
    text = args["text"]
    to = (args.get("to") or "").strip()
    if to and not text.lower().startswith(to.lower()):
        text = f"{to}, {text}"
    return [("say", {"text": text, "kind": args.get("kind") or "talk"})]


def route_recall(args: dict) -> list[tuple[str, dict]]:
    return [("recall", {"about": args["about"]}), ("recall_thing", {"thing": args["about"][:40]})]


def route_stop(args: dict) -> list[tuple[str, dict]]:
    return [("stop", {})]


def route_end(args: dict) -> list[tuple[str, dict]]:
    asker = (args.get("for") or "").strip()
    return [("end_activity", {"asked_by": asker} if asker else {})]


async def run_routes(steps: list[tuple[str, dict]], call: Call) -> dict:
    if len(steps) == 1:
        action, args = steps[0]
        return await call.act(action, args)
    out: dict = {"ok": True}
    for action, args in steps:
        result = await call.act(action, args)
        out[action] = result
        out["ok"] = out["ok"] and bool(result.get("ok", True))
    return out


def routed(route):
    async def handler(args: dict, call: Call) -> dict:
        return await run_routes(route(args), call)

    return handler


async def recall(args: dict, call: Call) -> dict:
    out: dict = {"ok": True}
    if call.has("recall"):
        found = await call.act("recall", {"about": args["about"]})
        out["memories"] = found.get("memories") or []
        if found.get("note") and not out["memories"]:
            out["note"] = found["note"]
    thing = canonical(args["about"][:40])
    if call.has("recall_thing") and (thing in THING_WORDS or thing.split(" ")[-1] in THING_WORDS):
        seen = await call.act("recall_thing", {"thing": thing})
        if seen.get("ok") and seen.get("memory") and "no memory of things" not in seen["memory"]:
            out["thing"] = seen["memory"]
    if call.has("how_to"):
        taught = await call.act("how_to", {"about": args["about"]})
        if taught.get("howto"):
            out["howto"] = taught["howto"]
    if not out.get("memories") and "thing" not in out and "howto" not in out and "note" not in out:
        out["note"] = "nothing comes to mind"
    return out


def register_broad(registry: ToolRegistry, today=lambda: None) -> None:
    registry.register(Tool(
        "say",
        "Say something out loud, only words that matter.",
        {
            "text": Param("string", "what to say", max_length=240),
            "kind": Param("enum", "", choices=("talk", "joke"), required=False, default="talk"),
            "to": Param("string", "who it is for", max_length=40, required=False),
        },
        routed(route_say),
        ("say",),
    ))
    registry.register(Tool(
        "face",
        "Your face screen and head: an expression, a drawing, or a tilt.",
        {
            "expression": Param("enum", "", choices=FACES, required=False),
            "draw": Param("string", "what to draw", max_length=80, required=False),
            "picture": Param("string", "a kept drawing to show, or a name for a new one", max_length=32, required=False),
            "tilt": Param("number", "head tilt, degrees up", -35, 90, required=False),
        },
        routed(route_face),
        ("set_face", "draw_scene", "show_scene", "look"),
    ))
    registry.register(Tool(
        "remember",
        "Keep a fact, a birthday or date, a note about someone here, a promise (my_promise if yours) or an impression.",
        {
            "fact": Param("string", "what to keep, in a few words", max_length=200),
            "kind": Param("enum", "", choices=REMEMBER_KINDS, required=False, default="fact"),
            "about": Param("string", "who or what", max_length=40, required=False),
            "by": Param("string", "who introduced them", max_length=40, required=False),
            "when": Param("string", "a date (12 March) or time (18:00, in 30 minutes)", max_length=40, required=False),
            "quality": Param("enum", "", choices=QUALITIES, required=False),
            "good": Param("boolean", "true if good", required=False),
            "relationship": Param("enum", "", choices=INTRODUCED, required=False),
        },
        routed(lambda args: route_remember(args, today())),
        ("remember", "note_person", "note_promise", "introduce", "note_impression", "add_event"),
    ))
    registry.register(Tool(
        "recall",
        "Look up what happened, what was said, or where things were.",
        {"about": Param("string", "what to look up", max_length=120)},
        recall,
        ("recall", "recall_thing"),
    ))
    registry.register(Tool(
        "self",
        "Your folder (mine/), wonderings and settings; requests to change you, forget something, or say how you see someone.",
        {
            "action": Param("enum", "", choices=SELF_ACTIONS),
            "name": Param("string", "a file, wondering id, setting, or what to change or forget", max_length=120, required=False),
            "text": Param("string", "what to write, a wondering, a name, tags, a value or the change", max_length=4000, required=False),
            "person": Param("string", "who asked", max_length=40, required=False),
            "kind": Param("enum", "for change or forget", choices=CHANGE_KINDS + FORGET_KINDS, required=False),
            "amount": Param("integer", "for change: up or down", -3, 3, required=False, default=0),
            "why": Param("string", "why", max_length=160, required=False),
        },
        routed(route_self),
        ("mine", "wonder", "tune", "request_change", "request_forget", "my_standing"),
    ))
    registry.register(Tool(
        "status",
        "Read battery, sensors or tasks, or mark a task.",
        {
            "about": Param("enum", "", choices=STATUS_PARTS, required=False, default="all"),
            "task": Param("integer", "a task's id", 1, 1_000_000, required=False),
            "mark": Param("enum", "", choices=MARKS, required=False),
            "note": Param("string", "a note", max_length=160, required=False),
        },
        routed(route_status),
        ("get_battery", "read_sensors", "list_tasks", "update_task"),
    ))
    registry.register(Tool(
        "end",
        "End your current activity (following, waiting, looking); not a safety stop.",
        {"for": Param("string", "who asked, if anyone", max_length=40, required=False)},
        routed(route_end),
        ("end_activity",),
    ))
    registry.register(Tool("stop", "Stop all motion at once.", {}, routed(route_stop), ("stop",)))


ROUTES = {"say": route_say, "face": route_face, "remember": route_remember, "recall": route_recall, "self": route_self, "status": route_status, "end": route_end, "stop": route_stop}
ACTED_MOST = 100


def _clip(text, limit: int = ACTED_MOST) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _answer(result: dict) -> str:
    if result.get("answer"):
        return str(result["answer"])
    if result.get("unclear"):
        return "you asked what they meant"
    if result.get("ok") is False:
        return f"no: {_clip(result.get('error') or result.get('reason'), 60)}" if result.get("error") or result.get("reason") else "no"
    return ""


def _kept(action: str, args: dict) -> str:
    if action == "add_event":
        return f"you kept a date: {_clip(args.get('title'), 80)}"
    if action == "note_promise":
        return f"you kept a promise: {_clip(args.get('what'), 80)}"
    if action == "note_person":
        return f"you kept a note about {_clip(args.get('person'), 30)}: {_clip(args.get('text'), 80)}"
    if action == "introduce":
        return f"you were told {_clip(args.get('who'), 30)} is called {_clip(args.get('name'), 30)}"
    if action == "note_impression":
        return f"you kept an impression of {_clip(args.get('person'), 30)}"
    return f"you kept: {_clip(args.get('fact'), 80)}"


def acted(name: str, args: dict | None, result: dict | None = None) -> str:
    args = args if isinstance(args, dict) else {}
    result = result if isinstance(result, dict) else {}
    if name == "say":
        return f'you said: "{_clip(args.get("text"), 80)}"'
    if name == "do":
        if args.get("done_when"):
            return f"you set yourself a task: {_clip(args.get('words'), 80)}"
        answer = _answer(result)
        return f"you did: {_clip(result.get('read_as') or args.get('words'), 80)}" + (f" ({answer})" if answer else "")
    if name == "recall":
        found = result.get("thing") or next(iter(result.get("memories") or []), "") or next(iter(result.get("howto") or []), "") or result.get("note")
        about = _clip(args.get("about"), 40)
        return f"you recalled {about}: {_clip(found)}" if found else f"you recalled {about}"
    if name == "recall_thing":
        return f"you recalled the {_clip(args.get('thing'), 30)}: {_clip(result.get('memory'))}"
    if name in ("add_task", "update_task"):
        return f"you {'set yourself a task' if name == 'add_task' else 'marked a task'}: {_clip(args.get('title') or args.get('status') or args.get('id'), 80)}"
    if name in ("add_event", "note_promise", "note_person", "introduce", "note_impression"):
        return _kept(name, args)
    if name == "remember":
        try:
            action, routed_args = route_remember(args)[0]
        except Exception:
            return f"you kept: {_clip(args.get('fact'), 80)}"
        return _kept(action, routed_args if action != "remember" else args)
    if name == "face":
        if args.get("draw"):
            return f"you drew {_clip(args['draw'], 60)}"
        if args.get("picture"):
            return f"you showed your drawing {_clip(args['picture'], 40)}"
        if args.get("expression"):
            return f"you made a {args['expression']} face"
    if name in ROUTES:
        try:
            actions = [action for action, _ in ROUTES[name](args)]
        except Exception:
            actions = []
        if actions:
            return "you used " + ", ".join(dict.fromkeys(actions))
    return f"you used {name}"
