import json
import logging
import math
from collections import deque
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

BIN_HZ = 46.875
LOW_HZ = 15_000.0
MAX_TOP_HZ = 24_000.0
BAND_HZ = 1_000.0
SILENT_DB = -160.0
MIN_DB = -110.0
PROMINENCE_DB = 6.0
STAND_OUT_DB = 10.0
NEIGHBOUR_NEAR = 3
NEIGHBOUR_FAR = 6
MAX_PEAKS = 8
MATCH_HZ = 190.0
PENDING_MATCH_HZ = 94.0
DROP_DB = 20.0
STEP_HZ = 12.0
MIN_FRAMES = 3
START_S = 0.25
GAP_FRAMES = 5
NOISE_FAR = 12
SHARP_DB = 6.0
WARM_FRAMES = 47
WARM_RATE = 0.1
MEAN_RATE = 0.02
OUTLIER = 4.0
CREEP = 0.002
FAST_RATE = 0.3
SETTLE_S = 0.5
JUMP_FRAMES = 3
STEADY_S = 10.0
STEADY_SPREAD_HZ = 100.0
SWEEP_HZ = 300.0
SWEEP_SHARE = 0.7
SAME_PITCH_HZ = 50.0
PULSES = 4
PULSE_MIN_S = 0.1
PULSE_MAX_S = 10.0
PULSE_SPREAD = 0.2
PATTERN_KEEP_S = 60.0
BEACON_LOW_HZ = 18_000.0
BEACON_HIGH_HZ = 20_000.0
BEACON_MAX_S = 1.0
DATA_HIGH_HZ = 19_500.0
DATA_TONES = 3
DATA_BINS = 6
DATA_GAP_S = 0.15
DATA_MIN_S = 0.1
MOTOR_HZ = 20_000.0
MOTOR_SPREAD_HZ = 150.0
LEVELS_EVERY_S = 1.0
KEEP = 300
NEWEST = 1 << 62

SAME_TONE_HZ = 75.0
BREAK_S = 60.0
NEW_AFTER_S = 600.0
DATA_KEEP_S = 3600.0
DATA_SURE_S = 1.0
DATA_AGAIN_S = 600.0
BLIP_S = 1.0
DAY_S = 86400.0
FORGET_S = 30 * DAY_S
OWN_ROOMS = 2
OWN_LEVEL_DB = 6.0
RECENT_S = 30.0
KNOWN_CAP = 40
ROOMS_CAP = 8
AUDIBLE_TOP_HZ = 20_000.0
TOLD_SHAPES = ("steady", "pulsing")


def _round(value: float, places: int = 0) -> float:
    scale = 10.0 ** places
    return math.floor(value * scale + 0.5) / scale


def _median(values) -> float:
    if not len(values):
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0


def khz(hz: float) -> str:
    return f"{int(_round(hz / 1000.0))}"


class _Tone:
    __slots__ = ("hz", "start", "last", "frames", "misses", "level_sum", "over_sum", "rise_sum", "strong", "lowest", "highest", "ups", "downs", "told", "steady_told", "own", "in_data")

    def __init__(self, hz: float, start: float):
        self.hz = hz
        self.start = start
        self.last = start
        self.frames = 0
        self.misses = 0
        self.level_sum = 0.0
        self.over_sum = 0.0
        self.rise_sum = 0.0
        self.strong = 0
        self.lowest = hz
        self.highest = hz
        self.ups = 0
        self.downs = 0
        self.told = False
        self.steady_told = False
        self.own = False
        self.in_data = False


