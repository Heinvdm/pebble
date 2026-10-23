import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from ..mind.base import CallOptions, MindUnavailable, options_kwargs
from ..mind.budget import GUIDE, JOB, MATCHED, WORDS, Prompt
from ..people.trust import CHILD, FRIEND, INNER, STRANGER, TRUSTED
from ..understand.request import Request
from .base import Activity, Ending
from .card import EXPRESSIVE, Card, request_of, said, step_words
from .gate import Asker, Verdict
from ..understand.cover import BODY_ACTS
from ..understand.rules import OTHER_VERBS, harmed
from .skills import AGAIN, TRY_AGAIN, Skills, name_of, plain, same

log = logging.getLogger(__name__)

PLAN_WAIT_S = 30.0
EXAMPLES_CHARS = 450
PLAN_IT = "Plan it."
ANOTHER_ASK = "Make a new plan that is different from every try above."
CHANGE_ASK = "The last try, number {number}, was {steps}. Change it: {change}. Keep the rest of it the same."
THINK_TOKENS = 256
PLAN_TOKENS = 220
ANSWER_WAIT_S = 20.0
AFTER_SKILL_S = 30.0
LEFT_S = 15.0
FACE_S = 0.8
TILT_S = 0.5
WAIT_DEFAULT_S = 2.0
WAIT_STEP_S = 0.5
LOOK_DEFAULT_S = 3.0
TEACHERS = frozenset({FRIEND, TRUSTED, INNER, CHILD})
FAILED_GO_ON = frozenset({"failed", "timeout", "no_sight"})
HOLDS = ("Hmm, let me try something.", "Ooh, let me try.", "Let me think how I'd do that.")
ASKS = ("Like that?", "Was that it?", "How was that?", "Is that what you meant?")
CHANGED = ("Okay, let me change it.", "Okay, like this then.", "Right, a bit different.")
ANOTHER = ("Okay, something different.", "Hmm, let me try another way.", "Okay, a new idea.")
KEPT = "Yay! I'll remember how to {how}."
REPLACED = "Okay, I'll {how} like that from now on."
ONE_OFF = "Glad you liked it!"
OUT_OF_IDEAS = "I'm out of ideas. Can you show me?"
CANT = "I can't do that in this body."
NOT_YET = "I don't know how to do that yet."
NEVER_MIND = "Okay, never mind."
SILENT = "Okay, I'll leave it there for now."
REST = {"battery": "My battery's low, so I'll stop trying for now. I'll remember where I got to.", "heat": "I'm getting too warm, so I'll stop trying for now. I'll remember where I got to."}
DRAFT_BACK = "Okay, let me try {doing} again."
ELSEWHERE = "I learned {doing} in another body, so let me try it in this one."
LEFT_OUT = "I'll leave that part out."
NOTHING_LEFT = "So I can't try that."
PART_ONLY = "I couldn't do all of it. "
NO_CHANGE = "I'm not sure how to change it. Can you show me?"
PLAN_GUIDE = """You plan how {name}, a small home robot on two wheels with a face screen, does something it has never done before. Build it only from the blocks below, at most 8 steps, in the order they happen. Reply with JSON only: {{"think":"...","steps":[...]}}, where think is a few short notes on how to do it, or {{"cant":"why"}} when this body can't do it at all (it has no arms or hands and can't lift, carry, climb, fly or jump). Never move towards a person or animal to bump them, and never push anything alive."""
PLAN_EXAMPLES = (
    ("Asked: \"do a bow\"\nPlan it.", {"think": "a bow: tilt the head down, hold it, then up again", "steps": [{"do": "tilt", "way": "down", "degrees": 30}, {"do": "wait", "seconds": 1}, {"do": "tilt", "way": "up", "degrees": 10}]}),
    ("Asked: \"wag your tail\"\nPlan it.", {"think": "no tail, so wiggle the whole body and look happy", "steps": [{"do": "face", "expression": "happy"}, {"do": "wiggle", "repeat": 2}]}),
    ("Asked: \"make me a cup of tea\"\nPlan it.", {"cant": "it has no hands to hold a cup or a kettle"}),
)
YES = re.compile(r"^(?:yes|yeah|yep|yup|ja|yes please|that's it|thats it|that is it|that's the one|perfect|exactly|good boy|good girl|good robot|good one|well done|great|lovely|nice|brilliant|awesome|spot on|that's right|thats right|love it|i love it|just like that|like that|that's perfect|bingo|nailed it|that'll do|that's good|good job|beautiful|amazing|fantastic|wonderful|super|cool|sweet|sweet as)\b")
NO = re.compile(r"^(?:no|nope|nah|not like that|not really|that's not it|thats not it|that isn't it|not that|wrong|no way)\b")
NEARLY = re.compile(r"^(?:nearly|almost|close|not quite|kind of|sort of|getting there|good but|better but|yes but|yeah but|ok but|okay but)\b")
END = re.compile(r"^(?:never mind|nevermind|forget it|that's enough|thats enough|enough|stop trying|leave it|don't worry|dont worry|no thanks|no thank you|forget about it|it doesn't matter)$")
LAUGH = re.compile(r"^(?:(?:ha|he|hah|heh|lol)\s*)+$|\b(?:haha+|hehe+|lol)\b")
NOT_LIKE = re.compile(r"^(?:no,? )?(?:not like that|that's not it|thats not it|not that one|that's wrong|wrong)\b")
CHANGE_START = re.compile(r"^(?:faster|slower|quicker|more|less|bigger|smaller|twice|three times|the other way|other way|longer|shorter|higher|lower|again but|and then|then|but|with|without|do it|a bit|a little|a lot|go faster|go slower|spin more|turn more)\b")
CHANGE_WORDS = frozenset("faster slower quicker slowly quickly bigger smaller more less twice thrice times three four other way longer shorter higher lower louder softer again then back around left right spin turn wiggle tilt nod face happy sad end start first after before also too and with without bit lot little wider tighter come go".split())
FILLERS = frozenset("pebble please thanks thank you really just so oh um well okay ok".split())
VERBS = BODY_ACTS | OTHER_VERBS | frozenset("spin turn go come roll push chase run walk move make be pretend jump hop".split())


