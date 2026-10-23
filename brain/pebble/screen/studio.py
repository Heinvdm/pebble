import logging
from typing import Callable

from ..clock import Clock, iso
from .gallery import Gallery, GalleryError, clean_name
from .generator import SceneGenerator
from .mutate import mutate, remix
from .parse import Scene
from .stage import SceneStage

log = logging.getLogger(__name__)

DOODLE_HOLD_S = 5.0
NAMES_SHOWN = 12


class Studio:
    def __init__(
        self,
        gallery: Gallery,
        stage: SceneStage,
        generator: SceneGenerator,
        clock: Clock,
        stream: Callable[[str], object] | None = None,
        level: Callable[[], float] = lambda: 0.0,
        record: Callable[..., None] = lambda kind, **data: None,
    ):
        self.gallery = gallery
        self.stage = stage
        self.generator = generator
        self.clock = clock
        self.stream = stream
        self.level = level
        self.record = record

    def names(self) -> list[str]:
        return self.gallery.names()

    def gallery_line(self) -> str:
        names = self.names()
        if not names:
            return ""
        shown = ", ".join(names[-NAMES_SHOWN:])
        more = f" and {len(names) - NAMES_SHOWN} more" if len(names) > NAMES_SHOWN else ""
        return f"Your drawings: {shown}{more}."

    def _vary(self, name: str, scene: Scene) -> tuple[str, Scene]:
        if self.stream is None:
            return name, scene
        varied = mutate(scene, self.stream("mutation"), self.level())
        if varied.text() == scene.text():
            return name, scene
        saved = self.gallery.variant(name, varied, iso(self.clock.now()))
        return saved, varied

    async def draw(self, subject: str, name: str | None = None, mode: str = "full", seconds: float = 8.0) -> dict:
        drawn = await self.generator.draw(subject, mode, seconds, name or subject)
        self.record(
            "scene_drawn",
            subject=subject,
            source=drawn.source,
            lines=len(drawn.scene.lines),
            rejected=len(drawn.scene.rejected),
            first_line_s=None if drawn.first_line_s is None else round(drawn.first_line_s, 3),
            seconds=round(drawn.seconds, 3),
            cards=[card.id for card in drawn.cards],
            error=drawn.error,
        )
        if not drawn.scene:
            fallback = self.gallery.find(subject)
            if fallback is not None:
                shown = await self.show(fallback, mode, seconds)
                shown["note"] = f"could not draw something new ({drawn.error}); showed {fallback} from the gallery instead"
                return shown
            return {"ok": False, "error": f"could not draw that: {drawn.error}"}
        result = {"drawn": drawn.scene.text(), "lines": len(drawn.scene.lines), "by": drawn.source, "seconds": round(drawn.seconds, 1)}
        if drawn.cards:
            result["idea"] = "; ".join(card.text for card in drawn.cards)
        if drawn.error:
            result["note"] = drawn.error
        if name:
            try:
                result["saved_as"] = self.gallery.save(name, drawn.scene, "drawn", iso(self.clock.now()), about=subject)
            except GalleryError as error:
                result["not_saved"] = str(error)
        return result

    async def show(self, name: str, mode: str = "full", seconds: float = 8.0, vary: bool = False) -> dict:
        key = clean_name(name)
        scene = self.gallery.get(key)
        if scene is None or not scene:
            names = self.names()
            return {"ok": False, "error": f"there is no drawing called {name!r}", "drawings": names[-NAMES_SHOWN:]}
        shown_name = key
        if vary:
            shown_name, scene = self._vary(key, scene)
        await self.stage.play(scene, mode, seconds, shown_name)
        self.gallery.shown(shown_name)
        return {"showing": shown_name, "lines": len(scene.lines), "varied": shown_name != key}

    async def doodle(self, hold_s: float = DOODLE_HOLD_S) -> dict:
        names = self.names()
        if not names or self.stream is None:
            return {"ok": False, "error": "no drawings to doodle with"}
        name = self.stream("whims").choice(names)
        vary = self.stream("mutation").random() < min(0.9, 0.1 + self.level() / 12.0)
        return await self.show(name, "overlay", hold_s, vary)

    def dream(self, night: str) -> dict | None:
        names = self.names()
        if len(names) < 2 or self.stream is None:
            return None
        stream = self.stream("dream")
        first = stream.choice(names)
        second = stream.choice([n for n in names if n != first])
        mixed = remix(self.gallery.get(first), self.gallery.get(second))
        if not mixed:
            return None
        try:
            saved = self.gallery.save(f"dream-{night}", mixed, "dream", iso(self.clock.now()), parent=first, about=f"a dream of {first} and {second}")
        except GalleryError as error:
            log.warning("dream not kept: %s", error)
            return None
        report = {"saved_as": saved, "from": [first, second], "lines": len(mixed.lines)}
        self.record("dream_remix", **report)
        return report
