import asyncio
import json
import math
import time

import pytest
from conftest import run

from pebble.activities.gate import PEBBLE, PRIVACY_NO, Asker, Situation, decide
from pebble.activities.picture import PictureQuestions
from pebble.clock import Clock, FakeClock
from pebble.eyes.geometry import Box
from pebble.eyes.service import CameraEyes
from pebble.eyes.sources import Frame
from pebble.people.trust import CHILD, FRIEND, STRANGER, TRUSTED
from pebble.privacy.core import LOGGED, REFUSAL, WHY_ANSWER, door_answer
from pebble.privacy.cues import Closeness, Sleepers, frame_cue, pair_close, reclined, torso_flat
from pebble.privacy.look import away_from
from pebble.privacy.rooms import PrivateRooms
from pebble.privacy.words import DEFAULT_S, LONGEST_S, PRIVACY, RESUME, WHY, read
from pebble.seams.sight import BodyPoint, SeenPerson, SeenThing, Sight
from pebble.understand.request import Request

np = pytest.importorskip("numpy")

OWNER = Asker("ina", "Ina", TRUSTED, owner=True)
FRIENDLY = Asker("mo", "Mo", FRIEND)
STRANGE = Asker(None, "someone", STRANGER)
SAM = Asker("sam", "Sam", CHILD)

ASKS = [
    "don't look",
    "Don't look!",
    "look away",
    "privacy please",
    "give me some privacy",
    "can I have some privacy please",
    "I need a bit of privacy",
    "go away",
    "leave me alone",
    "I'm changing",
    "I'm getting dressed",
    "I'm getting changed",
    "not now Pebble, I'm in the shower",
    "Pebble go away, I'm getting changed",
    "no perving",
    "stop perving",
    "don't look at me",
    "stop staring at me",
    "eyes off me",
    "face the wall",
    "I'm in the loo",
    "I'm on the toilet",
    "I'm having a shower",
    "I'm in my undies",
    "I'm in my togs",
    "I'm changing the baby's nappy",
    "moenie kyk nie",
    "kyk weg",
    "ek trek aan",
    "kaua e titiro mai",
    "don't look for 10 minutes",
    "look away till I say so",
]
NOT_ASKS = [
    "don't look for my keys",
    "look for the ball",
    "I'm changing the channel",
    "I'm changing my mind",
    "don't look so sad",
    "where is the bathroom",
    "go to the bathroom",
    "I'm going to the shops",
    "what are you looking at",
    "stop following me",
    "go away from the stairs",
    "don't look at the ball",
    "the shower is broken",
    "change the channel",
    "I am in the kitchen",
    "don't look now but the cat is on the table",
    "look at that",
    "come here",
]


@pytest.mark.parametrize("text", ASKS)
def test_people_ask_for_privacy_in_their_own_words(text):
    found = read(text)
    assert found is not None and found.kind == PRIVACY, text


@pytest.mark.parametrize("text", NOT_ASKS)
def test_ordinary_talk_is_not_a_privacy_request(text):
    found = read(text)
    assert found is None or found.kind != PRIVACY, (text, found)


def test_how_long_it_looks_away():
    assert read("don't look").seconds == DEFAULT_S == 300.0
    assert read("don't look for 10 minutes").seconds == 600.0
    assert read("look away for half an hour").seconds == 1800.0
    assert read("don't look for three hours").seconds == LONGEST_S == 3600.0
    assert read("don't look for a second").seconds == 30.0
    until = read("look away till I say so")
    assert until.until_said and until.seconds == LONGEST_S
    assert read("don't look until I tell you").until_said
    assert read("I'm getting dressed").statement and not read("don't look").statement
    assert read("no peeking").soft and not read("I'm changing").soft


def test_looking_again_and_the_why_question():
    for text in ("you can look now", "okay you can look", "I'm dressed", "I'm decent now", "jy kan nou kyk", "all done, you can look now", "you can turn around now"):
        assert read(text).kind == RESUME, text
    for text in ("why did you look away?", "why are you facing the wall", "why won't you look at me"):
        assert read(text).kind == WHY, text
    assert read("why do you look sad") is None


