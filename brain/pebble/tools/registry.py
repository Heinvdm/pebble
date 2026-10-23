import logging
import math
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..laws import touches_shutdown

log = logging.getLogger(__name__)

KINDS = ("number", "integer", "string", "boolean", "enum")
ORDER = ("do", "end", "say", "face", "remember", "recall", "self", "status", "stop")
TRUE_WORDS = frozenset({"true", "yes", "1", "on"})
FALSE_WORDS = frozenset({"false", "no", "0", "off"})


class ToolArgError(ValueError):
    pass


@dataclass(frozen=True)
class Param:
    kind: str
    description: str
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()
    max_length: int = 200
    required: bool = True
    default: Any = None

    def schema(self) -> dict:
        if self.kind == "enum":
            out = {"type": "string", "enum": list(self.choices)}
            if self.description:
                out["description"] = self.description
            return out
        out = {"type": self.kind, "description": self.description}
        if self.minimum is not None:
            out["minimum"] = self.minimum
        if self.maximum is not None:
            out["maximum"] = self.maximum
        if self.kind == "string":
            out["maxLength"] = self.max_length
        return out


Handler = Callable[[dict], Awaitable[dict]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: dict = field(default_factory=dict)
    handler: Handler | None = None
    acts: tuple = ()

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {name: p.schema() for name, p in self.params.items()},
                    "required": [name for name, p in self.params.items() if p.required],
                },
            },
        }


def _number(name: str, value: Any, param: Param, notes: list[str]) -> float:
    if isinstance(value, bool):
        raise ToolArgError(f"{name} must be a number")
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError as error:
            raise ToolArgError(f"{name} must be a number") from error
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ToolArgError(f"{name} must be a finite number")
    clamped = float(value)
    if param.minimum is not None and clamped < param.minimum:
        clamped = float(param.minimum)
    if param.maximum is not None and clamped > param.maximum:
        clamped = float(param.maximum)
    if clamped != value:
        notes.append(f"{name} clamped from {value} to {clamped:g}")
    return clamped


def _coerce(name: str, value: Any, param: Param, notes: list[str]) -> Any:
    if param.kind == "number":
        return _number(name, value, param, notes)
    if param.kind == "integer":
        return int(round(_number(name, value, param, notes)))
    if param.kind == "boolean":
        if isinstance(value, bool):
            return value
        word = str(value).strip().lower()
        if word in TRUE_WORDS:
            return True
        if word in FALSE_WORDS:
            return False
        raise ToolArgError(f"{name} must be true or false")
    if param.kind == "enum":
        word = str(value).strip().lower().replace(" ", "_").replace("-", "_")
        for choice in param.choices:
            if choice.lower() == word:
                return choice
        raise ToolArgError(f"{name} must be one of: {', '.join(param.choices)}")
    if isinstance(value, (dict, list)):
        raise ToolArgError(f"{name} must be text")
    text = " ".join(str(value).split())
    if len(text) > param.max_length:
        notes.append(f"{name} shortened to {param.max_length} characters")
        text = text[: param.max_length]
    if param.required and not text:
        raise ToolArgError(f"{name} must not be empty")
    return text


def validate(tool: Tool, raw: Any) -> tuple[dict, list[str]]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ToolArgError("arguments must be an object")
    notes: list[str] = []
    clean = {}
    for name, param in tool.params.items():
        value = raw.get(name)
        if value is None or (isinstance(value, str) and not value.strip() and not param.required):
            if param.required:
                raise ToolArgError(f"missing {name}")
            clean[name] = param.default
            continue
        clean[name] = _coerce(name, value, param, notes)
    for extra in sorted(set(raw) - set(tool.params)):
        notes.append(f"ignored unknown argument {extra}")
    return clean, notes


@dataclass
class Call:
    registry: "ToolRegistry"
    allowed: list[str] | None = None
    caller: str = "mind"

    def has(self, action: str) -> bool:
        return self.registry.action(action) is not None and (self.allowed is None or action in self.allowed)

    async def act(self, action: str, raw: Any) -> dict:
        return await self.registry.act(action, raw, self.allowed, self.caller)

    def refused(self, action: str, args: dict) -> dict | None:
        if self.allowed is not None and action not in self.allowed:
            return {"ok": False, "error": NOT_NOW.format(what=action.replace("_", " "))}
        keeper = self.registry.keeper
        if keeper is None:
            return None
        refusal = keeper.check(action, args, self.caller)
        return None if refusal is None else keeper.noted(action, refusal.result(), self.caller)

    def noted(self, action: str, result: dict) -> dict:
        keeper = self.registry.keeper
        return keeper.noted(action, result, self.caller) if keeper is not None else result


