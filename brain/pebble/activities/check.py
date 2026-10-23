import math
import re
from dataclasses import dataclass

from ..things.words import spoken
from ..understand.request import Request
from .base import Activity, Ending
from .kit import Kit
from .motion import Wheels, leave_dock, turn_by, wrap_deg
from .rounds import go, where

RESULT_KEEP_S = 1800.0
THING_RADIUS = 2.5
SETTLE_S = 1.0
WITH_YOU_S = 10.0
EARSHOT_M = 2.0
FACE_DEG = 15.0
OPENABLE = frozenset({"door", "window", "gate", "curtain", "curtains", "blind", "blinds", "lid", "fridge", "cupboard", "drawer", "tap", "garage"})
SWITCHED = frozenset({"oven", "stove", "hob", "light", "lights", "lamp", "heater", "tv", "telly", "television", "iron", "fan", "kettle", "dryer", "dishwasher", "computer", "radio", "cooker", "grill", "microwave", "machine"})
YES = re.compile(r"^\s*(?:yes|yeah|yep|yup)\b[,.!]*\s*", re.IGNORECASE)
NO = re.compile(r"^\s*(?:no|nope)\b[,.!]*\s*", re.IGNORECASE)
ASKED = re.compile(r"^(?P<verb>is|are|has|have|was|were|does|do) (?P<subj>(?:the|my|our|your|his|her|their) [a-z]+(?: (?!(?:have|has|is|are|got|had)\b)[a-z]+(?= ))?|anyone|anybody|someone|somebody|everyone|nobody|it|[a-z]+) (?P<rest>.+)$")
PARTICIPLE = re.compile(r"^(?:[a-z]+ed|[a-z]+en|gone|done|run|left|come|begun|set|shut|put|cut)(?: |$)")
STATE = re.compile(r"^(?P<lead>(?:the|my|our|your|his|her|their) .+?|it) (?P<verb>is|are|was|were)(?P<neg> not|n't)? (?P<rest>.+)$", re.IGNORECASE)
IT = re.compile(r"^(?:it's|it is) ", re.IGNORECASE)
LOOKS_AWAY = ("I can't look at pictures", "I can't get a clear look", "Not now")
LOOKED = {"is": "looked", "are": "looked", "was": "looked", "were": "looked"}
NOT_LOOKED = {"is": "didn't look", "are": "didn't look", "was": "didn't look", "were": "didn't look"}


@dataclass(frozen=True)
class Aim:
    x: float
    y: float
    radius: float
    thing: bool
    room: str = ""


@dataclass
class Found:
    answer: str
    line: str
    whether: str
    told: bool = False


def target_words(request: Request) -> str:
    if request.thing:
        return f"the {spoken(request.thing)}"
    if request.place:
        return f"the {request.place}"
    return "that"


def question_of(request: Request) -> str:
    if request.text:
        said = " ".join(request.text.split()).strip(" ?.!")
        return said[:1].upper() + said[1:] + "?"
    thing = spoken(request.thing) if request.thing else ""
    last = thing.split(" ")[-1] if thing else ""
    if thing and (thing in OPENABLE or last in OPENABLE):
        return f"Is the {thing} open?"
    if thing and (thing in SWITCHED or last in SWITCHED):
        return f"Is the {thing} on?"
    if thing:
        return f"Can you see the {thing}?"
    return f"Is anyone in the {request.place}?" if request.place else "Can you see anything wrong?"


def whether_of(question: str) -> str:
    said = question.strip(" ?").lower()
    found = ASKED.match(said)
    if found is None:
        return "what I wanted to know"
    verb, subj, rest = found.group("verb"), found.group("subj"), found.group("rest")
    if verb in ("does", "do"):
        words = rest.split(" ", 1)
        head = "has" if words[0] == "have" and verb == "does" else words[0]
        return f"{subj} {head} {words[1] if len(words) > 1 else ''}".strip()
    return f"{subj} {verb} {rest}"


def sentence(text: str) -> str:
    text = " ".join(text.split()).strip()
    if not text:
        return ""
    text = text[:1].upper() + text[1:]
    return text if text.endswith((".", "!", "?")) else text + "."


def statement(whether: str, yes: bool) -> str:
    found = re.match(r"^(?P<subj>.+?) (?P<verb>is|are|has|have|was|were) (?P<rest>.+)$", whether)
    if found is None:
        return "Yes." if yes else "No."
    verb = found.group("verb")
    owns = verb in ("has", "have") and not PARTICIPLE.match(found.group("rest"))
    if not yes:
        verb = {"is": "isn't", "are": "aren't", "has": "hasn't", "have": "haven't", "was": "wasn't", "were": "weren't"}[verb]
        if owns:
            verb = "doesn't have" if verb == "hasn't" else "don't have"
    subj = found.group("subj")
    if subj in ("anyone", "anybody") and verb in ("is", "isn't"):
        subj, verb = ("someone", "is") if yes else ("nobody", "is")
    return sentence(f"{subj} {verb} {found.group('rest')}")


def looked(line: str) -> str:
    found = STATE.match(line.rstrip("."))
    if found is None:
        return line.rstrip(".") + ", but it was dark."
    verb = found.group("verb").lower()
    said = NOT_LOOKED[verb] if found.group("neg") else LOOKED[verb]
    return sentence(f"{found.group('lead')} {said} {found.group('rest')}").rstrip(".") + ", but it was dark."


