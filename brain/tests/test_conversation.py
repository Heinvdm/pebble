import asyncio
import math
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from pebble.conversation import words as w
from pebble.conversation.address import ADDRESSED, MAYBE, OVERHEARD, Cues, Room, decide
from pebble.conversation.core import Conversation
from pebble.conversation.eval import evaluate, report
from pebble.conversation.facts import FILE as FACTS_FILE, Overheard, extract, forget, leaks
from pebble.conversation.gist import Gist
from pebble.conversation.listening import Listening, asks_start, asks_stop
from pebble.conversation.monologue import Monologue
from pebble.conversation.mouth import Mouth, sentences
from pebble.conversation.scripted import Said, ScriptedSpeech
from pebble.conversation.speakers import Speakers
from pebble.conversation.speakup import Moment, SpeakUp
from pebble.conversation.turns import TurnTaker
from pebble.conversation.window import Line, Window, visible
from pebble.people.fake import fake_print
from pebble.people.trust import FRIEND, TRUSTED
from pebble.seams.sight import SeenPerson, SeenThing, Sight
from pebble.speech.events import SpeechEvent

HOLDOUT = Path(__file__).resolve().parents[1] / "pebble" / "conversation" / "eval_holdout.jsonl"


def test_addressing_on_the_scripted_scenes():
    main = report(evaluate())
    assert main["lines"] >= 90 and main["scenes"] >= 25
    assert main["false_replies"] == 0
    assert main["missed"] == 0
    assert main["accuracy"] >= 0.95


def test_addressing_on_the_holdout_scenes():
    held = report(evaluate(HOLDOUT))
    assert held["false_replies"] == 0
    assert held["accuracy"] >= 0.9


@pytest.mark.parametrize("text,use", [
    ("pebble what do you think", "vocative"),
    ("hey pebble come here", "vocative"),
    ("what do you think pebble", "vocative"),
    ("thanks pebble", "vocative"),
    ("i think pebble is cute", "mention"),
    ("pebble's been quiet today", "mention"),
    ("did you charge pebble last night", "mention"),
    ("pebbles are small stones", "mention"),
    ("pebble can you come here", "vocative"),
    ("the dog ate my homework", None),
])
def test_name_use(text, use):
    assert w.name_use(text, "Pebble") == use


def test_other_names_and_room_questions():
    assert w.other_vocative("sam can you pass the salt", ["sam"]) == "sam"
    assert w.other_vocative("i saw sam yesterday", ["sam"]) is None
    assert w.other_vocative("sam is late again", ["sam"]) is None
    assert w.other_vocative("hi mum how are you", []) == "mum"
    assert w.to_room("has anyone seen the remote")
    assert w.as_asked_of_me("has anyone seen the remote") == "have you seen the remote"
    assert w.as_asked_of_me("does anybody know where my keys are") == "where is my keys"
    assert w.complete("what do you think") and not w.complete("so i was thinking that")


def test_a_stranger_on_the_phone_or_naming_someone_else_never_gets_addressed():
    assert decide(Cues(alone=True, on_phone=True, you_form=True, question=True, looking=True)).label != ADDRESSED
    assert decide(Cues(other_named=True, looking=True, you_form=True)).label != ADDRESSED
    assert decide(Cues(name="vocative", on_phone=True)).label != OVERHEARD
    assert decide(Cues(alone=True, looking=True, you_form=True, question=True)).label == ADDRESSED
    assert decide(Cues(exchange=True, others=1)).label == OVERHEARD


def test_room_remembers_who_pebble_was_talking_to():
    room = Room("Pebble")
    room.spoke(10.0, "ina", asked=True)
    cues = room.cues(12.0, "ina", "yes please", False, 2)
    assert cues.asked and cues.spoke_to_them and decide(cues).label == ADDRESSED
    other = room.cues(12.0, "sam", "no way", False, 2)
    assert decide(other).label != ADDRESSED


def events_of(said: list[tuple[str, str]], start: float = 0.0, gap: float = 0.5):
    speech = ScriptedSpeech()
    out = []
    t = start
    for who, text in said:
        found, end = speech.events(Said(who, text), t)
        out.extend(found)
        t = end + gap
    return out, t


def test_turns_end_sooner_after_a_complete_question():
    closed = []
    taker = TurnTaker(on_close=closed.append)
    found, _ = events_of([("ina", "what do you think about it")])
    for event in found:
        taker.feed(event)
    end = found[-1].end
    assert taker.tick(end + 0.2) is None
    assert taker.tick(end + 0.32) is not None
    assert closed[0].text == "what do you think about it"
    taker = TurnTaker(on_close=closed.append)
    found, _ = events_of([("ina", "so i was thinking that")])
    for event in found:
        taker.feed(event)
    end = found[-1].end
    assert taker.tick(end + 0.4) is None
    assert taker.tick(end + 0.66) is not None


