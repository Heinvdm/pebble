import asyncio
import logging
import random
from datetime import datetime
from typing import Awaitable, Callable

from ..chaos.ideas import Card, IdeaDecks
from ..seams.later import DreamResult
from ..things.words import listing, spoken, with_article
from ..respect import harsh, is_alive
from .reactions import about_looks

log = logging.getLogger(__name__)

TODAY_MAX = 12
DREAM_DRAW_CHANCE = 0.35
ASK_TIMEOUT_S = 40.0
TEMPLATES = (
    "{a} and {b} went rolling down a long hallway together, and I followed",
    "I was small enough to sit inside {a}, and it was cosy",
    "{a} was teaching me a song, and {b} kept the beat",
    "I chased {a} all the way to the moon and back",
    "the whole house was full of {plural_a}, and I had to find my charger among them",
    "{a} could talk, and it only wanted to talk about {b}",
)
SKIP = frozenset({"person", "chair", "table", "dining table", "wall", "floor"})


def plural(word: str) -> str:
    if word.endswith(("s", "x", "ch", "sh")):
        return word + "es"
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    return word + "s"


class Today:
    def __init__(self, local: Callable[[float], datetime]):
        self.local = local
        self.day: str | None = None
        self.seen: dict[str, int] = {}
        self.new: list[str] = []
        self.taught: list[str] = []
        self.doings: list[str] = []
        self.yesterday: dict | None = None

    def _roll(self, now: float) -> None:
        day = self.local(now).date().isoformat()
        if self.day != day:
            if self.day is not None:
                self.yesterday = {"day": self.day, "seen": dict(self.seen), "new": list(self.new), "taught": list(self.taught), "doings": list(self.doings)}
            self.day, self.seen, self.new, self.taught, self.doings = day, {}, [], [], []

    def saw(self, label: str, now: float, new: bool = False) -> None:
        self._roll(now)
        if label in SKIP:
            return
        self.seen[label] = self.seen.get(label, 0) + 1
        if new and label not in self.new:
            self.new.append(label)

    def learnt(self, title: str, now: float) -> None:
        self._roll(now)
        if title not in self.taught:
            self.taught.append(title)

    def did(self, text: str, now: float) -> None:
        self._roll(now)
        if text not in self.doings:
            self.doings.append(text)
            del self.doings[:-TODAY_MAX]

    def highlights(self, now: float | None = None) -> list[str]:
        if now is not None:
            self._roll(now)
        common = sorted(self.seen, key=lambda k: -self.seen[k])
        out = list(dict.fromkeys(self.taught + self.new + common))
        return out[:TODAY_MAX]

    def cards(self, kind: str, now: float) -> list[Card]:
        if kind not in ("drawing", "talk"):
            return []
        picks = self.highlights(now)[:3]
        return [Card("theme", f"today-{index}", f"something you saw today: {with_article(spoken(label)) if label not in self.taught else label}") for index, label in enumerate(picks)]

    def diary_line(self, now: float) -> str:
        picks = self.highlights(now)[:5]
        if not picks:
            return ""
        return f"Today I saw {listing([label if label in self.taught else with_article(spoken(label)) for label in picks])}."


class ThingDreamer:
    def __init__(self, today: Today, now: Callable[[], float], ask: Callable[[str], Awaitable[str]] | None = None, rng: random.Random | None = None):
        self.today = today
        self.now = now
        self.ask = ask
        self.rng = rng or random.Random()
        self.drawing: str | None = None

    def _named(self, label: str) -> str:
        return label if label in self.today.taught or label == "my charger" else with_article(spoken(label))

    def _template(self, picks: list[str]) -> str:
        a = picks[0]
        b = picks[1] if len(picks) > 1 else "my charger"
        template = self.rng.choice(TEMPLATES)
        if a in self.today.taught and "{plural_a}" in template:
            template = TEMPLATES[0]
        if "chased" in template and is_alive(a):
            template = TEMPLATES[0]
        return template.format(a=self._named(a), b=self._named(b), plural_a=plural(spoken(a)))

    async def _asked(self, picks: list[str]) -> str:
        if self.ask is None:
            return ""
        prompt = (
            "You are Pebble, a small desk robot, falling asleep. In one short sentence (under 25 words), first person, past tense, "
            f"describe a gentle, odd dream that mixes these things you saw today: {', '.join(spoken(p) for p in picks[:3])}. "
            "Never describe what anyone looks like. Reply with the sentence only."
        )
        try:
            text = await asyncio.wait_for(self.ask(prompt), ASK_TIMEOUT_S)
        except Exception:
            log.exception("the dream could not be asked for")
            return ""
        text = " ".join(str(text or "").split()).strip().strip('"')
        return text if 8 <= len(text) <= 220 and not about_looks(text) and not harsh(text) else ""

    async def consolidate(self, diary_today: list[dict], summary: str) -> DreamResult:
        now = self.now()
        picks = self.today.highlights()
        if not picks and self.today.yesterday:
            picks = list(dict.fromkeys(self.today.yesterday["taught"] + self.today.yesterday["new"] + sorted(self.today.yesterday["seen"], key=lambda k: -self.today.yesterday["seen"][k])))[:TODAY_MAX]
        if not picks:
            return DreamResult([], "nothing seen today to dream about")
        entries = []
        line = self.today.diary_line(now)
        if line:
            entries.append(line)
        dream = await self._asked(picks)
        source = "the mind"
        if not dream:
            dream = "I dreamt " + self._template(picks) + "."
            source = "a template"
        elif not dream.lower().startswith(("i dreamt", "i dreamed")):
            dream = "I dreamt " + dream[0].lower() + dream[1:]
        entries.append(dream)
        note = f"dreamt from {source} about {', '.join(spoken(p) for p in picks[:3])}"
        if self.rng.random() < DREAM_DRAW_CHANCE:
            self.drawing = dream.removeprefix("I dreamt ").rstrip(".")
            note += "; it will draw the dream in the morning"
        return DreamResult(entries, note)


class TodayDecks(IdeaDecks):
    def __init__(self, base: IdeaDecks, today: Callable[[], list[Card]]):
        self.base = base
        self.today = today

    @property
    def decks(self) -> dict:
        merged = dict(self.base.decks)
        try:
            extra = tuple(self.today())
        except Exception:
            extra = ()
        if extra:
            merged["theme"] = tuple(merged.get("theme", ())) + extra
        return merged
