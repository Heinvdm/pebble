import functools

import pytest

np = pytest.importorskip("numpy")

from pebble.hearing import synth
from pebble.hearing.audio import RATE, Block, to_samples
from pebble.hearing.events import LocalModel
from pebble.hearing.taught import PROFILE_SURE, Frame, Profiler, TaughtSounds, announcement, join, key_for, profile, thing_of
from pebble.hearing.yamnet import Yamnet

needs_model = pytest.mark.skipif(not Yamnet.available(), reason="YAMNet is not here")


def tune(notes, on=0.25, off=0.08, level=-22.0):
    out = []
    for freq in notes:
        out += synth.gated([(on, True)], freq, level, harmonics=((2, 0.3), (3, 0.15)))
        out += synth.silence(off)
    return out


WASHER = (1047, 1319, 1568, 2093, 1568, 1319, 1047, 1319)
DRYER = (784, 659, 523, 659, 784, 784, 784)


@functools.lru_cache(maxsize=None)
def yamnet():
    return Yamnet.load(threads=1)


def frames_of(values, with_model=True, noise_db=None, seed=1):
    values = list(values)
    if noise_db is not None:
        values = synth.mix(values, synth.noise(len(values) / RATE + 0.1, noise_db, "pink", seed))
    samples = to_samples(values + synth.silence(1.0))
    profiler = Profiler()
    model = LocalModel(yamnet()) if with_model else None
    profiles, rows, vectors = [], [], []
    step = RATE // 4
    for start in range(0, len(samples), step):
        block = Block(samples[start : start + step], (start + step) / RATE)
        profiles += profiler.feed(block)
        if model is not None:
            rows += model.feed(block)
            vectors += model.take_vectors()
    return join(profiles, rows, vectors, np)


def test_announcements_read_naturally():
    assert announcement("the washing machine finishing") == "The washing machine's finished."
    assert announcement("dryer done") == "The dryer's finished."
    assert announcement("the bread maker ready") == "The bread maker's ready."
    assert announcement("the gate") == "That sounded like the gate."
    assert thing_of("the washing machine finishing") == "the washing machine"
    assert key_for("The washing machine finishing") == key_for("the washing machine finished") == "the-washing-machine"


def test_a_quiet_window_has_no_profile():
    shaped, loud = profile(np.zeros(15600, np.float32), np)
    assert shaped is None and loud < -100


@needs_model
def test_two_teachings_are_enough_and_another_tune_does_not_match():
    sounds = TaughtSounds()
    first, outcome = sounds.teach("the washing machine finishing", frames_of(tune(WASHER)), "p1", 10.0)
    assert outcome == "learning" and not first.trusted
    _, outcome = sounds.teach("the washing machine finishing", frames_of(tune(WASHER, level=-28.0), noise_db=-58.0), "p1", 20.0)
    assert outcome == "trusted" and len(sounds) == 1
    heard = sounds.match(frames_of(tune(WASHER, level=-32.0), noise_db=-52.0, seed=4))
    assert [m.key for m in heard] == ["the-washing-machine"]
    assert sounds.match(frames_of(tune(DRYER))) == []
    assert sounds.match(frames_of(tune((2000,) * 6, on=0.15, off=0.15))) == []


@needs_model
def test_speech_music_and_room_noise_never_match():
    sounds = TaughtSounds()
    sounds.teach("the washing machine finishing", frames_of(tune(WASHER)), "p1", 10.0)
    sounds.teach("the washing machine finishing", frames_of(tune(WASHER, level=-26.0)), "p1", 20.0)
    for values in (synth.speechlike(8.0, -24.0, seed=5), synth.music(8.0, -25.0, seed=3), synth.noise(8.0, -60.0, "pink", 9)):
        assert sounds.match(frames_of(values)) == []


@needs_model
def test_the_same_sound_is_not_announced_twice_in_two_minutes():
    sounds = TaughtSounds()
    sounds.teach("dryer done", frames_of(tune(DRYER)), None, 0.0)
    sounds.teach("dryer done", frames_of(tune(DRYER, level=-27.0)), None, 1.0)
    frames = frames_of(tune(DRYER))
    assert len(sounds.match(frames)) == 1
    later = [Frame(f.at + 30.0, f.profile, f.kind, f.kind_name, f.level_db) for f in frames]
    assert sounds.match(later) == []
    much_later = [Frame(f.at + 200.0, f.profile, f.kind, f.kind_name, f.level_db) for f in frames]
    assert len(sounds.match(much_later)) == 1


@needs_model
def test_two_machines_with_the_same_tune_are_told_as_unsure():
    sounds = TaughtSounds()
    for name in ("the washing machine finishing", "the dishwasher finishing"):
        sounds.teach(name, frames_of(tune(WASHER)), None, 0.0)
        sounds.teach(name, frames_of(tune(WASHER, level=-26.0)), None, 1.0)
    heard = sounds.match(frames_of(tune(WASHER, level=-24.0)))
    assert len(heard) == 1 and heard[0].others


@needs_model
def test_saved_and_read_back_it_still_matches_and_forgetting_deletes_the_numbers():
    sounds = TaughtSounds()
    sounds.teach("the gate", frames_of(tune(DRYER)), "p2", 0.0)
    sounds.teach("the gate", frames_of(tune(DRYER, level=-27.0)), "p2", 1.0)
    data = sounds.to_dict()
    back = TaughtSounds(data)
    assert len(back.match(frames_of(tune(DRYER)))) == 1
    back.forget_person("p2")
    assert back.sounds["the-gate"].by is None
    assert back.forget("the-gate") and len(back) == 0 and back.to_dict()["sounds"] == []


def test_without_the_sound_model_the_pitch_alone_must_be_very_close():
    sounds = TaughtSounds()
    sounds.teach("the gate", frames_of(tune(DRYER), with_model=False), None, 0.0)
    sounds.teach("the gate", frames_of(tune(DRYER), with_model=False), None, 1.0)
    assert len(sounds.match(frames_of(tune(DRYER), with_model=False))) == 1
    assert sounds.match(frames_of(tune(WASHER), with_model=False)) == []
    assert PROFILE_SURE > 0.9
