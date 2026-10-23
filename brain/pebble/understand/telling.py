import re

from ..things.words import ROOMS
from .context import Context
from .request import Request, Trigger, When
from .rules import _lead, _strip_prefixes, _strip_tail, harmed, parse
from .words import FAMILY, normalise, number

NOT_NAMES = frozenset({"me", "us", "you", "yourself", "him", "her", "them", "it", "that", "this"})
EVERYONE = frozenset({"everyone", "everybody", "all of them", "the others", "the family", "the kids"})
TURNED = frozenset("i me my mine myself we us our ours ourselves he him his himself she her hers herself they them their theirs themselves you your yours yourself".split())
JOINED = re.compile(r"\b(?:then|and then|after that|afterwards)\b|, and |\b(?:when|whenever|if|unless|until|till|while)\b")
DURATION = re.compile(r"^(?:for )?(?:about |another |the next )?(?:(?P<half>half an hour)|(?P<n>[a-z0-9]+(?: [a-z]+)?) (?P<unit>minutes?|mins?|hours?|hrs?))$")
TOLD = re.compile(r"^(?:until|till) (?:i (?:say|tell you)(?: so| otherwise)?|further notice|i say you can|you are told)$|^for now$")
BACK = re.compile(r"^(?:until|till) i (?:am back|get back|come back|come home|get home|am home)$")
SHOW_ENDS = re.compile(r"^(?:until|till) (?:the|our|my) (?:movie|film|show|programme|program|game|match|telly|tv) (?:ends|is over|finishes|is finished)$")
TONIGHT = re.compile(r"^(?:tonight|for tonight|this evening|for the night)$")
KEEP_OUT = re.compile(r"^(?:(?:stay|keep) out of|(?:stay|keep) away from|(?:do not|never) (?:go|come) (?:in|into|in to|inside)|do not set foot in|no going (?:in|into)) (?P<rest>.+)$")
QUIET = re.compile(r"^(?:(?:be|keep|stay) (?:quiet|silent|quieter)|no (?:more )?(?:chirping|chirps|beeping|beeps|humming|noises?|chatter|chattering|talking)|(?:do not|never) (?:chirp|beep|hum|chatter)|(?:do not|never) make (?:a sound|any noise|any noises|noises))(?P<rest>(?: .+)?)$")
LIFT_IN = re.compile(r"^(?:you can|you may|it is (?:ok|okay|fine) to) (?:go|come) (?:back )?(?:in|into|in to|inside)(?P<rest>(?: .+)?)$")
LIFT_QUIET = re.compile(r"^(?:you (?:can|may) (?:talk|speak|chat|chirp|hum|make noise|make noises|be noisy|be loud)(?: again| now| again now)?|you do not (?:have|need) to (?:be|keep|stay) quiet(?: any ?more| now)?|(?:the )?quiet (?:time|rule) is over|no need to (?:be|keep|stay) quiet(?: any ?more)?)$")
LIFT_ANY = re.compile(r"^(?:forget|drop|cancel|lift|end|stop) (?:the |my |that |your |all (?:the |my )?)?(?:house )?rules?(?: about (?P<rest>.+))?$")
LIST = re.compile(r"^(?:(?:what|which) (?:house )?rules (?:do you have|have you got|are you keeping|do you keep|are there)|(?:list|tell me|say) (?:the |your |all the |all your )?(?:house )?rules|(?:do you have|have you got) any (?:house )?rules)$")
TELL = re.compile(r"^(?:go and |go |can you |could you |would you |will you )?(?P<verb>tell|remind|ask|let) (?P<who>[a-z]+(?: of them)?)(?P<know> know)? (?P<rest>.+)$")
PERFORMED = re.compile(r"^(?:a|an|another|some|the|that|this|your|one of your) (?:joke|story|secret|song|riddle|fact|tale|poem|rhyme)s?\b")
RELAY = re.compile(r"^(?P<who>[a-z]+) (?:wants you to|would like you to|(?:asked|told) me to (?:tell|ask) you to|(?:says|said) (?:that )?you (?:should|have to|need to|must|can|may)) (?P<rest>.+)$")


def _start(text: str, ctx: Context) -> str:
    s = normalise(text, ctx.name).replace("?", "").replace("!", "").strip(" ,.")
    s, _ = _strip_prefixes(_lead(s))
    return _strip_tail(s)


def _places(ctx: Context) -> list[str]:
    return sorted(set(ctx.places) | set(ROOMS) - {"room", "other room", "next room", "inside", "outside"}, key=len, reverse=True)


