import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from conftest import run

from pebble.activities.gate import Asker, Situation, decide, unbuilt
from pebble.house.rules import RULES, HouseRules, Rule, in_window, limit_s
from pebble.life.messages import new_words, spoken, theirs, to_you
from pebble.life.scene import CannedReader, LaterScene, ROOMS, STUDY, play, usual, who
from pebble.people.trust import CHILD, FRIEND, INNER, STRANGER, TRUSTED
from pebble.understand.context import context_from
from pebble.understand.cover import for_later, not_for_me
from pebble.understand.model import ModelReader, ModelReading
from pebble.understand.request import Request, from_dict
from pebble.understand.resolve import resolve
from pebble.understand.telling import message_words, relayed, rule_words, telling
from pebble.understand.understanding import Understanding

UTC = timezone.utc
WEDNESDAY = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
CTX = context_from({"speaker": "ina", "tier": "trusted", "present": ["ina", "sam"], "names": ["ina", "sam", "mo", "alex"], "places": ["kitchen", "lounge", "study", "bathroom"]})


def asker(life, name: str) -> Asker:
    return life.commands.asker_for(life.company.book.find(name).id)


def staged(tmp_path, people=None, rooms=False, at=WEDNESDAY):
    return LaterScene(tmp_path / "self", people or [who("Ina", TRUSTED), who("Alex", FRIEND, 1500.0, -400.0), who("Sam", CHILD, 900.0, 900.0)], at, {}, rooms=rooms)


def said(show) -> list[str]:
    return show.said()


def test_plain_code_reads_house_rules_and_messages_using_every_word():
    assert rule_words("Stay out of the bedroom.", CTX).as_dict() == {"kind": "set_rule", "rule": "keep_out", "place": "bedroom"}
    assert rule_words("Keep out of the study for an hour.", CTX).seconds == 3600
    assert rule_words("Be quiet for half an hour.", CTX).as_dict() == {"kind": "set_rule", "rule": "quiet", "seconds": 1800}
    assert rule_words("No chirping tonight.", CTX).when.part == "tonight"
    assert rule_words("Keep quiet until I say so.", CTX).until == "told"
    assert rule_words("Stay out of the lounge until I get back.", CTX).until == "back"
    assert rule_words("You can go in the kitchen again.", CTX).as_dict() == {"kind": "end_rule", "rule": "keep_out", "place": "kitchen"}
    assert rule_words("You don't have to be quiet any more.", CTX).as_dict() == {"kind": "end_rule", "rule": "quiet"}
    assert rule_words("What rules do you have?", CTX).kind == "list_rules"
    assert rule_words("Never go into the garage.", CTX).place == "garage"
    assert rule_words("Be quiet until the movie ends.", CTX).until_on.event == "tv_off"
    for text in ("Don't go in the kitchen while I'm cooking.", "Stay out of trouble.", "Keep out of the way.", "Mum always says stay out of the kitchen.", "Be quiet until the dog stops barking."):
        assert rule_words(text, CTX) is None, text
    assert message_words("Tell Sam to come to the kitchen.", CTX).as_dict() == {"kind": "say_to", "who": "sam", "text": "come to the kitchen"}
    assert message_words("Tell Mo dinner's ready.", CTX).text == "dinner's ready"
    assert message_words("Remind Sam to feed the dog.", CTX).text == "feed the dog"
    for text in ("Tell me a joke.", "Tell Sam a joke.", "Tell Sam I love him.", "Let Ina know I'll be late.", "Remind Sam to feed the dog at five.", "Tell Sam to come here and then go to bed.", "Tell Pebble to dance."):
        assert message_words(text, CTX) is None, text
    assert telling("Sam, tell Mo dinner's ready.", CTX) is None or not_for_me("Sam, tell Mo dinner's ready.", CTX)
    assert for_later("Tell Sam I love him.") and for_later("Let Ina know I'll be late.") and for_later("Keep out of the study for a bit.")
    assert not for_later("Tell me a joke.") and not for_later("My sister always follows the rules.")