@dataclass
class Loop:
    name: str
    words: str
    asker: Asker
    how: str
    tries: list = field(default_factory=list)
    hints: list = field(default_factory=list)
    skill: object | None = None
    activity: Activity | None = None
    current: list = field(default_factory=list)
    waiting_since: float | None = None
    held: list = field(default_factory=list)
    one_off: bool = False
    drafts: bool = True
    planning: bool = False
    asked: int = 0


@dataclass(frozen=True)
class Planned:
    steps: list = field(default_factory=list)
    cant: str = ""
    errors: tuple = ()
    think: str = ""
    seconds: float = 0.0
    failed: str = ""


def answer_of(text: str, own: str = "pebble") -> tuple[str, str] | None:
    said = " ".join(w for w in plain(text).split() if w != own)
    if not said:
        return None
    if END.match(said):
        return "end", ""
    lead, rest = "", said
    found = NOT_LIKE.match(said)
    if found:
        lead, rest = "no", said[found.end():]
    else:
        for kind, pattern in (("nearly", NEARLY), ("yes", YES), ("no", NO)):
            found = pattern.match(said)
            if found:
                lead, rest = kind, said[found.end():]
                break
    rest = re.sub(r"^(?:but|just|and|so)\s+", "", rest.strip(" ,"))
    words = [w for w in rest.split() if w not in FILLERS]
    changing = any(w in CHANGE_WORDS for w in words)
    if lead == "nearly":
        return "nearly", " ".join(words) or "a little different"
    if lead == "no":
        return ("nearly", " ".join(words)) if changing else ("no", "")
    if lead == "yes":
        return ("nearly", " ".join(words)) if changing and re.search(r"\bbut\b", said) else ("yes", "")
    if CHANGE_START.match(said):
        return "nearly", " ".join(words)
    if LAUGH.search(said):
        return "laugh", ""
    return None


def changed(steps: list, change: str) -> list | None:
    said = f" {plain(change)} "
    out = [dict(step) for step in steps]
    done = False
    if re.search(r" (?:faster|quicker|quickly|speed up) ", said):
        for step in out:
            if step["do"] in ("turn", "move"):
                step["speed"] = "quick"
                done = True
    if re.search(r" (?:slower|slowly|slow down) ", said):
        for step in out:
            if step["do"] in ("turn", "move"):
                step["speed"] = "slow"
                done = True
    if re.search(r" (?:other way|the other way|opposite way|other direction) ", said):
        swap = {"left": "right", "right": "left", "up": "down", "down": "up"}
        for step in out:
            if step.get("way") in swap:
                step["way"] = swap[step["way"]]
                done = True
    if re.search(r" (?:bigger|more|further|wider|longer) ", said):
        for step in out:
            for name, top in (("degrees", 720.0), ("metres", 1.0), ("seconds", 30.0)):
                if name in step:
                    step[name] = min(top, round(float(step[name]) * 1.5, 2))
                    done = True
    if re.search(r" (?:smaller|less|shorter|tighter) ", said):
        for step in out:
            for name, low in (("degrees", 10.0), ("metres", 0.05), ("seconds", 1.0)):
                if name in step:
                    step[name] = max(low, round(float(step[name]) * 0.6, 2))
                    done = True
    times = re.search(r" (twice|two times|three times|thrice) ", said)
    if times:
        count = 2 if times.group(1) in ("twice", "two times") else 3
        for step in out:
            step["repeat"] = min(4, max(1, int(step.get("repeat", 1))) * count) if len(out) == 1 else max(int(step.get("repeat", 1)), 1)
        if len(out) > 1:
            out = (out * count)[:8]
        done = True
    if re.search(r" (?:and then |then )?(?:come back|come to me|come here|come back to me) ", said):
        out = (out + [{"do": "come", "who": "me"}])[:8]
        done = True
    return out if done else None