def test_a_name_then_a_pause_stays_one_turn():
    closed, named = [], []
    taker = TurnTaker(on_close=closed.append, on_name=named.append)
    found, _ = events_of([("ina", "Pebble, what do you think?")])
    for event in sorted(found, key=lambda e: e.t):
        taker.tick(event.t)
        taker.feed(event)
    taker.tick(found[-1].t + 1.0)
    assert len(closed) == 1 and named
    turn = closed[0]
    assert turn.keyword and turn.name_alone and turn.text == "what do you think"


def test_a_different_voice_splits_the_turn():
    closed = []
    taker = TurnTaker(on_close=closed.append)
    speech = ScriptedSpeech()
    first, end = speech.events(Said("ina", "i really think we should go to the beach"), 0.0)
    second, _ = speech.events(Said("sam", "no the mountains are much better this time"), end + 0.3)
    for event in sorted(first + second, key=lambda e: e.t):
        taker.feed(event)
    taker.tick(100.0)
    assert [t.text for t in closed] == ["i really think we should go to the beach", "no the mountains are much better this time"]


def test_speak_up_waits_for_a_pause_and_never_interrupts_trouble():
    gate = SpeakUp(lambda: 5)
    calm = Moment(100.0, silent_for=3.0)
    assert gate.decide(calm, "room_question").speak
    for trouble in ("quiet", "alarm", "argument", "crying", "on_phone", "upset", "someone_talking", "pebble_speaking"):
        assert not gate.decide(Moment(100.0, silent_for=3.0, **{trouble: True}), "room_question").speak
    assert not gate.decide(Moment(100.0, silent_for=0.5), "room_question").speak
    assert gate.decide(Moment(100.0, silent_for=3.0, hushed=True), "room_question").speak
    assert not gate.decide(Moment(100.0, silent_for=3.0, hushed=True), "named", roll=0.0).speak


def spoke_up(gate, hours, reason="named", every=400.0):
    t, count = 0.0, 0
    while t < hours * 3600.0:
        t += every
        if gate.decide(Moment(t, silent_for=5.0), reason, roll=0.0).speak:
            gate.used(t, reason, someone_there=False)
            gate.tick(t, False)
            gate.tick(t + 30.0, False)
            count += 1
    return count


def test_how_often_it_speaks_up_unasked_is_its_own_dial():
    assert SpeakUp(lambda: 3).per_hour() == 2.0
    assert spoke_up(SpeakUp(lambda: 3), 6) == 12
    assert spoke_up(SpeakUp(lambda: 3, rate=lambda: 4.0), 6) == 24
    assert spoke_up(SpeakUp(lambda: 3, rate=lambda: 1.0), 6) == 6
    assert spoke_up(SpeakUp(lambda: 3, rate=lambda: 0.5), 6) == 3
    assert spoke_up(SpeakUp(lambda: 3, rate=lambda: 0.0), 6) == 0
    assert spoke_up(SpeakUp(lambda: 3, rate=lambda: 0.0), 1, "room_question") > 0
    assert SpeakUp(rate=lambda: 9.0).per_hour() == 4.0 and SpeakUp(rate=lambda: "x").per_hour() == 2.0
    assert SpeakUp(lambda: 5).decide(Moment(0.0, silent_for=5.0), "named", roll=0.99).why == "I let it pass"
    assert SpeakUp(lambda: 1).decide(Moment(0.0, silent_for=5.0), "named", roll=0.2).why == "I let it pass"
    assert SpeakUp(lambda: 9).decide(Moment(0.0, silent_for=5.0), "named", roll=0.2).speak


def reacted(gate, t, kind):
    gate.used(t, "feeling")
    gate.tick(t, True)
    gate.tick(t + 2.0, False)
    if kind == "hushed":
        gate.heard(t + 3.0, "shh not now", False)
    elif kind == "warm":
        gate.heard(t + 3.0, "haha that's funny", False)
    elif kind == "talked_over":
        gate.watch.ended_at = None
        gate.talked_over(t + 1.0)
        gate.tick(t + 2.0, False)
    return gate.tick(t + 30.0, False)


def test_how_people_take_it_nudges_how_often_it_speaks_up():
    gate = SpeakUp(lambda: 3)
    assert reacted(gate, 0.0, "hushed") == (-1, "people hushed me when I spoke up unasked")
    assert reacted(gate, 100.0, "warm") is None and reacted(gate, 200.0, "warm") is None
    assert reacted(gate, 1000.0, "warm") == (1, "people took it up warmly when I spoke up unasked")
    assert reacted(gate, 2000.0, "talked_over") is None
    assert reacted(gate, 2100.0, "talked_over") == (-1, "people talked over me when I spoke up unasked")
    assert [reacted(gate, 3000.0 + n * 100.0, "ignored") for n in range(4)] == [None, None, None, (-1, "nobody took it up when I spoke up unasked")]
    lonely = SpeakUp(lambda: 3)
    for n in range(6):
        lonely.used(n * 1000.0, "feeling", someone_there=False)
        lonely.tick(n * 1000.0 + 1.0, False)
        assert lonely.tick(n * 1000.0 + 30.0, False) is None
    care = SpeakUp(lambda: 3)
    for n in range(6):
        care.used(n * 1000.0, "care")
        care.tick(n * 1000.0 + 1.0, False)
        assert care.tick(n * 1000.0 + 30.0, False) is None
    assert gate.reactions == {"hushed": 1, "warm": 3, "talked_over": 2, "ignored": 4}


