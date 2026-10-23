import base64
import binascii
import csv
import json
import logging
import math
import struct
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .audio import RATE, Block, to_floats

log = logging.getLogger(__name__)

HOP_S = 0.48
CLASS_MAP = "yamnet_class_map.csv"
EMBEDDING = 1024
KEEP_VECTORS = 24


@dataclass(frozen=True)
class Rule:
    event: str
    classes: tuple
    threshold: float
    span_s: float
    share: float
    confidence: float
    gap_s: float
    text: str
    single: float = 2.0


RULES = (
    Rule("alarm_sound", ("Smoke detector, smoke alarm", "Fire alarm"), 0.3, 4.0, 0.4, 0.4, 20.0, "the sound model heard what sounds like a smoke or fire alarm"),
    Rule("glass", ("Glass", "Shatter", "Breaking"), 0.3, 2.0, 0.4, 0.6, 30.0, "the sound model heard what sounded like glass breaking", single=0.6),
    Rule("screaming", ("Screaming",), 0.35, 3.0, 0.5, 0.5, 30.0, "the sound model heard screaming", single=0.7),
    Rule("shouting", ("Shout", "Yell", "Bellow", "Children shouting"), 0.35, 5.0, 0.5, 0.3, 60.0, "the sound model heard shouting"),
    Rule("baby", ("Baby cry, infant cry",), 0.3, 90.0, 0.6, 0.7, 600.0, "the sound model heard a baby crying for more than a minute"),
    Rule("dog", ("Bark", "Dog", "Bow-wow", "Yip", "Howl"), 0.3, 120.0, 0.5, 0.7, 900.0, "the sound model heard a dog barking for a couple of minutes"),
    Rule("water", ("Water tap, faucet", "Sink (filling or washing)", "Bathtub (filling or washing)", "Water", "Gurgling"), 0.2, 300.0, 0.7, 0.7, 1800.0, "the sound model heard water running for five minutes"),
)


def load_labels(folder: Path) -> list[str]:
    path = Path(folder) / CLASS_MAP
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows.sort(key=lambda row: int(row["index"]))
    return [row["display_name"] for row in rows]


@dataclass(frozen=True)
class Heard:
    event: str
    confidence: float
    at: float
    text: str
    score: float


class SoundEvents:
    def __init__(self, labels: list[str], rules: tuple = RULES):
        index = {name: i for i, name in enumerate(labels)}
        self.rules = []
        for rule in rules:
            columns = tuple(index[name] for name in rule.classes if name in index)
            missing = [name for name in rule.classes if name not in index]
            if missing:
                log.warning("hearing: the sound model has no class %s", ", ".join(missing))
            if columns:
                self.rules.append((rule, columns))
        self.seen: dict[str, deque] = {rule.event: deque() for rule, _ in self.rules}
        self.said: dict[str, float] = {}
        self.top: list = []

    def share(self, event: str, seconds: float, until: float | None = None) -> float:
        rule = next((rule for rule, _ in self.rules if rule.event == event), None)
        window = self.seen.get(event)
        if rule is None or not window:
            return 0.0
        try:
            rows = list(window)
        except RuntimeError:
            return 0.0
        end = rows[-1][0] if until is None else max(until, rows[-1][0])
        recent = [score for at, score in rows if end - at <= seconds]
        hits = sum(1 for score in recent if score >= rule.threshold)
        return min(1.0, hits / max(1, int(seconds / HOP_S)))

    def feed(self, rows: list[tuple[float, list[float]]]) -> list[Heard]:
        out = []
        for at, scores in rows:
            for rule, columns in self.rules:
                score = max(scores[c] for c in columns)
                window = self.seen[rule.event]
                window.append((at, score))
                while window and at - window[0][0] > rule.span_s:
                    window.popleft()
                expected = max(1, int(rule.span_s / HOP_S))
                hits = sum(1 for _, s in window if s >= rule.threshold)
                if score < rule.threshold or (hits < max(1, math.ceil(rule.share * expected)) and score < rule.single):
                    continue
                if at - self.said.get(rule.event, -math.inf) < rule.gap_s:
                    continue
                self.said[rule.event] = at
                out.append(Heard(rule.event, rule.confidence, at, rule.text, round(score, 3)))
            self.top = sorted(range(len(scores)), key=lambda i: -scores[i])[:3]
        return out


