import logging
import math
import re
from dataclasses import dataclass, field
from typing import Callable

from ..clock import from_iso, iso
from .card import kind_of, key, said, slug

log = logging.getLogger(__name__)

BODIES = "mine/bodies/index.json"
DRAFT_KEEP_S = 7 * 86400.0
SKILLS_MOST = 200
ALIASES_MOST = 8
VERSIONS_MOST = 10
CLOSEST = 3
POLITE = re.compile(r"^(?:(?:can|could|would|will|wanna|want to) you |(?:please|go on|come on|hey|ok|okay|now|pebble),? )+")
LEAD = re.compile(r"^(?:try (?:to |and )?|(?:have|give it) (?:a|another) go (?:at )?|do (?:me |us )?|show (?:me |us |[a-z]+ )?|perform |give (?:me |us )?|make (?=a |an |the )|let's see |let me see )")
ARTICLE = re.compile(r"^(?:a|an|the|your|some|that|this|my|our|another|one more|a bit of)\s+")
TAIL = re.compile(r"\s+for (?:me|us|everyone|everybody|them|him|her|[a-z]+)$|\s+(?:please|now|then|pebble|for a bit|a bit|again|one more time|right now)$")
AGAIN = re.compile(r"\b(?:again|one more time|another go|another try|keep trying)\b")
TRY_AGAIN = re.compile(r"^(?:try|have another go at|keep trying|have a go at)\b")
STOP_WORDS = frozenset("a an the to of for and then me you us it him her them is are be do my your our some that this with on in at up down".split())
BUSY = frozenset("follow come wait stay look back go turn spin move stop find play here home bed sleep charge left right around forward closer slower faster away check watch remind tell again".split())


