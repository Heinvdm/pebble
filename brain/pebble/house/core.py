import logging
import math
from collections import deque

from ..activities.gate import PEBBLE, decide
from ..activities.seeing import body_bearing, person_gap_m
from ..hearing.sounds import HouseSounds
from ..hearing.taught import SOUNDS, Profiler, TaughtSounds, join, logged, thing_of
from ..people.trust import INNER, STRANGER, TRUSTED
from ..people.visitors import Visitors
from ..things.words import canonical, listing
from ..understand.request import Request
from .alarms import AlarmCare, counted
from .asks import Asks, Watchers
from .away import AwayLog
from .book import HouseBook
from .captions import Captions
from .checks import HearingChecks
from .cooking import CookingWatch
from .damp import Damp
from .days import Days
from .high import HighWatch
from .lists import Lists
from .noise import NoiseDiary
from .pets import PetCare
from .screen import text_layer_for
from .settings import Refused, apply, change, drop, tried, waiting
from .tell import Teller

log = logging.getLogger(__name__)

ROWS_KEEP = 64
TEACH_S = 12.0
TEACH_OVER_FLOOR_DB = 10.0
SPEECH_BELOW = 0.3
KITCHEN_THINGS = frozenset({"oven", "stove", "microwave", "fridge", "refrigerator", "kettle", "toaster", "pan", "pot", "frying pan", "sink"})
NEAR_COOKING_DEG = 40.0
SLOW_S = 2.0
PRUNE_S = 3600.0
POWER_MIN_S = 60.0
WALL_SANE_S = 3600.0
LUX_DARK = 5.0
LUX_DIM = 50.0
LUX_BRIGHT = 500.0
SETTINGS_S = 5.0
TURN_WAIT_S = 30.0


