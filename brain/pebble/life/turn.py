import json
import logging
import re
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

from ..clock import Clock, iso
from ..mind.base import CallOptions, Mind, MindInterrupted, MindUnavailable, assistant_message, options_kwargs, tool_message
from ..mind.budget import BOARD, BOARD_LEADS, CORE, ESTIMATE_MARGIN, FOLD, HISTORY, MATCHED, PEOPLE, REPLY, REPLY_TRIM, TASK, TOOLS, TURN, WORDS, WORK, Prompt, budgets, ceiling, note_event
from ..mind.history import History
from ..mind.prompt import PRIVATE, TURN_GUIDE, PromptBuilder
from ..mind.select import named_chars, pack
from ..mind.tokens import estimate_messages, estimate_text
from ..self.gatekeeper import PAUSED
from ..selfstore import SelfStore
from ..tools.registry import ToolRegistry

log = logging.getLogger(__name__)

MONOLOGUE = "logs/monologue.jsonl"
OVERHEARD_MASK = "[what you overheard then; not kept]"
REPLY_GUIDE = (
    "Someone is talking to you right now and you answer out loud. Reply in one to three short spoken sentences, in your own voice. "
    "No stage directions, no lists, no emoji, no quotes. If you don't know, say so briefly. "
    "Never repeat to anyone what you overheard about someone else, and never pass on what someone told you in private."
)
NOT_NOW = "Tools you can't use just now: {names}."
PARTS_NOT_NOW = "Not just now: {what}."
OFF_WORDS = {"draw_scene": "drawing", "show_scene": "drawing", "move": "moving"}
DEEP_ROUNDS = 2
REPLY_HEADROOM = 0.9
DEEP_TOKENS = 2
SAID = re.compile(r'is talking to you: "(.*)"\s*$', re.M)
HEARD_LINES = ("Heard:", "Events:")


def said_in(observation: str, kind: str) -> str:
    if kind == REPLY:
        found = SAID.findall(observation or "")
        return found[-1] if found else ""
    return " ".join(line.split(":", 1)[1] for line in (observation or "").splitlines() if line.startswith(HEARD_LINES))


@dataclass
class TurnResult:
    ran: bool
    thought: str = ""
    calls: list = field(default_factory=list)
    error: str | None = None
    compacted: int = 0
    interrupted: bool = False


def _bad_json(call) -> bool:
    raw = (call.raw_arguments or "").strip()
    return not call.arguments and raw not in ("", "{}")


