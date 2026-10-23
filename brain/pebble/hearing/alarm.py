import math
from dataclasses import dataclass, field

from .audio import FULL_SCALE, RATE, SILENT_DB, Block, decibels
from .chirp import ChirpWatch

WINDOW = 160
HOP = 320
FRAME_S = HOP / RATE
LOW_HZ = 2400.0
HIGH_HZ = 4600.0
STEP_HZ = RATE / WINDOW
FREQS = tuple(LOW_HZ + STEP_HZ * i for i in range(int(round((HIGH_HZ - LOW_HZ) / STEP_HZ)) + 1))
PROMINENCE = 10.0
ABOVE_FLOOR = 8.0
MIN_DB = -92.0
FLOOR_DOWN = 0.15
FLOOR_UP = 0.02
FLOOR_CREEP = 0.0005
MAX_MISSES = 2
MAX_PEAKS = 3
SAME_BIN = 2
MIN_FRAMES = 2
KEEP_S = 45.0

T3_ON = (0.3, 0.85)
T3_SPACING = (0.75, 1.3)
T3_QUIET = 1.0
T3_PERIOD = (3.4, 4.6)
T3_EVEN = 0.2
T4_ON = (0.05, 0.28)
T4_SPACING = (0.12, 0.5)
T4_QUIET = 2.0
T4_PERIOD = (3.5, 8.5)
T4_EVEN = 0.08
STEADY_COUNT = 8
STEADY_SPACING = (0.25, 2.0)
STEADY_SPREAD = 0.15
STEADY_MIN_S = 0.08
SIGNIFICANT = 0.6
GROUP_HZ = 200.0
NEIGHBOUR_HZ = 100.0
DRIFT_HZ = 600.0
CONFIDENCE = {1: 0.5, 2: 0.9}
SURE = 0.97
STEADY_CONFIDENCE = 0.45


def _window() -> list[float]:
    return [0.5 - 0.5 * math.cos(2.0 * math.pi * (n + 0.5) / WINDOW) for n in range(WINDOW)]


def _tables() -> tuple[list[list[float]], float]:
    w = _window()
    gain = sum(w)
    rows = []
    for freq in FREQS:
        step = 2.0 * math.pi * freq / RATE
        rows.append([w[n] * math.cos(step * n) for n in range(WINDOW)])
        rows.append([w[n] * math.sin(step * n) for n in range(WINDOW)])
    return rows, gain


class PlainEngine:
    name = "plain"

    def __init__(self):
        self.rows, gain = _tables()
        self.scale = (2.0 / (gain * FULL_SCALE)) ** 2
        self.sumprod = getattr(math, "sumprod", None) or (lambda a, b: sum(x * y for x, y in zip(a, b)))

    def powers(self, frames: list[list[float]]) -> list[list[float]]:
        out = []
        sp = self.sumprod
        rows = self.rows
        scale = self.scale
        for frame in frames:
            values = [sp(frame, row) for row in rows]
            out.append([(values[i] * values[i] + values[i + 1] * values[i + 1]) * scale for i in range(0, len(values), 2)])
        return out


class NumpyEngine:
    name = "numpy"

    def __init__(self):
        import numpy

        self.np = numpy
        rows, gain = _tables()
        self.table = numpy.array(rows, dtype=numpy.float64).T
        self.scale = (2.0 / (gain * FULL_SCALE)) ** 2

    def powers(self, frames: list[list[float]]) -> list[list[float]]:
        if not frames:
            return []
        np = self.np
        values = np.asarray(frames, dtype=np.float64) @ self.table
        power = (values[:, 0::2] ** 2 + values[:, 1::2] ** 2) * self.scale
        return power.tolist()


def engine_for(name: str = "auto"):
    if name in ("auto", "numpy"):
        try:
            return NumpyEngine()
        except ImportError:
            if name == "numpy":
                raise
    return PlainEngine()


@dataclass(frozen=True)
class Peak:
    bin: int
    freq: float
    level_db: float
    prominence_db: float
    rise_db: float = 60.0


@dataclass(frozen=True)
class Frame:
    at: float
    peaks: tuple

    @property
    def on(self) -> bool:
        return bool(self.peaks)


@dataclass(frozen=True)
class Beep:
    onset: float
    end: float
    freq: float
    level_db: float
    rise_db: float = 60.0
    prominence_db: float = 60.0

    @property
    def duration(self) -> float:
        return self.end - self.onset


