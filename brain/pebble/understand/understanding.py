import asyncio
import logging
import re
from dataclasses import dataclass, replace
from typing import Awaitable, Callable

from ..alive.book import TOY_KINDS
from ..conversation.listening import asks_start, asks_stop
from ..respect import is_alive
from ..things.words import ANIMALS, THING_WORDS, canonical
from ..self.registry import REGISTRY
from .context import Context
from .errands import errand_words
from .cover import for_later, later_words, leftover, new_act, not_for_me, signals
from .model import ModelReader, ModelReading
from .refs import ref_words
from .request import CHAT, STARTS, Cond, Request, Trigger, too_big
from .resolve import Reading, answer, resolve
from .rules import _noun_phrase, harmed, parse
from .telling import relayed, telling
from .words import FAMILY, normalise

log = logging.getLogger(__name__)

RULES_FIRST = "rules_first"
MODEL_LEADS = "model_leads"
MODES = (RULES_FIRST, MODEL_LEADS)
ALIASES = {"model_first": MODEL_LEADS}
READ_WAIT_S = 3.0
CHASING = re.compile(r"\bchas(?:e|es|ed|ing)\b")
ARRIVAL = re.compile(r"\b(?:when|once|as soon as) ([a-z]+) (?:gets|comes|is) (?:home|back|in)\b")
IF_WORD = re.compile(r"\b(?:if|unless)\b")
IF_NOT = re.compile(r"\b(?:if (?:it|there|they|he|she) (?:is|are|does|do|has|have) not|if not|unless)\b")
OTHERWISE = re.compile(r"\b(?:otherwise|or else|else)\b")
ASKING_IF = re.compile(r"\b(?:see|check|find out|ask|know|wonder|look and see|tell me) (?:if|whether)\b")
TO_SOMEONE = re.compile(r"\b(?:push|kick|roll|nudge|pass|dribble|bump|knock|bring)\b.* to (me|us|[a-z]+)$")
VAGUE = re.compile(r"\b(?:just now|now now|later on|later|in a while|one day|some ?day|next time|sometime)\b")
MAIN = "conscious"
UNDERSTAND = "understand"
UNDERSTAND_QUIETLY = "understand_quietly"
SUB = "subconscious"
DEFAULT_MODE = REGISTRY["reading.mode"].default


@dataclass(frozen=True)
class Door:
    reading: Reading | None = None
    rules: Reading | None = None
    early: Reading | None = None
    left: tuple = ()
    model: bool = False
    why: str = ""
    only: tuple | None = None


def _mode(value) -> str:
    value = str(value or "")
    return ALIASES.get(value, value)


