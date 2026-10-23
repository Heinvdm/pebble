import asyncio
import itertools
import logging
import math
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from ..clock import Clock, iso
from .notice import HIGH, LOW, MEDIUM, Kind, Notice, kind_of
from .words import Reading

log = logging.getLogger(__name__)

SURE = 0.85
ALARM_CONFIDENCE = 0.8
WONDER_CONFIDENCE = 0.55
HINTS = ("heat_rise", "gas_spike", "smoke_seen")
CHECK_S = 12.0
ASK_S = 15.0
HELP_ASK_S = 20.0
STOPPED_S = 12.0
SOUNDING = ("smoke_alarm", "co_alarm", "alarm_beeping", "alarm_sound")
END_AFTER_S = 180.0
HELP_ALARM_S = 600.0
WONDER_KEEP_S = 60.0
LINE_EVERY_S = 20.0
SIREN_ON_S = 8.0
SIREN_GAP_S = 4.0
NOTIFY_AFTER_S = 60.0
RESEEK_S = 120.0
SNOOZE_S = 600.0
REGRACE_S = 30.0
CONFIRM_S = 20.0
NEVER_SNOOZED = ("help",)
CONFIRM = {"help": "Are you sure you're all right?"}
CONFIRM_LINE = "Is it really fine?"
UNSEEN_LINE = "I need to see you to stop. Come where I can see you, and tell me again."
REFUSED_LINE = "Thanks. I'll keep going until someone I know well tells me it's fine."
QUIET_MUTE_S = 120.0
FRESH_S = {"fire": 60.0, "co": 60.0, "help": 60.0, "quake": 15.0}
QUAKE_CALM_S = 15.0
QUAKE_HOLD_S = 30.0
LONG_QUAKE_S = 60.0
STRONG_QUAKE = ("strong shaking", "very strong shaking")
TELL_WAIT_S = 1800.0
LOOK_NOTICE_KEEP_S = 600.0
TEST_S = 600.0
TEST_REAL_S = 30.0
TRUSTED = ("trusted", "inner circle")
KNOWN = ("friend", "trusted", "inner circle")
ORDER = {HIGH: 0, MEDIUM: 1, LOW: 2}


@dataclass
class Ports:
    clock: Clock
    say: Callable[[str, bool], Awaitable]
    siren: Callable[[bool], None]
    face_alarm: Callable[[str], None]
    face_show: Callable[[str], None]
    note: Callable[[str, bool], None]
    diary: Callable[[str, str], None]
    record: Callable[..., None]
    rouse: Callable[[str], None] = lambda why: None
    seek: Callable[[str, Callable[[str, str], None]], bool] = lambda why, done: False
    end_seek: Callable[[str], None] = lambda why: None
    stop_wheels: Callable[[], None] = lambda: None
    felt: Callable[[str, str], None] = lambda kind, text: None
    tier_of: Callable[[str | None], str] = lambda person: "stranger"
    label_of: Callable[[str | None], str] = lambda person: "someone"
    owner_of: Callable[[str | None], bool] = lambda person: False
    trusted_here: Callable[[], list] = lambda: []
    anyone_here: Callable[[], bool] = lambda: False
    notify: Callable[[str, str], None] = lambda title, text: None
    notify_on: Callable[[], bool] = lambda: False
    check_round: Callable[[str, Callable[[dict], None]], bool] = lambda why, done: False
    tsunami_zone: Callable[[], bool] = lambda: False


@dataclass
class Incident:
    id: int
    family: str
    plan: str
    severity: str
    kind: Kind
    began: float
    step: str = "check"
    since: float = 0.0
    evidence: dict = field(default_factory=dict)
    person: str | None = None
    asks: int = 0
    seeking: bool = False
    seek_result: tuple | None = None
    seek_spoken: bool = False
    seek_at: float = -math.inf
    notified: bool = False
    siren: bool = False
    siren_since: float = -math.inf
    line_at: float = -math.inf
    muted_until: float = -math.inf
    found: str | None = None
    refused_said: bool = False
    peak: float = 0.0
    details: dict = field(default_factory=dict)
    ended: str = ""
    test: bool = False
    confirm: tuple | None = None

    def confidence(self, mono: float) -> float:
        keep = FRESH_S.get(self.family, 300.0)
        miss = 1.0
        for confidence, at in self.evidence.values():
            if mono - at <= keep:
                miss *= 1.0 - max(0.0, min(0.99, confidence))
        return 1.0 - miss

    def stopped(self, mono: float) -> bool:
        sounding = [at for name, (_, at) in self.evidence.items() if name in SOUNDING]
        if not sounding or mono - max(sounding) < STOPPED_S:
            return False
        miss = 1.0
        for name, (confidence, at) in self.evidence.items():
            if name not in SOUNDING and mono - at <= FRESH_S.get(self.family, 300.0):
                miss *= 1.0 - max(0.0, min(0.99, confidence))
        return 1.0 - miss < ALARM_CONFIDENCE

    def last_evidence(self) -> float:
        return max((at for _, at in self.evidence.values()), default=self.began)

    def lead(self) -> Kind:
        best = max(self.evidence.items(), key=lambda item: item[1][0], default=None)
        return kind_of(best[0]) or self.kind if best else self.kind