class Planner:
    def __init__(self, mind_of: Callable[[], object | None], name: str = "Pebble", wait_s: float = PLAN_WAIT_S, monotonic: Callable[[], float] = time.monotonic):
        self.mind_of = mind_of
        self.name = name
        self.wait_s = wait_s
        self.monotonic = monotonic

    def ready(self) -> bool:
        try:
            return self.mind_of() is not None
        except Exception:
            return False

    def messages(self, card: Card, ask: str, examples: list = ()) -> Prompt:
        system = PLAN_GUIDE.format(name=self.name) + "\n\n" + card.text()
        out = [{"role": "system", "content": system}]
        for said_text, reply in PLAN_EXAMPLES:
            out.append({"role": "user", "content": said_text})
            out.append({"role": "assistant", "content": json.dumps(reply, separators=(",", ":"))})
        lines = []
        shown = []
        for skill in examples:
            item = f"{skill.name}: {json.dumps(skill.steps, separators=(',', ':'))}"
            if sum(len(s) for s in shown) + len(item) > EXAMPLES_CHARS:
                break
            shown.append(item)
        known = ("Ways you already know: " + " | ".join(shown)) if shown else ""
        if known:
            lines.append(known)
        lines.append(ask)
        out.append({"role": "user", "content": "\n".join(lines)})
        last = len(out) - 1
        parts = [(GUIDE, 0, system), (WORDS, last, ask)]
        if known:
            parts.append((MATCHED, last, known))
        return Prompt(out, JOB, parts)

    async def ask(self, card: Card, ask: str, examples: list = (), seed: int | None = None) -> Planned:
        mind = self.mind_of()
        if mind is None:
            return Planned(failed="no model to plan with")
        prompt = self.messages(card, ask, examples)
        start = self.monotonic()
        reply = await self._call(mind, prompt, card, seed)
        if isinstance(reply, Planned):
            return reply
        planned = self._read(reply, card)
        if planned.errors and not planned.cant:
            fix = prompt.like(list(prompt) + [{"role": "assistant", "content": reply}, {"role": "user", "content": "Problems with that plan:\n" + "\n".join(planned.errors) + "\nReply with the whole plan again, fixed."}])
            again = await self._call(mind, fix, card, seed)
            if not isinstance(again, Planned):
                fixed = self._read(again, card)
                if fixed.steps and not fixed.errors:
                    planned = fixed
                elif fixed.steps and len(fixed.steps) >= len(planned.steps):
                    planned = Planned(fixed.steps, "", fixed.errors, fixed.think)
        return Planned(planned.steps, planned.cant, planned.errors, planned.think, self.monotonic() - start, planned.failed)

    async def _call(self, mind, prompt: Prompt, card: Card, seed: int | None):
        options = CallOptions("steady", 0.3, 0.9, 0.1, seed=seed, grammar=card.grammar())
        try:
            reply = await asyncio.wait_for(mind.chat(prompt, purpose="plan", max_tokens=THINK_TOKENS + PLAN_TOKENS, **options_kwargs(options)), self.wait_s)
        except (MindUnavailable, asyncio.TimeoutError) as error:
            return Planned(failed=str(error) or "timed out")
        return reply.text or ""

    def _read(self, text: str, card: Card) -> Planned:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return Planned(failed="no JSON in the reply")
        try:
            data = json.loads(text[start : end + 1])
        except ValueError:
            return Planned(failed="the reply was not JSON")
        if not isinstance(data, dict):
            return Planned(failed="the reply was not an object")
        if data.get("cant"):
            return Planned(cant=" ".join(str(data["cant"]).split())[:120])
        steps, errors = card.check(data.get("steps"))
        return Planned(steps, "", tuple(errors), " ".join(str(data.get("think") or "").split())[:300])


def doing(name: str) -> str:
    first = name.split(" ", 1)[0] if name else ""
    return f"to {name}" if first in VERBS else f"the {name}"


def how_to(name: str) -> str:
    first = name.split(" ", 1)[0] if name else ""
    return name if first in VERBS else f"do the {name}"


def history(loop: Loop) -> str:
    lines = []
    for number, item in enumerate(loop.tries, 1):
        answer = item.get("answer") or "nothing"
        lines.append(f"{number}. {json.dumps(item.get('steps') or [], separators=(',', ':'))} They said: \"{answer}\".")
    return "\n".join(lines)


def asking(loop: Loop, who: str, ask: str) -> str:
    lines = [f'Asked by {who}: "{loop.words}"']
    if loop.tries:
        lines.append("Tries so far:")
        lines.append(history(loop))
    if loop.hints:
        lines.append(f"Hints: {'; '.join(loop.hints[-3:])}.")
    lines.append(ask)
    return "\n".join(lines)


