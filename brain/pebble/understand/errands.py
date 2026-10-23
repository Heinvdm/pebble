import re

from ..things.words import ROOMS, canonical
from .context import Context
from .request import Request
from .telling import _places, _seconds, _start
from .words import FAMILY, ME

THINGS_NOT_ROOMS = frozenset({"front door", "back door", "door", "side door", "gate", "window", "garage door"})
SHOUT = re.compile(r"(?:,? and|,)? (?:shout|yell|call out|call|holler|sing out)(?: it)?(?: out)?(?: to (?:me|us))?(?: from there)?$")
KEEP = re.compile(r"(?:,? (?:and|but)|,)? (?:do not tell me(?: now| yet| straight away| right away)?|keep it (?:to yourself )?(?:till|until) i ask|tell me when i ask|i will ask you later)$")
BACK = re.compile(r"(?:,? and|,)? (?:come back and tell me|come and tell me|tell me|let me know|report back)$")
GO = r"(?:(?:go|pop|nip|run|head|quickly go)(?: and)? )?"
LOOKING = r"(?:check|see|find out|have a look and see|look and see|go see)"
CHECK_IF = re.compile(rf"^{GO}{LOOKING} (?:if|whether) (?P<q>.+)$")
CHECK_THAT = re.compile(rf"^{GO}check (?:that )?(?P<q>(?:the|my|our) .+? (?:is|are|has|have) .+)$")
CHECK_THING = re.compile(rf"^{GO}(?:check|check up on) (?:the |my |our )?(?P<what>[a-z]+(?: [a-z]+)?)$")
INTO = re.compile(r"^(?:go|pop|nip|run|head)(?: in)?(?: into| in to| to) (?:the |my |our )?(?P<room>[a-z]+(?: [a-z]+)?) and (?:check|see|find out|have a look and see|look and see) (?:if|whether) (?P<q>.+)$")
STATE_IN = re.compile(r"^(?P<verb>is|are) (?P<what>(?:the|my|our) [a-z]+(?: [a-z]+)?) (?P<state>on|off|open|closed|shut|locked|unlocked|running|empty|full|done|finished|wet|dry|still on|left on|left open) (?:in|out in) (?:the |my |our )?(?P<room>[a-z]+(?: [a-z]+)?)$")
CLAUSE = re.compile(r"^(?P<subj>(?:the|my|our|your|his|her|their) [a-z]+(?: [a-z]+)?|anyone|anybody|someone|somebody|everyone|nobody|[a-z]+) (?P<verb>is|are|has|have|was|were) (?P<rest>.+)$")
WATCH = re.compile(r"^(?:keep an eye on|keep (?:an |your )?eyes on|keep watch (?:on|over)|watch over|babysit) (?P<what>.+)$")
WATCH_FOR = re.compile(r"^watch (?P<what>.+?) (?P<tail>for me|while (?:i|we) .+|till i .+|until i .+)$")
WATCH_ME = re.compile(r"^watch (?P<what>.+)$")
FOR_ME = re.compile(r"\bfor (?:me|us)[.!]*$")
PARTICIPLE = re.compile(r"^(?:[a-z]+ed|[a-z]+en|gone|done|run|left|come|begun|set|shut|put|cut|stopped)\b")
WHILE = re.compile(r"^(?:while|till|until|when) (?:i|we|he|she|they|[a-z]+) .+$")
NOT_TARGETS = frozenset({"it", "that", "this", "things", "everything", "yourself", "you", "the time", "the news", "the telly", "the tv", "out", "your step", "your language", "the clock"})
NOT_ASKED = re.compile(r"^(?:you|we|i|they) (?:can|could|will|would|should|might|may)\b")
PRONOUNS = {"her": "her", "him": "him", "them": "them"}


def _target(words: str, ctx: Context) -> tuple[str, str, str] | None:
    words = words.strip()
    if words in NOT_TARGETS:
        return None
    named = not re.match(r"^(?:the|my|our|your) ", words)
    words = re.sub(r"^(?:the|my|our|your) ", "", words)
    if not words or words in NOT_TARGETS:
        return None
    if words in ME or words == ctx.speaker:
        return None
    if words in PRONOUNS:
        return words, "", ""
    if words in ctx.known_names() or (named and words in FAMILY):
        return words, "", ""
    if words in ROOMS and words not in THINGS_NOT_ROOMS:
        return "", "", words
    if not re.fullmatch(r"[a-z]+(?: [a-z]+)?", words):
        return None
    return "", canonical(words), ""


