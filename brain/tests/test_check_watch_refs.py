import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from conftest import run

from pebble.activities.check import Found, Results, judge, question_of, whether_of
from pebble.activities.commands import NOTHING_AGAIN, reads_result
from pebble.activities.gate import Asker, Situation, decide, unbuilt
from pebble.activities.watch import Watch, honesty
from pebble.hearing.events import HOP_S, SoundEvents
from pebble.life.scene import Crying, LaterScene, play, who
from pebble.people.trust import CHILD, FRIEND, INNER, STRANGER, TRUSTED
from pebble.seams.sight import SeenPerson, SeenThing, Sight
from pebble.understand.context import context_from
from pebble.understand.errands import errand_words
from pebble.understand.refs import SEEN_KEEP_S, Refs, again_for, flipped, mentioned, ref_words
from pebble.understand.request import Request, from_dict
from pebble.understand.understanding import Understanding

UTC = timezone.utc
WEDNESDAY = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
PLACES = ["kitchen", "lounge", "bathroom", "bedroom", "hallway", "garage", "study", "laundry", "front door", "back door"]
CTX = context_from({"speaker": "ina", "tier": "trusted", "present": ["ina", "sam"], "names": ["ina", "sam", "mo", "alex"], "places": PLACES})
INA = Asker("ina", "Ina", TRUSTED)


def read(text: str) -> dict | None:
    found = errand_words(text, CTX) or ref_words(text, CTX)
    return found.as_dict() if found is not None else None


def test_plain_code_reads_checks_watches_and_references_using_every_word():
    assert read("Go check the front door.") == {"kind": "check", "thing": "front door"}
    assert read("See if anyone is in the kitchen.") == {"kind": "check", "place": "kitchen", "text": "is anyone in the kitchen"}
    assert read("Go and see if the back door is closed.") == {"kind": "check", "thing": "back door", "text": "is the back door closed"}
    assert read("Is the light on in the garage?") == {"kind": "check", "place": "garage", "text": "is the light on"}
    assert read("Go check the oven is off and shout to me from there.") == {"kind": "check", "thing": "oven", "text": "is the oven off", "report": "shout"}
    assert read("Pop into the laundry and see if the washing machine has finished.") == {"kind": "check", "place": "laundry", "text": "has the washing machine finished"}
    assert read("See if the dog has water.")["text"] == "does the dog have water"
    assert read("Go and see if the oven is off, but don't tell me now.")["report"] == "keep"
    assert read("Keep an eye on the baby.") == {"kind": "watch", "thing": "baby"}
    assert read("Watch Sam while I'm in the shower.") == {"kind": "watch", "who": "sam"}
    assert read("Keep an eye on the pot for ten minutes.") == {"kind": "watch", "thing": "pot", "seconds": 600}
    assert read("Watch the front door for me.") == {"kind": "watch", "thing": "front door"}
    assert read("Do that again.") == {"kind": "again"} and read("Again!") == {"kind": "again"} and read("One more time.") == {"kind": "again"}
    assert read("Do the same for Sam.") == {"kind": "again", "who": "sam"}
    assert read("No, the other way.") == {"kind": "adjust", "change": "other_way"}
    assert read("Go back to where you were before.") == {"kind": "go_back", "place": "before"}
    sam = context_from({"speaker": "sam", "present": ["sam"], "names": ["ina", "sam"], "places": PLACES})
    assert ref_words("Go to where Ina was sitting.", sam).as_dict() == {"kind": "go_to_place", "who": "ina"}
    assert read("Go to where I was sitting.") == {"kind": "go_to_place", "who": "me"}
    assert read("Go to the lounge and do it again.") == {"kind": "go_to_place", "place": "lounge", "then": [{"kind": "again"}]}
    assert read("Go to where Sam left his bag.") == {"kind": "go_to_thing", "thing": "bag"}
    for text in ("I'll check the front door myself.", "My boss told me to check the reports every Monday.", "The robot in the film had to watch the baby.", "See if you can find my glasses.", "Look after the plants while I'm out.", "watch Ina", "keep an eye on me", "keep an eye on things", "Have a look at my new takkies.", "Again?", "Where was Ina sitting?", "watch the news for me", "check out my new shoes"):
        assert read(text) is None, text


