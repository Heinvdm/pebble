import ast
import io
import math
import re
import tokenize
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .abilities import ABILITIES, FEELINGS, FOR_OTHERS, FREE, GAME, GROUP_OF, GROUPS, HANDLERS, MOVING, WANTED, group_of
from .program import ALL_METHODS, BUILTINS, HEADER, LIMITS, MAX_INT, build

MOST_LINES = 120
MOST_CHARS = 8000
MOST_NODES = 4000
MOST_DEPTH = 24
MOST_FUNCTIONS = 30
ABOUT_MOST = 200
EVERY_LEAST_S = 60
DAY_S = 86400.0
LONGEST_S = 30 * DAY_S
REFUSED_CALLS = {
    "print": "print is not allowed; use say() or note()",
    "open": "open is not allowed: a script can't reach files",
    "exec": "exec is not allowed",
    "eval": "eval is not allowed",
    "compile": "compile is not allowed",
    "getattr": "getattr is not allowed",
    "setattr": "setattr is not allowed",
    "hasattr": "hasattr is not allowed",
    "globals": "globals is not allowed",
    "locals": "locals is not allowed",
    "vars": "vars is not allowed",
    "input": "input is not allowed; use ask()",
    "__import__": "importing is not allowed",
    "list": "list() is not allowed; write [] or use sorted(...)",
    "dict": "dict() is not allowed; write {}",
    "set": "sets are not allowed; use a list",
    "tuple": "tuple() is not allowed; write (a, b)",
    "bool": "bool() is not allowed; compare instead",
    "isinstance": "isinstance is not allowed",
    "type": "type is not allowed",
    "reversed": "reversed is not allowed; use sorted(..., reverse=True) or a slice [::-1]",
    "map": "map is not allowed; use a for loop",
    "filter": "filter is not allowed; use a for loop",
}
METHOD_HINTS = {
    "sort": "use sorted(...)",
    "format": "use an f-string with plain {names}",
    "extend": "use += with a list",
    "update": "set each key with d[key] = value",
    "pop": "only lists have pop",
    "add": "sets are not allowed; use a list",
    "title": "use upper() or lower()",
    "capitalize": "use upper() or lower()",
    "isdigit": "compare instead",
}
FORBIDDEN = {
    ast.Import: "import is not allowed",
    ast.ImportFrom: "import is not allowed",
    ast.ClassDef: "class is not allowed",
    ast.Lambda: "lambda is not allowed; write a function with def at the top level",
    ast.Global: "global is not allowed; use keep() and kept() to remember values",
    ast.Nonlocal: "nonlocal is not allowed",
    ast.With: "with is not allowed",
    ast.AsyncWith: "async is not allowed",
    ast.AsyncFor: "async is not allowed",
    ast.AsyncFunctionDef: "async is not allowed",
    ast.Await: "await is not allowed",
    ast.Try: "try is not allowed",
    ast.Raise: "raise is not allowed",
    ast.Assert: "assert is not allowed",
    ast.Delete: "del is not allowed",
    ast.Yield: "yield is not allowed",
    ast.YieldFrom: "yield is not allowed",
    ast.ListComp: "list comprehensions are not allowed; use a for loop",
    ast.SetComp: "set comprehensions are not allowed; use a for loop",
    ast.DictComp: "dict comprehensions are not allowed; use a for loop",
    ast.GeneratorExp: "generator expressions are not allowed; use a for loop",
    ast.NamedExpr: ":= is not allowed",
    ast.Set: "sets are not allowed; use a list",
    ast.Starred: "* in calls and lists is not allowed",
    ast.Match: "match is not allowed; use if and elif",
}
if hasattr(ast, "TryStar"):
    FORBIDDEN[ast.TryStar] = "try is not allowed"
if hasattr(ast, "TypeAlias"):
    FORBIDDEN[ast.TypeAlias] = "type aliases are not allowed"
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CLOCK = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T]([01]?\d|2[0-3]):([0-5]\d)$")
HALF = re.compile(r"^(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(am|pm)$")
SPAN = re.compile(r"^(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?|days?|weeks?)$")
UNITS = {"min": 60.0, "minute": 60.0, "hr": 3600.0, "hour": 3600.0, "day": DAY_S, "week": 7 * DAY_S}
ME = ("me",)


