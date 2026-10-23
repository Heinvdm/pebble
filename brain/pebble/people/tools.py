from ..tools.registry import Param, Tool, ToolRegistry
from .company import Company
from .explain import standing_text
from .person import RELATIONSHIPS
from .proof import UNSEEN_REASON
from .promises import BadDue, due_at
from .qualities import QUALITIES, NotScored
from .trust import INNER, TRUSTED, allowed, at_least

PEOPLE_TOOLS = ("note_person", "note_promise", "introduce", "note_impression", "request_change", "request_forget", "my_standing")
NOTE_KINDS = ("name", "nickname", "like", "dislike", "wish", "private")
CHANGE_KINDS = ("personality", "value", "favourite", "preference", "joke", "trust")
FORGET_WHAT = {"person": "forget_person", "memory": "delete_memory", "drawing": "delete_drawing", "photo": "delete_photo"}
INTRODUCED = tuple(r for r in RELATIONSHIPS if r != "owner")
LIVE_ONLY = ("introduce", "request_change", "request_forget")


def register_people_tools(registry: ToolRegistry, company: Company) -> None:
    book = company.book
    presence = company.presence
    clock = company.clock

    def asked(ref: str, sure: bool = False):
        asking = company.asking
        if asking is None:
            return None, {"ok": False, "error": "you take that only from someone who has just asked you, live"}
        person = book.find(ref)
        if person is None or person.id not in asking:
            return None, {"ok": False, "error": f"{person.label if person is not None else 'that person'} has not asked you that just now"}
        if sure and not (asking[person.id] and len(asking) == 1):
            return None, {"ok": False, "error": UNSEEN_REASON}
        return person, None

    def present(ref: str):
        person = book.find(ref)
        if person is None:
            return None, {"ok": False, "error": f"I don't know who {ref!r} is; use a name or a visitor label from the people here"}
        if person.id not in presence.here(clock.now()):
            return None, {"ok": False, "error": f"{person.label} is not here right now"}
        return person, None

    async def note_person(args: dict) -> dict:
        person, problem = present(args["person"])
        if problem:
            return problem
        now = clock.now()
        kind = args["kind"]
        if kind != "private" and not allowed(company.tier(person, now)).teach_self:
            return {"ok": False, "error": f"I'll get to know {person.label} a little better first"}
        if kind == "name":
            if not presence.seen_and_heard(person.id, now):
                return {"ok": False, "error": "a name comes from the person themselves, seen and heard"}
            person.set_name(args["text"])
        elif not person.note(kind, args["text"]):
            return {"ok": False, "error": "nothing to note"}
        company.dirty = True
        company.flush()
        return {"noted": kind, "person": person.label}

    async def note_promise(args: dict) -> dict:
        person, problem = present(args["person"])
        if problem:
            return problem
        try:
            due = due_at(clock.local(), args.get("minutes"), args.get("at"))
        except BadDue as error:
            return {"ok": False, "error": str(error)}
        promise = person.add_promise(args["who"], args["what"], due, clock.now())
        company.dirty = True
        company.flush()
        return {"promise": promise.what, "by": "them" if promise.by == "them" else "you", "due": clock.local(due).strftime("%a %H:%M")}

    async def introduce(args: dict) -> dict:
        now = clock.now()
        by, problem = asked(args["by"], sure=True)
        if problem:
            return problem
        if not presence.seen_and_heard(by.id, now):
            return {"ok": False, "error": "I need to see and hear the person doing the introducing"}
        tier = company.tier(by, now)
        if not at_least(tier, TRUSTED):
            return {"ok": False, "error": "I'm glad to meet everyone, but I learn names from people I know well"}
        ref = args.get("who") or ""
        person = book.find(ref) if ref else None
        if person is None:
            if company.visiting():
                return {"ok": False, "error": "I'm in visitors mode, so I'm not learning anyone new until it's switched off"}
            face = company.claim_new_face(now)
            if face is None:
                return {"ok": False, "error": "I can't see who you mean"}
            person = book.meet(now, face=face)
            presence.saw(person.id, now)
        if person.is_owner:
            return {"ok": False, "error": "I already know my owner"}
        person.set_name(args["name"])
        relationship = args.get("relationship") or None
        if relationship and at_least(tier, INNER) and relationship in INTRODUCED:
            person.relationship = relationship
            person.introduced_by = by.id
        company.dirty = True
        company.flush()
        return {"introduced": person.label, "relationship": person.relationship}

    async def note_impression(args: dict) -> dict:
        person, problem = present(args["person"])
        if problem:
            return problem
        try:
            evidence = book.evidence(person, args["quality"], args["good"], "model", args["reason"])
        except NotScored as error:
            return {"ok": False, "error": str(error)}
        company.dirty = True
        company.flush()
        return {"noted": evidence.quality, "counted": evidence.counted}

    async def request_change(args: dict) -> dict:
        person, problem = asked(args["person"], sure=True)
        if problem:
            return problem
        answer = company.requests.ask(person.id, args["kind"], args.get("target") or "", int(args.get("amount") or 0), args.get("text") or "", args.get("why") or "")
        company.dirty = company.dirty or answer.ok
        company.flush()
        return answer.as_dict()

    async def request_forget(args: dict) -> dict:
        person, problem = asked(args["person"], sure=True)
        if problem:
            return problem
        what = FORGET_WHAT[args["what"]]
        target = args.get("target") or ""
        answer = company.requests.ask(person.id, what, target if what in ("forget_person", "delete_drawing") else "", 0, target, args.get("why") or "")
        company.dirty = company.dirty or answer.ok
        company.flush()
        return answer.as_dict()

    async def my_standing(args: dict) -> dict:
        now = clock.now()
        person, problem = asked(args["person"])
        if problem:
            return problem
        if not presence.seen_and_heard(person.id, now):
            return {"ok": False, "error": "I only tell people their own standing, when I can see and hear them asking"}
        return {"for": person.label, "standing": standing_text(person, company.tier(person, now), now)}

    registry.register_action(Tool(
        "note_person",
        "Note something about a person who is here: their name or nickname (from them), a like, dislike or wish, or something told in private.",
        {
            "person": Param("string", "their name or visitor label", max_length=40),
            "kind": Param("enum", "what it is", choices=NOTE_KINDS),
            "text": Param("string", "the note, in a few words", max_length=120),
        },
        note_person,
    ))
    registry.register_action(Tool(
        "note_promise",
        "Write down a promise, theirs to you or yours to them, with when it is due. Plain code checks it at that time.",
        {
            "person": Param("string", "who the promise is with", max_length=40),
            "who": Param("enum", "who promised", choices=("them", "me")),
            "what": Param("string", "the promise, in a few words", max_length=120),
            "minutes": Param("number", "due in this many minutes", 1, 43200, required=False),
            "at": Param("string", "or due at this time of day, like 18:00", max_length=8, required=False),
        },
        note_promise,
    ))
    registry.register_action(Tool(
        "introduce",
        "Someone you know well introduces a person to you (\"this is my sister\").",
        {
            "by": Param("string", "who is doing the introducing", max_length=40),
            "name": Param("string", "the new person's name", max_length=40),
            "relationship": Param("enum", "who they are to the house", choices=INTRODUCED, required=False),
            "who": Param("string", "their visitor label, if you have met them", max_length=40, required=False),
        },
        introduce,
    ))
    registry.register_action(Tool(
        "note_impression",
        "Your own reading of how someone here behaved (counts half as much as what your senses notice).",
        {
            "person": Param("string", "who", max_length=40),
            "quality": Param("enum", "which quality", choices=QUALITIES),
            "good": Param("boolean", "true if it speaks for them, false if against"),
            "reason": Param("string", "what happened, in a few words", max_length=120),
        },
        note_impression,
    ))
    registry.register_action(Tool(
        "request_change",
        "Pass on someone's request to change you: a personality dial or value (inner circle), a favourite, preference or joke (trusted), or how you count a person (owner). You sleep on it and may say no.",
        {
            "person": Param("string", "who is asking", max_length=40),
            "kind": Param("enum", "what kind of change", choices=CHANGE_KINDS),
            "target": Param("string", "which dial, value, favourite, preference or person", max_length=40, required=False),
            "amount": Param("integer", "for a dial or value: how much up (positive) or down (negative)", -3, 3, required=False, default=0),
            "text": Param("string", "the favourite, setting, joke or tier", max_length=200, required=False),
            "why": Param("string", "their reason, in a few words", max_length=160, required=False),
        },
        request_change,
    ))
    registry.register_action(Tool(
        "request_forget",
        "Pass on someone's request that you forget a person, or delete a memory, drawing or photo. Only people you trust can ask; you decide overnight.",
        {
            "person": Param("string", "who is asking", max_length=40),
            "what": Param("enum", "what to forget", choices=tuple(FORGET_WHAT)),
            "target": Param("string", "which person, memory, drawing or photo (leave empty for 'forget me')", max_length=200, required=False),
            "why": Param("string", "their reason, in a few words", max_length=160, required=False),
        },
        request_forget,
    ))
    registry.register_action(Tool(
        "my_standing",
        "Tell a person how you see them, only when they ask about themselves.",
        {"person": Param("string", "who is asking about themselves", max_length=40)},
        my_standing,
    ))
