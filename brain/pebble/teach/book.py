import base64
import binascii
import logging
import math
import re
import struct
from dataclasses import dataclass, field
from typing import Callable

from ..activities.card import slug
from ..clock import from_iso, iso
from .words import bare

log = logging.getLogger(__name__)

ROOT = "mine/howto"
INDEX = f"{ROOT}/index.json"
DRAFTS = f"{ROOT}/drafts"
KINDS = ("move", "route", "procedure", "concept", "word", "way", "habit", "game", "spot")
ENTRIES_MOST = 400
VERSIONS_MOST = 10
EXAMPLES_MOST = 8
PRINTS_MOST = 24
ALIASES_MOST = 8
DRAFT_KEEP_S = 7 * 86400.0
CLOSEST = 3
SLOT = re.compile(r"\{([a-z_]{1,16})\}")
LEADS = r"(?:(?:can|could|would|will) you |please |go and |now |pebble |okay |ok )*(?:do |run |show me |try |have a go at |let us see |time for |time to |go to |go back to |head to |go over to |take the way to |go the way to )?(?:the |your |a |my |our )?"
TAIL = re.compile(r"(?:\s+(?:please|now|for me|for us|thanks|thank you|again|pebble))+$")
STOP = frozenset("a an the to of for and then me you us it him her them is are be do my your our some that this with on in at up down go".split())


