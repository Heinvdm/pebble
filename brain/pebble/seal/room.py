import hashlib
import json
import os
import secrets
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..clock import iso
from ..selfstore.atomic import TamperedFile, write_bytes_atomic
from ..selfstore.codec import BadSeal
from ..selfstore.sealed import SEAL, b64, read_seal, seal_aad, unb64
from . import crypto
from .cards import Recovery
from .errors import NoRoom, RoomError, SealError
from .files import ROOM, ROOM_BODY, Outcome, Report, set_aside

KINDS = ("photo", "voice", "keepsake", "file")
SEALED = b"PEBBLE-ROOM-1\n"
PLAIN = b"PEBBLE-ROOM-PLAIN-1\n"
META = ".json"
ID_BYTES = 8
FINGERPRINT_BYTES = 8
BODY_AAD = b"pebble-room-item\x00"
NAME_LIMIT = 255
MIN_ID = 4
PHOTO = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".bmp"})
VOICE = frozenset({".wav", ".ogg", ".opus", ".mp3", ".m4a", ".aac", ".flac", ".amr"})
NO_ROOM = "This sealed self has no locked room (it was sealed before the room existed). Unseal and seal it again to make one."


def fingerprint(public: bytes) -> bytes:
    return hashlib.sha256(b"pebble-room-key\x00" + bytes(public)).digest()[:FINGERPRINT_BYTES]


def show_fingerprint(public: bytes) -> str:
    text = fingerprint(public).hex()
    return "-".join(text[i:i + 4] for i in range(0, len(text), 4))


class RoomKey:
    def __init__(self, private: bytes):
        if len(private) != crypto.X25519_BYTES:
            raise ValueError(f"a room key has {crypto.X25519_BYTES} bytes")
        self._private = bytes(private)
        self.public = crypto.x25519_public(self._private)

    @classmethod
    def generate(cls) -> "RoomKey":
        return cls(crypto.x25519_private())

    def secret(self) -> bytes:
        return self._private

    def __repr__(self) -> str:
        return f"RoomKey(fingerprint={show_fingerprint(self.public)!r})"


def room_lock(key: RoomKey, recovery: Recovery) -> dict:
    wrapped = crypto.Aead(recovery.secret).seal(key.secret(), seal_aad("room:cards"))
    return {"public": b64(key.public), "wrapped": b64(wrapped)}


def _record(seal: dict) -> dict:
    room = seal.get("room")
    if not isinstance(room, dict):
        raise NoRoom(NO_ROOM)
    return room


def public_key(seal: dict) -> bytes:
    try:
        public = unb64(_record(seal)["public"])
    except (KeyError, TypeError, ValueError) as error:
        raise SealError(f"the locked room's lock in {SEAL} is damaged") from error
    if len(public) != crypto.X25519_BYTES:
        raise SealError(f"the locked room's lock in {SEAL} is damaged")
    return public


def open_key(seal: dict, recovery: Recovery) -> RoomKey:
    room = _record(seal)
    try:
        private = crypto.Aead(recovery.secret).open(unb64(room["wrapped"]), seal_aad("room:cards"))
    except BadSeal as error:
        raise SealError(f"the locked room's lock in {SEAL} does not open with the recovery secret; it is damaged") from error
    except (KeyError, TypeError, ValueError) as error:
        raise SealError(f"the locked room's lock in {SEAL} is damaged") from error
    return RoomKey(private)


def is_id(text: str) -> bool:
    return len(text) == 2 * ID_BYTES and all(ch in "0123456789abcdef" for ch in text)


def body_name(item_id: str) -> str:
    return f"{ROOM}/{item_id}{ROOM_BODY}"


def meta_name(item_id: str) -> str:
    return f"{ROOM}/{item_id}{META}"


def _aad(relative: str, mark: bytes) -> bytes:
    return BODY_AAD + relative.encode("utf-8") + b"\x00" + mark


def seal_body(public: bytes, relative: str, payload: bytes) -> bytes:
    mark = fingerprint(public)
    return SEALED + mark + crypto.seal_to(public, payload, _aad(relative, mark))


