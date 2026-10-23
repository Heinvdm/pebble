import logging

from ..clock import iso
from .growth import LESS, MORE
from .registry import OWNER, PEBBLE, PEOPLE

log = logging.getLogger(__name__)

JOURNAL = "journal.jsonl"
LATELY_S = 14 * 86400.0
SHOWN = 4
WORDS = {"words.self": "words", "words.style": "style", "words.examples": "style"}
SETTINGS = (
    (("wonder.", "thoughtfulness"), "how readily I stop to think"),
    (("doubt.",), "when a quick choice counts as a doubt"),
    (("events.",), "what praise, a kind touch and talk mean to me"),
    (("attention.",), "what catches my eye"),
    (("mood.", "rhythm.", "needs.", "startle", "getting_used"), "my moods and my rhythm"),
    (("gate.",), "when I say not now"),
    (("ideas.", "chaos.", "initiative."), "how I pick my own ideas"),
    (("recall.", "board."), "what comes to mind for me"),
    (("speakup.",), "how often I speak up unasked"),
)
THEN = (("I think I'm", "I thought I was"), ("and I like ", "and I liked "), ("I'm a lot like", "I was a lot like"))


def _lower(text: str) -> str:
    first = text.split(" ", 1)[0]
    if not text or first == "I" or first.startswith("I'"):
        return text
    return text[0].lower() + text[1:]


def setting_words(name: str) -> str:
    for starts, words in SETTINGS:
        if any(name.startswith(start) for start in starts):
            return words
    return "one of my own settings"


def because(entry: dict) -> str:
    by = entry.get("by")
    if by == PEOPLE:
        return "because someone close to me asked"
    if by == OWNER:
        return "because my owner set it"
    why = " ".join(str(entry.get("why") or "").split()).rstrip(".")
    return f"because {_lower(why)}" if why else ""


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def said(entry: dict) -> str:
    kind = entry.get("kind")
    what = str(entry.get("what") or "")
    before, after = _number(entry.get("from")), _number(entry.get("to"))
    if kind == "trait" and before is not None and after is not None and after != before:
        line = f"I became a little {(MORE if after > before else LESS).get(what, ('more ' if after > before else 'less ') + what)}"
    elif kind == "value" and entry.get("by") == OWNER:
        return f"my owner set how much I care about {what}"
    elif kind == "value":
        up, _, down = what.partition(">")
        line = f"my {up} grew a little and my {down} eased off" if down else f"my {up} changed a little"
    elif kind == "words":
        line = "I changed a sentence in how I describe myself"
    elif kind == "style":
        line = "I changed how I speak"
    elif kind == "setting":
        return f"I adjusted {setting_words(what)}"
    elif kind == "note":
        return "I tidied the notes I keep"
    elif kind == "file":
        return "I made and changed things in my own folder"
    elif kind == "wondering":
        return "I started wondering about something new"
    elif kind == "script":
        return "I started running a new program"
    else:
        return ""
    reason = because(entry)
    return f"{line}, {reason}" if reason else line


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return "; ".join(parts[:-1]) + "; and " + parts[-1]


def then(line: str) -> str:
    line = " ".join(str(line or "").split())
    for now_words, past_words in THEN:
        line = line.replace(now_words, past_words)
    return line