class Watcher:
    def __init__(self, now_ms=None):
        import numpy

        self.np = numpy
        self.now_ms = now_ms or (lambda: 0.0)
        self.rate = 0
        self.size = 0
        self.window = None
        self.frame = None
        self.filled = 0
        self.mean = None
        self.unsettled_until = 0.0
        self.louder = 0
        self.first = 0
        self.last = 0
        self.norm = 1.0
        self.seconds = 0.0
        self.tones: list[_Tone] = []
        self.ended: deque = deque()
        self.data_since = -1.0
        self.data_on = False
        self.data_seen = -1.0
        self.data_bins: set = set()
        self.data_hz: list = []
        self.band_sums: list = []
        self.band_frames = 0
        self.band_start = 0.0
        self.rows: deque = deque()
        self.total = 0
        self.top_hz = MAX_TOP_HZ
        self.moving = False
        self.problem = "the high band needs a 48 or 96 kHz feed, and the microphone runs at 16 kHz"
        self.looks = 0

    @property
    def on(self) -> bool:
        return self.size > 0 and not self.problem

    def feed(self, samples, rate: int, channels: int = 1, speaking: bool = False) -> None:
        np = self.np
        if rate != self.rate:
            self._set_up(rate)
        if not self.size:
            return
        values = np.asarray(samples)
        if channels > 1:
            values = values[::channels]
        values = values.astype(np.float64) / 32768.0 if values.dtype.kind in "iu" else values.astype(np.float64)
        stamp = float(self.now_ms())
        count = len(values)
        index = 0
        while index < count:
            take = min(self.size - self.filled, count - index)
            self.frame[self.filled : self.filled + take] = values[index : index + take]
            self.filled += take
            index += take
            if self.filled == self.size:
                self.filled = 0
                self.seconds += self.size / rate
                if not speaking:
                    self._look(stamp - (count - index) * 1000.0 / rate)

    def _set_up(self, rate: int) -> None:
        np = self.np
        self.rate = rate
        self.tones = []
        self.ended.clear()
        self.filled = 0
        size = 1 << (max(2, int(_round(rate / BIN_HZ))).bit_length() - 1)
        if rate / 2.0 <= LOW_HZ + 8 * BIN_HZ or abs(rate / size - BIN_HZ) > 1.0:
            self.size = 0
            self.problem = f"the high band needs a 48 or 96 kHz feed, not {rate / 1000.0:g} kHz"
            return
        self.size = size
        self.window = 0.5 - 0.5 * np.cos(2.0 * np.pi * (np.arange(size) + 0.5) / size)
        self.norm = (float(self.window.sum()) / 2.0) ** 2
        self.frame = np.zeros(size)
        self.first = int(math.ceil(LOW_HZ / BIN_HZ))
        self.last = min(size // 2 - 3, int(math.floor(min(self.top_hz, rate / 2.0) / BIN_HZ)) - 1)
        self.mean = np.full(size // 2, -1.0)
        self.looks = 0
        self.band_sums = [0.0] * self._bands()
        self.band_frames = 0
        self.problem = f"this phone's microphone path stops at {_round(self.top_hz / 100.0) / 10.0:g} kHz, so the high band is off" if self.last - self.first < 8 else ""

    def _bands(self) -> int:
        return max(0, int(math.floor((self.last * BIN_HZ - LOW_HZ) / BAND_HZ)))

    def _db(self, power: float) -> float:
        return 10.0 * math.log10(power / self.norm) if power > 0 else SILENT_DB

    def _look(self, at: float) -> None:
        if self.last - self.first < 8:
            return
        np = self.np
        self.looks += 1
        spectrum = np.fft.rfft(self.frame * self.window)
        power = (spectrum.real ** 2 + spectrum.imag ** 2)[: self.size // 2]
        mean = self.mean
        first, last = self.first, self.last
        low_bin = max(1, first - NOISE_FAR)
        high_bin = min(len(power) - 1, last + NOISE_FAR)
        span = slice(low_bin, high_bin + 1)
        mean[span] = np.where(mean[span] < 0, power[span], mean[span])
        now = float(np.median(power[first : last + 1]))
        usual = float(np.median(mean[first : last + 1]))
        self.louder = self.louder + 1 if self.looks > WARM_FRAMES and now > OUTLIER * usual else 0
        jumped = self.louder >= JUMP_FRAMES
        if jumped:
            self.unsettled_until = at + SETTLE_S * 1000.0
        if self.louder == JUMP_FRAMES:
            self.tones = [t for t in self.tones if t.told]
        settling = at < self.unsettled_until
        peaks = self._peaks(power, low_bin, high_bin)
        peaks.sort(key=lambda p: -p[1])
        kept = peaks[:MAX_PEAKS]
        self._data([] if settling else kept, at)
        self._track(kept, at, not settling)
        speed = WARM_RATE if self.looks <= WARM_FRAMES else (FAST_RATE if jumped or settling else MEAN_RATE)
        part = power[span]
        before = mean[span]
        quick = self.looks <= WARM_FRAMES or jumped or settling
        rates = np.where(quick | (part < OUTLIER * before), speed, CREEP)
        mean[span] = before + rates * (part - before)
        self._levels(power, at)

    def _peaks(self, power, low_bin: int, high_bin: int) -> list:
        np = self.np
        first = self.first
        last = min(self.last, len(power) - 1 - NEIGHBOUR_FAR)
        if last < first:
            return []
        ks = np.arange(first, last + 1)
        p = power[first : last + 1]
        floor_power = self.norm * 10.0 ** (MIN_DB / 10.0)
        candidates = ks[(p >= power[ks - 1]) & (p >= power[ks + 1]) & (p >= floor_power) & (p > 0)]
        out = []
        mean = self.mean
        for k in candidates:
            k = int(k)
            level = self._db(float(power[k]))
            if level < MIN_DB:
                continue
            near = [float(power[k - d]) for d in range(NEIGHBOUR_NEAR, NEIGHBOUR_FAR + 1)] + [float(power[k + d]) for d in range(NEIGHBOUR_NEAR, NEIGHBOUR_FAR + 1)]
            around = _median(near)
            if level - self._db(around) < SHARP_DB:
                continue
            far = []
            for d in range(NEIGHBOUR_NEAR, NOISE_FAR + 1):
                if k - d >= low_bin:
                    far.append(float(mean[k - d]))
                if k + d <= high_bin:
                    far.append(float(mean[k + d]))
            over = level - self._db(max(_median(far), around))
            if over < PROMINENCE_DB:
                continue
            a = self._db(float(power[k - 1]))
            c = self._db(float(power[k + 1]))
            bend = a - 2.0 * level + c
            shift = max(-0.5, min(0.5, 0.5 * (a - c) / bend)) if bend < 0 else 0.0
            out.append([(k + shift) * BIN_HZ, level, level - self._db(float(mean[k])), over, k])
        return out

    def _track(self, peaks: list, at: float, fresh: bool) -> None:
        free = list(peaks)
        for tone in sorted(self.tones, key=lambda t: -t.frames):
            need = PROMINENCE_DB if tone.told else STAND_OUT_DB
            reach = MATCH_HZ if tone.told else PENDING_MATCH_HZ
            floor = tone.level_sum / tone.frames - DROP_DB
            fits = [p for p in free if p[3] >= need and p[1] >= floor and abs(p[0] - tone.hz) <= reach]
            if not fits:
                tone.misses += 1
                continue
            best = max(fits, key=lambda p: p[1])
            free.remove(best)
            step = best[0] - tone.hz
            if step > STEP_HZ:
                tone.ups += 1
            elif step < -STEP_HZ:
                tone.downs += 1
            tone.hz = best[0]
            tone.last = at
            tone.frames += 1
            tone.misses = 0
            tone.level_sum += best[1]
            tone.over_sum += best[3]
            tone.rise_sum += best[2]
            if best[3] >= STAND_OUT_DB:
                tone.strong += 1
            tone.lowest = min(tone.lowest, best[0])
            tone.highest = max(tone.highest, best[0])
            if self.moving and abs(best[0] - MOTOR_HZ) <= MOTOR_SPREAD_HZ:
                tone.own = True
            if not tone.told and not tone.in_data and tone.strong >= MIN_FRAMES and (at - tone.start) / 1000.0 >= START_S:
                tone.told = True
                self._keep(self._row(tone, "start", at))
            if not tone.steady_told and tone.told and (at - tone.start) / 1000.0 >= STEADY_S and tone.highest - tone.lowest <= STEADY_SPREAD_HZ:
                tone.steady_told = True
                self._keep(self._row(tone, "steady", at))
        gone = [t for t in self.tones if t.misses > GAP_FRAMES]
        for tone in gone:
            self.tones.remove(tone)
            if tone.strong < MIN_FRAMES:
                continue
            if tone.told or (not tone.in_data and not self.data_on):
                self._keep(self._row(tone, "end", at))
            self.ended.append((tone.start, tone.last, (tone.lowest + tone.highest) / 2.0))
        while self.ended and at - self.ended[0][1] > PATTERN_KEEP_S * 1000.0:
            self.ended.popleft()
        for peak in free:
            if not fresh or peak[3] < STAND_OUT_DB:
                continue
            tone = _Tone(peak[0], at)
            tone.frames = 1
            tone.level_sum = peak[1]
            tone.over_sum = peak[3]
            tone.rise_sum = peak[2]
            tone.strong = 1
            if self.moving and abs(peak[0] - MOTOR_HZ) <= MOTOR_SPREAD_HZ:
                tone.own = True
            tone.in_data = self.data_on
            self.tones.append(tone)

    def _shape(self, tone: _Tone, ended: bool) -> tuple[str, tuple | None]:
        length = (tone.last - tone.start) / 1000.0
        moves = tone.ups + tone.downs
        if tone.highest - tone.lowest >= SWEEP_HZ and moves >= 3 and max(tone.ups, tone.downs) >= SWEEP_SHARE * moves:
            return "sweeping", None
        if length >= STEADY_S and tone.highest - tone.lowest <= STEADY_SPREAD_HZ:
            return "steady", None
        middle = (tone.lowest + tone.highest) / 2.0
        same = [start for start, _, hz in self.ended if abs(hz - middle) <= SAME_PITCH_HZ] + [tone.start]
        if len(same) >= PULSES:
            ordered = sorted(same)
            gaps = [(b - a) / 1000.0 for a, b in zip(ordered, ordered[1:])][-(PULSES - 1) :]
            mean = sum(gaps) / len(gaps)
            spread = math.sqrt(sum((g - mean) ** 2 for g in gaps) / len(gaps))
            if PULSE_MIN_S <= mean <= PULSE_MAX_S and spread <= PULSE_SPREAD * mean:
                return "pulsing", (mean, 1.0 - spread / mean)
        if ended and length < BEACON_MAX_S and tone.lowest >= BEACON_LOW_HZ and tone.highest <= BEACON_HIGH_HZ:
            return "beacon", None
        return "tone", None

    def _row(self, tone: _Tone, what: str, at: float) -> dict:
        kind, rhythm = self._shape(tone, what == "end")
        end = what == "end"
        return {
            "t": _round(at, 1),
            "kind": "tone",
            "what": what,
            "hz": int(_round((tone.lowest + tone.highest) / 2.0 if end else tone.hz)),
            "low_hz": int(_round(tone.lowest)),
            "high_hz": int(_round(tone.highest)),
            "start": _round(tone.start, 1),
            "end": _round(tone.last, 1) if end else None,
            "level_db": _round(tone.level_sum / tone.frames, 1),
            "over_db": _round(tone.over_sum / tone.frames, 1),
            "rise_db": _round(tone.rise_sum / tone.frames, 1),
            "shape": kind,
            "period_s": _round(rhythm[0], 2) if rhythm else None,
            "regular": _round(rhythm[1], 2) if rhythm else None,
            "own": tone.own,
        }

    def _data(self, peaks: list, at: float) -> None:
        strong = [p for p in peaks if LOW_HZ <= p[0] <= DATA_HIGH_HZ and p[3] >= STAND_OUT_DB]
        if len(strong) >= DATA_TONES:
            if self.data_since < 0:
                self.data_since = at
                self.data_on = False
                self.data_bins = set()
                self.data_hz = []
            self.data_seen = at
            for p in strong:
                self.data_bins.add(int(p[4]))
                self.data_hz.append(p[0])
            if not self.data_on and (at - self.data_since) / 1000.0 >= DATA_MIN_S and len(self.data_bins) >= DATA_BINS:
                self.data_on = True
                for tone in self.tones:
                    if not tone.told:
                        tone.in_data = True
            return
        if self.data_since >= 0 and at - self.data_seen > DATA_GAP_S * 1000.0:
            if self.data_on:
                ordered = sorted(self.data_hz)
                self._keep({
                    "t": _round(at, 1),
                    "kind": "tone",
                    "what": "end",
                    "hz": int(_round(ordered[len(ordered) // 2])),
                    "low_hz": int(_round(ordered[0])),
                    "high_hz": int(_round(ordered[-1])),
                    "start": _round(self.data_since, 1),
                    "end": _round(self.data_seen, 1),
                    "level_db": None,
                    "over_db": None,
                    "rise_db": None,
                    "shape": "data",
                    "tones": len(self.data_bins),
                    "own": False,
                })
                self.tones = [t for t in self.tones if not t.in_data]
            self.data_since = -1.0
            self.data_on = False

    def _levels(self, power, at: float) -> None:
        if not self.band_sums:
            return
        if self.band_frames == 0:
            self.band_start = at
        for b in range(len(self.band_sums)):
            low = int(math.ceil((LOW_HZ + b * BAND_HZ) / BIN_HZ))
            high = int(math.floor((LOW_HZ + (b + 1) * BAND_HZ) / BIN_HZ)) - 1
            self.band_sums[b] += float(power[low : high + 1].sum()) / max(1, high - low + 1)
        self.band_frames += 1
        if at - self.band_start >= LEVELS_EVERY_S * 1000.0:
            levels = [_round(self._db(total / self.band_frames), 1) for total in self.band_sums]
            self._keep({"t": _round(at, 1), "kind": "levels", "from_hz": int(LOW_HZ), "step_hz": int(BAND_HZ), "db": levels})
            self.band_sums = [0.0] * len(self.band_sums)
            self.band_frames = 0

    def _keep(self, row: dict) -> None:
        self.rows.append(row)
        while len(self.rows) > KEEP:
            self.rows.popleft()
        self.total += 1

    def read(self, start: int) -> dict:
        oldest = self.total - len(self.rows)
        begin = max(oldest, min(int(start), self.total))
        return {
            "total": self.total,
            "from": begin,
            "rows": list(self.rows)[begin - oldest :],
            "now_ms": float(self.now_ms()),
            "on": self.on,
            "rate": self.rate,
            "low_hz": int(LOW_HZ),
            "top_hz": int(_round((self.last + 1) * BIN_HZ)) if self.size else None,
            "open_tones": sum(1 for t in self.tones if t.told),
            "heard_s": _round(self.seconds, 1),
            "problem": self.problem,
        }

    def top(self, hz: float) -> None:
        self.top_hz = max(LOW_HZ, min(MAX_TOP_HZ, float(hz)))
        self.rate = 0

    def highBand(self, start: int) -> str:
        return json.dumps(self.read(start))

    def highBandMoving(self, on: bool) -> None:
        self.moving = bool(on)


@dataclass
class Heard:
    what: str
    hz: float
    low_hz: float
    high_hz: float
    start: float | None
    end: float | None
    at: float
    shape: str
    level_db: float | None = None
    period_s: float | None = None
    tones: int = 0
    key: float = 0.0


def heard_from(row, mono: float, now_ms) -> Heard | None:
    if not isinstance(row, dict) or row.get("kind") != "tone" or row.get("own"):
        return None
    try:
        hz = float(row["hz"])
        now = float(now_ms) if now_ms is not None else float(row.get("t") or 0.0)

        def ago(value) -> float | None:
            return None if value is None else mono - max(0.0, (now - float(value)) / 1000.0)

        level = row.get("level_db")
        period = row.get("period_s")
        return Heard(
            what=str(row.get("what") or ""),
            hz=hz,
            low_hz=float(row.get("low_hz", hz)),
            high_hz=float(row.get("high_hz", hz)),
            start=ago(row.get("start")),
            end=ago(row.get("end")),
            at=ago(row.get("t", now)),
            shape=str(row.get("shape") or "tone"),
            level_db=None if level is None else float(level),
            period_s=None if period is None else float(period),
            tones=int(row.get("tones") or 0),
            key=float(row.get("start") or 0.0),
        )
    except (KeyError, TypeError, ValueError):
        return None


class PhoneBand:
    def __init__(self, bridge=None):
        self._bridge = bridge
        self.position: int | None = None
        self.last: dict = {}
        self.moving_now: bool | None = None
        self.problem = ""
        self.rows = 0

    def bridge(self):
        if self._bridge is not None:
            return self._bridge
        from ..android.bridge import require

        return require("the high band")

    def take(self, mono: float) -> list[Heard]:
        try:
            data = json.loads(str(self.bridge().highBand(int(self.position or 0))) or "{}")
        except Exception as error:
            if str(error) != self.problem:
                log.debug("high band: no rows from the phone: %s", error)
            self.problem = str(error)
            return []
        if not isinstance(data, dict):
            return []
        self.problem = ""
        self.last = {k: v for k, v in data.items() if k != "rows"}
        self.position = int(data.get("total") or 0)
        now_ms = data.get("now_ms")
        out = [h for h in (heard_from(row, mono, now_ms) for row in data.get("rows") or []) if h is not None]
        self.rows += len(out)
        return out

    def on(self) -> bool:
        return bool(self.last.get("on"))

    def top_hz(self) -> float | None:
        top = self.last.get("top_hz")
        return float(top) if isinstance(top, (int, float)) and not isinstance(top, bool) else None

    def why_off(self) -> str:
        return str(self.last.get("problem") or self.problem)

    def moving(self, on: bool) -> None:
        on = bool(on)
        if on == self.moving_now:
            return
        try:
            self.bridge().highBandMoving(on)
            self.moving_now = on
        except Exception as error:
            log.debug("high band: the phone would not take moving: %s", error)

    def status(self) -> dict:
        return {"on": self.on(), "top_hz": self.top_hz(), "rows": self.rows, "problem": self.why_off()}


@dataclass
class Known:
    hz: float
    shape: str
    first: float
    last: float
    heard_s: float = 0.0
    told: float | None = None
    own: bool = False
    rooms: dict = field(default_factory=dict)
    period_s: float | None = None
    ends: int = 0
    since: float | None = None
    seen: float = -math.inf
    sounding: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "hz": round(self.hz),
            "shape": self.shape,
            "first": round(self.first),
            "last": round(self.last),
            "heard_s": round(self.heard_s, 1),
            "told": None if self.told is None else round(self.told),
            "own": self.own,
            "rooms": {room: round(level, 1) for room, level in self.rooms.items()},
            "period_s": self.period_s,
            "ends": self.ends,
        }

    @classmethod
    def from_dict(cls, data) -> "Known | None":
        try:
            rooms = data.get("rooms") or {}
            return cls(
                float(data["hz"]),
                str(data.get("shape") or "tone"),
                float(data["first"]),
                float(data["last"]),
                float(data.get("heard_s") or 0.0),
                None if data.get("told") is None else float(data["told"]),
                bool(data.get("own")),
                {str(room): float(level) for room, level in rooms.items()} if isinstance(rooms, dict) else {},
                None if data.get("period_s") is None else float(data["period_s"]),
                int(data.get("ends") or 0),
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            return None

    def gap(self) -> float:
        return BREAK_S if self.period_s is None else max(BREAK_S, 3.0 * self.period_s)


@dataclass(frozen=True)
class News:
    kind: str
    hz: float
    tone: Known | None = None
    room: str | None = None


class HighTones:
    def __init__(self, data: dict | None = None):
        data = data if isinstance(data, dict) else {}
        self.known: list[Known] = [k for k in (Known.from_dict(item) for item in data.get("tones") or []) if k is not None]
        self.data_told = data.get("data_told")
        self.data_waiting: tuple | None = None
        self.last_data: tuple | None = None
        self.data_bursts: deque = deque(maxlen=16)
        self.dirty = False

    def to_dict(self) -> dict:
        return {"format": 1, "tones": [k.to_dict() for k in self.known], "data_told": self.data_told}

    def find(self, hz: float) -> Known | None:
        near = [k for k in self.known if abs(k.hz - hz) <= SAME_TONE_HZ]
        return min(near, key=lambda k: abs(k.hz - hz)) if near else None

    def feed(self, rows: list[Heard], mono: float, wall: float, room: str | None = None) -> None:
        for heard in rows:
            if heard.shape == "data":
                if heard.what == "end":
                    self._data(heard, mono, room)
                continue
            self._tone(heard, wall, room)
            self.dirty = True

    def _data(self, heard: Heard, mono: float, room: str | None) -> None:
        lasted = (heard.end - heard.start) if heard.end is not None and heard.start is not None else 0.0
        while self.data_bursts and mono - self.data_bursts[0] > DATA_AGAIN_S:
            self.data_bursts.popleft()
        self.data_bursts.append(mono)
        if lasted < DATA_SURE_S and len(self.data_bursts) < 2:
            return
        self.data_waiting = (heard.hz, room, mono)
        self.last_data = (heard.hz, room, heard.at)

    def _tone(self, heard: Heard, wall: float, room: str | None) -> None:
        known = self.find(heard.hz)
        if known is None:
            known = Known(heard.hz, heard.shape, wall, wall)
            self.known.append(known)
            self._cap()
        known.last = wall
        if heard.shape != "tone":
            known.shape = heard.shape
        if heard.period_s:
            known.period_s = heard.period_s
        if room and heard.level_db is not None:
            known.rooms[room] = max(known.rooms.get(room, -math.inf), heard.level_db)
            while len(known.rooms) > ROOMS_CAP:
                known.rooms.pop(next(iter(known.rooms)))
            levels = list(known.rooms.values())
            if len(levels) >= OWN_ROOMS and max(levels) - min(levels) <= OWN_LEVEL_DB:
                known.own = True
        began = heard.start if heard.start is not None else heard.at
        if known.since is None or (not known.sounding and began - known.seen > known.gap()):
            known.since = began
        if heard.what == "end":
            known.sounding.pop(heard.key, None)
            known.ends += 1
            if heard.end is not None and heard.start is not None:
                known.heard_s += max(0.0, heard.end - heard.start)
            known.seen = max(known.seen, heard.end if heard.end is not None else heard.at)
        else:
            known.sounding[heard.key] = heard.at
            known.seen = max(known.seen, heard.at)

    def _cap(self) -> None:
        if len(self.known) <= KNOWN_CAP:
            return
        self.known.sort(key=lambda k: k.last)
        del self.known[: len(self.known) - KNOWN_CAP]

    def present(self, known: Known, mono: float) -> bool:
        return bool(known.sounding) or mono - known.seen <= known.gap()

    def lasted(self, known: Known, mono: float) -> float:
        if known.since is None or not self.present(known, mono):
            return 0.0
        return mono - known.since

    def news(self, mono: float, wall: float) -> list[News]:
        out = [News(k.shape, k.hz, k) for k in self.known if not k.own and k.told is None and k.shape in TOLD_SHAPES and self.lasted(k, mono) >= NEW_AFTER_S]
        waiting = self.data_waiting
        if waiting is not None and mono - waiting[2] > DATA_KEEP_S:
            self.data_waiting = waiting = None
        if waiting is not None and (self.data_told is None or wall - float(self.data_told) >= DAY_S):
            out.append(News("data", waiting[0], None, waiting[1]))
        return out

    def told(self, news: News, wall: float) -> None:
        if news.kind == "data":
            self.data_told = round(wall)
            self.data_waiting = None
        elif news.tone is not None:
            news.tone.told = wall
        self.dirty = True

    def real(self, known: Known) -> bool:
        if known.shape in ("steady", "pulsing", "sweeping"):
            return True
        if known.shape == "beacon":
            return known.ends >= 2
        return known.heard_s >= BLIP_S

    def now(self, mono: float) -> list[Known]:
        return sorted((k for k in self.known if k.sounding or (mono - k.seen <= RECENT_S and self.real(k))), key=lambda k: k.hz)

    def data_now(self, mono: float) -> tuple | None:
        found = self.last_data
        return found if found is not None and found[2] is not None and mono - found[2] <= RECENT_S else None

    def forget_old(self, wall: float) -> None:
        kept = [k for k in self.known if wall - k.last <= FORGET_S]
        if len(kept) != len(self.known):
            self.known = kept
            self.dirty = True


def heard_line(known: Known) -> str:
    where = f"at about {khz(known.hz)} kHz"
    if known.shape == "pulsing" and known.period_s:
        every = known.period_s
        rhythm = f"about every {round(every)} seconds" if every >= 1.5 else ("about once a second" if every >= 0.75 else "several times a second")
        return f"There's a high beeping tone in here, {rhythm}, {where}."
    if known.shape == "sweeping":
        return f"There's a tone sliding up and down in here, {where}."
    if known.shape == "beacon":
        return f"There are short high bursts in here {where}, like the beacons some apps use."
    if known.shape == "steady":
        return f"There's a steady tone in here {where}."
    return f"There's a high tone in here {where}."


def data_line(hz: float, room: str | None = None) -> str:
    where = f"in the {room}" if room else "here"
    return f"Something {where} is sending data tones too high for most people to hear, at about {khz(hz)} kHz."


def who_hears(hz: float) -> str:
    if hz <= AUDIBLE_TOP_HZ:
        return "Children and young people can often hear tones that high; most adults can't."
    return "That's higher than people can hear."