class LocalModel:
    def __init__(self, model, hop_s: float = HOP_S):
        self.model = model
        self.window = int(getattr(model, "window", 15600))
        self.hop = int(hop_s * RATE)
        self.buffer: list[float] = []
        self.first = 0
        self.total = 0
        self.next_end = self.window
        self.runs = 0
        self.seconds = 0.0
        self.want_vectors = False
        self.vectors: list = []

    @property
    def labels(self) -> list[str]:
        return list(self.model.labels)

    def gap(self) -> None:
        self.buffer = []
        self.first = 0
        self.total = 0
        self.next_end = self.window

    def take_vectors(self) -> list:
        found, self.vectors = self.vectors, []
        return found

    def feed(self, block: Block) -> list[tuple[float, list[float]]]:
        if block.skipped:
            self.gap()
        self.buffer.extend(to_floats(block.samples))
        self.total += len(block.samples)
        rows = []
        both = getattr(self.model, "both", None)
        while self.total >= self.next_end:
            end = self.next_end - self.first
            self.next_end += self.hop
            if end < self.window:
                continue
            started = time.perf_counter()
            embedding = None
            if both is not None:
                found, embedding = both(self.buffer[end - self.window : end])
                scores = list(found)
            else:
                scores = list(self.model.scores(self.buffer[end - self.window : end]))
            self.seconds += time.perf_counter() - started
            self.runs += 1
            at = block.end - (self.total - (self.next_end - self.hop)) / RATE
            rows.append((at, scores))
            if embedding is not None:
                self.vectors.append((at, embedding))
                del self.vectors[:-KEEP_VECTORS]
        keep_from = self.next_end - self.window
        if keep_from > self.first:
            del self.buffer[: keep_from - self.first]
            self.first = keep_from
        return rows

    def status(self) -> dict:
        return {"kind": "local", "runs": self.runs, "ms_per_run": round(1000 * self.seconds / self.runs, 1) if self.runs else None}


class BridgeModel:
    def __init__(self, labels: list[str], bridge=None, monotonic: Callable[[], float] = time.monotonic):
        self.labels = labels
        self._bridge = bridge
        self.monotonic = monotonic
        self.position: int | None = None
        self.rows = 0
        self.want_vectors = False
        self.vector_position: int | None = None
        self.vector_rows = 0

    def bridge(self):
        if self._bridge is not None:
            return self._bridge
        from ..android.bridge import require

        return require("the sound model")

    def gap(self) -> None:
        return None

    def take_vectors(self) -> list:
        if not self.want_vectors:
            self.vector_position = None
            return []
        try:
            reader = getattr(self.bridge(), "soundVectors", None)
            if reader is None:
                return []
            if self.vector_position is None:
                data = json.loads(str(reader(1 << 62)) or "{}")
                self.vector_position = max(0, int(data.get("total") or 0) - KEEP_VECTORS)
            data = json.loads(str(reader(self.vector_position)) or "{}")
        except Exception as error:
            log.debug("hearing: no sound vectors: %s", error)
            return []
        self.vector_position = int(data.get("total") or self.vector_position or 0)
        now_ms = data.get("now_ms")
        mono = self.monotonic()
        out = []
        for row in data.get("rows") or []:
            if not isinstance(row, list) or len(row) != 2:
                continue
            vector = unpack_vector(row[1])
            if vector is None:
                continue
            age = (float(now_ms) - float(row[0])) / 1000.0 if now_ms is not None else 0.0
            out.append((mono - max(0.0, age), vector))
        self.vector_rows += len(out)
        return out

    def feed(self, block: Block | None = None) -> list[tuple[float, list[float]]]:
        try:
            data = json.loads(str(self.bridge().soundScores(1 << 62 if self.position is None else self.position)) or "{}")
        except Exception as error:
            log.debug("hearing: no sound scores: %s", error)
            return []
        total = int(data.get("total") or 0)
        if self.position is None:
            self.position = total
            return []
        self.position = total
        now_ms = data.get("now_ms")
        mono = self.monotonic()
        out = []
        for row in data.get("rows") or []:
            if not isinstance(row, list) or len(row) != 2 or not isinstance(row[1], list) or len(row[1]) != len(self.labels):
                continue
            age = (float(now_ms) - float(row[0])) / 1000.0 if now_ms is not None else 0.0
            out.append((mono - max(0.0, age), [float(v) for v in row[1]]))
        self.rows += len(out)
        return out

    def status(self) -> dict:
        return {"kind": "phone", "rows": self.rows, "vectors": self.vector_rows}


def unpack_vector(value) -> list[float] | None:
    if isinstance(value, list):
        if len(value) != EMBEDDING:
            return None
        try:
            return [float(v) for v in value]
        except (TypeError, ValueError):
            return None
    if isinstance(value, str) and value.startswith("f16:"):
        try:
            raw = base64.b64decode(value[4:], validate=True)
        except (ValueError, binascii.Error):
            return None
        if len(raw) != 2 * EMBEDDING:
            return None
        return [v[0] for v in struct.iter_unpack("<e", raw)]
    return None
