import math
from datetime import datetime, timedelta, timezone

import pytest
from conftest import run

from pebble.activities.gate import FEARED, PEBBLE, Asker, Situation, decide
from pebble.alive.attention import Attention, gaze_for
from pebble.alive.book import AliveBook, Known
from pebble.alive.doings import DoingReader
from pebble.alive.dream import ThingDreamer, Today, TodayDecks
from pebble.alive.gestures import GestureReader, body_point, pointed_target
from pebble.alive.reactions import Reactions, about_looks
from pebble.alive.rooms import RoomMap
from pebble.alive.showtell import ShowAndTell, best_known, first_look, key_for, thanks
from pebble.alive.surprise import Expectations
from pebble.activities.seeing import person_gap_m
from pebble.chaos.ideas import IdeaDecks
from pebble.people.trust import CHILD, STRANGER, TRUSTED
from pebble.seams.sight import BodyPoint, SeenPerson, SeenThing, Sight
from pebble.sim.alive_scene import dock_without_tag, play
from pebble.sim.eyes import SimEyes
from pebble.sim.world import Pose, SimPerson, World, room
from pebble.things.book import ThingBook
from pebble.understand.request import Request

DAY = 86400.0
TRAITS = {"traits": {"playful": 6, "curious": 8, "cautious": 5, "affectionate": 7}}


def thing(label, bearing=0.0, elevation=-5.0, size=0.1, held=False, known=None, track=None, score=0.8, animal=False):
    return SeenThing(label, bearing, elevation, size, size, score, 0.0, "fast", animal, track, held, known, 0.9 if known else 0.0)


def person(bearing=0.0, track=1, size=0.4, face=True, facing=0.0, points=()):
    return SeenPerson(bearing, 10.0, size, size * 0.4, 0.9, face, track, tuple(points), facing)


def sight(*seen, camera="front"):
    people = tuple(s for s in seen if isinstance(s, SeenPerson))
    things = tuple(s for s in seen if isinstance(s, SeenThing))
    return Sight(0.0, camera, 70.0, people, (), things)


class FakeOdometer:
    def __init__(self, x=0.0, y=0.0, heading=0.0, travelled=0.0):
        self.x, self.y, self.heading, self.travelled_m, self.usable = x, y, heading, travelled, True

    def pose(self):
        return self.x, self.y, self.heading


class Store:
    def __init__(self):
        self.files = {}

    def read(self, name, default=None):
        return self.files.get(name, default)

    def write(self, name, data):
        self.files[name] = data


def test_the_strongest_thing_steers_the_eyes_and_a_glance_wins_for_a_moment():
    attention = Attention(novelty=lambda kind: 1.0 if kind == "teddy bear" else 0.0)
    focus = attention.update(sight(person(bearing=20.0), thing("cup", bearing=-10.0)), 0.0)
    assert focus.kind == "person"
    focus = attention.update(sight(person(bearing=20.0), thing("cup", bearing=-10.0, held=True)), 4.0)
    assert focus.kind == "thing" and focus.held and "held" in focus.why
    attention.hear_named(["teddy"], 6.0)
    focus = attention.update(sight(person(bearing=20.0), thing("teddy bear", bearing=15.0)), 7.0)
    assert focus.label == "teddy bear" and "named" in focus.why and "new" in focus.why
    attention.hear_speaker(15.0, track=1)
    focus = attention.update(sight(person(bearing=20.0), thing("teddy bear", bearing=15.0)), 15.5)
    assert focus.kind == "person" and "speaking" in focus.why
    attention.glance_at(-30.0, 0.0, 16.0, 0.5, "about to act")
    assert attention.update(sight(person()), 16.2).kind == "glance"
    assert attention.update(sight(person()), 16.6).kind != "glance"
    assert gaze_for(30.0, -22.0) == (-1.0, 1.0) and gaze_for(-90.0, 0.0) == (1.0, -0.0)


def test_attention_does_not_flit_between_close_contenders():
    attention = Attention()
    first = attention.update(sight(thing("cup", bearing=-10.0, size=0.12), thing("book", bearing=10.0, size=0.1)), 0.0)
    again = attention.update(sight(thing("cup", bearing=-10.0, size=0.1), thing("book", bearing=10.0, size=0.12)), 0.5)
    assert first.label == again.label == "cup"


