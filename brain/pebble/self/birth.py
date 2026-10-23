import logging
import random
import secrets

from ..chaos.streams import derive
from ..selfstore.atomic import CorruptFile, TamperedFile, read_json
from ..selfstore.store import BIRTH, TEMPLATE_DIR
from .registry import ADD, BETWEEN, DIALS, PERSONALITY, TIMES, VALUES, born_with, entry

log = logging.getLogger(__name__)

SEED_BITS = 64
RUN_BITS = 48
FIRST_TASTES = {
    "round things": ("ball", "balloon", "orange"),
    "plants": ("plant", "flower", "plant pot"),
    "music": ("guitar", "piano", "radio"),
    "books": ("book",),
    "my blanket": ("blanket", "cushion"),
}


class BirthFixed(PermissionError):
    pass


def record_of(store) -> dict:
    try:
        data = store.read(BIRTH, None)
    except (CorruptFile, TamperedFile):
        log.warning("the birth record could not be read")
        data = None
    return dict(data) if isinstance(data, dict) else {"format": 1}


def seed_of(store) -> int | None:
    raw = record_of(store).get("seed")
    try:
        return int(str(raw), 16) if raw else None
    except ValueError:
        return None


def ensure_seed(store) -> int:
    seed = seed_of(store)
    if seed is not None:
        return seed
    record = record_of(store)
    seed = secrets.randbits(SEED_BITS)
    record["seed"] = f"{seed:016x}"
    record["draw"] = int(record.get("draw") or 1)
    store.write(BIRTH, record)
    return seed


def run_seed(seed: int, boots: int, label: str = "run") -> int:
    return derive(seed, label, boots) % (2**RUN_BITS)


def template() -> tuple[dict, dict]:
    return read_json(TEMPLATE_DIR / PERSONALITY), read_json(TEMPLATE_DIR / VALUES)


def _clamp(value, low, high):
    return max(low, min(high, value))


def _traits(rng: random.Random, personality: dict) -> dict:
    out = {}
    ranges = personality.get("ranges") or {}
    for name in sorted(personality.get("traits") or {}):
        found = entry(f"trait.{name}")
        how = found.birth if found is not None and found.birth else (ADD, -2, 2)
        low, high = (int(x) for x in ranges.get(name, (0, 10)))
        if found is not None and found.floor is not None:
            low = max(low, int(found.floor))
        out[name] = _clamp(int(personality["traits"][name]) + rng.randint(int(how[1]), int(how[2])), low, high)
    return out


def _values(rng: random.Random, values: dict) -> dict:
    out = {}
    dials = values.get("dials") or {}
    for name in sorted(dials):
        raw = dials[name]
        found = entry(f"value.{name}")
        if found is None or found.birth is None or raw.get("owner_only"):
            continue
        low, high = int(raw.get("min", 0)), int(raw.get("max", 10))
        if found.floor is not None:
            low = max(low, int(found.floor))
        out[name] = _clamp(int(raw.get("start", low)) + rng.randint(int(found.birth[1]), int(found.birth[2])), low, high)
    return out


def _dials(rng: random.Random) -> dict:
    out = {}
    for found in born_with():
        if found.home != DIALS:
            continue
        how, low, high = found.birth
        if how == BETWEEN:
            value = rng.uniform(low, high)
        elif how == TIMES:
            value = float(found.default) * rng.uniform(low, high)
        else:
            value = float(found.default) + rng.uniform(low, high)
        out[found.name] = round(value, found.places)
    return out


def draw(seed: int, number: int, personality: dict | None = None, values: dict | None = None) -> dict:
    if personality is None or values is None:
        personality, values = template()
    rng = random.Random(derive(seed, "birth", number))
    traits = _traits(rng, personality)
    drawn_values = _values(rng, values)
    dials = _dials(rng)
    tastes = rng.sample(list(FIRST_TASTES), rng.randint(1, 2))
    return {"number": number, "traits": traits, "values": drawn_values, "dials": dials, "tastes": tastes}


