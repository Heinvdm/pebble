from dataclasses import dataclass, field
from typing import Awaitable, Callable

from ..body.api import Body
from ..body.sensors import SensorSnapshot
from ..body.telemetry import pack_fraction
from ..books import Books
from ..clock import Clock, iso
from ..goals import GOAL_CAP, TASK_CAP, Item, Rejected
from ..laws import move_limits
from ..occasions import BadDate
from ..respect import cruel, harsh
from ..seams.face import FACES, Face
from ..seams.voice import Voice
from ..self.gatekeeper import Gatekeeper
from .broad import register_broad
from .registry import Param, Tool, ToolRegistry

DIRECTIONS = {
    "forward": lambda p: (p, p),
    "backward": lambda p: (-p, -p),
    "turn_left": lambda p: (round(p * 0.3), p),
    "turn_right": lambda p: (p, round(p * 0.3)),
    "spin_left": lambda p: (-p, p),
    "spin_right": lambda p: (p, -p),
}
FORWARD = ("forward", "turn_left", "turn_right")
NEEDS = ("none", "curiosity", "social", "rest", "energy")


@dataclass
class Permissions:
    can_move: bool = False
    quiet: bool = False
    initiative: bool = False
    homing: bool = False


@dataclass
class ToolContext:
    clock: Clock
    body: Body
    books: Books
    face: Face
    voice: Voice
    permissions: Permissions
    sensors: Callable[[], SensorSnapshot | None]
    on_spoke: Callable[[], None] = field(default=lambda: None)
    on_task_closed: Callable[[Item], None] = field(default=lambda item: None)
    motion_guard: Callable[[], str | None] = field(default=lambda: None)
    people_near: Callable[[], bool] = field(default=lambda: False)
    phrase: Callable[[str, str], Awaitable] | None = None
    joking_ok: Callable[[], bool] = field(default=lambda: True)
    task_from: Callable[[str], str | None] = field(default=lambda name: None)
    life_ahead: Callable[[], str | None] = field(default=lambda: None)


def _battery(ctx: ToolContext) -> dict:
    snapshot = ctx.sensors()
    reading = snapshot.battery if snapshot else None
    pack = ctx.body.telemetry.pack_mv
    fraction = pack_fraction(pack)
    return {
        "phone_pct": None if reading is None else reading.percent,
        "phone_charging": None if reading is None else reading.charging,
        "phone_health_pct": None if reading is None else reading.health_pct,
        "pack_mv": pack,
        "pack_pct": None if fraction is None else round(fraction * 100),
        "docked": ctx.body.telemetry.docked,
    }


