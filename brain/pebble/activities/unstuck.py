import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable

from ..mind.base import CallOptions, MindUnavailable, options_kwargs
from ..mind.budget import GUIDE, JOB, WORDS, Prompt
from ..understand.request import Request
from .base import Activity, Ending
from .gate import Asker, Verdict

log = logging.getLogger(__name__)

DECISIONS_MOST = 3
WAIT_S = 20.0
HELP_WAIT_S = 30.0
CASE_KEEP_S = 600.0
ASK_WAIT_S = 6.0
MAX_TOKENS = 24
KINDS = frozenset({"come", "go_to_place", "go_to_thing", "find", "go_back", "play", "check", "follow", "try_new"})
ENDINGS = frozenset({"blocked", "lost", "reflex", "refused"})
NOT_STUCK = re.compile(r"moving is off|fault|stay still|asleep|quiet hours|edge|privacy|private")
OPTIONS = ("another_way", "wait", "ask", "explain", "give_up")
WORDS_FOR = {
    "another_way": "try another way",
    "wait": "wait a little and try again",
    "ask": "ask {who} for help",
    "explain": "go back to {asker} and explain",
    "give_up": "give up and say why",
}
SKIP_WORDS = "leave that part out and carry on with the rest"
GUIDE_TEXT = "You decide what {name}, a small home robot on two wheels, does next after something went wrong. Pick one of the options. Reply with JSON only."
WAITING = "I'll wait a moment and try again."
TRYING = "I'll try another way."
SKIPPING = "I'll leave that part out and carry on."


@dataclass
class Case:
    key: str
    asker: Asker
    request: Request
    words: str
    at: float
    decisions: int = 0
    chose: list = field(default_factory=list)
    pending: str = ""


def _key(asker: Asker, request: Request) -> str:
    if request.kind == "try_new":
        return f"{asker.id}:try:{request.name}"
    return f"{asker.id}:" + json.dumps(request.with_(then=()).as_dict(), sort_keys=True)


REFUSED = re.compile(r"was refused \((.*)\)$")
SAY_TAIL = re.compile(r",? so I(?:'ll)? stop(?:ped)? here\.?$|\.? I'll stop here\.?$", re.IGNORECASE)


def problem_of(ending: Ending) -> str:
    said = SAY_TAIL.sub("", (ending.say or "").strip()).strip().rstrip(".")
    if said and ending.how != "refused":
        return said if said.startswith(("I ", "I'")) else said[:1].lower() + said[1:]
    text = ending.text or ""
    found = REFUSED.search(text)
    if found:
        text = found.group(1)
    if text.startswith("while trying ") and ", " in text:
        text = text.split(", ", 1)[1]
    text = re.sub(r"\b(asked|told|let|wants?|wanted|needs?|trusts?) you\b", r"\1 me", text)
    text = re.sub(r"\byou\b", "I", re.sub(r"\byour\b", "my", text))
    return text.rstrip(".")


