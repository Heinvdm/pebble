import logging
import math
import re
from dataclasses import dataclass

from ...clock import iso
from ...people.forget import forget_phrase
from ...respect import harsh
from .archive import Archive, month_of
from .vectors import cosines, pack, spread, unpack

log = logging.getLogger(__name__)

RECORDS = "stream/records.jsonl"
VECTORS = "stream/vectors.bin"
INDEX = "stream/vectors.json"
TEXT_MAX = 200
MOST = 10000
HOUR_S = 3600.0
RECENCY = 0.995
SAME = 0.92
FADE_AFTER_S = 30 * 86400.0
STRANGER_AFTER_S = 30 * 86400.0
VISITOR = "a visitor"
LABEL = re.compile(r"\bthe visitor (p\d+)\b", re.IGNORECASE)
ANSWERED = re.compile(r';?\s*you answered:?\s*"[^"]*"', re.IGNORECASE)
SAID_QUOTE = re.compile(r'\b(said|says|asked|told you|shouted|whispered|corrected you)\s*:?\s*"[^"]*"', re.IGNORECASE)
QUOTE = re.compile(r'\s*:?\s*"[^"]*"')
ABOUT_THEM = ("fact",)
WHO_THEY_ARE = ("overheard", "reading")
KINDS = ("happened", "fact", "said", "feeling", "dream", "lesson", "decided")
SOURCES = ("self", "seen", "person", "dream", "bot")
MARKS = ("", "private", "overheard", "reading")
HOT, WARM = "hot", "warm"
DAY_S = 86400.0
HOT_S = 30 * DAY_S
COLD_S = 180 * DAY_S
HOT_IMPORTANCE = 8
FOLD_MIN = 5
FOLD_IMPORTANCE = 4
FOLD_AFTER_S = 30 * DAY_S
FOLD_PIECE = 60
FOLD_KINDS = ("happened", "said", "fact")


def _tuple(value) -> tuple:
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value if v)
    return ()


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


@dataclass
class Record:
    id: str
    t: float
    kind: str
    text: str
    by: str = "self"
    who: str | None = None
    tier: str | None = None
    about: tuple = ()
    mark: str = ""
    audience: tuple = ()
    until: float | None = None
    importance: int = 3
    recalled: int = 0
    recalled_t: float | None = None
    strength: int = 1
    pinned: bool = False
    shared: bool = False
    shelf: str = HOT
    src: tuple = ()

    def as_dict(self) -> dict:
        out = {"id": self.id, "at": iso(self.t), "t": round(self.t, 3), "kind": self.kind, "text": self.text, "by": self.by}
        for name in ("who", "tier", "mark", "until"):
            value = getattr(self, name)
            if value:
                out[name] = value
        for name in ("about", "audience"):
            value = getattr(self, name)
            if value:
                out[name] = list(value)
        out["i"] = self.importance
        if self.recalled:
            out["r"] = self.recalled
            out["rt"] = self.recalled_t
        if self.strength > 1:
            out["s"] = self.strength
        if self.pinned:
            out["pinned"] = True
        if self.shared:
            out["shared"] = True
        if self.shelf != HOT:
            out["sh"] = self.shelf
        if self.src:
            out["src"] = list(self.src)
        return out

    @classmethod
    def from_dict(cls, raw) -> "Record | None":
        if not isinstance(raw, dict) or not raw.get("id") or not str(raw.get("text") or "").strip():
            return None
        t = _number(raw.get("t"))
        if t is None:
            return None
        kind = raw.get("kind") if raw.get("kind") in KINDS else "happened"
        by = raw.get("by") if raw.get("by") in SOURCES else "self"
        mark = raw.get("mark") if raw.get("mark") in MARKS else "private"
        return cls(
            id=str(raw["id"]),
            t=t,
            kind=kind,
            text=" ".join(str(raw["text"]).split())[:TEXT_MAX],
            by=by,
            who=str(raw["who"]) if raw.get("who") else None,
            tier=str(raw["tier"]) if raw.get("tier") else None,
            about=_tuple(raw.get("about")),
            mark=mark,
            audience=_tuple(raw.get("audience")),
            until=_number(raw.get("until")),
            importance=max(1, min(10, int(_number(raw.get("i")) or 3))),
            recalled=max(0, int(_number(raw.get("r")) or 0)),
            recalled_t=_number(raw.get("rt")),
            strength=max(1, int(_number(raw.get("s")) or 1)),
            pinned=bool(raw.get("pinned")),
            shared=bool(raw.get("shared")),
            shelf=WARM if raw.get("sh") == WARM else HOT,
            src=_tuple(raw.get("src")),
        )