@dataclass(frozen=True)
class AlarmHeard:
    kind: str
    confidence: float
    freq: float
    level_db: float
    groups: int
    at: float
    pattern: str

    def text(self) -> str:
        what = {"smoke_alarm": "a smoke alarm's beeping (three beeps, a pause)", "co_alarm": "a carbon monoxide alarm's beeping (four quick beeps, a long pause)", "alarm_beeping": "steady high beeping, like an older alarm"}[self.kind]
        sure = "sure" if self.confidence >= 0.85 else ("fairly sure" if self.confidence >= 0.6 else "not sure yet")
        return f"heard {what}, {sure}, at about {round(self.freq / 100) / 10:g} kHz"


@dataclass
class _Run:
    onset: float
    last: float
    bins: list = field(default_factory=list)
    freqs: list = field(default_factory=list)
    levels: list = field(default_factory=list)
    rises: list = field(default_factory=list)
    prominences: list = field(default_factory=list)
    misses: int = 0


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    count = len(ordered)
    if not count:
        return 0.0
    middle = count // 2
    return ordered[middle] if count % 2 else 0.5 * (ordered[middle - 1] + ordered[middle])


def _refine(powers: list[float], k: int) -> float:
    if 0 < k < len(powers) - 1 and powers[k - 1] > 0 and powers[k] > 0 and powers[k + 1] > 0:
        a, b, c = (math.log(powers[k - 1]), math.log(powers[k]), math.log(powers[k + 1]))
        denominator = a - 2.0 * b + c
        if denominator < 0:
            return FREQS[k] + STEP_HZ * max(-0.5, min(0.5, 0.5 * (a - c) / denominator))
    return FREQS[k]


class ToneFrames:
    def __init__(self, engine="auto"):
        self.engine = engine if hasattr(engine, "powers") else engine_for(engine)
        self.floor: list[float] | None = None
        self.carry: list[int] = []
        self.carry_end: float | None = None

    def reset(self) -> None:
        self.carry = []
        self.carry_end = None

    def feed(self, block: Block) -> list[Frame]:
        if block.skipped:
            self.reset()
        samples = self.carry + list(block.samples)
        count = len(samples) // HOP
        start = block.end - len(samples) / RATE
        frames = [list(map(float, samples[i * HOP : i * HOP + WINDOW])) for i in range(count)]
        self.carry = samples[count * HOP :]
        powers = self.engine.powers(frames)
        out = []
        for index, power in enumerate(powers):
            out.append(self._judge(start + (index * HOP + WINDOW) / RATE, power))
        return out

    def _judge(self, at: float, power: list[float]) -> Frame:
        if self.floor is None:
            self.floor = list(power)
        floor = self.floor
        median = _median(power)
        last = len(power) - 1
        peaks = []
        for k, value in enumerate(power):
            if k > 0 and power[k - 1] > value or k < last and power[k + 1] > value:
                continue
            level = decibels(value)
            if level < MIN_DB or value < PROMINENCE * median or value < ABOVE_FLOOR * floor[k]:
                continue
            peaks.append(Peak(k, _refine(power, k), level, decibels(value / median) if median > 0 else 60.0, decibels(value / floor[k]) if floor[k] > 0 else 60.0))
        peaks.sort(key=lambda peak: -peak.level_db)
        for i, value in enumerate(power):
            if value < floor[i]:
                floor[i] += FLOOR_DOWN * (value - floor[i])
            elif value < 4.0 * floor[i]:
                floor[i] += FLOOR_UP * (value - floor[i])
            else:
                floor[i] += FLOOR_CREEP * (value - floor[i])
        return Frame(at, tuple(peaks[:MAX_PEAKS]))


