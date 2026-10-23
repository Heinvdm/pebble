import logging
import os
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .. import __version__
from ..clock import Clock, iso
from ..laws import LAWS
from ..owner import OwnerGrant
from .atomic import (
    TMP_SUFFIX,
    _MISSING,
    CorruptFile,
    TamperedFile,
    append_jsonl,
    backup_path,
    drop_backup,
    read_json,
    read_jsonl,
    remove_stray_temps,
    write_bytes_atomic,
    write_json_atomic,
    write_lines_atomic,
)
from .codec import PLAIN, SealedCodec, is_line_file
from .migrate import migrate
from .rotation import settle
from .sealed import (
    BIRTH,
    JOURNAL,
    PROTECTED,
    UNFINISHED,
    VALUES,
    SealedFile,
    SealUnfinished,
    SelfIsSealed,
    WrongKey,
    core_matches,
    floors_of,
    is_reserved,
    key_opens,
    open_sealed_value,
    read_seal,
)

log = logging.getLogger(__name__)

SELF_FORMAT = 3
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "self_template"
MANIFEST = "manifest.json"
CORE = "core.json"
LOCKED = frozenset({CORE})
BIRTH_FIXED = ("born", "draw", "drawn", "line", "words", "kept", "late")
SNAPSHOT_EXCLUDE = frozenset({"logs", "room"})
SNAPSHOT_KEEP = 14


class LockedFile(PermissionError):
    pass


class SelfFormatTooNew(RuntimeError):
    pass


class BadSelfPath(ValueError):
    pass


def clean_name(name: str) -> str:
    return PurePosixPath(str(name).replace("\\", "/")).as_posix()


def rule_name(name: str) -> str:
    return clean_name(name).rstrip(". ").lower()


def default_snapshot_dir(root: Path, snapshot_dir: Path | None = None) -> Path:
    root = Path(root)
    return Path(snapshot_dir) if snapshot_dir else root.parent / f"{root.name}-snapshots"


