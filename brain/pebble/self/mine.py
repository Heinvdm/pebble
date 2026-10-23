import logging
import re
from typing import Callable

from ..clock import iso
from ..respect import harsh
from ..tact import tactless

log = logging.getLogger(__name__)

ROOT = "mine"
INDEX = "mine/index.json"
WONDERINGS = "mine/wonderings.json"
MOST_FILES = 200
FILE_MOST = 20000
TOTAL_MOST = 2_000_000
TAGS_MOST = 8
WONDERINGS_MOST = 20
SUFFIXES = (".md", ".txt")
NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,47}(/[a-z0-9][a-z0-9_.-]{0,47}){0,2}$")
FEELINGS = re.compile(r"\b(feel|feels|felt|feeling|health|healthy|ill|sick|unwell|sad|angry|upset|scared|lonely|crying|cries|pain|hurt|hurts|doctor|medicine|weight)\b", re.IGNORECASE)


class MineRefused(ValueError):
    pass


def tidy_name(name: str) -> str:
    text = str(name or "").strip().lower().replace("\\", "/").replace(" ", "-")
    text = "/".join(part for part in text.split("/") if part)
    if text and not text.endswith(SUFFIXES):
        text += ".md"
    if not NAME.match(text) or ".." in text:
        raise MineRefused("a name is lower-case letters, numbers, dashes and dots, at most three folders deep")
    return text


def _words_problem(text: str) -> str | None:
    if harsh(text):
        return "not kept: it would be unkind to something alive"
    if tactless(text):
        return "not kept: it remarks on how someone looks"
    return None


