import json
from pathlib import Path

import pytest
from conftest import run

from pebble.mind.base import Mind, MindReply, MindUnavailable
from pebble.screen.gbnf import parse_gbnf
from pebble.understand.context import Context, Pending, context_from
from pebble.understand.eval import fired, load, rules_reader, score, step_matches
from pebble.understand.grammar import request_grammar
from pebble.understand.model import ModelReader
from pebble.understand.request import ACTIONS, BadRequest, Request, from_dict, from_json
from pebble.understand.rules import parse
from pebble.understand.understanding import Understanding

SETS = Path(__file__).resolve().parents[1] / "pebble" / "understand"
TUNED = ("eval_set.jsonl", "eval_holdout.jsonl", "eval_things.jsonl", "eval_alive.jsonl")
UNTUNED = ("eval_fresh.jsonl", "eval_things_fresh.jsonl", "eval_alive_fresh.jsonl")


@pytest.mark.parametrize("name", TUNED)
def test_the_rules_get_every_core_line_and_fire_nothing_on_talk(name):
    items = load(SETS / name)
    assert len(items) >= 90
    result = run(score(items, rules_reader()))
    print(result.report(f"rules on {name}", 10))
    assert result.core_accuracy == 1.0, result.report(name)
    assert result.false_fires == [], result.report(name)
    assert result.accuracy >= 0.95, result.report(name)


def test_the_main_set_is_big_and_varied():
    items = load(SETS / "eval_set.jsonl")
    assert len(items) >= 150
    assert sum(1 for i in items if i.get("core")) >= 50
    assert sum(1 for i in items if i["group"] == "not_command") >= 30
    kinds = {i["expect"]["kind"] for i in items}
    assert kinds >= {"follow", "come", "wait", "look", "back_off", "go_home", "go_to_place", "turn", "move", "stop_activity", "adjust", "release", "chat", "other"}


@pytest.mark.parametrize("name", UNTUNED)
def test_the_late_sets_never_fire_on_talk(name):
    items = load(SETS / name)
    result = run(score(items, rules_reader()))
    print(result.report(f"rules on {name}", 40))
    assert result.false_fires == [], result.report(name)


def test_every_expected_parse_fits_the_model_grammar():
    grammar = parse_gbnf(request_grammar())
    for name in TUNED + UNTUNED:
        for item in load(SETS / name):
            expect = {k: v for k, v in item["expect"].items() if k not in ("ask", "speaker")}
            text = json.dumps(from_dict(expect).as_dict(), separators=(",", ":"))
            assert grammar.matches(text), (name, item["id"], text)


def test_request_json_is_read_forgivingly_and_refused_when_wrong():
    request = from_json('Sure! {"kind": "Follow", "who": "Ina", "seconds": "60", "speed": "zippy", "then": [{"kind": "wait"}]} ok')
    assert request.kind == "follow" and request.who == "ina" and request.seconds == 60.0 and request.speed == ""
    assert request.then[0].kind == "wait"
    for bad in ("", "no json", '{"kind": "dance"}', '{"kind": "wait", "seconds": "lots"}', '{"kind": "come", "then": {"kind": "wait"}}'):
        with pytest.raises(BadRequest):
            from_json(bad)
    assert from_json('{"kind":"move","metres":99}').metres == 30.0


@pytest.mark.parametrize(
    "text",
    [
        "don't follow me",
        "can you see me?",
        "do you like following people?",
        "Sam keeps following me around",
        "my dog follows me everywhere",
        "I'll wait for the bus",
        "come on, really?",
        "wait, what?",
        "look, I'm busy",
        "follow me just now",
        "Sam, come here",
        "come to think of it I never fed the cat",
        "hold on let me think",
        "you don't need to wait",
    ],
)
def test_talk_never_turns_into_a_command(text):
    request = parse(text, context_from({"present": ["ina", "sam"]})).request
    assert request.kind not in ACTIONS, (text, request)


def test_the_same_words_mean_different_things_while_doing_something():
    idle = context_from({})
    following = context_from({"activity": {"kind": "follow", "with": "ina", "by": "ina"}})
    waiting = context_from({"activity": {"kind": "wait", "by": "ina"}})
    assert parse("keep up", idle).request.kind == "follow"
    assert parse("keep up", following).request.as_dict() == {"kind": "adjust", "change": "faster"}
    assert parse("closer", idle).request.kind == "come"
    assert parse("not so close", following).request.change == "further"
    assert parse("you don't need to wait", waiting).request.kind == "release"
    assert parse("you don't need to wait", idle).request.kind == "chat"