def _join(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _notable(drawn: dict, personality: dict) -> list[str]:
    base = personality.get("traits") or {}
    traits = drawn.get("traits") or {}
    dials = drawn.get("dials") or {}

    def up(name: str) -> int:
        return int(traits.get(name, base.get(name, 5))) - int(base.get(name, 5))

    found = []
    for trait, word in (("curious", "very curious"), ("playful", "very playful"), ("affectionate", "very cuddly"), ("cautious", "careful")):
        if up(trait) >= 2:
            found.append(word)
    if up("chatty") >= 2:
        found.append("chatty")
    elif up("chatty") <= -2:
        found.append("quiet")
    shift = float(dials.get("rhythm.shift_h", 0.0))
    if shift >= 0.75:
        found.append("a bit of a night owl")
    elif shift <= -0.75:
        found.append("an early bird")
    resting = float(dials.get("mood.resting", 0.2))
    if resting >= 0.27:
        found.append("sunny")
    elif resting <= 0.13:
        found.append("a bit serious")
    company = float(dials.get("needs.company", 1.0))
    if company >= 1.25:
        found.append("keen on company")
    elif company <= 0.8:
        found.append("happy on my own")
    return found[:3]


def describe(drawn: dict, personality: dict | None = None) -> tuple[str, str]:
    personality = personality or template()[0]
    found = _notable(drawn, personality)
    tastes = _join(list(drawn.get("tastes") or []))
    likes = f", and I like {tastes}." if tastes else "."
    if found:
        return f"I think I'm {_join(found)}{likes}", f"I'm a small robot, {_join(found)}{likes}"
    return f"I think I'm a lot like other Pebbles so far{likes}", f"I'm a small robot{likes}"


def preview(store) -> dict:
    ensure_seed(store)
    record = record_of(store)
    if record.get("born"):
        return {"born": record["born"], "draw": record.get("draw"), "drawn": record.get("drawn"), "line": record.get("line", "")}
    number = int(record.get("draw") or 1)
    drawn = draw(seed_of(store), number)
    return {"born": None, "draw": number, "drawn": drawn, "line": describe(drawn)[0]}


def redraw(store) -> dict:
    ensure_seed(store)
    record = record_of(store)
    if record.get("born"):
        raise BirthFixed(f"Pebble was born on {record['born']}, and the draw it was born with is its own")
    record["draw"] = int(record.get("draw") or 1) + 1
    store.write(BIRTH, record)
    return preview(store)


def be_born(store, books, dials, book, born: str | None, now: float, today: str) -> dict | None:
    record = record_of(store)
    if record.get("born"):
        return None
    seed = ensure_seed(store)
    record = record_of(store)
    number = int(record.get("draw") or 1)
    base_personality, base_values = template()
    drawn = draw(seed, number, base_personality, base_values)
    kept = []
    personality = store.read(PERSONALITY, {}) or {}
    traits = dict(personality.get("traits") or {})
    for name, value in drawn["traits"].items():
        if name in traits and int(traits[name]) != int(base_personality["traits"][name]):
            kept.append(f"trait.{name}")
            continue
        traits[name] = value
    store.write(PERSONALITY, {**personality, "traits": traits})
    starts = base_values.get("dials") or {}
    for name, value in drawn["values"].items():
        dial = books.values.dials.get(name)
        if dial is None:
            continue
        start = int((starts.get(name) or {}).get("start", dial.start))
        if dial.value != start or dial.start != start:
            kept.append(f"value.{name}")
            continue
        dial.start = dial.value = value
    books.save("values")
    dials.born(drawn["dials"])
    if book is not None:
        book.reborn(traits, [kind for taste in drawn["tastes"] for kind in FIRST_TASTES.get(taste, ())], now)
    line, words = describe(drawn, base_personality)
    born = born or today
    record.update({"born": born, "draw": number, "drawn": drawn, "line": line, "words": words, "kept": kept, "late": born < today})
    store.write(BIRTH, record)
    return record
