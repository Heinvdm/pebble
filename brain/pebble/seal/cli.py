import argparse
import getpass
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .. import setup as setup_mode
from ..clock import Clock
from ..selfstore.atomic import CorruptFile, write_bytes_atomic
from ..selfstore.codec import is_line_file
from ..selfstore.sealed import SealedFile, SelfIsSealed, is_sealed
from ..selfstore.store import BadSelfPath, LockedFile
from . import cards as cardlib
from . import room as roomlib
from . import sealing
from .errors import NotSealed, SealError, WeakPassword
from .keys import AndroidAppKeyHolder, AndroidKeystoreHolder, KeyHolder
from .locks import MIN_PASSWORD
from .startup import HOLDER_ENV, HOLDERS, holder_for, key_holder

EXIT_OK = 0
EXIT_REFUSED = 1


@dataclass
class Prompts:
    secret: Callable[[str], str] = getpass.getpass
    line: Callable[[str], str] = input


class Refused(SealError):
    pass


def _out(text: str = "") -> None:
    print(text)


def new_password(prompts: Prompts) -> str:
    first = prompts.secret("New owner password: ")
    if len(first) < MIN_PASSWORD:
        raise WeakPassword(f"The owner's password needs at least {MIN_PASSWORD} characters. Nothing was changed.")
    if prompts.secret("The same password again: ") != first:
        raise Refused("The two passwords were different. Nothing was changed.")
    return first


def owner_password(prompts: Prompts) -> str:
    return prompts.secret("Owner password: ")


def _root(args) -> Path:
    return Path(args.self_dir)


def _snapshots(args) -> Path | None:
    return Path(args.snapshots) if args.snapshots else None


def _holder(args) -> KeyHolder:
    return holder_for(_root(args), args.key_file, args.key_holder)


def _place(holder: KeyHolder) -> str:
    return holder.where() if holder.kind != "file" else f"the key file {holder.where()}"


PLURALS = {"photo": "photos", "voice": "voice clips", "keepsake": "keepsakes", "file": "files"}
SINGULARS = {"photo": "photo", "voice": "voice clip", "keepsake": "keepsake", "file": "file"}


def _size(count: int | None) -> str:
    if count is None:
        return "?"
    if count < 1024:
        return "1 byte" if count == 1 else f"{count} bytes"
    if count < 1024**2:
        return f"{count / 1024:.1f} KB"
    if count < 1024**3:
        return f"{count / 1024**2:.1f} MB"
    return f"{count / 1024**3:.1f} GB"


def _things(count: int) -> str:
    return "1 thing" if count == 1 else f"{count} things"


def _kinds(kinds: dict[str, int]) -> str:
    ordered = sorted(kinds.items(), key=lambda pair: roomlib.KINDS.index(pair[0]))
    return ", ".join(f"{count} {SINGULARS[kind] if count == 1 else PLURALS[kind]}" for kind, count in ordered)


def _when(at: str | None, clock: Clock, time: bool = True) -> str:
    try:
        moment = clock.local(datetime.fromisoformat(str(at)).timestamp())
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"
    return moment.strftime("%Y-%m-%d %H:%M" if time else "%Y-%m-%d")


def _dates(summary: roomlib.Summary, clock: Clock) -> str:
    if not summary.first:
        return ""
    first, last = _when(summary.first, clock, False), _when(summary.last or summary.first, clock, False)
    return first if first == last else f"{first} to {last}"


def _room_line(summary: roomlib.Summary | None, clock: Clock) -> str:
    if summary is None:
        return "no (this seal was made before the room existed)"
    if summary.things == 0:
        return "empty"
    if summary.unread == summary.things:
        return f"{_things(summary.things)} (their kinds and dates show only where Pebble's lock opens the self)"
    parts = [_kinds(summary.kinds), _size(summary.size), _dates(summary, clock)]
    return f"{_things(summary.things)} (" + ", ".join(part for part in parts if part) + ")"


