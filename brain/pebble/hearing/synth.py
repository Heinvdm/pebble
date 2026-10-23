import math
import random

from .audio import RATE

TWO_PI = 2.0 * math.pi
RAMP_S = 0.004


def amplitude(level_db: float) -> float:
    return 10.0 ** (level_db / 20.0)


def silence(seconds: float) -> list[float]:
    return [0.0] * max(0, int(round(seconds * RATE)))


def gated(pattern: list[tuple[float, bool]], freq: float, level_db: float = -20.0, drift_hz_s: float = 0.0, harmonics: tuple = (), start_s: float = 0.0) -> list[float]:
    peak = amplitude(level_db)
    ramp = max(1, int(RAMP_S * RATE))
    out: list[float] = []
    phase = 0.0
    index = 0
    for seconds, on in pattern:
        count = max(0, int(round(seconds * RATE)))
        for n in range(count):
            t = start_s + (index + n) / RATE
            phase += TWO_PI * (freq + drift_hz_s * t) / RATE
            if not on:
                out.append(0.0)
                continue
            envelope = min(1.0, (n + 1) / ramp, (count - n) / ramp)
            value = math.sin(phase)
            for order, weight in harmonics:
                if order * (freq + drift_hz_s * t) < RATE / 2:
                    value += weight * math.sin(order * phase)
            out.append(peak * envelope * value)
        index += count
    return out


def t3_pattern(cycles: int, on_s: float = 0.5, off_s: float = 0.5, pause_s: float = 1.5, lead_s: float = 0.3) -> list[tuple[float, bool]]:
    pattern = [(lead_s, False)]
    for _ in range(cycles):
        pattern += [(on_s, True), (off_s, False), (on_s, True), (off_s, False), (on_s, True), (pause_s, False)]
    return pattern


def t4_pattern(cycles: int, on_s: float = 0.1, off_s: float = 0.1, pause_s: float = 5.0, lead_s: float = 0.3) -> list[tuple[float, bool]]:
    pattern = [(lead_s, False)]
    for _ in range(cycles):
        pattern += [(on_s, True), (off_s, False), (on_s, True), (off_s, False), (on_s, True), (off_s, False), (on_s, True), (pause_s, False)]
    return pattern


def beep_pattern(count: int, on_s: float, off_s: float, lead_s: float = 0.3, tail_s: float = 1.0) -> list[tuple[float, bool]]:
    pattern = [(lead_s, False)]
    for index in range(count):
        pattern.append((on_s, True))
        pattern.append((off_s if index < count - 1 else tail_s, False))
    return pattern


def t3(cycles: int = 3, freq: float = 3100.0, level_db: float = -20.0, drift_hz_s: float = 0.0, **timing) -> list[float]:
    return gated(t3_pattern(cycles, **timing), freq, level_db, drift_hz_s, harmonics=((2, 0.08), (3, 0.04)))


def t4(cycles: int = 3, freq: float = 3300.0, level_db: float = -20.0, drift_hz_s: float = 0.0, **timing) -> list[float]:
    return gated(t4_pattern(cycles, **timing), freq, level_db, drift_hz_s, harmonics=((2, 0.08), (3, 0.04)))


def beeps(count: int, on_s: float, off_s: float, freq: float, level_db: float = -20.0, **extra) -> list[float]:
    return gated(beep_pattern(count, on_s, off_s, **extra), freq, level_db)


def noise(seconds: float, level_db: float = -40.0, colour: str = "white", seed: int = 0) -> list[float]:
    rng = random.Random(seed)
    peak = amplitude(level_db)
    out = []
    state = [0.0] * 7
    brown = 0.0
    for _ in range(int(round(seconds * RATE))):
        white = rng.gauss(0.0, 1.0)
        if colour == "pink":
            state[0] = 0.99886 * state[0] + white * 0.0555179
            state[1] = 0.99332 * state[1] + white * 0.0750759
            state[2] = 0.96900 * state[2] + white * 0.1538520
            state[3] = 0.86650 * state[3] + white * 0.3104856
            state[4] = 0.55000 * state[4] + white * 0.5329522
            state[5] = -0.7616 * state[5] - white * 0.0168980
            value = (sum(state[:6]) + state[6] + white * 0.5362) * 0.11
            state[6] = white * 0.115926
        elif colour == "brown":
            brown = (brown + 0.02 * white) / 1.02
            value = brown * 3.5
        else:
            value = white
        out.append(peak * value)
    return out


class _Resonator:
    def __init__(self, freq: float, bandwidth: float):
        r = math.exp(-math.pi * bandwidth / RATE)
        self.a1 = 2.0 * r * math.cos(TWO_PI * freq / RATE)
        self.a2 = -r * r
        self.gain = 1.0 - r
        self.y1 = 0.0
        self.y2 = 0.0

    def step(self, x: float) -> float:
        y = self.gain * x + self.a1 * self.y1 + self.a2 * self.y2
        self.y2, self.y1 = self.y1, y
        return y


