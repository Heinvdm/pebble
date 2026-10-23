import re
from functools import lru_cache

from . import rules as R
from ..things.words import canonical
from .request import Request
from .words import FAMILY, NUMBERS, normalise

FUNCTION = frozenset(
    """
    a an the some any this that these those it its i me my mine myself you your yours yourself we us our ours he him his she her they them their
    is am are was were be been being do does did have has had will would can could shall should may might must
    to at in on by with from of for over up down out off into onto near next around about through there here away
    and then so but or also too as well
    ok please um uh er erm hmm oh hey hi yo yeah yes ya ja aye now just right well alright okay
    mate bro boet bru eh buddy lad boy girl kiddo china thanks thank cheers ta chur lekker sweet nice cool good great
    little guy friend dear darling love sweetie kindly listen
    able possible mind favour need want like let us go get got s thing instead anymore anywhere somewhere everywhere mister ooh aw wow
    """.split()
) | (R.ADJECTIVES - {"other"})
SEQUENCE = frozenset({"then", "and", "after", "afterwards", "also", "next", "that", "once", "done", "finished"})
COUNTS = frozenset({"twice", "thrice", "times", "again", "once", "more", "another"})
NUMBER_WORDS = frozenset(w for key in NUMBERS for w in key.split()) | frozenset({"half", "quarter", "full", "and"})
UNITS = frozenset({"second", "seconds", "sec", "secs", "minute", "minutes", "min", "mins", "hour", "hours", "hr", "hrs", "moment", "moments", "tick", "ticks", "jiffy", "mo", "metre", "metres", "m", "cm", "foot", "feet", "step", "steps", "degrees", "degree", "deg", "while", "bit"})
WAY_WORDS = frozenset({"left", "right", "around", "about", "forward", "forwards", "ahead", "back", "backwards", "backward", "reverse", "other", "way", "direction", "opposite", "circle", "spin", "u", "uey", "turn", "face", "behind"})
KIND_PATTERNS = {
    "follow": (R.FOLLOW,),
    "come": (R.COME, R.INDIRECT_COME),
    "wait": (R.WAIT, R.NEGATION),
    "look": (R.LOOK, R.LOOK_THERE, R.HAVE_A),
    "back_off": (R.BACK_OFF,),
    "go_home": (R.HOME,),
    "go_to_place": (R.PLACE, R.THERE, R.GO_LOOK_THERE, R.COME),
    "go_to_thing": (R.COME, R.PLACE),
    "find": (R.FIND,),
    "where_is": (R.WHERE, R.ROOM_ASK),
    "what_is": (R.WHAT_IS,),
    "what_see": (R.WHAT_SEE,),
    "sight_question": (R.OPEN_SHUT, R.COLOUR, R.READING, R.HOW_MANY, R.ANYONE_AT),
    "where_am_i": (R.WHERE_AM_I,),
    "teach": (R.CALLED, R.NAME_IS, R.CALL_IT, R.YOU_HAVE, R.MEET, R.SUBJECT, R.OWNED),
    "remember_spot": (R.REMEMBER_SPOT,),
    "go_back": (R.GO_BACK,),
    "play": (R.PLAY, R.GAME, R.CHASE),
    "turn": (R.TURN,),
    "move": (R.MOVE,),
    "stop_activity": (R.STOP_ACTIVITY, R.STOPPING, R.RELEASE),
    "adjust": tuple(p for _, p in R.ADJUST) + tuple(p for _, p in R.ADJUST_EXTRA) + (R.ADJUST_TRIM, R.ADJUST_INNER),
    "release": (R.RELEASE, R.STOP_ACTIVITY),
}
SLOT_PATTERNS = {
    "amount": (R.LITTLE, R.LOT),
    "speed": (R.SLOW, R.QUICK),
    "until": (R.UNTIL, R.BACK_WORDS, R.CALLED_WORDS, R.BE_BACK),
}
LATER = re.compile(
    r"\b(?:when|whenever|if|unless|until|till|while|remind|tonight|tomorrow|o ?clock|every (?:day|night|morning|evening|week|hour|minute|monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekday|weekend|other)|in (?:a |an |\d+ |[a-z]+ )?(?:minutes?|hours?|days?)|at (?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|noon|midnight)\b|before bed|bedtime|after (?:dinner|lunch|breakfast|school|work))\b"
)
TELLING = frozenset("i we he she they it its my our his her their the this that these those there someone somebody everyone everybody anyone anybody nobody people".split())
WAKE_ME = re.compile(r"\bwake (?:me|us)\b|\breminders?\b")
OTHERS = re.compile(r"\b(?:tell (?!me\b|us\b|you\b)[a-z]+|let (?!me\b|us\b)[a-z]+ know|ask (?!me\b|us\b|you\b)[a-z]+ (?:to|if|whether)|remind (?!me\b|us\b)[a-z]+|stay out|keep out|stay away from|(?:do not|never) (?:go|come) in|be quiet|keep quiet|stay quiet|no (?:more )?(?:chirping|beeping|humming|noise)|(?:do not|never) (?:chirp|beep|hum)|house rules?|what rules|you can (?:go|come) (?:back )?in|(?:do not|no need to) (?:have|need) to be quiet)\b")
STRONG = re.compile(
    r"\b(?:remind|tell|let (?:me|us|him|her|them|[a-z]+) know|wake|message|ask (?:him|her|them|[a-z]+) to|when|whenever|if|unless|until|till|while|once you|every|each (?:day|night|morning|hour)|tonight|tomorrow|morning|evening|afternoon|o ?clock|minutes?|hours?|monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekdays?|weekends?|before bed|keep an eye|patrol|see if|stay out|keep out|be quiet|keep quiet|stay quiet)\b"
)
WEAK = re.compile(
    r"\b(?:again|twice|thrice|times|check(?! out)|watch(?! out)|look around|no more|do that|do it|the other way|dance|sing|wiggle|jump|hop|nod|wave|bow|spin|chase your tail|show me|try)\b"
)
CALLED = frozenset({"guys", "everyone", "everybody", "boys", "girls", "children", "you guys"})
REPORTED = re.compile(r"\b(?:said|says|told|tells|telling|asked|asks|asking|wants|wanted)\b")
WONDERING = re.compile(r"^(?:imagine|what if|if only|i wish|i wonder|would not it be|would it not be|suppose|supposing)\b")
NEGATED = re.compile(r"^(?:please )?(?:do not|never (?!mind)|no more)\b")
ACTS = frozenset({"dance", "sing", "wiggle", "jump", "hop", "nod", "wave", "bow", "shake", "wag", "beep", "hum", "whistle", "chirp", "patrol", "guard", "check", "watch", "remind", "tell", "wake", "keep", "be", "stay", "try", "show", "spin", "twirl"})
NEW_ACTS = frozenset({"pretend", "act", "imitate", "copy", "mimic", "perform", "march", "shimmy", "boogie", "bounce", "wobble", "roll", "rock", "sway", "twirl", "curtsy", "salute", "push", "nudge", "kick", "dribble", "zigzag", "circle", "weave", "creep", "sneak", "tiptoe", "prance", "trot", "gallop", "parade", "celebrate", "greet", "bow", "nod", "wave", "shake", "wag", "beg"})
TALK_VERBS = frozenset({"tell", "remember", "set", "switch", "open", "close", "read", "write", "call", "text", "order", "buy", "help", "charge", "send", "teach", "learn", "guess", "record", "film", "photograph", "snap", "describe", "explain", "list", "note", "save", "forget", "delete", "wake", "light", "dim", "mute", "unmute", "pause", "resume", "skip", "repeat", "spell", "translate", "calculate", "add", "remind", "ring", "email", "message", "google", "search", "lock", "unlock", "feed", "water", "find", "check", "get", "give", "hand", "pass", "take", "fetch", "bring", "put", "pick", "clean", "grab", "count", "say", "start", "draw", "paint", "play"})
BODY_ACTS = (ACTS - TALK_VERBS - frozenset({"keep", "be", "stay", "patrol", "guard", "watch", "check", "try", "show"})) | NEW_ACTS
QUIET_PHRASES = re.compile(r"\b(?:for )?a (?:little |good |short |long )?(?:while|bit)\b|\bgood (?:morning|afternoon|evening|night)\b|\bbed ?time\b")