def test_door_answers():
    assert door_answer("yes come in") is True and door_answer("Come in, Pebble") is True and door_answer("ja") is True
    assert door_answer("no, not now") is False and door_answer("don't come in") is False and door_answer("hang on") is False
    assert door_answer("what's for dinner") is None


def test_anyone_may_ask_it_to_look_away_like_a_stop():
    for asker in (OWNER, FRIENDLY, STRANGE, SAM, PEBBLE):
        for sit in (Situation(), Situation(asleep=True), Situation(quiet=True), Situation(can_move=False), Situation(blocked="stop", sticky_by="ina")):
            assert decide(Request("look_away"), asker, sit).yes


def test_sight_requests_wait_while_it_looks_away_for_children_too():
    private = Situation(privacy=True)
    for asker in (OWNER, SAM, STRANGE):
        for kind in ("what_see", "what_is", "sight_question", "look", "follow", "come", "find", "go_to_thing", "hide_seek", "red_light"):
            verdict = decide(Request(kind), asker, private)
            assert verdict.answer == "no" and verdict.say == PRIVACY_NO, (asker, kind)
    assert decide(Request("look_away"), SAM, private).yes
    assert decide(Request("go_home"), OWNER, private).yes
    assert decide(Request("wait"), OWNER, private).yes
    assert decide(Request("what_see"), PEBBLE, private).say == ""
    assert REFUSAL == PRIVACY_NO == "Not now — I'm giving someone privacy."


def test_picture_questions_wait_in_a_private_room():
    room = Situation(private_view=True)
    assert decide(Request("sight_question"), OWNER, room).say == PRIVACY_NO
    assert decide(Request("what_see"), OWNER, room).yes


def test_it_never_heads_into_a_private_room_on_its_own():
    places = Situation(places_known=frozenset({"bathroom", "kitchen"}), private_places=frozenset({"bathroom"}))
    assert decide(Request("go_to_place", place="bathroom"), PEBBLE, places).answer == "no"
    assert decide(Request("go_to_place", place="kitchen"), PEBBLE, places).yes
    assert decide(Request("go_to_place", place="bathroom"), OWNER, places).yes


def box(x, y, w, h, score=0.9):
    return Box(x, y, w, h, score)


def test_undress_cues():
    person = box(0.4, 0.1, 0.2, 0.8)
    wrapped = box(0.38, 0.4, 0.24, 0.25, 0.6)
    rail = box(0.85, 0.3, 0.05, 0.1, 0.6)
    assert frame_cue([person], [("bath towel", wrapped)]) == "undress"
    assert frame_cue([person], [("towel", rail)]) is None
    assert frame_cue([], [("bath towel", wrapped)]) is None
    assert frame_cue([person], [("bikini", wrapped)]) == "undress"
    assert frame_cue([person], [("sleepwear", wrapped)]) is None
    assert frame_cue([person], [("sleepwear", wrapped)], night=True) == "undress"
    assert frame_cue([person], [("sleepwear", wrapped)], place="bedroom") == "undress"
    assert frame_cue([person], [], (0.9, 0.0)) == "undress"
    assert frame_cue([person], [], (0.1, 0.9)) is None
    assert frame_cue([person], [], (0.1, 0.9), place="bedroom") == "undress"
    assert frame_cue([person], [], (0.1, 0.1), place="bathroom") == "bathroom"
    toilet = box(0.6, 0.6, 0.12, 0.3)
    far_toilet = box(0.62, 0.5, 0.04, 0.1)
    assert frame_cue([person], [("toilet", toilet)]) == "bathroom"
    assert frame_cue([person], [("toilet", far_toilet)]) is None
    assert frame_cue([person], [("cup", wrapped)]) is None


