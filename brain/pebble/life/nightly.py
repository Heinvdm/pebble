import logging
from datetime import date

from ..blackbox import BlackBox
from ..books import Books
from ..clock import Clock, iso
from ..diary import DIARY, Diary
from ..mind.base import Mind
from ..mind.history import History
from ..seams.later import Dreamer
from ..selfstore import SelfStore
from ..setup import Setup

log = logging.getLogger(__name__)


class Nightly:
    def __init__(self, store: SelfStore, books: Books, history: History, diary: Diary, dreamer: Dreamer, clock: Clock, blackbox: BlackBox, people=None):
        self.people = people
        self.store = store
        self.books = books
        self.history = history
        self.diary = diary
        self.dreamer = dreamer
        self.clock = clock
        self.blackbox = blackbox
        self.setup = False
        self.grow = lambda: []
        self.memory = None
        self.budget = None

    def _values(self) -> dict:
        report = {}
        for moved in self.grow():
            report["nudge" if "raise" in moved else "trait"] = moved
        return report

    def _fold_setup(self, at: str) -> dict:
        setup = Setup.load(self.store)
        if setup.on or setup.folded or not setup.ended:
            return {}
        days = sorted({entry.get("day") for entry in self.store.read_lines(DIARY) if entry.get("setup") and entry.get("day")})
        span = f" over {len(days)} days" if len(days) > 1 else ""
        fact = self.books.memory.remember(f"My first memory: I was put together and tested{span}; it felt strange, but I'm okay.", at)
        fact["pinned"] = True
        self.books.save("memory")
        self.diary.write(f"My first memory: I was put together and tested{span}. It felt strange, but I'm okay.", "first_memory")
        setup.folded = True
        setup.save(self.store)
        return {"setup_folded": len(days)}

    async def run(self, night: str, stage: str, mind: Mind | None) -> dict:
        at = iso(self.clock.now())
        report: dict = {"night": night}
        dream = await self.dreamer.consolidate(self.diary.on_day(night), self.history.summary)
        report["dream"] = dream.note
        for entry in dream.entries:
            self.diary.write(str(entry), "dream")
        if self.people is not None:
            report["people"] = self.people.run(date.fromisoformat(night), stage, at)
        if self.setup:
            report["values"] = "no nudges while being set up"
        else:
            report.update(self._values())
        report.update(self._fold_setup(at))
        expired = self.books.goals.expire()
        report["expired"] = [item.id for item in expired]
        self.books.save("values", "goals")
        if self.history.turns:
            compaction = await self.history.compact(mind, at, everything=True)
            report["folded_turns"] = compaction.folded
        if self.memory is not None:
            try:
                report["memory"] = await self.memory(mind)
            except Exception:
                log.exception("the night's memory work failed")
                report["memory"] = {"error": "failed"}
        if self.budget is not None:
            try:
                line = self.budget(night)
            except Exception:
                log.exception("the day's prompt sizes could not be summed up")
                line = ""
            if line:
                report["budget"] = line
        try:
            report["snapshot"] = str(self.store.snapshot())
        except OSError as error:
            log.error("nightly snapshot failed: %s", error)
            report["snapshot_error"] = str(error)
        self.blackbox.record("nightly", **report)
        return report
