import base64
import binascii
import logging
import math
import re
import struct
from dataclasses import dataclass, field

from .audio import RATE, Block

log = logging.getLogger(__name__)

SOUNDS = "sounds.json"
WINDOW = 15600
HOP = 7680
FFT = 1024
STEP = 512
BANDS = 40
LOW_HZ = 250.0
HIGH_HZ = 6000.0
QUIET_DB = -75.0
MAX_SOUNDS = 20
TEACHINGS = 4
VIEWS_PER_TEACHING = 3
TOP_SCORES = 32
PROFILE_MATCH = 0.8
KIND_MATCH = 0.5
PROFILE_SURE = 0.92
KIND_SURE = 0.7
TIE = 0.03
PAIR_S = 3.0
JOIN_S = 0.6
GAP_S = 120.0
NAME_MAX = 40
TRUSTED_AFTER = 2
ENDINGS = {
    "finishing": "finished",
    "finished": "finished",
    "done": "finished",
    "ending": "finished",
    "ready": "ready",
    "beeping": "beeping",
    "ringing": "ringing",
    "going off": "going off",
    "playing": "playing",
}


def _numpy():
    try:
        import numpy
    except ImportError:
        return None
    return numpy


@dataclass(frozen=True)
class Frame:
    at: float
    profile: object
    kind: object = None
    kind_name: str = ""
    level_db: float = 0.0


@dataclass
class View:
    profile: object
    kind: object = None
    kind_name: str = ""

    def to_dict(self, np) -> dict:
        out = {"p": [round(float(v), 4) for v in self.profile]}
        if self.kind is not None:
            out[self.kind_name] = _pack(np.asarray(self.kind, dtype=np.float32))
        return out

    @classmethod
    def from_dict(cls, data: dict, np) -> "View | None":
        try:
            profile = np.asarray([float(v) for v in data["p"]], dtype=np.float32)
        except (KeyError, TypeError, ValueError):
            return None
        if profile.size != BANDS:
            return None
        for name in ("e", "s"):
            if isinstance(data.get(name), str):
                kind = _unpack(data[name], np)
                if kind is not None:
                    return cls(profile, kind, name)
        return cls(profile)


@dataclass
class Sound:
    key: str
    name: str
    by: str | None
    at: float
    teachings: list = field(default_factory=list)
    heard: int = 0
    right: int = 0
    wrong: int = 0
    last: float = -math.inf

    @property
    def trusted(self) -> bool:
        return len(self.teachings) >= TRUSTED_AFTER

    def views(self) -> list:
        return [view for teaching in self.teachings for view in teaching]

    def says(self) -> str:
        return announcement(self.name)

    def to_dict(self, np) -> dict:
        return {"key": self.key, "name": self.name, "by": self.by, "at": self.at, "heard": self.heard, "right": self.right, "wrong": self.wrong, "teachings": [[view.to_dict(np) for view in teaching] for teaching in self.teachings]}

    @classmethod
    def from_dict(cls, data: dict, np) -> "Sound | None":
        try:
            sound = cls(str(data["key"]), str(data["name"])[:NAME_MAX], data.get("by"), float(data.get("at", 0.0)), [], int(data.get("heard", 0)), int(data.get("right", 0)), int(data.get("wrong", 0)))
        except (KeyError, TypeError, ValueError):
            return None
        for raw in (data.get("teachings") or [])[-TEACHINGS:]:
            views = [v for v in (View.from_dict(item, np) for item in raw or [] if isinstance(item, dict)) if v is not None]
            if views:
                sound.teachings.append(views[:VIEWS_PER_TEACHING])
        return sound if sound.teachings else None


@dataclass(frozen=True)
class Match:
    key: str
    at: float
    score: float
    others: tuple = ()


def _pack(values) -> str:
    return "f16:" + base64.b64encode(struct.pack(f"<{len(values)}e", *(float(v) for v in values))).decode("ascii")


def _unpack(text: str, np):
    if not text.startswith("f16:"):
        return None
    try:
        raw = base64.b64decode(text[4:], validate=True)
    except (ValueError, binascii.Error):
        return None
    if not raw or len(raw) % 2:
        return None
    return np.frombuffer(raw, dtype="<f2").astype(np.float32)


def _plain(name: str) -> str:
    words = " ".join(str(name or "").lower().replace("'s ", " ").split())
    return re.sub(r" (?:is|has|was|has been|is now) (?=(?:finishing|finished|done|ending|ready|beeping|ringing|going off|playing)$)", " ", words)