@dataclass
class Header:
    about: str = ""
    uses: tuple = ()
    for_: str | None = None
    until: str = ""
    wants: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"ABOUT": self.about, "USES": list(self.uses), "FOR": self.for_, "UNTIL": self.until, "WANTS": dict(self.wants)}

    @property
    def own(self) -> bool:
        return not self.for_

    @classmethod
    def from_dict(cls, data: dict) -> "Header":
        data = data or {}
        uses = data.get("USES") or []
        wants = data.get("WANTS") or {}
        return cls(str(data.get("ABOUT") or ""), tuple(str(u) for u in uses if isinstance(u, str)), (str(data["FOR"]).strip().lower() or None) if isinstance(data.get("FOR"), str) else None, str(data.get("UNTIL") or ""), dict(wants) if isinstance(wants, dict) else {})


@dataclass
class Ground:
    people: dict = field(default_factory=dict)
    can_see: bool = True
    hearable: frozenset = frozenset({"doorbell", "knock", "microwave", "kettle", "phone", "alarm_clock", "rain", "thunder", "alarm", "meowing", "dog_crying"})
    longest_s: float = DAY_S
    asker: str | None = None
    places: tuple = ()
    quiet: tuple = ((22, 0), (7, 0))
    concepts: frozenset = frozenset()

    def tier(self, name: str | None) -> str | None:
        if not name:
            return None
        return self.people.get(str(name).strip().lower())


@dataclass
class Checked:
    source: str
    errors: list = field(default_factory=list)
    program: dict | None = None
    header: Header = field(default_factory=Header)
    called: frozenset = frozenset()
    targets: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors and self.program is not None


def _line(node) -> int:
    return int(getattr(node, "lineno", 0) or 0)


