import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ..mind.base import Mind, MindReply
from ..people.trust import FRIEND, TRUSTED
from ..sim.scene import Who
from ..understand.model import ModelReader
from ..understand.understanding import Understanding

UTC = timezone.utc
AT = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
HEARD = re.compile(r'Heard: "(.*)"\s*$', re.S)
PLAIN = re.compile(r'The plain (?:line|question): "(.*)"')
KITCHEN = (4.2, 2.2)
DANCE = "Do a little dance."
FIRST = {"think": "a dance: a happy face, then turn one way and the other", "steps": [{"do": "face", "expression": "happy"}, {"do": "turn", "way": "left", "degrees": 90}, {"do": "turn", "way": "right", "degrees": 90}]}
SECOND = {"think": "something different: a spin and two wiggles", "steps": [{"do": "turn", "way": "around", "degrees": 360}, {"do": "wiggle", "repeat": 2}, {"do": "face", "expression": "love"}]}
FASTER = {"think": "the same, but quick", "steps": [{"do": "turn", "way": "around", "degrees": 360, "speed": "quick"}, {"do": "wiggle", "repeat": 2}, {"do": "face", "expression": "love"}]}
SLOW = {"think": "a long slow spin", "steps": [{"do": "turn", "way": "around", "degrees": 720, "speed": "slow"}, {"do": "wiggle", "repeat": 3}, {"do": "tilt", "way": "up", "degrees": 30}]}
READINGS = {
    DANCE: {"kind": "try_new", "text": "do a little dance"},
    "Spin twice then come to me.": {"kind": "try_new", "text": "spin twice then come to me"},
    "Push the ball to Ina.": {"kind": "try_new", "text": "push the ball to ina"},
    "Do a little parade.": {"kind": "try_new", "text": "do a little parade"},
    "Do a little tour.": {"kind": "try_new", "text": "do a little tour"},
    "Nod three times.": {"kind": "other"},
    "Kick the ball to Ina.": {"kind": "play", "thing": "ball"},
    "remind me to water the plant in twenty minutes": {"kind": "say_to", "who": "me", "text": "water the plant", "when": {"in_s": 1200}},
}
PROMISE = "Sure, I'll remind you to water the plant in twenty minutes."
CHATTER = (
    ("The rain finally stopped, so the garden might dry out a bit by tonight.", "That's good, the grass looked soggy this morning."),
    ("I watched that cooking show again last night, the one with the big tent.", "Oh, the baking one? Those cakes always look amazing."),
    ("Work was so slow today, I spent half the afternoon sorting emails.", "That sounds a bit dull. Did you get them all sorted?"),
    ("I think we're out of milk again, honestly it goes so fast in this house.", "Milk does disappear quickly here."),
    ("I'm thinking of painting the hallway a lighter colour, maybe a pale green.", "Pale green sounds calm and fresh."),
    ("I found an old photo album in the cupboard, full of holiday pictures.", "That must have brought back memories."),
    ("There's a new cafe opening down the road, apparently they do good scones.", "Good scones are always worth trying."),
    ("I tried a new recipe with lentils and it actually turned out quite nice.", "Lentils can be really tasty."),
    ("We should probably clean out the garage one of these weekends.", "The garage is a big job."),
    ("I'm reading a mystery novel and I have no idea who did it yet.", "Mysteries are fun when you can't guess."),
    ("I keep meaning to call my aunt, I haven't spoken to her in ages.", "She would probably love to hear from you."),
    ("It's getting colder in the mornings now, I needed a jumper today.", "The mornings do feel colder lately."),
    ("I think I'll have soup for lunch tomorrow, it's that kind of weather.", "Soup sounds cosy."),
    ("We had a power cut at work for about an hour this afternoon.", "An hour without power is a long time."),
    ("I've been trying to drink more water, but I keep forgetting.", "Water is easy to forget."),
    ("We might go for a walk by the river on Sunday if it's fine.", "A river walk sounds nice."),
)


