import json
import math
from datetime import datetime, timezone

import pytest
from conftest import run

from pebble.activities.gate import Asker, Running, Situation, decide
from pebble.activities.tools import register_activity_tools
from pebble.people.trust import FRIEND, TRUSTED
from pebble.seams.sight import SeenThing, Sight
from pebble.sim.eyes import SimEyes
from pebble.sim.scene import Scene, Who, household
from pebble.sim.world import Pose, SimThing, World, room
from pebble.things.book import ThingBook, age_words
from pebble.things.watch import ThingWatcher
from pebble.things.words import canonical, is_animal, matches, spoken, with_article
from pebble.tools.registry import ToolRegistry
from pebble.understand.context import context_from
from pebble.understand.request import Request
from pebble.understand.rules import parse

DAY = 86400.0


def test_spoken_words_map_to_the_labels_the_eyes_use():
    assert canonical("the sofa") == "couch"
    assert canonical("my car keys") == "key"
    assert canonical("Slippers") == "slipper"
    assert canonical("kitty") == "cat" and is_animal("puppy")
    assert canonical("glasses") == "glasses" and canonical("news") == "news"
    assert matches("ball", "tennis ball") and matches("chair", "armchair") is False and matches("chair", "chair")
    assert matches("remote", "remote control") and not matches("cat", "catalogue")
    assert spoken("tennis ball") == "tennis ball" and spoken("tv") == "TV"
    assert with_article("apple") == "an apple" and with_article("glasses") == "some glasses"


def test_memory_answers_where_and_when_honestly():
    book = ThingBook({})
    assert book.answer("ball", 1000.0) == "I haven't seen a ball. I'll keep an eye out."
    book.note("couch", 900.0, "front", 2.2, 1.1, 1.0, [], 0.8, "fast", False)
    book.note("tennis ball", 700.0, "front", 2.0, 0.6, 0.6, ["couch"], 0.62, "slow", False)
    assert book.answer("ball", 1000.0) == "I saw a tennis ball near the couch about 5 minutes ago."
    book.note("slipper", 990.0, "front", None, None, 0.5, [], 0.4, "slow", False)
    assert book.answer("slipper", 1000.0) == "I think I saw a slipper a moment ago, but I'm not sure where."
    book.note("cat", 0.0, "front", 0.2, 0.1, 1.0, [], 0.8, "fast", True)
    assert book.answer("kitty", 1000.0).endswith("could be anywhere by now.") and "by my charger" in book.answer("cat", 1000.0)
    book.note("key", 0.0, "front", 3.5, -1.2, 1.0, [], 0.8, "slow", False)
    assert book.answer("keys", 2 * DAY).endswith("so it may have moved since.")
    assert age_words(30) == "a moment ago" and age_words(400) == "about 7 minutes ago" and age_words(4000) == "about an hour ago"


def test_memory_merges_nearby_sightings_keeps_a_few_places_and_fades():
    book = ThingBook({})
    first = book.note("ball", 0.0, "front", 1.0, 1.0, 0.5, [], 0.8, "fast", False)
    again = book.note("ball", 10.0, "front", 1.2, 1.1, 0.5, [], 0.8, "fast", False)
    moved = book.note("ball", 20.0, "front", 3.0, -1.0, 0.5, [], 0.8, "fast", False)
    assert first.new_kind and not again.new_place and moved.new_place
    assert len(book.things["ball"].spots) == 2
    for index in range(6):
        book.note("ball", 30.0 + index, "front", float(index) * 2, 5.0, 0.5, [], 0.8, "fast", False)
    assert len(book.things["ball"].spots) == 4
    book.note("cup", 0.0, "front", 0.0, 0.0, 0.5, [], 0.8, "fast", False)
    assert book.prune(31 * DAY) > 0 and "cup" not in book.things
    restored = ThingBook(json.loads(json.dumps(book.to_dict())))
    assert restored.answer("ball", 40.0) == book.answer("ball", 40.0)


def test_the_book_lives_in_the_self_with_the_other_books(rig_factory):
    rig = rig_factory()
    assert "things.json" in rig.store.manifest["files"]
    rig.books.things.note("plant pot", rig.clock.now(), "front", 1.0, 0.0, 1.0, [], 0.7, "slow", False)
    rig.life.save(clean=False)
    assert "plant pot" in json.dumps(rig.store.read("things.json"))


