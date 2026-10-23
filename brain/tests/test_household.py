import asyncio
import json

import pytest

from conftest import run
from pebble.activities.asks import read
from pebble.activities.climate import ClimateLog, Measured, answer, compare, dew_point
from pebble.activities.gate import PEBBLE, Asker, Running, Situation, decide
from pebble.alive.games import GameTable, Stillness
from pebble.chaos.engine import Chaos
from pebble.clock import FakeClock
from pebble.people.trust import CHILD, FRIEND, STRANGER, TRUSTED
from pebble.safety.ladder import Ladder, quake_length
from pebble.safety.notice import Notice
from pebble.seams.sight import BodyPoint, SeenPerson, Sight
from pebble.setup import tsunami_zone
from pebble.setup.cli import main as setup_main
from pebble.selfstore import SelfStore
from pebble.understand.request import Request
from tests.test_safety_ladder import Fake

PLACES = ["bedroom", "kitchen", "lounge", "hallway"]
SAM = Asker("sam", "Sam", CHILD)
MIA = Asker("mia", "Mia", FRIEND)
INA = Asker("ina", "Ina", TRUSTED, owner=True)
VISITOR = Asker(None, "someone", STRANGER)


@pytest.mark.parametrize("line, kind, extra", [
    ("Pebble, how warm is the bedroom?", "climate", {"room": "bedroom", "about": "temperature"}),
    ("How humid is the bathroom?", "climate", {"room": "bathroom", "about": "humidity"}),
    ("Is it damp in the laundry?", "climate", {"room": "laundry", "about": "humidity"}),
    ("How's the air in the kitchen?", "climate", {"room": "kitchen", "about": "air"}),
    ("How cold is the fridge?", "climate", {"room": "fridge"}),
    ("Is it warm in here?", "climate", {"room": "here"}),
    ("Which room is the warmest?", "climate_compare", {"which": "warm"}),
    ("Measure the rooms", "climate_round", {"room": ""}),
    ("Can you go and measure the air in the bedroom?", "climate_round", {"room": "bedroom"}),
    ("Let's play red light, green light!", "game", {"game": "red_light"}),
    ("Can we play musical statues?", "game", {"game": "statues"}),
    ("hide-and-seek!", "game", {"game": "hide_seek"}),
    ("Roll two dice", "dice", {"count": 2, "sides": 6}),
    ("roll a d20", "dice", {"count": 1, "sides": 20}),
    ("flip a coin", "coin", {}),
    ("Give Sam three points", "score_add", {"who": "sam", "points": 3}),
    ("take a point off Mia", "score_add", {"who": "mia", "points": -1}),
    ("30 seconds each turn", "turn_set", {"seconds": 30.0}),
    ("Which smoke alarm is chirping?", "find_chirp", {}),
    ("find the beeping alarm", "find_chirp", {}),
])
def test_the_household_reader_picks_out_its_own_requests(line, kind, extra):
    ask = read(line, PLACES)
    assert ask is not None and ask.kind == kind, ask
    for key, value in extra.items():
        assert getattr(ask, key) == value


@pytest.mark.parametrize("line", [
    "I'm cold",
    "it's cold in here",
    "how hot is the oven",
    "how warm is the water",
    "stop playing hide and seek",
    "set a timer for 5 minutes",
    "is the smoke alarm chirping",
    "what is that chirping noise",
    "what's the score?",
    "next turn",
    "again",
])
def test_the_household_reader_leaves_other_lines_alone(line):
    assert read(line, PLACES) is None


def test_score_and_timer_words_only_count_while_they_are_in_use():
    assert read("what's the score?", PLACES, has_scores=True).kind == "score_read"
    assert read("next turn", PLACES, timer_set=True).kind == "turn_next"
    assert read("play again", PLACES, last_game="statues").game == "statues"


