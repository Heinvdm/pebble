import logging
import math
import re
from dataclasses import dataclass, field

from ..things.words import singular
from .budget import ESTIMATE_MARGIN, MATCHED, PIXEL_WINDOW, budgets

log = logging.getLogger(__name__)

HOT, WARM, COLD = "hot", "warm", "cold"
SHELVES = (HOT, WARM, COLD)
NAMEABLE = frozenset({HOT, WARM})
DAY_S = 86400.0
HOT_S = 30 * DAY_S
COLD_S = 180 * DAY_S
HALF_LIFE_S = 14 * DAY_S
RATIO = 3.0
NAMED_SHARE = 0.45
FUZZY_FROM = 5
PHRASE_MOST = 6
SHELF_FILE = "shelves.json"
END = ""
WORD = re.compile(r"[a-z0-9']+")
LEADING = frozenset({"the", "a", "an", "my", "our", "your", "his", "her", "their", "this", "that"})
STOP = frozenset(
    """a an the and or but if then so to of in on at by for with from up down out over under into onto off about after again
    i me my mine you your yours he him his she her hers it its we us our they them their this that these those there here
    what which who whom whose when where why how is are was were be been being am do does did done have has had having
    can could would should will shall may might must not no yes nor too very just only also all any some each every both
    more most less much many few other another such same own than now still even ever never always often again really
    maybe today tonight tomorrow yesterday morning evening night later soon please thanks thank okay ok oh hey hi hello
    one two three four five six seven eight nine ten first last next new old good bad little big bit lot like want need
    know think thing things something anything everything nothing go going gone get got come came make made take took
    see saw look said say tell told ask asked let put give gave keep kept back way well right left time day week year
    pebble""".split()
)
DEFAULT_WEIGHTS = {"meaning": 2.0, "recency": 1.0, "use": 0.5, "importance": 0.5, "who": 1.0, "where": 1.0}
CAPITAL = re.compile(r"\b[A-Z][a-z]+(?:'s)?\b")
NOT_NAMES = frozenset(
    """I I'm I'll I've I'd A An The This That These Those It It's He She They We You Your My Our His Her Their There Here
    When Where What Who Why How If And But Or So Then Also Yes No Not Some Every Each Both Today Tonight Tomorrow
    Yesterday Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May June July August
    September October November December Mum Mom Dad Nana Grandma Grandad Grandpa Christmas Easter""".split()
)


def chars(tokens: int) -> int:
    return max(0, int(tokens * RATIO / ESTIMATE_MARGIN))


def named_chars(kind: str) -> int:
    return int(chars(budgets(kind, PIXEL_WINDOW)[MATCHED]) * NAMED_SHARE)


def chosen_chars(kind: str) -> int:
    return chars(budgets(kind, PIXEL_WINDOW)[MATCHED]) - named_chars(kind)


def tokens_of(text: str) -> int:
    return math.ceil(len(text or "") / RATIO * ESTIMATE_MARGIN)


def word_list(text: str) -> list[str]:
    lowered = str(text or "").lower().replace("’", "'").replace("-", " ").replace("_", " ")
    out = []
    for word in WORD.findall(lowered):
        word = word.strip("'")
        if word.endswith("'s"):
            word = word[:-2]
        word = word.replace("'", "")
        if word:
            out.append(singular(word))
    return out


def name_words(name: str) -> list[str]:
    words = word_list(name)
    while words and words[0] in LEADING:
        words = words[1:]
    return words[:PHRASE_MOST] if len(words) <= PHRASE_MOST else []


def content(text: str) -> set:
    return {w for w in word_list(text) if w not in STOP and len(w) > 2}


def _deletions(word: str) -> set:
    return {word[:n] + word[n + 1:] for n in range(len(word))}