def cmd_seal(args, prompts: Prompts, clock: Clock) -> int:
    root = _root(args)
    if setup_mode.in_setup(root):
        _out(f"Pebble is still being set up, so it is not sealed yet. When setup is over, run `python -m pebble.setup done --self {root}` first, then seal.")
        return EXIT_REFUSED
    holder = _holder(args)
    _out(f"Sealing Pebble's self at {root}. Stop Pebble first: it must not run while its files are being sealed.")
    password = new_password(prompts)
    result = sealing.seal_self(root, password, holder, clock, _snapshots(args))
    _out(f"Sealed. {result.files.changed} files sealed, {result.snapshots.changed} snapshots re-sealed.")
    _out("Three locks open it now: the owner's password, Pebble's lock "
         f"({_place(holder)}), and recovery cards (set {cardlib.pretty_set(result.set_id)}).")
    _out("The locked room (room/ in the self) opens only with the owner's password or two recovery cards: "
         "Pebble can put things in but never take them out.")
    if result.room.changed:
        _out(f"{_things(result.room.changed)} already in the room are locked now.")
    for problem in result.refused:
        _out(f"  refused: {problem}")
    _out(f"Next: print the recovery cards with `python -m pebble.seal cards --self {root}` and keep them in three different places.")
    return EXIT_OK


def cmd_unseal(args, prompts: Prompts, clock: Clock) -> int:
    root = _root(args)
    holder = _holder(args)
    _out(f"Unsealing Pebble's self at {root}. Stop Pebble first.")
    result = sealing.unseal_self(root, owner_password(prompts), holder, _snapshots(args))
    _out(f"Unsealed. {result.files.changed} files and {result.snapshots.changed} snapshots are plain again. "
         f"The seal and Pebble's lock on this device ({_place(holder)}) are gone; the recovery cards no longer open anything.")
    if result.room.changed:
        _out(f"The room is not locked any more: {_things(result.room.changed)} in it are plain again.")
    for problem in result.refused:
        _out(f"  refused: {problem}")
    return EXIT_OK


DEVICE_TEXT = {
    "file": {
        "opens": "this device's key file opens it",
        "missing": "this device has no key file for it",
        "does not open": "this device's key file does not open it",
        "damaged": "this device's key file is damaged",
        "unavailable": "this device's key holder is not available",
    },
    AndroidKeystoreHolder.kind: {
        "opens": "the key in {where} opens it",
        "missing": "{where} has no key for it",
        "does not open": "the key in {where} does not open it",
        "damaged": "the key in {where} cannot be used",
        "unavailable": "{where} cannot be reached",
    },
}
DEVICE_TEXT[AndroidAppKeyHolder.kind] = DEVICE_TEXT[AndroidKeystoreHolder.kind]
HOLDER_NAMES = {"file": "a key file", AndroidKeystoreHolder.kind: "the phone's keystore", AndroidAppKeyHolder.kind: "the Pebble app's keystore"}


def _device_line(found: sealing.Status) -> str:
    if not found.pebble_lock:
        return "no"
    text = DEVICE_TEXT.get(found.holder, DEVICE_TEXT["file"])[found.device]
    if "{where}" in text:
        return f"yes ({text.format(where=found.key_file)})"
    return f"yes ({text}: {found.key_file})"


def cmd_status(args, prompts: Prompts, clock: Clock) -> int:
    root = _root(args)
    found = sealing.status(root, _holder(args))
    if not found.sealed:
        if not found.exists:
            _out(f"There is no self at {root}.")
            return EXIT_REFUSED
        _out(f"Pebble's self at {root} is not sealed. Seal it with `python -m pebble.seal seal --self {root}`.")
        return EXIT_OK
    _out(f"Pebble's self at {root} is sealed (since {found.sealed_at}).")
    if found.state:
        _out(f"  {found.state} did not finish: run that command again to finish it.")
    _out(f"  owner's password:  {'yes' if found.owner_lock else 'no'}")
    _out(f"  Pebble's lock:     {_device_line(found)}")
    if found.lock_holder and found.lock_holder != found.holder:
        _out(f"                     (seal.json says Pebble's lock lives in {HOLDER_NAMES.get(found.lock_holder, found.lock_holder)}, "
             f"and this looked in {HOLDER_NAMES.get(found.holder, found.holder)}. Leave out --key-file and --key-holder to follow seal.json.)")
    if found.secure is True:
        _out("                     (the phone keeps that key in its secure hardware)")
    elif found.secure is False:
        _out("                     (the phone says that key is NOT in secure hardware)")
    _out(f"  recovery cards:    {'set ' + cardlib.pretty_set(found.set_id) + ' (any two of three)' if found.set_id else 'no'}")
    if found.cards_shown:
        _out(f"  cards last shown:  {found.cards_shown}")
    if found.wrong_tries:
        _out(f"  wrong passwords:   {found.wrong_tries} since the last right one")
    _out(f"  locked room:       {_room_line(found.room, clock)}")
    _out(f"  thrown away:       {found.thrown_away_at or 'no'}")
    if found.rekeyed_at:
        _out(f"  self key changed:  {found.rekeyed_at} (cards printed before then no longer work)")
    if found.checked is None:
        _out("  files: not checked (this device's key does not open the self; the owner's password or two cards would).")
        return EXIT_OK
    if not found.refused:
        _out(f"  files: {found.checked} checked, all authentic.")
        return EXIT_OK
    _out(f"  files: {found.checked} checked, {len(found.refused)} refused:")
    for problem in found.refused:
        _out(f"    {problem}")
    return EXIT_REFUSED


