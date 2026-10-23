from ..tools.registry import Call, Param, Tool, ToolRegistry
from ..things.guarded import STRANGER_NO, kept_from_strangers
from ..things.words import canonical
from ..understand.request import OLD_CHANGES, REPEAT_MAX, STARTS, UNTILS, Request
from ..understand.understanding import UNDERSTAND_QUIETLY
from .commands import Commands, for_mind
from .gate import PEBBLE

ACTIVITY_TOOLS = ("start_activity", "change_activity", "end_activity")
THING_TOOLS = ("recall_thing",)
START_KINDS = tuple(kind for kind in ("follow", "come", "wait", "look", "back_off", "go_home", "go_to_place", "go_to_thing", "find", "turn", "move") if kind in STARTS)
DO_ACTS = ("start_activity", "change_activity", "end_activity", "move", "add_task", "say")
TOO_MANY = "that is too many steps at once; ask for fewer"
NOT_BODY = "your body can't do that"
NOT_A_DO = "those words don't ask your body to do anything; to talk, use say"
NOW_KINDS = frozenset({"check", "watch", "again", "try_new"})


def action_of(step: Request) -> tuple[str, dict]:
    kind = step.kind
    if kind == "say_to":
        return "say", {"text": step.text or kind}
    if kind in ("stop_activity", "release"):
        return "end_activity", {}
    if kind == "adjust":
        return "change_activity", {"change": step.change}
    if kind == "move":
        return "move", {"direction": "backward" if step.way == "back" else "forward"}
    if kind == "turn":
        return "move", {"direction": "spin_left" if step.way == "left" else "spin_right"}
    return "start_activity", {key: value for key, value in (("kind", kind), ("who", step.who), ("thing", step.thing), ("place", step.place), ("text", step.text)) if value}


def actions_of(request: Request) -> list[tuple[str, dict]]:
    steps = [action_of(step) for step in request.steps() if not step.branch]
    if [part for part in request.needs_later() if part not in NOW_KINDS]:
        steps.insert(0, ("add_task", {"title": " ".join(step.text for step in request.steps() if step.text) or for_mind(request)}))
    return steps or [action_of(request)]


