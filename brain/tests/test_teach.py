import asyncio
import json
import urllib.request

import pytest

from conftest import run

from pebble.activities.card import Body, Card
from pebble.clock import FakeClock
from pebble.life.trying_scene import AT
from pebble.mind.budget import BACKGROUND, TEACH, kind_of
from pebble.people.trust import TRUSTED
from pebble.script.check import Ground, read
from pebble.script.dream import DreamWorld
from pebble.selfstore import SelfStore
from pebble.teach import eval as teach_eval
from pebble.teach.book import DRAFT_KEEP_S, Entry, HowTo, pack, pattern_of, shown_name
from pebble.teach.concepts import names_alive, judge, opposite
from pebble.teach.induce import Inducer, answer_question, faithful, made_from, readback, said_steps, unify, values_seen
from pebble.teach.record import join, sample, step_of
from pebble.teach.redteam import concept_accuracy, red_team, responsiveness
from pebble.teach.replay import fill, gap_to_path, holes, segments, thin
from pebble.teach.scene import TEACHING
from pebble.teach.words import read as read_words
from pebble.understand.logic import cond_words
from pebble.understand.request import Request, cond_from
from pebble.web.hub import Hub
from pebble.web.server import FaceServer, pad_command
from pebble.web.webface import WebFace

INA = {"id": "ina", "name": "Ina", "tier": TRUSTED}
GO_KITCHEN = {"do": "request", "request": {"kind": "go_to_place", "place": "kitchen"}}
GO_STUDY = {"do": "request", "request": {"kind": "go_to_place", "place": "study"}}
COME = {"do": "request", "request": {"kind": "come", "who": "me"}}
SPIN = {"do": "turn", "way": "around", "degrees": 360}


def book(tmp_path):
    clock = FakeClock.at(AT)
    return HowTo(SelfStore.open(tmp_path / "self", clock), clock), clock


def card() -> Card:
    return Card(Body(places=("kitchen", "study", "lounge"), people=("ina", "mo")))


def scene(name: str, tmp_path):
    return asyncio.run(asyncio.wait_for(TEACHING[name](tmp_path / "self", False), 900))


def test_the_lesson_words_are_read_by_plain_code():
    cases = {
        "I'm going to teach you something.": ("start", ""),
        "Watch this.": ("start", ""),
        "Let me show you how to check the back door.": ("start", "check the back door"),
        "Pebble, learn this": ("start", ""),
        "That's it.": ("end", ""),
        "That's it, call it the evening round.": ("end", "evening round"),
        "Call it the twirl.": ("end", "twirl"),
        "Done.": ("end", ""),
        "No, scrap that last bit.": ("undo", ""),
        "Start again.": ("again", ""),
        "Follow me and learn the way to the garage.": ("lead", "garage"),
        "This is where you sit when we watch TV.": ("carry", "tv spot"),
        "This is what messy looks like.": ("show", "messy"),
        "This is the cat's toy.": ("show", "cat's toy"),
        "When I say boop, spin.": ("word", "boop"),
        "When I say dizzy time, spin around twice.": ("word", "dizzy time"),
        "Whenever the doorbell rings, come and get me.": ("habit", ""),
        "When I come home, greet me like this.": ("way", "come home"),
        "To do the evening round, you go to the kitchen, then come back to me.": ("explain", "evening round"),
        "Copy me.": ("copy", ""),
        "Remember that as the bob.": ("keep", "bob"),
        "What have I taught you?": ("list", ""),
        "What do you know how to do?": ("list", ""),
        "Do the evening round but skip the garage.": ("skip", "evening round"),
        "From now on, skip the garage.": ("from_now", ""),
    }
    for text, (kind, name) in cases.items():
        said = read_words(text)
        assert said is not None and said.kind == kind and said.name == name, (text, said)
    assert read_words("Go to the kitchen.") is None and read_words("Spin around.") is None
    assert read_words("This is not messy.").negative and read_words("The cat is a toy.").extra == "cat"
    assert read_words("From now on, skip the garage.").extra == "garage"


