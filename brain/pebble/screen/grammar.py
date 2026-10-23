from functools import lru_cache

from .elements import ELEMENTS, MAX_LINES, MAX_TEXT, MOTIONS, PALETTE, SPEEDS, TEXT_CHARS, Element, Slot

END = ""


def _literal(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


_CLASS_ESCAPES = {"\\": "\\\\", "]": "\\]", "[": "\\[", "^": "\\^"}


def _class_char(ch: str) -> str:
    return _CLASS_ESCAPES.get(ch, ch)


def _char_class(chars: list[str]) -> str:
    unique = set(chars)
    dash = "-" in unique
    unique.discard("-")
    parts: list[str] = []
    ordered = sorted(unique, key=ord)
    if ordered:
        start = previous = ordered[0]
        for ch in ordered[1:] + [None]:
            if ch is not None and ord(ch) == ord(previous) + 1:
                previous = ch
                continue
            if start == previous:
                parts.append(_class_char(start))
            elif ord(previous) == ord(start) + 1:
                parts.append(_class_char(start) + _class_char(previous))
            else:
                parts.append(f"{_class_char(start)}-{_class_char(previous)}")
            if ch is not None:
                start = previous = ch
    if dash:
        parts.append("-")
    return "[" + "".join(parts) + "]"


def _trie(words: list[str]) -> dict:
    root: dict = {}
    for text in words:
        node = root
        for ch in text:
            node = node.setdefault(ch, {})
        node[END] = {}
    return root


def _alternatives(node: dict) -> list[str]:
    groups: dict[str, list[str]] = {}
    for ch, child in node.items():
        if ch != END:
            groups.setdefault(_suffix(child), []).append(ch)
    out = []
    for suffix, chars in sorted(groups.items(), key=lambda item: min(item[1])):
        head = _char_class(chars)
        out.append(f"{head} {suffix}" if suffix else head)
    return out


def _suffix(node: dict) -> str:
    children = [ch for ch in node if ch != END]
    if not children:
        return ""
    alternatives = _alternatives(node)
    inner = " | ".join(alternatives)
    atom = len(alternatives) == 1 and " " not in inner
    wrapped = inner if atom else f"({inner})"
    return wrapped + "?" if END in node else wrapped


def number_rule(lo: int, hi: int) -> str:
    if lo < 0 or hi < lo:
        raise ValueError("bad range")
    return " | ".join(_alternatives(_trie([str(n) for n in range(lo, hi + 1)])))


def _nested(item: str, count: int) -> str:
    text = item
    for _ in range(count - 1):
        text = f"{item} ({text})?"
    return text


def num_name(lo: int, hi: int) -> str:
    return f"n-{lo}-{hi}"


def slot_rule(element: Element, slot: Slot) -> str:
    if slot.kind == "num":
        return num_name(slot.lo, slot.hi)
    if slot.kind == "radius":
        return f"r-{slot.lo}-{slot.hi}"
    if slot.kind in ("colour", "motion", "speed", "text"):
        return slot.kind
    return f"{element.name}-{slot.name}"


def element_rule(element: Element) -> str:
    parts = [_literal(element.name)]
    for slot in element.slots:
        piece = f'" " {slot_rule(element, slot)}'
        parts.append(piece if slot.required else f"({piece})?")
    return " ".join(parts)


def _words(words) -> str:
    return " | ".join(_literal(w) for w in words)


@lru_cache(maxsize=1)
def scene_grammar() -> str:
    rules: dict[str, str] = {}
    rules["root"] = "line more-1 \"\\n\"?"
    for index in range(1, MAX_LINES):
        tail = f" more-{index + 1}" if index + 1 < MAX_LINES else ""
        rules[f"more-{index}"] = f'("\\n" line{tail})?'
    rules["line"] = " | ".join(f"el-{e.name}" for e in ELEMENTS)
    numbers: dict[str, str] = {}
    for element in ELEMENTS:
        rules[f"el-{element.name}"] = element_rule(element)
        for slot in element.slots:
            if slot.kind == "num":
                numbers[num_name(slot.lo, slot.hi)] = number_rule(slot.lo, slot.hi)
            elif slot.kind == "radius":
                numbers[f"r-{slot.lo}-{slot.hi}"] = f'"r" {num_name(slot.lo, slot.hi)}'
                numbers[num_name(slot.lo, slot.hi)] = number_rule(slot.lo, slot.hi)
            elif slot.kind == "word":
                rules[f"{element.name}-{slot.name}"] = _words(slot.words)
    rules["colour"] = _words(PALETTE)
    rules["motion"] = _words(MOTIONS)
    rules["speed"] = _words(SPEEDS)
    rules["text"] = '"\\"" text-body "\\""'
    rules["text-body"] = _nested("text-char", MAX_TEXT)
    rules["text-char"] = _char_class(list(TEXT_CHARS))
    rules.update(sorted(numbers.items()))
    return "\n".join(f"{name} ::= {body}" for name, body in rules.items()) + "\n"