@dataclass
class Entry:
    kind: str
    key: str
    names: tuple = ()
    short: str = ""
    long: str = ""
    text: str = ""
    t: float = 0.0
    used: int = 0
    weight: float = 0.0
    about: tuple = ()
    place: str = ""
    pinned: bool = False
    data: object = field(default=None, repr=False, compare=False)

    @property
    def id(self) -> str:
        return f"{self.kind}:{self.key}"


@dataclass(frozen=True)
class Hit:
    entry: Entry
    start: int
    end: int
    said: str


class Names:
    def __init__(self, entries: list[Entry]):
        self.entries = list(entries)
        self.trie: dict = {}
        self.vocab: set = set()
        self.near: dict = {}
        for index, entry in enumerate(self.entries):
            for name in entry.names:
                words = name_words(name)
                if not words or all(w in STOP for w in words) or len("".join(words)) < 2:
                    continue
                node = self.trie
                for word in words:
                    node = node.setdefault(word, {})
                    self.vocab.add(word)
                node.setdefault(END, set()).add(index)
        for word in self.vocab:
            if len(word) >= FUZZY_FROM and word not in STOP:
                for variant in _deletions(word) | {word}:
                    self.near.setdefault(variant, set()).add(word)

    def __len__(self) -> int:
        return len(self.entries)

    def _options(self, word: str) -> tuple:
        if word in self.vocab:
            return (word,)
        if len(word) < FUZZY_FROM or word in STOP:
            return ()
        found = set()
        for variant in _deletions(word) | {word}:
            for known in self.near.get(variant, ()):
                if known[0] == word[0] and abs(len(known) - len(word)) <= 1:
                    found.add(known)
        return tuple(sorted(found))

    def scan(self, text: str) -> list[Hit]:
        words = word_list(text)
        if not words:
            return []
        options = [self._options(w) for w in words]
        spans = []
        for start in range(len(words)):
            if not options[start]:
                continue
            stack = [(self.trie, start)]
            while stack:
                node, at = stack.pop()
                if at > start and END in node:
                    for index in node[END]:
                        spans.append((start, at, index))
                if at < len(words) and at - start < PHRASE_MOST:
                    for word in options[at]:
                        child = node.get(word)
                        if child is not None:
                            stack.append((child, at + 1))
        spans.sort(key=lambda s: (-(s[1] - s[0]), s[0], s[2]))
        taken: set = set()
        seen: set = set()
        hits = []
        for start, end, index in spans:
            if index in seen:
                continue
            covered = set(range(start, end))
            if covered & taken and not any(h.start == start and h.end == end for h in hits):
                continue
            seen.add(index)
            taken |= covered
            hits.append(Hit(self.entries[index], start, end, " ".join(words[start:end])))
        hits.sort(key=lambda h: (h.start, h.entry.kind, h.entry.key))
        return hits


def shelf_by_age(age_s: float, pinned: bool = False) -> str:
    if pinned or age_s <= HOT_S:
        return HOT
    if age_s <= COLD_S:
        return WARM
    return COLD


def cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    top = sum(x * y for x, y in zip(a, b))
    size = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return top / size if size else 0.0


def score(entry: Entry, now: float, query=None, vector=None, here=frozenset(), room: str = "", weights: dict | None = None) -> float:
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    meaning = cosine(query, vector) if query is not None and vector is not None else 0.0
    age = max(0.0, now - entry.t) if entry.t else COLD_S
    recency = 0.5 ** (age / HALF_LIFE_S)
    use = 1.0 - 1.0 / (1.0 + max(0, entry.used))
    who = 1.0 if here and set(entry.about) & set(here) else 0.0
    where = 1.0 if room and entry.place and entry.place == room else 0.0
    return weights["meaning"] * meaning + weights["recency"] * recency + weights["use"] * use + weights["importance"] * max(0.0, min(1.0, entry.weight)) + weights["who"] * who + weights["where"] * where