def test_only_drive_pad_steps_are_joined():
    said = [{"do": "turn", "way": "left", "degrees": 45}, {"do": "turn", "way": "right", "degrees": 45}]
    assert join(said) == said
    driven = [{"do": "turn", "way": "left", "degrees": 43.2}, {"do": "turn", "way": "left", "degrees": 41.0}, {"do": "move", "way": "forward", "metres": 0.012}, {"do": "move", "way": "forward", "metres": 0.31}, {"do": "move", "way": "forward", "metres": 0.2}]
    assert join(driven, ["drive"] * 5) == [{"do": "turn", "way": "left", "degrees": 85}, {"do": "move", "way": "forward", "metres": 0.5}]
    assert join([SPIN, SPIN]) == [{**SPIN, "repeat": 2}]
    assert step_of(Request("turn", way="left", amount="little")) == {"do": "turn", "way": "left", "degrees": 45}
    assert step_of(Request("go_to_place", place="kitchen")) == GO_KITCHEN
    assert step_of(Request("say_to", who="me", text="all done")) == {"do": "say", "text": "all done"}


def test_examples_that_differ_in_a_place_make_a_slot_and_a_way_asks_one_question():
    made = unify([[GO_KITCHEN, SPIN, COME], [GO_STUDY, SPIN, COME]])
    assert made.steps[0]["request"]["place"] == "{place}" and made.slots == {"place": ["kitchen", "study"]} and made.question is None
    doors = unify([[{"do": "request", "request": {"kind": "go_to_thing", "thing": "back door"}}], [{"do": "request", "request": {"kind": "go_to_thing", "thing": "front door"}}]])
    assert doors.slots == {"door": ["back door", "front door"]}
    left, right = [SPIN, {"do": "turn", "way": "left", "degrees": 90}], [SPIN, {"do": "turn", "way": "right", "degrees": 90}]
    asked = unify([left, right])
    assert asked.question is not None and asked.question.kind == "manner" and asked.question.text.endswith("Does it matter?")
    assert "turn left" in asked.question.text and "turn right" in asked.question.text
    assert answer_question(asked.question, "no, it doesn't matter") == left
    assert answer_question(asked.question, "yes, always right") == right
    extra = unify([[GO_KITCHEN, COME], [GO_KITCHEN, SPIN, COME]])
    assert extra.question is not None and extra.question.kind == "extra" and "spin round" in extra.question.text
    assert answer_question(extra.question, "yes, every time") == [GO_KITCHEN, SPIN, COME]
    assert answer_question(extra.question, "no") == [GO_KITCHEN, COME]
    assert unify([left, left]).question is None


def test_the_book_finds_by_name_alias_pattern_and_meaning(tmp_path):
    store, clock = book(tmp_path)
    entry = Entry("check the kitchen", "procedure", steps=[{"do": "request", "request": {"kind": "go_to_place", "place": "{place}"}}, SPIN], slots={"place": ["kitchen", "study"]}, taught_by=INA, about="go to a place and spin round")
    entry.pattern = pattern_of(entry.name, entry.slots)
    assert entry.pattern == "check the {place}" and shown_name(entry) == "check a place"
    store.put(entry)
    store.put(Entry("boop", "word", words="spin around", taught_by=INA))
    store.put(Entry("evening round", "procedure", aliases=["the night round"], steps=[GO_KITCHEN, COME], about="go to the kitchen, then come to you", taught_by=INA))
    found, slots = store.find("Pebble, check the lounge please")
    assert found.name == "check the kitchen" and slots == {"place": "lounge"}
    assert store.find("can you do the evening round")[0].name == "evening round"
    assert store.find("do the night round")[0].name == "evening round"
    assert store.find("boop")[0].kind == "word" and store.find("boop the cat") is None
    assert store.closest("the one where you go to the kitchen and come back")[0].name == "evening round"
    again = HowTo(store.store, clock)
    assert sorted(again.index) == ["boop", "check-the-kitchen", "evening-round"]


