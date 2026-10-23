import re
from dataclasses import dataclass

OWN = "pebble"
CONTRACTIONS = (
    (r"\bthat's\b", "that is"),
    (r"\bthats\b", "that is"),
    (r"\bit's\b", "it is"),
    (r"\bhere's\b", "here is"),
    (r"\bheres\b", "here is"),
    (r"\blet's\b", "let us"),
    (r"\blets\b", "let us"),
    (r"\bi'm\b", "i am"),
    (r"\bim\b", "i am"),
    (r"\bi'll\b", "i will"),
    (r"\bisn't\b", "is not"),
    (r"\bdon't\b", "do not"),
    (r"\bdont\b", "do not"),
    (r"\bwe're\b", "we are"),
    (r"\byou're\b", "you are"),
    (r"\bthis'll\b", "this will"),
    (r"\bi'd\b", "i would"),
    (r"\bwhat's\b", "what is"),
)
FILL = r"(?:(?:okay|ok|right|alright|now|so|hey|well|and|oh|um|yes|yeah|good)\s+)*"
POLITE = r"(?:(?:can|could|would|will) you\s+)?(?:please\s+)?"
START = re.compile(
    r"^" + FILL + r"(?:i am (?:going to|gonna) |i want to |let me |i will |let us |can i |i would like to |time to )?"
    r"(?:teach you|show you|teach)(?: (?P<plain>something|something new|a new trick|a trick|a thing|a move|a new move|a new thing|a dance|a new dance|a game|a new game|a few things|some things)"
    r"| how to (?P<how>.+)| (?P<what>(?:the|my|your|our|a|an) .+))?$"
)
WATCH = re.compile(r"^" + FILL + r"(?:watch this|watch me do this|learn this|here is how|watch and learn|learn from me|watch closely|pay attention|copy this|learn this one)$")
END = re.compile(
    r"^" + FILL + r"(?:that is it|that is all|that is how|that is how you do it|that is the lot|and that is it|all done|done|finished|the end|that will do|we are done|that is everything)"
    r"(?:,? (?:and )?(?:call it|it is called|name it|that is called|that is the|we call it) (?P<name>.+))?$"
)
NAMED_END = re.compile(r"^" + FILL + r"(?:call it|it is called|name it|that is called|we call it|that is how you do|that is how to do|that is how you|that is how to) (?P<name>.+)$")
UNDO = re.compile(r"^(?:no,? )?(?:scrap that|scrap that last bit|scrap the last bit|undo that|undo|not that last bit|forget that last bit|forget the last bit|take that back|scratch that|delete that|leave that out|leave that last bit out|not that bit|drop that|drop the last bit|ignore that|ignore that last bit|that last bit was wrong)$")
AGAIN = re.compile(r"^(?:no,? )?(?:let us )?(?:start again|start over|from the top|start from the beginning|begin again|start from scratch|let us try that again from the start|scrap all that)$")
LEAD = re.compile(r"^" + FILL + r"(?:follow me and learn (?:the way|how to get) to|follow me and i will show you the way to|learn the way to|i will show you the way to|let me show you the way to|this is the way to|follow me,? this is the way to) (?P<to>.+)$")
LEAD_TO = re.compile(r"^" + FILL + r"follow me to (?P<to>.+?) and learn the way$")
CARRY = re.compile(r"^" + FILL + r"(?:this is|here is|this will be|this is going to be) (?:where you (?P<where>.+)|your (?P<spot>.+?) spot|the spot (?:where you |for )(?P<for>.+)|your spot for (?P<spot_for>.+))$")
SHOW = re.compile(r"^" + FILL + r"(?:this is what (?P<what>.+?) looks? like|this is how (?P<how>.+?) looks?|that is what (?P<that>.+?) looks? like|(?:this|this one|that one|this here) is (?P<not>not |also |another |more )?(?P<plain>.+?)(?: too| as well)?)$")
WORD = re.compile(r"^" + FILL + r"(?:when|whenever|if|every time|each time|any time) i say (?P<alias>[a-z][a-z' ]{1,24}?),? (?:you |please |then |i want you to |you should )?(?P<do>.+)$")
WORD_COMMA = re.compile(r"^" + FILL + r"(?:when|whenever|if|every time|each time|any time) i say (?P<alias>[a-z][a-z' ]{1,24}), (?:you |please |then |i want you to |you should )?(?P<do>.+)$")
MEANS = re.compile(r"^" + FILL + r"(?P<alias>[a-z][a-z' ]{1,24}?) means (?:you |to |that you )?(?P<do>.+)$")
WAY = re.compile(r"^" + FILL + r"(?:when|whenever|every time|each time) i (?P<event>come home|get home|come in|get back|come back|arrive|walk in|come back home|get in|wake up|get up|go to bed|leave|go out|head out),? (?P<do>.+)$")
HABIT = re.compile(r"^" + FILL + r"(?:whenever|every time|each time|any time|anytime) (?P<event>.+?), (?P<do>.+)$")
EXPLAIN = re.compile(r"^" + FILL + r"(?:to do|to) (?P<name>.+?), (?:you |first you |first |just )(?P<how>.+)$")
HOW_TO = re.compile(r"^" + FILL + r"(?:here is how to|this is how to|this is how you do|the way to do) (?P<name>.+?)(?::|,) (?:you |first you |first )?(?P<how>.+)$")
COPY = re.compile(r"^" + FILL + r"(?:let us play )?(?:copy me|copy what i do|do what i do|copy my moves|mirror me|copycat|copy cat|play copy me|be my copycat)$")
KEEP = re.compile(r"^" + FILL + r"(?:remember that|keep that|remember those moves|learn that|remember that one|keep those moves)(?: as (?P<name>.+)| and call it (?P<called>.+))?$")
LIST = re.compile(r"^" + FILL + r"(?:what have i taught you|what have you learned|what have you learnt|what have you been taught|what do you know how to do|what did i teach you|what have we taught you|what things have you learned|what have people taught you|what can you do)$")
SHOW_ENTRY = re.compile(r"^" + FILL + POLITE + r"(?:show me|let me see|let us see) (?:the |your |how you do the |how you do your |how to )?(?P<name>.+)$")
FORGET = re.compile(r"^" + FILL + POLITE + r"(?:forget|unlearn|you can forget|stop doing|delete) (?:the |your |how to do the |how to do |how to |about the |what )?(?P<name>.+?)(?: means)?$")
CARRY_ON = re.compile(r"^" + FILL + r"(?:let us )?(?:carry on|keep going|continue|go on) (?:teaching|with the lesson|the lesson|learning|with what we were doing)(?: (?:the |with the )?(?P<name>.+))?$")
SKIP = re.compile(r"^" + FILL + POLITE + r"(?:do |run |go on )?(?:the |your )?(?P<name>.+?),? but (?:skip|miss out|leave out|do not do|do not go to|without) (?:the )?(?P<what>.+)$")
FROM_NOW = re.compile(r"^" + FILL + r"from now on,? (?:skip|miss out|leave out|do not go to|do not do|stop going to|you can skip) (?:the )?(?P<what>.+?)(?: (?:in|on|from|when you do) (?:the |your )?(?P<name>.+))?$")
IS_A = re.compile(r"^(?:the|my|our|your|that|this) (?P<subject>[a-z']+(?: [a-z']+)?) is (?P<not>not )?(?:a |an |the |my |our |your )?(?P<what>[a-z']+(?: [a-z']+){0,2})$")
NAME_TAIL = re.compile(r"\s+(?:please|for me|for us|now|then|ok|okay)$")
ARTICLE = re.compile(r"^(?:the|a|an|your|my|our|this|that|some)\s+")
SAID_LIKE = re.compile(r"\b(?:like this|like so|this way|the way i show you|the way i do)$")


