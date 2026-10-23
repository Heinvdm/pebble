import asyncio
import logging
import math
import re
from datetime import timedelta

from ..activities.gate import PEBBLE, Asker, guarded_refusal
from ..activities.kit import Pointed
from ..activities.places import FaceTo, Wiggle
from ..activities.seeing import THING_SCORE, body_bearing, person_gap_m, thing_gap_m
from ..people.trust import INNER, STRANGER
from ..respect import is_alive
from ..things.guarded import STRANGER_NO, kept_from_strangers
from ..things.words import LANDMARKS, canonical, is_animal, matches, spoken, with_article
from ..understand.request import Request
from ..understand.resolve import Reading
from ..activities.gate import FEARED
from .attention import Attention, find_target, gaze_for, glance_seconds
from .book import ALIVE, AliveBook, Known, toy, unit
from .caring import Caring
from .doings import HUSHED, DoingReader
from .dream import ThingDreamer, Today
from .gestures import GestureReader, body_point, pointed_target
from .reactions import Reactions
from .rooms import RoomMap
from .showtell import ShowAndTell, best_known, first_look, key_for, thanks
from .surprise import Expectations, usual_spot

log = logging.getLogger(__name__)

WATCH_S = 0.25
TICK_EVERY = 4
SLOW_TICK_S = 60.0
POINT_KEEP_S = 10.0
TILT_EVERY_S = 2.0
TILT_GAIN = 0.5
TILT_RANGE = (-20.0, 30.0)
TILT_SETTLE_S = 5.0
LOOKED_GAP_S = 20.0
ANCHOR_WEIGHT = 0.3
ANCHOR_MAX_M = 1.2
ANCHOR_SCORE = 0.6
ANCHOR_ERR_M = 0.1
ANCHOR_ERR_PER_M = 0.3
ANCHOR_AGAIN_M = 1.0
ANTICIPATE_AHEAD_MIN = 15
ANTICIPATE_COUNT = 2.5
ANTICIPATE_GAP_S = 3 * 3600.0
DOCK_PRINT_CAP = 8
DOCK_REFRESH_S = 7 * 86400.0
LEARN_IDLE_S = 600.0
SPEAKER_TURN_DEG = 15.0
NOD_DEG = 4.0
NOD_GAP_S = 1.5
PEEK_STILL_S = 5.0
LEAN_S = 6.0
ROUTINE_ROOMS = {"cooking": "kitchen", "eating": "kitchen", "watching tv": "lounge", "working": "office"}
SAY = {
    "leaving": "Bye! See you later.",
    "going to bed": "Night night.",
    "peekaboo": "Peekaboo!",
    "calm": "Phew. That was scary.",
}


