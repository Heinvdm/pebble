import array
import functools
import wave

import pytest

from pebble.hearing import synth
from pebble.hearing.alarm import AlarmDetector, PlainEngine, engine_for
from pebble.hearing.audio import RATE, Block, pcm_to_samples, samples_to_pcm, to_samples
from pebble.hearing.level import LevelMeter
from pebble.hearing.service import Hearing
from pebble.hearing.sources import AndroidTapSource, ArraySource, MixSource, WavSource, read_wav


def detect(signal, engine="plain", chunk_s=0.25):
    detector = AlarmDetector(engine)
    samples = to_samples(signal)
    step = int(chunk_s * RATE)
    heard = []
    for start in range(0, len(samples), step):
        part = samples[start : start + step]
        heard.extend(detector.feed(Block(part, (start + len(part)) / RATE)))
    return heard, detector


def best(heard, kind):
    found = [h.confidence for h in heard if h.kind == kind]
    return max(found, default=0.0)


@functools.lru_cache(maxsize=None)
def speech(seconds, level, seed):
    return tuple(synth.speechlike(seconds, level, seed=seed))


@functools.lru_cache(maxsize=None)
def music(seconds, level, seed):
    return tuple(synth.music(seconds, level, seed=seed))


@pytest.mark.parametrize("engine", ["plain", "numpy"])
def test_t3_is_heard_and_grows_sure(engine):
    if engine == "numpy":
        pytest.importorskip("numpy")
    heard, detector = detect(synth.t3(3), engine)
    assert detector.engine == engine
    smoke = [h for h in heard if h.kind == "smoke_alarm"]
    assert [round(h.confidence, 2) for h in smoke] == [0.5, 0.9, 0.97]
    assert all(abs(h.freq - 3100) < 60 for h in smoke)
    assert smoke[1].at < 7.5


@pytest.mark.parametrize("level", [-15.0, -40.0, -65.0])
def test_t3_level_does_not_matter(level):
    heard, _ = detect(synth.t3(2, level_db=level))
    assert best(heard, "smoke_alarm") >= 0.9


@pytest.mark.parametrize("freq", [2500.0, 3000.0, 3500.0, 4000.0, 4500.0])
def test_t3_anywhere_in_the_band(freq):
    heard, _ = detect(synth.t3(2, freq=freq))
    assert best(heard, "smoke_alarm") >= 0.9


def test_t3_drifting_in_frequency_still_counts():
    heard, _ = detect(synth.t3(4, freq=2550.0, drift_hz_s=110.0))
    assert best(heard, "smoke_alarm") >= 0.9
    heard, _ = detect(synth.t3(3, freq=4450.0, drift_hz_s=-80.0))
    assert best(heard, "smoke_alarm") >= 0.9


def test_t3_with_loose_timing():
    heard, _ = detect(synth.t3(3, on_s=0.45, off_s=0.55, pause_s=1.6))
    assert best(heard, "smoke_alarm") >= 0.9
    heard, _ = detect(synth.t3(3, on_s=0.55, off_s=0.45, pause_s=1.4))
    assert best(heard, "smoke_alarm") >= 0.9


def test_t4_carbon_monoxide():
    heard, _ = detect(synth.t4(3))
    assert best(heard, "co_alarm") >= 0.9
    assert best(heard, "smoke_alarm") == 0.0


def test_t3_under_speech():
    signal = synth.mix(synth.t3(3, level_db=-35), list(speech(13.0, -25.0, 1)))
    heard, _ = detect(signal)
    assert best(heard, "smoke_alarm") >= 0.9


def test_t3_in_another_room_under_speech():
    signal = synth.mix(synth.muffle(synth.t3(4, level_db=-20), wall_db=-20), list(speech(17.0, -30.0, 2)))
    heard, _ = detect(signal)
    assert best(heard, "smoke_alarm") >= 0.9


def test_t3_under_noise():
    signal = synth.mix(synth.t3(3, level_db=-35), synth.noise(13, -30, "pink", 3))
    heard, _ = detect(signal)
    assert best(heard, "smoke_alarm") >= 0.9


def test_t4_under_speech():
    signal = synth.mix(synth.t4(3, level_db=-30), list(speech(18.0, -32.0, 9)))
    heard, _ = detect(signal)
    assert best(heard, "co_alarm") >= 0.9


@pytest.mark.parametrize("seed", [4, 5, 6])
def test_no_alarm_from_speech(seed):
    heard, _ = detect(list(speech(25.0, -20.0, seed)))
    assert heard == []