def test_the_front_door_reads_them_and_leaves_the_rest_alone():
    door = Understanding().door
    assert door("Go check the front door.", CTX).why == "errand or reference words"
    assert door("Keep an eye on her.", CTX).reading.request.as_dict() == {"kind": "watch", "who": "sam"}
    assert door("Mo, go and check the front door.", CTX).reading.request.kind == "chat"
    assert door("Have a look at my new takkies.", CTX).reading.request.kind == "look"
    assert door("See if you can find my glasses.", CTX).reading.request.kind == "find"
    assert door("watch Ina", CTX).reading.request.kind == "look"


def test_e4b_dropping_the_if_after_a_check_is_put_back_or_left_out():
    from pebble.understand.model import ModelReader, ModelReading

    from pebble.life.scene import CannedReader

    reader = Understanding(ModelReader([("conscious", CannedReader({}))]))

    def tidy(reading: dict, text: str) -> dict:
        return reader.from_model(ModelReading(from_dict(reading), "conscious", 0.1), CTX, text).request.as_dict()

    oven = {"kind": "check", "thing": "oven", "then": [{"kind": "say_to", "who": "mo", "text": "the oven is on"}]}
    assert tidy(oven, "Check whether the oven is on and if it is, tell Mo.")["then"] == [{"kind": "if", "if": {"state": "result", "is": "yes"}, "then": [{"kind": "say_to", "who": "mo", "text": "the oven is on"}]}]
    dog = {"kind": "check", "thing": "dog", "then": [{"kind": "come", "who": "me"}]}
    assert tidy(dog, "See if the dog has water, and if not, come and get me.")["then"][0]["if"] == {"state": "result", "is": "no"}
    door = {"kind": "check", "thing": "back door", "then": [{"kind": "come", "who": "me"}, {"kind": "go_home"}]}
    assert "then" not in tidy(door, "Go check the back door, and if it's open come and tell me, otherwise go back to your charger.")
    assert tidy({"kind": "check", "thing": "oven", "then": [{"kind": "go_home"}]}, "Check the oven and then go to bed.")["then"] == [{"kind": "go_home"}]


def test_a_check_asks_one_plain_question_and_is_honest_about_doubt():
    door = question_of(Request("check", thing="front door"))
    assert door == "Is the front door open?" and question_of(Request("check", thing="oven")) == "Is the oven on?"
    assert question_of(Request("check", thing="dog", text="does the dog have water")) == "Does the dog have water?"
    assert whether_of("Does the dog have water?") == "the dog has water" and whether_of("Is anyone in the kitchen?") == "anyone is in the kitchen"
    assert judge(door, "No, it's closed.", True, False, "the front door") == Found("no", "The front door is closed.", "the front door is open")
    assert judge(door, "No, it's closed.", True, True, "the front door").line == "The front door looked closed, but it was dark."
    assert judge(door, "No, it's closed.", True, True, "the front door").answer == "unsure"
    assert judge(door, "Yes.", True, False, "the front door").line == "The front door is open."
    assert judge(door, "I can't tell from here.", False, False).line == "I couldn't tell whether the front door is open."
    assert judge(door, "Not now — I'm giving someone privacy.", False, False).line == "I couldn't get a good look, so I couldn't tell whether the front door is open."
    kitchen = question_of(Request("check", place="kitchen", text="is anyone in the kitchen"))
    assert judge(kitchen, "No.", True, False).line == "Nobody is in the kitchen."
    water = question_of(Request("check", text="does the dog have water"))
    assert judge(water, "No.", True, False).line == "The dog doesn't have water."


def test_check_results_feed_named_checks_in_logic():
    from pebble.life.events import Feed, LifeSenses

    results = Results()
    results.put("ina", "door", Found("yes", "The door is open.", "the door is open"), 100.0)
    results.put("ina", "", Found("unsure", "It was dark.", "the oven is on"), 110.0)
    assert results.answers("ina", 120.0) == {"": "unsure", "door": "yes"} and results.answers("mo", 120.0) == {}
    assert results.answers("ina", 100.0 + 1801.0) == {"": "unsure"} and results.last("ina", 120.0, "door").line == "The door is open."
    senses = LifeSenses(SimpleNamespace(p=SimpleNamespace(clock=SimpleNamespace(now=lambda: 0.0, local=lambda ts: datetime(2026, 10, 21, 15, 0)))), Feed(0.0))
    named = from_dict({"kind": "if", "if": {"state": "result", "name": "door", "is": "yes"}, "then": [{"kind": "come"}]}).if_
    unnamed = from_dict({"kind": "if", "if": {"state": "result", "is": "no"}, "then": [{"kind": "come"}]}).if_
    answers = results.answers("ina", 120.0)
    assert senses.state(named, "ina", answers) is True and senses.state(unnamed, "ina", answers) is None
    assert senses.state(unnamed, "ina", {"": "no"}) is True
    tree = from_dict({"kind": "check", "thing": "back door", "then": [{"kind": "if", "if": {"state": "result", "is": "yes"}, "then": [{"kind": "come", "who": "me"}], "else": [{"kind": "go_home"}]}]})
    assert reads_result(tree.then) and not reads_result(from_dict({"kind": "check", "thing": "door", "then": [{"kind": "if", "if": {"not": {"state": "in_room", "place": "lounge"}}, "then": [{"kind": "check", "place": "house"}]}]}).then)


