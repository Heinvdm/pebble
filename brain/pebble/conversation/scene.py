import argparse
import asyncio
import math
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from ..mind.base import MindReply
from ..mind.scripted import ScriptedMind
from ..people.trust import FRIEND, TRUSTED
from ..sim.scene import Scene, Who, household
from ..sim.world import SimThing
from .core import Conversation
from .scripted import Said, ScriptedSpeech

INA = (1300.0, 420.0)
SAM = (1450.0, -480.0)
REPLIES = [
    "I think the beach sounds lovely. Sam should bring the sunscreen, though. And maybe a hat.",
    "Sunday works too. The beach will still be there.",
]


class SlowMind(ScriptedMind):
    def __init__(self, sleep, first_s: float, per_s: float, **kwargs):
        super().__init__(**kwargs)
        self.sleep = sleep
        self.first_s = first_s
        self.per_s = per_s

    async def stream(self, messages, purpose="turn", max_tokens=None, options=None, tools=None):
        reply = await self.chat(messages, tools, purpose, max_tokens, options)
        await self.sleep(self.first_s)
        for word in (reply.text or "").split(" "):
            yield word + " "
            await self.sleep(1.0 / self.per_s)


class TracingFace:
    def __init__(self, inner, trace):
        self.inner = inner
        self.trace = trace
        self.last = None

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def show(self, expression: str) -> None:
        if expression != self.last:
            self.last = expression
            self.trace("face", expression)
        self.inner.show(expression)


class ConversationScene:
    def __init__(self, root: Path, echo: bool = False, first_s: float = 1.8, per_s: float = 8.0, aec: bool = True, turn_end: float | None = None):
        things = household() + [SimThing("remote", 2000.0, 1000.0, width_mm=180.0, depth_mm=50.0, height_mm=30.0, fast="remote control", slow="remote control", track=107)]
        self.scene = Scene(root, people=[Who("Ina", TRUSTED, *INA), Who("Sam", FRIEND, *SAM)], echo=echo, things=things)
        self.conversation: Conversation | None = None
        self.first_s = first_s
        self.per_s = per_s
        self.aec = aec
        self.turn_end = turn_end
        self.speech = ScriptedSpeech()
        self.talking: dict[str, tuple[float, float]] = {}

    @property
    def life(self):
        return self.scene.life

    def trace(self, what: str, text: str) -> None:
        self.scene.trace(what, text)

    async def setup(self) -> None:
        scene = self.scene
        await scene.setup()
        life = scene.life
        pace = scene.time
        face = TracingFace(life.p.face, self.trace)
        conv = Conversation(scene.clock, scene.store, scene.books, life.p.voice, face, life.p.rng, sleep=pace.sleep)
        self.conversation = conv
        life.p.conversation = conv
        life.overnight.forgetters.append(conv.forget)
        conv.trace = self.trace
        conv.aec = self.aec
        mind = SlowMind(pace.sleep, self.first_s, self.per_s, acts=[], replies=list(REPLIES))
        life.p.turns.mind = mind
        life.p.mind = mind
        life._mind_ready = True
        conv.attach(life)
        self._patch_eyes()
        self._patch_alive()
        self.runner = asyncio.ensure_future(conv.run())
        await scene.run(4.0)

    def _patch_eyes(self) -> None:
        eyes = self.scene.eyes
        latest = eyes.latest
        clock = self.scene.clock

        def patched(max_age_s: float = 0.5):
            sight = latest(max_age_s)
            if sight is None:
                return None
            now = clock.monotonic()
            names = {1: "ina", 2: "sam"}
            people = []
            for person in sight.people:
                who = names.get(person.track)
                window = self.talking.get(who)
                talking = window is not None and window[0] <= now <= window[1] + 0.3
                people.append(replace(person, speaking=0.85 if talking else 0.05))
            return replace(sight, people=tuple(people))

        eyes.latest = patched

    def _patch_alive(self) -> None:
        alive = self.life.alive
        trace = self.trace
        face_speaker, speaking, nod = alive.face_speaker, alive.speaking, alive.nod
        names = {1: "Ina", 2: "Sam", None: "the voice"}

        def traced_face(track=None, bearing_deg=None):
            trace("turns", f"eyes, then head, to {names.get(track, 'someone')}")
            return face_speaker(track, bearing_deg)

        def traced_speaking(track=None, bearing_deg=None):
            trace("looks", f"at {names.get(track, 'someone')}")
            return speaking(track, bearing_deg)

        def traced_nod():
            done = nod()
            trace("nods", "a small nod" if done else "(would nod; the head is busy)")
            return done

        alive.face_speaker, alive.speaking, alive.nod = traced_face, traced_speaking, traced_nod

    def face(self, who: str, look: str) -> None:
        world = self.scene.world
        person = world.person(who)
        if look == "me":
            person.facing = None
            return
        other = world.person("sam" if who == "ina" else "ina")
        person.facing = math.atan2(other.y - person.y, other.x - person.x)

    async def say(self, who: str, text: str, look: str = "other", gap: float = 0.0, level_db: float = -24.0) -> None:
        scene = self.scene
        if gap:
            await scene.run(gap)
        self.face(who, look)
        start = scene.clock.monotonic() + 0.05
        events, end = self.speech.events(Said(who, text, level_db, self.turn_end), start, speaking=self.conversation.mouth.speaking)
        self.talking[who] = (start, end)
        scene.trace("hears", f'{who.title()} ({"to Pebble" if look == "me" else "to " + ("Sam" if who == "ina" else "Ina")}): "{text}"')
        for event in events:
            await scene.time.run_until(event.t)
            if self.conversation.mouth.speaking and event.kind in ("voice_start", "partial", "final"):
                event = replace(event, pebble_speaking=True)
            self.conversation.on_speech(event)

    async def run(self, seconds: float) -> None:
        await self.scene.run(seconds)

    def leave(self, who: str) -> None:
        self.scene.leave(who.title())

    async def close(self) -> None:
        self.runner.cancel()
        await asyncio.gather(self.runner, return_exceptions=True)
        await self.scene.close()


