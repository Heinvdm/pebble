import json
import math
import random

import numpy as np
import pytest

from pebble.hearing.highband import BIN_HZ, NEW_AFTER_S, Heard, HighTones, Known, News, PhoneBand, Watcher, data_line, heard_line, who_hears

RATE = 48_000


class Band:
    def __init__(self):
        self.ms = 0.0
        self.watcher = Watcher(lambda: self.ms)
        self.noise = np.random.default_rng(3)

    def play(self, seconds, sample, speaking=False, rate=RATE):
        chunk = rate // 50
        total = int(seconds * rate)
        at = 0
        while at < total:
            t = (at + np.arange(chunk)) / rate
            x = sample(t) + self.noise.normal(0.0, level(-75.0), chunk)
            pcm = np.clip(np.round(x), -32768, 32767).astype(np.int16)
            at += chunk
            self.ms += chunk * 1000.0 / rate
            self.watcher.feed(pcm, rate, 1, speaking)

    def rows(self):
        return self.watcher.read(0)["rows"]

    def tones(self):
        return [r for r in self.rows() if r["kind"] == "tone"]


def level(db):
    return 32768 * 10 ** (db / 20)


def sine(hz, db):
    return lambda t: level(db) * np.sin(2 * np.pi * hz * t)


def quiet(t):
    return np.zeros(len(t))


def test_a_steady_mosquito_tone_is_found_and_called_steady():
    band = Band()
    band.play(12.0, sine(17_400, -40.0))
    found = band.tones()
    steady = [r for r in found if r["what"] == "steady"]
    assert steady and abs(steady[0]["hz"] - 17_400) <= 47 and steady[0]["shape"] == "steady"
    assert steady[0]["over_db"] > 20 and found[0]["what"] == "start"
    assert all(abs(r["hz"] - 17_400) < 100 for r in found)


def test_a_tone_ten_decibels_over_the_room_is_found_within_two_seconds():
    band = Band()
    band.play(2.0, quiet)
    hz = 371 * BIN_HZ
    band.play(2.0, sine(hz, -86.5))
    start = next(r for r in band.tones() if r["what"] == "start")
    assert abs(start["hz"] - hz) <= 47 and start["t"] - 2000 <= 2000


def test_two_minutes_of_hiss_and_clicks_make_no_tones():
    band = Band()
    clicks = np.random.default_rng(21)
    band.play(120.0, lambda t: np.where(clicks.integers(0, 4800, len(t)) == 0, 20_000.0, 0.0))
    assert band.tones() == []


class JavaRandom:
    MASK = (1 << 48) - 1

    def __init__(self, seed):
        self.seed = (seed ^ 0x5DEECE66D) & self.MASK
        self.spare = None

    def _next(self, bits):
        self.seed = (self.seed * 0x5DEECE66D + 0xB) & self.MASK
        return self.seed >> (48 - bits)

    def _double(self):
        return ((self._next(26) << 27) + self._next(27)) * (1.0 / (1 << 53))

    def gaussian(self):
        if self.spare is not None:
            found, self.spare = self.spare, None
            return found
        while True:
            v1, v2 = 2 * self._double() - 1, 2 * self._double() - 1
            s = v1 * v1 + v2 * v2
            if 0 < s < 1:
                break
        scale = math.sqrt(-2 * math.log(s) / s)
        self.spare = v2 * scale
        return v1 * scale


