import logging

from ..hearing.events import HOP_S, load_labels
from ..hearing.fetch import MODELS

log = logging.getLogger(__name__)

FALLBACK = (
    "Speech",
    "Silence",
    "Music",
    "Knock",
    "Door",
    "Doorbell",
    "Ding-dong",
    "Microwave oven",
    "Beep, bleep",
    "Ding",
    "Buzzer",
    "Frying (food)",
    "Sizzle",
    "Boiling",
    "Meow",
    "Cat",
    "Caterwaul",
    "Howl",
    "Whimper (dog)",
    "Bark",
    "Dog",
    "Rain",
    "Rain on surface",
    "Raindrop",
    "Thunder",
    "Telephone bell ringing",
    "Ringtone",
    "Telephone",
    "Alarm clock",
    "Steam whistle",
    "Whistle",
    "Whistling",
    "Cupboard open or close",
    "Drawer open or close",
    "Walk, footsteps",
    "Smoke detector, smoke alarm",
    "Fire alarm",
    "Glass",
    "Water tap, faucet",
)
SILENCE = 0.9


def sim_labels() -> list[str]:
    try:
        return load_labels(MODELS)
    except Exception:
        return list(FALLBACK)


class ScriptedSounds:
    window = 15600

    def __init__(self, labels: list[str] | None = None, hop_s: float = HOP_S):
        self.labels = list(labels or sim_labels())
        self.index = {name: i for i, name in enumerate(self.labels)}
        self.hop_s = hop_s
        self.clips: dict[str, tuple[dict, float, float]] = {}
        self.next_at: float | None = None
        self.want_vectors = False
        self.rows = 0

    def play(self, name: str, scores: dict, start: float, seconds: float) -> None:
        missing = [label for label in scores if label not in self.index]
        if missing:
            log.warning("sim sounds: no class %s", ", ".join(missing))
        self.clips[name] = (dict(scores), start, start + seconds)

    def stop(self, name: str) -> None:
        self.clips.pop(name, None)

    def gap(self) -> None:
        self.next_at = None

    def take_vectors(self) -> list:
        return []

    def feed(self, block=None) -> list[tuple[float, list[float]]]:
        end = block.end if block is not None else (self.next_at or 0.0)
        if self.next_at is None:
            self.next_at = end
        out = []
        while self.next_at <= end:
            at = self.next_at
            scores = [0.0] * len(self.labels)
            quiet = True
            for clip, start, stop in self.clips.values():
                if start <= at <= stop:
                    quiet = False
                    for label, value in clip.items():
                        column = self.index.get(label)
                        if column is not None:
                            scores[column] = max(scores[column], float(value))
            if quiet and "Silence" in self.index:
                scores[self.index["Silence"]] = SILENCE
            out.append((at, scores))
            self.next_at += self.hop_s
        self.rows += len(out)
        self.clips = {name: clip for name, clip in self.clips.items() if clip[2] >= end - 5.0}
        return out

    def status(self) -> dict:
        return {"kind": "sim", "rows": self.rows, "playing": sorted(self.clips)}
