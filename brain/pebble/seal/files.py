import io
import json
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..selfstore.atomic import TMP_SUFFIX, TamperedFile, TornLine, write_bytes_atomic
from ..selfstore.codec import LINE_MARK, MAGIC, SealedCodec, is_line_file
from ..selfstore.sealed import core_matches, is_reserved

REFUSED_SUFFIX = ".refused"
CORE = "core.json"
ROOM = "room"
ROOM_BODY = ".item"


@dataclass
class Outcome:
    data: bytes | None = None
    refused: list[str] = field(default_factory=list)
    drop: bool = False


@dataclass
class Report:
    changed: int = 0
    checked: int = 0
    removed: int = 0
    refused: list[str] = field(default_factory=list)


def is_temp(path: Path) -> bool:
    return path.name.startswith(".") and path.name.endswith(TMP_SUFFIX)


def is_seal_file(relative: str) -> bool:
    return is_reserved(relative)


def in_room(relative: str) -> bool:
    parts = str(relative).replace("\\", "/").split("/")
    return len(parts) > 1 and parts[0].lower() == ROOM


def is_room_body(relative: str) -> bool:
    parts = str(relative).replace("\\", "/").split("/")
    return len(parts) == 2 and parts[0].lower() == ROOM and parts[1].lower().endswith(ROOM_BODY)


def self_files(root: Path) -> list[tuple[Path, str]]:
    root = Path(root)
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if not is_seal_file(relative) and not is_room_body(relative):
            found.append((path, relative))
    return found


def _split(data: bytes) -> list[tuple[bytes, bytes]]:
    parts = []
    for part in data.split(b"\n"):
        if part.endswith(b"\r"):
            parts.append((part[:-1], b"\r"))
        else:
            parts.append((part, b""))
    return parts


def _join(parts: list[tuple[bytes, bytes] | None]) -> bytes:
    return b"\n".join(body + tail for body, tail in (p for p in parts if p is not None))


def _seal_lines(codec: SealedCodec, relative: str, data: bytes) -> Outcome:
    outcome = Outcome()
    parts: list[tuple[bytes, bytes] | None] = []
    changed = False
    for number, (body, tail) in enumerate(_split(data), 1):
        text = body.decode("utf-8", errors="replace")
        if not text.strip():
            parts.append((body, tail))
            continue
        if text.strip().startswith(LINE_MARK):
            try:
                codec.decode_line(relative, text)
            except TornLine:
                pass
            except TamperedFile as error:
                outcome.refused.append(f"{relative} line {number}: {error}")
            parts.append((body, tail))
            continue
        parts.append((codec.encode_line(relative, text).encode("ascii"), tail))
        changed = True
    outcome.data = _join(parts) if changed else None
    return outcome


def _unseal_lines(codec: SealedCodec, relative: str, data: bytes, strict: bool) -> Outcome:
    outcome = Outcome()
    parts: list[tuple[bytes, bytes] | None] = []
    changed = False
    for number, (body, tail) in enumerate(_split(data), 1):
        text = body.decode("utf-8", errors="replace")
        if not text.strip():
            parts.append((body, tail))
            continue
        if not text.strip().startswith(LINE_MARK):
            if strict:
                outcome.refused.append(f"{relative} line {number}: not sealed, dropped")
                changed = True
                continue
            parts.append((body, tail))
            continue
        try:
            parts.append((codec.decode_line(relative, text).encode("utf-8"), tail))
        except TornLine:
            pass
        except TamperedFile as error:
            outcome.refused.append(f"{relative} line {number}: {error}, dropped")
        changed = True
    outcome.data = _join(parts) if changed else None
    return outcome


def _rekey_lines(old: SealedCodec, new: SealedCodec, relative: str, data: bytes) -> Outcome:
    outcome = Outcome()
    parts: list[tuple[bytes, bytes] | None] = []
    for number, (body, tail) in enumerate(_split(data), 1):
        text = body.decode("utf-8", errors="replace")
        if not text.strip():
            parts.append((body, tail))
            continue
        try:
            plain = old.decode_line(relative, text)
        except TornLine:
            continue
        except TamperedFile as error:
            outcome.refused.append(f"{relative} line {number}: {error}, dropped")
            continue
        parts.append((new.encode_line(relative, plain).encode("ascii"), tail))
    outcome.data = _join(parts)
    return outcome


def rekey_content(old: SealedCodec, new: SealedCodec, relative: str, data: bytes) -> Outcome:
    if is_line_file(relative):
        return _rekey_lines(old, new, relative, data)
    try:
        return Outcome(data=new.encode(relative, old.decode(relative, data)))
    except TamperedFile as error:
        return Outcome(refused=[f"{relative}: {error}, dropped"], drop=True)


def seal_content(codec: SealedCodec, relative: str, data: bytes) -> Outcome:
    if is_line_file(relative):
        return _seal_lines(codec, relative, data)
    if data.startswith(MAGIC):
        try:
            codec.decode(relative, data)
        except TamperedFile as error:
            return Outcome(refused=[f"{relative}: {error}"])
        return Outcome()
    return Outcome(data=codec.encode(relative, data))