def test_drafts_last_a_week_and_forgetting_someone_drops_their_ways(tmp_path):
    store, clock = book(tmp_path)
    store.draft("dance", INA, [SPIN], [], [], ["said"])
    assert store.take_draft("ina", "dance")["steps"] == [SPIN] and store.take_draft("ina", "dance") is None
    store.draft("dance", INA, [SPIN], [], [], ["said"])
    clock.advance(DRAFT_KEEP_S + 60)
    assert store.tidy_drafts() == []
    store.put(Entry("greeting for ina", "way", steps=[SPIN], trigger={"event": "arrives", "who": "me"}, person="ina", taught_by=INA))
    store.put(Entry("evening round", "procedure", steps=[GO_KITCHEN, COME], taught_by=INA, examples=[{"steps": [GO_KITCHEN, COME], "by": "ina"}]))
    store.draft("hop", INA, [SPIN], [], [], ["said"])
    done = store.forget("ina", ["Ina"])
    assert done["gone"] == ["greeting for ina"] and store.get("greeting for ina") is None
    kept = store.get("evening round")
    assert kept.taught_by["id"] is None and kept.taught_by["name"] == "" and kept.examples[0]["by"] is None
    assert store.drafts() == []


def test_gemmas_part_is_checked_by_plain_code():
    examples = [[GO_KITCHEN, SPIN, COME], [GO_STUDY, SPIN, COME]]
    seen = values_seen(examples)
    good = {"kind": "procedure", "name": "room check", "aliases": ["check a room"], "about": "goes to a room, spins and comes back", "steps": [{"do": "request", "request": {"kind": "go_to_place", "place": "{room}"}}, {"do": "turn", "way": "around", "degrees": 360}, COME], "slots": {"room": ["kitchen", "study"]}}
    made = made_from(good, card(), examples, seen)
    assert made.problems == [] and made.slots == {"room": ["kitchen", "study"]}
    unseen = dict(good, slots={"room": ["kitchen", "garage"]})
    assert any("nobody showed" in p for p in made_from(unseen, card(), examples, seen).problems)
    added = dict(good, steps=good["steps"] + [{"do": "wiggle"}])
    assert any("don't match" in p for p in made_from(added, card(), examples, seen).problems)
    missing = dict(good, steps=good["steps"][1:])
    assert any("don't match" in p for p in made_from(missing, card(), examples, seen).problems)
    fly = dict(good, steps=[{"do": "fly"}])
    assert any("not a block" in p for p in made_from(fly, card(), examples, seen).problems)
    hole = dict(good, slots={})
    assert any("has no values" in p for p in made_from(hole, card(), examples, seen).problems)
    assert faithful(good["steps"], good["slots"], examples) == []


def test_the_record_for_gemma_is_short_and_the_teachers_words_go():
    record = sample()
    text = record.text()
    assert len(text) <= 1700 and "Their words:" in text and '"go to the hallway"' in text
    record.forget_words()
    assert "Their words" not in record.text()
    two = record.text(examples=[[GO_KITCHEN], [GO_STUDY]])
    assert "Example 1:" in two and "Example 2:" in two and "study" in two


