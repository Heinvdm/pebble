import json
import math
import random
from dataclasses import dataclass

import pytest

from pebble.safety.baro import Barometer
from pebble.safety.feeds import BridgeFeed, BridgeSensors, ListFeed, Sample
from pebble.safety.motion import G, PhoneMotion
from pebble.safety.notify import NoNotifier, NtfyNotifier, check_url, notifier_from
from pebble.safety.room import AirWatch, LightWatch, NearWatch, PhoneHeat
from pebble.safety.seen import FireWatch, FloorWatch
from pebble.seams.sight import SeenPerson, SeenThing, Sight

RATE = 50.0


def trace(seconds, shake=lambda t: (0.0, 0.0, 0.0), gravity=(0.0, 0.0, G), start=0.0, noise=0.01, seed=1):
    rng = random.Random(seed)
    out = []
    for i in range(int(seconds * RATE)):
        t = start + i / RATE
        dx, dy, dz = shake(t)
        out.append(Sample(t, (gravity[0] + dx + rng.gauss(0, noise), gravity[1] + dy + rng.gauss(0, noise), gravity[2] + dz + rng.gauss(0, noise))))
    return out


def quake_shake(level):
    parts = [(1.3, 0.7, 0.2), (2.6, 1.1, 0.9), (4.1, 0.6, 1.7), (6.8, 0.4, 2.4), (8.9, 0.25, 0.4)]
    total = math.sqrt(sum(a * a / 2 for _, a, _ in parts))

    def shake(t):
        x = sum(a * math.sin(2 * math.pi * f * t + p) for f, a, p in parts) / total * level
        y = sum(a * math.cos(2 * math.pi * f * t + 2 * p) for f, a, p in parts) / total * level * 0.8
        return x, y, 0.3 * x

    return shake


def footsteps(amplitude=0.8, every=0.55):
    def shake(t):
        phase = t % every
        if phase > 0.08:
            return 0.0, 0.0, 0.0
        burst = amplitude * math.exp(-phase / 0.02) * math.sin(2 * math.pi * 12 * phase)
        return 0.2 * burst, 0.1 * burst, burst

    return shake


def bump(at=2.0):
    def shake(t):
        dt = t - at
        if not 0 <= dt < 0.3:
            return 0.0, 0.0, 0.0
        value = 4.0 * math.exp(-dt / 0.05) * math.sin(2 * math.pi * 18 * dt)
        return value, 0.5 * value, 0.3 * value

    return shake


def kinds(events):
    return [e.kind for e in events]


def docked_motion():
    return PhoneMotion(still=lambda: True, driving=lambda: False, docked=lambda: True)


def loose_motion():
    return PhoneMotion(still=lambda: False, driving=lambda: False, docked=lambda: False)


@pytest.mark.parametrize("level", [0.25, 0.6, 2.0])
def test_quake_while_docked_and_still(level):
    motion = docked_motion()
    events = motion.feed(trace(5)) + motion.feed(trace(12, quake_shake(level), start=5))
    quakes = [e for e in events if e.kind == "quake"]
    assert quakes, kinds(events)
    first = quakes[0]
    assert first.detail["seconds"] >= 4 and 0 < first.detail["peak_g"] < 1
    assert quakes[-1].detail["strength"] in ("light shaking", "moderate shaking", "strong shaking", "very strong shaking")


def test_no_quake_from_footsteps():
    motion = docked_motion()
    events = motion.feed(trace(5)) + motion.feed(trace(30, footsteps(), start=5))
    assert "quake" not in kinds(events)


def test_no_quake_from_one_bump():
    motion = docked_motion()
    events = motion.feed(trace(5)) + motion.feed(trace(10, bump(8.0), start=5))
    assert "quake" not in kinds(events)


def test_no_quake_from_sensor_noise():
    motion = docked_motion()
    assert "quake" not in kinds(motion.feed(trace(60, noise=0.02)))


def test_no_quake_while_its_own_motors_run():
    motion = PhoneMotion(still=lambda: False, driving=lambda: True, docked=lambda: True)
    events = motion.feed(trace(20, quake_shake(0.6)))
    assert "quake" not in kinds(events)


def test_quake_strength_words():
    from pebble.safety.motion import strength

    assert strength(0.1) == "light shaking"
    assert strength(0.5) == "moderate shaking"
    assert strength(1.2) == "strong shaking"
    assert strength(3.0) == "very strong shaking"


