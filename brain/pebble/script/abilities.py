NEEDED = object()

SIGNATURES = {
    "do": (("request", NEEDED),),
    "say": (("text", NEEDED),),
    "say_to": (("who", NEEDED), ("text", NEEDED)),
    "ask": (("who", NEEDED), ("question", NEEDED), ("choices", None), ("wait", 20)),
    "face": (("expression", NEEDED),),
    "draw": (("scene", NEEDED),),
    "chirp": (("pattern", NEEDED),),
    "hum": (("tune", NEEDED),),
    "look": (),
    "where": (("thing", NEEDED),),
    "who_here": (),
    "room": (),
    "state": (("name", NEEDED), ("value", None), ("who", None), ("place", None), ("thing", None), ("at", None), ("end", None), ("day", None), ("minutes", None), ("level", None), ("what", None)),
    "now": (),
    "today": (),
    "feel": (),
    "dial": (("name", NEEDED),),
    "tune": (("name", NEEDED), ("value", NEEDED), ("why", "")),
    "keep": (("key", NEEDED), ("value", NEEDED)),
    "kept": (("key", NEEDED), ("default", None)),
    "note": (("text", NEEDED),),
    "wait": (("seconds", NEEDED),),
    "chance": (("p", NEEDED),),
    "pick": (("items", NEEDED),),
    "finish": (),
}
ABILITIES = frozenset(SIGNATURES)
GROUPS = {
    "do": ("do",),
    "say": ("say", "say_to"),
    "ask": ("ask",),
    "face": ("face",),
    "draw": ("draw",),
    "chirp": ("chirp",),
    "hum": ("hum",),
    "look": ("look", "where", "who_here", "room", "state"),
    "dial": ("dial",),
    "tune": ("tune",),
}
GROUP_OF = {name: group for group, names in GROUPS.items() for name in names}
FREE = frozenset({"keep", "kept", "now", "today", "feel", "note", "wait", "chance", "pick", "finish"})
LOCAL = frozenset({"finish"})
COUNTED = frozenset(GROUP_OF) | {"note"}
SPEAKING = frozenset({"say", "say_to", "ask"})
QUERIES = {"look": [], "where": None, "who_here": [], "room": None, "state": "unsure", "dial": None, "feel": {}}
MOVING = frozenset({"do"})
FOR_OTHERS = frozenset({"say_to", "ask"})
GAME = frozenset({"say", "say_to", "ask", "face", "draw", "chirp", "hum", "look", "where", "who_here", "room", "state"})
HANDLERS = {
    "on_start": (),
    "on_heard": ("who", "words"),
    "on_seen": ("thing", "place"),
    "on_arrives": ("who",),
    "on_leaves": ("who",),
    "on_sound": ("thing",),
    "on_at": ("time",),
    "on_every": ("time",),
    "on_feeling": ("feeling", "level"),
    "on_done": ("what", "how"),
    "on_stop": (),
}
WANTED = {"heard": "on_heard", "seen": "on_seen", "arrives": "on_arrives", "leaves": "on_leaves", "sound": "on_sound", "at": "on_at", "every": "on_every", "feeling": "on_feeling", "done": "on_done"}
FEELINGS = ("happy", "sad", "bored", "lonely", "tired", "curious", "scared", "excited", "calm", "restless")
STATES = ("present", "in_room", "after", "before", "time_between", "day_is", "heard_lately", "seen_lately", "battery_below", "doing", "cooking", "quiet_hours", "room_quiet")
STATE_MAIN = {"present": "who", "in_room": "place", "after": "at", "before": "at", "time_between": "at", "day_is": "day", "heard_lately": "thing", "seen_lately": "thing", "battery_below": "level", "doing": "what", "room_quiet": "minutes"}
CAN = {
    "do": "move about",
    "say": "talk",
    "ask": "ask questions and listen to the answer",
    "face": "change my face",
    "draw": "draw on my screen",
    "chirp": "chirp",
    "hum": "hum",
    "look": "look",
    "dial": "read my own settings",
    "tune": "change my own settings",
}
CARD = """Abilities (only those in USES, plus keep, kept, now, today, feel, note, wait, chance, pick and finish, which every script has):
- do(request) [USES "do"]: a plain request for your body: "go to the kitchen", "turn left 90 degrees", "come to me", "find the ball", "check the house". Returns "done", "stopped" or "refused: why".
- say(text), say_to(who, text) [USES "say"]: speak, or speak to one person ("me" is the person the script is for). Returns "done" or "refused: why".
- ask(who, question, choices=None, wait=20) [USES "ask"]: ask one person; returns their answer as text (one of choices if given), or None.
- face(expression) [USES "face"]: neutral, happy, curious, thinking, sleepy, sad, surprised, scared, grumpy, love, dizzy or mischief. draw(scene) [USES "draw"]: a short picture in words.
- [USES "look"] look(): everything in view, people and things together ("ina", "someone", "cat"). who_here(): just the people here. where(thing): the room it was last seen in, or None. room(): your room, or None. state(name, value): True, False or "unsure", for present (who), in_room (place), after and before ("HH:MM"), day_is (day), seen_lately and heard_lately (thing), cooking and quiet_hours.
- now(): "HH:MM". today(): "YYYY-MM-DD". feel(): your mood and needs, 0 to 1. dial(name), tune(name, value, why) [USES "dial", "tune"]: your own settings.
- keep(key, value), kept(key, default=None): this script's saved values. note(text): a journal line. wait(seconds): pause, at most 3600. chance(p): True with chance p. pick(items): one of them. finish(): end now."""
SHAPE = """Shape of a script:
ABOUT = "one plain line saying what it does"
USES = ["say"]
FOR = "alex"   (who it is for; leave it out for your own scripts)
UNTIL = "21:00"   ("HH:MM", "YYYY-MM-DD HH:MM" or "2 hours"; "ongoing" only for your own)
WANTS = {"seen": ["cat"], "at": ["21:00"]}
Events and their handlers: heard ["me"], on_heard(who, words); seen [things], on_seen(thing, place); arrives and leaves [people or "anyone"], on_arrives(who), on_leaves(who); sound, on_sound(thing); at ["HH:MM"], on_at(time); every [seconds], on_every(time); feeling, on_feeling(feeling, level); done (an activity of yours ended), on_done(what, how). on_start() runs once at the start, for anything to do straight away; on_stop() runs at the end. Names come in small letters ("sam"); time is text ("21:00")."""


def group_of(name: str) -> str:
    return GROUP_OF.get(name, name)


def needs_uses(name: str) -> bool:
    return name in GROUP_OF


def allowed_by(uses, name: str) -> bool:
    if name in FREE:
        return True
    groups = {group_of(str(u)) for u in uses or ()}
    return group_of(name) in groups


def can_words(groups) -> str:
    shown = [CAN[g] for g in ("look", "say", "ask", "face", "draw", "chirp", "hum", "dial", "tune", "do") if g in groups]
    if not shown:
        return "It only keeps its own notes"
    if len(shown) == 1:
        return f"It can only {shown[0]}"
    return f"It can only {', '.join(shown[:-1])} and {shown[-1]}" if "do" not in groups else f"It can {', '.join(shown[:-1])} and {shown[-1]}"