def relevant(items: list[str], talk: str, most: int) -> list[str]:
    if len(items) <= most:
        return list(items)
    wanted = content(talk)
    order = []
    for n, item in enumerate(items):
        overlap = len(content(item) & wanted)
        order.append((overlap, n, item))
    chosen = sorted(order, key=lambda o: (-o[0], -o[1]))[:most]
    return [item for _, _, item in sorted(chosen, key=lambda o: o[1])]


def pack(lines: list[tuple[str, str]], budget_chars: int, joiner: str = "\n") -> list[str]:
    out, used = [], 0
    for long, short in lines:
        for text in (long, short):
            if not text:
                continue
            cost = len(text) + (len(joiner) if out else 0)
            if used + cost <= budget_chars:
                out.append(text)
                used += cost
                break
    return out


def unknown_names(text: str, known, source: str = "", own: str = "pebble") -> list[str]:
    known_words = {w for name in known for w in word_list(name)}
    source_words = set(word_list(source))
    out = []
    for found in CAPITAL.finditer(str(text or "")):
        word = found.group(0)
        bare = word[:-2] if word.endswith("'s") else word
        if bare in NOT_NAMES or bare.lower() == own.lower() or bare.lower() in STOP:
            continue
        normal = singular(bare.lower())
        if normal in known_words or normal in source_words:
            continue
        out.append(bare)
    return list(dict.fromkeys(out))


class Shelves:
    def __init__(self, store, clock):
        self.store = store
        self.clock = clock
        try:
            data = store.read(SHELF_FILE, {}) or {}
        except Exception:
            log.exception("could not read the shelves; starting with none")
            data = {}
        self.day = str(data.get("day") or "")
        self.items: dict[str, dict] = {str(k): dict(v) for k, v in (data.get("items") or {}).items() if isinstance(v, dict)}
        self.dirty = False

    def shelf(self, entry: Entry, now: float | None = None) -> str:
        found = self.items.get(entry.id)
        if found and found.get("s") in SHELVES:
            return found["s"]
        now = self.clock.now() if now is None else now
        return shelf_by_age(max(0.0, now - max(entry.t, 0.0)) if entry.t else COLD_S, entry.pinned)

    def last(self, entry: Entry) -> float:
        found = self.items.get(entry.id) or {}
        return max(entry.t, float(found.get("t") or 0.0))

    def uses(self, entry: Entry) -> int:
        found = self.items.get(entry.id) or {}
        return entry.used + int(found.get("u") or 0)

    def use(self, entry: Entry, now: float | None = None) -> None:
        now = self.clock.now() if now is None else now
        found = self.items.setdefault(entry.id, {})
        found["u"] = int(found.get("u") or 0) + 1
        found["t"] = now
        found["s"] = HOT
        self.dirty = True

    def sort(self, entries: list[Entry], now: float | None = None) -> dict:
        now = self.clock.now() if now is None else now
        report = {HOT: 0, WARM: 0, COLD: 0, "up": 0, "down": 0}
        seen = set()
        for entry in entries:
            seen.add(entry.id)
            last = self.last(entry)
            shelf = shelf_by_age(now - last if last else COLD_S, entry.pinned)
            found = self.items.setdefault(entry.id, {})
            before = found.get("s")
            if before in SHELVES and before != shelf:
                report["up" if SHELVES.index(shelf) < SHELVES.index(before) else "down"] += 1
            found["s"] = shelf
            if last:
                found["t"] = last
            report[shelf] += 1
        for gone in [key for key in self.items if key not in seen]:
            self.items.pop(gone, None)
        self.day = self.clock.local(now).date().isoformat()
        self.dirty = True
        self.save()
        return report

    def forget(self, ids) -> None:
        for key in ids:
            if self.items.pop(key, None) is not None:
                self.dirty = True
        self.save()

    def save(self) -> None:
        if not self.dirty:
            return
        try:
            self.store.write(SHELF_FILE, {"format": 1, "day": self.day, "items": self.items})
            self.dirty = False
        except Exception:
            log.exception("could not keep the shelves")
