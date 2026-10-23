import math
import re
from dataclasses import dataclass

PAUSE_S = 1.2
HOUR_S = 3600.0
RATE = 2.0
MOST_RATE = 4.0
LONGEST_S = 4 * HOUR_S
REACT_S = 20.0
START_S = 5.0
NUDGES = {"hushed": -2.0, "talked_over": -1.0, "ignored": -0.5, "warm": 1.0}
TALLY_AT = 2.0
NUDGE_GAP_S = 900.0
WHY = {
    "hushed": "people hushed me when I spoke up unasked",
    "talked_over": "people talked over me when I spoke up unasked",
    "ignored": "nobody took it up when I spoke up unasked",
    "warm": "people took it up warmly when I spoke up unasked",
}
HUSH = re.compile(r"\b(?:shh+|shush|hush|(?:be|keep) quiet|quiet(?: please| now)?|not now|stop talking|shut up|pipe down|enough(?: now)?|you talk too much|talk less|too chatty)\b")
WARM = re.compile(r"\b(?:thanks|thank you|ha(?:ha)+|hehe+|lol|aw+|aww+|good one|nice one|that's (?:funny|cute|sweet|nice|right|true)|you're right|good point|oh cool|love (?:that|it))\b")
GAP_S = 180.0
QUESTION_GAP_S = 30.0
FLOW_S = 8.0
REASONS = {
    "room_question": 1.0,
    "care": 0.9,
    "named": 0.2,
    "feeling": 0.3,
}
ALWAYS = frozenset({"room_question", "care"})
WHILE_HUSHED = frozenset({"room_question", "care"})


@dataclass(frozen=True)
class Moment:
    now: float
    quiet: bool = False
    alarm: bool = False
    hushed: bool = False
    argument: bool = False
    crying: bool = False
    on_phone: bool = False
    upset: bool = False
    silent_for: float = math.inf
    someone_talking: bool = False
    pebble_speaking: bool = False
    flowing: bool = False


@dataclass(frozen=True)
class Decision:
    speak: bool
    why: str


def hushing(text: str) -> bool:
    return bool(HUSH.search((text or "").lower()))


def warm(text: str) -> bool:
    return bool(WARM.search((text or "").lower()))


@dataclass
class Watch:
    reason: str
    said_at: float
    someone_there: bool
    ended_at: float | None = None
    spoke: bool = False
    talked_over: bool = False
    hushed: bool = False
    warm: bool = False

    def verdict(self) -> str | None:
        if self.hushed:
            return "hushed"
        if self.warm:
            return "warm"
        if self.talked_over:
            return "talked_over"
        if self.someone_there and self.reason not in ALWAYS:
            return "ignored"
        return None


class SpeakUp:
    def __init__(self, chatty=lambda: 3, rng=None, rate=lambda: RATE):
        self.chatty = chatty
        self.rng = rng
        self.rate = rate
        self.spoken: list[tuple[float, str]] = []
        self.refused: dict[str, int] = {}
        self.watch: Watch | None = None
        self.tally = 0.0
        self.since: dict[str, int] = {}
        self.nudged_at = -math.inf
        self.reactions: dict[str, int] = {}

    def talkativeness(self) -> int:
        try:
            return max(1, min(10, int(self.chatty())))
        except (TypeError, ValueError):
            return 3

    def per_hour(self) -> float:
        try:
            value = float(self.rate())
        except (TypeError, ValueError):
            return RATE
        if not math.isfinite(value):
            return RATE
        return max(0.0, min(MOST_RATE, value))

    def allowance(self) -> tuple[int, float]:
        rate = self.per_hour()
        if rate <= 0.0:
            return 0, HOUR_S
        allowed = math.ceil(rate - 1e-9)
        return allowed, min(LONGEST_S, HOUR_S * allowed / rate)

    def blocked(self, moment: Moment) -> str:
        if moment.quiet:
            return "quiet hours"
        if moment.alarm:
            return "an alarm is going"
        if moment.argument:
            return "people are arguing"
        if moment.crying:
            return "someone is crying"
        if moment.upset:
            return "someone seems upset"
        if moment.on_phone:
            return "someone is on the phone"
        if moment.pebble_speaking:
            return "I'm already talking"
        if moment.someone_talking:
            return "someone is talking"
        if moment.silent_for < PAUSE_S:
            return "no pause yet"
        return ""

    def hold_tongue(self, moment: Moment) -> bool:
        return bool(moment.argument or moment.crying or moment.on_phone or moment.upset or moment.someone_talking or moment.flowing)

    def decide(self, moment: Moment, reason: str, roll: float | None = None) -> Decision:
        why = self.blocked(moment)
        if not why and moment.hushed and reason not in WHILE_HUSHED:
            why = "people are busy"
        now = moment.now
        allowed, window = self.allowance()
        self.spoken = [(at, r) for at, r in self.spoken if now - at < max(HOUR_S, window)]
        if not why and reason not in ALWAYS and len([1 for at, r in self.spoken if r not in ALWAYS and now - at < window]) >= allowed:
            why = "I've said enough this hour"
        last = self.spoken[-1][0] if self.spoken else -math.inf
        gap = QUESTION_GAP_S if reason in ALWAYS else GAP_S * (11 - self.talkativeness()) / 8.0
        if not why and now - last < gap:
            why = "I spoke up a moment ago"
        if not why and reason not in ALWAYS:
            chance = REASONS.get(reason, 0.2) * (0.5 + self.talkativeness() / 10.0)
            draw = roll if roll is not None else (self.rng.random() if self.rng is not None else 0.0)
            if draw >= chance:
                why = "I let it pass"
        if why:
            self.refused[why] = self.refused.get(why, 0) + 1
            return Decision(False, why)
        return Decision(True, reason)

    def used(self, now: float, reason: str, someone_there: bool = True) -> None:
        self.spoken.append((now, reason))
        self.watch = Watch(reason, now, someone_there)

    def watching(self, now: float) -> bool:
        watch = self.watch
        return watch is not None and (watch.ended_at is None or now - watch.ended_at <= REACT_S)

    def talked_over(self, now: float) -> None:
        if self.watching(now) and self.watch.ended_at is None:
            self.watch.talked_over = True

    def heard(self, now: float, text: str, to_me: bool) -> None:
        if not self.watching(now):
            return
        if hushing(text):
            self.watch.hushed = True
        elif to_me or warm(text):
            self.watch.warm = True

    def laughed(self, now: float) -> None:
        if self.watching(now):
            self.watch.warm = True

    def tick(self, now: float, speaking: bool) -> tuple[int, str] | None:
        watch = self.watch
        if watch is None:
            return None
        if watch.ended_at is None:
            if speaking:
                watch.spoke = True
            elif watch.spoke or now - watch.said_at >= START_S:
                watch.ended_at = now
            return None
        if now - watch.ended_at <= REACT_S and not watch.hushed:
            return None
        self.watch = None
        kind = watch.verdict()
        if kind is None:
            return None
        self.reactions[kind] = self.reactions.get(kind, 0) + 1
        self.tally += NUDGES[kind]
        self.since[kind] = self.since.get(kind, 0) + 1
        if abs(self.tally) < TALLY_AT or now - self.nudged_at < NUDGE_GAP_S:
            return None
        direction = 1 if self.tally > 0 else -1
        named = [k for k in self.since if (NUDGES[k] > 0) == (direction > 0)]
        why = WHY[max(named, key=lambda k: (self.since[k], abs(NUDGES[k])))] if named else WHY[kind]
        self.tally = 0.0
        self.since = {}
        self.nudged_at = now
        return direction, why