def test_being_hushed_lowers_its_own_speak_up_dial_through_the_checker(rig_factory, clock):
    talk = Talk(rig_factory, clock, people=(("Ina", TRUSTED),))
    conv = talk.conv
    conv.speakup.rng = None
    dials = talk.rig.life.dials
    assert dials.value("speakup.per_hour") == 2.0

    async def go():
        await talk.settle(2.0)
        conv._consider_speakup("feeling", "I'm in such a good mood.", None)
        await talk.settle(3.0)
        assert conv.stats.spoke_up == 1
        await talk.say("ina", "shh pebble not now")
        await talk.settle(25.0)

    asyncio.run(go())
    after = dials.value("speakup.per_hour")
    assert 1.5 <= after < 2.0
    change = dials.changes[-1]
    assert change["name"] == "speakup.per_hour" and change["why"] == "people hushed me when I spoke up unasked"
    assert conv.speakup.per_hour() == after
    assert not dials.propose("speakup.per_hour", 4.5, "pebble", "test").ok
    assert not dials.propose("speakup.per_hour", 3.0, "people", "someone asked").ok


def test_overheard_facts_are_pulled_out_in_plain_words():
    assert extract("i have my driving test on friday so saturday is perfect", "Ina") == ("Ina has their driving test on friday", "plan")
    assert extract("i'm so nervous about the interview", "Ina") == ("Ina felt nervous about the interview", "feeling")
    assert extract("my mum is visiting next week", "Sam") == ("Sam's mum is visiting next week", "plan")
    assert extract("it was a lovely day", "Sam") is None


def test_overheard_facts_are_kept_private_expire_and_can_be_forgotten(rig_factory, clock):
    rig = rig_factory()
    book = Overheard(rig.store, clock)
    fact = book.learn("p1", "Ina", "i have my driving test on friday")
    assert fact is not None and fact.kind == "plan" and "driving" in fact.words
    book.save()
    assert leaks("Ina has a driving test tomorrow", [fact])
    assert not leaks("The beach sounds lovely", [fact])
    assert Overheard(rig.store, clock).about("p1")
    clock.advance(14 * 86400)
    assert book.expire() == 1
    book.learn("p2", "Sam", "i love sushi")
    book.save()
    assert forget(rig.store, "p2", ["Sam"]) == 1
    assert (rig.store.read(FACTS_FILE, {}) or {}).get("facts") == []


def test_the_window_shows_talk_only_to_people_who_heard_it():
    line = Line(1.0, "ina", "Ina", "the beach on saturday", OVERHEARD, frozenset({"ina", "sam"}))
    assert visible(line, frozenset({"ina", "sam"})) and visible(line, frozenset({"sam"}))
    assert not visible(line, frozenset({"sam", "mo"}))
    secret = Line(1.0, "ina", "Ina", "between us", OVERHEARD, frozenset({"ina", "sam"}), private=True)
    assert visible(secret, frozenset({"ina"})) and not visible(secret, frozenset({"sam"}))
    window = Window(keep_s=60.0)
    window.add(line)
    window.add(Line(100.0, "sam", "Sam", "later", OVERHEARD, frozenset({"sam"})))
    assert [l.text for l in window.lines] == ["later"]


def test_gists_name_who_the_topic_and_the_mood_without_private_lines():
    gist = Gist()
    lines = [
        Line(1.0, "ina", "Ina", "are we going to the beach on saturday", OVERHEARD, frozenset({"ina", "sam"})),
        Line(4.0, "sam", "Sam", "the beach would be lovely haha", OVERHEARD, frozenset({"ina", "sam"})),
        Line(7.0, "ina", "Ina", "i have my driving test on friday", OVERHEARD, frozenset({"ina", "sam"}), private=True),
    ]
    gist.laughed()
    thoughts = gist.plain(lines, 10.0)
    assert thoughts[0].text.startswith("Ina and Sam talked about beach")
    assert "cheerful" in thoughts[0].text and "driving" not in thoughts[0].text
    assert gist.due(60.0, lines) and not gist.due(8.0, lines)


