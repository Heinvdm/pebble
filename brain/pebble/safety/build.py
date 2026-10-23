import logging
import time

from ..clock import Clock
from ..hearing.events import BridgeModel, LocalModel, load_labels
from ..hearing.service import Hearing
from ..hearing.sources import NoAudio, source_from
from .feeds import BridgeSensors
from .sounder import sounder_from
from .watch import Safety

log = logging.getLogger(__name__)

SENSED = ("accel", "pressure", "light", "proximity")
PHONE = {"hearing": {"kind": "android", "model": "phone"}, "sensors": "android", "sounder": {"kind": "android"}}


def on_phone() -> bool:
    from ..android import bridge

    return bridge.current() is not None


def model_from(kind: str, monotonic):
    if kind == "local":
        try:
            from ..hearing.yamnet import Yamnet

            return LocalModel(Yamnet.load(threads=1))
        except Exception as error:
            log.warning("safety: no sound model on this machine (%s); the beep detector still runs", error)
            return None
    if kind == "phone":
        try:
            from ..hearing.fetch import MODELS

            return BridgeModel(load_labels(MODELS), monotonic=monotonic)
        except Exception as error:
            log.warning("safety: the phone's sound model labels are missing (%s)", error)
            return None
    return None


def safety_from(config: dict | None, clock: Clock, name: str = "Pebble") -> Safety:
    config = dict(config or {})
    if config.get("enabled") is False:
        log.warning("safety: a profile cannot switch off listening for smoke, gas and falls, so it stays on")
    if on_phone():
        config = {**config, **PHONE}
    heard = dict(config.get("hearing") or {})
    source = source_from(heard, clock.monotonic)
    hearing = None
    model_kind = str(heard.get("model", "none"))
    if not isinstance(source, NoAudio):
        hearing = Hearing(source, clock.now, model=model_from(model_kind, clock.monotonic))
    feeds = {}
    sensors = None
    if config.get("sensors") == "android":
        sensors = BridgeSensors(monotonic=clock.monotonic)
        sensors.start()
        feeds = {kind: sensors.feed(kind) for kind in SENSED}
    safety = Safety(
        clock,
        hearing,
        feeds,
        sounder_from(config.get("sounder")),
        name=name,
        threaded=bool(config.get("threaded", True)),
        max_range=(lambda: sensors.max_range("proximity")) if sensors is not None else (lambda: None),
    )
    safety.sensors = sensors
    return safety
