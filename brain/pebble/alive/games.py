import asyncio
import itertools
import logging
import math
import random
import re
import time

from ..activities.base import Activity, Ending
from ..activities.kit import Kit
from ..activities.motion import Wheels, leave_dock, turn_by
from ..activities.rounds import budget, can_drive, go, known_places, private_room, tour, where
from ..activities.seeing import CAMERA_HEIGHT_M, person_gap_m
from ..screen.parse import SceneError, parse_line
from ..screen.stage import SceneStage
from ..things.words import listing
from .gestures import MIN_SCORE
from .hands import _across, _rise, _torso

log = logging.getLogger(__name__)

PERSON_SCORE = 0.5
MOVE_FRAC = 0.25
JUMP_FRAC = 0.6
POINTS_MOVED = 2
FRAMES_MOVED = 2
BOX_FRAC = 0.3
TALL_FRAC = 0.15
SIDE_DEG = 8.0
LOOK_S = 0.1
GRACE_S = 1.2
WATCH_S = 3.0
GAME_MAX_S = 480.0
NOBODY_S = 25.0
LINE_UP_S = 8.0
GREEN_S = (3.0, 7.0)
BACK_S = 6.0
WIN_M = 0.7
MUSIC_S = (5.0, 12.0)
SING_EVERY_S = 3.0
STATUE_ROUNDS = 12
COUNT_GROUP_S = 5.0
SEEK_MAX_S = 600.0
SEEK_TOP = 0.24
NEAR_TOP = 0.12
SEEK_LOOK_S = 0.2
LOOK_ROUND_DEG = 90.0
FOUND_GAP_S = 3.0
TRIES = 3
SCORES_KEEP_S = 12 * 3600.0
TIMER_KEEP_S = 2 * 3600.0
WARN_S = 10.0
DICE_MAX = 6
SIDES_MAX = 100
COUNTING = ("One, two, three, four, five.", "Six, seven, eight, nine, ten.", "Eleven, twelve, thirteen, fourteen, fifteen.", "Sixteen, seventeen, eighteen, nineteen, twenty!")
SECONDS = ("One", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
SONG = (
    "La la la, la la la!",
    "Dum de dum, de dum de dum!",
    "Wiggle, wiggle, shake, shake, shake!",
    "Boogie woogie, la la la!",
    "Dance, dance, dance, round and round!",
    "Ba da ba, ba da ba, ba da ba da ba!",
)
WIN_WORDS = re.compile(r"\b(i win|i won|we win|got you|gotcha|i tagged you|tag|tagged|i made it|i touched you|i reached you|i got you)\b")
CLOSED_EYES = ("eyes 16 12 closed white",)
OPEN_MUSIC = ("eyes 16 14 happy white", "note 5 6 white bounce", "note 26 8 yellow bounce")
AN_NUMBERS = frozenset({8, 11, 18} | set(range(80, 90)))

_scenes = itertools.count(1)
_spare = random.Random()


def a_number(n: int) -> str:
    return f"an {n}" if n in AN_NUMBERS else f"a {n}"


def how_long(seconds: float) -> str:
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds} seconds"
    if seconds == 60:
        return "a minute"
    if seconds == 90:
        return "a minute and a half"
    minutes, rest = divmod(seconds, 60)
    if rest == 0:
        return f"{minutes} minutes"
    return f"{minutes} minutes and {rest} seconds"


def draw_between(kit: Kit, low: float, high: float) -> float:
    stream = kit.chaos("choices") if kit.chaos is not None else None
    if stream is not None:
        try:
            return float(stream.uniform(low, high))
        except Exception:
            log.exception("the chaos stream could not draw")
    return _spare.uniform(low, high)