def test_monologue_keeps_private_thoughts_with_their_people():
    from pebble.conversation.gist import Thought

    mind = Monologue()
    mind.add(Thought(1.0, "Ina has a test on friday", "fact", ("ina",), frozenset({"ina"}), 0.6, True))
    mind.add(Thought(2.0, "Ina and Sam talked about the beach", "gist", ("ina", "sam"), frozenset({"ina", "sam"}), 0.7, True))
    assert [t.text for t in mind.recent(3.0, frozenset({"ina"}))] == ["Ina has a test on friday", "Ina and Sam talked about the beach"]
    assert [t.text for t in mind.recent(3.0, frozenset({"sam", "mo"}))] == []
    assert [t.text for t in mind.best_of_day()] == ["Ina and Sam talked about the beach"]


def test_who_is_talking_from_voice_and_from_lips(rig_factory, clock):
    rig = rig_factory()
    ina = rig.books.people.meet(clock.now(), voice=fake_print("ina", "voice"))
    ina.set_name("Ina")
    speakers = Speakers(rig.books.people, rig.life.company.presence, clock.now)
    who = speakers.identify(tuple(fake_print("ina", "voice")), 0.0, 1.0, clock.now())
    assert who.person_id == ina.id and who.how == "voice"
    assert speakers.identify(tuple(fake_print("sam", "voice")), 0.0, 1.0, clock.now()).person_id is None
    phone = SeenThing("phone", 11.0, 6.0, 0.05, 0.03, 0.9, 0.0, held=True)
    sight = Sight(0.0, "front", 60.0, people=(SeenPerson(10.0, 5.0, 0.4, 0.2, 0.9, True, 3, facing_deg=5.0, speaking=0.9), SeenPerson(-15.0, 5.0, 0.4, 0.2, 0.9, True, 4, facing_deg=60.0, speaking=0.05)), things=(phone,))
    speakers.look(sight, 2.0)
    who = speakers.identify(None, 1.8, 2.2, clock.now())
    assert who.track == 3 and who.looking is True and who.on_phone


def test_mouth_cuts_sentences_drops_echo_and_holds_back_leaks(clock):
    assert sentences("Hello there. How are", True, False) == (["Hello there."], "How are")
    assert sentences("I think that is right, yes", True, False)[0] == ["I think that is right,"]
    assert sentences("Well, I think so", True, False)[0] == []

    class Voice:
        def __init__(self):
            self.lines = []

        async def say(self, text, whisper=False):
            self.lines.append(text)

    async def go():
        async def fast(seconds):
            clock.advance(seconds)
            await asyncio.sleep(0)

        voice = Voice()
        mouth = Mouth(voice, None, clock, sleep=fast)

        async def words():
            for piece in ["Sunday ", "works. ", "Ina has her ", "driving test ", "then. ", "Bye."]:
                yield piece

        spoken = await mouth.stream(words(), check=lambda s: "driving" not in s)
        return voice, mouth, spoken

    voice, mouth, spoken = asyncio.run(go())
    assert voice.lines == ["Sunday works.", "Bye."] and mouth.held_back == 1
    assert mouth.echo("sunday works", clock.monotonic())
    assert not mouth.echo("what about monday then", clock.monotonic())


def test_listening_mute_and_unmute(rig_factory, clock):
    rig = rig_factory()
    listening = Listening(rig.store, clock, {})
    assert listening.policy(False, False) == "words" and listening.policy(True, False) == "keywords" and listening.policy(True, True) == "words"
    listening.mute("p1")
    assert listening.muted and listening.policy(False, False) == "keywords"
    assert Listening(rig.store, clock, {}).muted
    assert listening.mark("keywords") == {"on": True, "words": False, "muted": True}
    clock.advance(13 * 3600)
    assert not listening.muted
    assert asks_stop("could you stop listening for a bit") and asks_start("pebble start listening")
    assert not asks_stop("stop it")
    assert Listening(None, clock, {"listening": {"night_keywords": False}}).policy(True, False) == "off"


class Talk:
    def __init__(self, rig_factory, clock, people=(("Ina", TRUSTED),), replies=("Hello! Nice to hear you.",)):
        self.clock = clock
        self.rig = rig = rig_factory()
        rig.mind.replies = list(replies)
        self.ids = {}
        for name, tier in people:
            person = rig.books.people.meet(clock.now(), voice=fake_print(name.lower(), "voice"), face=fake_print(name.lower(), "face"))
            person.set_name(name)
            person.override = tier
            self.ids[name.lower()] = person.id
            rig.life.company.presence.saw(person.id, clock.now())
        rig.life._mind_ready = True

        async def fast(seconds):
            clock.advance(seconds)
            await asyncio.sleep(0)

        self.conv = Conversation(clock, rig.store, rig.books, rig.voice, rig.face, rng=random.Random(5), sleep=fast)
        rig.life.p.conversation = self.conv
        self.conv.attach(rig.life)
        self.speech = ScriptedSpeech()

    async def say(self, who: str, text: str, during=None):
        for person_id in self.ids.values():
            self.rig.life.company.presence.saw(person_id, self.clock.now())
        start = self.clock.monotonic()
        found, end = self.speech.events(Said(who, text), start, speaking=self.conv.mouth.speaking)
        for event in found:
            while self.clock.monotonic() < event.t:
                self.clock.advance(0.05)
                self.conv.tick()
                await asyncio.sleep(0)
            if during is not None:
                during()
            self.conv.on_speech(event)
        await self.settle(1.5)

    async def settle(self, seconds: float):
        end = self.clock.monotonic() + seconds
        while self.clock.monotonic() < end:
            self.clock.advance(0.05)
            self.conv.tick()
            for _ in range(5):
                await asyncio.sleep(0)

    def spoken(self):
        return list(self.rig.voice.lines)