class BeepTracker:
    def __init__(self):
        self.runs: list[_Run] = []

    def reset(self) -> list[Beep]:
        runs, self.runs = self.runs, []
        return [beep for run in runs for beep in _finish(run)]

    def feed(self, frames: list[Frame]) -> list[Beep]:
        beeps = []
        for frame in frames:
            used = set()
            for peak in frame.peaks:
                run = next((r for r in self.runs if id(r) not in used and abs(peak.bin - _median(r.bins)) <= SAME_BIN), None)
                if run is None:
                    run = _Run(frame.at - FRAME_S, frame.at)
                    self.runs.append(run)
                run.last = frame.at
                run.bins.append(peak.bin)
                run.freqs.append(peak.freq)
                run.levels.append(peak.level_db)
                run.rises.append(peak.rise_db)
                run.prominences.append(peak.prominence_db)
                run.misses = 0
                used.add(id(run))
            kept = []
            for run in self.runs:
                if id(run) not in used:
                    run.misses += 1
                    if run.misses > MAX_MISSES:
                        beeps.extend(_finish(run))
                        continue
                kept.append(run)
            self.runs = kept
        beeps.sort(key=lambda beep: beep.onset)
        return beeps


def _finish(run: _Run) -> list[Beep]:
    if len(run.bins) < MIN_FRAMES:
        return []
    return [Beep(run.onset, run.last, _median(run.freqs), _median(run.levels), _median(run.rises) if run.rises else 60.0, _median(run.prominences) if run.prominences else 60.0)]


def _within(value: float, bounds: tuple[float, float]) -> bool:
    return bounds[0] <= value <= bounds[1]


@dataclass(frozen=True)
class Group:
    kind: str
    onset: float
    end: float
    freq: float
    level_db: float
    beeps: int


def _significant(beep: Beep, on: tuple) -> bool:
    return beep.duration >= SIGNIFICANT * on[0]


def _runs(beeps: list[Beep], on: tuple, spacing: tuple) -> list[list[Beep]]:
    done: list[list[Beep]] = []
    open_runs: list[list[Beep]] = []
    for beep in beeps:
        if not _significant(beep, on):
            continue
        same = [run for run in open_runs if abs(beep.freq - run[-1].freq) <= GROUP_HZ]
        fits = _within(beep.duration, on)
        target = next((run for run in same if fits and _within(beep.onset - run[-1].onset, spacing)), None)
        for run in same:
            if run is not target:
                open_runs.remove(run)
                done.append(run)
        if target is not None:
            target.append(beep)
        elif fits:
            open_runs.append([beep])
    return sorted(done + open_runs, key=lambda run: run[0].onset)


def _neighbours(beeps: list[Beep], run: list[Beep], on: tuple) -> tuple[Beep | None, Beep | None]:
    before = [b for b in beeps if b.end <= run[0].onset and abs(b.freq - run[0].freq) <= NEIGHBOUR_HZ and _significant(b, on)]
    after = [b for b in beeps if b.onset >= run[-1].end and abs(b.freq - run[-1].freq) <= NEIGHBOUR_HZ and _significant(b, on)]
    return (before[-1] if before else None), (after[0] if after else None)


def find_groups(beeps: list[Beep], now: float, kind: str) -> list[Group]:
    if kind == "smoke_alarm":
        on, spacing, size, quiet, even = T3_ON, T3_SPACING, 3, T3_QUIET, T3_EVEN
    else:
        on, spacing, size, quiet, even = T4_ON, T4_SPACING, 4, T4_QUIET, T4_EVEN
    groups = []
    for run in _runs(beeps, on, spacing):
        if len(run) != size:
            continue
        gaps = [b.onset - a.onset for a, b in zip(run, run[1:])]
        lengths = [b.duration for b in run]
        if max(gaps) - min(gaps) > even or max(lengths) - min(lengths) > even:
            continue
        before, after = _neighbours(beeps, run, on)
        if before is not None and run[0].onset - before.end < quiet:
            continue
        if after is not None and after.onset - run[-1].end < quiet:
            continue
        if after is None and now - run[-1].end < quiet:
            continue
        groups.append(Group(kind, run[0].onset, run[-1].end, _median([b.freq for b in run]), _median([b.level_db for b in run]), size))
    return groups


def _repeats(groups: list[Group], period: tuple[float, float], most: int) -> int:
    if not groups:
        return 0
    chain = [groups[-1]]
    for other in reversed(groups[:-1]):
        newer = chain[-1]
        gap = newer.onset - other.onset
        if abs(other.freq - newer.freq) > DRIFT_HZ:
            continue
        if any(_within(gap / n, period) for n in range(1, most + 1)):
            chain.append(other)
    return len(chain)