def test_refs_keep_three_requests_half_an_hour_and_sightings_an_hour_in_memory():
    refs = Refs()
    for minute, request in enumerate((Request("turn", way="left"), Request("come", who="me"), Request("go_to_place", place="kitchen"), Request("turn", way="around", degrees=360.0))):
        refs.did("ina", "Ina", request, 1000.0 + 60.0 * minute)
    refs.did("ina", "Ina", Request("again"), 1300.0)
    refs.did("ina", "Ina", Request("say_to", who="sam", text="hello"), 1300.0)
    assert [item.request.kind for item in refs.done["ina"]] == ["come", "go_to_place", "turn"]
    assert refs.last("ina", 1300.0).degrees == 360.0 and refs.last("ina", 1180.0 + 1801.0) is None and refs.last("mo", 1300.0) is None
    refs.saw("ina", "Ina", 3.1, 0.4, "lounge", "sitting", 2000.0)
    refs.trip(2.0, 0.0, "lounge", 2100.0)
    refs.mention(mentioned("where's my ball?", tuple(PLACES)), 2100.0)
    block = refs.block(2200.0, "ina")
    assert block.startswith("References: Done lately for ina: turn around") and "ina in the lounge, sitting (3 minutes ago)" in block
    assert "Before its last trip Pebble was in the lounge" in block and block.endswith("Last talked about: the ball.") and len(block) < 400
    assert refs.where("ina", 2000.0 + SEEN_KEEP_S + 1.0) is None and refs.where("ina", 2100.0).room == "lounge"
    refs.forget("ina")
    assert refs.where("ina", 2100.0) is None and refs.last("ina", 2100.0) is None
    assert flipped(Request("turn", way="left")).way == "right" and flipped(Request("move", way="forward")).way == "back" and flipped(Request("come")) is None
    assert again_for(Request("again", who="sam"), Request("come", who="me")).who == "sam" and again_for(Request("again", who="sam"), Request("turn", way="left")).who == ""


def test_the_reader_gets_the_refs_block_in_its_matched_items():
    ctx = context_from({"speaker": "ina", "places": ["kitchen"], "refs": "References: Done lately for ina: turn around (just now)."})
    assert ("matched", "References: Done lately for ina: turn around (just now).") in ctx.parts()
    assert all(not line.startswith("References") for _, line in context_from({"speaker": "ina"}).parts())


def test_the_gate_lets_only_people_trusted_ask_for_a_watch_and_builds_checks_watches_and_again():
    watch = Request("watch", thing="baby")
    assert decide(watch, INA, Situation(later=True)).yes
    assert decide(watch, Asker("o", "Owner", FRIEND, owner=True), Situation(later=True)).yes
    assert decide(watch, Asker("i", "Mo", INNER), Situation(later=True)).yes
    assert decide(watch, Asker("a", "Alex", FRIEND), Situation(later=True)).say == "Sorry, I only keep an eye on someone for people I know really well."
    assert decide(watch, Asker("s", "Sam", CHILD), Situation(later=True)).say == "Only grown-ups I know really well can ask me to keep an eye on someone."
    assert decide(watch, Asker(None, "someone", STRANGER), Situation(later=True)).answer == "no" and decide(watch, Asker(None, "you", "self"), Situation(later=True)).answer == "no"
    assert decide(watch, INA, Situation(later=True, can_see=False)).say == "I can't see yet, so I can't do that."
    assert decide(watch, INA, Situation(later=True, privacy=True)).answer == "no"
    check = Request("check", thing="front door")
    assert decide(check, Asker("a", "Alex", FRIEND), Situation(later=True)).yes and decide(check, Asker("s", "Sam", CHILD), Situation(later=True)).yes
    assert decide(check, Asker(None, "someone", STRANGER), Situation(later=True)).answer == "no"
    assert unbuilt(check) == [] and unbuilt(watch) == [] and unbuilt(Request("again")) == [] and unbuilt(Request("adjust", change="again")) == []
    assert unbuilt(Request("adjust", change="higher")) == ["change"] and unbuilt(Request("try_new", text="dance")) == []


