import math
from collections import deque
from typing import Callable

from .feeds import Sample
from .motion import Felt
from .notice import Notice

LIT_LUX = 20.0
OUT_LUX = 3.0
OUT_WITHIN_S = 3.0
OUT_HOLD_S = 5.0
DARK_LUX = 5.0
DARK_S = 60.0
FLICKER_CHANGE = 0.3
FLICKER_RATE = 3.0
FLICKER_S = 3.0
LIGHT_GAP_S = 60.0

NEAR_HOLD_S = 0.3
NEAR_RELEASE_S = 2.0
NEAR_CM = 3.0
POKES = 3
POKE_WITHIN_S = 6.0

WARM_C = 40.0
HOT_C = 43.0
TOO_HOT_C = 46.0
HEAT_EASE_C = 2.0

RISE_C_PER_MIN = 8.0
RISE_SHORT_C_PER_MIN = 6.0
RISE_WINDOW_S = 60.0
RISE_SHORT_S = 30.0
RISE_MIN_C = 30.0
RISE_GAP_S = 300.0
GAS_DROP = 0.5
GAS_FREEZE = 0.7
GAS_WITHIN_S = 120.0
GAS_BASE_S = 2700.0
GAS_BASE_MIN_S = 600.0
GAS_SETTLE_S = 900
GAS_GAP_S = 600.0
HUMID_JUMP_S = 180.0
HUMID_JUMP_PCT = 8.0
COLD_C = 15.0
WARM_ROOM_C = 28.0
HUMID_PCT = 75.0
ROOM_EASE = 1.5
ROOM_GAP_S = 3 * 3600.0


