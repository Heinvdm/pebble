import asyncio
import logging
import time

from .firmware import SimFirmware

log = logging.getLogger(__name__)

MAX_SUBSTEP_S = 0.01
MAX_CATCHUP_S = 0.25
MAX_WRITE_BUFFER = 64 * 1024


class SimServer:
    def __init__(self, firmware: SimFirmware | None = None, host: str = "127.0.0.1", port: int = 7777, tick_s: float = 0.01):
        self.firmware = firmware or SimFirmware()
        self.host = host
        self.port = port
        self.tick_s = tick_s
        self._server: asyncio.base_events.Server | None = None
        self._client: asyncio.StreamWriter | None = None
        self._ticker: asyncio.Task | None = None
        self.clients_seen = 0
        self.lines_received: list[str] = []
        self.keep_lines = 2000

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._on_client, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        self._ticker = asyncio.create_task(self._tick_loop(), name="pebble-sim")
        log.info("sim body listening on %s:%d", self.host, self.port)
        return self.port

    async def stop(self) -> None:
        if self._ticker is not None:
            self._ticker.cancel()
            await asyncio.gather(self._ticker, return_exceptions=True)
            self._ticker = None
        client, self._client = self._client, None
        if client is not None:
            client.close()
        if self._server is not None:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), 2.0)
            except asyncio.TimeoutError:
                pass
            self._server = None

    def _write(self, lines: list[str], writer: asyncio.StreamWriter | None = None) -> None:
        target = writer or self._client
        if target is None or target.is_closing() or not lines:
            return
        if target.transport.get_write_buffer_size() > MAX_WRITE_BUFFER:
            log.warning("sim client is not reading; dropping it")
            target.close()
            if self._client is target:
                self._client = None
            return
        target.write("".join(line + "\n" for line in lines).encode("ascii"))

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        previous, self._client = self._client, writer
        if previous is not None:
            previous.close()
        self.clients_seen += 1
        self._write(self.firmware.connected(), writer)
        try:
            while True:
                data = await reader.readline()
                if not data or self._client is not writer:
                    break
                text = data.decode("ascii", errors="replace")
                self.lines_received.append(text.rstrip("\r\n"))
                if len(self.lines_received) > self.keep_lines:
                    del self.lines_received[: self.keep_lines // 2]
                self._write(self.firmware.receive(text), writer)
                if self.firmware.reboot_requested:
                    self.firmware.reboot_requested = False
                    await writer.drain()
                    break
        except (ConnectionError, OSError, ValueError, asyncio.LimitOverrunError):
            pass
        finally:
            if self._client is writer:
                self._client = None
            writer.close()

    async def _tick_loop(self) -> None:
        last = time.monotonic()
        while True:
            await asyncio.sleep(self.tick_s)
            now = time.monotonic()
            elapsed = min(now - last, MAX_CATCHUP_S)
            last = now
            out: list[str] = []
            while elapsed > 1e-6:
                step = min(MAX_SUBSTEP_S, elapsed)
                out.extend(self.firmware.step(step))
                elapsed -= step
            self._write(out)
