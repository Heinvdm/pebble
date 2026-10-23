import json
import queue
import threading
from typing import Callable

MAX_QUEUE = 512
CLOSE = None


def encode(event: str, data) -> bytes:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


class Hub:
    def __init__(self, max_queue: int = MAX_QUEUE):
        self.max_queue = max_queue
        self._lock = threading.Lock()
        self._clients: set[queue.Queue] = set()
        self._replay: Callable[[], list[tuple[str, object]]] = lambda: []
        self._extra: list[Callable[[], list[tuple[str, object]]]] = []
        self._closed = False
        self.published = 0

    @property
    def clients(self) -> int:
        with self._lock:
            return len(self._clients)

    @property
    def closed(self) -> bool:
        return self._closed

    def set_replay(self, replay: Callable[[], list[tuple[str, object]]]) -> None:
        self._replay = replay

    def add_replay(self, replay: Callable[[], list[tuple[str, object]]]) -> None:
        self._extra.append(replay)

    def publish(self, event: str, data) -> None:
        message = encode(event, data)
        with self._lock:
            if self._closed:
                return
            self.published += 1
            dropped = []
            for client in self._clients:
                try:
                    client.put_nowait(message)
                except queue.Full:
                    dropped.append(client)
            for client in dropped:
                self._clients.discard(client)
                self._drain_and_close(client)

    def subscribe(self) -> queue.Queue:
        client: queue.Queue = queue.Queue(self.max_queue)
        with self._lock:
            if self._closed:
                client.put_nowait(CLOSE)
                return client
            for source in (self._replay, *self._extra):
                for event, data in source():
                    client.put_nowait(encode(event, data))
            self._clients.add(client)
        return client

    def unsubscribe(self, client: queue.Queue) -> None:
        with self._lock:
            self._clients.discard(client)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            clients, self._clients = self._clients, set()
        for client in clients:
            self._drain_and_close(client)

    @staticmethod
    def _drain_and_close(client: queue.Queue) -> None:
        while True:
            try:
                client.get_nowait()
            except queue.Empty:
                break
        try:
            client.put_nowait(CLOSE)
        except queue.Full:
            pass
