import asyncio
import logging
from typing import Callable

from .events import SpeechEvent, parse

log = logging.getLogger(__name__)


class PhoneSpeech:
    def __init__(self, sink: Callable[[SpeechEvent], None] | None = None):
        self.sink = sink
        self.loop: asyncio.AbstractEventLoop | None = None
        self.received = 0
        self.bad = 0
        self.dropped = 0
        self.last: dict = {}

    def bind(self, loop: asyncio.AbstractEventLoop, sink: Callable[[SpeechEvent], None]) -> None:
        self.loop = loop
        self.sink = sink

    def event(self, json_text) -> None:
        found = parse(str(json_text) if not isinstance(json_text, (str, bytes)) else json_text)
        if found is None:
            self.bad += 1
            return
        self.received += 1
        self.last[found.kind] = found.t
        loop = self.loop
        if loop is None or loop.is_closed() or self.sink is None:
            self.dropped += 1
            return
        try:
            loop.call_soon_threadsafe(self._deliver, found)
        except RuntimeError:
            self.dropped += 1

    def _deliver(self, found: SpeechEvent) -> None:
        try:
            self.sink(found)
        except Exception:
            log.exception("speech: the conversation could not take an event from the phone")

    def status(self) -> dict:
        return {"received": self.received, "bad": self.bad, "dropped": self.dropped}


def attach_phone(phone: PhoneSpeech, bridge=None) -> bool:
    try:
        if bridge is None:
            from ..android.bridge import require

            bridge = require("hearing words")
        bridge.speechSink(phone)
        return True
    except Exception as error:
        log.warning("speech: the phone's speech sink is not there (%s); words come through the phone's own recogniser", error)
        return False


def detach_phone(bridge=None) -> None:
    try:
        if bridge is None:
            from ..android.bridge import require

            bridge = require("hearing words")
        bridge.speechSink(None)
    except Exception:
        pass