class Try(Activity):
    kind = "try_new"

    def __init__(self, request: Request, asker: Asker, target=None, battery: bool = False, steps=(), name: str = "", gate=None, run_step=None):
        super().__init__(request, asker, target, battery)
        self.steps = [dict(step) for step in steps]
        self.name = name
        self.gate = gate
        self.run_step = run_step
        self.problems: list[str] = []
        self.rest: list = []
        self.refused: Verdict | None = None
        self.failed_step: dict | None = None
        self.tilted = False
        self.skill = ""

    def describe(self) -> str:
        if not self.name:
            return "trying something new"
        if self.skill:
            return f"doing the {self.name}"
        return f"trying {doing(self.name)}"

    def adjust(self, request: Request) -> tuple[str, Request | None]:
        if request.change in ("enough", "stay"):
            return "Okay, I'll stop.", Request("wait")
        return "", None

    async def run(self, kit) -> Ending:
        try:
            for index, step in enumerate(self.steps):
                plain_step = {k: v for k, v in step.items() if k != "repeat"}
                for _ in range(max(1, int(step.get("repeat", 1)))):
                    refused, target = await self.gate(plain_step, self.asker)
                    if refused is not None:
                        self.refused = refused
                        self.failed_step = plain_step
                        self.rest = [dict(s) for s in self.steps[index + 1 :]]
                        return Ending("refused", f"you stopped trying {self.name}: {step_words(plain_step)} was refused ({refused.reason})", refused.say)
                    ending = await self.run_step(plain_step, kit, self, target)
                    if ending is None or ending.how == "done":
                        continue
                    if ending.how in FAILED_GO_ON:
                        self.problems.append(f"{step_words(plain_step)}: {ending.text}")
                        continue
                    self.failed_step = plain_step
                    self.rest = [dict(s) for s in self.steps[index:]]
                    return Ending(ending.how, f"while trying {self.name}, {ending.text}", ending.say)
            text = f"you did the {self.name}: {said(self.steps)}" if self.skill else f"you tried {self.name}: {said(self.steps)}"
            if self.problems:
                text += f" (not all of it worked: {'; '.join(self.problems)})"
            return Ending("done", text, "")
        finally:
            if self.tilted:
                await kit.body.tilt(kit.body.profile.tilt_rest)