def test_dice_come_from_the_logged_chaos_stream_and_can_be_checked():
    draws = []
    chaos = Chaos(seed=42, sink=draws.append)
    table = GameTable(lambda: chaos.stream("choices"), record=lambda kind, **data: draws.append({"kind": kind, **data}))
    first = table.roll(2, 6)
    again = GameTable(lambda: Chaos(seed=42).stream("choices")).roll(2, 6)
    assert first == again and first.endswith(".")
    logged = [d for d in draws if d.get("kind") == "dice"][0]
    streamed = [d["id"] for d in draws if "id" in d]
    assert len(logged["draws"]) == 2 and all(d.startswith("choices:") and d in streamed for d in logged["draws"])
    assert sum(logged["values"]) == int(first.split("That makes ")[1].rstrip("."))
    assert table.flip() in ("It's heads.", "It's tails.")


def test_scores_and_the_turn_timer():
    now = [0.0]
    table = GameTable(now=lambda: now[0])
    assert table.add("sam", 1) == "A point for Sam. Sam has 1 now."
    assert table.add("mia", 3) == "3 points for Mia. Mia has 3 now."
    assert table.add("sam", -1) == "One point off Sam. Sam has 0 now."
    assert table.words() == "Mia has 3 points and Sam has 0. Mia is winning."
    assert table.reset() == "Okay, the scores are back to zero."
    assert table.set_turns(30).startswith("Okay, 30 seconds a turn. Go!")
    now[0] = 21.0
    assert table.tick() == "Ten seconds left!"
    now[0] = 31.0
    assert table.tick() == "Time's up!"
    assert table.tick() is None
    assert table.start_turn() == "Go!" and table.timer_running()
    assert table.stop_turns() == "Okay, no more turn timer." and not table.timer_set()


def test_the_gate_keeps_the_household_drives_for_the_household():
    calm = Situation()
    for kind in ("climate_round", "hide_seek", "find_chirp"):
        assert decide(Request(kind), VISITOR, calm).answer == "no"
        assert decide(Request(kind), SAM, calm).answer == "yes"
        assert decide(Request(kind), MIA, calm).answer == "yes"
    assert decide(Request("red_light"), VISITOR, calm).answer == "yes"
    assert decide(Request("quake_round"), INA, calm).answer == "no"
    quiet = Situation(quiet=True, can_move=False)
    assert decide(Request("hide_seek"), SAM, quiet).answer == "no"
    assert decide(Request("statues"), SAM, quiet).say == "It's my quiet time, so no games just now."
    assert decide(Request("red_light"), SAM, Situation(can_see=False)).answer == "no"
    assert decide(Request("climate_round"), PEBBLE, Situation(low_battery=True)).answer == "no"
    busy = Situation(running=Running("follow", INA.id, INA.label, INA.tier, INA.id, INA.label))
    assert decide(Request("hide_seek"), SAM, busy).answer == "no"


def test_climate_answers_are_honest_about_what_and_when():
    clock = FakeClock(1_792_000_000.0)
    log = ClimateLog(None, clock)
    assert "I can't measure the fridge" in answer(log, "fridge", "temperature", PLACES)
    assert "outside" in answer(log, "outside", "temperature", PLACES)
    assert answer(log, "bedroom", "temperature", PLACES) == "I haven't measured the bedroom yet. I'll do it on my next round of the rooms."
    assert answer(log, "attic", "temperature", PLACES) == "I don't know where the attic is yet, so I haven't measured it."
    log.rooms["bedroom"] = [Measured("bedroom", clock.now(), 19.2, 55.0, dew_point(19.2, 55.0), None, True, 120.0)]
    log.rooms["kitchen"] = [Measured("kitchen", clock.now() - 600, 22.6, 48.0, dew_point(22.6, 48.0), None, True, 120.0)]
    clock.advance(2 * 3600)
    said = answer(log, "bedroom", "temperature", PLACES)
    assert said == "The bedroom was 19 degrees near the floor when I measured it about 2 hours ago, with 55 percent humidity."
    assert "would run wet" in answer(log, "bedroom", "humidity", PLACES)
    assert compare(log, "warm").startswith("The kitchen was the warmest, 23 degrees")
    assert round(dew_point(20.0, 65.0), 1) == 13.2