def content(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9']+", str(text or "").lower()) if w not in STOP and len(w) > 1}


def pack(vector) -> str:
    values = [float(v) for v in vector]
    return "f16:" + base64.b64encode(struct.pack(f"<{len(values)}e", *values)).decode("ascii")


def unpack(text: str) -> list[float] | None:
    if not isinstance(text, str) or not text.startswith("f16:"):
        return None
    try:
        raw = base64.b64decode(text[4:], validate=True)
    except (ValueError, binascii.Error):
        return None
    if not raw or len(raw) % 2:
        return None
    return list(struct.unpack(f"<{len(raw) // 2}e", raw))


def cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    top = sum(x * y for x, y in zip(a, b))
    size = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return top / size if size else 0.0


@dataclass
class Entry:
    name: str
    kind: str
    aliases: list = field(default_factory=list)
    about: str = ""
    body: str = ""
    steps: list = field(default_factory=list)
    slots: dict = field(default_factory=dict)
    pattern: str = ""
    trigger: dict = field(default_factory=dict)
    points: list = field(default_factory=list)
    rooms: list = field(default_factory=list)
    examples: list = field(default_factory=list)
    prints: list = field(default_factory=list)
    look: str = ""
    line: str = ""
    words: str = ""
    link: dict = field(default_factory=dict)
    taught_by: dict = field(default_factory=dict)
    person: str | None = None
    learned_at: str = ""
    last_used: str = ""
    versions: list = field(default_factory=list)
    good: int = 0
    bad: int = 0
    runs: int = 0
    made_by: str = "plain"
    asked: dict = field(default_factory=dict)

    @property
    def tag(self) -> str:
        return slug(self.name)

    @property
    def teacher_id(self) -> str | None:
        return (self.taught_by or {}).get("id")

    @property
    def teacher_tier(self) -> str:
        return str((self.taught_by or {}).get("tier") or "")

    def as_dict(self) -> dict:
        return {
            "format": 1,
            "name": self.name,
            "kind": self.kind,
            "aliases": list(self.aliases),
            "about": self.about,
            "body": self.body,
            "steps": list(self.steps),
            "slots": {k: list(v) for k, v in self.slots.items()},
            "pattern": self.pattern,
            "trigger": dict(self.trigger),
            "points": list(self.points),
            "rooms": list(self.rooms),
            "examples": list(self.examples),
            "prints": list(self.prints),
            "look": self.look,
            "line": self.line,
            "words": self.words,
            "link": dict(self.link),
            "taught_by": dict(self.taught_by),
            "person": self.person,
            "learned_at": self.learned_at,
            "last_used": self.last_used,
            "versions": list(self.versions),
            "good": self.good,
            "bad": self.bad,
            "runs": self.runs,
            "made_by": self.made_by,
            "asked": dict(self.asked),
        }

    @classmethod
    def from_dict(cls, data) -> "Entry | None":
        if not isinstance(data, dict) or not data.get("name") or data.get("kind") not in KINDS:
            return None
        try:
            return cls(
                name=str(data["name"])[:48],
                kind=str(data["kind"]),
                aliases=[str(a) for a in data.get("aliases") or []][:ALIASES_MOST],
                about=str(data.get("about") or "")[:200],
                body=str(data.get("body") or ""),
                steps=[dict(s) for s in data.get("steps") or [] if isinstance(s, dict)],
                slots={str(k): [str(v) for v in values][:EXAMPLES_MOST] for k, values in (data.get("slots") or {}).items() if isinstance(values, list)},
                pattern=str(data.get("pattern") or ""),
                trigger=dict(data.get("trigger") or {}),
                points=[list(p) for p in data.get("points") or [] if isinstance(p, (list, tuple)) and len(p) >= 2],
                rooms=[str(r) for r in data.get("rooms") or []],
                examples=[dict(e) for e in data.get("examples") or [] if isinstance(e, dict)][-EXAMPLES_MOST:],
                prints=[dict(p) for p in data.get("prints") or [] if isinstance(p, dict)][-PRINTS_MOST:],
                look=str(data.get("look") or ""),
                line=str(data.get("line") or "")[:120],
                words=str(data.get("words") or "")[:160],
                link=dict(data.get("link") or {}),
                taught_by=dict(data.get("taught_by") or {}),
                person=data.get("person"),
                learned_at=str(data.get("learned_at") or ""),
                last_used=str(data.get("last_used") or ""),
                versions=[dict(v) for v in data.get("versions") or [] if isinstance(v, dict)][-VERSIONS_MOST:],
                good=int(data.get("good") or 0),
                bad=int(data.get("bad") or 0),
                runs=int(data.get("runs") or 0),
                made_by=str(data.get("made_by") or "plain"),
                asked=dict(data.get("asked") or {}),
            )
        except (TypeError, ValueError):
            return None

    def forms(self) -> list[str]:
        return [self.name] + [a for a in self.aliases if a and a != self.name]

    def vectors(self) -> list[tuple[list[float], bool]]:
        out = []
        for item in self.prints:
            vector = unpack(item.get("v", ""))
            if vector:
                out.append((vector, bool(item.get("yes", True))))
        return out


def pattern_of(name: str, slots: dict) -> str:
    text = name
    for slot, values in slots.items():
        for value in sorted(values, key=len, reverse=True):
            if value and re.search(rf"\b{re.escape(value)}\b", text):
                text = re.sub(rf"\b{re.escape(value)}\b", "{" + slot + "}", text, count=1)
                break
    return text if SLOT.search(text) else ""


def shown_name(entry: Entry) -> str:
    if entry.pattern:
        text = re.sub(r"\b(?:the|a|an|your|my|our) \{([a-z_0-9]+)\}", lambda m: f"a {m.group(1).replace('_', ' ')}", entry.pattern)
        return SLOT.sub(lambda m: f"a {m.group(1).replace('_', ' ')}", text)
    return entry.name


def _regex(pattern: str) -> re.Pattern | None:
    parts = SLOT.split(pattern)
    out = []
    names = []
    for index, part in enumerate(parts):
        if index % 2:
            if part in names:
                return None
            names.append(part)
            out.append(rf"(?P<{part}>[a-z0-9' ]{{2,30}}?)")
        else:
            out.append(re.escape(part))
    try:
        return re.compile("^" + LEADS + "".join(out) + r"$")
    except re.error:
        return None


class HowTo:
    def __init__(self, store, clock, record: Callable[..., None] | None = None, embedder=None):
        self.store = store
        self.clock = clock
        self.record = record or (lambda kind, **data: None)
        self.embedder = embedder
        self._vectors: dict = {}
        self._loaded: dict | None = None
        data = store.read(INDEX, {}) or {}
        self.index: dict = {str(k): dict(v) for k, v in (data.get("entries") or {}).items() if isinstance(v, dict) and v.get("name")}

    def path(self, tag: str) -> str:
        return f"{ROOT}/{tag}.json"

    def save_index(self) -> None:
        self.store.write(INDEX, {"format": 1, "entries": dict(sorted(self.index.items()))})

    def _summary(self, entry: Entry) -> dict:
        return {"name": entry.name, "kind": entry.kind, "aliases": entry.aliases, "about": entry.about[:120], "pattern": entry.pattern, "person": entry.person, "by": entry.teacher_id, "tier": entry.teacher_tier, "last_used": entry.last_used, "good": entry.good, "bad": entry.bad, "slots": {k: list(v) for k, v in entry.slots.items()}}

    def get(self, name: str) -> Entry | None:
        tag = slug(name)
        if not tag or tag not in self.index:
            return None
        if self._loaded is not None and tag in self._loaded:
            return Entry.from_dict(self._loaded[tag].as_dict())
        return Entry.from_dict(self.store.read(self.path(tag), {}) or {})

    def all(self) -> list[Entry]:
        if self._loaded is None:
            loaded = {}
            for tag in list(self.index):
                entry = Entry.from_dict(self.store.read(self.path(tag), {}) or {})
                if entry is not None:
                    loaded[tag] = entry
            self._loaded = loaded
        return list(self._loaded.values())

    def of_kind(self, *kinds: str) -> list[Entry]:
        return [entry for entry in self.all() if entry.kind in kinds]

    def put(self, entry: Entry) -> Entry:
        tag = entry.tag
        if tag not in self.index and len(self.index) >= ENTRIES_MOST:
            oldest = min(self.index, key=lambda t: self.index[t].get("last_used", ""))
            self.remove(self.index[oldest]["name"], "the book was full")
        self.store.write(self.path(tag), entry.as_dict())
        self.index[tag] = self._summary(entry)
        self.save_index()
        if self._loaded is not None:
            self._loaded[tag] = entry
        self._vectors.pop(tag, None)
        return entry

    def remove(self, name: str, why: str = "") -> Entry | None:
        tag = slug(name)
        entry = self.get(name)
        if tag in self.index:
            self.index.pop(tag)
            self.store.remove(self.path(tag))
            self.save_index()
        if self._loaded is not None:
            self._loaded.pop(tag, None)
        self._vectors.pop(tag, None)
        if entry is not None:
            self.record("howto_removed", name=entry.name, shape=entry.kind, why=why[:60])
        return entry

    def new_version(self, entry: Entry, now: float, why: str) -> None:
        entry.versions = (list(entry.versions) + [{"steps": list(entry.steps), "slots": {k: list(v) for k, v in entry.slots.items()}, "words": entry.words, "taught_by": dict(entry.taught_by), "at": entry.learned_at, "replaced_at": iso(now), "why": why[:60]}])[-VERSIONS_MOST:]

    def used(self, entry: Entry, good: bool | None = None) -> None:
        current = self.get(entry.name) or entry
        current.runs += 1
        if good is True:
            current.good += 1
        elif good is False:
            current.bad += 1
        current.last_used = iso(self.clock.now())
        self.put(current)

    def find(self, text: str, kinds: tuple = ()) -> tuple[Entry, dict] | None:
        said = TAIL.sub("", bare(text)).strip()
        if not said:
            return None
        plain = re.sub("^" + LEADS, "", said).strip()
        best = None
        for tag, summary in self.index.items():
            if kinds and summary.get("kind") not in kinds:
                continue
            forms = [summary.get("name", "")] + list(summary.get("aliases") or [])
            forms = forms + [stripped for stripped in (re.sub("^" + LEADS, "", form).strip() for form in forms) if stripped and stripped not in forms]
            if summary.get("kind") == "word":
                if said in forms or (plain != said and plain in forms):
                    return self.get(summary["name"]), {}
                continue
            if plain in forms or said in forms:
                entry = self.get(summary["name"])
                if entry is not None:
                    return entry, {}
            pattern = summary.get("pattern") or ""
            if pattern:
                regex = _regex(pattern)
                found = regex.match(said) if regex is not None else None
                if found is not None:
                    slots = {k: v.strip() for k, v in found.groupdict().items() if v and v.strip()}
                    if slots and (best is None or len(pattern) > len(best[2])):
                        best = (summary["name"], slots, pattern)
            if summary.get("slots") and not pattern:
                for slot in summary["slots"]:
                    for form in forms:
                        found = re.match(rf"^{LEADS}{re.escape(form)} (?:for|with|at|in|to) (?:the )?(?P<v>[a-z0-9' ]{{2,30}})$", said)
                        if found is not None:
                            best = best or (summary["name"], {slot: found.group("v").strip()}, form)
        if best is not None:
            entry = self.get(best[0])
            if entry is not None:
                return entry, best[1]
        return None

    def closest(self, text: str, most: int = CLOSEST, kinds: tuple = ()) -> list[Entry]:
        entries = [e for e in self.all() if not kinds or e.kind in kinds]
        if not entries:
            return []
        said = bare(text)
        wanted = content(said)
        padded = f" {said} "
        vectors = self._embed(said, entries)
        scored = []
        for entry in entries:
            named = any(f" {bare(form)} " in padded for form in entry.forms() if bare(form))
            words = content(" ".join(entry.forms()) + " " + entry.about + " " + entry.line)
            overlap = len(words & wanted) / max(1, len(wanted))
            score = overlap + (vectors.get(entry.tag, 0.0) if vectors else 0.0) + (1.0 if named else 0.0)
            scored.append((score, entry.last_used, entry))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [entry for score, _, entry in scored[:most] if score > 0]

    def _embed(self, words: str, entries: list[Entry]) -> dict:
        if self.embedder is None or not words:
            return {}
        try:
            missing = [e for e in entries if e.tag not in self._vectors]
            if missing:
                found = self.embedder.embed([f"{e.name}: {e.about}" for e in missing])
                for entry, vector in zip(missing, found):
                    self._vectors[entry.tag] = list(vector)
            query = self.embedder.embed([words], query=True)[0]
        except Exception:
            log.exception("could not compare how-to entries by meaning")
            return {}
        return {entry.tag: cosine(query, self._vectors.get(entry.tag)) for entry in entries if self._vectors.get(entry.tag)}

    def taught_by(self, person_id: str | None) -> list[Entry]:
        return [entry for entry in self.all() if person_id is not None and entry.teacher_id == person_id]

    def drafts(self) -> list[dict]:
        data = self.store.read(f"{DRAFTS}/index.json", {}) or {}
        return [dict(d) for d in data.get("drafts") or [] if isinstance(d, dict)]

    def _save_drafts(self, drafts: list[dict]) -> None:
        self.store.write(f"{DRAFTS}/index.json", {"format": 1, "drafts": drafts})

    def draft(self, name: str, teacher: dict, steps: list, trail: list, examples: list, ways: list) -> dict:
        now = self.clock.now()
        item = {"name": name or "something new", "teacher": dict(teacher), "steps": list(steps), "trail": list(trail), "examples": list(examples), "ways": list(ways), "at": iso(now)}
        drafts = [d for d in self.tidy_drafts() if not (d.get("name") == item["name"] and (d.get("teacher") or {}).get("id") == teacher.get("id"))]
        drafts.append(item)
        self._save_drafts(drafts[-20:])
        self.record("howto_draft", name=item["name"], steps=len(steps))
        return item

    def take_draft(self, teacher_id: str | None, name: str = "") -> dict | None:
        drafts = self.tidy_drafts()
        mine = [d for d in drafts if (d.get("teacher") or {}).get("id") == teacher_id and (not name or d.get("name") == name or name in d.get("name", ""))]
        if not mine:
            return None
        found = mine[-1]
        self._save_drafts([d for d in drafts if d is not found])
        return found

    def tidy_drafts(self) -> list[dict]:
        now = self.clock.now()
        drafts = self.drafts()
        kept = []
        for item in drafts:
            try:
                at = from_iso(item.get("at") or "")
            except Exception:
                at = 0.0
            if now - at <= DRAFT_KEEP_S:
                kept.append(item)
        if len(kept) != len(drafts):
            self._save_drafts(kept)
        return kept

    def forget(self, person_id: str, names: list) -> dict:
        gone, renamed = [], 0
        for entry in self.all():
            if entry.person == person_id:
                self.remove(entry.name, "the person it was for was forgotten")
                gone.append(entry.name)
                continue
            changed = False
            if entry.teacher_id == person_id:
                entry.taught_by = {"id": None, "name": "", "tier": entry.teacher_tier}
                changed = True
            for version in entry.versions:
                if (version.get("taught_by") or {}).get("id") == person_id:
                    version["taught_by"] = {"id": None, "name": "", "tier": (version.get("taught_by") or {}).get("tier", "")}
                    changed = True
            for example in entry.examples:
                if example.get("by") == person_id:
                    example["by"] = None
                    changed = True
            if entry.trigger.get("who") == person_id:
                self.remove(entry.name, "the person it watched for was forgotten")
                gone.append(entry.name)
                continue
            if changed:
                renamed += 1
                self.put(entry)
        drafts = self.drafts()
        kept = [d for d in drafts if (d.get("teacher") or {}).get("id") != person_id]
        if len(kept) != len(drafts):
            self._save_drafts(kept)
        self.record("howto_forgotten", gone=len(gone), unnamed=renamed)
        return {"gone": gone, "unnamed": renamed}
