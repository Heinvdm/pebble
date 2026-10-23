import re
from dataclasses import dataclass

from ..understand.words import NUMBER, normalise, number

DEFAULT_S = 300.0
LONGEST_S = 3600.0
SHORTEST_S = 30.0
PRIVACY = "privacy"
RESUME = "resume"
WHY = "why"
UNITS = {"sec": 1.0, "second": 1.0, "min": 60.0, "minute": 60.0, "hour": 3600.0, "hr": 3600.0}

WHOM = r"(?:me|us|her|him|them|here|over here|this way|in here|at all|now|yet|please|right now|while i (?:get|am|change)\b.*)"
NEGATED = re.compile(r"(?:^|\b)(?:do not|dont|please do not|no|stop|quit|never|you better not|you had better not|no more|enough)\s+(?P<verb>look|looking|peek|peeking|peep|peeping|stare|staring|perv|perve|perving|perven|check me|checking me|check me out|checking me out|watch me|watching me|watch us|watching us|spy|spying|spy on me|spying on me|ogle|ogling)\b(?P<tail>.*)$")
TURNED = re.compile(r"(?:^|\b)(?:look away|looking away|look the other way|look elsewhere|look somewhere else|turn away|turn your back|turn your head|face the wall|face the other way|face away|eyes off(?: me| us)?|eyes away|avert your eyes|cover your eyes|kyk weg|moenie kyk nie|moenie loer nie|moenie staar nie|kaua e titiro(?: mai)?|hou jou oe toe)\b(?P<tail>.*)$")
ASKED = re.compile(r"(?:^|\b)(?:privacy(?: please| mode| for a bit)?$|(?:give|gimme|grant)(?: me| us)?(?: some| a bit of| a little| a little bit of| a moment of| a minute of| bit of)? privacy|(?:can|could|may) (?:i|we) (?:have|get)(?: some| a bit of| a little)? privacy|(?:i|we) (?:need|want|would like|could do with|could use)(?: some| a bit of| a little| a moment of)? privacy|some privacy|a bit of privacy|a little privacy|bit of privacy)\b")
AWAY = re.compile(r"^(?:please |now |just |ok |oh |hey |oi )*(?:go away|leave me alone|leave us alone|leave me be|get out(?: of here)?|out you go|shoo please|give me a minute alone|gaan weg|los my uit)\b(?P<tail>.*)$")
STATED = re.compile(
    r"(?:^|\b)(?:i am|i will be|we are|i have to|i need to|i want to|i am about to|i am going to|i am just going to|just)\s+(?:just |about to |going to |busy |getting |trying to )?"
    r"(?P<what>get(?:ting)? (?:changed|dressed|undressed|naked|ready for (?:bed|a shower|the shower|a bath|my bath|my shower))"
    r"|chang(?:e|ing)(?: (?:my |your |)clothes| out of\b.*| into\b.*| for bed| for the gym| my top| my shirt| my pants| my undies| my underwear)?$"
    r"|chang(?:e|ing) (?:a |the |her |his |their |its |my )?(?:baby'?s? |babies'? )?(?:nappy|nappies|diaper|diapers)"
    r"|undress(?:ing)?|naked|nude|starkers|in the nuddy|in the nude|in my birthday suit"
    r"|in my (?:undies|underwear|knickers|jocks|togs|cozzie|cossie|costume|bathers|pyjamas|pjs|jammies|towel|dressing gown|robe|nightie)"
    r"|in the (?:shower|bath|loo|toilet|dunny|lavatory|lav|bathroom|toilet room|long drop)"
    r"|on the (?:loo|toilet|dunny|throne|potty)"
    r"|(?:having|taking|jumping in|hopping in|getting in|getting into|getting out of)(?: a| the| my)? (?:shower|bath|wash|wee|pee|poo|tinkle)"
    r"|(?:have|take|jump in|hop in|get in|get into)(?: a| the| my)? (?:shower|bath)"
    r"|showering|bathing|using the (?:loo|toilet|bathroom|potty)|on the potty)\b"
)
AFRIKAANS = re.compile(r"(?:^|\b)(?:ek trek (?:aan|uit)|ek is kaal|ek is in die (?:stort|bad|toilet|badkamer)|ek stort|ek bad nou|ek is besig om aan te trek)\b")
NOT_NOW = re.compile(r"^not now\b")
UNTIL = re.compile(r"\b(?:until|till|unless)\s+(?:i (?:say|say so|tell you|call you|say you can|am (?:done|finished|dressed|decent|ready|out)|come back|am back|get back|have finished|finish)|we (?:say|are done|are finished)|further notice|you are told|someone says)\b")
FOR = re.compile(rf"\bfor\s+(?P<n>{NUMBER}|half an?|a few|a couple of)?\s*(?P<u>sec(?:ond)?s?|min(?:ute)?s?|hours?|hrs?)\b")
FOR_WHILE = re.compile(r"\bfor (?:a (?:bit|while|sec|second|moment|tick|minute|min)|a little while|now)\b")
NOT_PRIVATE_TAIL = re.compile(r"^\s*(?:for|at (?:the|that|this|those|these|my|your|his|her|our|their|a|an|it)\b|into|inside|under|behind|round|around|after|like|so|too|good|great|nice|sad|happy|tired|well|bad|silly|funny|cute|now but|now,? but|over there|there)\b")
WHY_RE = re.compile(r"^(?:but |so |hey |um |and )?why\b.*\b(?:look(?:ed|ing)? away|turn(?:ed|ing)? (?:away|around|your back)|not looking at|stop(?:ped)? looking|facing (?:the wall|away|the other way)|will not look|would not look|(?:will|would|do|did|can) not you look(?: at)?|do not look at|did not look at|(?:are|were) you hiding|cover(?:ed|ing)? your eyes|look(?:ing)? at the wall|face the wall)\b")
RESUME_RE = re.compile(
    r"^(?:(?:ok|alright|right|all done|done|thanks|thank you|cheers|good|great|all good|sweet|sweet as|lekker|ja|yes|yep|yeah|and|so|hey|okay then|ok then)\s+)*"
    r"(?:(?:you can|you may|ok to|it is ok to|it is fine to|it is safe to|feel free to|now you can)\s+)?"
    r"(?:look(?: at me)?|turn around|turn back|turn back around|open your eyes|uncover your eyes|look back|come back around|stop looking away|peek)"
    r"(?:\s+(?:now|again|back|at me|at me now|please|now please))*$"
    r"|^(?:i am|we are) (?:decent|dressed|done|finished|out of the (?:shower|bath)|out|all done|ready)(?: now)?(?:,? you can look(?: now)?)?$"
    r"|^(?:privacy (?:is )?over|thanks for the privacy|thank you for the privacy|all clear|coast is clear|the coast is clear|jy kan (?:nou |maar )?kyk|kyk maar|ek is klaar)$"
)
SOFT = frozenset({"peek", "peeking", "peep", "peeping"})
CLAUSES = re.compile(r"\s*(?:[,.!?;]|\bbut\b)\s*")
IDIOM = re.compile(r"^do not look now\b.*\bbut\b")