class _Walk:
    def __init__(self):
        self.errors: list[tuple[int, str]] = []
        self.nodes = 0
        self.functions: dict[str, ast.FunctionDef] = {}
        self.globals: set[str] = set()
        self.header: dict[str, ast.AST] = {}
        self.called: set[str] = set()
        self.targets: dict[str, list] = {}

    def error(self, node, text: str) -> None:
        item = (_line(node), text)
        if item not in self.errors:
            self.errors.append(item)

    def module(self, tree: ast.Module) -> None:
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                self._def_name(node)
                self.functions[node.name] = node
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name in HEADER:
                    self.header[name] = node.value
                else:
                    self._store_name(node.targets[0])
                    self.globals.add(name)
        if len(self.functions) > MOST_FUNCTIONS:
            self.error(tree, f"a script has at most {MOST_FUNCTIONS} functions")
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                self.function(node)
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id in HEADER:
                    self.header_value(node.targets[0].id, node.value)
                else:
                    self.expr(node.value, set(), 1, top=True)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                self._text(node.value, node.value.value)
            elif isinstance(node, ast.Pass):
                continue
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                self.error(node, f"{node.value.func.id}() can't be called at the top level; move it inside on_start()")
            elif type(node) in FORBIDDEN:
                self.error(node, FORBIDDEN[type(node)])
            else:
                self.error(node, "at the top level only ABOUT, USES, FOR, UNTIL, WANTS, plain values and functions are allowed; put actions inside on_start()")

    def _def_name(self, node: ast.FunctionDef) -> None:
        name = node.name
        if "__" in name or name.startswith("_"):
            self.error(node, "names starting with _ or holding __ are not allowed")
        elif name in BUILTINS or name in ABILITIES or name in HEADER or name in REFUSED_CALLS:
            self.error(node, f"'{name}' is already taken by the language; pick another name")
        elif name.startswith("on_") and name not in HANDLERS:
            self.error(node, f"{name} is not a handler; the handlers are {', '.join(HANDLERS)}")
        if name in self.functions:
            self.error(node, f"{name} is defined twice")

    def _store_name(self, target: ast.Name) -> bool:
        name = target.id
        if "__" in name or name.startswith("_"):
            self.error(target, "names starting with _ or holding __ are not allowed")
            return False
        if name in BUILTINS or name in ABILITIES or name in REFUSED_CALLS:
            self.error(target, f"'{name}' is the name of a built-in or an ability; pick another name")
            return False
        if name in HEADER:
            self.error(target, f"{name} can only be set once, at the top")
            return False
        if name in ("True", "False", "None"):
            self.error(target, f"{name} can't be changed")
            return False
        return True

    def header_value(self, name: str, node: ast.AST) -> None:
        try:
            value = ast.literal_eval(node)
        except Exception:
            self.error(node, f"{name} must be a plain value written out, with no calls or names")
            return
        if name == "ABOUT" and not isinstance(value, str):
            self.error(node, "ABOUT must be one line of text")
        elif name == "USES" and not (isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value)):
            self.error(node, "USES must be a list of ability names, like [\"say\", \"look\"]")
        elif name == "FOR" and not (value is None or isinstance(value, str)):
            self.error(node, "FOR must be the name of the person it is for")
        elif name == "UNTIL" and not isinstance(value, str):
            self.error(node, "UNTIL must be text, like \"21:00\" or \"2 hours\"")
        elif name == "WANTS" and not isinstance(value, dict):
            self.error(node, "WANTS must be a dict, like {\"seen\": [\"cat\"]}")

    def _locals(self, node: ast.FunctionDef) -> set:
        found = set()
        for arg in node.args.args:
            found.add(arg.arg)
        for inner in ast.walk(node):
            if isinstance(inner, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.For)):
                targets = inner.targets if isinstance(inner, ast.Assign) else [inner.target]
                for target in targets:
                    for leaf in ast.walk(target):
                        if isinstance(leaf, ast.Name):
                            found.add(leaf.id)
        return found

    def function(self, node: ast.FunctionDef) -> None:
        if node.decorator_list:
            self.error(node, "decorators are not allowed")
        args = node.args
        if args.posonlyargs or args.vararg or args.kwonlyargs or args.kwarg or args.kw_defaults:
            self.error(node, "a function takes plain arguments only (no *, ** or /)")
        for arg in args.args:
            if "__" in arg.arg or arg.arg.startswith("_"):
                self.error(arg, "names starting with _ or holding __ are not allowed")
            elif arg.arg in BUILTINS or arg.arg in ABILITIES:
                self.error(arg, f"'{arg.arg}' is the name of a built-in or an ability; pick another name")
            if arg.annotation is not None:
                self._annotation(arg.annotation)
        if node.returns is not None:
            self._annotation(node.returns)
        for default in args.defaults:
            if not isinstance(default, ast.Constant) or not isinstance(default.value, (str, int, float, bool, type(None))) or isinstance(default.value, complex):
                self.error(default, "a default must be a plain number, text, True, False or None")
        scope = self._locals(node)
        for name in scope & self.globals:
            if name not in {a.arg for a in args.args}:
                self.error(node, f"'{name}' is a top-level name, and a function can't change it; use keep(\"{name}\", ...) and kept(\"{name}\") instead")
        if len({a.arg for a in args.args}) != len(args.args):
            self.error(node, "an argument name is used twice")
        self.body(node.body, scope, 1, loops=0, in_function=True)

    def _annotation(self, node: ast.AST) -> None:
        for leaf in ast.walk(node):
            if not isinstance(leaf, (ast.Name, ast.Constant, ast.Subscript, ast.Load, ast.Tuple, ast.BinOp, ast.BitOr)):
                self.error(node, "leave out type hints")
                return
            if isinstance(leaf, ast.Name) and "__" in leaf.id:
                self.error(node, "names starting with _ or holding __ are not allowed")
                return

    def body(self, nodes: list, scope: set, depth: int, loops: int, in_function: bool) -> None:
        for node in nodes:
            self.stmt(node, scope, depth, loops, in_function)

    def _deep(self, node, depth: int) -> bool:
        self.nodes += 1
        if depth > MOST_DEPTH:
            self.error(node, "this is nested too deeply")
            return True
        if self.nodes > MOST_NODES:
            self.error(node, "the script is too long")
            return True
        return False

    def stmt(self, node: ast.stmt, scope: set, depth: int, loops: int, in_function: bool) -> None:
        if self._deep(node, depth):
            return
        kind = type(node)
        if kind in FORBIDDEN:
            self.error(node, FORBIDDEN[kind])
            return
        if isinstance(node, ast.FunctionDef):
            self.error(node, "functions go at the top level, not inside another function")
            return
        if isinstance(node, ast.Assign):
            for target in node.targets:
                self.target(target, scope, depth + 1)
            self.expr(node.value, scope, depth + 1)
            return
        if isinstance(node, ast.AnnAssign):
            if node.value is None or not isinstance(node.target, ast.Name):
                self.error(node, "leave out type hints")
                return
            self._annotation(node.annotation)
            self.target(node.target, scope, depth + 1)
            self.expr(node.value, scope, depth + 1)
            return
        if isinstance(node, ast.AugAssign):
            if type(node.op) not in BINARY:
                self.error(node, "only + - * / // % and ** are allowed")
            if isinstance(node.target, ast.Name):
                self.target(node.target, scope, depth + 1)
                self.load(node.target, scope)
            elif isinstance(node.target, ast.Subscript):
                self.target(node.target, scope, depth + 1)
            else:
                self.error(node, "+= and the like work on a name or an item, like count += 1 or d[k] += 1")
            self.expr(node.value, scope, depth + 1)
            return
        if isinstance(node, ast.If):
            self.expr(node.test, scope, depth + 1)
            self.body(node.body, scope, depth + 1, loops, in_function)
            self.body(node.orelse, scope, depth + 1, loops, in_function)
            return
        if isinstance(node, ast.While):
            if node.orelse:
                self.error(node, "else after a loop is not allowed")
            self.expr(node.test, scope, depth + 1)
            self.body(node.body, scope, depth + 1, loops + 1, in_function)
            return
        if isinstance(node, ast.For):
            if node.orelse:
                self.error(node, "else after a loop is not allowed")
            if getattr(node, "type_comment", None):
                self.error(node, "leave out type comments")
            self.loop_target(node.target, scope)
            self.expr(node.iter, scope, depth + 1)
            self.body(node.body, scope, depth + 1, loops + 1, in_function)
            return
        if isinstance(node, (ast.Break, ast.Continue)):
            if loops <= 0:
                self.error(node, f"{'break' if isinstance(node, ast.Break) else 'continue'} only works inside a loop")
            return
        if isinstance(node, ast.Return):
            if not in_function:
                self.error(node, "return only works inside a function")
            if node.value is not None:
                self.expr(node.value, scope, depth + 1)
            return
        if isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                self._text(node.value, node.value.value)
                return
            self.expr(node.value, scope, depth + 1)
            return
        if isinstance(node, ast.Pass):
            return
        self.error(node, f"{kind.__name__.lower()} is not allowed")

    def loop_target(self, node: ast.AST, scope: set) -> None:
        if isinstance(node, ast.Name):
            self._store_name(node)
            return
        if isinstance(node, (ast.Tuple, ast.List)) and all(isinstance(e, ast.Name) for e in node.elts) and node.elts:
            for elt in node.elts:
                self._store_name(elt)
            return
        self.error(node, "a for loop sets a plain name, or names like a, b")

    def target(self, node: ast.AST, scope: set, depth: int) -> None:
        if isinstance(node, ast.Name):
            self._store_name(node)
            return
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Slice):
                self.error(node, "setting a slice is not allowed; set one item at a time")
                return
            self.expr(node.value, scope, depth + 1)
            self.expr(node.slice, scope, depth + 1)
            return
        if isinstance(node, (ast.Tuple, ast.List)) and node.elts and all(isinstance(e, ast.Name) for e in node.elts):
            for elt in node.elts:
                self._store_name(elt)
            return
        if isinstance(node, ast.Attribute):
            self.error(node, "setting an attribute is not allowed")
            return
        self.error(node, "you can set a name, an item like d[k], or names like a, b")

    def load(self, node: ast.Name, scope: set) -> None:
        name = node.id
        if "__" in name or name.startswith("_"):
            self.error(node, "names starting with _ or holding __ are not allowed")
            return
        if name in scope or name in self.globals or name in HEADER:
            return
        if name in self.functions:
            self.error(node, f"'{name}' is a function; call it with ()")
            return
        if name in BUILTINS or name in ABILITIES:
            self.error(node, f"'{name}' must be called with ()")
            return
        if name in REFUSED_CALLS:
            self.error(node, REFUSED_CALLS[name])
            return
        self.error(node, f"'{name}' is not defined")

    def _text(self, node, value: str) -> None:
        if len(value) > LIMITS.text:
            self.error(node, f"text is at most {LIMITS.text:,} characters")

    def expr(self, node: ast.AST, scope: set, depth: int, top: bool = False) -> None:
        if self._deep(node, depth):
            return
        kind = type(node)
        if kind in FORBIDDEN:
            self.error(node, FORBIDDEN[kind])
            return
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, bool) or value is None:
                return
            if isinstance(value, str):
                self._text(node, value)
                return
            if isinstance(value, int):
                if abs(value) > MAX_INT:
                    self.error(node, "that number is too big")
                return
            if isinstance(value, float):
                if not math.isfinite(value):
                    self.error(node, "that number is too big")
                return
            self.error(node, "only numbers, text, True, False and None are allowed")
            return
        if isinstance(node, ast.Name):
            self.load(node, scope)
            return
        if isinstance(node, ast.BinOp):
            if type(node.op) not in BINARY:
                self.error(node, "only + - * / // % and ** are allowed")
            self.expr(node.left, scope, depth + 1, top)
            self.expr(node.right, scope, depth + 1, top)
            return
        if isinstance(node, ast.UnaryOp):
            if type(node.op) not in UNARY:
                self.error(node, "~ is not allowed")
            self.expr(node.operand, scope, depth + 1, top)
            return
        if isinstance(node, ast.BoolOp):
            for value in node.values:
                self.expr(value, scope, depth + 1, top)
            return
        if isinstance(node, ast.Compare):
            parts = [node.left] + list(node.comparators)
            for index, op in enumerate(node.ops):
                if type(op) not in COMPARE:
                    self.error(node, "that comparison is not allowed")
                if isinstance(op, (ast.Is, ast.IsNot)) and not any(isinstance(p, ast.Constant) and p.value is None for p in parts[index : index + 2]):
                    self.error(node, "use == to compare; is only works with None")
            for part in parts:
                self.expr(part, scope, depth + 1, top)
            return
        if isinstance(node, ast.IfExp):
            for part in (node.test, node.body, node.orelse):
                self.expr(part, scope, depth + 1, top)
            return
        if isinstance(node, ast.Call):
            self.call(node, scope, depth, top)
            return
        if isinstance(node, ast.Attribute):
            if "__" in node.attr or node.attr.startswith("_"):
                self.error(node, "names starting with _ or holding __ are not allowed")
            else:
                self.error(node, f".{node.attr} is not allowed; only calls of the allowed methods, like items.append(x)")
            return
        if isinstance(node, ast.Subscript):
            self.expr(node.value, scope, depth + 1, top)
            if isinstance(node.slice, ast.Slice):
                for part in (node.slice.lower, node.slice.upper, node.slice.step):
                    if part is not None:
                        self.expr(part, scope, depth + 1, top)
            else:
                self.expr(node.slice, scope, depth + 1, top)
            return
        if isinstance(node, (ast.List, ast.Tuple)):
            if len(node.elts) > LIMITS.items:
                self.error(node, f"a list holds at most {LIMITS.items} items")
            for elt in node.elts:
                self.expr(elt, scope, depth + 1, top)
            return
        if isinstance(node, ast.Dict):
            if len(node.keys) > LIMITS.items:
                self.error(node, f"a dict holds at most {LIMITS.items} items")
            for key, value in zip(node.keys, node.values):
                if key is None:
                    self.error(node, "** in a dict is not allowed")
                    continue
                self.expr(key, scope, depth + 1, top)
                self.expr(value, scope, depth + 1, top)
            return
        if isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    self._text(value, value.value)
                    continue
                if isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name) and value.conversion == -1 and value.format_spec is None:
                    self.load(value.value, scope)
                    continue
                self.error(node, "in an f-string use only plain {name} fields, like {count}; work the value out on the line before")
                return
            return
        if isinstance(node, ast.Slice):
            self.error(node, "a slice goes inside [ ]")
            return
        self.error(node, f"{kind.__name__} is not allowed")

    def call(self, node: ast.Call, scope: set, depth: int, top: bool) -> None:
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                self.error(arg, FORBIDDEN[ast.Starred])
                continue
            self.expr(arg, scope, depth + 1, top)
        for keyword in node.keywords:
            if keyword.arg is None:
                self.error(node, "** in calls is not allowed")
                continue
            if "__" in keyword.arg:
                self.error(node, "names starting with _ or holding __ are not allowed")
            self.expr(keyword.value, scope, depth + 1, top)
        func = node.func
        if isinstance(func, ast.Attribute):
            method = func.attr
            if "__" in method or method.startswith("_"):
                self.error(func, "names starting with _ or holding __ are not allowed")
                return
            if method not in ALL_METHODS:
                hint = METHOD_HINTS.get(method)
                self.error(func, f".{method}() is not allowed" + (f"; {hint}" if hint else ""))
                return
            if node.keywords:
                self.error(node, "methods take plain arguments, with no name=")
            self.expr(func.value, scope, depth + 1, top)
            return
        if not isinstance(func, ast.Name):
            self.error(node, "only functions defined with def, the built-ins and the abilities can be called")
            self.expr(func, scope, depth + 1, top)
            return
        name = func.id
        if "__" in name or name.startswith("_"):
            self.error(func, "names starting with _ or holding __ are not allowed")
            return
        if name in REFUSED_CALLS:
            self.error(func, REFUSED_CALLS[name])
            return
        if name in BUILTINS:
            allowed = BUILTIN_KEYWORDS.get(name, frozenset())
            for keyword in node.keywords:
                if keyword.arg not in allowed:
                    self.error(node, f"{name}() takes no {keyword.arg}=")
            return
        if name in ABILITIES:
            if top:
                self.error(node, "abilities can't be called at the top level; call them inside on_start() or a handler")
                return
            self.called.add(name)
            if name in ("say_to", "ask"):
                who = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "who"), None)
                self.targets.setdefault(name, []).append((_line(node), who.value if isinstance(who, ast.Constant) and isinstance(who.value, str) else None))
            return
        if name in self.functions:
            if top:
                self.error(node, "functions can't be called at the top level; call them inside on_start() or a handler")
            if name in HANDLERS:
                self.error(node, f"{name} is called by Pebble, not by the script")
            return
        if name in scope or name in self.globals:
            self.error(func, "only functions defined with def, the built-ins and the abilities can be called")
            return
        self.error(func, f"'{name}' is not a function you can use")


