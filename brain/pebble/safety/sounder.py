import logging
import math
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import Callable

from ..hearing.audio import RATE, samples_to_pcm, to_samples

SIREN_HZ = (650.0, 950.0)
SIREN_STEP_S = 0.5
SIREN_LEVEL = 0.8

log = logging.getLogger(__name__)


class LogSounder:
    def __init__(self, trace: Callable[[str, str], None] | None = None):
        self.trace = trace
        self.on = False
        self.spoken: list[str] = []
        self.switches = 0

    def siren(self, on: bool) -> bool:
        if on != self.on:
            self.switches += 1
            log.info("alarm sound %s", "on" if on else "off")
            if self.trace is not None:
                self.trace("alarm", "loud alarm sound on" if on else "alarm sound off")
        self.on = on
        return True

    def say(self, text: str) -> bool:
        self.spoken.append(text)
        del self.spoken[:-50]
        log.info("says loudly: %d words", len(text.split()))
        if self.trace is not None:
            self.trace("SAYS", f'"{text}" (loud)')
        return True

    def info(self) -> dict:
        return {"kind": "log", "on": self.on}


class AndroidSounder:
    def __init__(self, bridge=None):
        self._bridge = bridge
        self.on = False
        self.problem = ""

    def bridge(self):
        if self._bridge is not None:
            return self._bridge
        from ..android.bridge import require

        return require("the alarm sound")

    def siren(self, on: bool) -> bool:
        try:
            ok = bool(self.bridge().alarmSound(bool(on)))
        except Exception as error:
            ok = False
            self.problem = str(error)
            log.warning("safety: the alarm sound would not %s: %s", "start" if on else "stop", error)
        if ok:
            self.on = on
        return ok

    def say(self, text: str) -> bool:
        try:
            return bool(self.bridge().alarmSay(str(text)))
        except Exception as error:
            self.problem = str(error)
            log.warning("safety: could not speak loudly: %s", error)
            return False

    def info(self) -> dict:
        return {"kind": "android", "on": self.on, "problem": self.problem}


def siren_samples(seconds: float = 4.0) -> list[float]:
    out = []
    phase = 0.0
    for n in range(int(seconds * RATE)):
        freq = SIREN_HZ[int(n / (SIREN_STEP_S * RATE)) % 2]
        phase += 2.0 * math.pi * freq / RATE
        out.append(SIREN_LEVEL * math.sin(phase))
    return out


class CommandSounder:
    def __init__(self, command=("paplay",)):
        self.command = tuple(command)
        self.on = False
        self.problem = ""
        self.process: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None
        self.path = Path(tempfile.gettempdir()) / "pebble-siren.wav"

    def _write(self) -> None:
        if self.path.exists():
            return
        with wave.open(str(self.path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(RATE)
            handle.writeframes(samples_to_pcm(to_samples(siren_samples())))

    def _loop(self) -> None:
        while self.on:
            try:
                self.process = subprocess.Popen(self.command + (str(self.path),), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.process.wait()
            except OSError as error:
                self.problem = str(error)
                log.warning("safety: could not play the alarm sound with %s: %s", self.command[0], error)
                self.on = False
                return

    def siren(self, on: bool) -> bool:
        if on == self.on:
            return True
        if on:
            try:
                self._write()
            except OSError as error:
                self.problem = str(error)
                return False
            self.on = True
            self.thread = threading.Thread(target=self._loop, name="pebble-siren", daemon=True)
            self.thread.start()
            return True
        self.on = False
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
        return True

    def say(self, text: str) -> bool:
        return False

    def info(self) -> dict:
        return {"kind": "command", "command": self.command[0], "on": self.on, "problem": self.problem}


PLAYERS = (("paplay",), ("aplay", "-q"))


def sounder_from(config: dict | None):
    config = dict(config or {})
    kind = config.get("kind", "log")
    if kind == "android":
        return AndroidSounder()
    if kind == "command":
        command = tuple(str(part) for part in (config.get("command") or ("paplay",)))
        if command not in PLAYERS:
            log.warning("safety: a profile may name only a known player for the alarm sound, so %r is not run", command[:1])
            return LogSounder()
        return CommandSounder(command)
    return LogSounder()