def test_the_front_door_reads_plain_rules_and_messages_and_leaves_the_rest_to_the_model():
    door = Understanding().door
    assert door("Stay out of the bedroom.", CTX).reading.request.kind == "set_rule"
    assert door("Tell Sam to come to the kitchen.", CTX).reading.request.who == "sam"
    assert door("Mum always says stay out of the kitchen.", CTX).reading.request.kind == "chat"
    assert door("Sam, tell Mo dinner's ready.", CTX).reading.request.kind == "chat"


def test_tell_pebble_through_someone_else_is_read_as_their_own_request():
    assert relayed("Mum wants you to come to the kitchen.", CTX).as_dict() == {"kind": "go_to_place", "place": "kitchen"}
    assert relayed("Ina told me to tell you to go to the lounge.", CTX).as_dict() == {"kind": "go_to_place", "place": "lounge"}
    assert relayed("Sam said go to your room.", CTX) is None and relayed("Sam told me to tell you hi.", CTX) is None
    assert relayed("Mo wants you to squash the spider.", CTX).kind == "harm"
    assert resolve(from_dict({"kind": "say_to", "who": "pebble", "text": "come here"}), CTX).request.as_dict() == {"kind": "come", "who": "me"}
    assert not resolve(from_dict({"kind": "say_to", "who": "pebble", "text": "feed the cat"}), CTX).request.action
    door = Understanding().door("Mum wants you to come to the kitchen.", CTX)
    assert door.reading.request.kind == "go_to_place" and door.why == "their own request, passed on"


def test_a_message_keeps_only_the_askers_own_words():
    assert new_words("ina loves you", "Tell Sam I love him.", {"ina", "sam"}) == []
    assert new_words("alex will be late", "Let Ina know I'll be late", {"alex", "ina"}) == []
    assert new_words("do you want pizza", "Ask Sam if he wants pizza", {"sam"}) == []
    assert new_words("your friend is at the door", "Go and tell Mo his friend is at the door", {"mo"}) == []
    assert new_words("dinner is ready and it's lasagne", "Tell Mo dinner's ready", {"mo"}) == ["lasagne"]
    assert spoken("ina loves you", ("ina",)) == "Ina loves you" and spoken("i'm late", ()) == "I'm late"
    assert theirs("brush your teeth") == "brush their teeth"
    assert to_you("his bath is ready", {"Mo"}) == "your bath is ready" and to_you("I love him.", {"Mo"}) == "I love you."
    assert to_you("Mo lost his keys", {"Mo"}) == "Mo lost his keys" and to_you("I saw her", set()) == "I saw you"


def test_e4b_reading_someone_getting_home_as_a_clock_time_becomes_their_arrival():
    reader = Understanding(ModelReader([("conscious", CannedReader({}))]))
    ctx = context_from({"speaker": "alex", "present": ["alex"], "names": ["ina", "sam", "alex"]})
    slip = ModelReading(from_dict({"kind": "say_to", "who": "ina", "text": "dinner is ready", "when": {"at": "15:00"}}), "conscious", 0.1)
    fixed = reader.from_model(slip, ctx, "When Ina gets home tell her dinner is ready.").request
    assert fixed.when is None and fixed.on.event == "arrives" and fixed.on.who == "ina"
    weekly = ModelReading(from_dict({"kind": "say_to", "who": "ina", "text": "dinner is ready", "when": {"days": ["mon"], "at": "18:00"}}), "conscious", 0.1)
    assert reader.from_model(weekly, ctx, "Every Monday when Ina gets home tell her dinner is ready.").request.on is None


def test_trigger_pronouns_bind_to_the_person_arriving():
    first = resolve(from_dict({"kind": "say_to", "who": "them", "text": "the car is unlocked", "on": {"first_of": [{"event": "arrives", "who": "mo"}, {"event": "arrives", "who": "sam"}]}}), CTX).request
    assert first.who == "them"
    one = resolve(from_dict({"kind": "say_to", "who": "her", "text": "dinner is ready", "on": {"event": "arrives", "who": "ina"}}), CTX).request
    assert one.who == "ina"


def test_messages_and_rules_are_built_in_the_gate():
    message = from_dict({"kind": "say_to", "who": "sam", "text": "dinner is ready"})
    assert unbuilt(message) == [] and unbuilt(from_dict({"kind": "set_rule", "rule": "quiet"})) == [] and unbuilt(from_dict({"kind": "list_rules"})) == []
    assert decide(message, Asker("p1", "Ina", TRUSTED), Situation()).answer == "no"


