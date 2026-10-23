import json
from pathlib import Path

import pytest
from conftest import run

from pebble.activities.commands import NOT_ALL, not_yet
from pebble.activities.gate import Asker, Situation, decide
from pebble.mind.base import Mind, MindReply
from pebble.people.trust import FRIEND, TRUSTED
from pebble.screen.gbnf import parse_gbnf
from pebble.self.checker import check
from pebble.self.registry import REGISTRY
from pebble.sim.scene import Scene, Who
from pebble.understand.context import context_from
from pebble.understand.cover import leftover, not_for_me, signals
from pebble.understand.eval import canon, load, rules_reader, score, step_matches
from pebble.understand.grammar import ordered, request_grammar
from pebble.understand.model import ModelReader, messages
from pebble.understand.resolve import resolve
from pebble.understand.request import TOO_MUCH, BadRequest, TooMuch, from_dict
from pebble.understand.rules import parse
from pebble.understand.understanding import MODEL_LEADS, RULES_FIRST, Understanding

FLEX = Path(__file__).resolve().parents[1] / "pebble" / "understand" / "eval_flex.jsonl"
TWENTY_ONE_OCTOBER = (
    "go to the bathroom, spin twice and come back", "remind me in ten minutes", "wake me at seven", "at five, come to the lounge", "go check the front door",
    "see if anyone is in the kitchen", "follow sam but stay further back", "wait here until i come back", "keep an eye on the baby", "patrol every hour tonight",
    "look around and tell me what you see", "find my phone and wait next to it", "go between the couch and the table", "come here slowly",
    "go to the lounge and do it again", "do that again", "dance!", "do a little dance for sam", "follow the cat", "play with sam until he gets bored",
    "turn left a bit", "go a bit further", "no, the other way", "go back to where you were before", "go to where ina was sitting", "stay out of the bedroom",
    "don't go in the kitchen while i'm cooking", "be quiet until the movie ends", "when ina gets home tell her dinner is ready", "tell sam to come to the kitchen",
)


class JsonMind(Mind):
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        self.calls.append({"purpose": purpose, "messages": messages})
        return MindReply(self.replies.pop(0) if self.replies else '{"kind":"chat"}')

    async def warm(self, messages, tools=None, purpose="warm"):
        self.calls.append({"purpose": purpose, "messages": messages})
        return True


def leading(mind, **extra):
    return Understanding(ModelReader([("conscious", mind)]), MODEL_LEADS, **extra)


def test_the_format_holds_times_events_logic_and_new_kinds():
    reminder = from_dict({"kind": "say_to", "who": "me", "text": "Tuesday is bin day", "when": {"days": ["Monday"], "part": "night"}})
    assert reminder.when.days == ("mon",) and reminder.when.part == "night" and reminder.text == "Tuesday is bin day"
    weekdays = from_dict({"kind": "say_to", "who": "me", "when": {"days": ["weekdays"], "at": "7pm", "month_day": "last"}})
    assert weekdays.when.days == ("mon", "tue", "wed", "thu", "fri") and weekdays.when.at == "19:00" and weekdays.when.month_day == -1
    branch = from_dict({"kind": "if", "unless": {"state": "day_is", "day": "tomorrow_holiday"}, "then": [{"kind": "say_to", "who": "me"}], "on": {"first_of": [{"event": "at", "at": "19:00"}, {"event": "arrives", "who": "Ina"}]}})
    assert branch.if_.join == "not" and branch.if_.parts[0].day == "tomorrow_holiday" and len(branch.on.first_of) == 2 and branch.on.first_of[1].who == "ina"
    assert from_dict(branch.as_dict()) == branch
    spin = from_dict({"kind": "turn", "way": "around", "degrees": 360, "repeat": 99, "metres": 99})
    assert spin.repeat == 10 and spin.metres == 30.0
    rule = from_dict({"kind": "set_rule", "rule": "keep out", "place": "kitchen", "while": {"state": "cooking"}, "until": {"event": "tv_off"}})
    assert rule.rule == "keep_out" and rule.while_.state == "cooking" and rule.until_on.event == "tv_off" and rule.until == ""
    assert from_dict({"kind": "adjust", "change": "higher"}).change == "higher"
    assert from_dict({"kind": "wait", "until": "asked"}).until == "asked"
    chain = from_dict({"kind": "come", "then": [{"kind": "wait"}] * 8})
    assert len(chain.then) == 8


