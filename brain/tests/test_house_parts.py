import json
from datetime import datetime, timezone

import pytest
from test_house import Bench, run

from pebble.body.sensors import AirReading
from pebble.house.book import HOUSE
from pebble.house.damp import dew_point
from pebble.house.settings import Refused, change, main
from pebble.people.fake import fake_print
from pebble.people.trust import TRUSTED
from pebble.selfstore import SelfStore


def test_dew_point_matches_the_usual_table():
    assert round(dew_point(20.0, 65.0)) == 13
    assert round(dew_point(25.0, 50.0)) == 14
    assert round(dew_point(10.0, 90.0)) == 8
    assert dew_point(20.0, 0.0) is None and dew_point(None, 50.0) is None


def air(bench, celsius, humidity):
    bench.life.p.body.telemetry.air = AirReading(at=bench.clock.now(), body_ms=1, present=True, temperature_c=celsius, humidity_pct=humidity, pressure_pa=101300, gas_ohm=50000, heated_s=3600)


def test_the_condensation_line_is_honest_about_measuring_air_not_glass(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        air(bench, 20.0, 65.0)
        _, said = await bench.say("ina", "will the windows run wet tonight?")
        assert said[0].startswith("The air near me is at 65 % humidity, with a dew point of about 13 degrees. Tonight, any window colder than 13 degrees would run wet.")
        assert "not the walls or windows themselves" in said[0]
        air(bench, 22.0, 30.0)
        _, said = await bench.say("ina", "is it damp in here?")
        assert said[0].startswith("The air near me is fairly dry")

    run(play())
    bench.close()


def test_the_evening_damp_line_comes_once_when_the_air_is_wet(tmp_path):
    bench = Bench(tmp_path, at=datetime(2026, 10, 15, 18, 30, tzinfo=timezone.utc))

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.house.book["asked"]["alarm_test:2026-10"] = True
        air(bench, 21.0, 70.0)
        bench.rig.voice.lines.clear()
        for _ in range(4):
            air(bench, 21.0, 70.0)
            await bench.tick(60.0, people=[ina])
        lines = [line for line in bench.spoken() if "run wet" in line]
        assert len(lines) == 1 and "not the glass" in lines[0]

    run(play())
    bench.close()


def test_the_noise_diary_keeps_levels_never_sound_and_says_it_is_no_evidence(tmp_path):
    bench = Bench(tmp_path, at=datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc))

    class Meter:
        def __init__(self):
            self.level = -60.0

        def snapshot(self):
            now = bench.clock.monotonic()
            return [(now - i * 0.1, self.level, False) for i in range(100)][::-1]

        def floor(self, levels=None):
            return -60.0

    class Hearing:
        meter = Meter()

    async def play():
        await bench.wake()
        bench.house.hearing = Hearing()
        for minute in range(30):
            Hearing.meter.level = -30.0 if 10 <= minute < 15 else -60.0
            await bench.tick(60.0)
        bench.clock.advance(7 * 3600.0)
        ina = bench.person("ina", "Ina", TRUSTED)
        await bench.tick(120.0, people=[ina])
        _, said = await bench.say("ina", "how loud was it last night?")
        assert said[0].startswith("Last night, the loudest hour began at 1am, about 30 decibels above the usual quiet")
        assert "not evidence for a noise complaint" in said[0] and "never keep any sound" in said[0]
        assert all(set(bucket) == {"h", "peak", "loud", "floor"} for bucket in bench.house.book["noise"])

    run(play())
    bench.close()


