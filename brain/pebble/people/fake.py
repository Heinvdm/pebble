import asyncio
import random
from dataclasses import dataclass

DIMS = 32
LOOK_EVERY_S = 3.0


def fake_print(key: str, kind: str, dims: int = DIMS) -> list[float]:
    rng = random.Random(f"{kind}:{key}")
    return [rng.gauss(0.0, 1.0) for _ in range(dims)]


@dataclass(frozen=True)
class Visit:
    after_s: float
    who: str
    says: str = ""
    leaves: bool = False


DEFAULT_VISITS = (
    Visit(2.0, "sam", "Hello Pebble!"),
    Visit(6.0, "sam", "What are you up to today?"),
    Visit(90.0, "sam", leaves=True),
)


class FakePresence:
    def __init__(self, visits=DEFAULT_VISITS, look_every_s: float = LOOK_EVERY_S):
        self.visits = tuple(visits)
        self.look_every_s = look_every_s
        self.here: set[str] = set()

    async def _look(self, life) -> None:
        while True:
            for who in sorted(self.here):
                life.see(fake_print(who, "face"))
            await asyncio.sleep(self.look_every_s)

    async def run(self, life) -> None:
        looker = asyncio.create_task(self._look(life), name="pebble-fake-presence")
        try:
            elapsed = 0.0
            for visit in sorted(self.visits, key=lambda v: v.after_s):
                await asyncio.sleep(max(0.0, visit.after_s - elapsed))
                elapsed = visit.after_s
                if visit.leaves:
                    self.here.discard(visit.who)
                    continue
                self.here.add(visit.who)
                life.see(fake_print(visit.who, "face"))
                if visit.says:
                    life.hear(visit.says, fake_print(visit.who, "voice"))
            await asyncio.Event().wait()
        finally:
            looker.cancel()
            await asyncio.gather(looker, return_exceptions=True)
