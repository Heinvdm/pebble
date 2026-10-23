import asyncio
import random

import pytest
from conftest import run

import test_conversation as tc
from pebble.conversation.holds import CHILD, ECHO, HOLDS, SLOW, SMALL, STOCK, Phrasebook, echo_of, fence, norm, situation_of
from pebble.mind.scripted import ScriptedMind
from pebble.mind.subconscious import Subconscious
from pebble.people.trust import FRIEND, TRUSTED

ECHOES = [
    ("where are my keys", "Where are your keys?"),
    ("Pebble, what do you think?", "What do I think?"),
    ("are you tired", "Am I tired?"),
    ("what did I say", "What did you say?"),
    ("am I late", "Are you late?"),
    ("have you seen my keys", "Have I seen your keys?"),
    ("where are you pebble", "Where am I?"),
    ("what do they call you", "What do they call me?"),
    ("do you like me", "Do I like you?"),
    ("where did I put them", "Where did you put them?"),
    ("is it yours", "Is it mine?"),
    ("how old are you", "How old am I?"),
    ("what's your favourite colour", "What's my favourite colour?"),
    ("were you asleep", "Was I asleep?"),
    ("who am I", "Who are you?"),
    ("why are you smiling", "Why am I smiling?"),
]
NO_ECHO = [
    "can you help me",
    "could you come here",
    "i like cake",
    "tell me a joke",
    "what did you have for breakfast this morning with all your mates",
    "",
]


def test_the_echo_turns_pronouns_round_and_refuses_what_it_should():
    for heard, echo in ECHOES:
        assert echo_of(heard) == echo, heard
    for heard in NO_ECHO:
        assert echo_of(heard) == "", heard


def test_the_fence_refuses_bad_holds_and_lets_the_stock_ones_through():
    for stage in STOCK.values():
        for texts in stage.values():
            for text in texts:
                assert fence(text) == "", text
    for texts in CHILD.values():
        for text in texts:
            assert fence(text) == "", text
    refused = {
        "Let me check.": "isn't doing",
        "The answer is easy.": "answer",
        "Yes!": "answer",
        "I know this one": "answer",
        "What a silly question": "unkind",
        "Hold on *thinks*": "plain words",
        "Hmm, one moment please, I am thinking hard": "too long",
        "Three seconds": "number",
        "In 5 minutes": "number",
        "I am a bit slow": "slow",
        "": "empty",
    }
    for text, why in refused.items():
        assert why in fence(text), text
    assert fence("Let me check.", looking=True) == ""
    assert fence("Where did you put your keys?", echo=True) == ""
    assert situation_of("where are my keys") == "question"
    assert situation_of("can you tell me a joke") == "request"
    assert situation_of("my cat died today and i'm so sad") == "bad"
    assert situation_of("i got the job i'm so happy") == "good"


class Delayed(ScriptedMind):
    def __init__(self, clock, sleep, delay: float, text: str, conv=None):
        super().__init__(replies=[text] * 5)
        self.clock = clock
        self.pause = sleep
        self.delay = delay
        self.conv = conv

    async def stream(self, messages, purpose="turn", max_tokens=None, options=None, tools=None):
        reply = await self.chat(messages, tools, purpose, max_tokens, options)
        turn = getattr(self.conv, "replying_to", None)
        end = turn.end if turn is not None and turn.end is not None else self.clock.monotonic()
        while self.clock.monotonic() < end + self.delay:
            await self.pause(0.05)
        first, _, rest = (reply.text or "").partition(". ")
        yield first + (". " if rest else "")
        for word in rest.split(" "):
            if word:
                yield word + " "
                await self.pause(0.05)


ANSWER = "I saw them on the hall table this morning."


def asked(rig_factory, clock, delay: float, text: str = "Pebble, what's your favourite song?", sub=None, prepare=None):
    talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED),))
    talk.rig.turns.mind = Delayed(clock, talk.conv.sleep, delay, ANSWER, talk.conv)
    if sub is not None:
        talk.rig.life.p.subconscious = Subconscious(sub)
    if prepare is not None:
        prepare(talk)
    traced = []
    talk.conv.trace = lambda what, line: traced.append((what, line))

    async def go():
        await talk.say("ina", text)
        await talk.settle(delay + 8.0)

    asyncio.run(go())
    lines = talk.spoken()
    holds = [line for what, line in traced if what == "holds"]
    return talk, lines, holds


@pytest.mark.parametrize("delay", [1.0, 3.0, 8.0, 20.0])
def test_holds_come_in_stages_by_how_long_the_answer_takes(rig_factory, clock, delay):
    talk, lines, holds = asked(rig_factory, clock, delay)
    answer_at = next(i for i, line in enumerate(lines) if line.startswith("I saw them"))
    spoken_holds = lines[:answer_at]
    assert " ".join(lines[answer_at:]) == ANSWER
    assert len(spoken_holds) == len(holds) <= 3
    assert all(norm(a) != norm(b) for a, b in zip(spoken_holds, spoken_holds[1:]))
    stats = talk.conv.stats.as_dict()
    assert stats["replies"] == 1 and stats["first_word_s_max"] <= 0.75
    expected = {1.0: 1, 3.0: 2, 8.0: 2, 20.0: 3}[delay]
    assert len(spoken_holds) == expected
    assert (SLOW in spoken_holds) == (delay == 20.0)
    assert ANSWER not in " ".join(spoken_holds)


