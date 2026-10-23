import logging
import math
from dataclasses import dataclass, field
from typing import Protocol

log = logging.getLogger(__name__)

FACES = (
    "neutral",
    "happy",
    "curious",
    "thinking",
    "sleepy",
    "sad",
    "surprised",
    "scared",
    "grumpy",
    "love",
    "dizzy",
    "mischief",
)
TOUCH_KINDS = ("tap", "stroke", "hold")
ALARM_LETTERS = 8
SCENE_MODES = ("full", "overlay")


def _unit(value, low: float, high: float, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number):
        return fallback
    return max(low, min(high, number))


@dataclass(frozen=True)
class Touch:
    x: float
    y: float
    kind: str = "tap"

    @classmethod
    def from_dict(cls, data) -> "Touch | None":
        if not isinstance(data, dict):
            return None
        kind = str(data.get("kind", "tap"))
        if kind not in TOUCH_KINDS:
            return None
        x, y = data.get("x"), data.get("y")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (x, y)):
            return None
        return cls(_unit(x, 0.0, 1.0), _unit(y, 0.0, 1.0), kind)


@dataclass
class FaceState:
    expression: str = "neutral"
    valence: float = 0.0
    arousal: float = 0.0
    fear: float = 0.0
    gaze: tuple[float, float] = (0.0, 0.0)
    talk: float = 0.0
    asleep: bool = False
    chaos: float = 0.0
    noise_seed: int = 1
    motion: dict = field(default_factory=dict)
    attend: bool = False
    alarm: str = ""

    def as_dict(self) -> dict:
        return {
            "expression": self.expression,
            "valence": round(self.valence, 3),
            "arousal": round(self.arousal, 3),
            "fear": round(self.fear, 2),
            "gaze": [round(self.gaze[0], 3), round(self.gaze[1], 3)],
            "talk": round(self.talk, 3),
            "asleep": self.asleep,
            "chaos": round(self.chaos, 2),
            "noise_seed": self.noise_seed,
            "motion": dict(self.motion),
            "attend": self.attend,
            "alarm": self.alarm,
        }

    def set_expression(self, expression: str) -> bool:
        expression = expression if expression in FACES else "neutral"
        changed = expression != self.expression
        self.expression = expression
        return changed

    def set_feel(self, valence, arousal, fear, asleep) -> bool:
        new = (_unit(valence, -1.0, 1.0), _unit(arousal, -1.0, 1.0), _unit(fear, 0.0, 10.0), bool(asleep))
        old = (self.valence, self.arousal, self.fear, self.asleep)
        self.valence, self.arousal, self.fear, self.asleep = new
        return new[3] != old[3] or any(abs(a - b) >= 0.02 for a, b in zip(new[:2], old[:2])) or abs(new[2] - old[2]) >= 0.1

    def set_motion(self, chaos, motion: dict, noise_seed: int) -> bool:
        new = (round(_unit(chaos, 0.0, 10.0), 2), dict(motion or {}), int(noise_seed))
        changed = new != (self.chaos, self.motion, self.noise_seed)
        self.chaos, self.motion, self.noise_seed = new
        return changed

    def set_talk(self, loudness) -> bool:
        value = _unit(loudness, 0.0, 1.0)
        changed = abs(value - self.talk) >= 0.01
        self.talk = value
        return changed

    def set_attend(self, on) -> bool:
        changed = bool(on) != self.attend
        self.attend = bool(on)
        return changed

    def set_alarm(self, text) -> bool:
        word = alarm_word(text)
        changed = word != self.alarm
        self.alarm = word
        return changed

    def set_gaze(self, x, y) -> bool:
        new = (_unit(x, -1.0, 1.0), _unit(y, -1.0, 1.0))
        changed = new != self.gaze
        self.gaze = new
        return changed


class Face(Protocol):
    current: str

    def show(self, expression: str) -> None: ...

    def feel(self, valence: float, arousal: float, fear: float, asleep: bool) -> None: ...

    def motion(self, chaos: float, params: dict, noise_seed: int) -> None: ...

    def talk(self, loudness: float) -> None: ...

    def gaze(self, x: float, y: float) -> None: ...

    def scene_begin(self, scene_id: str, mode: str, hold_s: float, title: str = "") -> None: ...

    def scene_line(self, scene_id: str, index: int, element: dict, text: str) -> None: ...

    def scene_end(self, scene_id: str) -> None: ...

    def scene_clear(self) -> None: ...

    def alarm(self, text: str) -> None: ...


def alarm_word(text) -> str:
    kept = "".join(ch for ch in str(text or "").upper() if ch.isascii() and (ch.isalnum() or ch == " "))
    return " ".join(kept.split())[:ALARM_LETTERS].strip()


class LogFace:
    def __init__(self):
        self.current = "neutral"
        self.history: list[str] = []
        self.state = FaceState()
        self.scenes: list[dict] = []

    def show(self, expression: str) -> None:
        if expression not in FACES:
            expression = "neutral"
        if expression != self.current:
            log.info("face: %s", expression)
        self.current = expression
        self.state.set_expression(expression)
        self.history.append(expression)
        del self.history[:-50]

    def feel(self, valence: float, arousal: float, fear: float, asleep: bool) -> None:
        self.state.set_feel(valence, arousal, fear, asleep)

    def motion(self, chaos: float, params: dict, noise_seed: int) -> None:
        self.state.set_motion(chaos, params, noise_seed)

    def talk(self, loudness: float) -> None:
        self.state.set_talk(loudness)

    def gaze(self, x: float, y: float) -> None:
        self.state.set_gaze(x, y)

    def attend(self, on: bool) -> None:
        self.state.set_attend(on)

    def alarm(self, text: str) -> None:
        if self.state.set_alarm(text):
            log.info("face alarm: %s", self.state.alarm or "off")

    def scene_begin(self, scene_id: str, mode: str, hold_s: float, title: str = "") -> None:
        log.info("scene %s begins (%s, %ss)%s", scene_id, mode, round(hold_s, 1), f": {title}" if title else "")
        self.scenes.append({"id": scene_id, "mode": mode, "hold": hold_s, "title": title, "lines": [], "ended": False})
        del self.scenes[:-20]

    def scene_line(self, scene_id: str, index: int, element: dict, text: str) -> None:
        log.debug("scene %s line %d: %s", scene_id, index, text)
        for scene in reversed(self.scenes):
            if scene["id"] == scene_id:
                scene["lines"].append(text)
                return

    def scene_end(self, scene_id: str) -> None:
        for scene in reversed(self.scenes):
            if scene["id"] == scene_id:
                scene["ended"] = True
                log.info("scene %s on screen: %s", scene_id, " | ".join(scene["lines"]))
                return

    def scene_clear(self) -> None:
        log.info("scene cleared")


def face_for(valence: float, arousal: float, fear: float, asleep: bool = False) -> str:
    if asleep:
        return "sleepy"
    if fear >= 6:
        return "scared"
    if fear >= 4:
        return "surprised"
    if arousal < -0.5:
        return "sleepy"
    if valence < -0.4:
        return "grumpy" if arousal > 0 else "sad"
    if valence > 0.4 and arousal > 0.3:
        return "happy"
    if arousal > 0.2:
        return "curious"
    return "neutral"
