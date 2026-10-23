from dataclasses import dataclass, field
from pathlib import Path

from ..clock import Clock, iso
from ..selfstore.atomic import CorruptFile, backup_path, read_json
from ..selfstore.codec import PLAIN, SealedCodec
from ..selfstore.rotation import settle
from ..selfstore.sealed import SEAL, UNFINISHED, SelfIsSealed, b64, check_value, frozen_record, open_sealed_value, read_seal, seal_value
from ..selfstore.store import CORE, MANIFEST, SelfStore, default_snapshot_dir
from . import files as convert
from . import locks
from . import room as roomlib
from . import rotation
from .cards import Card, Recovery, render
from .errors import AlreadySealed, DeviceKeyDamaged, NoDeviceKey, NoRoom, NoSelf, SealError
from .keys import KeyHolder, SelfKey
from .startup import holder_for, open_self
from .tries import Tries

PHRASE = rotation.PHRASE
SAVED = rotation.SAVED
MILESTONE = rotation.MILESTONE
VALUES = "values.json"


@dataclass
class Result:
    key: SelfKey | None = None
    set_id: str | None = None
    files: convert.Report = field(default_factory=convert.Report)
    snapshots: convert.Report = field(default_factory=convert.Report)
    room: convert.Report = field(default_factory=convert.Report)

    @property
    def refused(self) -> list[str]:
        return self.files.refused + self.room.refused + self.snapshots.refused


def _has_self(root: Path) -> bool:
    manifest = root / MANIFEST
    return manifest.exists() or backup_path(manifest).exists()


def _frozen_now(root: Path) -> dict:
    try:
        return frozen_record(read_json(root / CORE), read_json(root / VALUES))
    except (FileNotFoundError, CorruptFile) as error:
        raise SealError(f"The core or the values cannot be read ({error}), so nothing can be frozen. Nothing was changed.") from error


def seal_self(
    root: Path,
    password: str,
    holder: KeyHolder,
    clock: Clock | None = None,
    snapshot_dir: Path | None = None,
    kdf: dict | None = None,
) -> Result:
    root = Path(root)
    clock = clock or Clock()
    settle(root)
    seal = read_seal(root)
    if seal is not None and seal.get("state") != "sealing":
        raise AlreadySealed(f"Pebble's self at {root} is already sealed.")
    if not _has_self(root):
        raise NoSelf(f"There is no self at {root}.")
    if seal is None:
        locks.check_password(password)
        frozen = _frozen_now(root)
        key = SelfKey.generate("owner")
        recovery = Recovery.generate()
        device_key = holder.load_or_create()
        seal = {
            "format": locks.SEAL_FORMAT,
            "kind": "pebble-seal",
            "state": "sealing",
            "sealed_at": iso(clock.now()),
            "thrown_away_at": None,
            "check": check_value(key),
            "locks": {
                "owner": locks.owner_lock(key, recovery, password, kdf),
                "pebble": locks.pebble_lock(key, device_key, holder),
                "cards": locks.card_lock(key, recovery),
            },
            "frozen": seal_value(frozen, "frozen", key),
            "room": roomlib.room_lock(roomlib.RoomKey.generate(), recovery),
        }
        locks.save(root, seal)
    else:
        key = locks.open_owner(seal, password, root)
    codec = SealedCodec(key)
    result = Result(key=key, set_id=seal["locks"]["cards"]["set_id"])
    result.room = roomlib.seal_bodies(root, roomlib.public_key(seal))
    result.files = convert.convert_folder(root, lambda name, data: convert.seal_content(codec, name, data))
    result.snapshots = convert.convert_snapshots(
        default_snapshot_dir(root, snapshot_dir), lambda name, data: convert.seal_content(codec, name, data)
    )
    seal.pop("state", None)
    locks.save(root, seal)
    return result


def unseal_self(root: Path, password: str, holder: KeyHolder, snapshot_dir: Path | None = None) -> Result:
    root = Path(root)
    seal = locks.load(root)
    key, recovery = locks.open_owner_all(seal, password, root)
    try:
        room_key = roomlib.open_key(seal, recovery)
    except NoRoom:
        room_key = None
    strict = seal.get("state") not in UNFINISHED
    seal["state"] = "unsealing"
    locks.save(root, seal)
    codec = SealedCodec(key)
    result = Result(key=key, set_id=(seal["locks"].get("cards") or {}).get("set_id"))
    if room_key is not None:
        result.room = roomlib.unseal_bodies(root, room_key, strict)
    result.files = convert.convert_folder(root, lambda name, data: convert.unseal_content(codec, name, data, strict))
    result.snapshots = convert.convert_snapshots(
        default_snapshot_dir(root, snapshot_dir), lambda name, data: convert.unseal_content(codec, name, data, strict)
    )
    (root / SEAL).unlink(missing_ok=True)
    try:
        holder.delete()
    except SealError:
        pass
    return result