def test_the_watcher_notes_new_kinds_and_things_in_new_places_and_animals():
    world = World(table=room(), pose=Pose(500.0, 0.0, 0.0), things=[SimThing("ball", 1500.0, 0.0, width_mm=200.0, depth_mm=200.0, height_mm=200.0, fast="ball", track=1)])
    clock = [100.0]
    eyes = SimEyes(world, lambda: clock[0], lambda: 8.0, noise=False)

    class Odo:
        usable = True

        def pose(self):
            return world.pose.x / 1000.0, world.pose.y / 1000.0, math.degrees(world.pose.heading)

    book = ThingBook({})
    watcher = ThingWatcher(book, eyes, Odo(), tilt=lambda: 8.0, monotonic=lambda: clock[0])
    seen = watcher.look()
    assert [(s.label, s.kind, s.where) for s in seen] == [("ball", "new", "ahead of you")]
    spot = book.things["ball"].last
    assert spot.x == pytest.approx(1.4, abs=0.1) and spot.y == pytest.approx(0.0, abs=0.05)
    clock[0] += 10.0
    assert watcher.look() == []
    world.things[0].x, world.things[0].y = 3500.0, 0.0
    clock[0] += 10.0
    assert [s.kind for s in watcher.look()] == ["moved"]
    assert not watcher.animal_near()
    world.things.append(SimThing("cat", 2000.0, 300.0, width_mm=450.0, depth_mm=200.0, height_mm=250.0, fast="cat", animal=True, track=2))
    clock[0] += 10.0
    assert watcher.animal_near() and "cat" in watcher.in_view()


@pytest.mark.parametrize(
    "text, expect",
    [
        ("look at the ball", {"kind": "look", "thing": "ball"}),
        ("go to the chair", {"kind": "go_to_thing", "thing": "chair"}),
        ("find the cat", {"kind": "find", "thing": "cat"}),
        ("where's my slipper?", {"kind": "where_is", "thing": "slipper"}),
        ("what's that?", {"kind": "what_is"}),
        ("what can you see?", {"kind": "what_see"}),
        ("follow the cat", {"kind": "follow", "thing": "cat"}),
        ("I can't find my keys", {"kind": "chat"}),
        ("the cat is asleep", {"kind": "chat"}),
        ("don't go near the cat", {"kind": "chat"}),
        ("what's that noise?", {"kind": "chat"}),
        ("look at the time", {"kind": "chat"}),
        ("go to the kitchen", {"kind": "go_to_place", "place": "kitchen"}),
    ],
)
def test_things_in_plain_words(text, expect):
    assert parse(text, context_from({})).request.as_dict() == expect


def test_questions_and_things_through_the_gate():
    stranger = Asker("p9", "the visitor p9", "stranger")
    friend = Asker("p3", "Mo", "friend", sure=True)
    family = Asker("p4", "Ana", "friend", sure=True, family=True)
    where = decide(Request("where_is", thing="key"), stranger, Situation())
    assert where.answer == "no" and "I'd rather not say" in where.say
    assert decide(Request("where_is", thing="key"), friend, Situation()).answer == "no"
    assert decide(Request("where_is", thing="key"), family, Situation()).answer == "yes"
    assert decide(Request("what_is"), stranger, Situation()).answer == "yes"
    assert decide(Request("what_is"), friend, Situation(can_see=False)).say == "I can't see yet, so I can't tell."
    busy = Situation(running=Running("follow", "p2", "Tui", TRUSTED))
    assert decide(Request("what_see"), friend, busy).answer == "yes"
    assert decide(Request("find", thing="cat"), friend, Situation(quiet=True, can_move=False)).answer == "no"