class Journal:
    def __init__(self, store, clock):
        self.store = store
        self.clock = clock

    def add(self, kind: str, what: str, before=None, after=None, by: str = PEBBLE, why: str = "") -> dict:
        now = self.clock.now()
        entry = {"at": iso(now), "t": round(now, 3), "kind": kind, "what": str(what)[:80], "from": before, "to": after, "by": by, "why": " ".join(str(why or "").split())[:200]}
        try:
            self.store.append(JOURNAL, entry)
        except OSError as error:
            log.warning("could not write the journal: %s", error)
        return entry

    def take(self, kind: str, data: dict) -> dict | None:
        who = data.get("who", PEBBLE)
        why = data.get("why", "")
        if kind == "dial_changed":
            name = str(data.get("dial") or "")
            if name.startswith("trait."):
                return self.add("trait", name.split(".", 1)[1], data.get("before"), data.get("after"), who, why)
            if name in WORDS:
                return self.add(WORDS[name], name, data.get("before"), data.get("after"), who, why)
            if name.startswith("value."):
                return None
            return self.add("setting", name, data.get("before"), data.get("after"), who, why)
        if kind == "value_changed":
            up, down = data.get("up"), data.get("down")
            return self.add("value", f"{up}>{down}", {up: data.get("up_to", 0) - 1, down: data.get("down_to", 0) + 1}, {up: data.get("up_to"), down: data.get("down_to")}, who, why)
        if kind == "value_set":
            return self.add("value", str(data.get("value")), data.get("before"), data.get("after"), OWNER, why)
        if kind == "trait_changed":
            return self.add("trait", str(data.get("trait")), data.get("before"), data.get("after"), who, why)
        if kind == "mine_changed":
            return self.add("file", str(data.get("name")), data.get("before"), data.get("after"), PEBBLE, str(data.get("action") or ""))
        if kind == "note_changed":
            return self.add("note", str(data.get("id")), data.get("before"), data.get("after"), PEBBLE, str(data.get("op") or ""))
        if kind == "wondering":
            return self.add("wondering", str(data.get("text") or ""), None, None, PEBBLE, str(data.get("why") or ""))
        if kind == "script_live":
            return self.add("script", str(data.get("script") or ""), None, data.get("version"), PEBBLE if data.get("who") == "pebble" else PEOPLE, f"a program {'of my own' if data.get('who') == 'pebble' else 'someone asked for'}")
        return None

    def entries(self, since: float | None = None) -> list[dict]:
        found = [e for e in self.store.read_lines(JOURNAL) if isinstance(e, dict)]
        if since is None:
            return found
        return [e for e in found if isinstance(e.get("t"), (int, float)) and e["t"] >= since]

    def lately(self, now: float | None = None, within: float = LATELY_S) -> str:
        now = self.clock.now() if now is None else now
        parts: list[str] = []
        for entry in reversed(self.entries(now - within)):
            line = said(entry)
            if line and line not in parts:
                parts.append(line)
            if len(parts) >= SHOWN:
                break
        if not parts:
            return "Nothing much has changed in me lately."
        text = "Lately " + _join(parts) + "."
        return text[0].upper() + text[1:]

    def since_birth(self, birth: dict, traits: dict, values: dict, words: str) -> str:
        if not birth.get("born"):
            return "I haven't really been born yet: I'm still being put together and set up."
        drawn = birth.get("drawn") or {}
        then_traits = drawn.get("traits") or {}
        then_values = drawn.get("values") or {}
        moved = []
        for name, now_value in sorted(traits.items()):
            before = _number(then_traits.get(name))
            after = _number(now_value)
            if before is None or after is None or before == after:
                continue
            moved.append((MORE if after > before else LESS).get(name, ("more " if after > before else "less ") + name))
        cares = []
        for name, now_value in sorted(values.items()):
            before = _number(then_values.get(name))
            after = _number(now_value)
            if before is None or after is None or before == after:
                continue
            cares.append(f"{'more' if after > before else 'less'} about {name}")
        start = then(birth.get("line", "")) or "I was a lot like other Pebbles."
        start = f"When I was born, {_lower(start)}"
        changes = []
        if moved:
            changes.append("I've become " + " and ".join(moved[:3]))
        if cares:
            changes.append("I care " + " and ".join(cares[:3]))
        seed = " ".join(str(birth.get("words") or "").split())
        if words and " ".join(words.split()) != seed:
            changes.append("I describe myself a little differently now")
        if not changes:
            return f"{start} I'm still much as I was then."
        return f"{start} Since then, " + _join(changes) + "."