def test_dropped():
    motion = loose_motion()
    fall = [Sample(2.0 + i / RATE, (0.1, 0.2, 0.4)) for i in range(15)]
    hit = [Sample(2.3 + i / RATE, (5.0, 3.0, 35.0 if i < 2 else G)) for i in range(10)]
    events = motion.feed(trace(2)) + motion.feed(fall + hit)
    assert kinds(events).count("dropped") == 1


def test_a_jolt_is_not_a_drop():
    motion = loose_motion()
    hit = [Sample(2.0 + i / RATE, (5.0, 3.0, 35.0 if i < 2 else G)) for i in range(10)]
    assert "dropped" not in kinds(motion.feed(trace(2) + hit))


def test_tipped_on_its_side_and_back():
    motion = loose_motion()
    side = (0.0, G * math.sin(math.radians(70)), G * math.cos(math.radians(70)))
    events = motion.feed(trace(2)) + motion.feed(trace(4, gravity=side, start=2)) + motion.feed(trace(4, start=6))
    assert kinds(events)[:2] == ["tipped", "righted"]


def test_head_tilt_alone_is_not_tipping():
    motion = loose_motion()
    nodded = (G * math.sin(math.radians(80)), 0.0, G * math.cos(math.radians(80)))
    assert "tipped" not in kinds(motion.feed(trace(6, gravity=nodded)))


def test_lifted_off_the_floor():
    motion = loose_motion()
    lift = [Sample(1.0 + i / RATE, (0.0, 0.0, G + 4.0)) for i in range(15)]
    events = motion.feed(trace(1) + lift + trace(2, start=1.3))
    assert "lifted" in kinds(events)


def test_carried_around():
    motion = loose_motion()
    gait = lambda t: (0.4 * math.sin(2 * math.pi * 1.9 * t), 0.3 * math.cos(2 * math.pi * 0.95 * t), 1.6 * math.sin(2 * math.pi * 1.9 * t + 0.4))
    events = motion.feed(trace(8, gait))
    assert "carried" in kinds(events) and "shaken" not in kinds(events)


def test_shaken_hard():
    motion = loose_motion()
    events = motion.feed(trace(3, lambda t: (14.0 * math.sin(2 * math.pi * 4 * t), 0.0, 0.0)))
    assert "shaken" in kinds(events)


def baro(seconds, value, start=0.0, rate=10.0, noise=0.005, seed=2):
    rng = random.Random(seed)
    return [Sample(start + i / rate, (value(start + i / rate) + rng.gauss(0, noise),)) for i in range(int(seconds * rate))]


def test_carried_up_a_floor():
    meter = Barometer()
    step = lambda t: 1013.0 - 0.36 * min(1.0, max(0.0, (t - 30) / 8.0))
    events = meter.feed(baro(60, step))
    moved = [e for e in events if e.kind == "moved_up"]
    assert len(moved) == 1 and 2.0 <= moved[0].detail["metres"] <= 4.0


def test_down_a_floor():
    meter = Barometer()
    events = meter.feed(baro(60, lambda t: 1013.0 + (0.4 if t > 30 else 0.0)))
    assert kinds(events) == ["moved_down"]


def test_door_pulse_in_a_closed_house():
    meter = Barometer()
    pulse = lambda t: 1013.0 + (0.07 * math.exp(-(t - 20.0) / 0.6) if 20.0 <= t < 22.0 else 0.0)
    events = meter.feed(baro(40, pulse))
    assert kinds(events) == ["door"]


def test_steady_pressure_is_quiet():
    meter = Barometer()
    assert meter.feed(baro(300, lambda t: 1013.0)) == []


def test_door_pulses_ignored_while_driving():
    meter = Barometer(still=lambda: False)
    pulse = lambda t: 1013.0 + (0.07 if 20.0 <= t < 21.0 else 0.0)
    assert meter.feed(baro(40, pulse)) == []


def test_storm_coming():
    meter = Barometer()
    falling = lambda t: 1015.0 - 4.0 * t / (3.5 * 3600.0)
    events = meter.feed(baro(3.6 * 3600.0, falling, rate=0.2, noise=0.003))
    storms = [e for e in events if e.kind == "storm"]
    assert len(storms) == 1 and "stormy" in storms[0].text


