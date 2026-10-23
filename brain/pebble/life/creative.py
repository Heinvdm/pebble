import asyncio
import logging
import math
from dataclasses import replace

from ..blackbox import BlackBox
from ..chaos.dial import DialInputs
from ..chaos.engine import Chaos
from ..chaos.ideas import IdeaDecks, card_text
from ..chaos.levers import dream_allowed
from ..chaos.novelty import RecentActions
from ..chaos.whims import Whim, WhimContext, WhimScheduler
from ..picker import TIER_OWN, Choice, Option, Variety
from ..seams.face import Face

log = logging.getLogger(__name__)

NOISE_RESEED_S = 3600.0
LEVEL_LOG_STEP = 0.5
LEVEL_PUSH_STEP = 0.2


class Creative:
    def __init__(self, chaos: Chaos, face: Face, decks: IdeaDecks, blackbox: BlackBox, start: float, acts=None, studio=None):
        self.chaos = chaos
        self.face = face
        self.decks = decks
        self.blackbox = blackbox
        self.acts = acts
        self.studio = studio
        self.recent = RecentActions()
        self.whims = WhimScheduler(chaos.stream("whims"), start) if chaos.enabled else None
        self.upset_until = -math.inf
        self._logged: float | None = None
        self._pushed: float | None = None
        self._noise_seed: int | None = None
        self._noise_at = -math.inf
        self._task: asyncio.Task | None = None

    @property
    def enabled(self) -> bool:
        return self.chaos.enabled

    @property
    def level(self) -> float:
        return self.chaos.level

    def update(self, inputs: DialInputs, mono: float) -> float:
        level = self.chaos.update(inputs)
        if not self.enabled:
            return level
        if self._logged is None or abs(level - self._logged) >= LEVEL_LOG_STEP:
            self._logged = level
            self.blackbox.record("chaos_level", **self.chaos.explain())
        reseed = self._noise_seed is None or mono - self._noise_at >= NOISE_RESEED_S
        if reseed:
            self._noise_seed = self.chaos.stream("motion").getrandbits(31)
            self._noise_at = mono
        if reseed or self._pushed is None or abs(level - self._pushed) >= LEVEL_PUSH_STEP:
            self._pushed = level
            self.face.motion(level, self.chaos.motion().as_dict(), self._noise_seed)
        return level

    def variety(self, options: list[Option], now: float) -> Variety | None:
        knobs = self.chaos.choices()
        if knobs is None:
            return None
        own = [option.key for option in options if option.tier == TIER_OWN]
        return Variety(knobs.spread, knobs.top_k, self.recent.bonuses(own, now, knobs.novelty))

    def rng(self, fallback):
        return self.chaos.stream("choices") if self.enabled else fallback

    def chose(self, choice: Choice | None, now: float) -> None:
        if choice is not None and choice.tier == TIER_OWN:
            self.recent.did(choice.chosen.key, now)

    def idea_line(self, kind: str = "talk") -> str:
        cards = self.chaos.cards(self.decks, kind)
        if not cards:
            return ""
        self.blackbox.record("idea_card", purpose=kind, cards=[card.as_dict() for card in cards])
        return card_text(cards) + " (use it only if it fits)."

    def someone_upset(self, until: float) -> None:
        self.upset_until = max(self.upset_until, until)

    @property
    def whim_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def maybe_whim(self, ctx: WhimContext) -> Whim | None:
        if not self.enabled or self.whims is None or self.acts is None:
            return None
        ctx = replace(ctx, busy=ctx.busy or self.whim_running, someone_upset=ctx.someone_upset or ctx.now < self.upset_until, available=self.acts.available())
        whim = self.whims.check(ctx, self.chaos.whim_rate())
        if whim is None:
            return None
        self.blackbox.record("whim", whim=whim.kind, draw=whim.draw, level=round(self.level, 2))
        self._task = asyncio.ensure_future(self._run(whim))
        return whim

    async def _run(self, whim: Whim) -> None:
        try:
            result = await self.acts.run(whim.kind)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log.exception("whim %s failed", whim.kind)
            result = {"ok": False, "error": str(error)}
        self.blackbox.record("whim_done", whim=whim.kind, result=result)

    def dream(self, night: str, quiet: bool, docked: bool) -> dict | None:
        if not self.enabled or self.studio is None or not dream_allowed(quiet, docked):
            return None
        return self.studio.dream(night)

    async def close(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