class Trying:
    def __init__(self, commands, skills: Skills, card_of: Callable[[], Card], planner: Planner | None = None):
        self.commands = commands
        self.skills = skills
        self.card_of = card_of
        self.card_for: Callable[[str], Card] | None = None
        self.planner = planner
        self.loop: Loop | None = None
        self.after: tuple | None = None
        self.fence: Callable[[], str] = lambda: ""
        self.leaks: Callable[[str], bool] = lambda text: False
        self.draw: Callable[[str], Awaitable] | None = None
        self.on_show: Callable[[str, str, Asker], None] | None = None
        self.turns = 0

    @property
    def clock(self):
        return self.commands.clock

    def record(self, kind: str, **data) -> None:
        self.commands.record(kind, **data)

    def _line(self, lines: tuple) -> str:
        self.turns += 1
        return lines[self.turns % len(lines)]

    def say(self, text: str) -> None:
        if text:
            self.commands._spawn(self.commands.speak(text, False))

    async def speak(self, text: str) -> None:
        if text:
            await self.commands.speak(text, False)

    def matched(self, text: str) -> Request | None:
        said = plain(text)
        if not said:
            return None
        if (AGAIN.search(said) or TRY_AGAIN.match(said)) and self.skills.drafted(said) is not None:
            return Request("try_new", text=said[:160])
        skill = self.skills.matches(text)
        if skill is None:
            return None
        return Request("try_new", text=said[:160], name=skill.name)

    def listed(self, text: str) -> str:
        try:
            return self.skills.listed(text)
        except Exception:
            log.exception("could not list kept skills")
            return ""

    async def start(self, request: Request, asker: Asker, how: str) -> Verdict:
        commands = self.commands
        words = request.text or request.name or ""
        harmful = harmed(words, commands.context(None, asker)) if words else None
        if harmful is not None:
            self.record("try_harm", person=asker.id)
            return await commands.act(harmful, asker, how)
        name = name_of(request.name or words) or plain(words) or "something new"
        held = list(request.then) + (list(commands.plan.steps) if how == "then" and commands.plan is not None else [])
        if self.loop is not None:
            self._close("replaced", True)
        again = (AGAIN.search(plain(words)) or TRY_AGAIN.match(plain(words))) and asker.tier != STRANGER and not asker.own
        draft = self.skills.drafted(words) if again else None
        skill = None
        if draft is None:
            skill = (self.skills.get(request.name) if request.name else None) or self.skills.find(words)
        if skill is not None:
            return await self._run_skill(skill, request, asker, how, words)
        first, opening = [], ""
        if draft is not None:
            name = draft.name
            first = draft.best()
            opening = DRAFT_BACK.format(doing=self._spoken(doing(name)))
        else:
            other = self.skills.elsewhere(words)
            if other is not None:
                name = other.name
                first, errors = self.card_of().check(other.steps)
                opening = ELSEWHERE.format(doing=self._spoken(doing(name))) if first else ""
        if not first and (self.planner is None or not self.planner.ready()):
            self.record("not_yet", how=how, parts=["try_new"], asked="try_new", person=asker.id, tier=asker.tier)
            if not asker.own:
                commands.note(f"{asker.label} asked you to try something new, but you have no way to work it out, so you said so", False)
                await self.speak(NOT_YET)
            return Verdict("no", "you have no model to work out something new with", "" if asker.own else NOT_YET)
        verdict = commands.decide_now(Request("try_new", text=words[:160]), asker)
        if not verdict.yes:
            await commands._answer(Request("try_new", text=words[:160]), asker, verdict, how)
            return verdict
        loop = Loop(name, words, asker, how, held=held, one_off=asker.own, drafts=not asker.own and asker.tier != STRANGER)
        if draft is not None:
            loop.tries = [dict(t) for t in draft.tries]
        if how == "then" and commands.plan is not None:
            commands.plan = None
        self.loop = loop
        commands.did(request, asker, how)
        self.record("try_started", name=name, person=asker.id, tier=asker.tier, resumed=draft is not None, elsewhere=bool(opening) and draft is None)
        if asker.own:
            commands.note(f"you decided to try {words}", False)
        elif draft is not None:
            commands.note(f"{asker.label} asked you to try {doing(name)} again, so you went back to where you got to", False)
        elif opening:
            commands.note(f"{asker.label} asked you to {words}; you learned it in another body, so you are trying it in this one", False)
        else:
            commands.note(f"{asker.label} asked you to {words or 'try something new'}; you have never done it, so you are trying it", False)
        commands.runner.kit.face.show("curious")
        if first:
            self.say(opening)
            await self._try(loop, first)
        else:
            self.say(self._line(HOLDS))
            commands._spawn(self._first(loop))
        return Verdict("yes", "you started trying something new", "")

    async def _first(self, loop: Loop) -> None:
        planned = await self._plan(loop, PLAN_IT)
        if loop is not self.loop:
            return
        if planned.cant or not planned.steps:
            self.record("try_cant", name=loop.name, why=planned.cant or planned.failed or "no plan")
            self._close("cant", False)
            self.commands.note(f"you could not work out how to {loop.words} in this body ({planned.cant or planned.failed})", False)
            if not loop.asker.own:
                await self.speak(CANT if planned.cant or not planned.failed else NOT_YET)
            return
        await self._try(loop, planned.steps)

    def _spoken(self, text: str) -> str:
        names = {n.lower() for person in self.commands.company.book.people.values() for n in person.names + person.nicknames if n}
        return " ".join(word.title() if word in names else word for word in text.split(" "))

    def _who(self, asker: Asker) -> str:
        return "yourself" if asker.own else asker.label

    def _examples(self, words: str) -> list:
        try:
            return self.skills.closest(words)
        except Exception:
            log.exception("could not find kept skills to show")
            return []

    async def _plan(self, loop: Loop, ask: str) -> Planned:
        if self.planner is None:
            return Planned(failed="no planner")
        loop.planning = True
        try:
            card = self.card_for(f"{loop.words} {ask}") if self.card_for is not None else self.card_of()
            planned = await self.planner.ask(card, asking(loop, self._who(loop.asker), ask), self._examples(loop.words), seed=len(loop.tries))
        except Exception:
            log.exception("planning a try failed")
            planned = Planned(failed="the plan went wrong")
        finally:
            loop.planning = False
        self.record("try_planned", name=loop.name, steps=len(planned.steps), errors=len(planned.errors), cant=bool(planned.cant), failed=planned.failed or None, seconds=round(planned.seconds, 2))
        return planned

    async def _try(self, loop: Loop, steps: list) -> None:
        commands = self.commands
        card = self.card_of()
        steps, errors = card.check(steps)
        if errors:
            self.record("try_steps_dropped", name=loop.name, errors=len(errors))
        kept, lines = [], []
        for step in steps:
            refused, _ = await self.gate(step, loop.asker, ahead=True)
            if refused is None:
                kept.append(step)
            else:
                self.record("try_step_refused", name=loop.name, step=step.get("do"), reason=refused.reason)
                if refused.say and refused.say not in lines:
                    lines.append(refused.say)
        if lines and not loop.asker.own:
            for line in lines:
                self.say(line)
        if not kept or not any(step["do"] in EXPRESSIVE for step in kept) or len(kept) * 2 < len(steps):
            self.record("try_nothing_left", name=loop.name)
            if not loop.asker.own:
                self.say(NOTHING_LEFT)
            self._close("refused", True)
            return
        if lines and not loop.asker.own:
            self.say(LEFT_OUT)
        loop.current = kept
        activity = Try(Request("try_new", text=loop.words[:160], name=loop.name), loop.asker, None, False, kept, loop.name, self.gate, self.run_step)
        loop.activity = activity
        commands.runner.start(activity)

    async def carry_on(self, activity: Try, steps: list) -> bool:
        loop = self.loop
        if loop is None or activity is not loop.activity:
            return False
        steps = [dict(s) for s in steps if s]
        if not steps:
            return False
        fresh = Try(activity.request, loop.asker, None, False, steps, loop.name, self.gate, self.run_step)
        fresh.problems = list(activity.problems)
        loop.activity = fresh
        self.commands.runner.start(fresh)
        return True

    async def gate(self, step: dict, asker: Asker, ahead: bool = False) -> tuple[Verdict | None, object]:
        commands = self.commands
        name = step.get("do")
        if name == "say":
            text = step.get("text", "")
            problem = commands.words_problem(text) or (self.leaks(text) and "it would repeat something you overheard about someone else")
            if problem:
                return Verdict("no", f"you won't say that: {problem}", "I won't say that part."), None
            return None, None
        if name == "draw":
            problem = commands.words_problem(step.get("subject", ""))
            if problem:
                return Verdict("no", f"you won't draw that: {problem}", "I won't draw that part."), None
            return None, None
        if name in ("face", "tilt", "wait"):
            sit = commands.situation()
            if sit.asleep:
                return Verdict("no", "you were asleep", ""), None
            return None, None
        request = Request("turn", way="left", degrees=14.0) if name == "wiggle" else request_of(step)
        if request is None:
            return Verdict("no", f"{name} is not something this body can do", ""), None
        if request.kind == "look" and not request.seconds:
            request = request.with_(seconds=LOOK_DEFAULT_S)
        verdict, target = await commands.check_step(request, asker, ahead)
        if not verdict.yes:
            return verdict, None
        return None, target

    async def run_step(self, step: dict, kit, activity: Try, target) -> Ending | None:
        name = step.get("do")
        if name == "face":
            kit.face.show(step.get("expression", "happy"))
            await kit.pace.sleep(FACE_S)
            return None
        if name == "tilt":
            rest = kit.body.profile.tilt_rest
            degrees = float(step.get("degrees") or 20.0) * (1.0 if step.get("way") == "up" else -1.0)
            await kit.body.tilt(rest + degrees)
            activity.tilted = True
            await kit.pace.sleep(TILT_S)
            return None
        if name == "say":
            text = step.get("text", "")
            kit.say(text)
            await kit.pace.sleep(min(4.0, 0.4 + 0.065 * len(text)))
            return None
        if name == "draw":
            if self.draw is not None:
                try:
                    await self.draw(step.get("subject", ""))
                except Exception:
                    log.exception("drawing during a try failed")
            return None
        if name == "wait":
            seconds = float(step.get("seconds") or WAIT_DEFAULT_S)
            until = step.get("until_seen") or ""
            end = kit.pace.now() + seconds
            while kit.pace.now() < end:
                if until and self._seen(kit, until):
                    break
                await kit.pace.sleep(min(WAIT_STEP_S, max(0.0, end - kit.pace.now())))
            return None
        if name == "wiggle":
            from .places import Wiggle

            wiggle = Wiggle(Request("turn"), activity.asker)
            wiggle.why = "for fun"
            return await wiggle.run(kit)
        request = request_of(step)
        if request is None:
            return Ending("failed", f"{name} is not something this body can do", "")
        if request.kind == "look" and not request.seconds:
            request = request.with_(seconds=LOOK_DEFAULT_S)
        inner = self.commands.make_activity(request, activity.asker, target)
        return await inner.run(kit)

    def _seen(self, kit, label: str) -> bool:
        sight = kit.eyes.latest(1.0)
        if sight is None:
            return False
        if any(label in (t.label or "") or (t.known and label in t.known) for t in sight.things):
            return True
        names = [kit.name_of(p.track) or "" for p in sight.people]
        return label in ("someone", "a person", "anyone") and bool(sight.people) or any(label == n.lower() for n in names if n)

    async def _run_skill(self, skill, request: Request, asker: Asker, how: str, words: str) -> Verdict:
        commands = self.commands
        steps, errors = self.card_of().check(skill.steps)
        if errors or not steps:
            self.record("skill_broken", name=skill.name, errors=len(errors))
        verdict = commands.decide_now(Request("try_new", text=words[:160]), asker)
        if not verdict.yes:
            await commands._answer(Request("try_new", text=words[:160]), asker, verdict, how)
            return verdict
        kept = []
        lines = []
        for step in steps:
            refused, _ = await self.gate(step, asker, ahead=True)
            if refused is None:
                kept.append(step)
            elif refused.say and refused.say not in lines:
                lines.append(refused.say)
        if not asker.own:
            for line in lines:
                self.say(line)
        if not kept or not any(step["do"] in EXPRESSIVE for step in kept):
            if not asker.own:
                self.say(NOTHING_LEFT)
            return Verdict("no", f"the steps of your {skill.name} were refused just now", NOTHING_LEFT)
        if lines and not asker.own:
            self.say(LEFT_OUT)
        if how != "then":
            commands.plan = commands.make_plan(asker, list(request.then)) if request.then else None
        elif request.then:
            commands.plan = commands.make_plan(asker, list(request.then) + (list(commands.plan.steps) if commands.plan is not None else []))
        activity = Try(Request("try_new", text=words[:160], name=skill.name), asker, None, False, kept, skill.name, self.gate, self.run_step)
        activity.skill = skill.name
        self.after = (skill, asker, activity, self.clock.now(), words)
        self.record("skill_run", name=skill.name, person=asker.id, how=how)
        commands.note(f"{asker.label} asked you to do your {skill.name}, which you know how to do" if not asker.own else f"you did your {skill.name}", False)
        commands.runner.kit.face.show("happy")
        commands.did(request, asker, how)
        commands.runner.start(activity)
        return Verdict("yes", f"you know how to do the {skill.name}", "")

    def ended(self, activity: Activity, ending: Ending) -> bool:
        if self.after is not None and activity is self.after[2]:
            if ending.how == "done":
                self.skills.used(self.after[0], True, self.after[4])
            return False
        loop = self.loop
        if loop is None or activity is not loop.activity:
            return False
        how = ending.how
        if how == "done":
            if loop.one_off and loop.asker.own:
                self._close("done", False)
                return False
            loop.tries.append({"steps": list(loop.current), "answer": "", "answer_kind": ""})
            loop.waiting_since = self.clock.now()
            loop.asked += 1
            question = self._line(ASKS)
            if getattr(activity, "problems", None):
                question = PART_ONLY + question
            self.say(question)
            return True
        if how == "stopped":
            self._close("stopped", False)
            return False
        if how == "replaced":
            self._close("replaced", True)
            return False
        if how == "battery":
            self._close("rest", True)
            self.say(REST["battery"])
            return True
        return False

    def dropped(self, activity: Activity, ending: Ending) -> None:
        loop = self.loop
        if loop is not None and activity is loop.activity:
            loop.tries.append({"steps": list(loop.current), "answer": "", "answer_kind": "rest"})
            self._close(f"ended {ending.how}", True)

    def _close(self, how: str, keep: bool) -> None:
        loop = self.loop
        if loop is None:
            return
        self.loop = None
        draft = None
        if keep and loop.drafts and not loop.one_off:
            tries = list(loop.tries)
            if loop.current and not same(loop.current, tries):
                tries.append({"steps": list(loop.current), "answer": "", "answer_kind": "silence"})
            try:
                draft = self.skills.draft(loop.name, loop.words, tries, loop.asker.id)
            except Exception:
                log.exception("could not keep a draft of a try")
        self.record("try_ended", name=loop.name, how=how, tries=len(loop.tries), draft=draft is not None)
        current = self.commands.runner.current
        if current is loop.activity and current is not None and how not in ("stopped", "replaced", "done", "kept") and not how.startswith("ended"):
            self.commands.runner.end("stopped", f"you stopped trying {loop.name} ({how})")

    def _resume_held(self, loop: Loop) -> None:
        if not loop.held:
            return
        rest = loop.held
        self.commands._spawn(self.commands.act(rest[0].with_(then=tuple(rest[1:])), self.commands.fresh(loop.asker), "then"))

    async def heard(self, heard) -> object | None:
        from ..understand.resolve import Reading

        text = heard.text or ""
        now = self.clock.now()
        done = Reading(Request("chat"), source="rules", answered=True)
        after = self.after
        if after is not None and now - after[3] > AFTER_SKILL_S:
            self.after = after = None
        loop = self.loop
        if loop is None and after is not None and heard.stop is None:
            answer = answer_of(text, self.commands.name.lower())
            if answer is not None and answer[0] in ("no", "nearly") and (NOT_LIKE.match(plain(text)) or answer[0] == "nearly"):
                person = self.commands.asker_heard(heard)
                if self._may_answer(person, after[1]):
                    await self._reopen(after, person, answer)
                    return done
            return None
        if loop is None:
            return None
        if heard.stop is not None:
            self._close("stopped", False)
            return None
        said = plain(text)
        if END.match(said) or (said in ("stop", "stop it") and loop.waiting_since is not None):
            person = self.commands.asker_heard(heard)
            if self._may_answer(person, loop.asker):
                self._close("never mind", False)
                if self.commands.runner.current is loop.activity and loop.activity is not None:
                    self.commands.runner.end("stopped", f"{person.label} said never mind")
                await self.speak(NEVER_MIND)
                return done
            return None
        if loop.waiting_since is None:
            if LAUGH.search(said):
                self.hint("laugh")
                return None
            return None
        answer = answer_of(text, self.commands.name.lower())
        if answer is None:
            return None
        kind, change = answer
        if kind == "laugh":
            self.hint("laugh")
            return done
        person = self.commands.asker_heard(heard)
        if not self._may_answer(person, loop.asker):
            self.record("try_answer_ignored", name=loop.name, tier=person.tier, said=kind)
            return None
        if kind == "yes" and not person.sure:
            self.hint("unseen yes")
            self.record("try_answer_ignored", name=loop.name, tier=person.tier, said=kind, why="not seen saying it")
            return done
        loop.waiting_since = None
        if loop.tries:
            loop.tries[-1]["answer"] = text[:80]
            loop.tries[-1]["answer_kind"] = kind
        self.record("try_answer", name=loop.name, said=kind, person=person.id, tier=person.tier)
        if kind == "yes":
            await self._yes(loop, person)
        elif kind == "nearly":
            self.commands._spawn(self._nearly(loop, change or text))
        elif kind == "no":
            self.commands._spawn(self._another(loop))
        elif kind == "end":
            self._close("never mind", False)
            await self.speak(NEVER_MIND)
        return done

    def _may_answer(self, person: Asker, asker: Asker) -> bool:
        if person.own:
            return False
        if asker.id is not None and person.id == asker.id:
            return True
        if asker.id is None and asker.tier == STRANGER and person.tier == STRANGER:
            return True
        return person.tier in TEACHERS or person.owner

    def hint(self, kind: str) -> None:
        loop = self.loop
        if loop is None:
            return
        number = len(loop.tries) + (0 if loop.waiting_since is not None else 1)
        words = {"laugh": "someone laughed", "clap": "someone clapped", "unseen yes": "someone said yes where you couldn't see them"}.get(kind, kind)
        note = f"{words} during try {number}"
        if note not in loop.hints:
            loop.hints.append(note)
            self.record("try_hint", name=loop.name, sound=kind, try_number=number)

    async def _yes(self, loop: Loop, person: Asker) -> None:
        teacher = person.tier in TEACHERS or person.owner
        keeps = teacher and person.id is not None and not loop.asker.own and loop.asker.tier != STRANGER and bool(loop.current)
        self._close("kept" if keeps else "one-off", False)
        if keeps:
            try:
                skill = self.skills.keep(loop.name, loop.words, loop.current, {"id": person.id, "name": person.label, "tier": "owner" if person.owner else person.tier}, replacing=loop.skill)
            except Exception:
                log.exception("could not keep a skill")
                skill = None
            if skill is not None:
                self.commands.runner.kit.face.show("love")
                how = self._spoken(how_to(skill.name))
                self.commands.note(f"{person.label} said yes, so you kept how to {how} for this body", False)
                self.commands.diary(f"I learned how to {how}" + ("" if loop.skill is None else " a new way") + f", because {person.label} liked it.", "activity")
                await self.speak((REPLACED if loop.skill is not None else KEPT).format(how=how))
        else:
            self.record("try_one_off", name=loop.name, tier=person.tier)
            self.commands.runner.kit.face.show("happy")
            await self.speak(ONE_OFF)
        self._resume_held(loop)

    async def _nearly(self, loop: Loop, change: str) -> None:
        last = list(loop.current)
        planned = await self._plan(loop, CHANGE_ASK.format(number=len(loop.tries), steps=json.dumps(last, separators=(",", ":")), change=change))
        steps = planned.steps
        if loop is not self.loop:
            return
        if not steps or same(steps, loop.tries[-1:]):
            steps = changed(last, change) or []
        if not steps:
            self._show_me(loop)
            await self.speak(NO_CHANGE)
            self._close("no change", True)
            return
        self.say(self._line(CHANGED))
        await self._try(loop, steps)

    async def _another(self, loop: Loop) -> None:
        planned = await self._plan(loop, ANOTHER_ASK)
        if loop is not self.loop:
            return
        steps = planned.steps
        if steps and same(steps, loop.tries):
            again = await self._plan(loop, f"That plan is the same as an earlier try. Make one that is different from all {len(loop.tries)} tries above.")
            if loop is not self.loop:
                return
            steps = again.steps if again.steps and not same(again.steps, loop.tries) else []
        if not steps:
            self.record("try_out_of_ideas", name=loop.name, tries=len(loop.tries))
            self._show_me(loop)
            self._close("out of ideas", True)
            await self.speak(OUT_OF_IDEAS)
            return
        self.say(self._line(ANOTHER))
        await self._try(loop, steps)

    def _show_me(self, loop: Loop) -> None:
        if self.on_show is None or loop.asker.own:
            return
        try:
            self.on_show(loop.name, loop.words, loop.asker)
        except Exception:
            log.exception("could not offer to be shown how")

    async def _reopen(self, after: tuple, person: Asker, answer: tuple) -> None:
        skill, asker, _, _, words = after
        self.after = None
        self.skills.used(skill, False)
        loop = Loop(skill.name, words, self.commands.fresh(asker), "heard", skill=skill, drafts=True)
        loop.current = list(skill.steps)
        kind, change = answer
        loop.tries = [{"steps": list(skill.steps), "answer": change or "no, not like that", "answer_kind": kind}]
        self.loop = loop
        self.record("skill_reopened", name=skill.name, person=person.id)
        if kind == "nearly" and change:
            self.commands._spawn(self._nearly(loop, change))
        else:
            self.commands._spawn(self._another(loop))

    def tick(self) -> None:
        loop = self.loop
        if loop is None:
            return
        now = self.clock.now()
        fence = ""
        try:
            fence = self.fence() or ""
        except Exception:
            fence = ""
        if fence in REST and not loop.planning:
            running = self.commands.runner.current is loop.activity and loop.activity is not None
            if loop.current and not same(loop.current, loop.tries):
                loop.tries.append({"steps": list(loop.current), "answer": "", "answer_kind": "rest"})
            self._close("rest", True)
            if running:
                self.commands.runner.end("stopped", f"you stopped trying {loop.name} to rest ({fence})")
            self.say(REST[fence])
            return
        if loop.waiting_since is not None and now - loop.waiting_since > ANSWER_WAIT_S:
            if loop.tries:
                loop.tries[-1]["answer_kind"] = "silence"
            self._close("silence", True)
            self.say(SILENT)
            return
        asker = loop.asker
        if asker.id is not None and loop.waiting_since is not None and not self.commands.present_within(asker.id, LEFT_S):
            if loop.tries:
                loop.tries[-1]["answer_kind"] = "left"
            self._close("left", True)