VOWELS = ((730, 1090, 2440), (270, 2290, 3010), (300, 870, 2240), (530, 1840, 2480), (570, 840, 2410), (440, 1020, 2240), (660, 1720, 2410))


def speechlike(seconds: float, level_db: float = -25.0, seed: int = 0, pitch: float = 140.0, sing: bool = False) -> list[float]:
    rng = random.Random(seed)
    total = int(round(seconds * RATE))
    out: list[float] = []
    phase = 0.0
    while len(out) < total:
        syllable = int(rng.uniform(0.6, 1.4) * (0.45 if sing else 0.2) * RATE)
        vowel = rng.choice(VOWELS)
        filters = [_Resonator(f * rng.uniform(0.93, 1.07), bw) for f, bw in zip(vowel, (90, 110, 170))]
        f0 = pitch * rng.uniform(0.8, 1.35)
        glide = rng.uniform(-0.4, 0.3) * f0 / max(1, syllable) * (0.1 if sing else 1.0)
        fricative = not sing and rng.random() < 0.35
        hiss = _Resonator(rng.uniform(3500, 6500), 1500)
        for n in range(syllable):
            envelope = math.sin(math.pi * n / syllable) ** (0.4 if sing else 1.2)
            freq = f0 + glide * n + (f0 * 0.02 * math.sin(TWO_PI * 5.5 * n / RATE) if sing else 0.0)
            phase += freq / RATE
            pulse = 0.0
            if phase >= 1.0:
                phase -= 1.0
                pulse = 1.0
            source = pulse * 6.0 + 0.02 * rng.gauss(0.0, 1.0)
            voiced = sum(f.step(source) for f in filters)
            value = voiced * envelope
            if fricative and n < syllable * 0.35:
                value += 0.3 * hiss.step(rng.gauss(0.0, 1.0)) * (1.0 - n / (syllable * 0.35))
            out.append(value)
        out.extend([0.0] * int(rng.uniform(0.02, 0.25 if not sing else 0.08) * RATE))
    out = out[:total]
    return _normalise(out, level_db)


NOTES = [440.0 * 2 ** (k / 12.0) for k in range(-12, 32)]


def music(seconds: float, level_db: float = -25.0, seed: int = 0, high: bool = True, staccato: bool = False) -> list[float]:
    rng = random.Random(seed)
    total = int(round(seconds * RATE))
    out = [0.0] * total
    t = 0
    pool = NOTES if high else NOTES[:24]
    while t < total:
        length = int(rng.choice((0.125, 0.25, 0.25, 0.375, 0.5, 0.75)) * RATE)
        voices = rng.randint(1, 3)
        for _ in range(voices):
            freq = rng.choice(pool)
            harmonics = rng.randint(1, 8)
            phase = rng.random()
            sound = int(length * (0.5 if staccato else rng.uniform(0.7, 1.0)))
            for n in range(min(sound, total - t)):
                envelope = math.exp(-3.0 * n / max(1, sound)) * min(1.0, n / 80.0)
                value = 0.0
                for h in range(1, harmonics + 1):
                    if freq * h >= RATE / 2:
                        break
                    value += math.sin(TWO_PI * (freq * h * n / RATE + phase)) / h
                out[t + n] += envelope * value / voices
        t += length
    return _normalise(out, level_db)


def _normalise(values: list[float], level_db: float) -> list[float]:
    if not values:
        return values
    rms = math.sqrt(sum(v * v for v in values) / len(values))
    if rms <= 0.0:
        return values
    scale = amplitude(level_db) / rms
    return [v * scale for v in values]


def gain(values: list[float], db: float) -> list[float]:
    scale = amplitude(db)
    return [v * scale for v in values]


def mix(*signals: list[float]) -> list[float]:
    length = max((len(s) for s in signals), default=0)
    out = [0.0] * length
    for signal in signals:
        for index, value in enumerate(signal):
            out[index] += value
    return out


def delayed(values: list[float], seconds: float) -> list[float]:
    return silence(seconds) + list(values)


def loop_to(values: list[float], seconds: float) -> list[float]:
    total = int(round(seconds * RATE))
    if not values:
        return silence(seconds)
    out = []
    while len(out) < total:
        out.extend(values)
    return out[:total]


def muffle(values: list[float], cutoff_hz: float = 1800.0, wall_db: float = -12.0, echoes: tuple = ((0.023, 0.35), (0.041, 0.2), (0.067, 0.12))) -> list[float]:
    k = 1.0 - math.exp(-TWO_PI * cutoff_hz / RATE)
    low = 0.0
    filtered = []
    for value in values:
        low += k * (value - low)
        filtered.append(low)
    out = list(filtered)
    for delay_s, weight in echoes:
        shift = int(delay_s * RATE)
        for index in range(shift, len(out)):
            out[index] += weight * filtered[index - shift]
    return gain(out, wall_db)
