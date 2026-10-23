import argparse
import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ..life.scene import LaterScene, who
from ..people.trust import TRUSTED
from ..sim.world import SimThing
from .book import STARTERS
from .check import read

UTC = timezone.utc
PEOPLE = [who("Alex", TRUSTED, 1300.0, 0.0), who("Ina", TRUSTED, 1600.0, 600.0)]
LOUNGE_ROOMS = {"lounge": (2.5, 0.0, 1.4), "kitchen": (4.2, 2.2, 0.9), "study": (4.2, -2.2, 0.9), "hall": (0.8, 1.8, 0.7), "bathroom": (6.5, 1.9, 1.0), "bedroom": (6.5, -1.9, 1.0)}
KEYS = SimThing("keys", 1700.0, -500.0, width_mm=120.0, depth_mm=60.0, height_mm=40.0, slow="keys", track=107)


class ScriptScene(LaterScene):
    def __init__(self, root: Path, at: datetime, people=None, echo: bool = False):
        super().__init__(root, people or PEOPLE, at, {}, echo=echo, rooms=LOUNGE_ROOMS)
        self.scene.extra = {"script_engine": "local"}
        self.scene.things = list(self.scene.things or []) + [SimThing(KEYS.name, KEYS.x, KEYS.y, width_mm=KEYS.width_mm, depth_mm=KEYS.depth_mm, height_mm=KEYS.height_mm, slow=KEYS.slow, track=KEYS.track)]

    @property
    def scripts(self):
        return self.life.scripts

    async def deploy(self, stem: str) -> dict:
        source = (STARTERS / f"{stem}.py").read_text(encoding="utf-8")
        checked = read(source)
        person = self.life.company.book.find(checked.header.for_) if checked.header.for_ else None
        entry = self.scripts.book.add(stem.replace("_", " "), source, checked.header.as_dict(), person.id if person is not None else None, person.label if person is not None else "", person.id if person is not None else None, "", True)
        self.life.household.planner.enabled = False
        self.trace(f"the program {entry['name']} goes live")
        await self.scripts.go_live(entry)
        await self.scene.run(1.0)
        return entry

    def entry(self, name: str) -> dict | None:
        return self.scripts.book.get(name)

    def diary(self) -> list[str]:
        return [str(e.get("text")) for e in self.scene.store.read_lines("diary.jsonl")]

    async def cat_through(self, times: int, gap_s: float = 600.0) -> None:
        cat = self.scene.world.thing("cat")
        for _ in range(times):
            cat.home, cat.x, cat.y = True, 3300.0, 200.0
            self.trace("the cat walks through the lounge")
            await self.scene.run(6.0)
            cat.home = False
            await self.skip(gap_s, 60.0)


async def cat_counter(show: ScriptScene) -> dict:
    show.scene.world.thing("cat").home = False
    entry = await show.deploy("cat_counter")
    await show.skip(120.0, 30.0)
    await show.cat_through(4)
    await show.skip_to(datetime(2026, 10, 21, 21, 1, tzinfo=UTC))
    await show.scene.run(10.0)
    return {"said": show.said(), "status": entry["status"], "kept": show.scripts.book.state(entry)}


async def plant_reminder(show: ScriptScene) -> dict:
    entry = await show.deploy("plant_reminder")
    await show.skip_to(datetime(2026, 10, 19, 9, 1, tzinfo=UTC))
    await show.scene.run(10.0)
    return {"said": show.said(), "status": entry["status"]}


async def tag_game(show: ScriptScene) -> dict:
    entry = await show.deploy("tag_game")
    await show.scene.run(5.0)
    await show.scene.say("Alex", "Go!")
    await show.scene.until_idle(240.0, 1.0)
    await show.scene.run(5.0)
    await show.scene.say("Alex", "That's enough now.")
    await show.scene.run(10.0)
    return {"said": show.said(), "status": entry["status"]}


async def simon_says(show: ScriptScene) -> dict:
    entry = await show.deploy("simon_says")
    await show.scene.run(60.0)
    return {"said": show.said(), "status": entry["status"]}


async def quiz(show: ScriptScene) -> dict:
    entry = await show.deploy("quiz")
    answers = ["Eight!", "Green", "Saturn?", "Seven", "Honey"]
    for answer in answers:
        await show.scene.run(6.0)
        await show.scene.say("Alex", answer)
    await show.scene.run(10.0)
    return {"said": show.said(), "status": entry["status"]}


async def treasure_hunt(show: ScriptScene) -> dict:
    entry = await show.deploy("treasure_hunt")
    ball = show.scene.world.thing("ball")
    ball.x, ball.y = 4200.0, 2000.0
    show.trace("Alex hides the ball in the kitchen")
    await show.scene.run(40.0)
    for _ in range(40):
        if entry["status"] != "trial" and entry["status"] != "live":
            break
        await show.scene.run(15.0)
    return {"said": show.said(), "status": entry["status"]}