def judge(question: str, answer: str, sure: bool, dark: bool, what: str = "") -> Found:
    whether = whether_of(question)
    if not sure:
        if answer.startswith(LOOKS_AWAY):
            return Found("unsure", f"I couldn't get a good look, so I couldn't tell whether {whether}.", whether)
        return Found("unsure", f"I couldn't tell whether {whether}.", whether)
    yes = bool(YES.match(answer))
    no = bool(NO.match(answer)) and not yes
    rest = sentence(YES.sub("", NO.sub("", answer, 1), 1))
    if what and IT.match(rest):
        rest = sentence(IT.sub(f"{what} is ", rest, 1))
    line = rest if rest and rest.lower() not in ("yes.", "no.") else (statement(whether, yes) if yes or no else sentence(answer))
    value = "yes" if yes else ("no" if no else "unsure")
    if dark:
        return Found("unsure", looked(line), whether)
    return Found(value, line, whether)


class Results:
    def __init__(self):
        self.items: dict = {}

    def put(self, asker: str | None, name: str, found: Found, now: float) -> None:
        kept = self.items.setdefault(asker, {})
        kept[""] = (found, now)
        if name:
            kept[name] = (found, now)

    def answers(self, asker: str | None, now: float) -> dict:
        return {name: found.answer for name, (found, at) in self.items.get(asker, {}).items() if now - at <= RESULT_KEEP_S}

    def last(self, asker: str | None, now: float, name: str = "") -> Found | None:
        found = self.items.get(asker, {}).get(name)
        if found is None or now - found[1] > RESULT_KEEP_S:
            return None
        return found[0]

    def forget(self, asker: str) -> None:
        self.items.pop(asker, None)


class Check(Activity):
    kind = "check"
    sight = True

    def __init__(self, request, asker, target=None, battery=False, aim: Aim | None = None, tree: bool = False):
        super().__init__(request, asker, target, battery)
        self.aim = aim
        self.tree = tree
        self.found: Found | None = None
        self.owed = ""

    def describe(self) -> str:
        return f"checking {target_words(self.request)}"

    def _with_asker(self, kit: Kit) -> bool:
        return self.asker.id is not None and kit.seen(self.asker.id, WITH_YOU_S)

    async def _face(self, kit: Kit, wheels: Wheels) -> None:
        odometer = kit.odometer
        if not self.aim.thing or odometer is None or not getattr(odometer, "usable", False) or wheels.why_not() is not None:
            return
        x, y, heading = odometer.pose()
        aim = wrap_deg(math.degrees(math.atan2(self.aim.y - y, self.aim.x - x)) - heading)
        if abs(aim) > FACE_DEG:
            await turn_by(kit, wheels, aim)

    async def _look(self, kit: Kit, question: str) -> tuple[str, bool]:
        if kit.picture is None:
            return "I can't look at pictures closely just now.", False
        return await kit.picture(question + " Answer yes or no first.")

    async def run(self, kit: Kit) -> Ending:
        what = target_words(self.request)
        question = question_of(self.request)
        whether = whether_of(question)
        own = self.asker.own
        if self.aim is None:
            self.found = Found("unsure", f"I don't know where {what} is, so I couldn't check whether {whether}.", whether)
            return self._report_now(kit, f"you did not know where {what} is, so you could not check it")
        start = where(kit)
        wheels = Wheels(kit).open()
        try:
            if wheels.why_not() is None:
                await leave_dock(kit, wheels)
            trip = await go(kit, self.aim.x, self.aim.y, THING_RADIUS if self.aim.thing else self.aim.radius)
            if not trip.ok and trip.how in ("stopped", "battery"):
                return Ending("stopped" if trip.how == "stopped" else "battery", f"you stopped on the way to check {what} ({trip.text})")
            if not trip.ok:
                self.found = Found("unsure", f"I couldn't get to {what}, so I couldn't check whether {whether}.", whether)
                kit.note(f"you could not get to {what} to check it ({trip.text})")
            else:
                await wheels.halt()
                await self._face(kit, wheels)
                await kit.pace.sleep(SETTLE_S)
                answer, sure = await self._look(kit, question)
                self.found = judge(question, answer, sure, kit.dark(), what)
                kit.note(f"you checked {what}: {self.found.line}")
            text = f"you checked {what}: {self.found.line}"
            if own:
                return Ending("done", text, "")
            report = self.request.report or ("tree" if self.tree else "back")
            if report == "tree" and self.found.answer != "unsure":
                return Ending("done", text, "")
            if report == "shout":
                self.found.told = True
                kit.say_loud(f"{self.asker.label}! {self.found.line}")
                return Ending("done", f"{text}; you called it out from there", "")
            if report == "keep":
                return Ending("done", f"{text}; you are keeping the answer until {self.asker.label} asks", "")
            here = where(kit)
            away = here is not None and start is not None and math.hypot(here[0] - start[0], here[1] - start[1]) > EARSHOT_M
            if start is not None and (away or not self._with_asker(kit)) and wheels.why_not() is None:
                back = await go(kit, start[0], start[1], 0.0)
                if not back.ok and back.how in ("stopped", "battery"):
                    return Ending("stopped" if back.how == "stopped" else "battery", f"{text}; you stopped on the way back ({back.text})")
            return self._report_now(kit, text)
        finally:
            await wheels.halt()
            wheels.close()

    def _report_now(self, kit: Kit, text: str) -> Ending:
        if self.asker.own:
            return Ending("done", text, "")
        self.found.told = True
        if self._with_asker(kit):
            return Ending("done", f"{text}; you told {self.asker.label}", self.found.line)
        self.owed = self.found.line
        return Ending("done", f"{text}; {self.asker.label} was not there, so you will tell them when you see them", self.found.line)