def visible(record: Record, audience: frozenset, now: float) -> bool:
    if record.until is not None and now > record.until:
        return False
    if record.mark == "":
        return True
    if record.mark == "overheard":
        return bool(record.about) and audience == frozenset(record.about)
    if record.mark == "reading":
        return audience <= frozenset(record.about)
    return audience <= frozenset(record.audience) if record.audience else not audience


def shown(record: Record) -> str:
    if record.by == "dream":
        return f"You dreamt: {record.text}"
    return record.text


def _their_words_gone(text: str) -> str:
    text = ANSWERED.sub("", text)
    text = SAID_QUOTE.sub(lambda m: f"{m.group(1)} something", text)
    return QUOTE.sub("", text)


def anonymised(record: "Record", person_id: str, names: list[str]) -> str:
    text = record.text
    if record.who == person_id and record.kind == "said":
        return "A visitor talked with you."
    for name in sorted({n for n in names if n and len(n) > 1}, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(name)}\b", VISITOR, text, flags=re.IGNORECASE)
    text = re.sub(rf"\bthe visitor {re.escape(person_id)}\b", VISITOR, text, flags=re.IGNORECASE)
    text = re.sub(rf"\b{re.escape(person_id)}\b", VISITOR, text)
    if record.who == person_id:
        text = _their_words_gone(text)
    text = " ".join(text.split()).strip(" ;,")
    if not text:
        return "A visitor was here."
    return text[0].upper() + text[1:]


def rank(found: list, rows: list, query, now: float, most: int, weights: dict | None, here, related: float | None) -> list:
    weights = weights or {}
    here = set(here or ())
    if not found:
        return []
    relevance = [0.0] * len(found)
    if query:
        known = [n for n, row in enumerate(rows) if row is not None]
        scores = cosines(query, [rows[n] for n in known])
        for n, score in zip(known, scores):
            relevance[n] = score
        if related is not None:
            best = max(scores) if scores else 0.0
            keep = [n for n in known if relevance[n] >= related and relevance[n] >= best - 0.15]
            found = [found[n] for n in keep]
            relevance = [relevance[n] for n in keep]
            if not found:
                return []
    recency = [RECENCY ** (max(0.0, now - (r.recalled_t or r.t)) / HOUR_S) for r in found]
    weight = [float(r.importance) for r in found]
    lift = [1.0 if here & (set(r.about) | ({r.who} if r.who else set())) else 0.0 for r in found]
    totals = [
        float(weights.get("recency", 1.0)) * a + float(weights.get("importance", 1.0)) * b + float(weights.get("relevance", 1.0)) * c + float(weights.get("people", 1.0)) * d
        for a, b, c, d in zip(recency, spread(weight), spread(relevance), lift)
    ]
    ranked = sorted(zip(found, totals), key=lambda pair: (-pair[1], -pair[0].t))
    return ranked[:most]


def shelf_of(record: "Record", now: float) -> str | None:
    age = max(0.0, now - (record.recalled_t or record.t))
    if record.pinned or age <= HOT_S or record.importance >= HOT_IMPORTANCE:
        return HOT
    if age <= COLD_S:
        return WARM
    return None


def _piece(text: str) -> str:
    text = ANSWERED.sub("", text).strip()
    if len(text) <= FOLD_PIECE:
        return text
    cut = text[:FOLD_PIECE].rsplit(" ", 1)[0].rstrip(" ,;:")
    if cut.count('"') % 2:
        cut += '"'
    return cut + "..."