class Understanding:
    def __init__(
        self,
        reader: ModelReader | None = None,
        mode: str | None = None,
        wait_s: float | None = READ_WAIT_S,
        mode_of: Callable[[], str] | None = None,
        cool: Callable[[], bool] | None = None,
        sleep: Callable[[float], Awaitable] | None = None,
    ):
        mode = DEFAULT_MODE if mode is None else _mode(mode)
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.reader = reader
        self.default = mode
        self.wait_s = wait_s
        self.mode_of = mode_of
        self.cool = cool or (lambda: True)
        self.sleep = sleep
        self.skills: Callable[[str], Request | None] | None = None

    @property
    def mode(self) -> str:
        if self.mode_of is not None:
            try:
                chosen = _mode(self.mode_of())
            except Exception:
                chosen = ""
            if chosen in MODES:
                return chosen
        return self.default

    @mode.setter
    def mode(self, value: str) -> None:
        if _mode(value) not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.default = _mode(value)

    @property
    def uses_models(self) -> bool:
        return self.reader is not None and self.reader.available

    @property
    def leads(self) -> bool:
        if self.mode != MODEL_LEADS or not self.uses_models:
            return False
        try:
            return bool(self.cool())
        except Exception:
            return True

    def claims(self, text: str, captured: str | None = None, name: str = "pebble") -> bool:
        if not self.leads:
            return True
        return not later_words(text if captured is None else captured, name)

    def door(self, text: str, ctx: Context) -> Door:
        harmful = harmed(text, ctx)
        if harmful is not None:
            return Door(Reading(harmful), why="harm")
        if asks_stop(text) or asks_start(text):
            return Door(Reading(CHAT), why="listening")
        if ctx.pending is not None:
            answered = answer(text, ctx.pending, ctx)
            if answered is not None:
                return Door(answered, why="answer")
        if self.skills is not None:
            try:
                kept = self.skills(text)
            except Exception:
                log.exception("could not match a kept skill")
                kept = None
            if kept is not None and not not_for_me(text, ctx):
                return Door(Reading(kept), why="a kept skill")
        relay = relayed(text, ctx)
        if relay is not None:
            return Door(resolve(relay, ctx), why="their own request, passed on")
        told = telling(text, ctx)
        if told is not None and not not_for_me(text, ctx):
            return Door(resolve(told, ctx), why="rule or message words")
        errand = errand_words(text, ctx) or ref_words(text, ctx)
        if errand is not None and not not_for_me(text, ctx):
            return Door(resolve(errand, ctx), why="errand or reference words")
        rules = parse(text, ctx)
        request = rules.request
        if request.action and too_big(request):
            return Door(Reading(Request("other"), too_much=True), why="too much")
        leads = self.leads
        if not request.action:
            elsewhere = not_for_me(text, ctx)
            if elsewhere:
                return Door(Reading(request if rules.certain else CHAT), why=elsewhere)
        if not request.action and rules.certain:
            plain = Reading(request)
            if leads and (request.kind == "other" or signals(text, ctx.name)):
                return Door(rules=plain, model=True, why="said more than talk")
            if not leads and self.uses_models and for_later(text, ctx.name):
                return Door(rules=plain, model=True, why="for later")
            if not leads and self.uses_models and request.kind == "other" and new_act(text, ctx.name):
                return Door(rules=plain, model=True, why="something new")
            return Door(plain, why="talk")
        resolved = resolve(request, ctx)
        if not self.uses_models:
            return Door(resolved, why="rules")
        if request.action and rules.certain:
            if not leads:
                left = leftover(text, request, ctx.name, frozenset(ctx.known_names())) if for_later(text, ctx.name) else ()
                if left:
                    return Door(rules=resolved, left=left, model=True, why="for later")
                return Door(resolved, why="rules")
            left = leftover(text, request, ctx.name, frozenset(ctx.known_names()))
            if not left:
                return Door(resolved, why="every word")
            first = resolve(request.with_(then=()), ctx)
            early = first if first.request.kind in STARTS and not first.ask else None
            return Door(rules=resolved, early=early, left=left, model=True, why="words left over")
        if not leads and not (rules.cue or ctx.pending is not None or signals(text, ctx.name) or new_act(text, ctx.name)):
            return Door(rules=resolved, model=True, why="rules unsure, no request words", only=(SUB,))
        return Door(rules=resolved, model=True, why="rules unsure")

    def instant(self, text: str, ctx: Context) -> Reading | None:
        return self.door(text, ctx).reading

    async def warm(self, text: str, ctx: Context) -> bool:
        if not self.leads or not text.strip():
            return False
        return await self.reader.warm(text, ctx, MAIN)

    async def ask_model(self, text: str, ctx: Context, wait_s: float | None = None, only: tuple | None = None, purpose: str = UNDERSTAND) -> ModelReading | None:
        leads = self.leads
        prefer = MAIN if leads else None
        task = asyncio.ensure_future(self.reader.read(text, ctx, only, prefer=prefer, purpose=purpose))
        wait = wait_s if wait_s is not None else (self.wait_s if leads else None)
        if wait is None:
            return await task
        if self.sleep is None:
            done, _ = await asyncio.wait({task}, timeout=wait)
        else:
            timer = asyncio.ensure_future(self.sleep(wait))
            done, _ = await asyncio.wait({task, timer}, return_when=asyncio.FIRST_COMPLETED)
            timer.cancel()
        if task in done:
            return task.result()
        task.add_done_callback(_quiet)
        return None

    def from_model(self, modelled: ModelReading, ctx: Context, text: str = "") -> Reading:
        if modelled.too_much:
            return Reading(Request("other"), source=modelled.source, too_much=True)
        request = _to_whom(_checked_if(_arrival(_for_speaker(harmless(modelled.request, text), text, ctx), text, ctx), text, ctx), text, ctx)
        if text and request.action and request.kind != "harm" and (not_for_me(text, ctx) or _vague(request, text, ctx) or _parroted(request, text, ctx)):
            return Reading(CHAT, source=modelled.source)
        if ctx.pending is not None and not request.action and request.kind == "chat":
            return replace(resolve(CHAT, ctx), source=modelled.source)
        return resolve(request, ctx, modelled.source)

    async def finish(self, text: str, ctx: Context, door: Door, wait_s: float | None = None, purpose: str = UNDERSTAND) -> Reading:
        if not door.model:
            return door.reading
        modelled = await self.ask_model(text, ctx, wait_s, door.only, purpose)
        if modelled is None:
            fallback = door.rules or Reading(CHAT)
            return replace(fallback, left=door.left) if door.left and fallback.request.action else fallback
        return self.from_model(modelled, ctx, text)

    async def read(self, text: str, ctx: Context, wait_s: float | None = None, purpose: str = UNDERSTAND) -> Reading:
        door = self.door(text, ctx)
        return await self.finish(text, ctx, door, wait_s, purpose)


