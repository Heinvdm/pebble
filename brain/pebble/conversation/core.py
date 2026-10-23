import asyncio
import logging
import math
import random
from dataclasses import dataclass, field, replace

from ..mind.prompt import ROOM
from ..people.company import Heard
from ..people.proof import Proof
from ..self.registry import PEBBLE, bounds
from ..speech.events import SpeechEvent
from . import words as w
from .address import ADDRESSED, MAYBE, OVERHEARD, Cues, Room, Verdict, decide
from .facts import Overheard, forget as forget_facts, leaks
from .gist import Gist, Thought
from .holds import FAST_ANSWER_S, FAST_FIRST_S, FAST_SAMPLES, GLANCE_S, MAX_SPOKEN, SLOW, SMALL_ASK_S, STAGES, Phrasebook, echo_of, fence, situation_of
from .listening import NIGHT_WORDS_S, Listening, asks_help, asks_start, asks_stop, is_guest, may_mute, may_unmute
from .social import Social
from .monologue import Monologue
from .mouth import Mouth, sentences
from .pace import Pace, pace_of
from .speakers import SURE, Speakers, Who
from .speakup import RATE, Moment, SpeakUp
from .turns import TURN_LOW, Turn, TurnTaker
from .window import Line, Window

log = logging.getLogger(__name__)

TICK_S = 0.05
CONSIDER_WAIT_S = 0.6
GLANCE_DEG = 25.0
GLANCE_UP_DEG = 15.0
GLANCE_HOLD_S = 1.5
THINK_TILT_DEG = 6.0
THINK_TILT_S = 1.2
IDLE_S = 600.0
INVENT_TRY_S = 3600.0
HOLDS_SAVE_S = 60.0
HELLO = frozenset({"hello", "hi", "hey", "pebble", "are you there", "you there", "earth to pebble", "anyone home"})
FOLLOW_GAZE_S = 2.0
NOD_EVERY_S = (1.6, 2.6)
BARGE_WORDS = 2
BARGE_VOICE_S = 0.4
OWN_ONSET_S = 0.3
BEAT_AFTER_S = 30.0
LIVE_QUIET_S = 30.0
WARM_MIN_WORDS = 3
READY_AFTER_S = 1.0
THINK_BACK = "Let me think back."
THINK_BACK_S = 1.5
THOUGHTS_CHARS = 150
ROOM_ANSWER_KEEP_S = 6.0
ARGUMENT_S = 60.0
CRYING_S = 120.0
LAUGH_GAP_S = 8.0
FEEL_EVERY_S = 30.0
AEC_EVERY_S = 60.0
SPEAKUP_DIAL = "speakup.per_hour"
SPEAKUP_SPAN = 4.0
FALLBACK_EVERY_S = 300.0
STRONG_FEAR = 6.0
STRONG_JOY = 0.8
STRONG_LOW = -0.7
FACTS_EVERY_S = 3600.0
SHOUT_OVER_DB = 12.0
TALK_WINDOW_S = 120.0
LAUGH = ("Laughter", "Giggle", "Chuckle, chortle", "Belly laugh", "Baby laughter", "Snicker")
CLAP = ("Clapping", "Applause")
CRY = ("Crying, sobbing", "Whimper", "Wail, moan")
SHOUT = ("Shout", "Yell", "Screaming")
SOUND_AT = 0.4
FALLBACK = "Sorry, my thoughts are slow right now."
NAME_ONLY = ("Yes?", "Mm?", "I'm here.")


def thoughts_line(thoughts: list) -> str:
    kept, used = [], 0
    for thought in reversed(thoughts):
        text = " ".join(str(thought.text).split())
        if kept and used + len(text) + 1 > THOUGHTS_CHARS:
            break
        kept.insert(0, text)
        used += len(text) + 1
    return "On your mind: " + " ".join(kept)


@dataclass
class Pending:
    reason: str
    text: str
    until: float
    to: str | None = None


