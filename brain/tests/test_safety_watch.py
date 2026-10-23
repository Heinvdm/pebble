import asyncio
import math
from types import SimpleNamespace

from pebble.body.sensors import BatteryReading
from pebble.clock import FakeClock
from pebble.hearing import synth
from pebble.hearing.alarm import AlarmDetector
from pebble.hearing.service import Hearing
from pebble.hearing.sources import ArraySource
from pebble.safety.feeds import ListFeed, Sample
from pebble.safety.motion import G
from pebble.safety.sounder import AndroidSounder, LogSounder
from pebble.safety.watch import Safety
from pebble.seams.sight import SeenThing, Sight
from tests.test_safety_ladder import Fake


class Eyes:
    available = True

    def __init__(self):
        self.sight = None

    def latest(self, max_age_s=0.5):
        return self.sight


def build(feeds=None, hearing=None, docked=True, eyes=None, battery=None):
    fake = Fake()
    telemetry = SimpleNamespace(docked=docked, last_motion_at=None, air_reading=lambda now, max_age=None: None)
    life = SimpleNamespace(p=SimpleNamespace(body=SimpleNamespace(telemetry=telemetry), eyes=eyes), sensors=SimpleNamespace(battery=battery, temperature_c=None), commands=None)
    safety = Safety(fake.clock, hearing=hearing, feeds=feeds or {})
    safety.attach(life, fake.ports())
    return safety, fake


def heard(text, person=None, label="someone"):
    return SimpleNamespace(text=text, person_id=person, label=label)


def tick(safety, fake, seconds=1.0, quiet=False):
    async def go():
        await safety.tick(quiet)

    asyncio.run(go())
    fake.clock.advance(seconds)


def test_help_heard_starts_the_help_ladder():
    safety, fake = build()
    safety.heard(heard("help! help me", "mo", "Mo"))
    incident = safety.ladder.incidents["help"]
    assert incident.person == "mo" and incident.confidence(fake.clock.monotonic()) >= 0.9
    tick(safety, fake)
    assert fake.loud() == ["Are you okay? Do you need help?"] and safety.active


def test_a_request_with_help_in_it_is_not_a_call_for_help():
    safety, fake = build()
    safety.heard(heard("can you help me find my keys"))
    assert not safety.ladder.incidents


def test_name_shouted_counts_only_when_loud_and_grows_when_repeated():
    quiet_room = synth.noise(30, -70, "pink", 1)
    hearing = Hearing(ArraySource(quiet_room), detector=AlarmDetector("plain"))
    safety, fake = build(hearing=hearing)
    hearing.pump()
    safety.heard(heard("Pebble!"))
    assert not safety.ladder.incidents
    safety.heard(heard("Pebble!"), loud=True)
    assert safety.ladder.incidents["help"].evidence["name_shouted"][0] == 0.5
    fake.clock.advance(3)
    safety.heard(heard("Pebble!"), loud=True)
    assert safety.ladder.incidents["help"].evidence["name_shouted"][0] == 0.7


def test_a_shout_measured_by_the_microphone_counts_as_loud():
    shout = synth.noise(20, -70, "pink", 1) + synth.speechlike(1.5, -15, seed=4)
    hearing = Hearing(ArraySource(shout), detector=AlarmDetector("plain"))
    safety, fake = build(hearing=hearing)
    hearing.pump()
    safety.heard(heard("Pebble"))
    assert "help" in safety.ladder.incidents


def test_fire_shouted():
    safety, fake = build()
    safety.heard(heard("fire! fire!"), loud=True)
    assert safety.ladder.incidents["fire"].evidence["fire_word"][0] == 0.6


def test_beeps_heard_through_the_hearing_service_reach_the_ladder():
    hearing = Hearing(ArraySource(synth.t3(3)), detector=AlarmDetector("plain"))
    safety, fake = build(hearing=hearing)
    tick(safety, fake)
    assert safety.ladder.incidents["fire"].confidence(fake.clock.monotonic()) >= 0.95
    tick(safety, fake)
    assert fake.lines() == ["I can hear a smoke alarm going off. Is everything okay?"]


