from dataclasses import dataclass
from datetime import datetime

from ..picker import OUTRANKED, Choice

MAX_PENDING = 20


@dataclass(frozen=True)
class Noticed:
    at: float
    text: str
    major: bool = False
    kind: str = ""


class EventLog:
    def __init__(self, on_add=None):
        self._pending: list[Noticed] = []
        self.on_add = on_add or (lambda item: None)

    def add(self, at: float, text: str, major: bool = False, kind: str = "") -> None:
        item = Noticed(at, text, major, kind)
        self._pending.append(item)
        del self._pending[:-MAX_PENDING]
        self.on_add(item)

    def put_back(self, items: list[Noticed]) -> None:
        self._pending = (list(items) + self._pending)[-MAX_PENDING:]

    def peek(self) -> list[Noticed]:
        return list(self._pending)

    def drain(self) -> list[Noticed]:
        taken, self._pending = self._pending, []
        return taken

    def has_major(self) -> bool:
        return any(item.major for item in self._pending)


def _bucket(value: float, step: float) -> int:
    return int(value / step)


def digest(state: str, task: str | None, battery_pct: float | None, docked: bool, fear: float, valence: float, arousal: float, needs: dict, link_up: bool) -> tuple:
    return (
        state,
        task,
        None if battery_pct is None else _bucket(battery_pct, 10),
        docked,
        _bucket(fear, 2),
        _bucket(valence + 1, 0.5),
        _bucket(arousal + 1, 0.5),
        tuple(sorted((k, _bucket(v, 25)) for k, v in needs.items())),
        link_up,
    )


def _plan(choice: Choice | None) -> str:
    if choice is None:
        return ""
    others = [f"{o.title} ({s:.2f})" for o, s, why in choice.rejected if why != OUTRANKED][:2]
    text = f"Your body suggests: {choice.chosen.title}"
    if choice.chosen.reason:
        text += f" ({choice.chosen.reason})"
    if others:
        text += f". Also considered: {'; '.join(others)}"
    return text + "."


def observation_text(local: datetime, status_line: str, events: list[Noticed], choice: Choice | None, wake_note: str | None, initiative: bool, quiet: bool, heard: list[str] | tuple = ()) -> str:
    lines = [f"Time: {local.strftime('%A %d %B %Y, %H:%M')}"]
    if wake_note:
        lines.append(f"Note: {wake_note}")
    lines.append(f"Status: {status_line}")
    if events:
        stamped = "; ".join(f"{datetime.fromtimestamp(e.at, local.tzinfo).strftime('%H:%M:%S')} {e.text}" for e in events)
        lines.append(f"Events: {stamped}")
    else:
        lines.append("Events: nothing new")
    if heard:
        lines.append("Heard: " + "; ".join(heard))
    plan = _plan(choice)
    if plan:
        lines.append(plan)
    if quiet:
        lines.append("It is quiet hours: stay quiet and keep still.")
    elif initiative:
        lines.append("You may speak first if something is worth saying.")
    else:
        lines.append("Stay quiet unless something matters.")
    return "\n".join(lines)
