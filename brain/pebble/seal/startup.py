import os
from pathlib import Path
from typing import Callable

from ..clock import Clock
from ..selfstore.atomic import TamperedFile, TornLine
from ..selfstore.codec import SealedCodec, logical
from ..selfstore.sealed import SelfIsSealed, is_sealed, read_seal
from ..selfstore.store import TEMPLATE_DIR, SelfStore
from . import locks
from .errors import SealError
from .keys import AndroidAppKeyHolder, AndroidKeystoreHolder, FileKeyHolder, KeyHolder, SelfKey, default_key_path

BLACKBOX = "logs/blackbox.jsonl"
HOLDER_ENV = "PEBBLE_KEY_HOLDER"
HOLDERS = ("file", "android", "android-app")


def key_holder(key_file: str | Path | None = None, kind: str | None = None) -> KeyHolder:
    chosen = (kind or os.environ.get(HOLDER_ENV) or "file").strip().lower()
    if chosen == "file":
        return FileKeyHolder(default_key_path(key_file))
    if chosen in ("android", AndroidKeystoreHolder.kind):
        return AndroidKeystoreHolder()
    if chosen == AndroidAppKeyHolder.kind:
        return AndroidAppKeyHolder()
    raise SealError(f"Pebble's lock is kept in a key file (file), the phone's keystore through Termux (android) or the Pebble app's keystore (android-app), not {chosen!r}.")


def recorded_holder(root: Path) -> str | None:
    try:
        seal = read_seal(Path(root))
    except SelfIsSealed:
        return None
    lock = (seal or {}).get("locks", {}).get("pebble") or {}
    return lock.get("holder") if isinstance(lock, dict) else None


def holder_for(root: Path, key_file: str | Path | None = None, kind: str | None = None) -> KeyHolder:
    if kind or key_file or os.environ.get(HOLDER_ENV):
        return key_holder(key_file, kind)
    recorded = recorded_holder(root)
    if recorded == AndroidAppKeyHolder.kind:
        return key_holder(None, AndroidAppKeyHolder.kind)
    return key_holder(None, "android" if recorded == AndroidKeystoreHolder.kind else "file")


def pebble_key(self_dir: Path, key_file: str | Path | None = None, holder: KeyHolder | None = None) -> SelfKey:
    root = Path(self_dir)
    return locks.open_pebble(locks.load(root), holder or holder_for(root, key_file), root)


def open_self(
    self_dir: Path,
    clock: Clock,
    snapshot_dir: Path | None = None,
    key_file: str | Path | None = None,
    template: Path = TEMPLATE_DIR,
    holder: KeyHolder | None = None,
) -> SelfStore:
    root = Path(self_dir)
    if not is_sealed(root):
        return SelfStore.open(root, clock, template, snapshot_dir)
    return SelfStore.open(root, clock, template, snapshot_dir, key=pebble_key(root, key_file, holder))


def line_name(self_dir: Path, path: Path) -> str:
    try:
        return logical(Path(path).resolve().relative_to(Path(self_dir).resolve()).as_posix())
    except ValueError:
        return BLACKBOX


def line_opener(self_dir: Path, path: Path | None = None, key_file: str | Path | None = None, holder: KeyHolder | None = None) -> Callable[[str], str | None]:
    root = Path(self_dir)
    if not is_sealed(root):
        return lambda text: text
    codec = SealedCodec(pebble_key(root, key_file, holder))
    name = line_name(root, path) if path is not None else BLACKBOX

    def open_line(text: str) -> str | None:
        try:
            return codec.decode_line(name, text)
        except (TamperedFile, TornLine):
            return None

    return open_line