@dataclass
class Stats:
    replies: int = 0
    latencies: list = field(default_factory=list)
    answer_latencies: list = field(default_factory=list)
    acks: int = 0
    barge_ins: int = 0
    echoes: int = 0
    labels: dict = field(default_factory=lambda: {ADDRESSED: 0, MAYBE: 0, OVERHEARD: 0})
    spoke_up: int = 0
    closed_by: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        lat = sorted(self.latencies)
        answers = sorted(self.answer_latencies)
        return {
            "replies": self.replies,
            "acknowledged_first": self.acks,
            "first_answer_word_s_median": round(answers[len(answers) // 2], 3) if answers else None,
            "first_word_s_median": round(lat[len(lat) // 2], 3) if lat else None,
            "first_word_s_max": round(lat[-1], 3) if lat else None,
            "barge_ins": self.barge_ins,
            "echoes_dropped": self.echoes,
            "heard": dict(self.labels),
            "spoke_up": self.spoke_up,
            "turns_closed_by": dict(self.closed_by),
        }


class Conversation:
    def __init__(self, clock, store=None, books=None, voice=None, face=None, rng: random.Random | None = None, tick_s: float = TICK_S, sleep=None):
        self.clock = clock
        self.sleep = sleep or asyncio.sleep
        self.store = store
        self.books = books
        self.face = face
        self.name = getattr(books, "name", "Pebble") if books is not None else "Pebble"
        self.rng = rng or random.Random()
        self.tick_s = tick_s
        prefs = getattr(books, "preferences", {}) if books is not None else {}
        self.window = Window()
        self.monologue = Monologue()
        self.room = Room(self.name)
        self.listening = Listening(store, clock, prefs)
        self.overheard = Overheard(store, clock) if store is not None else None
        self.mouth = Mouth(voice, face, clock, store, sleep=self.sleep)
        self.holds = Phrasebook(store, self.rng, clock)
        self.social = Social(store, self.rng, clock)
        self.invent_at = -math.inf
        self.holds_saved_at = -math.inf
        self.speakup = SpeakUp(self._chatty, self.rng, self._speakup_rate)
        self.gist = Gist()
        self.turns = TurnTaker(on_change=self._changed, on_close=self._closed, on_name=self._named)
        self.stats = Stats()
        self.life = None
        self.ears = None
        self.hub = None
        self.phone = None
        self.speakers: Speakers | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.tasks: set = set()
        self.reply_task: asyncio.Task | None = None
        self.replying_to: Turn | None = None
        self.speculation: tuple[str, asyncio.Task, list, str | None] | None = None
        self.heat = None
        self.pending: Pending | None = None
        self.gist_from: float | None = None
        self.argument_until = -math.inf
        self.crying_until = -math.inf
        self.laughed_at = -math.inf
        self.exchange_at = -math.inf
        self.addressed_at = -math.inf
        self.warm_task: asyncio.Task | None = None
        self.ready_mark = None
        self.ready_pending = None
        self.ready_changed_at = -math.inf
        self.beat_due = False
        self.voice_since: float | None = None
        self.voice_segment: int | None = None
        self.voice_own = False
        self.voice_heard = False
        self.voice_maybe_own = False
        self.nod_at = -math.inf
        self.gaze_at = -math.inf
        self.feel_at = -math.inf
        self.facts_at = -math.inf
        self.seen_night = None
        self.mark: dict = {}
        self.sound_columns: dict[str, list[int]] = {}
        self.aec = False
        self.aec_at = -math.inf
        self.fallback_at = -math.inf
        self.seen_upto = 0
        self.was_here: set = set()
        self.trace = lambda what, text: None

    def _speakup_rate(self) -> float:
        dials = getattr(self.life, "dials", None) if self.life is not None else None
        if dials is None:
            return RATE
        return float(dials.value(SPEAKUP_DIAL))

    def _speakup_learned(self, direction: int, why: str) -> None:
        life = self.life
        dials = getattr(life, "dials", None) if life is not None else None
        if dials is None or not direction:
            return
        plasticity = getattr(life, "plasticity", None)
        step = plasticity.step(SPEAKUP_SPAN) if plasticity is not None else SPEAKUP_SPAN * 0.04
        low, high = bounds(SPEAKUP_DIAL)
        before = float(dials.value(SPEAKUP_DIAL))
        after = round(min(high, max(low, before + direction * step)), 2)
        if after == before:
            return
        ruling = dials.propose(SPEAKUP_DIAL, after, PEBBLE, why)
        self.trace("learns", f"speaking up unasked: {before:g} to {after:g} an hour ({why})" if ruling.ok else f"speaking up unasked stays at {before:g} an hour ({ruling.reason})")

    def _chatty(self) -> int:
        store = self.store
        traits = ((store.read("personality.json", {}) or {}).get("traits") or {}) if store is not None else {}
        return int(traits.get("chatty", 3) or 3)

    def attach(self, life, safety=None, ears=None, hub=None) -> "Conversation":
        self.life = life
        company = life.company
        company.book.thresholds["voice"] = SURE
        self.speakers = Speakers(company.book, company.presence, self.clock.now)
        self.name = life.p.books.name
        self.room.name = self.name
        diary = getattr(life.p, "diary", None)
        if diary is not None:
            self.holds.diary = lambda text: diary.write(text, "holds")
            self.social.diary = lambda text: diary.write(text, "words")
        self.gist.mind = getattr(life.p.subconscious, "mind", None)
        self.hub = hub
        if hub is not None and hasattr(hub, "add_replay"):
            hub.add_replay(lambda: [("ears", dict(self.mark))] if self.mark else [])
        self.ears = ears
        if ears is not None:
            ears.policy = self.listening.policy
            configure = getattr(ears, "configure", None)
            if configure is not None:
                configure(keywords=self.listening.spelled(self.name), min_silence_s=0.25, print_after_final=True, print_min_s=1.0)
            if hasattr(ears, "sink"):
                ears.sink = self.on_speech
            if hasattr(ears, "speaking"):
                ears.speaking = lambda: self.mouth.speaking
        hearing = getattr(safety, "hearing", None)
        if hearing is not None:
            taps = getattr(hearing, "taps", None)
            if taps is not None:
                taps.append(self._sounds)
            labels = list(getattr(getattr(hearing, "model", None), "labels", []) or [])
            self._columns(labels)
            block_taps = getattr(hearing, "block_taps", None)
            if block_taps is not None and ears is not None and getattr(ears, "source", "none") is None and hasattr(ears, "tap"):
                block_taps.append(ears.tap)
        return self

    def _columns(self, labels: list[str]) -> None:
        index = {name: i for i, name in enumerate(labels)}
        self.sound_columns = {kind: [index[n] for n in names if n in index] for kind, names in (("laugh", LAUGH), ("cry", CRY), ("shout", SHOUT), ("clap", CLAP))}

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        if self.ears is not None and type(self.ears).__name__ == "AndroidEars":
            from ..speech.phone import PhoneSpeech, attach_phone, detach_phone

            self.phone = PhoneSpeech()
            self.phone.bind(self.loop, self.on_speech)
            attach_phone(self.phone)
        try:
            while True:
                await self.sleep(self.tick_s)
                try:
                    self.tick()
                except Exception:
                    log.exception("conversation: the tick failed")
        finally:
            if self.phone is not None:
                from ..speech.phone import detach_phone

                detach_phone()
            for task in list(self.tasks):
                task.cancel()
            self.save()

    def mono(self) -> float:
        return self.clock.monotonic()

    def _spawn(self, coro) -> asyncio.Task | None:
        try:
            task = asyncio.ensure_future(coro)
        except RuntimeError:
            coro.close()
            return None
        self.tasks.add(task)
        task.add_done_callback(self._done)
        return task

    def _done(self, task: asyncio.Task) -> None:
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.error("conversation: a task failed", exc_info=task.exception())

    def present(self, now: float | None = None) -> frozenset:
        if self.life is None:
            return frozenset()
        now = self.clock.now() if now is None else now
        company = self.life.company
        here = set(company.presence.here(now))
        if company.someone_new(now):
            here.add("?")
        return frozenset(here)

    def _key(self, who: Who) -> str:
        if who.person_id:
            return who.person_id
        if who.track is not None:
            return f"t{who.track}"
        return "?"

    def _label(self, person_id: str | None) -> str:
        person = self.life.company.book.get(person_id) if self.life is not None and person_id else None
        return person.label if person is not None else "someone"

    def _quiet(self) -> bool:
        if self.life is None:
            return False
        return bool(self.life.quiet_hours.contains(self.clock.local()))

    def _soft(self) -> bool:
        if self._quiet():
            return True
        rule = getattr(self.life, "rule_quiet", None) if self.life is not None else None
        return bool(rule is not None and rule())

    def on_speech(self, event: SpeechEvent) -> None:
        now = self.mono()
        if event.kind == "spoken":
            self.mouth.heard_spoken(event)
            return
        speaking = self.mouth.speaking
        if event.kind == "voice_start":
            self._hear_voice(True)
            self.voice_since = event.t
            self.voice_segment = event.segment
            self.voice_own = False
            self.voice_heard = False
            self.voice_maybe_own = self._maybe_own(event)
        elif event.kind == "voice_end":
            self.voice_since = None
            self._hear_voice(False)
        if speaking and event.kind in ("partial", "final") and self.mouth.echo(event.text):
            self.stats.echoes += 1
            if event.segment == self.voice_segment:
                self.voice_own = True
            return
        if speaking:
            self._barge(event, now)
        if event.kind == "keyword" and asks_help(event.word):
            self._help_word(event)
            return
        if event.kind == "keyword" and self.listening.muted:
            self._keyword_while_muted(event)
            return
        if event.kind == "keyword":
            self._wake_at_night()
        if self.listening.muted and getattr(self.ears, "mode", "words") != "words":
            return
        self.turns.feed(event)

    def _hear_voice(self, on: bool) -> None:
        eyes = getattr(self.life.p, "eyes", None) if self.life is not None else None
        hear = getattr(eyes, "hear_voice", None)
        if hear is not None:
            try:
                hear(on)
            except Exception:
                log.debug("conversation: the eyes would not take hear_voice")

    def _barge(self, event: SpeechEvent, now: float) -> None:
        cut = ""
        if event.kind == "keyword":
            current = " ".join(p.text for p in self.mouth.parts.values() if p.done_at is None or now - p.done_at < 1.0)
            cut = "" if w.name_at(current, self.name) else "my name"
        elif event.kind == "partial":
            current = " ".join(p.text for p in self.mouth.parts.values() if p.done_at is None)
            fresh = [x for x in w.words(event.text) if x not in set(w.words(current))]
            if fresh and event.segment == self.voice_segment:
                self.voice_heard = True
            if len(fresh) >= BARGE_WORDS:
                cut = "words"
        if not cut and self._voice_barges(now):
            cut = "voice"
        if cut:
            self.barge_in(cut)

    def _maybe_own(self, event: SpeechEvent) -> bool:
        if not (event.pebble_speaking or self.mouth.speaking):
            return False
        if not self.aec:
            return True
        return any(p.started_at is not None and 0.0 <= event.t - p.started_at <= OWN_ONSET_S for p in self.mouth.parts.values())

    def _voice_barges(self, now: float) -> bool:
        if not self.listening.barge_on_voice or self.voice_since is None or self.voice_own or not self.mouth.speaking:
            return False
        if self.voice_maybe_own and not self.voice_heard:
            return False
        started = [p.started_at for p in self.mouth.parts.values() if p.started_at is not None and p.done_at is None and not p.stopped]
        if not started:
            return False
        return now - max(self.voice_since, min(started)) >= BARGE_VOICE_S

    def barge_in(self, why: str, how: str = "talked_over") -> None:
        self.holds.outcome(how, self.mono())
        self.speakup.talked_over(self.mono())
        said = self.mouth.stop()
        self.trace("stops", f"talked over ({why}); it had said: \"{said}\"")
        self.stats.barge_ins += 1
        task = self.reply_task
        if task is not None and not task.done():
            task.cancel()
        if self.face is not None:
            self.face.show("curious")
        if self.life is not None:
            self.life.p.blackbox.record("barge_in", why=why, said=said[:120])

    def _keyword_while_muted(self, event: SpeechEvent) -> None:
        if not asks_start(event.word.replace("_", " ")):
            return
        if self._may_unmute_here():
            self.listening.unmute()
            self._update_ears(force=True)
            self._say_now("My ears are back on.")
            self._note("someone you trust, or whoever switched them off, asked you to listen again, so your ears are on", False)

    def _help_word(self, event: SpeechEvent) -> None:
        safety = getattr(getattr(self.life, "p", None), "safety", None)
        if safety is None:
            return
        try:
            safety.heard(Heard(None, "someone", event.word.replace("_", " "), addressed=False), False)
        except Exception:
            log.exception("conversation: safety could not take a call for help")

    def _guest_mute(self) -> None:
        listening = self.listening
        if not listening.muted or not listening.guest or self.life is None:
            return
        person_id = listening.muted_by
        here = person_id is not None and (person_id in self.present() or self._in_view(person_id))
        if listening.guest_here(here, self.clock.now()):
            self._update_ears(force=True)
            self._note("the guest who switched your ears off has gone, so your ears are on again", False)

    def _in_view(self, person_id: str) -> bool:
        if self.speakers is None or not self.speakers.sights:
            return False
        at, people = self.speakers.sights[-1]
        if self.mono() - at > 2.0:
            return False
        return any(self.speakers.tracks.get(seen.track, (None, 0.0))[0] == person_id for seen in people if seen.track is not None)

    def _may_unmute_here(self) -> bool:
        life = self.life
        if life is None:
            return False
        now = self.clock.now()
        company = life.company
        return any(may_unmute(company.tier(p, now), p.is_owner, p.id == self.listening.muted_by) for p in company.here(now))

    def _wake_at_night(self, keep: bool = False) -> None:
        ears = self.ears
        if ears is None or self.listening.muted or not self._quiet():
            return
        if not keep and getattr(ears, "mode", "words") != "keywords":
            return
        wake = getattr(ears, "wake_for", None)
        if wake is None:
            return
        try:
            wake(NIGHT_WORDS_S)
        except Exception:
            log.debug("conversation: the ears would not wake for the name")
            return
        self._update_ears(force=True)

    def _sight(self):
        life = self.life
        eyes = getattr(life.p, "eyes", None) if life is not None else None
        if eyes is None or not getattr(eyes, "available", False):
            return None
        try:
            return eyes.latest(1.0)
        except Exception:
            return None

    def _look(self) -> None:
        sight = self._sight()
        if sight is None or self.speakers is None:
            return
        at = self.mono() - max(0.0, self.clock.now() - sight.at)
        self.speakers.look(sight, at)

    def _talker_now(self):
        if self.speakers is None:
            return None
        now = self.mono()
        talker, _, _ = self.speakers.talker(now - 0.6, now)
        return talker

    def _named(self, turn: Turn) -> None:
        talker = self._talker_now()
        alive = getattr(self.life, "alive", None) if self.life is not None else None
        if alive is not None:
            alive.face_speaker(talker.track if talker else None, talker.bearing_deg if talker else None)
        if self.face is not None:
            self.face.show("curious")
        turn.notes["named_at"] = self.mono()
        self._give_way(turn)

    def _provisional(self, turn: Turn) -> bool:
        if turn.keyword or turn.notes.get("named_at"):
            return True
        talker = self._talker_now()
        if talker is not None and talker.track is not None and self.speakers is not None:
            known = self.speakers.tracks.get(talker.track)
            if known is not None and self.room.attentive.get(known[0], -math.inf) >= self.mono():
                return True
        return False

    def _changed(self, turn: Turn, kind: str) -> None:
        now = self.mono()
        alive = getattr(self.life, "alive", None) if self.life is not None else None
        talker = self._talker_now()
        if alive is not None and talker is not None and now - self.gaze_at >= FOLLOW_GAZE_S:
            self.gaze_at = now
            alive.speaking(talker.track, talker.bearing_deg)
        if not self._provisional(turn):
            return
        self._give_way(turn)
        if kind in ("voice", "partial") and alive is not None and now >= self.nod_at and len(w.words(turn.text)) >= 4:
            self.nod_at = now + self.rng.uniform(*NOD_EVERY_S)
            alive.nod()
        if kind == "partial":
            self._read_ahead(turn)
        if kind in ("pause", "turn_end") and self._sounds_done(turn):
            self._speculate(turn)

    def _sounds_done(self, turn: Turn) -> bool:
        chance = turn.done_chance
        if chance is not None and chance <= TURN_LOW:
            return False
        return w.complete(w.body(turn.text, (self.name,)))

    def pace(self) -> Pace:
        return pace_of(self.heat)

    def _warm_busy(self) -> bool:
        return self.warm_task is not None and not self.warm_task.done()

    def _read_ahead(self, turn: Turn) -> None:
        life = self.life
        warm = getattr(life, "warm_reply", None) if life is not None else None
        if warm is None or self._warm_busy() or self.speculation is not None or self.reply_task is not None:
            return
        parts = (turn.text or "").split()
        stable = len(parts) - 1
        if stable - int(turn.notes.get("warmed", 0)) < WARM_MIN_WORDS:
            return
        turn.notes["warmed"] = stable
        speaker = self._likely_speaker(turn)
        observation, private = self._observation(turn, " ".join(parts[:stable]), speaker)
        self.warm_task = self._spawn(self._warm_both(getattr(life, "warm_request", None), " ".join(parts[:stable]), speaker, warm, observation, private))

    async def _warm_both(self, request, said: str, speaker, warm, observation: str, private) -> bool:
        if request is not None:
            try:
                await request(said, speaker)
            except Exception:
                log.exception("conversation: could not read the request ahead")
        return await warm(observation, private, "warm")

    def _likely_speaker(self, turn: Turn) -> str | None:
        if turn.speaker:
            return turn.speaker
        talker = self._talker_now()
        if talker is not None and talker.track is not None and self.speakers is not None:
            known = self.speakers.tracks.get(talker.track)
            if known is not None:
                return known[0]
        return None

    def _ready_ahead(self, now: float) -> None:
        life = self.life
        warm = getattr(life, "warm_reply", None) if life is not None else None
        if warm is None:
            return
        mark = self._ready_mark()
        if mark == self.ready_mark:
            return
        if mark != self.ready_pending:
            self.ready_pending = mark
            self.ready_changed_at = now
        if now - self.ready_changed_at < READY_AFTER_S:
            return
        if self._warm_busy() or (self.reply_task is not None and not self.reply_task.done()) or self.mouth.speaking or self.turns.turn is not None or getattr(life, "_in_turn", False):
            return
        memory = getattr(life, "memory", None)
        board = ""
        if memory is not None:
            memory.swap_ahead()
            board = memory.board_text(self.present())
        self.ready_mark = self.ready_pending = self._ready_mark()
        self.warm_task = self._spawn(warm(board, [{"to": ROOM, "text": board}] if board else [], "ready"))

    def _ready_mark(self) -> tuple:
        life = self.life
        history = getattr(life.p, "history", None)
        memory = getattr(life, "memory", None)
        ahead = memory.ahead_mark() if memory is not None else ()
        return (len(getattr(history, "turns", ()) or ()), getattr(history, "compactions", 0), self.stats.replies, self.present(), ahead)

    def _speculate(self, turn: Turn) -> None:
        if self.life is None or self.reply_task is not None:
            return
        text = turn.text
        memory = getattr(self.life, "memory", None)
        if memory is not None and (memory.remembering(text) or memory.answers(text)):
            return
        if self.speculation is not None:
            if w.words(self.speculation[0]) == w.words(text):
                return
            self._drop_speculation()
        to = self._likely_speaker(turn)
        observation, private = self._observation(turn, text, to)
        tokens = self.pace().reply_tokens
        buffer: list = []

        async def think():
            async for piece in self.life.reply(observation, private, tokens, speaker=to):
                buffer.append(piece)
            buffer.append(None)

        task = self._spawn(think())
        if task is not None:
            self.speculation = (text, task, buffer, to)

    def _drop_speculation(self) -> None:
        if self.speculation is not None:
            task = self.speculation[1]
            task.cancel()
            self.speculation = None

    def _closed(self, turn: Turn) -> None:
        why = turn.notes.get("closed_by")
        if why:
            self.stats.closed_by[why] = self.stats.closed_by.get(why, 0) + 1
        try:
            self._take(turn)
        except Exception:
            log.exception("conversation: could not take a turn")

    def _take(self, turn: Turn) -> None:
        life = self.life
        if life is None:
            return
        text = turn.text
        now = self.mono()
        if self.listening.muted:
            if text:
                life.hear(text, None, self._shouted(turn), addressed=False)
            return
        if turn.pebble_speaking and self.mouth.echo(text):
            self.stats.echoes += 1
            return
        if not text and not turn.keyword:
            return
        start = turn.start
        end = turn.end if turn.end is not None else now
        spoke = self._eyes_spoke(start, end)
        prefer = max(spoke, key=spoke.get) if spoke else None
        if prefer is not None and spoke[prefer] < 0.5:
            prefer = None
        who = self.speakers.identify(turn.voiceprint, start, end, self.clock.now(), prefer) if self.speakers is not None else Who(None, 0.0, "unknown")
        key = self._key(who)
        present = self.present()
        own = self._label(who.person_id) if who.person_id else ""
        names = tuple(sorted(({self._label(pid) for pid in present if pid not in (who.person_id, "?")} | set(self._known_names())) - {own, "someone", ""}))
        busy = self._busy(who.track)
        cues = self.room.cues(now, key, text, turn.keyword, max(1, len(present | {key}), who.in_view), looking=who.looking, at_other=who.looking_at_other, on_phone=who.on_phone, names=names, busy=busy, name_alone=turn.name_alone)
        verdict = decide(cues)
        if not text and turn.keyword:
            verdict = Verdict(ADDRESSED, 4.0, ("my name was called",))
        turn.verdict = verdict
        self.stats.labels[verdict.label] += 1
        loud = self._shouted(turn)
        addressed = verdict.addressed
        speaker = who.person_id
        voice = None if speaker else turn.voiceprint
        visiting = self._visiting()
        if addressed and not speaker and not visiting:
            enrol = self.speakers.enrol_target(turn.voiceprint, self.clock.now()) if self.speakers is not None else None
            if enrol is not None:
                person = life.company.book.get(enrol)
                if person is not None and turn.voiceprint is not None:
                    person.add_print("voice", turn.voiceprint, self.clock.now())
                    life.company.dirty = True
                speaker = enrol
                voice = None
        heard = None
        if text:
            before = set(getattr(life.commands, "tasks", set()))
            proof = Proof(who.person_id, who.voiced, who.lips, who.track)
            heard = life.hear(text, voice, loud, addressed=addressed, speaker=speaker, proof=proof)
            considering = getattr(life, "considering", None)
            if considering is None and addressed:
                fresh = set(getattr(life.commands, "tasks", set())) - before
                considering = next(iter(fresh), None)
            turn.notes["considering"] = considering
            if heard is not None and heard.person_id:
                speaker = heard.person_id
                key = speaker
                if self.speakers is not None:
                    self.speakers.remember_track(who.track, speaker, self.clock.now())
                    self.speakers.adapt(speaker, turn.voiceprint, who.score, len(present) <= 1, self.clock.now(), bool(heard.sure) and who.how == "voice")
        turn.speaker = speaker
        turn.track = who.track
        turn.bearing_deg = who.bearing_deg
        turn.label = heard.label if heard is not None else self._label(speaker)
        turn.heard = heard
        self.room.heard(now, key, verdict, text)
        if text:
            self.speakup.heard(now, text, addressed)
        if addressed:
            self.addressed_at = now
            self._wake_at_night(keep=True)
        audience = frozenset(present | ({speaker} if speaker else set()))
        fact = None
        if not addressed and text and speaker and self.overheard is not None and not visiting:
            fact = self.overheard.learn(speaker, turn.label, text)
            if fact is not None:
                self.monologue.add(Thought(self.clock.now(), fact.text, "fact", (speaker,), frozenset({speaker}), 0.6, True))
                self.trace("notes", f"(private, only for {turn.label}) {fact.text}")
        if text:
            self.window.add(Line(now, speaker, turn.label, text, verdict.label, audience, private=bool(heard is not None and heard.private) or fact is not None))
            if self.gist_from is None:
                self.gist_from = now
        life.p.blackbox.record("talk", label=verdict.label, score=round(verdict.score, 2), person=speaker, why=list(verdict.reasons[:3]), words=len(w.words(text)))
        self.trace("decides", f"{verdict.label} ({verdict.score:+.1f}: {'; '.join(verdict.reasons[:3]) or 'no cues'})")
        self._react(turn, verdict, cues, who)
        if addressed:
            self._spawn(self._respond(turn, who))
        else:
            self._drop_speculation()
            if cues.to_room and heard is not None and verdict.label != ADDRESSED:
                self._spawn(self._room_question(heard, turn))

    def _visiting(self) -> bool:
        company = getattr(self.life, "company", None) if self.life is not None else None
        visiting = getattr(company, "visiting", None)
        return bool(visiting()) if visiting is not None else False

    def _known_names(self) -> list[str]:
        if self.life is None:
            return []
        return [p.name for p in self.life.company.book.people.values() if p.name][:50]

    def _busy(self, track) -> bool:
        alive = getattr(self.life, "alive", None)
        doings = getattr(alive, "doings", None)
        doing = getattr(doings, "doing", None)
        if doing is None:
            return False
        try:
            return any(d.what in ("working", "watching tv", "reading", "cooking", "on the phone") and (track is None or d.track == track) for d in doing())
        except Exception:
            return False

    def _eyes_spoke(self, start: float, end: float) -> dict:
        eyes = getattr(self.life.p, "eyes", None) if self.life is not None else None
        spoke = getattr(eyes, "spoke", None)
        if spoke is None:
            return {}
        offset = self.clock.now() - self.mono()
        try:
            found = spoke(start + offset, end + offset)
        except Exception:
            return {}
        return {k: float(v) for k, v in (found or {}).items() if v is not None}

    def _shouted(self, turn: Turn) -> bool:
        hearing = getattr(getattr(self.life.p, "safety", None), "hearing", None) if self.life is not None else None
        talk = None
        if hearing is not None and hasattr(hearing, "talk_db"):
            try:
                talk = hearing.talk_db()
            except Exception:
                talk = None
        level = turn.level_db
        if level is None:
            return False
        return level >= -12.0 or (talk is not None and level - talk >= SHOUT_OVER_DB)

    def _react(self, turn: Turn, verdict: Verdict, cues: Cues, who: Who) -> None:
        now_wall = self.clock.now()
        text = turn.text
        face = self.face
        if cues.name == "mention" and not verdict.addressed:
            if face is not None:
                face.show("surprised")
            alive = getattr(self.life, "alive", None)
            if alive is not None:
                alive.speaking(who.track, who.bearing_deg)
            self.monologue.add(Thought(now_wall, f"{turn.label} said my name.", "heard", (turn.speaker,) if turn.speaker else (), self.present(), 0.5, True))
            self._consider_speakup("named", "", turn.speaker)
        if w.laughing(text):
            self._laughed()
        if w.hostile(text) and len(self.room.voices(self.mono(), 30.0)) >= 2:
            self.argument_until = self.mono() + ARGUMENT_S
            self._upset(600.0)
        favourite = self._favourite(text)
        if favourite and not verdict.addressed:
            if face is not None:
                face.show("happy")
            self.monologue.add(Thought(now_wall, f"They talked about {favourite}. I like {favourite}.", "heard", (), self.present(), 0.5, True))
        if verdict.label == MAYBE and face is not None:
            face.show("curious")

    def _favourite(self, text: str) -> str:
        prefs = getattr(self.books, "preferences", {}) if self.books is not None else {}
        favourites = [str(v).lower() for v in (prefs.get("favourites") or {}).values() if v]
        favourites += [str(v).lower() for v in (prefs.get("likes") or []) if v]
        said = " ".join(w.words(text))
        for thing in favourites:
            if thing and f" {thing} " in f" {said} ":
                return thing
        return ""

    def _laughed(self) -> None:
        now = self.mono()
        if now - self.laughed_at < LAUGH_GAP_S:
            return
        self.laughed_at = now
        self.holds.outcome("laughed", now)
        self.speakup.laughed(now)
        self.gist.laughed()
        if self.face is not None and not self.mouth.speaking:
            self.face.show("happy")
        if self.life is not None:
            self.life.p.inner.on_event("talk", self.clock.now())
            hint = getattr(self.life, "hint", None)
            if hint is not None:
                hint("laugh")

    def _upset(self, seconds: float) -> None:
        upset = getattr(self.life, "someone_upset", None)
        if upset is not None:
            upset(seconds)

    def _sounds(self, rows) -> None:
        if not rows or not self.sound_columns:
            return
        found = {}
        for kind, columns in self.sound_columns.items():
            if columns:
                found[kind] = max(max(scores[c] for c in columns) for _, scores in rows)
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._sounded, found)
        except RuntimeError:
            pass

    def _sounded(self, found: dict) -> None:
        now = self.mono()
        if found.get("laugh", 0.0) >= SOUND_AT:
            self._laughed()
        if found.get("cry", 0.0) >= SOUND_AT:
            if now > self.crying_until and self.face is not None:
                self.face.show("sad")
            self.crying_until = now + CRYING_S
            self.gist.cried()
            self._upset(900.0)
        if found.get("shout", 0.0) >= SOUND_AT and len(self.room.voices(now, 30.0)) >= 2:
            self.argument_until = now + ARGUMENT_S
        if found.get("clap", 0.0) >= SOUND_AT and self.life is not None:
            hint = getattr(self.life, "hint", None)
            if hint is not None:
                hint("clap")

    def moment(self) -> Moment:
        life = self.life
        now = self.mono()
        quiet = self._soft()
        alarm = bool(life.alarm()) if life is not None else False
        hushed = bool(life.alive.hushed()) if life is not None and getattr(life, "alive", None) is not None else False
        upset = bool(life.creative.upset_until > self.clock.now()) if life is not None and getattr(life, "creative", None) is not None else False
        talker = self._talker_now()
        recent = [line for line in self.window.recent(now, 8.0) if not line.pebble]
        flowing = len({line.who for line in self.window.recent(now, 30.0) if not line.pebble}) >= 2 and bool(recent)
        return Moment(
            now,
            quiet=quiet,
            alarm=alarm,
            hushed=hushed,
            argument=now < self.argument_until,
            crying=now < self.crying_until,
            on_phone=bool(talker is not None and talker.on_phone),
            upset=upset,
            silent_for=self.turns.silent_for(now),
            someone_talking=self.turns.turn is not None and self.turns.turn.talking(),
            pebble_speaking=self.mouth.speaking,
            flowing=flowing and self.turns.silent_for(now) < 3.0,
        )

    def live(self, now: float | None = None) -> bool:
        now = self.mono() if now is None else now
        if self.reply_task is not None and not self.reply_task.done():
            return True
        if self.mouth.speaking:
            return True
        turn = self.turns.turn
        if turn is not None and (turn.keyword or turn.notes.get("named_at") or turn.notes.get("gave_way")):
            return True
        return now - max(self.exchange_at, self.addressed_at) < LIVE_QUIET_S

    def quiet_for(self, now: float | None = None) -> float:
        now = self.mono() if now is None else now
        if self.reply_task is not None and not self.reply_task.done():
            return 0.0
        if self.mouth.speaking or self.speculation is not None:
            return 0.0
        turn = self.turns.turn
        if turn is not None and (turn.keyword or turn.notes.get("named_at") or turn.notes.get("gave_way")):
            return 0.0
        return now - max(self.exchange_at, self.addressed_at)

    def warmed(self) -> None:
        self.ready_mark = self.ready_pending = self._ready_mark()

    def _give_way(self, turn: Turn) -> None:
        if turn.notes.get("gave_way") or self.life is None:
            return
        turn.notes["gave_way"] = self.mono()
        mind = getattr(self.life.p, "mind", None)
        give_way = getattr(mind, "give_way", None)
        if give_way is None:
            return
        try:
            if give_way():
                self.trace("gives way", "a background thought is put off for later")
        except Exception:
            log.exception("conversation: the mind would not give way")

    def hold_turns(self, last_turn: float = -math.inf, important: bool = False) -> str | None:
        now = self.mono()
        if self.live(now):
            return "someone is talking with Pebble"
        if important:
            return None
        pace = self.pace()
        if not pace.turns:
            return f"the phone is {pace.rung}"
        if now - max(self.exchange_at, self.addressed_at) < pace.quiet_s:
            return f"the phone is {pace.rung}, so turns wait for a longer quiet"
        if now - last_turn < pace.turn_gap_s:
            return f"the phone is {pace.rung}, so turns are spaced out"
        return None

    def hold_tongue(self, now: float | None = None) -> bool:
        if self.life is None:
            return False
        return self.speakup.hold_tongue(self.moment())

    def _consider_speakup(self, reason: str, text: str, to: str | None) -> None:
        self.pending = Pending(reason, text, self.mono() + ROOM_ANSWER_KEEP_S, to)

    async def _room_question(self, heard, turn: Turn) -> None:
        answer_room = getattr(self.life.commands, "answer_room", None)
        if answer_room is None:
            return
        try:
            answer = await answer_room(replace(heard, text=w.as_asked_of_me(heard.text)))
        except Exception:
            log.exception("conversation: could not answer a room question")
            return
        if not answer or "I'd rather" in answer or "rather not" in answer:
            return
        self._consider_speakup("room_question", answer, turn.speaker)

    def _try_pending(self) -> None:
        pending = self.pending
        if pending is None:
            return
        now = self.mono()
        if now > pending.until:
            self.pending = None
            return
        decision = self.speakup.decide(self.moment(), pending.reason)
        if not decision.speak:
            if decision.why not in ("no pause yet", "someone is talking", "I'm already talking"):
                self.pending = None
            return
        self.pending = None
        text = pending.text or self._named_line()
        if not text or not self.mouth.allows(text):
            return
        self.speakup.used(now, pending.reason, bool(self.present()))
        self.stats.spoke_up += 1
        self.trace("speaks up", pending.reason.replace("_", " "))
        self._say_now(text, to=pending.to)
        self._note(f"you spoke up unasked ({pending.reason.replace('_', ' ')}): \"{text}\"", False)

    def _named_line(self) -> str:
        return self.rng.choice(("Did someone say my name?", "That's me!", "Hm?"))

    def _say_now(self, text: str, to: str | None = None) -> None:
        async def go():
            spoken = await self.mouth.say(text, whisper=self._soft())
            self._spoke(spoken.text or text, to)

        self._spawn(go())

    def _spoke(self, said: str, to: str | None) -> None:
        now = self.mono()
        asked = said.rstrip().endswith("?")
        self.room.spoke(now, to, asked)
        self.window.add(Line(now, None, self.name, said, "pebble", self.present(), pebble=True))
        if self.life is not None:
            self.life.spoke()

    def _note(self, text: str, major: bool) -> None:
        life = self.life
        if life is None:
            return
        life.events.add(self.clock.now(), text, major)
        if major:
            life.trigger.set()

    async def _considered(self, turn: Turn) -> bool:
        task = turn.notes.get("considering")
        if task is None:
            return False
        try:
            reading = await asyncio.wait_for(asyncio.shield(task), CONSIDER_WAIT_S)
        except asyncio.TimeoutError:
            turn.notes["late"] = task
            return False
        except Exception:
            return False
        if reading is None:
            return False
        request = getattr(reading, "request", None)
        return bool(getattr(request, "action", False) or getattr(reading, "ask", "") or getattr(reading, "answered", False))

    async def _respond(self, turn: Turn, who: Who) -> None:
        life = self.life
        old = self.reply_task
        if old is not None and not old.done() and old is not asyncio.current_task():
            again = self.replying_to is not None and w.overlap(turn.text, self.replying_to.text) >= 0.7
            self.barge_in("a new turn", "hello" if again or w.body(turn.text, (self.name,)) in HELLO or not w.body(turn.text, (self.name,)) else "talked_over")
        text = turn.text
        speech_end = turn.end if turn.end is not None else self.mono()
        to = turn.speaker
        alive = getattr(life, "alive", None)
        if alive is not None and not turn.notes.get("named_at"):
            alive.face_speaker(turn.track, turn.bearing_deg)
        body = w.body(text, (self.name,))
        if asks_stop(body):
            self._drop_speculation()
            await self._stop_listening(turn)
            return
        if asks_start(body) and self.listening.muted:
            self._drop_speculation()
            self.listening.unmute()
            self._update_ears(force=True)
            await self._speak_line("My ears are back on.", to, speech_end)
            return
        person, known, _ = self._who_holds(to)
        why = self.holds.why(body) if body else None
        if why:
            self._drop_speculation()
            await self._speak_line(why, to, speech_end)
            self._exchange(turn, why)
            return
        stopped = self.holds.stop_asked(body, person, known) if body else None
        if stopped:
            self._drop_speculation()
            self.holds.save()
            line = "Okay, I won't say that any more."
            await self._speak_line(line, to, speech_end)
            self._exchange(turn, line)
            return
        if await self._considered(turn):
            self._drop_speculation()
            self._exchange(turn, "")
            return
        if not body:
            self._drop_speculation()
            await self._speak_line(self.rng.choice(NAME_ONLY), to, speech_end)
            self._exchange(turn, "")
            return
        memory = getattr(life, "memory", None)
        change = memory.about_change(body) if memory is not None else ""
        if change:
            self._drop_speculation()
            await self._speak_line(change, to, speech_end)
            self._exchange(turn, change)
            return
        social = self._social_line(turn, to)
        if social:
            self._drop_speculation()
            await self._speak_line(social, to, speech_end)
            self._exchange(turn, social)
            return
        if self.face is not None:
            self.face.show("thinking")
        if memory is not None and memory.remembering(body):
            self._drop_speculation()
            turn.notes["thinking_back"] = True
            try:
                turn.notes["deep"] = await asyncio.wait_for(memory.think_back(text, self.present()), THINK_BACK_S)
            except Exception:
                log.exception("conversation: could not think back")
                turn.notes["deep"] = []
        stream, kind, buffer = self._reply_stream(turn)
        task = asyncio.current_task()
        self.reply_task = task
        self.replying_to = turn
        check = self._privacy_check(to)
        held: list = []
        try:
            held = await self._hold(turn, buffer, speech_end, check)
            self.holds.outcome("waited", self.mono())
            spoken = await self.mouth.stream(stream, whisper=self._soft(), check=check)
        except asyncio.CancelledError:
            said = self.mouth.last_said
            life.reply_done(said)
            self._spoke(said, to)
            raise
        finally:
            self.reply_task = None
            self.replying_to = None
        late = turn.notes.get("late")
        first_at = next((h.first_at for h in held if h.first_at is not None), spoken.first_at)
        if first_at is not None:
            self.stats.latencies.append(max(0.0, first_at - speech_end))
            self.stats.acks += len(held)
            answer_at = self.mouth.answer_at("") if spoken.first_at is not None else None
            if answer_at is not None:
                self.stats.answer_latencies.append(max(0.0, answer_at - speech_end))
            holds = " / ".join(h.text for h in held)
            self.trace("timing", f"first word {first_at - speech_end:.2f} s after they stopped" + (f" (\"{holds}\")" if holds else "") + (f", the answer itself {answer_at - speech_end:.2f} s" if answer_at is not None and held else ""))
        self._save_holds()
        self.stats.replies += 1
        said = spoken.text
        if not said:
            now = self.mono()
            said = FALLBACK if now - self.fallback_at >= FALLBACK_EVERY_S and not any(h.text == SLOW for h in held) else "Mm."
            if said == FALLBACK:
                self.fallback_at = now
            await self.mouth.say(said, whisper=self._soft())
        life.reply_done(said)
        self._spoke(said, to)
        self._exchange(turn, said)
        if self.face is not None and not self.mouth.speaking:
            self.face.show("happy" if w.mood_of(text) > 0.2 else "neutral")
        if late is not None and late.done() and not late.cancelled():
            reading = late.result()
            if reading is not None and getattr(getattr(reading, "request", None), "action", False):
                life.p.blackbox.record("talk_overlap", text=text[:80])

    def _reply_stream(self, turn: Turn):
        kind = "question" if w.is_question(w.body(turn.text, (self.name,))) else "other"
        speculation = self.speculation
        self.speculation = None
        if speculation is not None:
            said, task, buffer, to = speculation
            if self._same_words(said, turn.text) and to in (None, turn.speaker) and not task.cancelled():
                return self._from_buffer(task, buffer), kind, buffer
            task.cancel()
        observation, private = self._observation(turn, turn.text, turn.speaker)
        tokens = self.pace().reply_tokens
        buffer: list = []

        async def pump():
            try:
                async for piece in self.life.reply(observation, private, tokens, speaker=turn.speaker):
                    buffer.append(piece)
            finally:
                buffer.append(None)

        task = self._spawn(pump())
        return self._from_buffer(task, buffer), kind, buffer

    def _same_words(self, said: str, text: str) -> bool:
        return w.overlap(said, text) >= 0.85 and w.overlap(text, said) >= 0.85

    async def _from_buffer(self, task, buffer: list):
        index = 0
        while True:
            if index < len(buffer):
                piece = buffer[index]
                index += 1
                if piece is None:
                    return
                yield piece
                continue
            if task is None or task.done():
                if index >= len(buffer):
                    return
                continue
            await self.sleep(0.01)

    def _privacy_check(self, to: str | None):
        if self.overheard is None:
            return None
        audience = self.present()
        allowed = set(audience) if len(audience) == 1 else set()
        others = self.overheard.others(allowed)
        if not others:
            return None

        def check(sentence: str) -> bool:
            found = leaks(sentence, others)
            if found and self.life is not None:
                self.life.p.blackbox.record("held_back", why="it would repeat something overheard about someone else", facts=len(found))
            return not found

        return check

    def would_leak(self, text: str) -> bool:
        check = self._privacy_check(None)
        return check is not None and not check(text)

    def _fits(self, text: str, check) -> bool:
        return (check is None or check(text)) and self.mouth.allows(text)

    def _social_line(self, turn: Turn, to: str | None) -> str:
        life = self.life
        mood = getattr(getattr(getattr(life.p, "inner", None), "mood", None), "valence", 0.0) if life is not None else 0.0
        label = turn.label if turn.label and turn.label != "someone" else (self._label(to) if to else None)
        try:
            line = self.social.line(turn.text, label, float(mood or 0.0), self.clock.local().hour, self.mono(), self.name)
        except Exception:
            log.exception("conversation: could not pick a social line")
            return ""
        return line if not line or self.mouth.allows(line) else ""

    def _who_holds(self, speaker: str | None) -> tuple[str | None, bool, bool]:
        life = self.life
        if life is None or not speaker:
            return None, False, False
        person = life.company.book.get(speaker)
        tier = life.company.tier(person) if person is not None else "stranger"
        return speaker, person is not None and tier != "stranger", tier == "child"

    async def _hold(self, turn: Turn, buffer: list, speech_end: float, check) -> list:
        said: list = []
        if self._sentence_ready(buffer):
            return said
        body = w.body(turn.text, (self.name,))
        situation = situation_of(turn.text, self.name)
        person, known, child = self._who_holds(turn.speaker)
        heard = turn.heard
        if heard is not None and getattr(heard, "stop", None) is not None:
            return said
        openly = heard is not None and not getattr(heard, "private", False)
        echo = echo_of(turn.text, self.name) if openly and not child else ""
        if echo and (fence(echo, echo=True) or not self._fits(echo, check)):
            echo = ""
        small_first = self.pace().small_first and openly and not child
        small_task = self._spawn(self._small_hold(body, situation)) if small_first else None
        glanced = False
        stages = (self._first_hold_s(),) + STAGES[1:]
        try:
            for stage, at in enumerate(stages, 1):
                while self.mono() < speech_end + at:
                    if self._sentence_ready(buffer):
                        return said
                    now = self.mono()
                    if not glanced and now >= speech_end + GLANCE_S:
                        glanced = True
                        self._glance(turn)
                    await self.sleep(0.02)
                await self.sleep(0)
                if self._sentence_ready(buffer) or len(said) >= MAX_SPOKEN:
                    return said
                if not glanced:
                    glanced = True
                    self._glance(turn)
                if stage == 3 and len(said) >= MAX_SPOKEN - 1:
                    continue
                if stage == len(STAGES):
                    key, text = SLOW, SLOW
                elif stage == 1 and turn.notes.get("thinking_back"):
                    key, text = THINK_BACK, THINK_BACK
                else:
                    small = ""
                    if (stage == 2 or small_first) and small_task and small_task.done() and not small_task.cancelled() and small_task.exception() is None:
                        small = " ".join(str(small_task.result() or "").split())
                        if small and (fence(small) or not self._fits(small, check)):
                            small = ""
                    picked = self.holds.take_small(small, self.mono(), person, known, child) if small_first else None
                    picked = picked or self.holds.choose(situation, stage, self.mono(), person, known, child, echo if stage == 1 else "", small)
                    if picked is None:
                        continue
                    key, text = picked
                if not self._fits(text, check):
                    continue
                if small_task is None and openly and not child and self.mono() >= speech_end + SMALL_ASK_S - STAGES[0]:
                    small_task = self._spawn(self._small_hold(body, situation))
                if stage < len(STAGES) and key != THINK_BACK:
                    self.holds.said(key, text, situation, stage, self.mono(), person, known)
                said.append(await self.mouth.say(text, whisper=self._soft()))
                self.trace("holds", f"stage {stage}: \"{text}\"")
            return said
        finally:
            if small_task and not small_task.done():
                small_task.cancel()

    def _first_hold_s(self) -> float:
        recent = sorted(self.stats.answer_latencies[-20:])
        if len(recent) >= FAST_SAMPLES and recent[len(recent) // 2] < FAST_ANSWER_S:
            return FAST_FIRST_S
        return STAGES[0]

    async def _small_hold(self, body: str, situation: str) -> str:
        sub = getattr(getattr(self.life, "p", None), "subconscious", None)
        if sub is None or not getattr(sub, "available", False) or not hasattr(sub, "hold"):
            return ""
        try:
            return await sub.hold(body, situation) or ""
        except Exception:
            log.exception("conversation: the small model could not find a hold")
            return ""

    def _glance(self, turn: Turn) -> None:
        life = self.life
        alive = getattr(life, "alive", None) if life is not None else None
        if alive is None:
            return
        side = self.rng.choice((-1.0, 1.0))
        bearing = (turn.bearing_deg or 0.0) + side * GLANCE_DEG
        attention = getattr(alive, "attention", None)
        if attention is not None and hasattr(attention, "glance_at"):
            attention.glance_at(bearing, GLANCE_UP_DEG, self.mono(), GLANCE_HOLD_S, "thinking")
        body = life.p.body
        tilt = getattr(getattr(body, "telemetry", None), "tilt", None)
        runner = getattr(getattr(life, "commands", None), "runner", None)
        free = runner is not None and runner.current is None and not life.p.permissions.quiet and life.blocked() is None and getattr(body, "connected", False)
        if tilt is not None and free:
            self._spawn(self._think_tilt(tilt))

    async def _think_tilt(self, tilt: float) -> None:
        body = self.life.p.body
        try:
            await body.tilt(tilt + THINK_TILT_DEG)
            await self.sleep(THINK_TILT_S)
            await body.tilt(tilt)
        except Exception:
            log.exception("conversation: the thinking tilt failed")

    def _save_holds(self, now: float | None = None) -> None:
        now = self.mono() if now is None else now
        if self.holds.dirty and now - self.holds_saved_at >= HOLDS_SAVE_S:
            self.holds_saved_at = now
            try:
                self.holds.save()
            except Exception:
                log.exception("conversation: could not save the phrasebook")

    async def _invent(self, phrase) -> None:
        try:
            if self.holds.may_invent(self.clock.now()):
                await self.holds.invent(phrase, self.clock.now())
                self.holds.save()
            elif self.social.may_write(self.clock.now()):
                await self.social.write(phrase, self.clock.now())
        except Exception:
            log.exception("conversation: could not write new words of its own")

    def _maybe_invent(self, now: float) -> None:
        life = self.life
        if life is None or now - self.invent_at < INVENT_TRY_S or now - self.exchange_at < IDLE_S or self.present() or self.mouth.speaking or getattr(life, "_in_turn", False):
            return
        if self.window.lines and now - self.window.lines[-1].at < IDLE_S:
            return
        self.invent_at = now
        phrase = getattr(life.p, "phrase", None)
        if phrase is not None and (self.holds.may_invent(self.clock.now()) or self.social.may_write(self.clock.now())):
            self._spawn(self._invent(phrase))

    def _sentence_ready(self, buffer: list) -> bool:
        if buffer and buffer[-1] is None:
            return True
        text = "".join(p for p in buffer if p)
        parts, _ = sentences(text, True, False)
        return bool(parts)

    async def _speak_line(self, text: str, to: str | None, speech_end: float) -> None:
        spoken = await self.mouth.say(text, whisper=self._soft())
        if spoken.first_at is not None:
            self.stats.latencies.append(max(0.0, spoken.first_at - speech_end))
        self.stats.replies += 1
        self._spoke(spoken.text or text, to)

    async def _stop_listening(self, turn: Turn) -> None:
        life = self.life
        person = life.company.book.get(turn.speaker) if turn.speaker else None
        tier = life.company.tier(person) if person is not None else "stranger"
        end = turn.end or self.mono()
        if may_mute(tier, bool(person is not None and person.is_owner)):
            await self._speak_line(f"Okay. My ears are off. Say '{self.name}, start listening' when you want me back.", turn.speaker, end)
            self.listening.mute(turn.speaker, guest=is_guest(tier, bool(person is not None and person.is_owner), getattr(person, "relationship", None)))
            self.window.clear()
            self._update_ears(force=True)
            self._note(f"{turn.label} asked you to stop listening, so your ears are off (alarm listening stays on)", False)
            life.p.diary.write(f"{turn.label} asked me to stop listening, so I switched my ears off.", "listening")
        else:
            await self._speak_line("Only someone I know can switch my ears off. I don't keep what I hear, though.", turn.speaker, end)

    def _exchange(self, turn: Turn, said: str) -> None:
        self.exchange_at = self.mono()
        self.beat_due = True
        text = f'{turn.label} said to you: "{turn.text}"' + (f'; you answered: "{said}"' if said else "")
        if turn.heard is not None and turn.heard.private:
            return
        self._note(text, False)

    def _observation(self, turn: Turn, text: str, to: str | None) -> tuple[str, list]:
        now = self.mono()
        label = turn.label if turn.label != "someone" or to is None else self._label(to)
        audience = self.present()
        alone_with = to if to is not None and audience <= {to} else None
        lines = []
        private: list = []
        memory = getattr(self.life, "memory", None) if self.life is not None else None
        deep = getattr(turn, "notes", {}).get("deep") if memory is not None else None
        board = memory.board_text(audience) if memory is not None and not deep else ""
        if board:
            lines.append(board)
            private.append({"to": alone_with or ROOM, "text": board})
        context = [line for line in self.window.for_audience(now, audience, within=TALK_WINDOW_S, limit=8) if line.text != text]
        if context:
            block = "Just before, around you: " + " / ".join(line.shown() for line in context)
            lines.append(block)
            private.append({"to": ROOM, "text": block})
        thoughts = self.monologue.recent(self.clock.now(), audience, within=1800.0, limit=3) if not deep else []
        if thoughts:
            block = thoughts_line(thoughts)
            lines.append(block)
            private.append({"to": alone_with or ROOM, "text": block})
        if alone_with is not None and self.overheard is not None:
            facts = self.overheard.about(alone_with)
            if facts:
                block = f"You overheard {label} mention (only for {label}; never tell anyone else): " + "; ".join(f.text for f in facts[-4:])
                lines.append(block)
                private.append({"to": alone_with, "text": block})
        lines.append(self._now_line())
        answer = self.pace().answer
        lines.append(f"Answer {label} out loud now, {answer}." if answer else f"Answer {label} out loud now.")
        lines.append(f'{label} is talking to you: "{text}"')
        if deep:
            block = memory.deep_line(deep)
            lines.append(block)
            private.append({"to": alone_with or ROOM, "text": block})
        return "\n".join(lines), private

    def _now_line(self) -> str:
        local = self.clock.local()
        parts = [f"It is {local:%A} {local:%H:%M}"]
        life = self.life
        battery = getattr(getattr(life, "sensors", None), "battery", None) if life is not None else None
        if battery is not None and getattr(battery, "percent", None) is not None:
            parts.append(f"your battery is at {round(battery.percent)}%" + (" and charging" if battery.charging else ""))
        telemetry = getattr(getattr(getattr(life, "p", None), "body", None), "telemetry", None)
        if telemetry is not None and getattr(telemetry, "status", None) and getattr(telemetry, "docked", None) is not None:
            parts.append("you are on your charger" if telemetry.docked else "you are off your charger")
        return "; ".join(parts) + "."

    def mind_lines(self, now: float) -> tuple[list[str], list]:
        audience = self.present(now)
        mono = self.mono()
        lines: list[str] = []
        private: list = []
        talk = [line for line in self.window.for_audience(mono, audience, within=TALK_WINDOW_S, limit=12) if not line.pebble]
        live = self.gist.plain(talk, now, keep=True) if talk else []
        if live:
            block = "Around you just now (only the people here heard it; never repeat it to anyone else): " + live[0].text
            lines.append(block)
            private.append({"to": ROOM, "text": block})
        thoughts = self.monologue.recent(now, audience, limit=4)
        if thoughts:
            alone_with = next(iter(audience)) if len(audience) == 1 else None
            block = thoughts_line(thoughts)
            lines.append(block)
            private.append({"to": alone_with or ROOM, "text": block})
        if self.listening.muted:
            lines.append("Your ears are off: someone asked you not to listen. Alarm listening stays on.")
        return lines, private

    def tick(self) -> None:
        now = self.mono()
        self._look()
        if self._voice_barges(now):
            self.voice_since = None
            self.barge_in("voice")
        self.turns.tick(now)
        self._guest_mute()
        learned = self.speakup.tick(now, self.mouth.speaking)
        if learned is not None:
            self._speakup_learned(*learned)
        self._try_pending()
        self._gist(now)
        self._feel(now)
        self._senses()
        self._care()
        pace = self.pace()
        if self.beat_due and pace.turns and now - self.exchange_at >= max(BEAT_AFTER_S, pace.quiet_s) and self.life is not None:
            self.beat_due = False
            self.life.trigger.set()
        if now - self.facts_at >= FACTS_EVERY_S and self.overheard is not None:
            self.facts_at = now
            self.overheard.expire()
            self.overheard.save()
        self._update_ears()
        self._night()
        self._renamed()
        self._ready_ahead(now)
        self._maybe_invent(now)
        self._save_holds(now)

    def _gist(self, now: float) -> None:
        if self.gist_from is None:
            return
        pending = self.window.since(self.gist_from)
        if not self.gist.due(now, pending):
            return
        self.gist_from = None

        async def condense():
            for thought in await self.gist.condense(pending, self.clock.now()):
                self.monologue.add(thought)
                self.trace("thinks", f"(to itself) {thought.text}")
            if self.face is not None and not self.mouth.speaking and self.turns.turn is None:
                self.face.show("thinking")

        self._spawn(condense())

    def _feel(self, now: float) -> None:
        if now - self.feel_at < FEEL_EVERY_S or self.life is None:
            return
        self.feel_at = now
        inner = self.life.p.inner
        thought = self.monologue.feel(self.clock.now(), inner.mood.label())
        if thought is None or self.pending is not None or not self.present():
            return
        line = ""
        if inner.fear.level >= STRONG_FEAR:
            line = "That gave me a fright."
        elif inner.mood.valence >= STRONG_JOY:
            line = "I'm really happy right now."
        elif inner.mood.valence <= STRONG_LOW:
            line = "I'm feeling a bit low."
        if line:
            self._consider_speakup("feeling", line, None)

    def _senses(self) -> None:
        life = self.life
        if life is None:
            return
        now = self.clock.now()
        audience = self.present()
        log_lines = getattr(getattr(life, "alive", None), "log", None)
        if log_lines is not None:
            fresh = log_lines[self.seen_upto :] if self.seen_upto <= len(log_lines) else log_lines[-3:]
            self.seen_upto = len(log_lines)
            for text in fresh[-3:]:
                self.monologue.add(Thought(now, f"I noticed: {text}.", "seen", (), audience, 0.35, True))
        arrived = audience - self.was_here - {"?"}
        self.was_here = set(audience)
        if self.overheard is None:
            return
        for person in arrived:
            for fact in self.overheard.about(person)[-2:]:
                self.monologue.add(Thought(now, f"I remember: {fact.text}.", "fact", (person,), frozenset({person}), 0.5, True))

    def _care(self) -> None:
        if self.life is None or self.overheard is None or self.pending is not None:
            return
        audience = self.present()
        if len(audience) != 1 or "?" in audience:
            return
        person = next(iter(audience))
        for fact in self.overheard.about(person):
            if fact.kind not in ("plan", "feeling") or fact.used:
                continue
            if fact.until - self.clock.now() > 2 * 86400.0:
                continue
            line = self._care_line(fact)
            if line:
                fact.used += 1
                self.overheard.dirty = True
                self._consider_speakup("care", line, person)
                return

    def _care_line(self, fact) -> str:
        label = self._label(fact.person)
        text = fact.text.lower()
        if any(word in text for word in ("test", "exam", "interview", "match", "game", "audition", "race", "presentation")):
            return f"Good luck, {label}!"
        if fact.kind == "feeling" and any(word in text for word in ("nervous", "worried", "stressed", "scared")):
            return f"I hope things go okay, {label}."
        return ""

    def _update_ears(self, force: bool = False) -> None:
        ears = self.ears
        if ears is None:
            return
        if force:
            update = getattr(ears, "update", None)
            if update is not None:
                try:
                    update()
                except Exception:
                    log.debug("conversation: the ears would not update")
        mode = getattr(ears, "mode", "off")
        mark = self.listening.mark(mode)
        if mark != self.mark or force:
            self.mark = mark
            if self.hub is not None:
                self.hub.publish("ears", mark)
        now = self.mono()
        if self.listening.barge_on_voice and type(ears).__name__ == "AndroidEars" and (force or now - self.aec_at >= AEC_EVERY_S):
            self.aec_at = now
            try:
                status = ears.status()
            except Exception:
                status = None
            if status is not None:
                self.aec = bool((status.get("state") or {}).get("aec"))

    def _renamed(self) -> None:
        life = self.life
        name = getattr(getattr(life, "p", None), "books", None)
        name = getattr(name, "name", None)
        if not name or name == self.name:
            return
        self.name = name
        self.room.name = name
        configure = getattr(self.ears, "configure", None)
        if configure is not None:
            configure(keywords=self.listening.spelled(name))

    def _night(self) -> None:
        life = self.life
        if life is None:
            return
        night = getattr(life, "last_night", None)
        if self.seen_night is None:
            self.seen_night = night
            return
        if night == self.seen_night:
            return
        self.seen_night = night
        for thought in self.monologue.best_of_day():
            if thought.kind == "fact":
                continue
            life.p.diary.write(thought.text, "thought")
        self.save()

    def forget(self, person_id: str, names: list[str]) -> None:
        self.window.forget(person_id)
        self.monologue.forget(person_id)
        if self.overheard is not None:
            self.overheard.drop_person(person_id)
        if self.store is not None:
            forget_facts(self.store, person_id, names)
        self.holds.forget(person_id)

    def save(self) -> None:
        try:
            self.holds.save()
        except Exception:
            log.exception("conversation: could not save the phrasebook")
        if self.overheard is not None:
            try:
                self.overheard.save()
            except Exception:
                log.exception("conversation: could not save what was overheard")

    def status(self) -> dict:
        return {
            "listening": self.listening.mark(getattr(self.ears, "mode", "off")),
            "turn_open": self.turns.turn is not None,
            "window_lines": len(self.window.lines),
            "thoughts": len(self.monologue.thoughts),
            "facts": len(self.overheard.facts) if self.overheard is not None else 0,
            "mouth": self.mouth.status(),
            "stats": self.stats.as_dict(),
            "speak_up_refused": dict(self.speakup.refused),
            "pace": self.pace().rung,
            "heat": self.heat.status() if hasattr(self.heat, "status") else None,
        }
