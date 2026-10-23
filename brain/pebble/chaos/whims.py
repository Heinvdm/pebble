from dataclasses import dataclass, field

from .levers import WHIM_MIN_GAP_S, WHIMS_MAX_PER_HOUR

WHIM_KINDS = ("hum", "spin", "doodle", "peek", "wink")
HOUR_S = 3600.0
SCARED = 4.0
LOW_MOOD = -0.4


@dataclass(frozen=True)
class WhimContext:
    now: float
    quiet: bool = False
    active: bool = True
    low_battery: bool = False
    fear: float = 0.0
    valence: float = 0.0
    someone_upset: bool = False
    busy: bool = False
    available: tuple[str, ...] = WHIM_KINDS


@dataclass(frozen=True)
class Whim:
    kind: str
    at: float
    draw: str


def suppressed(ctx: WhimContext) -> str | None:
    if ctx.quiet:
        return "quiet hours"
    if ctx.someone_upset:
        return "someone seems upset"
    if not ctx.active:
        return "not up and about"
    if ctx.low_battery:
        return "battery low"
    if ctx.fear >= SCARED:
        return "too scared"
    if ctx.valence <= LOW_MOOD:
        return "feeling low"
    if ctx.busy:
        return "already busy"
    if not ctx.available:
        return "nothing to do"
    return None


@dataclass
class WhimScheduler:
    stream: object
    started: float
    recent: list[float] = field(default_factory=list)
    wait: float | None = None
    since: float | None = None
    last_reason: str | None = None

    def __post_init__(self):
        if self.since is None:
            self.since = self.started

    def due_at(self, rate_per_hour: float) -> float | None:
        if rate_per_hour <= 0 or self.wait is None:
            return None
        rate = min(float(WHIMS_MAX_PER_HOUR), rate_per_hour)
        return self.since + WHIM_MIN_GAP_S + self.wait * HOUR_S / rate

    def _room(self, now: float) -> bool:
        self.recent = [at for at in self.recent if now - at < HOUR_S]
        if len(self.recent) >= WHIMS_MAX_PER_HOUR:
            return False
        return not self.recent or now - self.recent[-1] >= WHIM_MIN_GAP_S

    def check(self, ctx: WhimContext, rate_per_hour: float) -> Whim | None:
        reason = suppressed(ctx)
        self.last_reason = reason
        if reason is not None or rate_per_hour <= 0:
            self.since = ctx.now
            return None
        if not self._room(ctx.now):
            return None
        if self.wait is None:
            self.wait = self.stream.expovariate(1.0)
        due = self.due_at(rate_per_hour)
        if due is None or ctx.now < due:
            return None
        kind = self.stream.choice(ctx.available)
        whim = Whim(kind, ctx.now, self.stream.last["id"] if self.stream.last else "")
        self.recent.append(ctx.now)
        self.since = ctx.now
        self.wait = None
        return whim
