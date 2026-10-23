import argparse
import asyncio
import json
import re
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path

from ..alive.rooms import Room
from ..mind.base import Mind, MindReply
from ..people.fake import fake_print
from ..people.trust import CHILD, FRIEND, INNER, TRUSTED
from ..safety.scene import SafetyScene, alarm_in_another_room
from ..sim.scene import Scene, Who, household
from ..understand.model import ModelReader
from ..understand.understanding import Understanding
from ..teach.scene import TEACHING
from .later import Later
from .trying_scene import TRYING

HEARD = re.compile(r'Heard: "(.*)"\s*$', re.S)
SKIP_STEP_S = 540.0
NEAR_STEP_S = 20.0
SAVE_EVERY_S = 6 * 3600.0
HOUR = timedelta(hours=1)
ROOMS = {"lounge": (2.5, 0.0, 1.4), "bathroom": (6.5, 1.9, 1.0), "bedroom": (6.5, -1.9, 1.0), "kitchen": (4.2, 2.2, 0.9)}
STUDY = {**ROOMS, "study": (4.2, -2.2, 0.9)}
SIZE = (8000.0, 6000.0)


class NewZealand(tzinfo):
    def _sundays(self, year: int) -> tuple[int, int]:
        first_april = next(d for d in range(1, 8) if date(year, 4, d).weekday() == 6)
        last_september = next(d for d in range(30, 23, -1) if date(year, 9, d).weekday() == 6)
        return first_april, last_september

    def utcoffset(self, dt):
        ends, starts = self._sundays(dt.year)
        wall = dt.replace(tzinfo=None, fold=0)
        edge = 2 if dt.fold else 3
        summer = wall < datetime(dt.year, 4, ends, edge) or wall >= datetime(dt.year, 9, starts, edge)
        return timedelta(hours=13 if summer else 12)

    def dst(self, dt):
        return self.utcoffset(dt) - timedelta(hours=12)

    def tzname(self, dt):
        return "NZDT" if self.dst(dt) else "NZST"

    def fromutc(self, dt):
        utc = dt.replace(tzinfo=None)
        ends, starts = self._sundays(utc.year)
        winter_from = datetime(utc.year, 4, ends, 14) - timedelta(days=1)
        summer_from = datetime(utc.year, 9, starts, 14) - timedelta(days=1)
        summer = utc < winter_from or utc >= summer_from
        fold = 1 if winter_from <= utc < winter_from + HOUR else 0
        return (utc + timedelta(hours=13 if summer else 12)).replace(tzinfo=self, fold=fold)


NZ = NewZealand()