class LightWatch:
    def __init__(self, power_lost: Callable[[], bool] = lambda: False):
        self.power_lost = power_lost
        self.samples: deque = deque()
        self.out_at: float | None = None
        self.out_said = -math.inf
        self.dark = False
        self.changes: deque = deque()
        self.flicker_said = -math.inf
        self.latest: float | None = None

    def feed(self, samples: list[Sample]) -> list:
        out = []
        for sample in samples:
            out.extend(self._sample(sample.at, max(0.0, sample.value)))
        return out

    def _sample(self, at: float, lux: float) -> list:
        previous = self.latest
        self.latest = lux
        self.samples.append((at, lux))
        while self.samples and at - self.samples[0][0] > DARK_S:
            self.samples.popleft()
        out = []
        lit_before = [l for t, l in self.samples if 0 < at - t <= OUT_WITHIN_S + OUT_HOLD_S and l >= LIT_LUX]
        if lux <= OUT_LUX and lit_before and self.out_at is None:
            self.out_at = at
        if self.out_at is not None:
            if lux > OUT_LUX:
                self.out_at = None
            elif at - self.out_at >= OUT_HOLD_S and at - self.out_said >= LIGHT_GAP_S:
                self.out_said = at
                self.out_at = None
                power = " and your charger stopped at the same moment, so the power may be off" if self.power_lost() else ""
                out.append(Felt("lights_out", f"the lights went out{power}", {"power": bool(power)}))
        span = at - self.samples[0][0]
        if span >= DARK_S * 0.9:
            ordered = sorted(l for _, l in self.samples)
            middle = ordered[len(ordered) // 2]
            dark = middle <= DARK_LUX
            if dark != self.dark:
                self.dark = dark
                out.append(Felt("dark" if dark else "light", "the room is dark" if dark else "the room is light again", {"lux": round(middle, 1)}))
        if previous is not None and max(previous, lux) > 0 and abs(lux - previous) / max(previous, lux) >= FLICKER_CHANGE:
            self.changes.append(at)
        while self.changes and at - self.changes[0] > FLICKER_S:
            self.changes.popleft()
        if len(self.changes) >= FLICKER_RATE * FLICKER_S and at - self.flicker_said >= LIGHT_GAP_S:
            self.flicker_said = at
            self.changes.clear()
            out.append(Felt("flicker", "the light is flickering fast (only a hint: a television or a candle does this too)", {}))
        return out

    def status(self) -> dict:
        return {"lux": None if self.latest is None else round(self.latest, 1), "dark": self.dark}


class NearWatch:
    def __init__(self, max_range: Callable[[], float | None] = lambda: None):
        self.max_range = max_range
        self.near_since: float | None = None
        self.far_since: float | None = None
        self.holding = False
        self.pokes: deque = deque()
        self.latest: float | None = None

    def _is_near(self, cm: float) -> bool:
        limit = self.max_range()
        if limit is not None and limit > 0:
            return cm < limit
        return cm <= NEAR_CM

    def feed(self, samples: list[Sample], now: float) -> list:
        out = []
        for sample in samples:
            self.latest = sample.value
            near = self._is_near(sample.value)
            if near and self.near_since is None:
                self.near_since = sample.at
                self.far_since = None
                self.pokes.append(sample.at)
            elif not near and self.near_since is not None:
                self.near_since = None
                self.far_since = sample.at
        while self.pokes and now - self.pokes[0] > POKE_WITHIN_S:
            self.pokes.popleft()
        if self.near_since is not None and not self.holding and now - self.near_since >= NEAR_HOLD_S:
            self.holding = True
            poked = len(self.pokes) >= POKES
            out.append(Felt("poked" if poked else "touched_face", "someone keeps poking your face; you hold still" if poked else "something is right up against your face (maybe a curious little one); you hold still", {}))
        if self.holding and self.near_since is None and self.far_since is not None and now - self.far_since >= NEAR_RELEASE_S:
            self.holding = False
            out.append(Felt("face_clear", "nothing is against your face any more", {}))
        return out

    def hold_reason(self) -> str | None:
        return "something is pressed against my face" if self.holding else None

    def status(self) -> dict:
        return {"cm": self.latest, "holding": self.holding}


class PhoneHeat:
    def __init__(self):
        self.level = 0
        self.latest: float | None = None

    def update(self, celsius: float | None) -> list:
        if celsius is None or not -40.0 < celsius < 150.0:
            return []
        self.latest = celsius
        limits = (WARM_C, HOT_C, TOO_HOT_C)
        up = sum(1 for limit in limits if celsius >= limit)
        down = sum(1 for limit in limits if celsius >= limit - HEAT_EASE_C)
        level = up if up > self.level else (down if down < self.level else self.level)
        if level == self.level:
            return []
        rising = level > self.level
        self.level = level
        whole = round(celsius)
        if level == 0:
            return [Felt("phone_cool", f"your phone has cooled down ({whole} C)", {"c": whole})]
        if level == 1:
            return [Felt("phone_warm", f"your phone is warm ({whole} C); take it easy", {"c": whole})] if rising else []
        if level == 2:
            return [Felt("phone_hot", f"your phone is hot ({whole} C), so you hold your wheels still to look after yourself", {"c": whole})]
        return [Felt("phone_too_hot", f"your phone is far too hot ({whole} C); you keep still and ask to be moved somewhere cooler", {"c": whole})]

    def hold_reason(self) -> str | None:
        return "my phone is too hot" if self.level >= 2 else None

    def status(self) -> dict:
        return {"c": self.latest, "level": ("cool", "warm", "hot", "too hot")[self.level]}


class AirWatch:
    def __init__(self, clock_now: Callable[[], float]):
        self.now = clock_now
        self.temps: deque = deque()
        self.gas: deque = deque()
        self.humid: deque = deque()
        self.last_ms: int | None = None
        self.heated: int | None = None
        self.gas_low = False
        self.rise_said = -math.inf
        self.gas_said = -math.inf
        self.room_said: dict[str, float] = {}
        self.room_state: dict[str, bool] = {}
        self.latest: dict = {}

    def feed(self, reading) -> list:
        if reading is None or not getattr(reading, "present", False) or reading.body_ms == self.last_ms:
            return []
        self.last_ms = reading.body_ms
        at = reading.at
        if reading.heated_s is not None and self.heated is not None and reading.heated_s < self.heated:
            self.gas.clear()
            self.gas_low = False
        self.heated = reading.heated_s
        c, rh, ohm = reading.temperature_c, reading.humidity_pct, reading.gas_ohm
        self.latest = {"c": c, "rh": rh, "gas_ohm": ohm, "hpa": reading.pressure_hpa, "warming": reading.warming}
        out = []
        if c is not None:
            out.extend(self._heat(at, c))
            out.extend(self._room(at, "cold", c <= COLD_C, c > COLD_C + ROOM_EASE, f"the room is getting cold ({round(c)} C near the floor)"))
            out.extend(self._room(at, "warm", c >= WARM_ROOM_C, c < WARM_ROOM_C - ROOM_EASE, f"the room is warm ({round(c)} C near the floor)"))
        if rh is not None:
            self.humid.append((at, rh))
            while self.humid and at - self.humid[0][0] > HUMID_JUMP_S:
                self.humid.popleft()
            out.extend(self._room(at, "humid", rh >= HUMID_PCT, rh < HUMID_PCT - 5.0, f"the air is humid ({round(rh)} %)"))
        if ohm is not None and ohm > 0 and not reading.warming and (reading.heated_s or 0) >= GAS_SETTLE_S:
            out.extend(self._gas(at, float(ohm)))
        return out

    def _heat(self, at: float, c: float) -> list:
        self.temps.append((at, c))
        while self.temps and at - self.temps[0][0] > RISE_WINDOW_S:
            self.temps.popleft()
        if at - self.temps[0][0] < RISE_WINDOW_S * 0.9:
            return []
        rate = (c - self.temps[0][1]) / (at - self.temps[0][0]) * 60.0
        short = [(t, v) for t, v in self.temps if at - t <= RISE_SHORT_S]
        short_rate = (c - short[0][1]) / max(1.0, at - short[0][0]) * 60.0 if short else 0.0
        if rate < RISE_C_PER_MIN or short_rate < RISE_SHORT_C_PER_MIN or c < RISE_MIN_C or at - self.rise_said < RISE_GAP_S:
            return []
        self.rise_said = at
        return [Notice("heat_rise", 0.3, "air sensor", self.now(), f"the air near the floor warmed {rate:.0f} C in a minute (now {round(c)} C); only a hint, and late, since heat rises to the ceiling first", {"c_per_min": round(rate, 1), "c": round(c, 1)})]

    def _gas(self, at: float, ohm: float) -> list:
        while self.gas and at - self.gas[0][0] > GAS_BASE_S:
            self.gas.popleft()
        older = sorted(v for t, v in self.gas if at - t > GAS_WITHIN_S)
        span = at - self.gas[0][0] if self.gas else 0.0
        base = older[len(older) // 2] if older else None
        ratio = None if base is None else ohm / base
        if ratio is None or ratio > GAS_FREEZE:
            self.gas.append((at, ohm))
            self.gas_low = False
        if base is None or span < GAS_BASE_MIN_S or ratio > GAS_DROP:
            return []
        steam = len(self.humid) > 1 and self.humid[-1][1] - min(v for _, v in self.humid) >= HUMID_JUMP_PCT
        if self.gas_low or at - self.gas_said < GAS_GAP_S:
            return []
        self.gas_low = True
        if steam:
            return [Felt("room_steam", "the air got steamy (a shower or a kettle?), which also moves the air sensor", {})]
        self.gas_said = at
        return [Notice("gas_spike", 0.25, "air sensor", self.now(), f"the air sensor's reading dropped to {round(100 * ratio)} % of its usual level in a short time, like smoke, burning food, alcohol or strong fumes; only a hint", {"ratio": round(ratio, 2), "ohm": round(ohm), "base_ohm": round(base)})]

    def _room(self, at: float, name: str, on: bool, off: bool, text: str) -> list:
        state = self.room_state.get(name, False)
        if not state and on and at - self.room_said.get(name, -math.inf) >= ROOM_GAP_S:
            self.room_state[name] = True
            self.room_said[name] = at
            return [Felt(f"room_{name}", text, {})]
        if state and off:
            self.room_state[name] = False
        return []

    def status(self) -> dict:
        return dict(self.latest)
