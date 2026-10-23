import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from .protocol import Command, Err, Ok, SettingValue, letter_of, reply_kind

STALE_REPLY_S = 2.0


@dataclass(frozen=True)
class Listing:
    values: tuple[SettingValue, ...]


@dataclass(eq=False)
class Pending:
    letter: str
    kind: str
    key: str | None
    future: asyncio.Future
    sent_at: float
    collected: list = field(default_factory=list)

    def finish(self, value) -> None:
        if not self.future.done():
            self.future.set_result(value)


class ReplyBook:
    def __init__(self, monotonic: Callable[[], float] = time.monotonic, stale_s: float = STALE_REPLY_S):
        self._pending: deque[Pending] = deque()
        self._monotonic = monotonic
        self.stale_s = stale_s

    def __len__(self) -> int:
        return len(self._pending)

    def expect(self, command: Command) -> Pending | None:
        kind = reply_kind(command)
        if kind is None:
            return None
        entry = Pending(
            letter_of(command),
            kind,
            getattr(command, "key", None) if kind == "get" else None,
            asyncio.get_running_loop().create_future(),
            self._monotonic(),
        )
        self._pending.append(entry)
        return entry

    def forget(self, entry: Pending) -> None:
        if entry in self._pending:
            self._pending.remove(entry)
        entry.finish(None)

    def clear(self) -> None:
        while self._pending:
            self._pending.popleft().finish(None)

    def _drop_stale(self) -> None:
        now = self._monotonic()
        while self._pending and now - self._pending[0].sent_at > self.stale_s:
            self._pending.popleft().finish(None)

    def _take(self, entry: Pending, value) -> bool:
        self._pending.remove(entry)
        entry.finish(value)
        return True

    def settle(self, message) -> bool:
        self._drop_stale()
        if isinstance(message, Ok):
            for entry in self._pending:
                if entry.kind == "ok":
                    return self._take(entry, message)
                if entry.kind == "list":
                    return self._take(entry, Listing(tuple(entry.collected)))
            return False
        if isinstance(message, Err):
            for entry in self._pending:
                if entry.letter == message.command:
                    return self._take(entry, message)
            return False
        if isinstance(message, SettingValue):
            for entry in self._pending:
                if entry.kind == "list":
                    entry.collected.append(message)
                    return True
                if entry.kind == "get" and entry.key == message.key:
                    return self._take(entry, message)
            return False
        return False