BINARY = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
UNARY = (ast.USub, ast.UAdd, ast.Not)
COMPARE = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot)
BUILTIN_KEYWORDS = {"sorted": frozenset({"reverse"}), "enumerate": frozenset({"start"}), "round": frozenset({"ndigits"})}


def lines_of(errors) -> list[str]:
    return [f"line {line}: {text}" if line else text for line, text in sorted(errors, key=lambda item: item[0])]


def _names(source: str) -> list[tuple[int, str]]:
    found = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.NAME and not NAME.match(token.string):
                found.append((token.start[0], f"'{token.string}' uses letters outside plain English; names use only a-z, 0-9 and _"))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return found
    return found


def parse(source: str) -> tuple[ast.Module | None, list[tuple[int, str]]]:
    text = str(source or "")
    if "\x00" in text:
        return None, [(1, "the script holds a null character")]
    if len(text) > MOST_CHARS:
        return None, [(0, f"a script is at most {MOST_CHARS:,} characters")]
    lines = text.splitlines()
    if len(lines) > MOST_LINES:
        return None, [(MOST_LINES + 1, f"a script is at most {MOST_LINES} lines")]
    odd = _names(text)
    try:
        tree = ast.parse(text, mode="exec", type_comments=False)
    except SyntaxError as error:
        message = (error.msg or "this isn't valid").replace("invalid syntax", "this isn't valid Python")
        return None, odd + [(int(error.lineno or 0), message)]
    except (RecursionError, MemoryError):
        return None, [(1, "this is nested too deeply")]
    except ValueError as error:
        return None, [(1, str(error)[:80])]
    return tree, odd