def _place(rest: str, ctx: Context) -> tuple[str, str] | None:
    rest = re.sub(r"^(?:the|my|our|your|their) ", "", rest.strip())
    for place in _places(ctx):
        if rest == place or rest.startswith(place + " "):
            return place, rest[len(place):].strip(" ,")
    return None


def _seconds(tail: str) -> float:
    found = DURATION.match(tail)
    if found is None:
        return 0.0
    if found.group("half"):
        return 1800.0
    count = number(found.group("n"))
    if count is None or count <= 0:
        return 0.0
    return count * (3600.0 if found.group("unit").startswith("h") else 60.0)


def _lasting(request: Request, tail: str) -> Request | None:
    tail = tail.strip(" ,")
    if not tail:
        return request
    seconds = _seconds(tail)
    if seconds:
        return request.with_(seconds=seconds)
    if TOLD.match(tail):
        return request.with_(until="told")
    if BACK.match(tail):
        return request.with_(until="back")
    if TONIGHT.match(tail):
        return request.with_(when=When(part="tonight"))
    if SHOW_ENDS.match(tail):
        return request.with_(until_on=Trigger(event="tv_off"))
    return None


def rule_words(text: str, ctx: Context) -> Request | None:
    s = _start(text, ctx)
    if not s:
        return None
    if LIST.match(s):
        return Request("list_rules")
    if LIFT_QUIET.match(s):
        return Request("end_rule", rule="quiet")
    found = LIFT_IN.match(s)
    if found is not None:
        rest = re.sub(r"\b(?:again|now)\b", "", found.group("rest")).strip(" ,")
        if not rest:
            return Request("end_rule", rule="keep_out")
        place = _place(rest, ctx)
        if place is not None and not place[1]:
            return Request("end_rule", rule="keep_out", place=place[0])
        return None
    found = LIFT_ANY.match(s)
    if found is not None:
        rest = (found.group("rest") or "").strip()
        if not rest:
            return Request("end_rule")
        if rest in ("being quiet", "keeping quiet", "quiet", "the quiet"):
            return Request("end_rule", rule="quiet")
        place = _place(rest, ctx)
        return Request("end_rule", rule="keep_out", place=place[0]) if place is not None and not place[1] else None
    found = KEEP_OUT.match(s)
    if found is not None:
        place = _place(found.group("rest"), ctx)
        if place is None:
            return None
        return _lasting(Request("set_rule", rule="keep_out", place=place[0]), place[1])
    found = QUIET.match(s)
    if found is not None:
        return _lasting(Request("set_rule", rule="quiet"), found.group("rest"))
    return None


def _who(word: str, ctx: Context) -> str:
    if word in EVERYONE or word in ("all", "everyone of them"):
        return "everyone"
    if word in NOT_NAMES or word == ctx.name or (ctx.speaker and word == ctx.speaker):
        return ""
    if word in ctx.known_names() or word in FAMILY:
        return word
    return ""


def message_words(text: str, ctx: Context) -> Request | None:
    s = _start(text, ctx)
    found = TELL.match(s)
    if found is None:
        return None
    verb, rest = found.group("verb"), found.group("rest").strip()
    if (verb == "let") != bool(found.group("know")):
        return None
    who = _who(found.group("who"), ctx)
    if not who or (verb == "remind" and who == "everyone"):
        return None
    if verb in ("ask", "remind"):
        if not rest.startswith("to "):
            return None
        rest = rest[3:]
    else:
        rest = re.sub(r"^(?:that|to) ", "", rest)
    words = re.findall(r"[a-z']+", rest)
    if not words or PERFORMED.match(rest) or any(word in TURNED or word.split("'")[0] in TURNED for word in words) or JOINED.search(rest):
        return None
    if re.search(r"\b(?:tonight|tomorrow|o ?clock|at (?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|noon|midnight)|in (?:a|an|\d+|[a-z]+) (?:minutes?|hours?|days?)|every|later|just now)\b", rest):
        return None
    return Request("say_to", who=who, text=rest)


def relayed(text: str, ctx: Context) -> Request | None:
    s = _start(text, ctx)
    found = RELAY.match(s)
    if found is None:
        return None
    if found.group("who") not in ctx.known_names() and found.group("who") not in FAMILY:
        return None
    rest = found.group("rest")
    harmful = harmed(rest, ctx)
    if harmful is not None:
        return harmful
    reading = parse(rest, ctx)
    request = reading.request
    if not request.action or not reading.certain or request.kind in ("say_to", "set_rule", "end_rule", "list_rules"):
        return None
    return request


def telling(text: str, ctx: Context) -> Request | None:
    return rule_words(text, ctx) or message_words(text, ctx)