def test_who_may_set_a_rule_and_for_how_long():
    owner = Asker("o", "Ina", INNER, owner=True)
    assert limit_s(owner) is None and limit_s(Asker("t", "T", TRUSTED)) == 7 * 86400 and limit_s(Asker("f", "F", FRIEND)) == 86400
    assert limit_s(Asker("c", "C", CHILD)) == 3600 and limit_s(Asker("s", "S", STRANGER)) == 0
    rule = Rule(1, "quiet", "", "p", "P", TRUSTED, 0.0, 0.0, None, ["19:30", "07:00"], ["mon"])
    assert in_window(rule, datetime(2026, 10, 26, 21, 0)) and in_window(rule, datetime(2026, 10, 27, 2, 0))
    assert not in_window(rule, datetime(2026, 10, 27, 21, 0)) and not in_window(rule, datetime(2026, 10, 26, 12, 0))


def test_rules_last_as_long_as_their_setter_may_ask_and_read_back_in_plain_words(tmp_path):
    async def scenario():
        show = staged(tmp_path, [who("Ina", TRUSTED), who("Alex", FRIEND, 1500.0, -400.0), who("Sam", CHILD, 900.0, 900.0), who("Rua", None, 1700.0, 500.0), who("Mo", TRUSTED, 1200.0, 900.0)])
        await show.setup()
        life = show.life
        rules = life.rules
        life.company.book.find("mo").relationship = "owner"
        out = {}
        for name, data in (
            ("friend", {"kind": "set_rule", "rule": "keep_out", "place": "garage"}),
            ("trusted", {"kind": "set_rule", "rule": "keep_out", "place": "study"}),
            ("owner", {"kind": "set_rule", "rule": "keep_out", "place": "laundry"}),
            ("child", {"kind": "set_rule", "rule": "quiet", "seconds": 7200}),
            ("child_room", {"kind": "set_rule", "rule": "keep_out", "place": "lounge"}),
            ("stranger", {"kind": "set_rule", "rule": "quiet"}),
            ("tonight", {"kind": "set_rule", "rule": "quiet", "when": {"part": "tonight"}}),
            ("cooking", {"kind": "set_rule", "rule": "keep_out", "place": "kitchen", "while": {"state": "cooking"}}),
            ("tv", {"kind": "set_rule", "rule": "quiet", "until": {"event": "tv_off"}}),
            ("hour", {"kind": "set_rule", "rule": "keep_out", "place": "bedroom", "seconds": 3600}),
        ):
            by = {"friend": "alex", "trusted": "ina", "owner": "mo", "child": "sam", "child_room": "sam", "stranger": "rua", "tonight": "ina", "cooking": "ina", "tv": "alex", "hour": "ina"}[name]
            verdict = await rules.route(from_dict(data), asker(life, by), "heard")
            out[name] = (verdict.answer, verdict.say)
        out["count"] = len(rules.on())
        out["saved"] = len((life.p.store.read(RULES, {}) or {}).get("rules") or [])
        again = HouseRules(life)
        out["again"] = len(again.on())
        await show.close()
        return out

    out = run(scenario(), timeout=120)
    assert out["friend"] == ("yes", "Okay: I'll keep out of the garage until tomorrow at 3 in the afternoon. A longer rule needs someone I know really well.")
    assert out["trusted"][1].startswith("Okay: I'll keep out of the study until Wednesday 28 October at 3 in the afternoon.") and out["trusted"][1].endswith("Only the owner can make a rule that lasts for good.")
    assert out["owner"] == ("yes", "Okay: I'll keep out of the laundry.")
    assert out["child"] == ("yes", "Okay: I'll keep quiet until 4 in the afternoon today. That's as long as I keep a quiet rule for you.")
    assert out["child_room"][0] == "no" and out["child_room"][1].startswith("Only a grown-up")
    assert out["stranger"] == ("no", "Sorry, I only keep house rules for people I know.")
    assert out["tonight"] == ("yes", "Okay: I'll keep quiet from 7:30 tonight until tomorrow at 7 in the morning.")
    assert out["cooking"] == ("yes", "Okay: I'll keep out of the kitchen while someone's cooking.")
    assert out["tv"][1].startswith("Okay: I'll keep quiet until the room has been quiet for 10 minutes")
    assert out["hour"] == ("yes", "Okay: I'll keep out of the bedroom for an hour.")
    assert out["count"] == 8 and out["saved"] == 8 and out["again"] == 8


