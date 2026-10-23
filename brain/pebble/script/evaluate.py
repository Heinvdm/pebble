import json
import math
import time
from dataclasses import dataclass, field

from .abilities import LOCAL, NEEDED, SIGNATURES, allowed_by
from .program import LIMITS, MAX_INT, Limits

SCALAR = 8
CHECK_TIME_EVERY = 255
CHECK_SIZE_EVERY = 1023
TYPE_WORDS = {bool: "True or False", int: "a number", float: "a number", str: "text", list: "a list", tuple: "a tuple", dict: "a dict", type(None): "None"}


class Fail(Exception):
    def __init__(self, kind: str, what: str, text: str):
        super().__init__(text)
        self.kind = kind
        self.what = what
        self.text = text


class _Finish(Exception):
    pass


class Ret:
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


BREAK = object()
CONTINUE = object()


@dataclass(frozen=True)
class Call:
    name: str
    args: dict
    line: int = 0

    def as_dict(self) -> dict:
        return {"call": self.name, "args": self.args}


@dataclass(frozen=True)
class Done:
    value: object = None

    def as_dict(self) -> dict:
        return {"done": True}


@dataclass(frozen=True)
class Finish:
    def as_dict(self) -> dict:
        return {"finish": True}


@dataclass(frozen=True)
class Crash:
    kind: str
    what: str
    line: int
    text: str

    def as_dict(self) -> dict:
        return {"crash": self.kind, "what": self.what, "line": self.line}

    def words(self) -> str:
        return f"line {self.line}: {self.text}" if self.line else self.text


@dataclass
class Range:
    start: int
    stop: int
    step: int = 1
    values: range = field(init=False, repr=False)

    def __post_init__(self):
        self.values = range(self.start, self.stop, self.step)

    def __len__(self):
        return len(self.values)

    def __iter__(self):
        return iter(self.values)

    def __contains__(self, item):
        return item in self.values

    def __getitem__(self, index):
        return self.values[index]

    def __eq__(self, other):
        return isinstance(other, Range) and self.values == other.values

    def __hash__(self):
        return hash(self.values)


def kind_words(value) -> str:
    if isinstance(value, Range):
        return "a range"
    return TYPE_WORDS.get(type(value), "a value")


def _err(text: str) -> Fail:
    return Fail("error", "", text)


def _limit(what: str, text: str) -> Fail:
    return Fail("limit", what, text)


def _locals_of(func: dict) -> set:
    found = set(func.get("args") or [])

    def targets(target) -> None:
        if isinstance(target, list):
            for item in target:
                targets(item)
            return
        if target.get("t") == "name":
            found.add(target["n"])
        elif target.get("t") == "unpack":
            for item in target["items"]:
                found.add(item["n"])

    def walk(stmts) -> None:
        for stmt in stmts:
            kind = stmt["t"]
            if kind in ("assign", "aug", "for"):
                targets(stmt["to"])
            for key in ("then", "else", "body"):
                if key in stmt:
                    walk(stmt[key])

    walk(func.get("body") or [])
    return found