async def ina_and_sam(play: ConversationScene) -> None:
    await play.say("ina", "so are we still going to the beach on saturday", "other")
    await play.say("sam", "if the weather holds yeah", "other", gap=0.5)
    await play.say("ina", "i have my driving test on friday so saturday is perfect", "other", gap=0.6)
    await play.say("sam", "you'll smash it haha", "other", gap=0.5)
    await play.say("ina", "haha thanks", "other", gap=0.4)
    await play.say("sam", "pebble's been so good today", "other", gap=1.0)
    await play.say("ina", "it has", "other", gap=0.5)
    await play.run(2.0)
    await play.say("ina", "has anyone seen the remote", "other", gap=0.5)
    await play.run(4.0)
    await play.say("sam", "found it thanks", "other", gap=0.3)
    await play.run(1.5)
    await play.say("ina", "Pebble, what do you think?", "me", gap=1.0)
    await play.run(3.4)
    await play.say("ina", "oh wait actually we might go sunday", "me")
    await play.run(8.0)
    play.leave("sam")
    await play.run(140.0)


SCENES = {"ina_and_sam": ina_and_sam}


async def play(name: str = "ina_and_sam", root: Path | None = None, echo: bool = False, first_s: float = 1.8, per_s: float = 8.0, turn_end: float | None = None) -> ConversationScene:
    owned = None
    if root is None:
        owned = tempfile.TemporaryDirectory(prefix="pebble-talk-")
        root = Path(owned.name) / "self"
    show = ConversationScene(root, echo=echo, first_s=first_s, per_s=per_s, turn_end=turn_end)
    await show.setup()
    try:
        await SCENES[name](show)
    finally:
        await show.close()
        show.stats = show.conversation.stats.as_dict()
        if owned is not None:
            owned.cleanup()
    return show


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.conversation.scene", description="Ina and Sam chat near Pebble: it listens, reacts, answers a question to the room, replies fast when asked, and stops when talked over.")
    parser.add_argument("--scene", choices=sorted(SCENES), default="ina_and_sam")
    parser.add_argument("--first", type=float, default=1.8, help="seconds before the model's first word (the phone's main model)")
    parser.add_argument("--rate", type=float, default=8.0, help="the model's words per second after that")
    parser.add_argument("--turn-score", type=float, default=None, help="the phone's end-of-turn score for the end of every line (0 to 1); leave out for no end-of-turn model")
    args = parser.parse_args(argv)
    show = asyncio.run(play(args.scene, echo=True, first_s=args.first, per_s=args.rate, turn_end=args.turn_score))
    print()
    for key, value in show.stats.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