def test_no_alarm_from_singing():
    heard, _ = detect(synth.speechlike(25, -20, seed=7, pitch=300, sing=True))
    assert heard == []


@pytest.mark.parametrize("seed", [6, 8])
def test_no_alarm_from_music(seed):
    heard, _ = detect(list(music(25.0, -20.0, seed)))
    assert heard == []


def test_no_alarm_from_staccato_music():
    heard, _ = detect(synth.music(25, -20, seed=11, staccato=True))
    assert best(heard, "smoke_alarm") < 0.9 and best(heard, "co_alarm") < 0.9


def test_no_alarm_from_television_like_mix():
    signal = synth.mix(list(speech(25.0, -24.0, 12)), list(music(25.0, -30.0, 13)), synth.noise(25, -50, "pink", 14))
    heard, _ = detect(signal)
    assert heard == []


def test_microwave_is_only_a_maybe():
    heard, _ = detect(synth.beeps(3, 0.5, 0.5, 3000))
    assert best(heard, "smoke_alarm") == 0.5


def test_microwave_reminder_a_minute_later_is_still_a_maybe():
    once = synth.beeps(3, 0.5, 0.5, 3000)
    signal = once + synth.silence(60.0 - len(once) / RATE) + once
    heard, _ = detect(signal)
    assert best(heard, "smoke_alarm") == 0.5


def test_oven_timer_beeping_steadily_is_a_low_maybe():
    heard, _ = detect(synth.beeps(16, 0.5, 0.5, 3200))
    assert best(heard, "smoke_alarm") == 0.0
    assert 0.0 < best(heard, "alarm_beeping") < 0.5


def test_low_pitched_alarm_is_out_of_band():
    heard, _ = detect(synth.t3(3, freq=520.0))
    assert heard == []


def test_four_quick_beeps_with_a_short_pause_are_not_co():
    heard, _ = detect(synth.t4(4, pause_s=1.2))
    assert best(heard, "co_alarm") == 0.0


def test_engines_agree():
    pytest.importorskip("numpy")
    frames = [[float(v) for v in to_samples(synth.t3(1)[i : i + 160])] for i in range(0, 16000, 320)]
    plain = PlainEngine().powers(frames)
    fast = engine_for("numpy").powers(frames)
    for a, b in zip(plain, fast):
        for x, y in zip(a, b):
            assert abs(x - y) <= 1e-9 + 1e-6 * abs(x)


def test_a_gap_in_the_audio_does_not_join_beeps():
    detector = AlarmDetector("plain")
    first = to_samples(synth.t3(1)[: int(2.0 * RATE)])
    detector.feed(Block(first, 2.0))
    later = to_samples(synth.t3(1)[int(2.0 * RATE) :])
    detector.feed(Block(later, 30.0, skipped=RATE * 20))
    assert detector.last_heard("smoke_alarm") is None


def test_pcm_round_trip():
    samples = array.array("h", [0, 1, -1, 32767, -32768, 1234])
    assert list(pcm_to_samples(samples_to_pcm(samples))) == list(samples)


def test_wav_source_reads_and_resamples(tmp_path):
    path = tmp_path / "beep.wav"
    tone = to_samples(synth.t3(2, freq=3000))
    stereo = array.array("h")
    for value in tone[::2]:
        stereo.extend((value, value))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(samples_to_pcm(stereo))
    values = read_wav(path)
    assert abs(len(values) - len(tone)) <= 2
    source = WavSource(path)
    source.start()
    detector = AlarmDetector("plain")
    heard = []
    while True:
        block = source.read(0.5)
        if block is None:
            break
        heard.extend(detector.feed(block))
    assert source.done()
    assert best(heard, "smoke_alarm") >= 0.0


def test_paced_source_gives_only_what_time_allows():
    now = [100.0]
    source = ArraySource(synth.t3(1), monotonic=lambda: now[0])
    source.start()
    assert source.read(1.0) is None
    now[0] += 0.5
    block = source.read(1.0)
    assert len(block.samples) == RATE // 2
    assert block.end == pytest.approx(100.5)


def test_mix_source_plays_clips_in_time():
    now = [10.0]
    mix = MixSource(lambda: now[0])
    mix.start()
    mix.play("alarm", synth.t3(1), loop=True)
    detector = AlarmDetector("plain")
    heard = []
    for _ in range(40):
        now[0] += 0.25
        heard.extend(detector.feed(mix.read(1.0)))
    assert best(heard, "smoke_alarm") >= 0.9
    mix.stop_clip("alarm")
    now[0] += 0.5
    block = mix.read(1.0)
    assert max(abs(v) for v in block.samples) == 0