class GameTable:
    def __init__(self, stream=None, now=time.monotonic, record=lambda kind, **data: None):
        self.stream = stream
        self.now = now
        self.record = record
        self.scores: dict[str, int] = {}
        self.names: dict[str, str] = {}
        self.changed_at = -math.inf
        self.turn_s: float | None = None
        self.turn_ends: float | None = None
        self.turn_at = -math.inf
        self.warned = False
        self.fair = random.SystemRandom()

    def _draw(self, low: int, high: int) -> tuple[int, str]:
        stream = self.stream() if self.stream is not None else None
        if stream is not None:
            try:
                value = int(stream.randint(low, high))
                return value, str((stream.last or {}).get("id", ""))
            except Exception:
                log.exception("the chaos stream could not roll")
        return self.fair.randint(low, high), "system"

    def roll(self, count: int = 1, sides: int = 6) -> str:
        count = max(1, min(DICE_MAX, int(count)))
        sides = max(2, min(SIDES_MAX, int(sides)))
        draws = [self._draw(1, sides) for _ in range(count)]
        values = [value for value, _ in draws]
        self.record("dice", sides=sides, values=values, draws=[draw for _, draw in draws])
        if count == 1:
            return f"It's {a_number(values[0])}."
        return f"{listing([str(v) for v in values])}. That makes {sum(values)}."

    def flip(self) -> str:
        value, draw = self._draw(0, 1)
        side = "heads" if value == 0 else "tails"
        self.record("coin", side=side, draws=[draw])
        return f"It's {side}."

    def _fresh(self) -> None:
        if self.scores and self.now() - self.changed_at > SCORES_KEEP_S:
            self.scores.clear()
            self.names.clear()

    def has_scores(self) -> bool:
        self._fresh()
        return bool(self.scores)

    def add(self, who: str, points: int) -> str:
        self._fresh()
        key = " ".join(who.lower().split())
        if not key:
            return "Who should I give the points to?"
        name = self.names.setdefault(key, who.strip()[:1].upper() + who.strip()[1:])
        self.scores[key] = self.scores.get(key, 0) + int(points)
        self.changed_at = self.now()
        total = self.scores[key]
        self.record("score", who=name, points=int(points), total=total)
        if points >= 0:
            head = "A point" if points == 1 else f"{points} points"
            return f"{head} for {name}. {name} has {total} now."
        taken = -points
        head = "One point" if taken == 1 else f"{taken} points"
        return f"{head} off {name}. {name} has {total} now."

    def one(self, who: str) -> str:
        self._fresh()
        key = " ".join(who.lower().split())
        if key not in self.scores:
            return f"{who.strip().title()} doesn't have any points yet."
        total = self.scores[key]
        return f"{self.names[key]} has {total} {'point' if abs(total) == 1 else 'points'}."

    def words(self) -> str:
        self._fresh()
        if not self.scores:
            return "There are no scores yet."
        ranked = sorted(self.scores.items(), key=lambda item: (-item[1], self.names[item[0]]))
        if len(ranked) == 1:
            key, total = ranked[0]
            return f"{self.names[key]} has {total} {'point' if abs(total) == 1 else 'points'}."
        first_key, first = ranked[0]
        parts = [f"{self.names[first_key]} has {first} {'point' if abs(first) == 1 else 'points'}"] + [f"{self.names[key]} has {total}" for key, total in ranked[1:]]
        tops = [self.names[key] for key, total in ranked if total == first]
        lead = f"{tops[0]} is winning." if len(tops) == 1 else f"{listing(tops)} are level at the top."
        return f"{listing(parts)}. {lead}"

    def reset(self) -> str:
        had = bool(self.scores)
        self.scores.clear()
        self.names.clear()
        self.changed_at = self.now()
        self.record("scores_reset")
        return "Okay, the scores are back to zero." if had else "Okay. There weren't any scores yet."

    def timer_set(self) -> bool:
        if self.turn_s is not None and self.turn_ends is None and self.now() - self.turn_at > TIMER_KEEP_S:
            self.turn_s = None
        return self.turn_s is not None

    def timer_running(self) -> bool:
        return self.turn_ends is not None

    def set_turns(self, seconds: float) -> str:
        self.turn_s = max(5.0, min(3600.0, float(seconds)))
        self.start_turn()
        return f"Okay, {how_long(self.turn_s)} a turn. Go! Say next turn when the next person starts."

    def start_turn(self) -> str:
        if self.turn_s is None:
            return "There's no turn timer. Tell me how long each turn should be."
        self.turn_ends = self.now() + self.turn_s
        self.turn_at = self.now()
        self.warned = False
        return "Go!"

    def stop_turns(self) -> str:
        had = self.turn_s is not None
        self.turn_s = None
        self.turn_ends = None
        return "Okay, no more turn timer." if had else "There's no turn timer going."

    def left(self) -> str:
        if self.turn_ends is None:
            return "The timer isn't running. Say next turn to start it."
        return f"{how_long(max(1.0, self.turn_ends - self.now()))} left."

    def tick(self) -> str | None:
        if self.turn_ends is None:
            return None
        left = self.turn_ends - self.now()
        if left <= 0:
            self.turn_ends = None
            self.turn_at = self.now()
            return "Time's up!"
        if not self.warned and self.turn_s is not None and self.turn_s >= 3 * WARN_S and left <= WARN_S:
            self.warned = True
            return "Ten seconds left!"
        return None


