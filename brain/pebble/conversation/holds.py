import random
import re
from typing import Callable

from ..clock import iso
from ..respect import harsh
from ..tact import tactless
from . import words as w

HOLDS = "holds.json"
STAGES = (0.6, 2.5, 6.0, 15.0)
FAST_FIRST_S = 1.0
FAST_ANSWER_S = 1.2
FAST_SAMPLES = 5
GLANCE_S = 0.3
SMALL_ASK_S = 1.0
MAX_SPOKEN = 3
MAX_WORDS = 5
ECHO_WORDS = 8
MAX_SOUND_S = 1.6
SECONDS_PER_CHAR = 0.065
REPEAT_S = 600.0
REPEAT_MAX = 3
LAUGH_AFTER_S = 4.0
HELLO_AFTER_S = 10.0
FORGET = 0.98
STOCK_FLOOR = 0.15
TRIAL_TRIES = 3
TRIAL_BAD = 2
DROP_AFTER = 8
DROP_MEAN = 0.2
WEEK_S = 7 * 86400.0
INVENT_GAP_S = 2 * 86400.0
INVENT_WEEK_MAX = 3
LOG_KEEP = 60
ECHO = "<echo>"
SMALL = "<small>"
SLOW = "My thoughts are slow right now."
REWARDS = {"laughed": 1.0, "waited": 0.6, "talked_over": 0.0, "hello": 0.0}
SITUATIONS = ("question", "request", "good", "bad", "other")
STOCK = {
    1: {
        "question": ("Hmm,", "Ooh, good question.", "Let me see.", "Ooh,", "That's a tricky one."),
        "request": ("Okay,", "Right,", "Mm, okay."),
        "good": ("Ooh!", "Oh, nice."),
        "bad": ("Oh no.", "Aw.", "Oh."),
        "other": ("Mm.", "Oh,", "Hmm."),
    },
    2: {"any": ("Let me see...", "So...", "Um,", "Hmm, let me think.")},
    3: {"any": ("Still thinking.", "Give me a sec.")},
}
CHILD = {1: ("Hmm.", "Ooh."), 2: ("Um,",), 3: ("Still thinking.",)}
SEEDS = {
    1: {"question": ("Good question.", "Let me think."), "request": ("Okay, one moment.",), "other": ("Oh, I see.",)},
    2: {"any": ("Let me think about that.", "Give me a moment.")},
    3: {"any": ("I am still thinking.", "Nearly there.")},
}
PLAIN = {
    "question": "someone asks me something",
    "request": "someone asks me to do something",
    "good": "someone tells me good news",
    "bad": "someone tells me something sad",
    "other": "someone tells me something",
}
WHEN = {1: "and I need a moment", 2: "and it's taking me a little longer", 3: "and I'm taking a while"}
ECHO_START = frozenset("what where when who whom whose which how why is are am was were do does did have has what's where's who's how's when's why's isn't aren't don't doesn't didn't".split())
AUX = frozenset("do does did can could will would shall should may might must are were have has had am is was".split())
SWAP = {
    "i": "you", "me": "you", "my": "your", "mine": "yours", "myself": "yourself",
    "i'm": "you're", "i've": "you've", "i'll": "you'll", "i'd": "you'd",
    "your": "my", "yours": "mine", "yourself": "myself",
    "you're": "I'm", "you've": "I've", "you'll": "I'll", "you'd": "I'd",
}
REQUEST = re.compile(r"^(please|can you|could you|would you|will you|tell me|show me|let's|lets|help me)\b")
ANSWERS = re.compile(r"^(yes|yeah|yep|nope|no)\b|\b(the answer|i know|it's|it is|that's right|of course|definitely|here it is|i found|got it)\b")
DOING = re.compile(r"\b(check|checking|look it up|looking it up|search|searching|let me look|i'll look|google)")
NUMBERS = re.compile(r"\b(zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred|thousand|million|half past|o'clock)\b")
MOCK = re.compile(r"\b(silly|stupid|dumb|obvious|obviously|duh|boring|ugh|seriously|whatever|weird question|easy one|you should know)\b")
MARKS = re.compile(r"[*_#<>\[\]{}()\"“”:;@/\\|~^=+&%$]|[\U0001F000-\U0010FFFF☀-➿]")
STOP_SAYING = re.compile(r"\b(?:stop|quit|no more|enough of) (?:saying|with)\s+(.+)$|\bdon'?t say\s+(.+?)(?:\s+any ?more)?$")
WHY_SAY = re.compile(r"\bwhy do you (?:always |keep |sometimes |say |keep on )?(?:say|saying)\s+(.+?)$")
THAT = frozenset({"that", "it", "this", "that thing", "those things"})


