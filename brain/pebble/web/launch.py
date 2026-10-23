import asyncio
import logging
import signal
from pathlib import Path
from typing import Callable

from ..chaos.engine import Chaos
from ..clock import Clock
from ..eyes import close_eyes, eyes_from_config
from ..screen.gallery import GALLERY, Gallery
from ..screen.stage import SceneStage
from ..seams.face import Touch
from ..selfstore import CorruptFile, is_sealed, read_json
from .demo import LEVELS, Demo
from .eyes import BrowserEyes
from .hub import Hub
from .server import FaceServer
from .webface import WebFace

log = logging.getLogger(__name__)

DEMO_LEVEL = 5.0


def start_face_server(
    hub: Hub,
    host: str,
    port: int,
    on_touch: Callable[[Touch], None],
    state: Callable[[], dict],
    eyes: BrowserEyes | None = None,
    routes: dict | None = None,
    on_pad: Callable[[dict], None] | None = None,
) -> FaceServer:
    server = FaceServer(hub, host, port, on_touch, state, eyes=eyes, routes=routes, on_pad=on_pad)
    try:
        server.start()
    except OSError as error:
        if port == 0:
            raise
        log.warning("face page port %s is taken (%s); using a free one instead", port, error)
        server = FaceServer(hub, host, 0, on_touch, state, eyes=eyes, routes=routes, on_pad=on_pad)
        server.start()
    return server


def threadsafe(loop: asyncio.AbstractEventLoop, handler: Callable[[Touch], None]) -> Callable[[Touch], None]:
    def forward(touch: Touch) -> None:
        try:
            loop.call_soon_threadsafe(handler, touch)
        except RuntimeError:
            pass

    return forward


def demo_gallery(self_dir: Path) -> Gallery:
    saved = Path(self_dir) / GALLERY
    data = None
    if saved.exists() and not is_sealed(Path(self_dir)):
        try:
            data = read_json(saved, None)
        except (CorruptFile, OSError) as error:
            log.warning("the saved gallery cannot be read (%s); showing the template gallery", error)
    gallery = Gallery(data) if isinstance(data, dict) else Gallery()
    return gallery if gallery.names() else Gallery.template()


def stop_on_signals(loop: asyncio.AbstractEventLoop, stop: asyncio.Event) -> None:
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
        except (NotImplementedError, RuntimeError, ValueError):
            pass


async def run_demo(self_dir: Path, host: str, port: int, seed: int | None, seconds: float | None, level: float | None, eyes: dict | None = None) -> int:
    loop = asyncio.get_running_loop()
    hub = Hub()
    face = WebFace(hub)
    seeing = eyes_from_config(eyes, Clock(), hub=hub) if eyes else None
    page_eyes = seeing if isinstance(seeing, BrowserEyes) else None
    chaos = Chaos(seed=seed, pinned=DEMO_LEVEL if level is None else level)
    levels = (chaos.pinned,) if level is not None else LEVELS
    demo = Demo(face, SceneStage(face, prefix="demo"), demo_gallery(self_dir), chaos, levels=levels)
    stop = asyncio.Event()
    stop_on_signals(loop, stop)

    def state() -> dict:
        status = getattr(seeing, "status", None)
        return {"face": face.state.as_dict(), "chaos": chaos.explain(), "demo": True, "eyes": status() if callable(status) else None}

    server = start_face_server(hub, host, port, threadsafe(loop, demo.touched), state, page_eyes)
    log.info("screen demo running at %s (Ctrl+C to stop)", server.url)
    if seconds is not None:
        loop.call_later(max(0.0, seconds), stop.set)
    try:
        await demo.run(stop)
    finally:
        server.stop()
        close_eyes(seeing)
    return 0
