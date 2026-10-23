LINES = {
    "wait_for_me": "Wait for me!",
    "coming": "I'm coming!",
    "thanks": "Thanks for waiting!",
    "who": "{name}?",
    "call": "{name}?",
    "waiting": "I'll wait here for you, {name}.",
    "found": "There you are!",
    "stuck": "I'm stuck {where}. Could you help me?",
    "stuck_plain": "I'm stuck. Could you give me a hand?",
    "stairs": "I can't do stairs, so I'll wait here.",
    "put_down": "Thanks! Where did you go?",
}

NOTES = {
    "glass": "you bumped into something you could not see, maybe glass, and marked it on your map",
    "stairs": "{name} went where there is a drop, probably stairs, and you cannot do stairs",
    "threshold": "you crossed a little bump on the floor slowly and square on",
    "shortcut": "you took a short cut through space you had already seen was clear",
    "wait_for_me": "you fell behind {name} and called out for them to wait",
    "thanks": "{name} waited for you, and you thanked them",
    "unsure": "you were not sure which person was {name}, so you slowed down and asked",
    "carried": "someone carried you, and you kept track of where you were from your phone's motion",
    "stuck": "you got stuck {where} and tried to get yourself free",
    "recovered": "you got yourself unstuck",
    "animal": "the {where} is close ahead, so you slowed right down and keep your distance",
    "animal_blocked": "the {where} stayed in your way, so you stopped",
    "life": "the {where} is close ahead, so you slowed right down and are going round it",
    "life_accident": "you may have gone over a small {where} you saw a moment ago; you did not mean to, and you will go more slowly there from now on",
    "plant_bumped": "you bumped the {where}; you did not mean to, and you will go more slowly there from now on",
}


def line(kind: str, name: str = "", where: str = "") -> str:
    return LINES.get(kind, "").format(name=name or "Hello", where=where).strip()


def note(kind: str, name: str = "", where: str = "") -> str:
    return NOTES.get(kind, kind).format(name=name or "them", where=where or "somewhere").strip()
