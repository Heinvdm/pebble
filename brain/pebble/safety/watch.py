import asyncio
import logging
import math
import time
from typing import Callable

from ..clock import Clock
from .baro import Barometer
from .feeds import NoFeed
from .ladder import Ladder, Ports
from .motion import Felt, PhoneMotion
from .nightlight import NightLight
from .notice import Notice
from .notify import NoNotifier, notifier_from
from .room import AirWatch, LightWatch, NearWatch, PhoneHeat
from .seen import FireWatch, FloorWatch
from .sounder import LogSounder
from .words import read_line

log = logging.getLogger(__name__)

TRUSTED = ("trusted", "inner circle")
NAME_AGAIN_S = 10.0
FALL_STAIRS_S = 10.0
STILL_AFTER_S = 3.0
DRIVING_S = 1.0
POWER_LOST_S = 10.0
HOT_SAID_S = 1800.0
EARS_AWAKE_S = 30.0
STRANGER_GAP_S = 1800.0
SCARES = {"dropped", "stairs", "tipped", "shaken"}
CALM_S = 120.0
BODY_FELT = {"dropped", "tipped", "righted", "lifted", "carried", "shaken", "stairs", "moved_up", "moved_down"}
FACE_FELT = {"touched_face": "surprised", "poked": "happy"}