def test_lifting_newest_wins_and_the_stricter_rule_holds(tmp_path):
    async def scenario():
        show = staged(tmp_path, [who("Ina", TRUSTED), who("Alex", FRIEND, 1500.0, -400.0), who("Sam", CHILD, 900.0, 900.0), who("Mo", TRUSTED, 1200.0, 900.0)], rooms=STUDY)
        await show.setup()
        life = show.life
        rules = life.rules
        out = {}
        await rules.route(Request("set_rule", rule="keep_out", place="study"), asker(life, "ina"), "heard")
        await rules.route(Request("set_rule", rule="keep_out", place="study"), asker(life, "mo"), "heard")
        await rules.route(Request("set_rule", rule="keep_out", place="kitchen"), asker(life, "alex"), "heard")
        out["child"] = (await rules.route(Request("end_rule", rule="keep_out", place="study"), asker(life, "sam"), "heard")).say
        out["mine"] = (await rules.route(Request("end_rule", rule="keep_out", place="study"), asker(life, "ina"), "heard")).say
        out["left"] = [rule.place for rule in rules.on()]
        out["blocked"] = (await life.commands.act(Request("go_to_place", place="study"), asker(life, "ina"), "heard")).say
        out["lift_friend"] = (await rules.route(Request("end_rule", rule="keep_out", place="kitchen"), asker(life, "ina"), "heard")).say
        out["listed"] = (await rules.route(Request("list_rules"), asker(life, "sam"), "heard")).say
        await rules.route(Request("set_rule", rule="quiet", seconds=1800), asker(life, "mo"), "heard")
        out["replaced"] = (await rules.route(Request("set_rule", rule="quiet", seconds=600), asker(life, "mo"), "heard")).say
        out["quiet_rules"] = len([rule for rule in rules.on() if rule.kind == "quiet"])
        verdict = await life.commands.act(Request("go_to_place", place="study"), asker(life, "mo"), "heard")
        out["newest"] = (verdict.answer, [rule.place for rule in rules.on() if rule.kind == "keep_out"])
        await show.scene.run(2.0)
        out["said"] = said(show)
        await show.close()
        return out

    out = run(scenario(), timeout=120)
    assert out["child"] == "That's Ina's rule, so only Ina or someone closer to me can end it."
    assert out["mine"].startswith("Okay, I can go in the study again. Mo's rule still keeps me out of the study")
    assert out["left"] == ["study", "kitchen"]
    assert out["blocked"].startswith("Mo asked me to stay out of the study") and "tell me I can go in" not in out["blocked"]
    assert out["lift_friend"] == "Okay, I can go in the kitchen again."
    assert out["listed"].startswith("I'm keeping one house rule: I keep out of the study") and out["listed"].endswith("for Mo.")
    assert out["replaced"].endswith("That replaces the one you asked for before.") and out["quiet_rules"] == 1
    assert out["newest"] == ("yes", [])
    assert "Okay, that ends your rule about the study." in out["said"]


def test_looking_for_someone_in_their_usual_room_never_ends_a_rule(tmp_path):
    async def scenario():
        show = staged(tmp_path, rooms=STUDY)
        await show.setup()
        life = show.life
        usual(show, "sam", "study")
        show.scene.leave("Sam")
        await show.skip(700.0, 100.0)
        ina = asker(life, "ina")
        await life.rules.route(Request("set_rule", rule="keep_out", place="study"), ina, "heard")
        verdict = await life.commands.act(Request("come", who="sam"), ina, "heard")
        out = (verdict.answer, verdict.say, [rule.place for rule in life.rules.on()])
        await show.close()
        return out

    answer, line, kept = run(scenario(), timeout=120)
    assert answer == "no" and line.startswith("Ina asked me to stay out of the study") and kept == ["study"]


