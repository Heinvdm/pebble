import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from test_house import Bench, run

from pebble.android.mic import TODAY_RATE, WIDE_RATE, MicLadder, PhoneMic, SimMic, probe_result
from pebble.android.torch import PhoneTorch, SimTorch
from pebble.hearing.highband import Heard
from pebble.hearing.tvcheck import CHECKS, TvCheck
from pebble.house import checks as house_checks
from pebble.house.high import TONES, HighWatch
from pebble.house.settings import INBOX, Refused, send, waiting
from pebble.people.trust import TRUSTED
from pebble.safety.watch import Safety
from pebble.selfstore import SelfStore

MOSQUITO = "there's a steady tone in here at about 17 kHz. Children and young people can often hear tones that high; most adults can't."


class FakeBand:
    def __init__(self, mic=None, on=True):
        self.mic = mic
        self.fixed = on
        self.rows = []
        self.moves = []

    def take(self, mono):
        found, self.rows = self.rows, []
        return found

    def moving(self, on):
        self.moves.append(on)

    def on(self):
        if self.mic is not None:
            return self.mic.using["rate"] == WIDE_RATE
        return self.fixed

    def top_hz(self):
        return 23_906.0 if self.on() else None

    def why_off(self):
        return "" if self.on() else "the high band needs a 48 or 96 kHz feed, not 16 kHz"

    def status(self):
        return {"on": self.on()}


def tone(what, hz, mono, shape="tone", start=None, key=1.0, level_db=-40.0, period=None, end=None):
    return Heard(what, hz, hz - 20, hz + 20, mono if start is None else start, end, mono, shape, level_db, period, 0, key)


def with_band(bench, band):
    bench.house.high = HighWatch(bench.house, band)
    return band


def with_mic(bench, sim):
    ladder = MicLadder(PhoneMic(sim), bench.clock.monotonic)
    phone = SimpleNamespace(last={})
    bench.life.p.conversation = SimpleNamespace(ears=SimpleNamespace(mic=ladder), phone=phone)
    return ladder, phone


def steady_tone(bench, band, hz=17_400.0):
    mono = bench.clock.monotonic()
    band.rows = [tone("start", hz, mono, key=mono), tone("steady", hz, mono + 10.0, "steady", start=mono, key=mono)]


def test_a_new_steady_high_tone_is_told_once_by_day_to_someone_trusted(tmp_path):
    bench = Bench(tmp_path)
    band = with_band(bench, FakeBand())

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        steady_tone(bench, band)
        await bench.tick(590.0, people=[ina])
        assert not any("steady tone" in line for line in bench.spoken())
        await bench.tick(30.0, people=[ina])
        told = [line for line in bench.spoken() if "steady tone" in line]
        assert told == [f"Ina, {MOSQUITO}"]
        await bench.tick(900.0, people=[ina])
        assert [line for line in bench.spoken() if "steady tone" in line] == told
        bench.life.save(True)
        kept = bench.life.p.store.read(TONES)
        assert kept["tones"][0]["told"] is not None and "made-up" not in json.dumps(kept)

    run(play())
    bench.close()


def test_high_tones_are_never_told_at_night_to_a_child_or_to_nobody(tmp_path):
    bench = Bench(tmp_path, at=datetime(2026, 10, 15, 21, 30, tzinfo=timezone.utc))
    band = with_band(bench, FakeBand())

    async def play():
        await bench.wake()
        mo = bench.person("mo", "Mo", child=True)
        bench.here(mo)
        steady_tone(bench, band)
        await bench.tick(900.0, people=[mo])
        assert not any("tone" in line for line in bench.spoken())
        ina = bench.person("ina", "Ina", TRUSTED)
        await bench.tick(5.0, people=[ina])
        assert not any("tone" in line for line in bench.spoken())

    run(play())
    bench.close()


def test_data_tones_are_told_to_someone_trusted_with_the_room_at_most_once_a_day(tmp_path):
    bench = Bench(tmp_path)
    band = with_band(bench, FakeBand())
    bench.house.where_am_i = lambda: "lounge"

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        mono = bench.clock.monotonic()
        band.rows = [tone("end", 19_000.0, mono, "data", start=mono - 3.0, end=mono)]
        await bench.tick(2.0, people=[ina])
        told = [line for line in bench.spoken() if "data tones" in line]
        assert told == ["Ina, something in the lounge is sending data tones too high for most people to hear, at about 19 kHz."]
        mono = bench.clock.monotonic()
        band.rows = [tone("end", 19_000.0, mono, "data", start=mono - 3.0, end=mono, key=5.0)]
        await bench.tick(2.0, people=[ina])
        assert [line for line in bench.spoken() if "data tones" in line] == told

    run(play())
    bench.close()


