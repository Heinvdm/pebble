import logging
import time
from typing import Callable

from ..seams.face import FACES, SCENE_MODES, FaceState
from .hub import Hub

log = logging.getLogger(__name__)

UNENDED_SCENE_S = 30.0


class WebFace:
    def __init__(self, hub: Hub, monotonic: Callable[[], float] = time.monotonic):
        self.hub = hub
        self.monotonic = monotonic
        self.state = FaceState()
        self.current = self.state.expression
        self.history: list[str] = []
        self._scene: dict | None = None
        self._attend = False
        self._teach: dict = {"on": False, "steps": [], "pad": False}
        hub.set_replay(self.replay)

    def _face(self) -> dict:
        data = self.state.as_dict()
        data.setdefault("attend", self._attend)
        return data

    def _push(self) -> None:
        self.hub.publish("face", self._face())

    def attend(self, on: bool) -> None:
        on = bool(on)
        if on == self._attend:
            return
        self._attend = on
        if hasattr(self.state, "attend"):
            self.state.attend = on
        self._push()

    def teach(self, on: bool, steps: list, pad: bool) -> None:
        shown = {"on": bool(on), "steps": [str(s)[:60] for s in list(steps or [])[-6:]], "pad": bool(pad and on)}
        if shown == self._teach:
            return
        self._teach = shown
        self.hub.publish("teach", shown)

    def alarm(self, text: str) -> None:
        if self.state.set_alarm(text):
            log.info("face alarm: %s", self.state.alarm or "off")
            self._push()

    def show(self, expression: str) -> None:
        if expression not in FACES:
            expression = "neutral"
        if expression != self.current:
            log.info("face: %s", expression)
        self.current = expression
        self.history.append(expression)
        del self.history[:-50]
        if self.state.set_expression(expression):
            self._push()

    def feel(self, valence: float, arousal: float, fear: float, asleep: bool) -> None:
        if self.state.set_feel(valence, arousal, fear, asleep):
            self._push()

    def motion(self, chaos: float, params: dict, noise_seed: int) -> None:
        if self.state.set_motion(chaos, params, noise_seed):
            self._push()

    def talk(self, loudness: float) -> None:
        if self.state.set_talk(loudness):
            self._push()

    def gaze(self, x: float, y: float) -> None:
        if self.state.set_gaze(x, y):
            self._push()

    def scene_begin(self, scene_id: str, mode: str, hold_s: float, title: str = "") -> None:
        mode = mode if mode in SCENE_MODES else "full"
        hold = max(1.0, min(120.0, float(hold_s)))
        self._scene = {"id": scene_id, "mode": mode, "hold": hold, "title": title, "lines": [], "began": self.monotonic(), "ended": None}
        self.hub.publish("scene", {"op": "begin", "id": scene_id, "mode": mode, "hold": hold, "title": title})

    def scene_line(self, scene_id: str, index: int, element: dict, text: str) -> None:
        line = {"op": "line", "id": scene_id, "index": index, "element": element, "text": text}
        if self._scene is not None and self._scene["id"] == scene_id:
            self._scene["lines"].append(line)
        self.hub.publish("scene", line)

    def scene_end(self, scene_id: str) -> None:
        if self._scene is not None and self._scene["id"] == scene_id:
            self._scene["ended"] = self.monotonic()
        self.hub.publish("scene", {"op": "end", "id": scene_id})

    def scene_clear(self) -> None:
        self._scene = None
        self.hub.publish("scene", {"op": "clear"})

    def scene_remaining(self) -> float | None:
        scene = self._scene
        if scene is None:
            return None
        now = self.monotonic()
        if scene["ended"] is None:
            return None if now - scene["began"] > UNENDED_SCENE_S else scene["hold"]
        left = scene["hold"] - (now - scene["ended"])
        return left if left > 0 else None

    def replay(self) -> list[tuple[str, object]]:
        events: list[tuple[str, object]] = [("face", self._face())]
        if self._teach.get("on"):
            events.append(("teach", dict(self._teach)))
        scene = self._scene
        left = self.scene_remaining()
        if scene is None or left is None:
            return events
        events.append(("scene", {"op": "begin", "id": scene["id"], "mode": scene["mode"], "hold": round(left, 2), "title": scene["title"]}))
        events.extend(("scene", line) for line in list(scene["lines"]))
        if scene["ended"] is not None:
            events.append(("scene", {"op": "end", "id": scene["id"]}))
        return events