def reprint_cards(root: Path, password: str) -> list[str]:
    seal = locks.load(Path(root))
    _, recovery = locks.open_owner_all(seal, password, Path(root))
    Tries(Path(root)).cards_shown()
    return [render(card) for card in recovery.cards()]


def cards_last_shown(root: Path) -> str | None:
    return Tries(Path(root)).last_shown()


def recover(
    root: Path,
    holder: KeyHolder,
    cards: list[Card] | None = None,
    password: str | None = None,
    new_password: str | None = None,
    clock: Clock | None = None,
    kdf: dict | None = None,
    fresh_key: bool = False,
) -> SelfKey:
    root = Path(root)
    clock = clock or Clock()
    seal = locks.load(root)
    key, recovery = _open_with(seal, cards, password, "Recovery needs two cards or the owner's password.", root)
    if new_password is not None:
        locks.check_password(new_password)
    device_key = holder.create() if fresh_key else holder.load_or_create()
    seal["locks"]["pebble"] = locks.pebble_lock(key, device_key, holder)
    if new_password is not None:
        seal["locks"]["owner"] = locks.owner_lock(key, recovery, new_password, kdf)
        seal["owner_lock_made_at"] = iso(clock.now())
    locks.save(root, seal)
    return key


def _open_with(seal: dict, cards: list[Card] | None, password: str | None, refusal: str, root: Path) -> tuple[SelfKey, Recovery]:
    if cards:
        return locks.open_cards_all(seal, cards)
    if password is not None:
        return locks.open_owner_all(seal, password, root)
    raise SealError(refusal)


def prepare_throw_away(root: Path, password: str, confirmation: str, holder: KeyHolder | None = None) -> rotation.ThrowAway:
    return rotation.prepare(Path(root), password, confirmation, holder or holder_for(Path(root)))


def finish_throw_away(plan: rotation.ThrowAway, saved: str, clock: Clock | None = None, snapshot_dir: Path | None = None) -> rotation.Staged:
    return rotation.finish(plan, saved, clock, snapshot_dir)


def throw_away(
    root: Path,
    password: str,
    confirmation: str,
    clock: Clock | None = None,
    holder: KeyHolder | None = None,
    snapshot_dir: Path | None = None,
) -> rotation.ThrowAway:
    plan = prepare_throw_away(root, password, confirmation, holder)
    finish_throw_away(plan, rotation.SAVED, clock, snapshot_dir)
    return plan


@dataclass
class Status:
    root: Path
    sealed: bool
    exists: bool = True
    state: str | None = None
    sealed_at: str | None = None
    thrown_away_at: str | None = None
    rekeyed_at: str | None = None
    owner_lock: bool = False
    pebble_lock: bool = False
    key_file: str = ""
    holder: str = "file"
    lock_holder: str | None = None
    secure: bool | None = None
    device: str = "missing"
    set_id: str | None = None
    checked: int | None = None
    room: roomlib.Summary | None = None
    refused: list[str] = field(default_factory=list)
    cards_shown: str | None = None
    wrong_tries: int = 0


def _secure(holder: KeyHolder) -> bool | None:
    check = getattr(holder, "secure_hardware", None)
    if check is None:
        return None
    try:
        return check()
    except SealError:
        return None


def _room_summary(root: Path, seal: dict, codec) -> roomlib.Summary | None:
    try:
        public = roomlib.public_key(seal)
    except NoRoom:
        return None
    except SealError as error:
        return roomlib.Summary(locked=True, refused=[str(error)])
    return roomlib.summary(root, codec, public)


def status(root: Path, holder: KeyHolder) -> Status:
    root = Path(root)
    settle(root)
    seal = read_seal(root)
    if seal is None:
        found = Status(root, False, exists=_has_self(root), key_file=holder.where(), holder=holder.kind)
        if found.exists:
            found.room = roomlib.summary(root, PLAIN, None)
        return found
    found = Status(
        root,
        True,
        state=seal.get("state"),
        sealed_at=seal.get("sealed_at"),
        thrown_away_at=seal.get("thrown_away_at"),
        rekeyed_at=seal.get("rekeyed_at"),
        owner_lock=bool(seal["locks"].get("owner")),
        pebble_lock=bool(seal["locks"].get("pebble")),
        key_file=holder.where(),
        holder=holder.kind,
        lock_holder=(seal["locks"].get("pebble") or {}).get("holder"),
        set_id=(seal["locks"].get("cards") or {}).get("set_id"),
    )
    tries = Tries(root).read()
    found.cards_shown = cards_last_shown(root)
    found.wrong_tries = int(tries.get("failures") or 0) if isinstance(tries.get("failures"), int) else 0
    found.room = _room_summary(root, seal, None)
    try:
        present = holder.load() is not None
    except DeviceKeyDamaged:
        found.device = "damaged"
        return found
    except SealError:
        found.device = "unavailable"
        return found
    if not present:
        return found
    found.secure = _secure(holder)
    try:
        key = locks.open_pebble(seal, holder, root)
        frozen = open_sealed_value(seal, "frozen", key)
    except (SealError, SelfIsSealed):
        found.device = "does not open"
        return found
    found.device = "opens"
    codec = SealedCodec(key)
    report = convert.check_folder(root, codec, frozen.get("core"))
    found.checked = report.checked
    found.room = _room_summary(root, seal, codec)
    found.refused = report.refused + (found.room.refused if found.room else [])
    return found


