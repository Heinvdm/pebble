import math
from dataclasses import dataclass

from ..clock import iso
from ..things.words import listing
from ..understand.request import Request
from .base import Activity, Ending
from .gate import PEBBLE
from .kit import Kit
from .motion import Wheels, leave_dock
from .rounds import can_drive, find_place, go, private_room, tour, where

CLIMATE = "climate.json"
KEEP_DAYS = 30
KEEP_PER_ROOM = 60
SAMPLE_S = 5.0
STEADY_S = 60.0
STEADY_C = 0.2
STEADY_RH = 1.0
SETTLE_MIN_S = 90.0
SETTLE_MAX_S = 360.0
AIR_MAX_AGE_S = 10.0
STALE_S = 3 * 3600.0
FRESH_S = 1800.0
ROUND_GAP_S = 3600.0
CHECK_EVERY_S = 30.0
ROUND_BATTERY = 60.0
KEEP_GOING_BATTERY = 40.0
HOME_BATTERY = 50.0
CAN_NOT = {
    "fridge": "I can't measure the fridge",
    "freezer": "I can't measure the freezer",
    "outside": "I can't measure outside",
    "outdoors": "I can't measure outdoors",
    "garden": "I can't measure the garden",
}
ABOUT = {
    "warm": "temperature",
    "cold": "temperature",
    "hot": "temperature",
    "chilly": "temperature",
    "cool": "temperature",
    "temperature": "temperature",
    "humid": "humidity",
    "damp": "humidity",
    "humidity": "humidity",
    "muggy": "humidity",
    "stuffy": "air",
    "air": "air",
    "smelly": "air",
    "fresh": "air",
}


def dew_point(celsius: float, humidity_pct: float) -> float | None:
    if humidity_pct is None or celsius is None or humidity_pct <= 0:
        return None
    a, b = 17.62, 243.12
    gamma = math.log(min(100.0, humidity_pct) / 100.0) + a * celsius / (b + celsius)
    return b * gamma / (a - gamma)


def degrees(value: float) -> str:
    whole = round(value)
    return f"{whole} degree" if abs(whole) == 1 else f"{whole} degrees"


def ago(seconds: float) -> str:
    if seconds < 90:
        return "just now"
    minutes = seconds / 60.0
    if minutes < 50:
        return f"{round(minutes)} minutes ago"
    hours = minutes / 60.0
    if hours < 1.5:
        return "about an hour ago"
    if hours < 24:
        return f"about {round(hours)} hours ago"
    days = round(hours / 24.0)
    return "yesterday" if days <= 1 else f"{days} days ago"


@dataclass(frozen=True)
class Measured:
    room: str
    at: float
    celsius: float | None
    humidity_pct: float | None
    dew_c: float | None
    gas_kohm: float | None
    settled: bool
    waited_s: float

    def as_dict(self) -> dict:
        return {
            "room": self.room,
            "t": round(self.at, 1),
            "at": iso(self.at),
            "c": None if self.celsius is None else round(self.celsius, 2),
            "rh": None if self.humidity_pct is None else round(self.humidity_pct, 1),
            "dew_c": None if self.dew_c is None else round(self.dew_c, 1),
            "gas_kohm": None if self.gas_kohm is None else round(self.gas_kohm, 1),
            "settled": self.settled,
            "waited_s": round(self.waited_s),
        }

    @classmethod
    def from_dict(cls, room: str, data: dict) -> "Measured | None":
        try:
            return cls(
                room,
                float(data["t"]),
                None if data.get("c") is None else float(data["c"]),
                None if data.get("rh") is None else float(data["rh"]),
                None if data.get("dew_c") is None else float(data["dew_c"]),
                None if data.get("gas_kohm") is None else float(data["gas_kohm"]),
                bool(data.get("settled", False)),
                float(data.get("waited_s", 0.0)),
            )
        except (KeyError, TypeError, ValueError):
            return None


