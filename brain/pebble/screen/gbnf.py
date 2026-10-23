import random
import re
from dataclasses import dataclass

NAME = re.compile(r"[a-zA-Z0-9-]+")
RULE_START = re.compile(r"^\s*([a-zA-Z0-9-]+)\s*::=")
ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"', "[": "[", "]": "]", "-": "-", "^": "^"}
PRINTABLE = [chr(c) for c in range(32, 127)]


class GrammarError(ValueError):
    pass


@dataclass(frozen=True)
class Lit:
    text: str


@dataclass(frozen=True)
class Cls:
    ranges: tuple[tuple[str, str], ...]
    negated: bool

    def accepts(self, ch: str) -> bool:
        inside = any(lo <= ch <= hi for lo, hi in self.ranges)
        return inside != self.negated


@dataclass(frozen=True)
class Ref:
    name: str


@dataclass(frozen=True)
class Seq:
    items: tuple


@dataclass(frozen=True)
class Alt:
    options: tuple


@dataclass(frozen=True)
class Rep:
    node: object
    lo: int
    hi: int | None


class _Reader:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def skip(self) -> None:
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch == "#":
                while self.pos < len(self.text) and self.text[self.pos] != "\n":
                    self.pos += 1
            elif ch.isspace():
                self.pos += 1
            else:
                return

    def peek(self) -> str:
        self.skip()
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def escape(self) -> str:
        self.pos += 1
        ch = self.text[self.pos : self.pos + 1]
        if ch == "x":
            code = self.text[self.pos + 1 : self.pos + 3]
            self.pos += 3
            return chr(int(code, 16))
        if ch not in ESCAPES:
            raise GrammarError(f"unknown escape \\{ch}")
        self.pos += 1
        return ESCAPES[ch]

    def literal(self) -> Lit:
        self.pos += 1
        out = []
        while True:
            if self.pos >= len(self.text):
                raise GrammarError("unterminated string")
            ch = self.text[self.pos]
            if ch == '"':
                self.pos += 1
                return Lit("".join(out))
            if ch == "\n":
                raise GrammarError("newline inside a string")
            if ch == "\\":
                out.append(self.escape())
            else:
                out.append(ch)
                self.pos += 1

    def class_char(self) -> str:
        if self.text[self.pos] == "\\":
            return self.escape()
        ch = self.text[self.pos]
        self.pos += 1
        return ch

    def char_class(self) -> Cls:
        self.pos += 1
        negated = self.text[self.pos : self.pos + 1] == "^"
        if negated:
            self.pos += 1
        ranges = []
        while True:
            if self.pos >= len(self.text):
                raise GrammarError("unterminated character class")
            if self.text[self.pos] == "]":
                self.pos += 1
                break
            lo = self.class_char()
            hi = lo
            if self.text[self.pos : self.pos + 1] == "-" and self.text[self.pos + 1 : self.pos + 2] not in ("]", ""):
                self.pos += 1
                hi = self.class_char()
            if hi < lo:
                raise GrammarError("backwards range")
            ranges.append((lo, hi))
        if not ranges:
            raise GrammarError("empty character class")
        return Cls(tuple(ranges), negated)

    def atom(self):
        ch = self.peek()
        if ch == '"':
            return self.literal()
        if ch == "[":
            return self.char_class()
        if ch == "(":
            self.pos += 1
            node = self.alternation()
            if self.peek() != ")":
                raise GrammarError("missing )")
            self.pos += 1
            return node
        match = NAME.match(self.text, self.pos)
        if match is None:
            raise GrammarError(f"unexpected {ch!r} at {self.pos}")
        self.pos = match.end()
        return Ref(match.group(0))

    def postfix(self):
        node = self.atom()
        while True:
            ch = self.text[self.pos : self.pos + 1]
            if ch == "?":
                node, self.pos = Rep(node, 0, 1), self.pos + 1
            elif ch == "*":
                node, self.pos = Rep(node, 0, None), self.pos + 1
            elif ch == "+":
                node, self.pos = Rep(node, 1, None), self.pos + 1
            elif ch == "{":
                end = self.text.index("}", self.pos)
                body = self.text[self.pos + 1 : end]
                self.pos = end + 1
                low, _, high = body.partition(",")
                lo = int(low)
                hi = lo if "," not in body else (int(high) if high.strip() else None)
                node = Rep(node, lo, hi)
            else:
                return node

    def sequence(self):
        items = []
        while self.peek() not in ("", "|", ")"):
            items.append(self.postfix())
        if not items:
            raise GrammarError("empty sequence")
        return items[0] if len(items) == 1 else Seq(tuple(items))

    def alternation(self):
        options = [self.sequence()]
        while self.peek() == "|":
            self.pos += 1
            options.append(self.sequence())
        return options[0] if len(options) == 1 else Alt(tuple(options))


