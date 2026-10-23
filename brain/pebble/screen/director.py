from typing import Callable

from .elements import MAX_LINES
from .parse import Scene, SceneError, SceneLine, clean_line, parse_line

MAX_BUFFER = 400


class SceneDirector:
    def __init__(
        self,
        on_line: Callable[[SceneLine], None] | None = None,
        on_reject: Callable[[str, str], None] | None = None,
        max_lines: int = MAX_LINES,
    ):
        self.on_line = on_line or (lambda line: None)
        self.on_reject = on_reject or (lambda text, why: None)
        self.max_lines = max_lines
        self.buffer = ""
        self.lines: list[SceneLine] = []
        self.rejected: list[tuple[str, str]] = []
        self.finished = False

    @property
    def full(self) -> bool:
        return len(self.lines) >= self.max_lines

    def feed(self, chunk: str) -> list[SceneLine]:
        if self.finished or not chunk:
            return []
        self.buffer += chunk.replace("\r", "")
        made = []
        while "\n" in self.buffer:
            raw, self.buffer = self.buffer.split("\n", 1)
            line = self._take(raw)
            if line is not None:
                made.append(line)
        if len(self.buffer) > MAX_BUFFER:
            self._reject(self.buffer[:60], "line too long")
            self.buffer = ""
        return made

    def finish(self) -> Scene:
        if not self.finished and self.buffer.strip():
            self._take(self.buffer)
        self.buffer = ""
        self.finished = True
        return self.scene()

    def scene(self) -> Scene:
        return Scene(tuple(self.lines), tuple(self.rejected))

    def _reject(self, text: str, why: str) -> None:
        self.rejected.append((text, why))
        self.on_reject(text, why)

    def _take(self, raw: str) -> SceneLine | None:
        text = clean_line(raw)
        if not text:
            return None
        if self.full:
            self._reject(text, "too many lines")
            return None
        try:
            line = parse_line(text)
        except SceneError as error:
            self._reject(text, str(error))
            return None
        self.lines.append(line)
        self.on_line(line)
        return line


def parse_scene(text: str, max_lines: int = MAX_LINES) -> Scene:
    director = SceneDirector(max_lines=max_lines)
    director.feed(str(text))
    return director.finish()
