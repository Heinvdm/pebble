import json
import logging
import os
from pathlib import Path, PurePosixPath

from .atomic import encode_json, write_bytes_atomic
from .sealed import JOURNAL, NEXT, NEXT_SEAL, SEAL, SealDamaged, read_seal

log = logging.getLogger(__name__)

STAGING = "staging"
STAGED = "staged"


def _fsync_dir(directory: Path) -> None:
    if os.name != "posix" or not directory.exists():
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_parents(paths: list[Path]) -> None:
    for directory in sorted({path.parent for path in paths}):
        _fsync_dir(directory)


def read_journal(root: Path) -> dict | None:
    path = Path(root) / JOURNAL
    if not path.exists():
        return None
    try:
        journal = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise SealDamaged(f"{path} is damaged ({error}); the key change cannot be finished or undone") from error
    if not isinstance(journal, dict) or journal.get("state") not in (STAGING, STAGED) or not journal.get("rotation"):
        raise SealDamaged(f"{path} is damaged; the key change cannot be finished or undone")
    return journal


def write_journal(root: Path, journal: dict) -> None:
    write_bytes_atomic(Path(root) / JOURNAL, encode_json(journal), keep_backup=False)


def _snapshot_dir(journal: dict) -> Path | None:
    folder = journal.get("snapshots")
    return Path(folder) if folder else None


def staged_files(root: Path, snapshots: Path | None) -> list[Path]:
    found = [path for path in Path(root).rglob(f"*{NEXT}") if path.is_file()]
    if snapshots is not None and Path(snapshots).exists():
        found += [path for path in Path(snapshots).glob(f"self-*.zip{NEXT}") if path.is_file()]
    return sorted(found)


def _inside(base: Path, name: str) -> Path | None:
    pure = PurePosixPath(str(name).replace("\\", "/"))
    if not name or pure.is_absolute() or ".." in pure.parts or ":" in str(name):
        return None
    return Path(base).joinpath(*pure.parts)


def committed(root: Path, journal: dict) -> bool:
    if journal.get("state") != STAGED:
        return False
    seal = read_seal(root)
    return bool(seal and seal.get("rotation") == journal["rotation"])


def roll_back(root: Path, journal: dict) -> None:
    root = Path(root)
    snapshots = _snapshot_dir(journal)
    staged = staged_files(root, snapshots)
    for path in staged:
        path.unlink(missing_ok=True)
    _fsync_parents(staged)
    (root / NEXT_SEAL).unlink(missing_ok=True)
    (root / JOURNAL).unlink(missing_ok=True)
    _fsync_dir(root)


def roll_forward(root: Path, journal: dict) -> None:
    root = Path(root)
    snapshots = _snapshot_dir(journal)
    staged = staged_files(root, snapshots)
    for path in staged:
        os.replace(path, path.with_name(path.name[: -len(NEXT)]))
    _fsync_parents(staged)
    for name in journal.get("drop", []):
        target = _inside(root, name)
        if target is not None:
            target.unlink(missing_ok=True)
    for name in journal.get("drop_snapshots", []):
        target = _inside(snapshots, name) if snapshots is not None and "/" not in str(name) else None
        if target is not None and target.name.startswith("self-"):
            target.unlink(missing_ok=True)
    (root / NEXT_SEAL).unlink(missing_ok=True)
    (root / JOURNAL).unlink(missing_ok=True)
    _fsync_dir(root)


def settle(root: Path) -> str | None:
    root = Path(root)
    journal = read_journal(root)
    if journal is None:
        return None
    if committed(root, journal):
        roll_forward(root, journal)
        log.warning("a key change at %s was interrupted after it was committed; it is now finished", root)
        return "forward"
    roll_back(root, journal)
    log.warning("a key change at %s was interrupted before it was committed; it was undone and the old keys still open the self", root)
    return "back"


def commit(root: Path) -> None:
    root = Path(root)
    os.replace(root / NEXT_SEAL, root / SEAL)
    _fsync_dir(root)