class Unstuck:
    def __init__(self, commands, mind_of: Callable[[], object | None], name: str = "Pebble", wait_s: float = ASK_WAIT_S, monotonic: Callable[[], float] = time.monotonic):
        self.commands = commands
        self.mind_of = mind_of
        self.name = name
        self.wait_s = wait_s
        self.monotonic = monotonic
        self.case: Case | None = None
        self.keep: Callable[[dict], None] = lambda record: None

    @property
    def clock(self):
        return self.commands.clock

    def _fresh_case(self, asker: Asker, request: Request, words: str) -> Case:
        now = self.clock.now()
        key = _key(asker, request)
        case = self.case
        if case is None or case.key != key or now - case.at > CASE_KEEP_S:
            case = Case(key, asker, request, words, now)
            self.case = case
        return case

    def wants(self, activity: Activity, ending: Ending) -> bool:
        if activity.asker.own or activity.urgent or activity.homing or activity.battery:
            return False
        if self.mind_of() is None and not (self.case is not None and self.case.decisions):
            return False
        if activity.kind not in KINDS or ending.how not in ENDINGS or (activity.kind == "play" and not activity.request.to):
            return False
        if ending.how != "refused" and NOT_STUCK.search(ending.text or ""):
            return False
        if ending.how == "reflex" and "stuck" not in (ending.text or ""):
            return False
        return True

    def observe(self, activity: Activity, ending: Ending) -> None:
        case = self.case
        if case is None or not case.pending or _key(activity.asker, activity.request) != case.key:
            return
        label = f"{case.pending} worked" if ending.how == "done" else f"{case.pending} did not help"
        self._outcome(case, label, activity, ending)
        case.pending = ""
        if ending.how == "done":
            self.case = None

    def ended(self, activity: Activity, ending: Ending) -> bool:
        if not self.wants(activity, ending):
            return False
        words = activity.describe()
        case = self._fresh_case(activity.asker, activity.request, words)
        self.commands._spawn(self._decide(case, activity, ending))
        return True

    def refused(self, request: Request, asker: Asker, verdict: Verdict) -> bool:
        if asker.own or self.mind_of() is None or self.commands.plan is None or not self.commands.plan.steps:
            return False
        case = self._fresh_case(asker, Request("other", text="plan"), "the rest of what you asked")
        ending = Ending("refused", f"{verdict.reason}", "")
        self.commands._spawn(self._decide(case, None, ending, refused=request))
        return True

    def options(self, activity: Activity | None, ending: Ending, asker: Asker) -> list[tuple[str, str]]:
        if ending.how == "refused":
            out = [("another_way", ""), ("explain", ""), ("give_up", "")]
        else:
            out = [("another_way", ""), ("wait", "")]
            for name in self._helpers(asker):
                out.append(("ask", name))
            out += [("explain", ""), ("give_up", "")]
        return out

    def _helpers(self, asker: Asker) -> list[str]:
        commands = self.commands
        now = self.clock.now()
        names = []
        if asker.id is not None and commands.present(asker.id):
            names.append(asker.label)
        for person in commands.company.here(now):
            if person.label not in names and commands.company.tier(person, now) != "stranger":
                names.append(person.label)
        return names[:3]

    def _prompt(self, case: Case, activity: Activity | None, ending: Ending, options: list, refused: Request | None) -> Prompt:
        asker = case.asker
        doing = activity.describe() if activity is not None else "a plan of steps"
        what = f"{self.name} was {doing} for {asker.label}." if not refused else f"{self.name} was doing a plan of steps for {asker.label}, and one step was refused."
        lines = [what, f"It stopped: {problem_of(ending)}."]
        if case.chose:
            lines.append("Already tried: " + ", ".join(case.chose) + ".")
        lines.append("Options:")
        for option, who in options:
            if option == "another_way" and ending.how == "refused":
                lines.append(f"another_way: {SKIP_WORDS}")
            else:
                lines.append(f"{option}: " + WORDS_FOR[option].format(who=who or "someone", asker=asker.label))
        system = GUIDE_TEXT.format(name=self.name)
        user = "\n".join(lines)
        return Prompt([{"role": "system", "content": system}, {"role": "user", "content": user}], JOB, [(GUIDE, 0, system), (WORDS, 1, user)])

    def _grammar(self, options: list) -> str:
        chosen = sorted({option for option, _ in options}, key=OPTIONS.index)
        names = sorted({who.lower() for _, who in options if who})
        choice = " | ".join(f'"\\"{o}\\""' for o in chosen)
        rules = [f'root ::= "{{" ws "\\"choose\\":" ws ({choice})' + (' ("," ws "\\"who\\":" ws who)?' if names else "") + ' ws "}"']
        if names:
            rules.append("who ::= " + " | ".join(f'"\\"{n}\\""' for n in names))
        rules.append('ws ::= " "?')
        return "\n".join(rules) + "\n"

    async def what_now(self, case: Case, activity: Activity | None, ending: Ending, options: list, refused: Request | None = None) -> tuple[str, str] | None:
        mind = self.mind_of()
        if mind is None:
            return None
        prompt = self._prompt(case, activity, ending, options, refused)
        call = CallOptions("steady", 0.3, 0.9, 0.1, grammar=self._grammar(options))
        try:
            reply = await asyncio.wait_for(mind.chat(prompt, purpose="unstuck", max_tokens=MAX_TOKENS, **options_kwargs(call)), self.wait_s)
            text = reply.text or ""
            data = json.loads(text[text.find("{") : text.rfind("}") + 1])
        except (MindUnavailable, asyncio.TimeoutError, ValueError, AttributeError) as error:
            log.info("the what-now call gave no answer (%s)", error or "timed out")
            return None
        if not isinstance(data, dict):
            return None
        choice = str(data.get("choose") or "")
        who = str(data.get("who") or "").lower()
        for option, name in options:
            if option == choice and (option != "ask" or not who or name.lower() == who):
                return option, name
        return None

    async def _decide(self, case: Case, activity: Activity | None, ending: Ending, refused: Request | None = None) -> None:
        commands = self.commands
        try:
            if activity is not None and ending.say:
                await commands.speak(ending.say, False)
            if case.decisions >= DECISIONS_MOST:
                await self._explain(case, activity, ending, "I tried three times")
                self._outcome(case, "went back to explain after three tries", activity, ending)
                self.case = None
                return
            options = self.options(activity, ending, case.asker)
            chosen = await self.what_now(case, activity, ending, options, refused)
            if chosen is None:
                commands.record("unstuck", ended=ending.how, chose=None, decision=case.decisions, activity=activity.kind if activity is not None else "plan", person=case.asker.id)
                self._outcome(case, "stopped, with no decision from the model", activity, ending)
                self.case = None
                self._drop(activity, ending)
                return
            choice, who = chosen
            case.decisions += 1
            case.chose.append(WORDS_FOR[choice].format(who=who or "someone", asker=case.asker.label) if not (choice == "another_way" and ending.how == "refused") else SKIP_WORDS)
            commands.record("unstuck", ended=ending.how, chose=choice, decision=case.decisions, activity=activity.kind if activity is not None else "plan", person=case.asker.id)
            what = "a step was refused" if ending.how == "refused" else "you got stuck"
            commands.note(f"{what} ({problem_of(ending)}) and you chose to {case.chose[-1]}", False)
            await self._run(case, choice, who, activity, ending, refused)
        except Exception:
            log.exception("deciding what to do after getting stuck failed")
            if self.case is case:
                self.case = None

    async def _run(self, case: Case, choice: str, who: str, activity: Activity | None, ending: Ending, refused: Request | None) -> None:
        commands = self.commands
        kit = commands.runner.kit
        if choice == "give_up":
            line = self._gave_up(case, activity, ending)
            self._outcome(case, "gave up", activity, ending)
            self.case = None
            self._drop(activity, ending)
            await commands.speak(line, False)
            return
        if choice == "explain":
            await self._explain(case, activity, ending, "")
            self._outcome(case, "went back to explain", activity, ending)
            self.case = None
            return
        if refused is not None:
            plan = commands.plan
            if plan is None or not plan.steps:
                self.case = None
                return
            await commands.speak(SKIPPING, False)
            step = plan.steps.pop(0)
            if not plan.steps:
                commands.plan = None
            self._outcome(case, "left the refused part out", None, ending)
            self.case = None
            commands._spawn(commands.act(step, commands.fresh(plan.asker), "then"))
            return
        if choice == "wait":
            await commands.speak(WAITING, False)
            case.pending = "waiting"
            if not await self._pause(case, WAIT_S):
                return
        elif choice == "ask":
            problem = ending.say or f"{problem_of(ending)}."
            kit.say_loud(f"{who}, could you help me? {problem}".strip())
            case.pending = f"asking {who}"
            if not await self._pause(case, HELP_WAIT_S):
                return
        else:
            if ending.how == "refused":
                await commands.speak(SKIPPING, False)
            elif ending.say:
                await commands.speak(TRYING, False)
            case.pending = "another way"
        await self._retry(case, activity, ending)

    async def _pause(self, case: Case, seconds: float) -> bool:
        kit = self.commands.runner.kit
        start = self.commands.runner.history[-1] if self.commands.runner.history else None
        await kit.pace.sleep(seconds)
        if self.case is not case or self.commands.runner.current is not None:
            return False
        latest = self.commands.runner.history[-1] if self.commands.runner.history else None
        return latest is start

    async def _retry(self, case: Case, activity: Activity | None, ending: Ending) -> None:
        commands = self.commands
        if activity is not None and activity.kind == "try_new" and commands.trying is not None:
            if await commands.trying.carry_on(activity, list(activity.rest)):
                return
            commands.trying.dropped(activity, ending)
            self.case = None
            return
        if activity is None:
            return
        await commands.act(activity.request, commands.fresh(case.asker), "unstuck")

    def _drop(self, activity: Activity | None, ending: Ending) -> None:
        if activity is not None and activity.kind == "try_new" and self.commands.trying is not None:
            self.commands.trying.dropped(activity, ending)
        else:
            self.commands.plan = None

    def _gave_up(self, case: Case, activity: Activity | None, ending: Ending) -> str:
        what = case.words or "that"
        if ending.say or ending.how == "refused":
            return f"So I'll stop {what}."
        return f"I'll stop {what}: {problem_of(ending)}."

    async def _explain(self, case: Case, activity: Activity | None, ending: Ending, lead: str) -> None:
        from .watch import Fetch

        commands = self.commands
        asker = case.asker
        self._drop(activity, ending)
        problem = problem_of(ending)
        what = case.words or "what you asked"
        line = f"I couldn't finish {what}: {problem}." if not lead else f"{lead}, but I couldn't finish {what}: {problem}."
        if asker.id is not None and commands.present(asker.id) and commands.runner.kit.seen(asker.id, 30.0):
            await commands.speak(f"{asker.label}, {line}", False)
            return
        kit = commands.runner.kit
        spot = kit.where_was(asker.id) if asker.id else None
        commands.runner.start(Fetch(Request("come", who=asker.label.lower()), asker, None, False, line, spot))

    def _outcome(self, case: Case, label: str, activity: Activity | None, ending: Ending) -> None:
        record = {"at": self.clock.now(), "activity": activity.kind if activity is not None else "plan", "ended": ending.how, "problem": problem_of(ending)[:120], "chose": list(case.chose), "label": label}
        self.commands.record("unstuck_outcome", **{k: v for k, v in record.items() if k != "at"})
        try:
            self.keep(record)
        except Exception:
            log.exception("could not keep what happened after getting stuck")