class TryMind(Mind):
    name = "stand-in for E4B"

    def __init__(self, readings: dict, plans=(), choices=(), words=None, slow=None):
        self.readings = {self.key(text): reading for text, reading in readings.items()}
        self.plans = list(plans)
        self.choices = list(choices)
        self.words = dict(words or {})
        self.slow = dict(slow or {})
        self.sleep = None
        self.asked: list[tuple[str, str]] = []

    @staticmethod
    def key(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9']+", text.lower()))

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        last = messages[-1]["content"]
        self.asked.append((purpose, last))
        if purpose == "plan":
            reply = self.plans.pop(0) if self.plans else {"cant": "I have no more ideas"}
            return MindReply(json.dumps(reply))
        if purpose == "unstuck":
            reply = self.choices.pop(0) if self.choices else {"choose": "give_up"}
            return MindReply(json.dumps(reply))
        if purpose == "decision":
            found = PLAIN.search(last)
            line = found.group(1) if found else ""
            delay = self.slow.get(line, 0.0)
            if delay and self.sleep is not None:
                await self.sleep(delay)
            return MindReply(self.words.get(line, line))
        found = HEARD.search(last)
        reading = self.readings.get(self.key(found.group(1)) if found else "")
        return MindReply(json.dumps(reading) if reading is not None else '{"kind":"chat"}')

    async def warm(self, messages, tools=None, purpose="warm"):
        return True

    def purposes(self) -> list[str]:
        return [purpose for purpose, _ in self.asked]


async def staged(root: Path, echo: bool, people, plans=(), choices=(), words=None, slow=None, rooms=False):
    from .scene import LaterScene

    mind = TryMind(READINGS, plans, choices, words, slow)
    play = LaterScene(root, people, AT, {}, echo=echo, rooms=rooms)
    play.scene.understanding = Understanding(ModelReader([("conscious", mind)]))
    if words is not None:
        play.scene.extra = {"own_words": True}
    await play.setup()
    mind.sleep = play.scene.time.sleep
    return play, mind


def tries(play) -> list:
    return [activity.steps for activity, ending in play.life.commands.runner.history if activity.kind == "try_new"]


def endings(play) -> list:
    return [(activity.kind, ending.how) for activity, ending in play.life.commands.runner.history]


def records(play, *kinds) -> list:
    return [r for r in play.records() if r["kind"] in kinds]


def skill(play, name: str):
    return play.life.skills.get(name)


async def answer(play, who: str, text: str, settle: float = 60.0) -> None:
    await play.scene.say(who, text)
    await play.scene.until_idle(settle)


async def chat(play, who: str, text: str, reply: str, gap: float) -> None:
    life = play.life
    await play.scene.say(who, text)
    person = life.company.book.find(who.lower())
    life.p.turns.mind.replies = [reply]
    observation = f'Answer {who} out loud now.\n{who} is talking to you: "{text}"'
    said = [piece async for piece in life.reply(observation, [], 90, speaker=person.id)]
    life.reply_done("".join(said))
    await play.scene.run(gap)
    for _ in range(20):
        busy = [task for task in life.folding.tasks if not task.done()]
        if not busy:
            break
        await play.scene.run(0.5)


def card_in_reply(play) -> str:
    requests = [r for r in play.life.p.turns.mind.requests if r["purpose"] == "reply"]
    if not requests:
        return ""
    content = requests[-1]["messages"][-1]["content"] or ""
    start = content.find("Your task card")
    return content[start:] if start >= 0 else ""


async def long_talk(root: Path, echo: bool) -> tuple:
    from dataclasses import replace

    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1300.0, 0.0)], [FIRST, SECOND])
    life = play.life
    life._mind_ready = True
    life.p.history.profile = replace(life.p.history.profile, read_ahead=True)
    out = {}
    try:
        await play.scene.say("Ina", "Follow me.")
        await play.scene.run(3.0)
        out["following"] = life.commands.describe()
        await chat(play, "Ina", "The plant on the windowsill is looking thirsty.", PROMISE, 2.0)
        out["promise"] = [item.words for item in life.later.agenda.waiting()]
        for say, reply in CHATTER * 3:
            await chat(play, "Ina", say, reply, 2.0)
        turns, history = life.p.turns, life.p.history
        system = turns.builder.system_text(life.stage(play.local()), life.p.books.values.describe(), history.summary)
        out["passed_point"] = history.needs_compaction(turns._fixed_tokens(system, []))
        out["before_quiet"] = life.folding.folds
        await play.scene.run(7.0)
        out["after_quiet"] = life.folding.folds
        out["card_following"] = life.task_card()
        await play.scene.say("Ina", DANCE)
        await play.scene.until_idle(30.0)
        await play.scene.say("Ina", "No.")
        await play.scene.until_idle(30.0)
        for say, reply in CHATTER[:6]:
            await chat(play, "Ina", say, reply, 1.0)
        await play.scene.run(6.0)
        out["folds"] = life.folding.folds
        await chat(play, "Ina", "What a sunset tonight, the whole sky went orange and pink.", "I saw some orange light on the wall.", 1.0)
        out["card_trying"] = card_in_reply(play)
        await answer(play, "Ina", "Yes, that's it!")
        out["kept"] = skill(play, "little dance")
        out["trims"] = life.p.turns.trims
        out["events"] = [line for line in play.scene.store.read_lines("logs/budget.jsonl") if isinstance(line, dict) and line.get("event")]
        out["warms"] = [r["purpose"] for r in life.p.turns.mind.requests if r["purpose"] not in ("reply",)]
        out["tries"] = tries(play)
        out["agenda"] = [item.words for item in life.later.agenda.waiting()]
        out["said"] = play.said()
    finally:
        await life.folding.close()
        await play.close()
    return play, out


