from .bridge import as_bytes, as_json, require

RATE = 16000


class SoundTap:
    def __init__(self, bridge=None):
        self._bridge = bridge
        self.position: int | None = None
        self.skipped = 0

    def bridge(self):
        return self._bridge if self._bridge is not None else require("the sound tap")

    def start(self) -> None:
        self.bridge().soundTap(True)
        self.position = None

    def stop(self) -> None:
        self.bridge().soundTap(False)

    def info(self) -> dict:
        found = as_json(self.bridge().soundInfo(), {})
        return found if isinstance(found, dict) else {}

    def read(self, max_seconds: float = 1.0) -> bytes:
        info = self.info()
        total = int(info.get("total", 0))
        oldest = total - int(info.get("kept", 0))
        if self.position is None:
            self.position = total
        if self.position < oldest:
            self.skipped += oldest - self.position
            self.position = oldest
        data = as_bytes(self.bridge().soundRead(self.position, int(max(0.0, max_seconds) * RATE)))
        self.position += len(data) // 2
        return data
