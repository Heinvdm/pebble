import threading

import pytest

from pebble.eyes.droid import DroidSource, find_device, pipeline_text
from pebble.eyes.sources import SourceError

np = pytest.importorskip("numpy")


class Spec:
    minimum = 0
    maximum = 2


class Probe:
    def __init__(self, directions, has_property=True):
        self.directions = directions
        self.has_property = has_property
        self.device = 0
        self.reads = []

    def find_property(self, name):
        return Spec() if self.has_property and name == "camera-device" else None

    def set_property(self, name, value):
        self.device = value

    def get_property(self, name):
        self.reads.append(name)
        if name == "sensor-direction":
            assert "sensor-orientation" in self.reads
            return self.directions[self.device]
        return 90


class Message:
    def __init__(self, text):
        self.text = text

    def parse_error(self):
        return type("E", (), {"message": self.text})(), "droidcamsrc"


class Bus:
    def __init__(self, errors):
        self.errors = errors

    def pop_filtered(self, kind):
        return Message(self.errors.pop(0)) if self.errors else None


class Info:
    def __init__(self, data):
        self.data = data


class Buffer:
    def __init__(self, data):
        self.data = data
        self.unmapped = False

    def map(self, flag):
        assert flag == "READ"
        return True, Info(self.data)

    def unmap(self, info):
        self.unmapped = True


class Caps:
    def __init__(self, width, height):
        self.values = {"width": width, "height": height}

    def get_structure(self, index):
        return self

    def get_value(self, name):
        return self.values[name]


class Sample:
    def __init__(self, width, height, stride):
        rows = np.zeros((height, stride), np.uint8)
        rows[:, : width * 3] = np.arange(width * 3, dtype=np.uint16) % 251
        self.buffer = Buffer(rows.tobytes())
        self.caps = Caps(width, height)

    def get_caps(self):
        return self.caps

    def get_buffer(self):
        return self.buffer


class Sink:
    def __init__(self, pipeline):
        self.pipeline = pipeline

    def try_pull_sample(self, timeout):
        if self.pipeline.state != "PLAYING":
            return None
        return Sample(*self.pipeline.gst.size)


class Pipeline:
    def __init__(self, gst, text):
        self.gst = gst
        self.text = text
        self.state = "NULL"
        self.states = []
        self.bus = Bus(list(gst.errors.pop(0)) if gst.errors else [])

    def get_bus(self):
        return self.bus

    def set_state(self, state):
        self.states.append(state)
        self.state = state

    def get_state(self, timeout):
        return ("FAILURE" if self.bus.errors and self.state == "PLAYING" else "SUCCESS"), self.state, None

    def get_by_name(self, name):
        return Sink(self)


class FakeGst:
    SECOND = 1_000_000_000

    class State:
        PLAYING = "PLAYING"
        NULL = "NULL"

    class StateChangeReturn:
        FAILURE = "FAILURE"

    class MessageType:
        ERROR = "ERROR"

    class MapFlags:
        READ = "READ"

    def __init__(self, errors=None, directions=(0, 1, 1), size=(64, 48, 64 * 3 + 8), has_property=True):
        self.errors = list(errors or [])
        self.pipelines = []
        self.size = size
        self.probe = Probe(directions, has_property)
        gst = self

        class Factory:
            @staticmethod
            def make(name, label):
                return gst.probe if name == "droidcamsrc" else None

        self.ElementFactory = Factory

    def parse_launch(self, text):
        pipeline = Pipeline(self, text)
        self.pipelines.append(pipeline)
        return pipeline


def test_the_pipeline_asks_for_a_small_cpu_picture():
    text = pipeline_text(2, 640, 480)
    assert "droidcamsrc name=cam camera-device=2 mode=2 cam.vfsrc" in text
    assert "video/x-raw,format=NV21,width=640,height=480 ! videoconvert" in text
    assert "format=BGR ! appsink name=sink" in text and "max-buffers=1 drop=true sync=false" in text
    loose = pipeline_text(0, 640, 480, exact=False)
    assert "width=[320,1280],height=[240,960] ! videoscale ! video/x-raw,width=640,height=480" in loose


def test_cameras_are_found_by_the_way_they_face():
    gst = FakeGst(directions=(1, 0, 0))
    assert find_device("front", gst) == 0 and find_device("rear", gst) == 1
    with pytest.raises(SourceError, match="camera service"):
        find_device("rear", FakeGst(has_property=False))


def test_frames_come_out_as_upright_bgr_arrays_even_with_padded_rows():
    gst = FakeGst()
    source = DroidSource("rear", "auto", 64, 48, gst=gst, numpy=np)
    source.open()
    try:
        frame = source.read(2.0)
        assert frame is not None and frame.camera == "rear"
        assert frame.image.shape == (48, 64, 3) and frame.image.dtype == np.uint8
        assert frame.image[0, 1, 0] == 3 and frame.image[5, 63, 2] == (63 * 3 + 2) % 251
        assert "camera-device=0" in gst.pipelines[0].text
    finally:
        source.close()
    assert gst.pipelines[0].states[-1] == "NULL"


def test_a_busy_camera_is_a_clear_failure_and_is_let_go():
    gst = FakeGst(errors=[["error opening camera"]])
    source = DroidSource("front", 1, gst=gst, numpy=np)
    with pytest.raises(SourceError, match="busy or unavailable: error opening camera"):
        source.open()
    assert len(gst.pipelines) == 1 and gst.pipelines[0].states == ["PLAYING", "NULL"]


def test_a_size_the_camera_lacks_falls_back_to_the_nearest_one():
    gst = FakeGst(errors=[["failed to negotiate caps"]])
    source = DroidSource("front", 1, 640, 480, gst=gst, numpy=np)
    source.open()
    try:
        assert len(gst.pipelines) == 2 and "videoscale" in gst.pipelines[1].text
    finally:
        source.close()


def test_an_error_while_running_stops_the_source():
    gst = FakeGst()
    source = DroidSource("front", 1, gst=gst, numpy=np)
    source.open()
    try:
        assert source.read(2.0) is not None
        gst.pipelines[0].bus.errors.append("the camera service died")
        with pytest.raises(SourceError, match="died"):
            for _ in range(50):
                source.read(0.2)
    finally:
        source.close()
    assert not any(t.name.startswith("pebble-eyes-front") and t.is_alive() for t in threading.enumerate())