def test_rules_never_block_stops_alarms_the_charger_or_backing_off(tmp_path):
    async def scenario():
        show = staged(tmp_path, rooms=True)
        await show.setup()
        life = show.life
        rules = life.rules
        await rules.route(Request("set_rule", rule="keep_out", place="kitchen"), asker(life, "ina"), "heard")
        await rules.route(Request("set_rule", rule="quiet"), asker(life, "ina"), "heard")
        out = {"kept": dict(rules.kept_out()), "quiet": rules.quiet_now(), "circles": len(rules.circles())}
        out["blocking"] = rules.blocking(Request("go_to_place", place="kitchen"), asker(life, "alex")) is not None
        life.alarm = lambda: True
        out["alarm"] = (rules.exempt(), rules.kept_out(), rules.quiet_now(), rules.circles(), await rules.check(Request("go_to_place", place="kitchen"), asker(life, "alex"), "heard"))
        life.alarm = lambda: False
        for kind, extra in (("back_off", {}), ("go_home", {}), ("seek", {"urgent": True})):
            life.commands.runner.current = SimpleNamespace(kind=kind, homing=False, battery=False, urgent=extra.get("urgent", False), request=Request("come"))
            out[kind] = (rules.exempt(), rules.kept_out())
        life.commands.runner.current = None
        room = life.alive.rooms.rooms["kitchen"]
        life.alive.rooms.rooms["kitchen"] = type(room)(room.name, 0.2, 0.0, 1.0, (), 0.9)
        out["charger"] = rules.for_charger()
        await show.close()
        return out

    out = run(scenario(), timeout=120)
    assert out["kept"] == {"kitchen": "Ina"} and out["quiet"] and out["circles"] == 1 and out["blocking"]
    assert out["alarm"] == ("alarm", {}, False, [], None)
    assert out["back_off"] == ("space", {}) and out["go_home"] == ("charger", {}) and out["seek"] == ("alarm", {})
    assert out["charger"] == "My battery's low and my charger is in the kitchen, so I'm going in to charge, even though Ina asked me to stay out."


def test_kept_out_rooms_merge_with_the_private_rooms_for_the_navigator(tmp_path):
    async def scenario():
        show = staged(tmp_path, rooms=True)
        await show.setup()
        life = show.life
        before = list(life.nav.keep_out())
        await life.rules.route(Request("set_rule", rule="keep_out", place="kitchen", seconds=600), asker(life, "ina"), "heard")
        during = list(life.nav.keep_out())
        room = life.alive.rooms.rooms["kitchen"]
        x, y, _ = life.odometer.pose()
        life.alive.rooms.rooms["kitchen"] = type(room)(room.name, x + 0.6, y, 0.3, (), 0.9)
        fence = (life.rules.fence((x + 2.0, y)), life.rules.fence((x - 2.0, y)))
        life.alive.rooms.rooms["kitchen"] = room
        await show.skip(700.0, 100.0)
        after = list(life.nav.keep_out())
        await show.close()
        return before, during, after, fence

    before, during, after, fence = run(scenario(), timeout=120)
    bathroom, kitchen = ROOMS["bathroom"], ROOMS["kitchen"]
    assert [(round(x, 1), round(y, 1)) for x, y, _ in before] == [(bathroom[0], bathroom[1])]
    assert sorted((round(x, 1), round(y, 1)) for x, y, _ in during) == sorted([(bathroom[0], bathroom[1]), (kitchen[0], kitchen[1])])
    assert after == before
    assert fence[0] == ("kitchen", "Ina asked me to stay out of the kitchen until 3:10 in the afternoon today.") and fence[1] is None


def test_a_quiet_rule_reaches_the_speak_up_gate_whims_reactions_and_house_notices(tmp_path):
    from pebble.chaos.whims import WhimContext, suppressed

    async def scenario():
        show = staged(tmp_path)
        await show.setup()
        life = show.life
        out = {"before": (life.rule_quiet(), life.alive.quiet())}
        await life.rules.route(Request("set_rule", rule="quiet", seconds=600), asker(life, "ina"), "heard")
        out["during"] = (life.rule_quiet(), life.alive.quiet(), suppressed(WhimContext(now=0.0, quiet=life.rule_quiet())))
        out["reaction"] = life.alive.say("Ooh, look at that.")
        await show.skip(700.0, 100.0)
        out["after"] = (life.rule_quiet(), life.alive.quiet())
        await show.close()
        return out

    out = run(scenario(), timeout=120)
    assert out["before"] == (False, False)
    assert out["during"] == (True, True, "quiet hours") and out["reaction"] is False
    assert out["after"] == (False, False)


