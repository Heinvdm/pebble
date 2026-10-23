import logging
import math
from collections import deque
from dataclasses import dataclass, field

from .events import HOP_S

log = logging.getLogger(__name__)

SPEECH = ("Speech", "Child speech, kid speaking", "Hubbub, speech noise, speech babble")
COOKING = ("Frying (food)", "Sizzle", "Boiling")
COOKING_SCORE = 0.2
COOKING_WINDOW_S = 30.0
MICROWAVE = ("Microwave oven",)
MICROWAVE_HUM = 0.2
MICROWAVE_ON_S = 15.0
MICROWAVE_BEEPS = ("Beep, bleep", "Ding", "Buzzer")
MICROWAVE_BEEP = 0.25
MICROWAVE_AFTER_S = 15.0
KEEP_ROWS = 64


@dataclass(frozen=True)
class Burst:
    event: str
    classes: tuple
    threshold: float
    window_s: float
    hits: int
    single: float
    gap_s: float
    reject: tuple = ()


@dataclass(frozen=True)
class Spell:
    event: str
    classes: tuple
    threshold: float
    window_s: float
    share: float
    quiet_s: float
    rest_s: float = 0.0


BURSTS = (
    Burst("knock", ("Knock",), 0.25, 3.0, 2, 0.55, 4.0, ("Cupboard open or close", "Drawer open or close", "Walk, footsteps", "Chopping (food)", "Clapping", "Finger snapping")),
    Burst("doorbell", ("Doorbell", "Ding-dong"), 0.3, 3.0, 1, 0.45, 15.0),
    Burst("phone", ("Telephone bell ringing", "Ringtone", "Telephone"), 0.3, 6.0, 3, 0.9, 60.0),
    Burst("kettle", ("Steam whistle", "Whistle"), 0.35, 5.0, 3, 0.9, 120.0, ("Whistling",)),
    Burst("thunder", ("Thunder", "Thunderstorm"), 0.3, 5.0, 2, 0.6, 600.0),
)
SPELLS = (
    Spell("rain", ("Rain", "Rain on surface", "Raindrop"), 0.25, 60.0, 0.6, 600.0, 600.0),
    Spell("meowing", ("Meow", "Caterwaul", "Cat"), 0.3, 30.0, 0.1, 60.0),
    Spell("dog_crying", ("Howl", "Whimper (dog)"), 0.3, 30.0, 0.1, 120.0),
    Spell("alarm_clock", ("Alarm clock",), 0.3, 300.0, 0.6, 120.0, 1800.0),
)


@dataclass(frozen=True)
class SoundEvent:
    event: str
    at: float
    score: float
    detail: dict = field(default_factory=dict)


@dataclass
class _SpellState:
    hits: deque = field(default_factory=deque)
    on: bool = False
    began: float = 0.0
    last: float = -math.inf
    ended: float = -math.inf
    count: int = 0


def _columns(index: dict, names: tuple) -> tuple:
    return tuple(index[name] for name in names if name in index)