def _report(s: str) -> tuple[str, str]:
    for pattern, report in ((SHOUT, "shout"), (KEEP, "keep"), (BACK, "back")):
        found = pattern.search(s)
        if found is not None and found.start() > 0:
            return s[: found.start()].strip(" ,"), report
    return s, ""


def question(clause: str) -> str:
    clause = clause.strip(" ,")
    found = CLAUSE.match(clause)
    if found is None:
        return clause
    verb, subj, rest = found.group("verb"), found.group("subj"), found.group("rest")
    if verb in ("has", "have") and not PARTICIPLE.match(rest):
        return f"{'does' if verb == 'has' else 'do'} {subj} have {rest}"
    return f"{verb} {subj} {rest}"


def _room_in(text: str, ctx: Context) -> tuple[str, str]:
    for place in _places(ctx):
        if place in THINGS_NOT_ROOMS:
            continue
        found = re.search(rf"\b(?:in|into) (?:the |my |our )?{re.escape(place)}$", text)
        if found is not None:
            return place, text[: found.start()].strip()
    return "", text


def _subject_thing(clause: str) -> str:
    found = CLAUSE.match(clause.strip())
    if found is None:
        return ""
    subj = found.group("subj")
    if not subj.startswith(("the ", "my ", "our ")):
        return ""
    return canonical(re.sub(r"^(?:the|my|our) ", "", subj))


def _check(clause: str, ctx: Context, room: str = "") -> Request | None:
    if not clause or NOT_ASKED.match(clause):
        return None
    if re.search(r"\b(?:and|then|if|unless|when|otherwise|or)\b", clause):
        return None
    asked = question(clause)
    place = room or _room_in(asked, ctx)[0]
    thing = _subject_thing(clause) if not place else ""
    if thing and thing in ROOMS and thing not in THINGS_NOT_ROOMS:
        place, thing = thing, ""
    return Request("check", place=place, thing=thing, text=asked)


def check_words(text: str, ctx: Context) -> Request | None:
    s = _start(text, ctx)
    if not s:
        return None
    raw = " ".join((text or "").lower().split())
    found = STATE_IN.match(s)
    if found is not None:
        room = found.group("room")
        if room in _places(ctx) and room not in THINGS_NOT_ROOMS:
            what = found.group("what")
            return Request("check", place=room, text=f"{found.group('verb')} {what} {found.group('state')}")
        return None
    if raw.endswith("?"):
        return None
    s, report = _report(s)
    found = INTO.match(s)
    if found is not None:
        room = found.group("room")
        if room not in _places(ctx):
            return None
        request = _check(found.group("q"), ctx, room)
        return request.with_(report=report) if request is not None else None
    found = CHECK_IF.match(s) or CHECK_THAT.match(s)
    if found is not None:
        request = _check(found.group("q"), ctx)
        return request.with_(report=report) if request is not None else None
    found = CHECK_THING.match(s)
    if found is not None:
        what = found.group("what")
        if what.startswith("on ") or what in ("out", "it out", "that out", "this out"):
            return None
        target = _target(what, ctx)
        if target is None or target[0]:
            return None
        return Request("check", thing=target[1], place=target[2], report=report)
    return None


def watch_words(text: str, ctx: Context) -> Request | None:
    s = _start(text, ctx)
    if not s or " ".join((text or "").split()).endswith("?"):
        return None
    seconds = 0.0
    found = WATCH.match(s)
    if found is not None:
        what = found.group("what")
        tail = ""
        for joiner in (" while ", " till ", " until ", " when ", " for "):
            if joiner in f" {what} ":
                index = f" {what} ".index(joiner)
                if index > 0:
                    what, tail = what[: index - 1].strip(), what[index - 1 :].strip()
                    break
        if tail:
            seconds = _seconds(tail)
            if not seconds and not WHILE.match(tail) and tail != "for me":
                return None
    else:
        found = WATCH_FOR.match(s)
        if found is None and FOR_ME.search(" ".join((text or "").lower().split())):
            found = WATCH_ME.match(s)
        if found is None:
            return None
        what = found.group("what")
    target = _target(what, ctx)
    if target is None:
        return None
    who, thing, place = target
    if place:
        return None
    return Request("watch", who=who, thing=thing, seconds=seconds)


def errand_words(text: str, ctx: Context) -> Request | None:
    return check_words(text, ctx) or watch_words(text, ctx)
