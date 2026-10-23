import asyncio
import logging
import re
from typing import Callable

import json

from ...conversation.words import CORRECTING, REFUSING, SENTENCES
from ...mind.prompt import redact
from ...tools.broad import acted
from ..checker import order_to_pebble
from .archive import asks_old
from .board import BUDGET_CHARS as BOARD_CHARS, Board, Note, fit
from .embed import StandIn
from .stream import ANSWERED, HOT, TEXT_MAX, WARM, Record, Stream, importance, shown

log = logging.getLogger(__name__)

REMEMBERING = re.compile(
    r"\b(?:do|did|can|could) you (?:still )?(?:remember|recall)\b|\bremember (?:when|the time|that time|how|what|who|where|last)\b"
    r"|\bwhen did (?:we|i|you)\b|\b(?:the )?last time (?:we|i|you)\b|\bwhat do you remember\b",
    re.IGNORECASE,
)
TALK =re.compile(r'^(?P<who>.+?) is talking to you: "(?P<said>.*)"$')
SHARE = re.compile(
    r"\b(?:you can|you may|feel free to|it's okay to|it is okay to|it's fine to) (?:remember|keep) (?:that|this|it)\b(?! (?:a |to |between |private|secret|quiet|safe))"
    r"|\b(?:that|this|it)(?:'s| is) not a secret\b|\b(?:that|this|it) isn't a secret\b",
    re.IGNORECASE,
)
NOT_SHARED = re.compile(r"\b(?:don't|do not|never|can't|cannot|mustn't|shouldn't) (?:remember|keep)\b|\bkeep (?:that|this|it) (?:a )?secret\b|\bbetween us\b|\bdon't tell\b", re.IGNORECASE)
SHARE_BACK_S = 600.0
SHARE_AFTER_S = 120.0
KEEP = ("Events:", "Heard:", "Note:", "You can see:")
EMBED_BATCH = 32
SAVE_EVERY_S = 300.0
DIARY_KINDS = {"dream": ("dream", "dream"), "reflection": ("feeling", "self"), "value_nudge": ("feeling", "self"), "trait": ("feeling", "self")}
WORDS_KEPT = 300
WORDS_PIECE = 112
DEEP_CHARS = 125
ANSWER_KEPT = 80
THOUGHT_KEPT = 100
CORRECTION_KEPT = 160
PACK_MOST = 3
PUSHED = (HOT,)
LOOKED_UP = (HOT, WARM)
OLD_MOST = 2
NOTHING_NEW = "nothing new"
STAMP = re.compile(r"^\d{1,2}:\d{2}:\d{2}\s+")
EVENT_STAMP = re.compile(r";\s+(?=\d{1,2}:\d{2}:\d{2}\s)")
REFUSED_EVENT = re.compile(r"\byou said no \(")
CLAUSE = re.compile(r"(?<=[,;:.!?])\s+")


def remembering(text: str) -> bool:
    return bool(REMEMBERING.search(text or ""))


def may_share(text: str) -> bool:
    return bool(SHARE.search(text or "")) and not NOT_SHARED.search(text or "")


