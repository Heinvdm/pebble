import asyncio
import logging
from typing import Callable

from .base import Activity, Ending
from .kit import Kit

log = logging.getLogger(__name__)


class Runner:
    def __init__(self, kit: Kit, on_end: Callable[[Activity, Ending], None] = lambda act, ending: None):
        self.kit = kit
        self.on_end = on_end
        self.on_start: Callable[[Activity], None] = lambda activity: None
        self.current: Activity | None = None
        self.task: asyncio.Task | None = None
        self.history: list[tuple[Activity, Ending]] = []

    @property
    def busy(self) -> bool:
        return self.current is not None

    def busy_reason(self) -> str | None:
        if self.current is None:
            return None
        return f"you are busy {self.current.describe()}; end or change that activity first"

    def running(self):
        return self.current.running() if self.current is not None else None

    def start(self, activity: Activity) -> None:
        try:
            self.on_start(activity)
        except Exception:
            log.exception("noting the start of %s failed", activity.kind)
        previous = self.current
        if previous is not None:
            how = "updated" if previous.kind == activity.kind and previous.asker.id == activity.asker.id else "replaced"
            self._cancel(previous, Ending(how, f"you stopped {previous.describe()} to start {activity.describe()}"))
        self.current = activity
        activity.started_at = self.kit.pace.now()
        activity._began = False
        activity._reported = False
        self.task = asyncio.ensure_future(self._run(activity))
        activity._task = self.task

    def end(self, how: str, text: str, say: str = "") -> Activity | None:
        current = self.current
        if current is None:
            return None
        self._cancel(current, Ending(how, text, say))
        self.current = None
        return current

    def _cancel(self, activity: Activity, ending: Ending) -> None:
        if activity.cause is None:
            activity.cause = ending
        task = getattr(activity, "_task", None)
        if task is not None and not task.done():
            task.cancel()
            if not getattr(activity, "_began", True):
                self._report(activity, activity.cause)

    def _report(self, activity: Activity, ending: Ending) -> None:
        if getattr(activity, "_reported", False):
            return
        activity._reported = True
        if self.current is activity:
            self.current = None
        self.history.append((activity, ending))
        del self.history[:-20]
        try:
            self.on_end(activity, ending)
        except Exception:
            log.exception("reporting the end of %s failed", activity.kind)

    async def _run(self, activity: Activity) -> None:
        activity._began = True
        ending: Ending | None = None
        try:
            if activity.delay > 0.0:
                await self.kit.pace.sleep(activity.delay)
            ending = await activity.run(self.kit)
        except asyncio.CancelledError:
            ending = activity.cause or Ending("stopped", f"you stopped {activity.describe()}")
        except Exception as error:
            log.exception("activity %s failed", activity.kind)
            ending = Ending("failed", f"{activity.describe()} went wrong inside ({error})", "Oops, something went wrong.")
        finally:
            if activity.moving or activity.kind in ("look",):
                try:
                    await self.kit.body.drive(0, 0)
                except Exception:
                    log.exception("could not stop the wheels after %s", activity.kind)
        if activity.cause is not None and ending is not activity.cause and ending.how not in ("done",):
            ending = activity.cause
        self._report(activity, ending)

    async def wait_idle(self, timeout: float | None = None) -> None:
        task = self.task
        if task is not None and not task.done():
            await asyncio.wait({task}, timeout=timeout)

    async def close(self) -> None:
        current = self.end("stopped", "you were shutting down")
        task = self.task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if current is not None:
            log.info("stopped %s on shutdown", current.kind)