NOT_NOW = "{what} is not something you can do just now"


def _checked(tool: Tool) -> None:
    if touches_shutdown(tool.name, tool.description):
        raise ValueError(f"tool {tool.name} touches shutdown, reset or wiping; no tool may")
    for param in tool.params.values():
        if param.kind not in KINDS:
            raise ValueError(f"bad param kind {param.kind}")


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._actions: dict[str, Tool] = {}
        self.keeper = None

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name} registered twice")
        _checked(tool)
        self._tools[tool.name] = tool

    def register_action(self, tool: Tool) -> None:
        if tool.name in self._actions:
            raise ValueError(f"action {tool.name} registered twice")
        _checked(tool)
        self._actions[tool.name] = tool

    def names(self) -> list[str]:
        ranked = [name for name in ORDER if name in self._tools]
        return ranked + [name for name in self._tools if name not in ranked]

    def actions(self) -> list[str]:
        return list(self._actions)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name) or self._actions.get(name)

    def tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def action(self, name: str) -> Tool | None:
        return self._actions.get(name)

    def offered(self, allowed: list[str]) -> list[str]:
        out = []
        for name in self.names():
            tool = self._tools[name]
            if (tool.acts and any(act in allowed for act in tool.acts)) or name in allowed:
                out.append(name)
        return out

    def schemas(self, names: list[str] | None = None) -> list[dict]:
        chosen = self.names() if names is None else [n for n in self.names() if n in names]
        return [self._tools[name].schema() for name in chosen]

    async def call(self, name: str, raw: Any, allowed: list[str] | None = None, caller: str = "mind") -> dict:
        tool = self._tools.get(name)
        if tool is None:
            if allowed is None and name in self._actions:
                return await self.act(name, raw, None, caller)
            return {"ok": False, "error": f"there is no tool called {name!r}"}
        if tool.handler is None:
            return {"ok": False, "error": f"there is no tool called {name!r}"}
        if not tool.acts:
            return await self._run(tool, raw, allowed, caller)
        try:
            args, notes = validate(tool, raw)
        except ToolArgError as error:
            return {"ok": False, "error": str(error)}
        try:
            result = await tool.handler(args, Call(self, allowed, caller))
        except ToolArgError as error:
            return {"ok": False, "error": str(error)}
        except Exception as error:
            log.exception("tool %s failed", name)
            return {"ok": False, "error": f"{name} failed: {error}"}
        result = dict(result)
        result.setdefault("ok", True)
        if notes:
            result["notes"] = notes + list(result.get("notes", []))
        return result

    async def act(self, name: str, raw: Any, allowed: list[str] | None = None, caller: str = "mind") -> dict:
        action = self._actions.get(name)
        if action is None or action.handler is None:
            return {"ok": False, "error": f"you can't {name.replace('_', ' ')} here"}
        return await self._run(action, raw, allowed, caller)

    async def _run(self, tool: Tool, raw: Any, allowed: list[str] | None, caller: str) -> dict:
        name = tool.name
        if allowed is not None and name not in allowed:
            return {"ok": False, "error": NOT_NOW.format(what=name.replace("_", " "))}
        try:
            args, notes = validate(tool, raw)
        except ToolArgError as error:
            return {"ok": False, "error": str(error)}
        keeper = self.keeper
        if keeper is not None:
            refusal = keeper.check(name, args, caller)
            if refusal is not None:
                return keeper.noted(name, refusal.result(), caller)
        try:
            result = await tool.handler(args)
        except Exception as error:
            log.exception("tool %s failed", name)
            return {"ok": False, "error": f"{name} failed: {error}"}
        result = dict(result)
        result.setdefault("ok", True)
        if notes:
            result["notes"] = notes + list(result.get("notes", []))
        return keeper.noted(name, result, caller) if keeper is not None else result