async def dance(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1300.0, 0.0)], [FIRST, SECOND, FASTER])
    out = {}
    try:
        await answer(play, "Ina", DANCE)
        out["first"] = play.said()[:]
        await answer(play, "Ina", "No.")
        await answer(play, "Ina", "Faster!")
        await answer(play, "Ina", "Yes, that's it!")
        out["kept"] = skill(play, "little dance")
        before = len(play.said())
        await answer(play, "Ina", "Do your dance.")
        out["again"] = play.said()[before:]
        out["said"] = play.said()
        out["tries"] = tries(play)
        out["purposes"] = mind.purposes()
        out["prompts"] = [text for purpose, text in mind.asked if purpose == "plan"]
        out["records"] = records(play, "try_answer", "skill_kept", "skill_run", "try_started")
    finally:
        await play.close()
    return play, out


async def spin_come(root: Path, echo: bool) -> tuple:
    plan = {"think": "spin round twice on the spot, then go to the person", "steps": [{"do": "turn", "way": "around", "degrees": 360, "repeat": 2}, {"do": "come", "who": "me"}]}
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1600.0, 500.0)], [plan])
    out = {}
    try:
        await answer(play, "Ina", "Spin twice then come to me.", 150.0)
        pose = play.scene.world.pose
        ina = play.scene.world.person("ina")
        out["gap"] = ((pose.x - ina.x) ** 2 + (pose.y - ina.y) ** 2) ** 0.5 / 1000.0
        out["said"] = play.said()
        out["turns"] = [activity.request.as_dict() for activity, _ in play.life.commands.runner.history if activity.kind == "turn"]
        out["kinds"] = [activity.kind for activity, _ in play.life.commands.runner.history]
        out["planned"] = mind.purposes().count("plan")
    finally:
        await play.close()
    return play, out