def open_room(
    root: Path,
    clock: Clock | None = None,
    password: str | None = None,
    cards: list[Card] | None = None,
    snapshot_dir: Path | None = None,
) -> roomlib.OpenRoom:
    root = Path(root)
    clock = clock or Clock()
    settle(root)
    if read_seal(root) is None:
        if not _has_self(root):
            raise NoSelf(f"There is no self at {root}.")
        return roomlib.OpenRoom(SelfStore.open(root, clock, snapshot_dir=snapshot_dir), None, None)
    seal = locks.load(root)
    key, recovery = _open_with(seal, cards, password, "The locked room opens only with the owner's password or two recovery cards.", root)
    room_key = roomlib.open_key(seal, recovery)
    store = SelfStore.open(root, clock, snapshot_dir=snapshot_dir, key=key)
    return roomlib.OpenRoom(store, room_key, roomlib.public_key(seal))


def owner_lock_exists(root: Path) -> bool:
    return bool(locks.load(Path(root))["locks"].get("owner"))


def mend_room_lock(root: Path, opened: roomlib.OpenRoom) -> None:
    if opened.own_public is None:
        return
    seal = locks.load(Path(root))
    seal.setdefault("room", {})["public"] = b64(opened.own_public)
    locks.save(Path(root), seal)
    opened.public = opened.own_public


@dataclass
class RoomStatus:
    root: Path
    exists: bool
    sealed: bool
    owner_lock: bool = False
    summary: roomlib.Summary | None = None


def room_status(root: Path, holder: KeyHolder) -> RoomStatus:
    root = Path(root)
    settle(root)
    seal = read_seal(root)
    if seal is None:
        exists = _has_self(root)
        return RoomStatus(root, exists, False, summary=roomlib.summary(root, PLAIN, None) if exists else None)
    try:
        codec = SealedCodec(locks.open_pebble(seal, holder, root))
    except (SealError, SelfIsSealed):
        codec = None
    return RoomStatus(root, True, True, bool(seal["locks"].get("owner")), _room_summary(root, seal, codec))


def pebble_room(root: Path, holder: KeyHolder, clock: Clock | None = None, snapshot_dir: Path | None = None) -> roomlib.Room:
    root = Path(root)
    settle(root)
    if not _has_self(root):
        raise NoSelf(f"There is no self at {root}.")
    return roomlib.Room(open_self(root, clock or Clock(), snapshot_dir=snapshot_dir, holder=holder))


@dataclass
class Moved:
    source: str
    target: str
    already: bool = False


def move_lock(root: Path, source: KeyHolder, target: KeyHolder) -> Moved:
    root = Path(root)
    seal = locks.load(root)
    if seal.get("state") in UNFINISHED:
        raise SealError(f"{seal['state']} did not finish; run that command again first. Nothing was changed.")
    lock = seal["locks"].get("pebble")
    if not lock:
        raise NoDeviceKey(f"Pebble's self at {root} has no Pebble's lock to move. {locks.recover_hint(root)}")
    moved = Moved(source.where(), target.where())
    if lock.get("holder") == target.kind:
        locks.open_pebble(seal, target, root)
        source.delete()
        moved.already = True
        return moved
    key = locks.open_pebble(seal, source, root)
    device_key = target.load_or_create()
    seal["locks"]["pebble"] = locks.pebble_lock(key, device_key, target)
    locks.save(root, seal)
    locks.open_pebble(locks.load(root), target, root)
    source.delete()
    return moved


def owner_store(root: Path, password: str, clock: Clock | None = None, snapshot_dir: Path | None = None) -> SelfStore:
    seal = locks.load(Path(root))
    key = locks.open_owner(seal, password, Path(root))
    return SelfStore.open(Path(root), clock or Clock(), snapshot_dir=snapshot_dir, key=key)