def test_overheard_chat_never_gets_a_reply(rig_factory, clock):
    talk = Talk(rig_factory, clock, people=(("Ina", TRUSTED), ("Sam", FRIEND)))

    async def go():
        await talk.say("ina", "did you watch the game last night")
        await talk.say("sam", "no i fell asleep on the couch")
        await talk.say("ina", "sam can you pass the salt")
        await talk.say("sam", "i think pebble is hungry")
        await talk.settle(3.0)

    asyncio.run(go())
    assert talk.conv.stats.replies == 0
    assert len(talk.spoken()) == talk.conv.stats.spoke_up
    labels = talk.conv.stats.labels
    assert labels[ADDRESSED] == 0 and labels[OVERHEARD] + labels[MAYBE] == 4
    assert len([line for line in talk.conv.window.lines if not line.pebble]) == 4
    assert talk.rig.life._heard == []


def test_called_by_name_it_answers_fast(rig_factory, clock):
    talk = Talk(rig_factory, clock, people=(("Ina", TRUSTED), ("Sam", FRIEND)))

    async def go():
        await talk.say("ina", "Pebble, how are you today?")
        await talk.settle(4.0)

    asyncio.run(go())
    assert " ".join(talk.spoken()) == "Hello! Nice to hear you."
    stats = talk.conv.stats.as_dict()
    assert stats["replies"] == 1 and stats["first_word_s_max"] <= 1.0
    history = talk.rig.history.messages()
    assert history and history[-1]["content"] == "Hello! Nice to hear you."
    assert any("said to you" in e.text for e in talk.rig.life.events.peek())


def test_talking_over_pebble_stops_it(rig_factory, clock):
    long = "Well. " + " ".join(["This is a long story about the beach and the sea."] * 6)
    talk = Talk(rig_factory, clock, replies=(long, long, "Okay."))

    async def go():
        await talk.say("ina", "Pebble, tell me a story")
        await talk.settle(1.5)
        assert talk.conv.mouth.speaking
        await talk.say("ina", "oh wait actually never mind that")
        await talk.settle(3.0)

    asyncio.run(go())
    assert talk.conv.stats.barge_ins == 1
    assert sum("long story" in line for line in talk.spoken()) < 6


LONG = "Well. " + " ".join(["This is a long story about the beach and the sea."] * 6)


def storyteller(rig_factory, clock, aec=False, replies=(LONG, LONG, "Okay.")):
    talk = Talk(rig_factory, clock, replies=replies)
    talk.conv.aec = aec

    async def paced(seconds):
        end = clock.monotonic() + seconds
        while clock.monotonic() < end:
            await asyncio.sleep(0)

    talk.conv.sleep = talk.conv.mouth.sleep = paced
    return talk


async def story(talk):
    await talk.say("ina", "Pebble, tell me a story")
    await talk.settle(1.5)
    assert talk.conv.mouth.speaking


async def hush(talk):
    talk.conv.mouth.stop()
    await talk.settle(0.2)


def sentence_start(talk):
    return max(p.started_at for p in talk.conv.mouth.parts.values() if p.started_at is not None and p.done_at is None)


def voice(talk, segment, pebble_speaking=True):
    talk.conv.on_speech(SpeechEvent("voice_start", talk.clock.monotonic(), segment, start=talk.clock.monotonic(), pebble_speaking=pebble_speaking))


@pytest.mark.parametrize("aec", [False, True])
def test_its_own_voice_coming_back_never_stops_it(rig_factory, clock, aec):
    talk = storyteller(rig_factory, clock, aec)
    conv = talk.conv

    async def go():
        await story(talk)
        for segment in (50, 51):
            while clock.monotonic() - sentence_start(talk) > 0.1:
                await talk.settle(0.05)
            voice(talk, segment)
            said = [p.text for p in conv.mouth.parts.values() if p.done_at is None and p.started_at is not None][-1]
            await talk.settle(0.6)
            conv.on_speech(SpeechEvent("partial", clock.monotonic(), segment, text=" ".join(said.split()[:4]).lower(), pebble_speaking=True))
            await talk.settle(1.0)
            conv.on_speech(SpeechEvent("partial", clock.monotonic(), segment, text=said.lower(), pebble_speaking=True))
            await talk.settle(1.0)
            conv.on_speech(SpeechEvent("voice_end", clock.monotonic(), segment, end=clock.monotonic(), pebble_speaking=True))
            assert conv.mouth.speaking
        speaking = conv.mouth.speaking
        await hush(talk)
        return speaking

    assert asyncio.run(go())
    assert conv.stats.barge_ins == 0 and conv.stats.echoes >= 4


