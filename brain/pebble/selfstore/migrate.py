import logging
from typing import Any, Callable

from ..laws import LAWS, outdated
from .atomic import CorruptFile
from .past import without_goal_limit

log = logging.getLogger(__name__)

CORE = "core.json"


def _core(store: Any, what: str) -> dict | None:
    try:
        core = store.read(CORE)
    except (FileNotFoundError, CorruptFile) as error:
        log.warning("%s in %s could not be brought up to date: %s", what, CORE, error)
        return None
    return core if isinstance(core, dict) else None


def _replace_core(store: Any, newer: dict) -> None:
    store._put(CORE, newer)
    store._put(CORE, newer)


def bring_laws_up_to_date(store: Any) -> None:
    core = _core(store, "the laws")
    if core is None or not outdated(core.get("laws")):
        return
    _replace_core(store, {**core, "laws": list(LAWS)})
    log.info("the laws in %s now read as the code's laws", CORE)


def move_goal_limit(store: Any) -> None:
    core = _core(store, "the goal limit")
    newer = without_goal_limit(core) if core is not None else None
    if newer is None:
        return
    _replace_core(store, newer)
    log.info("the goal limit's wording moved from %s into the add_task tool", CORE)


MIGRATIONS: dict[int, Callable[[Any], None]] = {1: bring_laws_up_to_date, 2: move_goal_limit}


class MigrationMissing(RuntimeError):
    pass


def migrate(store: Any, from_version: int, to_version: int) -> list[int]:
    applied = []
    version = from_version
    while version < to_version:
        step = MIGRATIONS.get(version)
        if step is None:
            raise MigrationMissing(f"no migration from self format {version}")
        step(store)
        version += 1
        applied.append(version)
    return applied
