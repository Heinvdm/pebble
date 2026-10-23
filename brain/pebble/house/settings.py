import argparse
import copy
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

from ..clock import Clock, iso
from ..owner import gate_for
from ..selfstore import SelfIsSealed, SelfStore
from .almanac import TOWNS, town
from .book import HouseBook

EXIT_OK = 0
EXIT_REFUSED = 2
SECURITY = ("WPA", "WEP", "nopass")
INBOX = "house-settings"
KNOWN = ("town", "lat", "lon", "wifi", "children_arrivals", "guardians", "cooking_watch")


class Refused(Exception):
    pass


def _password_opens(store, password: str | None) -> bool:
    if not password or not getattr(store, "sealed", False) or not getattr(store, "owner_lock_exists", False):
        return False
    from ..seal import locks
    from ..seal.errors import SealError
    from ..selfstore.sealed import read_seal

    try:
        locks.open_owner(read_seal(store.root), str(password), Path(store.root))
    except (SealError, KeyError, TypeError, ValueError):
        return False
    return True


def owner_ok(store, passphrase: str | None = None, password: str | None = None) -> bool:
    gate = gate_for(store)
    if not gate.is_set():
        return True
    if passphrase is not None and gate.verify(passphrase) is not None:
        return True
    return _password_opens(store, password)


def _refusal(password: str | None) -> Refused:
    if password:
        return Refused("only the owner can change this, and the owner's password did not open the self")
    return Refused("only the owner can change this, and the passphrase did not match")


def people_in(store) -> list:
    data = store.read("people.json", {}) or {}
    return [(p.get("id"), list(p.get("names") or [])) for p in data.get("people") or [] if isinstance(p, dict)]


def shown(book: HouseBook) -> dict:
    settings = book.settings
    return {"place": book["place"], "guest_wifi": bool(book["guest_wifi"]), "children_arrivals": settings["children_arrivals"], "guardians": len(settings["guardians"]), "cooking_watch": settings["cooking_watch"]}


def change(store, passphrase: str | None, book: HouseBook | None = None, password: str | None = None, **changes) -> dict:
    if not owner_ok(store, passphrase, password):
        raise _refusal(password)
    book = book if book is not None else HouseBook(store)
    people = people_in(store)
    tried(book, people, **changes)
    apply(book, people, **changes)
    book.touch()
    book.save(force=True)
    return shown(book)


def apply(book: HouseBook, people: list, **changes) -> dict:
    settings = book.settings
    if "town" in changes or "lat" in changes:
        name = changes.get("town")
        if name:
            found = town(name)
            if found is None:
                raise Refused(f"I don't know a town called {name}; give the latitude and longitude instead")
            lat, lon = found
        else:
            lat, lon = float(changes["lat"]), float(changes["lon"])
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                raise Refused("that latitude and longitude are not on Earth")
        book["place"] = {"lat": round(lat, 2), "lon": round(lon, 2), "name": (name or "").strip().title()}
    if "wifi" in changes:
        wifi = changes["wifi"]
        if wifi is None:
            book["guest_wifi"] = None
        else:
            security = wifi.get("security") or ("WPA" if wifi.get("password") else "nopass")
            if security not in SECURITY:
                raise Refused(f"security must be one of {', '.join(SECURITY)}")
            book["guest_wifi"] = {"ssid": str(wifi["ssid"])[:32], "password": str(wifi.get("password") or "")[:63], "security": security}
    if "children_arrivals" in changes:
        settings["children_arrivals"] = bool(changes["children_arrivals"])
        found = []
        for wanted in changes.get("guardians") or []:
            match = next((pid for pid, names in people if str(wanted).lower() in [str(n).lower() for n in names]), None)
            if match is None:
                raise Refused(f"I haven't met anyone called {wanted}")
            found.append(match)
        settings["guardians"] = found
    if "cooking_watch" in changes:
        settings["cooking_watch"] = bool(changes["cooking_watch"])
    return shown(book)


def tried(book: HouseBook, people: list, **changes) -> dict:
    trial = HouseBook(None, data=copy.deepcopy(book.data))
    return apply(trial, people, **changes)


def send(store, passphrase: str | None = None, password: str | None = None, tsunami: bool | None = None, **changes) -> dict:
    if not owner_ok(store, passphrase, password):
        raise _refusal(password)
    wanted = {key: changes[key] for key in KNOWN if key in changes}
    result = tried(HouseBook(store), people_in(store), **wanted)
    if not wanted and tsunami is None:
        return dict(result, waiting=False)
    clock = getattr(store, "clock", None) or Clock()
    now = clock.now()
    name = f"{INBOX}/{int(now * 1000):014d}-{secrets.token_hex(4)}.json"
    store.write(name, {"format": 1, "at": iso(now), "changes": wanted, "tsunami": None if tsunami is None else bool(tsunami)}, keep_backup=False)
    if tsunami is not None:
        result["tsunami_zone"] = bool(tsunami)
    return dict(result, waiting=True)


def waiting(store) -> list[str]:
    folder = store.path(INBOX)
    if not folder.is_dir():
        return []
    return sorted(f"{INBOX}/{item.name}" for item in folder.iterdir() if item.is_file() and item.name.endswith(".json") and not item.name.startswith("."))


def drop(store, name: str) -> None:
    path = store.path(name)
    path.unlink(missing_ok=True)
    path.with_name(path.name + ".bak").unlink(missing_ok=True)


