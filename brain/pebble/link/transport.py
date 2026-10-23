import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

DEFAULT_TCP_PORT = 7777
DEFAULT_BAUD = 115200
_ADDRESS = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$|^[0-9A-Fa-f-]{36}$")


class LinkClosed(ConnectionError):
    pass


class TransportUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Closed:
    reason: str


class Transport(ABC):
    label: str = "transport"
    needs_key: bool = False

    @abstractmethod
    async def open(self) -> None: ...

    @abstractmethod
    async def read_line(self) -> str: ...

    @abstractmethod
    async def write_line(self, line: str) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


@dataclass(frozen=True)
class TransportSpec:
    kind: str
    target: str
    port: int | None = None
    baud: int = DEFAULT_BAUD


def parse_spec(spec: str) -> TransportSpec:
    kind, _, rest = spec.strip().partition(":")
    kind = kind.lower()
    if not rest:
        raise ValueError(f"link spec needs a target: {spec!r}")
    if kind == "tcp":
        host, sep, port = rest.rpartition(":")
        if sep and port.isdigit():
            return TransportSpec("tcp", host, int(port))
        return TransportSpec("tcp", rest, DEFAULT_TCP_PORT)
    if kind == "serial":
        device, sep, baud = rest.rpartition("@")
        if sep and baud.isdigit():
            return TransportSpec("serial", device, baud=int(baud))
        return TransportSpec("serial", rest)
    if kind == "ble":
        return TransportSpec("ble", rest)
    raise ValueError(f"unknown link kind {kind!r}; use tcp:, serial: or ble:")


def is_ble_address(text: str) -> bool:
    return bool(_ADDRESS.match(text))


def transport_factory(spec: str) -> Callable[[], Transport]:
    parsed = parse_spec(spec)
    if parsed.kind == "tcp":
        from .tcp import TcpTransport

        return lambda: TcpTransport(parsed.target, parsed.port or DEFAULT_TCP_PORT)
    if parsed.kind == "serial":
        from .serial_link import SerialTransport

        return lambda: SerialTransport(parsed.target, parsed.baud)
    from .ble import BleTransport

    return lambda: BleTransport(parsed.target)
