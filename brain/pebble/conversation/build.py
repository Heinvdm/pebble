import logging
import random

from ..android.heat import PhoneHeat
from .core import Conversation

log = logging.getLogger(__name__)


def conversation_from(config: dict | None, clock, books, store, voice, face, rng: random.Random | None = None) -> Conversation | None:
    config = dict(config or {})
    if config.get("conversation") is False:
        return None
    conversation = Conversation(clock, store, books, voice, face, rng)
    conversation.heat = PhoneHeat(clock.monotonic)
    return conversation


def ears_from(config: dict | None, clock):
    config = dict(config or {})
    if config.get("kind") != "sherpa":
        return None
    from ..speech.ears import SherpaEars

    source = None
    if config.get("source"):
        from ..hearing.sources import source_from

        source = source_from(config["source"], clock.monotonic)
    return SherpaEars(clock, source=source, threads=int(config.get("threads", 1) or 1), listen=bool(config.get("listen", True)))