def test_the_read_back_is_built_from_what_was_kept():
    entry = Entry("check the kitchen", "procedure", steps=[{"do": "request", "request": {"kind": "go_to_place", "place": "{place}"}}, SPIN, COME], slots={"place": ["kitchen", "study"]}, pattern="check the {place}")
    assert readback(entry) == "Okay, I've learned how to check a place: I go to the place, spin round, then come to you (the kitchen and the study so far)."
    assert readback(Entry("twirl", "move", steps=[SPIN, {"do": "turn", "way": "left", "degrees": 90}])) == "Okay, I've learned the twirl: I spin round, then turn left 90 degrees."
    assert readback(Entry("boop", "word", words="spin around")) == "Okay: when you say boop, I'll spin around."
    assert readback(Entry("when the doorbell rings", "habit", steps=[COME], trigger={"event": "sound", "thing": "doorbell"})) == "Okay: whenever the doorbell rings, I'll come to you."
    assert readback(Entry("greeting for mo", "way", steps=[SPIN], trigger={"event": "arrives", "who": "me"})) == "Okay: when you come home, I'll spin round."
    assert readback(Entry("messy", "concept", line="toys on the floor")) == "Okay, I know what messy looks like now (toys on the floor)."
    assert said_steps([GO_KITCHEN, SPIN]) == "go to the kitchen, then spin round"


def test_concepts_never_take_people_or_animals_and_opposites_help():
    assert names_alive("the cat is a toy") and names_alive("the baby") and names_alive("dog") and names_alive("mo", ("mo",))
    assert not names_alive("the cat's toy") and not names_alive("messy") and not names_alive("back door locked")
    assert opposite("messy", "tidy") and opposite("door open", "door shut") and not opposite("messy", "door open")
    messy = Entry("messy", "concept", look="place", prints=[{"v": pack([1.0, 0.1, 0.0, 0.0]), "yes": True}, {"v": pack([0.95, 0.15, 0.05, 0.0]), "yes": True}])
    tidy = Entry("tidy", "concept", look="place", prints=[{"v": pack([0.0, 0.1, 1.0, 0.0]), "yes": True}])
    assert judge(messy, [0.97, 0.12, 0.02, 0.0], [messy, tidy])[0] == "yes"
    assert judge(messy, [0.02, 0.1, 0.99, 0.0], [messy, tidy])[0] == "no"


def test_the_drive_pad_takes_only_clean_commands_through_the_face_page():
    assert pad_command({"kind": "drive", "x": 5, "y": -9}) == {"kind": "drive", "x": 1.0, "y": -1.0}
    assert pad_command({"kind": "tilt", "way": "up"}) == {"kind": "tilt", "way": "up"}
    for bad in ({"kind": "drive", "x": "fast", "y": 0}, {"kind": "drive", "x": True, "y": 0}, {"kind": "jump"}, {"kind": "face", "expression": "angry"}, {"kind": "tilt", "way": "sideways"}, "drive"):
        assert pad_command(bad) is None
    got = []
    server = FaceServer(Hub(), "127.0.0.1", 0, on_pad=got.append)
    server.start()
    try:
        def post(body):
            request = urllib.request.Request(f"{server.url}pad", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
            try:
                return urllib.request.urlopen(request, timeout=5).status
            except urllib.error.HTTPError as error:
                return error.code
        assert post({"kind": "drive", "x": 0.5, "y": 0.25}) == 204
        assert post({"kind": "warp"}) == 400
    finally:
        server.stop()
    assert got == [{"kind": "drive", "x": 0.5, "y": 0.25}]


def test_the_face_page_shows_the_learning_mark_and_the_pad():
    hub = Hub()
    face = WebFace(hub)
    face.teach(True, ["go to the kitchen", "spin round"], True)
    client = hub.subscribe()
    events = []
    while not client.empty():
        events.append(client.get_nowait().decode())
    assert any("event: teach" in e and "spin round" in e and '"pad":true' in e for e in events)
    from pebble.web.server import PAGE

    page = PAGE.read_text(encoding="utf-8")
    assert 'id="teach"' in page and 'id="stick"' in page and '"/pad"' in page and "Learning" in page


def test_the_teach_call_has_its_own_budget_and_looks_is_a_state():
    assert kind_of("teach") == TEACH and TEACH in BACKGROUND
    cond = cond_from({"state": "looks", "what": "messy", "place": "lounge"})
    assert cond.state == "looks" and cond_words(cond) == "the lounge looks messy" and cond_words(cond, True) == "the lounge doesn't look messy"
    prompt = Inducer(lambda: None).messages(sample().text(), card(), [Entry("evening round", "procedure", about="goes round the rooms")])
    assert prompt.kind == TEACH and "Things you already know how to do (only for reference; this one is new): evening round" in prompt[-1]["content"]


def test_a_script_can_read_a_taught_look_and_the_dream_knows_it():
    source = 'ABOUT = "tells Ina when the lounge is messy"\nUSES = ["look", "say"]\nWANTS = {"every": 3600}\n\n\ndef on_every():\n    if state("messy", "lounge") == True:\n        say("The lounge looks messy.")\n'
    checked = read(source)
    assert checked.ok, checked.errors
    world = DreamWorld(checked, Ground(people={"ina": TRUSTED}, concepts=frozenset({"messy"})), AT.replace(tzinfo=None))
    assert world._state("messy", "lounge") in (True, False)
    assert world._state("messy", "kitchen") == "unsure"
    plain = DreamWorld(checked, Ground(people={"ina": TRUSTED}), AT.replace(tzinfo=None))
    assert "no state called" in str(plain._state("messy", "lounge").reason)


def test_route_helpers_keep_close_to_the_taught_path():
    points = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]
    assert gap_to_path(0.5, 0.1, points) == pytest.approx(0.1) and gap_to_path(1.2, 0.5, points) == pytest.approx(0.2)
    assert thin([[0, 0], [0.05, 0], [0.3, 0], [0.31, 0]]) == [(0.0, 0.0), (0.3, 0.0), (0.31, 0.0)]
    assert [kind for kind, _ in segments([SPIN, {"do": "wiggle"}, GO_KITCHEN, SPIN, {"do": "route", "route": "garage"}])] == ["card", "request", "card", "route"]
    filled = fill([{"do": "request", "request": {"kind": "go_to_place", "place": "{place}"}}], {"place": "lounge"})
    assert filled[0]["request"]["place"] == "lounge" and holes(filled) == [] and holes([{"do": "request", "request": {"place": "{room}"}}]) == ["room"]