def register_activity_tools(registry: ToolRegistry, commands: Commands) -> None:
    def asker_of(args: dict):
        name = (args.get("asked_by") or "").strip()
        if not name:
            return PEBBLE, ""
        return commands.requester(name)

    def result(verdict) -> dict:
        out = {"ok": verdict.answer == "yes", "answer": verdict.answer, "reason": verdict.reason}
        if verdict.say:
            out["you_said"] = verdict.say
        if verdict.law is not None:
            out["law"] = verdict.law
        return out

    async def start_activity(args: dict) -> dict:
        asker, problem = asker_of(args)
        if asker is None:
            return {"ok": False, "error": problem}
        person = (args.get("person") or "").strip().lower()
        thing = canonical(args.get("thing") or "")
        if args["kind"] in ("go_to_thing", "find") and not thing:
            return {"ok": False, "error": "say which thing"}
        if not asker.own and person and asker.label.lower() == person:
            person = "me"
        if not person and not thing and not asker.own and args["kind"] in ("follow", "come", "look"):
            person = "me"
        if asker.own and args["kind"] in ("follow", "come", "look") and person in ("", "me") and not thing:
            return {"ok": False, "error": "say who: a name from the people here"}
        request = Request(
            args["kind"],
            who="" if thing else person,
            thing=thing,
            place=(args.get("place") or "").strip().lower(),
            way=args.get("way") or "",
            amount=args.get("amount") or "",
            speed=args.get("speed") or "",
            seconds=float(args.get("seconds") or 0.0),
            until=args.get("until") or "",
            metres=float(args.get("metres") or 0.0),
            repeat=max(1, min(REPEAT_MAX, int(args.get("repeat") or 1))),
        )
        verdict = await commands.act(request, asker, "mind")
        return result(verdict)

    async def change_activity(args: dict) -> dict:
        asker, problem = asker_of(args)
        if asker is None:
            return {"ok": False, "error": problem}
        if commands.runner.current is None:
            return {"ok": False, "error": "you are not doing anything that can be changed"}
        verdict = await commands.act(Request("adjust", change=args["change"]), asker, "mind")
        return result(verdict)

    async def end_activity(args: dict) -> dict:
        asker, problem = asker_of(args)
        if asker is None:
            return {"ok": False, "error": problem}
        if commands.runner.current is None:
            return {"ok": True, "note": "you were not doing anything"}
        verdict = await commands.act(Request("release"), asker, "mind")
        return result(verdict)

    registry.register_action(Tool(
        "start_activity",
        "Start doing something that lasts: follow, come, wait, look at someone or something, back off, go back to your charger, go to a place, go to a thing, look for a thing, turn or a small move. "
        "Use it when someone asks in words you understand, or when you decide yourself. Your rules decide yes or no and you say why.",
        {
            "kind": Param("enum", "what to do", choices=START_KINDS),
            "asked_by": Param("string", "name of the person who asked; leave empty when it is your own idea", max_length=40, required=False),
            "person": Param("string", "who to follow, come to or look at (a name, or empty for the person asking)", max_length=40, required=False),
            "thing": Param("string", "for go_to_thing, find, look or follow: the object or animal, in a word or two (ball, cat, slipper)", max_length=40, required=False),
            "place": Param("string", "for go_to_place: the room", max_length=40, required=False),
            "way": Param("enum", "for turn and move", choices=("left", "right", "around", "forward", "back"), required=False),
            "amount": Param("enum", "a little or a lot", choices=("little", "lot"), required=False),
            "speed": Param("enum", "slow or quick", choices=("slow", "quick"), required=False),
            "seconds": Param("number", "how long, if they said", 0, 3600, required=False),
            "metres": Param("number", "how far, or the gap to keep when following", 0, 30, required=False),
            "repeat": Param("number", "how many times, if they said (twice is 2)", 1, REPEAT_MAX, required=False),
            "until": Param("enum", "until they are back, until called, until they've had enough (asked) or until told to stop", choices=UNTILS, required=False),
        },
        start_activity,
    ))
    registry.register_action(Tool(
        "change_activity",
        "Change what you are doing now: slower, faster, closer, further, enough (stay where you are), stay, other_way or keep_going.",
        {
            "change": Param("enum", "the change", choices=OLD_CHANGES),
            "asked_by": Param("string", "name of the person who asked; empty if it is your own idea", max_length=40, required=False),
        },
        change_activity,
    ))
    async def recall_thing(args: dict) -> dict:
        thing = canonical(args["thing"])
        near = commands.strangers_near()
        memory = STRANGER_NO if near and kept_from_strangers(args["thing"]) else commands.recall(thing, near)
        if memory == STRANGER_NO:
            return {"thing": thing, "memory": "someone you don't know is here, so keep where that is to yourself for now"}
        kept = commands.unsafe_to_tell(args["thing"]) or commands.unsafe_to_tell(thing)
        if kept:
            return {"thing": thing, "memory": kept}
        return {"thing": thing, "memory": memory or "you keep no memory of things yet"}

    registry.register_action(Tool(
        "recall_thing",
        "Remember where and when you last saw a kind of thing or animal (a ball, the cat, keys). Answers honestly when unsure or never seen.",
        {"thing": Param("string", "the thing, in a word or two", max_length=40)},
        recall_thing,
    ))
    registry.register_action(Tool(
        "end_activity",
        "Finish what you are doing now (following, waiting and so on) and go back to your own things.",
        {"asked_by": Param("string", "name of the person who asked; empty if it is your own idea", max_length=40, required=False)},
        end_activity,
    ))

    async def do(args: dict, call: Call) -> dict:
        asker, problem = asker_of({"asked_by": args.get("for")})
        if asker is None:
            return {"ok": False, "error": problem}
        words = args["words"]
        if args.get("done_when"):
            task = {"title": words[:80], "done_when": args["done_when"], "reason": "my own idea" if asker.own else f"{asker.label} asked"}
            if args.get("hours"):
                task["hours"] = args["hours"]
            if not asker.own:
                task["requested_by"] = asker.label
            return await call.act("add_task", task)
        reading = await commands.read_words(words, asker, UNDERSTAND_QUIETLY)
        request = reading.request
        if commands.later is not None and request.action:
            asker, request = commands.later.for_whom(request, asker)
        if reading.too_much:
            return {"ok": False, "error": TOO_MANY}
        if reading.ask:
            return {"ok": False, "unclear": reading.question}
        if not request.action:
            return {"ok": False, "error": NOT_BODY if request.kind == "other" else NOT_A_DO}
        steps = actions_of(request)
        for action, action_args in steps:
            refused = call.refused(action, action_args)
            if refused is not None:
                return {**refused, "read_as": for_mind(request)}
        verdict = await commands.act(request, asker, "mind")
        return call.noted(steps[0][0], {**result(verdict), "read_as": for_mind(request)})

    registry.register(Tool(
        "do",
        "Do something with your body now, in plain words (\"follow Ina\", \"slower\"). For a task or reminder for later, add done_when.",
        {
            "words": Param("string", "what to do", max_length=160),
            "for": Param("string", "who asked, if anyone", max_length=40, required=False),
            "done_when": Param("string", "only for a task for later: how you'll know it's finished", max_length=160, required=False),
            "hours": Param("number", "for a task: hours it lasts", 0.25, 720, required=False),
        },
        do,
        DO_ACTS,
    ))