def steady(beeps: list[Beep], now: float) -> Beep | None:
    long = [b for b in beeps if b.duration >= STEADY_MIN_S]
    if not long:
        return None
    latest = long[-1]
    tail: list[Beep] = []
    for beep in reversed([b for b in long if abs(b.freq - latest.freq) <= GROUP_HZ]):
        if tail and not _within(tail[-1].onset - beep.onset, STEADY_SPACING):
            break
        tail.append(beep)
    if len(tail) < STEADY_COUNT or now - tail[0].end > STEADY_SPACING[1]:
        return None
    gaps = [a.onset - b.onset for a, b in zip(tail, tail[1:])]
    mean = sum(gaps) / len(gaps)
    spread = math.sqrt(sum((g - mean) ** 2 for g in gaps) / len(gaps))
    durations = [b.duration for b in tail]
    if spread > STEADY_SPREAD * mean or max(durations) - min(durations) > 0.25 * mean:
        return None
    return tail[0]


class PatternMatcher:
    def __init__(self, keep_s: float = KEEP_S):
        self.keep_s = keep_s
        self.beeps: list[Beep] = []
        self.reported: dict[str, float] = {}
        self.dirty = False

    def add(self, beeps: list[Beep]) -> None:
        if beeps:
            self.beeps.extend(beeps)
            self.beeps.sort(key=lambda beep: beep.onset)
            self.dirty = True

    def check(self, now: float) -> list[AlarmHeard]:
        recent = bool(self.beeps) and now - max(b.end for b in self.beeps[-8:]) <= T4_QUIET + 1.0
        if not self.dirty and not recent:
            return []
        self.dirty = False
        self.beeps = [b for b in self.beeps if now - b.end <= self.keep_s]
        heard = []
        matched = False
        for kind, period, most in (("smoke_alarm", T3_PERIOD, 3), ("co_alarm", T4_PERIOD, 2)):
            groups = find_groups(self.beeps, now, kind)
            if not groups:
                continue
            matched = True
            last = groups[-1]
            if self.reported.get(kind, -math.inf) >= last.onset:
                continue
            self.reported[kind] = last.onset
            repeats = _repeats(groups, period, most)
            confidence = CONFIDENCE.get(repeats, SURE)
            heard.append(AlarmHeard(kind, confidence, last.freq, last.level_db, repeats, last.end, "T3" if kind == "smoke_alarm" else "T4"))
        if not matched:
            first = steady(self.beeps, now)
            if first is not None and self.reported.get("alarm_beeping", -math.inf) < now - 10.0:
                self.reported["alarm_beeping"] = now
                last = self.beeps[-1]
                heard.append(AlarmHeard("alarm_beeping", STEADY_CONFIDENCE, last.freq, last.level_db, 1, last.end, "steady"))
        return heard


class AlarmDetector:
    def __init__(self, engine="auto"):
        self.frames = ToneFrames(engine)
        self.tracker = BeepTracker()
        self.matcher = PatternMatcher()
        self.chirps = ChirpWatch()
        self.new_chirps: list = []
        self.processed_s = 0.0
        self.last: dict[str, AlarmHeard] = {}

    @property
    def engine(self) -> str:
        return self.frames.engine.name

    def feed(self, block: Block) -> list[AlarmHeard]:
        if block.skipped:
            self._cut(block.start)
        frames = self.frames.feed(block)
        self.processed_s += block.seconds
        beeps = self.tracker.feed(frames)
        self.matcher.add(beeps)
        self.chirps.add(beeps)
        heard = self.matcher.check(block.end)
        self.new_chirps.extend(self.chirps.check(block.end))
        for item in heard:
            self.last[item.kind] = item
        return heard

    def take_chirps(self) -> list:
        found, self.new_chirps = self.new_chirps, []
        return found

    def _cut(self, at: float) -> None:
        cut = self.tracker.reset()
        self.matcher.add(cut)
        self.chirps.add(cut)
        self.chirps.gap(at)

    def gap(self, now: float) -> None:
        self.frames.reset()
        self._cut(now)

    def last_heard(self, kind: str) -> float | None:
        item = self.last.get(kind)
        return None if item is None else item.at

    def status(self) -> dict:
        return {
            "engine": self.engine,
            "seconds": round(self.processed_s, 1),
            "beeps": len(self.matcher.beeps),
            "chirps": self.chirps.status(),
            "last": {kind: {"confidence": h.confidence, "freq": round(h.freq), "at": round(h.at, 1)} for kind, h in self.last.items()},
        }