def light_store(self_dir, clock: Clock | None = None, holder=None) -> SelfStore:
    from ..selfstore.sealed import open_sealed_value, read_seal

    root = Path(self_dir)
    clock = clock or Clock()
    seal = read_seal(root)
    if seal is None:
        return SelfStore(root, clock)
    from ..seal.startup import pebble_key

    key = pebble_key(root, holder=holder)
    return SelfStore(root, clock, key=key, frozen=open_sealed_value(seal, "frozen", key))


def _answer(ok: bool, message: str, **extra) -> str:
    return json.dumps({"ok": ok, "message": message, **extra})


def post(self_dir: str, passphrase: str = "", password: str = "", changes_json: str = "{}", holder=None) -> str:
    try:
        wanted = json.loads(str(changes_json) or "{}")
    except ValueError:
        return _answer(False, "The settings could not be read.")
    if not isinstance(wanted, dict):
        return _answer(False, "The settings could not be read.")
    tsunami = wanted.pop("tsunami", None)
    changes = {key: wanted[key] for key in KNOWN if key in wanted}
    try:
        store = light_store(self_dir, holder=holder)
        result = send(store, passphrase or None, password or None, None if tsunami is None else bool(tsunami), **changes)
    except Refused as error:
        return _answer(False, str(error))
    except (KeyError, TypeError, ValueError) as error:
        return _answer(False, f"That setting is not right: {error}")
    except Exception as error:
        return _answer(False, str(error))
    if not result.pop("waiting"):
        return _answer(True, "Nothing to change.", house=result)
    return _answer(True, "Sent. Pebble takes them within a few seconds while it runs, or when it next starts.", house=result)


def pending(self_dir: str) -> int:
    return len(waiting(SelfStore(Path(self_dir), Clock())))


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--self", dest="self_dir", default=os.environ.get("PEBBLE_SELF", "self"), help="the self folder (default ./self or $PEBBLE_SELF)")
    parser = argparse.ArgumentParser(prog="python -m pebble.house", description="The household pack's few settings, kept sealed in Pebble's self")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    sub.add_parser("status", parents=[common], help="show what is set")
    place = sub.add_parser("place", parents=[common], help="where home is, for sunrise and sunset (a New Zealand town, or a latitude and longitude)")
    place.add_argument("--town", choices=sorted(TOWNS), default=None)
    place.add_argument("--lat", type=float, default=None)
    place.add_argument("--lon", type=float, default=None)
    wifi = sub.add_parser("guest-wifi", parents=[common], help="the guest network Pebble can show as a code (never the main one); the password is asked for, not typed on the command line")
    wifi.add_argument("--ssid", default=None)
    wifi.add_argument("--security", choices=SECURITY, default=None)
    wifi.add_argument("--off", action="store_true", help="forget the guest network")
    kids = sub.add_parser("children-arrivals", parents=[common], help="tell a child's grown-ups when the child gets home (off unless the owner turns it on)")
    kids.add_argument("answer", choices=("on", "off"))
    kids.add_argument("--guardian", action="append", default=[], help="a name Pebble knows, besides the owner (repeat for more)")
    cooking = sub.add_parser("cooking-watch", parents=[common], help="mention cooking that goes on with nobody in the kitchen (on unless turned off)")
    cooking.add_argument("answer", choices=("on", "off"))
    return parser


def main(argv: list[str] | None = None, clock: Clock | None = None, ask=getpass.getpass) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.self_dir)
    if not root.exists():
        print(f"There is no self at {root}.", file=sys.stderr)
        return EXIT_OK
    try:
        store = SelfStore.open(root, clock or Clock())
    except SelfIsSealed:
        print("The self is sealed, so these can only be changed while Pebble runs, from the app.", file=sys.stderr)
        return EXIT_REFUSED
    if args.command == "status":
        book = HouseBook(store)
        place = book["place"]
        print(f"Home: {place.get('name') or 'set by latitude and longitude'}" if place else "Home: not set, so Pebble can't work out sunrise and sunset.")
        print(f"Guest Wi-Fi: {'set' if book['guest_wifi'] else 'not set'}")
        print(f"Children's arrivals told to their grown-ups: {'on' if book.settings['children_arrivals'] else 'off'}")
        print(f"Cooking watch: {'on' if book.settings['cooking_watch'] else 'off'}")
        return EXIT_OK
    changes: dict = {}
    if args.command == "place":
        if args.town:
            changes["town"] = args.town
        elif args.lat is not None and args.lon is not None:
            changes.update(lat=args.lat, lon=args.lon)
        else:
            print("Give --town, or both --lat and --lon.", file=sys.stderr)
            return EXIT_REFUSED
    elif args.command == "guest-wifi":
        if args.off:
            changes["wifi"] = None
        elif not args.ssid:
            print("Give --ssid (the guest network's name), or --off.", file=sys.stderr)
            return EXIT_REFUSED
        else:
            password = "" if args.security == "nopass" else ask("Guest network password (leave empty for an open network): ")
            changes["wifi"] = {"ssid": args.ssid, "password": password, "security": args.security}
    elif args.command == "children-arrivals":
        changes.update(children_arrivals=args.answer == "on", guardians=args.guardian)
    elif args.command == "cooking-watch":
        changes["cooking_watch"] = args.answer == "on"
    print("Stop Pebble first, or change this from the app while it runs; a running Pebble keeps its own copy.")
    passphrase = ask("Owner passphrase: ") if gate_for(store).is_set() else None
    try:
        result = change(store, passphrase, **changes)
    except Refused as error:
        print(str(error), file=sys.stderr)
        return EXIT_REFUSED
    print(f"Saved. {result}")
    return EXIT_OK
