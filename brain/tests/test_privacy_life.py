import asyncio
import json

from conftest import run

from pebble.life.states import LifeState
from pebble.people.fake import fake_print
from pebble.privacy.core import OBSERVED, WHY_ANSWER
from pebble.seams.voice import TRANSCRIPT


def awake(rig):
    for _ in range(2):
        rig.clock.advance(1)
        run(rig.life.tick(1))
    assert rig.life.state is LifeState.ACTIVE


def spoken(rig):
    path = rig.store.path(TRANSCRIPT)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def hear(rig, text, key="ina", addressed=None):
    async def go():
        heard = rig.life.hear(text, fake_print(key, "voice"), addressed=addressed)
        task = rig.life.considering
        if task is not None:
            await task
        return heard

    return run(go())


def test_an_overheard_privacy_line_is_kept_silently(rig_factory):
    rig = rig_factory()
    awake(rig)
    hear(rig, "hello")
    before = len(spoken(rig))
    hear(rig, "hang on, I'm getting changed", addressed=False)
    privacy = rig.life.privacy
    assert privacy.active() and len(spoken(rig)) == before
    assert rig.life.situation().privacy and rig.life.beings_near()
    assert privacy.observation() == OBSERVED


def test_asked_aloud_it_says_at_most_a_soft_okay_and_explains_only_when_asked(rig_factory):
    rig = rig_factory()
    awake(rig)
    hear(rig, "Pebble, don't look", addressed=True)
    lines = spoken(rig)
    assert lines[-1]["text"] == "Okay." and lines[-1]["whisper"]
    hear(rig, "Pebble, why did you look away?", addressed=True)
    assert spoken(rig)[-1]["text"] == WHY_ANSWER
    hear(rig, "you can look now", addressed=True)
    assert not rig.life.privacy.active()
    assert rig.life.privacy.observation() == ""


def test_a_childs_dont_look_works_like_anyones(rig_factory):
    rig = rig_factory()
    awake(rig)
    hear(rig, "hello", key="sam")
    child = rig.life.company.book.get(hear(rig, "hi", key="sam").person_id)
    child.relationship = "child"
    hear(rig, "no peeking, I'm changing", key="sam", addressed=True)
    assert rig.life.privacy.active()
    hear(rig, "hello", key="ina")
    hear(rig, "you can look now", key="ina", addressed=True)
    assert rig.life.privacy.active()
    hear(rig, "you can look now", key="sam", addressed=True)
    assert not rig.life.privacy.active()


def test_the_why_question_is_left_alone_when_it_never_looked_away(rig_factory):
    rig = rig_factory()
    awake(rig)
    assert rig.life.privacy.heard(type("Heard", (), {"text": "why did you look away?", "person_id": None})(), True) is None


def test_the_time_runs_out_quietly(rig_factory):
    rig = rig_factory()
    awake(rig)
    hear(rig, "Pebble, don't look for a minute", addressed=True)
    privacy = rig.life.privacy
    assert privacy.active()
    said = len(spoken(rig))
    rig.clock.advance(61.0)
    assert not privacy.active() and len(spoken(rig)) == said
