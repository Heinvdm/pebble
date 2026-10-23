import secrets

from ..mind.base import CallOptions
from .dial import DialInputs, clamp_level, dial_level, parts
from .ideas import Card, IdeaDecks
from .levers import ChoiceKnobs, MotionKnobs, choice_knobs, motion_knobs, whims_per_hour
from .sampling import SEED_BITS, call_options, is_creative
from .streams import Sink, Stream, Streams

SEED_LIMIT = 2**48


class Chaos:
    def __init__(self, seed: int | None = None, sink: Sink | None = None, pinned: float | None = None, enabled: bool = True):
        self.seed = int(seed) % SEED_LIMIT if seed is not None else secrets.randbits(48)
        self.enabled = enabled
        self.streams = Streams(self.seed, sink)
        self.pinned = None if pinned is None else clamp_level(pinned)
        self.inputs = DialInputs(pinned=self.pinned)
        self.level = dial_level(self.inputs) if enabled else 0.0

    @classmethod
    def disabled(cls) -> "Chaos":
        return cls(seed=0, enabled=False)

    def pin(self, value: float | None) -> None:
        self.pinned = None if value is None else clamp_level(value)
        self.update(self.inputs)

    def update(self, inputs: DialInputs) -> float:
        self.inputs = DialInputs(
            inputs.playfulness, inputs.valence, inputs.arousal, inputs.stage, inputs.quiet, inputs.fear, self.pinned, inputs.mood_weight
        )
        self.level = dial_level(self.inputs) if self.enabled else 0.0
        return self.level

    def explain(self) -> dict:
        if not self.enabled:
            return {"enabled": False, "level": 0.0}
        out = {"level": round(self.level, 2), "pinned": self.pinned, "quiet": self.inputs.quiet}
        out.update({name: round(value, 2) for name, value in parts(self.inputs).items()})
        return out

    def stream(self, lever: str) -> Stream:
        return self.streams.stream(lever)

    def choices(self) -> ChoiceKnobs | None:
        return choice_knobs(self.level) if self.enabled else None

    def motion(self) -> MotionKnobs:
        return motion_knobs(self.level)

    def whim_rate(self) -> float:
        return whims_per_hour(self.level) if self.enabled else 0.0

    def call_options(self, kind: str) -> CallOptions | None:
        if not self.enabled:
            return None
        lever = "words" if is_creative(kind) else "steady"
        return call_options(kind, self.level, self.stream(lever).getrandbits(SEED_BITS))

    def cards(self, decks: IdeaDecks, kind: str) -> list[Card]:
        if not self.enabled or not decks.size():
            return []
        return decks.draw(self.stream("seeds"), self.level, kind)
