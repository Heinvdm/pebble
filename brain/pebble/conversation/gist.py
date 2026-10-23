import asyncio
import json
import re
from collections import Counter
from dataclasses import dataclass, field

from .window import Line
from .words import content, hostile, laughing, mood_of, to_room

EVERY_S = 45.0
MIN_LINES = 3
MAX_WAIT_S = 120.0
TOPIC_WORDS = 3
MODEL_TIMEOUT_S = 8.0
OBJECT = re.compile(r"\{.*\}", re.DOTALL)
GIST_SYSTEM = (
    "You condense a few lines of talk you overheard into one short private thought for a small robot's inner monologue. "
    "Reply with one line of JSON: {\"topic\": \"a few words\", \"mood\": \"one or two words\"}. No names of people who are not in the lines."
)


@dataclass(frozen=True)
class Thought:
    at: float
    text: str
    kind: str
    about: tuple = ()
    audience: frozenset = frozenset()
    weight: float = 0.5
    private: bool = True
    tags: tuple = field(default_factory=tuple)


def names_of(lines: list[Line]) -> list[str]:
    seen = []
    for line in lines:
        if not line.pebble and line.label not in seen:
            seen.append(line.label)
    return seen


def joined(names: list[str]) -> str:
    if not names:
        return "someone"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def topic_of(lines: list[Line]) -> list[str]:
    counts = Counter()
    for line in lines:
        for word in dict.fromkeys(content(line.text)):
            counts[word] += 1
    return [word for word, count in counts.most_common(TOPIC_WORDS * 2) if count >= 1][:TOPIC_WORDS]


def mood_word(lines: list[Line], laughs: int, crying: bool) -> tuple[str, float]:
    if crying:
        return "sad", -0.8
    if any(hostile(line.text) for line in lines):
        return "tense", -0.7
    score = sum(mood_of(line.text) for line in lines) / max(1, len(lines))
    score += 0.25 * laughs + 0.15 * sum(laughing(line.text) for line in lines)
    if score >= 0.35:
        return "cheerful", score
    if score >= 0.1:
        return "easy-going", score
    if score <= -0.3:
        return "a bit down", score
    return "calm", score


class Gist:
    def __init__(self, mind=None, every_s: float = EVERY_S):
        self.mind = mind
        self.every_s = every_s
        self.last_at = None
        self.laughs = 0
        self.crying = False

    def laughed(self) -> None:
        self.laughs += 1

    def cried(self) -> None:
        self.crying = True

    def due(self, now: float, pending: list[Line]) -> bool:
        heard = [line for line in pending if not line.pebble]
        if not heard:
            return False
        first = heard[0].at
        quiet_for = now - heard[-1].at
        if len(heard) >= MIN_LINES and now - first >= self.every_s:
            return True
        if len(heard) >= MIN_LINES and quiet_for >= 15.0:
            return True
        return now - first >= MAX_WAIT_S

    def plain(self, lines: list[Line], now: float, keep: bool = False) -> list[Thought]:
        heard = [line for line in lines if not line.pebble]
        if not heard:
            return []
        who = names_of(heard)
        about = tuple(sorted({line.who for line in heard if line.who}))
        audience = frozenset().union(*[line.audience for line in heard])
        words = topic_of([line for line in heard if not line.private])
        mood, score = mood_word(heard, self.laughs, self.crying)
        talk = "talked" if len(who) > 1 else "was talking"
        text = f"{joined(who)} {talk}" + (f" about {', '.join(words)}" if words else "") + f"; it felt {mood}."
        weight = min(1.0, 0.3 + 0.08 * len(heard) + 0.2 * abs(score) + 0.1 * self.laughs)
        thoughts = [Thought(now, text, "gist", about, audience, weight, True, tuple(words))]
        for line in heard:
            if to_room(line.text):
                about_words = content(line.text)
                thoughts.append(Thought(now, f"{line.label} asked everyone a question" + (f" about {' '.join(about_words[:3])}" if about_words else "") + ".", "question", (line.who,) if line.who else (), audience, 0.4, True))
        if not keep:
            self.laughs = 0
            self.crying = False
        return thoughts

    async def condense(self, lines: list[Line], now: float) -> list[Thought]:
        thoughts = self.plain(lines, now)
        if not thoughts or self.mind is None:
            return thoughts
        heard = [line for line in lines if not line.pebble and not line.private][-10:]
        if not heard:
            return thoughts
        request = [
            {"role": "system", "content": GIST_SYSTEM},
            {"role": "user", "content": "\n".join(line.shown() for line in heard)},
        ]
        try:
            reply = await asyncio.wait_for(self.mind.chat(request, purpose="job", max_tokens=48), MODEL_TIMEOUT_S)
            found = OBJECT.search(reply.text or "")
            data = json.loads(found.group(0)) if found else {}
        except Exception:
            return thoughts
        topic = " ".join(str(data.get("topic") or "").split())[:60]
        mood = " ".join(str(data.get("mood") or "").split())[:24]
        if not topic:
            return thoughts
        first = thoughts[0]
        who = names_of(heard)
        text = f"{joined(who)} {'talked' if len(who) > 1 else 'was talking'} about {topic}" + (f"; it felt {mood}." if mood else ".")
        return [Thought(first.at, text, first.kind, first.about, first.audience, first.weight, True, first.tags + ("model",))] + thoughts[1:]
