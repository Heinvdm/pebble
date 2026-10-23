import asyncio
import socket

from .transport import LinkClosed, Transport


class TcpTransport(Transport):
    needs_key = True

    def __init__(self, host: str, port: int, connect_timeout: float = 3.0):
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.label = f"tcp:{host}:{port}"
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def open(self) -> None:
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), self.connect_timeout
        )
        sock = self._writer.get_extra_info("socket")
        if sock is not None:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass

    async def read_line(self) -> str:
        if self._reader is None:
            raise LinkClosed("not open")
        try:
            data = await self._reader.readline()
        except (ConnectionError, OSError, ValueError, asyncio.LimitOverrunError) as error:
            raise LinkClosed(str(error)) from error
        if not data:
            raise LinkClosed("closed by the body")
        return data.decode("ascii", errors="replace").rstrip("\r\n")

    async def write_line(self, line: str) -> None:
        writer = self._writer
        if writer is None or writer.is_closing():
            raise LinkClosed("not open")
        try:
            writer.write((line + "\n").encode("ascii"))
            await writer.drain()
        except (ConnectionError, OSError, RuntimeError) as error:
            raise LinkClosed(str(error)) from error

    async def close(self) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        if writer is None:
            return
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), 1.0)
        except (asyncio.TimeoutError, ConnectionError, OSError, RuntimeError):
            pass