def test_light_goes_out_with_the_power():
    light = LightWatch(power_lost=lambda: True)
    samples = [Sample(t * 0.5, (150.0 if t < 20 else 1.0,)) for t in range(40)]
    events = light.feed(samples)
    out = [e for e in events if e.kind == "lights_out"]
    assert len(out) == 1 and "power may be off" in out[0].text


def test_dark_room_then_light():
    light = LightWatch()
    events = light.feed([Sample(float(t), (2.0,)) for t in range(70)]) + light.feed([Sample(70.0 + t, (200.0,)) for t in range(70)])
    assert kinds(events) == ["dark", "light"]


def test_flicker_is_only_a_hint():
    light = LightWatch()
    events = light.feed([Sample(t * 0.1, (100.0 if t % 2 else 40.0,)) for t in range(60)])
    flicker = [e for e in events if e.kind == "flicker"]
    assert len(flicker) == 1 and "only a hint" in flicker[0].text


def test_something_pressed_against_the_face_holds_the_wheels():
    near = NearWatch(max_range=lambda: 5.0)
    assert near.feed([Sample(0.0, (0.0,))], 0.1) == []
    events = near.feed([], 0.5)
    assert kinds(events) == ["touched_face"] and near.hold_reason()
    near.feed([Sample(1.0, (5.0,))], 1.0)
    assert near.hold_reason()
    events = near.feed([], 3.2)
    assert kinds(events) == ["face_clear"] and near.hold_reason() is None


def test_poking_is_noticed():
    near = NearWatch(max_range=lambda: 5.0)
    samples = []
    for i in range(4):
        samples += [Sample(i * 0.6, (0.0,)), Sample(i * 0.6 + 0.2, (5.0,))]
    near.feed(samples, 2.5)
    events = near.feed([Sample(2.6, (0.0,))], 3.0)
    assert kinds(events) == ["poked"]


def test_phone_heat_steps_with_hysteresis():
    heat = PhoneHeat()
    assert heat.update(38.0) == []
    assert kinds(heat.update(41.0)) == ["phone_warm"]
    assert kinds(heat.update(43.5)) == ["phone_hot"] and heat.hold_reason()
    assert kinds(heat.update(47.0)) == ["phone_too_hot"]
    assert heat.update(45.0) == [] and heat.hold_reason()
    assert kinds(heat.update(42.0)) == ["phone_hot"]
    assert heat.update(39.5) == []
    assert kinds(heat.update(37.0)) == ["phone_cool"] and heat.hold_reason() is None


@dataclass(frozen=True)
class Air:
    at: float
    body_ms: int
    present: bool = True
    temperature_c: float | None = 21.0
    humidity_pct: float | None = 50.0
    pressure_pa: int | None = 101300
    gas_ohm: int | None = 120000
    heated_s: int | None = 3600

    @property
    def pressure_hpa(self):
        return self.pressure_pa / 100.0

    @property
    def warming(self):
        return self.heated_s is None or self.heated_s < 300


def test_heat_rate_of_rise_is_a_low_hint():
    air = AirWatch(lambda: 1000.0)
    events = []
    for i in range(60):
        t = i * 3.0
        c = 25.0 + max(0.0, t - 60.0) / 60.0 * 10.0
        events += air.feed(Air(t, i, temperature_c=c, heated_s=3600 + i * 3))
    rises = [e for e in events if e.kind == "heat_rise"]
    assert len(rises) == 1 and rises[0].confidence == 0.3 and "late" in rises[0].text


def test_slow_warming_on_the_charger_is_not_a_fire():
    air = AirWatch(lambda: 1000.0)
    events = []
    for i in range(400):
        events += air.feed(Air(i * 3.0, i, temperature_c=22.0 + i * 3.0 / 600.0))
    assert "heat_rise" not in kinds(events)


def gas_run(drop_to, humidity_jump=0.0, warming_restart=False):
    air = AirWatch(lambda: 1000.0)
    events = []
    i = 0
    for i in range(400):
        events += air.feed(Air(i * 3.0, i, gas_ohm=120000 + (i % 7) * 500, heated_s=1800 + i * 3))
    start = i + 1
    for j in range(40):
        k = start + j
        ohm = int(120000 * (drop_to if j > 5 else 1.0))
        rh = 50.0 + (humidity_jump if j > 3 else 0.0)
        heated = (5 + j * 3) if warming_restart else 1800 + k * 3
        events += air.feed(Air(k * 3.0, k, gas_ohm=ohm, humidity_pct=rh, heated_s=heated))
    return events


