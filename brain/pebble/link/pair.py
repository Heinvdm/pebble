import argparse
import asyncio
import sys
import time
from pathlib import Path

from .auth import AuthError, RawKey, prove, read_key_file, write_key_file
from .serial_link import SerialTransport
from .transport import LinkClosed, TransportUnavailable

REPLY_S = 3.0


async def _answer(transport, prefixes: tuple[str, ...], timeout: float = REPLY_S) -> str:
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise AuthError("the body did not answer")
        line = (await asyncio.wait_for(transport.read_line(), left)).strip()
        if line.startswith(prefixes):
            return line


async def pair(device: str, key_file: Path, new: bool) -> str:
    key = RawKey.new() if new or not key_file.exists() else read_key_file(key_file)
    transport = SerialTransport(device)
    await transport.open()
    try:
        await transport.write_line(f"K {key.hex()}")
        answer = await _answer(transport, ("ok", "err K"))
        if answer != "ok":
            raise AuthError(f"the body refused the key ({answer}); send it over the body's own USB port")
        await prove(transport, key)
    finally:
        await transport.close()
    write_key_file(key_file, key)
    return f"Paired: the body and {key_file} now share a link key. Set {key_file} in PEBBLE_LINK_KEY_FILE for the brain on this PC."


async def check(device: str, key_file: Path) -> str:
    transport = SerialTransport(device)
    await transport.open()
    try:
        await prove(transport, read_key_file(key_file))
    finally:
        await transport.close()
    return "The body proved the key."


async def forget(device: str) -> str:
    transport = SerialTransport(device)
    await transport.open()
    try:
        await transport.write_line("K -")
        answer = await _answer(transport, ("ok", "err K"))
    finally:
        await transport.close()
    if answer != "ok":
        raise AuthError(f"the body refused ({answer})")
    return "The body forgot its link key; Wi-Fi and Bluetooth now refuse to drive it until it is paired again."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.link.pair", description="Give the body its link key over USB.")
    parser.add_argument("--serial", required=True, help="the body's USB serial port, for example COM5 or /dev/ttyACM0")
    parser.add_argument("--key-file", type=Path, default=Path.home() / ".pebble" / "link.key")
    parser.add_argument("--new", action="store_true", help="make a new key even if the key file exists")
    parser.add_argument("--check", action="store_true", help="only check that the body proves the key in the key file")
    parser.add_argument("--forget", action="store_true", help="make the body forget its key")
    args = parser.parse_args(argv)
    try:
        if args.forget:
            said = asyncio.run(forget(args.serial))
        elif args.check:
            said = asyncio.run(check(args.serial, args.key_file))
        else:
            said = asyncio.run(pair(args.serial, args.key_file, args.new))
    except (AuthError, LinkClosed, TransportUnavailable, OSError, ValueError, asyncio.TimeoutError) as error:
        print(f"Not done: {error}", file=sys.stderr)
        return 1
    print(said)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