def test_novelty_fades_with_exposure_and_comes_back_when_things_change():
    book = AliveBook()
    assert book.novelty("plant", 0.0) == 1.0
    for second in range(40):
        book.expose("plant", float(second), 0.05)
    tired = book.novelty("plant", 40.0)
    assert tired < 0.7
    assert book.novelty("plant", 40.0 + 60 * DAY) > tired
    book.unsettle("plant", 41.0)
    assert book.novelty("plant", 41.0) > tired


def test_tastes_start_from_personality_and_shift_with_fading_evidence():
    book = AliveBook()
    book.seed(TRAITS, 0.0)
    assert book.fear("vacuum", 10.0) >= FEARED and book.fear("vacuum cleaner", 10.0) >= FEARED
    assert book.liking("ball", 10.0) > 0.3 and book.liking("plant", 10.0) > 0.0
    assert book.liking("toaster", 10.0) < 0.0
    assert book.feel("cat", "like", 5.0, "it purred", 100.0) == 2.0
    assert book.feel("cat", "like", 1.0, "it purred again", 200.0) == 0.0
    assert book.liking("cat", 300.0) > book.liking("cat", 300.0 + 200 * DAY) > 0.0
    with pytest.raises(ValueError):
        book.feel("cat", "adore", 1.0, "", 0.0)
    again = AliveBook(book.to_dict())
    assert again.seeded and again.liking("cat", 300.0) == pytest.approx(book.liking("cat", 300.0))


def test_a_feared_thing_is_refused_even_when_asked_nicely():
    asker = Asker("p1", "Ina", TRUSTED, True)
    scared = Situation(thing_fear=0.5, can_see=True)
    verdict = decide(Request("go_to_thing", thing="vacuum"), asker, scared)
    assert verdict.answer == "no" and "scares me" in verdict.say
    assert decide(Request("go_to_thing", thing="vacuum"), PEBBLE, scared).say == ""
    assert decide(Request("go_to_thing", thing="ball"), asker, Situation(can_see=True)).answer == "yes"


def test_play_and_teach_follow_the_trust_rules():
    stranger = Asker(None, "someone", STRANGER)
    child = Asker("p3", "Sam", CHILD)
    assert decide(Request("play"), child, Situation(can_see=True)).answer == "yes"
    assert decide(Request("play"), stranger, Situation(valence=0.0, can_see=True)).answer == "no"
    assert decide(Request("teach", name="bob"), child, Situation()).answer == "yes"
    assert "people I know" in decide(Request("teach", name="bob"), stranger, Situation()).say
    assert decide(Request("where_am_i"), stranger, Situation()).answer == "yes"


def test_routines_count_once_a_day_and_expect_the_usual_hour():
    book = AliveBook()
    noon = datetime(2026, 10, 15, 12, 10, tzinfo=timezone.utc)
    assert book.saw_at("doing:cooking", noon)
    assert not book.saw_at("doing:cooking", noon + timedelta(minutes=20))
    for back in range(1, 7):
        book.saw_at("doing:cooking", noon - timedelta(days=back))
    assert book.usual("doing:cooking", noon) > 3.0
    assert book.usual("doing:cooking", noon - timedelta(hours=3)) == 0.0


def furnished_book() -> ThingBook:
    book = ThingBook({})
    for label, x, y in (("refrigerator", 8.6, 2.5), ("oven", 7.3, 2.6), ("microwave", 6.3, 2.7), ("couch", 3.0, -1.8), ("tv", 3.2, 1.9), ("desk", 8.0, -2.6), ("laptop", 8.0, -2.4)):
        for at in range(3):
            book.note(label, float(at), "front", x, y, 2.0, [], 0.8, "fast", False)
    return book