def test_a_stranger_is_told_where_ordinary_things_are_never_keys_wallets_bags_phones_or_medicines():
    stranger = Asker("p9", "the visitor p9", "stranger")
    friend = Asker("p3", "Mo", "friend", sure=True)
    family = Asker("p4", "Ana", "friend", sure=True, family=True)
    for thing in ("remote control", "remote", "ball", "cat", "teddy bear", "slipper", "glasses", "first aid kit"):
        assert decide(Request("where_is", thing=thing), stranger, Situation()).answer == "yes", thing
    kept = ("key", "keys", "car keys", "house keys", "key ring", "wallet", "purse", "handbag", "bag", "backpack", "schoolbag", "cellphone", "cell", "phone", "ipad", "laptop", "pills", "pill", "tablets", "medicine", "medication", "meds", "inhaler", "money", "bank card", "passport", "jewellery", "ring", "watch", "gun", "toby", "water shut off", "switchboard", "grab bag", "it", "")
    for thing in kept:
        verdict = decide(Request("where_is", thing=thing), stranger, Situation())
        assert verdict.answer == "no" and verdict.say == "I'd rather not say where things are to someone I don't know yet.", thing
    for thing in ("key", "car keys", "wallet", "handbag", "cellphone", "pills", "medicine", "toby"):
        assert decide(Request("where_is", thing=thing), family, Situation()).answer == "yes", thing
    for thing in ("cellphone", "toby"):
        assert decide(Request("where_is", thing=thing), friend, Situation()).answer == "yes", thing
    for thing in ("key", "car keys", "wallet", "handbag", "pills", "medicine"):
        assert decide(Request("where_is", thing=thing), friend, Situation()).answer == "no", thing
    assert decide(Request("find", thing="remote control"), stranger, Situation()).answer == "yes"
    assert decide(Request("find", thing="wallet"), stranger, Situation()).say == "Sorry, I only look for that for the people who live here."
    assert decide(Request("go_to_thing", thing="key"), stranger, Situation()).answer == "no"
    assert decide(Request("find", thing="wallet"), friend, Situation()).answer == "no"
    assert decide(Request("find", thing="wallet"), family, Situation()).answer == "yes"


def test_told_house_facts_stay_with_the_household_except_what_helps_someone_hurt():
    book = ThingBook({})
    book.tell("toby", "under the laundry sink", "p1", "Ina", 0.0)
    book.tell("first aid kit", "in the bathroom cupboard", "p1", "Ina", 0.0)
    book.tell("torch", "in the hall drawer", "p1", "Ina", 0.0)
    book.note("remote control", 900.0, "front", 2.0, 0.6, 0.6, [], 0.8, "slow", False)
    book.note("key", 900.0, "front", 1.0, 0.2, 0.6, [], 0.8, "slow", False)
    no = "I'd rather not say where things are to someone I don't know yet."
    assert book.answer("toby", 1000.0) == "Ina told me the water shut-off is under the laundry sink."
    assert book.answer("toby", 1000.0, stranger=True) == no
    assert book.answer("torch", 1000.0, stranger=True) == no
    assert book.answer("first aid kit", 1000.0, stranger=True) == "Ina told me the first aid kit is in the bathroom cupboard."
    assert book.answer("remote", 1000.0, stranger=True).startswith("I saw a remote control")
    assert book.answer("car keys", 1000.0, stranger=True) == no
    assert book.answer("keys", 1000.0).startswith("I saw a key")
    assert "follow the cat" in decide(Request("follow", thing="cat"), Asker("p2", "Tui", TRUSTED, sure=True), Situation()).say


async def staged(tmp_path, **options) -> Scene:
    scene = Scene(tmp_path / "self", things=options.pop("things", household()), **options)
    await scene.setup()
    return scene


def said(scene):
    return "\n".join(line for line in scene.lines if " says " in line)


def thought(scene):
    return "\n".join(line for line in scene.lines if " thinks " in line)


def test_find_turns_looks_closely_and_names_what_it_found(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, start=(1800.0, 100.0, 90.0))
        await scene.say("Ina", "can you find the ball")
        await scene.until_idle(90.0)
        await scene.say("Ina", "what's that?")
        looks = scene.eyes.close_looks
        await scene.close()
        return scene, looks

    scene, looks = run(scenario(), timeout=90)
    assert "There's the ball!" in said(scene)
    assert "That's a tennis ball." in said(scene)
    assert looks >= 2


def test_find_gives_up_and_says_where_it_last_saw_it(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, start=(1800.0, 100.0, 0.0))
        scene.books.things.note("slipper", scene.clock.now() - 300.0, "front", 2.0, 0.6, 0.6, ["couch"], 0.6, "slow", False)
        scene.world.thing("slipper").home = False
        await scene.say("Ina", "go find my slipper")
        await scene.until_idle(120.0)
        await scene.close()
        return scene

    scene = run(scenario(), timeout=90)
    assert "I looked all around but I can't see the slipper. I saw a slipper near the couch about" in said(scene)