def points(shoulders, hips, nose=None, width=6.0):
    out = [
        BodyPoint("left_shoulder", shoulders[0] - width / 2, shoulders[1], 0.9),
        BodyPoint("right_shoulder", shoulders[0] + width / 2, shoulders[1], 0.9),
        BodyPoint("left_hip", hips[0] - 2.0, hips[1], 0.9),
        BodyPoint("right_hip", hips[0] + 2.0, hips[1], 0.9),
    ]
    if nose is not None:
        out.append(BodyPoint("nose", nose[0], nose[1], 0.9))
    return tuple(out)


def lying(track=1, bearing=0.0, posture="lying", speaking=None, pts=()):
    return SeenPerson(bearing, -5.0, 0.2, 0.5, 0.9, False, track, pts, None, posture, speaking)


def test_someone_asleep_on_the_couch():
    couch = SeenThing("couch", 0.0, -8.0, 0.25, 0.6, 0.8, 0.0)
    flat = points((-10.0, -4.0), (8.0, -5.0))
    assert torso_flat(lying(pts=flat)) and not torso_flat(lying(pts=points((0.0, 5.0), (0.0, -10.0))))
    on_couch = Sight(0.0, "front", 70.0, (lying(),), (), (couch,))
    on_floor = Sight(0.0, "front", 70.0, (lying(),), (), ())
    assert reclined(lying(), on_couch) and not reclined(lying(), on_floor)
    assert reclined(lying(), on_floor, "bedroom")
    sleepers = Sleepers()
    for second in range(0, 100, 5):
        sleepers.update(on_couch, float(second))
    assert sleepers.near(100.0) and 1 in sleepers.asleep
    assert sleepers.near(200.0) and not sleepers.near(400.0)
    night = Sleepers()
    for second in range(0, 40, 5):
        night.update(on_couch, float(second), night=True)
    assert night.near(40.0)
    talking = Sleepers()
    for second in range(0, 200, 5):
        talking.update(Sight(0.0, "front", 70.0, (lying(speaking=0.9),), (), (couch,)), float(second))
    assert not talking.near(200.0)
    floor = Sleepers()
    for second in range(0, 200, 5):
        floor.update(on_floor, float(second))
    assert not floor.near(200.0)


def standing(track, bearing, nose):
    return SeenPerson(bearing, 10.0, 0.6, 0.25, 0.9, True, track, points((bearing, 15.0), (bearing, -10.0), nose), 0.0, "standing")


def test_close_moments():
    kissing = Sight(0.0, "front", 70.0, (standing(1, -2.0, (-0.5, 25.0)), standing(2, 2.0, (0.5, 25.0))), (), ())
    apart = Sight(0.0, "front", 70.0, (standing(1, -20.0, (-20.0, 25.0)), standing(2, 20.0, (20.0, 25.0))), (), ())
    assert pair_close(kissing.people[0], kissing.people[1], 70.0)
    assert not pair_close(apart.people[0], apart.people[1], 70.0)
    near = Closeness()
    assert not near.update(kissing, 0.0) and not near.update(kissing, 1.0) and near.update(kissing, 2.0)
    assert not near.update(apart, 2.5)


class Map:
    def __init__(self, rooms):
        from pebble.alive.rooms import Room

        self.rooms = {name: Room(name, x, y, r, (), 0.9) for name, (x, y, r) in rooms.items()}


def test_which_rooms_are_private():
    now = [0.0]
    rooms = PrivateRooms(Map({"bathroom": (5.0, 0.0, 1.0), "bedroom": (0.0, 5.0, 1.0), "kitchen": (0.0, -5.0, 1.0)}), lambda: now[0])
    assert rooms.private("bathroom") and not rooms.private("bedroom") and not rooms.private("kitchen")
    rooms.saw("ina", "bedroom")
    assert rooms.private("bedroom") and rooms.occupants("bedroom") == ["ina"]
    now[0] = 1801.0
    assert not rooms.private("bedroom")
    rooms.mark_shut("bedroom")
    assert rooms.private("bedroom")
    now[0] = 3700.0
    assert not rooms.private("bedroom")
    assert rooms.private_at(5.2, 0.3) == "bathroom" and rooms.private_at(0.0, -5.0) is None
    door = rooms.door("bathroom", 0.0, 0.0)
    assert door[0] == pytest.approx(5.0 - 1.25) and door[1] == pytest.approx(0.0)
    assert rooms.crossing(0.0, 0.0, 5.0, 0.0) == "bathroom"
    assert rooms.crossing(0.0, 0.0, 3.0, 0.0) is None
    assert rooms.crossing(0.0, 0.0, 5.0, 0.0, allowed=("bathroom",)) is None
    assert rooms.crossing(5.0, 0.2, 5.5, 0.0) is None
    doorways = PrivateRooms(Map({"bathroom": (5.0, 0.0, 1.0)}), lambda: 0.0, lambda: [(4.0, 1.2)])
    near = doorways.door("bathroom", 0.0, 0.0)
    assert math.hypot(near[0] - 5.0, near[1]) >= 1.25 and near[1] > 0.5


