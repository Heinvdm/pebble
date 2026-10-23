import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from ..clock import Clock, iso
from ..diary import DIARY, Diary
from ..occasions import BadDate, Calendar
from ..selfstore.atomic import TamperedFile, encode_json, write_bytes_atomic
from ..selfstore.codec import SealedCodec
from ..selfstore.rotation import STAGED, STAGING, commit, read_journal, roll_back, roll_forward, settle, staged_files, write_journal
from ..selfstore.sealed import NEXT, NEXT_SEAL, UNFINISHED, check_value, key_opens, open_sealed_value, seal_value
from ..selfstore.store import default_snapshot_dir
from . import files
from . import locks
from . import room as roomlib
from .cards import Recovery, render
from .errors import NoDeviceKey, NoRoom, SealError
from .keys import KeyHolder, SelfKey

PHRASE = "Pebble keeps its own key"
SAVED = "I have saved the new cards"
MILESTONE = "The day I became my own."
ANNIVERSARY = "The day I became my own"
CALENDAR = "calendar.json"


def _same(typed: str, expected: str) -> bool:
    return " ".join(str(typed).split()).lower() == expected.lower()


@dataclass
class ThrowAway:
    root: Path
    old: SelfKey
    new: SelfKey
    holder: KeyHolder
    set_id: str
    rotation: str
    cards: list[str] = field(repr=False)
    device_key: bytes = field(repr=False)
    recovery: Recovery = field(repr=False)
    old_room: roomlib.RoomKey | None = field(repr=False)
    new_room: roomlib.RoomKey = field(repr=False)


@dataclass
class Staged:
    drop: list[str] = field(default_factory=list)
    drop_snapshots: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    files: int = 0
    snapshots: int = 0
    room: int = 0
    written: int = 0


class _Lines:
    def __init__(self):
        self.records = []

    def append(self, name: str, record: dict) -> None:
        self.records.append(record)


def prepare(root: Path, password: str, confirmation: str, holder: KeyHolder) -> ThrowAway:
    root = Path(root)
    if not _same(confirmation, PHRASE):
        raise SealError(f'The confirmation was not "{PHRASE}", so nothing was changed.')
    seal = locks.load(root)
    if seal.get("state") in UNFINISHED:
        raise SealError(f"{seal['state']} did not finish; run that command again first. Nothing was changed.")
    old, old_recovery = locks.open_owner_all(seal, password, root)
    try:
        locks.open_pebble(seal, holder, root)
    except NoDeviceKey as error:
        raise SealError(
            f"Throw-away has to run where Pebble's lock is (its key file or the phone's keystore), because Pebble's lock is made "
            f"again with it ({holder.where()} does not open this self). Use --key-file or --key-holder, or run it on Pebble's phone. "
            "Nothing was changed."
        ) from error
    try:
        old_room = roomlib.open_key(seal, old_recovery)
    except NoRoom:
        old_room = None
    new = SelfKey.generate("pebble")
    recovery = Recovery.generate()
    printed = [render(card) for card in recovery.cards()]
    return ThrowAway(
        root, old, new, holder, recovery.set_id, secrets.token_hex(8), printed, holder.load(), recovery, old_room, roomlib.RoomKey.generate()
    )


def begin(root: Path, plan: ThrowAway, snapshots: Path, clock: Clock) -> None:
    write_journal(root, {"state": STAGING, "rotation": plan.rotation, "snapshots": str(Path(snapshots).resolve()), "started_at": iso(clock.now())})


def stage_file(path: Path, data: bytes) -> None:
    write_bytes_atomic(path.with_name(path.name + NEXT), data, keep_backup=False)


def _milestone(clock: Clock) -> dict:
    return Diary(_Lines(), clock).write(MILESTONE, kind="milestone")


def _with_milestone(new: SealedCodec, data: bytes, clock: Clock) -> bytes:
    if data and not data.endswith(b"\n"):
        data += b"\n"
    line = new.encode_line(DIARY, json.dumps(_milestone(clock), ensure_ascii=False))
    return data + line.encode("ascii") + b"\n"