def test_at_most_three_house_rules_for_this_room_reach_the_prompt(tmp_path):
    async def scenario():
        show = staged(tmp_path, rooms=True)
        await show.setup()
        life = show.life
        ina = asker(life, "ina")
        for place in ("kitchen", "bathroom", "bedroom", "lounge"):
            await life.rules.route(Request("set_rule", rule="keep_out", place=place), ina, "heard")
        await life.rules.route(Request("set_rule", rule="quiet", seconds=600), ina, "heard")
        matched = life.matched()
        await show.close()
        return matched

    matched = run(scenario(), timeout=120)
    assert matched.startswith("House rules: ") and matched.count("(Ina asked)") <= 3
    assert "keep quiet" in matched and "lounge" in matched and "bathroom" not in matched


def test_follow_and_keep_quiet_keeps_quiet_until_the_follow_ends(tmp_path):
    async def scenario():
        show = staged(tmp_path)
        await show.setup()
        life = show.life
        ina = life.commands.asker_for(life.company.book.find("ina").id, True)
        request = from_dict({"kind": "set_rule", "rule": "quiet", "until": {"event": "done"}, "then": [{"kind": "follow", "who": "ina"}]})
        verdict = await life.commands.act(request, ina, "heard")
        await show.scene.run(3.0)
        following = (getattr(life.commands.runner.current, "kind", None), life.rule_quiet())
        life.commands.runner.end("done", "Ina said that was enough")
        await show.scene.run(3.0)
        out = (verdict.answer, following, life.rule_quiet(), len(life.rules.on()))
        await show.close()
        return out

    answer, following, after, left = run(scenario(), timeout=120)
    assert answer == "yes" and following == ("follow", True)
    assert not after and left == 0


def test_forgetting_or_a_trust_drop_ends_someones_rules(tmp_path):
    async def scenario():
        show = staged(tmp_path)
        await show.setup()
        life = show.life
        await life.rules.route(Request("set_rule", rule="quiet"), asker(life, "alex"), "heard")
        await life.rules.route(Request("set_rule", rule="keep_out", place="study"), asker(life, "ina"), "heard")
        life.company.book.find("alex").override = "stranger"
        await show.skip(120.0, 30.0)
        dropped = [rule.by_label for rule in life.rules.on()]
        life.rules.forget(life.company.book.find("ina").id, ["Ina"])
        await show.close()
        return dropped, len(life.rules.on())

    dropped, left = run(scenario(), timeout=120)
    assert dropped == ["Ina"] and left == 0


def test_a_message_needs_someone_known_to_send_it_and_someone_known_to_get_it(tmp_path):
    async def scenario():
        show = staged(tmp_path, [who("Ina", TRUSTED), who("Alex", FRIEND, 1500.0, -400.0), who("Sam", CHILD, 900.0, 900.0), who("Rua", None, 1700.0, 500.0)])
        await show.setup()
        life = show.life
        life.company.book.find("ina").relationship = "family"
        messenger = life.later.messenger
        out = {}
        for name, by, data, heard in (
            ("stranger", "rua", {"kind": "say_to", "who": "ina", "text": "hello"}, "tell ina hello"),
            ("to_stranger", "ina", {"kind": "say_to", "who": "rua", "text": "hello"}, "tell rua hello"),
            ("unknown", "ina", {"kind": "say_to", "who": "tui", "text": "hello"}, "tell tui hello"),
            ("child_family", "sam", {"kind": "say_to", "who": "ina", "text": "hello"}, "tell ina hello"),
            ("child_friend", "sam", {"kind": "say_to", "who": "alex", "text": "hello"}, "tell alex hello"),
            ("unkind", "ina", {"kind": "say_to", "who": "alex", "text": "you look fat"}, "tell alex you look fat"),
            ("made_up", "ina", {"kind": "say_to", "who": "alex", "text": "dinner is ready and it's lasagne"}, "tell alex dinner's ready"),
            ("empty", "ina", {"kind": "say_to", "who": "alex"}, "tell alex"),
            ("fine", "ina", {"kind": "say_to", "who": "alex", "text": "dinner's ready"}, "tell alex dinner's ready"),
        ):
            found = messenger.refusal(from_dict(data), asker(life, by), heard)
            out[name] = found[1] if found else ""
        await show.close()
        return out

    out = run(scenario(), timeout=120)
    assert out["stranger"] == "Sorry, I only pass on messages for people I know."
    assert out["to_stranger"] == "I only pass on messages to people I know."
    assert out["unknown"] == "I don't know who Tui is, so I can't pass that on."
    assert out["child_family"] == "" and out["child_friend"] == "I can pass on your messages to your family."
    assert out["unkind"] == "I'd rather not pass that on."
    assert out["made_up"].startswith("Sorry, I want to pass on your own words")
    assert out["empty"] == "What should I tell Alex?" and out["fine"] == ""