def test_quake_from_the_accelerometer_holds_the_wheels():
    accel = ListFeed()
    safety, fake = build(feeds={"accel": accel})
    for second in range(14):
        for i in range(50):
            t = fake.clock.monotonic() + i / 50.0
            shake = 0.0 if second < 4 else 0.5 * math.sin(2 * math.pi * 2.3 * t) + 0.3 * math.sin(2 * math.pi * 5.1 * t)
            accel.push(t, shake, 0.6 * shake, G + 0.2 * shake)
        tick(safety, fake)
    assert safety.hold_reason() == "the floor is shaking"
    assert "Earthquake! Drop, cover and hold!" in fake.loud()
    assert fake.felts[0][0] == "quake"


def test_something_against_the_face_holds_and_reacts_gently():
    near = ListFeed()
    safety, fake = build(feeds={"proximity": near})
    safety.near.max_range = lambda: 5.0
    near.push(fake.clock.monotonic(), 0.0)
    tick(safety, fake)
    tick(safety, fake)
    assert safety.hold_reason() == "something is pressed against my face"
    assert fake.faces[-1] == "surprised" and fake.said == []


def test_falling_down_the_stairs():
    accel, pressure = ListFeed(), ListFeed()
    safety, fake = build(feeds={"accel": accel, "pressure": pressure}, docked=False)
    for i in range(300):
        pressure.push(fake.clock.monotonic() - 30 + i * 0.1, 1013.0 + (0.4 if i > 200 else 0.0))
    base = fake.clock.monotonic()
    for i in range(50):
        accel.push(base + i / 50.0, 0.0, 0.0, G)
    for i in range(15):
        accel.push(base + 1.0 + i / 50.0, 0.2, 0.1, 0.3)
    for i in range(5):
        accel.push(base + 1.3 + i / 50.0, 4.0, 2.0, 30.0 if i < 2 else G)
    calmed = []
    safety.life.calm_down = lambda seconds=120.0, why="": calmed.append((seconds, why))
    tick(safety, fake)
    assert ("stairs", "you fell down the stairs") in fake.felts
    assert calmed and calmed[-1] == (120.0, "you fell down the stairs")


def test_the_phone_too_hot_holds_still_and_asks_for_help():
    safety, fake = build(battery=BatteryReading(60.0, True, 47.5))
    fake.anyone = True

    async def go():
        await safety.tick(False)
        await asyncio.sleep(0)

    asyncio.run(go())
    assert safety.hold_reason() == "my phone is too hot"
    assert any("far too hot (48 C)" in text for text, _ in fake.notes)
    assert fake.stopped
    assert "room" not in " ".join(text for text, _ in fake.notes)


def test_fire_seen_by_the_eyes_starts_the_fire_ladder_and_keeps_distance():
    eyes = Eyes()
    safety, fake = build(eyes=eyes)
    for i in range(30):
        eyes.sight = Sight(float(i), "front", 70.0, (), (), (SeenThing("fire", 2.0, -5.0, 0.4, 0.3, 0.9, float(i)),))
        tick(safety, fake, 0.5)
    incident = safety.ladder.incidents["fire"]
    assert incident.evidence["smoke_seen"][0] == 0.86
    assert safety.hold_reason() == "there's fire right in front of me"
    assert incident.step == "ask"
    assert fake.lines() == ["I can see what looks like smoke or flames. Is everything okay?"]


def test_sounders():
    trace = []
    log = LogSounder(lambda what, text: trace.append((what, text)))
    assert log.siren(True) and log.on and log.say("Fire!")
    assert trace == [("alarm", "loud alarm sound on"), ("SAYS", '"Fire!" (loud)')]

    class Bridge:
        def __init__(self):
            self.calls = []

        def alarmSound(self, on):
            self.calls.append(("sound", on))
            return True

        def alarmSay(self, text):
            self.calls.append(("say", text))
            return True

    bridge = Bridge()
    android = AndroidSounder(bridge)
    assert android.siren(True) and android.on and android.say("Smoke alarm!")
    assert bridge.calls == [("sound", True), ("say", "Smoke alarm!")]
    broken = AndroidSounder(SimpleNamespace(alarmSound=lambda on: (_ for _ in ()).throw(RuntimeError("no audio"))))
    assert not broken.siren(True) and not broken.on and "no audio" in broken.info()["problem"]


def test_status_is_plain_data():
    safety, fake = build()
    status = safety.status()
    assert status["ladder"]["active"] is False and status["notices"] == {"kind": "off"} and status["hold"] is None


