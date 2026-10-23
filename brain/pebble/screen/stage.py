import asyncio
import itertools
from dataclasses import dataclass, field

from ..seams.face import SCENE_MODES, Face
from .parse import Scene, SceneLine

MIN_HOLD_S = 2.0
MAX_HOLD_S = 60.0


@dataclass
class OnScreen:
    id: str
    mode: str
    hold_s: float
    title: str
    lines: list[str] = field(default_factory=list)
    ended: bool = False


class SceneStage:
    def __init__(self, face: Face, prefix: str = "s"):
        self.face = face
        self._ids = itertools.count(1)
        self.prefix = prefix
        self.current: OnScreen | None = None

    def begin(self, mode: str = "full", hold_s: float = 8.0, title: str = "") -> str:
        mode = mode if mode in SCENE_MODES else "full"
        hold = max(MIN_HOLD_S, min(MAX_HOLD_S, float(hold_s)))
        scene_id = f"{self.prefix}{next(self._ids)}"
        self.current = OnScreen(scene_id, mode, hold, title[:60])
        self.face.scene_begin(scene_id, mode, hold, title[:60])
        return scene_id

    def line(self, scene_id: str, line: SceneLine) -> None:
        if self.current is None or self.current.id != scene_id:
            return
        index = len(self.current.lines)
        text = line.text()
        self.current.lines.append(text)
        self.face.scene_line(scene_id, index, line.as_dict(), text)

    def end(self, scene_id: str) -> None:
        if self.current is not None and self.current.id == scene_id and not self.current.ended:
            self.current.ended = True
            self.face.scene_end(scene_id)

    def clear(self) -> None:
        self.current = None
        self.face.scene_clear()

    async def play(self, scene: Scene, mode: str = "full", hold_s: float = 8.0, title: str = "", pace_s: float = 0.0) -> str:
        scene_id = self.begin(mode, hold_s, title)
        for line in scene.lines:
            if pace_s > 0:
                await asyncio.sleep(pace_s)
            self.line(scene_id, line)
        self.end(scene_id)
        return scene_id