class TurnRunner:
    def __init__(
        self,
        mind: Mind,
        history: History,
        builder: PromptBuilder,
        registry: ToolRegistry,
        store: SelfStore,
        clock: Clock,
        max_rounds: int = 3,
        max_calls: int = 4,
        options: Callable[[], CallOptions | None] | None = None,
    ):
        self.mind = mind
        self.history = history
        self.builder = builder
        self.registry = registry
        self.store = store
        self.clock = clock
        self.max_rounds = max_rounds
        self.max_calls = max_calls
        self.options = options
        self._replying: tuple | None = None
        self.audience = lambda: ()
        self.matched = lambda kind=REPLY: ""
        self.named: Callable[[str, str], list] = lambda words, kind: []
        self._ahead: tuple | None = None
        self.card: Callable[[str], str] = lambda kind: ""
        self.after_reply: Callable[[dict], None] | None = None
        self.folding: Callable[..., object] | None = None
        self.trims = 0
        self.fixed_seen = 0
        self._tools: list[dict] | None = None

    def _keep(self, current: list[dict], at: str) -> None:
        self.history.add_turn(current, at, t=self.clock.now(), audience=list(self.audience()))

    def _people(self, people: str) -> tuple[str, str, str]:
        if not self.history.profile.people_in_message:
            return people, "", ""
        return "", self.builder.household_text(), people.strip()

    def _lead(self, messages: list[dict], count: int, lead: list[str]) -> list[dict]:
        lead = [part for part in lead if part]
        if not lead or count <= 0:
            return messages
        index = len(messages) - count
        message = messages[index]
        messages[index] = {**message, "content": "\n\n".join(lead + [message.get("content") or ""])}
        return messages

    def _off(self, offered: list[str], tool_names: list[str]) -> list[str]:
        words = []
        for name in offered:
            tool = self.registry.tool(name)
            for act in getattr(tool, "acts", ()) or ():
                word = OFF_WORDS.get(act)
                if word and act not in tool_names and self.registry.action(act) is not None and word not in words:
                    words.append(word)
        return words

    def _shown(self, tool_names: list[str]) -> list[str]:
        if not tool_names:
            return []
        if not self.history.profile.steady_tools:
            return self.registry.offered(tool_names)
        return self.registry.names()

    def _fixed_tokens(self, system: str, current: list[dict]) -> int:
        profile = self.history.profile
        cpt = profile.chars_per_token
        fixed = estimate_text(system, cpt) + estimate_messages(current, cpt)
        if self._tools:
            fixed += max(0, estimate_text(json.dumps(self._tools), cpt) - budgets(TURN, profile.window())[TOOLS])
        self.fixed_seen = fixed
        return fixed

    def _prompt(self, kind: str, parts: list[tuple[str, str]], current: list[dict], private_to: str | None, lead: list[tuple[str, str]], tail: str = "") -> Prompt:
        system = "\n\n".join(text for _, text in parts)
        history = self.history.messages()
        messages = self._lead(self.builder.build(system, history, current, private_to), len(current), [text for _, text in lead])
        first = 1 + len(history)
        if tail:
            message = messages[first]
            messages[first] = {**message, "content": (message.get("content") or "") + "\n" + tail}
        found = [(section, 0, text) for section, text in parts if section != CORE]
        found += [(section, first, text) for section, text in lead if text and section != WORDS]
        if tail:
            found.append((MATCHED, first, tail))
        content = messages[first].get("content") or ""
        found += [(BOARD, first, line) for line in content.split("\n") if line.startswith(BOARD_LEADS)]
        return Prompt(messages, kind, found, [(HISTORY, 1, first), (WORK, first + 1, len(messages))])

    def _matched(self, kind: str = REPLY) -> str:
        try:
            return self.matched(kind) or ""
        except Exception:
            log.exception("could not list what is due soon")
            return ""

    def _named(self, words: str, kind: str) -> list:
        if not words:
            return []
        try:
            return list(self.named(words, kind) or [])
        except Exception:
            log.exception("could not look for named things")
            return []

    def _matched_parts(self, observation: str, kind: str, ahead: str | None = None) -> tuple[str, str]:
        chosen = self._matched(kind)
        words = said_in(observation, kind)
        found = self._named(words, kind)
        if ahead == "warm":
            self._ahead = (words, tuple(i for i, _ in found), tuple(line for _, line in found))
            lead, tail = [line for _, line in found], []
        elif ahead == "reply" and self._ahead is not None and words.startswith(self._ahead[0]):
            known, lead = self._ahead[1], list(self._ahead[2])
            room = named_chars(kind) - sum(len(line) + 1 for line in lead)
            tail = pack([(line, "") for i, line in found if i not in known], room)
        else:
            lead, tail = [line for _, line in found], []
        joined = "\n".join(part for part in [chosen] + lead if part)
        return joined, "\n".join(tail)

    def _card(self, kind: str) -> str:
        try:
            return self.card(kind) or ""
        except Exception:
            log.exception("could not build the task card")
            return ""

    async def _fold(self, where: str, at: str, warm: bool = True) -> int:
        if self.folding is not None:
            folded = await self.folding(where, warm)
        else:
            result = await self.history.compact(self.mind, at)
            folded = result.folded
            note_event(self.store, self.clock, FOLD, where=where, turns=folded)
        if folded:
            log.info("folded %d turns into the memory stream (%s)", folded, where)
        return folded

    async def _compact_if_needed(self, stage: str, values_text: str, current: list[dict], at: str, people: str = "") -> int:
        system = self.builder.system_text(stage, values_text, self.history.summary, people)
        if not self.history.needs_compaction(self._fixed_tokens(system, current)):
            return 0
        return await self._fold("turn_start", at, warm=False)

    def fold_due(self, stage: str, values_text: str, people: str = "") -> bool:
        if not self.history.turns:
            return False
        if self.fixed_seen and not self.history.soft_due(self.fixed_seen):
            return False
        system = self.builder.system_text(stage, values_text, self.history.summary, people)
        return self.history.soft_due(self._fixed_tokens(system, []))

    async def fold_if_due(self, stage: str, values_text: str, people: str = "", where: str = "quiet") -> int:
        if not self.fold_due(stage, values_text, people):
            return 0
        return await self._fold(where, iso(self.clock.now()))

    async def _trim_for_reply(self, observation: str, stage: str, values_text: str, people: str, room: int, at: str) -> int:
        profile = self.history.profile
        cpt = profile.chars_per_token
        system = self.builder.system_text(stage, values_text, self.history.summary, people)
        lead = estimate_text(self._card(REPLY), cpt) + estimate_text(self._matched(REPLY), cpt)
        fixed = estimate_text(system, cpt) + estimate_text(observation, cpt) + lead + int(room)
        top = ceiling(REPLY, profile.window())
        trimmed = 0
        while self.history.turns and (fixed + self.history.tokens()) * ESTIMATE_MARGIN > top * REPLY_HEADROOM:
            result = await self.history.compact(self.mind, at, oldest=1)
            if not result.folded:
                break
            trimmed += result.folded
        if trimmed:
            self.trims += trimmed
            note_event(self.store, self.clock, REPLY_TRIM, turns=trimmed)
            log.info("the reply path had to fold the oldest %d turns to fit the window", trimmed)
        return trimmed

    async def run(
        self,
        observation: str,
        tool_names: list[str],
        stage: str,
        values_text: str,
        people: str = "",
        private: list | None = None,
        private_to: str | None = None,
        deep: bool = False,
    ) -> TurnResult:
        at = iso(self.clock.now())
        shown = self._shown(tool_names)
        offered = self.registry.offered(tool_names) if tool_names else []
        hidden = [name for name in shown if name not in offered]
        if hidden:
            observation = "\n".join([observation, NOT_NOW.format(names=", ".join(hidden))])
        off = self._off(offered, tool_names)
        if off:
            observation = "\n".join([observation, PARTS_NOT_NOW.format(what=", ".join(off))])
        first = {"role": "user", "content": observation}
        if private:
            first[PRIVATE] = list(private)
        current = [first]
        compacted = await self._compact_if_needed(stage, values_text, current, at, people)
        in_system, household, here = self._people(people)
        parts = self.builder.system_parts(stage, values_text, self.history.summary, in_system, household)
        matched, _ = self._matched_parts(observation, TURN)
        card = self._card(TURN)
        schemas = self.registry.schemas(shown) or None
        self._tools = schemas
        thoughts: list[str] = []
        calls: list[dict] = []
        longer = {"max_tokens": self.history.profile.max_reply_tokens * DEEP_TOKENS} if deep else {}
        try:
            for _ in range(self.max_rounds + DEEP_ROUNDS if deep else self.max_rounds):
                messages = self._prompt(TURN, parts, current, private_to, [(PEOPLE, here), (TASK, card), (MATCHED, matched)])
                options = self.options() if self.options is not None else None
                reply = await self.mind.chat(messages, tools=schemas, purpose="turn", **longer, **options_kwargs(options))
                current.append(assistant_message(reply))
                if reply.text:
                    thoughts.append(reply.text)
                if not reply.tool_calls:
                    break
                paused = False
                for index, call in enumerate(reply.tool_calls):
                    if paused:
                        result = {"ok": False, "error": PAUSED}
                    elif index >= self.max_calls:
                        result = {"ok": False, "error": "too many tool calls at once"}
                    elif _bad_json(call):
                        result = {"ok": False, "error": "the arguments were not valid JSON"}
                    else:
                        result = await self.registry.call(call.name, call.arguments, allowed=tool_names)
                        paused = bool(result.get("paused"))
                    current.append(tool_message(call, result))
                    calls.append({"name": call.name, "args": call.arguments, "result": result})
                if paused:
                    break
        except MindInterrupted:
            if len(current) > 1:
                self._keep(current, at)
            return TurnResult(False, " ".join(thoughts), calls, None, compacted, True)
        except MindUnavailable as error:
            if len(current) > 1:
                self._keep(current, at)
            return TurnResult(False, " ".join(thoughts), calls, str(error), compacted)
        self._keep(current, at)
        thought = " ".join(thoughts).strip()
        self.store.append(MONOLOGUE, {"at": at, "thought": thought, "tools": [c["name"] for c in calls]})
        compacted += await self.fold_if_due(stage, values_text, people, "turn_end")
        return TurnResult(True, thought, calls, None, compacted)

    async def reply(
        self,
        observation: str,
        stage: str,
        values_text: str,
        people: str = "",
        private: list | None = None,
        private_to: str | None = None,
        max_tokens: int = 90,
        options: CallOptions | None = None,
        speaker: str | None = None,
        tier: str | None = None,
    ) -> AsyncIterator[str]:
        at = iso(self.clock.now())
        await self._trim_for_reply(observation, stage, values_text, people, max_tokens, at)
        current, messages, extra = self._reply_messages(observation, stage, values_text, people, private, private_to, "reply")
        self._ahead = None
        self._replying = (current, at, speaker, tier, tuple(self.audience()))
        async for piece in self.mind.stream(messages, purpose="reply", max_tokens=max_tokens, **extra, **options_kwargs(options)):
            yield piece

    def _reply_messages(self, observation: str, stage: str, values_text: str, people: str, private: list | None, private_to: str | None, ahead: str | None = None) -> tuple[list[dict], list[dict], dict]:
        first = {"role": "user", "content": observation}
        if private:
            first[PRIVATE] = list(private)
        current = [first]
        shared = self.history.profile.reply_shares_turn and bool(self._tools)
        in_system, household, here = self._people(people)
        parts = self.builder.system_parts(stage, values_text, self.history.summary, in_system, household)
        if not shared:
            parts = [(section, text.replace(TURN_GUIDE, REPLY_GUIDE)) for section, text in parts]
        matched, tail = self._matched_parts(observation, REPLY, ahead)
        messages = self._prompt(REPLY, parts, current, private_to, [(PEOPLE, here), (TASK, self._card(REPLY)), (MATCHED, matched), (CORE, REPLY_GUIDE if shared else "")], tail)
        return current, messages, ({"tools": self._tools} if shared else {})

    async def warm(
        self,
        observation: str,
        stage: str,
        values_text: str,
        people: str = "",
        private: list | None = None,
        private_to: str | None = None,
        purpose: str = "warm",
    ) -> bool:
        if not self.history.profile.read_ahead:
            return False
        _, messages, extra = self._reply_messages(observation, stage, values_text, people, private, private_to, "warm")
        return await self.mind.warm(messages, purpose=purpose, **extra)

    def reply_done(self, said: str) -> None:
        if self._replying is None:
            return
        current, at, speaker, tier, audience = self._replying
        self._replying = None
        said = " ".join((said or "").split())
        kept = []
        for message in current:
            message = dict(message)
            items = message.pop(PRIVATE, None) or []
            content = message.get("content") or ""
            for item in items:
                if isinstance(item, dict) and item.get("text"):
                    content = content.replace(str(item["text"]), OVERHEARD_MASK)
            message["content"] = content
            kept.append(message)
        kept.append({"role": "assistant", "content": said or "(you said nothing)"})
        self.history.add_turn(kept, at, t=self.clock.now(), audience=list(audience), by=speaker, tier=tier, checked=True if self.after_reply is not None else None)
        if self.after_reply is not None:
            try:
                self.after_reply(self.history.turns[-1])
            except Exception:
                log.exception("could not look at what was just said")
