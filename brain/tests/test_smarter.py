import math

import pytest
from conftest import run

from pebble.activities.hazards import someone_low, steer
from pebble.activities.picture import PictureQuestions, picture_message
from pebble.activities.seeing import animal_gap, animals_ahead, camera_fov_deg, life_ahead, view_cone_deg
from pebble.alive.book import AliveBook
from pebble.body.profile import BodyProfile, resolve_profile
from pebble.alive.caring import eating, late_night
from pebble.mind.base import Mind, MindReply
from pebble.mind.llama import LlamaServerMind, fold_system
from pebble.mind.profile import ModelProfile
from pebble.people.trust import TRUSTED
from pebble.seams.sight import SeenPerson, SeenThing, Sight
from pebble.sim.scene import Scene, Who, household
from pebble.sim.world import SimThing
from pebble.understand.context import Context
from pebble.understand.rules import parse


def floor_thing(label, floor_m, bearing=0.0, animal=False):
    return SeenThing(label, bearing, -20.0, 0.1, 0.1, 0.8, 0.0, "slow", animal, None, False, None, 0.0, floor_m, bearing)


def sight(*things, people=()):
    return Sight(0.0, "front", 70.0, tuple(people), (), tuple(things))


class SeeingMind(Mind):
    name = "seeing"

    def __init__(self, answer="Yes, the back door is open.", vision=True):
        self.answer = answer
        self.vision = vision
        self.messages = []

    async def sees(self) -> bool:
        return self.vision

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None) -> MindReply:
        self.messages.append(messages)
        return MindReply(self.answer)


class Snapper:
    available = True

    def __init__(self, picture=b"\xff\xd8jpeg\xff\xd9"):
        self.picture = picture
        self.asked = []

    async def snapshot(self, max_side=768, camera=None):
        self.asked.append((max_side, camera))
        return self.picture


def test_questions_about_what_it_sees_are_understood():
    ctx = Context()
    for line in ("Is the back door open?", "what colour is this?", "What does this say?", "can you read this for me", "how many cups are on the table?", "is anyone at the door?", "is the oven still on?"):
        assert parse(line, ctx).request.kind == "sight_question", line
    for line in ("Is the cat asleep?", "are you on?", "is it raining tomorrow?", "is Ina home?"):
        assert parse(line, ctx).request.kind != "sight_question", line