class House:
    def __init__(self, life):
        self.life = life
        p = life.p
        self.p = p
        self.clock = p.clock
        self.book = HouseBook(p.store)
        self.lists = Lists(self.book["lists"])
        self.watchers = Watchers(self, self.book["watchers"])
        self.visitors = Visitors(self.book["visitors"])
        life.company.visitors = self.visitors
        self.taught = TaughtSounds(p.store.read(SOUNDS, {}) or {})
        self.layer = text_layer_for(p.face, self.clock.monotonic)
        if self.visitors.on:
            self.layer.badge("Visitors")
        self.teller = Teller(self)
        self.away = AwayLog(self, self.book["away"])
        self.cooking = CookingWatch(self)
        self.alarms = AlarmCare(self)
        self.days = Days(self)
        self.damp = Damp(self)
        self.noise = NoiseDiary(self, self.book["noise"])
        self.pets = PetCare(self)
        self.captions = Captions(self)
        self.asks = Asks(self)
        self.detector: HouseSounds | None = None
        self.hearing = None
        self.inbox: deque = deque()
        self.rows: deque = deque(maxlen=ROWS_KEEP)
        self.profile_seen = -math.inf
        self.slow_at = -math.inf
        self.pruned_at = -math.inf
        self.charging: bool | None = None
        self.power_off_at: float | None = None
        self.ladder_attached = False
        self.tiers_at = -math.inf
        self.tiers: dict = {}
        self.high = HighWatch(self)
        self.checks = HearingChecks(self)
        self.settings_at = -math.inf
        life.overnight.forgetters.append(self.forget)
        self._attach_hearing()
        self._attach_pictures()
        self._take_settings()

    @property
    def safety(self):
        return self.p.safety

    def mono(self) -> float:
        return self.clock.monotonic()

    def _attach_hearing(self) -> None:
        hearing = getattr(self.p.safety, "hearing", None)
        if hearing is None:
            return
        self.hearing = hearing
        labels = list(getattr(getattr(hearing, "model", None), "labels", []) or [])
        if labels:
            self.detector = HouseSounds(labels)
            taps = getattr(hearing, "taps", None)
            if taps is not None:
                taps.append(self.inbox.append)
        if getattr(hearing, "profiler", "missing") is None:
            profiler = Profiler()
            if profiler.available:
                hearing.profiler = profiler
        hearing.want_vectors = len(self.taught) > 0

    def _attach_pictures(self) -> None:
        pictures = getattr(self.life.commands, "pictures", None)
        if pictures is not None and getattr(pictures, "turn", "missing") is None:
            pictures.turn = self.turn_round

    async def turn_round(self, degrees: float) -> bool:
        if bool(getattr(self.p.body.telemetry, "docked", False)):
            return False
        commands = self.life.commands
        if commands.runner.busy:
            return False
        plan = getattr(commands, "plan", None)
        request = Request("turn", way="left" if degrees > 0 else "right", degrees=abs(float(degrees)))
        try:
            verdict = await commands.act(request, PEBBLE, "own")
            if verdict.answer != "yes":
                return False
            await commands.runner.wait_idle(TURN_WAIT_S)
        finally:
            commands.plan = plan
        if commands.runner.busy or not commands.runner.history:
            return False
        activity, ending = commands.runner.history[-1]
        return activity.kind == "turn" and ending.how == "done"

    def ears(self):
        return getattr(self.p.safety, "ears", None) or getattr(self.p.conversation, "ears", None)

    def mic(self):
        return getattr(self.ears(), "mic", None)

    def light(self, on: bool) -> str:
        asked = getattr(self.safety, "light_asked", None)
        if asked is None:
            return "I don't have a light I can switch on."
        return asked(on)

    def _take_settings(self) -> None:
        store = self.p.store
        try:
            names = waiting(store)
        except Exception:
            log.exception("house: could not look for new settings")
            return
        for name in names:
            try:
                item = store.read(name, None)
            except Exception:
                item = None
            try:
                self._new_settings(item if isinstance(item, dict) else {})
            finally:
                drop(store, name)

    def _new_settings(self, item: dict) -> None:
        changes = item.get("changes") if isinstance(item.get("changes"), dict) else {}
        tsunami = item.get("tsunami")
        people = [(p.id, list(p.names)) for p in self.life.company.book.people.values()]
        changed = sorted(changes) + (["tsunami"] if tsunami is not None else [])
        if not changed:
            self.record("house_settings", applied=False, why="nothing readable")
            return
        try:
            if changes:
                tried(self.book, people, **changes)
                apply(self.book, people, **changes)
                self.book.touch()
                self.book.save(force=True)
        except (Refused, KeyError, TypeError, ValueError) as error:
            self.record("house_settings", applied=False, changed=changed, why=str(error)[:120])
            return
        if tsunami is not None:
            prefs = self.p.books.preferences
            block = dict(prefs.get("safety") or {})
            block["tsunami_zone"] = bool(tsunami)
            prefs["safety"] = block
            self.p.books.save_preferences()
        self.record("house_settings", applied=True, changed=changed)
        self.note(f"your owner changed your house settings from the app ({', '.join(changed)})", False)

    def heard(self, heard, addressed=None):
        self.captions.heard(heard, self.mono())
        try:
            return self.asks.take(heard, addressed)
        except Exception:
            log.exception("house: could not take what was heard")
            return None

    def tick(self, now: float, quiet: bool) -> None:
        mono = self.mono()
        try:
            if not self.ladder_attached and getattr(self.safety, "ladder", None) is not None:
                self.ladder_attached = True
                self.alarms.attach()
            self._sounds(now, mono, quiet)
            self.cooking.tick(now, mono)
            self.alarms.tick(now, mono, quiet)
            self.away.tick(now, mono, quiet)
            self.days.tick(now, mono, quiet)
            self.noise.tick(now, mono)
            self.captions.tick(now, mono)
            self.high.tick(now, mono, quiet)
            self.checks.tick(quiet)
            if mono - self.slow_at >= SLOW_S:
                self.slow_at = mono
                self._visitors(now, mono)
                self._power(now)
                self._water()
            if mono - self.settings_at >= SETTINGS_S:
                self.settings_at = mono
                self._take_settings()
            if mono - self.pruned_at >= PRUNE_S:
                self.pruned_at = mono
                self.away.prune(now)
            self.teller.flush(mono)
            self.layer.tick()
        except Exception:
            log.exception("house: the tick failed")

    def _sounds(self, now: float, mono: float, quiet: bool) -> None:
        rows = []
        while self.inbox:
            rows.extend(self.inbox.popleft())
        if rows and self.detector is not None:
            self.rows.extend(rows)
            for event in self.detector.feed(rows):
                self.record("house_sound", what=event.event, score=event.score, **{k: v for k, v in event.detail.items() if isinstance(v, (int, float, str))})
                self.heard_sound(event.event)
                self.teller.sound(event.event, mono, now, quiet, event.detail)
        if len(self.taught) and self.hearing is not None:
            self._match(now, mono, quiet)

    def _frames(self, since: float = -math.inf) -> list:
        hearing = self.hearing
        np = self.taught.np
        if hearing is None or np is None:
            return []
        profiles = hearing.recent_profiles(since)
        if not profiles:
            return []
        return join(profiles, list(self.rows), hearing.recent_vectors(), np)

    def _match(self, now: float, mono: float, quiet: bool) -> None:
        frames = self._frames(self.profile_seen)
        if not frames:
            return
        self.profile_seen = frames[-1].at
        for match in self.taught.match(frames):
            self._matched(match, frames, now, mono, quiet)

    def _matched(self, match, frames, now: float, mono: float, quiet: bool) -> None:
        sound = self.taught.sounds.get(match.key)
        if sound is None:
            return
        sound.heard += 1
        self.taught.dirty = True
        self.record("taught_heard", key=sound.key, score=match.score, trusted=sound.trusted, others=list(match.others))
        if not sound.trusted:
            if quiet or not self.household_here(now) or self.asks.waiting():
                return
            kept = [f for f in frames if abs(f.at - match.at) <= 3.0]
            if self.teller.to_household(f"Was that {sound.name}?", f"sound:{sound.key}", mono):
                self.asks.expect("sound_check", (sound.key, kept), mono)
            return
        others = [self.taught.sounds[k] for k in match.others if k in self.taught.sounds]
        self.heard_sound(sound.name)
        line = sound.says() if not others else f"I think that was {thing_of(sound.name)} or {thing_of(others[0].name)}."
        self.away.add("sound", logged(sound.name), now)
        watchers = self.watchers.take(f"sound:{sound.key}", now)
        if watchers:
            self.teller.to_people(line, watchers, "sound", mono, logged(sound.name))
        elif not quiet and self.teller.to_household(line, f"sound:{sound.key}", mono):
            self.asks.last_sound = (sound.key, mono)
            if not self.asks.waiting():
                self.asks.expect("announced", sound.key, mono)
        self.save_sounds()

    def heard_sound(self, kind: str) -> None:
        later = getattr(self.life, "later", None)
        if later is not None:
            later.sound(kind)

    def teach(self, ask, asker, mono: float) -> str:
        if ask.topic == "alarm":
            return "I listen for smoke and carbon monoxide alarms by their own beeping pattern, so I won't learn them as a sound."
        if self.taught.np is None or self.hearing is None or self.hearing.profiler is None:
            return "I can't learn sounds on this body yet."
        frames = self._teach_frames()
        sound, outcome = self.taught.teach(ask.item, frames, asker.id, self.clock.now())
        self.hearing.want_vectors = True
        latest = self._frames()
        if latest:
            self.profile_seen = latest[-1].at
        if self.asks.pending is not None and self.asks.pending.kind == "sound_check":
            self.asks.pending = None
        if outcome == "nothing heard":
            return "I didn't catch a sound just then. Say it again while it's playing, or straight after it stops."
        if outcome == "full":
            return "I already know twenty sounds, which is all I can keep. Ask me to forget one first."
        self.save_sounds()
        self.diary(f"{asker.label} taught me the sound of {sound.name}.")
        if outcome == "learning":
            return f"Got it: {sound.name}. Next time it plays, tell me again, so I'm sure."
        return f"Got it. I know {sound.name} now. When I hear it, I'll say so."

    def _teach_frames(self) -> list:
        frames = self._frames()
        if not frames:
            return []
        last = frames[-1].at
        floor = self.hearing.meter.floor() if getattr(self.hearing, "meter", None) is not None else -120.0
        speech = {round(at, 1): s for at, s, _, _ in (self.detector.rows if self.detector is not None else [])}
        out = []
        for frame in frames:
            if last - frame.at > TEACH_S or frame.level_db < floor + TEACH_OVER_FLOOR_DB:
                continue
            nearest = min(speech, key=lambda at: abs(at - frame.at), default=None)
            if nearest is not None and abs(nearest - frame.at) <= 0.6 and speech[nearest] >= SPEECH_BELOW:
                continue
            out.append(frame)
        return out

    def sound_checked(self, data, yes: bool, asker) -> str:
        key, frames = data
        sound = self.taught.sounds.get(key)
        if sound is None:
            return "Okay."
        if yes:
            self.taught.teach(sound.name, frames, asker.id, self.clock.now())
            sound.right += 1
            self.save_sounds()
            return f"Thanks. Now I know {sound.name}."
        sound.wrong += 1
        self.save_sounds()
        return "Okay, thanks. I'll keep listening."

    def sound_feedback(self, key: str, yes: bool) -> str:
        sound = self.taught.sounds.get(key)
        if sound is None:
            return "Okay."
        if yes:
            sound.right += 1
            self.save_sounds()
            return "Good."
        sound.wrong += 1
        self.save_sounds()
        return "Thanks for telling me. I'll be more careful."

    def forget_sound(self, name: str) -> str:
        sound = self.taught.find(name) if name else None
        if sound is None and not name and self.asks.last_sound is not None:
            sound = self.taught.sounds.get(self.asks.last_sound[0])
        if sound is None:
            return "I don't know that sound."
        self.taught.forget(sound.key)
        self.watchers.items[:] = [w for w in self.watchers.items if w["key"] != f"sound:{sound.key}"]
        self.save_sounds(keep_backup=False)
        if self.hearing is not None:
            self.hearing.want_vectors = len(self.taught) > 0
        return f"Okay, I've forgotten the sound of {sound.name}."

    def sounds_line(self, name: str = "") -> str:
        if not len(self.taught):
            return "I haven't learnt any sounds yet. When something plays a tune, say \"that's the washing machine finishing\", and I'll learn it."
        if name:
            sound = self.taught.find(name)
            if sound is None:
                return "I don't know that sound."
            return f"I've said I heard {sound.name} {sound.heard} time{'s' if sound.heard != 1 else ''}. You told me I was right {sound.right} time{'s' if sound.right != 1 else ''} and wrong {sound.wrong} time{'s' if sound.wrong != 1 else ''}."
        names = [s.name + ("" if s.trusted else " (still learning)") for s in self.taught.sounds.values()]
        return f"I know {counted(len(names))} sound{'s' if len(names) != 1 else ''}: {listing(names)}."

    def save_sounds(self, keep_backup: bool = True) -> None:
        if not self.taught.dirty:
            return
        try:
            self.p.store.write(SOUNDS, self.taught.to_dict(), keep_backup=keep_backup)
            self.taught.dirty = False
        except Exception:
            log.exception("house: could not save the taught sounds")

    def save(self, force: bool = False) -> None:
        self.book.save(mono=self.mono(), force=force and self.book.dirty)
        self.save_sounds()
        if force:
            self.high.save()

    def saved_now(self) -> None:
        self.book.touch()
        self.book.save(force=True)

    def forget(self, person_id: str, names: list[str]) -> None:
        self.lists.forget_person(person_id)
        self.watchers.forget_person(person_id)
        self.away.forget_person(person_id)
        guardians = self.book.settings.get("guardians") or []
        self.book.settings["guardians"] = [g for g in guardians if g != person_id]
        curtains = self.book.settings.get("curtains")
        if isinstance(curtains, dict) and curtains.get("by") == person_id:
            self.book.settings["curtains"] = {"by": None, "label": ""}
        if self.visitors.by == person_id:
            self.visitors.by = None
        if self.captions.for_id == person_id:
            self.captions.stop("forgotten")
        self.book.touch()
        self.book.save(force=True, keep_backup=False)
        self.taught.forget_person(person_id)
        self.taught.dirty = True
        self.save_sounds(keep_backup=False)
        things = self.p.books.things
        if things.forget_teller(person_id):
            self.p.store.write("things.json", things.to_dict(), keep_backup=False)
            things.dirty = False

    def visitors_on(self, asker) -> str:
        now = self.clock.now()
        if not self.visitors.start(now, asker.id):
            return "Visitors mode is already on."
        self._visitors_changed(f"{asker.label} switched visitors mode on")
        return "Okay, visitors mode is on. I won't learn any new faces or voices, or keep anything I overhear, until someone tells me they've gone. I'll still listen out for alarms."

    def visitors_off(self, asker, why: str = "") -> str:
        if not self.visitors.stop():
            return "Visitors mode wasn't on."
        self._visitors_changed(why or f"{asker.label} switched visitors mode off")
        return "Okay, visitors mode is off."

    def _visitors_changed(self, why: str) -> None:
        self.book["visitors"] = self.visitors.to_dict()
        self.book.save(force=True)
        self.layer.badge("Visitors" if self.visitors.on else None)
        self.diary(f"Visitors mode {'on' if self.visitors.on else 'off'}: {why}.")
        self.note(f"visitors mode is {'on' if self.visitors.on else 'off'} ({why})", False)

    def _visitors(self, now: float, mono: float) -> None:
        stale = self.visitors.stale(now)
        if stale:
            self.visitors.stop()
            self._visitors_changed(f"it ended by itself because {stale}")
            return
        sight = self.sight()
        if sight is None:
            return
        company = self.life.company
        known = [p for p in company.here(now) if company.presence.seen(p.id, now, 10.0)]
        unknown = max(0, len(sight.people) - len(known))
        if not self.visitors.saw(unknown, now) or self.asks.waiting():
            return
        close = self.close_here(now)
        if not close or self.p.permissions.quiet:
            return
        self.visitors.offered(now)
        self.say("There are a few people here I don't know. Shall I go into visitors mode? I won't learn new faces or voices, or keep anything I overhear, until you tell me they've gone.", to=close[0].label, why="visitors offer")
        self.asks.expect("visitors_offer", None, mono)

    def keeps_line(self) -> str:
        if self.visitors.on:
            return "While visitors are here, I'm not learning any new faces or voices and I'm not keeping anything I overhear. I never record sound or video. Words I hear stay in my memory for five minutes, then they're gone."
        return "I never record sound or video. For people I've talked with, I keep numbers made from their face and voice so I can recognise them, and for someone I've only seen, numbers made from their face, so I know if they come back; a stranger's fade after 30 days. Words I hear stay in my memory for five minutes, then they're gone. Things people mention about themselves stay private to them, for up to two weeks. Someone I trust can ask me to forget a person."

    async def light_line(self, text: str, asker) -> str:
        sensors = getattr(self.life, "sensors", None)
        lux = getattr(sensors, "light_lux", None)
        if lux is None:
            lux = getattr(getattr(self.safety, "light", None), "latest", None)
        if lux is None:
            commands = self.life.commands
            verdict = decide(Request("sight_question"), asker, self.life.situation())
            if verdict.answer != "yes":
                return verdict.say or "I can't tell just now."
            return await commands.look_closer(text)
        whole = int(round(lux))
        if lux < LUX_DARK:
            return f"It's dark here: my light sensor reads about {whole} lux. That's only the light reaching my screen, so I can't tell about other rooms."
        if lux < LUX_DIM:
            return f"It's dim here, about {whole} lux at my screen, like a lamp across the room or the last of the daylight."
        if lux < LUX_BRIGHT:
            return f"There's light here, about {whole} lux at my screen, so a light is probably on, or daylight is coming in. I can't tell which."
        return f"It's bright here, about {whole} lux at my screen, like daylight or a light close by."

    def _power(self, now: float) -> None:
        sensors = getattr(self.life, "sensors", None)
        battery = getattr(sensors, "battery", None)
        charging = getattr(battery, "charging", None)
        docked = bool(getattr(self.p.body.telemetry, "docked", False))
        if not docked or charging is None:
            self.power_off_at = None
            self.charging = charging
            return
        if self.charging is True and charging is False:
            self.power_off_at = now
        elif charging is True and self.power_off_at is not None:
            gone = now - self.power_off_at
            if gone >= POWER_MIN_S:
                minutes = max(1, round(gone / 60.0))
                self.away.add("power", f"my charger stopped for about {minutes} minute{'s' if minutes != 1 else ''}, so the power may have been off", self.power_off_at)
            self.power_off_at = None
        self.charging = charging

    def _water(self) -> None:
        if self.pets.busy or self.p.permissions.quiet:
            return
        sight = self.sight()
        if sight is None or not self.pets.water_due(sight):
            return
        self.life.commands._spawn(self.pets.water(sight))

    def sight(self):
        eyes = self.p.eyes
        if not getattr(eyes, "available", False):
            return None
        try:
            return eyes.latest(1.0)
        except Exception:
            return None

    def _tiers(self, now: float) -> dict:
        if abs(now - self.tiers_at) >= 1.0:
            self.tiers_at = now
            self.tiers = self.life.company.tiers(now)
        return self.tiers

    def household_here(self, now: float | None = None) -> list:
        now = self.clock.now() if now is None else now
        tiers = self._tiers(now)
        return [p for p in self.life.company.here(now) if tiers.get(p.id, STRANGER) != STRANGER]

    def close_here(self, now: float | None = None) -> list:
        now = self.clock.now() if now is None else now
        tiers = self._tiers(now)
        return [p for p in self.life.company.here(now) if tiers.get(p.id) in (TRUSTED, INNER) or p.is_owner]

    def inner_here(self, now: float | None = None) -> list:
        now = self.clock.now() if now is None else now
        tiers = self._tiers(now)
        return [p for p in self.life.company.here(now) if tiers.get(p.id) == INNER or p.is_owner]

    def person(self, person_id: str | None):
        return self.life.company.book.get(person_id) if person_id else None

    def guardians(self) -> list[str]:
        book = self.life.company.book
        owner = book.owner()
        out = [owner.id] if owner is not None else []
        for person_id in self.book.settings.get("guardians") or []:
            if person_id not in out and book.get(person_id) is not None:
                out.append(person_id)
        return out

    def busy(self) -> bool:
        return self.alarm_going() or self.talking() or self.life.alive.hushed()

    def alarm_going(self) -> bool:
        return self.life.alarm()

    def talking(self) -> bool:
        conversation = getattr(self.p, "conversation", None)
        live = getattr(conversation, "live", None)
        try:
            return bool(live()) if live is not None else False
        except Exception:
            return False

    def someone_on_phone(self) -> bool:
        return self.life.alive.doings.on_the_phone()

    def cooks(self) -> list:
        doings = self.life.alive.doings.cooking()
        if not doings:
            return []
        here = self.life.company.here(self.clock.now())
        return [here[0].id] if len(here) == 1 else [None]

    def someone_in_kitchen(self, now: float) -> bool:
        sight = self.sight()
        if sight is None or not sight.people:
            return False
        alive = self.life.alive
        if alive.rooms.where_am_i() == "kitchen":
            return True
        kitchen = [t for t in sight.things if canonical(t.label) in KITCHEN_THINGS]
        if any(abs(person.bearing_deg - thing.bearing_deg) <= NEAR_COOKING_DEG for person in sight.people for thing in kitchen):
            return True
        odometer = self.life.odometer
        if not odometer.usable:
            return False
        status = self.p.body.telemetry.status
        x, y, heading = odometer.pose()
        for person in sight.people:
            gap = person_gap_m(person, sight, status.front_mm if status else None)
            aim = math.radians(heading + body_bearing(person.bearing_deg, sight.camera))
            if alive.rooms.room_at(x + gap * math.cos(aim), y + gap * math.sin(aim)) == "kitchen":
                return True
        return False

    def where_am_i(self) -> str | None:
        try:
            return self.life.alive.rooms.where_am_i()
        except Exception:
            return None

    def layer_show(self, kind: str, title: str, lines: list, qr: str | None = None) -> bool:
        if getattr(self.layer, "publish", None) is None:
            return False
        self.layer.show(kind, title, lines, qr=qr, hold_s=30.0)
        return True

    def wall(self, at: float) -> float:
        mono = self.mono()
        now = self.clock.now()
        if abs(mono - at) <= WALL_SANE_S:
            return now - (mono - at)
        return now

    def hhmm(self, ts: float) -> str:
        local = self.clock.local(ts)
        hour = local.hour % 12 or 12
        return f"{hour}:{local.minute:02d}{'am' if local.hour < 12 else 'pm'}"

    def day_words(self, ts: float) -> str:
        local = self.clock.local(ts)
        today = self.clock.local().date()
        days = (today - local.date()).days
        if days == 0:
            return "today"
        if days == 1:
            return "yesterday"
        return local.strftime("%A %d %B").replace(" 0", " ")

    def away_words(self, kind: str, text: str) -> str:
        return text.rstrip(".")[:1].lower() + text.rstrip(".")[1:]

    def say(self, text: str, to: str | None = None, urgent: bool = False, why: str = "house") -> None:
        if not text:
            return
        if to and to != "someone":
            text = f"{to}, {text if text.startswith(('I ', "I'")) else text[:1].lower() + text[1:]}"
        self.record("house_say", text=text, why=why, urgent=urgent)
        self.life.commands._spawn(self._voice(text, urgent))

    async def _voice(self, text: str, urgent: bool) -> None:
        rule = getattr(self.life, "rule_quiet", None)
        quiet = bool(self.p.permissions.quiet) or bool(rule is not None and rule())
        await self.p.voice.say(text, whisper=quiet and not urgent)

    async def speak(self, text: str) -> None:
        if text:
            await self.life.commands.speak(text, False)

    def tell_owner(self, title: str, text: str) -> bool:
        teller = getattr(self.safety, "tell_owner", None)
        if teller is None:
            return False
        try:
            return bool(teller(title, text))
        except Exception:
            log.exception("house: could not send the notice")
            return False

    def note(self, text: str, major: bool = False) -> None:
        self.life.events.add(self.clock.now(), text, major)
        if major:
            self.life.trigger.set()

    def diary(self, text: str) -> None:
        self.p.diary.write(text, "house")

    def record(self, kind: str, **data) -> None:
        self.p.blackbox.record(kind, **data)

    def change_settings(self, passphrase: str | None = None, password: str | None = None, **changes) -> dict:
        return change(self.p.store, passphrase, book=self.book, password=password, **changes)

    def status(self) -> dict:
        return {
            "lists": {name: self.lists.count(name) for name in self.lists.names()},
            "visitors": self.visitors.on,
            "taught": len(self.taught),
            "cooking": {"open": self.cooking.open, "said": self.cooking.said},
            "testing": getattr(getattr(self.safety, "ladder", None), "test", None) is not None,
            "captions": self.captions.on,
            "place": bool(self.days.place()),
            "high": self.high.status(),
            "checks": self.checks.status(),
        }
