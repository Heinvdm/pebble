import json
import logging
import os
import queue
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import unquote

from ..screen.elements import registry_dict
from ..seams.face import Touch
from .hub import CLOSE, Hub

log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
PAGE = HERE / "page.html"
WORKER = HERE / "eyes_worker.js"
TEXT_LAYER = HERE / "text_layer.js"
REGISTRY_MARK = "__PEBBLE_REGISTRY__"
EYES_MARK = "__PEBBLE_EYES__"
KEEP_ALIVE_S = 15.0
MAX_BODY = 2048
PAD_KINDS = ("drive", "tilt", "face", "stop")
PAD_FACES = ("happy", "sad", "surprised", "love", "curious", "sleepy", "neutral")
MAX_SEE_BODY = 16384
DRAIN_MAX = 1 << 20
LOOPBACK = ("127.0.0.1", "localhost", "::1", "[::1]")
CSP = "default-src 'none'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; worker-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; media-src 'self' blob: mediastream:; base-uri 'none'; form-action 'none'"
ROUTE_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'"
WORKER_CSP = "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'"
NO_EYES = {"camera": False}
VENDOR_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".wasm": "application/wasm",
    ".tflite": "application/octet-stream",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".md": "text/plain; charset=utf-8",
    "": "text/plain; charset=utf-8",
}


def _script_json(data) -> str:
    return json.dumps(data, separators=(",", ":")).replace("</", "<\\/")


def render_page(template: str | None = None, eyes: dict | None = None) -> bytes:
    text = template if template is not None else PAGE.read_text(encoding="utf-8")
    text = text.replace(REGISTRY_MARK, _script_json(registry_dict()))
    return text.replace(EYES_MARK, _script_json(eyes or NO_EYES)).encode("utf-8")


def pad_command(data) -> dict | None:
    if not isinstance(data, dict):
        return None
    kind = data.get("kind")
    if kind not in PAD_KINDS:
        return None
    if kind == "drive":
        values = []
        for key in ("x", "y"):
            value = data.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value != value or value in (float("inf"), float("-inf")):
                return None
            values.append(max(-1.0, min(1.0, float(value))))
        return {"kind": "drive", "x": round(values[0], 3), "y": round(values[1], 3)}
    if kind == "tilt":
        way = data.get("way")
        return {"kind": "tilt", "way": way} if way in ("up", "down") else None
    if kind == "face":
        expression = data.get("expression")
        return {"kind": "face", "expression": expression} if expression in PAD_FACES else None
    return {"kind": "stop"}


def vendor_file(vendor: Path, path: str) -> Path | None:
    name = unquote(path)
    if not name or "\\" in name or "\x00" in name or name.startswith("/") or ":" in name:
        return None
    if any(part in ("", ".", "..") for part in name.split("/")):
        return None
    root = vendor.resolve()
    target = (root / name).resolve()
    if not target.is_relative_to(root) or not target.is_file() or target.name.startswith("."):
        return None
    if target.suffix not in VENDOR_TYPES:
        return None
    return target


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"
    block_on_close = False


class FaceServer:
    def __init__(
        self,
        hub: Hub,
        host: str = "127.0.0.1",
        port: int = 8765,
        on_touch: Callable[[Touch], None] | None = None,
        state: Callable[[], dict] | None = None,
        page: bytes | None = None,
        eyes=None,
        routes: dict | None = None,
        on_pad: Callable[[dict], None] | None = None,
    ):
        self.hub = hub
        self.on_pad = on_pad or (lambda command: None)
        self.routes = dict(routes or {})
        self.host = host
        self.port = port
        self.on_touch = on_touch or (lambda touch: None)
        self.state = state or (lambda: {})
        self.eyes = eyes
        self.page = page if page is not None else render_page(eyes=eyes.page_config() if eyes is not None else None)
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        host = self.host if self.host not in ("0.0.0.0", "", "::") else "127.0.0.1"
        host = f"[{host}]" if ":" in host and not host.startswith("[") else host
        return f"http://{host}:{self.port}/"

    def _allowed_hosts(self) -> set[str] | None:
        if self.host not in LOOPBACK:
            return None
        return {f"{name}:{self.port}" for name in ("127.0.0.1", "localhost", "[::1]")} | {"127.0.0.1", "localhost"}

    def start(self) -> int:
        handler = _handler_for(self)
        self._server = _Server((self.host, self.port), handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.2}, name="pebble-face-server", daemon=True)
        self._thread.start()
        log.info("face page: %s", self.url)
        return self.port

    def stop(self) -> None:
        self.hub.close()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


