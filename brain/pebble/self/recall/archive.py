import logging
import re
from datetime import datetime, timezone

from .vectors import cosines

log = logging.getLogger(__name__)

ROOT = "stream/archive"
INDEX = f"{ROOT}/index.json"
HOUR_S = 3600.0
RECENCY = 0.995
CANDIDATES = 64
OLD = re.compile(
    r"\b(?:last|that|the other)\s+(?:year|summer|winter|spring|autumn|fall|christmas|easter|holidays?|birthday)\b"
    r"|\b(?:a|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|several|some|many|few|\d+)\s+(?:years?|months?)\s+ago\b"
    r"|\b(?:a\s+)?(?:long|while)\s+(?:time\s+)?ago\b|\bages ago\b|\byears ago\b|\bmonths ago\b|\bback in\b|\bback when\b|\bthe first time\b"
    r"|\bwhen you were (?:little|new|small|young|a baby)\b|\bin (?:january|february|march|april|may|june|july|august|september|october|november|december)\b",
    re.IGNORECASE,
)


def asks_old(text: str) -> bool:
    return bool(OLD.search(text or ""))


def month_of(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m")


def _paths(month: str) -> tuple[str, str]:
    return f"{ROOT}/{month}.json", f"{ROOT}/{month}.bin"


def _top(records) -> int:
    return max((int(r.id[1:]) for r in records if r.id[1:].isdigit()), default=0)


class Archive:
    def __init__(self, store, record_type, visible):
        self.store = store
        self.record_type = record_type
        self.visible = visible
        try:
            data = store.read(INDEX, {}) or {}
        except Exception:
            log.exception("could not read the memory archive's index")
            data = {}
        self.counts: dict[str, int] = {str(k): int(v) for k, v in (data.get("months") or {}).items() if isinstance(v, (int, float))}
        self.tops: dict[str, int] = {str(k): int(v) for k, v in (data.get("tops") or {}).items() if isinstance(v, (int, float))}

    def __len__(self) -> int:
        return sum(self.counts.values())

    def top(self) -> int:
        return max(self.tops.values(), default=0)

    def months(self) -> list[str]:
        return sorted(self.counts)

    def _save_index(self) -> None:
        self.store.write(INDEX, {"format": 1, "months": dict(sorted(self.counts.items())), "tops": dict(sorted(self.tops.items()))})

    def raw(self, month: str) -> tuple[list, dict, str]:
        data_path, blob_path = _paths(month)
        try:
            data = self.store.read(data_path, {}) or {}
            blob = self.store.read_bytes(blob_path, b"")
        except (OSError, ValueError) as error:
            log.warning("could not read archived memories for %s: %s", month, error)
            return [], {}, ""
        ids = [str(i) for i in data.get("ids") or []]
        dim = int(data.get("dim") or 0)
        vectors = {}
        if dim > 0 and len(blob) == len(ids) * dim * 2:
            width = dim * 2
            vectors = {i: blob[n * width:(n + 1) * width] for n, i in enumerate(ids)}
        return [r for r in data.get("records") or [] if isinstance(r, dict)], vectors, str(data.get("model") or "")

    def load(self, month: str) -> tuple[list, dict, str]:
        raws, vectors, model = self.raw(month)
        return [r for r in (self.record_type.from_dict(raw) for raw in raws) if r is not None], vectors, model

    def _write(self, month: str, records: list, vectors: dict, model: str) -> None:
        data_path, blob_path = _paths(month)
        if not records:
            for name in (data_path, blob_path):
                self.store.remove(name)
            self.counts.pop(month, None)
            self.tops.pop(month, None)
            return
        ordered = sorted(records, key=lambda r: r.t)
        ids = [r.id for r in ordered if r.id in vectors]
        dim = len(vectors[ids[0]]) // 2 if ids else 0
        self.store.write_bytes(blob_path, b"".join(vectors[i] for i in ids))
        self.store.write(data_path, {"format": 1, "model": model, "dim": dim, "ids": ids, "records": [r.as_dict() for r in ordered]})
        self.counts[month] = len(ordered)
        self.tops[month] = _top(ordered)

    def put(self, records: list, vectors: dict, model: str) -> int:
        groups: dict[str, list] = {}
        for record in records:
            groups.setdefault(month_of(record.t), []).append(record)
        for month, fresh in groups.items():
            old, old_vectors, old_model = self.load(month) if month in self.counts else ([], {}, model)
            if old_model and old_model != model:
                old_vectors = {}
            known = {r.id for r in old}
            merged = old + [r for r in fresh if r.id not in known]
            rows = dict(old_vectors)
            rows.update({r.id: vectors[r.id] for r in fresh if r.id in vectors})
            self._write(month, merged, rows, model)
        if groups:
            self._save_index()
        return sum(len(v) for v in groups.values())

    def take(self, wanted: dict) -> list:
        out = []
        for month, ids in wanted.items():
            if month not in self.counts:
                continue
            records, vectors, model = self.load(month)
            found = [r for r in records if r.id in ids]
            if not found:
                continue
            out.extend((r, vectors.get(r.id), model) for r in found)
            self._write(month, [r for r in records if r.id not in ids], {k: v for k, v in vectors.items() if k not in ids}, model)
        if out:
            self._save_index()
        return out

    def rewrite(self, change) -> int:
        changed = 0
        for month in self.months():
            records, vectors, model = self.load(month)
            kept, touched = [], False
            for record in records:
                what = change(record)
                if what in ("drop", "changed"):
                    vectors.pop(record.id, None)
                    touched = True
                    changed += 1
                if what != "drop":
                    kept.append(record)
            if touched:
                self._write(month, kept, vectors, model)
        if changed:
            self._save_index()
        return changed

    def matching(self, test) -> int:
        count = 0
        for month in self.months():
            records, _, _ = self.load(month)
            count += sum(1 for r in records if test(r))
        return count

    def search(self, query, audience: frozenset, now: float, most: int, model: str, weights: dict | None = None, here=(), related: float | None = None) -> list:
        weights = weights or {}
        here = set(here or ())
        best: list = []
        for month in reversed(self.months()):
            raws, vectors, month_model = self.raw(month)
            if not raws:
                continue
            relevance = [0.0] * len(raws)
            if query and month_model == model:
                known = [n for n, raw in enumerate(raws) if str(raw.get("id")) in vectors]
                scores = cosines(query, [vectors[str(raws[n]["id"])] for n in known])
                for n, score in zip(known, scores):
                    relevance[n] = score
                order = sorted((n for n in known if related is None or relevance[n] >= related), key=lambda n: -relevance[n])
            else:
                order = sorted(range(len(raws)), key=lambda n: -(float(raws[n].get("i") or 3) + float(raws[n].get("t") or 0.0) / 1e9))
            picked = 0
            for n in order:
                record = self.record_type.from_dict(raws[n])
                if record is None or not self.visible(record, audience, now):
                    continue
                recency = RECENCY ** (max(0.0, now - (record.recalled_t or record.t)) / HOUR_S)
                lift = 1.0 if here & (set(record.about) | ({record.who} if record.who else set())) else 0.0
                total = float(weights.get("recency", 1.0)) * recency + float(weights.get("importance", 1.0)) * record.importance / 10.0 + float(weights.get("relevance", 1.0)) * relevance[n] + float(weights.get("people", 1.0)) * lift
                best.append((record, total, month))
                picked += 1
                if picked >= CANDIDATES:
                    break
            best.sort(key=lambda item: (-item[1], -item[0].t))
            del best[most:]
        return best