def test_gas_spike_is_a_low_hint():
    events = gas_run(0.35)
    spikes = [e for e in events if e.kind == "gas_spike"]
    assert len(spikes) == 1 and spikes[0].confidence == 0.25


def test_small_gas_wobble_is_nothing():
    assert "gas_spike" not in kinds(gas_run(0.8))


def test_steam_is_not_called_smoke():
    events = gas_run(0.35, humidity_jump=15.0)
    assert "gas_spike" not in kinds(events) and "room_steam" in kinds(events)


def test_no_gas_hints_while_the_sensor_warms_up():
    assert "gas_spike" not in kinds(gas_run(0.3, warming_restart=True))


def test_room_temperature_for_conversation():
    air = AirWatch(lambda: 1000.0)
    events = air.feed(Air(0.0, 1, temperature_c=13.5)) + air.feed(Air(3.0, 2, temperature_c=13.4))
    assert kinds(events) == ["room_cold"] and "cold" in events[0].text


def test_missing_air_sensor_is_ignored():
    air = AirWatch(lambda: 1000.0)
    assert air.feed(None) == [] and air.feed(Air(0.0, 1, present=False)) == []


def person(bearing=0.0, posture="lying", track=1, width=0.4):
    return SeenPerson(bearing, -10.0, 0.2, width, 0.9, track=track, posture=posture)


def thing(label, bearing=0.0, width=0.5, height=0.3, score=0.8):
    return SeenThing(label, bearing, -5.0, height, width, score, 0.0)


def sights(seconds, people=(), things=(), every=0.5):
    return [Sight(i * every, "front", 70.0, tuple(people), (), tuple(things)) for i in range(int(seconds / every))]


def test_someone_lying_on_the_floor():
    floor = FloorWatch()
    out = []
    for sight in sights(10, [person()], [thing("rug", 5.0)]):
        out += floor.feed(sight, 1000.0, sight.at)
    assert [n.kind for n in out] == ["on_floor"] and out[0].detail["place"] == "rug"


def test_lying_on_the_couch_is_normal():
    floor = FloorWatch()
    out = []
    for sight in sights(12, [person()], [thing("couch", 2.0, width=0.8)]):
        out += floor.feed(sight, 1000.0, sight.at)
    assert out == []


def test_standing_people_are_fine():
    floor = FloorWatch()
    out = []
    for sight in sights(12, [person(posture="standing")]):
        out += floor.feed(sight, 1000.0, sight.at)
    assert out == []


def test_a_usual_lying_place_lowers_the_worry():
    floor = FloorWatch()
    floor.fine_at("rug")
    floor.fine_at("rug")
    out = []
    for sight in sights(10, [person()], [thing("rug", 5.0)]):
        out += floor.feed(sight, 1000.0, sight.at)
    assert out[0].confidence < 0.5


def test_fire_seen_twice_and_kept_at_a_distance():
    fire = FireWatch()
    out = []
    for sight in sights(12, things=[thing("fire", 3.0, height=0.4)]):
        out += fire.feed(sight, 1000.0, sight.at)
    assert [round(n.confidence, 2) for n in out] == [0.6, 0.86]
    assert out[1].detail["second_look"] and "flames" in out[1].text
    assert fire.hold_reason(11.6) == "there's fire right in front of me"
    assert fire.hold_reason(30.0) is None


def test_a_flash_of_fire_is_nothing():
    fire = FireWatch()
    out = []
    for i, sight in enumerate(sights(12, things=[thing("fire")])):
        out += fire.feed(sight if i == 5 else Sight(sight.at, "front", 70.0), 1000.0, sight.at)
    assert out == []


class FakeBridge:
    def __init__(self):
        self.total = 100
        self.tap = None

    def sensorTap(self, on):
        self.tap = on

    def sensorInfo(self):
        return json.dumps({"proximity": {"max_range": 5.0}, "accel": {"rate_hz": 50}})

    def sensorRead(self, kind, start, most):
        if start > self.total:
            return json.dumps({"kind": kind, "total": self.total, "rows": [], "now_ms": 5000.0})
        rows = [[2000.0 + 20 * i, 0.1, 0.2, 9.8] for i in range(start, self.total)]
        return json.dumps({"kind": kind, "total": self.total, "rows": rows[-most:], "now_ms": 5000.0})