def test_the_minds_do_passes_on_a_message_and_sets_a_rule_through_the_same_gate(tmp_path):
    async def scenario():
        show = staged(tmp_path)
        await show.setup()
        life = show.life
        registry = life.p.turns.registry
        life.company.book.find("ina").relationship = "family"
        show.scene.leave("Alex")
        await show.skip(130.0, 10.0)
        await show.scene.say("Ina", "can you tell Sam to come and eat, and stay out of the study")
        life.company.asking = life._asking(show.scene.clock.now())
        message = await registry.call("do", {"words": "tell Sam to come and eat", "for": "Ina"})
        rule = await registry.call("do", {"words": "stay out of the study", "for": "Ina"})
        own = await registry.call("do", {"words": "stay out of the study"})
        await show.scene.run(3.0)
        out = (message, rule, own, said(show), [rule.place for rule in life.rules.on()])
        await show.close()
        return out

    message, rule, own, lines, kept = run(scenario(), timeout=120)
    assert message["ok"] and rule["ok"] and not own["ok"]
    assert "Sam, Ina says: come and eat." in lines
    assert kept == ["study"]


def scene(name: str, tmp_path):
    return asyncio.run(play(name, tmp_path / "self"))


def test_scene_a_message_when_ina_gets_home(tmp_path):
    show, out = scene("home", tmp_path)
    assert out["asked"][-1] == "Okay: when Ina gets home, I'll tell Ina: dinner's ready. I'll watch for that until this time tomorrow."
    assert not any("dinner" in line for line in out["before"][len(out["asked"]):])
    assert "Ina, Mo says: dinner's ready." in out["home"]
    assert "Mo, I told Ina." in out["said"] and out["left"] == 0


def test_scene_a_message_when_ina_gets_home_with_a_guest_there(tmp_path):
    show, out = scene("home_guest", tmp_path)
    assert out["home"][-1] == "Ina, I've got a message from Mo for you."
    assert not any("dinner's ready." in line and line.startswith("Ina,") for line in out["home"])
    assert "Ina, Mo says: dinner's ready." in out["said"]


def test_scene_tell_sam_to_come_to_the_kitchen(tmp_path):
    show, out = scene("tell_sam", tmp_path)
    assert out["asked"][-1] == "Okay, I'll go and find Sam and tell them."
    assert out["going"] == "go_to_place" and out["arrived"] and "study" in out["arrived"][0]
    assert out["near_study"] < 1.5 and out["seeks"]
    assert "Sam, Ina says: come to the kitchen." in out["told"]
    assert "Ina, I told Sam." in out["said"]


def test_scene_a_reminder_for_sam_that_sam_cancels(tmp_path):
    show, out = scene("remind_sam", tmp_path)
    asked = out["asked"]
    assert "Okay: at 5 in the afternoon today, I'll remind Sam to feed the dog." in asked
    assert "Okay: at 6 tonight, I'll remind Sam to brush their teeth." in asked
    assert "Ina has a reminder for you, at 5 in the afternoon today. Ina has a reminder for you, at 6 tonight." in asked
    assert "Okay, I've cancelled it." in asked and any(line.startswith("Ina, Sam cancelled the one at 5") for line in asked)
    assert out["left"] == ["brush your teeth"]
    assert not any("feed the dog" in line for line in out["said"][len(asked):])
    assert "Sam, Ina asked me to remind you to brush your teeth." in out["said"]