def test_rooms_come_from_the_things_seen_and_where_am_i_is_honest_about_drift():
    store = Store()
    odometer = FakeOdometer(7.4, 2.0)
    rooms = RoomMap(furnished_book(), odometer, store)
    found = dict(rooms.update())
    assert set(found) == {"kitchen", "lounge", "office"} and all(found.values())
    assert [place["name"] for place in store.files["places.json"]["places"]] == ["kitchen", "lounge", "office"]
    assert rooms.say_where() == "I think this is the kitchen."
    odometer.x, odometer.y, odometer.travelled_m = 3.1, 0.0, 30.0
    assert rooms.say_where().startswith("I think this is the lounge, but I've come a long way")
    odometer.usable = False
    assert "not sure where I am" in rooms.say_where()
    assert RoomMap(furnished_book(), odometer, store).place("kitchen") is not None
    assert rooms.update() == []


def test_a_missing_thing_surprises_only_with_a_good_view_and_twice():
    book = ThingBook({})
    for at in range(4):
        book.note("potted plant", float(at), "front", 2.0, 0.0, 1.9, [], 0.8, "fast", False)
    expect = Expectations(book)
    empty = sight()
    assert expect.check(empty, (0.1, 0.0, 0.0), 0.0, 10.0) == []
    assert expect.check(empty, (0.1, 0.0, 0.0), 0.0, 10.5) == []
    found = expect.check(empty, (0.1, 0.0, 0.0), 0.0, 12.0)
    assert len(found) == 1 and found[0].kind == "missing"
    assert expect.check(empty, (0.1, 0.0, 0.0), 0.0, 20.0) == []
    other = Expectations(book)
    assert other.check(empty, (0.1, 0.0, 0.0), 15.0, 10.0) == [] and other.check(empty, (0.1, 0.0, 0.0), 15.0, 12.0) == []
    assert other.check(empty, (0.1, 0.0, 90.0), 0.0, 10.0) == [] and other.check(empty, (0.1, 0.0, 90.0), 0.0, 12.0) == []
    seen = Expectations(book)
    plant = sight(thing("potted plant", bearing=0.0))
    assert seen.check(plant, (0.1, 0.0, 0.0), 0.0, 10.0) == [] and seen.check(plant, (0.1, 0.0, 0.0), 0.0, 12.0) == []


def test_toys_and_moving_views_never_count_as_surprises():
    book = ThingBook({})
    for at in range(4):
        book.note("ball", float(at), "front", 2.0, 0.0, 1.9, [], 0.8, "fast", False)
    expect = Expectations(book)
    assert expect.check(sight(), (0.1, 0.0, 0.0), 0.0, 10.0) == [] and expect.check(sight(), (0.1, 0.0, 0.0), 0.0, 12.0) == []
    book.note("cup", 0.0, "front", 1.0, 0.0, 1.0, [], 0.8, "fast", False)
    for at in range(1, 4):
        book.note("cup", float(at), "front", 1.0, 0.0, 1.0, [], 0.8, "fast", False)
    book.note("cup", 10.0, "front", 2.5, 1.5, 1.0, [], 0.8, "fast", False)
    assert expect.moved("cup", 0.8, 1.0, 20.0, level=False) is None
    assert expect.moved("cup", 0.8, 1.0, 20.0) is None
    assert expect.moved("cup", 0.8, 1.0, 22.0).kind == "moved"


def test_doings_need_time_and_stillness_and_quiet_down_pebble():
    reader = DoingReader()
    working = sight(person(bearing=5.0), thing("laptop", bearing=8.0))
    assert reader.read(working, 0.0, 14) == []
    started = reader.read(working, 16.0, 14)
    assert [c.doing.what for c in started] == ["working"] and started[0].started and reader.hushed()
    ended = reader.read(sight(), 40.0, 14)
    assert [c.started for c in ended] == [False] and not reader.hushed()
    walking = DoingReader()
    for second in range(20):
        walking.read(sight(person(bearing=float(second))), float(second), 14, {1: (second * 0.3, 0.0)})
    assert walking.doing() == []


def test_leaving_is_read_from_a_turned_back_a_bag_and_a_shrinking_figure():
    reader = DoingReader()
    changes = []
    for step in range(8):
        size = 0.6 - step * 0.05
        seen = sight(person(bearing=0.0, size=size, facing=180.0), thing("backpack", bearing=2.0, held=True))
        changes += reader.read(seen, step * 0.5, 9)
    assert [c.doing.what for c in changes] == ["leaving"]
    stays = DoingReader()
    for step in range(8):
        stays.read(sight(person(bearing=0.0, size=0.6 - step * 0.05, facing=0.0), thing("backpack", bearing=2.0, held=True)), step * 0.5, 9)
    assert stays.doing() == []


