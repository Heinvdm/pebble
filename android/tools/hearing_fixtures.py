import argparse
import json
import math
import random
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "app" / "src" / "test" / "resources" / "hearing"
RATE = 16_000
CUTOFF_HZ = 8_000.0
BETA = 7.0
TAPS_PER_STEP = 80
FACTORS = (2, 3, 6)


def bessel0(x: float) -> float:
    total = 1.0
    term = 1.0
    half = x / 2
    k = 1
    while term > total * 1e-17:
        term *= (half / k) * (half / k)
        total += term
        k += 1
    return total


def taps(factor: int) -> list[float]:
    count = TAPS_PER_STEP * factor + 1
    middle = (count - 1) / 2
    fc = CUTOFF_HZ / (RATE * factor)
    scale = bessel0(BETA)
    h = []
    for n in range(count):
        x = n - middle
        ideal = 2 * fc if x == 0 else math.sin(2 * math.pi * fc * x) / (math.pi * x)
        r = x / middle
        h.append(ideal * bessel0(BETA * math.sqrt(max(0.0, 1 - r * r))) / scale)
    total = sum(h)
    return [v / total for v in h]


def decimate(samples, factor: int) -> list[int]:
    h = np.array(taps(factor))
    x = np.concatenate([np.zeros(len(h) - 1), np.asarray(samples, dtype=np.float64)])
    y = np.convolve(x, h, mode="valid")[factor - 1 :: factor]
    return [int(v) for v in np.clip(np.floor(y + 0.5), -32768, 32767)]


def read_wav(path: Path):
    with wave.open(str(path)) as w:
        assert w.getsampwidth() == 2
        frames = w.readframes(w.getnframes())
        values = [int.from_bytes(frames[i : i + 2], "little", signed=True) for i in range(0, len(frames), 2)]
        return values, w.getframerate(), w.getnchannels()


def write_wav(path: Path, values, rate: int, channels: int = 1) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.clip(np.round(np.asarray(values, dtype=np.float64)), -32768, 32767).astype("<i2").tobytes())


def upsample(values, factor: int) -> np.ndarray:
    h = np.array(taps(factor))
    stuffed = np.zeros(len(values) * factor)
    stuffed[::factor] = np.asarray(values, dtype=np.float64) * factor
    delay = (len(h) - 1) // 2
    return np.convolve(stuffed, h)[delay : delay + len(stuffed)]


def high_junk(count: int, rate: int, seed: int = 11) -> np.ndarray:
    t = np.arange(count) / rate
    spectrum = np.fft.rfft(np.random.default_rng(seed).normal(0, 1, count))
    spectrum[np.fft.rfftfreq(count, 1 / rate) < 9_000] = 0
    hiss = np.fft.irfft(spectrum, count)
    hiss *= 60 / max(1e-9, hiss.std())
    return 1000 * np.sin(2 * np.pi * 17_400 * t) + 700 * np.sin(2 * np.pi * 20_000 * t) + 500 * np.sin(2 * np.pi * 12_000 * t) + 300 * np.sin(2 * np.pi * 9_000 * t) + hiss


def wide_copy(source: Path, target: Path, junk: bool) -> None:
    values, rate, channels = read_wav(source)
    assert rate == RATE and channels == 1, "the source must be 16 kHz mono"
    wide = upsample(values, 3)
    if junk:
        wide = wide + high_junk(len(wide), RATE * 3)
    write_wav(target, wide, RATE * 3)


def fixtures(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    r = random.Random(5)
    signal = [int(4000 * math.sin(2 * math.pi * 700 * i / 48_000) + 3000 * math.sin(2 * math.pi * 13_000 * i / 48_000) + r.gauss(0, 800)) for i in range(4_800)]
    data = {
        "rate": RATE,
        "cutoff_hz": CUTOFF_HZ,
        "beta": BETA,
        "taps": {str(f): [round(v, 10) for v in taps(f)] for f in FACTORS},
        "input": signal,
        "output": decimate(signal, 3),
    }
    (out / "decimate.json").write_text(json.dumps(data), encoding="utf-8")
    print(f"wrote {out / 'decimate.json'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Make the hearing fixtures shared by the phone's decimator and its Python twin, and 48 kHz copies of 16 kHz test sounds")
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--wide", nargs=2, metavar=("SOURCE", "TARGET"), help="write a 48 kHz copy of a 16 kHz mono WAV")
    parser.add_argument("--junk", action="store_true", help="with --wide, add tones and noise above 8 kHz that bringing it down must remove")
    args = parser.parse_args()
    if args.wide:
        wide_copy(Path(args.wide[0]), Path(args.wide[1]), args.junk)
        return
    fixtures(Path(args.out))


if __name__ == "__main__":
    main()