def test_asked_about_high_sounds_it_says_what_it_hears_and_how_high_it_can_hear(tmp_path):
    bench = Bench(tmp_path)
    band = with_band(bench, FakeBand())

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        _, said = await bench.say("ina", "Can you hear anything high-pitched?")
        assert said == ["I can't hear any high tones just now. I can hear up to about 24 kHz here."]
        steady_tone(bench, band)
        await bench.tick(15.0, people=[ina])
        _, said = await bench.say("ina", "Is my charger whining?")
        assert said == ["There's a steady tone in here at about 17 kHz. Children and young people can often hear tones that high; most adults can't."]
        _, said = await bench.say("ina", "How high can you hear?")
        assert said == ["On this phone I can hear up to about 24 kHz. Most pest repellers sit higher than that, so I'd only hear the lower parts of them."]
        _, said = await bench.say("stranger", "can you hear a high pitched noise?")
        assert said == ["Sorry, that's just for the people who live here."]

    run(play())
    bench.close()


def test_with_the_usual_feed_it_listens_up_high_for_two_minutes_when_asked(tmp_path):
    bench = Bench(tmp_path)
    sim = SimMic()
    ladder, _ = with_mic(bench, sim)
    band = with_band(bench, FakeBand(sim))

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        _, said = await bench.say("ina", "can you hear anything high pitched")
        assert said == ["I'll listen up high for two minutes and tell you what I hear."]
        assert sim.using["rate"] == WIDE_RATE
        steady_tone(bench, band, 18_000.0)
        await bench.tick(100.0, people=[ina])
        assert not any("steady tone" in line for line in bench.spoken())
        await bench.tick(30.0, people=[ina])
        assert "Ina, there's a steady tone in here at about 18 kHz. Children and young people can often hear tones that high; most adults can't." in bench.spoken()
        ladder.tick()
        assert sim.using["rate"] == TODAY_RATE
        sim.result = probe_result(13_000.0, wide=False)
        sim.probe_at = 9
        _, said = await bench.say("ina", "can you hear anything high pitched")
        assert said == ["I can't hear that high just now, because this phone's microphone stops at about 13 kHz."]

    run(play())
    bench.close()


def test_the_wheels_tell_the_high_band_when_they_turn(tmp_path):
    bench = Bench(tmp_path)
    band = with_band(bench, FakeBand())

    async def play():
        await bench.wake()
        assert band.moves and band.moves[-1] is False
        bench.life.p.body.telemetry.last_motion_at = bench.clock.now()
        await bench.tick(1.0)
        assert True in band.moves

    run(play())
    bench.close()