def open_body(key: RoomKey | None, relative: str, body: bytes) -> bytes:
    body = bytes(body)
    if body.startswith(PLAIN):
        if key is not None:
            raise TamperedFile(f"{relative} is not sealed")
        return body[len(PLAIN):]
    if not body.startswith(SEALED):
        raise TamperedFile(f"{relative} is not a thing from the room")
    if key is None:
        raise TamperedFile(f"{relative} is sealed, and this room is not open")
    start = len(SEALED)
    mark = body[start:start + FINGERPRINT_BYTES]
    if mark != fingerprint(key.public):
        raise TamperedFile(f"{relative} was sealed to a lock this room does not have")
    try:
        return crypto.open_from(key.secret(), body[start + FINGERPRINT_BYTES:], _aad(relative, mark))
    except BadSeal as error:
        raise TamperedFile(f"{relative} does not open: it was edited or moved") from error


def pack(item_id: str, name: str, kind: str, at: str, data: bytes) -> bytes:
    header = {"id": item_id, "name": name, "kind": kind, "at": at, "size": len(data)}
    return json.dumps(header, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n" + bytes(data)


def unpack(relative: str, payload: bytes) -> tuple[dict, bytes]:
    head, _, data = bytes(payload).partition(b"\n")
    try:
        header = json.loads(head.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise TamperedFile(f"{relative} is damaged") from error
    if not isinstance(header, dict) or header.get("size") != len(data):
        raise TamperedFile(f"{relative} is damaged")
    return header, data


def check_kind(kind: str) -> str:
    text = str(kind or "").strip().lower()
    if text not in KINDS:
        raise RoomError(f"A thing in the room is a {', '.join(KINDS[:-1])} or {KINDS[-1]}; {kind!r} is none of those.")
    return text


def check_name(name: str) -> str:
    text = " ".join(str(name or "").split())
    if not text:
        raise RoomError("A thing in the room needs a name (it is sealed inside, never written in the open).")
    if len(text) > NAME_LIMIT:
        raise RoomError(f"A name in the room has at most {NAME_LIMIT} characters.")
    return text


def guess_kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in PHOTO:
        return "photo"
    if suffix in VOICE:
        return "voice"
    return "file"


@dataclass(frozen=True)
class Item:
    id: str
    at: str | None = None
    kind: str | None = None
    size: int | None = None
    listed: bool = True
    present: bool = True


@dataclass(frozen=True)
class Thing:
    id: str
    name: str | None = None
    kind: str | None = None
    at: str | None = None
    size: int | None = None
    problem: str | None = None


def found(root: Path) -> dict[str, dict[str, Path]]:
    folder = Path(root) / ROOM
    if not folder.is_dir():
        return {}
    ids: dict[str, dict[str, Path]] = {}
    for path in folder.iterdir():
        if not path.is_file():
            continue
        for suffix, part in ((ROOM_BODY, "body"), (META, "meta")):
            stem = path.name[: -len(suffix)]
            if path.name.endswith(suffix) and is_id(stem):
                ids.setdefault(stem, {})[part] = path
    return ids


def new_id(root: Path) -> str:
    taken = found(root)
    while True:
        item_id = secrets.token_hex(ID_BYTES)
        if item_id not in taken:
            return item_id


def meta_record(item: Item) -> dict:
    return {"format": 1, "id": item.id, "at": item.at, "kind": item.kind, "size": item.size}


def read_meta(codec, item_id: str, path: Path) -> Item:
    relative = meta_name(item_id)
    try:
        record = json.loads(codec.decode(relative, path.read_bytes()).decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise TamperedFile(f"{relative} is damaged") from error
    if not isinstance(record, dict) or record.get("id") != item_id or record.get("kind") not in KINDS or not isinstance(record.get("size"), int):
        raise TamperedFile(f"{relative} is damaged")
    return Item(item_id, record.get("at"), record["kind"], record["size"])


def listing(root: Path, codec) -> tuple[list[Item], list[str]]:
    items, refused = [], []
    for item_id, parts in sorted(found(root).items()):
        present = "body" in parts
        if "meta" in parts and codec is not None:
            try:
                item = read_meta(codec, item_id, parts["meta"])
            except (TamperedFile, OSError) as error:
                refused.append(f"{meta_name(item_id)}: {error}")
            else:
                items.append(Item(item.id, item.at, item.kind, item.size, True, present))
                continue
        if present:
            items.append(Item(item_id, listed=False))
    items.sort(key=lambda item: (item.at or "", item.id))
    return items, refused


def bodies(root: Path) -> list[tuple[Path, str]]:
    return [(parts["body"], body_name(item_id)) for item_id, parts in sorted(found(root).items()) if "body" in parts]


def _head(path: Path) -> bytes:
    with open(path, "rb") as handle:
        return handle.read(max(len(PLAIN), len(SEALED) + FINGERPRINT_BYTES))


def check_bodies(root: Path, public: bytes) -> list[str]:
    problems = []
    mark = fingerprint(public)
    for path, relative in bodies(root):
        try:
            head = _head(path)
        except OSError as error:
            problems.append(f"{relative}: cannot be read ({error})")
            continue
        if head.startswith(PLAIN):
            problems.append(f"{relative}: not sealed")
        elif not head.startswith(SEALED):
            problems.append(f"{relative}: not a thing from the room")
        elif head[len(SEALED):len(SEALED) + FINGERPRINT_BYTES] != mark:
            problems.append(f"{relative}: sealed to a lock this room does not have")
    return problems


def seal_bodies(root: Path, public: bytes) -> Report:
    report = Report()
    for path, relative in bodies(root):
        report.checked += 1
        data = path.read_bytes()
        if data.startswith(PLAIN):
            write_bytes_atomic(path, seal_body(public, relative, data[len(PLAIN):]), keep_backup=False)
            report.changed += 1
        elif not data.startswith(SEALED):
            report.refused.append(f"{relative}: not a thing from the room, set aside")
            set_aside(path)
    return report


def unseal_bodies(root: Path, key: RoomKey | None, strict: bool) -> Report:
    report = Report()
    for path, relative in bodies(root):
        report.checked += 1
        data = path.read_bytes()
        if data.startswith(PLAIN):
            if strict:
                report.refused.append(f"{relative}: not sealed, set aside")
                set_aside(path)
            continue
        try:
            payload = open_body(key, relative, data)
        except TamperedFile as error:
            report.refused.append(f"{error}, set aside")
            set_aside(path)
            continue
        write_bytes_atomic(path, PLAIN + payload, keep_backup=False)
        report.changed += 1
    return report


def rekey_body(old: RoomKey | None, new_public: bytes, relative: str, data: bytes) -> Outcome:
    try:
        payload = open_body(old, relative, data)
    except TamperedFile as error:
        return Outcome(refused=[f"{error}, dropped"], drop=True)
    return Outcome(data=seal_body(new_public, relative, payload))


@dataclass
class Summary:
    locked: bool
    things: int = 0
    unread: int = 0
    missing: int = 0
    size: int = 0
    kinds: dict[str, int] = field(default_factory=dict)
    first: str | None = None
    last: str | None = None
    public: bytes | None = None
    refused: list[str] = field(default_factory=list)


def summary(root: Path, codec, public: bytes | None) -> Summary:
    items, refused = listing(root, codec)
    listed = [item for item in items if item.listed]
    dates = sorted(item.at for item in listed if item.at)
    result = Summary(
        locked=public is not None,
        things=len(items),
        unread=len(items) - len(listed),
        missing=sum(1 for item in listed if not item.present),
        size=sum(item.size or 0 for item in listed),
        kinds=dict(Counter(item.kind for item in listed)),
        first=dates[0] if dates else None,
        last=dates[-1] if dates else None,
        public=public,
        refused=refused,
    )
    if public is not None:
        result.refused += check_bodies(root, public)
    return result


class Room:
    def __init__(self, store):
        self.store = store

    @property
    def locked(self) -> bool:
        return self.store.sealed

    def put(self, kind: str, name: str, data: bytes) -> Item:
        kind, name, data = check_kind(kind), check_name(name), bytes(data)
        root = self.store.root
        item_id = new_id(root)
        at = iso(self.store.clock.now())
        payload = pack(item_id, name, kind, at, data)
        self.store.ensure_current()
        relative = body_name(item_id)
        if self.store.sealed:
            body = seal_body(public_key(read_seal(root) or {}), relative, payload)
        else:
            body = PLAIN + payload
        write_bytes_atomic(self.store.path(relative), body, keep_backup=False)
        item = Item(item_id, at, kind, len(data))
        self.store.write(meta_name(item_id), meta_record(item), keep_backup=False)
        return item

    def items(self) -> list[Item]:
        return listing(self.store.root, self.store.codec)[0]


class OpenRoom:
    def __init__(self, store, key: RoomKey | None, public: bytes | None):
        self.store = store
        self._key = key
        self.public = public

    @property
    def locked(self) -> bool:
        return self._key is not None

    @property
    def own_public(self) -> bytes | None:
        return self._key.public if self._key is not None else None

    @property
    def swapped(self) -> bool:
        return self._key is not None and self.public is not None and self._key.public != self.public

    def _open(self, item_id: str, parts: dict[str, Path]) -> tuple[Thing, bytes | None]:
        meta = None
        if "meta" in parts:
            try:
                meta = read_meta(self.store.codec, item_id, parts["meta"])
            except (TamperedFile, OSError):
                meta = None
        known = {"kind": meta.kind, "at": meta.at, "size": meta.size} if meta else {}
        if "body" not in parts:
            return Thing(item_id, problem="its contents are missing", **known), None
        relative = body_name(item_id)
        try:
            header, data = unpack(relative, open_body(self._key, relative, parts["body"].read_bytes()))
        except TamperedFile as error:
            return Thing(item_id, problem=str(error), **known), None
        if header.get("id") != item_id:
            return Thing(item_id, problem=f"{relative} belongs to another thing", **known), None
        return Thing(item_id, header.get("name"), header.get("kind"), header.get("at"), header.get("size")), data

    def things(self) -> list[Thing]:
        opened = [self._open(item_id, parts)[0] for item_id, parts in found(self.store.root).items()]
        return sorted(opened, key=lambda thing: (thing.at or "", thing.id))

    def find(self, text: str) -> str:
        wanted = "".join(str(text).split()).replace("-", "").lower()
        if len(wanted) < MIN_ID:
            raise RoomError(f"Give at least {MIN_ID} letters of the id.")
        matches = sorted(item_id for item_id in found(self.store.root) if item_id.startswith(wanted))
        if not matches:
            raise RoomError(f"Nothing in the room has the id {text}.")
        if len(matches) > 1:
            raise RoomError(f"{text} fits {len(matches)} things in the room; give more of the id.")
        return matches[0]

    def look(self, text: str) -> Thing:
        item_id = self.find(text)
        return self._open(item_id, found(self.store.root)[item_id])[0]

    def take_out(self, text: str) -> tuple[Thing, bytes]:
        item_id = self.find(text)
        thing, data = self._open(item_id, found(self.store.root)[item_id])
        if data is None:
            raise RoomError(f"{item_id} cannot be taken out: {thing.problem}.")
        return thing, data

    def delete(self, text: str) -> Thing:
        item_id = self.find(text)
        parts = found(self.store.root)[item_id]
        thing = self._open(item_id, parts)[0]
        self.store.ensure_current()
        for path in (parts.get("body"), parts.get("meta")):
            if path is not None:
                path.unlink(missing_ok=True)
        meta = self.store.path(meta_name(item_id))
        meta.with_name(meta.name + ".bak").unlink(missing_ok=True)
        if os.name == "posix":
            fd = os.open(meta.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        return thing