_ids = itertools.count(1)


def quake_length(seconds: float) -> str:
    if seconds < 10:
        return "a few seconds"
    if seconds < 55:
        return f"about {int(5 * round(seconds / 5))} seconds"
    if seconds < 75:
        return "about a minute"
    if seconds < 105:
        return "about a minute and a half"
    return f"about {round(seconds / 60)} minutes"


def tsunami_line(long: bool, strong: bool) -> str:
    what = "long and strong" if long and strong else ("long" if long else "strong")
    return f"That was {what}. The advice near the coast is: long or strong, get gone."


def either(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " or " + words[-1]


@dataclass
class AlarmTest:
    began: float
    until: float
    by: str = ""
    heard: list = field(default_factory=list)
    ended: str = ""


def _sense(kind: Kind) -> str:
    if kind.name in SOUNDING or kind.name in ("fire_word", "glass", "screaming", "shouting", "help"):
        return "I can hear"
    if kind.name == "smoke_seen":
        return "I can see"
    return "I noticed"


def _to(who: str | None, sentence: str) -> str:
    if not who or who == "someone":
        return sentence
    rest = sentence if sentence.startswith("I ") or sentence.startswith("I'") else sentence[:1].lower() + sentence[1:]
    return f"{who}, {rest}"


class Ladder:
    def __init__(self, ports: Ports, name: str = "Pebble"):
        self.p = ports
        self.name = name
        self.incidents: dict[str, Incident] = {}
        self.snoozed: dict[str, float] = {}
        self.history: list[dict] = []
        self.quiet = False
        self.on_end: Callable | None = None
        self.listeners: list[Callable] = []
        self.test: AlarmTest | None = None
        self.last_test: AlarmTest | None = None

    @property
    def active(self) -> bool:
        return any(i.step in ("ask", "alarm", "quake") or i.seeking for i in self.incidents.values())

    def start_test(self, by: str = "", seconds: float = TEST_S) -> bool:
        if self.active or self.test is not None:
            return False
        mono = self.p.clock.monotonic()
        self.test = AlarmTest(mono, mono + seconds, by)
        self.p.record("alarm_test", on=True, by=by, seconds=seconds)
        return True

    def end_test(self, why: str) -> AlarmTest | None:
        test, self.test = self.test, None
        if test is None:
            return None
        test.ended = why
        for incident in self.incidents.values():
            incident.test = False
        self.p.record("alarm_test", on=False, why=why, heard=len(test.heard))
        return test

    def test_over(self) -> AlarmTest | None:
        if self.test is not None and self.p.clock.monotonic() >= self.test.until:
            return self.end_test("ten minutes went by")
        return None

    def holding(self) -> str | None:
        quake = self.incidents.get("quake")
        if quake is not None and quake.step == "quake":
            return "the floor is shaking"
        return None

    def notice(self, notice: Notice) -> Incident | None:
        kind = kind_of(notice.kind)
        if kind is None:
            return None
        mono = self.p.clock.monotonic()
        self.p.record("safety_notice", what=notice.kind, confidence=round(notice.confidence, 2), source=notice.source, text=notice.text, detail=dict(notice.detail), person=notice.person)
        if mono < self.snoozed.get(kind.name, -math.inf):
            self.p.note(f"you noticed {kind.noun} again, but you were told it's fine", False)
            return None
        incident = self.incidents.get(kind.family)
        if incident is None:
            if self.quiet and kind.severity == LOW:
                self.p.note(f"you noticed {kind.noun} during quiet hours ({notice.text}); you kept it to yourself", False)
                self.p.diary(f"During the night I noticed {kind.noun}.", "safety")
                return None
            incident = Incident(next(_ids), kind.family, kind.plan, kind.severity, kind, mono, since=mono, person=notice.person)
            incident.test = self.test is not None and kind.name in SOUNDING
            self.incidents[kind.family] = incident
            self.p.record("safety_incident", id=incident.id, family=kind.family, plan=kind.plan, what=kind.name, confidence=round(notice.confidence, 2), test=incident.test)
            self.p.note(f"you noticed {kind.noun}: {notice.text}" + (" (the alarms are being tested)" if incident.test else ""), kind.severity != LOW and not incident.test)
        elif incident.test and kind.name not in SOUNDING:
            incident.test = False
            self.p.record("alarm_test_real", id=incident.id, why=kind.name)
            self.p.note(f"during the alarm test you also noticed {kind.noun}, so you are treating the alarm as real", True)
        old = incident.evidence.get(notice.kind, (0.0, -math.inf))[0]
        incident.evidence[notice.kind] = (max(notice.confidence, old * 0.5), mono)
        incident.peak = max(incident.peak, incident.confidence(mono))
        incident.details.update(notice.detail)
        if notice.person and incident.person is None:
            incident.person = notice.person
        if ORDER.get(kind.severity, 2) < ORDER.get(incident.severity, 2):
            incident.severity = kind.severity
        return incident

    def heard(self, person: str | None, reading: Reading, tier: str, sure: bool = False, addressed: bool | None = None, track: int | None = None) -> None:
        mono = self.p.clock.monotonic()
        said = addressed is not False
        for incident in list(self.incidents.values()):
            if incident.step == "done":
                continue
            asked = incident.confirm
            confirming = asked is not None and mono - asked[2] <= CONFIRM_S and ((person is not None and asked[0] == person) or (person is None and track is not None and asked[1] == track))
            may = self._may_stand_down(incident, person, tier, sure, said, track)
            if confirming and may and (reading.sure or reading.stand_down):
                incident.details["_by_fallen"] = self._fallen(incident, person, sure, track)
                self._end(incident, "stood down", person)
                continue
            if reading.stand_down or (reading.quiet and tier in TRUSTED):
                if may:
                    incident.confirm = (person, track, mono)
                    self._spawn(self.p.say(CONFIRM.get(incident.plan, CONFIRM_LINE), False))
                    continue
                if not incident.refused_said and said:
                    incident.refused_said = True
                    known = person is not None and tier != "stranger"
                    self._spawn(self.p.say(UNSEEN_LINE if known and not sure else REFUSED_LINE, False))
                continue
            if reading.quiet and incident.siren and said:
                incident.muted_until = mono + QUIET_MUTE_S
                self._siren(incident, False)
                continue
            if reading.yes and incident.plan == "help" and incident.step == "ask":
                incident.evidence["help"] = (0.95, mono)
                self._go(incident, "alarm")

    def _fallen(self, incident: Incident, person: str | None, sure: bool, track: int | None) -> bool:
        if incident.person is not None:
            return person == incident.person and sure
        fallen = incident.details.get("track")
        return fallen is not None and track is not None and track == fallen

    def _may_stand_down(self, incident: Incident, person: str | None, tier: str, sure: bool, said: bool, track: int | None) -> bool:
        if not said:
            return False
        close = tier in TRUSTED or self.p.owner_of(person)
        if incident.plan == "help":
            return self._fallen(incident, person, sure, track) or (sure and close)
        if not sure or person is None:
            return False
        if close:
            return True
        return incident.severity != HIGH and tier in KNOWN

    async def step(self, quiet: bool) -> None:
        self.quiet = quiet
        ended = self.test_over()
        if ended is not None:
            self.last_test = ended
        for incident in sorted(self.incidents.values(), key=lambda i: (ORDER.get(i.severity, 2), i.began)):
            try:
                await self._step(incident)
            except Exception:
                log.exception("safety: incident %s failed", incident.id)
                self.p.record("error", where="safety", incident=incident.id)
        for family, incident in list(self.incidents.items()):
            if incident.step == "done":
                del self.incidents[family]

    async def _step(self, incident: Incident) -> None:
        handler = getattr(self, f"_plan_{incident.plan}")
        await handler(incident, self.p.clock.monotonic())

    def _go(self, incident: Incident, step: str) -> None:
        if incident.step == step:
            return
        self.p.record("safety_step", id=incident.id, family=incident.family, step=step, was=incident.step, confidence=round(incident.confidence(self.p.clock.monotonic()), 2))
        incident.step = step
        incident.since = self.p.clock.monotonic()

    async def _plan_alarm(self, incident: Incident, mono: float) -> None:
        confidence = incident.confidence(mono)
        quiet_for = mono - incident.last_evidence()
        noun = incident.lead().noun
        if incident.test and await self._tested(incident, mono):
            return
        if incident.step == "check":
            if confidence >= SURE:
                self.p.rouse(f"you noticed {noun}")
                self._go(incident, "ask")
                self.p.face_show("scared")
                await self.p.say(f"{_sense(incident.lead())} {noun}. Is everything okay?", False)
                self.p.note(f"you are sure you noticed {noun}, so you asked if everything is okay", True)
            elif mono - incident.since >= CHECK_S:
                hint = any(kind in HINTS for kind in incident.evidence)
                if confidence >= WONDER_CONFIDENCE or hint:
                    self._go(incident, "wonder")
                    self.p.face_show("curious")
                    if hint:
                        self.p.rouse(f"you noticed {noun} and went to look")
                        self._seek(incident, f"checking on {noun}")
                        self.p.note(f"you think you noticed {noun}, but it is only a hint, so you went to look and listen", True)
                    else:
                        await self.p.say(f"I think I noticed {noun}, but I'm not sure. Is everything okay?", False)
                        self.p.note(f"you think you noticed {noun} but were not sure, so you asked", True)
                else:
                    self._end(incident, "unsure", None, quietly=True)
            return
        if incident.step == "wonder":
            if confidence >= SURE:
                incident.seek_result = None
                self._go(incident, "check")
                incident.since = mono - CHECK_S
            elif incident.seek_result is not None and not incident.seek_spoken:
                incident.seek_spoken = True
                result, detail = incident.seek_result
                if result == "found":
                    await self.p.say(_to(detail, f"I noticed {noun}, but I'm not sure. Is everything okay?"), False)
            elif quiet_for >= WONDER_KEEP_S and not incident.seeking:
                self._end(incident, "unsure", None)
            return
        if incident.step == "ask":
            if incident.stopped(mono):
                await self.p.say("It has stopped now. I'll keep listening.", False)
                self._end(incident, "stopped", None)
            elif mono - incident.since >= ASK_S:
                if confidence >= ALARM_CONFIDENCE or incident.peak >= SURE:
                    await self._raise(incident, mono)
                else:
                    self._end(incident, "unsure", None)
            return
        if incident.step == "alarm":
            await self._keep_alarm(incident, mono, quiet_for)

    async def _tested(self, incident: Incident, mono: float) -> bool:
        if any(name not in SOUNDING for name in incident.evidence):
            incident.test = False
            return False
        sounding = mono - incident.last_evidence() < STOPPED_S
        if sounding and mono - incident.began >= TEST_REAL_S:
            incident.test = False
            self.p.record("alarm_test_real", id=incident.id, why="kept going")
            self.p.note(f"{incident.lead().noun} kept going for more than half a minute during the alarm test, so you treat it as real", True)
            await self.p.say("That alarm has kept going for more than half a minute, so I'm treating it as real.", False)
            incident.since = mono - CHECK_S
            return False
        if sounding:
            return True
        test = self.test
        if test is not None:
            test.heard.append({"kind": incident.lead().name, "freq_hz": incident.details.get("freq_hz"), "level_db": incident.details.get("level_db"), "seconds": round(incident.last_evidence() - incident.began, 1), "at": self.p.clock.now()})
        self._end(incident, "tested", None, quietly=True)
        return True

    async def _raise(self, incident: Incident, mono: float) -> None:
        lead = incident.lead()
        self._go(incident, "alarm")
        self.p.rouse(f"you raised the alarm about {lead.noun}")
        self.p.face_alarm(lead.word or "ALARM")
        self.p.stop_wheels()
        self._siren(incident, True)
        self.p.note(f"nobody said it was fine, so you raised the alarm about {lead.noun}: a loud sound, a flashing screen, and you go to find people", True)
        self.p.diary(f"I raised the alarm: {lead.noun}.", "safety")
        self._seek(incident, f"raising the alarm about {lead.noun}")

    def _seek(self, incident: Incident, why: str) -> None:
        if incident.seeking:
            return
        started = False
        try:
            started = bool(self.p.seek(why, lambda result, detail, i=incident: self._sought(i, result, detail)))
        except Exception:
            log.exception("safety: could not start looking for people")
        incident.seeking = started
        incident.seek_at = self.p.clock.monotonic()
        self.p.record("safety_seek", id=incident.id, started=started)
        if not started:
            incident.seek_result = ("blocked", "could not start looking for people")

    def _sought(self, incident: Incident, result: str, detail: str) -> None:
        incident.seeking = False
        incident.seek_result = (result, detail)
        incident.seek_spoken = False
        if result == "found":
            incident.found = detail or "someone"
        self.p.record("safety_seek_done", id=incident.id, result=result, detail=detail)

    async def _keep_alarm(self, incident: Incident, mono: float, quiet_for: float) -> None:
        lead = incident.lead()
        if quiet_for >= END_AFTER_S:
            if incident.plan == "help":
                await self.p.say("I've stopped my alarm, but nobody has told me everyone is all right.", True)
            else:
                await self.p.say(f"I haven't noticed {lead.noun} for a few minutes, so I've stopped my alarm.", True)
            self._end(incident, "went quiet", None)
            return
        if incident.seek_result is not None and not incident.seek_spoken:
            incident.seek_spoken = True
            result, detail = incident.seek_result
            if result == "found":
                self._siren(incident, False)
                incident.line_at = mono
                await self.p.say(_to(detail, self._sentence(lead)) + " Please check, and tell me when it's safe.", True)
                self.p.note(f"you found {detail or 'someone'} and told them about {lead.noun}", True)
            elif result == "door":
                incident.line_at = mono
                await self.p.say(self._sentence(lead) + " Please check, and tell me when it's safe.", True)
                self.p.note(f"someone may be in the {detail}, which is private, so you stayed at the door and called through it about {lead.noun}", True)
                self._notify(incident, mono)
            else:
                self.p.note(f"you could not find anyone to tell about {lead.noun} ({detail})", True)
                self._notify(incident, mono)
        if mono - incident.since >= NOTIFY_AFTER_S:
            self._notify(incident, mono)
        if incident.found is None and not incident.seeking and incident.seek_spoken and mono - incident.seek_at >= RESEEK_S:
            incident.seek_result = None
            incident.seek_spoken = False
            self._seek(incident, f"still raising the alarm about {lead.noun}")
        if incident.found is None and mono >= incident.muted_until:
            if incident.siren and mono - incident.siren_since >= SIREN_ON_S:
                self._siren(incident, False)
            elif not incident.siren and mono - incident.line_at >= SIREN_GAP_S and mono - incident.siren_since >= SIREN_ON_S + SIREN_GAP_S:
                if mono - incident.line_at >= LINE_EVERY_S:
                    incident.line_at = mono
                    await self.p.say(self._sentence(lead), True)
                self._siren(incident, True)
        elif incident.found is not None and mono - incident.line_at >= LINE_EVERY_S:
            incident.line_at = mono
            await self.p.say(f"{self._sentence(lead)} Please tell me when it's safe.", True)

    def _sentence(self, kind: Kind) -> str:
        return {
            "smoke_alarm": "The smoke alarm is going off!",
            "alarm_beeping": "Something is beeping like an alarm!",
            "alarm_sound": "I can hear an alarm!",
            "heat_rise": "It's getting hot very fast near the floor!",
            "gas_spike": "I can smell something like smoke!",
            "fire_word": "Someone shouted fire!",
            "smoke_seen": "I think I can see smoke!",
            "co_alarm": "The carbon monoxide alarm is going off!",
            "help": "Someone is calling for help!",
            "name_shouted": "Someone called me and isn't answering!",
            "screaming": "I heard someone scream!",
            "shouting": "I heard shouting!",
            "on_floor": "Someone is lying on the floor and isn't answering!",
        }.get(kind.name, f"I noticed {kind.noun}!")

    def _siren(self, incident: Incident, on: bool) -> None:
        if incident.siren == on:
            return
        incident.siren = on
        if on:
            incident.siren_since = self.p.clock.monotonic()
        try:
            self.p.siren(on)
        except Exception:
            log.exception("safety: the alarm sound failed")
        self.p.record("safety_siren", id=incident.id, on=on)

    def _notify(self, incident: Incident, mono: float) -> None:
        if incident.notified:
            return
        incident.notified = True
        if not self.p.notify_on():
            self.p.record("safety_notify", id=incident.id, sent=False, why="off")
            return
        lead = incident.lead()
        when = self.p.clock.local().strftime("%H:%M")
        found = "and could not find anyone" if incident.found is None else "and told someone"
        text = f"{self.name} noticed {lead.noun} at home at {when} {found}. Nobody has told it that it's fine yet."
        if incident.plan == "quake":
            text = f"{self.name} felt the floor shaking at home at {when} ({incident.details.get('strength', 'shaking')})."
        elif incident.plan == "notify":
            text = f"{self.name} saw someone it hasn't met at home at {when}, while nobody it knows was there."
        self.p.notify(f"{self.name}: {lead.noun}", text)
        self.p.record("safety_notify", id=incident.id, sent=True)
        self.p.diary(f"I sent a notice to my owner's phone: {lead.noun}.", "safety")

    async def _plan_help(self, incident: Incident, mono: float) -> None:
        confidence = incident.confidence(mono)
        if incident.step == "check":
            self.p.rouse("someone may need help")
            self._go(incident, "ask")
            incident.asks = 1
            self.p.face_show("scared")
            line = {"name_shouted": "Did you call me? Is everything okay?", "on_floor": "Are you okay?"}.get(incident.kind.name, "Are you okay? Do you need help?") if confidence < ALARM_CONFIDENCE else "Are you okay? Do you need help?"
            await self.p.say(line, True)
            self.p.note(f"you noticed {incident.lead().noun}, so you asked if they are okay and went to find them", True)
            self._seek(incident, "someone may need help")
            return
        if incident.step == "ask":
            if incident.seek_result is not None and not incident.seek_spoken:
                incident.seek_spoken = True
                if incident.seek_result[0] == "found" and incident.asks < 2:
                    incident.asks += 1
                    incident.since = mono
                    await self.p.say(_to(incident.found, "Are you okay? Do you need help?"), True)
            if mono - incident.since >= HELP_ASK_S and not incident.seeking:
                if incident.kind.name == "on_floor":
                    incident.evidence["no_answer"] = (0.6, mono)
                    confidence = incident.confidence(mono)
                if confidence >= ALARM_CONFIDENCE or incident.peak >= ALARM_CONFIDENCE:
                    await self._raise(incident, mono)
                else:
                    self.p.note("nobody answered, so you let it go", False)
                    self._end(incident, "no answer", None)
            return
        if incident.step == "alarm":
            await self._keep_alarm(incident, mono, 0.0 if mono - incident.since < HELP_ALARM_S else END_AFTER_S)

    async def _plan_look(self, incident: Incident, mono: float) -> None:
        noun = incident.lead().noun
        if incident.step == "check":
            if self.quiet and incident.severity == LOW:
                self._end(incident, "quiet hours", None, quietly=True)
                return
            here = self.p.trusted_here()
            if here:
                await self.p.say(_to(here[0], f"I heard {noun}."), False)
                self._end(incident, "told", None)
                return
            self._go(incident, "look")
            self.p.rouse(f"you heard {noun} and went to look")
            self._seek(incident, f"heard {noun}")
            self.p.note(f"you heard {noun} and went to look and find someone to tell", incident.severity != LOW)
            return
        if incident.step == "look":
            if incident.seek_result is not None:
                result, detail = incident.seek_result
                if result == "found":
                    await self.p.say(_to(detail, f"I heard {noun}."), False)
                    self._end(incident, "told", None)
                else:
                    self.p.note(f"you heard {noun} but found nobody to tell ({detail})", False)
                    self._end(incident, "nobody", None)
            elif mono - incident.since >= LOOK_NOTICE_KEEP_S:
                self._end(incident, "gave up", None)

    async def _plan_tell(self, incident: Incident, mono: float) -> None:
        noun = incident.lead().noun
        if self.quiet and incident.severity == LOW:
            self._end(incident, "quiet hours", None, quietly=True)
            return
        if self.p.anyone_here():
            here = self.p.trusted_here()
            await self.p.say(_to(here[0] if here else None, f"I can hear {noun}. Is that okay?"), False)
            self._end(incident, "told", None)
        elif mono - incident.since >= TELL_WAIT_S:
            self._end(incident, "nobody", None)

    async def _plan_notify(self, incident: Incident, mono: float) -> None:
        noun = incident.lead().noun
        self.p.note(f"you noticed {noun}; you said nothing and only told your owner, if that is switched on", False)
        self.p.diary(f"I noticed {noun} at night.", "safety")
        self._notify(incident, mono)
        self._end(incident, "told the owner", None, quietly=True)

    async def _plan_quake(self, incident: Incident, mono: float) -> None:
        quiet_for = mono - incident.last_evidence()
        if incident.step == "check":
            self._go(incident, "quake")
            self.p.stop_wheels()
            self.p.face_show("scared")
            self.p.felt("quake", "the floor is shaking, like an earthquake; you stopped and held still")
            await self.p.say("Earthquake! Drop, cover and hold!", True)
            return
        if incident.step == "calm" and quiet_for < QUAKE_CALM_S:
            self._go(incident, "quake")
            self.p.stop_wheels()
            if incident.seeking:
                incident.seeking = False
                incident.details["_round_cut"] = True
                self.p.end_seek("it started shaking again")
            self.p.face_show("scared")
            self.p.felt("quake", "the floor is shaking again; you stopped and held still")
            await self.p.say("It's shaking again. Drop, cover and hold!", True)
            return
        if incident.step == "quake" and quiet_for >= QUAKE_CALM_S:
            self._go(incident, "calm")
            strength = incident.details.get("strength", "")
            seconds = incident.details.get("seconds")
            await self.p.say("The shaking has stopped.", False)
            if isinstance(seconds, (int, float)):
                await self.p.say(f"It lasted {quake_length(seconds)}.", False)
            long = isinstance(seconds, (int, float)) and seconds > LONG_QUAKE_S
            strong = strength in STRONG_QUAKE
            if (long or strong) and self.p.tsunami_zone() and not incident.details.get("_tsunami_said"):
                incident.details["_tsunami_said"] = True
                await self.p.say(tsunami_line(long, strong), False)
                self.p.record("safety_tsunami_line", id=incident.id, long=long, strong=strong)
            lasting = f" for about {round(seconds)} seconds" if isinstance(seconds, (int, float)) else ""
            self.p.diary(f"I felt the floor shake{lasting} ({strength or 'shaking'}). I said drop, cover and hold, and kept still.", "safety")
            self.p.note(f"the shaking stopped{lasting}; it was {strength or 'shaking'}", True)
            self._notify(incident, mono)
            if not incident.details.get("_checked") or incident.details.get("_round_cut"):
                await self._check_round(incident, mono)
            return
        if incident.step == "calm" and mono - incident.since >= QUAKE_HOLD_S and not incident.seeking:
            self._end(incident, "calm", None, quietly=True)

    async def _check_round(self, incident: Incident, mono: float) -> None:
        incident.details["_checked"] = True
        incident.details["_round_cut"] = False
        self.p.rouse("you felt an earthquake and went to check on everyone")
        started = False
        try:
            started = bool(self.p.check_round("checking on everyone after the earthquake", lambda result, i=incident: self._checked(i, result)))
        except Exception:
            log.exception("safety: could not start the check round after the earthquake")
        incident.seeking = started
        incident.seek_at = mono
        self.p.record("safety_check_round", id=incident.id, started=started)
        if started:
            await self.p.say("I'll come and check on everyone.", False)
        else:
            await self.p.say("Is everyone okay?", False)

    def _checked(self, incident: Incident, result: dict) -> None:
        if incident.details.get("_round_cut"):
            return
        incident.seeking = False
        found = list(result.get("found") or [])
        missing = [label for _, label in result.get("missing") or []]
        unchecked = [label for _, label in result.get("unchecked") or []]
        self.p.record("safety_check_round_done", id=incident.id, how=result.get("how"), found=[pid for pid, _ in found], missing=missing, unchecked=unchecked)
        if not missing and not unchecked:
            if found:
                self.p.note("after the earthquake you checked on everyone you knew was home and found them all", True)
                self.p.diary("After the earthquake I checked on everyone I knew was home, and found them all.", "safety")
            return
        parts = []
        if missing:
            parts.append(f"couldn't find {either(missing)}")
        if unchecked:
            parts.append(f"didn't get to check on {either(unchecked)}")
        owner = next((label for pid, label in found if self.p.owner_of(pid)), None)
        if owner is not None:
            self._spawn(self.p.say(_to(owner, "I " + ", and I ".join(parts) + "."), False))
            told = owner
        elif self.p.notify_on():
            when = self.p.clock.local().strftime("%H:%M")
            self.p.notify(f"{self.name}: after the earthquake", f"{self.name} checked on everyone it knew was home after the earthquake at {when}. It " + ", and it ".join(parts) + ".")
            self.p.record("safety_notify", id=incident.id, sent=True, why="check round")
            told = "the owner's phone"
        else:
            told = ""
        self.p.note(f"after the earthquake you {' and '.join(parts)}" + (f"; you told {told}" if told else "; there was nobody to tell"), True)
        self.p.diary(f"After the earthquake I {' and '.join(parts)}.", "safety")

    def _end(self, incident: Incident, how: str, person: str | None, quietly: bool = False) -> None:
        if incident.step == "done":
            return
        was = incident.step
        self._siren(incident, False)
        if was == "alarm":
            others = [i for i in self.incidents.values() if i is not incident and i.step == "alarm"]
            if not others:
                self.p.face_alarm("")
        incident.step = "done"
        incident.ended = how
        if incident.seeking and not any(i is not incident and i.seeking and i.step != "done" for i in self.incidents.values()):
            incident.seeking = False
            try:
                self.p.end_seek(how)
            except Exception:
                log.exception("safety: could not stop looking for people")
        mono = self.p.clock.monotonic()
        noun = incident.lead().noun
        record = {"id": incident.id, "family": incident.family, "how": how, "was": was, "seconds": round(mono - incident.began, 1), "peak": round(incident.peak, 2), "person": person}
        self.history.append(record)
        del self.history[:-50]
        self.p.record("safety_end", **record)
        if self.on_end is not None:
            try:
                self.on_end(incident, how)
            except Exception:
                log.exception("safety: the end hook failed")
        for listener in list(self.listeners):
            try:
                listener(incident, how)
            except Exception:
                log.exception("safety: a listener of the ladder failed")
        if how == "stood down":
            label = self.p.label_of(person)
            for name in incident.evidence:
                if name in NEVER_SNOOZED:
                    continue
                self.snoozed[name] = mono + (REGRACE_S if name in SOUNDING else SNOOZE_S)
            self._spawn(self.p.say("Okay, I'm glad you're all right." if incident.plan == "help" else "Okay, thank you. I'll stop.", False))
            self.p.face_show("happy")
            self.p.note(f"{label} said it was fine, so you stood down ({noun})", True)
            self.p.diary(f"I noticed {noun}; {label} told me it was fine, so I stood down.", "safety")
            return
        if quietly:
            return
        if how == "unsure":
            self.p.diary(f"I thought I noticed {noun}, but I wasn't sure, and it didn't come back.", "safety")
        elif how == "stopped":
            self.p.diary(f"I noticed {noun}; it stopped before I raised the alarm.", "safety")
        elif how == "went quiet":
            self.p.diary(f"I raised the alarm about {noun}; it went quiet and nobody told me it was fine.", "safety")
        elif how == "no answer":
            self.p.diary(f"I noticed {noun} and asked, but nobody answered.", "safety")
        elif how in ("told", "nobody", "gave up"):
            self.p.diary(f"I heard {noun}" + (" and told someone." if how == "told" else ", but I couldn't find anyone to tell."), "safety")
        self.p.note(f"you stopped paying attention to {noun} ({how})", False)

    def stand_down_all(self, why: str) -> None:
        for incident in list(self.incidents.values()):
            self._end(incident, why, None, quietly=True)

    def _spawn(self, coro) -> None:
        try:
            asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            coro.close()

    def status(self) -> dict:
        mono = self.p.clock.monotonic()
        return {
            "active": self.active,
            "incidents": [{"id": i.id, "family": i.family, "step": i.step, "confidence": round(i.confidence(mono), 2), "seeking": i.seeking, "siren": i.siren} for i in self.incidents.values()],
            "snoozed": {f: round(t - mono) for f, t in self.snoozed.items() if t > mono},
            "recent": self.history[-5:],
            "at": iso(self.p.clock.now()),
        }