async def push_ball(root: Path, echo: bool) -> tuple:
    plan = {"think": "go behind the ball and nudge it towards Ina", "steps": [{"do": "push", "thing": "ball", "to": "ina"}]}
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 3300.0, 400.0)], [plan])
    out = {}
    try:
        play.scene.world.thing("cat").home = False
        ball = play.scene.world.thing("ball")
        ball.x, ball.y, ball.pushable = 1500.0, -500.0, True
        ina = play.scene.world.person("ina")
        out["before"] = ((ball.x - ina.x) ** 2 + (ball.y - ina.y) ** 2) ** 0.5 / 1000.0
        await answer(play, "Ina", "Push the ball to Ina.", 240.0)
        out["after"] = ((ball.x - ina.x) ** 2 + (ball.y - ina.y) ** 2) ** 0.5 / 1000.0
        out["asked"] = play.said()[:]
        await answer(play, "Ina", "Perfect!")
        out["kept"] = skill(play, "push the ball to ina")
        out["said"] = play.said()
        out["endings"] = [ending.text for activity, ending in play.life.commands.runner.history if activity.kind == "try_new"]
    finally:
        await play.close()
    return play, out


async def refused_step(root: Path, echo: bool) -> tuple:
    plan = {"think": "march into the kitchen and back with a spin", "steps": [{"do": "go_to_place", "place": "kitchen"}, {"do": "turn", "way": "around", "degrees": 360}, {"do": "face", "expression": "happy"}]}
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1700.0, 600.0), Who("Sam", FRIEND, 1500.0, -400.0)], [plan], rooms=True)
    out = {}
    try:
        await answer(play, "Ina", "Stay out of the kitchen.", 10.0)
        before = len(play.said())
        await answer(play, "Sam", "Do a little parade.", 120.0)
        out["said"] = play.said()[before:]
        out["tries"] = tries(play)
        out["endings"] = endings(play)
        out["refused"] = records(play, "try_step_refused")
    finally:
        await play.close()
    return play, out


async def refused_midway(root: Path, echo: bool) -> tuple:
    plan = {"think": "a spin, a trip to the kitchen, a happy face", "steps": [{"do": "turn", "way": "around", "degrees": 720, "speed": "slow"}, {"do": "go_to_place", "place": "kitchen"}, {"do": "face", "expression": "happy"}]}
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1700.0, 600.0), Who("Mo", TRUSTED, 1500.0, -400.0)], [plan], choices=[{"choose": "another_way"}], rooms=True)
    out = {}
    try:
        await play.scene.say("Ina", "Do a little tour.")
        await play.scene.run(2.0)
        await play.scene.say("Mo", "Stay out of the kitchen.")
        await play.scene.until_idle(150.0)
        out["said"] = play.said()
        out["endings"] = endings(play)
        out["unstuck"] = records(play, "unstuck", "unstuck_outcome")
        out["purposes"] = mind.purposes()
        out["what_now"] = [text for purpose, text in mind.asked if purpose == "unstuck"]
    finally:
        await play.close()
    return play, out


async def stop_try(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1300.0, 0.0)], [SLOW])
    out = {}
    try:
        await play.scene.say("Ina", DANCE)
        await play.scene.run(3.0)
        out["moving"] = play.life.commands.runner.current.kind if play.life.commands.runner.current else None
        await play.scene.say("Ina", "Stop!")
        await play.scene.run(10.0)
        out["after"] = play.life.commands.runner.current
        out["said"] = play.said()
        out["endings"] = endings(play)
        out["kept"] = skill(play, "little dance")
        out["draft"] = play.life.skills.drafted("little dance")
        out["loop"] = play.life.commands.trying.loop
    finally:
        await play.close()
    return play, out


async def tv_laugh(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1300.0, 0.0)], [SLOW])
    out = {}
    try:
        await play.scene.say("Ina", DANCE)
        await play.scene.run(3.0)
        play.life.hint("laugh")
        await play.scene.say(None, "Hahaha!", seen=False)
        await play.scene.until_idle(60.0)
        out["asked"] = play.said()[:]
        await play.scene.say(None, "Yes! Brilliant!", seen=False)
        await play.scene.run(30.0)
        out["said"] = play.said()
        out["kept"] = skill(play, "little dance")
        out["draft"] = play.life.skills.drafted("little dance")
        out["hints"] = records(play, "try_hint")
        out["ignored"] = records(play, "try_answer_ignored")
    finally:
        await play.close()
    return play, out


