import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .abilities import COUNTED, QUERIES, SPEAKING, allowed_by
from .evaluate import Call, Crash, Done, Finish, Machine
from .program import LIMITS, Limits

log = logging.getLogger(__name__)

RATE_PER_MINUTE = 30
REFUSALS_PAUSE = 3
REFUSALS_WINDOW_S = 3600.0
KEEP_KEY_MOST = 80
LOG_MOST = 400
ANSWER_WAIT_S = 3.0
LOAD_WAIT_S = 10.0
MEMORY_MB = 256
PHONE_MEMORY_MB = 64
LINE_MOST = 1 << 20
BRAIN = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Refused:
    reason: str
    counted: bool = True
    law: int | None = None

    def said(self) -> str:
        return f"refused: {self.reason}"


class Paused(Exception):
    pass


class Stopped(Exception):
    pass


def outcome_of(message: dict):
    if "call" in message:
        return Call(str(message["call"]), dict(message.get("args") or {}), int(message.get("line") or 0))
    if message.get("done"):
        return Done()
    if message.get("finish"):
        return Finish()
    if "crash" in message:
        return Crash(str(message["crash"]), str(message.get("what") or ""), int(message.get("line") or 0), str(message.get("text") or "it stopped"))
    return Crash("error", "", 0, "the script's process sent something it shouldn't")


def message_of(outcome) -> dict:
    if isinstance(outcome, Call):
        return {"call": outcome.name, "args": outcome.args, "line": outcome.line}
    if isinstance(outcome, Finish):
        return {"finish": True}
    if isinstance(outcome, Crash):
        return {"crash": outcome.kind, "what": outcome.what, "line": outcome.line, "text": outcome.text}
    return {"done": True}


class Local:
    kind = "local"

    def __init__(self, limits: Limits = LIMITS):
        self.limits = limits
        self.machine: Machine | None = None
        self.run = None

    async def load(self, program: dict):
        try:
            self.machine = Machine(program, self.limits)
        except Exception as error:
            return Crash("error", "", 0, f"the program could not be loaded ({type(error).__name__})")
        out = self.machine.start().go()
        return out if isinstance(out, Crash) else None

    async def go(self, handler: str, args: list):
        if self.machine is None:
            return Crash("error", "", 0, "the program is not loaded")
        self.run = self.machine.run(handler, args)
        return self.run.go()

    async def reply(self, value):
        if self.run is None:
            return Crash("error", "", 0, "nothing was waiting for a reply")
        return self.run.go(value)

    async def stop(self) -> None:
        if self.run is not None:
            self.run.stop()
            self.run = None

    async def close(self) -> None:
        await self.stop()
        self.machine = None