class HouseSounds:
    def __init__(self, labels: list[str]):
        index = {name: i for i, name in enumerate(labels)}
        self.labels = list(labels)
        self.bursts = [(rule, _columns(index, rule.classes), _columns(index, rule.reject)) for rule in BURSTS]
        self.spells = [(rule, _columns(index, rule.classes)) for rule in SPELLS]
        missing = sorted({name for rule in BURSTS + SPELLS for name in rule.classes} - set(index))
        if missing:
            log.warning("hearing: the sound model has no class %s", ", ".join(missing))
        self.speech = _columns(index, SPEECH)
        self.cooking = _columns(index, COOKING)
        self.microwave = _columns(index, MICROWAVE)
        self.beeping = _columns(index, MICROWAVE_BEEPS)
        self.hits: dict[str, deque] = {rule.event: deque() for rule, _, _ in self.bursts}
        self.said: dict[str, float] = {}
        self.states: dict[str, _SpellState] = {rule.event: _SpellState() for rule, _ in self.spells}
        self.cooking_hits: deque = deque()
        self.cooking_kind = ""
        self.hum_since: float | None = None
        self.hum_last = -math.inf
        self.hum_ended: float | None = None
        self.rows: deque = deque(maxlen=KEEP_ROWS)
        self.last_at: float | None = None

    @staticmethod
    def _best(scores, columns: tuple) -> float:
        return max((scores[c] for c in columns), default=0.0)

    def feed(self, rows) -> list[SoundEvent]:
        out: list[SoundEvent] = []
        for at, scores in rows:
            self.last_at = at
            speech = self._best(scores, self.speech)
            top = max(range(len(scores)), key=scores.__getitem__) if scores else -1
            self.rows.append((at, speech, self.labels[top] if 0 <= top < len(self.labels) else "", scores[top] if top >= 0 else 0.0))
            for rule, columns, reject in self.bursts:
                found = self._burst(rule, columns, reject, at, scores)
                if found is not None:
                    out.append(found)
            for rule, columns in self.spells:
                out.extend(self._spell(rule, columns, at, scores))
            self._cook(at, scores)
            found = self._microwave(at, scores)
            if found is not None:
                out.append(found)
        return out

    def _burst(self, rule: Burst, columns: tuple, reject: tuple, at: float, scores) -> SoundEvent | None:
        score = self._best(scores, columns)
        if reject and self._best(scores, reject) > score:
            score = 0.0
        window = self.hits[rule.event]
        if score >= rule.threshold:
            window.append((at, score))
        while window and at - window[0][0] > rule.window_s:
            window.popleft()
        if not window or window[-1][0] != at:
            return None
        if len(window) < rule.hits and score < rule.single:
            return None
        if at - self.said.get(rule.event, -math.inf) < rule.gap_s:
            self.said[rule.event] = at
            return None
        self.said[rule.event] = at
        return SoundEvent(rule.event, at, round(max(s for _, s in window), 3), {"hits": len(window)})

    def _spell(self, rule: Spell, columns: tuple, at: float, scores) -> list[SoundEvent]:
        state = self.states[rule.event]
        score = self._best(scores, columns)
        if score >= rule.threshold:
            state.hits.append(at)
            state.last = at
            if state.on:
                state.count += 1
        while state.hits and at - state.hits[0] > rule.window_s:
            state.hits.popleft()
        expected = max(1, int(rule.window_s / HOP_S))
        out = []
        if not state.on and len(state.hits) >= max(2, math.ceil(rule.share * expected)) and at - state.ended >= rule.rest_s:
            state.on = True
            state.began = state.hits[0]
            state.count = len(state.hits)
            out.append(SoundEvent(rule.event, at, round(score, 3), {"phase": "start"}))
        elif state.on and at - state.last >= rule.quiet_s:
            state.on = False
            state.ended = state.last
            out.append(SoundEvent(rule.event, at, 0.0, {"phase": "end", "began": state.began, "ended": state.last, "seconds": round(state.last - state.began, 1), "hits": state.count}))
        return out

    def _cook(self, at: float, scores) -> None:
        best = 0.0
        kind = ""
        for column in self.cooking:
            if scores[column] > best:
                best, kind = scores[column], self.labels[column]
        if best >= COOKING_SCORE:
            self.cooking_hits.append(at)
            self.cooking_kind = kind
        while self.cooking_hits and at - self.cooking_hits[0] > COOKING_WINDOW_S:
            self.cooking_hits.popleft()

    def cooking_share(self) -> float:
        return min(1.0, len(self.cooking_hits) / max(1.0, COOKING_WINDOW_S / HOP_S))

    def cooking_word(self) -> str:
        return {"Boiling": "boiling", "Frying (food)": "sizzling", "Sizzle": "sizzling"}.get(self.cooking_kind, "cooking")

    def _microwave(self, at: float, scores) -> SoundEvent | None:
        hum = self._best(scores, self.microwave)
        if hum >= MICROWAVE_HUM:
            if self.hum_since is None or at - self.hum_last > 3 * HOP_S:
                self.hum_since = at
            self.hum_last = at
            return None
        if self.hum_since is not None and at - self.hum_last > 2 * HOP_S:
            if self.hum_last - self.hum_since >= MICROWAVE_ON_S:
                self.hum_ended = self.hum_last
            self.hum_since = None
        if self.hum_ended is not None and at - self.hum_ended > MICROWAVE_AFTER_S:
            self.hum_ended = None
        beeping = self._best(scores, self.beeping)
        recent = self.hum_ended is not None or (self.hum_since is not None and self.hum_last - self.hum_since >= MICROWAVE_ON_S)
        if beeping >= MICROWAVE_BEEP and recent:
            self.hum_ended = None
            self.hum_since = None
            if at - self.said.get("microwave", -math.inf) < 60.0:
                return None
            self.said["microwave"] = at
            return SoundEvent("microwave", at, round(beeping, 3))
        return None

    def quiet_frames(self, seconds: float = 10.0, speech_below: float = 0.3) -> list[float]:
        if not self.rows:
            return []
        last = self.rows[-1][0]
        return [at for at, speech, top, score in self.rows if last - at <= seconds and speech < speech_below and top != "Silence" and score >= 0.1]

    def spell(self, event: str) -> _SpellState | None:
        return self.states.get(event)