def unseal_content(codec: SealedCodec, relative: str, data: bytes, strict: bool) -> Outcome:
    if is_line_file(relative):
        return _unseal_lines(codec, relative, data, strict)
    if not data.startswith(MAGIC):
        if strict:
            return Outcome(refused=[f"{relative}: not sealed, set aside"], drop=True)
        return Outcome()
    try:
        return Outcome(data=codec.decode(relative, data))
    except TamperedFile as error:
        return Outcome(refused=[f"{relative}: {error}, set aside"], drop=True)


def check_content(codec: SealedCodec, relative: str, data: bytes, frozen_core: str | None) -> list[str]:
    if is_line_file(relative):
        problems = []
        for number, (body, _) in enumerate(_split(data), 1):
            text = body.decode("utf-8", errors="replace")
            if not text.strip():
                continue
            try:
                codec.decode_line(relative, text)
            except TornLine:
                continue
            except TamperedFile as error:
                problems.append(f"{relative} line {number}: {error}")
        return problems
    try:
        plain = codec.decode(relative, data)
    except TamperedFile as error:
        return [f"{relative}: {error}"]
    if frozen_core and relative == CORE:
        try:
            value = json.loads(plain.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return []
        if not core_matches(value, frozen_core):
            return [f"{relative}: differs from the core frozen at sealing"]
    return []


def set_aside(path: Path) -> None:
    os.replace(path, path.with_name(path.name + REFUSED_SUFFIX))


def convert_folder(root: Path, transform: Callable[[str, bytes], Outcome]) -> Report:
    report = Report()
    for path, relative in self_files(root):
        if is_temp(path):
            path.unlink(missing_ok=True)
            report.removed += 1
            continue
        report.checked += 1
        outcome = transform(relative, path.read_bytes())
        report.refused.extend(outcome.refused)
        if outcome.drop:
            set_aside(path)
        elif outcome.data is not None:
            write_bytes_atomic(path, outcome.data, keep_backup=False)
            report.changed += 1
    return report


def check_folder(root: Path, codec: SealedCodec, frozen_core: str | None) -> Report:
    report = Report()
    for path, relative in self_files(root):
        if is_temp(path):
            continue
        report.checked += 1
        try:
            data = path.read_bytes()
        except OSError as error:
            report.refused.append(f"{relative}: cannot be read ({error})")
            continue
        report.refused.extend(check_content(codec, relative, data, frozen_core))
    return report


def snapshot_zips(snapshot_dir: Path) -> list[Path]:
    snapshot_dir = Path(snapshot_dir)
    if not snapshot_dir.exists():
        return []
    return sorted(snapshot_dir.glob("self-*.zip"))


def remove_snapshot_temps(snapshot_dir: Path) -> int:
    snapshot_dir = Path(snapshot_dir)
    if not snapshot_dir.exists():
        return 0
    removed = 0
    for tmp in list(snapshot_dir.glob(f"*{TMP_SUFFIX}")):
        tmp.unlink(missing_ok=True)
        removed += 1
    return removed


def rebuild_zip(path: Path, transform: Callable[[str, bytes], Outcome]) -> Outcome:
    result = Outcome()
    try:
        with zipfile.ZipFile(path) as archive:
            members = [(info, archive.read(info)) for info in archive.infolist()]
    except (zipfile.BadZipFile, OSError) as error:
        return Outcome(refused=[f"{path.name}: the snapshot cannot be read ({error})"], drop=True)
    changed = False
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as rebuilt:
        for info, data in members:
            if info.is_dir():
                rebuilt.writestr(info, data)
                continue
            if is_seal_file(info.filename) or Path(info.filename).name.endswith(TMP_SUFFIX):
                changed = True
                continue
            outcome = transform(info.filename, data)
            result.refused.extend(f"{path.name}/{item}" for item in outcome.refused)
            if outcome.drop:
                changed = True
                continue
            member = zipfile.ZipInfo(info.filename, info.date_time)
            member.compress_type = zipfile.ZIP_DEFLATED
            member.external_attr = info.external_attr
            rebuilt.writestr(member, outcome.data if outcome.data is not None else data)
            changed = changed or outcome.data is not None
    if changed:
        result.data = buffer.getvalue()
    return result


def convert_zip(path: Path, transform: Callable[[str, bytes], Outcome]) -> Outcome:
    result = rebuild_zip(path, transform)
    if result.drop:
        result.refused = [f"{item}; delete it by hand" for item in result.refused]
        result.drop = False
        return result
    if result.data is not None:
        write_bytes_atomic(path, result.data, keep_backup=False)
        result.data = b""
    return result


def convert_snapshots(snapshot_dir: Path, transform: Callable[[str, bytes], Outcome]) -> Report:
    report = Report(removed=remove_snapshot_temps(snapshot_dir))
    for path in snapshot_zips(snapshot_dir):
        report.checked += 1
        outcome = convert_zip(path, transform)
        report.refused.extend(outcome.refused)
        if outcome.data is not None:
            report.changed += 1
    return report