async def silence(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1300.0, 0.0)], [FIRST])
    out = {}
    try:
        await answer(play, "Ina", DANCE)
        await play.scene.run(30.0)
        out["quiet"] = play.said()[:]
        out["draft"] = play.life.skills.drafted("little dance")
        out["kept_before"] = skill(play, "little dance")
        await answer(play, "Ina", "Try the dance again.")
        out["again"] = play.said()[len(out["quiet"]):]
        await answer(play, "Ina", "Yes!")
        out["kept"] = skill(play, "little dance")
        out["draft_after"] = play.life.skills.drafted("little dance")
        out["said"] = play.said()
        out["plans"] = mind.purposes().count("plan")
    finally:
        await play.close()
    return play, out


async def stranger_yes(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, [Who("Rua", None, 1300.0, 0.0)], [FIRST])
    out = {}
    try:
        await answer(play, "Rua", DANCE)
        out["asked"] = play.said()[:]
        await answer(play, "Rua", "Yes!")
        out["said"] = play.said()
        out["kept"] = skill(play, "little dance")
        out["draft"] = play.life.skills.drafted("little dance")
        out["one_off"] = records(play, "try_one_off")
    finally:
        await play.close()
    return play, out


async def out_of_ideas(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1300.0, 0.0)], [FIRST, FIRST, FIRST])
    out = {}
    try:
        await answer(play, "Ina", DANCE)
        await answer(play, "Ina", "No.")
        out["said"] = play.said()
        out["draft"] = play.life.skills.drafted("little dance")
        out["kept"] = skill(play, "little dance")
        out["tries"] = tries(play)
        out["plans"] = mind.purposes().count("plan")
    finally:
        await play.close()
    return play, out


async def not_like_that(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1300.0, 0.0)], [SECOND])
    out = {}
    try:
        ina = play.life.company.book.find("ina")
        play.life.skills.keep("little dance", "do a little dance", FIRST["steps"], {"id": ina.id, "name": "Ina", "tier": TRUSTED})
        await answer(play, "Ina", "Do your little dance.")
        out["first"] = play.said()[:]
        await answer(play, "Ina", "No, not like that.")
        await answer(play, "Ina", "Yes!")
        out["said"] = play.said()
        out["kept"] = skill(play, "little dance")
        out["tries"] = tries(play)
    finally:
        await play.close()
    return play, out


async def other_body(root: Path, echo: bool) -> tuple:
    from ..activities.skills import Skills

    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1300.0, 0.0)], [])
    out = {}
    try:
        ina = play.life.company.book.find("ina")
        hexapod = Skills(play.scene.store, "hexapod", play.scene.clock)
        hexapod.keep("little dance", "do a little dance", [{"do": "leg_wave", "legs": 2}, {"do": "turn", "way": "left", "degrees": 45}, {"do": "face", "expression": "happy"}], {"id": ina.id, "name": "Ina", "tier": TRUSTED})
        play.life.skills.reload()
        await answer(play, "Ina", DANCE)
        out["asked"] = play.said()[:]
        await answer(play, "Ina", "Yes!")
        out["said"] = play.said()
        out["here"] = skill(play, "little dance")
        out["there"] = Skills(play.scene.store, "hexapod", play.scene.clock).get("little dance")
        out["plans"] = mind.purposes().count("plan")
        out["tries"] = tries(play)
    finally:
        await play.close()
    return play, out


async def worded(root: Path, echo: bool) -> tuple:
    follow_no = "Sorry, I only follow people I know really well."
    words = {follow_no: "Sorry, Alex, I only tag along with people I know really well.", "Coming!": "On my way to you!"}
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1300.0, 300.0), Who("Alex", FRIEND, 1500.0, -400.0)], words=words, slow={})
    out = {}
    try:
        await answer(play, "Alex", "Follow me.", 5.0)
        out["worded"] = play.said()[:]
        mind.slow[follow_no] = 1.0
        await answer(play, "Alex", "Follow me.", 5.0)
        out["slow"] = play.said()[len(out["worded"]):]
        mind.words[follow_no] = "Okay, I'll follow you!"
        mind.slow.pop(follow_no)
        before = len(play.said())
        await answer(play, "Alex", "Follow me.", 5.0)
        out["dishonest"] = play.said()[before:]
        before = len(play.said())
        await answer(play, "Alex", "Squash that spider!", 5.0)
        out["harm"] = play.said()[before:]
        before = len(play.said())
        await answer(play, "Ina", "Come here.", 60.0)
        out["ack"] = play.said()[before:]
        out["records"] = records(play, "own_words")
        out["asked"] = [text for purpose, text in mind.asked if purpose == "decision"]
    finally:
        await play.close()
    return play, out