def test_its_own_voice_leaking_past_the_echo_canceller_at_a_sentence_start_needs_words_to_stop_it(rig_factory, clock):
    talk = storyteller(rig_factory, clock, aec=True)
    conv = talk.conv

    async def go():
        await story(talk)
        while clock.monotonic() - sentence_start(talk) > 0.1:
            await talk.settle(0.05)
        voice(talk, 60)
        await talk.settle(1.0)
        assert conv.mouth.speaking and conv.stats.barge_ins == 0
        conv.on_speech(SpeechEvent("partial", clock.monotonic(), 60, text="hang on", pebble_speaking=True))
        await talk.settle(0.2)

    asyncio.run(go())
    assert conv.stats.barge_ins == 1 and not conv.mouth.speaking


def test_any_voice_stops_it_with_the_echo_canceller_on(rig_factory, clock):
    talk = storyteller(rig_factory, clock, aec=True)
    conv = talk.conv

    async def go():
        await story(talk)
        while clock.monotonic() - sentence_start(talk) < 1.0:
            await talk.settle(0.05)
        voice(talk, 70)
        await talk.settle(0.3)
        assert conv.mouth.speaking
        await talk.settle(0.2)

    asyncio.run(go())
    assert conv.stats.barge_ins == 1 and not conv.mouth.speaking
    assert talk.rig.blackbox and any(e.get("kind") == "barge_in" and e.get("why") == "voice" for e in talk.rig.store.read_lines("logs/blackbox.jsonl"))


def test_without_the_echo_canceller_one_new_word_in_a_voice_stops_it(rig_factory, clock):
    talk = storyteller(rig_factory, clock, aec=False)
    conv = talk.conv

    async def go():
        await story(talk)
        voice(talk, 80)
        await talk.settle(0.5)
        assert conv.mouth.speaking
        conv.on_speech(SpeechEvent("partial", clock.monotonic(), 80, text="sorry", pebble_speaking=True))
        await talk.settle(0.1)

    asyncio.run(go())
    assert conv.stats.barge_ins == 1 and not conv.mouth.speaking


def test_any_voice_is_on_unless_the_owner_switches_it_off(rig_factory, clock):
    assert Listening(None, clock, {}).barge_on_voice
    talk = storyteller(rig_factory, clock, aec=True)
    talk.conv.listening.barge_on_voice = False

    async def go():
        await story(talk)
        while clock.monotonic() - sentence_start(talk) < 1.0:
            await talk.settle(0.05)
        voice(talk, 95)
        await talk.settle(1.0)
        speaking = talk.conv.mouth.speaking
        await hush(talk)
        return speaking

    assert asyncio.run(go())
    assert talk.conv.stats.barge_ins == 0


class NightEars:
    def __init__(self):
        self.mode = "keywords"
        self.woken = []

    def wake_for(self, seconds):
        self.woken.append(seconds)
        self.mode = "words"

    def update(self):
        pass


def test_at_night_its_name_wakes_it_and_it_whispers(rig_factory, clock):
    talk = Talk(rig_factory, clock)
    conv = talk.conv
    conv._quiet = lambda: True
    conv.ears = ears = NightEars()

    async def go():
        conv.on_speech(SpeechEvent("keyword", clock.monotonic(), 1, word="pebble"))
        await talk.settle(2.0)

    asyncio.run(go())
    assert ears.woken and ears.woken[0] == 30.0 and ears.mode == "words"
    said = talk.rig.store.read_lines("logs/speech.jsonl")
    assert said and all(entry["whisper"] for entry in said)
    assert talk.spoken()[-1] in ("Yes?", "Mm?", "I'm here.")


def test_at_night_muted_ears_stay_off_for_the_name_and_by_day_nothing_changes(rig_factory, clock):
    talk = Talk(rig_factory, clock)
    conv = talk.conv
    conv._quiet = lambda: True
    conv.ears = ears = NightEars()
    conv.listening.mute(talk.ids["ina"])

    async def go():
        conv.on_speech(SpeechEvent("keyword", clock.monotonic(), 1, word="pebble"))
        await talk.settle(2.0)

    asyncio.run(go())
    assert ears.woken == [] and talk.spoken() == []
    day = Talk(rig_factory, clock)
    day.conv.ears = day_ears = NightEars()
    day_ears.mode = "words"

    async def by_day():
        day.conv.on_speech(SpeechEvent("keyword", clock.monotonic(), 1, word="pebble"))
        await day.settle(2.0)

    asyncio.run(by_day())
    assert day_ears.woken == []


