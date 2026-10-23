import math
import re
from dataclasses import dataclass
from enum import IntFlag
from typing import Union

MAX_LINE = 96
POWER_LIMIT = 1000
SETTING_KEYS = ("ssid", "pass", "cpm", "edge", "stop", "tmin", "tmax", "trim", "rest")
NUMERIC_SETTINGS = frozenset({"cpm", "edge", "stop", "tmin", "tmax", "trim", "rest"})
EVENT_NAMES = frozenset({"boot", "bump", "edge", "obstacle", "stall", "dock", "lowbat", "deadman", "fault"})
AIR_VERSION = 1
AIR_NONE = "none"

_INT = re.compile(r"^[+-]?\d+$")
_NUM = re.compile(r"^[+-]?\d+(\.\d+)?$")
_KEY = re.compile(r"^[a-z][a-z0-9_]*$")


ERROR_REASONS = ("unknown", "syntax", "long", "cpm", "key", "value", "range", "nvs", "auth", "usb", "busy")
COMMAND_LETTERS = ("D", "M", "T", "X", "P", "Q", "C", "R", "H", "V", "K")
UNKNOWN_LETTER = "?"
EMPTY_VALUE = "-"
TEXT_SETTINGS = frozenset({"ssid", "pass"})


class ProtocolError(ValueError):
    def __init__(self, message: str, reason: str = "syntax", command: str = UNKNOWN_LETTER):
        super().__init__(message)
        self.reason = reason
        self.command = command


class Flags(IntFlag):
    NONE = 0
    EDGE_HOLD = 1
    BUMP_HOLD = 2
    OBSTACLE = 4
    STALL = 8
    LOW_BATTERY = 16
    DEADMAN = 32
    SENSOR_FAULT = 64
    REVERSE_LIMIT = 128


@dataclass(frozen=True)
class Drive:
    left: int
    right: int


@dataclass(frozen=True)
class Speed:
    left: int
    right: int


@dataclass(frozen=True)
class Tilt:
    degrees: float


@dataclass(frozen=True)
class Stop:
    pass


@dataclass(frozen=True)
class Ping:
    n: int


@dataclass(frozen=True)
class Query:
    pass


@dataclass(frozen=True)
class SetSetting:
    key: str
    value: str


@dataclass(frozen=True)
class GetSetting:
    key: str


@dataclass(frozen=True)
class ListSettings:
    pass


@dataclass(frozen=True)
class Reboot:
    pass


@dataclass(frozen=True)
class Status:
    ms: int
    enc_left: int
    enc_right: int
    front_mm: int
    down_mm: int
    bump: int
    dock: int
    pack_mv: int
    tilt: float
    flags: Flags


@dataclass(frozen=True)
class Air:
    ms: int
    temperature_c: float | None = None
    humidity_pct: float | None = None
    pressure_pa: int | None = None
    gas_ohm: int | None = None
    heated_s: int | None = None
    version: int = AIR_VERSION

    @property
    def present(self) -> bool:
        return self.temperature_c is not None


@dataclass(frozen=True)
class Event:
    name: str
    args: tuple[str, ...] = ()

    @property
    def arg(self) -> str | None:
        return self.args[0] if self.args else None

    def text(self) -> str:
        return " ".join((self.name,) + self.args)


@dataclass(frozen=True)
class Pong:
    n: int


@dataclass(frozen=True)
class SettingValue:
    key: str
    value: str


@dataclass(frozen=True)
class Ok:
    pass


@dataclass(frozen=True)
class Err:
    command: str
    reason: str


Command = Union[Drive, Speed, Tilt, Stop, Ping, Query, SetSetting, GetSetting, ListSettings, Reboot]
LETTERS = {Drive: "D", Speed: "M", Tilt: "T", Stop: "X", Ping: "P", Query: "Q", SetSetting: "C", GetSetting: "C", ListSettings: "C", Reboot: "R"}
REPLY_KINDS = {Stop: "ok", SetSetting: "ok", Reboot: "ok", GetSetting: "get", ListSettings: "list"}


def letter_of(command: Command) -> str:
    return LETTERS[type(command)]


def reply_kind(command: Command) -> str | None:
    return REPLY_KINDS.get(type(command))