def thing_of(name: str) -> str:
    words = _plain(name)
    for ending in sorted(ENDINGS, key=len, reverse=True):
        if words.endswith(" " + ending):
            return words[: -len(ending) - 1].strip()
    return words


def announcement(name: str) -> str:
    words = _plain(name)
    thing = thing_of(words)
    ending = next((ENDINGS[e] for e in sorted(ENDINGS, key=len, reverse=True) if words.endswith(" " + e)), "")
    if not thing.startswith(("the ", "my ", "our ", "a ")):
        thing = "the " + thing
    shown = thing[:1].upper() + thing[1:]
    if ending == "finished":
        return f"{shown}'s finished."
    if ending == "ready":
        return f"{shown}'s ready."
    if ending:
        return f"{shown}'s {ending}."
    return f"That sounded like {thing}."


def logged(name: str) -> str:
    words = _plain(name)
    thing = thing_of(words)
    ending = next((ENDINGS[e] for e in sorted(ENDINGS, key=len, reverse=True) if words.endswith(" " + e)), "")
    if not thing.startswith(("the ", "my ", "our ", "a ")):
        thing = "the " + thing
    if ending == "finished":
        return f"{thing} finished"
    if ending == "ready":
        return f"{thing} was ready"
    if ending:
        return f"{thing} was {ending}"
    return f"a sound like {thing}"