def importance(kind: str, major: bool = False, people: int = 0, first: bool = False, promise: bool = False, feeling: float = 0.0) -> int:
    score = 2 + (3 if major else 0) + min(2, max(0, int(people))) + (2 if first else 0) + (2 if promise else 0) + round(min(1.0, abs(float(feeling))) * 2)
    score += {"fact": 2, "dream": 1, "said": 1, "feeling": 1, "lesson": 2, "decided": 3}.get(kind, 0)
    return max(1, min(10, score))


class Stream:
    def __init__(self, store, clock):
        self.store = store
        self.clock = clock
        self.records: dict[str, Record] = {}
        self.vectors: dict[str, bytes] = {}
        self.model = ""
        self.dim = 0
        self.unsaved: list[Record] = []
        self.waiting: set[str] = set()
        self.dirty = False
        self.vectors_dirty = False
        self.counter = 0
        self.revive: dict[str, dict[str, float]] = {}
        self._load()
        self.archive = Archive(store, Record, visible)
        self.counter = max(self.counter, self.archive.top())

    def _load(self) -> None:
        try:
            lines = self.store.read_lines(RECORDS)
        except OSError as error:
            log.warning("could not read the memory stream: %s", error)
            lines = []
        for raw in lines:
            record = Record.from_dict(raw)
            if record is not None:
                self.records[record.id] = record
                found = re.match(r"m(\d+)$", record.id)
                if found:
                    self.counter = max(self.counter, int(found.group(1)))
        try:
            index = self.store.read(INDEX, {}) or {}
            blob = self.store.read_bytes(VECTORS, b"")
        except (OSError, ValueError) as error:
            log.warning("could not read the memory numbers: %s", error)
            index, blob = {}, b""
        ids = [str(i) for i in index.get("ids") or []]
        dim = int(index.get("dim") or 0)
        if dim > 0 and len(blob) == len(ids) * dim * 2:
            width = dim * 2
            self.vectors = {i: blob[n * width : (n + 1) * width] for n, i in enumerate(ids) if i in self.records}
            self.dim = dim
            self.model = str(index.get("model") or "")
        self.waiting = {i for i in self.records if i not in self.vectors}

    def __len__(self) -> int:
        return len(self.records)

    def add(self, text: str, kind: str = "happened", by: str = "self", who: str | None = None, tier: str | None = None, about=(), mark: str = "", audience=(), until: float | None = None, weight: int = 3, pinned: bool = False, at: float | None = None, shared: bool = False) -> Record | None:
        text = " ".join(str(text or "").split())
        if not text or harsh(text):
            return None
        if len(text) > TEXT_MAX:
            text = text[: TEXT_MAX - 3].rstrip() + "..."
        self.counter += 1
        record = Record(
            id=f"m{self.counter}",
            t=self.clock.now() if at is None else float(at),
            kind=kind if kind in KINDS else "happened",
            text=text,
            by=by if by in SOURCES else "self",
            who=who,
            tier=tier,
            about=_tuple(list(about)),
            mark=mark if mark in MARKS else "private",
            audience=_tuple(list(audience)),
            until=until,
            importance=max(1, min(10, int(weight))),
            pinned=pinned,
            shared=bool(shared) and by == "person" and bool(who),
        )
        self.records[record.id] = record
        self.unsaved.append(record)
        self.waiting.add(record.id)
        return record

    def pending(self, limit: int = 32) -> list[Record]:
        found = [self.records[i] for i in self.waiting if i in self.records]
        return sorted(found, key=lambda r: r.t)[:limit]

    def attach(self, model: str, items: list[tuple[str, list[float]]]) -> int:
        if model != self.model and self.vectors:
            self.vectors = {}
            self.waiting = set(self.records)
        self.model = model
        merged = 0
        for record_id, vector in items:
            record = self.records.get(record_id)
            self.waiting.discard(record_id)
            if record is None or not vector:
                continue
            row = pack(vector)
            self.dim = len(row) // 2
            twin = self._twin(record, row)
            if twin is not None:
                twin.strength += 1
                twin.t = max(twin.t, record.t)
                twin.importance = max(twin.importance, record.importance)
                del self.records[record.id]
                self.unsaved = [r for r in self.unsaved if r.id != record.id]
                self.dirty = True
                merged += 1
                continue
            self.vectors[record.id] = row
            self.vectors_dirty = True
        return merged

    def _twin(self, record: Record, row: bytes) -> Record | None:
        same = [r for r in self.records.values() if r.id != record.id and r.id in self.vectors and r.mark == record.mark and r.audience == record.audience and r.by == record.by and r.who == record.who and r.shared == record.shared]
        if not same:
            return None
        scores = cosines(unpack(row), [self.vectors[r.id] for r in same])
        best = max(range(len(same)), key=lambda n: scores[n])
        return same[best] if scores[best] >= SAME else None

    def recall(self, query: list[float] | None, audience: frozenset, now: float, most: int = 3, weights: dict | None = None, here=(), skip=(), related: float | None = None, kinds=None, shelves=None) -> list[tuple[Record, float]]:
        found = [r for r in self.records.values() if r.id not in skip and visible(r, audience, now) and (kinds is None or r.kind in kinds) and (shelves is None or r.shelf in shelves)]
        return rank(found, [self.vectors.get(r.id) for r in found], query, now, most, weights, here, related)

    def old(self, query: list[float] | None, audience: frozenset, now: float, most: int = 3, weights: dict | None = None, here=(), related: float | None = None) -> list[tuple[Record, float]]:
        if not len(self.archive):
            return []
        found = self.archive.search(query, audience, now, most, self.model, weights, here, related)
        for record, _, month in found:
            self.revive.setdefault(month, {})[record.id] = now
        return [(record, score) for record, score, _ in found]

    def touch(self, records: list[Record], now: float) -> None:
        for record in records:
            if record.id in self.records:
                record.recalled += 1
                record.recalled_t = now
                record.shelf = HOT
                self.dirty = True

    def _drop(self, gone: list[Record]) -> int:
        for record in gone:
            self.records.pop(record.id, None)
            self.waiting.discard(record.id)
            if self.vectors.pop(record.id, None) is not None:
                self.vectors_dirty = True
        if gone:
            self.unsaved = [r for r in self.unsaved if r.id in self.records]
            self.dirty = True
        return len(gone)

    def forget(self, person_id: str, names: list[str]) -> int:
        words = [n.lower() for n in names if n and len(n) > 1]
        gone = []
        for record in list(self.records.values()):
            text = record.text.lower()
            if person_id in record.about or person_id in record.audience or record.who == person_id or any(re.search(rf"\b{re.escape(w)}\b", text) for w in words):
                gone.append(record)
        count = self._drop(gone)
        count += self.archive.rewrite(lambda record: "drop" if person_id in record.about or person_id in record.audience or record.who == person_id or any(re.search(rf"\b{re.escape(w)}\b", record.text.lower()) for w in words) else "keep")
        if count:
            self.save()
        return count

    def share(self, person_id: str, since: float, until: float) -> int:
        count = 0
        for record in self.records.values():
            if record.kind == "said" and record.by == "person" and record.who == person_id and since <= record.t <= until and not record.shared:
                record.shared = True
                count += 1
        if count:
            self.dirty = True
        return count

    def _people_in(self, record: Record) -> set:
        found = set(record.about) | set(record.audience) | ({record.who} if record.who else set())
        found |= {m.group(1).lower() for m in LABEL.finditer(record.text)}
        return found - {"?"}

    def _anonymised(self, record: Record, now: float, stranger) -> str:
        if now - record.t <= STRANGER_AFTER_S:
            return "keep"
        what = "keep"
        for person_id in sorted(self._people_in(record)):
            names = stranger(person_id)
            if names is None:
                continue
            if person_id in record.about and (record.kind in ABOUT_THEM or record.mark in WHO_THEY_ARE):
                return "drop"
            text = anonymised(record, person_id, list(names))
            if record.who == person_id:
                record.who = None
            record.about = tuple(a for a in record.about if a != person_id)
            record.audience = tuple(a for a in record.audience if a != person_id)
            if text != record.text:
                record.text = text[:TEXT_MAX]
            what = "changed"
        return what

    def anonymise(self, now: float, stranger) -> int:
        gone, changed = [], 0
        for record in list(self.records.values()):
            before = record.text
            what = self._anonymised(record, now, stranger)
            if what == "drop":
                gone.append(record)
                continue
            if what == "changed":
                if record.text != before:
                    if self.vectors.pop(record.id, None) is not None:
                        self.vectors_dirty = True
                    self.waiting.add(record.id)
                changed += 1
                self.dirty = True
        changed += self.archive.rewrite(lambda record: self._anonymised(record, now, stranger))
        return changed + self._drop(gone)

    def _unremembered(self, words: str) -> list[Record]:
        pattern = forget_phrase(words)
        if pattern is None:
            return []
        return [r for r in self.records.values() if not r.pinned and pattern.search(r.text.lower())]

    def matching(self, words: str) -> int:
        pattern = forget_phrase(words)
        archived = self.archive.matching(lambda r: not r.pinned and bool(pattern.search(r.text.lower()))) if pattern is not None else 0
        return len(self._unremembered(words)) + archived

    def unremember(self, words: str) -> int:
        count = self._drop(self._unremembered(words))
        pattern = forget_phrase(words)
        if pattern is not None:
            count += self.archive.rewrite(lambda r: "drop" if not r.pinned and pattern.search(r.text.lower()) else "keep")
        if count:
            self.save()
        return count

    def fade(self, now: float, stranger=None) -> int:
        count = self.anonymise(now, stranger) if stranger is not None else 0
        gone = [r for r in self.records.values() if (r.until is not None and now > r.until) or (not r.pinned and r.importance <= 3 and r.recalled == 0 and now - r.t > FADE_AFTER_S)]
        count += self._drop(gone)
        return count

    def _bring_back(self) -> int:
        if not self.revive:
            return 0
        wanted = {month: set(ids) for month, ids in self.revive.items()}
        back = self.archive.take(wanted)
        for record, row, model in back:
            used = self.revive.get(month_of(record.t), {}).get(record.id)
            record.recalled += 1
            record.recalled_t = used if used is not None else record.recalled_t
            record.shelf = HOT
            self.records[record.id] = record
            if row is not None and model == self.model:
                self.vectors[record.id] = row
                self.vectors_dirty = True
            else:
                self.waiting.add(record.id)
        self.revive = {}
        if back:
            self.dirty = True
        return len(back)

    def shelve(self, now: float) -> dict:
        report = {"back": self._bring_back(), "hot": 0, "warm": 0, "archived": 0}
        cold = []
        for record in self.records.values():
            shelf = shelf_of(record, now)
            if shelf is None:
                cold.append(record)
                continue
            if record.shelf != shelf:
                record.shelf = shelf
                self.dirty = True
        extra = len(self.records) - len(cold) - MOST
        if extra > 0:
            chosen = {r.id for r in cold}
            loose = sorted((r for r in self.records.values() if not r.pinned and r.id not in chosen), key=lambda r: (r.shelf == HOT, r.importance + 2 * r.recalled + r.strength, r.t))
            cold.extend(loose[:extra])
        if cold:
            report["archived"] = self.archive.put(cold, {r.id: self.vectors[r.id] for r in cold if r.id in self.vectors}, self.model)
            for record in cold:
                self.records.pop(record.id, None)
                self.waiting.discard(record.id)
                if self.vectors.pop(record.id, None) is not None:
                    self.vectors_dirty = True
            self.unsaved = [r for r in self.unsaved if r.id in self.records]
            self.dirty = True
        for record in self.records.values():
            report[record.shelf] += 1
        report["cold"] = len(self.archive)
        return report

    def dedupe(self) -> int:
        seen: dict = {}
        gone = []
        for record in sorted(self.records.values(), key=lambda r: r.t):
            key = (record.text.casefold(), record.kind, record.mark, record.audience, record.by, record.who, record.shared, record.until)
            first = seen.get(key)
            if first is None:
                seen[key] = record
                continue
            first.strength += record.strength
            first.importance = max(first.importance, record.importance)
            first.recalled += record.recalled
            first.recalled_t = max(first.recalled_t or 0.0, record.recalled_t or 0.0) or None
            first.pinned = first.pinned or record.pinned
            first.src = tuple(dict.fromkeys(first.src + record.src))
            gone.append(record)
        return self._drop(gone)

    def fold(self, now: float, labels: dict, places=()) -> list[Record]:
        groups: dict = {}
        rooms = [p for p in places if p]
        for record in self.records.values():
            if record.pinned or record.shelf != WARM or record.importance > FOLD_IMPORTANCE or record.kind not in FOLD_KINDS or record.src or now - record.t <= FOLD_AFTER_S:
                continue
            topics = [("person", a) for a in record.about if a in labels]
            if not topics:
                lowered = record.text.lower()
                topics = [("place", p) for p in rooms if re.search(rf"\b{re.escape(p.lower())}\b", lowered)][:1]
            for topic in topics[:1]:
                key = (topic, record.kind, record.mark, record.audience, record.by, record.who, record.shared)
                groups.setdefault(key, []).append(record)
        made, retire = [], []
        for (topic, kind, mark, audience, by, who, shared), members in groups.items():
            if len(members) < FOLD_MIN:
                continue
            members.sort(key=lambda r: r.t)
            lead = f"About {labels[topic[1]]}: " if topic[0] == "person" else f"About the {topic[1]}: "
            pieces, used = [], []
            for record in members:
                piece = _piece(record.text)
                joined = lead + "; ".join(pieces + [piece])
                if len(joined) > TEXT_MAX:
                    break
                pieces.append(piece)
                used.append(record)
            if len(used) < 2:
                continue
            about = tuple(dict.fromkeys(a for r in used for a in r.about))
            fold = self.add(lead + "; ".join(pieces), kind, by=by, who=who, about=about, mark=mark, audience=audience, weight=max(r.importance for r in used) + 1, at=used[-1].t, shared=shared)
            if fold is None:
                continue
            fold.src = tuple(r.id for r in used)
            fold.shelf = WARM
            retire.extend(used)
            made.append(fold)
        if retire:
            cold = retire
            self.archive.put(cold, {r.id: self.vectors[r.id] for r in cold if r.id in self.vectors}, self.model)
            for record in cold:
                self.records.pop(record.id, None)
                self.waiting.discard(record.id)
                if self.vectors.pop(record.id, None) is not None:
                    self.vectors_dirty = True
            self.unsaved = [r for r in self.unsaved if r.id in self.records]
            self.dirty = True
        return made

    def flush(self) -> int:
        if self.dirty or not self.unsaved:
            return 0
        written = 0
        for record in list(self.unsaved):
            try:
                self.store.append(RECORDS, record.as_dict())
            except OSError as error:
                log.warning("could not keep a memory: %s", error)
                break
            written += 1
        self.unsaved = self.unsaved[written:]
        return written

    def save(self) -> None:
        if self.dirty:
            ordered = sorted(self.records.values(), key=lambda r: r.t)
            self.store.rewrite_lines(RECORDS, [r.as_dict() for r in ordered])
            self.unsaved = []
            self.dirty = False
        else:
            self.flush()
        if self.vectors_dirty:
            ids = [r.id for r in sorted(self.records.values(), key=lambda r: r.t) if r.id in self.vectors]
            self.store.write_bytes(VECTORS, b"".join(self.vectors[i] for i in ids))
            self.store.write(INDEX, {"format": 1, "model": self.model, "dim": self.dim, "ids": ids})
            self.vectors_dirty = False
