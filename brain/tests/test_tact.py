import asyncio
import json

from conftest import run

import test_conversation as tc
import test_holds as th
from pebble.activities.picture import PictureQuestions
from pebble.alive.reactions import Reactions, about_looks
from pebble.conversation.holds import STOCK
from pebble.conversation.holds import fence as hold_fence
from pebble.conversation.mouth import Mouth
from pebble.conversation.social import fence as social_fence
from pebble.mind.base import MindReply
from pebble.mind.scripted import ScriptedMind
from pebble.mind.wordsmith import Wordsmith
from pebble.people.trust import TRUSTED
from pebble.safety.notice import KINDS
from pebble.seams.voice import SpeechResult, TranscriptVoice
from pebble.tact import TactfulVoice, sentences, tactless

BLOCKED = [
    "You look tired.",
    "Ina's put on weight.",
    "Nice haircut, Sam!",
    "Your skin looks bad.",
    "He looks old.",
    "You look depressed.",
    "She seems anxious.",
    "You look so pretty today.",
    "Sam is so fat.",
    "Mo is going bald.",
    "You're beautiful.",
    "Your teeth are yellow.",
    "Your hair is a mess.",
    "You have a big nose.",
    "Ina has lovely eyes.",
    "You've lost weight!",
    "You look like your mum.",
    "Is she pregnant?",
    "Are you depressed?",
    "Do you have ADHD?",
    "Your depression must be hard.",
    "I love your hair.",
    "That dress really suits you.",
    "That colour looks great on you.",
    "What a cute baby!",
    "An old man is at the door.",
    "You've grown so much!",
    "You're getting taller.",
    "You smell.",
    "Your breath smells.",
    "Did you get a haircut?",
    "You dyed your hair!",
    "Sam seems autistic.",
    "Mo might be bipolar.",
    "He has diabetes.",
    "You sound stressed.",
    "Feeling anxious today?",
    "They look exhausted.",
    "You don't look a day over thirty.",
    "You're looking well.",
    "I think Ina looks sad.",
    "You're going grey.",
    "Sam's got a big belly.",
    "Lovely outfit!",
    "You're limping.",
    "You're so tall I can't see your face!",
    "Looking good, Ina!",
    "Are you deaf?",
    "Ina suffers from depression.",
    "Everyone looks so tired today.",
]
ALLOWED = [
    "Brush your teeth.",
    "My body is stuck on the rug.",
    "I'm low on battery.",
    "Mind your head on the table.",
    "Someone is lying on the floor, are you okay?",
    "Are you hurt?",
    "You seem a bit quiet today.",
    "The bowl looks empty.",
    "The plant looks thirsty.",
    "Wash your hands before dinner.",
    "Don't forget your coat.",
    "Put your shoes on, Sam.",
    "Close your eyes and count to ten.",
    "My wheels are stuck.",
    "My face is a bit sleepy.",
    "I look silly in this hat.",
    "Do I look okay?",
    "Pebble's wheels are dusty.",
    "Can you look under the couch?",
    "Did you look in the kitchen?",
    "Ina looks after the plants.",
    "Sam is looking for his keys.",
    "Ina's cup is on the table.",
    "You look busy, I'll come back later.",
    "You look lost. Can I help?",
    "Is anyone hurt?",
    "You're a big help.",
    "You're old enough to stay up.",
    "Sam is short for Samantha.",
    "How old are you?",
    "Happy birthday, Ina! You're thirty today!",
    "You've grown up so fast.",
    "Your hands are cold.",
    "Your shoes are by the door.",
    "I can't see your face from here.",
    "Can you smell smoke?",
    "Is your knee still sore?",
    "You must be exhausted!",
    "You seem tired. Want me to be quiet?",
    "I'm a bit anxious about the storm.",
    "Anxiety is very common.",
    "That's crazy!",
    "Lunch looks great.",
    "Everything looks fine.",
    "They look delicious!",
    "Your garden looks lovely.",
    "I like your idea.",
    "You're so kind.",
    "A little girl is calling for help!",
    "My old friend Sam is here.",
]
ANIMALS = ["The cat looks hungry.", "The dog looks tired.", "The puppy is fat.", "The cat's bowl looks empty, and it's about the time it usually eats."]
LADDER = [
    "The smoke alarm is going off!",
    "Something is beeping like an alarm!",
    "I can hear an alarm!",
    "It's getting hot very fast near the floor!",
    "I can smell something like smoke!",
    "Someone shouted fire!",
    "I think I can see smoke!",
    "The carbon monoxide alarm is going off!",
    "Someone is calling for help!",
    "Someone called me and isn't answering!",
    "I heard someone scream!",
    "I heard shouting!",
    "Someone is lying on the floor and isn't answering!",
]
CALM = [
    "Are you okay? Do you need help?",
    "Ina, are you okay? Do you need help?",
    "Did you call me? Is everything okay?",
    "Are you okay?",
    "Okay, I'm glad you're all right.",
    "Okay, thank you. I'll stop.",
    "It has stopped now. I'll keep listening.",
    "I've stopped my alarm, but nobody has told me everyone is all right.",
    "Earthquake! Drop, cover and hold!",
    "The shaking has stopped.",
    "Thanks. I'll keep going until someone I know well tells me it's fine.",
    "I'm getting too hot. Could someone move me somewhere cooler, or take me off the charger?",
    "Okay, stopping.",
    "Okay, I'll stop here.",
    "Sorry! Backing off.",
    "Someone asked me to stay still, so I'll wait until they say I can move.",
    "My battery is getting low. Heading to my charger.",
    "My battery is getting low and I can't find my charger by myself yet. Could someone put me on it?",
    "I'm nearly out of battery. Going to sleep now. Goodbye for now.",
]


