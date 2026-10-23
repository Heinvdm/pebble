import json
import logging
import struct
import threading

from ..self.recall.embed import DIM, ONNX_NAME, OnnxEmbedder, StandIn

log = logging.getLogger(__name__)

_lock = threading.Lock()
_bridge = None


class NoBridge(RuntimeError):
    pass


def install(bridge) -> None:
    global _bridge
    with _lock:
        _bridge = bridge


def current():
    with _lock:
        return _bridge


def require(what: str):
    found = current()
    if found is None:
        raise NoBridge(f"{what} works only inside the Pebble Android app")
    return found


def as_bytes(value) -> bytes:
    if value is None:
        return b""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return bytes(b & 0xFF for b in value) if isinstance(value, (list, tuple)) else bytes(value)


def as_json(value, default=None):
    if value is None:
        return default
    try:
        return json.loads(str(value))
    except ValueError:
        return default


def number(value) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


class PhoneSentences:
    dim = DIM

    def __init__(self, phone):
        self.phone = phone
        self.standin = StandIn()
        self.on_standin = False
        self.why = ""
        self._lock = threading.Lock()
        choice = as_json(phone.recallChoice(), {}) or {}
        if not self._turned(choice):
            log.info("memory search uses the phone's sentence model (%s, %s)", ONNX_NAME, choice.get("rung") or "unknown")

    @property
    def name(self) -> str:
        return self.standin.name if self.on_standin else ONNX_NAME

    @property
    def related(self) -> float:
        return self.standin.related if self.on_standin else OnnxEmbedder.related

    def _turned(self, choice: dict) -> bool:
        with self._lock:
            if not self.on_standin and choice.get("standin_now"):
                self.on_standin = True
                self.why = str(choice.get("why") or "")
                log.info("memory search uses the stand-in: %s", self.why or "the phone's sentence model is not in use")
            return self.on_standin

    def embed(self, texts, query: bool = False) -> list[list[float]]:
        lines = [str(text or "") for text in texts]
        if not lines:
            return []
        if self.on_standin:
            return self.standin.embed(lines, query)
        try:
            blob = as_bytes(self.phone.recallEmbed(json.dumps(lines), bool(query)))
        except Exception as error:
            log.warning("the phone's sentence model could not be asked: %s", error)
            return []
        count = len(lines) * DIM
        if len(blob) == count * 4:
            values = struct.unpack(f"<{count}f", blob)
            return [list(values[n * DIM : (n + 1) * DIM]) for n in range(len(lines))]
        if blob:
            log.warning("the phone's sentence model gave %d bytes for %d lines", len(blob), len(lines))
            return []
        if self._turned(as_json(self.phone.recallChoice(), {}) or {}):
            return self.standin.embed(lines, query)
        return []

    def close(self) -> None:
        try:
            self.phone.recallClose()
        except Exception as error:
            log.debug("the phone's sentence model did not close: %s", error)


def sentences(phone=None) -> PhoneSentences | None:
    found = phone if phone is not None else current()
    if found is None or not hasattr(found, "recallEmbed"):
        return None
    try:
        return PhoneSentences(found)
    except Exception as error:
        log.warning("the phone's sentence model is not available: %s", error)
        return None
