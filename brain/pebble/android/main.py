import asyncio
import logging
import logging.handlers
import os
import threading
import time
from pathlib import Path

from .. import app
from . import bridge as bridges

log = logging.getLogger("pebble.android")

HEARTBEAT_S = 5.0
LOGCAT_LEVEL = logging.WARNING
LOG_BYTES = 1_000_000
LOG_KEEP = 2
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

_lock = threading.Lock()
_running: dict = {}


def run(argv, bridge=None, heartbeat: str | None = None, log_file: str | None = None) -> int:
    words = [str(word) for word in argv]
    if bridge is not None:
        bridges.install(bridge)
    args = app.build_parser().parse_args(words)
    setup_logging(args.log_level, Path(log_file) if log_file else None)
    log.info("brain starting on Android: %s", " ".join(words))
    try:
        return asyncio.run(_life(args, Path(heartbeat) if heartbeat else None))
    except KeyboardInterrupt:
        return app.EXIT_OK


async def _life(args, heartbeat: Path | None) -> int:
    stop = asyncio.Event()
    with _lock:
        _running.update(loop=asyncio.get_running_loop(), stop=stop)
    beat = asyncio.create_task(_beat(heartbeat), name="pebble-heartbeat") if heartbeat is not None else None
    sentences = bridges.sentences()
    chosen = app.embedder_from
    if sentences is not None:
        app.embedder_from = _phone_first(sentences, chosen)
    try:
        return await app.run(args, stop)
    finally:
        app.embedder_from = chosen
        if sentences is not None:
            sentences.close()
        if beat is not None:
            beat.cancel()
            await asyncio.gather(beat, return_exceptions=True)
        with _lock:
            _running.clear()


def _phone_first(sentences, chosen):
    def embedder_from(kind: str = "auto", *rest):
        return sentences if kind == "auto" else chosen(kind, *rest)

    return embedder_from


async def _beat(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(f"{time.time():.3f} {os.getpid()}\n", encoding="ascii")
            os.replace(tmp, path)
        except OSError as error:
            log.warning("heartbeat could not be written: %s", error)
        await asyncio.sleep(HEARTBEAT_S)


def stop() -> bool:
    with _lock:
        loop, event = _running.get("loop"), _running.get("stop")
    if loop is None or event is None or loop.is_closed():
        return False
    try:
        loop.call_soon_threadsafe(event.set)
    except RuntimeError:
        return False
    return True


def setup_logging(level: str, log_file: Path | None) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    if any(getattr(handler, "pebble_android", False) for handler in root.handlers):
        return
    logcat = logging.StreamHandler()
    logcat.setLevel(LOGCAT_LEVEL)
    handlers: list[logging.Handler] = [logcat]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(log_file, maxBytes=LOG_BYTES, backupCount=LOG_KEEP, encoding="utf-8"))
    for handler in handlers:
        handler.setFormatter(logging.Formatter(FORMAT))
        handler.pebble_android = True
        root.addHandler(handler)
