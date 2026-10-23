import logging
import subprocess
from dataclasses import dataclass, field
from typing import Protocol

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DockAttempt:
    started: bool
    reason: str


@dataclass(frozen=True)
class DreamResult:
    entries: list = field(default_factory=list)
    note: str = ""


class Vision(Protocol):
    available: bool

    async def glance(self) -> list[str]: ...


class NoVision:
    available = False

    async def glance(self) -> list[str]:
        return []


class PlaceMap(Protocol):
    def where_am_i(self) -> str | None: ...


class NoMap:
    def where_am_i(self) -> str | None:
        return None


class DockSeeker(Protocol):
    async def seek(self) -> DockAttempt: ...


class NoDockSeeker:
    async def seek(self) -> DockAttempt:
        return DockAttempt(False, "Pebble cannot find its dock by itself yet (needs the AprilTag homing)")


class Dreamer(Protocol):
    async def consolidate(self, diary_today: list[dict], summary: str) -> DreamResult: ...


class NoDreamer:
    async def consolidate(self, diary_today: list[dict], summary: str) -> DreamResult:
        return DreamResult([], "dream consolidation is not built yet")


class PowerControl(Protocol):
    def shutdown(self) -> bool: ...


class ProcessOnly:
    def shutdown(self) -> bool:
        log.warning("no shutdown command configured; only the brain process stops")
        return False


class CommandPower:
    def __init__(self, argv: list[str]):
        self.argv = list(argv)

    def shutdown(self) -> bool:
        try:
            subprocess.run(self.argv, timeout=30, check=True)
        except (OSError, subprocess.SubprocessError) as error:
            log.error("shutdown command failed: %s", error)
            return False
        return True


SHUTDOWNS = (("systemctl", "poweroff"), ("poweroff",), ("shutdown", "-h", "now"))


def power_from(config: dict) -> PowerControl:
    if config.get("kind") == "android":
        from ..android.power import AndroidPower

        return AndroidPower(str(config.get("mode", "rest")))
    command = tuple(str(part) for part in (config.get("shutdown_command") or ()))
    if not command:
        return ProcessOnly()
    if command not in SHUTDOWNS:
        log.warning("a profile may name only a known shutdown command, so %r is not run", command[:1])
        return ProcessOnly()
    return CommandPower(list(command))


@dataclass(frozen=True)
class CodeDrawing:
    ok: bool
    source: str = ""
    reason: str = ""


class CodeArtist(Protocol):
    available: bool

    async def draw_code(self, request: str) -> CodeDrawing: ...


class NoCodeArtist:
    available = False

    async def draw_code(self, request: str) -> CodeDrawing:
        return CodeDrawing(False, reason="free-code drawing (a draw(t) function from the big model) is not built yet")


class JokeVariation(Protocol):
    async def vary(self, joke: dict, rng) -> str | None: ...


class NoJokeVariation:
    async def vary(self, joke: dict, rng) -> str | None:
        return None