def stuck_nav(play, times: int):
    from ..nav.navigator import Trip

    nav = play.life.nav
    real = nav.go_to
    left = {"stuck": times, "calls": 0}

    async def go_to(kit, x, y, stop_m=0.3, top=None, exempt="", max_s=None, settle_m=0.0):
        near = ((x - KITCHEN[0]) ** 2 + (y - KITCHEN[1]) ** 2) ** 0.5 < 0.6
        if near:
            left["calls"] += 1
        if near and left["stuck"] > 0:
            left["stuck"] -= 1
            kit.say("I'm stuck by the door. Could you help me?")
            return Trip(False, "stuck", "you got stuck by the kitchen door and asked for help")
        extra = {} if max_s is None else {"max_s": max_s}
        return await real(kit, x, y, stop_m=stop_m, top=top, exempt=exempt, settle_m=settle_m, **extra)

    nav.go_to = go_to
    return left


async def doorway(root: Path, echo: bool) -> tuple:
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1700.0, 600.0)], choices=[{"choose": "wait"}], rooms=True)
    out = {}
    try:
        left = stuck_nav(play, 1)
        await play.scene.say("Ina", "Go to the kitchen.")
        await play.scene.until_idle(200.0, 2.0)
        await play.scene.run(25.0)
        await play.scene.until_idle(200.0, 2.0)
        pose = play.scene.world.pose
        out["kitchen"] = ((pose.x / 1000.0 - KITCHEN[0]) ** 2 + (pose.y / 1000.0 - KITCHEN[1]) ** 2) ** 0.5
        out["said"] = play.said()
        out["calls"] = left["calls"]
        out["what_now"] = [text for purpose, text in mind.asked if purpose == "unstuck"]
        out["unstuck"] = records(play, "unstuck", "unstuck_outcome")
        out["kept"] = play.scene.store.read_lines("outcomes.jsonl")
    finally:
        await play.close()
    return play, out


async def three_tries(root: Path, echo: bool) -> tuple:
    choices = [{"choose": "wait"}, {"choose": "ask", "who": "ina"}, {"choose": "another_way"}, {"choose": "wait"}]
    play, mind = await staged(root, echo, [Who("Ina", TRUSTED, 1700.0, 600.0)], choices=choices, rooms=True)
    out = {}
    try:
        left = stuck_nav(play, 10)
        await play.scene.say("Ina", "Go to the kitchen.")
        for _ in range(8):
            await play.scene.until_idle(200.0, 2.0)
            await play.scene.run(35.0)
        out["said"] = play.said()
        out["calls"] = left["calls"]
        out["what_now"] = [text for purpose, text in mind.asked if purpose == "unstuck"]
        out["unstuck"] = records(play, "unstuck", "unstuck_outcome")
        out["kept"] = play.scene.store.read_lines("outcomes.jsonl")
        out["left_choices"] = list(mind.choices)
    finally:
        await play.close()
    return play, out


TRYING = {
    "dance": dance,
    "spin_come": spin_come,
    "push_ball": push_ball,
    "refused_step": refused_step,
    "refused_midway": refused_midway,
    "stop_try": stop_try,
    "tv_laugh": tv_laugh,
    "silence": silence,
    "stranger_yes": stranger_yes,
    "out_of_ideas": out_of_ideas,
    "not_like_that": not_like_that,
    "other_body": other_body,
    "worded": worded,
    "doorway": doorway,
    "three_tries": three_tries,
    "long_talk": long_talk,
}
