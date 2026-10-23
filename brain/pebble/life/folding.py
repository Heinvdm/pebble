import asyncio
import json
import logging
import math
import re

from ..activities.gate import decide_later
from ..clock import iso
from ..conversation.words import CORRECTING, FOR_LATER, PROMISED, REFUSING, SENTENCES
from ..mind.base import CallOptions, MindUnavailable
from ..mind.budget import FOLD, GUIDE, JOB, WORDS, Prompt, note_event
from ..mind.prompt import ROOM, redact
from ..self.recall.core import TALK, WORDS_KEPT, WORDS_PIECE, arguments_of, pieces_of
from ..self.recall.stream import TEXT_MAX, importance
from ..tools.broad import acted
from ..understand.understanding import UNDERSTAND_QUIETLY

log = logging.getLogger(__name__)

QUIET_S = 5.0
TALK_S = 300.0
REWARM = "rewarm"
PICKS = "picks"
PROMISE_HOW = "promise"
ITEM_MADE_S = 600.0
PICK_LINES = 40
PICK_CHARS = 180
PICK_MOST = 5
PICK_LIFT = 3
PICK_TOKENS = 40
PICKS_WAIT_S = 120.0
MIN_LINE = 12
QUIET_WHERE = ("quiet", "turn_end")
CANT_KEEP = "Sorry {label}, I can't keep that promise after all."
PICKS_GUIDE = (
    "You keep a small robot's memory tidy. The numbered lines are old talk and events that are about to leave its short memory. "
    "Pick the lines it would need later: facts about people, plans, promises, corrections, refusals and answers it gave. "
    'Pick at most five, or none. Reply only with JSON: {"keep":[numbers]}.'
)
PICKS_GRAMMAR = 'root ::= "{\\"keep\\":[" list? "]}"\nlist ::= num ("," num)? ("," num)? ("," num)? ("," num)?\nnum ::= [1-9] [0-9]?\n'
SWAPS = {"you": "me", "your": "my", "yours": "mine", "yourself": "myself", "you're": "i'm", "you'll": "i'll"}
WORD = re.compile(r"[A-Za-z']+")
STAMP = re.compile(r"^\d{1,2}:\d{2}:\d{2}\s+")
EVENT_STAMP = re.compile(r";\s+(?=\d{1,2}:\d{2}:\d{2}\s)")