def sim_person(arm, side="right", point_at=None, hiding=None):
    clock = [0.0]
    body = SimPerson("ina", 2100.0, 0.0, track=1, arm=arm, arm_side=side, point_at=point_at)
    world = World(table=room(9000.0, 6000.0), pose=Pose(500.0, 0.0, 0.0), people=[body])
    eyes = SimEyes(world, lambda: clock[0], lambda: 8.0, noise=False)
    reader = GestureReader()
    found = []
    while clock[0] < 4.0:
        clock[0] += 0.25
        if hiding:
            body.hiding = hiding[0] <= clock[0] < hiding[1]
        seen = eyes.latest()
        for one in seen.people:
            found += [(g, one, seen) for g in reader.read(one, seen.at)]
    return found


def test_waves_beckons_and_points_are_read_and_hanging_arms_are_not():
    assert [g.kind for g, _, _ in sim_person("wave")] == ["wave"]
    assert [g.kind for g, _, _ in sim_person("beckon")] == ["beckon"]
    assert sim_person("down") == [] and sim_person("hold") == []
    pointed = sim_person("point", "left", point_at=(2100.0, 1200.0))
    assert [g.kind for g, _, _ in pointed] == ["point"]
    gesture, one, seen = pointed[0]
    gap = person_gap_m(one, seen, None)
    x, y = pointed_target(gap, body_point(one, "left_shoulder"), body_point(one, "left_wrist"), "front", 8.0)
    assert math.hypot(x - 1.51, y - 1.2) < 0.6


def test_peekaboo_needs_a_face_that_hides_and_comes_back():
    reader = GestureReader()
    shown, hidden = person(face=True), person(face=False)
    assert reader.read(shown, 0.0) == [] and reader.read(hidden, 0.5) == []
    assert [g.kind for g in reader.read(shown, 2.0)] == ["peekaboo"]
    assert reader.read(hidden, 3.0) == [] and reader.read(shown, 9.0) == []


def test_show_and_tell_waits_for_a_close_centred_held_thing_offered_by_someone_facing():
    show = ShowAndTell()
    offered = sight(person(bearing=2.0), thing("cup", bearing=1.0, size=0.25, held=True, track=7))
    assert show.watch(offered, 0.0) is None
    assert show.watch(offered, 1.2).label == "cup"
    assert show.watch(offered, 5.0) is None
    late = ShowAndTell()
    away = sight(person(bearing=2.0, facing=180.0), thing("backpack", bearing=1.0, size=0.25, held=True, track=8))
    assert late.watch(away, 0.0) is None and late.watch(away, 2.0) is None
    far = sight(person(bearing=2.0), thing("cup", bearing=25.0, size=0.25, held=True))
    assert late.watch(far, 0.0) is None and late.watch(far, 2.0) is None


def test_taught_things_are_remembered_by_print_with_their_owner():
    book = AliveBook()
    vec = [1.0, 0.0, 0.0, 0.0]
    key = key_for(book, "cup", "", "p1")
    book.teach(Known(key, "cup", "", "p1", "Ina", "p1", 0.0, [vec]))
    assert key == "p1-cup" and key_for(book, "cup", "", "p1") == "p1-cup-2"
    found, score = best_known(book, [0.9, 0.1, 0.0, 0.0])
    assert found.key == key and score > 0.75
    assert best_known(book, [0.0, 1.0, 0.0, 0.0])[0] is None
    assert thanks(book.known[key], "p1") == "Your cup. Got it."
    assert thanks(book.known[key], "p2") == "Ina's cup. Got it."
    mine = Known("pebble-ball", "ball", "", "pebble")
    assert thanks(mine, "p1") == "My very own ball? Thank you!" and mine.title() == "my ball" and mine.title(you=True) == "your ball"
    named = Known("mr-snuggles", "teddy bear", "mr snuggles")
    assert first_look(None, named) == "Mr Snuggles!" and thanks(named, "p1") == "Mr Snuggles! I'll remember."
    again = AliveBook(book.to_dict())
    assert again.known[key].prints == [vec] and again.known[key].owner_label == "Ina"