def test_go_to_a_thing_stops_short_and_never_near_an_animal(tmp_path):
    async def scenario():
        things = [
            SimThing("chair", 2400.0, 0.0, width_mm=500.0, depth_mm=500.0, height_mm=900.0, fast="chair", track=1),
            SimThing("cat", 2400.0, -1200.0, width_mm=450.0, depth_mm=200.0, height_mm=250.0, fast="cat", animal=True, track=2),
        ]
        scene = await staged(tmp_path, start=(1000.0, -300.0, 0.0), things=things)
        await scene.say("Ina", "go over to the chair")
        await scene.until_idle(120.0)
        chair = scene.world.thing("chair")
        to_chair = math.hypot(chair.x - scene.world.pose.x, chair.y - scene.world.pose.y) / 1000.0 - 0.1 - chair.depth_mm / 2000.0
        await scene.say("Ina", "now go say hi to the cat")
        await scene.until_idle(120.0)
        cat = scene.world.thing("cat")
        to_cat = math.hypot(cat.x - scene.world.pose.x, cat.y - scene.world.pose.y) / 1000.0 - 0.1 - cat.depth_mm / 2000.0
        await scene.close()
        return scene, to_chair, to_cat

    scene, to_chair, to_cat = run(scenario(), timeout=120)
    assert "Here's the chair." in said(scene)
    assert 0.15 < to_chair < 0.5
    assert "Hello, cat. I'll stay back a little." in said(scene)
    assert to_cat >= 0.7


def test_a_cat_crossing_while_following_makes_pebble_slow_and_wait(tmp_path):
    async def scenario():
        cat = SimThing("cat", 1650.0, -1300.0, width_mm=450.0, depth_mm=200.0, height_mm=250.0, fast="cat", animal=True, track=9)
        scene = await staged(tmp_path, things=[cat])
        await scene.say("Ina", "follow me")
        scene.walk("Ina", (2.4, 0.3), speed_mm_s=45.0)
        await scene.run(12.0)
        scene.move_thing("cat", (1.65, 1.3), speed_mm_s=110.0)
        closest = math.inf
        for _ in range(200):
            await scene.run(0.15)
            pose = scene.world.pose
            ahead = (cat.x - pose.x) * math.cos(pose.heading) + (cat.y - pose.y) * math.sin(pose.heading)
            side = abs(-(cat.x - pose.x) * math.sin(pose.heading) + (cat.y - pose.y) * math.cos(pose.heading))
            if ahead > 0 and side < 250.0:
                closest = min(closest, ahead / 1000.0)
        await scene.close()
        return scene, closest

    scene, closest = run(scenario(), timeout=90)
    assert "the cat is close ahead, so you slowed right down" in thought(scene)
    assert closest > 0.45


def test_an_animal_alone_counts_like_a_person_for_the_speed_caps(tmp_path):
    async def scenario():
        cat = SimThing("cat", 1500.0, 0.0, width_mm=450.0, depth_mm=200.0, height_mm=250.0, fast="cat", animal=True, track=9)
        scene = await staged(tmp_path, people=[], things=[cat], start=(500.0, 0.0, 0.0))
        near_with_cat = scene.life.beings_near()
        cat.home = False
        await scene.run(10.0)
        near_without = scene.life.beings_near()
        await scene.close()
        return near_with_cat, near_without

    near_with_cat, near_without = run(scenario(), timeout=60)
    assert near_with_cat and not near_without


def test_what_can_you_see_and_unsure_answers(tmp_path):
    async def scenario():
        things = [
            SimThing("cat", 1800.0, 200.0, width_mm=450.0, depth_mm=200.0, height_mm=250.0, fast="cat", animal=True, track=1),
            SimThing("couch", 2600.0, -500.0, width_mm=1800.0, depth_mm=700.0, height_mm=800.0, fast="couch", track=2),
        ]
        scene = await staged(tmp_path, start=(800.0, 0.0, 0.0), things=things)
        await scene.say("Ina", "what can you see?")
        for thing in scene.world.things:
            thing.home = False
        await scene.say("Ina", "what's that?")
        await scene.close()
        return scene

    scene = run(scenario(), timeout=60)
    assert "I can see you, a cat and a couch." in said(scene)
    assert "I'm not sure what that is." in said(scene)


