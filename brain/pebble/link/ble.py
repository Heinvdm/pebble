import asyncio

from .transport import Closed, LinkClosed, Transport, TransportUnavailable, is_ble_address

NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
CHUNK = 20
MAX_BUFFER = 512


class BleTransport(Transport):
    needs_key = True

    def __init__(self, target: str = "Pebble", scan_timeout: float = 8.0):
        self.target = target
        self.scan_timeout = scan_timeout
        self.label = f"ble:{target}"
        self._client = None
        self._queue: asyncio.Queue | None = None
        self._buffer = bytearray()

    async def open(self) -> None:
        try:
            from bleak import BleakClient, BleakScanner
        except ImportError as error:
            raise TransportUnavailable("bleak is not installed (pip install bleak)") from error
        self._queue = asyncio.Queue()
        self._buffer = bytearray()
        if is_ble_address(self.target):
            device = self.target
        else:
            device = await BleakScanner.find_device_by_name(self.target, timeout=self.scan_timeout)
            if device is None:
                raise LinkClosed(f"no BLE device named {self.target}")
        self._client = BleakClient(device, disconnected_callback=self._on_disconnect)
        try:
            await self._client.connect()
            await self._client.start_notify(NUS_TX, self._on_notify)
        except Exception as error:
            raise LinkClosed(str(error)) from error

    def _on_notify(self, _sender, data: bytearray) -> None:
        self._buffer.extend(data)
        while b"\n" in self._buffer:
            line, _, rest = bytes(self._buffer).partition(b"\n")
            self._buffer = bytearray(rest)
            self._queue.put_nowait(line.decode("ascii", errors="replace").rstrip("\r"))
        if len(self._buffer) > MAX_BUFFER:
            self._buffer.clear()

    def _on_disconnect(self, _client) -> None:
        if self._queue is not None:
            self._queue.put_nowait(Closed("BLE disconnected"))

    async def read_line(self) -> str:
        if self._queue is None:
            raise LinkClosed("not open")
        item = await self._queue.get()
        if isinstance(item, Closed):
            raise LinkClosed(item.reason)
        return item

    async def write_line(self, line: str) -> None:
        if self._client is None:
            raise LinkClosed("not open")
        payload = (line + "\n").encode("ascii")
        try:
            for start in range(0, len(payload), CHUNK):
                await self._client.write_gatt_char(NUS_RX, payload[start : start + CHUNK], response=False)
        except Exception as error:
            raise LinkClosed(str(error)) from error

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        try:
            await client.disconnect()
        except Exception:
            pass
