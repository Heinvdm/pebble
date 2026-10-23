import ast
import json
from dataclasses import asdict, dataclass

FORMAT = 1
HEADER = ("ABOUT", "USES", "FOR", "UNTIL", "WANTS")
MAX_INT = 2**53 - 1
BUILTINS = frozenset({"len", "min", "max", "abs", "round", "int", "float", "str", "range", "sorted", "sum", "any", "all", "enumerate", "zip"})
METHODS = {
    "list": frozenset({"append", "pop", "insert", "remove", "index", "count"}),
    "dict": frozenset({"get", "keys", "values", "items"}),
    "str": frozenset({"lower", "upper", "strip", "split", "join", "startswith", "endswith", "replace"}),
}
ALL_METHODS = frozenset().union(*METHODS.values())
BINOPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**"}
CMPOPS = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.In: "in", ast.NotIn: "not in", ast.Is: "is", ast.IsNot: "is not"}
UNOPS = {ast.USub: "-", ast.UAdd: "+", ast.Not: "not"}


@dataclass(frozen=True)
class Limits:
    steps: int = 100_000
    ms: float | None = 50.0
    text: int = 2000
    items: int = 500
    depth: int = 4
    size: int = 256 * 1024
    recursion: int = 20
    keep: int = 64 * 1024

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Limits":
        base = cls()
        if not data:
            return base
        values = asdict(base)
        for key in values:
            if key in data:
                values[key] = data[key]
        return cls(**values)


LIMITS = Limits()


def _line(node) -> int:
    return int(getattr(node, "lineno", 0) or 0)


def _stmts(nodes) -> list:
    out = []
    for node in nodes:
        item = _stmt(node)
        if item is not None:
            out.append(item)
    return out


def _target(node) -> dict:
    if isinstance(node, ast.Name):
        return {"t": "name", "n": node.id}
    if isinstance(node, ast.Subscript):
        return {"t": "index", "o": _expr(node.value), "i": _expr(node.slice)}
    return {"t": "unpack", "items": [{"t": "name", "n": elt.id} for elt in node.elts]}


def _stmt(node) -> dict | None:
    line = _line(node)
    if isinstance(node, ast.Assign):
        if len(node.targets) == 1:
            return {"t": "assign", "l": line, "to": _target(node.targets[0]), "v": _expr(node.value)}
        return {"t": "assign", "l": line, "to": [_target(t) for t in node.targets], "v": _expr(node.value)}
    if isinstance(node, ast.AnnAssign):
        return {"t": "assign", "l": line, "to": _target(node.target), "v": _expr(node.value)}
    if isinstance(node, ast.AugAssign):
        return {"t": "aug", "l": line, "op": BINOPS[type(node.op)], "to": _target(node.target), "v": _expr(node.value)}
    if isinstance(node, ast.If):
        return {"t": "if", "l": line, "c": _expr(node.test), "then": _stmts(node.body), "else": _stmts(node.orelse)}
    if isinstance(node, ast.While):
        return {"t": "while", "l": line, "c": _expr(node.test), "body": _stmts(node.body)}
    if isinstance(node, ast.For):
        return {"t": "for", "l": line, "to": _target(node.target), "in": _expr(node.iter), "body": _stmts(node.body)}
    if isinstance(node, ast.Break):
        return {"t": "break", "l": line}
    if isinstance(node, ast.Continue):
        return {"t": "continue", "l": line}
    if isinstance(node, ast.Pass):
        return None
    if isinstance(node, ast.Return):
        return {"t": "return", "l": line, "v": _expr(node.value) if node.value is not None else None}
    if isinstance(node, ast.Expr):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return None
        return {"t": "expr", "l": line, "v": _expr(node.value)}
    raise ValueError(f"line {line}: {type(node).__name__} can't be turned into a program")


def _expr(node) -> dict:
    if isinstance(node, ast.Constant):
        return {"t": "const", "v": node.value}
    if isinstance(node, ast.Name):
        return {"t": "name", "n": node.id}
    if isinstance(node, ast.BinOp):
        return {"t": "bin", "op": BINOPS[type(node.op)], "a": _expr(node.left), "b": _expr(node.right)}
    if isinstance(node, ast.UnaryOp):
        return {"t": "un", "op": UNOPS[type(node.op)], "a": _expr(node.operand)}
    if isinstance(node, ast.BoolOp):
        return {"t": "bool", "op": "and" if isinstance(node.op, ast.And) else "or", "vs": [_expr(v) for v in node.values]}
    if isinstance(node, ast.Compare):
        return {"t": "cmp", "a": _expr(node.left), "ops": [CMPOPS[type(op)] for op in node.ops], "bs": [_expr(c) for c in node.comparators]}
    if isinstance(node, ast.IfExp):
        return {"t": "ifx", "c": _expr(node.test), "a": _expr(node.body), "b": _expr(node.orelse)}
    if isinstance(node, ast.Call):
        args = [_expr(a) for a in node.args]
        kw = {k.arg: _expr(k.value) for k in node.keywords}
        if isinstance(node.func, ast.Attribute):
            return {"t": "method", "l": _line(node), "o": _expr(node.func.value), "m": node.func.attr, "args": args}
        return {"t": "call", "l": _line(node), "f": node.func.id, "args": args, "kw": kw}
    if isinstance(node, ast.Subscript):
        if isinstance(node.slice, ast.Slice):
            s = node.slice
            return {"t": "slice", "o": _expr(node.value), "lo": _expr(s.lower) if s.lower is not None else None, "hi": _expr(s.upper) if s.upper is not None else None, "st": _expr(s.step) if s.step is not None else None}
        return {"t": "index", "o": _expr(node.value), "i": _expr(node.slice)}
    if isinstance(node, ast.List):
        return {"t": "list", "items": [_expr(e) for e in node.elts]}
    if isinstance(node, ast.Tuple):
        return {"t": "tuple", "items": [_expr(e) for e in node.elts]}
    if isinstance(node, ast.Dict):
        return {"t": "dict", "keys": [_expr(k) for k in node.keys], "vals": [_expr(v) for v in node.values]}
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(value.value)
            else:
                parts.append({"n": value.value.id})
        return {"t": "fstr", "parts": parts}
    raise ValueError(f"{type(node).__name__} can't be turned into a program")


def build(tree: ast.Module, header: dict) -> dict:
    out = {"format": FORMAT, "header": {k: header[k] for k in HEADER if k in header}, "globals": [], "funcs": {}}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            args = [a.arg for a in node.args.args]
            defaults = [d.value for d in node.args.defaults]
            out["funcs"][node.name] = {"l": _line(node), "args": args, "defaults": defaults, "body": _stmts(node.body)}
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in HEADER:
            continue
        else:
            item = _stmt(node)
            if item is not None:
                out["globals"].append(item)
    return out


def dumps(program: dict) -> str:
    return json.dumps(program, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def loads(text: str) -> dict:
    program = json.loads(text)
    if not isinstance(program, dict) or program.get("format") != FORMAT:
        raise ValueError("not a Pebble script program")
    return program