def harmless(request: Request, text: str = "") -> Request:
    if request.kind == "play" and request.thing and CHASING.search(text.lower()) and _living(request.thing):
        return Request("harm", thing=request.thing, harm="chase")
    if request.kind != "harm" or request.who or not request.thing:
        return request
    words = _words(request.thing)
    if _living(request.thing):
        return request
    if not any(w in THING_WORDS for w in words):
        return request
    toy = next((w for w in words if w in TOY_KINDS), "")
    if toy and request.harm in ("chase", "hurt"):
        return Request("play", thing=toy)
    return Request("other")


def _for_speaker(request: Request, text: str, ctx: Context) -> Request:
    said = normalise(text, ctx.name)
    names = "me" + (f"|{re.escape(ctx.speaker)}" if ctx.speaker else "")
    if not re.match(rf"^(?:(?:can|could|would|will) you |please )?(?:remind|wake) (?:{names})\b", said):
        return request
    if request.kind in ("list_later", "cancel_later", "change_later"):
        return Request("other")
    if request.kind != "say_to" or request.who in ("", "me", ctx.speaker) or request.when is None and request.on is None:
        return request
    words = request.text if request.who in request.text.lower().split() else f"{request.text} {request.who}".strip()
    return request.with_(who="me", text=words)


def _arrival(request: Request, text: str, ctx: Context) -> Request:
    if not text or request.on is not None or request.kind != "say_to":
        return request
    found = ARRIVAL.search(normalise(text, ctx.name))
    if found is None:
        return request
    who = found.group(1)
    if who not in ctx.known_names() and who not in FAMILY:
        return request
    when = request.when
    if when is not None and (when.repeats or when.date or when.in_s or when.part):
        return request
    return request.with_(when=None, on=Trigger(event="arrives", who="me" if who == ctx.speaker else who))


def _checked_if(request: Request, text: str, ctx: Context) -> Request:
    if not text or request.kind != "check" or not request.then or any(step.branch for step in request.then):
        return request
    said = ASKING_IF.sub(" ", normalise(text, ctx.name))
    if not IF_WORD.search(said):
        return request
    if OTHERWISE.search(said) or len(IF_WORD.findall(said)) > 1:
        return request.with_(then=())
    answer = "no" if IF_NOT.search(said) else "yes"
    return request.with_(then=(Request("if", if_=Cond(state="result", is_=answer), then=tuple(request.then)),))


def _to_whom(request: Request, text: str, ctx: Context) -> Request:
    if not text or request.kind != "play" or not request.thing or request.to or _living(request.thing):
        return request
    found = TO_SOMEONE.search(normalise(text, ctx.name).strip(" ,.!?"))
    if found is None:
        return request
    who = found.group(1)
    if who in ("me", "us") or who == ctx.speaker:
        return request.with_(to="me")
    if who in ctx.known_names() or who in FAMILY:
        return request.with_(to=who)
    return request


def _words(thing: str) -> list[str]:
    return [w for w in (thing, canonical(thing), _noun_phrase(thing.split())) if w]


def _living(thing: str) -> bool:
    return any(is_alive(w) or w in ANIMALS for w in _words(thing))


def _vague(request: Request, text: str, ctx: Context) -> bool:
    return request.when is None and request.on is None and bool(VAGUE.search(normalise(text, ctx.name)))


def _parroted(request: Request, text: str, ctx: Context) -> bool:
    if request.kind != "say_to" or request.when is not None or request.on is not None or not request.text:
        return False
    return _bare(request.text, ctx) == _bare(text, ctx)


def _bare(text: str, ctx: Context) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", normalise(text, ctx.name)))


def _quiet(task: asyncio.Task) -> None:
    if not task.cancelled():
        error = task.exception()
        if error is not None:
            log.debug("a late request reading failed: %s", error)