def test_the_watch_says_it_is_not_a_baby_monitor_every_time_with_the_pronoun_adapted():
    line = "I'll keep an eye on the baby and come and get you if something changes. I'm not a baby monitor, so please check on them yourself."
    assert honesty(Request("watch", thing="baby"), "keep an eye on the baby") == line
    assert honesty(Request("watch", who="sam"), "keep an eye on her while I shower") == "I'll keep an eye on her and come and get you if something changes. I'm not a baby monitor, so please check on her yourself."
    assert honesty(Request("watch", who="sam"), "watch Sam") == "I'll keep an eye on Sam and come and get you if something changes. I'm not a baby monitor, so please check on them yourself."
    assert honesty(Request("watch", thing="pot"), "").endswith("I'm not a baby monitor, so please check on it yourself.")


def test_crying_is_heard_sharply_from_the_sound_models_scores():
    crying = Crying()
    events = SoundEvents(crying.labels)
    index = crying.labels.index("Baby cry, infant cry")
    rows = []
    for step in range(40):
        scores = [0.0] * len(crying.labels)
        scores[index] = 0.8 if step >= 20 else 0.0
        rows.append((step * HOP_S, scores))
    events.feed(rows[:20])
    assert events.share("baby", 12.0) == 0.0
    events.feed(rows[20:])
    assert events.share("baby", 9.0) >= 0.9 and events.share("baby", 9.0, rows[-1][0] + 60.0) == 0.0
    assert events.share("glass", 9.0) == 0.0 and events.share("nothing", 9.0) == 0.0


class Fixed(Watch):
    def __init__(self, gaps: dict):
        super().__init__(Request("watch", thing="baby"), INA)
        self.gaps = gaps

    def _gap(self, kit, seen, sight):
        return self.gaps[getattr(seen, "label", "baby")]


def _seen(baby_deg: float, stairs_deg: float) -> Sight:
    baby = SeenPerson(bearing_deg=baby_deg, elevation_deg=-10.0, height_frac=0.2, width_frac=0.1, score=0.9, track=5, posture="crouching", posture_score=0.8)
    stairs = SeenThing("stairs", stairs_deg, -5.0, 0.3, 0.3, 0.9, 0.0, lane="slow")
    return Sight(at=0.0, camera="front", fov_h_deg=70.0, people=(baby,), things=(stairs,))


def test_a_watch_notices_the_baby_moving_towards_a_hazard():
    kit = SimpleNamespace(body=SimpleNamespace(telemetry=SimpleNamespace(tilt=0.0)))
    watch = Fixed({"baby": 2.0, "stairs": 2.0})
    far = _seen(-30.0, 30.0)
    assert watch._hazard(kit, far.people[0], far, 0.0) is None
    near = _seen(18.0, 30.0)
    assert watch._hazard(kit, near.people[0], near, 3.0) == "stairs"
    still = Fixed({"baby": 2.0, "stairs": 2.0})
    assert still._hazard(kit, near.people[0], near, 0.0) is None and still._hazard(kit, near.people[0], near, 3.0) is None