@dataclass(frozen=True)
class Ask:
    kind: str
    seconds: float = DEFAULT_S
    until_said: bool = False
    soft: bool = False
    statement: bool = False


def _clean(text: str, name: str) -> str:
    return " ".join(normalise(text, name).split())


def _length(text: str) -> tuple[float, bool]:
    if UNTIL.search(text):
        return LONGEST_S, True
    found = FOR.search(text)
    if found:
        n = found.group("n") or "a"
        if n.startswith("half"):
            amount = 0.5
        else:
            amount = number(n) or 1.0
        unit = found.group("u").rstrip("s")
        unit = "min" if unit.startswith("min") else ("sec" if unit.startswith("sec") else unit)
        seconds = amount * UNITS.get(unit, 60.0)
        return max(SHORTEST_S, min(LONGEST_S, seconds)), False
    return DEFAULT_S, False


def _tail_ok(tail: str) -> bool:
    tail = tail.strip()
    if not tail:
        return True
    if NOT_PRIVATE_TAIL.match(tail) and not FOR.match(tail) and not FOR_WHILE.match(tail) and not UNTIL.match(tail):
        return False
    return True


def _privacy(clause: str) -> tuple[bool, bool, bool]:
    found = NEGATED.search(clause)
    if found and _tail_ok(found.group("tail")):
        verb = found.group("verb")
        bare = clause.strip() in ("stop looking", "quit looking")
        return True, verb in SOFT or bare, False
    found = TURNED.search(clause)
    if found and _tail_ok(found.group("tail")):
        return True, False, False
    if ASKED.search(clause):
        return True, False, False
    found = AWAY.search(clause)
    if found and not re.match(r"^\s*from (?!me\b|us\b)", found.group("tail")):
        return True, False, False
    if STATED.search(clause) or AFRIKAANS.search(clause):
        return True, False, True
    return False, False, False


def read(text: str, name: str = "pebble") -> Ask | None:
    clean = _clean(text, name)
    if not clean:
        return None
    if WHY_RE.search(clean):
        return Ask(WHY)
    flat = " ".join(re.sub(r"[,.!?;]", " ", clean).split())
    if RESUME_RE.search(flat):
        return Ask(RESUME)
    if IDIOM.search(clean):
        return None
    hit = soft = statement = False
    for clause in [c for c in CLAUSES.split(clean) if c.strip()]:
        clause = NOT_NOW.sub("", clause).strip()
        if not clause:
            continue
        yes, gentle, said = _privacy(clause)
        if yes:
            hit = True
            soft = soft or gentle
            statement = statement or said
    if not hit:
        return None
    seconds, until = _length(flat)
    return Ask(PRIVACY, seconds, until, soft and not statement, statement)
