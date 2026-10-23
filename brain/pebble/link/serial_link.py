import asyncio
import threading

from .transport import Closed, LinkClosed, Transport, TransportUnavailable

MAX_BUFFER = 512


class SerialTransport(Transport):
    needs_key = True

    def __init__(self, device: str, baud: int = 115200):
        self.device = device
        self.baud = baud
        self.label = f"serial:{device}@{baud}"
        self._serial = None
        self._queue: asyncio.Queue | None = None
        self._alive = False
        self._thread: threading.Thread | None = None

    async def open(self) -> None:
        try:
            import serial
        except ImportError as error:
            raise TransportUnavailable("pyserial is not installed (pip install pyserial)") from error
        try:
            self._serial = await asyncio.to_thread(serial.Serial, self.device, self.baud, timeout=0.2)
        except (OSError, ValueError, serial.SerialException) as error:
            raise LinkClosed(str(error)) from error
        self._queue = asyncio.Queue()
        self._alive = True
        loop = asyncio.get_running_loop()
        self._thread = threading.Thread(target=self._read_forever, args=(loop,), daemon=True)
        self._thread.start()

    def _deliver(self, loop: asyncio.AbstractEventLoop, item) -> None:
        try:
            loop.call_soon_threadsafe(self._queue.put_nowait, item)
        except RuntimeError:
            self._alive = False

    def _read_forever(self, loop: asyncio.AbstractEventLoop) -> None:
        buffer = bytearray()
        try:
            while self._alive:
                chunk = self._serial.read(256)
                if not chunk:
                    continue
                buffer.extend(chunk)
                while b"\n" in buffer:
                    line, _, rest = bytes(buffer).partition(b"\n")
                    buffer = bytearray(rest)
                    self._deliver(loop, line.decode("ascii", errors="replace").rstrip("\r"))
                if len(buffer) > MAX_BUFFER:
                    buffer.clear()
        except Exception as error:
            self._deliver(loop, Closed(str(error)))

    async def read_line(self) -> str:
        if self._queue is None:
            raise LinkClosed("not open")
        item = await self._queue.get()
        if isinstance(item, Closed):
            raise LinkClosed(item.reason)
        return item

    async def write_line(self, line: str) -> None:
        if self._serial is None:
            raise LinkClosed("not open")
        try:
            await asyncio.to_thread(self._serial.write, (line + "\n").encode("ascii"))
        except Exception as error:
            raise LinkClosed(str(error)) from error

    async def close(self) -> None:
        self._alive = False
        port, self._serial = self._serial, None
        if port is not None:
            try:
                await asyncio.to_thread(port.close)
            except Exception:
                pass