def _shape(person, pitch: float, camera_z: float, span: float):
    points = {p.name: (_across(p), _rise(p, pitch)) for p in person.points if p.score >= MIN_SCORE}
    torso = _torso(person, pitch, camera_z)
    scale = 2.0 * torso.half if torso is not None else None
    box = (math.tan(math.radians(person.bearing_deg)), max(1e-3, person.width_frac * span), max(1e-3, person.height_frac))
    return points, scale, box


def _moved(old, new) -> bool:
    points, scale, box = old
    now_points, _, now_box = new
    if scale:
        common = points.keys() & now_points.keys()
        if len(common) >= 3:
            shifts = [math.hypot(now_points[n][0] - points[n][0], now_points[n][1] - points[n][1]) / scale for n in common]
            return sum(1 for s in shifts if s > MOVE_FRAC) >= POINTS_MOVED or max(shifts) > JUMP_FRAC
    across, width, tall = box
    return abs(now_box[0] - across) > BOX_FRAC * width or abs(now_box[2] - tall) > TALL_FRAC * tall


class Stillness:
    def __init__(self):
        self.base: dict[int, tuple] = {}
        self.hits: dict[int, int] = {}
        self.caught: list[int] = []
        self.at: float | None = None

    def reset(self) -> None:
        self.base.clear()
        self.hits.clear()
        self.caught = []
        self.at = None

    def watch(self, sight, tilt_deg: float = 0.0, skip=()) -> list[int]:
        if sight is None or sight.at == self.at:
            return []
        self.at = sight.at
        camera = getattr(sight, "camera", "front")
        pitch = tilt_deg if camera == "front" else -tilt_deg
        camera_z = CAMERA_HEIGHT_M.get(camera, 0.14)
        span = 2.0 * math.tan(math.radians(max(1.0, sight.fov_h_deg)) / 2.0)
        fresh = []
        for person in sight.people:
            track = person.track
            if track is None or person.score < PERSON_SCORE or track in skip or track in self.caught:
                continue
            shape = _shape(person, pitch, camera_z, span)
            old = self.base.get(track)
            if old is None:
                self.base[track] = shape
                continue
            self.hits[track] = self.hits.get(track, 0) + 1 if _moved(old, shape) else 0
            if self.hits[track] >= FRAMES_MOVED:
                self.caught.append(track)
                fresh.append(track)
        return fresh


def side_of(person) -> str:
    if person.bearing_deg < -SIDE_DEG:
        return "the one on my left"
    if person.bearing_deg > SIDE_DEG:
        return "the one on my right"
    return "the one in the middle"


class TurnGame(Activity):
    moving = False
    sight = True
    game = True

    def __init__(self, request, asker, target=None, battery: bool = False):
        super().__init__(request, asker, target, battery)
        self.stage: SceneStage | None = None
        self.seen: dict[int, float] = {}
        self.judge = Stillness()
        self.won: str | None = None

    def heard(self, text: str, person_id: str | None, label: str) -> bool:
        return False

    def _sight(self, kit: Kit):
        return kit.eyes.latest(0.6)

    def _people(self, sight) -> list:
        if sight is None:
            return []
        return [p for p in sight.people if p.track is not None and p.score >= PERSON_SCORE]

    def _players(self, kit: Kit, sight) -> list[int]:
        now = kit.pace.now()
        for person in self._people(sight):
            self.seen[person.track] = now
        return [track for track, at in self.seen.items() if now - at <= NOBODY_S]

    def _who(self, kit: Kit, tracks: list[int], sight) -> list[str]:
        people = {p.track: p for p in self._people(sight)}
        names = []
        for track in tracks:
            name = kit.name_of(track)
            if name:
                names.append(name)
            elif len(people) <= 1:
                names.append("")
            elif track in people:
                names.append(side_of(people[track]))
            else:
                names.append("someone")
        return names

    def _caught_line(self, names: list[str], tail: str) -> str:
        named = [n for n in names if n]
        if not named:
            return f"I saw you move! {tail}"
        head = listing(named)
        return f"{head[:1].upper()}{head[1:]}, I saw you move! {tail}"

    def _show(self, kit: Kit, lines: tuple, hold_s: float, title: str) -> None:
        if self.stage is None:
            self.stage = SceneStage(kit.face, prefix=f"game{next(_scenes)}-")
        try:
            parsed = [parse_line(line) for line in lines]
        except SceneError:
            log.exception("a game scene did not parse")
            return
        scene = self.stage.begin("full", hold_s, title)
        for line in parsed:
            self.stage.line(scene, line)
        self.stage.end(scene)

    def _clear(self, kit: Kit, face: str = "curious") -> None:
        if self.stage is not None:
            self.stage.clear()
        kit.face.show(face)

    async def _watch(self, kit: Kit, seconds: float, skip=()) -> list[int]:
        self.judge.reset()
        caught: list[int] = []
        until = kit.pace.now() + seconds
        while kit.pace.now() < until:
            sight = self._sight(kit)
            self._players(kit, sight)
            caught.extend(self.judge.watch(sight, kit.body.telemetry.tilt or 0.0, skip))
            await kit.pace.sleep(LOOK_S)
        return caught

    async def _wait_for_players(self, kit: Kit, seconds: float) -> list[int]:
        until = kit.pace.now() + seconds
        while kit.pace.now() < until:
            self._players(kit, self._sight(kit))
            await kit.pace.sleep(LOOK_S * 2)
        return self._players(kit, self._sight(kit))