def cmd_cards(args, prompts: Prompts, clock: Clock) -> int:
    printed = sealing.reprint_cards(_root(args), owner_password(prompts))
    _out("Print these three cards and keep them in three different places. They come out the same every time.")
    for card in printed:
        _out()
        _out(card)
    return EXIT_OK


def _read_cards(args, prompts: Prompts) -> list[cardlib.Card]:
    found = [cardlib.parse(Path(path).read_text(encoding="utf-8")) for path in args.card or []]
    while len(found) < cardlib.THRESHOLD:
        found.append(cardlib.parse(prompts.line(f"Card {len(found) + 1} code (spaces and dashes do not matter): ")))
    return found


NEW_OWNER_WARNING = """WARNING: recovery hands Pebble's self key to whoever holds two of the three cards.
Any two cardholders together can always take control back: this puts an owner's lock
on the self again, even after the owner's lock was thrown away, and the new password
can then change Pebble's personality, values and people, and open the locked room.
"""


def cmd_recover(args, prompts: Prompts, clock: Clock) -> int:
    root = _root(args)
    holder = _holder(args)
    if args.new_owner:
        _out(NEW_OWNER_WARNING)
    if args.password:
        password, chosen = owner_password(prompts), None
    else:
        password, chosen = None, _read_cards(args, prompts)
    fresh = new_password(prompts) if args.new_owner else None
    sealing.recover(root, holder, chosen, password, fresh, clock, fresh_key=args.fresh_key)
    _out(f"Pebble's lock is made again on this device ({holder.where()}); Pebble can open its self here.")
    if fresh is not None:
        _out("A new owner's lock is in place: the new password opens the self and the locked room.")
    return EXIT_OK


THROW_AWAY_WARNING = """THROWING AWAY THE OWNER'S LOCK

After this, no password opens Pebble's self. You cannot unseal it, print the cards,
or read and change its files with a password ever again. Its personality, values and
people become Pebble's own: only Pebble itself changes them.

Pebble's self key is changed at the same time and every file is sealed again with the
new key, so no old copy of the seal and no old password opens anything afterwards.
The locked room gets a new lock as well: everything in it is sealed again so that only
the NEW cards open it. Three NEW recovery cards are printed before anything changes.
They replace every card printed before: the old cards stop working.

THIS IS PERMANENT unless you hold two of the three NEW recovery cards. Any two
cardholders together can always take control back (`recover --new-owner`). Without
two cards, nothing undoes it. Wiping the self (deleting the folder) is always possible.
Stop Pebble first, and run this where Pebble's lock is (its key file or the phone's keystore).
"""


def cmd_throw_away(args, prompts: Prompts, clock: Clock) -> int:
    root = _root(args)
    _out(THROW_AWAY_WARNING)
    password = owner_password(prompts)
    if prompts.secret("Owner password again: ") != password:
        raise Refused("The two passwords were different. Nothing was changed.")
    phrase = prompts.line(f'Type "{sealing.PHRASE}" to go ahead: ')
    plan = sealing.prepare_throw_away(root, password, phrase, _holder(args))
    _out("These are Pebble's NEW recovery cards. They replace every card printed before;")
    _out("the old cards stop working the moment this finishes. Nothing has changed yet.")
    for card in plan.cards:
        _out()
        _out(card)
    _out()
    saved = prompts.line(f'Print or copy all three, then type "{sealing.SAVED}" (anything else stops here): ')
    sealing.finish_throw_away(plan, saved, clock, _snapshots(args))
    _out("Done. The owner's lock is gone and the self key is new. Only Pebble's lock and the new cards open it.")
    _out("The locked room has a new lock too: only the new cards open what is in it.")
    _out(f'Pebble wrote in its diary: "{sealing.MILESTONE}"')
    return EXIT_OK