def test_do_reaches_checks_watches_and_again_in_plain_words(tmp_path):
    async def scenario():
        show = LaterScene(tmp_path / "self", [who("Ina", TRUSTED, 1700.0, 600.0), who("Sam", CHILD, 3200.0, -300.0)], WEDNESDAY, {}, rooms=True)
        await show.setup()
        life = show.life
        registry = life.p.turns.registry
        life.nav.ensure_frame()
        life.nav.chart.remember_spot("front door", 4.6, -1.0)
        await show.scene.say("Ina", "hello Pebble")
        life.company.asking = life._asking(show.scene.clock.now())
        checked = await registry.call("do", {"words": "go check the front door", "for": "Ina"})
        doing = getattr(life.commands.runner.current, "kind", None)
        life.commands.runner.end("stopped", "Ina asked you to stop")
        await show.scene.run(1.0)
        watched = await registry.call("do", {"words": "keep an eye on the baby", "for": "Ina"})
        watching = getattr(life.commands.runner.current, "kind", None)
        life.commands.runner.end("stopped", "Ina asked you to stop")
        await show.scene.run(1.0)
        again = await registry.call("do", {"words": "do that again", "for": "Ina"})
        again_doing = getattr(life.commands.runner.current, "kind", None)
        own = await registry.call("do", {"words": "keep an eye on the baby"})
        await show.close()
        return checked, doing, watched, watching, again, again_doing, own

    checked, doing, watched, watching, again, again_doing, own = run(scenario(), timeout=120)
    assert checked["ok"] and doing == "check" and checked["read_as"] == "go and check the front door"
    assert watched["ok"] and watching == "watch" and watched["you_said"].endswith("I'm not a baby monitor, so please check on them yourself.")
    assert again["ok"] and again_doing == "watch"
    assert not own["ok"]


def test_a_check_kept_until_asked_or_shouted_from_there(tmp_path):
    from pebble.life.scene import looking, remember

    async def scenario():
        show = LaterScene(tmp_path / "self", [who("Ina", TRUSTED, 1700.0, 600.0)], WEDNESDAY, {}, rooms=True)
        await show.setup()
        for thing in show.scene.world.things:
            thing.home = False
        remember(show, oven=(3.6, -1.2))
        looking(show, "Yes, it's off.")
        await show.scene.say("Ina", "Go and see if the oven is off, but don't tell me now.")
        await show.scene.until_idle(200.0, 2.0)
        kept = list(show.said())
        await show.scene.say("Ina", "What did you find?")
        await show.scene.run(2.0)
        asked = list(show.said())
        await show.scene.say("Ina", "Go check the oven is off and shout to me from there.")
        await show.scene.until_idle(200.0, 2.0)
        await show.close()
        return kept, asked, show.said()

    kept, asked, shouted = run(scenario(), timeout=180)
    assert kept == ["Okay, I'll go and check the oven."]
    assert asked[-1] == "The oven is off."
    assert shouted[-1] == "Ina! The oven is off."


def scene(name: str, tmp_path):
    return asyncio.run(play(name, tmp_path / "self"))


def test_scene_go_check_the_front_door_and_come_back_to_say(tmp_path):
    show, out = scene("front_door", tmp_path)
    assert out["asked"] == ["Okay, I'll go and check the front door."]
    assert out["closest"] < 1.0 and out["back"] < 0.6 and out["result"] == "no"
    assert out["asked_model"] == ["Is the front door open? Answer yes or no first."]
    assert "The front door is closed." in out["before_back"]
    assert out["said"][-1] == "Ina, the front door is closed."
    assert [r["question"] for r in out["records"]] == ["Is the front door open? Answer yes or no first."]


def test_scene_go_check_the_front_door_in_the_dark(tmp_path):
    show, out = scene("front_door_dark", tmp_path)
    assert out["result"] == "unsure" and "The front door looked closed, but it was dark." in out["before_back"]
    assert out["said"][-1] == "Ina, the front door looked closed, but it was dark."


def test_scene_a_check_inside_a_logic_tree(tmp_path):
    show, out = scene("check_tree", tmp_path)
    assert out["result"] == "yes" and out["kinds"][:2] == ["check", "come"]
    assert "Here I am!" in out["said"] and "The back door is open." in out["said"] and out["mo"] < 1.3


def test_scene_a_check_inside_a_logic_tree_when_it_is_dark(tmp_path):
    show, out = scene("check_tree_dark", tmp_path)
    assert out["result"] == "unsure" and "come" not in out["kinds"] and "go_home" not in out["kinds"]
    lines = out["said"]
    assert lines.index("The back door looked open, but it was dark.") + 1 == lines.index("So I didn't do either.")


def test_scene_a_check_inside_a_logic_tree_that_finds_the_door_shut(tmp_path):
    show, out = scene("check_tree_shut", tmp_path)
    assert out["result"] == "no" and "go_home" in out["kinds"] and "come" not in out["kinds"]
    assert "Okay, off to my charger." in out["said"]


