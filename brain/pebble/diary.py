from .clock import Clock, iso
from .respect import harsh
from .selfstore import SelfStore

DIARY = "diary.jsonl"


class Diary:
    def __init__(self, store: SelfStore, clock: Clock):
        self.store = store
        self.clock = clock
        self.setup = False
        self.on_write = lambda entry: None

    def write(self, text: str, kind: str = "note") -> dict:
        now = self.clock.now()
        line = " ".join(text.split())[:300]
        if harsh(line):
            line = "I held back a line that was not kind to something alive."
        entry = {"at": iso(now), "day": self.clock.local(now).date().isoformat(), "kind": kind, "text": line}
        if self.setup:
            entry["setup"] = True
        self.store.append(DIARY, entry)
        self.on_write(entry)
        return entry

    def recent(self, count: int = 20) -> list[dict]:
        return self.store.read_lines(DIARY, count)

    def on_day(self, day: str) -> list[dict]:
        return [entry for entry in self.store.read_lines(DIARY) if entry.get("day") == day]

    def has_kind(self, kind: str) -> bool:
        return any(entry.get("kind") == kind for entry in self.store.read_lines(DIARY))