class RedLight(TurnGame):
    kind = "red_light"

    def describe(self) -> str:
        return "playing red light, green light"

    def heard(self, text: str, person_id: str | None, label: str) -> bool:
        if WIN_WORDS.search(text.lower()):
            self.won = label if person_id else ""
            return True
        return False

    def _close(self, sight) -> int | None:
        people = self._people(sight)
        if not people:
            return None
        gap, track = min((person_gap_m(person, sight, None), person.track) for person in people)
        return track if gap <= WIN_M else None

    async def _green(self, kit: Kit, seconds: float) -> str | None:
        self._show(kit, CLOSED_EYES + ('text 6 26 "GREEN" green',), seconds + 2.0, "green light")
        kit.say("Green light!")
        start = kit.pace.now()
        said = 0
        while kit.pace.now() - start < seconds:
            if self.won is not None:
                return self.won
            sight = self._sight(kit)
            self._players(kit, sight)
            near = self._close(sight)
            if near is not None:
                return kit.name_of(near) or ""
            count = int(kit.pace.now() - start)
            if count > said and count <= len(SECONDS):
                kit.say(SECONDS[count - 1])
                said = count
            await kit.pace.sleep(LOOK_S)
        return None

    def _winner(self, name: str) -> Ending:
        say = f"You made it, {name}! You win!" if name else "You made it! You win!"
        return Ending("done", f"{name or 'someone'} reached you and won red light, green light", say)

    async def run(self, kit: Kit) -> Ending:
        if not getattr(kit.eyes, "available", False):
            return Ending("no_sight", "you could not see, so you could not play red light, green light", "I can't see yet, so I can't play that.")
        start = kit.pace.now()
        try:
            await kit.pace.sleep(2.0)
            kit.say("Everyone line up a few big steps away from me. Here we go!")
            if not await self._wait_for_players(kit, LINE_UP_S):
                return Ending("done", "nobody came to play red light, green light", "I can't see anyone to play with. Let's play another time.")
            while True:
                if kit.pace.now() - start > GAME_MAX_S:
                    return Ending("done", "red light, green light ran out of time with no winner", "That's time! Nobody reached me, so it's a draw. That was fun!")
                if not self._players(kit, self._sight(kit)):
                    return Ending("done", "everyone left the game of red light, green light", "Where did everyone go? Let's play another time.")
                winner = await self._green(kit, draw_between(kit, *GREEN_S))
                if winner is not None:
                    self._clear(kit, "happy")
                    return self._winner(winner)
                self._clear(kit)
                kit.say("Red light!")
                await kit.pace.sleep(GRACE_S)
                caught = await self._watch(kit, WATCH_S)
                if self.won is not None:
                    return self._winner(self.won)
                if caught:
                    sight = self._sight(kit)
                    kit.face.show("mischief")
                    kit.say(self._caught_line(self._who(kit, caught, sight), "Back to the start."))
                    await kit.pace.sleep(BACK_S)
        finally:
            self._clear(kit, "happy")