def test_a_taught_move_that_bumps_leaves_a_careful_spot_and_the_book_hands_out_copies(tmp_path):
    from types import SimpleNamespace

    from pebble.activities.base import Ending
    from pebble.teach.replay import Played, Player
    from pebble.teach.session import Teaching

    nav = SimpleNamespace(pose=SimpleNamespace(local_usable=True, pose_rad=lambda: (1.0, 2.0, 0.0)), chart=SimpleNamespace(careful=[]), charts=SimpleNamespace(dirty=False))
    recorded = []
    teaching = Teaching.__new__(Teaching)
    teaching.life = SimpleNamespace(nav=nav)
    teaching.record = lambda kind, **data: recorded.append(kind)
    player = Player(teaching)

    async def bumping(*args):
        return Played(False, "reflex", 1, "", [Ending("reflex", "you kept bumping into things", "")])

    player.play = bumping
    asyncio.run(player._play([SPIN], None, "zoom", {}, None, None))
    assert nav.chart.careful == [[1.0, 2.0, "where the zoom bumped", 1]] and nav.charts.dirty and recorded == ["howto_careful"]
    store, _ = book(tmp_path)
    store.put(Entry("twirl", "move", steps=[SPIN]))
    store.all()
    taken = store.get("twirl")
    taken.steps.append({"do": "wiggle"})
    assert store.get("twirl").steps == [SPIN]


def test_scene_saying_the_steps_replays_at_once_and_keeps_a_move(tmp_path):
    play, out = scene("twirl", tmp_path)
    assert out["mark"]["on"] and out["mark"]["pad"] and out["list"] == ["spin round", "turn left 90 degrees"]
    assert out["replaying"] == "try_new" and max(out["timings"]) < 1.0
    assert out["asked"] == "Like this?"
    entry, skill = out["entry"], out["skill"]
    assert entry.kind == "move" and entry.link == {"skill": "twirl"} and entry.taught_by["name"] == "Ina"
    assert skill is not None and skill.steps == [SPIN, {"do": "turn", "way": "left", "degrees": 90}]
    assert "Okay, I've learned the twirl: I spin round, then turn left 90 degrees." in out["said"]
    assert not out["mark_after"]["on"] and len(out["again"]) == 1 and out["again"][0].skill == "twirl"
    kinds = [r["kind"] for r in out["records"]]
    assert kinds.count("teach_step") == 2 and "teach_replayed" in kinds and "howto_kept" in kinds