class Mine:
    def __init__(self, store, clock, record: Callable[..., None] | None = None, names: Callable[[], list[str]] | None = None):
        self.store = store
        self.clock = clock
        self.record = record or (lambda kind, **data: None)
        self.names = names or (lambda: [])
        data = store.read(INDEX, {}) or {}
        self.index: dict[str, dict] = {str(k): dict(v) for k, v in (data.get("files") or {}).items() if isinstance(v, dict)}
        found = store.read(WONDERINGS, {}) or {}
        self.wonderings: list[dict] = [dict(w) for w in found.get("items") or [] if isinstance(w, dict) and w.get("id")]
        self.counter = int(found.get("counter") or 0)

    def _save(self) -> None:
        self.store.write(INDEX, {"format": 1, "files": dict(sorted(self.index.items()))})

    def _save_wonderings(self) -> None:
        self.store.write(WONDERINGS, {"format": 1, "counter": self.counter, "items": self.wonderings})

    def used(self) -> int:
        return sum(int(entry.get("size") or 0) for entry in self.index.values())

    def files(self, prefix: str = "", tag: str = "") -> list[dict]:
        prefix = str(prefix or "").strip().lower()
        out = []
        for name, entry in sorted(self.index.items()):
            if prefix and not name.startswith(prefix):
                continue
            if tag and tag.lower() not in entry.get("tags", []):
                continue
            out.append({"name": name, **{k: entry[k] for k in ("size", "tags", "pinned", "at") if k in entry}})
        return out

    def read(self, name: str) -> str:
        name = tidy_name(name)
        if name not in self.index:
            raise MineRefused(f"there is nothing called {name} in my folder")
        return self.store.read_bytes(f"{ROOT}/{name}", b"").decode("utf-8", errors="replace")

    def write(self, name: str, text: str) -> dict:
        name = tidy_name(name)
        text = str(text or "").replace("\r\n", "\n").strip() + "\n"
        problem = _words_problem(text)
        if problem:
            raise MineRefused(problem)
        size = len(text.encode("utf-8"))
        if size > FILE_MOST:
            raise MineRefused(f"one file holds at most {FILE_MOST} characters")
        before = self.index.get(name)
        if before is None and len(self.index) >= MOST_FILES:
            raise MineRefused(f"my folder holds at most {MOST_FILES} things; let one go first")
        if self.used() - int((before or {}).get("size") or 0) + size > TOTAL_MOST:
            raise MineRefused("my folder is full; let something go first")
        self.store.write_bytes(f"{ROOT}/{name}", text.encode("utf-8"))
        entry = dict(before or {"tags": [], "pinned": False})
        entry.update({"size": size, "at": iso(self.clock.now())})
        self.index[name] = entry
        self._save()
        self.record("mine_changed", action="changed" if before else "made", name=name)
        return {"name": name, "size": size, "new": before is None}

    def rename(self, old: str, new: str) -> dict:
        old, new = tidy_name(old), tidy_name(new)
        if old not in self.index:
            raise MineRefused(f"there is nothing called {old} in my folder")
        if new in self.index:
            raise MineRefused(f"{new} is already taken")
        data = self.store.read_bytes(f"{ROOT}/{old}", b"")
        self.store.write_bytes(f"{ROOT}/{new}", data)
        self.store.remove(f"{ROOT}/{old}")
        self.index[new] = self.index.pop(old)
        self._save()
        self.record("mine_changed", action="renamed", name=new, before=old, after=new)
        return {"name": new, "was": old}

    def tag(self, name: str, tags) -> dict:
        name = tidy_name(name)
        if name not in self.index:
            raise MineRefused(f"there is nothing called {name} in my folder")
        words = [re.sub(r"[^a-z0-9-]", "", str(t).strip().lower()) for t in (tags.split(",") if isinstance(tags, str) else tags or [])]
        words = list(dict.fromkeys(w for w in words if w))[:TAGS_MOST]
        self.index[name]["tags"] = words
        self._save()
        self.record("mine_changed", action="tagged", name=name, after=words)
        return {"name": name, "tags": words}

    def pin(self, name: str, on: bool = True) -> dict:
        name = tidy_name(name)
        if name not in self.index:
            raise MineRefused(f"there is nothing called {name} in my folder")
        self.index[name]["pinned"] = bool(on)
        self._save()
        self.record("mine_changed", action="pinned" if on else "unpinned", name=name)
        return {"name": name, "pinned": bool(on)}

    def delete(self, name: str) -> dict:
        name = tidy_name(name)
        entry = self.index.get(name)
        if entry is None:
            raise MineRefused(f"there is nothing called {name} in my folder")
        if entry.get("pinned"):
            raise MineRefused(f"{name} is pinned; unpin it first")
        self.store.remove(f"{ROOT}/{name}")
        del self.index[name]
        self._save()
        self.record("mine_changed", action="let go", name=name)
        return {"name": name, "gone": True}

    def forget(self, person_id: str, names: list[str]) -> int:
        words = [n.lower() for n in names if n and len(n) > 1]
        gone = [w for w in self.wonderings if any(re.search(rf"\b{re.escape(n)}\b", w["text"].lower()) for n in words)]
        for item in gone:
            self.wonderings.remove(item)
        if gone:
            self._save_wonderings()
        return len(gone)

    def open_wonderings(self) -> list[dict]:
        return [w for w in self.wonderings if w.get("open", True)]

    def wonder(self, text: str, why: str = "") -> dict:
        text = " ".join(str(text or "").split())[:160]
        if not text:
            raise MineRefused("a wondering needs words")
        problem = _words_problem(text)
        if problem:
            raise MineRefused(problem)
        lowered = text.lower()
        if FEELINGS.search(text) and any(n and len(n) > 1 and re.search(rf"\b{re.escape(n.lower())}\b", lowered) for n in self.names()):
            raise MineRefused("I don't wonder about how a named person feels or how well they are")
        if any(w["text"].lower() == lowered for w in self.open_wonderings()):
            return {"wondering": text, "already": True}
        open_now = self.open_wonderings()
        if len(open_now) >= WONDERINGS_MOST:
            oldest = min(open_now, key=lambda w: w.get("at") or "")
            self.wonderings.remove(oldest)
        self.counter += 1
        item = {"id": f"w{self.counter}", "text": text, "why": " ".join(str(why or "").split())[:160], "at": iso(self.clock.now()), "open": True}
        self.wonderings.append(item)
        self.wonderings = self.wonderings[-(WONDERINGS_MOST * 3) :]
        self._save_wonderings()
        self.record("wondering", text=text, why=item["why"])
        return {"wondering": text, "id": item["id"]}

    def answered(self, wondering_id: str, answer: str = "") -> dict:
        item = next((w for w in self.wonderings if w["id"] == str(wondering_id)), None)
        if item is None:
            raise MineRefused("there is no wondering with that id")
        item["open"] = False
        item["answer"] = " ".join(str(answer or "").split())[:200]
        self._save_wonderings()
        return {"id": item["id"], "answered": True}
