import asyncio
import logging

from .bridge import as_bytes, as_json, current, require

log = logging.getLogger(__name__)

JPEG = b"\xff\xd8"


class PhoneCloseUp:
    def __init__(self, bridge=None):
        self._bridge = bridge
        self.taken = 0
        self.problem = ""

    def bridge(self):
        return self._bridge if self._bridge is not None else require("a close look")

    def info(self) -> dict:
        try:
            found = as_json(self.bridge().eyesCloseUpInfo(), {})
        except Exception as error:
            return {"problem": str(error)}
        return found if isinstance(found, dict) else {}

    def available(self) -> bool:
        return not self.info().get("problem")

    def _take(self, max_side: int, zoom: float) -> bytes | None:
        try:
            data = as_bytes(self.bridge().eyesCloseUp(int(max_side), float(zoom)))
        except Exception as error:
            self.problem = str(error)
            log.warning("close look: the phone gave no picture: %s", error)
            return None
        if data[:2] != JPEG:
            last = self.info().get("last")
            self.problem = str((last or {}).get("problem") or "the phone gave no picture") if isinstance(last, dict) else "the phone gave no picture"
            return None
        self.problem = ""
        return data

    async def take(self, max_side: int, zoom: float) -> bytes | None:
        picture = await asyncio.to_thread(self._take, max_side, zoom)
        if picture is not None:
            self.taken += 1
        return picture

    def how(self) -> dict:
        last = self.info().get("last")
        if not isinstance(last, dict):
            return {}
        return {key: last.get(key) for key in ("asked", "lens_zoom", "digital", "lens", "lens_fov_deg", "ms") if key in last}


class SimCloseUp:
    def __init__(self, eyes):
        self.eyes = eyes
        self.taken = 0
        self.problem = ""
        self.asked: list = []

    def available(self) -> bool:
        return bool(getattr(self.eyes, "available", False)) and getattr(self.eyes, "snapshot", None) is not None

    async def take(self, max_side: int, zoom: float) -> bytes | None:
        self.asked.append((int(max_side), float(zoom)))
        before = self.eyes.camera() if callable(getattr(self.eyes, "camera", None)) else None
        try:
            picture = await self.eyes.snapshot(max_side=int(max_side), camera="rear")
        finally:
            if before and before != "rear" and getattr(self.eyes, "use_camera", None) is not None:
                await self.eyes.use_camera(before)
        if picture is None or picture[:2] != JPEG:
            self.problem = "the rear camera gave no picture"
            return None
        self.taken += 1
        return picture

    def how(self) -> dict:
        return {"asked": self.asked[-1][1] if self.asked else None, "lens": "the sim's rear camera"}


def closeup_for(eyes, bridge=None):
    found = bridge if bridge is not None else current()
    if found is not None and hasattr(found, "eyesCloseUp") and type(eyes).__name__ == "AndroidEyes":
        return PhoneCloseUp(found)
    try:
        from ..sim.eyes import SimEyes
    except ImportError:
        return None
    return SimCloseUp(eyes) if isinstance(eyes, SimEyes) else None
