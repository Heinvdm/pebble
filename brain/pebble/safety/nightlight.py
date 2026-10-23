import asyncio
import math

CUT_LEVEL = 0.4
ASKED_LEVEL = 0.8
SPELL_S = 600.0
RENEW_S = 300.0
CUT_MOST_S = 1800.0
CUT_BATTERY_PCT = 25.0
ASKED_BATTERY_PCT = 10.0
LIGHT_BACK_LUX = 20.0
NOBODY_S = 120.0
POWER_CUT = "power cut"
ASKED = "asked"


class NightLight:
    def __init__(self, clock, torch=None):
        self.clock = clock
        self.torch = torch
        self.looked = torch is not None
        self.ports = None
        self.on = False
        self.why = ""
        self.since = -math.inf
        self.sent_at = -math.inf
        self.nobody_since: float | None = None
        self.problem = ""
        self.last_cut = ""

    def attach(self, ports) -> None:
        self.ports = ports
        if not self.looked:
            from ..android.torch import torch_for

            self.looked = True
            self.torch = torch_for()

    def has(self) -> bool:
        if self.torch is None:
            return False
        try:
            return bool(self.torch.has())
        except Exception:
            return False

    def _record(self, **data) -> None:
        if self.ports is not None:
            self.ports.record("torch", **data)

    def _note(self, text: str) -> None:
        if self.ports is not None:
            self.ports.note(text, False)

    def _say(self, text: str) -> None:
        if self.ports is None:
            return
        try:
            asyncio.ensure_future(self.ports.say(text, False))
        except RuntimeError:
            pass

    def _switch(self, on: bool, level: float = 1.0) -> bool:
        info = self.torch.set(on, level, SPELL_S) if self.torch is not None else {}
        self.problem = str(info.get("problem") or "")
        lit = bool(info.get("wanted") or info.get("on"))
        self.sent_at = self.clock.monotonic()
        return lit if on else True

    def power_cut(self, quiet: bool, anyone: bool, lux: float | None, charging: bool | None, hot: bool, battery: float | None) -> bool:
        why = ""
        if self.on:
            why = "the light was already on"
        elif not self.has():
            why = "there is no light on this phone"
        elif quiet:
            why = "it was quiet hours"
        elif not anyone:
            why = "nobody was around"
        elif lux is not None and lux > LIGHT_BACK_LUX:
            why = "it was not dark"
        elif hot:
            why = "the phone was too hot"
        elif battery is not None and battery < CUT_BATTERY_PCT:
            why = "the battery was low"
        self.last_cut = why
        if why:
            self._record(on=False, why=POWER_CUT, skipped=why)
            return False
        if not self._switch(True, CUT_LEVEL):
            self._record(on=False, why=POWER_CUT, problem=self.problem[:120])
            return False
        self.on, self.why, self.since = True, POWER_CUT, self.clock.monotonic()
        self.nobody_since = None
        self._record(on=True, why=POWER_CUT, level=CUT_LEVEL)
        self._note("the power seems to have gone off, so you put your light on for whoever is here")
        self._say("It looks like the power's gone off, so I've put my light on.")
        return True

    def asked(self, on: bool, battery: float | None = None, hot: bool = False) -> str:
        if not self.has():
            return "I don't have a light I can switch on."
        if not on:
            if not self.on:
                return "My light's already off."
            self._off("someone asked")
            return "Okay, light off."
        if hot:
            return "My phone's too hot for the light just now."
        if battery is not None and battery < ASKED_BATTERY_PCT:
            return "My battery's too low for the light just now."
        if not self._switch(True, ASKED_LEVEL):
            self._record(on=False, why=ASKED, problem=self.problem[:120])
            return "My light won't come on just now."
        self.on, self.why, self.since = True, ASKED, self.clock.monotonic()
        self._record(on=True, why=ASKED, level=ASKED_LEVEL)
        return "Okay, here's some light. It goes off by itself after ten minutes."

    def shut(self) -> None:
        if self.on and self.torch is not None:
            self.torch.set(False, 1.0, SPELL_S)
        self.on, self.why = False, ""

    def _off(self, reason: str, say: str = "") -> None:
        self._switch(False)
        self.on, self.why = False, ""
        self.nobody_since = None
        self._record(on=False, ended=reason)
        self._note(f"you turned your light off ({reason})")
        if say:
            self._say(say)

    def tick(self, quiet: bool, anyone: bool, lux: float | None, charging: bool | None, hot: bool, battery: float | None) -> None:
        if not self.on or self.torch is None:
            return
        mono = self.clock.monotonic()
        try:
            info = self.torch.info()
        except Exception:
            info = {}
        if info and not info.get("wanted") and not info.get("on"):
            self.on, self.why = False, ""
            ended = str(info.get("ended") or "the phone ended it")
            self._record(on=False, ended=ended)
            self._note(f"your light went off by itself ({ended})")
            return
        if hot:
            self._off("my phone got hot", "My phone's getting hot, so I've turned my light off.")
            return
        if self.why != POWER_CUT:
            return
        if charging is True:
            self._off("the power came back")
            return
        if lux is not None and lux > LIGHT_BACK_LUX:
            self._off("the room is light again")
            return
        if quiet:
            self._off("my quiet time began")
            return
        if anyone:
            self.nobody_since = None
        elif self.nobody_since is None:
            self.nobody_since = mono
        elif mono - self.nobody_since >= NOBODY_S:
            self._off("nobody was around")
            return
        if battery is not None and battery < CUT_BATTERY_PCT:
            self._off("my battery got low", "My battery's getting low, so I've turned my light off.")
            return
        if mono - self.since >= CUT_MOST_S:
            self._off("it had been on for half an hour", "I've turned my light off to save my battery. Say \"Pebble, light\" if you need it again.")
            return
        if mono - self.sent_at >= RENEW_S:
            self._switch(True, CUT_LEVEL)

    def status(self) -> dict:
        return {"has": self.has(), "on": self.on, "why": self.why, "problem": self.problem, "last_power_cut": self.last_cut}