def tokens(text: str, name: str = "pebble") -> list[str]:
    return re.findall(r"[a-z0-9]+", normalise(text, name))


def core(text: str, name: str = "pebble") -> str:
    s = normalise(text, name).replace("?", "").replace("!", "").strip(" ,.")
    s = R._lead(s)
    parts = R.CORRECTION.split(f" {s} ")
    if len(parts) > 1:
        s = parts[-1].strip(" ,")
    s, _ = R._strip_prefixes(s)
    return R._strip_tail(s)


@lru_cache(maxsize=64)
def _vocab(patterns: tuple) -> frozenset:
    found = set()
    for pattern in patterns:
        found.update(w for w in re.findall(r"[a-z]+", pattern.pattern) if len(w) > 1)
    return frozenset(found)


def _kind_words(kind: str) -> frozenset:
    return _vocab(KIND_PATTERNS.get(kind, ()))


def _slot_words(name: str) -> frozenset:
    return _vocab(SLOT_PATTERNS.get(name, ()))


def _thing_words(thing: str, words: list[str]) -> set:
    out = set(thing.split())
    for index, word in enumerate(words):
        if canonical(word) == thing or word.rstrip("s") == thing:
            out.add(word)
        if index + 1 < len(words) and canonical(f"{word} {words[index + 1]}") == thing:
            out.update((word, words[index + 1]))
    return out