def person(track, bearing, points):
    return SeenPerson(bearing, 5.0, 0.6, 0.15, 0.9, track=track, points=tuple(BodyPoint(name, b, e, 0.9) for name, b, e in points))


BODY = [("nose", 0.0, 12.0), ("left_shoulder", 4.0, 6.0), ("right_shoulder", -4.0, 6.0), ("left_hip", 3.0, -6.0), ("right_hip", -3.0, -6.0), ("left_wrist", 5.0, -4.0), ("right_wrist", -5.0, -4.0)]


def pose(track, bearing, shift=0.0, wobble=0.0):
    return person(track, bearing, [(n, bearing + b + shift + (wobble if i % 2 else -wobble), e) for i, (n, b, e) in enumerate(BODY)])


def test_stillness_catches_a_step_but_not_a_wobble():
    judge = Stillness()
    frames = [Sight(t * 0.2, "front", 70.0, (pose(1, -15.0, wobble=0.3 * (t % 2)), pose(2, 15.0, shift=1.2 * t))) for t in range(6)]
    caught = []
    for sight in frames:
        caught += judge.watch(sight)
    assert caught == [2]


def test_quake_says_how_long_it_lasted_and_the_tsunami_line_only_when_asked_for():
    def shake(fake, seconds, strength):
        return lambda t: [Notice("quake", 0.8, "test", fake.clock.now(), "test quake", {"seconds": min(t, seconds) + 4, "strength": strength}, None)] if t < seconds else []

    async def go(zone, seconds, strength):
        fake = Fake()
        rounds = []
        ports = fake.ports()
        ports.tsunami_zone = lambda: zone
        ports.check_round = lambda why, done: rounds.append(done) or True
        ladder = Ladder(ports)
        feed = shake(fake, seconds, strength)
        t = 0.0
        while t < seconds + 20:
            for item in feed(t):
                ladder.notice(item)
            await ladder.step(False)
            await asyncio.sleep(0)
            fake.clock.advance(1.0)
            t += 1.0
        return fake, ladder, rounds

    fake, ladder, rounds = run(go(True, 70, "moderate shaking"))
    lines = fake.lines()
    assert "The shaking has stopped." in lines and "It lasted about a minute and a half." not in lines
    assert any(line.startswith("It lasted about") for line in lines)
    assert "That was long. The advice near the coast is: long or strong, get gone." in lines
    assert len(rounds) == 1 and ladder.incidents["quake"].seeking
    assert any("earthquake" in why for why in fake.roused)
    fake, ladder, rounds = run(go(False, 70, "strong shaking"))
    assert not any("get gone" in line for line in fake.lines())
    fake, ladder, rounds = run(go(True, 20, "moderate shaking"))
    assert not any("get gone" in line for line in fake.lines())
    assert quake_length(42) == "about 40 seconds" and quake_length(70) == "about a minute"


def test_after_the_round_the_owner_hears_who_was_not_found_or_gets_a_notice():
    async def go(owner_found):
        fake = Fake(notify=True)
        dones = []
        ports = fake.ports()
        ports.check_round = lambda why, done: dones.append(done) or True
        ladder = Ladder(ports)
        ladder.notice(Notice("quake", 0.9, "test", fake.clock.now(), "test quake", {"seconds": 30, "strength": "strong shaking"}, None))
        for _ in range(20):
            await ladder.step(False)
            fake.clock.advance(1.0)
        found = [("ina", "Ina")] if owner_found else [("mo", "Mo")]
        dones[0]({"how": "done", "found": found, "missing": [("sam", "Sam")], "unchecked": [], "someone": True})
        await asyncio.sleep(0)
        for _ in range(40):
            await ladder.step(False)
            fake.clock.advance(1.0)
        return fake, ladder

    fake, ladder = run(go(True))
    assert "Ina, I couldn't find Sam." in fake.lines()
    assert len(fake.notified) == 1
    assert "quake" not in ladder.incidents
    fake, _ = run(go(False))
    assert len(fake.notified) == 2 and "It couldn't find Sam." in fake.notified[1][1]