def _short(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def arguments_of(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def bare(text: str, limit: int = DEEP_CHARS) -> str:
    if len(text) <= limit:
        return text
    return _short(ANSWERED.sub("", text), limit)


def _unstamped(text: str) -> str:
    return STAMP.sub("", text or "", count=1)


def _units(text: str, size: int) -> list[str]:
    out = []
    for clause in CLAUSE.split(text):
        if len(clause) <= size:
            out.append(clause)
            continue
        current = ""
        for word in clause.split(" "):
            joined = f"{current} {word}".strip()
            if current and len(joined) > size:
                out.append(current)
                current = word
            else:
                current = joined
        if current:
            out.append(current)
    return out


def pieces_of(text: str, most: int, size: int) -> list[str]:
    text = _short(text, most)
    if not text:
        return []
    if len(text) <= size:
        return [text]
    out, current = [], []
    for unit in _units(text, size):
        if current and len(" ".join(current + [unit])) > size:
            out.append(" ".join(current))
            carried = [unit]
            for earlier in reversed(current[1:]):
                if len(" ".join([earlier] + carried)) > size:
                    break
                carried.insert(0, earlier)
            current = carried
        else:
            current.append(unit)
    if current:
        out.append(" ".join(current))
    return out


def _packed(items: list[str]) -> list[str]:
    out, current = [], ""
    for item in items:
        item = _short(item, TEXT_MAX)
        joined = f"{current}; {item}" if current else item
        if current and len(joined) > TEXT_MAX:
            out.append(current)
            current = item
        else:
            current = joined
    if current:
        out.append(current)
    return out[:PACK_MOST]


class Recall:
    def __init__(self, store, clock, embedder=None, weights: Callable[[], dict] | None = None, name: str = "Pebble"):
        self.clock = clock
        self.stream = Stream(store, clock)
        self.embedder = embedder or StandIn()
        self.weights = weights or (lambda: {})
        self.board = Board()
        self.name = name
        self.working = False
        self.topic_query: list[float] | None = None
        self._saved_at = clock.monotonic()

    def related(self) -> float:
        return float(getattr(self.embedder, "related", 0.55))

    def keep(self, text: str, kind: str = "happened", **details) -> Record | None:
        return self.stream.add(text, kind, **details)

    def quote(self, label: str, said: str) -> str:
        return f'{label or "Someone"} said: "{_short(said, 150)}"'

    def from_turns(self, turns: list[dict]) -> int:
        kept = 0
        for turn in turns:
            try:
                records = self._from_turn(turn)
            except (KeyError, TypeError, ValueError):
                log.exception("could not move a turn into the memory stream")
                records = []
            kept += bool(records)
        return kept

    def _from_turn(self, turn: dict) -> list[Record]:
        audience = tuple(str(a) for a in turn.get("audience") or ())
        at = turn.get("t")
        heard_from = turn.get("by")
        lines, thought, calls, asked, label = [], "", [], "", ""
        results: dict = {}
        private = False
        for message in turn.get("messages") or []:
            if message.get("private"):
                private = True
            clean = redact(message)
            content = clean.get("content") or ""
            role = message.get("role")
            if role == "user":
                for line in content.splitlines():
                    found = TALK.match(line.strip())
                    if found:
                        label, asked = found.group("who"), found.group("said")
                    elif line.startswith(KEEP):
                        lines.append(line.strip())
            elif role == "assistant":
                if content.strip() and not thought:
                    thought = content.strip()
                for call in message.get("tool_calls") or []:
                    function = call.get("function") or {}
                    calls.append((str(call.get("id") or ""), str(function.get("name") or "?"), arguments_of(function.get("arguments"))))
            elif role == "tool":
                results[str(message.get("tool_call_id") or "")] = arguments_of(content)
        used = [acted(name, args, results.get(call_id)) for call_id, name, args in calls]
        if asked or heard_from:
            return self._talk(turn, audience, at, heard_from, label or "Someone", asked, thought, used, private)
        events, rest = [], []
        for line in lines:
            if line.startswith("Events:"):
                body = line[len("Events:"):].strip()
                if body and body != NOTHING_NEW:
                    events.extend(part.strip() for part in EVENT_STAMP.split(body) if part.strip())
            else:
                rest.append(line)
        items = ([f"Events: {events[0]}"] + events[1:] if events else []) + rest
        if thought:
            items.append(f"you thought: {_short(thought, THOUGHT_KEPT)}")
        items.extend(dict.fromkeys(used))
        if not items:
            return []
        heard = any(line.startswith("Heard:") for line in lines)
        mark = "private" if (private or heard) else ""
        weight = importance("happened", people=len(audience))
        out = [self.stream.add(text, "happened", mark=mark, audience=audience, weight=weight, at=at) for text in _packed(items)]
        for event in events:
            if REFUSED_EVENT.search(event):
                out.append(self.stream.add(_short(_unstamped(event), TEXT_MAX), "decided", mark=mark, audience=audience, weight=importance("decided", people=len(audience)), at=at))
        return [record for record in out if record is not None]

    def _talk(self, turn: dict, audience: tuple, at, heard_from, label: str, asked: str, said: str, used: list, private: bool) -> list[Record]:
        shared = bool(turn.get("shared")) and bool(heard_from) and not private
        about = (heard_from,) if heard_from else ()
        talk = {"by": "person", "who": heard_from, "tier": turn.get("tier"), "about": about, "mark": "private", "audience": audience, "at": at, "shared": shared}
        head = f'{label} said: "'
        texts = [f'{head}{piece}"' for piece in pieces_of(asked, WORDS_KEPT, WORDS_PIECE)] or [f'{head}"']
        answer = _short(said, ANSWER_KEPT)
        if answer:
            tail = f'; you answered: "{answer}"'
            if len(texts[-1]) + len(tail) <= TEXT_MAX:
                texts[-1] += tail
            else:
                texts.append(f'You answered {label}: "{answer}"')
        out = [self.stream.add(text, "said", weight=importance("said", people=1), **talk) for text in texts]
        if asked and CORRECTING.search(asked):
            out.append(self.stream.add(f'{label} corrected you: "{_short(asked, CORRECTION_KEPT)}"', "decided", weight=importance("decided", people=1), **talk))
        refusal = next((part for part in SENTENCES.split(said or "") if REFUSING.search(part)), "")
        if refusal:
            mine = {**talk, "by": "self", "who": None, "tier": None, "shared": False}
            out.append(self.stream.add(f'You told {label} no: "{_short(refusal, CORRECTION_KEPT)}"', "decided", weight=importance("decided", people=1), **mine))
        if used:
            out.append(self.stream.add(_short("; ".join(dict.fromkeys(used)), TEXT_MAX), "happened", mark="private", audience=audience, weight=importance("happened", people=len(audience)), at=at))
        return [record for record in out if record is not None]

    def share(self, person_id: str, at: float, turns: list[dict]) -> int:
        since, until = at - SHARE_BACK_S, at + SHARE_AFTER_S
        marked = 0
        for turn in turns:
            t = turn.get("t")
            if turn.get("by") == person_id and isinstance(t, (int, float)) and since <= t <= until and not turn.get("shared"):
                turn["shared"] = True
                marked += 1
        return marked + self.stream.share(person_id, since, until)

    def from_diary(self, entry: dict, audience: tuple, named: tuple) -> Record | None:
        kind, by = DIARY_KINDS.get(str(entry.get("kind") or ""), ("happened", "self"))
        first = entry.get("kind") == "milestone"
        major = entry.get("kind") == "safety"
        mark = "private" if named else ""
        hearers = tuple(dict.fromkeys(tuple(audience) + tuple(named))) if named else tuple(audience)
        return self.stream.add(str(entry.get("text") or ""), kind, by=by, about=named, mark=mark, audience=hearers, weight=importance(kind, major=major, people=len(named), first=first))

    def from_fact(self, text: str, audience: tuple, about: tuple, speaker: tuple | None = None) -> Record | None:
        if order_to_pebble(text, self.name):
            who, label, tier = speaker or (None, "Someone", None)
            return self.stream.add(self.quote(label, text), "said", by="person", who=who, tier=tier, about=(who,) if who else (), mark="private", audience=tuple(audience), weight=importance("said", people=1))
        mark = "private" if about else ""
        hearers = tuple(dict.fromkeys(tuple(audience) + tuple(about))) if about else tuple(audience)
        return self.stream.add(text, "fact", about=about, mark=mark, audience=hearers, weight=importance("fact", people=len(about)))

    async def vector(self, text: str, query: bool = True) -> list[float] | None:
        text = " ".join(str(text or "").split())
        if not text:
            return None
        try:
            rows = await asyncio.to_thread(self.embedder.embed, [text], query)
        except Exception as error:
            log.warning("could not turn a question into numbers: %s", error)
            return None
        return rows[0] if rows else None

    async def think_back(self, text: str, audience: frozenset, here=(), now: float | None = None) -> list[str]:
        now = self.clock.now() if now is None else now
        query = await self.vector(text)
        if query is None:
            return []
        ranked = self.stream.recall(query, audience, now, most=3, weights=self.weights(), here=here, related=self.related(), shelves=LOOKED_UP)
        if asks_old(text):
            older = await asyncio.to_thread(self.stream.old, query, audience, now, OLD_MOST, self.weights(), here, self.related())
            ranked = older + [pair for pair in ranked if pair[0].id not in {r.id for r, _ in older}]
        notes = fit([Note(bare(shown(r)), "memory", r) for r, _ in ranked], DEEP_CHARS)
        self.stream.touch([n.record for n in notes if n.record is not None], now)
        return [n.text for n in notes]

    async def search(self, text: str, audience: frozenset, here=(), now: float | None = None, most: int = 5) -> list[str]:
        now = self.clock.now() if now is None else now
        query = await self.vector(text)
        ranked = self.stream.recall(query, audience, now, most=most, weights=self.weights(), here=here, related=self.related() if query else None, shelves=LOOKED_UP)
        if asks_old(text):
            older = await asyncio.to_thread(self.stream.old, query, audience, now, most, self.weights(), here, self.related() if query else None)
            ranked = (older + [pair for pair in ranked if pair[0].id not in {r.id for r, _ in older}])[:most]
        self.stream.touch([r for r, _ in ranked], now)
        return [_short(shown(r), 160) for r, _ in ranked]

    async def for_turn(self, text: str, audience: frozenset, here=(), now: float | None = None) -> list[str]:
        now = self.clock.now() if now is None else now
        query = await self.vector(text) if text.strip() else None
        ranked = self.stream.recall(query, audience, now, most=3, weights=self.weights(), here=here, related=self.related() if query else None, shelves=PUSHED)
        notes = fit([Note(bare(shown(r), BOARD_CHARS), "memory", r) for r, _ in ranked])
        return [n.text for n in notes]

    async def refresh(self, audience: frozenset, here=(), topic: str = "", extras: list[Note] | None = None, kinds: dict | None = None, now: float | None = None) -> bool:
        now = self.clock.now() if now is None else now
        kinds = kinds or {}
        query = await self.vector(topic) if topic.strip() else None
        self.topic_query = query
        ranked = self.stream.recall(query, audience, now, most=3, weights=self.weights(), here=here, shelves=PUSHED)
        scored = [(float(kinds.get("memories", 1.0)) * (1.0 - 0.2 * n), Note(bare(shown(r), BOARD_CHARS), "memory", r)) for n, (r, _) in enumerate(ranked)]
        for note in extras or []:
            scored.append((float(kinds.get(note.kind + "s", 1.0)) * 0.9, note))
        ordered = [note for _, note in sorted(scored, key=lambda pair: -pair[0])]
        return self.board.offer(ordered)

    async def work(self, idle: Callable[[], bool], save: bool = False) -> int:
        if self.working:
            return 0
        self.working = True
        embedded = 0
        try:
            batch = self.stream.pending(EMBED_BATCH)
            if batch and idle():
                try:
                    vectors = await asyncio.to_thread(self.embedder.embed, [r.text for r in batch], False)
                except Exception as error:
                    log.warning("could not turn memories into numbers: %s", error)
                    vectors = []
                if vectors:
                    self.stream.attach(self.embedder.name, list(zip([r.id for r in batch], vectors)))
                    embedded = len(vectors)
            if idle():
                due = save or self.clock.monotonic() - self._saved_at >= SAVE_EVERY_S
                if due:
                    self._saved_at = self.clock.monotonic()
                    self.stream.save()
                else:
                    self.stream.flush()
        finally:
            self.working = False
        return embedded

    def busy(self) -> bool:
        stream = self.stream
        return bool(stream.unsaved) or bool(stream.waiting) or stream.dirty or stream.vectors_dirty
