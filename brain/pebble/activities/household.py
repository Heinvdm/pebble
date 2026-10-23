import logging
import math
from dataclasses import dataclass

from ..alive.games import GameTable, HideSeek, RedLight, Statues
from ..body.telemetry import pack_fraction
from ..safety.room import LIT_LUX
from ..understand.request import Request
from ..understand.resolve import Reading
from .asks import read
from .chirp import FindChirp
from .climate import ClimateLog, ClimatePlanner, ClimateRound, answer, compare
from .commands import ADDED, RECENT_KEEP
from .quake import QuakeRound
from .rounds import spot_names

log = logging.getLogger(__name__)

ACTIVITIES = {
    "climate_round": ClimateRound,
    "find_chirp": FindChirp,
    "quake_round": QuakeRound,
    "red_light": RedLight,
    "statues": Statues,
    "hide_seek": HideSeek,
}
DRIVES = frozenset({"climate_round", "find_chirp", "hide_seek"})
GAMES = frozenset({"red_light", "statues", "hide_seek"})
TALK_QUIET_S = 30.0
AGAIN_S = 120.0
LIVE_AIR_S = 30.0
NAME_SIGHT_S = 1.0

ADDED.update(ACTIVITIES)


@dataclass(frozen=True)
class Stale:
    present: bool = True
    temperature_c: float | None = None
    humidity_pct: float | None = None
    warming: bool = False


