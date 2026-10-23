import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Callable

from .auth import AuthError, LinkKey, Session, find_key, prove
from .protocol import Command, Err, Message, Ok, Ping, Pong, ProtocolError, SettingValue, format_command, parse_message, reply_kind
from .replies import Listing, Pending, ReplyBook
from .transport import LinkClosed, Transport, TransportUnavailable

log = logging.getLogger(__name__)

FIND_KEY = object()
AUTH_RETRY_S = 5.0


@dataclass(frozen=True)
class LinkUp:
    label: str


@dataclass(frozen=True)
class LinkDown:
    reason: str


class _Subscription:
    def __init__(self, kinds: tuple[type, ...] | None, maxsize: int):
        self.kinds = kinds
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)

    def offer(self, item) -> None:
        if self.kinds is not None and not isinstance(item, self.kinds):
            return
        if self.queue.full():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self.queue.put_nowait(item)


class LinkClient:
    def __init__(
        self,
        factory: Callable[[], Transport],
        ping_every_s: float = 1.0,
        stale_s: float = 2.0,
        backoff: tuple[float, float] = (0.5, 5.0),
        key: LinkKey | None | object = FIND_KEY,
    ):
        self._factory = factory
        self._key = key
        self._session: Session | None = None
        self.proven = False
        self.auth_problem = ""
        self.ping_every_s = ping_every_s
        self.stale_s = stale_s
        self._backoff = backoff
        self._transport: Transport | None = None
        self._connected = asyncio.Event()
        self._subscriptions: list[_Subscription] = []
        self._waiters: list[tuple[Callable[[Message], bool], asyncio.Future]] = []
        self._replies = ReplyBook()
        self._write_lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._ping_n = 0
        self._ping_sent: dict[int, float] = {}
        self.latency_ms: float | None = None
        self.malformed = 0
        self.last_rx = 0.0
        self.label = ""
        self.fatal: str | None = None

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="pebble-link")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        transport, self._transport = self._transport, None
        if transport is not None:
            await transport.close()
        self._connected.clear()

    def subscribe(self, kinds: tuple[type, ...] | None = None, maxsize: int = 500) -> asyncio.Queue:
        subscription = _Subscription(kinds, maxsize)
        self._subscriptions.append(subscription)
        return subscription.queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscriptions = [s for s in self._subscriptions if s.queue is not queue]

    async def wait_connected(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self._connected.wait(), timeout)
        except asyncio.TimeoutError:
            return False
        return True

    def _key_for(self, transport: Transport) -> LinkKey | None:
        if not getattr(transport, "needs_key", False):
            return None
        if self._key is FIND_KEY:
            return find_key()
        return self._key

    def _wire(self, line: str) -> str:
        session = self._session
        return session.seal(line) if session is not None else line

    async def _write(self, command: Command) -> tuple[bool, Pending | None]:
        line = format_command(command)
        transport = self._transport
        if transport is None or not self.connected:
            return False, None
        async with self._write_lock:
            entry = self._replies.expect(command)
            try:
                await transport.write_line(self._wire(line))
            except LinkClosed as error:
                if entry is not None:
                    self._replies.forget(entry)
                log.info("link write failed: %s", error)
                asyncio.create_task(transport.close())
                return False, None
        return True, entry

    async def send(self, command: Command) -> bool:
        sent, _ = await self._write(command)
        return sent

    async def exchange(self, command: Command, timeout: float = 1.0) -> Ok | Err | SettingValue | Listing | None:
        if reply_kind(command) is None:
            raise ValueError(f"{type(command).__name__} has no reply to wait for")
        sent, entry = await self._write(command)
        if not sent or entry is None:
            return None
        try:
            return await asyncio.wait_for(asyncio.shield(entry.future), timeout)
        except asyncio.TimeoutError:
            return None

    async def request(self, command: Command, match: Callable[[Message], bool], timeout: float) -> Message | None:
        future = asyncio.get_running_loop().create_future()
        waiter = (match, future)
        self._waiters.append(waiter)
        try:
            if not await self.send(command):
                return None
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            if waiter in self._waiters:
                self._waiters.remove(waiter)

    def next_ping(self) -> int:
        self._ping_n = (self._ping_n + 1) % 1_000_000
        return self._ping_n

    async def ping(self, timeout: float = 1.0) -> float | None:
        n = self.next_ping()
        started = time.monotonic()
        reply = await self.request(Ping(n), lambda m: isinstance(m, Pong) and m.n == n, timeout)
        if reply is None:
            return None
        return (time.monotonic() - started) * 1000.0

    def _publish(self, item) -> None:
        for subscription in list(self._subscriptions):
            subscription.offer(item)

    def _dispatch(self, message: Message) -> None:
        if isinstance(message, Pong):
            sent = self._ping_sent.pop(message.n, None)
            if sent is not None:
                self.latency_ms = (time.monotonic() - sent) * 1000.0
        elif isinstance(message, (Ok, Err, SettingValue)):
            self._replies.settle(message)
        for match, future in list(self._waiters):
            if not future.done():
                try:
                    if match(message):
                        future.set_result(message)
                except Exception:
                    log.exception("link waiter failed")
        self._publish(message)

    async def _run(self) -> None:
        delay = self._backoff[0]
        while True:
            transport = self._factory()
            try:
                await transport.open()
            except asyncio.CancelledError:
                await transport.close()
                raise
            except TransportUnavailable as error:
                self.fatal = str(error)
                log.error("link unavailable: %s", error)
                self._publish(LinkDown(str(error)))
                return
            except (OSError, LinkClosed, asyncio.TimeoutError) as error:
                log.debug("link connect to %s failed: %s", transport.label, error)
                await transport.close()
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._backoff[1])
                continue
            held: list[str] = []
            key = self._key_for(transport)
            if key is not None:
                try:
                    self._session, held = await prove(transport, key)
                except asyncio.CancelledError:
                    await transport.close()
                    raise
                except (AuthError, LinkClosed, OSError, asyncio.TimeoutError) as error:
                    self.auth_problem = str(error)
                    log.warning("link down: handshake failed with %s: %s", transport.label, error)
                    self._publish(LinkDown(f"handshake failed: {error}"))
                    await transport.close()
                    await asyncio.sleep(max(delay, AUTH_RETRY_S))
                    delay = min(delay * 2, self._backoff[1])
                    continue
                except Exception as error:
                    self.auth_problem = f"the handshake failed: {error}"
                    log.exception("link handshake with %s failed", transport.label)
                    self._publish(LinkDown(self.auth_problem))
                    await transport.close()
                    await asyncio.sleep(max(delay, AUTH_RETRY_S))
                    continue
            self.proven = self._session is not None
            self.auth_problem = ""
            delay = self._backoff[0]
            self._replies.clear()
            self._transport = transport
            self.label = transport.label
            self.last_rx = time.monotonic()
            self._connected.set()
            log.info("link up: %s%s", transport.label, " (the body proved the key)" if self.proven else "")
            self._publish(LinkUp(transport.label))
            for line in held:
                self._take(line, sealed=False)
            reason = "closed"
            try:
                reason = await self._serve(transport)
            finally:
                self._session = None
                self.proven = False
                self._transport = None
                self._connected.clear()
                self._replies.clear()
                await transport.close()
                log.info("link down: %s", reason)
                self._publish(LinkDown(reason))
            await asyncio.sleep(self._backoff[0])

    async def _serve(self, transport: Transport) -> str:
        reader = asyncio.create_task(self._read_loop(transport))
        keeper = asyncio.create_task(self._probe(transport))
        try:
            done, _ = await asyncio.wait({reader, keeper}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (reader, keeper):
                task.cancel()
            await asyncio.gather(reader, keeper, return_exceptions=True)
        for task in done:
            if not task.cancelled() and task.exception() is not None:
                return str(task.exception())
        return "ended"

    def _take(self, line: str, sealed: bool = True) -> None:
        if not line.strip():
            return
        session = self._session if sealed else None
        if session is not None:
            text = session.open(line)
            if text is None:
                self.malformed += 1
                log.debug("line from body without a good tag: %r", line)
                return
            line = text
        self.last_rx = time.monotonic()
        try:
            message = parse_message(line)
        except ProtocolError as error:
            self.malformed += 1
            log.debug("malformed line from body %r: %s", line, error)
            return
        self._dispatch(message)

    async def _read_loop(self, transport: Transport) -> None:
        while True:
            self._take(await transport.read_line())

    async def _probe(self, transport: Transport) -> None:
        while True:
            await asyncio.sleep(self.ping_every_s)
            if time.monotonic() - self.last_rx > self.stale_s:
                raise LinkClosed(f"no data from the body for {self.stale_s:.0f} s")
            n = self.next_ping()
            if len(self._ping_sent) > 50:
                self._ping_sent.clear()
            self._ping_sent[n] = time.monotonic()
            async with self._write_lock:
                await transport.write_line(self._wire(format_command(Ping(n))))