def _handler_for(owner: FaceServer):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PebbleFace/1"
        protocol_version = "HTTP/1.0"

        def log_message(self, fmt, *args):
            log.debug("face page %s - %s", self.address_string(), fmt % args)

        def _host_ok(self) -> bool:
            allowed = owner._allowed_hosts()
            if allowed is None:
                return True
            return (self.headers.get("Host") or "").lower() in allowed

        def _send(self, code: int, body: bytes = b"", content_type: str = "text/plain; charset=utf-8", extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if body and self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, b"forbidden")
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                return self._send(200, owner.page, "text/html; charset=utf-8", {"Content-Security-Policy": CSP, "Referrer-Policy": "no-referrer"})
            if path == "/events":
                return self._events()
            if path == "/elements.json":
                return self._send(200, json.dumps(registry_dict()).encode("utf-8"), "application/json")
            if path == "/state":
                return self._send(200, json.dumps(owner.state(), default=str).encode("utf-8"), "application/json")
            if path == "/health":
                return self._send(200, b'{"status":"ok"}', "application/json")
            if path == "/text_layer.js":
                return self._file(TEXT_LAYER, VENDOR_TYPES[".js"], {})
            if path in owner.routes:
                return self._route(owner.routes[path])
            if owner.eyes is not None and path == "/eyes_worker.js":
                return self._file(WORKER, VENDOR_TYPES[".js"], {"Content-Security-Policy": WORKER_CSP})
            if owner.eyes is not None and path.startswith("/vendor/"):
                target = vendor_file(owner.eyes.vendor, path[len("/vendor/"):])
                if target is None:
                    return self._send(404, b"not found")
                return self._file(target, VENDOR_TYPES[target.suffix], {"Cache-Control": "public, max-age=604800, immutable", "Content-Security-Policy": WORKER_CSP})
            return self._send(404, b"not found")

        def do_HEAD(self):
            return self.do_GET()

        def _route(self, make) -> None:
            try:
                content_type, body = make()
            except Exception:
                log.exception("face page route failed")
                return self._send(500, b"failed")
            return self._send(200, body, content_type, {"Content-Security-Policy": ROUTE_CSP, "Referrer-Policy": "no-referrer"})

        def _file(self, target: Path, content_type: str, extra: dict) -> None:
            try:
                handle = open(target, "rb")
            except OSError:
                return self._send(404, b"not found")
            with handle:
                headers = {"Content-Type": content_type, "Content-Length": str(os.fstat(handle.fileno()).st_size), "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", **extra}
                self.send_response(200)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                if self.command == "HEAD":
                    return
                try:
                    shutil.copyfileobj(handle, self.wfile, 1 << 16)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return

        def _drain(self) -> None:
            try:
                left = min(int(self.headers.get("Content-Length") or 0), DRAIN_MAX)
                while left > 0:
                    chunk = self.rfile.read(min(left, 65536))
                    if not chunk:
                        return
                    left -= len(chunk)
            except (ValueError, OSError):
                return

        def _read_json(self, limit: int):
            if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
                self._drain()
                self._send(415, b"json only")
                return None
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._send(400, b"bad length")
                return None
            if length <= 0 or length > limit:
                self._drain()
                self._send(413 if length > limit else 400, b"bad length")
                return None
            try:
                return (json.loads(self.rfile.read(length).decode("utf-8")),)
            except (UnicodeDecodeError, ValueError):
                self._send(400, b"bad json")
                return None

        def do_POST(self):
            if not self._host_ok():
                self._drain()
                return self._send(403, b"forbidden")
            path = self.path.split("?", 1)[0]
            if path == "/touch":
                return self._touch()
            if path == "/pad":
                return self._pad()
            if path == "/see" and owner.eyes is not None:
                return self._see()
            if path == "/eyes" and owner.eyes is not None:
                return self._eyes()
            self._drain()
            return self._send(404, b"not found")

        def _touch(self) -> None:
            body = self._read_json(MAX_BODY)
            if body is None:
                return
            touch = Touch.from_dict(body[0])
            if touch is None:
                return self._send(400, b"bad touch")
            try:
                owner.on_touch(touch)
            except Exception:
                log.exception("touch handler failed")
            return self._send(204)

        def _pad(self) -> None:
            body = self._read_json(MAX_BODY)
            if body is None:
                return
            command = pad_command(body[0])
            if command is None:
                return self._send(400, b"bad pad")
            try:
                owner.on_pad(command)
            except Exception:
                log.exception("pad handler failed")
            return self._send(204)

        def _see(self) -> None:
            body = self._read_json(MAX_SEE_BODY)
            if body is None:
                return
            try:
                taken = owner.eyes.seen(body[0])
            except ValueError as error:
                return self._send(400, f"bad sight: {error}".encode("utf-8"))
            return self._send(204) if taken else self._send(409, b"eyes are off")

        def _eyes(self) -> None:
            body = self._read_json(MAX_BODY)
            if body is None:
                return
            try:
                owner.eyes.report(body[0])
            except ValueError as error:
                return self._send(400, f"bad report: {error}".encode("utf-8"))
            return self._send(204)

        def _events(self) -> None:
            client = owner.hub.subscribe()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                self.wfile.write(b"retry: 1500\n\n")
                self.wfile.flush()
                while True:
                    try:
                        message = client.get(timeout=KEEP_ALIVE_S)
                    except queue.Empty:
                        message = b": ping\n\n"
                    if message is CLOSE:
                        return
                    self.wfile.write(message)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return
            finally:
                owner.hub.unsubscribe(client)
                self.close_connection = True

    return Handler
