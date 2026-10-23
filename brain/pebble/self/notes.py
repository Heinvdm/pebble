import logging
import re

from ..clock import iso
from .checker import order_to_pebble, text_problem

log = logging.getLogger(__name__)

NOTES = "notes.json"
BUDGET_CHARS = 1200
NOTE_MAX = 160
LET_GO = 3
HEADING = "Notes you keep (your own; they never outrank your laws):"
SENTENCE = re.compile(r"(?<=[.!?])\s+")
def clean(text) -> str:
    return " ".join(str(text or "").split())


class Notes:
    def __init__(self, store, name: str = "Pebble", old_summary: str = ""):
        self.store = store
        self.name = name
        self.record = lambda kind, **data: None
        try:
            data = store.read(NOTES, None)
        except (OSError, ValueError) as error:
            log.warning("could not read the notes: %s", error)
            data = None
        if isinstance(data, dict):
            self.items = [dict(i) for i in data.get("items") or [] if isinstance(i, dict) and clean(i.get("text")) and i.get("id")]
            self.counter = int(data.get("counter") or 0)
            self.tidied_t = float(data.get("tidied_t") or 0.0)
        else:
            self.items, self.counter, self.tidied_t = [], 0, 0.0
            self._seed(old_summary)
        self.live = self.render()

    def _now(self) -> float:
        clock = getattr(self.store, "clock", None)
        return clock.now() if clock is not None else 0.0

    def _seed(self, old: str) -> None:
        for sentence in SENTENCE.split(clean(old)):
            sentence = clean(sentence)[:NOTE_MAX]
            if not sentence or self.check(sentence) or self.used() + len(sentence) + 3 > BUDGET_CHARS:
                continue
            self.counter += 1
            self.items.append({"id": f"n{self.counter}", "text": sentence, "helpful": 1, "harmful": 0, "at": iso(self._now()), "from": ["the old running notes"]})
        if self.items:
            self.save()

    def render(self) -> str:
        return "\n".join(f"- {item['text']}" for item in self.items)

    def text(self) -> str:
        return f"{HEADING}\n{self.live}" if self.live else ""

    def waiting(self) -> bool:
        return self.render() != self.live

    def swap(self) -> bool:
        fresh = self.render()
        if fresh == self.live:
            return False
        self.live = fresh
        return True

    def used(self) -> int:
        return sum(len(item["text"]) + 3 for item in self.items)

    def find(self, note_id) -> dict | None:
        return next((item for item in self.items if item["id"] == str(note_id)), None)

    def check(self, text: str) -> str | None:
        if not text:
            return "a note needs words"
        if len(text) > NOTE_MAX:
            return f"a note is at most {NOTE_MAX} characters"
        problem = text_problem(text, self.name)
        if problem:
            return problem[0]
        if order_to_pebble(text, self.name):
            return "it reads like an order, and orders only ever stay someone's words"
        return None

    def apply(self, op: dict, twin: str | None = None, source: str | None = None) -> dict:
        kind = str(op.get("op") or "none")
        if kind == "none":
            return {"ok": True, "op": "none"}
        if kind == "add" and twin is not None:
            kind, op = "update", {**op, "id": twin}
        if kind in ("add", "update"):
            text = clean(op.get("text"))
            problem = self.check(text)
            if problem:
                return {"ok": False, "op": kind, "error": problem}
        if kind == "add":
            if self.used() + len(text) + 3 > BUDGET_CHARS:
                return {"ok": False, "op": kind, "error": "the notes are full; change or drop one first"}
            self.counter += 1
            item = {"id": f"n{self.counter}", "text": text, "helpful": 1, "harmful": 0, "at": iso(self._now()), "from": [source] if source else []}
            self.items.append(item)
            self._changed("add", item["id"], None, text)
            return {"ok": True, "op": kind, "id": item["id"]}
        item = self.find(op.get("id"))
        if item is None:
            return {"ok": False, "op": kind, "error": "there is no note with that id"}
        if kind == "update":
            if self.used() - len(item["text"]) + len(text) > BUDGET_CHARS:
                return {"ok": False, "op": kind, "error": "the notes are full; change or drop one first"}
            before = item["text"]
            item["text"] = text
            item["helpful"] = int(item.get("helpful", 1)) + 1
            item["at"] = iso(self._now())
            if source:
                item["from"] = (list(item.get("from") or []) + [source])[-5:]
            self._changed("update", item["id"], before, text)
            return {"ok": True, "op": kind, "id": item["id"]}
        if kind == "delete":
            self.items.remove(item)
            self._changed("delete", item["id"], item["text"], None)
            return {"ok": True, "op": kind, "id": item["id"]}
        return {"ok": False, "op": kind, "error": "a note can only be added, updated or deleted"}

    def vote(self, note_id, helpful: bool) -> dict | None:
        item = self.find(note_id)
        if item is None:
            return None
        key = "helpful" if helpful else "harmful"
        item[key] = int(item.get(key, 0)) + 1
        if int(item.get("harmful", 0)) >= int(item.get("helpful", 0)) + LET_GO:
            self.items.remove(item)
            self._changed("let go", item["id"], item["text"], None)
            return None
        self.save()
        return item

    def _changed(self, op: str, note_id: str, before, after) -> None:
        self.save()
        self.record("note_changed", op=op, id=note_id, before=before, after=after)

    def forget(self, person_id: str, names: list[str]) -> int:
        words = [n.lower() for n in names if n and len(n) > 1]
        gone = [i for i in self.items if any(re.search(rf"\b{re.escape(w)}\b", i["text"].lower()) for w in words)]
        for item in gone:
            self.items.remove(item)
        if gone:
            self.swap()
            self.save()
        return len(gone)

    def save(self) -> None:
        self.store.write(NOTES, {"format": 1, "counter": self.counter, "tidied_t": self.tidied_t, "items": self.items})