class Safety:
    def __init__(
        self,
        clock: Clock,
        hearing=None,
        feeds: dict | None = None,
        sounder=None,
        notifier=None,
        name: str = "Pebble",
        threaded: bool = False,
        max_range: Callable[[], float | None] = lambda: None,
    ):
        self.clock = clock
        self.hearing = hearing
        self.feeds = dict(feeds or {})
        self.sounder = sounder or LogSounder()
        self.notifier = notifier or NoNotifier()
        self.name = name
        self.threaded = threaded
        self.life = None
        self.ladder: Ladder | None = None
        self.motion = PhoneMotion(self._still, self._driving, self._docked)
        self.baro = Barometer(lambda: not self._driving())
        self.light = LightWatch(self._power_lost)
        self.near = NearWatch(max_range)
        self.heat = PhoneHeat()
        self.air = AirWatch(clock.now)
        self.floor = FloorWatch()
        self.fire = FireWatch()
        self.last_name: tuple[str | None, float] = (None, -math.inf)
        self.fell_at = -math.inf
        self.moved_down_at = -math.inf
        self.charging: bool | None = None
        self.charge_lost_at = -math.inf
        self.hot_said = -math.inf
        self.ticks = 0
        self.closed = False
        self.sensors = None
        self.ears = None
        self.stranger_watch = False
        self.stranger_at = -math.inf
        self.night = NightLight(clock)
        self.quiet_now = False
        self.sharp_until = -math.inf

    @property
    def active(self) -> bool:
        return self.ladder is not None and self.ladder.active

    def hold_reason(self) -> str | None:
        return (self.ladder.holding() if self.ladder else None) or self.fire.hold_reason(self.clock.monotonic()) or self.near.hold_reason() or self.heat.hold_reason()

    def attach(self, life, ports: Ports | None = None) -> "Safety":
        self.life = life
        if ports is None:
            ports = ports_for(life, self)
        self.ladder = Ladder(ports, self.name)
        self.ladder.on_end = self._ended
        self.night.attach(ports)
        prefs =(getattr(getattr(life.p, "books", None), "preferences", None) or {}).get("safety") or {}
        if isinstance(self.notifier, NoNotifier) and prefs.get("notify"):
            self.notifier = notifier_from(prefs.get("notify"))
        self.stranger_watch = prefs.get("stranger_watch") is True
        if self.hearing is not None:
            self.hearing.start()
        return self

    def heard(self, heard, loud: bool = False) -> None:
        if self.ladder is None:
            return
        now = self.clock.now()
        mono = self.clock.monotonic()
        reading = read_line(getattr(heard, "text", ""), self.name)
        person = getattr(heard, "person_id", None)
        tier = self.ladder.p.tier_of(person)
        shouted = bool(loud)
        if self.hearing is not None:
            shouted = shouted or self.hearing.loudness().shouted
        if reading.help:
            confidence = min(0.97, reading.help + (0.05 if shouted else 0.0))
            self.ladder.notice(Notice("help", confidence, "speech", now, f'{getattr(heard, "label", "someone")} said "{getattr(heard, "text", "")}"' + (" loudly" if shouted else ""), {"shouted": shouted}, person))
        elif reading.name_only and shouted:
            again = self.last_name[0] == person and mono - self.last_name[1] <= NAME_AGAIN_S
            self.last_name = (person, mono)
            self.ladder.notice(Notice("name_shouted", 0.7 if again else 0.5, "speech", now, f"someone shouted your name{' again' if again else ''}", {"again": again}, person))
        elif reading.fire:
            self.ladder.notice(Notice("fire_word", 0.6 if shouted else 0.4, "speech", now, f'{getattr(heard, "label", "someone")} said "{getattr(heard, "text", "")}"', {"shouted": shouted}, person))
        self.ladder.heard(person, reading, tier, bool(getattr(heard, "sure", False)), getattr(heard, "addressed", None), getattr(heard, "track", None))

    async def tick(self, quiet: bool = False) -> None:
        if self.ladder is None or self.closed:
            return
        self.ticks += 1
        self.quiet_now = quiet
        notices = []
        if self.hearing is not None:
            self.hearing.mute(self.sounder_on(), self.clock.monotonic())
            try:
                notices = await asyncio.to_thread(self.hearing.pump) if self.threaded else self.hearing.pump()
            except Exception:
                log.exception("safety: hearing failed")
        for notice in notices:
            self.ladder.notice(notice)
        for item in self.sense():
            self._take(item)
        try:
            self.night.tick(**self._light_now())
        except Exception:
            log.exception("safety: the night light failed")
        self._stranger(quiet)
        await self.ladder.step(quiet)
        self._wake_ears(quiet)

    def _light_now(self) -> dict:
        snapshot = getattr(self.life, "sensors", None) if self.life is not None else None
        battery = getattr(snapshot, "battery", None)
        try:
            anyone = bool(self.ladder.p.anyone_here()) if self.ladder is not None else False
        except Exception:
            anyone = False
        return {"quiet": self.quiet_now, "anyone": anyone, "lux": self.light.latest, "charging": self.charging, "hot": self.heat.level >= 2, "battery": getattr(battery, "percent", None)}

    def light_asked(self, on: bool) -> str:
        now = self._light_now()
        return self.night.asked(on, now["battery"], now["hot"])

    def _stranger(self, quiet: bool) -> None:
        if not quiet or not self.stranger_watch:
            return
        company = getattr(self.life, "company", None)
        if company is None:
            return
        now = self.clock.now()
        mono = self.clock.monotonic()
        if company.someone_new(now) and not company.here(now) and mono - self.stranger_at >= STRANGER_GAP_S:
            self.stranger_at = mono
            self.ladder.notice(Notice("stranger", 0.6, "eyes", now, "someone you have not met is in view at night, and nobody you know is here"))

    def crying(self, seconds: float) -> float:
        events = getattr(self.hearing, "events", None)
        if events is None:
            return 0.0
        try:
            return events.share("baby", seconds, getattr(self.hearing, "last_end", None))
        except Exception:
            log.exception("safety: could not tell whether someone is crying")
            return 0.0

    def sharpen(self, seconds: float) -> None:
        self.sharp_until = max(self.sharp_until, self.clock.monotonic() + seconds)

    def _wake_ears(self, quiet: bool) -> None:
        wake = getattr(self.ears, "wake_for", None)
        if wake is None:
            return
        loud = quiet and self.hearing is not None and self.hearing.loudness().loud
        if self.ladder.active or self.ladder.incidents or loud or self.clock.monotonic() < self.sharp_until:
            try:
                wake(EARS_AWAKE_S)
            except Exception:
                log.exception("safety: the ears would not wake")

    def sounder_on(self) -> bool:
        return bool(getattr(self.sounder, "on", False))

    def sense(self) -> list:
        out: list = []
        out.extend(self.motion.feed(self._read("accel")))
        out.extend(self.baro.feed(self._read("pressure")))
        out.extend(self.light.feed(self._read("light")))
        out.extend(self.near.feed(self._read("proximity"), self.clock.monotonic()))
        out.extend(self._look())
        snapshot = getattr(self.life, "sensors", None) if self.life is not None else None
        battery = getattr(snapshot, "battery", None)
        out.extend(self.heat.update(battery.temperature_c if battery is not None and battery.temperature_c is not None else getattr(snapshot, "temperature_c", None)))
        self._watch_charger(battery)
        body = getattr(getattr(self.life, "p", None), "body", None)
        telemetry = getattr(body, "telemetry", None)
        reader = getattr(telemetry, "air_reading", None)
        if reader is not None:
            try:
                out.extend(self.air.feed(reader(self.clock.now(), 10.0)))
            except Exception:
                log.exception("safety: the air reading failed")
        return out

    def _look(self) -> list:
        eyes = getattr(getattr(self.life, "p", None), "eyes", None)
        if eyes is None or not getattr(eyes, "available", False):
            return []
        try:
            sight = eyes.latest(1.0)
        except Exception:
            log.exception("safety: the eyes failed")
            return []
        if sight is None:
            return []
        now, mono = self.clock.now(), self.clock.monotonic()
        return self.floor.feed(sight, now, mono) + self.fire.feed(sight, now, mono)

    def _ended(self, incident, how: str) -> None:
        if how == "stood down" and "on_floor" in incident.evidence and incident.details.get("_by_fallen"):
            self.floor.fine_at(incident.details.get("place"))

    def _read(self, kind: str) -> list:
        feed = self.feeds.get(kind) or NoFeed()
        try:
            return feed.read()
        except Exception:
            log.exception("safety: the %s feed failed", kind)
            return []

    def _take(self, item) -> None:
        ladder = self.ladder
        if isinstance(item, Notice):
            ladder.notice(item)
            return
        if not isinstance(item, Felt):
            return
        mono = self.clock.monotonic()
        p = ladder.p
        if item.kind == "quake":
            ladder.notice(Notice("quake", 0.8, "motion", self.clock.now(), item.text, dict(item.detail)))
            return
        if item.kind == "dropped":
            self.fell_at = mono
            if mono - self.moved_down_at <= FALL_STAIRS_S:
                p.felt("stairs", "you fell down the stairs")
                self._calm("you fell down the stairs")
                return
        if item.kind == "moved_down":
            self.moved_down_at = mono
            if mono - self.fell_at <= FALL_STAIRS_S:
                p.felt("stairs", "you fell down the stairs")
                self._calm("you fell down the stairs")
                return
        p.record("safety_sense", what=item.kind, text=item.text, **{k: v for k, v in item.detail.items() if isinstance(v, (int, float, str, bool))})
        if item.kind in BODY_FELT:
            p.felt(item.kind, item.text)
            if item.kind in SCARES:
                self._calm(item.text)
            return
        if item.kind in FACE_FELT:
            p.face_show(FACE_FELT[item.kind])
            p.note(item.text, False)
            return
        if item.kind in ("phone_hot", "phone_too_hot"):
            p.stop_wheels()
            p.note(item.text, True)
            if item.kind == "phone_too_hot" and mono - self.hot_said >= HOT_SAID_S and p.anyone_here():
                self.hot_said = mono
                asyncio.ensure_future(p.say("I'm getting too hot. Could someone move me somewhere cooler, or take me off the charger?", False))
            return
        p.note(item.text, False)
        if item.kind == "lights_out" and item.detail.get("power"):
            try:
                self.night.power_cut(**self._light_now())
            except Exception:
                log.exception("safety: the night light failed")

    def tell_owner(self, title: str, text: str) -> bool:
        if not getattr(self.notifier, "enabled", False):
            return False
        record = getattr(getattr(getattr(self.life, "p", None), "blackbox", None), "record", None)
        if record is not None:
            record("safety_notify", sent=True, what="owner note", title=" ".join(str(title).split())[:80])
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return bool(self.notifier.send(title, text))
        loop.run_in_executor(None, self.notifier.send, title, text)
        return True

    def _calm(self, why: str) -> None:
        calm = getattr(self.life, "calm_down", None)
        if calm is None:
            return
        try:
            calm(seconds=CALM_S, why=why)
        except Exception:
            log.exception("safety: could not settle down")

    def _watch_charger(self, battery) -> None:
        charging = None if battery is None else battery.charging
        if self.charging and charging is False:
            self.charge_lost_at = self.clock.monotonic()
        if charging is not None:
            self.charging = charging

    def _power_lost(self) -> bool:
        return self._docked() and self.clock.monotonic() - self.charge_lost_at <= POWER_LOST_S

    def _telemetry(self):
        return getattr(getattr(getattr(self.life, "p", None), "body", None), "telemetry", None)

    def _docked(self) -> bool:
        telemetry = self._telemetry()
        return bool(getattr(telemetry, "docked", False))

    def _driving(self) -> bool:
        telemetry = self._telemetry()
        last = getattr(telemetry, "last_motion_at", None)
        if last is not None and self.clock.now() - last <= DRIVING_S:
            return True
        commands = getattr(self.life, "commands", None)
        runner = getattr(commands, "runner", None)
        current = getattr(runner, "current", None)
        return bool(current is not None and getattr(current, "moving", False))

    def _still(self) -> bool:
        telemetry = self._telemetry()
        last = getattr(telemetry, "last_motion_at", None)
        recent = last is not None and self.clock.now() - last < STILL_AFTER_S
        return self._docked() and not recent and not self._driving()

    def close(self) -> None:
        self.closed = True
        try:
            if self.sounder_on():
                self.sounder.siren(False)
        except Exception:
            log.exception("safety: the alarm sound would not stop")
        if self.hearing is not None:
            self.hearing.stop()
        if self.sensors is not None:
            self.sensors.stop()
        try:
            self.night.shut()
        except Exception:
            log.exception("safety: the light would not go off")

    def status(self) -> dict:
        return {
            "ladder": self.ladder.status() if self.ladder else None,
            "hearing": self.hearing.status() if self.hearing is not None else None,
            "motion": self.motion.status(),
            "barometer": self.baro.status(),
            "light": self.light.status(),
            "torch": self.night.status(),
            "near": self.near.status(),
            "phone_heat": self.heat.status(),
            "air": self.air.status(),
            "sounder": self.sounder.info() if hasattr(self.sounder, "info") else {},
            "notices": self.notifier.info(),
            "hold": self.hold_reason(),
        }


