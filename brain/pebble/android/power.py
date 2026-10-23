import logging

from .bridge import require

log = logging.getLogger(__name__)

MODES = ("rest", "reboot", "none")


class AndroidPower:
    def __init__(self, mode: str = "rest", bridge=None):
        self.mode = mode if mode in MODES else "rest"
        self._bridge = bridge

    def shutdown(self) -> bool:
        if self.mode == "none":
            log.warning("power: nothing to do on Android with mode none; only the brain stops")
            return False
        try:
            bridge = self._bridge if self._bridge is not None else require("powering the phone down")
            done = str(bridge.powerOff(self.mode))
        except Exception as error:
            log.error("power: the phone would not %s: %s", self.mode, error)
            return False
        log.warning("power: %s", done)
        return done not in ("", "none")
