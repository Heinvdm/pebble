import array

from pebble.hearing import synth
from pebble.hearing.alarm import AlarmDetector
from pebble.hearing.audio import RATE, Block, to_samples
from pebble.hearing.chirp import REPEAT, SINGLE, STEADY_SCORE, ChirpWatch
from pebble.hearing.service import Hearing
from pebble.hearing.sources import ArraySource

CHUNK_S = 0.5


def chirp(level_db=-30.0, freq=3200.0, on_s=0.08):
    return synth.gated([(on_s, True)], freq, level_db, harmonics=((2, 0.08),))


def timeline(seconds, sounds):
    total = int(seconds * RATE)
    out = array.array("h", bytes(2 * total))
    for at, values in sounds:
        start = int(at * RATE)
        samples = to_samples(values)
        for i, value in enumerate(samples):
            if start + i < total:
                out[start + i] = max(-32768, min(32767, out[start + i] + value))
    return out


def feed(detector, samples, chunk_s=CHUNK_S):
    step = int(chunk_s * RATE)
    found = []
    for start in range(0, len(samples), step):
        part = samples[start : start + step]
        detector.feed(Block(part, (start + len(part)) / RATE))
        found.extend(detector.take_chirps())
    return found


def test_a_chirp_every_40_seconds_builds_up_to_steady():
    sounds = [(5.0, chirp()), (45.0, chirp()), (85.0, chirp())]
    found = feed(AlarmDetector(), timeline(90.0, sounds))
    assert [h.score for h in found] == [SINGLE, REPEAT, STEADY_SCORE]
    assert found[0].period_s is None and [round(h.period_s) for h in found[1:]] == [40, 40]
    assert all(abs(h.freq_hz - 3200.0) < 60.0 for h in found)
    assert [round(h.onset) for h in found] == [5, 45, 85]


def test_a_missed_chirp_still_counts_the_rhythm():
    sounds = [(2.0, chirp()), (37.0, chirp()), (107.0, chirp()), (142.0, chirp())]
    found = feed(AlarmDetector(), timeline(146.0, sounds))
    assert [h.score for h in found] == [SINGLE, REPEAT, STEADY_SCORE, STEADY_SCORE]
    assert round(found[2].unit_s) == 35


def test_alarms_and_appliance_beeps_are_not_chirps():
    sounds = [
        (1.0, synth.t3(3, freq=3100.0)),
        (20.0, synth.t4(2, freq=3300.0)),
        (40.0, synth.beeps(3, 0.15, 0.2, 2900.0)),
        (60.0, synth.beeps(10, 0.1, 0.5, 3000.0)),
    ]
    assert feed(AlarmDetector(), timeline(75.0, sounds)) == []


def test_two_beeps_close_together_are_not_a_chirp():
    sounds = [(5.0, chirp()), (6.5, chirp())]
    assert feed(AlarmDetector(), timeline(12.0, sounds)) == []


def test_a_chirp_under_room_noise_is_still_heard():
    noise = synth.noise(30.0, -62.0, "pink", 3)
    sounds = [(0.0, noise), (10.0, chirp(level_db=-40.0))]
    found = feed(AlarmDetector(), timeline(30.0, sounds))
    assert len(found) == 1 and found[0].score == SINGLE


def test_the_watch_forgets_after_ten_minutes():
    watch = ChirpWatch()
    sounds = [(1.0, chirp())]
    detector = AlarmDetector()
    detector.chirps = watch
    feed(detector, timeline(5.0, sounds))
    assert len(watch.found) == 1
    watch.check(700.0)
    assert len(watch.found) == 0


class Wall:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


def test_hearing_lists_chirps_on_the_wall_clock_and_from_a_time():
    wall = Wall()
    samples = timeline(90.0, [(5.0, chirp()), (45.0, chirp()), (85.0, chirp())])
    hearing = Hearing(ArraySource(samples), now=wall)
    hearing.start()
    step = int(CHUNK_S * RATE)
    for start in range(0, len(samples), step):
        wall.t = 1_800_000_000.0 + (start + step) / RATE
        hearing._take(Block(samples[start : start + step], (start + step) / RATE))
    listed = hearing.chirps()
    assert [round(c.at - 1_800_000_000.0) for c in listed] == [5, 45, 85]
    assert [c.score for c in listed] == [SINGLE, REPEAT, STEADY_SCORE]
    assert [round(c.period_s) if c.period_s else None for c in listed] == [None, 40, 40]
    assert hearing.chirps(since=listed[0].at) == listed[1:]
    assert hearing.status()["beeps"]["chirps"]["period_s"] == 40.0


def test_a_chirp_heard_while_muted_is_never_listed():
    wall = Wall()
    samples = timeline(30.0, [(5.0, chirp()), (20.0, chirp())])
    hearing = Hearing(ArraySource(samples), now=wall)
    step = int(CHUNK_S * RATE)
    for start in range(0, len(samples), step):
        t = (start + step) / RATE
        wall.t = 1_800_000_000.0 + t
        hearing.mute(3.0 <= t <= 7.0, t)
        hearing._take(Block(samples[start : start + step], t))
    assert [round(c.at - 1_800_000_000.0) for c in hearing.chirps()] == [20]
