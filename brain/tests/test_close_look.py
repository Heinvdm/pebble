import base64
import math

import pytest
from conftest import run
from test_smarter import SeeingMind, Snapper

from pebble.activities.picture import CLOSE_SIDE, CLOSE_ZOOM, PictureQuestions, wants_close
from pebble.house.pets import WATER_QUESTION
from pebble.people.trust import TRUSTED
from pebble.sim.scene import Scene, Who, household

CLOSE = b"\xff\xd8CLOSE\xff\xd9"


class Turner:
    def __init__(self, ok=True):
        self.ok = ok
        self.turns = []

    async def __call__(self, degrees):
        self.turns.append(degrees)
        return self.ok


class Closer:
    def __init__(self, picture=CLOSE):
        self.picture = picture
        self.asked = []

    def available(self):
        return True

    async def take(self, max_side, zoom):
        self.asked.append((max_side, zoom))
        return self.picture


def sent(mind):
    return base64.b64decode(mind.messages[-1][-1]["content"][1]["image_url"]["url"].split(",", 1)[1])


@pytest.mark.parametrize("question", ["What does the whiteboard say?", "What time does the clock say?", "Can you read the sign over there?", "What's written on the fridge?", "What does the calendar on the wall say?", "What's the date on the poster?"])
def test_questions_about_something_small_or_far_want_a_close_look(question):
    assert wants_close(question)


@pytest.mark.parametrize("question", ["What does this say?", "What's the use-by date on this?", "Is the back door open?", "What colour is this?", "How many cups are on the table?", "Is anyone at the door?", "Is the pet food bowl on the floor empty?", "Is the door in this picture open?", WATER_QUESTION, "is the light on"])
def test_other_picture_questions_and_pebbles_own_checks_never_turn_it_round(question):
    assert not wants_close(question)
    assert not wants_close(question + " Answer yes or no first.")


def test_a_close_look_turns_round_takes_the_back_cameras_close_up_turns_back_and_keeps_nothing():
    mind, eyes, turner, closer = SeeingMind("It says: buy milk."), Snapper(), Turner(), Closer()
    pictures = PictureQuestions(eyes, mind, closer=closer, turn=turner)
    assert run(pictures.ask("What does the whiteboard say?")) == ("It says: buy milk.", True)
    assert turner.turns == [180.0, -180.0] and closer.asked == [(CLOSE_SIDE, CLOSE_ZOOM)] and eyes.asked == []
    assert sent(mind) == CLOSE and pictures.close_how == "a close look with the back camera"
    assert not any(isinstance(v, (bytes, bytearray)) for v in vars(pictures).values())
    assert run(pictures.ask("What does this say?")) == ("It says: buy milk.", True)
    assert turner.turns == [180.0, -180.0] and eyes.asked == [(640, None)]


def test_without_a_turn_a_close_up_or_with_a_refusal_it_answers_from_where_it_is():
    mind, eyes = SeeingMind("It says hello."), Snapper()
    refused = Turner(ok=False)
    pictures = PictureQuestions(eyes, mind, closer=Closer(), turn=refused)
    assert run(pictures.ask("What does the whiteboard say?")) == ("It says hello.", True)
    assert refused.turns == [180.0] and pictures.close_how == "I could not turn round" and eyes.asked == [(640, None)]
    plain = PictureQuestions(Snapper(), mind)
    assert run(plain.ask("What does the whiteboard say?"))[1] and plain.close_how == "no close look on this body"
    unturned = PictureQuestions(Snapper(), mind, closer=Closer())
    assert run(unturned.ask("What does the whiteboard say?"))[1] and unturned.close_how == "nothing to turn me round"
    blank = PictureQuestions(Snapper(), mind, closer=Closer(None), turn=Turner())
    assert run(blank.ask("What does the whiteboard say?"))[1] and blank.close_how == "the close look gave no picture"
    looks = PictureQuestions(Snapper(), SeeingMind("She looks tired."), closer=Closer(), turn=Turner())
    assert run(looks.ask("What does the board over there say about her?")) == ("I can't tell from here.", False)


def test_in_the_sim_pebble_turns_its_back_for_the_close_look_and_turns_back(tmp_path):
    async def scenario():
        scene = Scene(tmp_path / "self", people=[Who("Ina", TRUSTED, 1300.0, 0.0)], things=household(), start=(600.0, 0.0, 0.0))
        await scene.setup()
        pictures = PictureQuestions(scene.eyes, SeeingMind("It says: buy milk."))
        scene.life.commands.pictures = pictures
        headings = []

        async def turn(degrees):
            done = await scene.life.house.turn_round(degrees)
            headings.append(math.degrees(scene.world.pose.heading))
            return done

        pictures.turn = turn
        await scene.say("Ina", "What does the whiteboard say?")
        await scene.run(2.0)
        await scene.close()
        return scene, pictures, headings

    scene, pictures, headings = run(scenario(), timeout=120)
    said = [line for line in scene.lines if " says " in line]
    assert any("It says: buy milk." in line for line in said)
    assert pictures.close_how == "a close look with the back camera" and pictures.closer().taken == 1
    assert len(headings) == 2 and abs(abs((headings[0] + 180.0) % 360.0 - 180.0) - 180.0) < 25.0 and abs((headings[1] + 180.0) % 360.0 - 180.0) < 25.0