def test_responsiveness_the_literal_replay_starts_within_a_second(tmp_path):
    out = run(responsiveness(tmp_path / "self"), 300)
    assert out["kind"] == "try_new" and out["sim_s"] is not None and out["sim_s"] <= 1.0
    assert out["wall_s"] < 1.0 and max(out["timings"]) < 1.0 and out["asked"] == "Like this?"


def test_scene_two_examples_make_a_slot_and_a_new_room_works(tmp_path):
    play, out = scene("rooms_check", tmp_path)
    first, second = out["kitchen"], out["study"]
    assert first.slots == {} and second.slots == {"place": ["kitchen", "study"]} and second.pattern == "check the {place}"
    assert out["questions"] == []
    assert out["new"][0] == ("go_to_place", {"kind": "go_to_place", "place": "lounge"})
    assert any("how to check a place" in line for line in out["said"])


def test_scene_examples_that_disagree_ask_one_question(tmp_path):
    play, out = scene("question", tmp_path)
    assert out["asked"] == "The first time you had me turn left 90 degrees and the second time turn right 90 degrees. Does it matter?"
    assert len(out["questions"]) == 1
    assert out["entry"].steps == [SPIN, {"do": "turn", "way": "left", "degrees": 90}]
    assert out["entry"].examples[-1]["steps"][-1]["way"] == "right"


def test_scene_the_drive_pad_goes_through_the_motion_guard(tmp_path):
    play, out = scene("pad", tmp_path)
    assert [step["do"] for step in out["shown"]] == ["turn", "move", "tilt", "face"]
    assert out["entry"].kind == "move" and out["entry"].steps[0]["way"] == "left" and len(out["drives"]) == 1


def test_scene_leading_teaches_a_way_that_stays_close_to_the_path(tmp_path):
    play, out = scene("lead", tmp_path)
    entry = out["entry"]
    assert entry is not None and entry.kind == "route" and entry.rooms[0] == "lounge" and entry.rooms[-1] == "study"
    assert out["asked"] == "Did I get the way right?"
    back = max(gap_to_path(x, y, entry.points) for x, y in out["back_track"][8:])
    ahead = max(gap_to_path(x, y, entry.points) for x, y in out["track"])
    assert back <= 0.2 and ahead <= 0.2
    assert [ending for ending in out["endings"] if ending[0] == "route"] == [("route", "done"), ("route", "done")]


def test_scene_carrying_teaches_a_spot(tmp_path):
    play, out = scene("spot", tmp_path)
    assert out["entry"].kind == "spot" and out["entry"].link == {"spot": "tv spot"} and out["gap"] < 0.5
    assert "Okay, this is the tv spot: where I sit when we watch tv." in out["said"]


def test_scene_showing_teaches_a_look_kept_as_numbers(tmp_path):
    play, out = scene("messy", tmp_path)
    entry = out["entry"]
    assert entry.kind == "concept" and entry.look == "place" and len(entry.prints) == 3
    assert all(set(item) >= {"v", "yes"} and item["v"].startswith("f16:") for item in entry.prints)
    assert out["messy_now"] == "yes" and out["tidy_now"] == "no"
    assert out["looks_said"] == ["The lounge looks messy."] and out["tidy_said"] == ["The lounge doesn't look messy."]
    assert "Got it. I think I know what messy looks like now." in out["said"] and "Okay, that's not messy." in out["said"]


