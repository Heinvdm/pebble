import logging
import time
import urllib.parse
import urllib.request
from collections import deque
from typing import Callable

log = logging.getLogger(__name__)

TIMEOUT_S = 10.0
PER_HOUR = 6
MAX_CHARS = 400
USER_AGENT = "pebble-notice/1 (personal robot)"


class NoNotifier:
    enabled = False

    def send(self, title: str, text: str) -> bool:
        return False

    def info(self) -> dict:
        return {"kind": "off"}


def _plain(text: str, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


def check_url(url: str) -> str:
    parts = urllib.parse.urlsplit(str(url or "").strip())
    if parts.scheme not in ("https", "http") or not parts.netloc or not parts.path.strip("/"):
        raise ValueError("the notice address must look like https://ntfy.sh/your-own-topic")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("the notice address must be a plain topic address, with no name, password or extra parts in it")
    return parts.geturl()


class NtfyNotifier:
    enabled = True

    def __init__(self, url: str, token: str = "", opener: Callable | None = None, clock: Callable[[], float] = time.monotonic, per_hour: int = PER_HOUR):
        self.url = check_url(url)
        self.token = str(token or "")
        self.opener = opener or urllib.request.urlopen
        self.clock = clock
        self.per_hour = per_hour
        self.sent: deque = deque()
        self.failures = 0
        self.problem = ""

    def send(self, title: str, text: str) -> bool:
        now = self.clock()
        while self.sent and now - self.sent[0] > 3600.0:
            self.sent.popleft()
        if len(self.sent) >= self.per_hour:
            log.warning("safety: notice not sent, %d already this hour", self.per_hour)
            return False
        headers = {"Title": _plain(title, 80).encode("ascii", "replace").decode("ascii"), "Priority": "high", "Tags": "warning", "User-Agent": USER_AGENT, "Content-Type": "text/plain; charset=utf-8"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.url, data=_plain(text, MAX_CHARS).encode("utf-8"), headers=headers, method="POST")
        try:
            with self.opener(request, timeout=TIMEOUT_S) as response:
                ok = 200 <= getattr(response, "status", 200) < 300
        except Exception as error:
            ok = False
            self.problem = str(error)
        if ok:
            self.sent.append(now)
            self.problem = ""
        else:
            self.failures += 1
            log.warning("safety: the notice could not be sent: %s", self.problem or "refused")
        return ok

    def info(self) -> dict:
        host = urllib.parse.urlsplit(self.url).netloc
        return {"kind": "ntfy", "host": host, "sent_this_hour": len(self.sent), "failures": self.failures, "problem": self.problem}


def notifier_from(config: dict | None, **options):
    config = dict(config or {})
    if config.get("kind") != "ntfy" or not config.get("url"):
        return NoNotifier()
    try:
        return NtfyNotifier(config["url"], config.get("token", ""), **options)
    except ValueError as error:
        log.warning("safety: notices stay off: %s", error)
        return NoNotifier()