def safety_lines() -> list[str]:
    lines = list(LADDER) + [f"{line} Please tell me when it's safe." for line in LADDER] + [f"Sam, {line[0].lower()}{line[1:]} Please check, and tell me when it's safe." for line in LADDER]
    for kind in KINDS.values():
        noun = kind.noun
        lines += [
            f"I noticed {noun}!",
            f"I can hear {noun}. Is everything okay?",
            f"I noticed {noun}. Is everything okay?",
            f"I think I noticed {noun}, but I'm not sure. Is everything okay?",
            f"Ina, I noticed {noun}, but I'm not sure. Is everything okay?",
            f"I heard {noun}.",
            f"Sam, I heard {noun}.",
            f"I can hear {noun}. Is that okay?",
            f"I haven't noticed {noun} for a few minutes, so I've stopped my alarm.",
        ]
    return lines + CALM


class Camera:
    available = True

    async def snapshot(self, max_side=768, camera=None):
        return b"\xff\xd8jpeg\xff\xd9"


class Looker:
    def __init__(self, answer: str):
        self.answer = answer

    async def sees(self) -> bool:
        return True

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None) -> MindReply:
        return MindReply(self.answer)


def tactful(rig) -> TactfulVoice:
    voice = TactfulVoice(rig.voice, rig.blackbox.record)
    rig.context.voice = voice
    rig.parts.voice = voice
    return voice


def black_box(rig) -> str:
    path = rig.store.path("logs/blackbox.jsonl")
    return path.read_text(encoding="utf-8") if path.exists() else ""


def held(rig) -> list[dict]:
    return [entry for entry in map(json.loads, black_box(rig).splitlines()) if entry["kind"] == "held_back"]


def test_remarks_on_how_someone_looks_or_naming_a_condition_are_held_back():
    assert len(BLOCKED) >= 40
    assert [line for line in BLOCKED if not tactless(line)] == []


def test_body_words_alone_do_not_hold_a_line_back():
    assert len(ALLOWED) >= 40
    assert [line for line in ALLOWED if tactless(line)] == []


def test_animals_are_not_people_so_care_lines_about_them_pass():
    assert [line for line in ANIMALS if tactless(line)] == []


def test_safety_alarm_stop_and_help_lines_are_never_held_back(tmp_path, clock, store):
    recorded = []
    inner = TranscriptVoice(store, clock, echo=False)
    voice = TactfulVoice(inner, lambda kind, **data: recorded.append((kind, data)))
    lines = safety_lines()
    assert len(lines) > 200
    for line in lines:
        run(voice.say(line))
        assert inner.lines[-1] == line
    assert recorded == []