def norm(text: str) -> str:
    return " ".join(w.words(text or ""))


def situation_of(text: str, name: str = "Pebble") -> str:
    body = w.body(text, (name,))
    said = body.split()
    if REQUEST.match(body):
        return "request"
    if w.is_question(body) or "?" in (text or "") or (said and said[0] in ECHO_START):
        return "question"
    mood = w.mood_of(text)
    if mood <= -0.3:
        return "bad"
    if mood >= 0.3:
        return "good"
    if w.is_command(body):
        return "request"
    return "other"


def turned(said: list[str]) -> list[str]:
    out = []
    for index, word in enumerate(said):
        before = said[index - 1] if index else ""
        after = said[index + 1] if index + 1 < len(said) else ""
        if word in ("you", "u", "ya"):
            out.append("I" if index == 0 or before in AUX else "me")
        elif word in SWAP:
            out.append(SWAP[word])
        elif word == "am" and "i" in (before, after):
            out.append("are")
        elif word == "are" and "you" in (before, after):
            out.append("am")
        elif word == "was" and "i" in (before, after):
            out.append("were")
        elif word == "were" and "you" in (before, after):
            out.append("was")
        else:
            out.append(word)
    return out


def echo_of(text: str, name: str = "Pebble") -> str:
    said = w.body(text, (name,)).split()
    if not said or len(said) > ECHO_WORDS or said[0] not in ECHO_START:
        return ""
    line = " ".join(turned(said))
    line = re.sub(r"\bi\b", "I", line)
    return line[0].upper() + line[1:] + "?"


def fence(text: str, echo: bool = False, looking: bool = False) -> str:
    text = " ".join((text or "").split())
    if not text or not re.search(r"[A-Za-z]", text):
        return "empty"
    said = w.words(text)
    if len(said) > (ECHO_WORDS if echo else MAX_WORDS):
        return "too long"
    if not echo and len(text) * SECONDS_PER_CHAR > MAX_SOUND_S:
        return "too long"
    if MARKS.search(text):
        return "not plain words"
    if re.search(r"\d", text) or NUMBERS.search(text.lower()):
        return "a number would claim an answer"
    lower = text.lower()
    if not echo and ANSWERS.search(lower):
        return "it would claim an answer"
    if DOING.search(lower) and not looking:
        return "it would claim something Pebble isn't doing"
    if "slow" in lower:
        return "only the slow-thoughts line may say that"
    if MOCK.search(lower):
        return "unkind"
    if tactless(text):
        return "it would remark on someone's looks"
    if harsh(text):
        return "it would be unkind to something alive"
    return ""


def _stock() -> dict:
    out: dict = {}
    for stage, groups in STOCK.items():
        for situation, texts in groups.items():
            for text in texts:
                info = out.setdefault(text, {"source": "stock", "stages": [], "situations": []})
                if stage not in info["stages"]:
                    info["stages"].append(stage)
                for name in (SITUATIONS if situation == "any" else (situation,)):
                    if name not in info["situations"]:
                        info["situations"].append(name)
    for stage, texts in CHILD.items():
        for text in texts:
            info = out.setdefault(text, {"source": "stock", "stages": [], "situations": list(SITUATIONS)})
            if stage not in info["stages"]:
                info["stages"].append(stage)
    return out


