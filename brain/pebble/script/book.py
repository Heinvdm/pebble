import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..clock import from_iso, iso

log = logging.getLogger(__name__)

ROOT = "mine/scripts"
INDEX = f"{ROOT}/index.json"
STARTERS = Path(__file__).resolve().parent / "starters"
LIVE_MOST = 20
VERSIONS_MOST = 10
RETIRE_AFTER_S = 30 * 86400.0
CLOSEST = 3
LIVE = ("live", "trial")
STOP_WORDS = frozenset("a an the to of for and then me you us it him her them is are be do my your our some that this with on in at up down program programs script scripts little".split())
NAMES = (
    (re.compile(r"\b(?:simon says)\b"), "simon says"),
    (re.compile(r"\b(?:red light|green light)\b"), "red light green light"),
    (re.compile(r"\b(?:treasure hunt|treasure)\b"), "treasure hunt"),
    (re.compile(r"\b(?:quiz|trivia)\b"), "quiz"),
    (re.compile(r"\b(?:story|stories)\b"), "story time"),
    (re.compile(r"\b(?:score|scores|points)\b"), "score keeper"),
    (re.compile(r"\b(?:how was (?:your|the) day|check in|check-in|checks in)\b"), "check-in"),
    (re.compile(r"\b(?:tag)\b"), "tag game"),
    (re.compile(r"\b(?:patrol|look round|looks round|look around)\b"), "patrol"),
    (re.compile(r"\b(?:dance|dances|dancing)\b"), "dance"),
    (re.compile(r"\b(?:good morning|morning hello|says hello|say hello|greets?)\b"), "hello"),
)
COUNT = re.compile(r"\b(?:count|counts|counting|how many|how often|tally|number of)\b")
REMIND = re.compile(r"\b(?:remind|reminds|reminder|reminding)\b")
GAME = re.compile(r"\b(?:game|play|plays|playing)\b")
WEAK = frozenset({"water", "walks", "walk", "steps", "laps"})
GENERIC = frozenset({"counter", "reminder", "game", "keeper", "time", "hunt", "says", "check", "in", "hello"})
THING_WORDS = re.compile(r"\b(cat|dog|bird|ball|plants?|keys?|visits?|visitors?|people|doorbell|knocks?|kettle|mail|post|bins?|water|walks?|steps?|laps?|goals?|birds?)\b")