def test_turning_away_puts_the_person_behind():
    assert away_from(30.0) == -150.0 and away_from(-20.0) == 160.0 and away_from(None) == 150.0


class Watch:
    def __init__(self, scores=None, found=None):
        self.offers = 0
        self.forgot = 0
        self.checks = 0
        self.scores = scores
        self.found = found

    def offer(self, *args, **kwargs):
        self.offers += 1

    def forget(self):
        self.forgot += 1

    def current(self, *args):
        return self.found

    def check(self, image):
        self.checks += 1
        return self.scores

    def start(self):
        pass

    def close(self):
        pass

    def status(self):
        return {}


class Counting:
    can = {"faces": True, "bodies": True, "tags": True}

    def __init__(self):
        self.calls = {"faces": 0, "bodies": 0, "tags": 0}

    def faces(self, image):
        self.calls["faces"] += 1
        return [Box(0.45, 0.2, 0.1, 0.13, 0.95)]

    def objects(self, image):
        self.calls["bodies"] += 1
        return [Box(0.4, 0.15, 0.2, 0.8, 0.8)], []

    def tags(self, image, fov):
        self.calls["tags"] += 1
        return []


class Floor:
    def __init__(self):
        self.offered = []
        self.reach_m = 2.0
        self.going = True

    def moving(self):
        return self.going

    def offer(self, image, camera, captured, at, fov, head):
        self.offered.append(image)

    def current(self, camera, captured):
        return (), None

    def forget(self):
        pass

    def set_moving(self, on):
        self.going = on

    def start(self):
        pass

    def close(self):
        pass


def test_no_frame_reaches_a_model_while_it_looks_away():
    clock = FakeClock()
    detector, slow, hazards, undress, floor = Counting(), Watch(), Watch(found=[]), Watch((0.0, 0.0)), Floor()
    eyes = CameraEyes(lambda camera: None, detector, clock, slow=slow, hazards=hazards, undress=undress, floor=floor)
    image = np.full((480, 640, 3), 200, np.uint8)
    sight = eyes.process(Frame(image, "front", clock.monotonic(), 1))
    eyes._show(sight, Frame(image, "front", clock.monotonic(), 1))
    assert sight.people and detector.calls["faces"] == 1 and slow.offers == 1 and hazards.offers == 1 and undress.offers == 1
    eyes.set_privacy(True, ("floor",))
    assert eyes.private and eyes.latest(5.0) is None and slow.forgot and hazards.forgot and undress.forgot
    calls, offers, floors = dict(detector.calls), (slow.offers, hazards.offers, undress.offers), len(floor.offered)
    for n in range(2, 12):
        clock.advance(0.1)
        private = eyes.process(Frame(image, "front", clock.monotonic(), n))
        assert not private.people and not private.things and not private.tags
    assert detector.calls == calls and (slow.offers, hazards.offers, undress.offers) == offers
    assert eyes.private_frames == 10 and len(floor.offered) == floors + 10
    from pebble.eyes.floor import horizon_row

    top = horizon_row(480, 640, 70.0, 8.0)
    assert 40 < top < 120
    for masked in floor.offered[floors:]:
        assert (masked[:top] == 128).all() and (masked[top:] == 200).all()
    floor.going = False
    eyes.process(Frame(image, "front", clock.monotonic(), 20))
    assert len(floor.offered) == floors + 10 and not eyes._needed()
    assert run(eyes.snapshot()) is None and run(eyes.look_closely()) is None
    eyes.set_privacy(False)
    clock.advance(0.1)
    again = eyes.process(Frame(image, "front", clock.monotonic(), 30))
    assert again.people and detector.calls["faces"] == calls["faces"] + 1