def build_registry(ctx: ToolContext) -> ToolRegistry:
    profile = ctx.body.profile
    books = ctx.books
    registry = ToolRegistry()
    keeper = Gatekeeper(ctx.clock)
    keeper.can_move = lambda: ctx.permissions.can_move
    keeper.motion_guard = lambda: ctx.motion_guard()
    keeper.life_ahead = lambda: ctx.life_ahead()
    registry.keeper = keeper

    async def move(args: dict) -> dict:
        if not ctx.permissions.can_move:
            return {"ok": False, "error": "moving is off right now (resting, quiet hours or the battery routine)"}
        blocked = ctx.motion_guard()
        if blocked:
            return {"ok": False, "error": f"not moving: {blocked}"}
        alive = ctx.life_ahead() if args["direction"] in FORWARD else None
        if alive:
            return {"ok": False, "error": f"not moving: there is a {alive} just ahead, and you never go over anything alive", "law": 1}
        speed, seconds, notes = move_limits(args["speed"], args["seconds"], ctx.people_near())
        left, right = DIRECTIONS[args["direction"]](round(speed * profile.max_power))
        report = (await ctx.body.move(left, right, seconds)).as_dict()
        if notes:
            report["notes"] = notes
        return report

    async def look(args: dict) -> dict:
        target = await ctx.body.tilt(args["degrees"])
        if target is None:
            return {"ok": False, "error": "the body is not connected"}
        return {"tilt_target_deg": target}

    async def stop(args: dict) -> dict:
        sent = await ctx.body.stop()
        return {"ok": sent, "stopped": sent}

    async def set_face(args: dict) -> dict:
        ctx.face.show(args["expression"])
        return {"face": ctx.face.current}

    async def remember(args: dict) -> dict:
        if cruel(args["fact"]):
            return {"ok": False, "error": "not kept: it would be unkind to something alive"}
        fact = books.memory.remember(args["fact"], iso(ctx.clock.now()), args.get("about"))
        books.save("memory")
        return {"remembered": fact["text"], "times": fact["times"]}

    async def add_task(args: dict) -> dict:
        requested_by = args.get("requested_by") or None
        need = args.get("need") or "none"
        refused = ctx.task_from(requested_by) if requested_by else None
        if refused:
            return {"ok": False, "error": refused}
        try:
            item = books.goals.add(
                kind=args["kind"],
                title=args["title"],
                done_when=args["done_when"],
                reason=args["reason"],
                source="person" if requested_by else "self",
                priority=args["priority"],
                hours=args.get("hours"),
                requested_by=requested_by,
                serves=() if need == "none" else (need,),
            )
        except Rejected as error:
            return {"ok": False, "error": str(error)}
        books.save("goals")
        return {"added": item.summary()}

    async def update_task(args: dict) -> dict:
        try:
            item = books.goals.update(args["id"], args.get("status"), args.get("note"))
        except Rejected as error:
            return {"ok": False, "error": str(error)}
        books.save("goals")
        if item.status in ("done", "failed"):
            ctx.on_task_closed(item)
        return {"updated": item.summary()}

    async def list_tasks(args: dict) -> dict:
        return {
            "active": [item.summary() for item in books.goals.active()],
            "current_id": books.goals.current_id,
        }

    async def read_sensors(args: dict) -> dict:
        snapshot = ctx.sensors()
        body = ctx.body.telemetry.snapshot(ctx.clock.now())
        phone = {
            "temperature_c": None if snapshot is None else snapshot.temperature_c,
            "light_lux": None if snapshot is None else snapshot.light_lux,
            "motion_sensor": snapshot is not None and snapshot.imu is not None,
        }
        return {"body": body, "phone": phone}

    async def get_battery(args: dict) -> dict:
        return _battery(ctx)

    async def add_event(args: dict) -> dict:
        try:
            entry = books.calendar.add_personal(
                args["title"], args["month"], args["day"], args["kind"], iso(ctx.clock.now()), args.get("year"), args.get("person")
            )
        except BadDate as error:
            return {"ok": False, "error": str(error)}
        books.save("calendar")
        return {"added": entry}

    async def say(args: dict) -> dict:
        kind = args.get("kind") or "talk"
        if kind == "joke" and not ctx.joking_ok():
            kind = "talk"
        if kind == "joke" and harsh(args["text"]):
            return {"spoken": False, "held_back": "the joke would be unkind to something alive"}
        words, phrasing = args["text"], "draft"
        whisper = ctx.permissions.quiet
        results = []

        async def aloud(part: str) -> None:
            results.append(await ctx.voice.say(part, whisper=whisper))

        spoken = False
        if ctx.phrase is not None:
            phrased = await ctx.phrase(words, kind, speak=aloud)
            words, phrasing, spoken = phrased.text, phrased.source, phrased.spoken
        if not spoken:
            results.append(await ctx.voice.say(words, whisper=whisper))
        ctx.on_spoke()
        return {"spoken": all(r.spoken for r in results), "engine": results[-1].engine, "whisper": whisper, "words": words, "phrasing": phrasing}

    registry.register_action(Tool(
        "move",
        "Roll for a moment. Keep it short; the body's reflexes stop it at edges, bumps and stalls.",
        {
            "direction": Param("enum", "which way to roll", choices=tuple(DIRECTIONS)),
            "speed": Param("number", "fraction of the safe top speed", 0.1, 1.0, required=False, default=0.4),
            "seconds": Param("number", "how long to roll", 0.2, profile.max_move_seconds, required=False, default=1.0),
        },
        move,
    ))
    registry.register_action(Tool(
        "look",
        "Tilt the head (the phone) up or down. 0 is level, positive looks up.",
        {"degrees": Param("number", "tilt angle in degrees", profile.tilt_min, profile.tilt_max)},
        look,
    ))
    registry.register_action(Tool("stop", "Stop all motion at once.", {}, stop))
    registry.register_action(Tool(
        "set_face",
        "Show an expression on the face.",
        {"expression": Param("enum", "the expression", choices=FACES)},
        set_face,
    ))
    registry.register_action(Tool(
        "remember",
        "Save a short fact to long-term memory.",
        {
            "fact": Param("string", "the fact, in plain words", max_length=200),
            "about": Param("string", "who or what it is about", max_length=40, required=False),
        },
        remember,
    ))
    registry.register_action(Tool(
        "add_task",
        f"Add a concrete task or goal with a done-when and an expiry. Vague grand goals are refused. You hold at most {GOAL_CAP} goals and {TASK_CAP} tasks at once; finish or drop one before adding more.",
        {
            "title": Param("string", "short title", max_length=80),
            "done_when": Param("string", "how to tell it is finished", max_length=160),
            "reason": Param("string", "why, in a few words", max_length=160),
            "kind": Param("enum", "task or goal", choices=("task", "goal"), required=False, default="task"),
            "priority": Param("integer", "1 low to 5 high", 1, 5, required=False, default=3),
            "hours": Param("number", "hours until it expires", 0.25, 720, required=False),
            "need": Param("enum", "which need it serves", choices=NEEDS, required=False, default="none"),
            "requested_by": Param("string", "name of the person who asked, if someone asked", max_length=40, required=False),
        },
        add_task,
    ))
    registry.register_action(Tool(
        "update_task",
        "Mark a task or goal done, failed or abandoned, or add a progress note.",
        {
            "id": Param("integer", "task or goal id", 1, 1_000_000),
            "status": Param("enum", "new status", choices=("active", "done", "failed", "abandoned"), required=False),
            "note": Param("string", "progress note", max_length=160, required=False),
        },
        update_task,
    ))
    registry.register_action(Tool("list_tasks", "List active tasks and goals.", {}, list_tasks))
    registry.register_action(Tool("read_sensors", "Read the body's and the phone's sensors in detail.", {}, read_sensors))
    registry.register_action(Tool("get_battery", "Read the phone battery and the body's pack.", {}, get_battery))
    registry.register_action(Tool(
        "add_event",
        "Save a birthday, anniversary or event to the calendar.",
        {
            "title": Param("string", "what it is", max_length=60),
            "month": Param("integer", "month 1-12", 1, 12),
            "day": Param("integer", "day of the month", 1, 31),
            "kind": Param("enum", "birthday, anniversary or event", choices=("birthday", "anniversary", "event"), required=False, default="event"),
            "year": Param("integer", "year, if known", 1900, 2100, required=False),
            "person": Param("string", "whose it is", max_length=40, required=False),
        },
        add_event,
    ))
    registry.register_action(Tool(
        "say",
        "Say something out loud. Only for words that matter. Give the gist; your voice finds the words.",
        {
            "text": Param("string", "what to say", max_length=240),
            "kind": Param("enum", "plain talk or a joke", choices=("talk", "joke"), required=False, default="talk"),
        },
        say,
    ))

    async def tune(args: dict) -> dict:
        value = args["value"]
        try:
            value = float(value)
        except ValueError:
            pass
        return keeper.ruling(args["name"], value, args.get("why") or "")

    registry.register_action(Tool(
        "tune",
        "Change one of your own settings, within the range you may.",
        {
            "name": Param("string", "the setting", max_length=60),
            "value": Param("string", "the new value", max_length=60),
            "why": Param("string", "why, in a few words", max_length=160, required=False),
        },
        tune,
    ))
    register_broad(registry, lambda: ctx.clock.local().date())
    return registry