def explained(request: Request, words: list[str]) -> set:
    out = set(_kind_words(request.kind))
    for name in ("who", "place", "thing", "name"):
        value = getattr(request, name)
        if value:
            out.update(value.split())
    if request.thing:
        out |= _thing_words(request.thing, words)
    if request.who in ("me", ""):
        out.update(("me", "us", "i", "myself"))
    if request.way:
        out |= WAY_WORDS
    for name in ("amount", "speed", "until"):
        if getattr(request, name):
            out |= _slot_words(name)
    if request.metres or request.degrees or request.seconds:
        out |= NUMBER_WORDS | UNITS
        out.update(w for w in words if w.isdigit())
    if request.kind == "turn" and request.degrees >= 360:
        out |= {"twice", "times", "thrice", "full", "whole", "all", "circle", "spin", "three", "sixty"}
    if request.kind == "adjust" and request.change:
        out.update(request.change.split("_"))
    for step in request.then:
        out |= explained(step, words)
    if request.then:
        out |= SEQUENCE
        kinds = [request.kind] + [step.kind for step in request.then]
        if len(set(kinds)) < len(kinds):
            out.update(("again", "another", "more"))
    return out


def leftover(text: str, request: Request, name: str = "pebble", names: frozenset = frozenset()) -> tuple[str, ...]:
    s = QUIET_PHRASES.sub(lambda m: "bedtime" if m.group(0).startswith("bed") else " ", core(text, name))
    words = re.findall(r"[a-z0-9]+", s)
    used = explained(request, words) | FUNCTION | names | {name.lower()}
    if request.kind == "go_home":
        used.add("bedtime")
    left = []
    for word in words:
        if word in used or R.GERUNDS.get(word) in used or word in left:
            continue
        if word in COUNTS or word not in FUNCTION:
            left.append(word)
    return tuple(left)


def signals(text: str, name: str = "pebble") -> tuple[str, ...]:
    s = normalise(text, name).replace("?", "").replace("!", "").strip(" ,.")
    quiet = QUIET_PHRASES.sub(" ", s)
    stripped, polite = R._strip_prefixes(s)
    first = stripped.split(" ", 1)[0] if stripped else ""
    statement = not polite and first in R.SUBJECTS
    found = [m.group(0) for m in STRONG.finditer(quiet)]
    if not statement:
        found.extend(m.group(0) for m in WEAK.finditer(quiet))
    if NEGATED.match(stripped):
        found.append("not")
    if not statement and not stripped.startswith(first + " out") and (first in ACTS or (first in R.OTHER_VERBS and first != "do")):
        found.append(first)
    return tuple(dict.fromkeys(found))


def new_act(text: str, name: str = "pebble") -> bool:
    s = normalise(text, name).replace("?", "").replace("!", "").strip(" ,.")
    stripped, polite = R._strip_prefixes(s)
    said = stripped.split()
    if not said or NEGATED.match(stripped):
        return False
    first, second = said[0], said[1] if len(said) > 1 else ""
    if first != "do" and first in R.SUBJECTS:
        return False
    if first == "do" and second in ("not", "you", "i", "we", "they", "he", "she", "it", "that", "this", "those", "these", "so", "too"):
        return False
    return first in BODY_ACTS or (first in R.OTHER_VERBS and first not in TALK_VERBS)


def later_words(text: str, name: str = "pebble") -> tuple[str, ...]:
    s = normalise(text, name)
    return tuple(dict.fromkeys(m.group(0) for m in LATER.finditer(s)))


def for_later(text: str, name: str = "pebble") -> tuple[str, ...]:
    s = normalise(text, name).replace("?", "").replace("!", "").strip(" ,.")
    stripped, polite = R._strip_prefixes(s)
    first = stripped.split(" ", 1)[0] if stripped else ""
    if not polite and first in TELLING:
        return ()
    found = list(later_words(text, name))
    found.extend(m.group(0) for m in WAKE_ME.finditer(s))
    found.extend(m.group(0) for m in OTHERS.finditer(s))
    return tuple(dict.fromkeys(found))


def not_for_me(text: str, ctx) -> str:
    s = normalise(text, ctx.name).replace("?", "").replace("!", "").strip(" ,.")
    if not s:
        return ""
    if R._addressed_elsewhere(s, ctx):
        return "said to someone else"
    stripped, polite = R._strip_prefixes(R._lead(s))
    if WONDERING.match(stripped):
        return "wondering"
    said = R.IDIOMS.match(stripped)
    if said and said.group(1) not in ("look at that", "look at this"):
        return "a saying"
    asked = R.WHAT_IS.match(stripped)
    if asked and R.WHAT_IS_NOT.match(asked.group(1).strip()):
        return "a sound or a smell"
    first = stripped.split(" ", 1)[0] if stripped else ""
    second = stripped.split(" ")[1] if stripped.count(" ") else ""
    if (first in FAMILY or first in CALLED) and (second in R.VERB_STARTS or second in R.OTHER_VERBS):
        return "said to someone else"
    statement = not polite and (first in R.SUBJECTS or first in ctx.known_names() or first in FAMILY)
    if statement and REPORTED.search(stripped):
        return "someone else's words"
    return ""
