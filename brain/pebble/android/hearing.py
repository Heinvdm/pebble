import asyncio
import json
import logging
from typing import Callable

from ..clock import Clock
from ..hearing.tvcheck import CHECKS, tv_passed
from .bridge import NoBridge, as_json, require
from .mic import MicLadder, PhoneMic

log = logging.getLogger(__name__)

CHECK_S = 20.0
MAX_CHARS = 400
MODES = ("words", "keywords", "off")
TURN_CHECK_S = 60.0
TURN_RETRY_S = 3600.0


class AndroidEars:
    def __init__(self, clock: Clock | None = None, listen: bool = True, bridge=None, check_s: float = CHECK_S):
        self.clock = clock or Clock()
        self.enabled = bool(listen)
        self._bridge = bridge
        self.check_s = max(0.05, float(check_s))
        self.life = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.listening = False
        self.heard_count = 0
        self.dropped = 0
        self._awake_until = float("-inf")
        self.policy: Callable[[bool, bool], str] | None = None
        self.mode = "off"
        self.turn_wanted = True
        self.turn_state = "unknown"
        self.turn_checked_at = float("-inf")
        self.turn_gave_up_at = float("-inf")
        self.turn_asked = False
        self.mic: MicLadder | None = None

    def bridge(self):
        return self._bridge if self._bridge is not None else require("listening")

    def wanted_mode(self) -> str:
        if not self.enabled or self.life is None:
            return "off"
        awake = self.clock.monotonic() < self._awake_until
        if awake:
            return "words"
        quiet = self.life.quiet_hours.contains(self.clock.local())
        if self.policy is not None:
            try:
                chosen = str(self.policy(quiet, awake))
            except Exception as error:
                log.warning("ears: the listening policy failed (%s); keeping words off in quiet hours", error)
                chosen = "off" if quiet else "words"
            return chosen if chosen in MODES else "off"
        return "off" if quiet else "words"

    def wanted(self) -> bool:
        return self.wanted_mode() != "off"

    def configure(self, **settings) -> None:
        try:
            self.bridge().speechConfig(json.dumps(settings))
        except Exception as error:
            log.warning("ears: the phone would not take the listening settings: %s", error)

    def _switch(self, on: bool) -> None:
        if on == self.listening:
            return
        try:
            self.bridge().listen(bool(on))
        except Exception as error:
            log.warning("ears: the phone would not %s listening: %s", "start" if on else "stop", error)
            return
        self.listening = on
        log.info("ears: %s", "listening (on the phone only)" if on else "not listening")

    def set_enabled(self, on: bool) -> None:
        self.enabled = bool(on)
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.update)

    def wake_for(self, seconds: float) -> None:
        self._awake_until = max(self._awake_until, self.clock.monotonic() + max(0.0, float(seconds)))
        if self.loop is not None and not self.loop.is_closed():
            try:
                self.loop.call_soon_threadsafe(self.update)
            except RuntimeError:
                pass

    def update(self) -> None:
        mode = self.wanted_mode()
        if mode != self.mode:
            try:
                self.bridge().speechConfig(json.dumps({"mode": mode}))
            except Exception as error:
                log.debug("ears: the phone has no listening modes: %s", error)
            self.mode = mode
            log.info("ears: listening mode %s", mode)
        self._switch(mode != "off")
        self._check_turn_model()
        self._check_mic()

    def _check_mic(self) -> None:
        if self.mic is None:
            return
        try:
            self.mic.tick(self.clock.monotonic())
        except Exception:
            log.exception("ears: the microphone settings could not be checked")

    def _gain_checked(self, life) -> bool:
        store = getattr(getattr(life, "p", None), "store", None)
        if store is None:
            return False
        try:
            return tv_passed(store.read(CHECKS, {}) or {})
        except Exception:
            return False

    def turn_model_state(self) -> str:
        try:
            info = as_json(self.bridge().hearingInfo(), {})
        except Exception:
            return "none"
        if not isinstance(info, dict):
            return "none"
        engine = info.get("engine")
        found = engine.get("turn_model") if isinstance(engine, dict) else None
        return str(found or info.get("turn_model") or "none")

    def _check_turn_model(self) -> None:
        now = self.clock.monotonic()
        if not self.turn_wanted or now - self.turn_checked_at < TURN_CHECK_S:
            return
        self.turn_checked_at = now
        state = self.turn_model_state()
        if state != self.turn_state:
            log.info("ears: the phone's end-of-turn model is %s", state)
        self.turn_state = state
        if state == "off" and now - self.turn_gave_up_at >= TURN_RETRY_S:
            self.turn_asked = True
            self.configure(turn_model=True)
        elif state == "missing" or state.startswith("failed"):
            self.turn_gave_up_at = now
            if self.turn_asked:
                self.turn_asked = False
                self.configure(turn_model=False)

    async def run(self, life) -> None:
        self.life = life
        self.loop = asyncio.get_running_loop()
        try:
            bridge = self.bridge()
        except NoBridge as error:
            log.warning("ears: %s; Pebble hears nothing", error)
            return
        bridge.earsSink(self)
        if self.mic is None:
            self.mic = MicLadder(PhoneMic(bridge), self.clock.monotonic, self._gain_checked(life), hold=lambda: bool(getattr(self.life, "alarm", lambda: False)()))
        try:
            while True:
                self.update()
                await asyncio.sleep(self.check_s)
        finally:
            self._switch(False)
            try:
                bridge.earsSink(None)
            except Exception:
                pass

    def heard(self, text, confidence=None) -> None:
        words = " ".join(str(text or "").split())[:MAX_CHARS]
        loop = self.loop
        if not words or loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._deliver, words)
        except RuntimeError:
            pass

    def _deliver(self, words: str) -> None:
        if not self.listening or self.life is None:
            self.dropped += 1
            return
        self.heard_count += 1
        self.life.hear(words)

    def status(self) -> dict:
        try:
            phone = as_json(self.bridge().hearingInfo(), {})
        except Exception as error:
            phone = {"problem": str(error)}
        try:
            state = as_json(self.bridge().earsState(), {})
        except Exception:
            state = {}
        mic = self.mic.status() if self.mic is not None else None
        return {"enabled": self.enabled, "listening": self.listening, "mode": self.mode, "state": state, "awake_for_s": round(max(0.0, self._awake_until - self.clock.monotonic()), 1), "heard": self.heard_count, "dropped": self.dropped, "phone": phone, "mic": mic}