def command_letter(line: str) -> str:
    words = line.strip().split(maxsplit=1)
    return words[0] if words and words[0] in COMMAND_LETTERS else UNKNOWN_LETTER


def long_line_letter(line: str) -> str:
    first = line.lstrip()[:1]
    return first if first in COMMAND_LETTERS else UNKNOWN_LETTER
Message = Union[Status, Air, Event, Pong, SettingValue, Ok, Err]


def _int(token: str, what: str) -> int:
    if not _INT.match(token):
        raise ProtocolError(f"{what} is not an integer: {token!r}")
    return int(token)


def _num(token: str, what: str) -> float:
    if not _NUM.match(token):
        raise ProtocolError(f"{what} is not a number: {token!r}")
    return float(token)


def _fmt_num(value: float) -> str:
    value = float(value)
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


def _fmt_fixed(value: float, places: int = 2) -> str:
    scale = 10**places
    scaled = math.floor(abs(float(value)) * scale + 0.5)
    whole, fraction = divmod(scaled, scale)
    text = str(whole)
    if fraction:
        text += "." + f"{fraction:0{places}d}".rstrip("0")
    return "-" + text if value < 0 and scaled else text


def _arity(tokens: list[str], count: int, head: str) -> None:
    if len(tokens) != count:
        raise ProtocolError(f"{head} takes {count} values, got {len(tokens)}")


def _in_range(value: int, low: int, high: int, what: str) -> int:
    if not low <= value <= high:
        raise ProtocolError(f"{what} {value} outside {low}..{high}")
    return value


def _clean(line: str) -> str:
    if not isinstance(line, str):
        raise ProtocolError("line is not text")
    text = line.rstrip("\r\n")
    if "\n" in text or "\r" in text:
        raise ProtocolError("embedded newline")
    if len(text) > MAX_LINE:
        raise ProtocolError(f"line longer than {MAX_LINE} characters", "long")
    if not text.isascii():
        raise ProtocolError("line is not ASCII")
    text = text.strip()
    if not text:
        raise ProtocolError("empty line")
    return text


def _emit(text: str) -> str:
    if len(text) > MAX_LINE:
        raise ProtocolError(f"line longer than {MAX_LINE} characters", "long")
    if not text.isascii() or "\n" in text or "\r" in text:
        raise ProtocolError("line must be one line of ASCII")
    return text


def _split(text: str) -> tuple[str, str, list[str]]:
    head, _, rest = text.partition(" ")
    return head, rest.strip(), rest.split()


def format_command(command: Command) -> str:
    if isinstance(command, Drive):
        left = _in_range(int(command.left), -POWER_LIMIT, POWER_LIMIT, "left power")
        right = _in_range(int(command.right), -POWER_LIMIT, POWER_LIMIT, "right power")
        return _emit(f"D {left} {right}")
    if isinstance(command, Speed):
        return _emit(f"M {int(command.left)} {int(command.right)}")
    if isinstance(command, Tilt):
        return _emit(f"T {round(command.degrees)}")
    if isinstance(command, Stop):
        return "X"
    if isinstance(command, Ping):
        if command.n < 0:
            raise ProtocolError("ping number must not be negative")
        return _emit(f"P {int(command.n)}")
    if isinstance(command, Query):
        return "Q"
    if isinstance(command, SetSetting):
        if command.key not in SETTING_KEYS:
            raise ProtocolError(f"unknown setting {command.key!r}", "key")
        value = str(command.value).strip()
        if not value:
            raise ProtocolError(f"setting value is empty; send {EMPTY_VALUE} to clear", "value")
        if command.key in NUMERIC_SETTINGS and not _NUM.match(value):
            raise ProtocolError(f"setting {command.key} needs a number", "value")
        return _emit(f"C {command.key} {value}")
    if isinstance(command, GetSetting):
        if command.key not in SETTING_KEYS:
            raise ProtocolError(f"unknown setting {command.key!r}", "key")
        return f"C {command.key}"
    if isinstance(command, ListSettings):
        return "C ?"
    if isinstance(command, Reboot):
        return "R"
    raise ProtocolError(f"not a command: {command!r}")


def parse_command(line: str) -> Command:
    try:
        return _parse_command(line)
    except ProtocolError as error:
        text = line if isinstance(line, str) else ""
        error.command = long_line_letter(text) if error.reason == "long" else command_letter(text)
        raise