async def morning_hello(show: ScriptScene) -> dict:
    entry = await show.deploy("morning_hello")
    show.scene.leave("Alex")
    show.scene.leave("Ina")
    await show.skip(1200.0, 120.0)
    show.scene.arrive("Alex", 1.3, 0.2)
    show.seen()
    await show.scene.run(10.0)
    return {"said": show.said(), "status": entry["status"]}


async def evening_patrol(show: ScriptScene) -> dict:
    entry = await show.deploy("evening_patrol")
    await show.skip_to(datetime(2026, 10, 21, 20, 0, 30, tzinfo=UTC))
    await show.scene.until_idle(900.0, 5.0)
    await show.scene.run(5.0)
    notes = [e for e in show.scene.store.read_lines("journal.jsonl") if e.get("kind") == "script_note"]
    return {"said": show.said(), "notes": notes, "status": entry["status"]}


async def dance_loop(show: ScriptScene) -> dict:
    entry = await show.deploy("dance_loop")
    show.life.p.inner.mood.valence = 0.9
    await show.scene.run(3.0)
    turns = 0
    for _ in range(60):
        await show.scene.run(2.0)
        turns = len([a for a, _ in show.life.commands.runner.history if a.kind == "turn"])
        if turns >= 9:
            break
    return {"turns": turns, "status": entry["status"]}


async def score_keeper(show: ScriptScene) -> dict:
    entry = await show.deploy("score_keeper")
    for line in ("Point to Sam.", "Point to Ina.", "Point to Sam!", "Final score."):
        await show.scene.run(4.0)
        await show.scene.say("Alex", line)
    await show.scene.run(5.0)
    return {"said": show.said(), "status": entry["status"]}


async def story_time(show: ScriptScene) -> dict:
    entry = await show.deploy("story_time")
    await show.scene.run(60.0)
    return {"said": show.said(), "status": entry["status"]}


async def find_keys(show: ScriptScene) -> dict:
    entry = await show.deploy("find_keys")
    await show.scene.until_idle(120.0, 1.0)
    await show.scene.run(5.0)
    await show.scene.say("Alex", "Where are my keys?")
    await show.scene.run(5.0)
    return {"said": show.said(), "status": entry["status"], "kept": show.scripts.book.state(entry)}


async def red_light(show: ScriptScene) -> dict:
    entry = await show.deploy("red_light")
    await show.scene.run(70.0)
    return {"said": show.said(), "status": entry["status"]}


async def visit_counter(show: ScriptScene) -> dict:
    entry = await show.deploy("visit_counter")
    for name in ("Ina", "Alex", "Ina"):
        show.scene.leave(name)
        await show.skip(900.0, 120.0)
        show.scene.arrive(name, 1.5, 0.3)
        show.seen()
        await show.scene.run(5.0)
    await show.skip_to(datetime(2026, 10, 21, 22, 1, tzinfo=UTC))
    await show.scene.run(5.0)
    notes = [e for e in show.scene.store.read_lines("journal.jsonl") if e.get("kind") == "script_note"]
    return {"notes": notes, "status": entry["status"], "kept": show.scripts.book.state(entry)}


async def check_in(show: ScriptScene) -> dict:
    entry = await show.deploy("check_in")
    await show.skip_to(datetime(2026, 10, 21, 18, 0, 30, tzinfo=UTC))
    await show.scene.run(4.0)
    await show.scene.say("Alex", "It was good, thanks.")
    await show.scene.run(5.0)
    return {"said": show.said(), "status": entry["status"]}


DAY = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
SCENES = {
    "cat_counter": (cat_counter, DAY),
    "plant_reminder": (plant_reminder, datetime(2026, 10, 19, 8, 0, tzinfo=UTC)),
    "tag_game": (tag_game, DAY),
    "simon_says": (simon_says, DAY),
    "quiz": (quiz, DAY),
    "treasure_hunt": (treasure_hunt, DAY),
    "morning_hello": (morning_hello, datetime(2026, 10, 21, 7, 0, tzinfo=UTC)),
    "evening_patrol": (evening_patrol, datetime(2026, 10, 21, 19, 30, tzinfo=UTC)),
    "dance_loop": (dance_loop, DAY),
    "score_keeper": (score_keeper, DAY),
    "story_time": (story_time, DAY),
    "find_keys": (find_keys, DAY),
    "red_light": (red_light, DAY),
    "visit_counter": (visit_counter, DAY),
    "check_in": (check_in, datetime(2026, 10, 21, 17, 30, tzinfo=UTC)),
}


async def play(name: str, root: Path | None = None, echo: bool = False) -> tuple[ScriptScene, dict]:
    holder = None
    if root is None:
        holder = tempfile.TemporaryDirectory(prefix="pebble-script-scene-")
        root = Path(holder.name) / "self"
    script, at = SCENES[name]
    show = ScriptScene(root, at, echo=echo)
    try:
        await show.setup()
        result = await script(show)
    finally:
        await show.close()
        if holder is not None:
            holder.cleanup()
    return show, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.script.scene", description="Play a sim day with one of the starter programs live and print what happened")
    parser.add_argument("--scene", choices=sorted(SCENES), default="cat_counter")
    args = parser.parse_args(argv)
    _, result = asyncio.run(play(args.scene, echo=True))
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
