import asyncio
import json
import logging
import math

from .bridge import as_json, number, require

log = logging.getLogger(__name__)

TODAY_RATE = 16000
WIDE_RATE = 48000
CHECK_S = 60.0
VERIFY_S = 15.0
BAND_FLOOR_HZ = 16000.0


def wide_verdict(plan: dict) -> tuple[bool, str]:
    probe = plan.get("probe") if isinstance(plan, dict) else None
    if not isinstance(probe, dict):
        return False, "my microphones haven't been measured yet"
    suggested = probe.get("suggested") if isinstance(probe.get("suggested"), dict) else {}
    reasons = [str(reason) for reason in suggested.get("why_not") or []]
    if number(suggested.get("rate")) != WIDE_RATE or reasons:
        return False, "; ".join(reasons) or "the measurement said to stay at 16 kHz"
    return True, ""


def hears_to(plan: dict) -> float | None:
    probe = plan.get("probe") if isinstance(plan, dict) else None
    sweep = probe.get("sweep") if isinstance(probe, dict) else None
    return number(sweep.get("hears_to_hz")) if isinstance(sweep, dict) else None


def probe_at(plan: dict):
    probe = plan.get("probe") if isinstance(plan, dict) else None
    return probe.get("at") if isinstance(probe, dict) else None


def rate_of(part) -> int | None:
    found = number(part.get("rate")) if isinstance(part, dict) else None
    return None if found is None else int(found)


def probe_words(result: dict) -> str:
    if not isinstance(result, dict) or result.get("problem"):
        problem = result.get("problem") if isinstance(result, dict) else ""
        return f"The microphone check didn't work{': ' + str(problem) if problem else ''}."
    sweep = result.get("sweep") if isinstance(result.get("sweep"), dict) else {}
    top = number(sweep.get("hears_to_hz"))
    if top is not None:
        reach = f"My microphones hear up to about {round(top / 1000.0)} kHz on this phone."
    else:
        reach = "I couldn't hear my own whistle, so I don't know yet how high this phone can hear."
    ok, _ = wide_verdict({"probe": result})
    feed = "I'll try a wider sound feed, so I can listen for high tones all the time." if ok else "I'll stay on my usual sound feed, and listen for high tones only when someone asks."
    clicks = result.get("clicks") if isinstance(result.get("clicks"), dict) else {}
    spacing = number(clicks.get("spacing_m"))
    if clicks.get("two_separate_microphones") and spacing:
        mics = f" I have two separate microphones, about {round(spacing * 100)} cm apart."
    elif "copied" in str(clicks.get("verdict") or ""):
        mics = " My two sound channels are really one microphone, so I can't tell which way a sound comes from."
    else:
        mics = ""
    return f"Done. {reach} {feed}{mics}"


class PhoneMic:
    def __init__(self, bridge=None):
        self._bridge = bridge

    def bridge(self):
        return self._bridge if self._bridge is not None else require("the microphone")

    def _json(self, method: str, *args) -> dict:
        found = as_json(getattr(self.bridge(), method)(*args), {})
        return found if isinstance(found, dict) else {}

    def plan(self) -> dict:
        return self._json("micPlan")

    def info(self) -> dict:
        return self._json("hearingInfo")

    def state(self) -> dict:
        return self._json("earsState")

    def set(self, **settings) -> None:
        self.bridge().speechConfig(json.dumps(settings))

    def probe(self, options: dict | None = None) -> dict:
        return self._json("micProbe", json.dumps(options or {}))