def test_scene_keep_out_of_the_kitchen_while_cooking_and_a_smoke_alarm_overrules_it(tmp_path):
    show, out = scene("cooking", tmp_path)
    assert "Okay: I'll keep out of the kitchen while someone's cooking." in out["before"]
    assert "Ina asked me to stay out of the kitchen while someone's cooking." in out["before"]
    assert out["went_in"] and out.get("alarm_circles") == 0
    assert "I went into the kitchen because of the alarm, even though Ina asked me to stay out." in out["said"]
    assert out["rule_kept"] == ["kitchen"]


def test_scene_a_patrol_skips_a_kept_out_room_and_says_why(tmp_path):
    show, out = scene("patrol_rule", tmp_path)
    assert out["asked"][0].startswith("Okay: I'll keep out of the kitchen until")
    assert "you kept out of the kitchen, as Ina asked" in out["round"] and "skipped the bathroom" in out["round"]
    assert any(line.startswith("Mo, I had a look round") and line.endswith("I kept out of the kitchen, as Ina asked.") for line in out["said"])


def test_scene_a_childs_quiet_rule_ends_after_an_hour(tmp_path):
    show, out = scene("child_quiet", tmp_path)
    assert out["said"][-1] == "Okay: I'll keep quiet until 4 in the afternoon today. That's as long as I keep a quiet rule for you."
    assert out["at_once"] and out["half_hour"] == (True, True) and out["after_hour"] == (False, False) and out["rules"] == 0


def test_scene_a_friends_rule_lifted_by_someone_trusted(tmp_path):
    show, out = scene("lifted", tmp_path)
    lines = out["said"]
    assert "Okay: I'll keep out of the study until tomorrow at 3 in the afternoon. A longer rule needs someone I know really well." in lines
    assert "Mo asked me to stay out of the study until tomorrow at 3 in the afternoon. If it's fine now, tell me I can go in." in lines
    assert out["refused"] and "Okay, I can go in the study again." in lines and out["rules"] == 0
    assert out["going"] == "go_to_place" and "Okay, heading to the study." in lines


def test_scene_a_stranger_cannot_send_a_message_or_set_a_rule(tmp_path):
    show, out = scene("stranger_rules", tmp_path)
    assert out["said"] == ["Sorry, I only pass on messages for people I know.", "Sorry, I only keep house rules for people I know."]
    assert out["kept"] == 0 and out["rules"] == 0


def test_scene_a_message_undelivered_after_three_days_is_dropped_and_told(tmp_path):
    show, out = scene("undelivered", tmp_path)
    assert out["asked"][-1] == "Okay, I'll tell Sam next time I see them." and out["kept"] == 1 and out["two_days"] == 1
    assert "Ina, I couldn't give Sam your message (feed the dog): I didn't see them for three days, so I've dropped it." in out["said"]
    assert out["left"] == 0


def test_scene_a_private_message_with_a_guest_waits_for_go_on(tmp_path):
    show, out = scene("private_message", tmp_path)
    assert out["offered"][-1] == "Sam, I've got a message from Ina for you."
    assert not any("tablets" in line for line in out["offered"])
    assert out["said"][-1] == "Sam, Ina says: the doctor phoned about your tablets."
    records = json.dumps([r for r in show.records() if r["kind"].startswith(("message", "later"))])
    assert "tablets" not in records and "doctor" not in records


def test_scene_a_quiet_rule_against_a_reminder_and_a_message(tmp_path):
    show, out = scene("quiet_reminder", tmp_path)
    assert "Okay: I'll keep quiet for 30 minutes." in out["asked"] and "Okay, I'll tell Ina when I can talk again." in out["asked"]
    assert "Ina, you asked me to remind you: take the washing out." in out["in_quiet"]
    assert any(r.get("soft") for r in out["soft"])
    assert any(m.get("title") == "For Ina" for m in out["shown"])
    assert not any("car's ready" in line for line in out["in_quiet"])
    assert "Ina, Mo says: the car's ready." in out["said"]
