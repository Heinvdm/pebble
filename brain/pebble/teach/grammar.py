from ..activities.card import THINK_SET, Card

KINDS = ("move", "procedure", "route", "concept", "word", "way", "habit")
ABOUT_CHARS = "a-zA-Z0-9' ,.?!-"
VALUE_CHARS = "a-zA-Z0-9' ,.?!:;_{}()/+-"
THINK_MOST = 300
STEPS_MOST = 12
SKIPPED = ("root", "cant", "plan", "steps", "step")


def _key(name: str) -> str:
    return '"\\"' + name + '\\":" ws'


def grammar(card: Card, kinds: tuple = ()) -> str:
    allowed = tuple(kind for kind in kinds if kind in KINDS) or KINDS
    rules: dict = {}
    for line in card.grammar().splitlines():
        if " ::= " not in line:
            continue
        name, body = line.split(" ::= ", 1)
        if name not in SKIPPED:
            rules[name] = body
    blocks = [name for name in rules if name.startswith("b") and name[1:].isdigit()]
    rules["root"] = '"{" ws tthink "," ws tkind "," ws tname "," ws taliases "," ws tabout "," ws tsteps "," ws tslots ws "}"'
    rules["tthink"] = _key("think") + ' "\\"" [' + THINK_SET + "]{0," + str(THINK_MOST) + '} "\\""'
    rules["tkind"] = _key("kind") + " (" + " | ".join('"\\"' + kind + '\\""' for kind in allowed) + ")"
    rules["tname"] = _key("name") + " words"
    rules["taliases"] = _key("aliases") + ' "[" ws (words (ws "," ws words){0,3})? ws "]"'
    rules["tabout"] = _key("about") + ' "\\"" [' + ABOUT_CHARS + ']{1,160} "\\""'
    rules["tsteps"] = _key("steps") + ' "[" ws tstep (ws "," ws tstep){0,' + str(STEPS_MOST - 1) + '} ws "]"'
    rules["tstep"] = " | ".join(blocks + ["treq"])
    rules["treq"] = '"{" ws ' + _key("do") + ' "\\"request\\"" ws "," ws ' + _key("request") + ' jobject ws "}"'
    rules["tslots"] = _key("slots") + ' "{" ws (tslot (ws "," ws tslot){0,3})? ws "}"'
    rules["tslot"] = '"\\"" [a-z_]{1,16} "\\":" ws "[" ws jstring (ws "," ws jstring){0,7} ws "]"'
    rules["jobject"] = '"{" ws (jpair (ws "," ws jpair){0,11})? ws "}"'
    rules["jpair"] = 'jstring ws ":" ws jvalue'
    rules["jvalue"] = 'jobject | jarray | jstring | jnum | "true" | "false"'
    rules["jarray"] = '"[" ws (jvalue (ws "," ws jvalue){0,7})? ws "]"'
    rules["jstring"] = '"\\"" [' + VALUE_CHARS + ']{0,80} "\\""'
    rules["jnum"] = '"-"? [0-9]{1,5} ("." [0-9]{1,3})?'
    return "\n".join(f"{name} ::= {body}" for name, body in rules.items()) + "\n"