class SimMic:
    def __init__(self, result: dict | None = None, echo: bool = True, refuse_wide: str = "", echo_at_wide: bool = True, gain_engine: bool = True):
        self.result = result
        self.echo = echo
        self.refuse_wide = refuse_wide
        self.echo_at_wide = echo_at_wide
        self.gain_engine = gain_engine
        self.wanted = {"rate": TODAY_RATE, "channels": 1, "speech_channel": 0}
        self.using = dict(self.wanted)
        self.step_down = ""
        self.kws_gain = False
        self.configs: list = []
        self.probes = 0
        self.probe_at = 0

    def speechConfig(self, text: str) -> None:
        settings = json.loads(text)
        self.configs.append(settings)
        if "kws_gain" in settings:
            self.kws_gain = bool(settings["kws_gain"])
        if "mic_rate" in settings:
            self.wanted = {"rate": int(settings["mic_rate"]), "channels": int(settings.get("mic_channels", 1)), "speech_channel": int(settings.get("mic_speech_channel", 0))}
            if self.wanted["rate"] != TODAY_RATE and self.refuse_wide:
                self.using = {"rate": TODAY_RATE, "channels": 1, "speech_channel": 0}
                self.step_down = self.refuse_wide
            else:
                self.using = dict(self.wanted)
                self.step_down = ""

    def micPlan(self) -> str:
        probe = None
        if self.result is not None:
            probe = {"at": self.probe_at, "suggested": self.result.get("suggested"), "clicks": self.result.get("clicks"), "sweep": self.result.get("sweep")}
        return json.dumps({"wanted": self.wanted, "using": self.using, "step_down": self.step_down, "probing": None, "probe": probe})

    def micProbe(self, options: str) -> str:
        self.probes += 1
        self.probe_at += 1
        if self.result is None:
            return json.dumps({"problem": "no microphone in this process"})
        return json.dumps(self.result)

    def earsState(self) -> str:
        wide = self.using["rate"] != TODAY_RATE
        return json.dumps({"listening": True, "aec": self.echo and (self.echo_at_wide or not wide), "ears": "ready"})

    def hearingInfo(self) -> str:
        engine = {"engine": "sherpa-onnx", "kws_gain": 1.0 if self.kws_gain else None} if self.gain_engine else {"engine": "android"}
        return json.dumps({"engine": engine, "microphone": {"rate": self.using["rate"]}})


def probe_result(hears_to_hz: float | None = 21000.0, wide: bool = True, two: bool = False) -> dict:
    reasons = []
    if not wide:
        reasons.append("no 48 kHz voice-recognition feed that keeps the sound above 8 kHz")
    if hears_to_hz is None or hears_to_hz < BAND_FLOOR_HZ:
        reasons.append("the sweep did not show the path carrying sound above 15 kHz")
    ok = not reasons
    return {
        "configs": [],
        "clicks": {"two_separate_microphones": two, "spacing_m": 0.155 if two else None, "verdict": "two separate microphones about 15.5 cm apart" if two else "both channels hear every click at the same moment: one microphone copied twice, or a mix"},
        "sweep": {"hears_to_hz": hears_to_hz, "verdict": "the path carries the sweep"},
        "suggested": {"rate": WIDE_RATE if ok else TODAY_RATE, "channels": 1, "speech_channel": 0, "high_band_top_hz": hears_to_hz if ok else None, "why_not": reasons},
    }