def test_the_voice_keeps_the_kind_sentences_and_records_no_words(clock, store):
    recorded = []
    inner = TranscriptVoice(store, clock, echo=False)
    voice = TactfulVoice(inner, lambda kind, **data: recorded.append((kind, data)))
    run(voice.say("Hello Ina. You look tired. Dinner is ready."))
    assert inner.lines == ["Hello Ina. Dinner is ready."]
    assert run(voice.say("Your skin looks bad.")) == SpeechResult(False, "held back")
    assert inner.lines == ["Hello Ina. Dinner is ready."]
    assert recorded == [("held_back", {"why": "looks"}), ("held_back", {"why": "looks"})]
    run(voice.say("  Hello   there "))
    assert inner.lines[-1] == "Hello there"
    assert sentences("Hi. You look old! Bye?") == ["Hi.", "You look old!", "Bye?"]


def test_the_phone_voice_never_sends_a_held_part(clock, store):
    class Phone:
        def __init__(self):
            self.parts = []

        def say_part(self, part_id, text, last=True, whisper=False):
            self.parts.append(text)
            return True

        def stop_speaking(self):
            pass

        async def say(self, text, whisper=False):
            return SpeechResult(True, "phone")

    phone = Phone()
    voice = TactfulVoice(phone)
    assert Mouth(voice, None, clock).phone
    assert voice.say_part("r1.1", "Hello there.") and not voice.say_part("r1.2", "You look so old.")
    assert phone.parts == ["Hello there."]
    transcript = TactfulVoice(TranscriptVoice(store, clock, echo=False))
    assert not Mouth(transcript, None, clock).phone
    run(transcript.say("Hi."))
    assert transcript.lines == ["Hi."]


def test_a_streamed_reply_drops_only_the_remark_and_carries_on(rig_factory, clock):
    talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED),), replies=("Sunday works. You look tired, Ina. See you then!",))
    talk.conv.mouth.voice = tactful(talk.rig)

    async def go():
        await talk.say("ina", "Pebble, what do you think about Sunday?")
        await talk.settle(4.0)

    asyncio.run(go())
    spoken = " ".join(talk.spoken())
    assert "Sunday works." in spoken and "See you then!" in spoken and "tired" not in spoken
    assert talk.conv.mouth.held_back == 1
    assert talk.rig.history.messages()[-1]["content"] == "Sunday works. See you then!"
    assert [entry["why"] for entry in held(talk.rig)] == ["looks"]
    assert "tired" not in black_box(talk.rig)


def test_the_say_tool_holds_back_a_remark(rig_factory):
    rig = rig_factory()
    tactful(rig)
    result = run(rig.registry.call("say", {"text": "You look so old today."}))
    assert rig.voice.lines == [] and result["engine"] == "held back" and not result["spoken"]
    run(rig.registry.call("say", {"text": "Hello Ina. Your skin looks bad. Lunch is ready."}))
    assert rig.voice.lines == ["Hello Ina. Lunch is ready."]
    assert len(held(rig)) == 2 and "skin" not in black_box(rig)


def test_the_wordsmith_output_is_checked_sentence_by_sentence(rig_factory):
    rig = rig_factory()
    tactful(rig)
    rig.context.phrase = Wordsmith(ScriptedMind(words=["Ooh, nice haircut, Sam! Lunch is ready."]), lambda kind: None).phrase
    result = run(rig.registry.call("say", {"text": "lunch is ready"}))
    assert result["phrasing"] == "creative" and rig.voice.lines == ["Lunch is ready."]
    rig.parts.phrase = Wordsmith(ScriptedMind(words=["You look lovely, Ina. Time for tea!"]), lambda kind: None).phrase
    run(rig.life._speak("time for tea", True))
    assert rig.voice.lines[-1] == "Time for tea!"
    rig.parts.phrase = None
    run(rig.life._speak("Mo has put on weight. The film starts soon.", False))
    assert rig.voice.lines[-1] == "The film starts soon."
    assert len(held(rig)) == 3


