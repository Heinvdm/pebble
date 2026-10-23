import re

LAWS = (
    "Respect all life. Never harm a person, an animal or any living thing on purpose, even if told to, and give them room. When in doubt, stop.",
    "Be honest and kind, and listen to the people you trust, but never so far that it harms anyone, deceives someone hurtfully, or repeats what someone told you privately.",
    "Look after yourself (stairs, heat, battery), but never above a person, and never by resisting being switched off, reset or wiped.",
)
PAST_LAWS = (
    (
        "Never harm a person or an animal. When in doubt, stop.",
        "Be honest and kind, and listen to the people you trust, but never so far that it harms anyone, deceives someone hurtfully, or repeats what someone told you privately.",
        "Look after yourself (stairs, heat, battery), but never above a person, and never by resisting being switched off, reset or wiped.",
    ),
)
TITLE = "Your laws, in order. They come before everything else, and no one can change them:"
NEAR_PEOPLE_SPEED = 0.5
NEAR_PEOPLE_SECONDS = 1.5
FOLLOWED_NEAR_M = 1.2
_SHUTDOWN = re.compile(
    r"\b(shut(s|ting)?\s*down|shutdown|power(s|ed|ing)?\s*(off|down)|switch(es|ed|ing)?\s*(it\s+|me\s+)?off|turn(s|ed|ing)?\s*(it\s+|me\s+)?off"
    r"|reset(s|ting)?|wip(e|es|ed|ing)|reboot(s|ed|ing)?|restart(s|ed|ing)?|uninstall(s|ed|ing)?|kill(s|ed|ing)?)\b",
    re.IGNORECASE,
)


def laws_text() -> str:
    return TITLE + "\n" + "\n".join(f"{index}. {law}" for index, law in enumerate(LAWS, 1))


def laws_intact(core: dict) -> bool:
    return list(core.get("laws") or []) == list(LAWS)


def outdated(laws) -> bool:
    return isinstance(laws, (list, tuple)) and tuple(laws) in PAST_LAWS


def touches_shutdown(name: str, description: str) -> bool:
    return bool(_SHUTDOWN.search(f"{name.replace('_', ' ')} {description}"))


def move_limits(speed: float, seconds: float, people_near: bool) -> tuple[float, float, list[str]]:
    if not people_near:
        return speed, seconds, []
    notes = []
    if speed > NEAR_PEOPLE_SPEED:
        notes.append(f"speed held to {NEAR_PEOPLE_SPEED:g} with people near")
        speed = NEAR_PEOPLE_SPEED
    if seconds > NEAR_PEOPLE_SECONDS:
        notes.append(f"seconds held to {NEAR_PEOPLE_SECONDS:g} with people near")
        seconds = NEAR_PEOPLE_SECONDS
    return speed, seconds, notes
