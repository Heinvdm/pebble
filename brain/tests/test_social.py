import asyncio
import random

from conftest import run

import test_conversation as tc
from pebble.conversation.holds import norm
from pebble.conversation.social import SOCIAL, STOCK, Social, fence, kind_of
from pebble.people.trust import TRUSTED


def test_social_talk_is_recognised_in_plain_code():
    assert kind_of("Pebble, good night") == "night"
    assert kind_of("hi pebble") == "hello"
    assert kind_of("thank you") == "thanks"
    assert kind_of("Pebble, how are you?") == "how"
    assert kind_of("good boy pebble") == "praise"
    assert kind_of("see you later") == "bye"
    assert kind_of("how are you getting on with the drawing") == ""
    assert kind_of("thanks for nothing you broke my mug") == ""
    assert kind_of("Pebble") == ""


def test_lines_greet_by_name_vary_and_follow_the_mood():
    social = Social(rng=random.Random(2))
    said = [social.line("good night", "Ina", 0.5, 21, index * 120.0) for index in range(30)]
    assert all("Ina" in line or line == "Night night!" for line in said)
    assert all(norm(a) != norm(b) for a, b in zip(said, said[1:]))
    for start in range(0, len(said) - 5):
        window = said[start : start + 5]
        assert max(window.count(line) for line in window) <= 3
    assert social.line("how are you", "Ina", 0.6, 12, 0.0) in STOCK["how_good"]
    assert social.line("how are you", "Ina", -0.6, 12, 100.0) in STOCK["how_low"]
    assert social.line("hello", "Ina", 0.0, 8, 200.0).startswith(("Good morning", "Morning"))
    stranger = social.line("hello", None, 0.0, 14, 300.0)
    assert stranger in ("Hi!", "Hello!", "Hey!")
    assert social.line("what's the capital of france", "Ina", 0.0, 14, 400.0) == ""


def test_the_fence_keeps_social_lines_short_plain_and_personal():
    for slot, lines in STOCK.items():
        for line in lines:
            assert fence(line, slot) == "", line
    assert "too long" in fence("Good night to you and everyone you love so very much", "night")
    assert fence("You're welcome, it's 5 o'clock", "thanks")
    assert "back" in fence("You're welcome. Why?", "thanks")
    assert "unkind" in fence("Whatever, {name}.", "bye")


def test_new_social_lines_are_written_by_the_wordsmith_through_the_fence(clock):
    from pebble.mind.wordsmith import Phrased

    diary = []
    social = Social(rng=random.Random(1), clock=clock)
    social.rng.choice = lambda options: "night" if "night" in options else options[0]
    social.diary = diary.append
    offers = iter(["Night night, Ina, sleep tight!", "Sleep well, Ina!", "Good night, everyone!", "Nighty night, Ina!"])

    async def phrase(seed, kind):
        return Phrased(next(offers), "creative")

    now = clock.now()
    assert run(social.write(phrase, now)) == "Night night, {name}, sleep tight!"
    assert diary and "started saying" in diary[-1] and "Ina" not in diary[-1]
    assert run(social.write(phrase, now + 10.0)) is None
    assert run(social.write(phrase, now + 2 * 86400.0)) is None
    assert run(social.write(phrase, now + 4 * 86400.0)) is None
    assert run(social.write(phrase, now + 6 * 86400.0)) == "Nighty night, {name}!"
    assert social.own["night"] == ["Night night, {name}, sleep tight!", "Nighty night, {name}!"]
    assert all("Ina" not in line for lines in social.own.values() for line in lines)


def test_good_night_gets_an_instant_line_and_no_model_call(rig_factory, clock):
    talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED),))

    async def go():
        await talk.say("ina", "Pebble, good night")
        await talk.settle(2.0)

    asyncio.run(go())
    spoken = talk.spoken()
    assert len(spoken) == 1 and ("Ina" in spoken[0] or spoken[0] == "Night night!")
    assert not any(r["purpose"] == "reply" for r in talk.rig.mind.requests)
    assert talk.conv.stats.as_dict()["first_word_s_max"] <= 0.75


def test_social_lines_are_kept_in_the_self(rig_factory, clock):
    talk = tc.Talk(rig_factory, clock)
    talk.conv.social.own["thanks"] = ["Happy to help."]
    talk.conv.social.dirty = True
    talk.conv.social.save()
    again = Social(talk.rig.store)
    assert again.own["thanks"] == ["Happy to help."]
    assert talk.rig.store.read(SOCIAL)["own"]["thanks"] == ["Happy to help."]


def test_visitors_mode_keeps_no_overheard_facts_and_enrols_no_voices(rig_factory, clock):
    from types import SimpleNamespace

    from pebble.people.trust import FRIEND

    def overheard(visiting: bool):
        talk = tc.Talk(rig_factory, clock, people=(("Ina", TRUSTED), ("Sam", FRIEND)))
        talk.rig.life.company.visitors = SimpleNamespace(on=visiting)
        asked = []
        if talk.conv.speakers is not None:
            talk.conv.speakers.enrol_target = lambda *args: asked.append(args) or None

        async def go():
            await talk.say("ina", "i have my driving test on friday so saturday is perfect")
            await talk.say("zed", "Pebble, hello there")
            await talk.settle(2.0)

        asyncio.run(go())
        return talk.conv.overheard.facts, asked

    facts, asked = overheard(False)
    assert facts and asked
    facts, asked = overheard(True)
    assert not facts and not asked