def test_the_camera_closes_while_it_looks_away():
    opened = []

    class Source:
        def __init__(self, camera):
            self.camera = camera
            self.count = 0

        def open(self):
            opened.append(self.camera)

        def read(self, timeout_s):
            self.count += 1
            time.sleep(0.01)
            return Frame(np.zeros((480, 640, 3), np.uint8), self.camera, time.monotonic(), self.count)

        def close(self):
            opened.append("closed")

    detector = Counting()
    eyes = CameraEyes(Source, detector, Clock(), max_fps=50)
    eyes.start()
    try:
        deadline = time.monotonic() + 5.0
        while detector.calls["faces"] < 3 and time.monotonic() < deadline:
            time.sleep(0.02)
        eyes.set_privacy(True)
        deadline = time.monotonic() + 5.0
        while "closed" not in opened and time.monotonic() < deadline:
            time.sleep(0.02)
        assert "closed" in opened
        seen = detector.calls["faces"]
        time.sleep(0.3)
        assert detector.calls["faces"] == seen and eyes.latest(5.0) is None
    finally:
        eyes.close()


def test_a_picture_for_a_question_is_checked_before_it_leaves_the_eyes():
    clock = FakeClock()
    cues = []
    undress = Watch((0.9, 0.1))
    eyes = CameraEyes(lambda camera: None, Counting(), clock, undress=undress)
    eyes.snapshot_veto = lambda people, things, undressed: undressed is not None and undressed[0] >= 0.35
    eyes.on_cue = lambda: cues.append(1)
    image = np.zeros((480, 640, 3), np.uint8)
    sight = eyes.process(Frame(image, "front", clock.monotonic(), 1))
    eyes._show(sight, Frame(image, "front", clock.monotonic(), 1))
    assert run(eyes.snapshot()) is None and undress.checks == 1 and cues == [1]
    undress.scores = (0.05, 0.05)
    picture = run(eyes.snapshot())
    assert picture is not None and picture[:2] == b"\xff\xd8"


class Mind:
    def __init__(self):
        self.calls = 0

    async def sees(self):
        return True

    async def chat(self, messages, purpose="", max_tokens=0):
        self.calls += 1
        return type("Reply", (), {"text": "The door is open."})()


class Guard:
    def __init__(self, line=None):
        self.line = line

    def refusal(self):
        return self.line


class Eyes:
    available = True

    def __init__(self, veto=None):
        self.taken = 0
        self.veto = veto

    async def snapshot(self, max_side=768, camera=None):
        self.taken += 1
        return None if self.veto else b"\xff\xd8 picture \xff\xd9"


def test_no_privacy_gated_picture_reaches_the_language_model():
    mind = Mind()
    questions = PictureQuestions(Eyes(), mind)
    questions.guard = Guard(REFUSAL)
    assert run(questions.ask("Is the door open?")) == (REFUSAL, False)
    assert mind.calls == 0 and questions.eyes.taken == 0
    vetoed = PictureQuestions(Eyes(veto=True), mind)
    guard = Guard()
    vetoed.guard = guard
    original = vetoed.eyes.snapshot

    async def snapped(**kwargs):
        guard.line = REFUSAL
        return await original(**kwargs)

    vetoed.eyes.snapshot = snapped
    assert run(vetoed.ask("Is the door open?")) == (REFUSAL, False) and mind.calls == 0
    fine = PictureQuestions(Eyes(), mind)
    fine.guard = Guard()
    assert run(fine.ask("Is the door open?")) == ("The door is open.", True) and mind.calls == 1