def _parse_command(line: str) -> Command:
    text = _clean(line)
    head, rest, tokens = _split(text)
    if head == "D":
        _arity(tokens, 2, head)
        return Drive(_int(tokens[0], "left power"), _int(tokens[1], "right power"))
    if head == "M":
        _arity(tokens, 2, head)
        return Speed(_int(tokens[0], "left speed"), _int(tokens[1], "right speed"))
    if head == "T":
        _arity(tokens, 1, head)
        return Tilt(_num(tokens[0], "tilt"))
    if head == "X":
        _arity(tokens, 0, head)
        return Stop()
    if head == "P":
        _arity(tokens, 1, head)
        n = _int(tokens[0], "ping")
        if n < 0:
            raise ProtocolError("ping number must not be negative")
        return Ping(n)
    if head == "Q":
        _arity(tokens, 0, head)
        return Query()
    if head == "R":
        _arity(tokens, 0, head)
        return Reboot()
    if head == "C":
        if rest == "?":
            return ListSettings()
        key, _, value = rest.partition(" ")
        value = value.strip()
        if not key:
            raise ProtocolError("C needs a key")
        if key not in SETTING_KEYS:
            raise ProtocolError(f"unknown setting {key!r}", "key")
        if not value:
            return GetSetting(key)
        if key in NUMERIC_SETTINGS and not _NUM.match(value):
            raise ProtocolError(f"setting {key} needs a number", "value")
        return SetSetting(key, value)
    raise ProtocolError(f"unknown command {head!r}", "unknown")


def _event_args(name: str, args: tuple[str, ...]) -> tuple[str, ...]:
    if name in ("edge", "deadman"):
        if args:
            raise ProtocolError(f"event {name} takes no values")
    elif name == "bump":
        if len(args) != 1 or args[0] not in ("L", "R", "B"):
            raise ProtocolError("bump needs L, R or B")
    elif name == "stall":
        if len(args) != 1 or args[0] not in ("L", "R"):
            raise ProtocolError("stall needs L or R")
    elif name == "dock":
        if len(args) != 1 or args[0] not in ("0", "1"):
            raise ProtocolError("dock needs 0 or 1")
    elif name in ("obstacle", "lowbat"):
        if len(args) != 1:
            raise ProtocolError(f"{name} needs one number")
        _int(args[0], name)
    elif name in ("boot", "fault"):
        if not args:
            raise ProtocolError(f"{name} needs a value")
    return args


def format_message(message: Message) -> str:
    if isinstance(message, Status):
        return _emit(
            f"S {message.ms} {message.enc_left} {message.enc_right} {message.front_mm} {message.down_mm} "
            f"{message.bump} {message.dock} {message.pack_mv} {_fmt_num(message.tilt)} {int(message.flags)}"
        )
    if isinstance(message, Air):
        if message.version != AIR_VERSION:
            raise ProtocolError(f"air field set version {message.version} not understood", "unknown")
        if not message.present:
            return _emit(f"A {message.version} {int(message.ms)} {AIR_NONE}")
        if message.humidity_pct is None or message.pressure_pa is None or message.heated_s is None:
            raise ProtocolError("an air reading needs temperature, humidity, pressure and heated seconds")
        gas = -1 if message.gas_ohm is None else int(message.gas_ohm)
        return _emit(
            f"A {message.version} {int(message.ms)} {_fmt_fixed(message.temperature_c)} {_fmt_fixed(message.humidity_pct)} "
            f"{int(message.pressure_pa)} {gas} {int(message.heated_s)}"
        )
    if isinstance(message, Event):
        if message.name not in EVENT_NAMES:
            raise ProtocolError(f"unknown event {message.name!r}", "unknown")
        args = _event_args(message.name, tuple(message.args))
        return _emit(" ".join(("E", message.name) + args))
    if isinstance(message, Pong):
        return _emit(f"p {int(message.n)}")
    if isinstance(message, SettingValue):
        return _emit(f"c {message.key} {message.value}".rstrip())
    if isinstance(message, Ok):
        return "ok"
    if isinstance(message, Err):
        if message.command not in COMMAND_LETTERS + (UNKNOWN_LETTER,) or message.reason not in ERROR_REASONS:
            raise ProtocolError(f"bad error reply {message!r}")
        return _emit(f"err {message.command} {message.reason}")
    raise ProtocolError(f"not a message: {message!r}")