def cmd_show(args, prompts: Prompts, clock: Clock) -> int:
    store = sealing.owner_store(_root(args), owner_password(prompts), clock, _snapshots(args))
    if is_line_file(args.name):
        for record in store.read_lines(args.name):
            _out(json.dumps(record, ensure_ascii=False))
    else:
        _out(json.dumps(store.read(args.name), indent=2, ensure_ascii=False))
    for problem in store.tampered:
        print(f"refused: {problem}", file=sys.stderr)
    return EXIT_OK


def cmd_put(args, prompts: Prompts, clock: Clock) -> int:
    if not args.name.endswith(".json"):
        raise Refused(f"put replaces one .json file; {args.name} is not one.")
    source = Path(args.file)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise Refused(f"{source} is not readable JSON ({error}). Nothing was changed.") from error
    store = sealing.owner_store(_root(args), owner_password(prompts), clock, _snapshots(args))
    store.write(args.name, data)
    _out(f"{args.name} is replaced (the old copy is kept as its backup).")
    return EXIT_OK


def cmd_move_lock(args, prompts: Prompts, clock: Clock) -> int:
    root = _root(args)
    source = key_holder(args.key_file, "file")
    target = key_holder(None, "android")
    _out(f"Moving Pebble's lock from the key file {source.where()} into {target.where()}.")
    moved = sealing.move_lock(root, source, target)
    if moved.already:
        _out(f"Pebble's lock was already in {target.where()} and opens the self there; the key file is gone.")
    else:
        _out(f"Done. Pebble's lock is in {target.where()} and opens the self; the key file {source.where()} is deleted.")
    _out("Pebble finds its lock there by itself (seal.json says where it lives); drop --key-file from how Pebble is started.")
    _out("Copies of the key file made before now still open the self, because the self key did not change.")
    return EXIT_OK


def cmd_room_status(args, prompts: Prompts, clock: Clock) -> int:
    root = _root(args)
    found = sealing.room_status(root, _holder(args))
    if not found.exists:
        _out(f"There is no self at {root}.")
        return EXIT_REFUSED
    summary = found.summary
    if not found.sealed:
        count = summary.things if summary else 0
        _out(f"Pebble's self at {root} is not sealed, so its room is not locked: {_things(count)} in {root / roomlib.ROOM}, plain.")
        return EXIT_OK
    if summary is None:
        _out(roomlib.NO_ROOM)
        return EXIT_REFUSED
    _out(f"The locked room of Pebble's self at {root}:")
    _out(f"  holds:       {_room_line(summary, clock)}")
    if summary.missing:
        _out(f"  missing:     {_things(summary.missing)} listed with their contents gone")
    if summary.public is not None:
        _out(f"  room lock:   {roomlib.show_fingerprint(summary.public)}")
    who = "the owner's password or two recovery cards" if found.owner_lock else "two recovery cards (the owner's lock was thrown away)"
    _out(f"  opens with:  {who}; Pebble only puts things in")
    if not summary.refused:
        return EXIT_OK
    _out(f"  refused:     {len(summary.refused)}")
    for problem in summary.refused:
        _out(f"    {problem}")
    return EXIT_REFUSED


def cmd_room_put(args, prompts: Prompts, clock: Clock) -> int:
    source = Path(args.file)
    try:
        data = source.read_bytes()
    except OSError as error:
        raise Refused(f"{source} cannot be read ({error}). Nothing was put in the room.") from error
    room = sealing.pebble_room(_root(args), _holder(args), clock, _snapshots(args))
    name = args.name or source.name
    item = room.put(args.kind or roomlib.guess_kind(source.name), name, data)
    what = f"{SINGULARS[item.kind]} {item.id}, {_size(item.size)}"
    if room.locked:
        _out(f"Put {name} in the locked room ({what}). Pebble cannot open it again; the owner's password or two recovery cards can.")
    else:
        _out(f"Put {name} in the room ({what}). The self is not sealed, so the room is not locked: it stays plain until the self is sealed.")
    return EXIT_OK