def test_a_trusted_person_can_switch_the_ears_off(rig_factory, clock):
    talk = Talk(rig_factory, clock, people=(("Ina", TRUSTED),))

    async def go():
        await talk.say("ina", "Pebble, stop listening")
        await talk.settle(3.0)

    asyncio.run(go())
    assert talk.conv.listening.muted
    assert "ears are off" in " ".join(talk.spoken())
    assert talk.conv.listening.policy(False, False) == "keywords"
    assert talk.conv.listening.policy(False, True) == "words"
    assert talk.conv.window.lines == type(talk.conv.window.lines)()


def test_a_stranger_cannot_switch_the_ears_off(rig_factory, clock):
    stranger = Talk(rig_factory, clock, people=(("Mo", "stranger"),))

    async def go2():
        await stranger.say("mo", "Pebble, stop listening")
        await stranger.settle(3.0)

    asyncio.run(go2())
    assert not stranger.conv.listening.muted
    assert "Only someone I know can" in " ".join(stranger.spoken())


@pytest.mark.parametrize("tier", [FRIEND, "child"])
def test_a_guest_or_a_child_can_switch_the_ears_off_for_themselves(rig_factory, clock, tier):
    talk = Talk(rig_factory, clock, people=(("Mo", FRIEND),))
    mo = talk.rig.books.people.get(talk.ids["mo"])
    if tier == "child":
        mo.override = None
        mo.relationship = "child"

    async def go():
        await talk.say("mo", "Pebble, stop listening")
        await talk.settle(3.0)

    asyncio.run(go())
    listening = talk.conv.listening
    assert listening.muted and listening.muted_by == talk.ids["mo"]
    assert "ears are off" in " ".join(talk.spoken())
    assert listening.policy(False, False) == "keywords"
    if tier == "child":
        assert 11.9 * 3600 < listening.muted_until - clock.now() <= 12 * 3600 and not listening.guest
    else:
        assert 1.9 * 3600 < listening.muted_until - clock.now() <= 2 * 3600 and listening.guest


def test_a_guests_mute_ends_ten_minutes_after_they_go_and_help_is_heard_meanwhile(rig_factory, clock):
    talk = Talk(rig_factory, clock, people=(("Mo", FRIEND),))
    heard = []
    talk.rig.life.p.safety = SimpleNamespace(heard=lambda line, loud: heard.append((line.text, line.person_id, line.addressed)), active=False, hearing=None, ladder=None, hold_reason=lambda: None)

    async def go():
        await talk.say("mo", "Pebble, stop listening")
        await talk.settle(3.0)
        talk.conv.on_speech(SpeechEvent("keyword", clock.monotonic(), 5, word="help"))
        await talk.settle(1.0)

    asyncio.run(go())
    listening = talk.conv.listening
    assert listening.muted and listening.guest
    assert heard[-1] == ("help", None, False)
    talk.rig.life.company.presence.left(talk.ids["mo"])
    for _ in range(11):
        clock.advance(60.0)
        talk.conv.tick()
    assert not listening.muted


def test_whoever_switched_the_ears_off_can_switch_them_back_on(rig_factory, clock):
    talk = Talk(rig_factory, clock, people=(("Mo", FRIEND),))
    talk.conv.listening.mute(talk.ids["mo"])

    async def go():
        talk.conv.on_speech(SpeechEvent("keyword", clock.monotonic(), 2, word="pebble start listening"))
        await talk.settle(2.0)

    asyncio.run(go())
    assert not talk.conv.listening.muted
    other = Talk(rig_factory, clock, people=(("Sam", FRIEND),))
    other.conv.listening.mute("someone else")

    async def again():
        other.conv.on_speech(SpeechEvent("keyword", clock.monotonic(), 2, word="pebble start listening"))
        await other.settle(2.0)

    asyncio.run(again())
    assert other.conv.listening.muted


def test_muted_ears_come_back_on_by_the_spoken_phrase(rig_factory, clock):
    talk = Talk(rig_factory, clock, people=(("Ina", TRUSTED),))
    talk.conv.listening.mute(talk.ids["ina"])

    async def go():
        talk.conv.on_speech(SpeechEvent("keyword", clock.monotonic(), 1, word="pebble"))
        await talk.settle(1.0)
        assert talk.conv.listening.muted
        talk.conv.on_speech(SpeechEvent("keyword", clock.monotonic(), 2, word="pebble start listening"))
        await talk.settle(2.0)

    asyncio.run(go())
    assert not talk.conv.listening.muted
    assert talk.spoken()[-1] == "My ears are back on."


def test_a_reply_knows_the_time_and_its_battery_so_it_never_makes_them_up(rig_factory, clock):
    talk = Talk(rig_factory, clock)
    asyncio.run(talk.rig.life.read_sensors())
    observation, _ = talk.conv._observation(type("T", (), {"label": "Ina"})(), "what's the time?", talk.ids["ina"])
    local = clock.local()
    lines = observation.split("\n")
    assert f"It is {local:%A} {local:%H:%M}; your battery is at 80%" in observation
    assert lines[-2].startswith("Answer Ina out loud now") and lines[-3].startswith("It is ")