class Statues(TurnGame):
    kind = "statues"

    def describe(self) -> str:
        return "playing musical statues"

    async def _music(self, kit: Kit, seconds: float) -> None:
        self._show(kit, OPEN_MUSIC, seconds + 2.0, "music")
        start = kit.pace.now()
        sung = -math.inf
        while kit.pace.now() - start < seconds:
            if kit.pace.now() - sung >= SING_EVERY_S:
                sung = kit.pace.now()
                kit.say(SONG[int(draw_between(kit, 0, len(SONG) - 0.001))])
            self._players(kit, self._sight(kit))
            await kit.pace.sleep(LOOK_S)

    async def run(self, kit: Kit) -> Ending:
        if not getattr(kit.eyes, "available", False):
            return Ending("no_sight", "you could not see, so you could not play musical statues", "I can't see yet, so I can't play that.")
        start = kit.pace.now()
        out: set[int] = set()
        try:
            await kit.pace.sleep(2.0)
            kit.say("When the music stops, freeze like a statue. Ready? Here's the music!")
            first = await self._wait_for_players(kit, 3.0)
            if not first:
                return Ending("done", "nobody came to play musical statues", "I can't see anyone to play with. Let's play another time.")
            players = len(first)
            for _ in range(STATUE_ROUNDS):
                if kit.pace.now() - start > GAME_MAX_S:
                    break
                await self._music(kit, draw_between(kit, *MUSIC_S))
                self._clear(kit, "surprised")
                kit.say("Freeze!")
                await kit.pace.sleep(GRACE_S)
                caught = [track for track in await self._watch(kit, WATCH_S, skip=out) if track not in out]
                still = [track for track in self._players(kit, self._sight(kit)) if track not in out and track not in caught]
                sight = self._sight(kit)
                if not still and not caught:
                    return Ending("done", "everyone left the game of musical statues", "Where did everyone go? Let's play another time.")
                if caught:
                    names = self._who(kit, caught, sight)
                    out.update(caught)
                    if players == 1:
                        return Ending("done", "the only player moved in musical statues", "You moved! That was fun. Let's play again some time.")
                    if not still:
                        return Ending("done", "everyone moved at once in musical statues", "Everyone moved! Nobody wins this time. That was fun!")
                    named = [n for n in names if n]
                    kit.say(f"{listing(named)[:1].upper()}{listing(named)[1:]}, you moved! You're out." if named else "You moved! You're out.")
                    if len(still) == 1 and players > 1:
                        winner = (self._who(kit, still, sight) or [""])[0]
                        say = f"{winner[:1].upper()}{winner[1:]} wins! Well done, statue!" if winner else "You win! Well done, statue!"
                        return Ending("done", f"{winner or 'someone'} won musical statues", say)
                else:
                    kit.say("Lovely statues!")
                await kit.pace.sleep(2.0)
            return Ending("done", "musical statues ended after the last round", "That's the end of the music. You were brilliant statues!")
        finally:
            self._clear(kit, "happy")


def screened(kit: Kit, sight):
    privacy = getattr(kit, "privacy", None)
    return privacy.screen(sight) if privacy is not None else sight