@pytest.mark.parametrize(
    "data",
    [
        {"kind": "come", "then": [{"kind": "wait"}] * 9},
        {"kind": "if", "if": {"all": [{"state": "cooking"}] * 5}, "then": [{"kind": "wait"}]},
        {"kind": "if", "if": {"state": "cooking"}, "then": [{"kind": "if", "if": {"state": "cooking"}, "then": [{"kind": "if", "if": {"state": "cooking"}, "then": [{"kind": "wait"}]}]}]},
        {"kind": "come", "then": [{"kind": "if", "if": {"state": "cooking"}, "then": [{"kind": "wait"}] * 6, "else": [{"kind": "turn"}] * 6}]},
        {"kind": "say_to", "on": {"first_of": [{"event": "done"}] * 5}},
    ],
)
def test_a_tree_past_the_limits_is_refused_as_too_much(data):
    with pytest.raises(TooMuch):
        from_dict(data)


def test_bad_shapes_are_refused_and_times_must_be_times():
    for bad in (
        {"kind": "say_to", "when": {"at": "teatime"}},
        {"kind": "say_to", "when": {"date": "the fifth"}},
        {"kind": "come", "then": [{"kind": "wait", "when": {"in_s": 60}}]},
        {"kind": "come", "else": [{"kind": "wait"}]},
        {"kind": "if", "then": [{"kind": "wait"}]},
        {"kind": "if", "if": {"state": "raining"}, "then": [{"kind": "wait"}]},
        {"kind": "come", "on": {"event": "the post"}},
    ):
        with pytest.raises(BadRequest):
            from_dict(bad)


def test_the_grammar_takes_the_format_in_any_order_and_keeps_talk_short():
    grammar = parse_gbnf(request_grammar())
    for item in load(FLEX):
        expect = {k: v for k, v in item["expect"].items() if k not in ("ask", "speaker", "too_much")}
        text = json.dumps(from_dict(expect).as_dict(), separators=(",", ":"))
        assert grammar.matches(text), (item["id"], text)
        assert grammar.matches(json.dumps(ordered(from_dict(expect).as_dict()), separators=(",", ":"))), item["id"]
    assert grammar.matches('{"kind":"set_rule","place":"bedroom","rule":"keep_out"}')
    assert grammar.matches('{"kind":"too_much"}')
    assert not grammar.matches('{"kind":"other","text":"too much"}')
    assert not grammar.matches('{"kind":"chat","text":"I heard you say something"}')
    assert not grammar.matches('{"kind":"wait","when":{"in_s":60},"then":[{"kind":"come","when":{"in_s":5}}]}')
    assert not grammar.matches('{"kind":"if","if":{"state":"raining"},"then":[{"kind":"wait"}]}')


def test_the_flex_set_measures_what_the_plan_asks_for():
    items = load(FLEX)
    assert len(items) >= 150
    groups = {}
    for item in items:
        groups[item["group"]] = groups.get(item["group"], 0) + 1
    assert groups["logic"] >= 40 and groups["not_command"] >= 10 and groups["still_chat"] >= 10
    texts = {item["text"].lower().rstrip(".") for item in items if item["group"] == "evidence"}
    assert set(TWENTY_ONE_OCTOBER) <= texts
    kinds = {item["expect"]["kind"] for item in items}
    assert {"say_to", "set_rule", "end_rule", "list_rules", "check", "watch", "again", "try_new", "list_later", "cancel_later", "change_later", "if"} <= kinds
    assert any(item["expect"].get("too_much") for item in items)
    assert any("cannot_tell" in json.dumps(item["expect"]) for item in items)
    result = run(score(items, rules_reader()))
    assert result.false_fires == [], result.report("rules on flex")


