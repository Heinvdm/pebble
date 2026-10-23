import asyncio
import logging

from ..android.mic import hears_to, probe_words, wide_verdict
from ..clock import iso
from ..hearing.tvcheck import CHECKS, TvCheck, tv_passed

log = logging.getLogger(__name__)


def times(n: int) -> str:
    return "once" if n == 1 else ("twice" if n == 2 else f"{n} times")


class HearingChecks:
    def __init__(self, house):
        self.house = house
        self.tv: TvCheck | None = None
        self.probe_task = None
        self.tv_task = None
        self.tv_ok = self.passed()

    def passed(self) -> bool:
        try:
            return tv_passed(self.house.p.store.read(CHECKS, {}) or {})
        except Exception:
            return False

    def _start(self, coro):
        try:
            task = asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            coro.close()
            return None
        task.add_done_callback(self._done)
        return task

    def _done(self, task) -> None:
        if not task.cancelled() and task.exception() is not None:
            log.error("house: a hearing check failed", exc_info=task.exception())

    def _keywords(self):
        phone = getattr(getattr(self.house.p, "conversation", None), "phone", None)
        if phone is None or not hasattr(phone, "last"):
            return None
        return lambda: (getattr(phone, "last", None) or {}).get("keyword")

    def _busy(self) -> str:
        ladder = self.house.mic()
        if ladder is not None and ladder.probing or (self.probe_task is not None and not self.probe_task.done()):
            return "I'm measuring my microphones just now. Ask me again in a few minutes."
        if self.tv is not None and self.tv.running:
            return "I'm in the middle of the television check. Say \"stop the television check\" if you need me to stop it."
        return ""

    def start_probe(self, asker) -> str:
        house = self.house
        if house.p.permissions.quiet:
            return "Not in my quiet time. The check plays some clicks and a quiet whistle."
        if house.alarm_going():
            return "Not while an alarm is going."
        ladder = house.mic()
        if ladder is None:
            return "I can't measure my microphones on this body."
        busy = self._busy()
        if busy:
            return busy
        self.probe_task = self._start(self._probe(ladder, asker.id, asker.label))
        house.note(f"{asker.label} asked you to measure your microphones; it takes about four minutes and plays clicks and a quiet whistle", False)
        return "Okay. It takes about four minutes, and I'll play some clicks and a quiet whistle. Carry on as normal."

    async def _probe(self, ladder, person_id, label: str) -> None:
        house = self.house
        result = await ladder.probe()
        line = probe_words(result)
        ok, _ = wide_verdict({"probe": result})
        clicks = result.get("clicks") if isinstance(result.get("clicks"), dict) else {}
        top = hears_to({"probe": result})
        house.record("mic_probe", wide=ok, hears_to_hz=top, two_microphones=bool(clicks.get("two_separate_microphones")), spacing_m=clicks.get("spacing_m"), problem=str(result.get("problem") or "")[:120])
        house.diary(f"I measured my microphones for {label}." + (f" I can hear up to about {round(top / 1000)} kHz." if top else ""))
        if person_id:
            house.teller.to_people(line, [(person_id, label)], "mic_probe", house.mono(), "my microphone check finished")
        else:
            house.teller.to_household(line, "mic_probe", house.mono())

    def start_tv(self, asker) -> str:
        house = self.house
        if house.p.permissions.quiet:
            return "Not in my quiet time. The check needs half an hour of ordinary television."
        ladder = house.mic()
        keywords = self._keywords()
        if ladder is None or keywords is None:
            return "The television check needs the phone's ears."
        busy = self._busy()
        if busy:
            return busy
        self.tv = TvCheck(ladder.set_gain, keywords, house.mono)
        ladder.gain_hold = True
        self.tv_task = self._start(self._tv(ladder, asker.id, asker.label))
        house.note(f"{asker.label} started the television check: half an hour of counting how often you think you hear your name", False)
        return "Okay. Put the television on as usual, and please don't call my name for half an hour. I'll count how often I think I hear it, with and without listening harder for my name."

    def stop_tv(self, why: str = "someone asked me to stop") -> str:
        if self.tv is None or not self.tv.running:
            return "We weren't doing the television check."
        self.tv.stop(why)
        return "Okay, I've stopped the television check. Nothing changes."

    async def _tv(self, ladder, person_id, label: str) -> None:
        house = self.house
        try:
            result = await self.tv.run()
        finally:
            ladder.gain_hold = False
        house.record("tv_check", **result)
        if result.get("stopped"):
            house.note(f"the television check stopped early ({result['stopped']}); nothing changed", False)
            return
        record = dict(result, at=iso(house.clock.now()))
        try:
            checks = dict(house.p.store.read(CHECKS, {}) or {})
            checks["format"] = 1
            checks["tv"] = record
            house.p.store.write(CHECKS, checks)
        except Exception:
            log.exception("house: could not keep the television check")
        ladder.gain_checked = self.tv_ok = bool(result["passed"])
        ladder.checked_at = float("-inf")
        off, on = result["false_off"], result["false_on"]
        heard = f"I thought I heard my name {times(off)} without listening harder, and {times(on)} with it" if off or on else "I never thought I heard my name, with or without listening harder"
        line = f"The television check is done. {heard}, so I'll {'keep listening harder for my name' if result['passed'] else 'leave that off'}."
        house.diary(f"I did the television check: {off} without, {on} with listening harder for my name.")
        if person_id:
            house.teller.to_people(line, [(person_id, label)], "tv_check", house.mono(), "the television check finished")
        else:
            house.teller.to_household(line, "tv_check", house.mono())

    def tick(self, quiet: bool) -> None:
        if quiet and self.tv is not None and self.tv.running:
            self.tv.stop("my quiet time began")

    def status(self) -> dict:
        return {"tv": None if self.tv is None else self.tv.status(), "tv_passed": self.tv_ok}
