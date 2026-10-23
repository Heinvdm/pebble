import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Callable

from . import qr as codes

log = logging.getLogger(__name__)

MAX_HOLD_S = 30.0
CAPTION_S = 8.0
LINES_PER_PAGE = 10
DEFAULT_HOLD_S = 20.0
MAX_LINES = 60
LINE_CHARS = 60
CAPTION_LINES = 2
CAPTION_CHARS = 90
BADGE_CHARS = 24
MAX_CODE_PAGES = 6
END_SLACK_S = 0.05
KINDS = ("list", "qr", "card")
CAPTION = "caption"
KEEP_SHOWN = 20
ELLIPSIS = "…"


def hold_seconds(value, default: float = DEFAULT_HOLD_S) -> float:
    try:
        hold = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(hold) or hold <= 0:
        return default
    return min(MAX_HOLD_S, hold)


def clean(text, limit: int, keep_end: bool = False) -> str:
    words = " ".join(str("" if text is None else text).split())
    if len(words) <= limit:
        return words
    if keep_end:
        return ELLIPSIS + words[len(words) - limit + 1:].lstrip()
    return words[:limit - 1].rstrip() + ELLIPSIS


def clean_lines(lines, limit: int, keep_end: bool = False) -> list[str]:
    if lines is None:
        return []
    if isinstance(lines, str):
        lines = lines.splitlines()
    return [line for line in (clean(raw, limit, keep_end) for raw in lines) if line]


@dataclass
class _Item:
    id: str
    kind: str
    title: str
    pages: list
    began: float
    hold: float
    page: int = 0
    current: dict | None = None

    @property
    def ends(self) -> float:
        return self.began + self.hold

    def left(self, now: float) -> float:
        return self.ends - now

    def page_at(self, now: float) -> int:
        index = int((now - self.began) * len(self.pages) / self.hold)
        return max(0, min(len(self.pages) - 1, index))

    def message(self, index: int, now: float) -> dict:
        lines, rows = self.pages[index]
        return {
            "op": "show",
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "lines": list(lines),
            "qr": list(rows) if rows else None,
            "hold": round(self.left(now), 2),
            "page": index + 1,
            "pages": len(self.pages),
        }


def _copy(message: dict) -> dict:
    out = dict(message)
    if isinstance(out.get("lines"), list):
        out["lines"] = list(out["lines"])
    if isinstance(out.get("qr"), list):
        out["qr"] = list(out["qr"])
    return out


class TextLayer:
    def __init__(self, publish: Callable[[str, dict], None] | None = None, monotonic: Callable[[], float] = time.monotonic):
        self.publish = publish
        self.monotonic = monotonic
        self.shown: list[dict] = []
        self._lock = threading.Lock()
        self._count = 0
        self._item: _Item | None = None
        self._caption: _Item | None = None
        self._badge: str | None = None

    def _new_id(self) -> str:
        self._count += 1
        return f"text-{self._count}"

    def _remember(self, message: dict) -> None:
        self.shown.append(message)
        del self.shown[:-KEEP_SHOWN]

    def _send(self, data: dict) -> None:
        if self.publish is None:
            log.debug("text layer: %s %s %s", data.get("op"), data.get("id"), data.get("kind", ""))
            return
        try:
            self.publish("text", data)
        except Exception:
            log.exception("text layer publish failed")

    def _codes(self, text) -> list[list[str]]:
        if text is None or not str(text).strip():
            return []
        pieces = codes.parts(str(text))
        if len(pieces) > MAX_CODE_PAGES:
            log.warning("text layer: the code needs %d parts, showing the first %d", len(pieces), MAX_CODE_PAGES)
            pieces = pieces[:MAX_CODE_PAGES]
        made = []
        for piece in pieces:
            try:
                made.append(codes.encode(piece))
            except ValueError:
                log.warning("text layer: a code part could not be made, dropped")
        return made

    def show(self, kind: str, title: str = "", lines=(), qr: str | None = None, hold_s: float = DEFAULT_HOLD_S) -> str:
        if kind not in KINDS:
            raise ValueError(f"unknown text kind: {kind!r}")
        title = clean(title, LINE_CHARS)
        lines = clean_lines(lines, LINE_CHARS)[:MAX_LINES]
        made = self._codes(qr)
        if not (title or lines or made):
            log.debug("text layer: nothing to show")
            return ""
        chunks = [lines[i:i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)]
        count = max(len(chunks), len(made), 1)
        pages = [(chunks[i] if i < len(chunks) else [], made[i] if i < len(made) else None) for i in range(count)]
        hold = hold_seconds(hold_s)
        with self._lock:
            now = self.monotonic()
            item = _Item(self._new_id(), kind, title, pages, now, hold)
            item.current = item.message(0, now)
            self._item = item
            self._remember(item.current)
        self._send(item.current)
        return item.id

    def caption(self, lines) -> str:
        text = clean_lines(lines, CAPTION_CHARS, keep_end=True)[-CAPTION_LINES:]
        if not text:
            with self._lock:
                old, self._caption = self._caption, None
            if old is not None:
                self._send({"op": "clear", "id": old.id})
            return ""
        with self._lock:
            now = self.monotonic()
            item = _Item(self._new_id(), CAPTION, "", [(text, None)], now, CAPTION_S)
            item.current = item.message(0, now)
            self._caption = item
            self._remember(item.current)
        self._send(item.current)
        return item.id

    def badge(self, text: str | None) -> None:
        value = clean(text, BADGE_CHARS) if text is not None else ""
        value = value or None
        with self._lock:
            if value == self._badge:
                return
            self._badge = value
        self._send({"op": "badge", "text": value})

    def clear(self, item_id: str | None = None) -> None:
        with self._lock:
            if item_id is None:
                self._item = None
                self._caption = None
            elif self._item is not None and self._item.id == item_id:
                self._item = None
            elif self._caption is not None and self._caption.id == item_id:
                self._caption = None
            else:
                return
        self._send({"op": "clear", "id": item_id})

    def tick(self) -> None:
        out = []
        with self._lock:
            if self._item is None and self._caption is None:
                return
            now = self.monotonic()
            item = self._item
            if item is not None:
                if item.left(now) < END_SLACK_S:
                    self._item = None
                    out.append({"op": "clear", "id": item.id})
                else:
                    index = item.page_at(now)
                    if index != item.page:
                        item.page = index
                        item.current = item.message(index, now)
                        self._remember(item.current)
                        out.append(item.current)
            caption = self._caption
            if caption is not None and caption.left(now) < END_SLACK_S:
                self._caption = None
                out.append({"op": "clear", "id": caption.id})
        for message in out:
            self._send(message)

    def showing(self) -> dict | None:
        with self._lock:
            item = self._item or self._caption
            return _copy(item.current) if item is not None and item.current is not None else None

    def replay(self) -> list[tuple[str, dict]]:
        events: list[tuple[str, dict]] = []
        with self._lock:
            now = self.monotonic()
            for item in (self._item, self._caption):
                if item is not None and item.left(now) >= END_SLACK_S:
                    events.append(("text", item.message(item.page_at(now), now)))
            if self._badge is not None:
                events.append(("text", {"op": "badge", "text": self._badge}))
        return events


def text_layer_for(face, monotonic: Callable[[], float] = time.monotonic) -> TextLayer:
    hub = getattr(face, "hub", None)
    publish = getattr(hub, "publish", None)
    if not callable(publish):
        return TextLayer(None, monotonic)
    layer = TextLayer(publish, monotonic)
    add_replay = getattr(hub, "add_replay", None)
    if callable(add_replay):
        add_replay(layer.replay)
    return layer