def _with_anniversary(old: SealedCodec, new: SealedCodec, data: bytes | None, clock: Clock) -> bytes | None:
    try:
        calendar_data = json.loads(old.decode(CALENDAR, data).decode("utf-8")) if data is not None else {}
    except (TamperedFile, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(calendar_data, dict):
        return None
    calendar = Calendar(calendar_data)
    now = clock.now()
    local = clock.local(now)
    try:
        calendar.add_personal(ANNIVERSARY, local.month, local.day, "anniversary", at=iso(now), year=local.year)
    except BadDate:
        return None
    calendar_data["personal"] = calendar.personal
    return new.encode(CALENDAR, encode_json(calendar_data))


def stage(root: Path, plan: ThrowAway, snapshots: Path, clock: Clock) -> Staged:
    old, new = SealedCodec(plan.old), SealedCodec(plan.new)
    staged = Staged()
    seen = set()

    def put(path: Path, data: bytes) -> None:
        stage_file(path, data)
        staged.written += 1
    files.remove_snapshot_temps(snapshots)
    gone = set()
    for path, relative in roomlib.bodies(root):
        outcome = roomlib.rekey_body(plan.old_room, plan.new_room.public, relative, path.read_bytes())
        staged.refused.extend(outcome.refused)
        if outcome.drop:
            staged.drop.append(relative)
            gone.add(roomlib.meta_name(path.name[: -len(files.ROOM_BODY)]))
            continue
        put(path, outcome.data)
        staged.room += 1
    for path, relative in files.self_files(root):
        if files.is_temp(path):
            path.unlink(missing_ok=True)
            continue
        if relative in gone:
            staged.drop.append(relative)
            continue
        seen.add(relative)
        data = path.read_bytes()
        outcome = files.rekey_content(old, new, relative, data)
        staged.refused.extend(outcome.refused)
        if relative == CALENDAR:
            outcome.data = _with_anniversary(old, new, data, clock) or outcome.data
        if outcome.drop and outcome.data is None:
            staged.drop.append(relative)
            continue
        content = _with_milestone(new, outcome.data, clock) if relative == DIARY else outcome.data
        put(path, content)
        staged.files += 1
    if DIARY not in seen:
        put(Path(root) / DIARY, _with_milestone(new, b"", clock))
    if CALENDAR not in seen:
        made = _with_anniversary(old, new, None, clock)
        if made is not None:
            put(Path(root) / CALENDAR, made)
    def rekey_member(name: str, data: bytes) -> files.Outcome:
        if files.in_room(name):
            return files.Outcome(refused=[f"{name}: the room never goes into snapshots, dropped"], drop=True)
        return files.rekey_content(old, new, name, data)

    for path in files.snapshot_zips(snapshots):
        outcome = files.rebuild_zip(path, rekey_member)
        staged.refused.extend(outcome.refused)
        if outcome.drop:
            staged.drop_snapshots.append(path.name)
            continue
        put(path, outcome.data if outcome.data is not None else path.read_bytes())
        staged.snapshots += 1
    return staged


def _interrupted(root: Path, plan: ThrowAway, snapshots: Path) -> SealError:
    roll_back(root, {"rotation": plan.rotation, "snapshots": str(Path(snapshots).resolve())})
    return SealError("Something else opened the self while its key was being changed, so the change was undone. Stop Pebble and run throw-away again.")


def _ours(root: Path, plan: ThrowAway, state: str) -> bool:
    journal = read_journal(root)
    return bool(journal and journal.get("rotation") == plan.rotation and journal.get("state") == state)


def mark_staged(root: Path, plan: ThrowAway, snapshots: Path, staged: Staged, clock: Clock) -> None:
    if not _ours(root, plan, STAGING):
        raise _interrupted(root, plan, snapshots)
    journal = read_journal(root)
    journal.update({
        "state": STAGED,
        "rotation": plan.rotation,
        "snapshots": str(Path(snapshots).resolve()),
        "drop": staged.drop,
        "drop_snapshots": staged.drop_snapshots,
        "written": staged.written,
        "staged_at": iso(clock.now()),
    })
    write_journal(root, journal)


def ready(root: Path, plan: ThrowAway, snapshots: Path, staged: Staged) -> None:
    whole = _ours(root, plan, STAGED) and (Path(root) / NEXT_SEAL).exists()
    if not whole or len(staged_files(root, Path(snapshots).resolve())) != staged.written:
        raise _interrupted(root, plan, snapshots)


def write_next_seal(root: Path, plan: ThrowAway, seal: dict, clock: Clock) -> None:
    now = iso(clock.now())
    upcoming = {
        "format": seal.get("format", locks.SEAL_FORMAT),
        "kind": "pebble-seal",
        "rotation": plan.rotation,
        "sealed_at": seal.get("sealed_at"),
        "thrown_away_at": now,
        "rekeyed_at": now,
        "check": check_value(plan.new),
        "locks": {"pebble": locks.pebble_lock(plan.new, plan.device_key, plan.holder), "cards": locks.card_lock(plan.new, plan.recovery)},
        "frozen": seal_value(open_sealed_value(seal, "frozen", plan.old), "frozen", plan.new),
        "room": roomlib.room_lock(plan.new_room, plan.recovery),
    }
    write_bytes_atomic(Path(root) / NEXT_SEAL, encode_json(upcoming), keep_backup=False)


def finish(plan: ThrowAway, saved: str, clock: Clock | None = None, snapshot_dir: Path | None = None) -> Staged:
    clock = clock or Clock()
    if not _same(saved, SAVED):
        raise SealError(f'The answer was not "{SAVED}", so nothing was changed. The cards just shown are not in use.')
    root = plan.root
    settle(root)
    seal = locks.load(root)
    if not key_opens(seal, plan.old) or not seal["locks"].get("owner") or seal.get("state") in UNFINISHED:
        raise SealError("The self changed since the new cards were made. Nothing was changed; run throw-away again.")
    snapshots = default_snapshot_dir(root, snapshot_dir)
    begin(root, plan, snapshots, clock)
    staged = stage(root, plan, snapshots, clock)
    mark_staged(root, plan, snapshots, staged, clock)
    write_next_seal(root, plan, seal, clock)
    ready(root, plan, snapshots, staged)
    commit(root)
    roll_forward(root, read_journal(root))
    return staged