def test_hiss_that_starts_after_silence_is_not_taken_for_tones_or_data_on_the_phone_tests_own_sound():
    band = Band()
    for _ in range(300):
        band.ms += 20.0
        band.watcher.feed(np.zeros(960, dtype=np.int16), RATE)
    noise, white = JavaRandom(3), JavaRandom(5)
    last = 0.0
    for _ in range(4 * RATE // 960):
        out = np.empty(960, dtype=np.int16)
        for i in range(960):
            hiss = white.gaussian() * level(-50.0)
            out[i] = max(-32768, min(32767, math.floor(hiss - last + noise.gaussian() * level(-75.0) + 0.5)))
            last = hiss
        band.ms += 20.0
        band.watcher.feed(out, RATE)
    assert band.tones() == []


def test_a_pulsing_tone_is_called_pulsing_with_its_period():
    band = Band()
    band.play(9.0, lambda t: np.where(t % 1.0 < 0.2, level(-45.0) * np.sin(2 * np.pi * 18_000 * t), 0.0))
    band.play(0.5, quiet)
    ends = [r for r in band.tones() if r["what"] == "end"]
    assert len(ends) >= 7
    assert ends[-1]["shape"] == "pulsing" and abs(ends[-1]["period_s"] - 1.0) <= 0.05 and ends[-1]["regular"] > 0.9


def test_a_sweep_is_called_sweeping():
    band = Band()
    phase = [0.0]

    def sweep(t):
        steps = 2 * np.pi * (16_000 + 1_000 * t) / RATE
        values = phase[0] + np.cumsum(steps)
        phase[0] = values[-1]
        return level(-40.0) * np.sin(values)

    band.play(3.0, sweep)
    band.play(0.5, quiet)
    end = [r for r in band.tones() if r["what"] == "end"][-1]
    assert end["shape"] == "sweeping" and end["low_hz"] < 16_200 and end["high_hz"] > 18_800


def test_hopping_data_tones_make_one_data_row():
    band = Band()
    pick = random.Random(9)
    symbols = [[320 + pick.randrange(96) for _ in range(3)] for _ in range(40)]

    def data(t):
        index = np.minimum((t / 0.064).astype(int), len(symbols) - 1)
        out = np.zeros(len(t))
        for column in range(3):
            bins = np.array([symbols[i][column] for i in index])
            out += level(-50.0) * np.sin(2 * np.pi * bins * BIN_HZ * t)
        return out

    band.play(2.56, data)
    band.play(1.0, quiet)
    found = band.tones()
    rows = [r for r in found if r["shape"] == "data"]
    assert len(rows) == 1 and rows[0]["tones"] >= 20 and len(found) <= 3


def test_a_short_burst_near_nineteen_kilohertz_looks_like_a_beacon():
    band = Band()
    band.play(1.0, quiet)
    band.play(0.4, sine(19_000, -45.0))
    band.play(1.0, quiet)
    ends = [r for r in band.tones() if r["what"] == "end"]
    assert len(ends) == 1 and ends[0]["shape"] == "beacon"


def test_speech_and_music_below_eight_kilohertz_make_no_tones():
    band = Band()
    band.play(5.0, lambda t: sum(level(-30.0 - h) * np.sin(2 * np.pi * 200 * h * t) for h in range(1, 36)))
    assert band.tones() == []
    levels = [r for r in band.rows() if r["kind"] == "levels"]
    assert len(levels) >= 4 and len(levels[0]["db"]) == 8 and levels[0]["from_hz"] == 15_000


def test_the_wheels_twenty_kilohertz_line_is_pebbles_own_while_it_moves():
    band = Band()
    band.watcher.highBandMoving(True)
    band.play(1.0, sine(20_000, -40.0))
    band.watcher.highBandMoving(False)
    band.play(0.5, quiet)
    assert band.tones()[-1]["own"] is True


def test_pebbles_own_sounds_are_not_watched():
    band = Band()
    band.play(2.0, sine(17_000, -40.0), speaking=True)
    assert band.tones() == []


def test_sixteen_kilohertz_sound_gives_no_high_band():
    band = Band()
    assert band.watcher.read(0)["on"] is False
    band.watcher.feed(np.zeros(320, dtype=np.int16), 16_000)
    state = band.watcher.read(0)
    assert state["on"] is False and "48 or 96 kHz" in state["problem"]


def test_a_path_that_stops_below_fifteen_kilohertz_switches_the_watcher_off():
    band = Band()
    band.watcher.top(15_100.0)
    band.play(1.0, sine(15_050, -40.0))
    state = band.watcher.read(0)
    assert state["on"] is False and "stops at" in state["problem"]


def test_ninety_six_kilohertz_uses_the_same_bins():
    band = Band()
    band.play(12.0, sine(21_000, -40.0), rate=96_000)
    state = band.watcher.read(0)
    assert state["on"] is True and state["top_hz"] == 24_000
    assert any(abs(r["hz"] - 21_000) < 47 for r in band.tones())


def test_the_reader_takes_the_phones_rows_once_in_brain_time_and_drops_its_own():
    band = Band()
    reader = PhoneBand(band.watcher)
    band.watcher.highBandMoving(True)
    band.play(1.0, sine(20_000, -40.0))
    band.watcher.highBandMoving(False)
    band.play(12.0, sine(17_400, -40.0))
    rows = reader.take(1000.0)
    assert reader.on() and reader.top_hz() == 23_906
    assert [r.what for r in rows] == ["start", "steady"] and all(abs(r.hz - 17_400) < 50 for r in rows)
    assert rows[1].at == pytest.approx(998.0, abs=0.5) and rows[1].at - rows[0].at == pytest.approx(9.75, abs=0.3)
    assert rows[0].key == rows[1].key
    assert reader.take(1001.0) == []
    reader.moving(True)
    assert band.watcher.moving is True


def heard(what, hz, at, shape="tone", start=None, level_db=-40.0, period=None, key=None):
    return Heard(what, hz, hz - 10, hz + 10, at if start is None else start, at if what == "end" else None, at, shape, level_db, period, 0, at if key is None else key)


def test_a_steady_tone_is_news_once_after_ten_minutes():
    tones = HighTones()
    tones.feed([heard("start", 17_400, 0.0)], 0.0, 1_000.0, "lounge")
    tones.feed([heard("steady", 17_400, 10.0, "steady", start=0.0, key=0.0)], 10.0, 1_010.0, "lounge")
    assert tones.news(NEW_AFTER_S - 1, 1_600.0) == []
    news = tones.news(NEW_AFTER_S + 1, 1_601.0)
    assert len(news) == 1 and news[0].kind == "steady" and abs(news[0].hz - 17_400) < 1
    tones.told(news[0], 1_601.0)
    assert tones.news(NEW_AFTER_S + 100, 1_700.0) == []
    again = HighTones(json.loads(json.dumps(tones.to_dict())))
    assert again.known[0].told is not None and again.known[0].shape == "steady"


def test_a_tone_that_stops_is_not_news_and_must_last_ten_minutes_again():
    tones = HighTones()
    tones.feed([heard("start", 17_400, 0.0)], 0.0, 0.0)
    tones.feed([heard("end", 17_400, 300.0, "tone", start=0.0, key=0.0)], 300.0, 300.0)
    assert tones.news(700.0, 700.0) == []
    tones.feed([heard("start", 17_400, 800.0), heard("steady", 17_400, 810.0, "steady", start=800.0, key=800.0)], 810.0, 810.0)
    assert tones.news(1_300.0, 1_300.0) == []
    assert len(tones.news(1_401.0, 1_401.0)) == 1


def test_a_pulsing_tone_counts_while_its_beeps_keep_coming():
    tones = HighTones()
    for n in range(0, 700, 2):
        tones.feed([heard("end", 18_000, float(n), "pulsing", start=float(n), period=2.0)], float(n), float(n))
    news = tones.news(700.0, 700.0)
    assert len(news) == 1 and news[0].kind == "pulsing"
    assert "about every 2 seconds" in heard_line(news[0].tone)


def test_a_tone_that_follows_pebble_from_room_to_room_is_its_own():
    tones = HighTones()
    tones.feed([heard("start", 15_600, 0.0, level_db=-60.0)], 0.0, 0.0, "lounge")
    tones.feed([heard("steady", 15_600, 10.0, "steady", start=0.0, key=0.0, level_db=-61.0)], 10.0, 10.0, "kitchen")
    assert tones.known[0].own and tones.news(1_000.0, 1_000.0) == []


def test_a_tone_heard_faintly_from_the_next_room_is_not_taken_for_its_own():
    tones = HighTones()
    tones.feed([heard("start", 17_400, 0.0, level_db=-40.0)], 0.0, 0.0, "lounge")
    tones.feed([heard("steady", 17_400, 10.0, "steady", start=0.0, key=0.0, level_db=-62.0)], 10.0, 10.0, "kitchen")
    assert not tones.known[0].own and len(tones.news(700.0, 700.0)) == 1


def test_data_tones_are_news_at_most_once_a_day():
    tones = HighTones()
    tones.feed([heard("end", 19_000, 5.0, "data", start=1.0)], 5.0, 5.0, "lounge")
    news = tones.news(6.0, 6.0)
    assert [n.kind for n in news] == ["data"] and news[0].room == "lounge"
    tones.told(news[0], 6.0)
    tones.feed([heard("end", 19_100, 50.0, "data", start=45.0)], 50.0, 50.0, "lounge")
    assert tones.news(51.0, 51.0) == []
    tones.feed([heard("end", 19_100, 90_000.0, "data", start=89_990.0)], 90_000.0, 90_000.0, "lounge")
    assert [n.kind for n in tones.news(90_001.0, 90_001.0)] == ["data"]


def test_a_moment_of_stray_data_tones_or_a_single_blip_is_never_told_or_described():
    tones = HighTones()
    tones.feed([heard("end", 18_150, 10.25, "data", start=10.0)], 10.3, 10.3, "lounge")
    tones.feed([heard("end", 22_770, 10.4, "tone", start=10.2), heard("end", 18_660, 10.5, "beacon", start=10.3)], 10.5, 10.5, "lounge")
    assert tones.news(11.0, 11.0) == [] and tones.now(11.0) == [] and tones.data_now(11.0) is None
    tones.feed([heard("end", 18_150, 300.25, "data", start=300.0), heard("end", 18_660, 301.0, "beacon", start=300.8)], 301.0, 301.0, "lounge")
    assert [n.kind for n in tones.news(302.0, 302.0)] == ["data"]
    assert [k.shape for k in tones.now(302.0)] == ["beacon"]


def test_only_numbers_and_room_names_are_kept_and_old_tones_are_forgotten():
    tones = HighTones()
    tones.feed([heard("start", 17_400, 0.0)], 0.0, 0.0, "lounge")
    kept = tones.to_dict()
    assert set(kept["tones"][0]) == {"hz", "shape", "first", "last", "heard_s", "told", "own", "rooms", "period_s", "ends"}
    tones.forget_old(31 * 86400.0)
    assert tones.known == []


def test_the_words_say_what_the_plan_says():
    steady = Known(17_400.0, "steady", 0.0, 0.0)
    assert heard_line(steady) == "There's a steady tone in here at about 17 kHz."
    assert who_hears(17_400.0) == "Children and young people can often hear tones that high; most adults can't."
    assert who_hears(21_500.0) == "That's higher than people can hear."
    assert data_line(19_000.0, "lounge") == "Something in the lounge is sending data tones too high for most people to hear, at about 19 kHz."
    assert isinstance(News("data", 19_000.0), News)
    assert math.isclose(BIN_HZ, 46.875)
