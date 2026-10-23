import asyncio
import logging
import math
import re
from dataclasses import dataclass

from ..activities.gate import PRIVACY_NO
from ..understand.request import CHAT, Request
from ..understand.resolve import Reading
from ..understand.words import normalise
from .cues import Closeness, Sleepers, frame_cue, in_bathroom, sight_cue
from .rooms import PrivateRooms
from .words import PRIVACY, RESUME, WHY, read

log = logging.getLogger(__name__)

REFUSAL = PRIVACY_NO
WHY_ANSWER = "To give you some privacy."
OKAY = "Okay."
LOGGED = "looked away for privacy"
OBSERVED = "You are looking away for a while to give someone privacy. Don't look round, and don't talk about it."
WHY_KEEP_S = 3600.0
CUE_S = 300.0
BATHROOM_S = 120.0
CLOSE_S = 120.0
DOOR_HOLD_S = 60.0
GRACE_S = 600.0
DOOR_S = 15.0
DOOR_STEP_S = 0.25
PERMIT_S = 900.0
NIGHT_HOURS = (21, 7)
YES = re.compile(r"^(?:yes|yeah|yep|yup|ja|sure|ok|okay|alright|come in|you can come in|come on in|it is fine|it is ok|that is fine|of course|go ahead|in you come)\b")
NO = re.compile(r"^(?:no|nope|nah|nee|not now|not yet|do not come in|stay out|stay there|wait|hang on|one minute|one sec|just a minute|go away|do not)\b")
KEEP_ALWAYS = ("floor",)
KEEP_OUT_MARGIN_M = 0.5
KEEP_OUT_MIN_M = 0.3
SLEEPER_GAP_M = 1.0
FENCE_AHEAD_M = 0.4


@dataclass
class Hold:
    why: str
    by: str | None
    until: float
    until_said: bool
    started: float


def door_answer(text: str, name: str = "pebble") -> bool | None:
    clean = " ".join(re.sub(r"[,.!?;]", " ", normalise(text, name)).split())
    if NO.match(clean):
        return False
    if YES.match(clean):
        return True
    return None