def test_a_picture_question_sends_one_picture_and_keeps_nothing():
    mind, eyes = SeeingMind(), Snapper()
    pictures = PictureQuestions(eyes, mind, max_side=512)
    answer, sure = run(pictures.ask("Is the back door open?"))
    assert (answer, sure) == ("Yes, the back door is open.", True)
    assert eyes.asked == [(512, None)]
    sent = mind.messages[0][-1]["content"]
    assert sent[0] == {"type": "text", "text": "Is the back door open?"}
    assert sent[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "can't tell" in mind.messages[0][0]["content"]
    assert not any(isinstance(v, (bytes, bytearray)) for v in vars(pictures).values())
    assert run(PictureQuestions(eyes, SeeingMind(vision=False)).ask("What colour is this?")) == ("I can't look at pictures closely just now.", False)
    assert run(PictureQuestions(Snapper(None), SeeingMind()).ask("What colour is this?")) == ("I can't get a clear look just now.", False)
    assert run(PictureQuestions(eyes, SeeingMind("It's hard to tell from this angle.")).ask("What colour is this?")) == ("I can't tell from here.", False)
    assert run(PictureQuestions(eyes, SeeingMind("She looks old and tired.")).ask("Who is that?")) == ("I can't tell from here.", False)
    assert run(PictureQuestions(eyes, SeeingMind("No, it's shut.")).yes("Is the door open?")) is False
    assert run(PictureQuestions(eyes, SeeingMind("Yes.")).yes("Is the bowl empty?")) is True


def test_the_llama_mind_checks_for_eyes_and_folds_pictures_safely():
    mind = LlamaServerMind(ModelProfile.from_dict({"name": "main", "endpoint": "http://127.0.0.1:1"}))
    mind._get = lambda path, timeout: (200, {"modalities": {"vision": True, "audio": False}})
    assert run(mind.sees())
    mind._vision = None
    mind._get = lambda path, timeout: (200, {"modalities": {"vision": False}})
    assert not run(mind.sees())
    folded = fold_system([{"role": "system", "content": "Be brief."}, picture_message("What is it?", b"x")])
    assert folded[0]["content"][0] == {"type": "text", "text": "Be brief."} and folded[0]["content"][2]["type"] == "image_url"


def test_floor_hazards_are_steered_round_and_the_target_is_not_one():
    forward, turn, avoided = steer(sight(floor_thing("cable", 0.6, bearing=5.0)), 0.4, 0.0)
    assert avoided == "cable" and forward <= 0.22 and turn > 0.0
    forward, turn, avoided = steer(sight(floor_thing("sock", 0.2, bearing=-5.0)), 0.4, 0.0)
    assert avoided == "sock" and forward == 0.0 and turn < 0.0
    assert steer(sight(floor_thing("ball", 0.5)), 0.4, 0.0, exempt="ball")[2] is None
    assert steer(sight(floor_thing("cable", 0.6, bearing=40.0)), 0.4, 0.0)[2] is None
    assert steer(sight(floor_thing("couch", 0.6)), 0.4, 0.0)[2] is None
    assert steer(sight(floor_thing("cable", 0.6)), -0.3, 0.0)[2] is None


def test_someone_low_on_the_floor_makes_pebble_creep():
    crawling = SeenPerson(0.0, -10.0, 0.3, 0.4, 0.9, True, 1, posture="crouching", posture_score=0.7)
    standing = SeenPerson(0.0, 10.0, 0.6, 0.2, 0.9, True, 2, posture="standing", posture_score=0.9)
    assert someone_low(sight(people=(crawling,)))
    assert not someone_low(sight(people=(standing,)))


def test_dogs_get_more_room_than_cats():
    assert animal_gap("dog") > animal_gap("cat") >= 0.8


def test_animal_caution_covers_the_whole_camera_view():
    def seen(fov, *things, camera="front"):
        return Sight(0.0, camera, fov, (), (), tuple(things))

    edge = floor_thing("cat", 1.0, bearing=38.0, animal=True)
    other_edge = floor_thing("cat", 1.0, bearing=-38.0, animal=True)
    assert len(animals_ahead(seen(80.0, edge, other_edge), 8.0)) == 2
    assert animals_ahead(seen(70.0, edge), 8.0) == []
    assert animals_ahead(seen(80.0, floor_thing("cat", 1.0, bearing=45.0, animal=True)), 8.0) == []
    assert animals_ahead(seen(80.0, floor_thing("cat", 1.0, animal=True), camera="rear"), 8.0) == []
    assert len(animals_ahead(seen(60.0, floor_thing("cat", 1.0, bearing=34.0, animal=True)), 8.0)) == 1
    assert len(life_ahead(seen(80.0, floor_thing("snail", 0.5, bearing=38.0)), 8.0)) == 1
    pixel = BodyProfile.load(resolve_profile("android", "body"))
    assert view_cone_deg(camera_fov_deg(None, pixel)) == pytest.approx(81.1 / 2.0)
    assert view_cone_deg(None) == 35.0 and view_cone_deg(60.0) == 35.0


def test_remembered_animals_are_watched_across_the_camera_view_and_never_narrower():
    from types import SimpleNamespace

    from pebble.nav.navigator import ANIMAL_SIDE_RAD, Navigator

    def side(eyes, profile):
        return math.degrees(Navigator.animal_side(SimpleNamespace(eyes=eyes, body=SimpleNamespace(profile=profile))))

    pixel = BodyProfile.load(resolve_profile("android", "body"))
    assert side(None, pixel) == pytest.approx(math.degrees(ANIMAL_SIDE_RAD))
    assert side(None, None) == pytest.approx(math.degrees(ANIMAL_SIDE_RAD))
    assert side(SimpleNamespace(cameras={"front": {"fov_h_deg": 150.0}}), pixel) == pytest.approx(75.0)


def test_pets_eating_and_late_nights_are_recognised():
    assert eating(sight(floor_thing("bowl", 1.0), floor_thing("cat", 1.1, animal=True))) == "cat"
    assert eating(sight(floor_thing("bowl", 1.0), floor_thing("cat", 2.5, animal=True))) is None
    assert late_night(23) and late_night(2) and not late_night(21)


def test_people_are_looked_for_where_they_usually_are():
    book = AliveBook()
    for day in range(4):
        book.met("p1", "kitchen", day * 86400.0)
    book.met("p1", "lounge", 0.0)
    assert book.usual_room("p1", 4 * 86400.0) == "kitchen"
    assert book.usual_room("p2", 0.0) is None


def test_going_to_a_known_thing_out_of_view_drives_there_first(tmp_path):
    async def scenario():
        things = household() + [SimThing("lamp", 1300.0, -1400.0, width_mm=300.0, depth_mm=300.0, height_mm=1200.0, fast="lamp", track=150)]
        scene = Scene(tmp_path / "self", people=[Who("Ina", TRUSTED, 900.0, 600.0)], things=things)
        await scene.setup()
        scene.books.things.note("lamp", scene.clock.now() - 60.0, "front", 1.3, -1.4, 1.5, [], 0.8, "fast", False)
        await scene.say("Ina", "go to the lamp")
        await scene.until_idle(150.0)
        pose = scene.world.pose
        await scene.close()
        return scene, math.hypot(pose.x - 1300.0, pose.y + 1400.0)

    scene, gap = run(scenario(), timeout=120)
    noted = "\n".join(line for line in scene.lines if " thinks " in line)
    assert "you drove over to where you last saw the lamp" in noted
    assert gap < 900.0


def test_a_cable_on_the_floor_is_driven_round_in_the_sim(tmp_path):
    async def scenario():
        things = [SimThing("cable", 1100.0, 0.0, width_mm=250.0, depth_mm=60.0, height_mm=20.0, slow="cable", track=160)]
        scene = Scene(tmp_path / "self", people=[Who("Ina", TRUSTED, 2200.0, 0.0)], things=things)
        await scene.setup()
        await scene.say("Ina", "come here")
        closest = math.inf
        for _ in range(1500):
            await scene.run(0.1)
            pose = scene.world.pose
            closest = min(closest, math.hypot(pose.x - 1100.0, pose.y))
            if not scene.life.commands.runner.busy:
                break
        reached = math.hypot(scene.world.pose.x - 2200.0, scene.world.pose.y) < 1200.0
        await scene.close()
        return closest, reached

    closest, reached = run(scenario(), timeout=120)
    assert reached and closest > 150.0


@pytest.mark.parametrize("text", ["What colour is this?", "Is the back door open?"])
def test_a_picture_question_is_answered_in_the_sim_after_a_close_look(tmp_path, text):
    async def scenario():
        scene = Scene(tmp_path / "self", people=[Who("Ina", TRUSTED, 1300.0, 0.0)], things=household())
        await scene.setup()
        scene.life.commands.pictures = PictureQuestions(scene.eyes, SeeingMind("It's red."))
        await scene.say("Ina", text)
        await scene.run(2.0)
        await scene.close()
        return scene

    scene = run(scenario(), timeout=60)
    said = [line for line in scene.lines if " says " in line]
    assert any("Let me have a close look." in line for line in said) and any("It's red." in line for line in said)


def test_an_empty_bowl_at_feeding_time_is_mentioned_once_to_someone_trusted(tmp_path):
    from datetime import timedelta

    async def scenario():
        things = [
            SimThing("bowl", 1300.0, -150.0, width_mm=180.0, depth_mm=180.0, height_mm=60.0, fast="bowl", track=170),
            SimThing("cat", 1300.0, 150.0, width_mm=400.0, depth_mm=200.0, height_mm=250.0, fast="cat", animal=True, track=171),
        ]
        scene = Scene(tmp_path / "self", people=[Who("Ina", TRUSTED, 900.0, 900.0)], things=things)
        await scene.setup()
        scene.life.commands.pictures = PictureQuestions(scene.eyes, SeeingMind("Yes, it looks empty."))
        book = scene.life.alive.book
        now = scene.clock.local()
        for back in range(1, 8):
            book.saw_at("pet:eating", now - timedelta(days=back))
        await scene.run(8.0)
        await scene.run(8.0)
        await scene.close()
        return scene

    scene = run(scenario(), timeout=60)
    said = [line for line in scene.lines if " says " in line]
    assert sum("The cat's bowl looks empty" in line for line in said) == 1


def test_an_open_door_late_at_night_is_noticed_from_the_charger(tmp_path):
    from datetime import datetime, timezone

    async def scenario():
        things = [SimThing("door", 2400.0, 300.0, width_mm=900.0, depth_mm=80.0, height_mm=2000.0, slow="door", track=180)]
        scene = Scene(tmp_path / "self", people=[], things=things, at=datetime(2026, 10, 15, 23, 30, tzinfo=timezone.utc))
        await scene.setup()
        scene.life.commands.pictures = PictureQuestions(scene.eyes, SeeingMind("Yes, the door is open."))
        await scene.run(6.0)
        caring = scene.life.alive.caring
        pending = dict(caring.pending)
        await scene.close()
        return pending

    pending = run(scenario(), timeout=60)
    assert pending == {"door": "The door I can see from my charger looks open, and it's late."}


def test_spots_can_be_remembered_and_gone_back_to_once_nav_is_there(tmp_path):
    from types import SimpleNamespace

    ctx = Context()
    assert parse("remember this spot as the car", ctx).request.as_dict() == {"kind": "remember_spot", "name": "car"}
    assert parse("take me back", ctx).request.as_dict() == {"kind": "go_back", "place": "start"}
    assert parse("go back to the car", ctx).request.as_dict() == {"kind": "go_back", "place": "car"}
    assert parse("take me back to the kitchen", ctx).request.as_dict() == {"kind": "go_to_place", "place": "kitchen"}
    assert parse("go back to bed", ctx).request.kind == "go_home"

    class Nav:
        def __init__(self):
            self.spots = {}

        def remember_spot(self, name):
            self.spots[name] = (1.0, 2.0)
            return True

        async def go_back(self, kit, to="start"):
            return SimpleNamespace(ok=True, how="arrived", text=f"you retraced your way to the {to}", travelled_m=3.0)

    async def scenario():
        scene = Scene(tmp_path / "self", people=[Who("Ina", TRUSTED, 1300.0, 0.0)], things=household())
        await scene.setup()
        scene.life.commands.runner.kit.nav = None
        await scene.say("Ina", "remember this spot as the car")
        before = [line for line in scene.lines if " says " in line][-1]
        nav = Nav()
        scene.life.commands.runner.kit.nav = nav
        await scene.say("Ina", "remember this spot as the car")
        after = [line for line in scene.lines if " says " in line][-1]
        await scene.say("Ina", "go back to the car")
        await scene.until_idle(10.0)
        await scene.close()
        return scene, before, after, nav

    scene, before, after, nav = run(scenario(), timeout=60)
    assert "can't remember spots like that yet" in before
    assert "I'll remember this spot as the car" in after and "car" in nav.spots
    noted = "\n".join(line for line in scene.lines if " thinks " in line)
    assert "you retraced your way to the car" in noted