class Household:
    def __init__(self, life):
        self.life = life
        p = life.p
        self.p = p
        commands = life.commands
        self.commands = commands
        kit = commands.runner.kit
        self.kit = kit
        self.climate = ClimateLog(p.store, p.clock)
        chaos = getattr(p, "chaos", None)
        lively = chaos is not None and getattr(chaos, "enabled", False)
        self.table = GameTable((lambda: chaos.stream("choices")) if lively else None, kit.pace.now, self._record)
        self.planner = ClimatePlanner(commands, kit, self.climate, self.hushed)
        self.heard_at = -math.inf
        self.playing: str | None = None
        self.last_game: tuple[str, float] | None = None
        kit.talking = self.talking
        kit.battery_pct = self.battery_pct
        kit.dark = self.dark
        kit.rooms = self.rooms
        kit.climate = self.climate
        kit.chirps = self.chirps if self.finds_chirps else None
        kit.chaos = (lambda lever: chaos.stream(lever)) if lively else None
        kit.here = self.here
        kit.usual_room = self.usual_room
        kit.last_present = self.last_present
        kit.hushed = self.hushed
        kit.name_of = self.name_of
        commands.household = self

    def _record(self, kind: str, **data) -> None:
        self.p.blackbox.record(f"game_{kind}", **data)

    @property
    def hearing(self):
        return getattr(getattr(self.p, "safety", None), "hearing", None)

    @property
    def finds_chirps(self) -> bool:
        return callable(getattr(self.hearing, "chirps", None))

    def chirps(self, since: float) -> list:
        hearing = self.hearing
        if hearing is None or not callable(getattr(hearing, "chirps", None)):
            return []
        return list(hearing.chirps(since))

    def talking(self) -> bool:
        conversation = getattr(self.p, "conversation", None)
        live = getattr(conversation, "live", None)
        if live is not None:
            try:
                if live():
                    return True
            except Exception:
                log.exception("could not ask the conversation if it is live")
        if self.kit.pace.now() - self.heard_at < TALK_QUIET_S:
            return True
        company = self.life.company
        now = self.p.clock.now()
        return any(now - company.presence.last_heard(pid) < TALK_QUIET_S for pid in company.book.people)

    def battery_pct(self) -> float | None:
        sensors = getattr(self.life, "sensors", None)
        battery = getattr(sensors, "battery", None) if sensors is not None else None
        levels = []
        if battery is not None and battery.percent is not None:
            levels.append(float(battery.percent))
        fraction = pack_fraction(self.p.body.telemetry.pack_mv)
        if fraction is not None:
            levels.append(fraction * 100.0)
        return min(levels) if levels else None

    def dark(self) -> bool:
        sensors = getattr(self.life, "sensors", None)
        lux = getattr(sensors, "light_lux", None) if sensors is not None else None
        return lux is not None and lux < LIT_LUX

    def _alive(self):
        return getattr(self.commands, "alive", None)

    def rooms(self) -> list[str]:
        alive = self._alive()
        return sorted(alive.rooms.rooms) if alive is not None else []

    def places(self) -> list[str]:
        names = list(self.rooms())
        for name in spot_names(self.kit.nav):
            if name not in names:
                names.append(name)
        return names

    def here(self, within: float) -> list[tuple[str, str]]:
        company = self.life.company
        now = self.p.clock.now()
        out = []
        for pid in company.presence.here(now, within):
            person = company.book.get(pid)
            if person is not None:
                out.append((pid, person.label))
        return out

    def usual_room(self, person_id: str) -> str | None:
        alive = self._alive()
        return alive.usual_room(person_id) if alive is not None else None

    def last_present(self, person_id: str) -> float:
        return self.life.company.presence.last_present(person_id)

    def hushed(self) -> bool:
        alive = self._alive()
        try:
            return bool(alive.hushed()) if alive is not None else False
        except Exception:
            log.exception("could not tell if someone is busy")
            return False

    def name_of(self, track: int | None) -> str | None:
        hands = getattr(self.life, "hands", None)
        eyes = self.p.eyes
        if track is None or hands is None or not getattr(eyes, "available", False):
            return None
        person = hands.who(track, eyes.latest(NAME_SIGHT_S), self.p.clock.now())
        return person.label if person is not None else None

    def _live_air(self):
        telemetry = self.p.body.telemetry
        fresh = telemetry.air_reading(self.p.clock.now(), LIVE_AIR_S)
        if fresh is not None:
            return fresh
        air = telemetry.air
        return None if air is None or not air.present else Stale()

    def climate_words(self, room: str, about: str) -> str:
        alive = self._alive()
        where = alive.rooms.where_am_i() if alive is not None else None
        return answer(self.climate, room, about, self.places(), here=where, live=self._live_air())

    def _again(self) -> str:
        if self.last_game is None:
            return ""
        kind, at = self.last_game
        return kind if self.kit.pace.now() - at <= AGAIN_S else ""

    async def consider(self, heard) -> Reading | None:
        self.heard_at = self.kit.pace.now()
        current = self.commands.runner.current
        hear = getattr(current, "heard", None)
        if hear is not None:
            try:
                if hear(heard.text, heard.person_id, heard.label):
                    self.p.blackbox.record("household", text=heard.text[:120], ask="game_line", person=heard.person_id)
                    return Reading(Request("chat"), source="household", answered=True)
            except Exception:
                log.exception("the game could not take what was said")
        ask = read(
            heard.text,
            self.places(),
            getattr(self.commands, "name", "pebble") or "pebble",
            has_scores=self.table.has_scores(),
            timer_set=self.table.timer_set(),
            timer_running=self.table.timer_running(),
            last_game=self._again(),
        )
        if ask is None:
            return None
        understanding = getattr(self.commands, "understanding", None)
        if understanding is not None and not understanding.claims(heard.text, name=getattr(self.commands, "name", "pebble") or "pebble"):
            self.p.blackbox.record("household_passed", ask=ask.kind, person=heard.person_id)
            return None
        self.p.blackbox.record("household", text=heard.text[:120], ask=ask.kind, person=heard.person_id)
        self.commands.recent.append(f"{heard.label.lower()}: {heard.text[:120]}")
        del self.commands.recent[:-RECENT_KEEP]
        await self._do(ask, heard)
        return Reading(Request("chat"), source="household", answered=True)

    async def _say(self, text: str, heard, what: str) -> None:
        commands = self.commands
        commands.note(f"{heard.label} asked you {what}; you said: {text}", False)
        await commands.speak(text, False)

    async def _act(self, request: Request, heard) -> None:
        commands = self.commands
        if heard.stop is not None and request.kind in DRIVES:
            commands.note(f"{heard.label} said stop in the same breath as asking you to do that, so you stayed still", False)
            return
        await commands.act(request, commands.asker_heard(heard), "heard")

    async def _do(self, ask, heard) -> None:
        kind = ask.kind
        commands = self.commands
        if kind == "climate_round":
            await self._act(Request("climate_round", place=ask.room), heard)
            return
        if kind == "find_chirp":
            await self._act(Request("find_chirp"), heard)
            return
        if kind == "game":
            await self._act(Request(ask.game), heard)
            return
        if commands.situation().asleep:
            await commands.speak("Mm... I'm asleep.", False)
            return
        table = self.table
        if kind == "climate":
            await self._say(self.climate_words(ask.room, ask.about), heard, f"about the air in the {ask.room}")
        elif kind == "climate_compare":
            await self._say(compare(self.climate, ask.which), heard, "which room was the " + {"warm": "warmest", "cold": "coldest"}.get(ask.which, "most humid"))
        elif kind == "dice":
            await self._say(table.roll(ask.count, ask.sides), heard, "to roll the dice")
        elif kind == "coin":
            await self._say(table.flip(), heard, "to flip a coin")
        elif kind == "score_add":
            who = ask.who
            if who in ("me", "myself"):
                who = heard.label if heard.person_id else ""
            text = table.add(who, ask.points) if who else "Who should I give the points to? Tell me their name."
            await self._say(text, heard, "to keep the score")
        elif kind == "score_read":
            await self._say(table.words(), heard, "for the scores")
        elif kind == "score_one":
            await self._say(table.one(ask.who), heard, "for a score")
        elif kind == "score_reset":
            await self._say(table.reset(), heard, "to clear the scores")
        elif kind == "turn_set":
            await self._say(table.set_turns(ask.seconds), heard, "to time the turns")
        elif kind == "turn_next":
            await self._say(table.start_turn(), heard, "to start the next turn")
        elif kind == "turn_stop":
            await self._say(table.stop_turns(), heard, "to stop the turn timer")
        elif kind == "turn_left":
            await self._say(table.left(), heard, "how long is left")

    def tick(self) -> None:
        if self.kit.chirps is None and self.finds_chirps:
            self.kit.chirps = self.chirps
        current = self.commands.runner.current
        kind = current.kind if current is not None else None
        if self.playing is not None and kind != self.playing:
            self.last_game = (self.playing, self.kit.pace.now())
        self.playing = kind if kind in GAMES else None
        line = self.table.tick()
        if line:
            self.commands._spawn(self.commands.speak(line, False))
        try:
            self.planner.tick()
        except Exception:
            log.exception("the climate planner failed")
