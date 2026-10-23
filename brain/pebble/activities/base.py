from dataclasses import dataclass

from ..people.trust import STRANGER
from ..understand.request import Request
from .gate import Asker, Running
from .kit import Kit


@dataclass(frozen=True)
class Target:
    id: str | None
    label: str
    tier: str = STRANGER


@dataclass(frozen=True)
class Ending:
    how: str
    text: str
    say: str = ""
    next: Request | None = None


class Activity:
    kind = ""
    moving = True
    homing = False
    urgent = False
    sight = False
    delay = 0.0
    words = ""
    heard_by: tuple = ()

    def __init__(self, request: Request, asker: Asker, target: Target | None = None, battery: bool = False):
        self.request = request
        self.asker = asker
        self.target = target
        self.battery = battery
        self.cause: Ending | None = None
        self.started_at: float | None = None

    def whom(self, you: str = "you") -> str:
        if self.target is None or (self.asker.id is not None and self.target.id == self.asker.id):
            return you if not self.asker.own else (self.target.label if self.target else "someone")
        return self.target.label

    def who(self) -> str:
        if self.target is not None:
            return self.target.label
        return "someone"

    def describe(self) -> str:
        return self.kind.replace("_", " ")

    def running(self) -> Running:
        return Running(
            self.kind,
            self.asker.id,
            self.asker.label,
            self.asker.tier,
            self.target.id if self.target else None,
            self.target.label if self.target else "",
            self.battery,
            self.urgent,
        )

    def adjust(self, request: Request) -> tuple[str, Request | None]:
        if request.change in ("enough", "stay"):
            return "Okay, I'll stay here.", Request("wait")
        return "Okay.", None

    async def run(self, kit: Kit) -> Ending:
        raise NotImplementedError
