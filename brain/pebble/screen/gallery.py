import re
from pathlib import Path
from typing import Callable

from ..selfstore import SelfStore, read_json
from .director import parse_scene
from .parse import Scene

GALLERY = "gallery.json"
TEMPLATE = Path(__file__).resolve().parent.parent / "self_template" / GALLERY
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
SOURCES = ("curated", "drawn", "variant", "dream")
MAX_SCENES = 120
KEPT = frozenset({"curated", "drawn"})


class GalleryError(ValueError):
    pass


def clean_name(text: str) -> str:
    name = re.sub(r"[^a-z0-9-]+", "-", str(text).strip().lower()).strip("-")
    return name[:32].strip("-")


class Gallery:
    def __init__(self, data: dict | None = None, saver: Callable[[dict], None] | None = None):
        data = data or {}
        self.scenes: dict[str, dict] = {}
        for name, entry in (data.get("scenes") or {}).items():
            if isinstance(entry, dict) and NAME.match(str(name)) and isinstance(entry.get("text"), str):
                self.scenes[name] = dict(entry)
        self._saver = saver

    @classmethod
    def open(cls, store: SelfStore) -> "Gallery":
        data = store.read(GALLERY, None)
        if data is None:
            data = read_json(TEMPLATE, {})
        return cls(data, lambda payload: store.write(GALLERY, payload))

    @classmethod
    def template(cls) -> "Gallery":
        return cls(read_json(TEMPLATE, {}))

    def names(self) -> list[str]:
        return list(self.scenes)

    def __contains__(self, name: str) -> bool:
        return name in self.scenes

    def get(self, name: str) -> Scene | None:
        entry = self.scenes.get(name)
        return None if entry is None else parse_scene(entry["text"])

    def entry(self, name: str) -> dict | None:
        entry = self.scenes.get(name)
        return None if entry is None else dict(entry)

    def _free_name(self, base: str) -> str:
        if base not in self.scenes:
            return base
        counter = 2
        while True:
            suffix = f"-{counter}"
            candidate = base[: 32 - len(suffix)] + suffix
            if candidate not in self.scenes:
                return candidate
            counter += 1

    def save(self, name: str, scene: Scene, source: str, at: str | None = None, parent: str | None = None, about: str = "") -> str:
        base = clean_name(name)
        if not base or not NAME.match(base):
            raise GalleryError("a drawing needs a short name made of letters, numbers and dashes")
        if source not in SOURCES:
            raise GalleryError(f"unknown source {source}")
        if not scene.lines:
            raise GalleryError("an empty drawing is not kept")
        final = self._free_name(base)
        self.scenes[final] = {"text": scene.text(), "source": source, "parent": parent, "made_at": at, "about": about[:80], "shown": 0}
        self._prune()
        self._save()
        return final

    def variant(self, name: str, varied: Scene, at: str | None = None) -> str:
        if name not in self.scenes:
            raise GalleryError(f"there is no drawing called {name}")
        root = self.scenes[name].get("parent") or name
        base = f"{root[:26]}-v"
        number = 1
        while f"{base}{number}" in self.scenes:
            number += 1
        return self.save(f"{base}{number}", varied, "variant", at, parent=root, about=self.scenes[name].get("about", ""))

    def remove(self, name: str) -> bool:
        key = clean_name(name)
        if key not in self.scenes:
            return False
        del self.scenes[key]
        self._save()
        return True

    def shown(self, name: str) -> None:
        if name in self.scenes:
            self.scenes[name]["shown"] = int(self.scenes[name].get("shown", 0)) + 1
            self._save()

    def find(self, words: str) -> str | None:
        wanted = {w for w in re.split(r"[^a-z0-9]+", words.lower()) if len(w) > 2}
        best, best_hits = None, 0
        for name, entry in self.scenes.items():
            have = set(re.split(r"[^a-z0-9]+", f"{name} {entry.get('about', '')}".lower()))
            hits = len(wanted & have)
            if hits > best_hits:
                best, best_hits = name, hits
        return best

    def _prune(self) -> None:
        extra = len(self.scenes) - MAX_SCENES
        if extra <= 0:
            return
        disposable = [name for name, entry in self.scenes.items() if entry.get("source") not in KEPT]
        for name in disposable[:extra]:
            del self.scenes[name]

    def to_dict(self) -> dict:
        return {"format": 1, "scenes": self.scenes}

    def _save(self) -> None:
        if self._saver is not None:
            self._saver(self.to_dict())
