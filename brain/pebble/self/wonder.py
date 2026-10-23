from dataclasses import dataclass

from .drives import PRESSING, Drive

KINDS = ("stakes", "surprise", "stuck", "invalid", "doubt", "drives", "pile")
PUSHED = ("stakes", "surprise", "stuck", "invalid", "doubt")
DRIVEN = frozenset({"company", "curiosity", "energy", "warmth", "safety"})
DEEP = ("stakes", "stuck", "invalid", "doubt")
FADE_S = 900.0
FULL_PILE = 12.0
MIDDLE = 0.6
DEEP_AT = 0.5
KEEP = 40
KEEP_WHY = 5


@dataclass(frozen=True)
class Push:
    kind: str
    amount: float
    why: str
    at: float


def threshold(thoughtfulness: float) -> float:
    return max(0.1, min(0.9, 0.75 - 0.6 * float(thoughtfulness)))


class Wonder:
    def __init__(self):
        self.pushes: list[Push] = []
        self.pile = 0.0
        self.pile_why: list[str] = []
        self.drive: tuple[float, str] = (0.0, "")
        self.seen: tuple[float, str] = (0.0, "")

    def push(self, kind: str, amount: float, why: str, now: float) -> None:
        if kind not in PUSHED or amount <= 0:
            return
        self.pushes.append(Push(kind, min(1.0, float(amount)), why, now))
        del self.pushes[:-KEEP]

    def noticed(self, importance: float, why: str, now: float) -> None:
        self.pile += max(0.0, float(importance))
        if why:
            self.pile_why.append(why)
            del self.pile_why[:-KEEP_WHY]

    def feel(self, found: tuple[Drive, ...]) -> None:
        strong = [d for d in found if d.name in DRIVEN and d.pressure > PRESSING]
        if not strong:
            self.drive = self.seen = (0.0, "")
            return
        top = max(strong, key=lambda d: d.pressure)
        value = (top.pressure - PRESSING) / (1.0 - PRESSING)
        if top.why != self.seen[1]:
            self.seen = (0.0, top.why)
        elif value < self.seen[0]:
            self.seen = (value, top.why)
        self.drive = (value, top.why)

    def _pressing(self) -> float:
        return max(0.0, self.drive[0] - self.seen[0])

    def parts(self, now: float, pulls: dict | None = None) -> dict[str, tuple[float, str]]:
        pulls = pulls or {}
        found: dict[str, tuple[float, str]] = {}
        for kind in PUSHED:
            items = [(push.amount * 0.5 ** (max(0.0, now - push.at) / FADE_S), push.why) for push in self.pushes if push.kind == kind]
            if items:
                found[kind] = (min(1.0, sum(value for value, _ in items)), max(items)[1])
        if self._pressing() > 0:
            found["drives"] = (self._pressing(), self.drive[1])
        if self.pile > 0:
            found["pile"] = (min(1.0, self.pile / FULL_PILE), self.pile_why[-1] if self.pile_why else "")
        return {kind: (min(1.0, value * float(pulls.get(kind, 1.0))), why) for kind, (value, why) in found.items()}

    def score(self, now: float, pulls: dict | None = None) -> float:
        left = 1.0
        for value, _ in self.parts(now, pulls).values():
            left *= 1.0 - value
        return 1.0 - left

    def reasons(self, now: float, pulls: dict | None = None, most: int = 3) -> list[str]:
        ranked = sorted(self.parts(now, pulls).items(), key=lambda item: -item[1][0])
        out = []
        for _, (value, why) in ranked:
            if why and value > 0.05 and why not in out:
                out.append(why)
        return out[:most]

    def deep(self, now: float, pulls: dict | None = None) -> bool:
        parts = self.parts(now, pulls)
        return any(parts.get(kind, (0.0, ""))[0] >= DEEP_AT for kind in DEEP)

    def strongest(self, now: float, pulls: dict | None = None) -> str | None:
        parts = self.parts(now, pulls)
        return max(parts, key=lambda kind: parts[kind][0]) if parts else None

    def quiet(self) -> bool:
        return not self.pushes and self.pile <= 0 and self._pressing() <= 0

    def looked(self) -> None:
        self.pushes = []
        self.pile = 0.0
        self.pile_why = []
        self.seen = self.drive