class Machine:
    def __init__(self, program: dict, limits: Limits = LIMITS, timer=time.perf_counter):
        self.program = json.loads(json.dumps(program))
        self.limits = limits
        self.timer = timer
        self.header = dict(self.program.get("header") or {})
        self.uses = tuple(self.header.get("USES") or ())
        self.funcs: dict = self.program.get("funcs") or {}
        self.locals = {name: _locals_of(func) for name, func in self.funcs.items()}
        self.globals: dict = {}
        self.frames: list = []
        self.names: list = []
        self.steps = 0
        self.since = 0.0
        self.line = 0
        self.busy = False
        for func in self.funcs.values():
            for stmt in func.get("body") or []:
                self._mark_stmt(stmt)
        for stmt in self.program.get("globals") or []:
            self._mark_stmt(stmt)

    def _mark_stmt(self, stmt: dict) -> bool:
        pure = True
        for key in ("v", "c", "in"):
            node = stmt.get(key)
            if isinstance(node, dict):
                pure = self._mark(node) and pure
        to = stmt.get("to")
        if to is not None:
            for target in to if isinstance(to, list) else [to]:
                pure = self._mark_target(target) and pure
        for key in ("then", "else", "body"):
            for inner in stmt.get(key) or []:
                pure = self._mark_stmt(inner) and pure
        stmt["_p"] = pure
        return pure

    def _mark_target(self, target: dict) -> bool:
        if target.get("t") == "index":
            return self._mark(target["o"]) & self._mark(target["i"])
        return True

    def _mark(self, node: dict | None) -> bool:
        if node is None:
            return True
        kind = node["t"]
        pure = True
        if kind == "call" and node["f"] not in BUILTIN_NAMES:
            pure = False
        for key in ("a", "b", "c", "o", "i", "lo", "hi", "st"):
            child = node.get(key)
            if isinstance(child, dict):
                pure = self._mark(child) and pure
        for key in ("vs", "bs", "items", "keys", "vals", "args"):
            for child in node.get(key) or []:
                pure = self._mark(child) and pure
        for child in (node.get("kw") or {}).values():
            pure = self._mark(child) and pure
        node["_p"] = pure
        return pure

    def start(self) -> "Run":
        return Run(self, self._start())

    def _start(self):
        for name in ("ABOUT", "USES", "FOR", "UNTIL", "WANTS"):
            if name in self.header:
                self.globals[name] = self.header[name]
        self.frames = []
        self.names = []
        yield from self.block_gen(self.program.get("globals") or [])

    def run(self, handler: str, args=()) -> "Run":
        return Run(self, self._handle(handler, list(args)))

    def _handle(self, handler: str, args: list):
        func = self.funcs.get(handler)
        self.frames = []
        self.names = []
        if func is None:
            return None
        params = func.get("args") or []
        defaults = func.get("defaults") or []
        first_default = len(params) - len(defaults)
        bound = []
        for index, _ in enumerate(params):
            if index < len(args):
                bound.append(args[index])
            elif index >= first_default:
                bound.append(defaults[index - first_default])
            else:
                bound.append(None)
        value = yield from self.call_user(handler, bound, {})
        return value

    def tick(self) -> None:
        self.steps += 1
        if self.steps > self.limits.steps:
            raise _limit("steps", f"it ran more than {self.limits.steps:,} steps")
        if not self.steps & CHECK_TIME_EVERY:
            if self.limits.ms is not None and (self.timer() - self.since) * 1000.0 > self.limits.ms:
                raise _limit("time", f"it computed for more than {self.limits.ms:g} ms without stopping")
            if not self.steps & CHECK_SIZE_EVERY:
                self.check_all()

    def check_all(self) -> None:
        budget = self.limits.size
        used = 0
        for scope in [self.globals] + self.frames:
            for value in scope.values():
                used += self.measure(value, budget - used)[0]
        if used > budget:
            raise _limit("size", f"its values came to more than {budget // 1024} KB")

    def measure(self, value, budget: int | None = None, forbid=None) -> tuple[int, int]:
        budget = self.limits.size if budget is None else budget
        total = 0
        deepest = 0
        stack = [(value, 0)]
        seen = 0
        while stack:
            item, level = stack.pop()
            seen += 1
            if not seen & 4095 and self.limits.ms is not None and (self.timer() - self.since) * 1000.0 > self.limits.ms:
                raise _limit("time", f"it computed for more than {self.limits.ms:g} ms without stopping")
            if forbid is not None and item is forbid:
                raise _err("a list or dict can't hold itself")
            if isinstance(item, str):
                total += SCALAR + len(item)
            elif isinstance(item, (list, tuple)):
                total += SCALAR
                level += 1
                if level > deepest:
                    deepest = level
                if level > self.limits.depth:
                    raise _limit("depth", f"lists and dicts nest at most {self.limits.depth} deep")
                stack.extend((child, level) for child in item)
            elif isinstance(item, dict):
                total += SCALAR
                level += 1
                if level > deepest:
                    deepest = level
                if level > self.limits.depth:
                    raise _limit("depth", f"lists and dicts nest at most {self.limits.depth} deep")
                for key, child in item.items():
                    stack.append((key, level))
                    stack.append((child, level))
            else:
                total += SCALAR
            if total > budget:
                raise _limit("size", f"its values came to more than {self.limits.size // 1024} KB")
        return total, deepest

    def text(self, value: str) -> str:
        if len(value) > self.limits.text:
            raise _limit("text", f"text is at most {self.limits.text:,} characters")
        return value

    def count(self, items) -> None:
        if len(items) > self.limits.items:
            raise _limit("items", f"a list or dict holds at most {self.limits.items} items")

    def made(self, value):
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, (list, tuple, dict)):
            self.count(value)
            self.measure(value)
        return value

    def number(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            if -MAX_INT <= value <= MAX_INT:
                return value
            raise _limit("number", "a number got too big")
        if isinstance(value, float):
            if math.isfinite(value):
                return value
            raise _limit("number", "a number got too big")
        return value

    def lookup(self, name: str):
        frame = self.frames[-1] if self.frames else None
        if frame is not None:
            if name in frame:
                return frame[name]
            if name in self.locals.get(self.names[-1], ()):
                raise _err(f"'{name}' is used before it is set")
        if name in self.globals:
            return self.globals[name]
        if name in self.funcs:
            raise _err(f"'{name}' is a function; call it with ()")
        raise _err(f"'{name}' is not defined")

    def store(self, name: str, value) -> None:
        if self.frames:
            self.frames[-1][name] = value
        else:
            self.globals[name] = value

    def block(self, stmts: list):
        for stmt in stmts:
            code = self.ex(stmt)
            if code is not None:
                return code
        return None

    def block_gen(self, stmts: list):
        for stmt in stmts:
            if stmt["_p"]:
                code = self.ex(stmt)
            else:
                code = yield from self.ex_gen(stmt)
            if code is not None:
                return code
        return None

    def ex(self, stmt: dict):
        self.tick()
        self.line = stmt.get("l", self.line)
        kind = stmt["t"]
        if kind == "expr":
            self.ev(stmt["v"])
            return None
        if kind == "assign":
            self.assign(stmt["to"], self.ev(stmt["v"]))
            return None
        if kind == "aug":
            self.augment(stmt, self.ev(stmt["v"]), self.ev_target_parts(stmt["to"]))
            return None
        if kind == "if":
            return self.block(stmt["then"] if self.truth(self.ev(stmt["c"])) else stmt["else"])
        if kind == "while":
            while self.truth(self.ev(stmt["c"])):
                code = self.block(stmt["body"])
                if code is BREAK:
                    break
                if isinstance(code, Ret):
                    return code
                self.tick()
            return None
        if kind == "for":
            for item in self.iterate(self.ev(stmt["in"])):
                self.assign(stmt["to"], item)
                code = self.block(stmt["body"])
                if code is BREAK:
                    break
                if isinstance(code, Ret):
                    return code
                self.tick()
            return None
        if kind == "break":
            return BREAK
        if kind == "continue":
            return CONTINUE
        if kind == "return":
            return Ret(self.ev(stmt["v"]) if stmt["v"] is not None else None)
        raise _err(f"{kind} is not something a script can do")

    def ex_gen(self, stmt: dict):
        self.tick()
        self.line = stmt.get("l", self.line)
        kind = stmt["t"]
        if kind == "expr":
            yield from self.sub(stmt["v"])
            return None
        if kind == "assign":
            value = yield from self.sub(stmt["v"])
            parts = yield from self.target_parts_gen(stmt["to"])
            self.assign(stmt["to"], value, parts)
            return None
        if kind == "aug":
            value = yield from self.sub(stmt["v"])
            parts = yield from self.target_parts_gen(stmt["to"])
            self.augment(stmt, value, parts)
            return None
        if kind == "if":
            test = yield from self.sub(stmt["c"])
            return (yield from self.block_gen(stmt["then"] if self.truth(test) else stmt["else"]))
        if kind == "while":
            while True:
                test = yield from self.sub(stmt["c"])
                if not self.truth(test):
                    break
                code = yield from self.block_gen(stmt["body"])
                if code is BREAK:
                    break
                if isinstance(code, Ret):
                    return code
                self.tick()
            return None
        if kind == "for":
            items = yield from self.sub(stmt["in"])
            for item in self.iterate(items):
                self.assign(stmt["to"], item)
                code = yield from self.block_gen(stmt["body"])
                if code is BREAK:
                    break
                if isinstance(code, Ret):
                    return code
                self.tick()
            return None
        if kind == "return":
            value = (yield from self.sub(stmt["v"])) if stmt["v"] is not None else None
            return Ret(value)
        return self.ex(stmt)

    def sub(self, node: dict):
        if node["_p"]:
            return self.ev(node)
        return (yield from self.ev_gen(node))

    def ev_target_parts(self, target):
        if isinstance(target, dict) and target["t"] == "index":
            return (self.ev(target["o"]), self.ev(target["i"]))
        return None

    def target_parts_gen(self, target):
        if isinstance(target, dict) and target["t"] == "index":
            obj = yield from self.sub(target["o"])
            index = yield from self.sub(target["i"])
            return (obj, index)
        return None

    def assign(self, target, value, parts=None) -> None:
        if isinstance(target, list):
            for item in target:
                self.assign(item, value)
            return
        kind = target["t"]
        if kind == "name":
            self.store(target["n"], value)
            return
        if kind == "unpack":
            if not isinstance(value, (list, tuple)):
                raise _err(f"can't unpack {kind_words(value)} into {len(target['items'])} names")
            if len(value) != len(target["items"]):
                raise _err(f"{len(target['items'])} names but {len(value)} values")
            for item, part in zip(target["items"], value):
                self.store(item["n"], part)
            return
        obj, index = parts if parts is not None else (self.ev(target["o"]), self.ev(target["i"]))
        self.set_item(obj, index, value)

    def set_item(self, obj, index, value) -> None:
        if isinstance(obj, list):
            if not isinstance(index, int):
                raise _err("a list's position must be a whole number")
            if not -len(obj) <= index < len(obj):
                raise _err(f"position {index} is past the end of a list of {len(obj)}")
            self._holds(obj, value)
            obj[index] = value
            return
        if isinstance(obj, dict):
            self._key(index)
            if index not in obj and len(obj) + 1 > self.limits.items:
                raise _limit("items", f"a list or dict holds at most {self.limits.items} items")
            self._holds(obj, value)
            obj[index] = value
            return
        raise _err(f"can't set an item in {kind_words(obj)}")

    def _holds(self, container, value) -> None:
        _, depth = self.measure(value, forbid=container)
        if depth + 1 > self.limits.depth:
            raise _limit("depth", f"lists and dicts nest at most {self.limits.depth} deep")

    def _key(self, key) -> None:
        if not isinstance(key, (str, int)) or isinstance(key, bool):
            raise _err("a dict's keys must be text or whole numbers")

    def augment(self, stmt: dict, value, parts) -> None:
        target = stmt["to"]
        op = stmt["op"]
        if target["t"] == "name":
            current = self.lookup(target["n"])
            if op == "+" and isinstance(current, list):
                self._extend(current, value)
                return
            self.store(target["n"], self.binop(op, current, value))
            return
        obj, index = parts
        current = self.get_item(obj, index)
        if op == "+" and isinstance(current, list):
            self._extend(current, value)
            return
        self.set_item(obj, index, self.binop(op, current, value))

    def _extend(self, current: list, value) -> None:
        if not isinstance(value, (list, tuple)):
            raise _err(f"can't add {kind_words(value)} to a list")
        self.count(current + list(value))
        for item in value:
            self._holds(current, item)
        current.extend(value)
        self.measure(current)

    def truth(self, value) -> bool:
        return bool(value)

    def iterate(self, value) -> list:
        if isinstance(value, (list, tuple)):
            return list(value)
        if isinstance(value, str):
            return list(value)
        if isinstance(value, dict):
            return list(value.keys())
        if isinstance(value, Range):
            return value.values
        raise _err(f"can't loop over {kind_words(value)}")

    def items_of(self, value) -> list:
        if isinstance(value, Range):
            if len(value) > self.limits.items:
                raise _limit("items", f"a list or dict holds at most {self.limits.items} items")
            return list(value)
        return list(self.iterate(value))

    def ev(self, node: dict):
        self.tick()
        kind = node["t"]
        if kind == "const":
            return node["v"]
        if kind == "name":
            return self.lookup(node["n"])
        if kind == "bin":
            return self.binop(node["op"], self.ev(node["a"]), self.ev(node["b"]))
        if kind == "un":
            return self.unop(node["op"], self.ev(node["a"]))
        if kind == "bool":
            value = None
            for part in node["vs"]:
                value = self.ev(part)
                if (node["op"] == "and") != self.truth(value):
                    return value
            return value
        if kind == "cmp":
            left = self.ev(node["a"])
            for op, part in zip(node["ops"], node["bs"]):
                right = self.ev(part)
                if not self.compare(op, left, right):
                    return False
                left = right
            return True
        if kind == "ifx":
            return self.ev(node["a"]) if self.truth(self.ev(node["c"])) else self.ev(node["b"])
        if kind == "call":
            self.line = node.get("l", self.line)
            args = [self.ev(a) for a in node["args"]]
            kw = {k: self.ev(v) for k, v in node["kw"].items()}
            return self.builtin(node["f"], args, kw)
        if kind == "method":
            self.line = node.get("l", self.line)
            obj = self.ev(node["o"])
            return self.method(obj, node["m"], [self.ev(a) for a in node["args"]])
        if kind == "index":
            return self.get_item(self.ev(node["o"]), self.ev(node["i"]))
        if kind == "slice":
            return self.slice(self.ev(node["o"]), *(self.ev(node[k]) if node[k] is not None else None for k in ("lo", "hi", "st")))
        if kind == "list":
            return self.made([self.ev(e) for e in node["items"]])
        if kind == "tuple":
            return self.made(tuple(self.ev(e) for e in node["items"]))
        if kind == "dict":
            return self.dict_of([self.ev(k) for k in node["keys"]], [self.ev(v) for v in node["vals"]])
        if kind == "fstr":
            return self.fstr(node["parts"])
        raise _err(f"{kind} is not something a script can work out")

    def ev_gen(self, node: dict):
        self.tick()
        kind = node["t"]
        if kind == "bin":
            a = yield from self.sub(node["a"])
            b = yield from self.sub(node["b"])
            return self.binop(node["op"], a, b)
        if kind == "un":
            a = yield from self.sub(node["a"])
            return self.unop(node["op"], a)
        if kind == "bool":
            value = None
            for part in node["vs"]:
                value = yield from self.sub(part)
                if (node["op"] == "and") != self.truth(value):
                    return value
            return value
        if kind == "cmp":
            left = yield from self.sub(node["a"])
            for op, part in zip(node["ops"], node["bs"]):
                right = yield from self.sub(part)
                if not self.compare(op, left, right):
                    return False
                left = right
            return True
        if kind == "ifx":
            test = yield from self.sub(node["c"])
            return (yield from self.sub(node["a"] if self.truth(test) else node["b"]))
        if kind == "call":
            args = []
            for a in node["args"]:
                args.append((yield from self.sub(a)))
            kw = {}
            for k, v in node["kw"].items():
                kw[k] = yield from self.sub(v)
            self.line = node.get("l", self.line)
            name = node["f"]
            if name in BUILTIN_NAMES:
                return self.builtin(name, args, kw)
            if name in self.funcs:
                return (yield from self.call_user(name, args, kw))
            return (yield from self.ability(name, args, kw))
        if kind == "method":
            obj = yield from self.sub(node["o"])
            args = []
            for a in node["args"]:
                args.append((yield from self.sub(a)))
            self.line = node.get("l", self.line)
            return self.method(obj, node["m"], args)
        if kind == "index":
            obj = yield from self.sub(node["o"])
            index = yield from self.sub(node["i"])
            return self.get_item(obj, index)
        if kind == "slice":
            obj = yield from self.sub(node["o"])
            parts = []
            for key in ("lo", "hi", "st"):
                parts.append((yield from self.sub(node[key])) if node[key] is not None else None)
            return self.slice(obj, *parts)
        if kind in ("list", "tuple"):
            items = []
            for e in node["items"]:
                items.append((yield from self.sub(e)))
            return self.made(items if kind == "list" else tuple(items))
        if kind == "dict":
            keys, values = [], []
            for k, v in zip(node["keys"], node["vals"]):
                keys.append((yield from self.sub(k)))
                values.append((yield from self.sub(v)))
            return self.dict_of(keys, values)
        return self.ev(node)

    def call_user(self, name: str, args: list, kw: dict):
        func = self.funcs[name]
        params = func.get("args") or []
        defaults = func.get("defaults") or []
        if len(args) > len(params):
            raise _err(f"{name}() takes {len(params)} arguments but got {len(args)}")
        frame = dict(zip(params, args))
        for key, value in kw.items():
            if key not in params:
                raise _err(f"{name}() has no argument called {key}")
            if key in frame:
                raise _err(f"{name}() got {key} twice")
            frame[key] = value
        first_default = len(params) - len(defaults)
        for index, param in enumerate(params):
            if param not in frame:
                if index >= first_default:
                    frame[param] = defaults[index - first_default]
                else:
                    raise _err(f"{name}() needs {param}")
        if len(self.frames) >= self.limits.recursion:
            raise _limit("recursion", f"functions call each other at most {self.limits.recursion} deep")
        self.frames.append(frame)
        self.names.append(name)
        line = self.line
        code = yield from self.block_gen(func.get("body") or [])
        self.frames.pop()
        self.names.pop()
        self.line = line
        return code.value if isinstance(code, Ret) else None

    def bind(self, name: str, args: list, kw: dict) -> dict:
        signature = SIGNATURES[name]
        if len(args) > len(signature):
            raise _err(f"{name}() takes at most {len(signature)} arguments")
        out = {}
        for (param, _), value in zip(signature, args):
            out[param] = value
        names = [param for param, _ in signature]
        for key, value in kw.items():
            if key not in names:
                raise _err(f"{name}() has no argument called {key}")
            if key in out:
                raise _err(f"{name}() got {key} twice")
            out[key] = value
        for param, default in signature:
            if param not in out:
                if default is NEEDED:
                    raise _err(f"{name}() needs {param}")
                out[param] = default
        return {param: out[param] for param in names}

    def ability(self, name: str, args: list, kw: dict):
        if name not in SIGNATURES:
            raise _err(f"'{name}' is not a function you can use")
        if not allowed_by(self.uses, name):
            raise Fail("uses", name, f"{name}() is not in USES")
        bound = self.bind(name, args, kw)
        for value in bound.values():
            self.measure(value)
        if name in LOCAL:
            raise _Finish()
        reply = yield Call(name, bound, self.line)
        return reply

    def accept(self, value):
        if isinstance(value, tuple):
            value = list(value)
        self._plain(value, 0)
        if isinstance(value, (list, dict, str)):
            self.made(value)
        return value

    def _plain(self, value, level: int) -> None:
        if level > self.limits.depth + 1:
            raise _limit("depth", f"lists and dicts nest at most {self.limits.depth} deep")
        if value is None or isinstance(value, (bool, int, str)):
            if isinstance(value, int) and not isinstance(value, bool):
                self.number(value)
            return
        if isinstance(value, float):
            self.number(value)
            return
        if isinstance(value, list):
            for item in value:
                self._plain(item, level + 1)
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, (str, int)) or isinstance(key, bool):
                    raise _err("a reply held a key that is not text")
                self._plain(item, level + 1)
            return
        raise _err("a reply held something that is not a plain value")

    def dict_of(self, keys: list, values: list) -> dict:
        out = {}
        for key, value in zip(keys, values):
            self._key(key)
            out[key] = value
        return self.made(out)

    def binop(self, op: str, a, b):
        if op == "+":
            if _num(a) and _num(b):
                return self.number(a + b)
            if isinstance(a, str) and isinstance(b, str):
                if len(a) + len(b) > self.limits.text:
                    raise _limit("text", f"text is at most {self.limits.text:,} characters")
                return a + b
            if isinstance(a, list) and isinstance(b, list) or isinstance(a, tuple) and isinstance(b, tuple):
                if len(a) + len(b) > self.limits.items:
                    raise _limit("items", f"a list or dict holds at most {self.limits.items} items")
                return self.made(a + b)
            raise _err(f"can't add {kind_words(a)} and {kind_words(b)}")
        if op == "*":
            if _num(a) and _num(b):
                return self.number(a * b)
            if isinstance(b, (str, list, tuple)) and _whole(a):
                a, b = b, a
            if isinstance(a, (str, list, tuple)) and _whole(b):
                times = max(0, int(b))
                if isinstance(a, str):
                    if len(a) * times > self.limits.text:
                        raise _limit("text", f"text is at most {self.limits.text:,} characters")
                    return a * times
                if len(a) * times > self.limits.items:
                    raise _limit("items", f"a list or dict holds at most {self.limits.items} items")
                size, _ = self.measure(a)
                if size * times > self.limits.size:
                    raise _limit("size", f"its values came to more than {self.limits.size // 1024} KB")
                return self.made(a * times)
            raise _err(f"can't multiply {kind_words(a)} by {kind_words(b)}")
        if not (_num(a) and _num(b)):
            if op == "%" and isinstance(a, str):
                raise _err("% doesn't format text here; use an f-string with plain {names}")
            raise _err(f"can't use {op} on {kind_words(a)} and {kind_words(b)}")
        if op == "-":
            return self.number(a - b)
        if op == "/":
            if b == 0:
                raise _err("can't divide by zero")
            return self.number(a / b)
        if op == "//":
            if b == 0:
                raise _err("can't divide by zero")
            return self.number(a // b)
        if op == "%":
            if b == 0:
                raise _err("can't divide by zero")
            return self.number(a % b)
        if op == "**":
            return self.power(a, b)
        raise _err(f"{op} is not allowed")

    def power(self, a, b):
        if isinstance(a, int) and isinstance(b, int) and b >= 0:
            if abs(a) > 1 and b * math.log2(abs(a)) > 53:
                raise _limit("number", "a number got too big")
            return self.number(a**b)
        try:
            value = float(a) ** float(b)
        except OverflowError:
            raise _limit("number", "a number got too big")
        except ZeroDivisionError:
            raise _err("can't divide by zero")
        if isinstance(value, complex):
            raise _err("that power has no answer in plain numbers")
        return self.number(value)

    def unop(self, op: str, a):
        if op == "not":
            return not self.truth(a)
        if not _num(a):
            raise _err(f"can't use {op} on {kind_words(a)}")
        return self.number(-a if op == "-" else +a)

    def _big(self, value) -> None:
        if isinstance(value, (list, tuple, dict)):
            self.measure(value)

    def compare(self, op: str, a, b) -> bool:
        if op == "is":
            return a is None and b is None
        if op == "is not":
            return not (a is None and b is None)
        self._big(a)
        self._big(b)
        try:
            if op == "==":
                return a == b
            if op == "!=":
                return a != b
            if op == "<":
                return a < b
            if op == "<=":
                return a <= b
            if op == ">":
                return a > b
            if op == ">=":
                return a >= b
            if op in ("in", "not in"):
                if isinstance(b, str):
                    if not isinstance(a, str):
                        raise _err(f"can't look for {kind_words(a)} in text")
                    found = a in b
                elif isinstance(b, (list, tuple, Range)):
                    found = a in b
                elif isinstance(b, dict):
                    found = isinstance(a, (str, int)) and not isinstance(a, list) and a in b
                else:
                    raise _err(f"can't look inside {kind_words(b)}")
                return found if op == "in" else not found
        except TypeError:
            raise _err(f"can't compare {kind_words(a)} with {kind_words(b)}")
        raise _err(f"{op} is not allowed")

    def get_item(self, obj, index):
        if isinstance(obj, (list, tuple, str, Range)):
            if not isinstance(index, int):
                raise _err(f"a position in {kind_words(obj)} must be a whole number")
            if not -len(obj) <= index < len(obj):
                raise _err(f"position {index} is past the end of {kind_words(obj)} of {len(obj)}")
            return obj[index]
        if isinstance(obj, dict):
            if not isinstance(index, (str, int)) or isinstance(index, bool):
                raise _err("a dict's keys are text or whole numbers")
            if index not in obj:
                raise _err(f"{_short(index)} is not in the dict; use .get() to allow for that")
            return obj[index]
        raise _err(f"can't take an item from {kind_words(obj)}")

    def slice(self, obj, lo, hi, step):
        for part in (lo, hi, step):
            if part is not None and not isinstance(part, int):
                raise _err("a slice takes whole numbers")
        if step == 0:
            raise _err("a slice's step can't be zero")
        if isinstance(obj, (list, tuple, str)):
            return obj[lo:hi:step]
        raise _err(f"can't slice {kind_words(obj)}")

    def fstr(self, parts: list) -> str:
        out = []
        size = 0
        for part in parts:
            text = part if isinstance(part, str) else self.show(self.lookup(part["n"]))
            size += len(text)
            if size > self.limits.text:
                raise _limit("text", f"text is at most {self.limits.text:,} characters")
            out.append(text)
        return "".join(out)

    def show(self, value) -> str:
        if isinstance(value, str):
            return value
        self._big(value)
        out = []
        self._show(value, out, [0], top=True)
        return "".join(out)

    def _show(self, value, out: list, size: list, top: bool = False) -> None:
        if isinstance(value, str):
            piece = value if top else repr(value)
        elif value is None or isinstance(value, (bool, int, float)):
            piece = repr(value)
        elif isinstance(value, Range):
            piece = repr(value.values)
        elif isinstance(value, list):
            self._add(out, size, "[")
            for index, item in enumerate(value):
                if index:
                    self._add(out, size, ", ")
                self._show(item, out, size)
            self._add(out, size, "]")
            return
        elif isinstance(value, tuple):
            self._add(out, size, "(")
            for index, item in enumerate(value):
                if index:
                    self._add(out, size, ", ")
                self._show(item, out, size)
            self._add(out, size, ",)" if len(value) == 1 else ")")
            return
        elif isinstance(value, dict):
            self._add(out, size, "{")
            for index, (key, item) in enumerate(value.items()):
                if index:
                    self._add(out, size, ", ")
                self._show(key, out, size)
                self._add(out, size, ": ")
                self._show(item, out, size)
            self._add(out, size, "}")
            return
        else:
            piece = "?"
        self._add(out, size, piece)

    def _add(self, out: list, size: list, piece: str) -> None:
        size[0] += len(piece)
        if size[0] > self.limits.text:
            raise _limit("text", f"text is at most {self.limits.text:,} characters")
        out.append(piece)

    def builtin(self, name: str, args: list, kw: dict):
        if name == "len":
            _arity(name, args, 1, 1)
            value = args[0]
            if isinstance(value, (str, list, tuple, dict, Range)):
                return len(value)
            raise _err(f"{kind_words(value)} has no length")
        if name in ("min", "max"):
            if not args:
                raise _err(f"{name}() needs something to look at")
            items = self.items_of(args[0]) if len(args) == 1 else list(args)
            if not items:
                raise _err(f"{name}() of nothing")
            for item in items:
                self._big(item)
            try:
                return min(items) if name == "min" else max(items)
            except TypeError:
                raise _err(f"{name}() can't compare those")
        if name == "abs":
            _arity(name, args, 1, 1)
            if not _num(args[0]):
                raise _err(f"abs() of {kind_words(args[0])}")
            return self.number(abs(args[0]))
        if name == "round":
            _arity(name, args, 1, 2)
            digits = args[1] if len(args) > 1 else kw.get("ndigits")
            if not _num(args[0]) or (digits is not None and not _whole(digits)):
                raise _err("round() takes a number and a whole number of places")
            if digits is not None and abs(int(digits)) > 15:
                raise _err("round() to at most 15 places")
            return self.number(round(args[0]) if digits is None else round(args[0], int(digits)))
        if name == "int":
            _arity(name, args, 1, 1)
            value = args[0]
            if isinstance(value, str):
                try:
                    return self.number(int(value.strip()))
                except ValueError:
                    raise _err(f"{_short(value)} is not a whole number")
            if _num(value):
                return self.number(int(value))
            raise _err(f"int() of {kind_words(value)}")
        if name == "float":
            _arity(name, args, 1, 1)
            value = args[0]
            if isinstance(value, str):
                try:
                    out = float(value.strip())
                except ValueError:
                    raise _err(f"{_short(value)} is not a number")
                if not math.isfinite(out):
                    raise _err(f"{_short(value)} is not a number")
                return out
            if _num(value):
                return self.number(float(value))
            raise _err(f"float() of {kind_words(value)}")
        if name == "str":
            _arity(name, args, 0, 1)
            return self.show(args[0]) if args else ""
        if name == "range":
            _arity(name, args, 1, 3)
            if not all(_whole(a) for a in args):
                raise _err("range() takes whole numbers")
            parts = [int(a) for a in args]
            if len(parts) == 3 and parts[2] == 0:
                raise _err("range()'s step can't be zero")
            start, stop, step = (0, parts[0], 1) if len(parts) == 1 else (parts[0], parts[1], parts[2] if len(parts) > 2 else 1)
            return Range(start, stop, step)
        if name == "sorted":
            _arity(name, args, 1, 1)
            items = self.items_of(args[0])
            for item in items:
                self._big(item)
            try:
                return self.made(sorted(items, reverse=bool(kw.get("reverse", False))))
            except TypeError:
                raise _err("sorted() can't compare those")
        if name == "sum":
            _arity(name, args, 1, 1)
            total = 0
            for item in self.items_of(args[0]):
                if not _num(item):
                    raise _err(f"sum() of {kind_words(item)}")
                total = self.number(total + item)
            return total
        if name in ("any", "all"):
            _arity(name, args, 1, 1)
            items = self.items_of(args[0])
            return any(self.truth(i) for i in items) if name == "any" else all(self.truth(i) for i in items)
        if name == "enumerate":
            _arity(name, args, 1, 1)
            start = kw.get("start", 0)
            if not _whole(start):
                raise _err("enumerate()'s start is a whole number")
            return self.made([(int(start) + i, item) for i, item in enumerate(self.items_of(args[0]))])
        if name == "zip":
            lists = [self.items_of(a) for a in args]
            return self.made([tuple(group) for group in zip(*lists)]) if lists else []
        raise _err(f"'{name}' is not a function you can use")

    def method(self, obj, name: str, args: list):
        if isinstance(obj, list):
            return self._list_method(obj, name, args)
        if isinstance(obj, dict):
            return self._dict_method(obj, name, args)
        if isinstance(obj, str):
            return self._str_method(obj, name, args)
        raise _err(f"{kind_words(obj)} has no .{name}()")

    def _list_method(self, obj: list, name: str, args: list):
        if name == "append":
            _arity(name, args, 1, 1)
            if len(obj) + 1 > self.limits.items:
                raise _limit("items", f"a list or dict holds at most {self.limits.items} items")
            self._holds(obj, args[0])
            obj.append(args[0])
            return None
        if name == "pop":
            _arity(name, args, 0, 1)
            if not obj:
                raise _err("can't pop from an empty list")
            index = args[0] if args else -1
            if not isinstance(index, int) or not -len(obj) <= index < len(obj):
                raise _err(f"position {index} is past the end of a list of {len(obj)}")
            return obj.pop(index)
        if name == "insert":
            _arity(name, args, 2, 2)
            if not isinstance(args[0], int):
                raise _err("insert() takes a whole-number position")
            if len(obj) + 1 > self.limits.items:
                raise _limit("items", f"a list or dict holds at most {self.limits.items} items")
            self._holds(obj, args[1])
            obj.insert(args[0], args[1])
            return None
        if name in ("remove", "index", "count"):
            _arity(name, args, 1, 1)
            self._big(args[0])
            if name == "count":
                return obj.count(args[0])
            if args[0] not in obj:
                raise _err(f"{_short(args[0])} is not in the list")
            if name == "index":
                return obj.index(args[0])
            obj.remove(args[0])
            return None
        raise _err(f"a list has no .{name}()")

    def _dict_method(self, obj: dict, name: str, args: list):
        if name == "get":
            _arity(name, args, 1, 2)
            key = args[0]
            if not isinstance(key, (str, int)) or isinstance(key, bool):
                return args[1] if len(args) > 1 else None
            return obj.get(key, args[1] if len(args) > 1 else None)
        if name == "keys":
            _arity(name, args, 0, 0)
            return list(obj.keys())
        if name == "values":
            _arity(name, args, 0, 0)
            return list(obj.values())
        if name == "items":
            _arity(name, args, 0, 0)
            return [(k, v) for k, v in obj.items()]
        raise _err(f"a dict has no .{name}()")

    def _str_method(self, obj: str, name: str, args: list):
        if name in ("lower", "upper"):
            _arity(name, args, 0, 0)
            return self.text(obj.lower() if name == "lower" else obj.upper())
        if name == "strip":
            _arity(name, args, 0, 1)
            if args and not isinstance(args[0], str):
                raise _err("strip() takes text")
            return obj.strip(args[0] if args else None)
        if name == "split":
            _arity(name, args, 0, 2)
            sep = args[0] if args else None
            if sep is not None and (not isinstance(sep, str) or not sep):
                raise _err("split() takes some text to split on")
            most = args[1] if len(args) > 1 else -1
            if not isinstance(most, int):
                raise _err("split()'s second argument is a whole number")
            parts = obj.split(sep, most)
            self.count(parts)
            return parts
        if name == "join":
            _arity(name, args, 1, 1)
            items = self.items_of(args[0])
            if not all(isinstance(i, str) for i in items):
                raise _err("join() takes a list of text")
            if sum(len(i) for i in items) + len(obj) * max(0, len(items) - 1) > self.limits.text:
                raise _limit("text", f"text is at most {self.limits.text:,} characters")
            return obj.join(items)
        if name in ("startswith", "endswith"):
            _arity(name, args, 1, 1)
            if not isinstance(args[0], str):
                raise _err(f"{name}() takes text")
            return obj.startswith(args[0]) if name == "startswith" else obj.endswith(args[0])
        if name == "replace":
            _arity(name, args, 2, 3)
            old, new = args[0], args[1]
            if not isinstance(old, str) or not isinstance(new, str):
                raise _err("replace() takes text")
            most = args[2] if len(args) > 2 else -1
            if not isinstance(most, int):
                raise _err("replace()'s third argument is a whole number")
            times = (len(obj) + 1) if old == "" else obj.count(old)
            if most >= 0:
                times = min(times, most)
            if len(obj) + times * (len(new) - len(old)) > self.limits.text:
                raise _limit("text", f"text is at most {self.limits.text:,} characters")
            return obj.replace(old, new, most)
        raise _err(f"text has no .{name}()")


BUILTIN_NAMES = frozenset({"len", "min", "max", "abs", "round", "int", "float", "str", "range", "sorted", "sum", "any", "all", "enumerate", "zip"})


def _num(value) -> bool:
    return isinstance(value, (int, float))


def _whole(value) -> bool:
    return isinstance(value, int)


def _arity(name: str, args: list, least: int, most: int) -> None:
    if len(args) < least:
        raise _err(f"{name}() needs {least} argument{'s' if least != 1 else ''}")
    if len(args) > most:
        raise _err(f"{name}() takes at most {most} argument{'s' if most != 1 else ''}")


def _short(value) -> str:
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."


_NOTHING = object()


class Run:
    def __init__(self, machine: Machine, gen):
        self.machine = machine
        self.gen = gen
        self.started = False
        self.over = False
        self.outcome = None

    def go(self, reply=_NOTHING):
        if self.over:
            return self.outcome
        machine = self.machine
        try:
            if not self.started:
                self.started = True
                machine.steps = 0
                machine.since = machine.timer()
                if self.gen is None:
                    return self._end(Done())
                out = next(self.gen)
            else:
                value = machine.accept(None if reply is _NOTHING else reply)
                machine.since = machine.timer()
                out = self.gen.send(value)
            machine.check_all()
            return out
        except StopIteration as stop:
            try:
                machine.check_all()
            except Fail as fail:
                return self._end(Crash(fail.kind, fail.what, machine.line, fail.text))
            return self._end(Done(stop.value))
        except _Finish:
            return self._end(Finish())
        except Fail as fail:
            return self._end(Crash(fail.kind, fail.what, machine.line, fail.text))
        except RecursionError:
            return self._end(Crash("limit", "recursion", machine.line, "it went too deep"))
        except MemoryError:
            return self._end(Crash("limit", "size", machine.line, "it used too much memory"))
        except Exception as error:
            return self._end(Crash("error", "", machine.line, f"something went wrong ({type(error).__name__})"))

    def _end(self, outcome):
        self.over = True
        self.outcome = outcome
        machine = self.machine
        machine.frames = []
        machine.names = []
        if self.gen is not None:
            try:
                self.gen.close()
            except Exception:
                pass
        return outcome

    def stop(self) -> None:
        if not self.over:
            self._end(Finish())


def drive(machine: Machine, handler: str | None, args=(), answer=None):
    run = machine.start() if handler is None else machine.run(handler, args)
    calls = []
    out = run.go()
    while isinstance(out, Call):
        calls.append(out)
        reply = answer(out) if answer is not None else None
        out = run.go(reply)
    return out, calls