def parse_message(line: str) -> Message:
    text = _clean(line)
    head, rest, tokens = _split(text)
    if head == "S":
        _arity(tokens, 10, head)
        ms = _int(tokens[0], "ms")
        front = _int(tokens[3], "front")
        down = _int(tokens[4], "down")
        bump = _int(tokens[5], "bump")
        dock = _int(tokens[6], "dock")
        pack = _int(tokens[7], "pack")
        flags = _int(tokens[9], "flags")
        if ms < 0 or pack < 0 or flags < 0:
            raise ProtocolError("negative status value")
        if front < -1 or down < -1:
            raise ProtocolError("distance below -1")
        _in_range(bump, 0, 3, "bump")
        _in_range(dock, 0, 1, "dock")
        return Status(
            ms=ms,
            enc_left=_int(tokens[1], "left encoder"),
            enc_right=_int(tokens[2], "right encoder"),
            front_mm=front,
            down_mm=down,
            bump=bump,
            dock=dock,
            pack_mv=pack,
            tilt=_num(tokens[8], "tilt"),
            flags=Flags(flags),
        )
    if head == "A":
        return _parse_air(tokens)
    if head == "E":
        if not tokens:
            raise ProtocolError("event without a name")
        name = tokens[0]
        if name not in EVENT_NAMES:
            raise ProtocolError(f"unknown event {name!r}", "unknown")
        args = tuple(tokens[1:])
        if name in ("boot", "fault"):
            value = rest[len(name):].strip()
            args = (value,) if value else ()
        return Event(name, _event_args(name, args))
    if head == "p":
        _arity(tokens, 1, head)
        return Pong(_int(tokens[0], "pong"))
    if head == "c":
        key, _, value = rest.partition(" ")
        if not _KEY.match(key):
            raise ProtocolError(f"bad setting key {key!r}")
        return SettingValue(key, value.strip())
    if head == "ok":
        _arity(tokens, 0, head)
        return Ok()
    if head == "err":
        _arity(tokens, 2, head)
        if tokens[0] not in COMMAND_LETTERS + (UNKNOWN_LETTER,):
            raise ProtocolError(f"bad command letter in error {tokens[0]!r}")
        if tokens[1] not in ERROR_REASONS:
            raise ProtocolError(f"unknown error reason {tokens[1]!r}")
        return Err(tokens[0], tokens[1])
    raise ProtocolError(f"unknown message {head!r}", "unknown")


def _parse_air(tokens: list[str]) -> Air:
    if len(tokens) < 3:
        raise ProtocolError("air line too short")
    version = _int(tokens[0], "air version")
    if version != AIR_VERSION:
        raise ProtocolError(f"air field set version {version} not understood", "unknown")
    ms = _int(tokens[1], "ms")
    if ms < 0:
        raise ProtocolError("negative air time")
    if tokens[2] == AIR_NONE:
        return Air(ms)
    if len(tokens) < 7:
        raise ProtocolError(f"an air reading takes 7 values, got {len(tokens)}")
    humidity = _num(tokens[3], "humidity")
    pressure = _int(tokens[4], "pressure")
    gas = _int(tokens[5], "gas")
    heated = _int(tokens[6], "heated seconds")
    if not 0.0 <= humidity <= 100.0:
        raise ProtocolError(f"humidity {humidity} outside 0..100")
    if pressure <= 0 or gas < -1 or heated < 0:
        raise ProtocolError("air value out of range")
    return Air(
        ms=ms,
        temperature_c=_num(tokens[2], "temperature"),
        humidity_pct=humidity,
        pressure_pa=pressure,
        gas_ohm=None if gas < 0 else gas,
        heated_s=heated,
    )


def setting_text(key: str, value: str) -> str:
    if key in TEXT_SETTINGS and not str(value).strip():
        return EMPTY_VALUE
    return str(value).strip()


def setting_from_wire(key: str, value: str) -> str:
    return "" if key in TEXT_SETTINGS and value == EMPTY_VALUE else value
