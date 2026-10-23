import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..selfstore.atomic import encode_json, write_bytes_atomic
from ..selfstore.sealed import TRIES
from .errors import TooManyTries

FREE_TRIES = 4
FIRST_WAIT_S = 30.0
MAX_WAIT_S = 3600.0
SHOWN_KEEP = 20


def wait_for(failures: int) -> float:
    if failures <= FREE_TRIES:
        return 0.0
    return min(MAX_WAIT_S, FIRST_WAIT_S * 2 ** min(10, failures - FREE_TRIES - 1))


class Tries:
    def __init__(self, root: Path, now: Callable[[], float] | None = None):
        self.path = Path(root) / TRIES
        self.now = now or (lambda: time.time())

    def read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"failures": FREE_TRIES, "until": 0.0}
        return data if isinstance(data, dict) else {"failures": FREE_TRIES, "until": 0.0}

    def _write(self, data: dict) -> None:
        write_bytes_atomic(self.path, encode_json(data), keep_backup=False)

    def waiting(self) -> float:
        try:
            until = float(self.read().get("until") or 0.0)
        except (TypeError, ValueError):
            until = self.now() + FIRST_WAIT_S
        return max(0.0, until - self.now())

    def check(self) -> None:
        wait = self.waiting()
        if wait > 0:
            raise TooManyTries(f"Too many wrong passwords. Try again in {math.ceil(wait)} seconds.", wait)

    def failed(self) -> float:
        data = self.read()
        try:
            failures = int(data.get("failures") or 0) + 1
        except (TypeError, ValueError):
            failures = FREE_TRIES + 1
        wait = wait_for(failures)
        self._write({**data, "failures": failures, "until": self.now() + wait if wait else 0.0})
        return wait

    def passed(self) -> None:
        data = self.read()
        if data.get("failures") or data.get("until"):
            self._write({**data, "failures": 0, "until": 0.0})

    def cards_shown(self) -> None:
        data = self.read()
        shown = [str(at) for at in data.get("cards_shown") or [] if at][-(SHOWN_KEEP - 1):]
        shown.append(datetime.fromtimestamp(self.now(), timezone.utc).isoformat(timespec="seconds"))
        self._write({**data, "cards_shown": shown})

    def last_shown(self) -> str | None:
        shown = self.read().get("cards_shown") or []
        return str(shown[-1]) if shown else None
