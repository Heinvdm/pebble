import asyncio
import logging
import time
from contextlib import aclosing
from dataclasses import dataclass, replace
from typing import Callable

from ..chaos.ideas import Card, card_text
from ..mind.base import CallOptions, Mind, MindUnavailable
from .director import SceneDirector
from .grammar import scene_grammar
from .guide import scene_guide, scene_request
from .parse import Scene
from .stage import SceneStage

log = logging.getLogger(__name__)

TIMEOUT_S = 25.0
MAX_TOKENS = 140


@dataclass(frozen=True)
class Drawn:
    scene: Scene
    scene_id: str | None
    source: str
    seconds: float
    first_line_s: float | None
    cards: tuple[Card, ...] = ()
    error: str | None = None


class SceneGenerator:
    def __init__(
        self,
        minds: list[tuple[str, Mind]],
        stage: SceneStage,
        options: Callable[[str], CallOptions | None] = lambda kind: None,
        cards: Callable[[str], list[Card]] = lambda kind: [],
        timeout_s: float = TIMEOUT_S,
        max_tokens: int = MAX_TOKENS,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.minds = [(name, mind) for name, mind in minds if mind is not None]
        self.stage = stage
        self.options = options
        self.cards = cards
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.monotonic = monotonic

    def messages(self, subject: str, cards: list[Card]) -> list[dict]:
        return [
            {"role": "system", "content": scene_guide()},
            {"role": "user", "content": scene_request(subject, card_text(cards))},
        ]

    def call_options(self) -> CallOptions:
        options = self.options("drawing") or CallOptions("creative")
        return replace(options, grammar=scene_grammar())

    async def draw(self, subject: str, mode: str = "full", hold_s: float = 8.0, title: str = "") -> Drawn:
        cards = list(self.cards("drawing"))
        messages = self.messages(subject, cards)
        options = self.call_options()
        start = self.monotonic()
        problems = []
        for name, mind in self.minds:
            drawn = await self._attempt(name, mind, messages, options, mode, hold_s, title or subject, start, tuple(cards))
            if drawn.scene:
                return drawn
            problems.append(f"{name}: {drawn.error or 'drew nothing'}")
        return Drawn(Scene(), None, "none", self.monotonic() - start, None, tuple(cards), "; ".join(problems) or "there is no mind to draw with")

    async def _attempt(self, name, mind, messages, options, mode, hold_s, title, start, cards) -> Drawn:
        state = {"id": None, "first": None}

        def on_line(line) -> None:
            if state["id"] is None:
                state["id"] = self.stage.begin(mode, hold_s, title)
                state["first"] = self.monotonic() - start
            self.stage.line(state["id"], line)

        director = SceneDirector(on_line)
        error = None
        try:
            async with asyncio.timeout(self.timeout_s):
                async with aclosing(mind.stream(messages, purpose="scene", max_tokens=self.max_tokens, options=options)) as pieces:
                    async for piece in pieces:
                        director.feed(piece)
                        if director.full:
                            break
        except MindUnavailable as problem:
            error = str(problem) or "the mind is unavailable"
        except TimeoutError:
            error = f"timed out after {self.timeout_s:g} s"
        scene = director.finish()
        if state["id"] is not None:
            self.stage.end(state["id"])
        if scene.rejected:
            log.info("scene lines rejected from %s: %s", name, scene.rejected[:3])
        return Drawn(scene, state["id"], name, self.monotonic() - start, state["first"], cards, error)
