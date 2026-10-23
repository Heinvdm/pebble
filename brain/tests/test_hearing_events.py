import json

from pebble.hearing.audio import RATE, Block, to_samples
from pebble.hearing.events import HOP_S, RULES, BridgeModel, LocalModel, SoundEvents, load_labels
from pebble.hearing.fetch import MODELS

LABELS = ["Speech", "Glass", "Shatter", "Baby cry, infant cry", "Bark", "Dog", "Water tap, faucet", "Water", "Screaming", "Smoke detector, smoke alarm", "Fire alarm", "Shout", "Silence"]


def rows(seconds, scores: dict, start=0.0):
    out = []
    t = start
    while t < start + seconds:
        out.append((t, [scores.get(name, 0.0) for name in LABELS]))
        t += HOP_S
    return out


def events(feed):
    return [h.event for h in feed]


def test_one_strong_window_of_glass_is_enough():
    sounds = SoundEvents(LABELS)
    heard = sounds.feed(rows(0.5, {"Glass": 0.87}))
    assert events(heard) == ["glass"] and heard[0].confidence == 0.6
    assert sounds.feed(rows(1.0, {"Glass": 0.9}, start=1.0)) == []


def test_a_faint_glass_window_is_not_enough():
    assert SoundEvents(LABELS).feed(rows(0.3, {"Glass": 0.4})) == []


def test_a_baby_must_cry_for_more_than_a_minute():
    sounds = SoundEvents(LABELS)
    assert sounds.feed(rows(40, {"Baby cry, infant cry": 0.8})) == []
    heard = sounds.feed(rows(60, {"Baby cry, infant cry": 0.8}, start=40))
    assert events(heard) == ["baby"]


def test_a_dog_barking_on_and_off_for_two_minutes():
    sounds = SoundEvents(LABELS)
    out = []
    for i, row in enumerate(rows(130, {})):
        t, scores = row
        if (i // 3) % 3 != 2:
            scores = [0.9 if name == "Bark" else 0.0 for name in LABELS]
        out += sounds.feed([(t, scores)])
    assert events(out) == ["dog"]


def test_a_few_barks_are_nothing():
    sounds = SoundEvents(LABELS)
    out = sounds.feed(rows(10, {"Bark": 0.9})) + sounds.feed(rows(110, {}, start=10))
    assert out == []


def test_water_running_for_five_minutes():
    sounds = SoundEvents(LABELS)
    assert sounds.feed(rows(200, {"Water tap, faucet": 0.6})) == []
    assert events(sounds.feed(rows(120, {"Water tap, faucet": 0.6}, start=200))) == ["water"]


def test_the_sound_models_alarm_class_helps_the_fire_ladder():
    heard = SoundEvents(LABELS).feed(rows(4, {"Smoke detector, smoke alarm": 0.9}))
    assert events(heard) == ["alarm_sound"] and heard[0].confidence == 0.4


def test_rules_name_real_yamnet_classes():
    labels = load_labels(MODELS)
    assert len(labels) == 521
    missing = [name for rule in RULES for name in rule.classes if name not in labels]
    assert missing == []


class FakeModel:
    window = 15600
    labels = LABELS

    def __init__(self):
        self.calls = []

    def scores(self, samples):
        self.calls.append((len(samples), samples[0]))
        return [0.0] * len(LABELS)


def test_local_model_scores_the_first_full_window_then_every_hop():
    model = FakeModel()
    local = LocalModel(model)
    ramp = to_samples([i / 40000.0 for i in range(32000)])
    out = []
    for start in range(0, len(ramp), 4000):
        out += local.feed(Block(ramp[start : start + 4000], (start + 4000) / RATE))
    assert [round(t, 3) for t, _ in out] == [round(15600 / RATE, 3), round(23280 / RATE, 3), round(30960 / RATE, 3)]
    assert all(size == 15600 for size, _ in model.calls)
    assert abs(model.calls[0][1]) < 1e-3 and abs(model.calls[1][1] - 7680 / 40000.0) < 1e-3
    local.feed(Block(ramp[:100], 99.0, skipped=1000))
    assert local.total == 100


class FakeBridge:
    def __init__(self):
        self.total = 5

    def soundScores(self, start):
        rows = [[1000.0 + 480 * i, [0.5] * len(LABELS)] for i in range(max(0, start), self.total)] if start <= self.total else []
        return json.dumps({"total": self.total, "rows": rows, "now_ms": 4000.0})


def test_bridge_model_reads_only_new_rows():
    bridge = FakeBridge()
    model = BridgeModel(LABELS, bridge, monotonic=lambda: 10.0)
    assert model.feed() == []
    bridge.total = 7
    got = model.feed()
    assert len(got) == 2 and got[0][0] == 10.0 - (4000.0 - (1000.0 + 480 * 5)) / 1000.0
    assert model.feed() == []
