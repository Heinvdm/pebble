import pytest

from pebble.hearing import synth
from pebble.hearing.alarm import AlarmDetector
from pebble.hearing.audio import RATE, Block, to_samples
from pebble.hearing.fetch import MODELS
from pebble.hearing.sources import read_wav

SAMPLES = MODELS / "samples"


def clip(name):
    path = SAMPLES / f"{name}.wav"
    if not path.exists():
        pytest.skip(f"{path.name} is not here (python -m pebble.hearing.fetch --samples)")
    return read_wav(path)


def detect(values):
    detector = AlarmDetector("plain")
    samples = to_samples(values)
    heard = []
    for start in range(0, len(samples), 4000):
        part = samples[start : start + 4000]
        heard.extend(detector.feed(Block(part, (start + len(part)) / RATE)))
    return heard


def sure(heard, kind="smoke_alarm"):
    return [h for h in heard if h.kind == kind and h.confidence >= 0.9]


def test_a_real_smoke_alarm_recording():
    values = clip("smoke_alarm_t3")
    heard = sure(detect(values))
    assert heard and heard[0].at < 11.0 and abs(heard[0].freq - 3350) < 50


def test_a_real_smoke_alarm_under_speech_and_through_a_wall():
    values = clip("smoke_alarm_t3")
    seconds = len(values) / RATE
    assert sure(detect(synth.mix(synth.gain(values, -12), synth.speechlike(seconds, -25, seed=3))))
    assert sure(detect(synth.mix(synth.muffle(values, wall_db=-20), synth.noise(seconds, -60, "pink", 2))))


@pytest.mark.parametrize("name", ["smoke_alarm", "speech", "dog_barking", "glass_breaking", "baby_crying", "tap_water"])
def test_other_real_sounds_are_not_the_alarm_pattern(name):
    assert sure(detect(clip(name))) == [] and sure(detect(clip(name)), "co_alarm") == []


def test_the_sound_model_on_real_recordings():
    yamnet = pytest.importorskip("pebble.hearing.yamnet")
    if not yamnet.Yamnet.available():
        pytest.skip("the sound model is not here")
    from pebble.hearing.events import LocalModel, SoundEvents

    model = yamnet.Yamnet.load(threads=1)
    found = {}
    for name in ("smoke_alarm_t3", "glass_breaking", "speech"):
        local = LocalModel(model)
        events = SoundEvents(local.labels)
        samples = to_samples(clip(name))
        heard = []
        for start in range(0, len(samples), 8000):
            part = samples[start : start + 8000]
            heard += events.feed(local.feed(Block(part, (start + len(part)) / RATE)))
        found[name] = {h.event for h in heard}
    assert "alarm_sound" in found["smoke_alarm_t3"]
    assert "glass" in found["glass_breaking"]
    assert found["speech"] == set()
