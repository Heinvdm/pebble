import hashlib
import json
import random
from typing import Callable

LEVERS = ("choices", "words", "steady", "seeds", "whims", "motion", "mutation", "dream", "scripts")
PROTECTED = frozenset({"safety", "stop", "battery", "limits", "speed", "distance", "core", "owner", "reflexes"})

Sink = Callable[[dict], None]


class ProtectedLever(ValueError):
    pass


def derive(*parts) -> int:
    digest = hashlib.sha256("/".join(str(part) for part in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _choices(rng: random.Random, args: list):
    population, weights, k = args
    return rng.choices(population, weights=weights, k=k)


OPS: dict[str, Callable[[random.Random, list], object]] = {
    "random": lambda rng, args: rng.random(),
    "uniform": lambda rng, args: rng.uniform(args[0], args[1]),
    "randint": lambda rng, args: rng.randint(args[0], args[1]),
    "randrange": lambda rng, args: rng.randrange(args[0]),
    "choice": lambda rng, args: rng.choice(args[0]),
    "choices": _choices,
    "gauss": lambda rng, args: rng.gauss(args[0], args[1]),
    "expovariate": lambda rng, args: rng.expovariate(args[0]),
    "getrandbits": lambda rng, args: rng.getrandbits(args[0]),
}


def run_op(seed: int, n: int, op: str, args: list):
    if op not in OPS:
        raise ValueError(f"unknown draw {op}")
    return OPS[op](random.Random(derive(seed, n)), args)


def normal(value):
    return json.loads(json.dumps(value))


class Stream:
    def __init__(self, lever: str, seed: int, sink: Sink | None = None, start: int = 0):
        self.lever = lever
        self.seed = seed
        self.n = start
        self.sink = sink or (lambda record: None)
        self.last: dict | None = None

    def _draw(self, op: str, args: list):
        n = self.n
        self.n += 1
        outcome = run_op(self.seed, n, op, args)
        self.last = {"lever": self.lever, "seed": self.seed, "n": n, "id": f"{self.lever}:{self.seed}:{n}", "op": op, "args": args, "outcome": outcome}
        self.sink(dict(self.last))
        return outcome

    def random(self) -> float:
        return self._draw("random", [])

    def uniform(self, a: float, b: float) -> float:
        return self._draw("uniform", [a, b])

    def randint(self, a: int, b: int) -> int:
        return self._draw("randint", [a, b])

    def randrange(self, stop: int) -> int:
        return self._draw("randrange", [stop])

    def choice(self, seq):
        return self._draw("choice", [list(seq)])

    def choices(self, population, weights=None, k: int = 1) -> list:
        return self._draw("choices", [list(population), None if weights is None else list(weights), k])

    def gauss(self, mu: float, sigma: float) -> float:
        return self._draw("gauss", [mu, sigma])

    def expovariate(self, rate: float) -> float:
        return self._draw("expovariate", [rate])

    def getrandbits(self, bits: int) -> int:
        return self._draw("getrandbits", [bits])


class Streams:
    def __init__(self, seed: int, sink: Sink | None = None):
        self.seed = seed
        self.sink = sink
        self._streams: dict[str, Stream] = {}

    def stream(self, lever: str) -> Stream:
        if lever in PROTECTED:
            raise ProtectedLever(f"chaos never touches {lever}")
        if lever not in LEVERS:
            raise ValueError(f"unknown lever {lever}")
        if lever not in self._streams:
            self._streams[lever] = Stream(lever, derive(self.seed, lever), self.sink)
        return self._streams[lever]

    def counts(self) -> dict[str, int]:
        return {lever: stream.n for lever, stream in self._streams.items()}


def replay(record: dict):
    return run_op(int(record["seed"]), int(record["n"]), str(record["op"]), list(record.get("args") or []))


def check(record: dict) -> bool:
    return normal(replay(record)) == normal(record.get("outcome"))