class Bridge:
    def __init__(self, privacy=True):
        self.calls = []
        if privacy:
            self.eyesPrivacy = lambda text: self.calls.append(("privacy", json.loads(text)))

    def eyesSink(self, sink):
        self.sink = sink

    def eyesStart(self, config):
        self.calls.append(("start",))

    def eyesEnable(self, on):
        self.calls.append(("enable", on))

    def eyesSnapshot(self, camera, max_side, max_age_s):
        self.calls.append(("snapshot",))
        return b"\xff\xd8 x \xff\xd9"

    def eyesLookClosely(self, demand):
        self.calls.append(("closely", demand))

    def eyesHead(self, head):
        pass


def frame(**parts):
    data = {"camera": "front", "t": time.monotonic(), "w": 640, "h": 480, "faces": [[0.45, 0.2, 0.1, 0.13, 0.9]], "objects": [[0.4, 0.15, 0.2, 0.8, 0.8, 0]]}
    data.update(parts)
    return json.dumps(data)


def test_the_phone_is_told_to_look_away_and_its_results_are_dropped():
    from pebble.eyes.android import AndroidEyes

    bridge = Bridge()
    eyes = AndroidEyes(Clock(), words={}, hazards={"hazards": False}, bridge=bridge)
    eyes.start()
    assert eyes.feed(frame(undress=[0.02, 0.6])) and eyes.latest(1.0).people
    assert eyes.undressed() == (0.02, 0.6)
    eyes.set_privacy(True, ("floor",))
    assert ("privacy", {"on": True, "keep": ["floor"]}) in bridge.calls
    assert not eyes.feed(frame()) and eyes.latest(1.0) is None and eyes.private_frames == 1
    assert eyes.undressed() is None
    assert not eyes.slow(json.dumps({"camera": "front", "w": 640, "h": 480, "found": [[0.1, 0.1, 0.2, 0.2, 0.9, 0]]}))
    assert run(eyes.snapshot()) is None and ("snapshot",) not in bridge.calls
    eyes.set_privacy(False)
    assert ("privacy", {"on": False, "keep": []}) in bridge.calls
    assert eyes.feed(frame()) and eyes.latest(1.0).people
    older = Bridge(privacy=False)
    plain = AndroidEyes(Clock(), words={}, hazards={"hazards": False}, bridge=older)
    plain.start()
    plain.set_privacy(True)
    plain.set_privacy(False)
    assert [c for c in older.calls if c[0] == "enable"] == [("enable", False), ("enable", True)]


def test_the_face_page_is_told_to_stop_looking():
    from pebble.web.eyes import BrowserEyes
    from pebble.web.hub import Hub

    hub = Hub()
    eyes = BrowserEyes(hub, Clock())
    assert eyes._event()["on"]
    eyes.set_privacy(True)
    assert not eyes._event()["on"]
    assert eyes.seen({"t": 0.0, "camera": "front", "people": []}) is False and eyes.private_frames == 1
    eyes.set_privacy(False)
    assert eyes._event()["on"]


def test_the_undress_model_stays_quiet_on_ordinary_household_photos():
    from pathlib import Path

    from pebble.eyes import fetch as fetching
    from pebble.eyes.undress import MODEL, NoUndressModel, UndressModel

    cv2 = pytest.importorskip("cv2")
    try:
        model = UndressModel(fetching.MODELS / MODEL, 1)
    except NoUndressModel:
        pytest.skip("no privacy cue model (python -m pebble.eyes.fetch)")
    data = Path(__file__).parent / "data"
    photos = sorted(data.glob("hazards/*.jpg")) + sorted(data.glob("mouths/*/*.jpg")) + sorted(data.glob("teapots/*.jpg"))
    assert len(photos) >= 40
    worst = max(model.scores(cv2.imread(str(photo)))[0] for photo in photos)
    assert worst < 0.35


def test_black_box_line_and_nothing_else():
    assert LOGGED == "looked away for privacy" and WHY_ANSWER == "To give you some privacy."