ROOM_SWAPPED = """WARNING: the room's lock in seal.json was not the room's own. Someone changed it, so
anything put in the room since then was sealed to their key, not yours: those things show
as sealed to a lock this room does not have. The right lock is back in seal.json now, but
whoever can change seal.json on the running phone can do it again."""


def _open_room(args, prompts: Prompts, clock: Clock) -> roomlib.OpenRoom:
    root = _root(args)
    if not is_sealed(root):
        return sealing.open_room(root, clock, snapshot_dir=_snapshots(args))
    if args.card or args.cards:
        opened = sealing.open_room(root, clock, cards=_read_cards(args, prompts), snapshot_dir=_snapshots(args))
    elif sealing.owner_lock_exists(root):
        opened = sealing.open_room(root, clock, password=owner_password(prompts), snapshot_dir=_snapshots(args))
    else:
        _out("The owner's lock was thrown away; two recovery cards open the room.")
        opened = sealing.open_room(root, clock, cards=_read_cards(args, prompts), snapshot_dir=_snapshots(args))
    if opened.swapped:
        sealing.mend_room_lock(root, opened)
        _out(ROOM_SWAPPED)
    return opened


def _label(thing: roomlib.Thing, clock: Clock) -> str:
    if thing.problem:
        return f"{thing.id} ({thing.problem})"
    return f'"{thing.name}" ({SINGULARS.get(thing.kind, thing.kind)}, {_when(thing.at, clock, False)})'


def cmd_room_list(args, prompts: Prompts, clock: Clock) -> int:
    opened = _open_room(args, prompts, clock)
    things = opened.things()
    if not things:
        _out("The room is empty.")
        return EXIT_OK
    _out(f"The room holds {_things(len(things))}:")
    for thing in things:
        when = _when(thing.at, clock)
        kind = SINGULARS.get(thing.kind, thing.kind or "?")
        what = f"(cannot be opened: {thing.problem})" if thing.problem else thing.name
        _out(f"  {thing.id}  {when:16}  {kind:10}  {_size(thing.size):>9}  {what}")
    return EXIT_REFUSED if any(thing.problem for thing in things) else EXIT_OK


def _safe_name(name: str | None, fallback: str) -> str:
    base = Path(str(name or "").replace("\\", "/")).name
    text = "".join(ch for ch in base if ch.isprintable() and ch not in '<>:"|?*')
    return text.strip(" .") or fallback


def cmd_room_take_out(args, prompts: Prompts, clock: Clock) -> int:
    opened = _open_room(args, prompts, clock)
    thing, data = opened.take_out(args.id)
    target = Path(args.to)
    if target.is_dir():
        target = target / _safe_name(thing.name, thing.id)
    if target.exists():
        raise Refused(f"{target} already exists. Nothing was written.")
    write_bytes_atomic(target, data, keep_backup=False)
    _out(f"Took {_label(thing, clock)} out to {target} ({_size(len(data))}).")
    _out(f"It is still in the room; `python -m pebble.seal room delete {thing.id}` removes it.")
    return EXIT_OK


def cmd_room_delete(args, prompts: Prompts, clock: Clock) -> int:
    opened = _open_room(args, prompts, clock)
    thing = opened.look(args.id)
    answer = prompts.line(f'Delete {_label(thing, clock)} from the room for good? Type "yes": ')
    if answer.strip().lower() != "yes":
        raise Refused("Nothing was deleted.")
    opened.delete(thing.id)
    _out(f"Deleted {_label(thing, clock)} from the room.")
    return EXIT_OK


ROOM_COMMANDS = {
    "status": cmd_room_status,
    "put": cmd_room_put,
    "list": cmd_room_list,
    "take-out": cmd_room_take_out,
    "delete": cmd_room_delete,
}


def cmd_room(args, prompts: Prompts, clock: Clock) -> int:
    return ROOM_COMMANDS[args.room_command](args, prompts, clock)