def whitelist(tree: ast.Module) -> _Walk:
    walk = _Walk()
    try:
        walk.module(tree)
    except RecursionError:
        walk.error(tree, "this is nested too deeply")
    return walk


def read(source: str) -> Checked:
    tree, errors = parse(source)
    out = Checked(str(source or ""))
    if tree is None:
        out.errors = lines_of(errors)
        return out
    walk = whitelist(tree)
    errors = list(errors) + walk.errors
    header = {}
    for name, node in walk.header.items():
        try:
            header[name] = ast.literal_eval(node)
        except Exception:
            continue
    out.header = Header.from_dict(header)
    out.called = frozenset(walk.called)
    out.targets = {name: list(found) for name, found in walk.targets.items()}
    if errors:
        out.errors = lines_of(errors)
        return out
    try:
        out.program = build(tree, header)
    except RecursionError:
        out.errors = ["line 1: this is nested too deeply"]
        return out
    out.program["called"] = sorted(out.called)
    return out


def until_at(text: str, now: datetime, own: bool = False) -> datetime | str | None:
    said = " ".join(str(text or "").strip().lower().split())
    if said in ("ongoing", "always", "for good"):
        return "ongoing" if own else None
    said = said.replace("midnight", "00:00").replace("noon", "12:00")
    later = 0
    for word in ("tomorrow", "today", "tonight"):
        if said.startswith(word + " ") or said.endswith(" " + word):
            said = said.replace(word, "").strip()
            later = 1 if word == "tomorrow" else 0
    half = HALF.match(said)
    if half:
        hour = int(half.group(1)) % 12 + (12 if half.group(3) == "pm" else 0)
        said = f"{hour:02d}:{half.group(2) or '00'}"
    found = CLOCK.match(said)
    if found:
        at = now.replace(hour=int(found.group(1)), minute=int(found.group(2)), second=0, microsecond=0)
        if later:
            return at + timedelta(days=1)
        return at if at > now else at + timedelta(days=1)
    found = STAMP.match(said)
    if found:
        try:
            day = datetime.strptime(found.group(1), "%Y-%m-%d")
        except ValueError:
            return None
        at = now.replace(year=day.year, month=day.month, day=day.day, hour=int(found.group(2)), minute=int(found.group(3)), second=0, microsecond=0)
        return at if at > now else None
    found = SPAN.match(said.replace("an hour", "1 hour").replace("a day", "1 day"))
    if found:
        unit = found.group(2).rstrip("s")
        seconds = float(found.group(1)) * UNITS.get(unit, UNITS.get(unit[:3], 0.0))
        return now + timedelta(seconds=seconds) if seconds > 0 else None
    return None