def plain(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", str(text or "").lower().replace("’", "'")))


def name_of(words: str, own: str = "pebble", names=()) -> str:
    text = " ".join(w for w in plain(words).split() if w not in (own, f"{own}'s"))
    for _ in range(4):
        before = text
        text = POLITE.sub("", text).strip()
        text = LEAD.sub("", text).strip()
        text = ARTICLE.sub("", text).strip()
        text = TAIL.sub("", text).strip()
        if text == before:
            break
    return text[:60]


def content(text: str) -> set:
    return {w for w in plain(text).split() if w not in STOP_WORDS}


def head(name: str) -> str:
    words = [w for w in plain(name).split() if w not in STOP_WORDS]
    return words[-1] if words and words[-1] not in BUSY else ""


@dataclass
class Skill:
    name: str
    steps: list
    aliases: list = field(default_factory=list)
    kind: str = "move"
    about: str = ""
    body: str = ""
    taught_by: dict = field(default_factory=dict)
    learned_at: str = ""
    versions: list = field(default_factory=list)
    good: int = 0
    bad: int = 0
    last_used: str = ""

    def as_dict(self) -> dict:
        return {
            "format": 1,
            "name": self.name,
            "aliases": list(self.aliases),
            "kind": self.kind,
            "about": self.about,
            "body": self.body,
            "steps": list(self.steps),
            "taught_by": dict(self.taught_by),
            "learned_at": self.learned_at,
            "versions": list(self.versions),
            "good": self.good,
            "bad": self.bad,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Skill | None":
        if not isinstance(data, dict) or not data.get("name") or not isinstance(data.get("steps"), list):
            return None
        return cls(
            name=str(data["name"]),
            steps=[dict(s) for s in data["steps"] if isinstance(s, dict)],
            aliases=[str(a) for a in data.get("aliases") or []],
            kind=str(data.get("kind") or "move"),
            about=str(data.get("about") or ""),
            body=str(data.get("body") or ""),
            taught_by=dict(data.get("taught_by") or {}),
            learned_at=str(data.get("learned_at") or ""),
            versions=[dict(v) for v in data.get("versions") or [] if isinstance(v, dict)],
            good=int(data.get("good") or 0),
            bad=int(data.get("bad") or 0),
            last_used=str(data.get("last_used") or ""),
        )

    def words(self) -> set:
        found = content(self.name)
        for alias in self.aliases:
            found |= content(alias)
        return found


@dataclass
class Draft:
    name: str
    words: str
    tries: list
    asker: str | None
    at: float

    def as_dict(self) -> dict:
        return {"format": 1, "name": self.name, "words": self.words, "tries": list(self.tries), "asker": self.asker, "at": iso(self.at)}

    @classmethod
    def from_dict(cls, data: dict) -> "Draft | None":
        if not isinstance(data, dict) or not data.get("name"):
            return None
        try:
            at = from_iso(str(data.get("at")))
        except Exception:
            return None
        return cls(str(data["name"]), str(data.get("words") or data["name"]), [dict(t) for t in data.get("tries") or [] if isinstance(t, dict)], data.get("asker"), at)

    def best(self) -> list:
        for item in reversed(self.tries):
            if item.get("steps") and item.get("answer_kind") in ("nearly", "silence", "left", "rest", "", None):
                return list(item["steps"])
        return list(self.tries[-1]["steps"]) if self.tries and self.tries[-1].get("steps") else []


class Skills:
    def __init__(self, store, body: str, clock, record: Callable[..., None] | None = None, embedder=None):
        self.store = store
        self.body = slug(body) or "body"
        self.clock = clock
        self.record = record or (lambda kind, **data: None)
        self.embedder = embedder
        self._vectors: dict = {}
        self._indexes: dict = {}
        self._loaded: dict = {}
        self._bodies: list | None = None
        self._drafts: dict | None = None

    def reload(self) -> None:
        self._indexes.clear()
        self._loaded.clear()
        self._vectors.clear()
        self._bodies = None
        self._drafts = None

    def _root(self, body: str | None = None) -> str:
        return f"mine/bodies/{body or self.body}/skills"

    def _index(self, body: str | None = None) -> dict:
        body = body or self.body
        if body not in self._indexes:
            data = self.store.read(f"{self._root(body)}/index.json", {}) or {}
            self._indexes[body] = {str(k): dict(v) for k, v in (data.get("skills") or {}).items() if isinstance(v, dict)}
        return {tag: dict(entry) for tag, entry in self._indexes[body].items()}

    def _save_index(self, index: dict) -> None:
        self.store.write(f"{self._root()}/index.json", {"format": 1, "skills": dict(sorted(index.items()))})
        self._indexes[self.body] = {tag: dict(entry) for tag, entry in index.items()}
        self._loaded.pop(self.body, None)
        bodies = self.bodies()
        if self.body not in bodies:
            self.store.write(BODIES, {"format": 1, "bodies": sorted(set(bodies) | {self.body})})
            self._bodies = None

    def bodies(self) -> list[str]:
        if self._bodies is None:
            self._bodies = [b for b in (self.store.read(BODIES, {}) or {}).get("bodies") or [] if isinstance(b, str)]
        return list(self._bodies)

    def get(self, name: str, body: str | None = None) -> Skill | None:
        tag = slug(name)
        if not tag or tag not in self._index(body):
            return None
        return Skill.from_dict(self.store.read(f"{self._root(body)}/{tag}.json", {}) or {})

    def all(self, body: str | None = None) -> list[Skill]:
        body = body or self.body
        if body not in self._loaded:
            out = []
            for tag in self._index(body):
                skill = Skill.from_dict(self.store.read(f"{self._root(body)}/{tag}.json", {}) or {})
                if skill is not None:
                    out.append(skill)
            self._loaded[body] = out
        return list(self._loaded[body])

    def names(self) -> list[str]:
        return [entry.get("name", tag) for tag, entry in self._index().items()]

    def find(self, words: str, body: str | None = None) -> Skill | None:
        wanted = name_of(words)
        if not wanted:
            return None
        index = self._index(body)
        exact = []
        loose = []
        said_words = content(wanted)
        for tag, entry in index.items():
            forms = [entry.get("name", "")] + list(entry.get("aliases") or [])
            if wanted in forms or slug(wanted) == tag:
                exact.append(tag)
                continue
            words = set()
            for form in forms:
                words |= content(form)
            heads = {head(form) for form in forms if head(form)}
            if said_words - BUSY and said_words <= words and said_words & heads:
                loose.append(tag)
        chosen = exact or loose
        if not chosen:
            return None
        best = max(chosen, key=lambda tag: (index[tag].get("good", 0) - index[tag].get("bad", 0), index[tag].get("last_used", "")))
        return self.get(index[best].get("name", best), body)

    def elsewhere(self, words: str) -> Skill | None:
        for body in self.bodies():
            if body == self.body:
                continue
            found = self.find(words, body)
            if found is not None:
                return found
        return None

    def matches(self, text: str) -> Skill | None:
        said = plain(text)
        if not said or re.search(r"\b(?:don't|dont|do not|never|stop|no more|not)\b", said):
            return None
        return self.find(said)

    def keep(self, name: str, words: str, steps: list, teacher: dict, replacing: Skill | None = None) -> Skill:
        now = iso(self.clock.now())
        index = self._index()
        old = self.get(replacing.name if replacing is not None else name) or replacing
        if old is None and len(index) >= SKILLS_MOST:
            oldest = min(index, key=lambda tag: index[tag].get("last_used", ""))
            self.store.remove(f"{self._root()}/{oldest}.json")
            index.pop(oldest, None)
        aliases = list(dict.fromkeys(a for a in [name, name_of(words), head(name)] + (old.aliases if old is not None else []) if a and len(a) > 2))[:ALIASES_MOST]
        versions = list(old.versions) if old is not None else []
        if old is not None:
            versions.append({"steps": old.steps, "taught_by": old.taught_by, "at": old.learned_at, "replaced_at": now})
            versions = versions[-VERSIONS_MOST:]
        skill = Skill(
            name=old.name if old is not None else name,
            steps=list(steps),
            aliases=aliases,
            kind=kind_of(steps),
            about=said(steps)[:160],
            body=self.body,
            taught_by=dict(teacher),
            learned_at=now,
            versions=versions,
            good=old.good if old is not None else 0,
            bad=old.bad if old is not None else 0,
            last_used=now,
        )
        self._write(skill, index)
        self.drop_draft(skill.name)
        self.record("skill_kept", name=skill.name, shape=skill.kind, steps=len(steps), tier=teacher.get("tier"), replaced=old is not None)
        return skill

    def _write(self, skill: Skill, index: dict | None = None) -> None:
        index = self._index() if index is None else index
        tag = slug(skill.name)
        self.store.write(f"{self._root()}/{tag}.json", skill.as_dict())
        index[tag] = {"name": skill.name, "aliases": skill.aliases, "kind": skill.kind, "about": skill.about, "good": skill.good, "bad": skill.bad, "last_used": skill.last_used}
        self._save_index(index)
        self._vectors.pop(tag, None)

    def used(self, skill: Skill, good: bool | None, words: str = "") -> None:
        current = self.get(skill.name)
        if current is None:
            return
        if good is True:
            current.good += 1
        elif good is False:
            current.bad += 1
        alias = name_of(words) if words else ""
        if alias and alias not in current.aliases and len(alias) > 2 and len(current.aliases) < ALIASES_MOST:
            current.aliases.append(alias)
        current.last_used = iso(self.clock.now())
        self._write(current)

    def drop(self, name: str) -> bool:
        tag = slug(name)
        index = self._index()
        if not tag or tag not in index:
            return False
        index.pop(tag)
        self.store.remove(f"{self._root()}/{tag}.json")
        self._save_index(index)
        self._vectors.pop(tag, None)
        self.record("skill_dropped", name=name)
        return True

    def merge(self, keep: Skill, gone: Skill) -> Skill:
        index = self._index()
        names = [gone.name] + list(gone.aliases) + list(keep.aliases)
        keep.aliases = list(dict.fromkeys(a for a in names if a and len(a) > 2 and a != keep.name))[:ALIASES_MOST]
        keep.versions = (list(keep.versions) + [{"steps": gone.steps, "taught_by": gone.taught_by, "at": gone.learned_at, "merged": gone.name}] + list(gone.versions))[-VERSIONS_MOST:]
        keep.good += gone.good
        keep.bad += gone.bad
        keep.last_used = max(keep.last_used, gone.last_used)
        tag = slug(gone.name)
        if tag in index and tag != slug(keep.name):
            index.pop(tag)
            self.store.remove(f"{self._root()}/{tag}.json")
            self._vectors.pop(tag, None)
        self._write(keep, index)
        self.record("skill_merged", name=keep.name, merged=gone.name)
        return keep

    def closest(self, words: str, most: int = CLOSEST) -> list[Skill]:
        skills = self.all()
        if not skills:
            return []
        wanted = name_of(words) or plain(words)
        said_words = content(wanted)
        padded = f" {plain(words)} "
        scored = []
        vectors = self._embed(wanted, skills)
        for skill in skills:
            named = any(f" {plain(form)} " in padded for form in [skill.name] + list(skill.aliases) if plain(form))
            overlap = len((skill.words() | content(skill.about)) & said_words) / max(1, len(said_words))
            score = overlap + (vectors.get(slug(skill.name), 0.0) if vectors else 0.0)
            scored.append((score + (1.0 if named else 0.0), skill.last_used, skill))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [skill for _, _, skill in scored[:most]]

    def _embed(self, words: str, skills: list[Skill]) -> dict:
        if self.embedder is None or not words:
            return {}
        try:
            missing = [s for s in skills if slug(s.name) not in self._vectors]
            if missing:
                found = self.embedder.embed([f"{s.name}: {s.about}" for s in missing])
                for skill, vector in zip(missing, found):
                    self._vectors[slug(skill.name)] = vector
            query = self.embedder.embed([words], query=True)[0]
        except Exception:
            log.exception("could not compare skills by meaning")
            return {}
        out = {}
        for skill in skills:
            vector = self._vectors.get(slug(skill.name))
            if vector:
                top = sum(a * b for a, b in zip(query, vector))
                size = math.sqrt(sum(a * a for a in query)) * math.sqrt(sum(b * b for b in vector)) or 1.0
                out[slug(skill.name)] = top / size
        return out

    def listed(self, text: str, most: int = CLOSEST) -> str:
        found = self.closest(text, most)
        if not found:
            return ""
        return "Skills you know: " + "; ".join(f"{s.name} ({s.about[:50]})" for s in found)

    def _drafts_root(self) -> str:
        return f"{self._root()}/drafts"

    def _draft_index(self) -> dict:
        if self._drafts is None:
            data = self.store.read(f"{self._drafts_root()}/index.json", {}) or {}
            self._drafts = {str(k): dict(v) for k, v in (data.get("drafts") or {}).items() if isinstance(v, dict)}
        return {tag: dict(entry) for tag, entry in self._drafts.items()}

    def _save_drafts(self, index: dict) -> None:
        self.store.write(f"{self._drafts_root()}/index.json", {"format": 1, "drafts": dict(sorted(index.items()))})
        self._drafts = {tag: dict(entry) for tag, entry in index.items()}

    def draft(self, name: str, words: str, tries: list, asker: str | None) -> Draft | None:
        tries = [t for t in tries if t.get("steps")]
        if not tries:
            return None
        now = self.clock.now()
        item = Draft(name, words, tries, asker, now)
        tag = slug(name)
        self.store.write(f"{self._drafts_root()}/{tag}.json", item.as_dict())
        index = self._draft_index()
        index[tag] = {"name": name, "at": iso(now), "asker": asker}
        self._save_drafts(index)
        self.record("skill_draft", name=name, tries=len(tries))
        return item

    def drafted(self, words: str) -> Draft | None:
        self.tidy()
        wanted = name_of(AGAIN.sub(" ", plain(words)))
        if not wanted:
            return None
        index = self._draft_index()
        said_words = content(wanted)
        for tag, entry in sorted(index.items(), key=lambda item: item[1].get("at", ""), reverse=True):
            name = entry.get("name", tag)
            if name == wanted or (said_words and said_words <= content(name) and said_words & {head(name)}):
                return Draft.from_dict(self.store.read(f"{self._drafts_root()}/{tag}.json", {}) or {})
        return None

    def drop_draft(self, name: str) -> None:
        tag = slug(name)
        index = self._draft_index()
        if tag in index:
            index.pop(tag)
            self.store.remove(f"{self._drafts_root()}/{tag}.json")
            self._save_drafts(index)

    def tidy(self) -> int:
        now = self.clock.now()
        index = self._draft_index()
        gone = []
        for tag, entry in index.items():
            try:
                at = from_iso(entry.get("at") or "")
            except Exception:
                at = 0.0
            if now - at > DRAFT_KEEP_S:
                gone.append(tag)
        for tag in gone:
            index.pop(tag)
            self.store.remove(f"{self._drafts_root()}/{tag}.json")
        if gone:
            self._save_drafts(index)
        return len(gone)

    def forget(self, person_id: str, names: list) -> None:
        for body in set(self.bodies()) | {self.body}:
            for skill in self.all(body):
                changed = False
                if skill.taught_by.get("id") == person_id:
                    skill.taught_by = {"id": None, "name": "", "tier": skill.taught_by.get("tier", "")}
                    changed = True
                for version in skill.versions:
                    if (version.get("taught_by") or {}).get("id") == person_id:
                        version["taught_by"] = {"id": None, "name": "", "tier": version["taught_by"].get("tier", "")}
                        changed = True
                if changed:
                    tag = slug(skill.name)
                    self.store.write(f"mine/bodies/{body}/skills/{tag}.json", skill.as_dict())
            self._loaded.pop(body, None)
        index = self._draft_index()
        gone = [tag for tag, entry in index.items() if entry.get("asker") == person_id]
        for tag in gone:
            index.pop(tag)
            self.store.remove(f"{self._drafts_root()}/{tag}.json")
        if gone:
            self._save_drafts(index)


def same(steps, tries) -> bool:
    mine = key(steps)
    return any(key(item.get("steps") or []) == mine for item in tries)
