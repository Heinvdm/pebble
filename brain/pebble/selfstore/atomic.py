import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

TMP_SUFFIX = ".tmp"
_MISSING = object()


class CorruptFile(Exception):
    pass


class TamperedFile(CorruptFile):
    pass


class TornLine(ValueError):
    pass


def backup_path(path: Path) -> Path:
    path = Path(path)
    return path.with_name(path.name + ".bak")


def _fsync_dir(directory: Path) -> None:
    if os.name != "posix":
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_temp(directory: Path, name: str, data: bytes) -> Path:
    fd, tmp_name = tempfile.mkstemp(prefix=f".{name}.", suffix=TMP_SUFFIX, dir=directory)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def _replace(tmp: Path, target: Path) -> None:
    try:
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _refresh_backup(path: Path, is_valid: Callable[[bytes], bool] | None) -> None:
    current = path.read_bytes()
    if is_valid is not None and not is_valid(current):
        log.warning("not backing up %s: the current copy is unreadable", path)
        return
    bak = backup_path(path)
    _replace(_write_temp(path.parent, bak.name, current), bak)


def write_bytes_atomic(
    path: Path,
    data: bytes,
    keep_backup: bool = True,
    is_valid: Callable[[bytes], bool] | None = None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _write_temp(path.parent, path.name, data)
    if keep_backup and path.exists():
        try:
            _refresh_backup(path, is_valid)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    _replace(tmp, path)
    _fsync_dir(path.parent)


def encode_json(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def is_json(data: bytes) -> bool:
    try:
        json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False
    return True


def opens_as_json(codec: Any, name: str, blob: bytes) -> bool:
    try:
        return is_json(codec.decode(name, blob))
    except TamperedFile:
        return False


def write_json_atomic(path: Path, obj: Any, keep_backup: bool = True, codec: Any = None, name: str | None = None) -> None:
    if codec is None:
        write_bytes_atomic(path, encode_json(obj), keep_backup, is_json)
        return
    key = name or Path(path).name
    write_bytes_atomic(path, codec.encode(key, encode_json(obj)), keep_backup, lambda blob: opens_as_json(codec, key, blob))


def _refuse(source: Path, reason: str, on_tamper: Callable[[Path, str], None] | None) -> None:
    if on_tamper is None:
        log.warning("refused %s: %s", source, reason)
        return
    on_tamper(source, reason)


def read_json(
    path: Path,
    default: Any = _MISSING,
    codec: Any = None,
    name: str | None = None,
    on_tamper: Callable[[Path, str], None] | None = None,
    vet: Callable[[Any], str | None] | None = None,
) -> Any:
    path = Path(path)
    candidates = [p for p in (path, backup_path(path)) if p.exists()]
    if not candidates:
        if default is _MISSING:
            raise FileNotFoundError(str(path))
        return default
    tampered = False
    for candidate in candidates:
        try:
            data = candidate.read_bytes()
            if codec is not None:
                data = codec.decode(name or path.name, data)
            value = json.loads(data.decode("utf-8"))
        except TamperedFile as error:
            tampered = True
            _refuse(candidate, str(error), on_tamper)
            continue
        except (UnicodeDecodeError, ValueError, OSError) as error:
            log.warning("unreadable %s: %s", candidate, error)
            continue
        problem = vet(value) if vet is not None else None
        if problem:
            tampered = True
            _refuse(candidate, problem, on_tamper)
            continue
        if candidate != path:
            log.warning("recovered %s from its backup", path)
        return value
    if tampered:
        raise TamperedFile(str(path))
    raise CorruptFile(str(path))


def _ends_cleanly(path: Path) -> bool:
    size = path.stat().st_size
    if size == 0:
        return True
    with open(path, "rb") as handle:
        handle.seek(size - 1)
        return handle.read(1) == b"\n"


def encode_line(record: Any, codec: Any = None, name: str = "") -> str:
    text = json.dumps(record, ensure_ascii=False)
    return text if codec is None else codec.encode_line(name, text)


def append_jsonl(path: Path, record: Any, codec: Any = None, name: str | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = encode_line(record, codec, name or path.name) + "\n"
    if path.exists() and not _ends_cleanly(path):
        line = "\n" + line
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(
    path: Path,
    limit: int | None = None,
    codec: Any = None,
    name: str | None = None,
    on_tamper: Callable[[Path, str], None] | None = None,
) -> list:
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for number, raw in enumerate(handle, 1):
            text = raw.strip()
            if not text:
                continue
            if codec is not None:
                try:
                    text = codec.decode_line(name or path.name, text)
                except TornLine:
                    continue
                except TamperedFile as error:
                    _refuse(path, f"line {number}: {error}", on_tamper)
                    continue
            try:
                records.append(json.loads(text))
            except ValueError:
                continue
    if limit is not None:
        return records[-limit:] if limit > 0 else []
    return records


def drop_backup(path: Path) -> None:
    bak = backup_path(path)
    if bak.exists():
        bak.unlink()
        _fsync_dir(bak.parent)


def write_lines_atomic(path: Path, records: list, codec: Any = None, name: str | None = None) -> None:
    path = Path(path)
    key = name or path.name
    data = "".join(encode_line(record, codec, key) + "\n" for record in records).encode("utf-8")
    write_bytes_atomic(path, data, keep_backup=False)
    drop_backup(path)


def remove_stray_temps(directory: Path) -> int:
    removed = 0
    for tmp in Path(directory).rglob(f".*{TMP_SUFFIX}"):
        tmp.unlink(missing_ok=True)
        removed += 1
    return removed
