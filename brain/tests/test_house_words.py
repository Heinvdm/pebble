import json
from pathlib import Path

import pytest

from pebble.understand.context import Context
from pebble.understand.house import answer_word, claimed_name, read
from pebble.understand.rules import parse

EVALS = Path(__file__).resolve().parent.parent / "pebble" / "understand"

ASKS = [
    ("add milk to the list", "list_add", {"items": ("milk",), "list": "shopping"}),
    ("Pebble, add milk, eggs and bread to the shopping list", "list_add", {"items": ("milk", "eggs", "bread")}),
    ("we're out of dishwasher tablets", "list_add", {"items": ("dishwasher tablets",)}),
    ("we're running low on coffee", "list_add", {"items": ("coffee",)}),
    ("put fix the gate on the to-do list", "list_add", {"items": ("fix the gate",), "list": "to do"}),
    ("remind me to buy batteries", "list_add", {"items": ("batteries",)}),
    ("what's on the list?", "list_read", {"list": "shopping"}),
    ("read me the to do list", "list_read", {"list": "to do"}),
    ("take milk off the list", "list_remove", {"items": ("milk",)}),
    ("cross bread off", "list_remove", {"items": ("bread",)}),
    ("I got the milk", "list_remove", {"only_if_listed": True}),
    ("show me the list", "list_show", {}),
    ("I'm off to the supermarket now", "list_show", {"topic": "going"}),
    ("clear the shopping list", "list_clear", {}),
    ("we've got people over tonight", "visitors_on", {}),
    ("visitors mode off", "visitors_off", {}),
    ("the guests have gone home", "visitors_off", {}),
    ("are you recording us?", "keeps", {}),
    ("what's the wi-fi password?", "guest_wifi", {}),
    ("the water shut-off is under the laundry sink", "house_fact", {"item": "water shut off", "where": "under the laundry sink"}),
    ("the getaway bag's in the hall cupboard", "house_fact", {"item": "getaway bag"}),
    ("remember the spare torch is in the top drawer", "house_fact", {"item": "spare torch"}),
    ("that's the washing machine finishing", "teach_sound", {"item": "the washing machine finishing"}),
    ("this sound means the dryer is done", "teach_sound", {"item": "the dryer is done"}),
    ("that's the smoke alarm going off", "teach_sound", {"topic": "alarm"}),
    ("forget the dryer sound", "forget_sound", {"item": "dryer"}),
    ("what sounds do you know?", "sounds_ask", {}),
    ("we're testing the smoke alarms", "alarm_test", {}),
    ("we're done testing", "alarm_test_end", {}),
    ("which alarms went off today?", "alarms_ask", {}),
    ("anything happen while I was out?", "while_out", {}),
    ("what did I miss?", "while_out", {}),
    ("tell me when the microwave's done", "tell_when", {"item": "microwave"}),
    ("tell me if it starts raining", "tell_when", {"item": "rain"}),
    ("the washing's out", "tell_when", {"item": "rain"}),
    ("is the light on?", "light_ask", {}),
    ("is it dark in here?", "light_ask", {}),
    ("when's sunset?", "almanac", {"topic": "sunset"}),
    ("what time does it get dark tonight", "almanac", {"topic": "sunset", "when": "tonight"}),
    ("is it a public holiday on monday?", "almanac", {"topic": "holiday", "when": "monday"}),
    ("when's Matariki?", "almanac", {"topic": "named_holiday", "item": "matariki"}),
    ("when do the clocks go back?", "almanac", {"topic": "clocks"}),
    ("is it a full moon tonight?", "almanac", {"topic": "moon"}),
    ("what's the dew point?", "damp", {}),
    ("will the windows run wet tonight?", "damp", {}),
    ("remind me to close the curtains at sunset", "curtains_on", {}),
    ("stop reminding me about the curtains", "curtains_off", {}),
    ("how loud was it last night?", "noise_ask", {}),
    ("captions on", "captions_on", {}),
    ("show me what people are saying", "captions_on", {}),
    ("captions off", "captions_off", {}),
]

NOT_ASKS = [
    "follow me",
    "come here",
    "where's my slipper?",
    "where's the water shut-off?",
    "let's play",
    "what's that?",
    "go to the kitchen",
    "that's all",
    "stop",
    "I'm going to bed",
    "we need to talk",
    "add two and two",
    "can you add some music",
    "add a reminder",
    "put the kettle on",
    "it's cold in here",
    "how cold is the bedroom",
    "is it humid in here",
    "which room is the warmest",
    "what's the temperature in the kitchen",
    "who's at the door",
    "is the back door open?",
    "what does this say?",
    "the cat is on the couch",
    "the list of things I want to do today is long",
    "stick with me",
    "pop into the lounge",
    "I'm watching it",
    "it's fine",
]


@pytest.mark.parametrize("text,kind,slots", ASKS)
def test_household_requests_are_read(text, kind, slots):
    ask = read(text)
    assert ask is not None and ask.kind == kind, (text, ask)
    for name, value in slots.items():
        assert getattr(ask, name) == value, (text, name, getattr(ask, name))


@pytest.mark.parametrize("text", NOT_ASKS)
def test_other_talk_is_left_alone(text):
    assert read(text) is None, text


def test_im_watching_it_is_read_only_while_the_cooking_watch_speaks():
    assert read("I'm watching it", cooking=True).kind == "cooking_ok"
    assert read("it's fine, it's meant to simmer", cooking=True).kind == "cooking_ok"


def test_no_line_from_the_request_evaluation_sets_is_taken():
    taken = []
    for path in sorted(EVALS.glob("eval*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if read(row["text"]) is not None:
                    taken.append((path.name, row["text"]))
    assert taken == []


def test_answers_and_names():
    assert answer_word("yes please") == "yes" and answer_word("nah") == "no" and answer_word("stop asking") == "never"
    assert answer_word("maybe the blue one") is None
    assert claimed_name("it's Ina") == "ina" and claimed_name("Sam") == "sam" and claimed_name("yes") is None


def test_where_is_keeps_the_names_of_house_things_whole():
    ctx = Context()
    assert parse("where's the water shut-off?", ctx).request.thing == "water shut off"
    assert parse("where's the getaway bag?", ctx).request.thing == "getaway bag"
    assert parse("where is the first aid kit", ctx).request.thing == "first aid kit"
    assert parse("have you seen my bag", ctx).request.thing == "bag"