@dataclass(frozen=True)
class Said:
    kind: str
    name: str = ""
    words: str = ""
    extra: str = ""
    negative: bool = False


def clean(text: str, own: str = OWN) -> str:
    said = str(text or "").lower().replace("’", "'").replace("‘", "'")
    for pattern, replacement in CONTRACTIONS:
        said = re.sub(pattern, replacement, said)
    said = re.sub(r"[^a-z0-9' ,:]+", " ", said)
    words = [w for w in said.replace(",", " , ").replace(":", " : ").split() if w.strip("'") and w not in (own, f"{own}'s", f"{own},")]
    said = " ".join(words).replace(" , ", ", ").replace(" : ", ": ")
    said = re.sub(r"(?:^[,: ]+|[,: ]+$)", "", said)
    return re.sub(r"\s+", " ", said).strip()


def bare(text: str, own: str = OWN) -> str:
    return clean(text, own).replace(",", "").replace(":", "")


def name_from(text: str) -> str:
    name = bare(text)
    for _ in range(3):
        before = name
        name = NAME_TAIL.sub("", name).strip()
        name = ARTICLE.sub("", name).strip()
        if name == before:
            break
    return name[:40]


def read(text: str, own: str = OWN) -> Said | None:
    said = clean(text, own)
    flat = said.replace(",", "").replace(":", "")
    if not flat:
        return None
    if UNDO.match(flat):
        return Said("undo")
    if AGAIN.match(flat):
        return Said("again")
    found = END.match(flat)
    if found:
        return Said("end", name_from(found.group("name") or ""))
    found = NAMED_END.match(flat)
    if found:
        return Said("end", name_from(found.group("name")))
    found = COPY.match(flat)
    if found:
        return Said("copy")
    found = KEEP.match(flat)
    if found:
        return Said("keep", name_from(found.group("name") or found.group("called") or ""))
    found = LIST.match(flat)
    if found:
        return Said("list")
    found = LEAD.match(flat) or LEAD_TO.match(flat)
    if found:
        return Said("lead", name_from(found.group("to")), found.group("to"))
    found = START.match(flat)
    if found:
        what = found.group("how") or found.group("what") or ""
        return Said("start", name_from(what) if what else "", what, "how" if found.group("how") else "")
    if WATCH.match(flat):
        return Said("start")
    found = CARRY_ON.match(flat)
    if found:
        return Said("carry_on", name_from(found.group("name") or ""))
    found = WORD_COMMA.match(said) or WORD.match(said) or MEANS.match(flat)
    if found:
        alias = name_from(found.group("alias"))
        doing = found.group("do").strip(" ,.")
        if alias and doing:
            return Said("word", alias, doing)
    found = WAY.match(said)
    if found:
        doing = found.group("do").strip(" ,.")
        return Said("way", found.group("event"), doing, "shown" if SAID_LIKE.search(doing) else "")
    found = HABIT.match(said)
    if found:
        return Said("habit", "", found.group("do").strip(" ,."), found.group("event").strip(" ,."))
    found = EXPLAIN.match(said) or HOW_TO.match(said)
    if found:
        return Said("explain", name_from(found.group("name")), found.group("how").strip(" ,."))
    found = FROM_NOW.match(flat)
    if found:
        return Said("from_now", name_from(found.group("name") or ""), extra=name_from(found.group("what")))
    found = SKIP.match(flat)
    if found:
        return Said("skip", name_from(found.group("name")), extra=name_from(found.group("what")))
    found = CARRY.match(flat)
    if found:
        where = found.group("where") or found.group("for") or found.group("spot_for") or ""
        spot = found.group("spot") or ""
        return Said("carry", spot_name(spot, where), where or spot)
    found = SHOW.match(flat)
    if found:
        what = found.group("what") or found.group("how") or found.group("that") or found.group("plain") or ""
        negative = (found.group("not") or "").strip() == "not"
        return Said("show", concept_name(what), what, negative=negative)
    found = IS_A.match(flat)
    if found:
        subject, what = found.group("subject"), found.group("what")
        return Said("show", concept_name(what), f"{subject} is {what}", subject, negative=bool(found.group("not")))
    return None


def entry_named(text: str, pattern: re.Pattern, own: str = OWN) -> str:
    found = pattern.match(bare(text, own))
    if found is None:
        return ""
    return name_from(found.group("name"))


def spot_name(spot: str, where: str) -> str:
    if spot:
        return f"{name_from(spot)} spot"
    words = [w for w in re.findall(r"[a-z0-9']+", where) if w not in SPOT_STOP]
    if not words:
        return "your spot"
    return f"{words[-1]} spot"


SPOT_STOP = frozenset("sit sits stay stays wait waits go goes be when we i you while the a an my our your for to and in on at is are watch watching do does".split())


def concept_name(what: str) -> str:
    name = name_from(what)
    name = re.sub(r"^(?:what|how) ", "", name)
    return name.strip()[:40]