def test_unknown_speaker_and_unclear_pronoun_lead_to_one_question():
    understanding = Understanding()
    many = context_from({"speaker": None, "present": ["ina", "sam"]})
    reading = run(understanding.read("follow me", many))
    assert reading.ask == "speaker" and "who" in reading.question.lower()
    three = context_from({"present": ["ina", "sam", "mo"]})
    reading = run(understanding.read("follow her", three))
    assert reading.ask == "who" and "Sam" in reading.question and "Mo" in reading.question
    told = context_from({"present": ["ina", "sam", "mo"], "recent": ["sam: has anyone seen mo?"]})
    assert run(understanding.read("follow her", told)).request.who == "mo"
    nowhere = run(understanding.read("go over there", context_from({})))
    assert nowhere.ask == "place"


def test_answers_to_a_pending_question_complete_the_request():
    understanding = Understanding()
    pending = Pending("who", Request("follow"), "Who should I follow?")
    ctx = context_from({"present": ["ina", "sam"]})
    ctx = Context(ctx.speaker, ctx.tier, ctx.present, None, pending, (), (), ())
    assert run(understanding.read("Sam", ctx)).request.as_dict() == {"kind": "follow", "who": "sam"}
    assert run(understanding.read("never mind", ctx)).request.kind == "chat"
    confirm = Context("ina", "trusted", ("ina",), None, Pending("confirm", Request("come", who="me"), "Do you want me to come to you?"))
    assert run(understanding.read("ja", confirm)).request.kind == "come"
    assert run(understanding.read("nah", confirm)).request.kind == "chat"
    assert run(understanding.read("actually, wait here", confirm)).request.kind == "wait"
    speaker = Context(None, "stranger", ("ina", "sam"), None, Pending("speaker", Request("follow", who="me"), "Who's asking?"))
    reading = run(understanding.read("it's Sam", speaker))
    assert reading.speaker == "sam" and reading.request.kind == "follow"


class JsonMind(Mind):
    def __init__(self, replies, down=False):
        self.replies = list(replies)
        self.down = down
        self.calls = []

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        self.calls.append({"purpose": purpose, "messages": messages, "options": options})
        if self.down:
            raise MindUnavailable("down")
        return MindReply(self.replies.pop(0) if self.replies else '{"kind":"chat"}')


def test_the_small_model_reads_what_the_rules_cannot_with_the_grammar_and_steady_sampling():
    sub = JsonMind(['{"kind":"follow","who":"me"}'])
    understanding = Understanding(ModelReader([("subconscious", sub)]))
    reading = run(understanding.read("would you be a darling and trail me round the house", context_from({})))
    assert reading.source == "subconscious" and reading.request.as_dict() == {"kind": "follow", "who": "me"}
    call = sub.calls[0]
    assert call["purpose"] == "understand"
    options = call["options"]
    assert options.grammar == request_grammar() and options.temperature == 0.3 and options.top_p == 0.9 and options.min_p == 0.1
    text = json.dumps(call["messages"])
    assert "Present:" in text and "Pebble is doing" in text and "trail me round the house" in text


def test_obvious_commands_and_obvious_talk_never_wait_on_a_model():
    sub = JsonMind(['{"kind":"come","who":"me"}'])
    understanding = Understanding(ModelReader([("subconscious", sub)]))
    assert run(understanding.read("follow me", context_from({}))).source == "rules"
    assert run(understanding.read("don't follow me", context_from({}))).request.kind == "chat"
    assert sub.calls == []


def test_the_main_mind_steps_in_when_the_small_one_is_down_and_rules_are_last():
    sub = JsonMind([], down=True)
    main = JsonMind(['{"kind":"wait","until":"back"}'])
    understanding = Understanding(ModelReader([("subconscious", sub), ("conscious", main)]))
    reading = run(understanding.read("park your wee self there till I'm home again my friend", context_from({})))
    assert reading.source == "conscious" and reading.request.until == "back"
    both_down = Understanding(ModelReader([("subconscious", JsonMind([], down=True)), ("conscious", JsonMind([], down=True))]))
    assert run(both_down.read("hang about here a sec", context_from({}))).source == "rules"


def test_the_main_mind_is_not_asked_about_plain_talk():
    main = JsonMind(['{"kind":"come","who":"me"}'])
    understanding = Understanding(ModelReader([("conscious", main)]))
    run(understanding.read("the weather is lovely today", context_from({})))
    assert main.calls == []


def test_an_unsure_model_reading_turns_into_a_confirming_question():
    sub = JsonMind(['{"kind":"come","who":"me","sure":false}'])
    understanding = Understanding(ModelReader([("subconscious", sub)]))
    reading = run(understanding.read("oi you over yonder by the couch", context_from({})))
    assert reading.ask == "confirm" and reading.question.startswith("Do you want me to come")


def test_scoring_compares_only_what_was_expected():
    assert step_matches({"kind": "wait"}, {"kind": "wait", "until": "back"}) == []
    assert step_matches({"kind": "wait", "seconds": 60}, {"kind": "wait", "seconds": 55}) == []
    assert step_matches({"kind": "come"}, {"kind": "follow"})
    assert fired({"kind": "follow"}) and not fired({"kind": "follow", "ask": "who"}) and not fired({"kind": "chat"})