class Privacy:
    def __init__(self, life):
        self.life = life
        p = life.p
        self.p = p
        self.eyes = p.eyes
        self.kit = life.commands.runner.kit
        self.name = getattr(p.books, "name", "Pebble") or "Pebble"
        alive = getattr(life, "alive", None)
        self.rooms = PrivateRooms(getattr(alive, "rooms", None), self.mono, self._doorways)
        self.holds: list[Hold] = []
        self.last_away = -math.inf
        self.grace_until = -math.inf
        self.sleepers = Sleepers()
        self.sleeper_spots: list = []
        self.closeness = Closeness()
        self.permits: dict[str, float] = {}
        self.door_wait: tuple[str, asyncio.Future] | None = None
        self.told: tuple | None = None
        self.head_down = False
        self.looked_away = 0
        self.rules = None
        self.kit.privacy = self
        life.commands.privacy = self
        if hasattr(self.eyes, "snapshot_veto"):
            self.eyes.snapshot_veto = self.frame_veto
            self.eyes.on_cue = self.cue_seen
        pictures = getattr(life.commands, "pictures", None)
        if pictures is not None:
            pictures.guard = self
        nav = getattr(life, "nav", None)
        if nav is not None and hasattr(nav, "keep_out"):
            nav.keep_out = self.keep_out

    def mono(self) -> float:
        return self.kit.pace.now()

    def _doorways(self) -> list:
        chart = getattr(getattr(self.life, "nav", None), "chart", None)
        try:
            places = chart.places if chart is not None else []
        except Exception:
            return []
        return [(place.x, place.y) for place in places if getattr(place, "kind", "") == "doorway"]

    def active(self, mono: float | None = None) -> bool:
        mono = self.mono() if mono is None else mono
        before = bool(self.holds)
        self.holds = [h for h in self.holds if h.until > mono]
        if before and not self.holds:
            self._resumed()
        return bool(self.holds)

    def night(self) -> bool:
        if self.p.permissions.quiet:
            return True
        hour = self.p.clock.local().hour
        return hour >= NIGHT_HOURS[0] or hour < NIGHT_HOURS[1]

    def place(self) -> str | None:
        alive = getattr(self.life, "alive", None)
        rooms = getattr(alive, "rooms", None)
        try:
            return rooms.where_am_i() if rooms is not None else None
        except Exception:
            return None

    def private_places(self) -> frozenset:
        rooms = self.rooms._all()
        return frozenset(name for name in rooms if self.rooms.private(name))

    def private_view(self) -> bool:
        here = self.place()
        if here is not None and self.rooms.private(here):
            return True
        odometer = getattr(self.life, "odometer", None)
        if odometer is None or not getattr(odometer, "usable", False):
            return False
        x, y, heading = odometer.pose()
        camera = self.eyes.camera() if callable(getattr(self.eyes, "camera", None)) else "front"
        aim = math.radians(heading + (180.0 if camera == "rear" else 0.0))
        for reach in (0.8, 1.5):
            room = self.rooms.private_at(x + reach * math.cos(aim), y + reach * math.sin(aim))
            if room is not None and room not in self.permits:
                return True
        return False

    def refusal(self) -> str | None:
        mono = self.mono()
        if self.active(mono) or self.sleepers.near(mono) or self.private_view():
            return REFUSAL
        return None

    def hushed(self) -> bool:
        return self.sleepers.near(self.mono())

    def whisper(self) -> bool:
        return self.sleepers.near(self.mono())

    def observation(self) -> str:
        return OBSERVED if self.active() else ""

    def hidden(self, person, sight) -> bool:
        if person.track in self.sleepers.asleep:
            return True
        if in_bathroom(person, sight):
            return True
        alive = getattr(self.life, "alive", None)
        room_of = getattr(alive, "_room_of", None)
        if room_of is None:
            return False
        try:
            room = room_of(person.track, sight)
        except Exception:
            return False
        return room is not None and self.rooms.private(room) and not self.permitted(room) and room != self.place()

    def screen(self, sight):
        if sight is None or not sight.people:
            return sight
        kept = tuple(p for p in sight.people if not self.hidden(p, sight))
        if len(kept) == len(sight.people):
            return sight
        from dataclasses import replace

        return replace(sight, people=kept)

    def frame_veto(self, people, things, undressed) -> bool:
        mono = self.mono()
        if any(h.until > mono for h in self.holds):
            return True
        if self.sleepers.near(mono) and people:
            return True
        return frame_cue(people, things, undressed, self.place(), self.night()) is not None

    def cue_seen(self) -> None:
        loop = _loop()
        if loop is None:
            self.look_away("cue", None, CUE_S, turn=False)
            return
        loop.call_soon_threadsafe(self.look_away, "cue", None, CUE_S, False, None, False)

    def permitted(self, room: str) -> bool:
        until = self.permits.get(room)
        return until is not None and until > self.mono()

    def permit(self, room: str, seconds: float = PERMIT_S) -> None:
        self.permits[room] = self.mono() + seconds
        self.end("door")

    def blocks(self, x: float, y: float) -> str | None:
        room = self.rooms.private_at(x, y)
        if room is None or self.permitted(room):
            return None
        return room

    def keep_out(self) -> list:
        odometer = getattr(self.life, "odometer", None)
        if odometer is None or not getattr(odometer, "usable", False):
            return []
        x, y, _ = odometer.pose()
        out = []
        for name, room in self.rooms._all().items():
            if not self.rooms.private(name) or self.permitted(name) or math.hypot(room.x - x, room.y - y) <= room.radius:
                continue
            out.append((room.x, room.y, max(KEEP_OUT_MIN_M, room.radius - KEEP_OUT_MARGIN_M)))
        if self.sleepers.near(self.mono()):
            out.extend((sx, sy, SLEEPER_GAP_M) for sx, sy in self.sleeper_spots)
        if self.rules is not None:
            out.extend(self.rules.circles())
        return out

    def fence(self, goal: tuple[float, float] | None) -> str | None:
        odometer = getattr(self.life, "odometer", None)
        if goal is None or odometer is None or not getattr(odometer, "usable", False):
            return None
        x, y, _ = odometer.pose()
        gap = math.hypot(goal[0] - x, goal[1] - y)
        if gap > FENCE_AHEAD_M:
            goal = (x + (goal[0] - x) / gap * FENCE_AHEAD_M, y + (goal[1] - y) / gap * FENCE_AHEAD_M)
        allowed = tuple(room for room in self.permits if self.permitted(room))
        return self.rooms.crossing(x, y, goal[0], goal[1], allowed)

    def door_for(self, room: str) -> tuple[float, float] | None:
        odometer = getattr(self.life, "odometer", None)
        if odometer is None or not getattr(odometer, "usable", False):
            return None
        x, y, _ = odometer.pose()
        return self.rooms.door(room, x, y)

    def may_enter_unanswered(self, room: str, asker) -> bool:
        if asker is None or not getattr(asker, "owner", False):
            return False
        inside = [who for who in self.rooms.occupants(room) if who != asker.id]
        return not inside

    async def ask_door(self, room: str, line: str, loud: bool = False, seconds: float = DOOR_S) -> bool | None:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.door_wait = (room, future)
        self.look_away("door", None, max(DOOR_HOLD_S, seconds + 10.0), turn=False)
        self._say(line, loud)
        until = self.mono() + seconds
        try:
            while not future.done() and self.mono() < until:
                await self.kit.pace.sleep(DOOR_STEP_S)
            return future.result() if future.done() else None
        finally:
            if self.door_wait is not None and self.door_wait[1] is future:
                self.door_wait = None

    def leave_door(self) -> None:
        if any(h.why == "door" for h in self.holds):
            self.end("door")

    def at_door(self, room: str, seconds: float = DOOR_HOLD_S) -> None:
        self.look_away("door", None, seconds, turn=False)

    def _say(self, line: str, loud: bool = False) -> None:
        speak = getattr(self.kit, "say_loud", None) if loud else None
        (speak or self.kit.say)(line)

    def heard(self, heard, addressed=None):
        text = getattr(heard, "text", "") or ""
        if self.door_wait is not None and not self.door_wait[1].done():
            answer = door_answer(text, self.name)
            if answer is not None:
                self.door_wait[1].set_result(answer)
                return self._done()
        ask = read(text, self.name)
        if ask is None:
            return None
        mono = self.mono()
        person = getattr(heard, "person_id", None)
        if ask.kind == WHY:
            if addressed is False or (not self.active(mono) and mono - self.last_away > WHY_KEEP_S):
                return None
            return self._done(WHY_ANSWER)
        if ask.kind == RESUME:
            if not self.holds or not self.resume(person):
                return None
            return self._done()
        if ask.soft and self._playing_or_searching():
            return None
        self.look_away("asked", person, ask.seconds, until_said=ask.until_said)
        return self._done(OKAY if addressed is not False else "", whisper=True)

    def _playing_or_searching(self) -> bool:
        current = self.life.commands.runner.current
        return current is not None and (getattr(current, "game", False) or current.kind in ("find", "hide_seek", "red_light", "statues"))

    def _done(self, line: str = "", whisper: bool = False) -> asyncio.Task | None:
        async def answer():
            if line:
                await self.p.voice.say(line, whisper=whisper or self.p.permissions.quiet)
            return Reading(CHAT, answered=True, source="privacy")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        task = loop.create_task(answer())
        self.life.commands.tasks.add(task)
        task.add_done_callback(self.life.commands.tasks.discard)
        return task

    def resume(self, person: str | None) -> bool:
        before = len(self.holds)
        kept = []
        for hold in self.holds:
            mine = hold.why in ("asked", "cue", "close") and (person is None or hold.by is None or hold.by == person)
            if not mine:
                kept.append(hold)
        self.holds = kept
        if len(kept) == before:
            return False
        self.grace_until = self.mono() + GRACE_S
        if not self.holds:
            self._resumed()
        return True

    def end(self, why: str) -> None:
        before = bool(self.holds)
        self.holds = [h for h in self.holds if h.why != why]
        if before and not self.holds:
            self._resumed()

    def look_away(self, why: str, by: str | None, seconds: float, until_said: bool = False, angle: float | None = None, turn: bool = True) -> None:
        mono = self.mono()
        first = not self.active(mono)
        self.holds = [h for h in self.holds if not (h.why == why and h.by == by)]
        self.holds.append(Hold(why, by, mono + seconds, until_said, mono))
        if why != "door":
            self.last_away = mono
        if angle is None and turn:
            angle = self._angle_to_someone()
        self.sync()
        if first:
            self.looked_away += 1
            self.p.blackbox.record("privacy", what=LOGGED)
            self._glance_away()
        if turn and why != "door":
            self._turn_away(angle, by, why == "asked")

    def _angle_to_someone(self) -> float | None:
        from ..activities.seeing import body_bearing

        sight = self.eyes.latest(1.5) if not getattr(self.eyes, "private", False) else None
        if sight is None or not sight.people:
            return None
        person = max(sight.people, key=lambda p: p.height_frac)
        return body_bearing(person.bearing_deg, sight.camera)

    def _glance_away(self) -> None:
        face = self.p.face
        try:
            face.show("sleepy")
            attend = getattr(face, "attend", None)
            if attend is not None:
                attend(True)
            face.gaze(0.8, 0.8)
        except Exception:
            log.exception("privacy: could not turn the eyes away")

    def _turn_away(self, angle: float | None, by: str | None, asked: bool = True) -> None:
        from ..activities.gate import decide
        from .look import LookAway

        commands = self.life.commands
        runner = commands.runner
        current = runner.current
        if current is not None and (not asked or current.kind == "look_away" or current.urgent or current.homing or current.battery):
            return
        asker = commands.asker_for(by) if by is not None else None
        if asker is None or asker.id is None:
            from ..activities.gate import PEBBLE

            asker = PEBBLE
        request = Request("look_away")
        try:
            verdict = decide(request, asker, self.life.situation())
        except Exception:
            log.exception("privacy: the gate could not decide")
            return
        if verdict.answer != "yes":
            return
        runner.start(LookAway(request, asker, None, angle_deg=angle))

    def _resumed(self) -> None:
        self.sync()
        face = self.p.face
        try:
            attend = getattr(face, "attend", None)
            if attend is not None:
                attend(False)
            face.show("neutral")
        except Exception:
            log.exception("privacy: could not look back")
        if self.head_down:
            self.head_down = False
            body = self.p.body
            if getattr(body, "connected", False):
                self.life.commands._spawn(body.tilt(body.profile.tilt_rest))

    def keep(self) -> tuple:
        keep = list(KEEP_ALWAYS)
        current = self.life.commands.runner.current
        if current is not None and current.kind == "go_home":
            keep.append("tag")
        return tuple(keep)

    def sync(self) -> None:
        blind = bool(self.holds) and not self.life.alarm()
        wanted = (blind, self.keep() if blind else ())
        if wanted == self.told:
            return
        self.told = wanted
        told = getattr(self.eyes, "set_privacy", None)
        if told is None:
            return
        try:
            told(blind, wanted[1])
        except Exception:
            log.exception("privacy: the eyes would not look away")

    def watch(self, sight) -> bool:
        mono = self.mono()
        on = self.active(mono)
        self.sync()
        if self.life.alarm():
            return on
        if on or sight is None:
            return on
        place = self.place()
        night = self.night()
        self._occupants(sight)
        asleep = self.sleepers.update(sight, mono, night, place)
        if asleep:
            self.sleeper_spots = self._spots(sight, asleep)
        undressed = self.eyes.undressed() if callable(getattr(self.eyes, "undressed", None)) else None
        cue = sight_cue(sight, undressed, place, night)
        if cue == "undress" and undressed is not None and undressed[0] >= 0.35:
            self.look_away("cue", None, CUE_S)
            return True
        if cue is not None and mono >= self.grace_until:
            self.look_away("cue", None, BATHROOM_S if cue == "bathroom" else CUE_S)
            return True
        if self.closeness.update(sight, mono):
            self.closeness.since = None
            self.look_away("close", None, CLOSE_S)
            return True
        return False

    def _spots(self, sight, tracks) -> list:
        alive = getattr(self.life, "alive", None)
        place_of = getattr(alive, "_place_of", None)
        if place_of is None:
            return []
        out = []
        for person in sight.people:
            if person.track in tracks:
                try:
                    spot = place_of(person, sight)
                except Exception:
                    spot = None
                if spot is not None:
                    out.append(spot)
        return out

    def _occupants(self, sight) -> None:
        alive = getattr(self.life, "alive", None)
        if alive is None or not sight.people:
            return
        room_of = getattr(alive, "_room_of", None)
        if room_of is None:
            return
        person_id, _, _ = alive.who_is_here()
        for person in sight.people:
            room = room_of(person.track, sight)
            if room is None:
                continue
            who = person_id if person_id is not None and len(sight.people) == 1 else f"track:{person.track}"
            self.rooms.saw(who, room)

    def status(self) -> dict:
        mono = self.mono()
        return {"looking_away": self.active(mono), "holds": len(self.holds), "sleeper_near": self.sleepers.near(mono), "private_rooms": sorted(self.private_places())}


def _loop():
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None