class Process:
    kind = "process"

    def __init__(self, limits: Limits = LIMITS, memory_mb: int = MEMORY_MB, wait_s: float = ANSWER_WAIT_S, python: str | None = None):
        self.limits = limits
        self.memory_mb = memory_mb
        self.wait_s = wait_s
        self.python = python or sys.executable
        self.proc: asyncio.subprocess.Process | None = None
        self.program: dict | None = None

    def _env(self) -> dict:
        keep = {k: v for k, v in os.environ.items() if k.upper() in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL")}
        keep["PYTHONPATH"] = str(BRAIN)
        keep["PYTHONDONTWRITEBYTECODE"] = "1"
        keep["PYTHONIOENCODING"] = "utf-8"
        return keep

    async def _spawn(self) -> None:
        self.proc = await asyncio.create_subprocess_exec(
            self.python, "-X", "utf8", "-m", "pebble.script.host", "--memory-mb", str(self.memory_mb),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            cwd=str(BRAIN), env=self._env(), limit=LINE_MOST,
        )

    async def _send(self, message: dict) -> None:
        proc = self.proc
        if proc is None or proc.stdin is None:
            raise ConnectionError("no script process")
        proc.stdin.write((json.dumps(message, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8"))
        await proc.stdin.drain()

    async def _read(self, wait_s: float) -> dict:
        proc = self.proc
        if proc is None or proc.stdout is None:
            raise ConnectionError("no script process")
        line = await asyncio.wait_for(proc.stdout.readline(), wait_s)
        if not line:
            raise ConnectionError("the script process ended")
        return json.loads(line.decode("utf-8"))

    async def _ask(self, message: dict, wait_s: float | None = None):
        try:
            await self._send(message)
            reply = await self._read(self.wait_s if wait_s is None else wait_s)
        except asyncio.TimeoutError:
            await self.kill()
            return Crash("limit", "time", 0, "it computed for too long without stopping, so its process was stopped")
        except (ConnectionError, OSError, ValueError) as error:
            await self.kill()
            return Crash("error", "", 0, f"its process failed ({type(error).__name__})")
        return reply

    async def load(self, program: dict):
        self.program = program
        if self.proc is None or self.proc.returncode is not None:
            try:
                await self._spawn()
            except OSError as error:
                return Crash("error", "", 0, f"its process could not start ({error})")
        reply = await self._ask({"op": "load", "id": "s", "program": program, "limits": self.limits.as_dict()}, LOAD_WAIT_S)
        if isinstance(reply, Crash):
            return reply
        if reply.get("loaded"):
            return None
        return outcome_of(reply)

    async def go(self, handler: str, args: list):
        if self.proc is None or self.proc.returncode is not None:
            if self.program is None:
                return Crash("error", "", 0, "the program is not loaded")
            crashed = await self.load(self.program)
            if crashed is not None:
                return crashed
        reply = await self._ask({"op": "run", "id": "s", "handler": handler, "args": list(args)})
        return reply if isinstance(reply, Crash) else outcome_of(reply)

    async def reply(self, value):
        reply = await self._ask({"op": "reply", "id": "s", "value": value})
        return reply if isinstance(reply, Crash) else outcome_of(reply)

    async def stop(self) -> None:
        if self.proc is not None and self.proc.returncode is None:
            try:
                await self._send({"op": "stop", "id": "s"})
                await self._read(self.wait_s)
            except Exception:
                await self.kill()

    async def kill(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None:
            return
        try:
            if proc.returncode is None:
                proc.kill()
            await asyncio.wait_for(proc.wait(), 5.0)
        except (ProcessLookupError, asyncio.TimeoutError, OSError):
            pass

    async def close(self) -> None:
        proc = self.proc
        if proc is not None and proc.returncode is None:
            try:
                await self._send({"op": "quit"})
                await asyncio.wait_for(proc.wait(), 2.0)
            except Exception:
                pass
        await self.kill()

    @property
    def pid(self) -> int | None:
        return self.proc.pid if self.proc is not None else None


class Phone:
    kind = "phone"

    def __init__(self, limits: Limits = LIMITS, memory_mb: int = PHONE_MEMORY_MB, wait_s: float = ANSWER_WAIT_S, link=None):
        self.limits = limits
        self.memory_mb = memory_mb
        self.wait_s = wait_s
        self.link = link
        self.handle: str | None = None
        self.program: dict | None = None

    def _link(self):
        if self.link is None:
            from ..android.bridge import require

            self.link = require("running programs on the phone")
        return self.link

    async def _open(self) -> Crash | None:
        try:
            handle = await asyncio.to_thread(self._link().scriptOpen, int(self.memory_mb))
        except Exception as error:
            return Crash("error", "", 0, f"its process could not start ({type(error).__name__})")
        if not handle:
            return Crash("error", "", 0, "its process could not start")
        self.handle = str(handle)
        return None

    async def _ask(self, message: dict, wait_s: float | None = None):
        if self.handle is None:
            return Crash("error", "", 0, "its process failed (closed)")
        wait = self.wait_s if wait_s is None else wait_s
        line = json.dumps(message, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        try:
            text = await asyncio.to_thread(self._link().scriptAsk, self.handle, line, int(wait * 1000))
            reply = json.loads(str(text or ""))
        except Exception as error:
            await self.kill()
            return Crash("error", "", 0, f"its process failed ({type(error).__name__})")
        if not isinstance(reply, dict):
            await self.kill()
            return Crash("error", "", 0, "its process failed (not a message)")
        link = reply.get("link")
        if link == "timeout":
            self.handle = None
            return Crash("limit", "time", 0, "it computed for too long without stopping, so its process was stopped")
        if link is not None:
            self.handle = None
            return Crash("error", "", 0, f"its process failed ({link})")
        return reply

    async def load(self, program: dict):
        self.program = program
        if self.handle is None:
            crashed = await self._open()
            if crashed is not None:
                return crashed
        reply = await self._ask({"op": "load", "id": "s", "program": program, "limits": self.limits.as_dict()}, LOAD_WAIT_S)
        if isinstance(reply, Crash):
            return reply
        if reply.get("loaded"):
            return None
        return outcome_of(reply)

    async def go(self, handler: str, args: list):
        if self.handle is None:
            if self.program is None:
                return Crash("error", "", 0, "the program is not loaded")
            crashed = await self.load(self.program)
            if crashed is not None:
                return crashed
        reply = await self._ask({"op": "run", "id": "s", "handler": handler, "args": list(args)})
        return reply if isinstance(reply, Crash) else outcome_of(reply)

    async def reply(self, value):
        reply = await self._ask({"op": "reply", "id": "s", "value": value})
        return reply if isinstance(reply, Crash) else outcome_of(reply)

    async def stop(self) -> None:
        if self.handle is not None:
            reply = await self._ask({"op": "stop", "id": "s"})
            if isinstance(reply, Crash):
                await self.kill()

    async def kill(self) -> None:
        handle, self.handle = self.handle, None
        if handle is None:
            return
        try:
            await asyncio.to_thread(self._link().scriptClose, handle)
        except Exception as error:
            log.debug("a program's process did not close: %s", error)

    async def close(self) -> None:
        await self.kill()

    @property
    def pid(self) -> str | None:
        return self.handle


@dataclass
class Session:
    name: str
    program: dict
    engine: object
    world: object
    monotonic: Callable[[], float] = time.monotonic
    record: Callable[..., None] = lambda kind, **data: None
    kept: dict = field(default_factory=dict)
    keep_most: int = LIMITS.keep
    calls: list = field(default_factory=list)
    refusals: list = field(default_factory=list)
    log: list = field(default_factory=list)
    finished: bool = False
    paused: bool = False
    crash: Crash | None = None
    dirty: bool = False
    running: bool = False
    meta: dict = field(default_factory=dict)

    @property
    def header(self) -> dict:
        return self.program.get("header") or {}

    @property
    def uses(self) -> tuple:
        return tuple(self.header.get("USES") or ())

    async def load(self) -> Crash | None:
        crashed = await self.engine.load(self.program)
        if crashed is not None:
            self.crash = crashed
            self.record("script_crash", script=self.name, how=crashed.kind, what=crashed.what, line=crashed.line)
        return crashed

    async def handle(self, handler: str, args=()):
        if self.finished or self.paused or self.crash is not None:
            return Done()
        self.running = True
        try:
            out = await self.engine.go(handler, list(args))
            while isinstance(out, Call):
                try:
                    value = await self.answer(out)
                except Stopped:
                    await self.engine.stop()
                    return Done()
                except Paused:
                    await self.engine.stop()
                    if self.crash is None:
                        self.paused = True
                        self.record("script_paused", script=self.name, refusals=len(self.refusals))
                    return self.crash or Done()
                out = await self.engine.reply(value)
        finally:
            self.running = False
        if isinstance(out, Finish):
            self.finished = True
        elif isinstance(out, Crash):
            self.crash = out
            self.record("script_crash", script=self.name, how=out.kind, what=out.what, line=out.line)
        return out

    async def answer(self, call: Call):
        name, args = call.name, call.args
        if not allowed_by(self.uses, name):
            return await self._refused(name, args, f"{name} is not in this program's USES")
        if name == "keep":
            return self._keep(args.get("key"), args.get("value"))
        if name == "kept":
            return self._kept(args.get("key"), args.get("default"))
        now = self.monotonic()
        if name in COUNTED:
            self.calls = [at for at in self.calls if now - at < 60.0]
            if len(self.calls) >= RATE_PER_MINUTE:
                return await self._refused(name, args, f"it asked for more than {RATE_PER_MINUTE} things in a minute")
            self.calls.append(now)
        try:
            value = await self.world.ability(self, name, args)
        except (Paused, Stopped):
            raise
        except Exception:
            log.exception("a script's %s call failed", name)
            value = Refused("that didn't work just now", False)
        if isinstance(value, Refused):
            return await self._refused(name, args, value.reason, value.counted)
        self.log.append({"call": name, "args": args, "reply": value, "at": self.world_time()})
        del self.log[:-LOG_MOST]
        return value

    def world_time(self):
        clock = getattr(self.world, "now_text", None)
        return clock() if clock is not None else None

    async def _refused(self, name: str, args: dict, reason: str, counted: bool = True):
        now = self.monotonic()
        if counted:
            self.refusals = [at for at in self.refusals if now - at < REFUSALS_WINDOW_S] + [now]
        self.log.append({"call": name, "args": args, "refused": reason, "counted": counted, "at": self.world_time()})
        del self.log[:-LOG_MOST]
        self.record("script_refused", script=self.name, ability=name, reason=reason[:120], counted=counted)
        refused = getattr(self.world, "refused", None)
        if refused is not None:
            refused(self, name, reason)
        if counted and len(self.refusals) >= REFUSALS_PAUSE:
            raise Paused(reason)
        return QUERIES[name] if name in QUERIES else Refused(reason).said()

    def _keep(self, key, value):
        if not isinstance(key, str) or not key or len(key) > KEEP_KEY_MOST:
            return Refused("keep needs a short text key").said()
        try:
            plain = json.loads(json.dumps(value, allow_nan=False))
        except (TypeError, ValueError):
            return Refused("keep holds numbers, text, True, False, None, lists and dicts with text keys").said()
        if not _text_keys(plain):
            return Refused("keep holds dicts with text keys only").said()
        trial = dict(self.kept)
        trial[key] = plain
        if len(json.dumps(trial, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > self.keep_most:
            self.crash = Crash("limit", "keep", 0, f"its saved values came to more than {self.keep_most // 1024} KB")
            raise Paused("keep")
        self.kept = trial
        self.dirty = True
        self.log.append({"call": "keep", "args": {"key": key, "value": plain}, "reply": None, "at": self.world_time()})
        return None

    def _kept(self, key, default):
        if not isinstance(key, str):
            return default
        return json.loads(json.dumps(self.kept[key])) if key in self.kept else default

    async def stop(self) -> None:
        await self.engine.stop()

    async def close(self) -> None:
        await self.engine.close()

    def speaking(self) -> int:
        return sum(1 for item in self.log if item.get("call") in SPEAKING and "reply" in item)


def _text_keys(value) -> bool:
    if isinstance(value, dict):
        return all(isinstance(k, str) for k in value) and all(_text_keys(v) for v in value.values())
    if isinstance(value, list):
        return all(_text_keys(v) for v in value)
    return True


def limit_memory(megabytes: int) -> bool:
    limit = int(megabytes) * 1024 * 1024
    if os.name == "nt":
        return _windows_limit(limit)
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        return True
    except (ImportError, ValueError, OSError):
        return False


def _windows_limit(limit: int) -> bool:
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class Basic(ctypes.Structure):
            _fields_ = [
                ("per_process_time", ctypes.c_int64),
                ("per_job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD),
                ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t),
                ("active_processes", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", IoCounters), ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return False
        info = Extended()
        info.basic.flags = 0x100 | 0x8 | 0x2000
        info.basic.active_processes = 1
        info.process_memory = limit
        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            return False
        return bool(kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()))
    except Exception:
        return False


def serve(stdin, stdout, memory_mb: int = MEMORY_MB) -> int:
    limited = limit_memory(memory_mb)
    sys.setrecursionlimit(20000)
    machines: dict = {}
    runs: dict = {}

    def write(message: dict) -> None:
        stdout.write(json.dumps(message, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=str) + "\n")
        stdout.flush()

    def out(script_id: str, outcome) -> None:
        if not isinstance(outcome, Call):
            runs.pop(script_id, None)
        write({"id": script_id, **message_of(outcome)})

    for line in stdin:
        if len(line) > LINE_MOST:
            write({"error": "line too long"})
            continue
        try:
            message = json.loads(line)
        except ValueError:
            write({"error": "not JSON"})
            continue
        op = message.get("op")
        script_id = str(message.get("id") or "")
        try:
            if op == "quit":
                break
            if op == "ping":
                write({"pong": True, "limited": limited})
            elif op == "load":
                machine = Machine(message["program"], Limits.from_dict(message.get("limits")))
                machines[script_id] = machine
                result = machine.start().go()
                write({"id": script_id, **(message_of(result) if isinstance(result, Crash) else {"loaded": True})})
            elif op == "run":
                machine = machines.get(script_id)
                if machine is None:
                    write({"id": script_id, "crash": "error", "what": "", "line": 0, "text": "the program is not loaded"})
                    continue
                run = machine.run(str(message.get("handler") or ""), list(message.get("args") or []))
                runs[script_id] = run
                out(script_id, run.go())
            elif op == "reply":
                run = runs.get(script_id)
                if run is None:
                    write({"id": script_id, "crash": "error", "what": "", "line": 0, "text": "nothing was waiting for a reply"})
                    continue
                out(script_id, run.go(message.get("value")))
            elif op == "stop":
                run = runs.pop(script_id, None)
                if run is not None:
                    run.stop()
                write({"id": script_id, "stopped": True})
            elif op == "drop":
                machines.pop(script_id, None)
                runs.pop(script_id, None)
                write({"id": script_id, "dropped": True})
            else:
                write({"error": "unknown op"})
        except MemoryError:
            runs.pop(script_id, None)
            write({"id": script_id, "crash": "limit", "what": "size", "line": 0, "text": "it used too much memory"})
        except Exception as error:
            runs.pop(script_id, None)
            write({"id": script_id, "crash": "error", "what": "", "line": 0, "text": f"something went wrong ({type(error).__name__})"})
    return 0


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m pebble.script.host", description="Run Pebble script programs in their own process, speaking JSON lines on stdin and stdout.")
    parser.add_argument("--memory-mb", type=int, default=MEMORY_MB)
    args = parser.parse_args(argv)
    stdin = open(sys.stdin.fileno(), "r", encoding="utf-8", newline="\n", closefd=False)
    stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", newline="\n", closefd=False)
    return serve(stdin, stdout, args.memory_mb)


if __name__ == "__main__":
    raise SystemExit(main())