def test_spoken_reactions_have_a_budget_and_never_mention_looks():
    reactions = Reactions(per_hour=2, gap_s=60.0)
    assert reactions.speak("Huh.", 0.0, False) == "Huh."
    assert reactions.speak("Oh!", 30.0, False) == ""
    assert reactions.speak("Oh!", 70.0, False) == "Oh!"
    assert reactions.speak("Wow.", 200.0, False) == ""
    assert reactions.speak("Wow.", 4000.0, True) == "" and reactions.speak("Wow.", 4000.0, False, hushed=True) == ""
    assert reactions.speak("Nice haircut!", 5000.0, False) == ""
    assert about_looks("you look tired and old") and not about_looks("Ina's cup. Got it.")
    assert set(reactions.refused) >= {"budget", "quiet", "hushed", "looks"}


def test_the_dreamer_works_offline_and_feeds_the_idea_cards():
    clock = [1_800_000_000.0]
    today = Today(lambda at: datetime.fromtimestamp(at, timezone.utc))
    today.saw("cat", clock[0], new=True)
    today.saw("ball", clock[0])
    today.learnt("Ina's cup", clock[0])
    assert today.diary_line(clock[0]) == "Today I saw Ina's cup, a cat and a ball."
    decks = TodayDecks(IdeaDecks({}), lambda: today.cards("drawing", clock[0]))
    assert [card.text for card in decks.decks["theme"]][:1] == ["something you saw today: Ina's cup"]
    dreamer = ThingDreamer(today, lambda: clock[0])
    dream = run(dreamer.consolidate([], ""))
    assert dream.entries[0].startswith("Today I saw") and dream.entries[1].startswith("I dreamt") and not about_looks(dream.entries[1])

    async def ask(prompt):
        assert "Never describe what anyone looks like" in prompt
        return "A cat and a ball sailed a teacup across the kitchen."

    asked = run(ThingDreamer(today, lambda: clock[0], ask).consolidate([], ""))
    assert asked.entries[1] == "I dreamt a cat and a ball sailed a teacup across the kitchen."
    assert "the mind" in asked.note
    empty = run(ThingDreamer(Today(lambda at: datetime.fromtimestamp(at, timezone.utc)), lambda: clock[0]).consolidate([], ""))
    assert empty.entries == []


def test_docking_by_sight_alone_works_from_a_known_start():
    docked, seconds, text = run(dock_without_tag(3, True), timeout=300)
    assert docked and "by sight alone" in text


@pytest.fixture(scope="module")
def alive_scene():
    return run(play(), timeout=600)


def lines(scene, kind):
    return [line for line in scene.lines if f" {kind} " in line]


def test_the_alive_scene_shows_each_behaviour(alive_scene):
    said = "\n".join(lines(alive_scene, "says"))
    noticed = "\n".join(lines(alive_scene, "notices") + lines(alive_scene, "thinks"))
    assert "you took 3 good looks at your charger and went back onto it" in noticed
    assert "Ina waved at you" in noticed and "back at a wave" in noticed
    assert "the potted plant is not" in noticed
    assert "Ooh, a cup? What's it called?" in said and "Your cup. Got it." in said and "That's Ina's cup!" in said
    assert "My very own ball? Thank you!" in said
    assert "nudged it 6 times" in noticed or "you nudged the ball" in noticed
    assert "pointed at a spot" in noticed and "Ina asked you to go where they pointed; you said yes" in noticed
    assert "played peekaboo" in noticed and "beckoned you over" in noticed
    assert "The vacuum scares me a bit." in said
    assert "I think this is the kitchen." in said and "I think this is the lounge." in said
    assert "Ina is working at the laptop, so keep quiet" in noticed
    assert "Bye! See you later." in said
    assert "so you went to wait in the kitchen" in noticed
    assert "by sight alone, without its tag" in noticed and alive_scene.world.docked()
    assert any("I dreamt" in line for line in lines(alive_scene, "diary"))
    assert not any(about_looks(line.split('"')[1]) for line in lines(alive_scene, "says") if '"' in line)