def test_overheard_facts_shape_care_for_that_person_only(rig_factory, clock):
    talk = Talk(rig_factory, clock, people=(("Ina", TRUSTED), ("Sam", FRIEND)))
    ina, sam = talk.ids["ina"], talk.ids["sam"]

    async def go():
        await talk.say("ina", "i have my driving test on friday")
        await talk.say("sam", "you'll be fine")

    asyncio.run(go())
    facts = talk.conv.overheard.about(ina)
    assert facts and "driving test" in facts[0].text
    lines, private = talk.conv.mind_lines(clock.now())
    text = "\n".join(lines)
    assert "driving" not in text
    turn = type("T", (), {"label": "Sam"})()
    observation, _ = talk.conv._observation(turn, "what's up", sam)
    assert "driving" not in observation
    presence = talk.rig.life.company.presence
    presence.left(sam)
    clock.advance(1.0)
    observation, items = talk.conv._observation(type("T", (), {"label": "Ina"})(), "hi pebble", ina)
    assert "driving test" in observation
    assert any(item["to"] == ina and "driving test" in item["text"] for item in items)
    assert talk.conv._privacy_check(ina) is None
    presence.saw(sam, clock.now())
    check = talk.conv._privacy_check(sam)
    assert check is not None and not check("Ina has a driving test on Friday!") and check("The beach sounds lovely.")


def test_forgetting_someone_clears_what_was_overheard(rig_factory, clock):
    talk = Talk(rig_factory, clock, people=(("Ina", TRUSTED), ("Sam", FRIEND)))

    async def go():
        await talk.say("ina", "i have my driving test on friday")

    asyncio.run(go())
    talk.conv.save()
    ina = talk.ids["ina"]
    talk.conv.forget(ina, ["Ina"])
    assert not talk.conv.overheard.about(ina)
    assert not any(line.who == ina for line in talk.conv.window.lines)
    assert (talk.rig.store.read(FACTS_FILE, {}) or {}).get("facts") == []


def test_the_scene_ina_and_sam(tmp_path):
    from pebble.conversation.scene import play

    show = asyncio.run(play(root=tmp_path / "self"))
    lines = show.scene.lines
    stats = show.stats
    says = [line for line in lines if " says " in line]
    assert stats["replies"] == 2 and stats["barge_ins"] == 1 and stats["spoke_up"] >= 2
    assert stats["first_word_s_max"] <= 1.0
    assert any("remote control near the couch" in line for line in says)
    assert any("Good luck, Ina!" in line for line in says)
    first_question = next(i for i, line in enumerate(lines) if "has anyone seen the remote" in line)
    assert not any(" says " in line for line in lines[:first_question])
    assert any("notes" in line and "driving test" in line for line in lines)
    assert any("face     happy" in line for line in lines)
    assert any("face     surprised" in line for line in lines)


def test_the_model_sees_recent_talk_but_the_history_keeps_none_of_it(rig_factory, clock):
    talk = Talk(rig_factory, clock, people=(("Ina", TRUSTED), ("Sam", FRIEND)))

    async def go():
        await talk.say("sam", "the zebra crossing on main street is closed")
        await talk.say("ina", "Pebble, what do you think?")
        await talk.settle(4.0)

    asyncio.run(go())
    asked = [r for r in talk.rig.mind.requests if r["purpose"] == "reply"]
    assert asked and any("zebra" in (m.get("content") or "") for m in asked[-1]["messages"])
    stored = str(talk.rig.store.read("conversation/history.json"))
    assert "what do you think" in stored and "zebra" not in stored
    lines, _ = talk.conv.mind_lines(clock.now())
    assert lines and "zebra, crossing, main" in " ".join(lines) and "the zebra crossing on main street" not in " ".join(lines)


def test_the_monologue_takes_in_what_it_sees_and_remembers(rig_factory, clock):
    talk = Talk(rig_factory, clock, people=(("Ina", TRUSTED),))
    ina = talk.ids["ina"]
    talk.conv.overheard.learn(ina, "Ina", "i have my driving test on friday")
    talk.conv.was_here = set()
    talk.rig.life.alive.log.append("Ina waved at you")
    talk.conv.tick()
    texts = [t.text for t in talk.conv.monologue.thoughts]
    assert "I noticed: Ina waved at you." in texts
    assert "I remember: Ina has their driving test on friday." in texts
    alone = [t.text for t in talk.conv.monologue.recent(clock.now(), frozenset({ina}))]
    assert "I remember: Ina has their driving test on friday." in alone
    assert not [t for t in talk.conv.monologue.recent(clock.now(), frozenset({ina, "p99"})) if "driving" in t.text]