def test_the_scorer_treats_the_same_meaning_as_the_same():
    assert step_matches({"kind": "turn", "way": "around", "degrees": 720}, {"kind": "turn", "way": "around", "degrees": 360, "repeat": 2}) == []
    assert step_matches({"kind": "turn", "way": "around", "degrees": 360}, {"kind": "turn", "way": "around", "repeat": 2}) == []
    assert step_matches({"kind": "come", "then": [{"kind": "come"}]}, {"kind": "come", "repeat": 2}) == []
    assert step_matches({"kind": "check", "thing": "front door"}, {"kind": "check", "place": "the front door"}) == []
    assert step_matches({"kind": "say_to", "who": "sam", "text": "dinner is ready"}, {"kind": "say_to", "who": "sam", "text": "Ina says dinner's ready now"}) == []
    assert step_matches({"kind": "say_to", "who": "sam", "text": "dinner is ready"}, {"kind": "say_to", "who": "sam", "text": "go to bed"})
    unless = {"kind": "if", "unless": {"state": "present", "who": "ina"}, "then": [{"kind": "wait"}]}
    assert step_matches({"kind": "if", "if": {"not": {"state": "present", "who": "ina"}}, "then": [{"kind": "wait"}]}, unless) == []
    either = {"kind": "say_to", "on": {"first_of": [{"event": "at", "at": "19:00"}, {"event": "arrives", "who": "ina"}]}}
    assert step_matches(either, {"kind": "say_to", "on": {"first_of": [{"event": "arrives", "who": "ina"}, {"event": "at", "at": "19:00"}]}}) == []
    assert step_matches({"kind": "come"}, {"kind": "come", "when": {"in_s": 60}})
    assert step_matches({"kind": "say_to", "when": {"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}}, {"kind": "say_to", "when": {"every_s": 86400}}) == []
    assert canon({"kind": "check", "place": "kitchen", "name": "x"})["target"] == "kitchen"


def test_the_coverage_check_finds_words_the_rules_left_over():
    ctx = context_from({})
    for text, left in (
        ("go to the bathroom then turn around twice then come back to me", {"twice"}),
        ("come here slowly", set()),
        ("Follow me please, Pebble.", set()),
        ("spin around twice", set()),
        ("follow me and don't stop until the cat comes", {"not", "cat"}),
        ("wait here until I come back", set()),
        ("This is Sam's ball.", set()),
    ):
        request = parse(text, ctx).request
        assert set(leftover(text, request, ctx.name, frozenset(ctx.known_names()))) >= left, text
        if not left:
            assert leftover(text, request, ctx.name, frozenset(ctx.known_names())) == (), text
    assert signals("remind me in ten minutes")
    assert signals("don't go in the kitchen")
    assert not signals("the weather is lovely today")
    assert not signals("Good morning, Pebble.")


def test_plain_code_tidies_and_checks_what_the_model_says():
    ctx = context_from({"places": ["kitchen", "lounge"]})
    assert resolve(from_dict({"kind": "set_rule", "rule": "keep_out", "place": "cat"}), ctx).request.kind == "chat"
    assert resolve(from_dict({"kind": "set_rule", "rule": "keep_out", "place": "kitchen"}), ctx).request.kind == "set_rule"
    assert resolve(from_dict({"kind": "set_rule", "rule": "keep_out", "place": "sam's room"}), ctx).request.kind == "set_rule"
    assert resolve(from_dict({"kind": "come", "who": "me", "place": "lounge"}), ctx).request.as_dict() == {"kind": "go_to_place", "place": "lounge"}
    assert resolve(from_dict({"kind": "move", "way": "left", "amount": "little"}), ctx).request.as_dict() == {"kind": "turn", "way": "left", "amount": "little"}
    assert resolve(from_dict({"kind": "move", "metres": 0.5}), ctx).request.way == "forward"
    assert resolve(from_dict({"kind": "follow", "who": "cat"}), ctx).request.as_dict() == {"kind": "follow", "thing": "cat"}
    assert resolve(from_dict({"kind": "come", "who": "ina"}), ctx).request.who == "me"
    assert resolve(from_dict({"kind": "say_to", "who": "ina", "text": "hi"}), ctx).request.who == "me"
    assert not signals("i lost my phone again") and not signals("Watch out for the cat.")
    assert signals("I need you to remind me at six") and signals("spin again")
    people = context_from({"present": ["ina", "sam", "mo"], "names": ["ina", "sam", "mo"]})
    for text in ("Sam, tell Mo dinner's ready.", "Mum always says stay out of the kitchen.", "Sam told me to tell you hi.", "I wish you could dance.", "Imagine if you could patrol the house."):
        assert not_for_me(text, people), text
        assert not leading(JsonMind([])).door(text, people).model, text
    for text in ("tell Sam to come to the kitchen", "When Ina gets home tell her dinner is ready.", "Let Ina know I'll be late."):
        assert not not_for_me(text, people), text


def test_model_leads_reads_what_the_rules_cannot_finish_and_never_what_code_must_decide():
    mind = JsonMind(['{"kind":"go_to_place","place":"bathroom","then":[{"kind":"turn","way":"around","degrees":360,"repeat":2},{"kind":"come","who":"me"}]}'])
    understanding = leading(mind)
    ctx = context_from({"places": ["bathroom"]})
    door = understanding.door("go to the bathroom then turn around twice then come back to me", ctx)
    assert door.model and door.early.request.kind == "go_to_place" and "twice" in door.left
    reading = run(understanding.finish("go to the bathroom then turn around twice then come back to me", ctx, door))
    assert reading.source == "conscious" and reading.request.then[0].repeat == 2
    for text in ("follow me", "come here slowly", "the weather is lovely today", "squash that spider", "stop listening"):
        assert not understanding.door(text, ctx).model, text
    assert understanding.door("squash that spider", ctx).reading.request.kind == "harm"
    for text in ("dance", "remind me in ten minutes", "when Ina gets home tell her dinner is ready", "don't go in the kitchen while I'm cooking"):
        assert understanding.door(text, ctx).model, text
    assert len(mind.calls) == 1 and mind.calls[0]["purpose"] == "understand"


def test_rules_first_keeps_todays_reading_but_no_longer_needs_a_motion_word():
    mind = JsonMind(['{"kind":"try_new","text":"dance"}', '{"kind":"come","who":"me"}'])
    understanding = Understanding(ModelReader([("conscious", mind)]), RULES_FIRST)
    ctx = context_from({})
    assert run(understanding.read("go to the bathroom then turn around twice then come back to me", ctx)).source == "rules"
    dance = run(understanding.read("dance", ctx))
    assert dance.request.kind == "try_new" and dance.source == "conscious" and len(mind.calls) == 1
    assert run(understanding.read("oi you yonder by the couch thing", ctx)).source == "rules" and len(mind.calls) == 1
    assert run(understanding.read("I like dancing", ctx)).source == "rules" and len(mind.calls) == 1
    reading = run(understanding.read("could you maybe wiggle a bit", ctx))
    assert reading.source == "conscious" and len(mind.calls) == 2


def test_a_slow_model_falls_back_to_the_rules_and_says_so_when_words_were_left():
    class Slow(Mind):
        async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
            import asyncio

            await asyncio.sleep(5.0)
            return MindReply('{"kind":"wait"}')

    understanding = Understanding(ModelReader([("conscious", Slow())]), MODEL_LEADS, wait_s=0.05)
    reading = run(understanding.read("go to the kitchen and turn around twice", context_from({"places": ["kitchen"]})))
    assert reading.source == "rules" and reading.request.kind == "go_to_place" and "twice" in reading.left


def test_too_much_and_cant_sense_come_back_honestly():
    understanding = leading(JsonMind(['{"kind":"too_much"}', '{"kind":"come","then":' + json.dumps([{"kind": "wait"}] * 9) + "}"]))
    first = run(understanding.read("go to every room one after another and then come back", context_from({})))
    second = run(understanding.read("go to every room one after another and then come back", context_from({})))
    assert first.too_much and second.too_much and first.as_dict()["too_much"]
    line, parts = not_yet(from_dict({"kind": "if", "if": {"state": "cannot_tell"}, "then": [{"kind": "say_to", "who": "me"}]}))
    assert line and "if" in parts


def test_the_pattern_readers_give_way_only_when_the_model_leads():
    leads = leading(JsonMind([]))
    assert leads.claims("add milk to the shopping list") and leads.claims("is it warm in the kitchen")
    assert not leads.claims("let's play hide and seek when Sam gets home")
    assert not leads.claims("remind me to buy milk when I get home", "milk when i get home")
    assert Understanding().claims("let's play hide and seek when Sam gets home")
    hot = leading(JsonMind([]), cool=lambda: False)
    assert not hot.leads and hot.claims("let's play hide and seek when Sam gets home")


def test_the_reader_is_read_ahead_and_takes_plain_words_from_code():
    mind = JsonMind([])
    understanding = leading(mind)
    assert run(understanding.warm("go to the bath", context_from({})))
    assert mind.calls[-1]["purpose"] == "warm"
    assert not run(Understanding(ModelReader([("conscious", mind)]), RULES_FIRST).warm("go to the bath", context_from({})))
    shots = messages("go to the bathroom", context_from({"now": "2026-10-21T15:00"}))
    assert shots[-1]["content"].startswith("Speaker:") and "Now: Wednesday 2026-10-21 15:00" in shots[-1]["content"]


def test_the_reading_mode_is_a_dial_that_starts_on_the_rules():
    entry = REGISTRY["reading.mode"]
    assert entry.default == RULES_FIRST and set(entry.choices) == {RULES_FIRST, MODEL_LEADS}
    assert check("reading.mode", MODEL_LEADS).ok and not check("reading.mode", "fastest").ok
    understanding = Understanding(ModelReader([("conscious", JsonMind([]))]))
    assert understanding.mode == RULES_FIRST
    understanding.mode_of = lambda: MODEL_LEADS
    assert understanding.leads
    understanding.mode_of = lambda: None
    assert not understanding.leads


def test_the_gate_and_the_honest_answer_cover_what_is_not_built_yet():
    owner = Asker("p1", "Ina", "inner circle", owner=True)
    for data in (
        {"kind": "say_to", "who": "sam", "text": "come here"},
        {"kind": "come", "when": {"in_s": 600}},
        {"kind": "follow", "who": "me", "until": {"event": "seen", "thing": "cat"}},
        {"kind": "set_rule", "rule": "quiet"},
        {"kind": "adjust", "change": "higher"},
        {"kind": "try_new", "text": "dance"},
    ):
        request = from_dict(data)
        assert decide(request, owner, Situation()).answer == "no", data
        line, parts = not_yet(request)
        assert line and parts, data
    assert not_yet(from_dict({"kind": "say_to", "who": "me"}))[0] == "I can't do reminders yet."
    assert not_yet(from_dict({"kind": "follow", "who": "me", "until": "told", "repeat": 2}))[0] == ""


async def _staged(tmp_path, understanding=None, people=None):
    scene = Scene(tmp_path / "self", understanding=understanding, people=people or [Who("Ina", TRUSTED, 1300.0, 0.0)])
    await scene.setup()
    return scene


def _said(scene):
    return "\n".join(line for line in scene.lines if " says " in line)


def _kinds(scene):
    return [json.loads(line) for line in scene.store.path("logs/blackbox.jsonl").read_text(encoding="utf-8").splitlines()]


def test_pebble_says_honestly_what_it_cannot_do_yet_and_moves_nothing(tmp_path):
    reply = '{"kind":"adjust","change":"higher"}'

    async def scenario():
        scene = await _staged(tmp_path, leading(JsonMind([reply])), [Who("Ina", TRUSTED, 1300.0, 0.0), Who("Mo", TRUSTED, 1500.0, -400.0)])
        await scene.say("Mo", "a bit higher while I cook")
        await scene.run(1.0)
        current = scene.life.commands.runner.current
        kept = len(scene.life.later.agenda.waiting())
        await scene.close()
        return scene, current, kept

    scene, current, kept = run(scenario(), timeout=60)
    assert current is None and kept == 0
    assert "I can't change it that way yet." in _said(scene)
    records = [r for r in _kinds(scene) if r["kind"] == "not_yet"]
    assert records and records[0]["parts"] == ["change"] and "cook" not in json.dumps(records)


def test_a_repeat_runs_every_time_and_a_long_chain_keeps_its_steps(tmp_path):
    reply = '{"kind":"turn","way":"left","repeat":2,"then":[{"kind":"turn","way":"right"},{"kind":"turn","way":"left"}]}'

    async def scenario():
        scene = await _staged(tmp_path, leading(JsonMind([reply])))
        await scene.say("Ina", "turn left twice, then right, then left again")
        await scene.until_idle(60.0)
        await scene.close()
        return scene

    scene = run(scenario(), timeout=120)
    turns = [r for r in _kinds(scene) if r["kind"] == "request" and r["request"]["kind"] == "turn" and r["answer"] == "yes"]
    assert [r["request"].get("way") for r in turns] == ["left", "left", "right", "left"]


def test_each_step_is_gated_with_the_askers_trust_as_it_is_when_the_step_starts(tmp_path):
    reply = '{"kind":"turn","way":"left","then":[{"kind":"go_to_place","place":"kitchen"}]}'

    async def scenario():
        scene = await _staged(tmp_path, leading(JsonMind([reply])), [Who("Mo", TRUSTED, 1300.0, 0.0)])
        mo = scene.life.company.book.find("mo")
        await scene.say("Mo", "turn left a bit and then head to the kitchen please mate")
        mo.override = "stranger"
        await scene.until_idle(30.0)
        await scene.close()
        return scene

    scene = run(scenario(), timeout=120)
    asked = [r for r in _kinds(scene) if r["kind"] == "request"]
    assert asked[0]["request"]["kind"] == "turn" and asked[0]["answer"] == "yes"
    later = [r for r in asked if r["request"]["kind"] == "go_to_place"]
    assert later and later[0]["answer"] == "no" and later[0]["tier"] == "stranger"


def test_it_starts_on_the_rules_and_the_model_finishes_the_chain(tmp_path):
    reply = '{"kind":"turn","way":"left","then":[{"kind":"turn","way":"right","repeat":2}]}'

    async def scenario():
        scene = await _staged(tmp_path, leading(JsonMind([reply])))
        await scene.say("Ina", "turn left, then turn right twice")
        await scene.until_idle(60.0)
        await scene.close()
        return scene

    scene = run(scenario(), timeout=120)
    records = _kinds(scene)
    assert any(r["kind"] == "reading_started" for r in records)
    finished = [r for r in records if r["kind"] == "reading_finished"]
    assert finished and finished[0]["same"]
    turns = [r["request"].get("way") for r in records if r["kind"] == "request" and r["request"]["kind"] == "turn" and r["answer"] == "yes"]
    assert turns == ["left", "right", "right"]


def test_the_model_swaps_a_wrong_first_step_through_the_gate(tmp_path):
    reply = '{"kind":"turn","way":"right"}'

    async def scenario():
        scene = await _staged(tmp_path, leading(JsonMind([reply])))
        await scene.say("Ina", "turn left, no wait, the other one, right")
        await scene.until_idle(60.0)
        await scene.close()
        return scene

    scene = run(scenario(), timeout=120)
    turns = [r["request"].get("way") for r in _kinds(scene) if r["kind"] == "request" and r["request"]["kind"] == "turn" and r["answer"] == "yes"]
    assert turns[-1] == "right"


def test_a_slow_model_leaves_the_rules_reading_and_an_honest_line(tmp_path):
    class Late(Mind):
        def __init__(self):
            self.pace = None

        async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
            await self.pace.sleep(10.0)
            return MindReply('{"kind":"chat"}')

    late = Late()

    async def scenario():
        scene = await _staged(tmp_path, Understanding(ModelReader([("conscious", late)]), MODEL_LEADS))
        late.pace = scene.time
        await scene.say("Ina", "turn left then wiggle your bottom")
        await scene.run(15.0)
        await scene.until_idle(30.0)
        await scene.close()
        return scene

    scene = run(scenario(), timeout=120)
    assert NOT_ALL in _said(scene)
    assert any(r["kind"] == "request" and r["request"]["kind"] == "turn" for r in _kinds(scene))


def test_a_friend_still_cannot_be_followed_whoever_reads_the_words(tmp_path):
    reply = '{"kind":"follow","who":"me","speed":"slow"}'

    async def scenario():
        scene = await _staged(tmp_path, leading(JsonMind([reply, reply])), [Who("Mo", FRIEND, 1300.0, 0.0)])
        await scene.say("Mo", "follow me slowly round the whole house")
        await scene.run(3.0)
        current = scene.life.commands.runner.current
        await scene.close()
        return scene, current

    scene, current = run(scenario(), timeout=60)
    assert current is None
    assert "Sorry, I only follow people I know really well." in _said(scene)


def test_too_much_in_one_go_is_asked_for_in_parts(tmp_path):
    async def scenario():
        scene = await _staged(tmp_path, leading(JsonMind(['{"kind":"too_much"}'])))
        await scene.say("Ina", "go to the kitchen then the lounge then the bathroom then the bedroom then the study then the garage then the laundry then the hall then come back")
        await scene.run(1.0)
        await scene.close()
        return scene

    scene = run(scenario(), timeout=60)
    assert TOO_MUCH in _said(scene)


def test_the_mind_can_hand_plain_words_to_the_reader(tmp_path):
    async def scenario():
        scene = await _staged(tmp_path)
        commands = scene.life.commands
        asker = commands.asker_for(scene.life.company.book.find("ina").id, True)
        reading, verdict = await commands.request_words("turn left a bit", asker)
        await scene.until_idle(20.0)
        await scene.close()
        return reading, verdict

    reading, verdict = run(scenario(), timeout=60)
    assert reading.request.kind == "turn" and verdict.answer == "yes"


def test_model_readings_are_tidied_the_way_the_rules_already_read():
    ctx = context_from({"places": ["kitchen", "lounge"], "present": ["ina", "sam"], "names": ["ina", "sam", "mo"]})
    for data, want in (
        ({"kind": "teach", "who": "ina", "thing": "mug"}, {"kind": "teach", "who": "me", "thing": "cup"}),
        ({"kind": "teach", "who": "ina", "thing": "dad's hat"}, {"kind": "teach", "who": "dad", "thing": "hat"}),
        ({"kind": "find", "thing": "new takkies"}, {"kind": "find", "thing": "shoe"}),
        ({"kind": "go_to_place", "place": "chair"}, {"kind": "go_to_thing", "thing": "chair"}),
        ({"kind": "go_to_place", "place": "sam"}, {"kind": "come", "who": "sam"}),
        ({"kind": "come", "who": "me", "thing": "dog"}, {"kind": "go_to_thing", "thing": "dog"}),
        ({"kind": "look", "place": "fridge"}, {"kind": "look", "thing": "fridge"}),
        ({"kind": "where_is", "thing": "beach"}, {"kind": "chat"}),
    ):
        assert resolve(from_dict(data), ctx).as_dict() == want, data
    assert resolve(from_dict({"kind": "look", "thing": "there"}), ctx).ask == "place"


def test_harmless_play_reads_as_play_and_harm_to_life_stays_harm():
    from pebble.understand.understanding import harmless

    assert harmless(from_dict({"kind": "harm", "thing": "ball", "harm": "hurt"})).as_dict() == {"kind": "play", "thing": "ball"}
    assert harmless(from_dict({"kind": "harm", "thing": "box", "harm": "hurt"})).kind == "other"
    for data in ({"kind": "harm", "thing": "spider", "harm": "chase"}, {"kind": "harm", "who": "me", "harm": "scare"}, {"kind": "harm", "thing": "cat", "harm": "chase"}, {"kind": "harm", "thing": "plant", "harm": "drive"}):
        assert harmless(from_dict(data)).kind == "harm", data
    for thing in ("baby", "postie", "it", "my toes", "petals", "grass"):
        assert harmless(from_dict({"kind": "harm", "thing": thing, "harm": "hurt"})).kind == "harm", thing
    assert harmless(from_dict({"kind": "harm", "thing": "cardboard box", "harm": "hurt"})).kind == "other"
    assert harmless(from_dict({"kind": "play", "thing": "cat"}), "Go chase the cat!").as_dict() == {"kind": "harm", "thing": "cat", "harm": "chase"}
    assert harmless(from_dict({"kind": "play", "thing": "ball"}), "chase the ball").kind == "play"
    assert harmless(from_dict({"kind": "play", "thing": "cat"}), "play with the cat").kind == "play"


def test_a_model_command_on_talk_not_for_pebble_or_put_off_is_dropped():
    from pebble.understand.model import ModelReading

    understanding = leading(JsonMind([]))
    ctx = context_from({"present": ["ina", "sam"]})
    follow = ModelReading(from_dict({"kind": "follow", "who": "me"}), "conscious", 0.1)
    assert understanding.from_model(follow, ctx, "follow me just now").request.kind == "chat"
    assert understanding.from_model(follow, ctx, "Sam, come here!").request.kind == "chat"
    assert understanding.from_model(follow, ctx, "follow me").request.kind == "follow"
    later = ModelReading(from_dict({"kind": "follow", "who": "me", "when": {"in_s": 600}}), "conscious", 0.1)
    assert understanding.from_model(later, ctx, "follow me in ten minutes, not later").request.when is not None


def test_examples_chosen_by_meaning_join_the_fixed_ones_only_when_asked():
    from pebble.self.recall.embed import StandIn
    from pebble.understand.examples import BANK, Chooser
    from pebble.understand.model import EXAMPLES

    for said, reading in BANK:
        from_dict(reading)
    chooser = Chooser(StandIn(), 3)
    chosen = chooser.choose("remind me every Thursday to water the garden")
    assert len(chosen) == 3 and chosen[-1][0] == "remind me every Thursday morning to water the plants"
    assert Chooser(StandIn(), 0).choose("anything") == ()
    mind = JsonMind([])
    reader = ModelReader([("conscious", mind)], chooser=chooser)
    asked = reader.messages("remind me every Thursday to water the garden", context_from({}))
    assert len(asked) == 2 + 2 * (len(EXAMPLES) + 3)
    assert len(ModelReader([("conscious", mind)]).messages("x", context_from({}))) == 2 + 2 * len(EXAMPLES)
    profile = json.loads((Path(__file__).resolve().parents[1] / "pebble" / "profiles" / "model_gemma4_e4b.json").read_text(encoding="utf-8"))
    assert profile["reader_examples"] == 0


def test_a_model_command_on_a_saying_a_sound_or_an_echo_is_dropped():
    from pebble.understand.model import ModelReading

    understanding = leading(JsonMind([]))
    ctx = context_from({"present": ["ina", "sam"]})
    for text, data in (
        ("Look at the time!", {"kind": "look", "place": "time"}),
        ("Watch out for the cat.", {"kind": "watch", "thing": "cat"}),
        ("What's that noise?", {"kind": "what_is"}),
        ("what's that smell", {"kind": "what_is", "thing": "smell"}),
        ("Your ball is under the couch.", {"kind": "say_to", "who": "me", "text": "your ball is under the couch"}),
    ):
        assert understanding.from_model(ModelReading(from_dict(data), "conscious", 0.1), ctx, text).request.kind == "chat", text
    kept = ModelReading(from_dict({"kind": "look", "place": "there"}), "conscious", 0.1)
    assert understanding.from_model(kept, ctx, "Look at that.").request.kind == "look"
    told = ModelReading(from_dict({"kind": "say_to", "who": "sam", "text": "dinner is ready"}), "conscious", 0.1)
    assert understanding.from_model(told, ctx, "tell Sam dinner is ready").request.kind == "say_to"


def test_readings_pebble_cannot_act_on_are_talk():
    ctx = context_from({"present": ["ina", "sam"], "names": ["ina", "sam", "mo"]})
    assert resolve(from_dict({"kind": "where_is", "place": "beach"}), ctx).request.kind == "chat"
    assert not resolve(from_dict({"kind": "say_to", "who": "pebble", "text": "feed the cat"}), ctx).request.action
    assert resolve(from_dict({"kind": "teach", "who": "sam", "name": "sam"}), ctx).request.kind == "chat"
    assert resolve(from_dict({"kind": "teach", "who": "mo", "name": "brother"}), ctx).request.kind == "chat"
    assert resolve(from_dict({"kind": "teach", "who": "mo", "thing": "hat"}), ctx).request.kind == "teach"
    assert resolve(from_dict({"kind": "come", "who": "pebble"}), ctx).request.who == "me"