def test_captions_show_only_while_the_asker_is_here_and_never_private_lines(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        sam = bench.person("sam", "Sam", TRUSTED)
        bench.here(ina)
        bench.here(sam)
        _, said = await bench.say("ina", "captions on")
        assert said[0].startswith("Okay. I'll show what people say")
        bench.life.hear("are you coming to the beach", fake_print("sam", "voice"), addressed=False)
        captions = [m for m in bench.published if m.get("kind") == "caption"]
        assert captions and captions[-1]["lines"][-1] == "Sam: are you coming to the beach"
        before = len(bench.published)
        bench.life.hear("between us, I'm planning a surprise", fake_print("sam", "voice"), addressed=False)
        assert len(bench.published) == before
        bench.life.company.presence.left(ina.id)
        await bench.tick(130.0, people=[sam])
        assert not bench.house.captions.on

    run(play())
    bench.close()


def test_owner_settings_need_the_passphrase_and_stay_in_the_self(tmp_path, clock):
    store = SelfStore.open(tmp_path / "self", clock)
    result = change(store, None, town="dunedin")
    assert result["place"] == {"lat": -45.87, "lon": 170.5, "name": "Dunedin"}
    with pytest.raises(Refused):
        change(store, None, town="atlantis")
    with pytest.raises(Refused):
        change(store, None, lat=120.0, lon=0.0)
    change(store, None, wifi={"ssid": "guests", "password": "made-up", "security": "WPA"})
    data = store.read(HOUSE)
    assert data["guest_wifi"]["ssid"] == "guests" and data["place"]["name"] == "Dunedin"
    assert main(["status", "--self", str(tmp_path / "self")], clock) == 0
    assert main(["cooking-watch", "off", "--self", str(tmp_path / "self")], clock, ask=lambda prompt: "") == 0
    assert store.read(HOUSE)["settings"]["cooking_watch"] is False


def test_the_water_bowl_is_checked_once_a_day_and_an_empty_one_is_told_to_someone_trusted(tmp_path):
    from pebble.seams.sight import SeenThing, Sight

    bench = Bench(tmp_path, at=datetime(2026, 10, 15, 16, 0, tzinfo=timezone.utc))

    class Eyes:
        available = True

        def latest(self, max_age_s=0.5):
            bowl = SeenThing("bowl", 5.0, -20.0, 0.1, 0.1, 0.8, bench.clock.now(), floor_m=1.0, floor_bearing_deg=5.0)
            return Sight(bench.clock.now(), "front", 70.0, things=(bowl,))

    class Pictures:
        def __init__(self):
            self.asked = []

        async def can_look(self):
            return True

        async def yes(self, question, camera=None):
            self.asked.append(question)
            return True

    async def play():
        await bench.wake()
        bench.house.book["asked"]["alarm_test:2026-10"] = True
        ina = bench.person("ina", "Ina", TRUSTED)
        pictures = Pictures()
        bench.life.p.eyes = Eyes()
        bench.life.commands.pictures = pictures
        bench.rig.voice.lines.clear()
        await bench.tick(5.0, people=[ina])
        await bench.tick(5.0, people=[ina])
        assert len(pictures.asked) == 1 and "water bowl" in pictures.asked[0]
        assert "The pet's water bowl looks empty." in bench.spoken()

    run(play())
    bench.close()


def test_forgetting_someone_scrubs_them_from_the_household_pack(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        await bench.say("ina", "add milk to the list")
        await bench.say("ina", "tell me if it rains")
        await bench.say("ina", "the switchboard is in the garage")
        bench.house.away.add("rain", "it started raining", bench.clock.now(), person=ina.id)
        bench.house.forget(ina.id, ["Ina"])
        assert all(entry["by"] is None for entry in bench.house.lists.items("shopping"))
        assert bench.house.watchers.items == []
        assert not [e for e in bench.house.away.entries if e.get("person") == ina.id]
        told = bench.life.p.books.things.facts.find("switchboard")
        assert told.by is None and told.by_label == ""
        saved = bench.life.p.store.read("house.json")
        assert ina.id not in json.dumps(saved)

    run(play())
    bench.close()


def test_the_cat_meowing_by_the_door_is_told_and_spells_are_kept_for_later(tmp_path):
    from pebble.seams.sight import SeenThing, Sight

    bench = Bench(tmp_path)

    class Eyes:
        available = True

        def latest(self, max_age_s=0.5):
            cat = SeenThing("cat", 10.0, -10.0, 0.2, 0.2, 0.9, bench.clock.now(), animal=True, floor_m=1.5, floor_bearing_deg=10.0)
            door = SeenThing("door", 12.0, 5.0, 0.6, 0.3, 0.8, bench.clock.now(), floor_m=2.0, floor_bearing_deg=12.0)
            return Sight(bench.clock.now(), "front", 70.0, things=(cat, door))

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.life.p.eyes = Eyes()
        bench.rig.voice.lines.clear()
        for _ in range(12):
            bench.sound(5.0, {"Meow": 0.6})
            await bench.tick(5.0, people=[ina])
        assert "Ina, the cat's meowing by the door." in bench.spoken()
        for _ in range(30):
            bench.sound(5.0, {})
            await bench.tick(5.0, people=[ina])
        spells = [e for e in bench.house.away.entries if e["kind"] == "meowing"]
        assert spells and spells[-1]["text"].startswith("the cat meowed on and off from ")

    run(play())
    bench.close()


def test_the_house_tick_is_cheap(tmp_path):
    import time

    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        started = time.perf_counter()
        for _ in range(300):
            bench.sound(1.0, {"Speech": 0.8})
            bench.house.tick(bench.clock.now(), False)
            bench.clock.advance(1.0)
        return (time.perf_counter() - started) / 300

    per_tick = run(play())
    assert per_tick < 0.005
    bench.close()


def test_the_monthly_alarm_test_is_offered_once_in_the_first_week(tmp_path):
    bench = Bench(tmp_path, at=datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc))

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.rig.voice.lines.clear()
        await bench.tick(70.0, people=[ina])
        offers = [line for line in bench.spoken() if "Shall we test the smoke alarms?" in line]
        assert offers == ["Ina, it's a new month. Shall we test the smoke alarms? Fire and Emergency suggests testing them every month."]
        _, said = await bench.say("ina", "not now")
        assert said == ["Okay, maybe later."]
        await bench.tick(200.0, people=[ina])
        assert not [line for line in bench.spoken() if "Shall we test" in line]

    run(play())
    bench.close()


def test_no_alarm_test_offer_after_the_first_week(tmp_path):
    bench = Bench(tmp_path, at=datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc))

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.rig.voice.lines.clear()
        await bench.tick(120.0, people=[ina])
        assert not [line for line in bench.spoken() if "Shall we test" in line]

    run(play())
    bench.close()