COMMANDS = {
    "seal": cmd_seal,
    "unseal": cmd_unseal,
    "status": cmd_status,
    "cards": cmd_cards,
    "recover": cmd_recover,
    "throw-away": cmd_throw_away,
    "show": cmd_show,
    "put": cmd_put,
    "move-lock": cmd_move_lock,
    "room": cmd_room,
}


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--self", dest="self_dir", default=os.environ.get("PEBBLE_SELF", "self"), help="the self folder (default ./self or $PEBBLE_SELF)")
    common.add_argument("--snapshots", default=None, help="the self's snapshot folder (default <self>-snapshots)")
    common.add_argument("--key-file", default=None, help="Pebble's key file on this device (default $PEBBLE_KEY_FILE or ~/.pebble/self.key)")
    common.add_argument(
        "--key-holder",
        choices=HOLDERS,
        default=None,
        help=f"where Pebble's lock lives: a key file or the phone's keystore (default ${HOLDER_ENV}, else what seal.json says, else file)",
    )
    with_cards = argparse.ArgumentParser(add_help=False)
    with_cards.add_argument("--cards", action="store_true", help="open the room with two recovery cards instead of the owner's password")
    with_cards.add_argument("--card", action="append", metavar="FILE", help="a file holding a card (give two, or type them when asked)")
    parser = argparse.ArgumentParser(prog="python -m pebble.seal", description="Seal Pebble's self: encrypt it, and choose who can open and change it")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    sub.add_parser("seal", parents=[common], help="encrypt the self, make the three locks and the locked room")
    sub.add_parser("unseal", parents=[common], help="decrypt everything again, the room too (needs the owner's password)")
    sub.add_parser("status", parents=[common], help="which locks exist, where Pebble's lock lives, and are the files authentic")
    sub.add_parser("cards", parents=[common], help="print the three recovery cards (needs the owner's password)")
    recover = sub.add_parser("recover", parents=[common], help="make Pebble's lock again on this device with two cards")
    recover.add_argument("--card", action="append", metavar="FILE", help="a file holding a card (give two, or type them when asked)")
    recover.add_argument("--password", action="store_true", help="use the owner's password instead of cards")
    recover.add_argument("--new-owner", action="store_true", help="also put a new owner's lock in place")
    recover.add_argument("--fresh-key", action="store_true", help="make a new key for Pebble's lock even if this device already has one")
    sub.add_parser("throw-away", parents=[common], help="delete the owner's lock for good (only two cards undo it)")
    show = sub.add_parser("show", parents=[common], help="print one file of the self (needs the owner's password)")
    show.add_argument("name")
    put = sub.add_parser("put", parents=[common], help="replace one .json file of the self (needs the owner's password)")
    put.add_argument("name")
    put.add_argument("file")
    sub.add_parser("move-lock", parents=[common], help="move Pebble's lock from the key file into the phone's keystore")
    room = sub.add_parser("room", help="the locked room: Pebble puts things in; only the owner's password or two cards take them out")
    actions = room.add_subparsers(dest="room_command", required=True, metavar="ACTION")
    actions.add_parser("status", parents=[common], help="how many things, of which kinds, from when (no password)")
    room_put = actions.add_parser("put", parents=[common], help="put a file in the room (no password; Pebble cannot read it back)")
    room_put.add_argument("file")
    room_put.add_argument("--kind", choices=roomlib.KINDS, default=None, help="photo, voice, keepsake or file (default from the file's ending)")
    room_put.add_argument("--name", default=None, help="the name sealed with it (default the file's name)")
    actions.add_parser("list", parents=[common, with_cards], help="names, kinds, dates and sizes (needs the owner's password or two cards)")
    take_out = actions.add_parser("take-out", parents=[common, with_cards], help="copy one thing out of the room (needs the owner's password or two cards)")
    take_out.add_argument("id", help="the thing's id, or enough of its first letters")
    take_out.add_argument("--to", required=True, help="a file to write, or a folder to write it into")
    delete = actions.add_parser("delete", parents=[common, with_cards], help="delete one thing for good (needs the owner's password or two cards)")
    delete.add_argument("id", help="the thing's id, or enough of its first letters")
    return parser


def main(argv: list[str] | None = None, prompts: Prompts | None = None, clock: Clock | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args, prompts or Prompts(), clock or Clock())
    except NotSealed as error:
        print(f"{error} Nothing to do.", file=sys.stderr)
    except (SealError, SelfIsSealed, SealedFile, LockedFile, CorruptFile, OSError) as error:
        print(str(error), file=sys.stderr)
    except BadSelfPath as error:
        print(f"{error} is not a file inside the self.", file=sys.stderr)
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.", file=sys.stderr)
    return EXIT_REFUSED