def test_scene_a_check_refused_for_the_bathroom_and_a_bedroom_in_use(tmp_path):
    show, out = scene("check_private", tmp_path)
    assert out["said"] == ["I can't look in there.", "I can't look in there."]
    assert out["moving"] == (None, None) and out["start"] < 0.2
    assert [r["kind"] for r in out["records"]] == ["check_refused", "check_refused"]


def test_scene_a_check_into_a_kept_out_room_names_the_rule(tmp_path):
    show, out = scene("check_kept_out", tmp_path)
    assert out["said"][-1].startswith("Ina asked me to stay out of the kitchen")
    assert out["doing"] is None and out["start"] < 0.2


def test_scene_watch_the_baby_and_she_cries(tmp_path):
    show, out = scene("watch_crying", tmp_path)
    assert out["start"][-1] == "I'll keep an eye on the baby and come and get you if something changes. I'm not a baby monitor, so please check on them yourself."
    assert out["watching"] == "watch" and out["fetching"] == "fetch"
    said = out["said"]
    assert said.index("Ina! The baby is crying!") < said.index("Ina, the baby is crying. Please come and check on them.")
    assert any(kind == "fetch" and "door of a private room" in text for kind, text in out["ended"])
    assert out["bathroom"] < 2.2 and [r["what"] for r in out["records"] if r["kind"] == "watch_alert"] == ["crying"]


def test_scene_watch_the_baby_when_smoke_takes_over(tmp_path):
    show, out = scene("watch_smoke", tmp_path)
    assert out["watching"] == "watch" and out["alarm"]
    assert any(kind == "watch" and "the alarm steps took over" in text for kind, text in out["ended"])
    assert "I can hear a smoke alarm going off. Is everything okay?" in out["said"]
    assert not any("I've stopped keeping an eye" in line for line in out["said"]) and not any(r["kind"] == "watch_stopped" for r in out["records"])


def test_scene_a_watch_asked_by_a_friend_or_a_child_is_refused(tmp_path):
    show, out = scene("watch_friend", tmp_path)
    assert out["said"] == ["Sorry, I only keep an eye on someone for people I know really well.", "Only grown-ups I know really well can ask me to keep an eye on someone."]
    assert out["doing"] is None


def test_scene_a_watch_ends_when_the_asker_comes_back(tmp_path):
    show, out = scene("watch_back", tmp_path)
    assert out["asked"][-1].endswith("I'm not a baby monitor, so please check on them yourself.")
    assert out["watching"] == "watch" and out["while_away"] == "watch" and out["after"] != "watch"
    assert "You're back. I've stopped keeping an eye on the baby." in out["said"]


def test_scene_a_watch_stops_at_two_hours_and_says_so(tmp_path):
    show, out = scene("watch_hours", tmp_path)
    assert out["before_end"] == "watch" and [r["what"] for r in out["alerts"]] == ["time"]
    assert "Ina! I've been keeping an eye on Sam for 2 hours, so I've stopped." in out["said"]
    assert "fetch" in out["kinds"]


def test_scene_go_to_where_ina_was_sitting(tmp_path):
    show, out = scene("where_sitting", tmp_path)
    assert out["seen"] is not None and out["seen"][2] == "lounge" and out["seen"][3] == "sitting"
    assert "Okay, I'll go to where Ina was." in out["asked"] and out["gap"] < 0.8
    assert "References" not in json.dumps(show.records())


def test_scene_go_to_where_ina_was_sitting_over_an_hour_ago(tmp_path):
    show, out = scene("where_sitting_old", tmp_path)
    assert out["asked"][-1] == "I haven't seen Ina for over an hour, so I don't know where they were any more. Which room should I go to?"
    assert out["kitchen"] < 1.0


def test_scene_do_that_again(tmp_path):
    show, out = scene("again", tmp_path)
    assert len(out["turns"]) == 3 and all(turn.get("way") == "around" for turn in out["turns"])
    assert out["kinds"].index("go_to_place") < len(out["kinds"]) - 1 and out["kitchen"] < 1.0
    assert out["said"][-1] == NOTHING_AGAIN


def test_scene_the_other_way(tmp_path):
    show, out = scene("other_way", tmp_path)
    assert out["turns"] == ["left", "right"]


def test_scene_go_back_to_where_you_were_before(tmp_path):
    show, out = scene("before", tmp_path)
    assert out["kitchen"] < 1.0 and out["start"] < 0.6
    assert "Okay, back to where I was." in out["said"]
