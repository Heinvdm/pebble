import re
from dataclasses import dataclass, field

from .elements import MAX_TEXT, REGISTRY, TEXT_CHARS, Element, Slot

_TOKEN = re.compile(r'"([^"]*)"|(\S+)')
_RADIUS = re.compile(r"^r(\d{1,3})$")
_INT = re.compile(r"^\d{1,3}$")
_FENCE = re.compile(r"^`{3}\w*$")
_BULLET = re.compile(r"^(?:[-*]\s+|\d{1,2}[.)]\s+)")
_TEXT_OK = frozenset(TEXT_CHARS)


class SceneError(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    text: str
    quoted: bool


@dataclass(frozen=True)
class SceneLine:
    element: str
    values: dict = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def get(self, name: str):
        return self.values.get(name)

    def as_dict(self) -> dict:
        return {"element": self.element, **self.values}

    def text(self) -> str:
        return format_line(self)


@dataclass(frozen=True)
class Scene:
    lines: tuple[SceneLine, ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()

    def text(self) -> str:
        return "\n".join(line.text() for line in self.lines)

    def elements(self) -> list[str]:
        return [line.element for line in self.lines]

    def __bool__(self) -> bool:
        return bool(self.lines)


def tokenize(text: str) -> list[Token]:
    tokens = []
    for match in _TOKEN.finditer(text):
        quoted = match.group(1)
        tokens.append(Token(quoted, True) if quoted is not None else Token(match.group(2), False))
    return tokens


def _clamp(value: int, slot: Slot, notes: list[str]) -> int:
    clamped = max(slot.lo, min(slot.hi, value))
    if clamped != value:
        notes.append(f"{slot.name} clamped from {value} to {clamped}")
    return clamped


def read_slot(slot: Slot, token: Token | None, notes: list[str]):
    if token is None:
        return None
    if slot.kind == "text":
        if not token.quoted:
            return None
        text = "".join(ch for ch in token.text if ch in _TEXT_OK)
        if not text:
            return None
        if len(text) > MAX_TEXT:
            notes.append(f"text shortened to {MAX_TEXT} letters")
            text = text[:MAX_TEXT]
        return text
    if token.quoted:
        return None
    word = token.text.lower()
    if slot.kind == "num":
        return _clamp(int(word), slot, notes) if _INT.match(word) else None
    if slot.kind == "radius":
        match = _RADIUS.match(word)
        return _clamp(int(match.group(1)), slot, notes) if match else None
    return word if word in slot.choices() else None


def parse_tokens(element: Element, tokens: list[Token]) -> SceneLine:
    values: dict = {}
    notes: list[str] = []
    index = 0
    for slot in element.slots:
        token = tokens[index] if index < len(tokens) else None
        value = read_slot(slot, token, notes)
        if value is not None:
            values[slot.name] = value
            index += 1
        elif slot.required:
            found = "nothing" if token is None else repr(token.text)
            raise SceneError(f"{element.name}: expected {slot.describe()}, found {found}")
        else:
            values[slot.name] = slot.default
    if index < len(tokens):
        raise SceneError(f"{element.name}: did not expect {tokens[index].text!r}")
    return SceneLine(element.name, values, tuple(notes))


def clean_line(raw: str) -> str:
    text = raw.strip().strip("`").strip()
    if not text or _FENCE.match(raw.strip()) or text.startswith("#"):
        return ""
    return _BULLET.sub("", text).strip()


def parse_line(raw: str) -> SceneLine:
    text = clean_line(raw)
    if not text:
        raise SceneError("empty line")
    tokens = tokenize(text)
    if not tokens or tokens[0].quoted:
        raise SceneError("a line starts with an element name")
    name = tokens[0].text.lower()
    element = REGISTRY.get(name)
    if element is None:
        raise SceneError(f"unknown element {name!r}")
    return parse_tokens(element, tokens[1:])


def format_value(slot: Slot, value) -> str:
    if slot.kind == "radius":
        return f"r{value}"
    if slot.kind == "text":
        return f'"{value}"'
    return str(value)


def format_line(line: SceneLine) -> str:
    element = REGISTRY[line.element]
    return " ".join([element.name] + [format_value(slot, line.values[slot.name]) for slot in element.slots])


def make_line(element: str, **values) -> SceneLine:
    spec = REGISTRY[element]
    resolved = {}
    for slot in spec.slots:
        value = values.get(slot.name, slot.default)
        if value is None:
            raise SceneError(f"{element}: {slot.name} is needed")
        resolved[slot.name] = value
    return SceneLine(element, resolved)