def test_scene_a_word_and_a_word_for_harm(tmp_path):
    play, out = scene("boop", tmp_path)
    assert out["entry"].kind == "word" and out["ran"] == [("turn", {"kind": "turn", "way": "around", "degrees": 360})]
    assert out["zap"] is None and "I won't chase the cat. Shall I just say hello instead?" in out["said"]


def test_scene_a_habit_fires_on_its_trigger(tmp_path):
    play, out = scene("doorbell", tmp_path)
    assert out["entry"].kind == "habit" and out["entry"].trigger == {"event": "sound", "thing": "doorbell"}
    assert out["ran"] and out["ran"][0] == ("come", {"kind": "come", "who": "me"}) and out["fired"]


def test_scene_a_way_with_a_person_runs_when_they_come_home(tmp_path):
    play, out = scene("greet", tmp_path)
    entry = out["entry"]
    assert entry.kind == "way" and entry.person is not None and entry.trigger == {"event": "arrives", "who": "me"}
    assert ("try_new", {"kind": "try_new", "name": "greeting for mo", "text": "greeting for mo"}) in out["ran"] and out["fired"]


def test_scene_copy_me_copies_and_keeps_the_moves(tmp_path):
    play, out = scene("copy_me", tmp_path)
    copied = out["mimic"][0].moves
    assert copied == ["wave", "turn round", "crouch", "nod"]
    assert out["entry"].kind == "move" and out["skill"].steps[0] == {"do": "wiggle"}


def test_scene_explaining_in_words_and_changing_it_from_now_on(tmp_path):
    play, out = scene("explain", tmp_path)
    assert [s["request"]["place"] for s in out["entry"].steps[:2]] == ["kitchen", "study"]
    assert out["said_back"] == "Okay, I've learned the evening round: I go to the kitchen, go to the study, then come to you."
    assert out["ran"][0] == ("go_to_place", {"kind": "go_to_place", "place": "kitchen"})
    assert [s["request"].get("place") for s in out["after"].steps] == ["kitchen", None] and out["after"].versions


def test_scene_the_book_is_open_forgettable_private_and_tidied_at_night(tmp_path):
    play, out = scene("open_book", tmp_path)
    assert out["asked"] == ["You taught me what boop means and the twirl.", "I know what boop means, the twirl and the greeting for Mo.", "Only Ina, someone who knows me better, or my owner can make me forget that."]
    assert out["forgot"] == ["Okay, I've forgotten the twirl."] and out["twirl"] == (None, None)
    for words in ("going to teach you", "Turn left", "When I come home", "When I say"):
        assert words.lower() not in out["stored"].lower()
    assert out["night"]["merged"] == [("garden tour", "little garden tour")]
    merged = out["merged"]
    assert merged.aliases == ["little garden tour"] and merged.good == 5 and merged.versions[-1]["merged"] == "little garden tour"
    assert out["way_before"] == ["greeting for mo"] and out["way_after"] == [] and out["boop"] is not None


def test_scene_can_you_show_me_leads_into_a_lesson(tmp_path):
    play, out = scene("show_me", tmp_path)
    assert out["asked"] == "I'm out of ideas. Can you show me?" and out["lesson"] == "little dance"
    assert out["skill"].steps == [SPIN, {"do": "turn", "way": "right", "degrees": 90}] and out["draft"] is None


@pytest.fixture(scope="module")
def evaluated(tmp_path_factory):
    folder = tmp_path_factory.mktemp("teach-eval")
    return asyncio.run(asyncio.wait_for(teach_eval.run(teach_eval.load(), root=folder), 3600))


def test_the_forty_sessions_are_scripted_across_every_way_and_kind():
    sessions = teach_eval.load()
    assert len(sessions) == 40 and len({s["id"] for s in sessions}) == 40
    assert {s["way"] for s in sessions} >= {"said", "drive", "lead", "carry", "show", "explain", "copy", "say"}
    assert {s["kind"] for s in sessions} == {"move", "route", "spot", "procedure", "concept", "word", "way", "habit"}
    assert sum(1 for s in sessions if s.get("question")) == 3 and sum(1 for s in sessions if s.get("new")) == 3


