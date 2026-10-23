import argparse
import sys
import time

from . import synth
from .alarm import AlarmDetector, engine_for
from .audio import RATE, Block, to_samples

CHUNK_S = 0.5


def run(samples, engine: str) -> tuple[list, float]:
    detector = AlarmDetector(engine)
    step = int(CHUNK_S * RATE)
    heard = []
    started = time.perf_counter()
    for start in range(0, len(samples), step):
        part = samples[start : start + step]
        heard.extend(detector.feed(Block(part, (start + len(part)) / RATE)))
    return heard, time.perf_counter() - started


def mixes(minutes: float, seed: int) -> dict:
    seconds = minutes * 60.0
    return {
        "speech": lambda: synth.speechlike(seconds, -22.0, seed=seed),
        "singing": lambda: synth.speechlike(seconds, -20.0, seed=seed + 1, pitch=280.0, sing=True),
        "music": lambda: synth.music(seconds, -20.0, seed=seed + 2),
        "staccato music": lambda: synth.music(seconds, -20.0, seed=seed + 3, staccato=True),
        "television": lambda: synth.mix(synth.speechlike(seconds, -24.0, seed=seed + 4), synth.music(seconds, -30.0, seed=seed + 5), synth.noise(seconds, -50.0, "pink", seed + 6)),
        "kitchen noise": lambda: synth.mix(synth.noise(seconds, -35.0, "pink", seed + 7), synth.noise(seconds, -45.0, "white", seed + 8)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.hearing.bench", description="Time the smoke/CO alarm beep detector and count false alarms on made-up speech, music and noise")
    parser.add_argument("--minutes", type=float, default=2.0, help="minutes of each kind of made-up sound (default 2)")
    parser.add_argument("--seed", type=int, default=21)
    args = parser.parse_args(argv)
    engines = ["plain"]
    try:
        engine_for("numpy")
        engines.append("numpy")
    except ImportError:
        pass
    alarm = to_samples(synth.mix(synth.t3(8, level_db=-35.0), synth.speechlike(33.0, -28.0, seed=args.seed)))
    for engine in engines:
        heard, took = run(alarm, engine)
        sure = [h for h in heard if h.confidence >= 0.9]
        print(f"{engine:6s} smoke alarm under speech: {len(sure)} sure detections, first after {sure[0].at:.1f} s; {1000 * took / (len(alarm) / RATE):.2f} ms of processor time per second of sound" if sure else f"{engine:6s} smoke alarm under speech: MISSED")
    total_s = 0.0
    false = 0
    for name, make in mixes(args.minutes, args.seed).items():
        samples = to_samples(make())
        total_s += len(samples) / RATE
        heard, took = run(samples, "plain")
        maybe = [h for h in heard if h.confidence < 0.9]
        sure = [h for h in heard if h.confidence >= 0.9]
        false += len(sure)
        print(f"{name:15s} {len(samples) / RATE / 60:4.1f} min: {len(sure)} false alarms, {len(maybe)} maybes; {1000 * took / (len(samples) / RATE):.2f} ms per second (plain)")
    print(f"total {total_s / 60:.1f} min of made-up sound, {false} false alarms")
    return 0 if false == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