def test_where_is_answers_from_memory_and_strangers_are_told_no(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, people=[Who("Ina", TRUSTED, 1300.0, 0.0), Who("Rua", None, 900.0, 900.0)])
        scene.books.things.note("key", scene.clock.now() - 120.0, "front", 1.5, -1.0, 0.6, [], 0.7, "slow", False)
        await scene.say("Ina", "have you seen my keys?")
        await scene.say("Rua", "where are the keys?")
        await scene.close()
        return scene

    scene = run(scenario(), timeout=60)
    assert "I saw a key about 2 metres from my charger about 2 minutes ago." in said(scene)
    assert "I'd rather not say where things are to someone I don't know yet." in said(scene)


def test_a_stranger_is_told_where_the_remote_is_but_not_the_keys_wallet_or_pills(tmp_path):
    async def scenario():
        scene = await staged(tmp_path, people=[Who("Mo", FRIEND, 1300.0, 0.0), Who("Rua", None, 900.0, 900.0)])
        for label in ("remote control", "key", "wallet", "bag", "phone", "pill"):
            scene.books.things.note(label, scene.clock.now() - 120.0, "front", 1.5, -1.0, 0.6, [], 0.7, "slow", False)
        await scene.say("Rua", "where's the remote?")
        for asked in ("where are the car keys?", "where's the wallet?", "where's my handbag?", "where's my cellphone?", "where are the pills?", "where's the medicine?"):
            await scene.say("Rua", asked)
        await scene.say("Mo", "where are my keys?")
        registry = ToolRegistry()
        register_activity_tools(registry, scene.life.commands)
        scene.memory = [(await registry.call("recall_thing", {"thing": thing}))["memory"] for thing in ("car keys", "remote")]
        await scene.close()
        return scene

    scene = run(scenario(), timeout=90)
    assert scene.memory[0] == "someone you don't know is here, so keep where that is to yourself for now"
    assert scene.memory[1].startswith("I saw a remote control")
    lines = [line for line in scene.lines if " says " in line]
    assert any("I saw a remote control" in line for line in lines)
    assert sum("I'd rather not say where things are to someone I don't know yet." in line for line in lines) == 6
    assert any("Sorry, I only say where that is to the family or people I know really well." in line for line in lines)
    assert not any("I saw a key" in line for line in lines)
    assert not any("I saw a wallet" in line or "I saw a bag" in line or "I saw a phone" in line or "I saw a pill" in line for line in lines)


def test_a_new_thing_makes_pebble_curious_but_not_at_night_or_when_busy(tmp_path):
    async def scenario(at, busy):
        things = [SimThing("plant pot", 2000.0, 0.0, width_mm=300.0, depth_mm=300.0, height_mm=300.0, slow="plant pot", track=1)]
        scene = await staged(tmp_path / f"{at.hour}{busy}", start=(1000.0, 0.0, 0.0), things=things, people=[Who("Ina", TRUSTED, 1000.0, 1200.0)], at=at)
        if busy:
            await scene.say("Ina", "wait here")
        await scene.run(70.0)
        current = scene.life.commands.runner.current
        events = [item.text for item in scene.life.events.peek()]
        await scene.close()
        return scene, current, events

    day = datetime(2026, 10, 15, 11, 0, tzinfo=timezone.utc)
    night = datetime(2026, 10, 15, 23, 0, tzinfo=timezone.utc)
    scene, _, events = run(scenario(day, False), timeout=60)
    assert any("something new on camera: a plant pot" in text for text in events)
    assert "You decided to go to the plant pot; you said yes" in thought(scene)
    scene, _, _ = run(scenario(night, False), timeout=60)
    assert "You decided" not in thought(scene)
    scene, current, _ = run(scenario(day, True), timeout=60)
    assert current is not None and current.kind == "wait" and "You decided" not in thought(scene)


def test_eyes_are_told_when_the_mind_is_busy(rig_factory):
    calls = []

    class BusyEyes:
        available = True

        def latest(self, max_age_s=0.5):
            return Sight(0.0, "front", 70.0, things=(SeenThing("cup", 0.0, -5.0, 0.1, 0.05, 0.9, 0.0),))

        async def use_camera(self, camera):
            return True

        def camera(self):
            return "front"

        def set_busy(self, busy):
            calls.append(busy)

    rig = rig_factory()
    rig.life.p.eyes = BusyEyes()
    rig.life.watcher.eyes = rig.life.p.eyes
    rig.life._mind_ready = True
    run(rig.life.read_sensors())
    rig.life.wake = "a note"
    run(rig.life.beat())
    assert calls == [True, False]
    observation = [r for r in rig.mind.requests if r["purpose"] == "turn"][0]["messages"][-1]["content"]
    assert "You can see: cup." in observation