def test_bridge_feed_starts_at_now_and_ages_samples():
    bridge = FakeBridge()
    feed = BridgeFeed("accel", bridge, monotonic=lambda: 50.0)
    assert feed.read() == []
    bridge.total = 103
    samples = feed.read()
    assert len(samples) == 3 and samples[0].values == (0.1, 0.2, 9.8)
    assert samples[-1].at == pytest.approx(50.0 - (5000.0 - (2000.0 + 20 * 102)) / 1000.0)
    bridge.total = 200
    feed.max_rows = 10
    assert len(feed.read()) == 10 and feed.skipped == 87


def test_bridge_sensors_switch_on_and_off():
    bridge = FakeBridge()
    sensors = BridgeSensors(bridge)
    sensors.start()
    assert bridge.tap is True and sensors.max_range("proximity") == 5.0 and sensors.has("accel")
    sensors.stop()
    assert bridge.tap is False


def test_list_feed():
    feed = ListFeed()
    feed.push(1.0, 2.0)
    assert feed.read()[0].value == 2.0 and feed.read() == []


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_ntfy_sends_words_only():
    sent = []

    def opener(request, timeout):
        sent.append(request)
        return Response()

    notifier = NtfyNotifier("https://ntfy.sh/pebble-at-home-x7q", opener=opener, clock=lambda: 0.0)
    assert notifier.send("Pebble: a smoke alarm going off", "Pebble noticed a smoke alarm going off at home at 21:40.")
    request = sent[0]
    assert request.full_url == "https://ntfy.sh/pebble-at-home-x7q" and request.get_method() == "POST"
    assert request.data.decode("utf-8").startswith("Pebble noticed")
    headers = {k.lower(): v for k, v in request.header_items()}
    assert headers["title"].startswith("Pebble:") and "pebble-notice" in headers["user-agent"]
    assert "authorization" not in headers
    assert "@" not in json.dumps(headers)


def test_ntfy_is_rate_limited_and_survives_failures():
    calls = []

    def opener(request, timeout):
        calls.append(1)
        raise OSError("no network")

    notifier = NtfyNotifier("https://ntfy.sh/x", opener=opener, clock=lambda: 0.0, per_hour=2)
    assert not notifier.send("t", "x")
    assert notifier.failures == 1 and "no network" in notifier.info()["problem"]
    ok = NtfyNotifier("https://ntfy.sh/x", opener=lambda r, timeout: Response(), clock=lambda: 0.0, per_hour=2)
    assert ok.send("a", "b") and ok.send("a", "b") and not ok.send("a", "b")


@pytest.mark.parametrize("url", ["ftp://ntfy.sh/x", "https://ntfy.sh/", "https://user:pw@ntfy.sh/x", "https://ntfy.sh/x?email=me@example.com", "not a url"])
def test_bad_notice_addresses_are_refused(url):
    with pytest.raises(ValueError):
        check_url(url)


def test_notices_are_off_by_default():
    assert isinstance(notifier_from(None), NoNotifier)
    assert isinstance(notifier_from({"kind": "ntfy"}), NoNotifier)
    assert isinstance(notifier_from({"kind": "ntfy", "url": "https://ntfy.sh/x?y=1"}), NoNotifier)
    assert isinstance(notifier_from({"kind": "ntfy", "url": "https://ntfy.sh/pebble-x"}), NtfyNotifier)


def test_smoke_alone_stays_a_hint():
    fire = FireWatch()
    out = []
    for sight in sights(12, things=[thing("smoke", 3.0, height=0.4)]):
        out += fire.feed(sight, 1000.0, sight.at)
    assert [round(n.confidence, 2) for n in out] == [0.45, 0.7]
    assert fire.hold_reason(11.6) is None


def test_lookalikes_are_not_fire():
    fire = FireWatch()
    out = []
    for sight in sights(12, things=[thing("candle", 0.0, height=0.5), thing("fireplace", 10.0)]):
        out += fire.feed(sight, 1000.0, sight.at)
    assert out == []
