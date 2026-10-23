import logging

log = logging.getLogger(__name__)


class Tap:
    def __init__(self, bridge=None):
        self._bridge = bridge
        self.on = False

    def bridge(self):
        if self._bridge is not None:
            return self._bridge
        from ..android.bridge import require

        return require("the phone's motion sensors")

    def start(self) -> None:
        if self.on:
            return
        try:
            self.bridge().sensorTap(True)
            self.on = True
        except Exception as error:
            log.warning("nav: the phone's motion sensors would not start: %s", error)

    def stop(self) -> None:
        if not self.on:
            return
        try:
            self.bridge().sensorTap(False)
        except Exception as error:
            log.warning("nav: the phone's motion sensors would not stop: %s", error)
        self.on = False


def motion_feeds(profile, bridge=None) -> tuple:
    kind = str(((getattr(profile, "sensors", None) or {}).get("imu") or {}).get("kind") or "")
    if kind != "android":
        return None, None, None
    from ..safety.feeds import BridgeFeed

    tap = Tap(bridge)
    return BridgeFeed("gyro", bridge), BridgeFeed("accel", bridge), tap