class FakeSafety:
    def __init__(self):
        self.active = False

    def heard(self, heard, loud):
        pass

    async def tick(self, quiet):
        pass

    def hold_reason(self):
        return None


def test_after_an_alarm_pebble_settles_down_before_its_own_ideas_come_back(tmp_path):
    from pebble.sim.scene import Scene, Who, household

    async def scenario():
        safety = FakeSafety()
        scene = Scene(tmp_path / "self", people=[Who("Ina", TRUSTED, 1300.0, 0.0)], things=household(), extra={"safety": safety})
        await scene.setup()
        life = scene.life
        safety.active = True
        await scene.run(3.0)
        during = decide(Request("go_to_thing", thing="ball"), PEBBLE, life.situation(thing="ball"))
        safety.active = False
        await scene.run(3.0)
        calm = life.calming()
        after = decide(Request("go_to_thing", thing="ball"), PEBBLE, life.situation(thing="ball"))
        asked = decide(Request("come", who="me"), Asker("p1", "Ina", TRUSTED, True), life.situation())
        await scene.run(125.0)
        later = decide(Request("go_to_thing", thing="ball"), PEBBLE, life.situation(thing="ball"))
        await scene.close()
        return during, calm, after, asked, later

    during, calm, after, asked, later = run(scenario(), timeout=120)
    assert during.answer == "no" and "alarm" in during.reason
    assert calm and after.answer == "no" and "settling down" in after.reason
    assert asked.answer == "yes"
    assert later.answer == "yes"


def test_hearing_said_to_the_room_or_overheard_takes_the_quiet_path(tmp_path):
    from pebble.people.fake import fake_print
    from pebble.sim.scene import Scene, Who, household

    async def scenario():
        scene = Scene(tmp_path / "self", people=[Who("Ina", TRUSTED, 1300.0, 0.0)], things=household())
        await scene.setup()
        life = scene.life
        people = len(life.p.books.people.people)
        life.hear("so then he said the cat was asleep", fake_print("stranger", "voice"), addressed=False)
        overheard = (len(life.p.books.people.people), list(life._heard))
        life.hear("follow me", fake_print("ina", "voice"), addressed=False)
        await scene.run(1.0)
        moved = life.commands.runner.current
        life.hear("come here", fake_print("ina", "voice"), addressed=True)
        await scene.run(1.0)
        came = life.commands.runner.current.kind if life.commands.runner.current else None
        heard = list(life._heard)
        room = await life.commands.answer_room(life.company.hear("what can you see?", fake_print("ina", "voice")))
        pending = life.commands.pending
        await scene.close()
        return people, overheard, moved, came, heard, room, pending

    people, overheard, moved, came, heard, room, pending = run(scenario(), timeout=60)
    assert overheard == (people, []) and moved is None
    assert came == "come" and heard == []
    assert room.startswith("I can see") and pending is None


def test_forgetting_someone_scrubs_what_pebble_learnt_about_them(tmp_path):
    from pebble.sim.scene import Scene, Who, household

    async def scenario():
        scene = Scene(tmp_path / "self", people=[Who("Ina", TRUSTED, 1300.0, 0.0)], things=household())
        await scene.setup()
        alive = scene.life.alive
        ina = scene.life.p.books.people.find("ina")
        alive.book.teach(Known("ina-cup", "cup", "", ina.id, "Ina", ina.id, 0.0, [[1.0, 0.0]]))
        alive.book.feel("ball", "like", 1.0, "Ina gave you your very own ball", 0.0)
        alive.book.saw_at(f"person:{ina.id}", scene.clock.local())
        for forget in scene.life.overnight.forgetters:
            forget(ina.id, ["Ina"])
        saved = scene.life.p.store.read("alive.json")
        await scene.close()
        return ina.id, saved

    person_id, saved = run(scenario(), timeout=60)
    cup = next(k for k in saved["known"] if k["key"] == "ina-cup")
    assert cup["owner"] is None and cup["owner_label"] == "" and cup["taught_by"] is None
    assert f"person:{person_id}" not in saved["routine"]
    assert all("Ina" not in entry[3] for entries in saved["taste"].values() for entry in entries)