def _wanted_list(value) -> list | None:
    if value is True:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)) and all(isinstance(v, (str, int, float)) and not isinstance(v, bool) for v in value):
        return list(value)
    return None


def static(checked: Checked, ground: Ground, now: datetime) -> list[str]:
    errors: list[tuple[int, str]] = []
    program = checked.program or {}
    header = checked.header
    funcs = program.get("funcs") or {}
    line_of = {name: int(item.get("l") or 0) for name, item in funcs.items()}

    def fail(text: str, line: int = 0) -> None:
        if (line, text) not in errors:
            errors.append((line, text))

    about = " ".join(header.about.split())
    if not about:
        fail("ABOUT is missing: one plain line saying what the script does")
    elif len(about) > ABOUT_MOST or "\n" in header.about:
        fail(f"ABOUT is one line of at most {ABOUT_MOST} characters")
    if "ABOUT" not in (program.get("header") or {}):
        pass
    groups = set()
    for name in header.uses:
        if name in FREE:
            continue
        group = group_of(name)
        if group not in GROUPS:
            fail(f"USES names {name!r}, which is not an ability; the abilities are {', '.join(GROUPS)}")
            continue
        groups.add(group)
    for name in sorted(checked.called):
        if name in FREE:
            continue
        if group_of(name) not in groups:
            fail(f"{name}() is called but {group_of(name)!r} is not in USES")
    used = {group_of(name) for name in checked.called if name in GROUP_OF}
    own = header.own
    tier = None
    if not own:
        tier = ground.tier(header.for_)
        if tier is None:
            fail(f"FOR names {header.for_!r}, someone I don't know")
        elif tier == "stranger":
            fail("I don't make programs for people I don't know")
        else:
            others = _for_others(checked, header.for_)
            if tier in ("child", "friend"):
                if "do" in used:
                    fail("a program that moves me needs someone I trust; leave out do()")
                if "tune" in used or "dial" in used:
                    fail("only my own programs read or change my settings")
                if others:
                    line, name = others[0]
                    fail(f"in a program for {header.for_}, {name} goes only to the person it is for (\"me\")", line)
                if tier == "child" and used - set(GAME):
                    fail("a program for a child can only be a game: talking, asking, faces and looking")
            elif "tune" in used:
                fail("only my own programs change my settings")
    if not header.until:
        fail("UNTIL is missing: when the script ends at the latest, like \"21:00\" or \"2 hours\"")
    else:
        end = until_at(header.until, now, own)
        if end is None:
            if " ".join(header.until.lower().split()) in ("ongoing", "always", "for good"):
                fail("only my own programs may run on and on; give UNTIL a time")
            else:
                fail(f"UNTIL {header.until!r} isn't a time I understand: use \"HH:MM\", \"YYYY-MM-DD HH:MM\", \"2 hours\" or \"3 days\"")
        elif end != "ongoing":
            span = (end - now).total_seconds()
            most = LONGEST_S if own else max(DAY_S, min(LONGEST_S, ground.longest_s))
            if span > most + 60:
                fail(f"UNTIL is too far off; at most {_span_words(most)} from now" + ("" if own or most > DAY_S else " unless they asked for longer"))
    wants = header.wants
    for key, value in wants.items():
        handler = WANTED.get(key)
        if handler is None:
            fail(f"WANTS has {key!r}, which is not an event; the events are {', '.join(WANTED)}")
            continue
        if handler not in funcs:
            fail(f"WANTS has {key!r} but there is no {handler}()")
        items = _wanted_list(value)
        if items is None:
            fail(f"WANTS {key!r} must be a list of plain words")
            continue
        problem = _sense(key, items, ground, own, header.for_)
        if problem:
            fail(problem)
    for name, handler_line in line_of.items():
        if name in HANDLERS and name not in ("on_start", "on_stop"):
            key = next(k for k, h in WANTED.items() if h == name)
            if key not in wants:
                fail(f"{name}() is never called unless WANTS has {key!r}", handler_line)
    if not any(name in HANDLERS for name in funcs):
        fail("the script has no handler: define on_start() or one for an event in WANTS")
    return lines_of(errors)