class Alive:
    def __init__(self, life):
        self.life = life
        p = life.p
        self.p = p
        now = p.clock.now()
        self.book = AliveBook(p.store.read(ALIVE, {}) or {})
        self.book.seed(p.store.read("personality.json", {}) or {}, now)
        self.attention = Attention(novelty=lambda kind: self.book.novelty(kind, p.clock.now()), taste=self.taste, weights=self.attention_weights)
        self.gestures = GestureReader()
        self.rooms = RoomMap(p.books.things, life.odometer, p.store)
        self.expect = Expectations(p.books.things)
        self.doings = DoingReader()
        self.show = ShowAndTell()
        self.reactions = Reactions()
        self.today = Today(p.clock.local)
        self.dreamer = ThingDreamer(self.today, p.clock.now, None, p.rng)
        self.pointed: Pointed | None = None
        self.focus = None
        self.rng = p.rng
        self._tilted_at = -math.inf
        self._tilt_lost_at = -math.inf
        self._tilted = False
        self._attend = False
        self._watching_moved: dict[str, float] = {}
        self._inspecting = False
        self._anticipated: dict[str, float] = {}
        self._looked_at = -math.inf
        self._slow_at = -math.inf
        self._anchored_at = None
        self._registered = False
        self._drawn_dream = False
        self._ticks = 0
        self._docked_idle = None
        self._head: float | None = None
        self._nodded = -math.inf
        self._view_moved = -math.inf
        self.log: list[str] = []
        self.caring = Caring(self)
        kit = life.commands.runner.kit
        kit.place_at = self.place_at
        kit.pointed = lambda: self.pointed
        kit.toy = self.toy
        kit.dock_print = self.learn_dock_print
        kit.thing_at = self.thing_at
        life.commands.alive = self

    @property
    def mono(self) -> float:
        return self.life.commands.runner.kit.pace.now()

    def taste(self, kind: str) -> tuple[float, float]:
        now = self.p.clock.now()
        return self.book.liking(kind, now), self.book.fear(kind, now)

    def attention_weights(self) -> dict:
        dials = getattr(self.life, "dials", None)
        return dials.attention() if dials is not None else {}

    def toy(self, label: str) -> bool:
        kind = canonical(label)
        if is_alive(label) or is_alive(kind):
            return False
        if toy(kind) or toy(label):
            return True
        return any(k.owner == "pebble" and (k.key == label or k.label == kind) for k in self.book.known.values())

    def thing_at(self, label: str) -> tuple[float, float] | None:
        best = None
        for thing in self.p.books.things.find(label):
            if thing.animal:
                continue
            for spot in thing.spots:
                if spot.placed and (best is None or (spot.count, spot.at) > (best.count, best.at)):
                    best = spot
        return None if best is None else (best.x, best.y)

    def usual_room(self, person_id: str) -> str | None:
        room = self.book.usual_room(person_id, self.p.clock.now())
        return room if room is not None and self.rooms.place(room) is not None else None

    def place_at(self, name: str) -> tuple[float, float, float] | None:
        room = self.rooms.place(name)
        return None if room is None else (room.x, room.y, room.radius)

    def places(self) -> frozenset:
        return frozenset(self.rooms.rooms)

    def pointing(self) -> bool:
        return self.pointed is not None and self.mono - self.pointed.at <= POINT_KEEP_S

    def hushed(self) -> bool:
        privacy = getattr(self.life, "privacy", None)
        return self.doings.hushed() or (privacy is not None and privacy.hushed())

    def note(self, text: str, major: bool = False, kind: str = "") -> None:
        self.log.append(text)
        del self.log[:-50]
        self.life.events.add(self.p.clock.now(), text, major, kind=kind)
        if major:
            self.life.trigger.set()

    def quiet(self) -> bool:
        rule = getattr(self.life, "rule_quiet", None)
        return bool(self.p.permissions.quiet) or self.life.state.value in ("asleep", "resting") or bool(rule is not None and rule())

    def say(self, text: str, chance: float = 1.0) -> bool:
        said = self.reactions.speak(text, self.mono, self.quiet(), self.hushed(), chance, self.rng.random())
        if said:
            self.life.commands._spawn(self.life.commands.speak(said, False))
            self.p.blackbox.record("reaction", said=said)
        return bool(said)

    def sight(self):
        eyes = self.p.eyes
        if not getattr(eyes, "available", False):
            return None
        return eyes.latest(1.0)

    def who_is_here(self) -> tuple[str | None, str, str]:
        here = self.life.company.here(self.p.clock.now())
        if len(here) == 1:
            person = here[0]
            return person.id, person.label, self.life.company.tier(person)
        return None, "someone", STRANGER

    def asker(self) -> Asker:
        person_id, _, _ = self.who_is_here()
        return self.life.commands.asker_for(person_id)

    async def start(self) -> None:
        if self._registered:
            return
        self._registered = True
        remember = getattr(self.p.eyes, "remember_print", None)
        if remember is None:
            return
        for known in self.book.known.values():
            for index, view in enumerate(known.prints):
                try:
                    remember(known.key, tuple(view), replace=index == 0)
                except Exception:
                    log.exception("could not hand back the print for %s", known.key)
        for index, view in enumerate(self.book.dock.get("prints") or []):
            try:
                remember("charger", tuple(view), replace=index == 0)
            except Exception:
                log.exception("could not hand back the charger print")

    async def run(self) -> None:
        await self.start()
        pace = self.life.commands.runner.kit.pace
        while True:
            await pace.sleep(WATCH_S)
            try:
                self.watch()
            except Exception:
                log.exception("watching failed")
            self._ticks += 1
            if self._ticks % TICK_EVERY == 0:
                try:
                    await self.tick()
                except Exception:
                    log.exception("the alive tick failed")

    def calm_down(self) -> None:
        self.p.face.show("love")
        self.say(SAY["calm"], 0.6)

    def speaking(self, track: int | None = None, bearing_deg: float | None = None) -> None:
        self.attention.hear_speaker(self.mono, track, bearing_deg)

    def face_speaker(self, track: int | None = None, bearing_deg: float | None = None) -> bool:
        self.speaking(track, bearing_deg)
        sight = self.sight()
        if sight is None or not sight.people:
            return False
        if track is not None:
            chosen = next((p for p in sight.people if p.track == track), None)
        elif bearing_deg is not None:
            chosen = min(sight.people, key=lambda p: abs(p.bearing_deg - bearing_deg))
        else:
            chosen = sight.people[0] if len(sight.people) == 1 else None
        if chosen is None:
            return False
        if not self.life._gaze_held:
            self.p.face.gaze(*gaze_for(chosen.bearing_deg, chosen.elevation_deg))
        angle = body_bearing(chosen.bearing_deg, sight.camera)
        commands = self.life.commands
        sit = self.life.situation()
        if abs(angle) > SPEAKER_TURN_DEG and commands.runner.current is None and sit.can_move and not sit.quiet and not sit.blocked and not sit.alarm and not sit.docked:
            commands.runner.start(FaceTo(Request("turn"), PEBBLE, None, angle_deg=angle))
        return True

    def nod(self) -> bool:
        tilt = self.p.body.telemetry.tilt
        if tilt is None or self.mono - self._nodded < NOD_GAP_S or not self._may_tilt():
            return False
        self._nodded = self.mono
        self.life.commands._spawn(self._nod(tilt))
        return True

    async def _nod(self, tilt: float) -> None:
        await self.p.body.tilt(tilt - NOD_DEG)
        await self.life.commands.runner.kit.pace.sleep(0.25)
        await self.p.body.tilt(tilt)

    def forget(self, person_id: str, names: list[str]) -> None:
        patterns = [re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE) for name in names if name.strip()]

        def mentions(text: str) -> bool:
            return any(pattern.search(str(text or "")) for pattern in patterns)

        for known in self.book.known.values():
            if known.owner == person_id or (known.owner_label and mentions(known.owner_label)):
                known.owner, known.owner_label = None, ""
            if known.taught_by == person_id:
                known.taught_by = None
        self.book.routine.pop(f"person:{person_id}", None)
        self.book.met_in.pop(person_id, None)
        for entries in self.book.taste.values():
            for entry in entries:
                if mentions(entry[3]):
                    entry[3] = "about someone forgotten"
        self.today.taught = [title for title in self.today.taught if not mentions(title)]
        self.today.doings = [text for text in self.today.doings if not mentions(text)]
        self.log = [text for text in self.log if not mentions(text)]
        self.p.store.write(ALIVE, self.book.to_dict(), keep_backup=False)
        self.book.dirty = False

    def asked(self) -> None:
        self.attention.asked(self.mono)

    def heard(self, text: str) -> None:
        words = [w.strip(".,!?").lower() for w in text.split()]
        pairs = [" ".join(words[i : i + 2]) for i in range(len(words) - 1)]
        self.attention.hear_named(words + pairs, self.mono)
        sight = self.sight()
        if sight is not None and len(sight.people) == 1:
            self.attention.hear_speaker(self.mono, sight.people[0].track)

    def watch(self) -> None:
        if self.life.state.value == "asleep":
            self._release_gaze()
            return
        now = self.mono
        self._tell_head()
        current = self.life.commands.runner.current
        if current is not None and current.moving:
            self._view_moved = now
        sight = self.sight()
        privacy = getattr(self.life, "privacy", None)
        if privacy is not None:
            try:
                if privacy.watch(sight):
                    return
            except Exception:
                log.exception("the privacy watch failed")
            sight = privacy.screen(sight)
        focus = self.attention.update(sight, now)
        self.focus = focus
        self._gaze(focus, sight, now)
        if sight is None:
            return
        for person in sight.people:
            for gesture in self.gestures.read(person, sight.at):
                self._gesture(gesture, person, sight)
        self.gestures.forget({p.track for p in sight.people if p.track is not None})
        self._follow_look(sight, now)
        self.caring.watch(sight)
        shown = self.show.watch(sight, now)
        if shown is not None and not self._inspecting:
            self.life.commands._spawn(self.inspect(shown))

    def _tell_head(self) -> None:
        tilt = self.p.body.telemetry.tilt
        told = getattr(self.p.eyes, "set_head", None)
        if tilt is None or told is None or (self._head is not None and abs(tilt - self._head) < 0.5):
            return
        self._head = tilt
        self._view_moved = self.mono
        try:
            told(tilt_deg=tilt)
        except Exception:
            log.exception("could not tell the eyes where the head is")

    def _release_gaze(self) -> None:
        if self._attend:
            self._attend = False
            attend = getattr(self.p.face, "attend", None)
            if attend is not None:
                attend(False)

    def _gaze(self, focus, sight, now: float) -> None:
        if self.life._gaze_held:
            return
        if focus is None or focus.camera != "front":
            self._release_gaze()
            self._settle_tilt(now)
            return
        if not self._attend:
            self._attend = True
            attend = getattr(self.p.face, "attend", None)
            if attend is not None:
                attend(True)
        self.p.face.gaze(*gaze_for(focus.bearing_deg, focus.elevation_deg))
        self._tilt_lost_at = now
        self._tilt_towards(focus, now)

    def _may_tilt(self) -> bool:
        return self.life.commands.runner.current is None and not self.p.permissions.quiet and self.life.blocked() is None and self.p.body.connected

    def _tilt_towards(self, focus, now: float) -> None:
        if abs(focus.elevation_deg) < 10.0 or now - self._tilted_at < TILT_EVERY_S or not self._may_tilt():
            return
        body = self.p.body
        tilt = body.telemetry.tilt
        if tilt is None:
            return
        target = max(body.profile.tilt_rest + TILT_RANGE[0], min(body.profile.tilt_rest + TILT_RANGE[1], tilt + focus.elevation_deg * TILT_GAIN))
        if abs(target - tilt) < 3.0:
            return
        self._tilted_at = now
        self._tilted = True
        self.life.commands._spawn(self._tilt(target))

    async def _tilt(self, target: float) -> None:
        await self.p.body.tilt(target)
        moved = getattr(self.p.eyes, "moved", None)
        if moved is not None:
            moved()

    def _settle_tilt(self, now: float) -> None:
        if self._tilted and now - self._tilt_lost_at > TILT_SETTLE_S and self._may_tilt():
            self._tilted = False
            self.life.commands._spawn(self._tilt(self.p.body.profile.tilt_rest))

    def _follow_look(self, sight, now: float) -> None:
        if now - self._looked_at < LOOKED_GAP_S or self.focus is None or self.focus.kind != "person":
            return
        person = next((p for p in sight.people if p.track == self.focus.track), None)
        if person is None or person.facing_deg is None or not 30.0 <= abs(person.facing_deg) <= 100.0:
            return
        if self.rng.random() > 0.08:
            return
        self._looked_at = now
        self.attention.glance_at(person.bearing_deg + person.facing_deg * 0.6, person.elevation_deg - 8.0, now, 1.0, "where they were looking")

    def _gesture(self, gesture, person, sight) -> None:
        now = self.mono
        person_id, label, _ = self.who_is_here()
        face = self.p.face
        self.p.blackbox.record("gesture", gesture=gesture.kind, person=person_id, side=gesture.side)
        if gesture.kind == "wave":
            face.show("happy")
            self.note(f"{label} waved at you", kind="stakes")
            self._wiggle("back at a wave")
            return
        if gesture.kind == "peekaboo":
            if self.mono - self._view_moved < PEEK_STILL_S:
                return
            face.show("surprised")
            self.note(f"{label} played peekaboo with you", kind="stakes")
            self.say(SAY["peekaboo"], 0.6)
            face.show("happy")
            return
        if gesture.kind == "beckon":
            self.note(f"{label} beckoned you over", kind="stakes")
            self.life.commands._spawn(self.life.commands.act(Request("come"), self.asker(), "gesture"))
            return
        if gesture.kind == "point":
            self._pointed(person, sight, gesture)

    def _wiggle(self, why: str) -> None:
        commands = self.life.commands
        sit = self.life.situation()
        if commands.runner.current is not None or not sit.can_move or sit.quiet or sit.blocked or sit.alarm or sit.calm:
            return
        wiggle = Wiggle(Request("turn"), PEBBLE, None)
        wiggle.why = why
        commands.runner.start(wiggle)

    def _pointed(self, person, sight, gesture) -> None:
        side = gesture.side
        shoulder, wrist = body_point(person, f"{side}_shoulder"), body_point(person, f"{side}_wrist")
        if shoulder is None or wrist is None:
            return
        status = self.p.body.telemetry.status
        gap = person_gap_m(person, sight, status.front_mm if status else None)
        tilt = self.p.body.telemetry.tilt or 0.0
        tx, ty = pointed_target(gap, shoulder, wrist, sight.camera, tilt)
        target_angle = math.degrees(math.atan2(ty, tx))
        distance = math.hypot(tx, ty)
        world = None
        odometer = self.life.odometer
        if odometer.usable:
            x, y, heading = odometer.pose()
            aim = math.radians(heading + target_angle)
            world = (x + distance * math.cos(aim), y + distance * math.sin(aim))
        self.pointed = Pointed(target_angle, distance, self.mono, world)
        _, label, _ = self.who_is_here()
        bearing = -target_angle if sight.camera == "front" else 180.0 - target_angle
        self.attention.glance_at(bearing, -10.0, self.mono, 1.2, "where they pointed")
        self.p.face.show("curious")
        side_words = "to your left" if target_angle > 20 else ("to your right" if target_angle < -20 else "ahead of you")
        self.note(f"{label} pointed at a spot about {distance:.1f} m away, {side_words}")

    def before(self, request: Request) -> float:
        if not request.starts or request.kind in ("wait", "back_off"):
            return 0.0
        sight = self.sight()
        target = None
        if request.kind in ("look", "go_to_place") and request.place == "there" and self.pointed is not None:
            bearing = -self.pointed.angle_deg
            elevation = -10.0
        else:
            target = find_target(sight, request.thing, person=request.kind in ("come", "follow", "look"))
            if target is None:
                return 0.0
            bearing, elevation = target.bearing_deg, target.elevation_deg
        seconds = glance_seconds(self.rng)
        self.attention.glance_at(bearing, elevation, self.mono, seconds, "about to act")
        self.p.face.gaze(*gaze_for(bearing, elevation))
        return seconds

    async def inspect(self, thing) -> None:
        self._inspecting = True
        eyes = self.p.eyes
        face = self.p.face
        body = self.p.body
        rest = body.profile.tilt_rest
        leaned = False
        try:
            now = self.mono
            face.show("curious")
            person_id, label, _ = self.who_is_here()
            if self._may_tilt() and body.telemetry.tilt is not None and abs(thing.elevation_deg) > 5.0:
                await body.tilt(max(rest + TILT_RANGE[0], min(rest + TILT_RANGE[1], body.telemetry.tilt + thing.elevation_deg * 0.7)))
                leaned = True
            closely = getattr(eyes, "look_closely", None)
            if closely is not None:
                try:
                    await asyncio.wait_for(closely(), LEAN_S)
                except Exception:
                    pass
            vec = None
            printer = getattr(eyes, "fingerprint", None)
            if printer is not None and thing.track is not None:
                try:
                    vec = await printer(thing.track)
                except Exception:
                    log.exception("could not print the shown thing")
            known = self.book.known.get(thing.known) if thing.known else None
            if known is None and vec is not None:
                known, _ = best_known(self.book, vec)
            shown = self.show.shown(thing, now, person_id, label)
            shown.vec = list(vec) if vec is not None else None
            shown.known = known.key if known else None
            kind = canonical(thing.label)
            self.book.expose(kind, self.p.clock.now())
            self.today.saw(kind, self.p.clock.now())
            if known is not None:
                if known.owner == "pebble":
                    face.show("love")
                else:
                    face.show("happy")
                self.note(f"{label} showed you {known.title(you=True)}, which you recognised")
                if not self.quiet():
                    await self.life.commands.speak(first_look(shown, known), False)
                return
            question = first_look(shown, None)
            self.note(f"{label} showed you {with_article(spoken(kind))} up close")
            if self.quiet():
                return
            await self.life.commands.ask(Reading(Request("teach", thing=kind), "name", question), self.life.commands.asker_for(person_id), f"you asked {label}: {question}")
        finally:
            if leaned:
                await body.tilt(rest)
            self._inspecting = False

    def _owner(self, who: str, asker: Asker) -> tuple[str | None, str]:
        if who == "pebble":
            return "pebble", "Pebble"
        if who == "me":
            return asker.id, asker.label if asker.id else ""
        if not who:
            return None, ""
        person = self.life.company.book.find(who)
        if person is not None:
            return person.id, person.label
        return who, who.title()

    async def _fresh_print(self, thing: str):
        sight = self.sight()
        if sight is None:
            return None
        held = [t for t in sight.things if t.held and (not thing or matches(thing, t.label))]
        printer = getattr(self.p.eyes, "fingerprint", None)
        if not held or printer is None or held[0].track is None:
            return None
        try:
            return await printer(held[0].track)
        except Exception:
            return None

    async def teach(self, request: Request, asker: Asker) -> str:
        now = self.p.clock.now()
        shown = self.show.current(self.mono)
        if shown is not None and request.thing and not matches(request.thing, shown.label) and not matches(shown.label, request.thing):
            shown = None
        label = canonical(request.thing) if request.thing else (shown.label if shown else "")
        vec = shown.vec if shown is not None else None
        if vec is None:
            vec = await self._fresh_print(label)
            vec = list(vec) if vec is not None else None
        if shown is None and vec is None:
            if not label:
                return "Show me first? Hold it up close so I can see it."
            return f"Hold the {spoken(label)} up close so I can see it properly?"
        old = self.book.known.get(shown.known) if shown is not None and shown.known else None
        owner, owner_label = self._owner(request.who, asker) if request.who else ((old.owner, old.owner_label) if old else (None, ""))
        name = request.name or (old.name if old else "")
        key = old.key if old else key_for(self.book, label, name, owner)
        known = Known(key, label or (old.label if old else "thing"), name, owner, owner_label, asker.id, now, [vec] if vec else [])
        known = self.book.teach(known)
        remember = getattr(self.p.eyes, "remember_print", None)
        if remember is not None and vec:
            try:
                remember(key, tuple(unit(vec)), replace=False)
            except Exception:
                log.exception("could not remember the print for %s", key)
        if owner == "pebble":
            self.book.feel(known.label, "like", 1.0, f"{asker.label} gave you your very own {spoken(known.label)}", now)
            self.book.feel(f"known:{key}", "like", 1.5, "it is yours", now)
        if shown is not None:
            shown.known = key
        self.today.learnt(known.title(), now)
        self.p.diary.write(f"{asker.label} told me about {known.title()}." if not asker.own else f"I learnt about {known.title()}.", "learnt")
        self.note(f"{asker.label} told you about {known.title(you=True)}")
        self.p.blackbox.record("taught", key=key, label=known.label, named=bool(name), owner=owner, by=asker.id, views=len(known.prints))
        self.save()
        return thanks(known, asker.id)

    def where_privacy(self, request: Request, asker: Asker) -> str:
        if asker.own or asker.tier == INNER:
            return ""
        for known in self.book.known.values():
            if not matches(request.thing, known.label) and not (known.name and matches(request.thing, known.name)):
                continue
            if asker.tier == STRANGER and kept_from_strangers(known.label):
                return STRANGER_NO
            guarded = guarded_refusal(known.label, asker)
            if guarded is not None:
                return guarded[1]
            if known.owner in (None, "pebble") or known.owner == asker.id:
                continue
            owner = known.owner_label or "someone else"
            return f"That's {owner}'s, so I'd rather let {owner} say where it is."
        return ""

    async def answer(self, request: Request, asker: Asker) -> str | None:
        if request.kind == "where_am_i":
            return self.rooms.say_where()
        if request.kind == "teach":
            return await self.teach(request, asker)
        if request.kind == "where_is":
            return self.where_privacy(request, asker) or None
        return None

    def situation_extras(self, thing: str) -> dict:
        now = self.p.clock.now()
        return {
            "places_known": self.places(),
            "pointed": self.pointing(),
            "knows_where": bool(self.life.odometer.usable),
            "thing_fear": self.book.fear(canonical(thing), now) if thing else 0.0,
        }

    async def tick(self) -> None:
        sight = self.sight()
        if not self.caring.busy:
            self.life.commands._spawn(self.caring.tick(sight))
        if self.life.state.value == "asleep":
            return
        now = self.p.clock.now()
        mono = self.mono
        self._notice_things(sight, now)
        self._surprises(sight, mono)
        self._read_doings(sight, mono)
        self._anchor(sight)
        if mono - self._slow_at >= SLOW_TICK_S:
            self._slow_at = mono
            self._slow(now)
        await self._morning_drawing()
        if self.book.dirty:
            self.save()

    def _notice_things(self, sight, now: float) -> None:
        if sight is None:
            return
        for thing in sight.things:
            if thing.score < THING_SCORE:
                continue
            kind = canonical(thing.label)
            before = self.book.expose(kind, now, 0.05)
            if thing.known:
                self.book.expose(f"known:{thing.known}", now, 0.05)
            self.today.saw(kind, now, new=before < 0.2)
            if is_animal(kind):
                continue
            liking = self.book.liking(kind, now)
            fear = self.book.fear(kind, now)
            if fear >= FEARED and self.focus is not None and self.focus.kind == "thing" and canonical(self.focus.label) == kind:
                self.p.face.show("scared")
            elif liking >= 0.4 and self.focus is not None and self.focus.kind == "thing" and canonical(self.focus.label) == kind:
                self.p.face.show("happy")

    def _surprises(self, sight, mono: float) -> None:
        odometer = self.life.odometer
        pose = odometer.pose() if odometer.usable else None
        tilt = self.p.body.telemetry.tilt
        off = (tilt - self.p.body.profile.tilt_rest) if tilt is not None else 99.0
        current = self.life.commands.runner.current
        still = current is None or not current.moving
        found = self.expect.check(sight, pose if still else None, off, mono)
        for seen in self.life.watcher_moved():
            self._watching_moved[seen] = mono
        if sight is not None:
            for label, since in list(self._watching_moved.items()):
                if mono - since > 30.0:
                    self._watching_moved.pop(label, None)
                    continue
                here = [t for t in sight.things if canonical(t.label) == canonical(label) or t.label == label]
                if not here:
                    continue
                status = self.p.body.telemetry.status
                gap = thing_gap_m(here[0], sight, tilt, status.front_mm if status else None)
                surprise = self.expect.moved(label, here[0].score, gap, mono, abs(off) <= 6.0 and still)
                if surprise is not None:
                    self._watching_moved.pop(label, None)
                    found.append(surprise)
        for surprise in found:
            self._react_surprise(surprise, sight)

    def _react_surprise(self, surprise, sight) -> None:
        face = self.p.face
        face.show("surprised")
        bearing = -surprise.bearing_deg
        self.attention.glance_at(bearing, -5.0, self.mono, 0.4, "double take")
        self.life.commands._spawn(self._double_take(bearing))
        self.book.unsettle(canonical(surprise.label), self.p.clock.now())
        self.note(surprise.text, kind="surprise")
        self.p.blackbox.record("surprise", surprise=surprise.kind, label=surprise.label)
        self.say(surprise.say, 0.3)

    async def _double_take(self, bearing: float) -> None:
        pace = self.life.commands.runner.kit.pace
        face = self.p.face
        face.gaze(*gaze_for(bearing - 25.0, 0.0))
        await pace.sleep(0.25)
        face.gaze(*gaze_for(bearing, -5.0))
        await pace.sleep(0.35)
        face.gaze(*gaze_for(bearing - 25.0, 0.0))
        await pace.sleep(0.2)
        face.gaze(*gaze_for(bearing, -5.0))

    def _read_doings(self, sight, mono: float) -> None:
        hour = self.p.clock.local().hour
        for change in self.doings.read(sight, mono, hour, self._places_of(sight)):
            _, label, _ = self.who_is_here()
            doing = change.doing
            if change.started:
                text = doing.text(label)
                self.note(text + (", so keep quiet unless spoken to" if doing.what in HUSHED else ""))
                self.today.did(text, self.p.clock.now())
                self.p.blackbox.record("doing", what=doing.what, started=True)
                self.book.saw_at(f"doing:{doing.what}", self.p.clock.local())
                room = self._room_of(doing.track, sight)
                if room:
                    self.book.where[doing.what] = room
                    self.book.dirty = True
                if doing.what in SAY:
                    self.p.face.show("love" if doing.what == "leaving" else "sleepy")
                    self.say(SAY[doing.what])
                    if doing.what == "leaving":
                        self._wiggle("goodbye")
            else:
                self.p.blackbox.record("doing", what=doing.what, started=False)
                if doing.what in HUSHED:
                    self.note(f"{label} seems to have stopped {'working' if doing.what == 'working' else doing.what}")

    def _place_of(self, person, sight) -> tuple[float, float] | None:
        odometer = self.life.odometer
        if not odometer.usable:
            return None
        status = self.p.body.telemetry.status
        gap = person_gap_m(person, sight, status.front_mm if status else None)
        x, y, heading = odometer.pose()
        aim = math.radians(heading + body_bearing(person.bearing_deg, sight.camera))
        return x + gap * math.cos(aim), y + gap * math.sin(aim)

    def _places_of(self, sight) -> dict:
        if sight is None:
            return {}
        out = {}
        for person in sight.people:
            spot = self._place_of(person, sight)
            if spot is not None:
                out[person.track] = spot
        return out

    def _room_of(self, track, sight) -> str | None:
        odometer = self.life.odometer
        if sight is None or not odometer.usable:
            return None
        person = next((p for p in sight.people if p.track == track), None)
        if person is None:
            return self.rooms.where_am_i()
        spot = self._place_of(person, sight)
        return self.rooms.room_at(*spot) if spot is not None else None

    def _anchor(self, sight) -> None:
        odometer = self.life.odometer
        if sight is None or sight.camera != "front" or not odometer.usable or self.life.commands.runner.busy or self.p.body.telemetry.docked:
            return
        x, y, heading = odometer.pose()
        drift = getattr(odometer, "drift_m", None)
        travelled = getattr(odometer, "total_m", None)
        if travelled is not None and self._anchored_at is not None and travelled - self._anchored_at < ANCHOR_AGAIN_M:
            return
        status = self.p.body.telemetry.status
        for thing in sight.things:
            kind = canonical(thing.label)
            if thing.score < ANCHOR_SCORE or kind not in LANDMARKS:
                continue
            spot = usual_spot(self.p.books.things, thing.label)
            if spot is None:
                continue
            gap = thing_gap_m(thing, sight, self.p.body.telemetry.tilt, status.front_mm if status else None) + 0.1
            aim = math.radians(heading + body_bearing(thing.bearing_deg, sight.camera))
            ex, ey = spot.x - gap * math.cos(aim), spot.y - gap * math.sin(aim)
            off = math.hypot(ex - x, ey - y)
            weight = ANCHOR_WEIGHT
            if drift is not None:
                sure, unsure = drift(), ANCHOR_ERR_M + ANCHOR_ERR_PER_M * gap
                weight = min(ANCHOR_WEIGHT, sure * sure / (sure * sure + unsure * unsure))
            if 0.1 < off <= ANCHOR_MAX_M and weight > 0.01:
                odometer.anchor(ex, ey, weight)
                self._anchored_at = travelled
                self.p.blackbox.record("anchored", on=kind, moved_m=round(off * weight, 3))
                return

    def _slow(self, now: float) -> None:
        local = self.p.clock.local(now)
        for person in self.life.company.here(now):
            self.book.saw_at(f"person:{person.id}", local)
        sight = self.sight()
        person_id, _, _ = self.who_is_here()
        if person_id is not None and sight is not None and len(sight.people) == 1:
            room = self._room_of(sight.people[0].track, sight)
            if room:
                self.book.met(person_id, room, now)
        for name, new in self.rooms.update():
            self.note(f"you worked out where the {name} is" if new else f"you have a better idea of where the {name} is", kind="place" if new else "")
            self.p.blackbox.record("room", name=name, new=new)
        self._anticipate(local)
        self._maybe_learn_dock()

    def _anticipate(self, local) -> None:
        commands = self.life.commands
        if commands.runner.current is not None or not self.life.odometer.usable:
            return
        sit = self.life.situation()
        if sit.quiet or not sit.can_move or sit.low_battery or sit.resting or sit.alarm or sit.calm or sit.privacy:
            return
        ahead = local + timedelta(minutes=ANTICIPATE_AHEAD_MIN)
        for what, default in ROUTINE_ROOMS.items():
            room = self.book.where.get(what, default)
            if self.rooms.place(room) is None:
                continue
            privacy = getattr(self.life, "privacy", None)
            if privacy is not None and privacy.rooms.kind(room):
                continue
            if self.book.usual(f"doing:{what}", ahead) < ANTICIPATE_COUNT or self.book.usual(f"doing:{what}", local) >= ANTICIPATE_COUNT:
                continue
            if self.mono - self._anticipated.get(what, -math.inf) < ANTICIPATE_GAP_S:
                continue
            if any(d.what == what for d in self.doings.doing()):
                continue
            self._anticipated[what] = self.mono
            self.note(f"it's nearly the time someone is usually {what}, so you went to wait in the {room}")
            request = Request("go_to_place", place=room, then=(Request("wait", seconds=600.0),))
            commands._spawn(commands.act(request, PEBBLE, "routine"))
            return

    def learn_dock_print(self, vec) -> None:
        if not vec:
            return
        prints = self.book.dock.setdefault("prints", [])
        prints.append([round(float(v), 5) for v in unit(vec)])
        del prints[:-DOCK_PRINT_CAP]
        self.book.dock["at"] = self.p.clock.now()
        self.book.dirty = True
        remember = getattr(self.p.eyes, "remember_print", None)
        if remember is not None:
            try:
                remember("charger", tuple(unit(vec)), replace=False)
            except Exception:
                log.exception("could not remember the charger print")

    def _maybe_learn_dock(self) -> None:
        if getattr(self.p.eyes, "dock_print", None) is None:
            return
        fresh = self.p.clock.now() - float(self.book.dock.get("at", 0.0) or 0.0) < DOCK_REFRESH_S
        if len(self.book.dock.get("prints") or []) >= 3 and fresh:
            return
        commands = self.life.commands
        sit = self.life.situation()
        if commands.runner.current is not None or not sit.docked or sit.quiet or not sit.can_move or sit.low_battery or sit.alarm or sit.calm:
            self._docked_idle = None
            return
        if self._docked_idle is None:
            self._docked_idle = self.mono
        if self.mono - self._docked_idle < LEARN_IDLE_S:
            return
        self._docked_idle = None
        from ..activities.home import LearnDock

        self.note("you went to take a good look at your charger so you can find it again")
        commands.runner.start(LearnDock(Request("go_home"), PEBBLE, None))

    async def _morning_drawing(self) -> None:
        drawing = self.dreamer.drawing
        studio = self.p.studio
        if not drawing or studio is None or self.quiet() or self.life.state.value != "active":
            return
        self.dreamer.drawing = None
        try:
            await studio.draw(f"a dream: {drawing}", name=f"dream-{self.p.clock.local().date().isoformat()}")
            self.note("you drew last night's dream")
        except Exception:
            log.exception("could not draw the dream")

    def cards(self, kind: str):
        return self.today.cards(kind, self.p.clock.now())

    def save(self) -> None:
        self.p.store.write(ALIVE, self.book.to_dict())
        self.book.dirty = False
