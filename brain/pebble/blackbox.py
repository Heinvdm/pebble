import itertools
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

from .clock import Clock, iso

_ids = itertools.count()

BLACKBOX = "logs/blackbox.jsonl"


class BlackBox:
    def __init__(
        self,
        path: Path,
        clock: Clock,
        max_bytes: int = 1_000_000,
        backups: int = 5,
        seal_line: Callable[[str], str] | None = None,
    ):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.clock = clock
        self._seal_line = seal_line
        self._logger = logging.getLogger(f"pebble.blackbox.{next(_ids)}")
        self._logger.propagate = False
        self._logger.setLevel(logging.INFO)
        self._handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
        self._handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(self._handler)

    @classmethod
    def for_store(cls, store, clock: Clock, name: str = BLACKBOX, **options) -> "BlackBox":
        return cls(store.path(name), clock, seal_line=store.line_sealer(name) if store.sealed else None, **options)

    def record(self, kind: str, **data) -> None:
        line = {"at": iso(self.clock.now()), "kind": kind}
        line.update(data)
        text = json.dumps(line, default=str, ensure_ascii=False)
        self._logger.info(text if self._seal_line is None else self._seal_line(text))

    def close(self) -> None:
        self._logger.removeHandler(self._handler)
        self._handler.close()
