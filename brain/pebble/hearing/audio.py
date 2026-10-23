import array
import math
import sys
from dataclasses import dataclass
from typing import Iterable, Protocol

RATE = 16000
FULL_SCALE = 32768.0
SILENT_DB = -120.0


@dataclass(frozen=True)
class Block:
    samples: array.array
    end: float
    skipped: int = 0
    own_voice: bool = False

    @property
    def seconds(self) -> float:
        return len(self.samples) / RATE

    @property
    def start(self) -> float:
        return self.end - self.seconds


class AudioSource(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def read(self, max_seconds: float = 1.0) -> Block | None: ...

    def info(self) -> dict: ...


def pcm_to_samples(data: bytes) -> array.array:
    samples = array.array("h")
    samples.frombytes(bytes(data[: len(data) // 2 * 2]))
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def samples_to_pcm(samples: array.array) -> bytes:
    out = array.array("h", samples)
    if sys.byteorder == "big":
        out.byteswap()
    return out.tobytes()


def to_samples(values: Iterable[float]) -> array.array:
    out = array.array("h")
    for value in values:
        number = round(value * FULL_SCALE)
        out.append(32767 if number > 32767 else (-32768 if number < -32768 else number))
    return out


def to_floats(samples) -> list[float]:
    scale = 1.0 / FULL_SCALE
    return [value * scale for value in samples]


def decibels(power: float) -> float:
    return 10.0 * math.log10(power) if power > 1e-12 else SILENT_DB


def power_of(level_db: float) -> float:
    return 10.0 ** (level_db / 10.0)


def resample(values: list[float], rate: int, target: int = RATE) -> list[float]:
    if rate == target or not values:
        return list(values)
    count = max(1, int(len(values) * target / rate))
    step = rate / target
    last = len(values) - 1
    out = []
    for index in range(count):
        position = index * step
        low = int(position)
        if low >= last:
            out.append(values[last])
            continue
        frac = position - low
        out.append(values[low] * (1.0 - frac) + values[low + 1] * frac)
    return out