class ClimateLog:
    def __init__(self, store=None, clock=None):
        self.store = store
        self.clock = clock
        self.rooms: dict[str, list[Measured]] = {}
        raw = (store.read(CLIMATE, {}) or {}) if store is not None else {}
        for room, items in (raw.get("rooms") or {}).items():
            entries = [m for m in (Measured.from_dict(str(room), item) for item in items or []) if m is not None]
            if entries:
                self.rooms[str(room)] = sorted(entries, key=lambda m: m.at)

    def now(self) -> float:
        return self.clock.now() if self.clock is not None else 0.0

    def add(self, room: str, reading, settled: bool, waited_s: float) -> Measured:
        c = reading.temperature_c
        rh = reading.humidity_pct
        gas = None if reading.gas_ohm is None or reading.gas_ohm <= 0 or reading.warming else reading.gas_ohm / 1000.0
        entry = Measured(room, self.now(), c, rh, None if c is None or rh is None else dew_point(c, rh), gas, settled, waited_s)
        self.rooms.setdefault(room, []).append(entry)
        self.prune()
        self.save()
        return entry

    def prune(self) -> None:
        cutoff = self.now() - KEEP_DAYS * 86400.0
        for room in list(self.rooms):
            kept = [m for m in self.rooms[room] if m.at >= cutoff][-KEEP_PER_ROOM:]
            if kept:
                self.rooms[room] = kept
            else:
                del self.rooms[room]

    def save(self) -> None:
        if self.store is None:
            return
        self.store.write(CLIMATE, {"format": 1, "rooms": {room: [m.as_dict() for m in items] for room, items in sorted(self.rooms.items())}}, keep_backup=False)

    def latest(self, room: str) -> Measured | None:
        items = self.rooms.get(room)
        return items[-1] if items else None

    def age(self, room: str) -> float:
        last = self.latest(room)
        return math.inf if last is None else max(0.0, self.now() - last.at)

    def usual_gas(self) -> float | None:
        values = sorted(m.gas_kohm for items in self.rooms.values() for m in items if m.gas_kohm)
        return values[len(values) // 2] if len(values) >= 3 else None

    def air_words(self, entry: Measured) -> str:
        usual = self.usual_gas()
        if entry.gas_kohm is None or usual is None:
            return ""
        ratio = entry.gas_kohm / usual
        if ratio < 0.5:
            return "The air sensor read much lower than usual there, which smells, fumes or smoke can do"
        if ratio < 0.8:
            return "The air sensor read a bit lower than usual there, which smells or fumes can do"
        return "The air sensor read about usual there"


def _room_words(log: ClimateLog, room: str, entry: Measured, about: str, now: float) -> str:
    when = ago(now - entry.at)
    parts = []
    if about in ("temperature", "all") and entry.celsius is not None:
        parts.append(f"The {room} was {degrees(entry.celsius)} near the floor when I measured it {when}")
        if entry.humidity_pct is not None:
            parts[-1] += f", with {round(entry.humidity_pct)} percent humidity"
    elif about == "humidity" and entry.humidity_pct is not None:
        parts.append(f"The {room} had {round(entry.humidity_pct)} percent humidity when I measured it {when}")
        if entry.dew_c is not None:
            parts.append(f"Any window there colder than about {degrees(entry.dew_c)} would run wet")
    elif about == "air":
        words = log.air_words(entry)
        if not words:
            return f"I measured the {room} {when}, but I don't know its usual air well enough to compare yet. My air sensor only gives a rough hint at smells and fumes, not carbon dioxide or carbon monoxide."
        return f"{words}, when I measured it {when}. It's only a rough hint, not carbon dioxide or carbon monoxide."
    if not parts:
        return f"I measured the {room} {when}, but my air sensor didn't give me that."
    text = ". ".join(parts) + "."
    if not entry.settled:
        text += " The reading was still settling, so it may be a little off."
    return text


def answer(log: ClimateLog | None, room: str, about: str, known: list[str], here: str | None = None, live=None, now: float | None = None) -> str:
    if log is None:
        return "I can't keep track of the rooms' air on this body."
    now = log.now() if now is None else now
    room = room.strip().lower()
    for word, start in CAN_NOT.items():
        if room == word or room.endswith(" " + word):
            return f"{start}. I only measure the air in rooms I can drive into, near the floor, and a reading is only as fresh as my last visit."
    if room in ("", "here", "in here", "this room"):
        if live is not None and getattr(live, "present", False) and live.temperature_c is not None:
            where = f"Here in the {here}" if here else "Here"
            text = f"{where} it's {degrees(live.temperature_c)} near the floor"
            if live.humidity_pct is not None:
                text += f", with {round(live.humidity_pct)} percent humidity"
            text += "."
            if live.warming:
                text += " My air sensor is still warming up, so that may be a little off."
            return text
        if live is None or not getattr(live, "present", False):
            return "I don't have an air sensor on this body, so I can't tell."
        return "My air sensor isn't giving a reading just now."
    entry = log.latest(room)
    if entry is None:
        if room in known:
            return f"I haven't measured the {room} yet. I'll do it on my next round of the rooms."
        return f"I don't know where the {room} is yet, so I haven't measured it."
    return _room_words(log, room, entry, about, now)


def compare(log: ClimateLog | None, which: str, now: float | None = None) -> str:
    if log is None or not log.rooms:
        return "I haven't measured any rooms yet."
    now = log.now() if now is None else now
    latest = [m for m in (log.latest(room) for room in log.rooms) if m is not None]
    if which in ("humid", "damp"):
        scored = [m for m in latest if m.humidity_pct is not None]
        if not scored:
            return "I don't have humidity readings for the rooms yet."
        top = max(scored, key=lambda m: m.humidity_pct)
        return f"The {top.room} was the most humid, {round(top.humidity_pct)} percent when I measured it {ago(now - top.at)}."
    scored = [m for m in latest if m.celsius is not None]
    if not scored:
        return "I don't have temperatures for the rooms yet."
    pick = min(scored, key=lambda m: m.celsius) if which in ("cold", "coldest", "chilly") else max(scored, key=lambda m: m.celsius)
    word = "coldest" if which in ("cold", "coldest", "chilly") else "warmest"
    if len(scored) == 1:
        return f"I've only measured the {pick.room} so far: {degrees(pick.celsius)} near the floor, {ago(now - pick.at)}."
    return f"The {pick.room} was the {word}, {degrees(pick.celsius)} near the floor when I measured it {ago(now - pick.at)}."


class ClimateRound(Activity):
    kind = "climate_round"

    def describe(self) -> str:
        return f"measuring the air in the {self.request.place}" if self.request.place else "measuring the air in each room"

    def _order(self, kit: Kit, log: ClimateLog) -> list[str]:
        if self.request.place:
            return [self.request.place] if find_place(kit, self.request.place) is not None else []
        rooms = []
        for name in kit.rooms():
            place = kit.place_at(name)
            if place is not None and log.age(name) > FRESH_S and private_room(kit, place[0], place[1]) is None:
                rooms.append((name, place))
        if not rooms:
            return []
        start = where(kit) or (0.0, 0.0)
        stalest = max(rooms, key=lambda item: (log.age(item[0]), -math.hypot(item[1][0] - start[0], item[1][1] - start[1])))
        rest = tour([(name, place[0], place[1]) for name, place in rooms if name != stalest[0]], (stalest[1][0], stalest[1][1]))
        return [stalest[0]] + [item[0] for item in rest]

    def _why_stop(self, kit: Kit, wheels: Wheels) -> Ending | None:
        if self.asker.own and kit.talking():
            return Ending("stopped", "someone started talking to you, so you put your round of the rooms off until later")
        if kit.battery_low():
            return Ending("battery", "your battery got low during your round of the rooms")
        battery = kit.battery_pct()
        if battery is not None and battery < KEEP_GOING_BATTERY:
            return Ending("battery", f"your battery fell to {round(battery)} percent, so you stopped your round of the rooms")
        reason = wheels.why_not()
        if reason:
            return Ending("stopped", f"you stopped your round of the rooms ({reason})")
        return None

    async def _settle(self, kit: Kit, wheels: Wheels):
        start = kit.pace.now()
        samples: list[tuple[float, float | None, float | None]] = []
        last = None
        while True:
            stop = self._why_stop(kit, wheels)
            if stop is not None:
                return last, False, kit.pace.now() - start, stop, False
            if self.asker.own and kit.hushed():
                return last, False, kit.pace.now() - start, None, True
            now = kit.pace.now()
            reading = kit.body.telemetry.air_reading(kit.body.clock.now(), AIR_MAX_AGE_S)
            if reading is not None and reading.present:
                last = reading
                samples.append((now, reading.temperature_c, reading.humidity_pct))
                while samples and now - samples[0][0] > STEADY_S:
                    samples.pop(0)
                waited = now - start
                if waited >= SETTLE_MIN_S and now - samples[0][0] >= STEADY_S * 0.9:
                    temps = [c for _, c, _ in samples if c is not None]
                    hums = [h for _, _, h in samples if h is not None]
                    steady = (not temps or max(temps) - min(temps) <= STEADY_C) and (not hums or max(hums) - min(hums) <= STEADY_RH)
                    if steady:
                        return reading, True, waited, None, False
            if now - start >= SETTLE_MAX_S:
                return last, False, now - start, None, False
            await kit.pace.sleep(SAMPLE_S)

    async def run(self, kit: Kit) -> Ending:
        log = kit.climate
        own = self.asker.own
        if log is None or not can_drive(kit):
            return Ending("failed", "you can't do a round of the rooms on this body", "" if own else "I can't do a round of the rooms on this body.")
        if kit.body.telemetry.air is None:
            return Ending("failed", "this body has no air sensor, so a round of the rooms would measure nothing", "" if own else "This body has no air sensor, so I can't measure the rooms.")
        if where(kit) is None:
            return Ending("failed", "you have lost track of where you are", "" if own else "I've lost track of where I am. I'll know again after a visit to my charger.")
        rooms = self._order(kit, log)
        asked = find_place(kit, self.request.place) if self.request.place else None
        if asked is not None and private_room(kit, asked[0], asked[1]) is not None:
            return Ending("done", f"the {self.request.place} is private, so you did not go in to measure it", "" if own else f"The {self.request.place} is private, so I don't go in to measure it.")
        if not rooms:
            if self.request.place:
                return Ending("failed", f"you do not know where the {self.request.place} is", "" if own else f"I don't know where the {self.request.place} is yet.")
            known = kit.rooms()
            text = "you have measured every room you know recently" if known else "you don't know any rooms yet"
            say = "" if own else ("I've measured every room I know just recently." if known else "I don't know my way round the rooms yet.")
            return Ending("done", text, say)
        docked = kit.body.telemetry.docked
        wheels = Wheels(kit).open()
        measured: list[Measured] = []
        skipped: list[str] = []
        ending: Ending | None = None
        try:
            if docked and wheels.why_not() is None:
                await leave_dock(kit, wheels)
            for room in rooms:
                ending = self._why_stop(kit, wheels)
                if ending is not None:
                    break
                place = find_place(kit, room)
                if place is None:
                    skipped.append(room)
                    continue
                x, y, radius = place
                trip = await go(kit, x, y, radius)
                if not trip.ok:
                    if trip.how in ("stopped", "battery"):
                        ending = Ending("stopped" if trip.how == "stopped" else "battery", f"your round of the rooms stopped on the way to the {room} ({trip.text})")
                        break
                    skipped.append(room)
                    kit.note(f"you could not get to the {room} on your round of the rooms ({trip.text})")
                    continue
                await wheels.halt()
                if own and kit.hushed():
                    skipped.append(room)
                    kit.note(f"someone in the {room} was busy, so you left measuring it for later")
                    continue
                reading, settled, waited, stop, left = await self._settle(kit, wheels)
                if left:
                    skipped.append(room)
                    kit.note(f"someone in the {room} got busy, so you left measuring it for later")
                    continue
                if reading is not None and (stop is None or settled):
                    entry = log.add(room, reading, settled, waited)
                    measured.append(entry)
                    kit.note(f"you measured the {room}: " + ", ".join(part for part in (
                        None if entry.celsius is None else f"{round(entry.celsius, 1)} C near the floor",
                        None if entry.humidity_pct is None else f"{round(entry.humidity_pct)} % humidity",
                        None if entry.dew_c is None else f"dew point {round(entry.dew_c, 1)} C",
                    ) if part) + ("" if settled else " (still settling)"))
                if stop is not None:
                    ending = stop
                    break
        finally:
            await wheels.halt()
            wheels.close()
        names = [m.room for m in measured]
        done_text = f"you measured {', '.join(names)}" if names else "you measured no rooms"
        if skipped:
            done_text += f"; you could not measure {', '.join(skipped)}"
        if ending is not None:
            return Ending(ending.how, f"{ending.text}; {done_text}", ending.say)
        battery = kit.battery_pct()
        go_home = docked or (battery is not None and battery < HOME_BATTERY)
        say = ""
        if not own:
            if len(measured) == 1 and self.request.place:
                say = answer(log, self.request.place, "all", kit.rooms())
            elif names:
                say = f"I've measured the {listing(names)}."
            else:
                say = "I couldn't get to any of the rooms."
        return Ending("done", done_text, say, Request("go_home") if go_home else None)


class ClimatePlanner:
    def __init__(self, commands, kit: Kit, log: ClimateLog, hushed=lambda: False):
        self.commands = commands
        self.kit = kit
        self.log = log
        self.hushed = hushed
        self.checked_at = -math.inf
        self.started_at = -math.inf
        self.enabled = True

    def stale_rooms(self) -> list[str]:
        out = []
        for name in self.kit.rooms():
            place = self.kit.place_at(name)
            if place is not None and self.log.age(name) >= STALE_S and private_room(self.kit, place[0], place[1]) is None:
                out.append(name)
        return out

    def why_not(self) -> str | None:
        commands = self.commands
        if not self.enabled:
            return "the climate round is switched off"
        if commands.runner.current is not None or commands.tasks:
            return "you are busy"
        if self.kit.body.telemetry.air is None:
            return "this body has no air sensor"
        if where(self.kit) is None:
            return "you have lost track of where you are"
        if self.kit.talking():
            return "someone is talking to you"
        sit = commands.situation()
        if sit.quiet or sit.asleep or sit.resting or sit.waking or sit.low_battery or sit.alarm or sit.calm or sit.fault or not sit.can_move or sit.blocked or sit.privacy:
            return "this is not a good time"
        battery = self.kit.battery_pct()
        if battery is None or battery < ROUND_BATTERY:
            return "your battery is not charged enough"
        if self.hushed():
            return "someone nearby is busy"
        if not self.stale_rooms():
            return "every room was measured recently"
        return None

    def tick(self) -> bool:
        now = self.kit.pace.now()
        if now - self.checked_at < CHECK_EVERY_S or now - self.started_at < ROUND_GAP_S:
            return False
        self.checked_at = now
        if self.why_not() is not None:
            return False
        self.started_at = now
        self.commands._spawn(self.commands.act(Request("climate_round"), PEBBLE, "routine"))
        return True