class MicLadder:
    def __init__(self, mic, monotonic, gain_checked: bool = False, hold=lambda: False):
        self.mic = mic
        self.monotonic = monotonic
        self.gain_checked = bool(gain_checked)
        self.hold = hold
        self.plan_now: dict = {}
        self.checked_at = -math.inf
        self.until = -math.inf
        self.failed: dict | None = None
        self.switched: tuple | None = None
        self.gain_hold = False
        self.probing = False
        self.problem = ""

    def read_plan(self) -> dict:
        try:
            self.plan_now = self.mic.plan()
            self.problem = ""
        except Exception as error:
            self.problem = str(error)
        return self.plan_now

    def _failed_here(self, plan: dict) -> bool:
        return self.failed is not None and self.failed.get("probe_at") == probe_at(plan)

    def always_wide(self, plan: dict | None = None) -> bool:
        plan = self.plan_now if plan is None else plan
        ok, _ = wide_verdict(plan)
        return ok and not self._failed_here(plan)

    def wanted_rate(self, mono: float) -> int:
        return WIDE_RATE if self.always_wide() or mono < self.until else TODAY_RATE

    def wide(self) -> bool:
        return rate_of(self.plan_now.get("using")) == WIDE_RATE

    def tick(self, mono: float | None = None, force: bool = False) -> None:
        mono = self.monotonic() if mono is None else mono
        if self.probing:
            return
        if self.switched is not None and mono - self.switched[0] >= VERIFY_S:
            self._verify(mono)
        due = force or mono - self.checked_at >= CHECK_S or (self.until > -math.inf and mono >= self.until)
        if not due:
            return
        self.checked_at = mono
        self.read_plan()
        if mono >= self.until:
            self.until = -math.inf
        self._rate(mono)
        if not self.gain_hold:
            self._gain()

    def _rate(self, mono: float) -> None:
        plan = self.plan_now
        if not plan:
            return
        want = self.wanted_rate(mono)
        have = rate_of(plan.get("wanted"))
        if have == want:
            return
        try:
            held = bool(self.hold())
        except Exception:
            held = True
        if held:
            self.checked_at = -math.inf
            return
        aec = None
        if want == WIDE_RATE:
            try:
                aec = bool(self.mic.state().get("aec"))
            except Exception:
                aec = None
        try:
            self.mic.set(mic_rate=want, mic_channels=1, mic_speech_channel=0)
        except Exception as error:
            self.problem = str(error)
            log.warning("microphone: the phone would not change its feed: %s", error)
            return
        log.info("microphone: asked for the %s kHz feed", want // 1000)
        self.switched = (mono, aec) if want == WIDE_RATE else None
        self.read_plan()

    def _verify(self, mono: float) -> None:
        started, aec_before = self.switched
        self.switched = None
        plan = self.read_plan()
        why = ""
        if rate_of(plan.get("using")) != WIDE_RATE or plan.get("step_down"):
            why = f"the phone would not give me a 48 kHz feed ({plan.get('step_down') or 'it stayed at 16 kHz'})"
        elif aec_before:
            try:
                kept = bool(self.mic.state().get("aec"))
            except Exception:
                kept = False
            if not kept:
                why = "the echo canceller would not work on the 48 kHz feed"
        if not why:
            return
        self.failed = {"probe_at": probe_at(plan), "why": why}
        self.until = -math.inf
        log.warning("microphone: back to the 16 kHz feed, because %s", why)
        try:
            self.mic.set(mic_rate=TODAY_RATE, mic_channels=1, mic_speech_channel=0)
        except Exception as error:
            self.problem = str(error)
        self.read_plan()

    def _gain_on(self) -> bool | None:
        try:
            info = self.mic.info()
        except Exception:
            return None
        engine = info.get("engine")
        if not isinstance(engine, dict) or "kws_gain" not in engine:
            return None
        return engine.get("kws_gain") is not None

    def _gain(self) -> None:
        have = self._gain_on()
        if have is None or have == self.gain_checked:
            return
        self.set_gain(self.gain_checked)

    def set_gain(self, on: bool) -> bool:
        try:
            self.mic.set(kws_gain=bool(on))
            return True
        except Exception as error:
            self.problem = str(error)
            return False

    def listen_wide(self, seconds: float, mono: float | None = None) -> tuple[bool, str]:
        mono = self.monotonic() if mono is None else mono
        plan = self.read_plan()
        top = hears_to(plan)
        if top is not None and top < BAND_FLOOR_HZ:
            return False, f"this phone's microphone stops at about {round(top / 1000.0)} kHz"
        if self._failed_here(plan):
            return False, str(self.failed.get("why"))
        if self.always_wide(plan) and self.wide():
            return True, ""
        self.until = max(self.until, mono + float(seconds))
        self.tick(mono, force=True)
        return True, ""

    async def probe(self, options: dict | None = None) -> dict:
        self.probing = True
        try:
            result = await asyncio.to_thread(self.mic.probe, options)
        except Exception as error:
            result = {"problem": str(error)}
        finally:
            self.probing = False
        self.failed = None
        self.checked_at = -math.inf
        self.switched = None
        return result

    def status(self) -> dict:
        ok, why = wide_verdict(self.plan_now)
        return {
            "using_hz": rate_of(self.plan_now.get("using")),
            "always_wide": ok and not self._failed_here(self.plan_now),
            "why_not": why,
            "failed": self.failed,
            "listening_wide_for_s": round(max(0.0, self.until - self.monotonic()), 1) if self.until > -math.inf else 0.0,
            "kws_gain_checked": self.gain_checked,
            "probing": self.probing,
            "problem": self.problem,
        }