class SelfStore:
    def __init__(
        self,
        root: Path,
        clock: Clock,
        snapshot_dir: Path | None = None,
        created: bool = False,
        key: Any = None,
        frozen: dict | None = None,
    ):
        self.root = Path(root)
        self.clock = clock
        self.snapshot_dir = default_snapshot_dir(self.root, snapshot_dir)
        self.created = created
        self.codec = SealedCodec(key) if key is not None else PLAIN
        self.tampered: list[str] = []
        self._key = key
        self._frozen = frozen or {}
        self._check = None

    @classmethod
    def open(
        cls,
        root: Path,
        clock: Clock,
        template: Path = TEMPLATE_DIR,
        snapshot_dir: Path | None = None,
        key: Any = None,
    ) -> "SelfStore":
        root = Path(root)
        settle(root)
        seal = read_seal(root)
        if seal is not None:
            return cls._open_sealed(root, clock, Path(template), snapshot_dir, key, seal)
        manifest = root / MANIFEST
        created = not manifest.exists() and not backup_path(manifest).exists()
        store = cls(root, clock, snapshot_dir, created)
        if created:
            store._create(Path(template))
        else:
            store._load(Path(template))
        return store

    @classmethod
    def _open_sealed(cls, root: Path, clock: Clock, template: Path, snapshot_dir: Path | None, key: Any, seal: dict) -> "SelfStore":
        if key is None:
            raise SelfIsSealed(
                f"{root} is sealed. Open it through Pebble's lock (pebble.seal.startup.open_self), "
                "the owner's password or two recovery cards."
            )
        state = seal.get("state")
        if state in UNFINISHED:
            command = "seal" if state == "sealing" else "unseal"
            raise SealUnfinished(f"{state} {root} did not finish. Run `python -m pebble.seal {command}` again to finish it.")
        if not key_opens(seal, key):
            raise WrongKey(f"that key does not open {root}")
        store = cls(root, clock, snapshot_dir, False, key, open_sealed_value(seal, "frozen", key))
        store._check = seal.get("check")
        store._load(template)
        return store

    def _create(self, template: Path) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        remove_stray_temps(self.root)
        manifest = read_json(template / MANIFEST)
        for name in manifest["files"]:
            self._copy_from_template(template, name)
        now = self.clock.now()
        core = self.read(CORE)
        core["birthday"] = self.clock.local(now).date().isoformat()
        core["first_boot_at"] = iso(now)
        self._put(CORE, core)
        manifest["created_at"] = iso(now)
        manifest["software"] = __version__
        self._put(MANIFEST, manifest)
        log.info("created a new self at %s", self.root)

    def _load(self, template: Path) -> None:
        remove_stray_temps(self.root)
        manifest = self.read(MANIFEST)
        version = int(manifest.get("self_format", 1))
        if version > SELF_FORMAT:
            raise SelfFormatTooNew(f"self format {version} is newer than this software ({SELF_FORMAT})")
        changed = False
        if version < SELF_FORMAT:
            migrate(self, version, SELF_FORMAT)
            manifest["self_format"] = SELF_FORMAT
            changed = True
        template_manifest = read_json(template / MANIFEST)
        for name, info in template_manifest["files"].items():
            if name not in manifest.setdefault("files", {}) or not self.path(name).exists():
                if self._copy_from_template(template, name):
                    log.info("added %s from the template", name)
                manifest["files"][name] = info
                changed = True
        if manifest.get("software") != __version__:
            manifest["software"] = __version__
            changed = True
        if changed:
            self._put(MANIFEST, manifest)

    def _copy_from_template(self, template: Path, name: str) -> bool:
        target = self.path(name)
        if target.exists():
            return False
        if self.sealed and clean_name(name) == CORE:
            log.warning("%s is missing from a sealed self; the template is never copied over the frozen core", name)
            return False
        source = template / name
        if name.endswith(".json"):
            self._put(name, read_json(source), keep_backup=False)
        elif self.sealed and is_line_file(name):
            write_lines_atomic(target, read_jsonl(source), self.codec, clean_name(name))
        elif self.sealed:
            write_bytes_atomic(target, self.codec.encode(clean_name(name), source.read_bytes()), keep_backup=False)
        else:
            write_bytes_atomic(target, source.read_bytes(), keep_backup=False)
        return True

    @property
    def sealed(self) -> bool:
        return self.codec.sealed

    @property
    def access(self) -> str | None:
        return getattr(self._key, "access", None) if self.sealed else None

    @property
    def owner_lock_exists(self) -> bool:
        if not self.sealed:
            return False
        seal = read_seal(self.root)
        return bool(seal and seal["locks"].get("owner"))

    @property
    def manifest(self) -> dict:
        return self.read(MANIFEST)

    def path(self, name: str) -> Path:
        pure = PurePosixPath(name.replace("\\", "/"))
        if not name or pure.is_absolute() or any(part in ("", "..") for part in pure.parts) or ":" in name:
            raise BadSelfPath(name)
        return self.root.joinpath(*pure.parts)

    def _codec(self):
        return self.codec if self.sealed else None

    def _report(self, source: Path, reason: str) -> None:
        try:
            where = Path(source).relative_to(self.root).as_posix()
        except ValueError:
            where = str(source)
        entry = f"{where}: {reason}"
        if entry not in self.tampered:
            self.tampered.append(entry)
            log.warning("refused part of the sealed self: %s", entry)

    def _vet(self, name: str) -> Callable[[Any], str | None] | None:
        if not self.sealed or name != CORE or "core" not in self._frozen:
            return None
        frozen = self._frozen["core"]
        return lambda value: None if core_matches(value, frozen) else "differs from the core frozen at sealing"

    def read(self, name: str, default: Any = _MISSING) -> Any:
        key = clean_name(name)
        self._refuse_seal_file(key)
        return read_json(self.path(name), default, self._codec(), key, self._report, self._vet(key))

    def _still_current(self) -> None:
        if not self.sealed:
            return
        if (self.root / JOURNAL).exists():
            raise SealUnfinished(f"the key of {self.root} is being changed; open the self again once that is done")
        seal = read_seal(self.root)
        if seal is None:
            raise SelfIsSealed(f"{self.root} is no longer sealed; open it again")
        if seal.get("check") != self._check and not key_opens(seal, self._key):
            raise WrongKey(f"the key of {self.root} was changed after this store was opened; open it again")

    def ensure_current(self) -> None:
        self._still_current()

    def _put(self, name: str, data: Any, keep_backup: bool = True) -> None:
        self._still_current()
        write_json_atomic(self.path(name), data, keep_backup, self._codec(), clean_name(name))

    def _refuse_seal_file(self, name: str) -> None:
        if is_reserved(rule_name(name)):
            raise LockedFile(f"{name} belongs to the seal and never goes through the store")

    def _may_shape(self) -> bool:
        return self.access == "pebble" or (self.access == "owner" and self.owner_lock_exists)

    def _guard(self, name: str, data: Any) -> None:
        if not self.sealed:
            return
        name = rule_name(name)
        if name == CORE:
            raise SealedFile("core.json was frozen when the self was sealed")
        if name in PROTECTED and not self._may_shape():
            who = "the owner's lock was thrown away" if self.access == "owner" else f"this self was opened with {self.access}"
            raise SealedFile(f"{name} is Pebble's own now and only Pebble writes it ({who})")
        if name == VALUES and floors_of(data) != self._frozen.get("floors"):
            raise SealedFile("the honesty and kindness floors were frozen when the self was sealed")

    def _guard_birth(self, name: str, data: Any) -> None:
        if rule_name(name) != BIRTH:
            return
        try:
            before = self.read(BIRTH, None)
        except (CorruptFile, TamperedFile):
            log.warning("the birth record could not be read, so it is written afresh")
            return
        if not isinstance(before, dict):
            return
        after = data if isinstance(data, dict) else {}
        if before.get("seed") and after.get("seed") != before.get("seed"):
            raise LockedFile("Pebble's birth seed is its own and never changes")
        if before.get("born") and any(after.get(field) != before.get(field) for field in BIRTH_FIXED):
            raise LockedFile("the birth record stays as it was on Pebble's birthday")

    def write(self, name: str, data: Any, keep_backup: bool = True) -> None:
        key = clean_name(name)
        self._refuse_seal_file(key)
        if rule_name(key) in LOCKED:
            raise LockedFile(f"{name} is locked")
        self._guard(key, data)
        self._guard_birth(key, data)
        self._put(name, data, keep_backup)
        if not keep_backup:
            drop_backup(self.path(name))

    def write_locked(self, name: str, data: Any, grant: OwnerGrant) -> None:
        if not isinstance(grant, OwnerGrant):
            raise LockedFile(f"{name} needs the owner's passphrase")
        key = clean_name(name)
        self._refuse_seal_file(key)
        if rule_name(key) == CORE and not (isinstance(data, dict) and list(data.get("laws") or []) == list(LAWS)):
            raise LockedFile("the laws can never be edited")
        self._guard(key, data)
        self._guard_birth(key, data)
        self._put(name, data)

    def write_bytes(self, name: str, data: bytes, keep_backup: bool = False) -> None:
        key = clean_name(name)
        self._refuse_seal_file(key)
        if rule_name(key) in LOCKED or rule_name(key) in PROTECTED or is_line_file(key):
            raise LockedFile(f"{name} is not a plain file of its own")
        self._still_current()
        codec = self._codec()
        blob = codec.encode(key, bytes(data)) if codec is not None else bytes(data)
        write_bytes_atomic(self.path(name), blob, keep_backup)
        if not keep_backup:
            drop_backup(self.path(name))

    def read_bytes(self, name: str, default: Any = _MISSING) -> Any:
        key = clean_name(name)
        self._refuse_seal_file(key)
        path = self.path(name)
        codec = self._codec()
        for candidate in (path, backup_path(path)):
            if not candidate.exists():
                continue
            try:
                data = candidate.read_bytes()
                return codec.decode(key, data) if codec is not None else data
            except TamperedFile as error:
                self._report(candidate, str(error))
            except OSError as error:
                log.warning("unreadable %s: %s", candidate, error)
        if default is _MISSING:
            raise FileNotFoundError(str(path))
        return default

    def remove(self, name: str) -> bool:
        key = clean_name(name)
        self._refuse_seal_file(key)
        if rule_name(key) in LOCKED or rule_name(key) in PROTECTED or rule_name(key) == MANIFEST:
            raise LockedFile(f"{name} is never removed through the store")
        self._still_current()
        path = self.path(name)
        existed = path.exists()
        if existed:
            path.unlink()
        drop_backup(path)
        return existed

    def append(self, name: str, record: Any) -> None:
        key = clean_name(name)
        self._refuse_seal_file(key)
        self._still_current()
        append_jsonl(self.path(name), record, self._codec(), key)

    def rewrite_lines(self, name: str, records: list) -> None:
        key = clean_name(name)
        self._refuse_seal_file(key)
        if not is_line_file(key):
            raise LockedFile(f"{name} is not a lines file")
        self._still_current()
        write_lines_atomic(self.path(name), list(records), self._codec(), key)

    def read_lines(self, name: str, limit: int | None = None) -> list:
        key = clean_name(name)
        self._refuse_seal_file(key)
        return read_jsonl(self.path(name), limit, self._codec(), key, self._report)

    def line_sealer(self, name: str) -> Callable[[str], str]:
        key = clean_name(name)
        codec = self.codec
        return lambda text: codec.encode_line(key, text)

    def snapshot(self, keep: int = SNAPSHOT_KEEP) -> Path:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        stamp = self.clock.local().strftime("%Y%m%d-%H%M%S")
        target = self.snapshot_dir / f"self-{stamp}.zip"
        counter = 1
        while target.exists():
            target = self.snapshot_dir / f"self-{stamp}-{counter}.zip"
            counter += 1
        tmp = target.with_name(target.name + TMP_SUFFIX)
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as archive:
                for file in sorted(self.root.rglob("*")):
                    if not file.is_file():
                        continue
                    relative = file.relative_to(self.root)
                    if relative.parts[0] in SNAPSHOT_EXCLUDE or file.name.endswith(TMP_SUFFIX):
                        continue
                    if is_reserved(relative.as_posix()):
                        continue
                    archive.write(file, relative.as_posix())
            os.replace(tmp, target)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        self.prune_snapshots(keep)
        return target

    def snapshots(self) -> list[Path]:
        if not self.snapshot_dir.exists():
            return []
        return sorted(self.snapshot_dir.glob("self-*.zip"))

    def prune_snapshots(self, keep: int) -> None:
        existing = self.snapshots()
        for old in existing[: max(0, len(existing) - keep)]:
            old.unlink(missing_ok=True)