class HideSeek(Activity):
    kind = "hide_seek"
    sight = True

    def __init__(self, request, asker, target=None, battery: bool = False):
        super().__init__(request, asker, target, battery)
        self.stage: SceneStage | None = None
        self.found: list[str] = []
        self.tracks: set[int] = set()
        self.found_at = -math.inf

    def describe(self) -> str:
        return "playing hide and seek"

    def _new(self, kit: Kit) -> tuple[int, str] | None:
        sight = screened(kit, kit.eyes.latest(0.6))
        if sight is None:
            return None
        for person in sight.people:
            if person.score < PERSON_SCORE or person.track is None or person.track in self.tracks:
                continue
            name = kit.name_of(person.track) or ""
            if name and name in self.found:
                self.tracks.add(person.track)
                continue
            if not name and kit.pace.now() - self.found_at < FOUND_GAP_S:
                self.tracks.add(person.track)
                continue
            return person.track, name
        return None

    def _found(self, kit: Kit, track: int, name: str) -> None:
        self.tracks.add(track)
        self.found.append(name or "someone")
        self.found_at = kit.pace.now()
        kit.face.show("happy")
        kit.say(f"Found you, {name}!" if name else "Found you!")

    def _anyone(self, kit: Kit) -> bool:
        sight = screened(kit, kit.eyes.latest(0.6))
        return sight is not None and any(p.score >= PERSON_SCORE for p in sight.people)

    async def _trip(self, kit: Kit, x: float, y: float, radius: float, deadline: float):
        for _ in range(TRIES):
            top = NEAR_TOP if self._anyone(kit) else SEEK_TOP
            task = asyncio.ensure_future(go(kit, x, y, radius, top=top, max_s=max(5.0, min(budget(kit, x, y, top), deadline - kit.pace.now()))))
            spotted = None
            try:
                while not task.done():
                    spotted = self._new(kit)
                    if spotted is not None:
                        break
                    await kit.pace.sleep(SEEK_LOOK_S)
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
            if spotted is None:
                return task.result() if not task.cancelled() and task.exception() is None else None
            self._found(kit, *spotted)
            if kit.pace.now() >= deadline:
                return None
        return None

    async def _look_round(self, kit: Kit, wheels: Wheels, deadline: float) -> None:
        for _ in range(int(360.0 / LOOK_ROUND_DEG)):
            spotted = self._new(kit)
            if spotted is not None:
                self._found(kit, *spotted)
            if kit.pace.now() >= deadline or wheels.why_not() is not None:
                return
            await turn_by(kit, wheels, LOOK_ROUND_DEG)
            await kit.pace.sleep(0.4)
        spotted = self._new(kit)
        if spotted is not None:
            self._found(kit, *spotted)

    async def run(self, kit: Kit) -> Ending:
        if kit.dark():
            return Ending("no_sight", "it was too dark to play hide and seek", "It's too dark for me to play hide and seek. Maybe with the lights on?")
        if not getattr(kit.eyes, "available", False):
            return Ending("no_sight", "you could not see, so you could not play hide and seek", "I can't see yet, so I can't play that.")
        places = [place for place in known_places(kit) if private_room(kit, place[1], place[2]) is None]
        if not can_drive(kit) or not places or where(kit) is None:
            return Ending("failed", "you do not know your way round well enough for hide and seek", "I don't know my way round the house well enough to play hide and seek yet.")
        sight = kit.eyes.latest(1.0)
        seen = len([p for p in (sight.people if sight is not None else ()) if p.score >= PERSON_SCORE])
        players = max(1, seen, len(kit.here(120.0)))
        self.stage = SceneStage(kit.face, prefix=f"game{next(_scenes)}-")
        wheels = Wheels(kit).open()
        try:
            await kit.pace.sleep(2.0)
            try:
                scene = self.stage.begin("full", COUNT_GROUP_S * len(COUNTING) + 2.0, "counting")
                for line in CLOSED_EYES:
                    self.stage.line(scene, parse_line(line))
                self.stage.end(scene)
            except SceneError:
                log.exception("the counting scene did not parse")
            for words in COUNTING:
                kit.say(words)
                await kit.pace.sleep(COUNT_GROUP_S)
            self.stage.clear()
            kit.face.show("mischief")
            kit.say("Ready or not, here I come!")
            await kit.pace.sleep(1.5)
            deadline = kit.pace.now() + SEEK_MAX_S
            if kit.body.telemetry.docked and wheels.why_not() is None:
                await leave_dock(kit, wheels)
            await self._look_round(kit, wheels, deadline)
            for name, x, y, radius in tour(places, where(kit)):
                if len(self.found) >= players or kit.pace.now() >= deadline:
                    break
                if kit.dark():
                    return Ending("no_sight", "it got too dark to keep playing hide and seek", "It's got too dark to play. Come out, everyone!")
                reason = wheels.why_not()
                if reason:
                    return Ending("stopped", f"you stopped playing hide and seek ({reason})")
                trip = await self._trip(kit, x, y, radius, deadline)
                if trip is not None and not trip.ok and trip.how in ("stopped", "battery"):
                    return Ending(trip.how, f"hide and seek stopped on the way to the {name} ({trip.text})")
                if len(self.found) >= players:
                    break
                if trip is not None and trip.ok:
                    await wheels.halt()
                    await self._look_round(kit, wheels, deadline)
        finally:
            await wheels.halt()
            wheels.close()
            if self.stage is not None:
                self.stage.clear()
        if len(self.found) >= players:
            return Ending("done", f"you found {listing(self.found)}", "I found everyone! That was fun.")
        return Ending("done", f"you found {listing(self.found)} before you gave up" if self.found else "you found nobody before you gave up", "I give up! Come out, come out, wherever you are!")