class Phrasebook:
    def __init__(self, store=None, rng: random.Random | None = None, clock=None):
        self.store = store
        self.rng = rng or random.Random()
        self.clock = clock
        data = (store.read(HOLDS, {}) if store is not None else {}) or {}
        self.holds: dict = {**_stock(), **{k: v for k, v in (data.get("holds") or {}).items() if isinstance(v, dict) and v.get("source") == "own"}}
        self.arms: dict = dict(data.get("arms") or {})
        self.people: dict = dict(data.get("people") or {})
        self.strangers: dict = {}
        self.log: list = list(data.get("log") or [])
        self.made: list = list(data.get("made") or [])
        self.recent: list = []
        self.pending: list = []
        self.last: dict | None = None
        self.dirty = False
        self.diary: Callable[[str], None] = lambda text: None

    def own(self) -> list[str]:
        return [text for text, info in self.holds.items() if info.get("source") == "own" and not info.get("dropped")]

    def _person(self, person: str | None, known: bool, make: bool = True) -> dict | None:
        if not person:
            return None
        book = self.people if known else self.strangers
        if person not in book and not make:
            return None
        return book.setdefault(person, {"arms": {}, "stopped": []})

    def _stopped(self, person: str | None, known: bool) -> set:
        record = self._person(person, known, make=False)
        return set(record.get("stopped") or []) if record else set()

    def _too_soon(self, text: str, now: float) -> bool:
        key = norm(text)
        if self.recent and self.recent[-1][1] == key:
            return True
        return sum(1 for at, said in self.recent if said == key and now - at <= REPEAT_S) >= REPEAT_MAX

    def candidates(self, situation: str, stage: int, child: bool = False) -> list[str]:
        if child:
            return list(CHILD.get(stage, ()))
        group = STOCK.get(stage, {})
        base = list(group.get(situation) or group.get("any") or ())
        mine = [text for text in self.own() if stage in self.holds[text].get("stages", []) and situation in self.holds[text].get("situations", SITUATIONS)]
        return base + mine

    def _sample(self, key: str, situation: str, stage: int, person: str | None, known: bool) -> float:
        slot = f"{situation}/{stage}"
        a = b = 1.0
        for arms in (self.arms, (self._person(person, known, make=False) or {}).get("arms")):
            if arms:
                got = (arms.get(slot) or {}).get(key)
                if got:
                    a += got[0]
                    b += got[1]
        score = self.rng.betavariate(a, b)
        if key == ECHO or key == SMALL or self.holds.get(key, {}).get("source") == "stock":
            score = max(score, self.rng.random() * STOCK_FLOOR)
        return score

    def take_small(self, small: str, now: float, person: str | None = None, known: bool = False, child: bool = False) -> tuple[str, str] | None:
        if not small or child:
            return None
        stopped = self._stopped(person, known)
        if norm(small) in stopped or norm(SMALL) in stopped or self._too_soon(small, now):
            return None
        return SMALL, small

    def choose(self, situation: str, stage: int, now: float, person: str | None = None, known: bool = False, child: bool = False, echo: str = "", small: str = "") -> tuple[str, str] | None:
        stopped = self._stopped(person, known)
        options = []
        keys = self.candidates(situation, stage, child) + ([ECHO] if echo and not child else []) + ([SMALL] if small and not child else [])
        for key in keys:
            text = echo if key == ECHO else small if key == SMALL else key
            if not text or norm(text) in stopped or norm(key) in stopped or self._too_soon(text, now):
                continue
            options.append((key, text))
        if not options:
            return None
        scored = [(self._sample(key, situation, stage, person, known), index, key, text) for index, (key, text) in enumerate(options)]
        _, _, key, text = max(scored)
        return key, text

    def said(self, key: str, text: str, situation: str, stage: int, now: float, person: str | None = None, known: bool = False) -> None:
        self.recent.append((now, norm(text)))
        self.recent = [(at, said) for at, said in self.recent if now - at <= REPEAT_S]
        entry = {"key": key, "text": text, "situation": situation, "stage": stage, "person": person, "known": known, "at": now}
        self.pending.append(entry)
        self.last = entry

    def outcome(self, kind: str, now: float) -> int:
        if kind == "waited":
            done = [entry for entry in self.pending]
            self.pending = []
            for entry in done:
                self._update(entry, kind)
            return len(done)
        if kind == "laughed":
            entry = self.last
            if entry is None or now - entry["at"] > LAUGH_AFTER_S:
                return 0
            self._update(entry, kind)
            return 1
        if kind in ("talked_over", "hello"):
            window = LAUGH_AFTER_S if kind == "talked_over" else HELLO_AFTER_S
            entry = self.last
            if not self.pending or entry is None or now - entry["at"] > window:
                self.pending = []
                return 0
            earlier = [e for e in self.pending if e is not entry]
            self.pending = []
            for other in earlier:
                self._update(other, "waited")
            self._update(entry, kind)
            return 1
        return 0

    def _update(self, entry: dict, kind: str) -> None:
        reward = REWARDS[kind]
        slot = f"{entry['situation']}/{entry['stage']}"
        record = self._person(entry["person"], entry["known"])
        for arms in (self.arms, record["arms"] if record else None):
            if arms is None:
                continue
            got = arms.setdefault(slot, {}).get(entry["key"], [0.0, 0.0])
            arms[slot][entry["key"]] = [round(got[0] * FORGET + reward, 4), round(got[1] * FORGET + 1.0 - reward, 4)]
        self.log.append({"at": self._iso(), "hold": entry["key"], "situation": entry["situation"], "stage": entry["stage"], "how": kind, "person": entry["person"] if entry["known"] else None})
        del self.log[:-LOG_KEEP]
        info = self.holds.get(entry["key"])
        if info is not None and info.get("source") == "own":
            info["tries"] = int(info.get("tries", 0)) + 1
            if reward < 0.5:
                info["bad"] = int(info.get("bad", 0)) + 1
            self._review(entry["key"])
        self.dirty = True

    def mean(self, key: str) -> float:
        a = b = 0.0
        for slot in self.arms.values():
            got = slot.get(key)
            if got:
                a += got[0]
                b += got[1]
        return (a + 1.0) / (a + b + 2.0)

    def _review(self, key: str) -> None:
        info = self.holds[key]
        tries = int(info.get("tries", 0))
        if info.get("trial") and tries <= TRIAL_TRIES and int(info.get("bad", 0)) >= TRIAL_BAD:
            self.drop(key, "it didn't go down well when I tried it")
        elif info.get("trial") and tries >= TRIAL_TRIES:
            info["trial"] = False
        elif tries >= DROP_AFTER and self.mean(key) < DROP_MEAN:
            self.drop(key, "people kept talking over it")

    def drop(self, key: str, why: str) -> None:
        info = self.holds.get(key)
        if info is None or info.get("source") != "own" or info.get("dropped"):
            return
        info["dropped"] = self._iso()
        info["why_dropped"] = why
        self.dirty = True
        self.diary(f"I've stopped saying \"{key}\" while I think: {why}.")

    def stop_asked(self, text: str, person: str | None, known: bool) -> str | None:
        found = STOP_SAYING.search(" ".join(w.words(text)))
        if found is None:
            return None
        asked = norm(found.group(1) or found.group(2) or "")
        if asked in THAT and self.last is not None:
            matches = [self.last["text"] if self.last["key"] in (ECHO, SMALL) else self.last["key"]]
        else:
            matches = [key for key in self.holds if norm(key) and (norm(key) == asked or norm(key).startswith(asked + " "))]
        if not matches:
            return None
        record = self._person(person or "someone", known)
        for key in matches:
            if norm(key) not in record["stopped"]:
                record["stopped"].append(norm(key))
        self.dirty = True
        target = min(matches, key=len)
        self.diary(f"I was asked to stop saying \"{target}\", so I have.")
        return target

    def why(self, text: str) -> str | None:
        found = WHY_SAY.search(" ".join(w.words(text)))
        if found is None:
            return None
        asked = norm(found.group(1))
        exact = [k for k in self.holds if norm(k) == asked]
        near = [k for k in self.holds if len(asked) >= 2 and asked in norm(k)]
        key = (exact or near or [None])[0]
        if key is None:
            return None
        info = self.holds[key]
        situation, stage = self._habit(key, info)
        when = f"I say it when {PLAIN[situation]} {WHEN.get(stage, WHEN[1])}."
        if info.get("source") == "own":
            day = str(info.get("added") or "")[:10]
            return f"I started saying \"{key}\" myself" + (f" on {day}" if day else "") + f". {when}"
        return f"\"{key}\" is one of the things I started with. {when}"

    def _habit(self, key: str, info: dict) -> tuple[str, int]:
        best, used = None, -1.0
        for slot, arms in self.arms.items():
            got = arms.get(key)
            if got and got[0] + got[1] > used:
                best, used = slot, got[0] + got[1]
        if best is not None:
            situation, _, stage = best.partition("/")
            if situation in PLAIN and stage.isdigit():
                return situation, int(stage)
        situations = info.get("situations") or ["question"]
        stages = info.get("stages") or [1]
        return (situations[0] if situations[0] in PLAIN else "question"), int(stages[0])

    def may_invent(self, now_s: float) -> bool:
        times = [t for t in self.made if isinstance(t, (int, float)) and now_s - t <= WEEK_S]
        return len(times) < INVENT_WEEK_MAX and (not times or now_s - max(times) >= INVENT_GAP_S)

    async def invent(self, phrase, now_s: float) -> str | None:
        if not self.may_invent(now_s):
            return None
        stage = self.rng.choice((1, 2, 3))
        groups = SEEDS[stage]
        situation = self.rng.choice(sorted(groups))
        seed = self.rng.choice(groups[situation])
        self.made.append(now_s)
        self.dirty = True
        try:
            phrased = await phrase(seed, "talk")
        except Exception:
            return None
        words = " ".join(str(getattr(phrased, "text", phrased) or "").split())
        problem = fence(words)
        if not problem and norm(words) in {norm(k) for k in self.holds}:
            problem = "it already has that one"
        if not problem and getattr(phrased, "source", "creative") != "creative":
            problem = "the wordsmith gave back the draft"
        if problem:
            self.log.append({"at": self._iso(), "hold": words[:60], "how": f"refused: {problem}"})
            del self.log[:-LOG_KEEP]
            return None
        self.holds[words] = {
            "source": "own",
            "added": self._iso(),
            "stages": [stage],
            "situations": list(SITUATIONS) if situation == "any" else [situation],
            "tries": 0,
            "trial": True,
            "from": seed,
        }
        self.diary(f"I've started saying \"{words}\" while I think.")
        return words

    def forget(self, person_id: str) -> None:
        changed = self.people.pop(person_id, None) is not None
        self.strangers.pop(person_id, None)
        kept = [entry for entry in self.log if entry.get("person") != person_id]
        changed = changed or len(kept) != len(self.log)
        self.log = kept
        self.pending = [e for e in self.pending if e.get("person") != person_id]
        if self.last is not None and self.last.get("person") == person_id:
            self.last = None
        if changed:
            self.dirty = True
            self.save(force=True)

    def to_dict(self) -> dict:
        return {
            "format": 1,
            "holds": self.holds,
            "arms": self.arms,
            "people": self.people,
            "log": self.log,
            "made": self.made,
        }

    def save(self, force: bool = False) -> None:
        if self.store is None or not (self.dirty or force):
            return
        self.store.write(HOLDS, self.to_dict(), keep_backup=False)
        self.dirty = False

    def _iso(self) -> str:
        return iso(self.clock.now()) if self.clock is not None else ""