class FakeTap:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.skipped = 0
        self.started = False
        self.speaking = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def read(self, max_seconds=1.0):
        return self.chunks.pop(0) if self.chunks else b""

    def info(self):
        return {"running": True, "speaking": self.speaking}


def test_android_tap_source_turns_bytes_into_blocks():
    pcm = samples_to_pcm(to_samples(synth.t3(1)[:8000]))
    tap = FakeTap([pcm[:8000], pcm[8000:]])
    source = AndroidTapSource(tap, monotonic=lambda: 5.0)
    source.start()
    assert tap.started
    first = source.read(1.0)
    assert len(first.samples) == 4000 and first.end == 5.0 and first.skipped == 0
    tap.skipped = 1600
    tap.speaking = True
    second = source.read(1.0)
    assert second.skipped == 1600 and second.own_voice
    assert source.read(1.0) is None


def test_level_meter_tells_a_shout_from_talk():
    meter = LevelMeter()
    quiet = to_samples(synth.noise(20, -70, "pink", 1))
    meter.feed(Block(quiet, 20.0))
    talk = to_samples(synth.speechlike(2, -45, seed=2))
    meter.feed(Block(talk, 22.0))
    assert not meter.recent(22.0, 2.0).shouted
    shout = to_samples(synth.speechlike(1.5, -18, seed=3))
    meter.feed(Block(shout, 23.5))
    loud = meter.recent(23.5, 2.0)
    assert loud.shouted and loud.loud


def test_hearing_service_turns_beeps_into_notices():
    source = ArraySource(synth.mix(synth.t3(3, level_db=-30), synth.noise(13, -55, "pink", 2)))
    hearing = Hearing(source, now=lambda: 1234.0, detector=AlarmDetector("plain"))
    hearing.start()
    notices = hearing.pump()
    smoke = [n for n in notices if n.kind == "smoke_alarm"]
    assert [round(n.confidence, 2) for n in smoke] == [0.5, 0.9, 0.97]
    assert smoke[0].source == "beeps" and smoke[0].at == 1234.0 and smoke[0].detail["pattern"] == "T3"
    assert "smoke alarm" in smoke[0].text
    status = hearing.status()
    assert status["heard_s"] > 12 and status["cpu_ms_per_s"] is not None


def test_muted_hearing_ignores_its_own_alarm():
    source = ArraySource(synth.t3(3))
    hearing = Hearing(source, detector=AlarmDetector("plain"))
    hearing.start()
    hearing.mute(True, 0.0)
    assert hearing.pump() == []


class ScoresModel:
    labels = ["Laughter", "Speech"]
    window = 1600

    def __init__(self):
        self.calls = 0

    def feed(self, block):
        self.calls += 1
        return [(block.end, [0.9, 0.1])]

    def gap(self):
        return None


def test_taps_see_the_sound_models_rows_and_a_bad_tap_is_harmless():
    seen = []
    model = ScoresModel()
    hearing = Hearing(ArraySource(synth.noise(2, -60, "pink", 1)), detector=AlarmDetector("plain"), model=model)
    hearing.taps.append(lambda rows: 1 / 0)
    hearing.taps.append(seen.extend)
    hearing.start()
    hearing.pump()
    assert seen and seen[0][1] == [0.9, 0.1] and len(seen) == model.calls


def test_talk_level_needs_some_talk_first():
    hearing = Hearing(ArraySource(synth.noise(5, -70, "pink", 1) + synth.speechlike(5, -35, seed=2)), detector=AlarmDetector("plain"))
    assert hearing.talk_db() is None
    hearing.start()
    hearing.pump()
    assert -45.0 < hearing.talk_db() < -25.0


def test_block_taps_get_every_block_and_know_when_muted():
    blocks = []
    hearing = Hearing(ArraySource(synth.noise(3, -60, "pink", 1)), detector=AlarmDetector("plain"))
    hearing.block_taps.append(lambda block, muted: 1 / 0)
    hearing.block_taps.append(lambda block, muted: blocks.append((len(block.samples), muted)))
    hearing.start()
    hearing.mute(True, 0.0)
    hearing.pump()
    assert blocks and all(muted for _, muted in blocks) and sum(n for n, _ in blocks) == 3 * 16000