def key_for(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", thing_of(name)).strip("-")[:NAME_MAX] or "sound"


def profile(samples, np):
    values = np.asarray(samples, dtype=np.float32).reshape(-1)
    if values.size < FFT:
        return None
    window = np.hanning(FFT).astype(np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(values, FFT)[::STEP] * window
    power = (np.abs(np.fft.rfft(frames, axis=1)) ** 2).mean(axis=0)
    loud = 10.0 * math.log10(float(power.sum()) / (FFT * FFT / 4.0) + 1e-12)
    if loud < QUIET_DB:
        return None, loud
    edges = np.geomspace(LOW_HZ, HIGH_HZ, BANDS + 1)
    index = np.searchsorted(edges, np.fft.rfftfreq(FFT, 1.0 / RATE)) - 1
    keep = (index >= 0) & (index < BANDS)
    bands = np.bincount(index[keep], weights=power[keep], minlength=BANDS)
    shaped = np.log10(bands + 1e-10)
    shaped = shaped - shaped.mean()
    norm = float(np.linalg.norm(shaped))
    if norm < 1e-6:
        return None, loud
    return (shaped / norm).astype(np.float32), loud


class Profiler:
    def __init__(self, np=None):
        self.np = np if np is not None else _numpy()
        self.buffer = None
        self.total = 0
        self.next_end = WINDOW

    @property
    def available(self) -> bool:
        return self.np is not None

    def gap(self) -> None:
        self.buffer = None
        self.total = 0
        self.next_end = WINDOW

    def feed(self, block: Block) -> list:
        np = self.np
        if np is None:
            return []
        if block.skipped:
            self.gap()
        fresh = np.frombuffer(block.samples, dtype=np.int16).astype(np.float32) / 32768.0 if block.samples.typecode == "h" else np.asarray(block.samples, dtype=np.float32)
        self.buffer = fresh if self.buffer is None else np.concatenate([self.buffer, fresh])
        self.total += fresh.size
        out = []
        while self.total >= self.next_end:
            end = self.buffer.size - (self.total - self.next_end)
            self.next_end += HOP
            if end < WINDOW:
                continue
            shaped, loud = profile(self.buffer[end - WINDOW : end], np)
            if shaped is not None:
                out.append((block.end - (self.total - (self.next_end - HOP)) / RATE, shaped, loud))
        keep = WINDOW
        if self.buffer.size > keep:
            self.buffer = self.buffer[-keep:]
        return out


def top_scores(scores, np, count: int = TOP_SCORES):
    values = np.asarray(scores, dtype=np.float32)
    if values.size <= count:
        return values
    out = np.zeros_like(values)
    index = np.argpartition(values, -count)[-count:]
    out[index] = values[index]
    return out


def join(profiles: list, rows: list, vectors: list, np, within: float = JOIN_S) -> list[Frame]:
    out = []
    for at, shaped, loud in profiles:
        vector = min(vectors, key=lambda item: abs(item[0] - at), default=None)
        if vector is not None and abs(vector[0] - at) <= within:
            out.append(Frame(at, shaped, np.asarray(vector[1], dtype=np.float32), "e", loud))
            continue
        row = min(rows, key=lambda item: abs(item[0] - at), default=None)
        if row is not None and abs(row[0] - at) <= within:
            out.append(Frame(at, shaped, top_scores(row[1], np), "s", loud))
            continue
        out.append(Frame(at, shaped, None, "", loud))
    return out


def _cosine(a, b, np) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.dot(a, b)) / (na * nb)


class TaughtSounds:
    def __init__(self, data: dict | None = None, np=None):
        self.np = np if np is not None else _numpy()
        self.sounds: dict[str, Sound] = {}
        self.dirty = False
        self.recent: dict[str, list] = {}
        if self.np is not None:
            for raw in (data or {}).get("sounds") or []:
                sound = Sound.from_dict(raw, self.np) if isinstance(raw, dict) else None
                if sound is not None:
                    self.sounds[sound.key] = sound

    @property
    def available(self) -> bool:
        return self.np is not None

    def __len__(self) -> int:
        return len(self.sounds)

    def find(self, name: str) -> Sound | None:
        key = key_for(name)
        if key in self.sounds:
            return self.sounds[key]
        wanted = thing_of(name)
        hits = [s for s in self.sounds.values() if wanted and (wanted in thing_of(s.name) or thing_of(s.name) in wanted)]
        return hits[0] if len(hits) == 1 else None

    def pick(self, frames: list[Frame]) -> list[Frame]:
        usable = [f for f in frames if f.profile is not None]
        return sorted(usable, key=lambda f: -f.level_db)[:VIEWS_PER_TEACHING]

    def teach(self, name: str, frames: list[Frame], by: str | None, at: float) -> tuple[Sound | None, str]:
        if self.np is None:
            return None, "no numpy"
        chosen = self.pick(frames)
        if not chosen:
            return None, "nothing heard"
        key = key_for(name)
        sound = self.sounds.get(key)
        if sound is None:
            if len(self.sounds) >= MAX_SOUNDS:
                return None, "full"
            sound = Sound(key, " ".join(name.split())[:NAME_MAX], by, at)
            self.sounds[key] = sound
        sound.teachings.append([View(f.profile, f.kind, f.kind_name) for f in chosen])
        del sound.teachings[:-TEACHINGS]
        self.dirty = True
        return sound, "trusted" if sound.trusted else "learning"

    def _frame_score(self, frame: Frame, sound: Sound) -> tuple[float, float]:
        np = self.np
        best = (0.0, 0.0)
        for view in sound.views():
            p = _cosine(frame.profile, view.profile, np)
            if p < PROFILE_MATCH:
                continue
            k = 0.0
            if frame.kind is not None and view.kind is not None and frame.kind_name == view.kind_name and frame.kind.size == view.kind.size:
                k = _cosine(frame.kind, view.kind, np)
            elif frame.kind is None or view.kind is None:
                k = KIND_MATCH if p >= PROFILE_SURE else 0.0
            if k >= KIND_MATCH and p > best[0]:
                best = (p, k)
        return best

    def match(self, frames: list[Frame]) -> list[Match]:
        if self.np is None or not self.sounds:
            return []
        out = []
        for frame in frames:
            if frame.profile is None:
                continue
            scored = []
            for sound in self.sounds.values():
                p, k = self._frame_score(frame, sound)
                if p <= 0.0:
                    continue
                hits = self.recent.setdefault(sound.key, [])
                hits.append(frame.at)
                hits[:] = [t for t in hits if frame.at - t <= PAIR_S]
                if len(hits) >= 2 or (p >= PROFILE_SURE and k >= KIND_SURE):
                    scored.append((p, sound))
            if not scored:
                continue
            scored.sort(key=lambda item: -item[0])
            best_score, best = scored[0]
            if frame.at - best.last < GAP_S:
                continue
            others = tuple(s.key for score, s in scored[1:] if best_score - score <= TIE)
            best.last = frame.at
            self.recent.pop(best.key, None)
            out.append(Match(best.key, frame.at, round(best_score, 3), others))
        return out

    def forget(self, key: str) -> bool:
        found = self.sounds.pop(key, None) is not None
        self.recent.pop(key, None)
        if found:
            self.dirty = True
        return found

    def forget_person(self, person_id: str) -> None:
        for sound in self.sounds.values():
            if sound.by == person_id:
                sound.by = None
                self.dirty = True

    def to_dict(self) -> dict:
        if self.np is None:
            return {"format": 1, "sounds": []}
        return {"format": 1, "sounds": [s.to_dict(self.np) for s in sorted(self.sounds.values(), key=lambda s: s.key)]}