def test_pebble_light_switches_the_back_light_on_and_off_and_it_ends_by_itself(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        _, said = await bench.say("stranger", "Pebble, light")
        assert said == ["I don't have a light I can switch on."]
        lamp = SimTorch(bench.clock.monotonic)
        safety = Safety(bench.clock)
        safety.night.torch, safety.night.looked = PhoneTorch(lamp), True
        bench.life.p.safety = safety
        safety.attach(bench.life)
        _, said = await bench.say("stranger", "Pebble, light")
        assert said == ["Okay, here's some light. It goes off by itself after ten minutes."]
        assert lamp.calls[-1] == (True, 0.8, 600.0) and safety.night.on
        _, said = await bench.say("stranger", "turn your light off")
        assert said == ["Okay, light off."] and lamp.calls[-1][0] is False
        await bench.say("stranger", "torch on")
        await bench.tick(601.0)
        assert not safety.night.on and safety.status()["torch"]["on"] is False

    run(play())
    bench.close()


def test_only_the_owner_starts_the_microphone_check_and_hears_how_it_went(tmp_path):
    bench = Bench(tmp_path)
    sim = SimMic(probe_result(21_000.0))
    ladder, _ = with_mic(bench, sim)

    async def play():
        await bench.wake()
        sam = bench.person("sam", "Sam", TRUSTED)
        bench.here(sam)
        _, said = await bench.say("sam", "check your microphones")
        assert said == ["Only my owner can ask me to do that."] and sim.probes == 0
        ina = bench.person("ina", "Ina", relationship="owner")
        await bench.tick(2.0, people=[ina])
        _, said = await bench.say("ina", "Pebble, check your microphones")
        assert said[0] == "Okay. It takes about four minutes, and I'll play some clicks and a quiet whistle. Carry on as normal."
        for _ in range(50):
            if bench.house.checks.probe_task.done():
                break
            await asyncio.sleep(0.01)
        await bench.tick(1.0, people=[ina])
        assert sim.probes == 1
        assert any(line.startswith("Ina, done. My microphones hear up to about 21 kHz on this phone.") for line in bench.spoken())

    run(play())
    bench.close()


def test_the_television_check_is_the_owners_and_keeps_its_numbers(tmp_path, monkeypatch):
    bench = Bench(tmp_path)
    sim = SimMic()
    ladder, phone = with_mic(bench, sim)
    clock = bench.clock

    async def quick_sleep(seconds):
        clock.advance(seconds)
        await asyncio.sleep(0)

    monkeypatch.setattr(house_checks, "TvCheck", lambda gain, keyword, mono: TvCheck(gain, keyword, mono, quick_sleep, block_s=2.0, blocks=6, poll_s=1.0))

    async def play():
        await bench.wake()
        sam = bench.person("sam", "Sam", TRUSTED)
        bench.here(sam)
        _, said = await bench.say("sam", "start the television check")
        assert said == ["Only my owner can ask me to do that."]
        ina = bench.person("ina", "Ina", relationship="owner")
        bench.here(ina)
        _, said = await bench.say("ina", "do the TV check")
        assert said[0].startswith("Okay. Put the television on as usual")
        task = bench.house.checks.tv_task
        await asyncio.wait_for(task, 10)
        await bench.tick(1.0, people=[ina])
        kept = bench.life.p.store.read(CHECKS)
        assert kept["tv"]["passed"] is True and kept["tv"]["false_on"] == 0
        assert ladder.gain_checked and not ladder.gain_hold
        assert "Ina, the television check is done. I never thought I heard my name, with or without listening harder, so I'll keep listening harder for my name." in bench.spoken()
        assert [c["kws_gain"] for c in sim.configs if "kws_gain" in c][:2] == [False, True]

    run(play())
    bench.close()


def test_stopping_the_television_check_changes_nothing(tmp_path):
    bench = Bench(tmp_path)
    sim = SimMic()
    ladder, _ = with_mic(bench, sim)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", relationship="owner")
        bench.here(ina)
        await bench.say("ina", "start the television check")
        assert bench.house.checks.tv.running and ladder.gain_hold
        bench.life.company.presence.left(ina.id)
        _, said = await bench.say("stranger", "stop the television check")
        assert said == ["Okay, I've stopped the television check. Nothing changes."]
        await asyncio.wait_for(bench.house.checks.tv_task, 10)
        assert not ladder.gain_hold and bench.life.p.store.read(CHECKS, None) is None

    run(play())
    bench.close()


def test_settings_sent_from_the_admin_screen_reach_the_running_house_without_a_restart(tmp_path):
    bench = Bench(tmp_path)
    store = bench.life.p.store

    async def play():
        await bench.wake()
        send(store, None, None, True, town="nelson", wifi={"ssid": "guests", "password": "made-up"})
        assert len(waiting(store)) == 1
        await bench.tick(6.0)
        assert waiting(store) == []
        assert bench.house.book["place"]["name"] == "Nelson" and bench.house.book["guest_wifi"]["ssid"] == "guests"
        assert bench.life.p.books.preferences["safety"]["tsunami_zone"] is True
        assert store.read("preferences.json")["safety"]["tsunami_zone"] is True
        assert store.read("house.json")["place"]["name"] == "Nelson"
        notes = [item.text for item in bench.life.events.peek()]
        assert any("your owner changed your house settings from the app" in text for text in notes)
        with pytest.raises(Refused):
            send(store, None, None, None, children_arrivals=True, guardians=["Nobody"])
        store.write(f"{INBOX}/00000000000001-stale.json", {"format": 1, "changes": {"children_arrivals": True, "guardians": ["Nobody"]}, "tsunami": None}, keep_backup=False)
        await bench.tick(6.0)
        assert waiting(store) == [] and bench.house.book.settings["children_arrivals"] is False

    run(play())
    bench.close()


def test_settings_sent_while_pebble_was_off_are_taken_when_it_starts(tmp_path, clock):
    store = SelfStore.open(tmp_path / "self", clock)
    send(store, None, None, None, cooking_watch=False)
    bench = Bench(tmp_path)
    assert bench.house.book.settings["cooking_watch"] is False and waiting(bench.life.p.store) == []
    bench.close()
