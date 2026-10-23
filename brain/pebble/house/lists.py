from ..things.words import listing

LISTS_CAP = 8
ITEMS_CAP = 60
READ_OUT = 10
SINGULAR_ENDINGS = ("ss", "us", "is")


def title(name: str) -> str:
    return "to-do list" if name == "to do" else f"{name} list"


def _same(a: str, b: str) -> bool:
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return True
    for x, y in ((a, b), (b, a)):
        if x.endswith("es") and x[:-2] == y or x.endswith("s") and not x.endswith(SINGULAR_ENDINGS) and x[:-1] == y:
            return True
    return False


def _verb(items: list[str]) -> str:
    if len(items) > 1:
        return "are"
    word = items[0].split()[-1]
    return "are" if word.endswith("s") and not word.endswith(SINGULAR_ENDINGS) else "is"


class Lists:
    def __init__(self, data: dict):
        self.data = data

    def items(self, name: str) -> list[dict]:
        return list(self.data.get(name) or [])

    def names(self) -> list[str]:
        return sorted(self.data)

    def count(self, name: str) -> int:
        return len(self.data.get(name) or [])

    def has(self, item: str) -> str | None:
        for name, items in self.data.items():
            if any(_same(entry["text"], item) for entry in items):
                return name
        return None

    def add(self, name: str, items: list[str], by: str | None, at: float) -> tuple[list[str], list[str], bool]:
        if name not in self.data and len(self.data) >= LISTS_CAP:
            return [], [], True
        entries = self.data.setdefault(name, [])
        added, already = [], []
        for item in items:
            if any(_same(entry["text"], item) for entry in entries):
                already.append(item)
                continue
            if len(entries) >= ITEMS_CAP:
                return added, already, True
            entries.append({"text": item, "by": by, "at": at})
            added.append(item)
        return added, already, False

    def remove(self, name: str, items: list[str]) -> tuple[list[str], list[str]]:
        entries = self.data.get(name) or []
        gone, missing = [], []
        for item in items:
            found = next((entry for entry in entries if _same(entry["text"], item)), None)
            if found is None:
                missing.append(item)
                continue
            entries.remove(found)
            gone.append(item)
        if name in self.data and not entries:
            del self.data[name]
        return gone, missing

    def clear(self, name: str) -> int:
        return len(self.data.pop(name, None) or [])

    def forget_person(self, person_id: str) -> bool:
        changed = False
        for entries in self.data.values():
            for entry in entries:
                if entry.get("by") == person_id:
                    entry["by"] = None
                    changed = True
        return changed

    def added_line(self, name: str, added: list[str], already: list[str], full: bool) -> str:
        parts = []
        if added:
            parts.append(f"Okay, {listing(added)} {_verb(added)} on the {title(name)}.")
        if already:
            parts.append(f"{listing(already)[:1].upper()}{listing(already)[1:]} {_verb(already)} already on it.")
        if full:
            parts.append("The list is full, so I couldn't add any more.")
        return " ".join(parts) or "Okay."

    def removed_line(self, name: str, gone: list[str], missing: list[str]) -> str:
        parts = []
        if gone:
            parts.append(f"Okay, I've taken {listing(gone)} off the {title(name)}.")
        if missing:
            parts.append(f"{listing(missing)[:1].upper()}{listing(missing)[1:]} {'was' if len(missing) == 1 else 'were'} not on the {title(name)}.")
        return " ".join(parts) or "Okay."

    def read_line(self, name: str) -> str:
        items = [entry["text"] for entry in self.items(name)]
        if not items:
            return f"The {title(name)} is empty."
        thing = "thing" if len(items) == 1 else "things"
        if len(items) <= READ_OUT:
            return f"The {title(name)} has {len(items)} {thing}: {listing(items)}."
        rest = len(items) - READ_OUT
        return f"The {title(name)} has {len(items)} things: {', '.join(items[:READ_OUT])}, and {rest} more. Ask me to show you the list to see them all."

    def text(self, name: str) -> str:
        items = [entry["text"] for entry in self.items(name)]
        heading = title(name)[:1].upper() + title(name)[1:]
        return "\n".join([heading] + [f"- {item}" for item in items])