def test_an_aftershock_cuts_the_round_and_holds_still_again():
    async def go():
        fake = Fake()
        ended = []
        ports = fake.ports()
        ports.check_round = lambda why, done: True
        ports.end_seek = ended.append
        ladder = Ladder(ports)
        ladder.notice(Notice("quake", 0.9, "test", fake.clock.now(), "test quake", {"seconds": 12, "strength": "moderate shaking"}, None))
        for _ in range(18):
            await ladder.step(False)
            fake.clock.advance(1.0)
        assert ladder.incidents["quake"].seeking
        ladder.notice(Notice("quake", 0.9, "test", fake.clock.now(), "test quake", {"seconds": 5, "strength": "moderate shaking"}, None))
        await ladder.step(False)
        return fake, ladder, ended

    fake, ladder, ended = run(go())
    assert ladder.holding() == "the floor is shaking"
    assert ended == ["it started shaking again"]
    assert "It's shaking again. Drop, cover and hold!" in fake.loud()


@pytest.mark.setup_mode
def test_the_tsunami_question_is_asked_once_when_setup_ends(tmp_path, clock):
    root = tmp_path / "self"
    store = SelfStore.open(root, clock)
    store.write("setup.json", {"format": 1, "on": True})
    asked = []
    assert setup_main(["done", "--self", str(root)], clock=clock, ask=lambda prompt: "", answer=lambda prompt: asked.append(prompt) or "yes") == 0
    assert len(asked) == 1 and "tsunami zone" in asked[0]
    assert tsunami_zone(SelfStore.open(root, clock)) is True
    assert setup_main(["tsunami", "no", "--self", str(root)], clock=clock) == 0
    assert tsunami_zone(SelfStore.open(root, clock)) is False
    prefs = json.loads((root / "preferences.json").read_text(encoding="utf-8"))
    assert prefs["safety"]["tsunami_zone"] is False


@pytest.mark.setup_mode
def test_an_unclear_answer_leaves_the_tsunami_line_off(tmp_path, clock):
    root = tmp_path / "self"
    store = SelfStore.open(root, clock)
    store.write("setup.json", {"format": 1, "on": True})
    assert setup_main(["done", "--self", str(root)], clock=clock, ask=lambda prompt: "", answer=lambda prompt: "maybe") == 0
    assert tsunami_zone(SelfStore.open(root, clock)) is None


def test_a_dice_line_is_answered_once_by_the_household_in_a_whole_life(rig_factory):
    rig = rig_factory()
    life = rig.life
    assert life.commands.household is life.household

    async def go():
        life.hear("Pebble, roll a dice", None)
        await life.commands.settle()
        await asyncio.sleep(0.05)

    run(go())
    said = [line for line in rig.voice.lines if line.startswith("It's ")]
    assert len(said) == 1 and said[0][5:].split()[1].rstrip(".").isdigit()
    records = [entry for entry in rig.store.read_lines("logs/blackbox.jsonl") if entry.get("kind") == "game_dice"]
    assert records and records[0]["draws"]


def test_a_beckon_or_a_shoo_during_a_turn_game_is_part_of_the_game(rig_factory):
    rig = rig_factory()
    commands = rig.life.commands

    class Game:
        game = True
        kind = "red_light"

    commands.runner.current = Game()
    try:
        verdict = run(commands.act(Request("come"), SAM, "gesture"))
    finally:
        commands.runner.current = None
    assert verdict.answer == "no" and "game" in verdict.reason


def test_the_quake_round_needs_eyes_to_drive(rig_factory):
    rig = rig_factory()
    assert rig.life.commands.quake_round("checking on everyone", lambda result: None) is False