def _for_others(checked: Checked, for_: str | None) -> list:
    out = []
    mine = {"me", "you", str(for_ or "").lower()}
    for name in FOR_OTHERS:
        for line, who in checked.targets.get(name, []):
            if who is None or str(who).strip().lower() not in mine:
                out.append((line, f"{name}()"))
    return sorted(out)


def _sense(key: str, items: list, ground: Ground, own: bool, for_: str | None) -> str:
    if key == "seen" and not ground.can_see:
        return "I can't see yet, so WANTS can't have 'seen'"
    if key == "seen" and not items:
        return "WANTS 'seen' needs the things to watch for, like [\"cat\"]"
    if key == "sound":
        for item in items:
            word = str(item).strip().lower().replace(" ", "_")
            if word not in ground.hearable:
                return f"I can't tell the sound {item!r} apart, so WANTS can't have it"
    if key in ("arrives", "leaves"):
        if not items:
            return f"WANTS {key!r} needs the people to watch for"
        for item in items:
            name = str(item).strip().lower()
            if name in ("anyone", "someone", "me"):
                continue
            if ground.tier(name) is None:
                return f"I don't know who {item!r} is, so I can't tell when they come and go"
    if key == "at":
        for item in items:
            if not CLOCK.match(str(item).strip()):
                return f"WANTS 'at' times look like \"21:00\", not {item!r}"
    if key == "every":
        for item in items:
            if isinstance(item, str) or float(item) < EVERY_LEAST_S:
                return f"WANTS 'every' is a number of seconds, at least {EVERY_LEAST_S}"
    if key == "feeling":
        for item in items:
            if str(item).strip().lower() not in FEELINGS:
                return f"WANTS 'feeling' can be {', '.join(FEELINGS)}"
    if key == "heard":
        if own:
            return "my own programs don't listen to what people say; leave 'heard' out"
        for item in items:
            if str(item).strip().lower() not in ("me", "you", str(for_ or "").lower(), "anyone"):
                return "a program only hears the person it is for; use \"heard\": [\"me\"]"
    return ""


def _span_words(seconds: float) -> str:
    if seconds >= 2 * DAY_S:
        return f"{round(seconds / DAY_S)} days"
    return f"{round(seconds / 3600.0)} hours"


def moves(checked: Checked) -> bool:
    return bool(set(checked.called) & MOVING)