def ports_for(life, safety: Safety) -> Ports:
    p = life.p
    clock = p.clock
    company = life.company

    async def say(text: str, loud: bool) -> None:
        p.blackbox.record("safety_say", text=text, loud=loud)
        if loud and safety.sounder.say(text):
            return
        await p.voice.say(text, whisper=False)

    def siren(on: bool) -> None:
        safety.sounder.siren(on)
        if safety.hearing is not None:
            safety.hearing.mute(on, clock.monotonic())

    def face_alarm(word: str) -> None:
        alarm = getattr(p.face, "alarm", None)
        if alarm is not None:
            alarm(word)

    def note(text: str, major: bool) -> None:
        life.events.add(clock.now(), text, major)
        if major:
            life.trigger.set()

    def stop_wheels() -> None:
        if p.body.connected:
            asyncio.ensure_future(p.body.stop())

    def person(person_id):
        return company.book.get(person_id) if person_id else None

    def tier_of(person_id) -> str:
        found = person(person_id)
        return company.tier(found) if found is not None else "stranger"

    def label_of(person_id) -> str:
        found = person(person_id)
        return found.label if found is not None else "someone"

    def trusted_here() -> list:
        now = clock.now()
        return [who.label for who in company.here(now) if company.tier(who, now) in TRUSTED or who.is_owner]

    def end_seek(why: str) -> None:
        ender = getattr(life.commands, "end_seek", None)
        if ender is not None:
            ender(why)

    def tsunami_zone() -> bool:
        prefs = (getattr(getattr(p, "books", None), "preferences", None) or {}).get("safety") or {}
        return prefs.get("tsunami_zone") is True

    def notify(title: str, text: str) -> None:
        notifier = safety.notifier
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            notifier.send(title, text)
            return
        loop.run_in_executor(None, notifier.send, title, text)

    return Ports(
        clock=clock,
        say=say,
        siren=siren,
        face_alarm=face_alarm,
        face_show=p.face.show,
        note=note,
        diary=p.diary.write,
        record=p.blackbox.record,
        rouse=getattr(life, "rouse", lambda why: None),
        seek=getattr(life.commands, "seek_people", lambda why, done: False),
        end_seek=end_seek,
        stop_wheels=stop_wheels,
        felt=lambda kind, text: life.felt(kind, text),
        tier_of=tier_of,
        label_of=label_of,
        owner_of=lambda person_id: bool(getattr(person(person_id), "is_owner", False)),
        trusted_here=trusted_here,
        anyone_here=lambda: company.anyone_here(clock.now()),
        notify=notify,
        notify_on=lambda: bool(getattr(safety.notifier, "enabled", False)),
        check_round=getattr(life.commands, "quake_round", lambda why, done: False),
        tsunami_zone=tsunami_zone,
    )
