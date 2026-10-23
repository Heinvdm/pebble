import logging
import math

from ..android.bridge import current
from ..android.mic import hears_to
from ..hearing.highband import HighTones, News, PhoneBand, data_line, heard_line, khz, who_hears

log = logging.getLogger(__name__)

TONES = "hearing/tones.json"
READ_S = 1.0
DAY_HOURS = (8, 21)
LISTEN_S = 120.0
SETTLE_S = 5.0
SAVE_S = 300.0
MOVED_S = 1.0
REPELLERS = "Most pest repellers sit higher than that, so I'd only hear the lower parts of them."


def band_for(bridge=None):
    found = bridge if bridge is not None else current()
    if found is None or not hasattr(found, "highBand"):
        return None
    return PhoneBand(found)


class HighWatch:
    def __init__(self, house, source=None):
        self.house = house
        self.source = source if source is not None else band_for()
        self.tones = HighTones(house.p.store.read(TONES, {}) or {})
        self.read_at = -math.inf
        self.saved_at = house.mono()
        self.waiting: list = []

    def tick(self, now: float, mono: float, quiet: bool) -> None:
        if self.source is None or mono - self.read_at < READ_S:
            return
        self._read(now, mono)
        self._answer_waiting(mono)
        if not quiet and self.by_day(now) and not self.house.alarm_going():
            self._tell(now, mono)
        if mono - self.saved_at >= SAVE_S:
            self.save(mono)

    def _read(self, now: float, mono: float) -> None:
        source = self.source
        self.read_at = mono
        source.moving(self._moving(now))
        rows = source.take(mono)
        if not rows:
            return
        self.tones.feed(rows, mono, now, self.house.where_am_i())
        for heard in rows:
            if heard.what == "start" or (heard.what == "end" and heard.shape in ("data", "beacon", "pulsing")):
                self.house.record("high_tone", what=heard.what, hz=round(heard.hz), shape=heard.shape)

    def by_day(self, now: float) -> bool:
        hour = self.house.clock.local(now).hour
        return DAY_HOURS[0] <= hour < DAY_HOURS[1]

    def _moving(self, now: float) -> bool:
        runner = getattr(self.house.life.commands, "runner", None)
        doing = getattr(runner, "current", None)
        if doing is not None and getattr(doing, "moving", False):
            return True
        telemetry = getattr(getattr(self.house.p, "body", None), "telemetry", None)
        last = getattr(telemetry, "last_motion_at", None)
        return last is not None and now - last <= MOVED_S

    def _tell(self, now: float, mono: float) -> None:
        news = self.tones.news(mono, now)
        if not news:
            return
        house = self.house
        close = house.close_here(now)
        if not close:
            return
        person = close[0]
        for item in news:
            house.teller.to_people(self.news_line(item), [(person.id, person.label)], "high_tone", mono, "")
            self.tones.told(item, now)
            house.record("high_tone_told", hz=round(item.hz), shape=item.kind, to=person.id)
            what = "data tones" if item.kind == "data" else f"a {item.kind} high tone"
            house.note(f"you heard {what} at about {khz(item.hz)} kHz, too high for most adults, and told {person.label}", False)
        self.save(mono)

    def news_line(self, item: News) -> str:
        if item.kind == "data":
            return data_line(item.hz, item.room)
        return f"{heard_line(item.tone)} {who_hears(item.hz)}"

    def reach_line(self) -> str:
        source = self.source
        top = source.top_hz() if source is not None and source.on() else None
        if top is None:
            ladder = self.house.mic()
            top = hears_to(ladder.plan_now) if ladder is not None else None
        if top is None:
            return "I don't know yet how high I can hear on this phone. My owner can ask me to check my microphones."
        return f"On this phone I can hear up to about {khz(top)} kHz. {REPELLERS}"

    def heard_now(self, mono: float) -> str:
        found = self.tones.now(mono)
        others = [k for k in found if not k.own]
        mine = [k for k in found if k.own]
        data = self.tones.data_now(mono)
        parts = []
        if others:
            parts.append(heard_line(others[0]))
            if len(others) > 1:
                parts.append(f"I can hear {len(others) - 1} other high {'tone' if len(others) == 2 else 'tones'} too.")
            parts.append(who_hears(others[0].hz))
        if data is not None:
            parts.append(data_line(data[0], data[1]))
        if not parts:
            parts.append("I can't hear any high tones just now.")
            if mine:
                parts.append(f"There's a faint one at about {khz(mine[0].hz)} kHz, but I think that comes from me.")
            top = self.source.top_hz() if self.source is not None else None
            if top is not None:
                parts.append(f"I can hear up to about {khz(top)} kHz here.")
        return " ".join(parts)

    def answer(self, asker, topic: str = "") -> str:
        source = self.source
        if source is None:
            return "I can't hear sounds that high on this body."
        if topic == "reach":
            return self.reach_line()
        now, mono = self.house.clock.now(), self.house.mono()
        self._read(now, mono)
        if source.on():
            return self.heard_now(mono)
        ladder = self.house.mic()
        if ladder is None:
            return f"I can't hear that high just now, because {source.why_off() or 'my microphone runs at 16 kHz'}."
        ok, why = ladder.listen_wide(LISTEN_S, mono)
        if not ok:
            return f"I can't hear that high just now, because {why}."
        if any(w[0] == asker.id for w in self.waiting):
            return "I'm already listening up high. I'll tell you in a minute or two."
        self.waiting.append((asker.id, asker.label, mono + LISTEN_S + SETTLE_S))
        self.house.record("high_listen", seconds=LISTEN_S, by=asker.id)
        return "I'll listen up high for two minutes and tell you what I hear."

    def _answer_waiting(self, mono: float) -> None:
        due = [w for w in self.waiting if mono >= w[2]]
        if not due:
            return
        self.waiting = [w for w in self.waiting if mono < w[2]]
        if self.source is not None and self.source.on():
            line = self.heard_now(mono)
        else:
            line = "I couldn't switch to my wider hearing just now, so I can't tell you about high tones."
        for person_id, label, _ in due:
            if person_id:
                self.house.teller.to_people(line, [(person_id, label)], "high_tone", mono, "")
            else:
                self.house.teller.to_household(line, "high_tone", mono)

    def save(self, mono: float | None = None) -> None:
        self.saved_at = self.house.mono() if mono is None else mono
        self.tones.forget_old(self.house.clock.now())
        if not self.tones.dirty:
            return
        try:
            self.house.p.store.write(TONES, self.tones.to_dict())
            self.tones.dirty = False
        except Exception:
            log.exception("house: could not save the high tones")

    def status(self) -> dict:
        return {"source": None if self.source is None else self.source.status(), "known": len(self.tones.known), "waiting": len(self.waiting)}
