import argparse
import asyncio
import logging
import math

from .firmware import SimFirmware
from .server import SimServer
from .world import Pose, World


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m pebble.sim", description="Simulated Pebble body speaking the firmware line protocol over TCP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--start", default="80.5,0,0", help="x_mm,y_mm,heading_deg; the default sits on the dock")
    parser.add_argument("--pack", type=float, default=3950.0, help="starting pack voltage in mV")
    return parser.parse_args(argv)


async def serve(args: argparse.Namespace) -> None:
    x, y, heading = (float(part) for part in args.start.split(","))
    firmware = SimFirmware(World(pose=Pose(x, y, math.radians(heading))), pack_mv=args.pack)
    server = SimServer(firmware, args.host, args.port)
    port = await server.start()
    print(f"Pebble sim body on tcp:{args.host}:{port} (Ctrl+C to stop)", flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        await server.stop()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(serve(parse_args(argv)))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
