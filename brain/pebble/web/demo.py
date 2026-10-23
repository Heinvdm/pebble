import asyncio
import logging
import math

from ..chaos.engine import Chaos
from ..chaos.levers import motion_knobs
from ..screen.gallery import Gallery
from ..screen.stage import SceneStage
from ..seams.face import FACES, Face, Touch

log = logging.getLogger(__name__)

FEELS = {
    "neutral": (0.1, 0.0, 0.0),
    "happy": (0.8, 0.5, 0.0),
    "curious": (0.3, 0.4, 0.0),
    "thinking": (0.1, 0.1, 0.0),
    "sleepy": (0.1, -0.8, 0.0),
    "sad": (-0.7, -0.3, 0.0),
    "surprised": (0.0, 0.8, 4.5),
    "scared": (-0.5, 0.9, 7.0),
    "grumpy": (-0.6, 0.4, 0.0),
    "love": (0.9, 0.3, 0.0),
    "dizzy": (0.0, 0.6, 1.0),
    "mischief": (0.5, 0.5, 0.0),
}
LEVELS = (2.0, 5.0, 8.5)
EXPRESSION_S = 2.6
SCENE_EVERY = 4
SCENE_HOLD_S = 6.0
LINE_PACE_S = 0.35


class Demo:
    def __init__(self, face: Face, stage: SceneStage, gallery: Gallery, chaos: Chaos, pace: float = 1.0, levels: tuple[float, ...] = LEVELS):
        self.levels = tuple(levels) or LEVELS
        self.face = face
        self.stage = stage
        self.gallery = gallery
        self.chaos = chaos
        self.pace = max(0.01, pace)
        self.shown = 0
        self.scenes = 0

    async def _wait(self, seconds: float, stop: asyncio.Event) -> bool:
        try:
            await asyncio.wait_for(stop.wait(), seconds * self.pace)
        except asyncio.TimeoutError:
            return False
        return True

    def set_level(self, level: float) -> None:
        self.chaos.pin(level)
        seed = self.chaos.stream("motion").getrandbits(31)
        self.face.motion(level, motion_knobs(level).as_dict(), seed)

    def express(self, name: str, step: int) -> None:
        valence, arousal, fear = FEELS.get(name, (0.0, 0.0, 0.0))
        self.face.feel(valence, arousal, fear, False)
        self.face.show(name)
        self.face.gaze(math.sin(step * 1.7) * 0.6, math.cos(step * 1.3) * 0.4)
        self.shown += 1

    async def scene(self, index: int, stop: asyncio.Event) -> None:
        names = self.gallery.names()
        if not names:
            return
        name = names[index % len(names)]
        scene = self.gallery.get(name)
        if not scene:
            return
        mode = "overlay" if index % 3 == 2 else "full"
        await self.stage.play(scene, mode, SCENE_HOLD_S * self.pace, name, LINE_PACE_S * self.pace)
        self.scenes += 1
        await self._wait(SCENE_HOLD_S + 0.6, stop)

    async def run(self, stop: asyncio.Event) -> None:
        step = 0
        while not stop.is_set():
            self.set_level(self.levels[(step // len(FACES)) % len(self.levels)])
            name = FACES[step % len(FACES)]
            self.express(name, step)
            if step % 5 == 3:
                self.face.talk(0.8)
                if await self._wait(1.2, stop):
                    break
                self.face.talk(0.0)
            if await self._wait(EXPRESSION_S, stop):
                break
            step += 1
            if step % SCENE_EVERY == 0:
                self.face.gaze(0.0, 0.0)
                await self.scene(step // SCENE_EVERY - 1, stop)
        self.face.talk(0.0)

    def touched(self, touch: Touch) -> None:
        self.face.gaze(touch.x * 2 - 1, touch.y * 2 - 1)
        self.face.show("love" if touch.kind != "tap" else "happy")