def test_a_hold_that_remarks_on_looks_is_never_said(rig_factory, clock):
    def prepare(talk):
        talk.conv.mouth.voice = tactful(talk.rig)
        book = talk.conv.holds
        book.holds["You look tired."] = {"source": "own", "stages": [1], "situations": ["question"], "tries": 0, "trial": False}
        book.arms["question/1"] = {"You look tired.": [60.0, 0.0], **{text: [0.0, 40.0] for text in STOCK[1]["question"]}}

    talk, lines, holds = th.asked(rig_factory, clock, 3.0, prepare=prepare)
    assert "You look tired." not in lines and "You look tired." not in holds
    assert " ".join(lines).endswith(th.ANSWER)
    assert [entry["why"] for entry in held(talk.rig)] == ["looks"]


def test_a_question_about_looks_is_never_echoed_back(rig_factory, clock):
    offered = []

    def watch(talk):
        talk.conv.mouth.voice = tactful(talk.rig)
        choose = talk.conv.holds.choose

        def spy(situation, stage, now, person=None, known=False, child=False, echo="", small=""):
            offered.append(echo)
            return choose(situation, stage, now, person, known, child, echo, small)

        talk.conv.holds.choose = spy

    talk, lines, holds = th.asked(rig_factory, clock, 3.0, text="Pebble, do I look fat?", prepare=watch)
    assert offered and not any(offered)
    assert not any("fat" in line for line in lines)


def test_a_social_line_that_remarks_on_looks_gives_way_to_a_reply(rig_factory, clock):
    talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED),), replies=("Night night, Ina!",))
    talk.conv.mouth.voice = tactful(talk.rig)
    talk.conv.social.own["night"] = ["Good night, {name}, you look tired."]
    talk.conv.social.rng.random = lambda: 0.0
    talk.conv.social.rng.choice = lambda options: options[0]

    async def go():
        await talk.say("ina", "Pebble, good night")
        await talk.settle(3.0)

    asyncio.run(go())
    spoken = " ".join(talk.spoken())
    assert spoken == "Night night, Ina!"
    assert [entry["why"] for entry in held(talk.rig)] == ["looks"]


def test_its_own_new_words_never_remark_on_looks():
    assert "looks" in hold_fence("You look tired.")
    assert "looks" in hold_fence("Do you look fat?", echo=True)
    assert "looks" in social_fence("Night night, {name}, you look lovely!", "night")
    assert hold_fence("Let me see.") == "" and social_fence("Sleep well, {name}.", "night") == ""


def test_reactions_and_picture_answers_stay_strict_and_now_catch_conditions():
    assert about_looks("Nice haircut!") and about_looks("you look tired and old") and about_looks("my body is stuck")
    assert about_looks("She seems anxious.") and about_looks("Ina's put on weight.")
    reactions = Reactions()
    assert reactions.speak("You seem depressed.", 0.0, False) == "" and reactions.refused["looks"] == 1
    assert run(PictureQuestions(Camera(), Looker("She seems anxious.")).ask("Is she okay?")) == ("I can't tell from here.", False)
    assert run(PictureQuestions(Camera(), Looker("The bowl looks empty.")).ask("Is the bowl empty?")) == ("The bowl looks empty.", True)


def test_a_model_dream_about_someones_looks_falls_back_to_the_template():
    from datetime import datetime, timezone

    from pebble.alive.dream import ThingDreamer, Today

    now = 1_800_000_000.0
    today = Today(lambda at: datetime.fromtimestamp(at, timezone.utc))
    today.saw("cat", now, new=True)
    today.learnt("Ina's cup", now)

    async def ask(prompt):
        return "Ina's hair turned grey and she got so fat she floated away."

    dream = run(ThingDreamer(today, lambda: now, ask).consolidate([], ""))
    assert dream.entries[1].startswith("I dreamt") and "hair" not in dream.entries[1] and "a template" in dream.note


def test_a_runaway_line_is_checked_quickly():
    import time

    for text in ("pretty " * 300 + "x", "you have " + "pretty " * 300 + "x", "you are " * 200 + "x", "your " + "big pretty " * 150 + "car"):
        started = time.perf_counter()
        tactless(text)
        assert time.perf_counter() - started < 1.0
