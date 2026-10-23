from typing import Protocol

from ..clock import Clock


class Ears(Protocol):
    async def run(self, life) -> None: ...

    def status(self) -> dict: ...


def hearing_from(config: dict | None, clock: Clock) -> Ears | None:
    config = dict(config or {})
    if config.get("kind") == "android":
        from ..android.hearing import AndroidEars

        return AndroidEars(clock, listen=bool(config.get("listen", True)))
    return None