def test_safety_from_a_profile():
    import sys
    import time

    from pebble.clock import Clock
    from pebble.hearing.service import Hearing
    from pebble.hearing.sources import PARECORD, CommandSource
    from pebble.safety.build import safety_from
    from pebble.safety.sounder import CommandSounder

    allowed = safety_from({"hearing": {"kind": "command", "command": list(PARECORD), "model": "none"}, "sounder": {"kind": "command", "command": ["paplay"]}}, Clock())
    assert isinstance(allowed.hearing.source, CommandSource) and allowed.hearing.source.command == PARECORD
    assert isinstance(allowed.sounder, CommandSounder) and allowed.threaded and allowed.hearing.model is None
    command = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(bytes(32000)); sys.stdout.flush()"]
    hearing = Hearing(CommandSource(command, time.monotonic), Clock().now)
    sounder = CommandSounder([sys.executable, "-c", "pass"])
    hearing.start()
    deadline = time.monotonic() + 10
    got = 0
    while time.monotonic() < deadline and got < 16000:
        block = hearing.source.read(2.0)
        got += 0 if block is None else len(block.samples)
        time.sleep(0.05)
    hearing.stop()
    assert got == 16000
    assert sounder.siren(True) and sounder.on
    assert sounder.siren(False) and not sounder.on


def test_a_body_profile_cannot_run_commands_or_switch_safety_off(monkeypatch):
    import sys

    from pebble.clock import Clock
    from pebble.safety import build
    from pebble.safety.build import safety_from
    from pebble.safety.sounder import AndroidSounder, LogSounder
    from pebble.seams.later import CommandPower, ProcessOnly, power_from

    for config in (None, {}, {"enabled": False}, {"enabled": False, "hearing": {"kind": "command"}}):
        assert safety_from(config, Clock()) is not None, config
    planted = safety_from({"hearing": {"kind": "command", "command": [sys.executable, "-c", "print(1)"]}, "sounder": {"kind": "command", "command": ["sh", "-c", "rm -rf /"]}}, Clock())
    assert planted.hearing is None and isinstance(planted.sounder, LogSounder)
    assert isinstance(power_from({"shutdown_command": ["sh", "-c", "curl example"]}), ProcessOnly)
    assert isinstance(power_from({"shutdown_command": ["systemctl", "poweroff"]}), CommandPower)
    monkeypatch.setattr(build, "on_phone", lambda: True)
    monkeypatch.setattr(build, "BridgeSensors", lambda monotonic: SimpleNamespace(start=lambda: None, feed=lambda kind: None, max_range=lambda kind: None))
    phone = safety_from({"enabled": False, "hearing": {"kind": "none"}, "sounder": {"kind": "log"}}, Clock())
    assert isinstance(phone.sounder, AndroidSounder) and phone.hearing is not None


def test_only_the_person_who_fell_makes_a_spot_usual():
    safety, fake = build()
    incident = SimpleNamespace(evidence={"on_floor": (0.7, 0.0)}, details={"place": "rug", "_by_fallen": False})
    safety._ended(incident, "stood down")
    assert safety.floor.usual == {}
    incident.details["_by_fallen"] = True
    safety._ended(incident, "stood down")
    assert safety.floor.usual == {"rug": 1}


def test_stranger_watch_is_off_by_default_and_only_notifies():
    safety, fake = build()
    people = SimpleNamespace(someone_new=lambda now: True, here=lambda now: [])
    safety.life.company = people
    tick(safety, fake, quiet=True)
    assert not fake.notified
    safety.stranger_watch = True
    tick(safety, fake, quiet=True)
    assert len(fake.notified) == 1 and "a stranger" in fake.notified[0][0]
    assert "saw someone it hasn't met at home at" in fake.notified[0][1]
    assert fake.said == [] and fake.sirens == []
    tick(safety, fake, quiet=True)
    assert len(fake.notified) == 1
    safety.stranger_watch = True
    safety.stranger_at = -1e9
    tick(safety, fake, quiet=False)
    assert len(fake.notified) == 1


def test_tell_owner_goes_through_the_notifier_only_when_switched_on():
    safety, fake = build()
    assert safety.tell_owner("Pebble noticed something", "The door looks open.") is False

    class Notifier:
        enabled = True

        def __init__(self):
            self.sent = []

        def send(self, title, text):
            self.sent.append((title, text))
            return True

        def info(self):
            return {"kind": "test"}

    safety.notifier = Notifier()
    assert safety.tell_owner("Pebble noticed something", "The door looks open.") is True
    assert safety.notifier.sent == [("Pebble noticed something", "The door looks open.")]