def tag_of(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_")[:40] or "script"


def content(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9']+", str(text or "").lower()) if w not in STOP_WORDS}


def name_for(words: str, about: str = "") -> str:
    said = " ".join(re.findall(r"[a-z0-9' -]+", f"{words} {about}".lower()))
    for pattern, name in NAMES:
        if pattern.search(said):
            thing = THING_WORDS.search(said)
            if name == "hello" and thing is None:
                return "morning hello" if "morning" in said else "hello"
            return name
    found = [w for w in THING_WORDS.findall(said)]
    strong = [w for w in found if w not in WEAK]
    noun = (strong or found or [""])[0]
    noun = noun[:-1] if noun.endswith("s") and noun not in ("glass",) else noun
    if COUNT.search(said):
        return f"{noun} counter" if noun else "counter"
    if REMIND.search(said):
        return f"{noun} reminder" if noun else "reminder"
    if GAME.search(said):
        return f"{noun} game" if noun else "game"
    picked = [w for w in re.findall(r"[a-z]+", about.lower()) if w not in STOP_WORDS and len(w) > 2][:3]
    return " ".join(picked) or "program"


@dataclass
class Starter:
    name: str
    source: str


def starters() -> list[Starter]:
    out = []
    for path in sorted(STARTERS.glob("*.py")):
        out.append(Starter(path.stem.replace("_", " "), path.read_text(encoding="utf-8")))
    return out


class Book:
    def __init__(self, store, clock, record: Callable[..., None] | None = None, embedder=None):
        self.store = store
        self.clock = clock
        self.record = record or (lambda kind, **data: None)
        self.embedder = embedder
        self._vectors: dict = {}
        data = store.read(INDEX, {}) or {}
        self.scripts: dict = {str(k): dict(v) for k, v in (data.get("scripts") or {}).items() if isinstance(v, dict) and v.get("name")}

    def save(self) -> None:
        self.store.write(INDEX, {"format": 1, "scripts": dict(sorted(self.scripts.items()))})

    def get(self, name: str) -> dict | None:
        tag = tag_of(name)
        if tag in self.scripts:
            return self.scripts[tag]
        for entry in self.scripts.values():
            if entry.get("name") == name:
                return entry
        return None

    def unique(self, name: str) -> str:
        base = name or "program"
        if tag_of(base) not in self.scripts:
            return base
        for n in range(2, 100):
            option = f"{base} {n}"
            if tag_of(option) not in self.scripts:
                return option
        return f"{base} {len(self.scripts) + 1}"

    def path(self, tag: str, version: int) -> str:
        return f"{ROOT}/{tag}/v{int(version)}.py"

    def source(self, entry: dict, version: int | None = None) -> str:
        number = int(version if version is not None else entry.get("version") or 1)
        return self.store.read_bytes(self.path(entry["tag"], number), b"").decode("utf-8", errors="replace")

    def add(self, name: str, source: str, header: dict, for_id: str | None, for_label: str, made_by: str, words: str = "", sure: bool = False) -> dict:
        now = iso(self.clock.now())
        name = self.unique(name)
        tag = tag_of(name)
        entry = {
            "tag": tag,
            "name": name,
            "aliases": [],
            "about": str(header.get("ABOUT") or "")[:200],
            "for": for_id,
            "for_label": for_label,
            "kind": "own" if for_id is None else "person",
            "words": str(words or "")[:200],
            "status": "trial",
            "version": 1,
            "good_version": None,
            "versions": [1],
            "made_at": now,
            "made_by": made_by,
            "last_used": now,
            "used": 0,
            "good": 0,
            "bad": 0,
            "until": str(header.get("UNTIL") or ""),
            "uses": list(header.get("USES") or []),
            "wants": sorted((header.get("WANTS") or {}).keys()),
            "sure": bool(sure),
        }
        self.store.write_bytes(self.path(tag, 1), source.encode("utf-8"))
        self.scripts[tag] = entry
        self._trim()
        self.save()
        self.record("script_made", script=name, whose=entry["kind"], version=1)
        return entry

    def new_version(self, entry: dict, source: str, header: dict) -> dict:
        number = max(entry.get("versions") or [0]) + 1
        self.store.write_bytes(self.path(entry["tag"], number), source.encode("utf-8"))
        versions = list(entry.get("versions") or []) + [number]
        for old in versions[:-VERSIONS_MOST]:
            if old != entry.get("good_version"):
                self.store.remove(self.path(entry["tag"], old))
        entry["versions"] = [v for v in versions if v in versions[-VERSIONS_MOST:] or v == entry.get("good_version")]
        entry["version"] = number
        entry["status"] = "trial"
        entry["about"] = str(header.get("ABOUT") or entry.get("about") or "")[:200]
        entry["until"] = str(header.get("UNTIL") or "")
        entry["uses"] = list(header.get("USES") or [])
        entry["wants"] = sorted((header.get("WANTS") or {}).keys())
        self.save()
        self.record("script_changed", script=entry["name"], version=number)
        return entry

    def good(self, entry: dict) -> None:
        entry["good_version"] = entry.get("version")
        entry["status"] = "live"
        entry["good"] = int(entry.get("good") or 0) + 1
        self.save()

    def used(self, entry: dict) -> None:
        entry["last_used"] = iso(self.clock.now())
        entry["used"] = int(entry.get("used") or 0) + 1
        self.save()

    def rollback(self, entry: dict, why: str) -> bool:
        entry["bad"] = int(entry.get("bad") or 0) + 1
        good = entry.get("good_version")
        if good is not None and good != entry.get("version") and good in (entry.get("versions") or []):
            entry["version"] = good
            entry["status"] = "live"
            self.save()
            self.record("script_rolled_back", script=entry["name"], to=good, why=why[:80])
            return True
        entry["status"] = "retired"
        entry["retired_why"] = why[:120]
        self.save()
        self.record("script_retired", script=entry["name"], why=why[:80])
        return False

    def retire(self, entry: dict, why: str, status: str = "retired") -> None:
        entry["status"] = status
        entry["retired_why"] = why[:120]
        entry["retired_at"] = iso(self.clock.now())
        self.save()
        self.record("script_retired" if status == "retired" else "script_ended", script=entry["name"], why=why[:80])

    def live(self) -> list[dict]:
        return [entry for entry in self.scripts.values() if entry.get("status") in LIVE]

    def state(self, entry: dict) -> dict:
        data = self.store.read(f"{ROOT}/{entry['tag']}/state.json", {}) or {}
        return dict(data.get("kept") or {}) if isinstance(data, dict) else {}

    def save_state(self, entry: dict, kept: dict) -> None:
        self.store.write(f"{ROOT}/{entry['tag']}/state.json", {"format": 1, "kept": kept})

    def find(self, words: str, among: list[dict] | None = None) -> list[dict]:
        said = content(words)
        if not said:
            return []
        out = []
        for entry in among if among is not None else list(self.scripts.values()):
            forms = [entry.get("name", "")] + list(entry.get("aliases") or [])
            names = set()
            for form in forms:
                names |= content(form)
            special = names - GENERIC
            if names and names <= said:
                out.append(entry)
            elif special and special <= said:
                out.append(entry)
        return out

    def forget(self, person_id: str, names: list) -> int:
        words = [str(n).lower() for n in names if n and len(str(n)) > 1]
        patterns = [re.compile(rf"\b{re.escape(w)}\b") for w in words]
        gone = 0
        for tag, entry in list(self.scripts.items()):
            if entry.get("for") == person_id:
                for version in entry.get("versions") or []:
                    self.store.remove(self.path(tag, version))
                self.store.remove(f"{ROOT}/{tag}/state.json")
                self.scripts.pop(tag)
                gone += 1
                continue
            if entry.get("made_by") == person_id:
                entry["made_by"] = None
            kept = self.state(entry)
            cleaned = _scrub(kept, patterns)
            if cleaned != kept:
                self.save_state(entry, cleaned)
        self.save()
        if gone:
            self.record("script_forgotten", scripts=gone)
        return gone

    def tidy(self) -> list[str]:
        now = self.clock.now()
        retired = []
        for entry in list(self.scripts.values()):
            if entry.get("kind") != "own" or entry.get("status") not in LIVE:
                continue
            try:
                last = from_iso(entry.get("last_used") or entry.get("made_at") or "")
            except Exception:
                last = now
            if now - last > RETIRE_AFTER_S:
                self.retire(entry, "not run for 30 days")
                retired.append(entry["name"])
        self._trim()
        self.save()
        return retired

    def _trim(self) -> None:
        live = sorted(self.live(), key=lambda e: e.get("last_used") or "")
        while len(live) > LIVE_MOST:
            oldest = live.pop(0)
            oldest["status"] = "retired"
            oldest["retired_why"] = "too many live programs"

    def recipes(self) -> list[tuple[str, str, str]]:
        out = []
        for entry in self.scripts.values():
            if int(entry.get("good") or 0) > 0 and entry.get("good_version"):
                source = self.source(entry, entry["good_version"])
                if source:
                    out.append((entry["name"], entry.get("about") or "", source))
        for starter in starters():
            about = next((line.split("=", 1)[1].strip().strip('"') for line in starter.source.splitlines() if line.startswith("ABOUT")), "")
            out.append((starter.name, about, starter.source))
        return out

    def closest(self, words: str, most: int = CLOSEST) -> list[tuple[str, str, str]]:
        found = self.recipes()
        said = content(words)
        vectors = self._embed(words, found)
        scored = []
        for index, (name, about, source) in enumerate(found):
            overlap = len(said & (content(name) | content(about))) / max(1, len(said))
            scored.append((overlap + vectors.get(index, 0.0), -len(source), index))
        scored.sort(reverse=True)
        return [found[index] for _, _, index in scored[:most]]

    def _embed(self, words: str, found: list) -> dict:
        if self.embedder is None or not words or not found:
            return {}
        try:
            texts = [f"{name}: {about}" for name, about, _ in found]
            missing = [t for t in texts if t not in self._vectors]
            if missing:
                for text, vector in zip(missing, self.embedder.embed(missing)):
                    self._vectors[text] = vector
            query = self.embedder.embed([words], query=True)[0]
        except Exception:
            log.exception("could not compare scripts by meaning")
            return {}
        out = {}
        for index, text in enumerate(texts):
            vector = self._vectors.get(text)
            if vector:
                top = sum(a * b for a, b in zip(query, vector))
                size = math.sqrt(sum(a * a for a in query)) * math.sqrt(sum(b * b for b in vector)) or 1.0
                out[index] = top / size
        return out


def _scrub(value, patterns):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if any(p.search(str(key).lower()) for p in patterns):
                continue
            if isinstance(item, str) and any(p.search(item.lower()) for p in patterns):
                continue
            out[key] = _scrub(item, patterns)
        return out
    if isinstance(value, list):
        return [_scrub(item, patterns) for item in value if not (isinstance(item, str) and any(p.search(item.lower()) for p in patterns))]
    return value
