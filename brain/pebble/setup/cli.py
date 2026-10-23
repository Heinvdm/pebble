import argparse
import getpass
import os
import sys
from pathlib import Path

from ..clock import Clock
from ..owner import gate_for
from ..self.birth import preview
from ..selfstore import SelfIsSealed, SelfStore
from . import Setup, SetupRefused, birth_draw, finish, may_draw_again, set_tsunami_zone, tsunami_zone

EXIT_OK = 0
EXIT_REFUSED = 2
TSUNAMI_QUESTION = "Is this house in a tsunami zone, near the coast? If you say yes, after a long or strong earthquake Pebble repeats Civil Defence's advice: long or strong, get gone. (yes/no) "
YES = frozenset({"y", "yes", "yeah", "yep", "ja", "true"})
NO = frozenset({"n", "no", "nope", "nah", "false"})


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--self", dest="self_dir", default=os.environ.get("PEBBLE_SELF", "self"), help="the self folder (default ./self or $PEBBLE_SELF)")
    parser = argparse.ArgumentParser(prog="python -m pebble.setup", description="Pebble starts life in setup mode while it is built and tested; only the owner ends it")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    sub.add_parser("status", parents=[common], help="is Pebble still being set up, and since when")
    sub.add_parser("done", parents=[common], help="end setup: Pebble wakes up for real today (needs the owner's passphrase once one is set)")
    tsunami = sub.add_parser("tsunami", parents=[common], help="say whether the house is in a tsunami zone (yes or no), or show the answer")
    tsunami.add_argument("answer", nargs="?", choices=("yes", "no"), help="yes turns on the 'long or strong, get gone' line after big earthquakes")
    born = sub.add_parser("draw", parents=[common], help="see what Pebble would be born like; while it is being set up, --again draws again (owner only)")
    born.add_argument("--again", action="store_true", help="draw again from Pebble's own seed; only while it is being set up")
    return parser


def _open(root: Path, clock: Clock) -> SelfStore | None:
    if not root.exists():
        print(f"There is no self at {root}.", file=sys.stderr)
        return None
    try:
        return SelfStore.open(root, clock)
    except SelfIsSealed:
        print("The self is sealed, and a self is only sealed after setup, so setup is already over.")
        return None


def cmd_status(args, clock: Clock, ask, answer=input) -> int:
    store = _open(Path(args.self_dir), clock)
    if store is None:
        return EXIT_OK
    setup = Setup.load(store)
    if setup.on:
        print(f"Pebble is being set up (since {setup.since or 'its first start'}). End it with `python -m pebble.setup done --self {args.self_dir}`.")
    elif setup.born:
        print(f"Setup is over. Pebble woke up for real on {setup.born}.")
    else:
        print("This self has no setup record, so it is not in setup mode.")
    print(_born_words(preview(store)))
    print(_tsunami_words(tsunami_zone(store)))
    return EXIT_OK


def _born_words(found: dict) -> str:
    if found.get("born"):
        return f"Born on {found['born']} (draw {found.get('draw')}): \"{found.get('line', '')}\" That draw is its own now."
    return f"If it were born now (draw {found.get('draw')}): \"{found.get('line', '')}\""


def cmd_draw(args, clock: Clock, ask, answer=input) -> int:
    store = _open(Path(args.self_dir), clock)
    if store is None:
        return EXIT_OK
    passphrase = ask("Owner passphrase: ") if args.again and may_draw_again(store) and gate_for(store).is_set() else None
    found = birth_draw(args.self_dir, args.again, passphrase, clock)
    if not found["ok"]:
        print(f"{found['error'][0].upper()}{found['error'][1:]}.", file=sys.stderr)
        return EXIT_REFUSED
    print(_born_words(found))
    return EXIT_OK


def _tsunami_words(value: bool | None) -> str:
    if value is None:
        return "Tsunami zone: not answered yet, so the 'long or strong, get gone' line is off."
    return "Tsunami zone: yes, so Pebble says 'long or strong, get gone' after a long or strong earthquake." if value else "Tsunami zone: no, so the 'long or strong, get gone' line is off."


def _yes_no(reply: str | None) -> bool | None:
    word = (reply or "").strip().lower().rstrip(".!")
    if word in YES:
        return True
    if word in NO:
        return False
    return None


def _ask_tsunami(store, answer, self_dir: str) -> None:
    if tsunami_zone(store) is not None:
        return
    try:
        reply = answer(TSUNAMI_QUESTION)
    except (EOFError, OSError):
        reply = None
    value = _yes_no(reply)
    if value is None:
        print(f"I'll leave the tsunami line off. Set it any time with `python -m pebble.setup tsunami yes --self {self_dir}`.")
        return
    set_tsunami_zone(store, value)
    print(_tsunami_words(value))


def cmd_done(args, clock: Clock, ask, answer=input) -> int:
    store = _open(Path(args.self_dir), clock)
    if store is None:
        return EXIT_OK
    if not Setup.load(store).on:
        print("Setup is already over. Nothing to do.")
        return EXIT_OK
    print("Stop Pebble first, or end setup from the app while it runs.")
    passphrase = ask("Owner passphrase: ") if gate_for(store).is_set() else None
    try:
        setup = finish(store, clock, passphrase)
    except SetupRefused as error:
        print(str(error), file=sys.stderr)
        return EXIT_REFUSED
    print(f"Setup is over. Pebble wakes up for real today ({setup.born}); that is its birthday now.")
    _ask_tsunami(store, answer, args.self_dir)
    print(f"Next, when you are ready: seal it with `python -m pebble.seal seal --self {args.self_dir}`.")
    return EXIT_OK


def cmd_tsunami(args, clock: Clock, ask, answer=input) -> int:
    root = Path(args.self_dir)
    if not root.exists():
        print(f"There is no self at {root}.", file=sys.stderr)
        return EXIT_OK
    try:
        store = SelfStore.open(root, clock)
    except SelfIsSealed:
        print("The self is sealed, so this can only be changed while Pebble runs.", file=sys.stderr)
        return EXIT_REFUSED
    if args.answer is None:
        print(_tsunami_words(tsunami_zone(store)))
        return EXIT_OK
    gate = gate_for(store)
    if gate.is_set() and gate.verify(ask("Owner passphrase: ")) is None:
        print("Only the owner can change this, and the passphrase did not match.", file=sys.stderr)
        return EXIT_REFUSED
    set_tsunami_zone(store, args.answer == "yes")
    print(_tsunami_words(args.answer == "yes"))
    return EXIT_OK


COMMANDS = {"status": cmd_status, "done": cmd_done, "tsunami": cmd_tsunami, "draw": cmd_draw}


def main(argv: list[str] | None = None, clock: Clock | None = None, ask=getpass.getpass, answer=input) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args, clock or Clock(), ask, answer)
