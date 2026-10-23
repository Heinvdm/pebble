import base64
import json
import struct

from pebble.hearing.events import EMBEDDING, KEEP_VECTORS, BridgeModel, unpack_vector

LABELS = ["Speech", "Silence"]


class Bridge:
    def __init__(self):
        self.total = 30
        self.asked = []

    def soundScores(self, start):
        return json.dumps({"total": 0, "rows": [], "now_ms": 0.0})

    def soundVectors(self, start):
        self.asked.append(start)
        rows = [[1000.0 + 480 * i, [0.25] * EMBEDDING] for i in range(max(0, start), self.total)] if start <= self.total else []
        return json.dumps({"total": self.total, "rows": rows, "now_ms": 1000.0 + 480 * self.total})


def test_the_phones_numbers_are_read_only_while_wanted_starting_with_the_recent_past():
    bridge = Bridge()
    model = BridgeModel(LABELS, bridge, monotonic=lambda: 50.0)
    assert model.take_vectors() == [] and bridge.asked == []
    model.want_vectors = True
    first = model.take_vectors()
    assert len(first) == KEEP_VECTORS and len(first[0][1]) == EMBEDDING
    bridge.total = 32
    assert len(model.take_vectors()) == 2
    model.want_vectors = False
    assert model.take_vectors() == []


def test_half_floats_and_bad_rows():
    values = [0.5] * EMBEDDING
    packed = "f16:" + base64.b64encode(struct.pack(f"<{EMBEDDING}e", *values)).decode("ascii")
    assert unpack_vector(packed) == values
    assert unpack_vector([1.0] * 3) is None
    assert unpack_vector("f16:!!!") is None
    assert unpack_vector(42) is None
