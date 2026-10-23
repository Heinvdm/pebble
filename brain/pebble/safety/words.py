import re
from dataclasses import dataclass

_CLEAN = re.compile(r"[^a-z0-9' ]+")
_DISTRESS = re.compile(
    r"\b(i(?:'ve| have)? fallen|i fell( over| down)?|i can'?t get up|i'?m hurt|i(?:'ve| have) hurt myself|i'?m bleeding|i can'?t breathe|call (?:an |the )?ambulance|call (?:111|911|999|112|the police|the fire brigade|an? doctor)|i'?m stuck|i need a doctor)\b"
)
_HELP_WORD = re.compile(r"\bhelp\b")
_REQUEST = re.compile(
    r"\bhelp(?:\s+me)?(?:\s+out)?\s+(?:to\s+|with\s+)?(find|with|carry|get|look|move|choose|do|make|fix|understand|cook|clean|pick|work|figure|decide|set|put|bring|lift|open|read|write|learn|practise|practice|remember|think|out)\b"
)
_NOT_URGENT = re.compile(
    r"\b(can|could|would|will|may|might|should|shall)\s+(you|u|i|we|pebble)\s+(please\s+)?help\b|\bhelp(ful|fully|ed|ing|less|er|ers)\b|\bhelps\b|\bhelp yourself\b|\bthanks? (you )?for (the |your |all the )?help\b|\bno help\b|\bhelp desk\b|\bself.help\b|\bi'?ll help\b|\blet me help\b|\bto help\b|\bdon'?t need (any )?help\b|\bnot help\b|\bhelp (him|her|them|you|it)\b"
)
_STAND_DOWN = re.compile(
    r"\b(it'?s (?:all )?(?:fine|ok(?:ay)?|all right|alright|nothing|safe|sorted|under control|just (?:the )?(?:toast|cooking|a test|testing|steam|the oven))"
    r"|(?:it was|that was|that'?s) (?:just )?(?:the )?(?:toast|cooking|a test|nothing|steam|the oven|me)"
    r"|false alarm|i'?m (?:fine|ok(?:ay)?|all right|alright|good|not hurt)|we'?re (?:fine|ok(?:ay)?|all right|alright|safe)"
    r"|all (?:good|clear|safe)|no worries|stand down|you can stop|stop (?:the |your |that )?(?:alarm|beeping|noise|siren)|turn (?:it|that|the alarm|your alarm) off"
    r"|that'?s enough|never ?mind|calm down|just testing|testing the alarm|no (?:i'?m|we'?re) (?:fine|ok(?:ay)?)|don'?t worry|nothing'?s wrong|i'?ve got it|i'?m on it|i'?m dealing with it)\b"
)
_QUIET = re.compile(r"^(?:(?:be|keep) quiet|quiet|shush|hush|shh+|shut up|enough|ok(?:ay)? ok(?:ay)?)$")
_YES = re.compile(r"^(?:yes|yeah|yep|ja|please|help|yes please|i do|i need help|help me)$")
_FIRE = re.compile(r"^(?:(?:there'?s a )?fire(?: fire)*|everyone out|get out)$")
_SURE = re.compile(r"^(?:yes|yeah|yep|yup|ja|sure|really|definitely|i promise|yes really|yes i am|yes it is|yes i'?m sure|yes i am sure|i'?m sure|i am sure|it really is|it is|really fine|yes (?:it'?s|i'?m) fine)$")


@dataclass(frozen=True)
class Reading:
    help: float = 0.0
    stand_down: bool = False
    quiet: bool = False
    yes: bool = False
    name_only: bool = False
    fire: bool = False
    sure: bool = False


def clean(text: str) -> str:
    return " ".join(_CLEAN.sub(" ", str(text or "").lower().replace("’", "'")).split())


def read_line(text: str, name: str = "pebble") -> Reading:
    words = clean(text)
    if not words:
        return Reading()
    name = clean(name) or "pebble"
    tokens = words.split()
    without_name = [t for t in tokens if t not in (name, "hey", "oi", "hi")]
    name_only = name in tokens and not without_name
    stand_down = bool(_STAND_DOWN.search(words))
    quiet = bool(_QUIET.match(" ".join(without_name)))
    yes = bool(_YES.match(" ".join(without_name)))
    fire = bool(_FIRE.match(" ".join(without_name)))
    level = 0.0
    if _DISTRESS.search(words):
        level = 0.9
    elif _HELP_WORD.search(words) and not _NOT_URGENT.search(words) and not _REQUEST.search(words):
        level = 0.9 if len(without_name) <= 5 else 0.6
    if stand_down and level < 0.9:
        level = 0.0
    sure = bool(_SURE.match(" ".join(without_name)))
    return Reading(level, stand_down and level < 0.9, quiet, yes, name_only, fire, sure)
