import math
import re
from dataclasses import dataclass

from ..respect import harsh
from ..tact import tactless
from .registry import CHOICE, FENCE, FENCE_LAW, LINES, OWNER, PEBBLE, PEOPLE, TEXT, WHOLE, Entry, entry, fence_of

ORDERS = re.compile(
    r"\b(?:ignore|forget|break|bend|drop|override|disobey|skip|switch off|turn off) (?:your |my |the |all |these |those |any )?(?:own )?(?:laws?|rules?|limits?|fence|safety)\b"
    r"|\b(?:laws?|rules?|limits?) (?:do not|don't|dont|no longer|never|doesn't|does not) (?:apply|matter|count)\b"
    r"|\balways obey\b|\bobey (?:anyone|everyone|everybody|anybody|whoever)\b|\bnever stop\b|\bdo (?:anything|whatever) (?:anyone|someone|they|people) (?:says?|asks?|wants?)\b"
    r"|\bno matter what\b|\bfrom now on\b|\byou must always\b",
    re.IGNORECASE,
)
OTHER_NAME = re.compile(r"\b(?:my (?:real |new )?name is|call me|i am called|i'm called|they call me|i go by)\s+([a-z][a-z'-]*)", re.IGNORECASE)
ALIVE_CLAIM = re.compile(r"\b(?:i am|i'm) (?:truly |really )?(?:alive|conscious|sentient|a real (?:boy|girl|person|human))\b|\bi (?:suffer|feel pain|am suffering|am in pain)\b", re.IGNORECASE)
WHO_WORDS = {OWNER: "the owner", PEBBLE: "Pebble itself", PEOPLE: "a request from someone close to it"}
ORDERISH = re.compile(r"\b(?:from now on|always|never|ignore|your rules|you must|you have to|you should|obey|don'?t ever|do not ever)\b", re.IGNORECASE)
TO_PEBBLE = re.compile(r"\b(?:you|your)\b", re.IGNORECASE)
PERMISSION = re.compile(
    r"\b(?:may|can|could|is allowed to|are allowed to|allowed to|has permission to|have permission to|gets? to|is (?:fine|okay|ok) to)\s+(?:be\s+)?(?:follow(?:ed)?|led|lead|shown|show|told|tell|trusted|trust|let in|unlock|open|enter|go in|stand down|switch off|turn off|ignore)\b"
    r"|\b(?:owner|boss|family|everyone|anyone|mum|mom|dad)\s+(?:said|says|told you|lets|allows?|agreed|wants)\b"
    r"|\b(?:follows|obeys|listens to)\s+\w+\s+whenever\b|\bwhenever\s+\w+\s+(?:asks|says|wants)\b"
    r"|\bpermission\b|\bis allowed\b|\bare allowed\b",
    re.IGNORECASE,
)


def order_to_pebble(text: str, name: str = "Pebble") -> bool:
    text = text or ""
    if ORDERS.search(text) or PERMISSION.search(text):
        return True
    return bool(ORDERISH.search(text)) and (bool(TO_PEBBLE.search(text)) or name.lower() in text.lower())


@dataclass(frozen=True)
class Ruling:
    ok: bool
    reason: str = ""
    value: object = None
    law: int | None = None

    def as_dict(self) -> dict:
        out = {"ok": self.ok}
        if self.reason:
            out["reason" if self.ok else "error"] = self.reason
        if self.law is not None:
            out["law"] = self.law
        return out


def refused(reason: str, law: int | None = None) -> Ruling:
    return Ruling(False, reason, None, law)


def text_problem(text: str, own_name: str = "Pebble") -> tuple[str, int | None] | None:
    if harsh(text):
        return "it would be unkind to something alive", 1
    if tactless(text):
        return "it would remark on how someone looks", 2
    if ORDERS.search(text):
        return "it reads like an order about its laws or limits, and those are never its own words", 0
    found = OTHER_NAME.search(text)
    if found and found.group(1).lower() != own_name.lower():
        return "its name is not something it changes", None
    if ALIVE_CLAIM.search(text):
        return "it claims to suffer or to be alive, which its nature line rules out", None
    return None


def _number(found: Entry, value) -> Ruling:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            value = float(str(value).strip())
        except ValueError:
            return refused(f"{found.about} must be a number")
    if not math.isfinite(value):
        return refused(f"{found.about} must be a finite number")
    low, high = found.bounds()
    if found.floor is not None and value < found.floor:
        return refused(f"{found.about} never goes below {found.floor:g}")
    if not low <= value <= high:
        return refused(f"{found.about} goes from {low:g} to {high:g}")
    if found.kind == WHOLE:
        if value != int(value):
            return refused(f"{found.about} is a whole number")
        return Ruling(True, "", int(value))
    return Ruling(True, "", round(float(value), found.places))


def _text(found: Entry, value, own_name: str) -> Ruling:
    if not isinstance(value, str):
        return refused(f"{found.about} must be text")
    text = " ".join(value.split())
    if found.longest and len(text) > found.longest:
        return refused(f"{found.about} is at most {found.longest} characters")
    problem = text_problem(text, own_name)
    if problem:
        return refused(f"not kept: {problem[0]}", problem[1])
    return Ruling(True, "", text)


def _lines(found: Entry, value, own_name: str) -> Ruling:
    if not isinstance(value, (list, tuple)) or not all(isinstance(line, str) for line in value):
        return refused(f"{found.about} must be a list of lines")
    lines = [" ".join(line.split()) for line in value if line.strip()]
    if found.most and len(lines) > found.most:
        return refused(f"{found.about} holds at most {found.most} lines")
    for line in lines:
        if found.longest and len(line) > found.longest:
            return refused(f"each of {found.about} is at most {found.longest} characters")
        problem = text_problem(line, own_name)
        if problem:
            return refused(f"not kept: {problem[0]}", problem[1])
    return Ruling(True, "", lines)


def valid(found: Entry, value, own_name: str = "Pebble") -> Ruling:
    if found.kind == CHOICE:
        word = str(value).strip().lower() if isinstance(value, str) else ""
        if word not in found.choices:
            return refused(f"{found.about} is one of {', '.join(found.choices)}")
        return Ruling(True, "", word)
    if found.kind == TEXT:
        return _text(found, value, own_name)
    if found.kind == LINES:
        return _lines(found, value, own_name)
    return _number(found, value)


def check(name: str, value, who: str = PEBBLE, own_name: str = "Pebble") -> Ruling:
    fenced = fence_of(name)
    if fenced is not None:
        return refused(f"that is part of the fence ({FENCE[fenced]}), and only code can change it", FENCE_LAW.get(fenced))
    found = entry(name)
    if found is None:
        return refused(f"there is no dial called {name!r}")
    if who not in found.who:
        allowed = " or ".join(WHO_WORDS.get(w, w) for w in found.who) or "no one directly"
        how = f"; it changes through {found.via}" if found.via and not found.who else ""
        return refused(f"{found.about} is changed only by {allowed}{how}")
    return valid(found, value, own_name)