def test_no_hold_once_the_answer_is_ready(rig_factory, clock):
    talk, lines, holds = asked(rig_factory, clock, 0.0)
    assert holds == [] and " ".join(lines) == ANSWER


def test_a_stop_gets_no_holds(rig_factory, clock):
    talk, lines, holds = asked(rig_factory, clock, 5.0, text="Pebble, stop")
    assert holds == []
    assert not any(line in [t for s in STOCK.values() for g in s.values() for t in g] for line in lines)


def test_holds_are_whispered_in_quiet_hours(rig_factory, clock):
    talk, lines, holds = asked(rig_factory, clock, 3.0, prepare=lambda t: setattr(t.conv, "_quiet", lambda: True))
    said = talk.rig.store.read_lines("logs/speech.jsonl")
    assert holds and all(entry["whisper"] for entry in said if entry["text"] in lines)


def test_the_small_model_may_write_the_second_hold_but_only_inside_the_fence(rig_factory, clock):
    def favour_small(talk):
        talk.conv.holds.arms["question/2"] = {SMALL: [60.0, 0.0], **{text: [0.0, 40.0] for text in STOCK[2]["any"]}}

    sub = ScriptedMind(holds=["Ooh, the song question."])
    talk, lines, holds = asked(rig_factory, clock, 4.0, sub=sub, prepare=favour_small)
    assert any(r["purpose"] == "hold" for r in sub.requests)
    assert "Ooh, the song question." in lines
    bad = ScriptedMind(holds=["The answer is under the couch."])
    talk, lines, holds = asked(rig_factory, clock, 4.0, sub=bad, prepare=favour_small)
    assert "The answer is under the couch." not in lines
    assert len([line for line in lines if not line.startswith("I saw")]) == 2


def test_a_private_question_is_never_echoed(rig_factory, clock):
    offered = []

    def watch(talk):
        choose = talk.conv.holds.choose

        def spy(situation, stage, now, person=None, known=False, child=False, echo="", small=""):
            offered.append(echo)
            return choose(situation, stage, now, person, known, child, echo, small)

        talk.conv.holds.choose = spy

    asked(rig_factory, clock, 3.0, prepare=watch)
    assert "What's my favourite song?" in offered
    offered.clear()
    asked(rig_factory, clock, 3.0, text="Pebble, between us, what's your favourite song?", prepare=watch)
    assert offered and not any(offered)


def bandit_run(book: Phrasebook, rounds: int, judge, person=None, known=False, echo=""):
    picks = []
    now = 0.0
    for _ in range(rounds):
        now += 240.0
        picked = book.choose("question", 1, now, person, known, echo=echo)
        assert picked is not None
        key, text = picked
        book.said(key, text, "question", 1, now, person, known)
        picks.append(key)
        book.outcome(judge(key), now + 1.0)
    return picks


def test_the_bandit_fades_a_talked_over_hold_and_keeps_a_liked_one():
    book = Phrasebook(rng=random.Random(3))
    picks = bandit_run(book, 400, lambda key: "talked_over" if key == "Hmm," else "laughed" if key == "Ooh, good question." else "waited")
    late = picks[-150:]
    assert late.count("Hmm,") <= 0.05 * len(late)
    assert late.count("Ooh, good question.") > 0.35 * len(late)
    assert book.mean("Hmm,") < 0.2 < book.mean("Ooh, good question.")
    assert book.holds["Hmm,"]["source"] == "stock" and not book.holds["Hmm,"].get("dropped")
    scores = [book._sample("Hmm,", "question", 1, None, False) for _ in range(200)]
    assert min(scores) >= 0.0 and max(scores) > 0.0


def test_the_bandit_learns_per_person():
    book = Phrasebook(rng=random.Random(5))
    echo = "Where are your keys?"
    bandit_run(book, 200, lambda key: "laughed" if key == ECHO else "waited", "ina", True, echo)
    bandit_run(book, 200, lambda key: "talked_over" if key == ECHO else "waited", "sam", True, echo)
    ina = bandit_run(book, 100, lambda key: "waited", "ina", True, echo)
    sam = bandit_run(book, 100, lambda key: "waited", "sam", True, echo)
    assert ina.count(ECHO) > sam.count(ECHO) + 10
    assert book.people["ina"]["arms"]["question/1"][ECHO][0] > book.people["sam"]["arms"]["question/1"][ECHO][0]


