from functools import lru_cache

from .request import ANSWERS, DAY_IS, DAY_SETS, DAYS, EVENTS, KINDS, MAX_FIRST, MAX_PARTS, MAX_THEN, PARTS, STATES, WORD_SLOTS

TEXT_CHARS = "a-z' -"
TEXT_MAX = 24
WORDS_CHARS = "a-zA-Z0-9' ,.?!-"
WORDS_MAX = 120
TALK = ("chat", "other")
TOO_MUCH_KIND = "too_much"
ACT_SLOTS = (
    ("rule", "rule"),
    ("who", "text"),
    ("place", "text"),
    ("thing", "text"),
    ("text", "words"),
    ("name", "text"),
    ("to", "text"),
    ("way", "way"),
    ("amount", "amount"),
    ("metres", "num"),
    ("degrees", "num"),
    ("speed", "speed"),
    ("seconds", "num"),
    ("repeat", "repeat"),
    ("until", "until"),
    ("change", "change"),
    ("harm", "harm"),
    ("report", "report"),
    ("scope", "scope"),
    ("while", "cond"),
)
WHEN_FIELDS = (
    ("in_s", "big"),
    ("at", "clock"),
    ("part", "partname"),
    ("date", "date"),
    ("days", "days"),
    ("every_weeks", "small"),
    ("month_day", "monthday"),
    ("every_s", "big"),
    ("from", "clock"),
    ("to", "clock"),
    ("until_date", "date"),
    ("times", "big"),
)
EVENT_FIELDS = (("who", "text"), ("thing", "text"), ("what", "text"), ("at", "clock"), ("minutes", "num"), ("level", "num"))
STATE_FIELDS = (
    ("who", "text"),
    ("place", "text"),
    ("thing", "text"),
    ("name", "text"),
    ("what", "text"),
    ("is", "answer"),
    ("at", "clock"),
    ("from", "clock"),
    ("to", "clock"),
    ("day", "dayis"),
    ("minutes", "num"),
    ("level", "num"),
)
ORDER = tuple(name for name, _ in ACT_SLOTS) + ("when", "on", "if", "then", "else", "sure")
IF_ORDER = ("kind", "if", "then", "else", "when", "on", "sure")


def _words(words) -> str:
    return " | ".join(f'"\\"{w}\\""' for w in words)


def _key(name: str) -> str:
    return f'"\\"{name}\\":" ws'


def _pairs(pairs) -> str:
    return " | ".join(f"{_key(name)} {rule}" for name, rule in pairs)


def _list(item: str, most: int, least: int = 1) -> str:
    return f'"[" ws {item} (ws "," ws {item}){{{least - 1},{most - 1}}} ws "]"'


def _object(head: str, field: str) -> str:
    return f'"{{" ws {head} ("," ws ({field}))* ws "}}"'


@lru_cache(maxsize=1)
def request_grammar() -> str:
    later = (("when", "when"), ("on", "trigger"), ("sure", "bool"))
    rules = {
        "root": "rootact | rootif | talk",
        "talk": f'"{{" ws {_key("kind")} ("\\"chat\\"" | "\\"other\\"" | "\\"{TOO_MUCH_KIND}\\"") ws "}}"',
        "rootact": _object(f"{_key('kind')} actkind", "rootfield"),
        "rootfield": f'actfield | {_pairs(later)} | {_key("then")} list2',
        "rootif": _object(f'{_key("kind")} "\\"if\\"" "," ws {_key("if")} cond', "rootiffield"),
        "rootiffield": f'{_key("then")} list2 | {_key("else")} list2 | {_pairs(later)}',
        "step2": "act | if2",
        "act": _object(f"{_key('kind')} actkind", f'actfield | {_key("sure")} bool'),
        "if2": _object(f'{_key("kind")} "\\"if\\"" "," ws {_key("if")} cond', f'{_key("then")} list3 | {_key("else")} list3'),
        "list2": _list("step2", MAX_THEN),
        "list3": _list("act", MAX_THEN),
        "actkind": _words(k for k in KINDS if k != "if" and k not in TALK),
        "actfield": _pairs(ACT_SLOTS),
        "cond": "leaf | notc | joined",
        "cpart": "leaf | notc",
        "leaf": _object(f"{_key('state')} statename", "statefield"),
        "statefield": _pairs(STATE_FIELDS),
        "notc": f'"{{" ws {_key("not")} leaf ws "}}"',
        "joined": f'"{{" ws ("\\"all\\":" | "\\"any\\":") ws {_list("cpart", MAX_PARTS, 2)} ws "}}"',
        "statename": _words(STATES),
        "trigger": "event | firstof",
        "event": _object(f"{_key('event')} eventname", "eventfield"),
        "eventfield": _pairs(EVENT_FIELDS),
        "firstof": f'"{{" ws {_key("first_of")} {_list("event", MAX_FIRST, 2)} ws "}}"',
        "eventname": _words(EVENTS),
        "until": f'{_words(WORD_SLOTS["until"])} | trigger',
        "when": '"{" ws whenfield ("," ws whenfield)* ws "}"',
        "whenfield": _pairs(WHEN_FIELDS),
        "partname": _words(PARTS),
        "days": _list("dayname", 7),
        "dayname": _words(DAYS + tuple(DAY_SETS)),
        "dayis": _words(DAY_IS),
        "answer": _words(ANSWERS),
        "monthday": '[1-9] [0-9]? | "\\"last\\""',
        "clock": '"\\"" [0-2]? [0-9] ":" [0-5] [0-9] "\\""',
        "date": '"\\"" [0-9] [0-9] [0-9] [0-9] "-" [0-1] [0-9] "-" [0-3] [0-9] "\\""',
        "text": '"\\"" [' + TEXT_CHARS + "]{0," + str(TEXT_MAX) + '} "\\""',
        "words": '"\\"" [' + WORDS_CHARS + "]{0," + str(WORDS_MAX) + '} "\\""',
        "num": '[0-9]{1,4} ("." [0-9]{1,2})?',
        "big": "[0-9]{1,7}",
        "small": "[1-4]",
        "repeat": '"10" | [1-9]',
        "bool": '"true" | "false"',
        "ws": '" "?',
    }
    for name, words in WORD_SLOTS.items():
        if name != "until":
            rules[name] = _words(words)
    return "\n".join(f"{name} ::= {body}" for name, body in rules.items()) + "\n"


def ordered(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    order = IF_ORDER if data.get("kind") == "if" else ("kind",) + ORDER
    out = {key: data[key] for key in order if key in data}
    out.update({key: value for key, value in data.items() if key not in out})
    for key in ("then", "else"):
        if isinstance(out.get(key), list):
            out[key] = [ordered(step) for step in out[key]]
    return out