class CannedReader(Mind):
    def __init__(self, readings: dict):
        self.readings = {self.key(text): reading for text, reading in readings.items()}
        self.calls = 0

    @staticmethod
    def key(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9']+", text.lower()))

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        self.calls += 1
        found = HEARD.search(messages[-1]["content"])
        reading = self.readings.get(self.key(found.group(1)) if found else "")
        return MindReply(json.dumps(reading) if reading is not None else '{"kind":"chat"}')

    async def warm(self, messages, tools=None, purpose="warm"):
        return True


def canned(readings: dict) -> Understanding:
    return Understanding(ModelReader([("conscious", CannedReader(readings))]))


class LaterScene:
    def __init__(self, root: Path, people: list, at: datetime, readings: dict, echo: bool = False, rooms: bool = False):
        self.scene = Scene(root, people=people, echo=echo, things=household(), at=at, understanding=canned(readings), size=SIZE if rooms else None, start=(2000.0, 0.0, 0.0) if rooms else (80.5, 0.0, 0.0))
        self.rooms = rooms

    @property
    def life(self):
        return self.scene.life

    @property
    def later(self):
        return self.scene.life.later

    def local(self) -> datetime:
        return self.scene.clock.local()

    async def setup(self) -> None:
        scene = self.scene
        if self.rooms:
            meet = scene._meet

            def met() -> None:
                meet()
                for name, (x, y, r) in (self.rooms if isinstance(self.rooms, dict) else ROOMS).items():
                    scene.life.alive.rooms.rooms[name] = Room(name, x, y, r, (), 0.9)

            scene._meet = met
        await scene.setup()
        scene.life.s.save_every_s = SAVE_EVERY_S
        scene.life.later.agenda.every = SAVE_EVERY_S

    def seen(self) -> None:
        for person in self.scene.world.people:
            if person.home:
                self.life.see(fake_print(person.name, "face"))

    async def skip(self, seconds: float, step: float = SKIP_STEP_S) -> None:
        scene = self.scene
        end = scene.clock.monotonic() + seconds
        while scene.clock.monotonic() < end - 1e-6:
            gap = min(step, end - scene.clock.monotonic())
            scene.clock.advance(gap)
            self.seen()
            await scene.time.run_until(scene.clock.monotonic())
            await scene.time.settle()

    async def skip_to(self, when: datetime, step: float = SKIP_STEP_S) -> None:
        target = when.timestamp()
        while self.scene.clock.now() < target - NEAR_STEP_S * 2:
            left = target - self.scene.clock.now()
            await self.skip(min(left - NEAR_STEP_S, step * 12), step)
        left = target - self.scene.clock.now()
        if left > 0:
            await self.skip(left, NEAR_STEP_S)

    def trace(self, text: str) -> None:
        self.scene.trace("sim", text)

    def records(self) -> list[dict]:
        path = self.scene.store.path("logs/blackbox.jsonl")
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def said(self) -> list[str]:
        return [line.split('says     "', 1)[1].rstrip('"') for line in self.scene.lines if 'says     "' in line]

    async def close(self) -> None:
        await self.scene.close()


BIN = {"kind": "say_to", "who": "me", "text": "tuesday is bin day", "when": {"days": ["mon"], "part": "night"}}
NOT_HOME = {"kind": "if", "when": {"at": "18:00"}, "if": {"not": {"state": "present", "who": "ina"}}, "then": [{"kind": "say_to", "who": "me", "text": "call ina"}]}
LOUNGE_AT_FIVE = {"kind": "go_to_place", "place": "lounge", "when": {"at": "17:00"}}
READINGS = {
    "Remind me every Monday night that Tuesday is bin day.": BIN,
    "Remind me in ten minutes to take the washing out.": {"kind": "say_to", "who": "me", "text": "take the washing out", "when": {"in_s": 600}},
    "Remind me in ten minutes to turn the oven off.": {"kind": "say_to", "who": "me", "text": "turn the oven off", "when": {"in_s": 600}},
    "Wake me up at half past six.": {"kind": "say_to", "who": "me", "text": "wake up", "when": {"at": "06:30"}},
    "Every hour tonight have a look round the house.": {"kind": "check", "place": "house", "when": {"every_s": 3600, "from": "19:00", "to": "20:00"}},
    "When Ina gets home, remind me to call the plumber.": {"kind": "say_to", "who": "me", "text": "call the plumber", "on": {"event": "arrives", "who": "ina"}},
    "If Ina's not home by six, remind me to call her.": NOT_HOME,
    "Remind me at seven or when Ina gets home, whichever comes first.": {"kind": "say_to", "who": "me", "text": "ring the plumber", "on": {"first_of": [{"event": "at", "at": "19:00"}, {"event": "arrives", "who": "ina"}]}},
    "Once you've checked the door, and only if nobody's in the lounge, do your patrol.": {"kind": "check", "thing": "door", "then": [{"kind": "if", "if": {"not": {"state": "in_room", "place": "lounge"}}, "then": [{"kind": "check", "place": "house"}]}]},
    "If nobody's in the kitchen, go to the kitchen.": {"kind": "if", "if": {"not": {"state": "in_room", "place": "kitchen"}}, "then": [{"kind": "go_to_place", "place": "kitchen"}]},
    "Go check the back door, and if it's open come and tell me, otherwise go back to your charger.": {"kind": "check", "thing": "back door", "then": [{"kind": "if", "if": {"state": "result", "is": "yes"}, "then": [{"kind": "come", "who": "me"}, {"kind": "say_to", "who": "me", "text": "the back door is open"}], "else": [{"kind": "go_home"}]}]},
    "Follow me until you see the cat.": {"kind": "follow", "who": "me", "until": {"event": "seen", "thing": "cat"}},
    "Follow me.": {"kind": "follow", "who": "me"},
    "At eight, remind me to feed the cat.": {"kind": "say_to", "who": "me", "text": "feed the cat", "when": {"at": "20:00"}},
    "At eight, remind me to take my tablets.": {"kind": "say_to", "who": "me", "text": "take my tablets", "when": {"at": "20:00"}},
    "At five, come to the lounge.": LOUNGE_AT_FIVE,
    "At half past two, remind me to check the oven.": {"kind": "say_to", "who": "me", "text": "check the oven", "when": {"at": "02:30"}},
    "At seven, remind me to put the bins out.": {"kind": "say_to", "who": "me", "text": "put the bins out", "when": {"at": "19:00"}},
    "When Mo gets home, remind me to ask about school.": {"kind": "say_to", "who": "me", "text": "ask mo about school", "on": {"event": "arrives", "who": "mo"}},
    "When Sam gets home, remind me to ask about the bus.": {"kind": "say_to", "who": "me", "text": "ask sam about the bus", "on": {"event": "arrives", "who": "sam"}},
    "Follow me until I've had enough.": {"kind": "follow", "who": "me", "until": "asked"},
    "Wait here while it's before five past three.": {"kind": "wait", "while": {"state": "before", "at": "15:05"}},
    "At nine, remind me to feed the cat.": {"kind": "say_to", "who": "me", "text": "feed the cat", "when": {"at": "21:00"}},
    "Cancel my reminder.": {"kind": "cancel_later"},
    "When Ina gets home tell her dinner's ready.": {"kind": "say_to", "who": "ina", "text": "dinner's ready", "on": {"event": "arrives", "who": "ina"}},
    "Remind Sam to feed the dog at five.": {"kind": "say_to", "who": "sam", "text": "feed the dog", "when": {"at": "17:00"}},
    "Remind Sam to brush his teeth at six.": {"kind": "say_to", "who": "sam", "text": "brush your teeth", "when": {"at": "18:00"}},
    "Tell Sam the doctor phoned about his tablets.": {"kind": "say_to", "who": "sam", "text": "the doctor phoned about your tablets"},
    "Don't go in the kitchen while I'm cooking.": {"kind": "set_rule", "rule": "keep_out", "place": "kitchen", "while": {"state": "cooking"}},
}


def who(name: str, tier: str | None, x: float = 1300.0, y: float = 0.0) -> Who:
    return Who(name, tier, x, y)


async def bin_day(play: LaterScene) -> dict:
    scene = play.scene
    out = {}
    await scene.say("Ina", "Remind me every Monday night that Tuesday is bin day.")
    await scene.run(5.0)
    await scene.say("Ina", "Make it eight.")
    await scene.run(2.0)
    item = play.later.agenda.waiting()[0]
    out["at"] = play.later.agenda.local(item.next_at).strftime("%a %d %H:%M")
    await play.skip_to(datetime(2027, 12, 27, 19, 45, tzinfo=timezone.utc))
    scene.leave("Ina")
    play.trace("Ina is out of the room on Monday night")
    await play.skip_to(datetime(2027, 12, 27, 20, 40, tzinfo=timezone.utc), NEAR_STEP_S)
    out["while_out"] = len(play.said())
    scene.arrive("Ina", 1.3, 0.0)
    play.seen()
    await scene.run(5.0)
    await scene.say("Ina", "No bin reminder next week.")
    await scene.run(2.0)
    out["next"] = play.later.agenda.local(item.next_at).strftime("%a %d %b %H:%M")
    before = len(play.said())
    await play.skip_to(datetime(2028, 1, 3, 20, 30, tzinfo=timezone.utc))
    out["skipped_week"] = play.said()[before:]
    out["said"] = play.said()
    return out


async def ten_minutes(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Ina", "Remind me in ten minutes to take the washing out.")
    await scene.run(2.0)
    await play.skip(560.0, NEAR_STEP_S)
    before = list(play.said())
    await play.skip(60.0, 5.0)
    return {"before": before, "said": play.said()}


async def wake_up(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Ina", "Wake me up at half past six.")
    await scene.run(2.0)
    await play.skip_to(datetime(2026, 10, 22, 6, 29, tzinfo=timezone.utc))
    quiet = play.life.quiet_hours.contains(play.local())
    await play.skip(240.0, 10.0)
    tries = list(play.said())
    await scene.say("Ina", "I'm up, I'm up.")
    await play.skip(300.0, 10.0)
    return {"tries": tries, "said": play.said(), "quiet": quiet}


async def patrol(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Ina", "Every hour tonight have a look round the house.")
    await scene.run(2.0)
    rounds = []
    for hour in (19, 20):
        await play.skip_to(datetime(2026, 10, 21, hour, 0, 30, tzinfo=timezone.utc), NEAR_STEP_S)
        await scene.until_idle(900.0, 5.0)
        found = [ending.text for activity, ending in scene.life.commands.runner.history if activity.kind == "check"]
        rounds.append(found[-1] if found else "")
    return {"rounds": rounds, "said": play.said(), "left": len(play.later.agenda.waiting())}


async def trigger(play: LaterScene) -> dict:
    scene = play.scene
    scene.leave("Ina")
    await play.skip(700.0, 100.0)
    await scene.say("Mo", "When Ina gets home, remind me to call the plumber.")
    await scene.run(2.0)
    await play.skip(1800.0, 100.0)
    before = list(play.said())
    scene.arrive("Ina", 1.5, 0.4)
    play.seen()
    await scene.run(6.0)
    return {"before": before, "said": play.said()}


async def two_at_once(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Ina", "At eight, remind me to feed the cat.")
    await scene.run(5.0)
    await scene.say("Ina", "Remind me every Monday night that Tuesday is bin day.")
    await scene.run(5.0)
    await scene.say("Ina", "Make it eight.")
    await scene.run(2.0)
    await play.skip_to(datetime(2026, 10, 26, 20, 1, tzinfo=timezone.utc), 600.0)
    await scene.run(5.0)
    return {"said": play.said()}


async def while_following(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Ina", "Remind me in ten minutes to turn the oven off.")
    await scene.run(2.0)
    await play.skip(570.0, NEAR_STEP_S)
    await scene.say("Ina", "Follow me.")
    await scene.run(3.0)
    scene.walk("Ina", (2.2, 0.4), speed_mm_s=40.0)
    await scene.run(40.0)
    current = scene.life.commands.runner.current
    return {"said": play.said(), "following": current is not None and current.kind == "follow"}


async def logic(play: LaterScene) -> dict:
    scene = play.scene
    out = {}
    cat = scene.world.thing("cat")
    cat.home = False
    remember(play, door=(1.4, -0.9), back_door=(1.4, 0.9))
    await scene.say("Mo", "Once you've checked the door, and only if nobody's in the lounge, do your patrol.")
    await scene.run(5.0)
    await scene.until_idle(120.0)
    await scene.say("Mo", "If nobody's in the kitchen, go to the kitchen.")
    await scene.run(5.0)
    await scene.say("Mo", "Go check the back door, and if it's open come and tell me, otherwise go back to your charger.")
    await scene.run(5.0)
    await scene.until_idle(120.0)
    out["now"] = list(play.said())
    await scene.say("Mo", "Follow me until you see the cat.")
    await scene.run(3.0)
    scene.walk("Mo", (2.6, 0.5), speed_mm_s=40.0)
    await scene.run(60.0)
    out["following"] = getattr(scene.life.commands.runner.current, "kind", None)
    cat.home, cat.x, cat.y = True, 3300.0, 300.0
    play.trace("the cat walks in close by")
    await scene.run(10.0)
    out["after_cat"] = getattr(scene.life.commands.runner.current, "kind", None)
    await scene.until_idle(60.0)
    await scene.say("Mo", "If Ina's not home by six, remind me to call her.")
    await scene.run(5.0)
    await scene.say("Mo", "Remind me at seven or when Ina gets home, whichever comes first.")
    await scene.run(5.0)
    scene.leave("Ina")
    await play.skip_to(datetime(2026, 10, 21, 18, 1, tzinfo=timezone.utc), 300.0)
    await scene.run(5.0)
    out["at_six"] = list(play.said())
    scene.arrive("Ina", 1.8, 0.4)
    play.seen()
    await scene.run(5.0)
    await play.skip_to(datetime(2026, 10, 21, 19, 5, tzinfo=timezone.utc), 300.0)
    out["said"] = play.said()
    return out


async def flapping(play: LaterScene) -> dict:
    scene = play.scene
    scene.leave("Mo")
    await play.skip(700.0, 100.0)
    await scene.say("Ina", "When Mo gets home, remind me to ask about school.")
    await scene.run(2.0)
    for _ in range(3):
        scene.arrive("Mo", 1.6, -0.5)
        play.seen()
        await scene.run(4.0)
        scene.leave("Mo")
        await play.skip(240.0, 60.0)
    return {"said": play.said()}


async def runs_out(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Ina", "When Sam gets home, remind me to ask about the bus.")
    await scene.run(2.0)
    await play.skip(25 * 3600.0)
    await scene.run(5.0)
    return {"said": play.said(), "left": len(play.later.agenda.waiting())}


async def stranger(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Rua", "At five, come to the lounge.")
    await scene.run(3.0)
    return {"said": play.said(), "kept": len(play.later.agenda.waiting())}


async def trust_drop(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Mo", "At five, come to the lounge.")
    await scene.run(3.0)
    kept = len(play.later.agenda.waiting())
    scene.life.company.book.find("mo").override = "stranger"
    play.trace("Mo's trust drops to a stranger's")
    await play.skip_to(datetime(2026, 10, 21, 17, 5, tzinfo=timezone.utc), 300.0)
    records = [r for r in play.records() if r["kind"] in ("later_dropped", "later_moved")]
    return {"kept": kept, "left": len(play.later.agenda.waiting()), "records": records, "said": play.said()}


async def daylight_saving(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Ina", "At half past two, remind me to check the oven.")
    await scene.run(2.0)
    await play.skip_to(datetime(2026, 9, 27, 3, 10, tzinfo=NZ), 300.0)
    times = [r for r in play.records() if r["kind"] == "later_said"]
    return {"said": play.said(), "fired": [datetime.fromisoformat(r["at"]).astimezone(NZ).strftime("%H:%M") for r in times]}


async def clock_jump(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Ina", "At seven, remind me to put the bins out.")
    await scene.run(2.0)
    await play.skip_to(datetime(2026, 10, 21, 19, 1, tzinfo=timezone.utc), 300.0)
    first = len([line for line in play.said() if "remind you: put the bins out" in line])
    scene.clock.set(scene.clock.now() - 3600.0)
    play.trace("the phone's clock jumps back an hour")
    await play.skip(5400.0, 300.0)
    scene.clock.set(scene.clock.now() + 3 * 3600.0)
    play.trace("the phone's clock jumps forward three hours")
    await play.skip(600.0, 300.0)
    jumps = [r for r in play.records() if r["kind"] == "clock_jump"]
    return {"first": first, "said": play.said(), "told": len([line for line in play.said() if "remind you: put the bins out" in line]), "jumps": len(jumps)}


async def watching(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Sam", "If Ina's not home by six, remind me to call her.")
    await scene.run(3.0)
    by_friend = len(play.later.agenda.waiting())
    await scene.say("Mo", "If Ina's not home by six, remind me to call her.")
    await scene.run(3.0)
    by_trusted = len(play.later.agenda.waiting())
    await scene.say("Ina", "What have people asked you about me?")
    await scene.run(3.0)
    await scene.say("Ina", "Cancel it.")
    await scene.run(3.0)
    left = len(play.later.agenda.waiting())
    await play.skip(120.0, 30.0)
    return {"by_friend": by_friend, "by_trusted": by_trusted, "left": left, "said": play.said()}


async def private(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Ina", "At eight, remind me to take my tablets.")
    await scene.run(3.0)
    await play.skip_to(datetime(2026, 10, 21, 20, 1, tzinfo=timezone.utc), 300.0)
    await scene.run(3.0)
    offered = list(play.said())
    await scene.say("Ina", "Go on.")
    await scene.run(3.0)
    return {"offered": offered, "said": play.said()}


async def checking_in(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Ina", "Follow me until I've had enough.")
    await scene.run(305.0)
    asked = list(play.said())
    await scene.say("Ina", "No, I'm done.")
    await scene.run(3.0)
    return {"asked": asked, "said": play.said(), "doing": getattr(scene.life.commands.runner.current, "kind", None)}


async def lasting_while(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Ina", "Wait here while it's before five past three.")
    await scene.run(5.0)
    waiting = getattr(scene.life.commands.runner.current, "kind", None)
    await scene.run(600.0)
    return {"waiting": waiting, "said": play.said(), "doing": getattr(scene.life.commands.runner.current, "kind", None)}


async def restart(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Ina", "At seven, remind me to put the bins out.")
    await scene.run(3.0)
    play.later.save(force=True)
    play.trace("the brain stops at 3 pm and starts again at 9 pm")
    scene.clock.advance(6 * 3600.0)
    later = Later(scene.life)
    scene.life.later = later
    scene.life.commands.later = later
    later.agenda.every = SAVE_EVERY_S
    play.seen()
    await scene.run(5.0)
    return {"said": play.said(), "left": len(later.agenda.waiting())}


async def ladder(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Ina", "At five, come to the lounge.")
    await scene.run(3.0)
    await play.skip_to(datetime(2026, 10, 21, 16, 58, tzinfo=timezone.utc), 300.0)
    await scene.say("Mo", "Wait here until I call you.")
    await scene.run(3.0)
    scene.leave("Ina")
    await play.skip_to(datetime(2026, 10, 21, 17, 16, tzinfo=timezone.utc), 60.0)
    doing = getattr(scene.life.commands.runner.current, "kind", None)
    scene.arrive("Ina", 1.6, 0.6)
    play.seen()
    await scene.run(5.0)
    return {"doing": doing, "said": play.said(), "left": len(play.later.agenda.waiting())}


async def asking(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Ina", "At eight, remind me to feed the cat.")
    await scene.run(35.0)
    await scene.say("Ina", "At nine, remind me to feed the cat.")
    await scene.run(3.0)
    await scene.say("Ina", "Both.")
    await scene.run(35.0)
    both = len(play.later.agenda.waiting())
    await scene.say("Ina", "Remind me in ten minutes to take the washing out.")
    await scene.run(35.0)
    await scene.say("Ina", "Cancel my reminder.")
    await scene.run(3.0)
    await scene.say("Ina", "The washing one.")
    await scene.run(3.0)
    left = sorted(item.words for item in play.later.agenda.waiting())
    await scene.say("Ina", "Cancel my reminder.")
    await scene.run(25.0)
    return {"both": both, "left": left, "said": play.said(), "after": len(play.later.agenda.waiting())}


def relate(play: LaterScene, **ties) -> None:
    for name, tie in ties.items():
        play.life.company.book.find(name).relationship = tie


def usual(play: LaterScene, name: str, room: str) -> None:
    person = play.life.company.book.find(name)
    play.life.alive.book.met_in[person.id] = {room: {"n": 6, "at": play.scene.clock.now()}}


async def message_home(play: LaterScene, guest: bool = False) -> dict:
    scene = play.scene
    relate(play, ina="family", mo="family")
    scene.leave("Ina")
    if not guest:
        scene.leave("Rua")
    await play.skip(700.0, 100.0)
    await scene.say("Mo", "When Ina gets home tell her dinner's ready.")
    await scene.run(3.0)
    out = {"asked": list(play.said())}
    scene.leave("Mo")
    await play.skip(1200.0, 100.0)
    out["before"] = list(play.said())
    scene.arrive("Ina", 1.5, 0.4)
    play.seen()
    await scene.run(6.0)
    out["home"] = list(play.said())
    if guest:
        await scene.say("Ina", "Go on.")
        await scene.run(3.0)
    await play.skip(700.0, 100.0)
    scene.arrive("Mo", 1.6, -0.5)
    play.seen()
    await scene.run(6.0)
    out["said"] = play.said()
    out["left"] = len(play.later.agenda.waiting())
    return out


async def message_home_guest(play: LaterScene) -> dict:
    return await message_home(play, guest=True)


async def tell_sam(play: LaterScene) -> dict:
    scene = play.scene
    relate(play, ina="family")
    usual(play, "sam", "study")
    scene.world.thing("cat").home = False
    scene.leave("Sam")
    await play.skip(700.0, 100.0)
    await scene.say("Ina", "Tell Sam to come to the kitchen.")
    await scene.run(3.0)
    out = {"asked": list(play.said())}
    scene.leave("Ina")
    await scene.run(5.0)
    out["going"] = getattr(scene.life.commands.runner.current, "kind", None)
    await scene.run(70.0)
    out["arrived"] = [ending.text for activity, ending in scene.life.commands.runner.history if activity.kind == "go_to_place"]
    await play.skip(130.0, 10.0)
    pose = scene.world.pose
    out["near_study"] = ((pose.x / 1000.0 - 4.2) ** 2 + (pose.y / 1000.0 + 2.2) ** 2) ** 0.5
    scene.arrive("Sam", pose.x / 1000.0 + 0.8, pose.y / 1000.0)
    play.seen()
    await scene.run(6.0)
    out["told"] = list(play.said())
    await play.skip(300.0, 60.0)
    scene.arrive("Ina", 2.0, 0.6)
    play.seen()
    await scene.run(6.0)
    out["said"] = play.said()
    out["seeks"] = [r for r in play.records() if r["kind"] == "later_seek"]
    return out


async def remind_sam(play: LaterScene) -> dict:
    scene = play.scene
    relate(play, ina="family")
    await scene.say("Ina", "Remind Sam to feed the dog at five.")
    await scene.run(3.0)
    await scene.say("Ina", "Remind Sam to brush his teeth at six.")
    await scene.run(35.0)
    await scene.say("Sam", "What reminders do I have?")
    await scene.run(3.0)
    await scene.say("Sam", "Cancel the dog reminder.")
    await scene.run(5.0)
    out = {"asked": list(play.said()), "left": sorted(item.words for item in play.later.agenda.waiting())}
    await play.skip_to(datetime(2026, 10, 21, 18, 2, tzinfo=timezone.utc), 300.0)
    await scene.run(5.0)
    out["said"] = play.said()
    return out


async def cooking_alarm(root: Path, echo: bool) -> tuple:
    show = SafetyScene(root, echo=echo)
    scene = show.scene
    scene.people = [Who("Ina", TRUSTED, 4400.0, 2500.0), Who("Mo", TRUSTED, 1200.0, -1200.0)]
    scene.start, scene.size, scene.things = (2000.0, 0.0, 45.0), SIZE, []
    scene.understanding = canned(READINGS)
    meet = scene._meet

    def met() -> None:
        meet()
        for name, (x, y, r) in ROOMS.items():
            scene.life.alive.rooms.rooms[name] = Room(name, x, y, r, (), 0.9)

    scene._meet = met
    await show.setup()
    out = {}
    try:
        life = scene.life
        cooking = life.house.cooking
        cooking.tick = lambda now, mono: None
        cooking.open = True
        scene.trace("sim", "Ina is cooking in the kitchen")
        await scene.say("Ina", "Don't go in the kitchen while I'm cooking.")
        await scene.run(4.0)
        await scene.say("Mo", "Go to the kitchen.")
        await scene.run(4.0)
        out["before"] = [line.split('says     "', 1)[1].rstrip('"') for line in scene.lines if 'says     "' in line]
        out["circles"] = len(life.rules.circles())
        scene.trace("sim", "a smoke alarm starts beeping")
        show.mix.play("smoke alarm", alarm_in_another_room(), loop=True)
        kitchen = ROOMS["kitchen"]
        out["went_in"] = False
        for _ in range(240):
            await scene.run(1.0)
            pose = scene.world.pose
            if ((pose.x / 1000.0 - kitchen[0]) ** 2 + (pose.y / 1000.0 - kitchen[1]) ** 2) ** 0.5 <= kitchen[2]:
                out["went_in"] = True
            if out["went_in"] and life.alarm():
                out["alarm_circles"] = len(life.rules.circles())
                break
        await scene.run(3.0)
        await scene.say("Ina", "it's fine, it was just the toast")
        await scene.run(1.0)
        await scene.say("Ina", "yes")
        show.mix.stop_clip("smoke alarm")
        await scene.run(15.0)
        out["rule_kept"] = [rule.place for rule in life.rules.on()]
        out["said"] = [line.split('says     "', 1)[1].rstrip('"') for line in scene.lines if 'says     "' in line]
    finally:
        await show.close()
    return scene, out


async def patrol_rule(play: LaterScene) -> dict:
    scene = play.scene
    scene.world.thing("cat").home = False
    await scene.say("Ina", "Stay out of the kitchen.")
    await scene.run(3.0)
    await scene.say("Mo", "Every hour tonight have a look round the house.")
    await scene.run(3.0)
    out = {"asked": list(play.said())}
    scene.leave("Mo")
    await play.skip_to(datetime(2026, 10, 21, 19, 0, 30, tzinfo=timezone.utc), NEAR_STEP_S)
    await scene.until_idle(900.0, 5.0)
    found = [ending.text for activity, ending in scene.life.commands.runner.history if activity.kind == "check"]
    out["round"] = found[-1] if found else ""
    scene.arrive("Mo", 2.4, 0.5)
    play.seen()
    await scene.run(6.0)
    out["said"] = play.said()
    return out


async def child_quiet(play: LaterScene) -> dict:
    scene = play.scene
    life = scene.life
    await scene.say("Sam", "Be quiet for two hours.")
    await scene.run(3.0)
    out = {"said": list(play.said()), "at_once": life.rule_quiet()}
    await play.skip(1800.0, 300.0)
    out["half_hour"] = (life.rule_quiet(), life.alive.quiet())
    await play.skip(1900.0, 300.0)
    out["after_hour"] = (life.rule_quiet(), life.alive.quiet())
    out["rules"] = len(life.rules.on())
    return out


async def lifted(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Mo", "Keep out of the study.")
    await scene.run(3.0)
    await scene.say("Ina", "Go to the study.")
    await scene.run(3.0)
    out = {"refused": scene.life.commands.runner.current is None}
    await scene.say("Ina", "You can go in the study now.")
    await scene.run(3.0)
    out["rules"] = len(scene.life.rules.on())
    await scene.say("Ina", "Go to the study.")
    await scene.run(3.0)
    out["going"] = getattr(scene.life.commands.runner.current, "kind", None)
    out["said"] = play.said()
    return out


async def stranger_rules(play: LaterScene) -> dict:
    scene = play.scene
    await scene.say("Rua", "Tell Ina dinner's ready.")
    await scene.run(3.0)
    await scene.say("Rua", "Stay out of the kitchen.")
    await scene.run(3.0)
    return {"said": play.said(), "kept": len(play.later.agenda.waiting()), "rules": len(scene.life.rules.on())}


async def undelivered(play: LaterScene) -> dict:
    scene = play.scene
    scene.leave("Sam")
    await play.skip(700.0, 100.0)
    await scene.say("Ina", "Tell Sam to feed the dog.")
    await scene.run(3.0)
    out = {"asked": list(play.said()), "kept": len(play.later.agenda.waiting())}
    await play.skip(2 * 86400.0, 3600.0)
    out["two_days"] = len(play.later.agenda.waiting())
    await play.skip(86400.0 + 3600.0, 3600.0)
    await scene.run(5.0)
    out["said"] = play.said()
    out["left"] = len(play.later.agenda.waiting())
    return out


async def private_message(play: LaterScene) -> dict:
    scene = play.scene
    relate(play, ina="family")
    scene.leave("Sam")
    await play.skip(700.0, 100.0)
    await scene.say("Ina", "Tell Sam the doctor phoned about his tablets.")
    await scene.run(3.0)
    out = {"asked": list(play.said())}
    scene.arrive("Sam", 1.5, 0.5)
    play.seen()
    await scene.run(6.0)
    out["offered"] = list(play.said())
    await scene.say("Sam", "Go on.")
    await scene.run(3.0)
    out["said"] = play.said()
    return out


async def quiet_reminder(play: LaterScene) -> dict:
    scene = play.scene
    relate(play, ina="family", mo="family")
    await scene.say("Ina", "Remind me in ten minutes to take the washing out.")
    await scene.run(3.0)
    await scene.say("Mo", "Be quiet for half an hour.")
    await scene.run(3.0)
    await scene.say("Mo", "Tell Ina the car's ready.")
    await scene.run(3.0)
    out = {"asked": list(play.said())}
    await play.skip(620.0, NEAR_STEP_S)
    out["soft"] = [r for r in play.records() if r["kind"] == "later_said"]
    out["shown"] = [m for m in scene.life.house.layer.shown if m.get("op") == "show"]
    out["in_quiet"] = list(play.said())
    await play.skip(1300.0, 60.0)
    await scene.run(5.0)
    out["said"] = play.said()
    return out


class Looking(Mind):
    def __init__(self, answer: str):
        self.answer = answer
        self.asked: list[str] = []

    async def sees(self) -> bool:
        return True

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        content = messages[-1]["content"]
        self.asked.append(content[0]["text"] if isinstance(content, list) else str(content))
        return MindReply(self.answer)


class Crying:
    def __init__(self):
        from ..hearing.events import RULES

        self.labels = sorted({name for rule in RULES for name in rule.classes})
        self.on = False
        self.want_vectors = False

    def feed(self, block) -> list:
        from ..hearing.events import HOP_S

        index = self.labels.index("Baby cry, infant cry")
        out = []
        for hop in range(max(1, int(round(block.seconds / HOP_S)))):
            scores = [0.0] * len(self.labels)
            if self.on:
                scores[index] = 0.8
            out.append((block.start + (hop + 1) * HOP_S, scores))
        return out

    def gap(self) -> None:
        return None

    def take_vectors(self) -> list:
        return []


def bare(play) -> None:
    for thing in play.scene.world.things:
        thing.home = False


def remember(play, **spots) -> None:
    nav = play.life.nav
    nav.ensure_frame()
    for name, (x, y) in spots.items():
        nav.chart.remember_spot(name.replace("_", " "), x, y)


def looking(play, answer: str) -> Looking:
    from ..activities.picture import PictureQuestions

    mind = Looking(answer)
    pictures = PictureQuestions(play.scene.eyes, mind)
    pictures.guard = play.life.privacy
    play.life.commands.pictures = pictures
    return mind


def checks_of(play) -> list[str]:
    return [ending.text for activity, ending in play.life.commands.runner.history if activity.kind == "check"]


def pose_gap(scene, x: float, y: float) -> float:
    pose = scene.world.pose
    return ((pose.x / 1000.0 - x) ** 2 + (pose.y / 1000.0 - y) ** 2) ** 0.5


async def front_door(play: LaterScene, dark: bool = False) -> dict:
    scene = play.scene
    bare(play)
    life = play.life
    remember(play, front_door=(4.6, -1.0))
    mind = looking(play, "No, it's closed.")
    if dark:
        life.commands.runner.kit.dark = lambda: True
        play.trace("the hallway light is off")
    await scene.say("Ina", "Go check the front door.")
    await scene.run(3.0)
    out = {"asked": list(play.said())}
    scene.leave("Ina")
    closest = 99.0
    for _ in range(240):
        await scene.run(1.0)
        closest = min(closest, pose_gap(play.scene, 4.6, -1.0))
        if not scene.life.commands.runner.busy and checks_of(play):
            break
    out["closest"] = closest
    out["back"] = pose_gap(play.scene, 2.0, 0.0)
    out["checked"] = checks_of(play)
    out["asked_model"] = list(mind.asked)
    ina = life.company.book.find("ina").id
    found = life.commands.checks.last(ina, scene.clock.now())
    out["result"] = found.answer if found else None
    out["before_back"] = list(play.said())
    await play.skip(300.0, 30.0)
    scene.arrive("Ina", 1.6, 0.5)
    play.seen()
    await scene.run(6.0)
    out["said"] = play.said()
    out["records"] = [r for r in play.records() if r["kind"] in ("picture_question", "check_refused")]
    return out


async def front_door_dark(play: LaterScene) -> dict:
    return await front_door(play, dark=True)


async def check_tree(play: LaterScene, answer: str = "Yes, it's open.", dark: bool = False) -> dict:
    scene = play.scene
    bare(play)
    life = play.life
    remember(play, back_door=(4.6, 1.0))
    looking(play, answer)
    if dark:
        life.commands.runner.kit.dark = lambda: True
        play.trace("the back porch light is off")
    await scene.say("Mo", "Go check the back door, and if it's open come and tell me, otherwise go back to your charger.")
    await scene.run(3.0)
    await scene.until_idle(300.0, 2.0)
    await scene.run(3.0)
    await scene.until_idle(300.0, 2.0)
    mo = life.company.book.find("mo").id
    found = life.commands.checks.last(mo, scene.clock.now())
    kinds = [activity.kind for activity, _ in life.commands.runner.history]
    return {"said": play.said(), "kinds": kinds, "result": found.answer if found else None, "mo": pose_gap(play.scene, 3.0, 0.0), "docked": scene.world.docked()}


async def check_tree_dark(play: LaterScene) -> dict:
    return await check_tree(play, "Yes, it's open.", dark=True)


async def check_tree_shut(play: LaterScene) -> dict:
    return await check_tree(play, "No, it's shut.")


async def check_private(play: LaterScene) -> dict:
    scene = play.scene
    bare(play)
    life = play.life
    looking(play, "Yes.")
    sam = life.company.book.find("sam")
    life.privacy.rooms.saw(sam.id, "bedroom")
    play.trace("Sam is in the bedroom")
    await scene.say("Ina", "Is the light on in the bathroom?")
    await scene.run(3.0)
    first = getattr(life.commands.runner.current, "kind", None)
    await scene.say("Ina", "Is the window open in the bedroom?")
    await scene.run(3.0)
    second = getattr(life.commands.runner.current, "kind", None)
    return {"said": play.said(), "moving": (first, second), "start": pose_gap(play.scene, 2.0, 0.0), "records": [r for r in play.records() if r["kind"] in ("check_refused", "picture_question")]}


async def check_kept_out(play: LaterScene) -> dict:
    scene = play.scene
    bare(play)
    life = play.life
    looking(play, "No, it's off.")
    remember(play, oven=(4.2, 2.3))
    await scene.say("Ina", "Stay out of the kitchen.")
    await scene.run(3.0)
    await scene.say("Mo", "See if the oven is off.")
    await scene.run(3.0)
    return {"said": play.said(), "doing": getattr(life.commands.runner.current, "kind", None), "start": pose_gap(play.scene, 2.0, 0.0)}


def baby_sitting(play: LaterScene) -> None:
    sam = play.scene.world.person("sam")
    sam.posture, sam.height_mm = "crouching", 700.0
    play.trace("Sam, the baby, is crawling on the lounge floor")


async def watch_back(play: LaterScene) -> dict:
    scene = play.scene
    bare(play)
    life = play.life
    baby_sitting(play)
    await scene.say("Ina", "Keep an eye on the baby while I make a cup of tea.")
    await scene.run(5.0)
    out = {"asked": list(play.said()), "watching": getattr(life.commands.runner.current, "kind", None)}
    scene.leave("Ina")
    await scene.run(90.0)
    out["while_away"] = getattr(life.commands.runner.current, "kind", None)
    scene.arrive("Ina", 1.8, 0.6)
    play.seen()
    await scene.run(10.0)
    out["after"] = getattr(life.commands.runner.current, "kind", None)
    out["said"] = play.said()
    return out


async def watch_hours(play: LaterScene) -> dict:
    scene = play.scene
    bare(play)
    life = play.life
    baby_sitting(play)
    await scene.say("Ina", "Keep an eye on Sam.")
    await scene.run(5.0)
    out = {"asked": list(play.said())}
    scene.leave("Ina")
    await play.skip(7140.0, 60.0)
    out["before_end"] = getattr(life.commands.runner.current, "kind", None)
    await play.skip(120.0, 5.0)
    await scene.run(10.0)
    out["said"] = play.said()
    out["kinds"] = [activity.kind for activity, _ in life.commands.runner.history]
    out["alerts"] = [r for r in play.records() if r["kind"] == "watch_alert"]
    return out


async def watch_friend(play: LaterScene) -> dict:
    scene = play.scene
    bare(play)
    await scene.say("Alex", "Keep an eye on the baby.")
    await scene.run(3.0)
    await scene.say("Sam", "Keep an eye on Ina for me.")
    await scene.run(3.0)
    return {"said": play.said(), "doing": getattr(scene.life.commands.runner.current, "kind", None)}


async def where_sitting(play: LaterScene, old: bool = False) -> dict:
    scene = play.scene
    bare(play)
    life = play.life
    ina = scene.world.person("ina")
    ina.posture = "sitting"
    scene.leave("Sam")
    play.trace("Ina sits on the couch; Sam is out")
    await scene.run(140.0)
    seen = life.commands.refs.where(life.company.book.find("ina").id, scene.clock.now())
    out = {"seen": (round(seen.x, 1), round(seen.y, 1), seen.room, seen.posture) if seen else None}
    scene.leave("Ina")
    play.trace("Ina gets up and goes out")
    await play.skip(3720.0 if old else 300.0, 60.0)
    scene.arrive("Sam", 1.4, -0.6)
    play.seen()
    await scene.run(3.0)
    await scene.say("Sam", "Go to where Ina was sitting.")
    await scene.run(3.0)
    out["asked"] = list(play.said())
    if old:
        await scene.say("Sam", "The kitchen.")
        await scene.run(3.0)
    await scene.until_idle(150.0, 2.0)
    out["said"] = play.said()
    out["gap"] = pose_gap(play.scene, *(out["seen"][:2])) if out["seen"] else None
    out["kitchen"] = pose_gap(play.scene, 4.2, 2.2)
    out["kinds"] = [(activity.kind, ending.text) for activity, ending in life.commands.runner.history]
    return out


async def where_sitting_old(play: LaterScene) -> dict:
    return await where_sitting(play, old=True)


async def again(play: LaterScene) -> dict:
    scene = play.scene
    bare(play)
    life = play.life
    await scene.say("Ina", "Spin around.")
    await scene.until_idle(60.0)
    await scene.say("Ina", "Do that again.")
    await scene.until_idle(60.0)
    await scene.say("Ina", "Go to the kitchen and do it again.")
    await scene.until_idle(150.0, 2.0)
    await scene.say("Mo", "Again!")
    await scene.until_idle(60.0)
    turns = [activity.request.as_dict() for activity, _ in life.commands.runner.history if activity.kind == "turn"]
    return {"said": play.said(), "turns": turns, "kinds": [activity.kind for activity, _ in life.commands.runner.history], "kitchen": pose_gap(play.scene, 4.2, 2.2)}


async def other_way(play: LaterScene) -> dict:
    scene = play.scene
    bare(play)
    life = play.life
    await scene.say("Ina", "Turn left.")
    await scene.until_idle(60.0)
    await scene.say("Ina", "No, the other way.")
    await scene.until_idle(60.0)
    turns = [activity.request.way for activity, _ in life.commands.runner.history if activity.kind == "turn"]
    return {"said": play.said(), "turns": turns}


async def back_before(play: LaterScene) -> dict:
    scene = play.scene
    bare(play)
    await scene.say("Ina", "Go to the kitchen.")
    await scene.until_idle(150.0, 2.0)
    out = {"kitchen": pose_gap(play.scene, 4.2, 2.2)}
    await scene.say("Ina", "Go back to where you were before.")
    await scene.until_idle(150.0, 2.0)
    out["start"] = pose_gap(play.scene, 2.0, 0.0)
    out["said"] = play.said()
    return out


async def watch_alarm(root: Path, echo: bool, smoke: bool = False) -> tuple:
    from ..hearing.events import SoundEvents

    show = SafetyScene(root, echo=echo)
    scene = show.scene
    scene.people = [Who("Ina", TRUSTED, 3200.0, 700.0), Who("Sam", CHILD, 3300.0, -500.0)]
    scene.start, scene.size, scene.things = (2000.0, 0.0, 0.0), SIZE, []
    scene.understanding = canned(READINGS)
    meet = scene._meet

    def met() -> None:
        meet()
        for name, (x, y, r) in ROOMS.items():
            scene.life.alive.rooms.rooms[name] = Room(name, x, y, r, (), 0.9)

    scene._meet = met
    await show.setup()
    out = {}
    try:
        life = scene.life
        sam = scene.world.person("sam")
        sam.posture, sam.height_mm = "crouching", 700.0
        scene.trace("sim", "Sam, the baby, is crawling on the lounge floor")
        ina = life.company.book.find("ina")
        life.alive.book.met_in[ina.id] = {"bathroom": {"n": 6, "at": scene.clock.now()}}
        crying = Crying()
        hearing = show.safety.hearing
        hearing.model, hearing.events = crying, SoundEvents(crying.labels)
        await scene.say("Ina", "Keep an eye on the baby while I shower.")
        await scene.run(4.0)
        out["start"] = [line.split('says     "', 1)[1].rstrip('"') for line in scene.lines if 'says     "' in line]
        scene.walk("Ina", (5.4, 1.6), speed_mm_s=300.0)
        await scene.run(12.0)
        scene.leave("Ina")
        scene.trace("sim", "Ina goes into the bathroom for a shower")
        await scene.run(30.0)
        out["watching"] = getattr(life.commands.runner.current, "kind", None)
        if smoke:
            scene.trace("sim", "a smoke alarm starts beeping")
            show.mix.play("smoke alarm", alarm_in_another_room(), loop=True)
            for _ in range(120):
                await scene.run(1.0)
                if life.alarm() and getattr(life.commands.runner.current, "kind", None) != "watch":
                    break
            await scene.run(20.0)
            out["alarm"] = life.alarm()
            out["doing"] = getattr(life.commands.runner.current, "kind", None)
            show.mix.stop_clip("smoke alarm")
        else:
            crying.on = True
            scene.trace("sim", "the baby starts crying")
            for _ in range(60):
                await scene.run(1.0)
                if getattr(life.commands.runner.current, "kind", None) == "fetch":
                    break
            out["fetching"] = getattr(life.commands.runner.current, "kind", None)
            await scene.until_idle(120.0, 2.0)
            crying.on = False
            out["bathroom"] = pose_gap(scene, 6.5, 1.9)
        out["said"] = [line.split('says     "', 1)[1].rstrip('"') for line in scene.lines if 'says     "' in line]
        out["ended"] = [(activity.kind, ending.text) for activity, ending in life.commands.runner.history]
        records = [json.loads(line) for line in scene.store.path("logs/blackbox.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        out["records"] = [r for r in records if r["kind"] in ("watch_alert", "watch_stopped", "safety_incident")]
    finally:
        await show.close()
    return scene, out


async def watch_crying(root: Path, echo: bool) -> tuple:
    return await watch_alarm(root, echo, smoke=False)


async def watch_smoke(root: Path, echo: bool) -> tuple:
    return await watch_alarm(root, echo, smoke=True)


UTC = timezone.utc
SCENES = {
    "bin": (bin_day, datetime(2027, 12, 22, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED)], False),
    "ten": (ten_minutes, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED)], False),
    "wake": (wake_up, datetime(2026, 10, 21, 22, 30, tzinfo=UTC), [who("Ina", TRUSTED)], False),
    "patrol": (patrol, datetime(2026, 10, 21, 18, 0, tzinfo=UTC), [who("Ina", TRUSTED, 2600.0, -900.0)], True),
    "trigger": (trigger, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Mo", TRUSTED), who("Ina", TRUSTED, 1600.0, 600.0)], False),
    "two": (two_at_once, datetime(2026, 10, 26, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED)], False),
    "follow": (while_following, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED)], False),
    "logic": (logic, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Mo", TRUSTED, 3000.0, 0.0), who("Ina", TRUSTED, 1700.0, 500.0)], True),
    "flapping": (flapping, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED), who("Mo", CHILD, 1700.0, -500.0)], False),
    "runs_out": (runs_out, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED), who("Sam", CHILD, 900.0, 900.0)], False),
    "stranger": (stranger, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED), who("Rua", None, 1500.0, -400.0)], False),
    "trust_drop": (trust_drop, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Mo", TRUSTED)], True),
    "dst": (daylight_saving, datetime(2026, 9, 26, 22, 0, tzinfo=NZ), [who("Ina", TRUSTED)], False),
    "jump": (clock_jump, datetime(2026, 10, 21, 18, 0, tzinfo=UTC), [who("Ina", TRUSTED)], False),
    "watching": (watching, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 1200.0, 300.0), who("Sam", FRIEND, 1500.0, -400.0), who("Mo", TRUSTED, 1700.0, 400.0)], False),
    "private": (private, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED), who("Rua", None, 1500.0, -400.0)], False),
    "checking_in": (checking_in, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED)], False),
    "while": (lasting_while, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED)], False),
    "restart": (restart, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED)], False),
    "ladder": (ladder, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED), who("Mo", INNER, 1500.0, -400.0)], True),
    "asking": (asking, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED)], False),
    "home": (message_home, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Mo", TRUSTED), who("Ina", TRUSTED, 1600.0, 600.0), who("Rua", None, 1500.0, -400.0)], False),
    "home_guest": (message_home_guest, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Mo", TRUSTED), who("Ina", TRUSTED, 1600.0, 600.0), who("Rua", None, 1500.0, -400.0)], False),
    "tell_sam": (tell_sam, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 2600.0, 600.0), who("Sam", CHILD, 4300.0, -2300.0)], STUDY),
    "remind_sam": (remind_sam, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED), who("Sam", CHILD, 1500.0, -400.0)], False),
    "patrol_rule": (patrol_rule, datetime(2026, 10, 21, 18, 0, tzinfo=UTC), [who("Ina", TRUSTED, 2600.0, -900.0), who("Mo", TRUSTED, 2400.0, 500.0)], True),
    "child_quiet": (child_quiet, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED), who("Sam", CHILD, 1500.0, -400.0)], False),
    "lifted": (lifted, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 2600.0, 600.0), who("Mo", FRIEND, 2400.0, -500.0)], STUDY),
    "stranger_rules": (stranger_rules, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED), who("Rua", None, 1500.0, -400.0)], False),
    "undelivered": (undelivered, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED), who("Sam", CHILD, 1500.0, -400.0)], False),
    "private_message": (private_message, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED), who("Sam", CHILD, 1500.0, -400.0), who("Rua", None, 1700.0, 500.0)], False),
    "quiet_reminder": (quiet_reminder, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED), who("Mo", TRUSTED, 1500.0, -400.0)], False),
    "front_door": (front_door, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 1700.0, 500.0)], True),
    "front_door_dark": (front_door_dark, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 1700.0, 500.0)], True),
    "check_tree": (check_tree, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Mo", TRUSTED, 3000.0, -600.0)], True),
    "check_tree_dark": (check_tree_dark, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Mo", TRUSTED, 3000.0, -600.0)], True),
    "check_tree_shut": (check_tree_shut, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Mo", TRUSTED, 3000.0, -600.0)], True),
    "check_private": (check_private, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 1700.0, 500.0), who("Sam", CHILD, 900.0, 900.0)], True),
    "check_kept_out": (check_kept_out, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 1700.0, 500.0), who("Mo", TRUSTED, 1500.0, -400.0)], True),
    "watch_back": (watch_back, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 1700.0, 600.0), who("Sam", CHILD, 3200.0, -300.0)], True),
    "watch_hours": (watch_hours, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 1700.0, 600.0), who("Sam", CHILD, 3200.0, -300.0)], True),
    "watch_friend": (watch_friend, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 1700.0, 600.0), who("Alex", FRIEND, 1500.0, -400.0), who("Sam", CHILD, 900.0, 900.0)], True),
    "where_sitting": (where_sitting, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 3200.0, 500.0), who("Sam", FRIEND, 1400.0, -600.0)], True),
    "where_sitting_old": (where_sitting_old, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 3200.0, 500.0), who("Sam", FRIEND, 1400.0, -600.0)], True),
    "again": (again, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 1700.0, 600.0), who("Mo", TRUSTED, 1500.0, -500.0)], True),
    "other_way": (other_way, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 1700.0, 600.0)], True),
    "before": (back_before, datetime(2026, 10, 21, 15, 0, tzinfo=UTC), [who("Ina", TRUSTED, 1700.0, 600.0)], True),
}
BUILT = {"cooking": cooking_alarm, "watch_crying": watch_crying, "watch_smoke": watch_smoke, **TRYING, **TEACHING}


async def play(name: str = "ten", root: Path | None = None, echo: bool = False) -> tuple[LaterScene, dict]:
    holder = None
    if root is None:
        holder = tempfile.TemporaryDirectory(prefix="pebble-later-scene-")
        root = Path(holder.name) / "self"
    if name in BUILT:
        try:
            return await BUILT[name](root, echo)
        finally:
            if holder is not None:
                holder.cleanup()
    script, at, people, rooms = SCENES[name]
    show = LaterScene(root, people, at, READINGS, echo=echo, rooms=rooms)
    try:
        await show.setup()
        result = await script(show)
    finally:
        await show.close()
        if holder is not None:
            holder.cleanup()
    return show, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.life.scene", description="Play a scripted scene about things for later against the simulated body and print what happened")
    parser.add_argument("--scene", choices=sorted(SCENES) + sorted(BUILT), default="ten")
    parser.add_argument("--self", dest="self_dir", default=None, help="keep the self folder here (default: a temporary one)")
    args = parser.parse_args(argv)
    asyncio.run(play(args.scene, Path(args.self_dir) if args.self_dir else None, echo=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