def test_stop_saying_a_hold_stops_it_for_that_person(rig_factory):
    book = Phrasebook(rng=random.Random(1))
    assert book.stop_asked("Pebble, stop saying hmm", "ina", True) == "Hmm,"
    for index in range(200):
        picked = book.choose("question", 1, index * 700.0, "ina", True)
        assert picked is None or norm(picked[1]) != "hmm"
    assert any(norm(book.choose("other", 1, index * 700.0, "sam", True)[1]) == "hmm" for index in range(200))
    assert book.stop_asked("please stop saying banana", "ina", True) is None
    assert book.stop_asked("i wish you would stop", "ina", True) is None


def test_why_do_you_say_answers_from_the_phrasebook(rig_factory, clock):
    book = Phrasebook(rng=random.Random(2), clock=clock)
    answer = book.why("Pebble, why do you always say ooh?")
    assert answer.startswith('"Ooh,"') and "started with" in answer and "asks me something" in answer
    assert book.why("why do you say banana") is None
    assert book.why("what do you say") is None


def test_new_holds_come_from_the_wordsmith_through_the_fence(rig_factory, clock):
    from pebble.mind.wordsmith import Phrased

    diary = []
    book = Phrasebook(rng=random.Random(4), clock=clock)
    book.diary = diary.append
    offers = iter(["Let me check that for you.", "Ooh, let me ponder.", "Hmm, a puzzle."])

    async def phrase(seed, kind):
        return Phrased(next(offers), "creative")

    now = clock.now()
    assert run(book.invent(phrase, now)) is None
    assert "Let me check that for you." not in book.holds
    assert run(book.invent(phrase, now + 1.0)) is None
    added = run(book.invent(phrase, now + 3 * 86400.0))
    assert added == "Ooh, let me ponder."
    assert book.holds[added]["source"] == "own" and book.holds[added]["trial"]
    assert diary and "started saying" in diary[-1]
    assert run(book.invent(phrase, now + 3 * 86400.0 + 60.0)) is None
    situation = book.holds[added]["situations"][0]
    stage = book.holds[added]["stages"][0]
    for index in range(2):
        entry = {"key": added, "text": added, "situation": situation, "stage": stage, "person": None, "known": False, "at": 0.0}
        book._update(entry, "talked_over")
    assert book.holds[added].get("dropped") and "stopped saying" in diary[-1]
    assert added not in book.own()


def test_the_phrasebook_is_kept_and_forget_deletes_a_persons_weights(rig_factory, clock):
    talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED), ("Sam", FRIEND)))
    book = talk.conv.holds
    ina = talk.ids["ina"]
    sam = talk.ids["sam"]
    for person in (ina, sam):
        book.said("Hmm,", "Hmm,", "question", 1, 1.0, person, True)
        book.outcome("laughed", 2.0)
    book.said("Ooh,", "Ooh,", "question", 1, 3.0, "stranger-1", False)
    book.outcome("laughed", 4.0)
    book.save()
    kept = talk.rig.store.read(HOLDS)
    assert ina in kept["people"] and sam in kept["people"] and "stranger-1" not in kept["people"]
    assert any(entry.get("person") == ina for entry in kept["log"])
    talk.conv.forget(ina, ["Ina"])
    kept = talk.rig.store.read(HOLDS)
    assert ina not in kept["people"] and sam in kept["people"]
    assert not any(entry.get("person") == ina for entry in kept["log"])
    again = Phrasebook(talk.rig.store)
    assert ina not in again.people and sam in again.people and "Hmm," in again.holds


def test_a_hold_talked_over_counts_against_it(rig_factory, clock):
    talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED),))
    talk.rig.turns.mind = Delayed(clock, talk.conv.sleep, 12.0, ANSWER, talk.conv)
    traced = []
    talk.conv.trace = lambda what, line: traced.append((what, line))

    async def go():
        await talk.say("ina", "Pebble, what's your favourite song?")
        await talk.settle(0.4)
        await talk.say("ina", "Pebble, what's your favourite song?")
        await talk.settle(16.0)

    asyncio.run(go())
    spoken = [line.split('"')[1] for what, line in traced if what == "holds"]
    assert spoken
    hello = [entry for entry in talk.conv.holds.log if entry["how"] == "hello"]
    assert len(hello) == 1
    last = hello[0]
    assert last["hold"] in spoken + ["<echo>", "<small>"]
    slot = talk.conv.holds.arms[f"{last['situation']}/{last['stage']}"]
    assert slot[last["hold"]][1] >= 1.0


def test_on_a_fast_rung_the_first_spoken_hold_waits_until_about_a_second(rig_factory, clock):
    def fast(talk):
        talk.conv.stats.answer_latencies = [0.8] * 6

    talk, lines, holds = asked(rig_factory, clock, 0.9)
    assert len(holds) == 1
    talk, lines, holds = asked(rig_factory, clock, 0.9, prepare=fast)
    assert holds == [] and " ".join(lines) == ANSWER
    talk, lines, holds = asked(rig_factory, clock, 1.6, prepare=fast)
    assert len(holds) == 1
    assert talk.conv.stats.as_dict()["first_word_s_max"] >= 0.95
