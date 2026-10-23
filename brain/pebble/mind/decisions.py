import asyncio
import logging
import re
from typing import Awaitable, Callable

from ..respect import cruel
from ..tact import tactless
from .base import CallOptions, MindUnavailable, options_kwargs
from .budget import EXAMPLES, GUIDE, JOB, WORDS, Prompt
from .wordsmith import NUMBER, tidy

log = logging.getLogger(__name__)

WAIT_S = 0.6
MOST_WORDS = 15
MAX_TOKENS = 40
STEADY = CallOptions("steady", 0.3, 0.9, 0.1)
VOICE = (
    "You are {name}, a small home robot. Say the plain line again in your own voice, as yourself (I, me), warm and simple. "
    "Reply with one short sentence of at most 15 words, plain words only, no quotes. "
    "Keep its meaning exactly: the same yes or no, every name, place, time and number, and nothing new."
)
ASKS = {
    "no": 'You are saying no.\nWhy: {reason}.\nThe plain line: "{line}"',
    "yes": 'You are saying yes.\nThe plain line: "{line}"',
    "ask": 'You need to ask first.\nThe plain question: "{line}"\nKeep every choice in it and end with a question mark.',
}
SHOWN = (
    ("no", "I'm too tired just now. Maybe later.", "you are resting because you are tired", "I'm a bit worn out right now. Maybe later?"),
    ("yes", "Okay, I'll keep back a bit.", "", "Sure, I'll give you a little more room."),
    ("ask", "Do you want me to come to you?", "", "Should I come over to you?"),
)
NO_WORDS = re.compile(r"n't\b|\b(?:no|not|cannot|sorry|rather|only|later|unable|afraid|instead|too|nope)\b", re.IGNORECASE)
YES_WORDS = re.compile(r"\b(?:okay|ok|sure|yes|yep|yay|coming|on my way|right away|here i go|let's go|will do|no problem|of course|happy to|i'm on it|on it)\b", re.IGNORECASE)
STRONG_NO = re.compile(r"n't\b|\b(?:no|not|cannot|sorry|unable|nope)\b", re.IGNORECASE)
TIME_WORDS = re.compile(r"\b(?:tomorrow|tonight|today|soon|in a minute|in a bit|in an hour|next|morning|evening|afternoon|o'clock|minutes?|hours?|seconds?|week|weekend|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE)
WORD = re.compile(r"[A-Za-z']+")
PROMISE = re.compile(r"\b(?:i'll|i will|i can|let me|i'm going to|i am going to|i'm gonna)\b", re.IGNORECASE)
MARKS = re.compile(r"[{}\[\]<>\"=*_#|\\]")


def _words(text: str) -> list[str]:
    return WORD.findall(text or "")


def _kept(line: str, said: str) -> bool:
    wanted = {w.lower() for w in _words(line) if len(w) > 3}
    have = {w.lower() for w in _words(said)}
    return bool(wanted) and len(wanted & have) * 2 >= len(wanted)


def honest(answer: str, said: str, line: str, facts: str, names=(), places=(), own: str = "") -> str:
    words = _words(said)
    if not words:
        return "empty"
    if MARKS.search(said):
        return "not plain words"
    if len(words) > MOST_WORDS:
        return "too long"
    if tactless(said):
        return "it would remark on how someone looks"
    if cruel(said, tuple(names)):
        return "it would be unkind to something alive"
    known = f"{line} {facts}".lower()
    for number in NUMBER.findall(said):
        if number not in known:
            return f"it added the number {number}"
    for found in TIME_WORDS.findall(said):
        if found.lower() not in known:
            return f"it added a time ({found})"
    lowered = f" {' '.join(w.lower() for w in words)} "
    for name in list(names) + list(places):
        name = str(name).lower().strip()
        if name and f" {name} " in lowered and name not in known:
            return f"it added {name}"
    if own and re.search(rf"\b{re.escape(own)}\b", said, re.IGNORECASE) and not re.search(rf"\b{re.escape(own)}\b", line, re.IGNORECASE):
        return "it talked about itself by name"
    if answer == "no":
        if not NO_WORDS.search(said) and (NO_WORDS.search(line) or not _kept(line, said)):
            return "it did not say no"
        if YES_WORDS.search(said):
            return "it sounded like a yes"
        promised = PROMISE.findall(said)
        if promised and not PROMISE.search(line):
            return f"it promised something ({promised[0]})"
    if answer == "yes" and STRONG_NO.search(said) and not STRONG_NO.search(line):
        return "it sounded like a no"
    if answer == "ask":
        if not said.rstrip().endswith("?"):
            return "it did not ask"
        for name in list(names) + list(places):
            name = str(name).lower().strip()
            if name and f" {name} " in f" {line.lower()} " and name not in lowered:
                return f"it dropped {name}"
    return ""


class OwnWords:
    def __init__(
        self,
        mind_of: Callable[[], object | None],
        name: str = "Pebble",
        persona: Callable[[], str] = lambda: "",
        wait_s: float = WAIT_S,
        sleep: Callable[[float], Awaitable] | None = None,
        record: Callable[..., None] | None = None,
    ):
        self.mind_of = mind_of
        self.name = name
        self.persona = persona
        self.wait_s = wait_s
        self.sleep = sleep
        self.record = record or (lambda kind, **data: None)
        self.leaks: Callable[[str], bool] = lambda text: False
        self.names: Callable[[], tuple] = lambda: ()
        self.places: Callable[[], tuple] = lambda: ()

    def messages(self, answer: str, line: str, reason: str, asked: str) -> Prompt:
        persona = ""
        try:
            persona = (self.persona() or "").strip()
        except Exception:
            persona = ""
        system = VOICE.format(name=self.name) + (f"\n\n{persona}" if persona else "")
        out = [{"role": "system", "content": system}]
        for kind, plain, why, worded in SHOWN:
            out.append({"role": "user", "content": ASKS[kind].format(reason=why, line=plain)})
            out.append({"role": "assistant", "content": worded})
        user = ASKS[answer].format(reason=reason or "it isn't allowed", line=line)
        out.append({"role": "user", "content": user})
        return Prompt(out, JOB, [(GUIDE, 0, system), (WORDS, len(out) - 1, user)], [(EXAMPLES, 1, len(out) - 1)])

    async def word(self, answer: str, line: str, reason: str = "", asked: str = "") -> str:
        if not line or answer not in ASKS:
            return line
        mind = self.mind_of()
        if mind is None:
            return line
        task = asyncio.ensure_future(mind.chat(self.messages(answer, line, reason, asked), purpose="decision", max_tokens=MAX_TOKENS, **options_kwargs(STEADY)))
        if self.sleep is None:
            done, _ = await asyncio.wait({task}, timeout=self.wait_s)
        else:
            timer = asyncio.ensure_future(self.sleep(self.wait_s))
            done, _ = await asyncio.wait({task, timer}, return_when=asyncio.FIRST_COMPLETED)
            timer.cancel()
        if task not in done:
            task.cancel()
            task.add_done_callback(_quiet)
            self.record("own_words", answer=answer, used="fixed", why="slow")
            return line
        try:
            said = tidy(task.result().text or "")
        except (MindUnavailable, asyncio.CancelledError, Exception) as error:
            self.record("own_words", answer=answer, used="fixed", why=type(error).__name__)
            return line
        try:
            names, places = tuple(self.names()), tuple(self.places())
        except Exception:
            names, places = (), ()
        problem = honest(answer, said, line, f"{reason} {asked}", names, places, self.name)
        if not problem and self.leaks(said):
            problem = "it would repeat something overheard"
        if problem:
            self.record("own_words", answer=answer, used="fixed", why=problem)
            return line
        self.record("own_words", answer=answer, used="own")
        return said


def _quiet(task: asyncio.Task) -> None:
    if not task.cancelled():
        try:
            task.exception()
        except Exception:
            pass