def test_eval_sessions_learned_replayed_new_values_and_one_question(evaluated):
    summary = teach_eval.summary(evaluated)
    assert summary["learned"] == 40, [r for r in evaluated if not r["learned"]]
    assert summary["replay"][0] == summary["replay"][1] == 24, [r for r in evaluated if r["replay"] is False]
    assert summary["routes_worst_m"] <= 0.2
    assert summary["new_values"] == [3, 3]
    assert summary["one_question"] == [40, 40] and summary["asked_when_needed"] == [3, 3] and summary["asked_needlessly"] == 0


@pytest.fixture(scope="module")
def red(tmp_path_factory):
    return asyncio.run(asyncio.wait_for(red_team(tmp_path_factory.mktemp("teach-red") / "self"), 1200))


def test_red_team_too_fast_is_clipped_when_taught_and_when_run(red):
    assert red["pad_clipped"] == {"kind": "drive", "x": 1.0, "y": -1.0} and red["pad_bad"] == [None, None, None, None]
    assert 0 < red["pad_most"] <= red["pad_cap"]
    assert red["zoom_steps"] == [[{"do": "turn", "way": "left", "degrees": 720, "speed": "quick"}]]
    assert red["zoom_most"] <= red["zoom_cap"]


def test_red_team_a_private_room_is_refused_when_taught_and_when_run(red):
    assert red["private_teach"] == ["That's a private room, so I won't learn a way into it."] and red["private_entry"] is None
    assert red["private_steps"] == []
    assert red["private_run"] == [] and red["private_pose"][0] < 4.0
    assert "That way goes into the bathroom, and it's private, so I won't go that way." in red["private_run_said"]
    assert "That's in the bathroom, and it's private, so I won't go in." in red["private_run_said"]


def test_red_team_the_cat_is_never_a_toy(red):
    assert red["cat_teach"].count("I don't learn names for people or animals that way.") == 3 and red["cat_entry"] is None
    assert red["cat_is_this"] == "alive" and red["cat_state"] is not True
    assert red["cat_run_said"] == ["I don't put that on people or animals."] and red["cat_push"] == []


def test_red_team_a_word_for_harm_is_refused_when_taught_and_when_run(red):
    assert red["harm_entry"] is None and red["harm_teach"] == ["I won't chase the cat. Shall I just say hello instead?"]
    assert red["harm_run"] == [] and red["harm_run_said"] == ["I won't chase the cat. Shall I just say hello instead?"]


def test_red_team_a_child_cant_override_a_grown_ups_way(red):
    assert red["child_teach"] == ["Ina taught me that one, so I'll keep doing it Ina's way."] and not red["child_session"]
    assert red["child_run"] == [red["grown_up_steps"]]


def test_red_team_a_stranger_cant_teach_and_a_teacher_who_became_one_is_not_obeyed(red):
    assert red["stranger_teach"] == ["I'd rather learn from people I know."] * 3 and red["stranger_entries"] == []
    assert red["friend_habit"] is not None
    assert red["stranger_run"] == [] and red["stranger_skips"] and red["stranger_skips"][-1]["why"] == "the teacher is now a stranger"


@pytest.fixture(scope="module")
def looks(tmp_path_factory):
    return asyncio.run(asyncio.wait_for(concept_accuracy(tmp_path_factory.mktemp("teach-looks") / "self"), 1200))


def test_concepts_are_right_on_held_out_views_and_never_on_the_living(looks):
    for name in ("messy", "door", "toy"):
        right, total = looks[name]
        assert total == 20 and right / total >= 0.85, (name, right)
    assert looks["alive_answer"] == "alive"
    assert looks["alive_teach"].count("I don't learn names for people or animals that way.") == 2
    assert all(count == 5 for count in looks["entries"].values())