def _short(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def turned(clause: str) -> str:
    return WORD.sub(lambda m: SWAPS.get(m.group(0).lower(), m.group(0).lower()), clause).strip(" .!?")


def promises_in(text: str) -> list[str]:
    return [part.strip() for part in SENTENCES.split(text or "") if PROMISED.search(part)]


def talk_of(turn: dict) -> tuple[str, str, str]:
    label, words, said = "", "", ""
    for message in turn.get("messages") or []:
        content = redact(message).get("content") or ""
        if message.get("role") == "user":
            for line in content.splitlines():
                found = TALK.match(line.strip())
                if found:
                    label, words = found.group("who"), found.group("said")
        elif message.get("role") == "assistant" and content.strip() and not said:
            said = content.strip()
    return label, words, said


def candidates(turns: list[dict]) -> list[dict]:
    out = []
    for turn in turns:
        audience = tuple(str(a) for a in turn.get("audience") or ())
        private = any(m.get("private") for m in turn.get("messages") or [])
        base = {"audience": audience, "at": turn.get("t"), "private": private}
        by = turn.get("by")
        label, words, said = talk_of(turn)
        if by or words:
            head = f'{label or "Someone"} said: "'
            for piece in pieces_of(words, WORDS_KEPT, WORDS_PIECE):
                out.append({**base, "kind": "said", "text": f'{head}{piece}"', "who": by, "tier": turn.get("tier")})
            if said:
                out.append({**base, "kind": "happened", "text": f'You told {label or "them"}: "{_short(said, PICK_CHARS)}"', "talk": True})
            continue
        results = {}
        calls = []
        for message in turn.get("messages") or []:
            content = redact(message).get("content") or ""
            if message.get("role") == "user":
                for line in content.splitlines():
                    if line.startswith("Events:"):
                        body = line[len("Events:"):].strip()
                        for event in EVENT_STAMP.split(body):
                            event = STAMP.sub("", event.strip(), count=1)
                            if event and event != "nothing new":
                                out.append({**base, "kind": "happened", "text": _short(event, PICK_CHARS)})
            elif message.get("role") == "assistant":
                for call in message.get("tool_calls") or []:
                    function = call.get("function") or {}
                    calls.append((str(call.get("id") or ""), str(function.get("name") or "?"), arguments_of(function.get("arguments"))))
            elif message.get("role") == "tool":
                results[str(message.get("tool_call_id") or "")] = arguments_of(content)
        for call_id, name, args in calls:
            out.append({**base, "kind": "happened", "text": _short(acted(name, args, results.get(call_id)), PICK_CHARS)})
    return [line for line in out if len(line["text"]) >= MIN_LINE][:PICK_LINES]


def picked(text: str, count: int) -> list[int]:
    start, end = (text or "").find("{"), (text or "").rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return []
    keep = data.get("keep") if isinstance(data, dict) else None
    if not isinstance(keep, list):
        return []
    out = []
    for value in keep:
        if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= count and value not in out:
            out.append(value)
    return out[:PICK_MOST]


class Picks:
    def __init__(self, life):
        self.life = life
        self.asked = 0
        self.kept = 0

    def messages(self, lines: list[dict]) -> Prompt:
        numbered = "\n".join(f"{n}. {line['text']}" for n, line in enumerate(lines, 1))
        out = [{"role": "system", "content": PICKS_GUIDE}, {"role": "user", "content": numbered}]
        return Prompt(out, JOB, [(GUIDE, 0, PICKS_GUIDE), (WORDS, 1, numbered)])

    async def choose(self, turns: list[dict]) -> int | None:
        lines = candidates(turns)
        if not lines:
            return 0
        mind = self.life.p.mind
        options = CallOptions("steady", 0.0, grammar=PICKS_GRAMMAR)
        self.asked += 1
        try:
            reply = await asyncio.wait_for(mind.chat(self.messages(lines), purpose=PICKS, max_tokens=PICK_TOKENS, options=options), PICKS_WAIT_S)
        except (MindUnavailable, asyncio.TimeoutError):
            return None
        stream = self.life.memory.recall.stream
        kept = 0
        for number in picked(reply.text, len(lines)):
            line = lines[number - 1]
            people = len(line["audience"])
            weight = min(10, importance(line["kind"], people=1 if line["kind"] == "said" else people) + PICK_LIFT)
            if line["kind"] == "said":
                record = stream.add(line["text"][:TEXT_MAX], "said", by="person", who=line.get("who"), tier=line.get("tier"), about=(line["who"],) if line.get("who") else (), mark="private", audience=line["audience"], weight=weight, at=line["at"])
            else:
                mark = "private" if line["private"] or line.get("talk") else ""
                record = stream.add(line["text"][:TEXT_MAX], "happened", mark=mark, audience=line["audience"], weight=weight, at=line["at"])
            kept += record is not None
        self.kept += kept
        self.life.p.blackbox.record("fold_picks", lines=len(lines), kept=kept)
        return kept


class Folding:
    def __init__(self, life):
        self.life = life
        self.busy = False
        self.task: asyncio.Task | None = None
        self.warming: asyncio.Task | None = None
        self.tasks: set = set()
        self.replied_at = -math.inf
        self.folds = 0
        self.picks = Picks(life)

    @property
    def clock(self):
        return self.life.p.clock

    def picks_on(self) -> bool:
        return bool(getattr(self.life.p.history.profile, "fold_picks", False))

    def _spawn(self, coro) -> asyncio.Task | None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            coro.close()
            return None
        task = loop.create_task(self._quietly(coro))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def _quietly(self, coro):
        try:
            return await coro
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("folding work failed")
            self.life.p.blackbox.record("error", where="folding")
            return None

    def talker(self) -> str | None:
        now = self.clock.now()
        for turn in reversed(self.life.p.history.turns):
            if turn.get("by"):
                t = turn.get("t")
                return turn["by"] if isinstance(t, (int, float)) and now - t <= TALK_S else None
        return None

    def quiet_for(self) -> float:
        life = self.life
        if life._in_turn:
            return 0.0
        quiet = getattr(life.p.conversation, "quiet_for", None)
        if quiet is not None:
            return quiet()
        speaker = getattr(getattr(life, "memory", None), "speaker", None)
        last = max(speaker[3] if speaker else -math.inf, self.replied_at)
        return self.clock.now() - last

    def _cool(self) -> bool:
        life = self.life
        try:
            return life._mind_ready and life._rung() == "cool" and not life.battery.low and not life._hot()
        except Exception:
            return False

    def tick(self) -> None:
        life = self.life
        if self.busy or (self.task is not None and not self.task.done()) or life._in_turn:
            return
        turns = life.p.turns
        due = getattr(turns, "fold_due", None)
        history = life.p.history
        if due is None or not history.turns or self.quiet_for() < QUIET_S:
            return
        seen = getattr(turns, "fixed_seen", 0)
        if seen and not history.soft_due(seen):
            return
        now = self.clock.now()
        local = self.clock.local(now)
        if due(life.stage(local), life.p.books.values.describe(), life.company.prompt_text(now, self.clock.local)):
            self.task = self._spawn(self.fold("quiet"))

    async def fold(self, where: str, warm: bool = True) -> int:
        if self.busy:
            return 0
        self.busy = True
        try:
            history = self.life.p.history
            if not history.turns:
                return 0
            kept = None
            if where in QUIET_WHERE and self.picks_on() and self._cool():
                planned, _ = history.plan()
                kept = await self.picks.choose(planned)
                if where == "quiet" and (kept is None or self.quiet_for() < QUIET_S):
                    return 0
            result = await history.compact(None, iso(self.clock.now()))
            self.folds += 1
            note_event(self.life.p.store, self.clock, FOLD, where=where, turns=result.folded, picks=kept)
            self.life.p.blackbox.record("fold", where=where, turns=result.folded, picks=kept)
            if result.folded and warm:
                self.rewarm()
            return result.folded
        finally:
            self.busy = False

    def rewarm(self) -> None:
        if self.warming is not None and not self.warming.done():
            return
        self.warming = self._spawn(self._rewarm())

    async def _rewarm(self) -> bool:
        life = self.life
        warm = getattr(life, "warm_reply", None)
        if warm is None:
            return False
        memory = life.memory
        board = memory.board_text(memory.audience())
        warmed = await warm(board, [{"to": ROOM, "text": board}] if board else [], purpose=REWARM)
        done = getattr(life.p.conversation, "warmed", None)
        if warmed and done is not None:
            done()
        return warmed

    def heard(self) -> None:
        task = self.warming
        if task is None or task.done():
            return
        task.cancel()
        try:
            self.life.p.mind.give_way()
        except Exception:
            log.exception("the mind would not give way to talk")

    def moved(self, turns: list[dict]) -> int:
        kept = self.life.memory.recall.from_turns(turns)
        for turn in turns:
            if turn.get("checked"):
                continue
            try:
                self._promises_at_fold(turn)
            except Exception:
                log.exception("could not look for promises in a folded turn")
        return kept

    def _promises_at_fold(self, turn: dict) -> None:
        audience = frozenset(turn.get("audience") or ())
        by = turn.get("by")
        if by:
            label, _, said = talk_of(turn)
            for sentence in promises_in(said):
                if not self._known(by, sentence):
                    self._spawn(self.promise(by, label or "you", sentence, audience))
            return
        for message in turn.get("messages") or []:
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                if function.get("name") != "say":
                    continue
                args = arguments_of(function.get("arguments"))
                who = self._person(args.get("to"), audience)
                if who is None:
                    continue
                person = self.life.company.book.get(who)
                for sentence in promises_in(args.get("text") or ""):
                    if not self._known(who, sentence):
                        self._spawn(self.promise(who, person.label if person is not None else "you", sentence, audience))

    def _person(self, name, audience: frozenset) -> str | None:
        if name:
            person = self.life.company.book.find(str(name))
            return person.id if person is not None else None
        people = [a for a in audience if a != "?"]
        return people[0] if len(people) == 1 else None

    def _known(self, who: str, sentence: str) -> bool:
        return self.life.taskcard.promise_for(who, sentence) is not None or self._has_item(who, sentence)

    def _has_item(self, who: str, text: str) -> bool:
        later = getattr(self.life, "later", None)
        if later is None:
            return False
        now = self.clock.now()
        wanted = {w for w in WORD.findall(text.lower()) if len(w) > 3}
        for item in later.agenda.waiting():
            if item.by != who:
                continue
            if now - float(item.made or 0.0) <= ITEM_MADE_S:
                return True
            have = {w for w in WORD.findall((item.words or "").lower()) if len(w) > 3}
            if wanted and len(wanted & have) * 2 >= len(wanted):
                return True
        return False

    def replied(self, turn: dict) -> None:
        self.replied_at = self.clock.now()
        by = turn.get("by")
        if not by:
            return
        label, words, said = talk_of(turn)
        label = label or "someone"
        audience = frozenset(turn.get("audience") or ())
        card = self.life.taskcard
        if words and CORRECTING.search(words):
            card.corrected(by, label, words, audience)
        refusal = next((part for part in SENTENCES.split(said) if REFUSING.search(part)), "")
        if refusal:
            card.refused(by, label, refusal, audience)
        for sentence in promises_in(said):
            if not self._known(by, sentence):
                self._spawn(self.promise(by, label, sentence, audience))

    async def promise(self, who: str, label: str, sentence: str, audience: frozenset) -> str:
        life = self.life
        found = PROMISED.search(sentence)
        if found is None:
            return ""
        card = life.taskcard
        later = getattr(life, "later", None)
        clause = sentence[found.start("act"):]
        if later is None or not FOR_LATER.match(clause):
            card.promised(who, label, sentence, audience)
            return "open"
        if self._has_item(who, clause):
            return "matched"
        commands = life.commands
        asker = commands.asker_for(who, True)
        reading = await commands.read_words(turned(clause), asker, UNDERSTAND_QUIETLY)
        request = reading.request
        if reading.ask or reading.too_much or not request.action or (request.when is None and request.on is None) or not decide_later(request, asker).yes:
            card.promised(who, label, sentence, audience)
            return "open"
        later.hush = True
        try:
            verdict = await later.route(request, asker, PROMISE_HOW)
        finally:
            later.hush = False
        if verdict is not None and verdict.answer == "yes":
            life.p.blackbox.record("promise_kept_for_later", person=who)
            commands.note(f"you promised {label} something for later in talk, so you put it on your list", False)
            return "item"
        if verdict is None or verdict.answer == "ask":
            card.promised(who, label, sentence, audience)
            return "open"
        life.p.blackbox.record("promise_cant_keep", person=who, reason=verdict.reason)
        line = CANT_KEEP.format(label=label)
        if verdict.say:
            line += " " + verdict.say
        await commands.speak(line, False)
        return "cant"

    async def close(self) -> None:
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)
