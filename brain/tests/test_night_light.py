import asyncio

from test_safety_watch import build

from pebble.android.torch import PhoneTorch, SimTorch
from pebble.body.sensors import BatteryReading
from pebble.safety.feeds import ListFeed
from pebble.safety.nightlight import CUT_LEVEL, SPELL_S

CUT_LINE = "It looks like the power's gone off, so I've put my light on."


class Room:
    def __init__(self, anyone=True, has=True):
        self.feed = ListFeed()
        self.safety, self.fake = build(feeds={"light": self.feed}, battery=BatteryReading(80.0, True, 30.0))
        self.lamp = SimTorch(self.fake.clock.monotonic, has=has)
        self.safety.night.torch = PhoneTorch(self.lamp)
        self.fake.anyone = anyone

    def step(self, lux, charging=True, seconds=1.0, quiet=False, celsius=30.0, percent=80.0):
        self.safety.life.sensors.battery = BatteryReading(percent, charging, celsius)
        self.feed.push(self.fake.clock.monotonic(), lux)

        async def go():
            await self.safety.tick(quiet)
            await asyncio.sleep(0)

        asyncio.run(go())
        self.fake.clock.advance(seconds)

    def run(self, seconds, lux, **kwargs):
        for _ in range(int(seconds)):
            self.step(lux, **kwargs)

    def cut(self, quiet=False):
        self.run(10, 150.0, quiet=quiet)
        self.run(8, 1.0, charging=False, quiet=quiet)

    def lit(self):
        return self.safety.night.on and self.lamp.wanted

    def torch_records(self):
        return [data for kind, data in self.fake.records if kind == "torch"]


def test_in_a_power_cut_with_someone_here_in_the_dark_the_back_light_comes_on():
    room = Room()
    room.cut()
    assert room.lit() and room.lamp.calls[-1] == (True, CUT_LEVEL, SPELL_S)
    assert room.fake.lines() == [CUT_LINE]
    assert room.torch_records()[-1] == {"on": True, "why": "power cut", "level": CUT_LEVEL}
    room.run(3, 1.0, charging=True)
    assert not room.lit() and room.fake.lines() == [CUT_LINE]
    assert any("the power came back" in text for text, _ in room.fake.notes)


def test_no_light_in_quiet_hours_with_nobody_around_or_without_a_torch():
    quiet = Room()
    quiet.cut(quiet=True)
    assert not quiet.lit() and quiet.lamp.calls == [] and quiet.torch_records()[-1]["skipped"] == "it was quiet hours"
    empty = Room(anyone=False)
    empty.cut()
    assert not empty.lit() and empty.torch_records()[-1]["skipped"] == "nobody was around"
    bare = Room(has=False)
    bare.cut()
    assert not bare.lit() and bare.torch_records()[-1]["skipped"] == "there is no light on this phone"
    assert bare.safety.light_asked(True) == "I don't have a light I can switch on."


def test_the_power_cut_light_goes_off_when_people_go_quiet_hours_start_or_the_lights_return():
    room = Room()
    room.cut()
    room.fake.anyone = False
    room.run(119, 1.0, charging=False)
    assert room.lit()
    room.run(3, 1.0, charging=False)
    assert not room.lit()
    later = Room()
    later.cut()
    later.run(2, 1.0, charging=False, quiet=True)
    assert not later.lit()
    bright = Room()
    bright.cut()
    bright.run(2, 200.0, charging=False)
    assert not bright.lit()


def test_a_long_power_cut_keeps_the_light_going_then_turns_it_off_to_save_the_battery():
    room = Room()
    room.cut()
    room.run(301, 1.0, charging=False)
    assert room.lit() and len([c for c in room.lamp.calls if c[0]]) == 2
    room.run(1500, 1.0, charging=False)
    assert not room.lit()
    assert room.fake.lines()[-1] == "I've turned my light off to save my battery. Say \"Pebble, light\" if you need it again."


def test_a_hot_phone_or_a_low_battery_puts_the_light_out():
    hot = Room()
    hot.cut()
    hot.run(2, 1.0, charging=False, celsius=47.5)
    assert not hot.lit() and "My phone's getting hot, so I've turned my light off." in hot.fake.lines()
    assert hot.safety.light_asked(True) == "My phone's too hot for the light just now."
    low = Room()
    low.cut()
    low.run(2, 1.0, charging=False, percent=20.0)
    assert not low.lit() and "My battery's getting low, so I've turned my light off." in low.fake.lines()


def test_asked_for_light_it_comes_on_even_in_quiet_hours_and_ends_by_itself():
    room = Room()
    room.run(2, 1.0, quiet=True)
    assert room.safety.light_asked(True) == "Okay, here's some light. It goes off by itself after ten minutes."
    assert room.lamp.calls[-1] == (True, 0.8, SPELL_S)
    room.run(601, 1.0, quiet=True)
    assert not room.safety.night.on and any("went off by itself (its time ran out)" in text for text, _ in room.fake.notes)
    assert room.safety.light_asked(False) == "My light's already off."