def _split_rules(text: str) -> list[tuple[str, str]]:
    rules: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        match = RULE_START.match(line)
        if match:
            rules.append((match.group(1), [line[match.end() :]]))
        elif line.strip() and not line.strip().startswith("#"):
            if not rules:
                raise GrammarError("text before the first rule")
            rules[-1][1].append(line)
    return [(name, "\n".join(body)) for name, body in rules]


class Grammar:
    def __init__(self, rules: dict):
        self.rules = rules
        for name in self._refs():
            if name not in rules:
                raise GrammarError(f"undefined rule {name}")

    def _refs(self) -> set[str]:
        found: set[str] = set()

        def walk(node) -> None:
            if isinstance(node, Ref):
                found.add(node.name)
            elif isinstance(node, Seq):
                for item in node.items:
                    walk(item)
            elif isinstance(node, Alt):
                for option in node.options:
                    walk(option)
            elif isinstance(node, Rep):
                walk(node.node)

        for node in self.rules.values():
            walk(node)
        return found

    def _ends(self, node, text: str, start: int, memo: dict) -> frozenset:
        key = (id(node), start)
        if key in memo:
            return memo[key]
        memo[key] = frozenset()
        if isinstance(node, Lit):
            result = frozenset({start + len(node.text)}) if text.startswith(node.text, start) else frozenset()
        elif isinstance(node, Cls):
            result = frozenset({start + 1}) if start < len(text) and node.accepts(text[start]) else frozenset()
        elif isinstance(node, Ref):
            result = self._ends(self.rules[node.name], text, start, memo)
        elif isinstance(node, Seq):
            positions = frozenset({start})
            for item in node.items:
                positions = frozenset(end for p in positions for end in self._ends(item, text, p, memo))
                if not positions:
                    break
            result = positions
        elif isinstance(node, Alt):
            result = frozenset(end for option in node.options for end in self._ends(option, text, start, memo))
        else:
            result = set()
            current = frozenset({start})
            if node.lo == 0:
                result.add(start)
            limit = node.hi if node.hi is not None else len(text) - start + 1
            for count in range(1, limit + 1):
                current = frozenset(end for p in current for end in self._ends(node.node, text, p, memo))
                if not current:
                    break
                if count >= node.lo:
                    result |= current
            result = frozenset(result)
        memo[key] = result
        return result

    def matches(self, text: str, start: str = "root") -> bool:
        return len(text) in self._ends(Ref(start), text, 0, {})

    def sample(self, rng: random.Random, start: str = "root", depth: int = 200) -> str:
        return self._sample(Ref(start), rng, depth)

    def _sample(self, node, rng: random.Random, depth: int) -> str:
        if depth <= 0:
            raise GrammarError("sampling went too deep")
        if isinstance(node, Lit):
            return node.text
        if isinstance(node, Cls):
            pool = [ch for ch in PRINTABLE if node.accepts(ch)]
            return rng.choice(pool)
        if isinstance(node, Ref):
            return self._sample(self.rules[node.name], rng, depth - 1)
        if isinstance(node, Seq):
            return "".join(self._sample(item, rng, depth - 1) for item in node.items)
        if isinstance(node, Alt):
            return self._sample(rng.choice(node.options), rng, depth - 1)
        count = node.lo
        ceiling = node.hi if node.hi is not None else node.lo + 4
        while count < ceiling and rng.random() < 0.5:
            count += 1
        return "".join(self._sample(node.node, rng, depth - 1) for _ in range(count))


def parse_gbnf(text: str) -> Grammar:
    rules = {}
    for name, body in _split_rules(text):
        if name in rules:
            raise GrammarError(f"rule {name} defined twice")
        reader = _Reader(body)
        rules[name] = reader.alternation()
        if reader.peek() != "":
            raise GrammarError(f"trailing text in rule {name}")
    if not rules:
        raise GrammarError("no rules")
    return Grammar(rules)
