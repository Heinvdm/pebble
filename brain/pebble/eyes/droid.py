import logging
import time
from typing import Callable

from .sources import GrabbingSource, SourceError

log = logging.getLogger(__name__)

START_S = 10.0
STOP_S = 5.0
PULL_S = 0.5
DIRECTIONS = {"rear": 0, "front": 1}
FALLBACK_DEVICES = {"rear": 0, "front": 1}


def pipeline_text(device: int, width: int, height: int, exact: bool = True) -> str:
    if exact:
        size = f"video/x-raw,format=NV21,width={width},height={height}"
        scale = ""
    else:
        size = f"video/x-raw,format=NV21,width=[{width // 2},{width * 2}],height=[{height // 2},{height * 2}]"
        scale = f" ! videoscale ! video/x-raw,width={width},height={height}"
    return (
        f"droidcamsrc name=cam camera-device={int(device)} mode=2 cam.vfsrc ! {size}{scale} ! videoconvert ! "
        "video/x-raw,format=BGR ! appsink name=sink emit-signals=false max-buffers=1 drop=true sync=false"
    )


def frame_from(sample, np, read_flag):
    caps = sample.get_caps().get_structure(0)
    width, height = int(caps.get_value("width")), int(caps.get_value("height"))
    buffer = sample.get_buffer()
    ok, info = buffer.map(read_flag)
    if not ok:
        return None
    try:
        data = np.frombuffer(info.data, np.uint8)
        stride = data.size // height if height else 0
        if stride < width * 3:
            return None
        return data[: stride * height].reshape(height, stride)[:, : width * 3].reshape(height, width, 3).copy()
    finally:
        buffer.unmap(info)


_GST = None


def _gst():
    global _GST
    if _GST is None:
        try:
            import gi

            gi.require_version("Gst", "1.0")
            gi.require_version("GstApp", "1.0")
            from gi.repository import Gst, GstApp
        except (ImportError, ValueError) as error:
            raise SourceError("GStreamer for Python is missing (apt install python3-gi gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 gstreamer1.0-droid)") from error
        Gst.init(None)
        _GST = Gst
    return _GST


def find_device(camera: str, gst=None) -> int:
    Gst = gst or _gst()
    probe = Gst.ElementFactory.make("droidcamsrc", None)
    if probe is None:
        raise SourceError("this phone has no droidcamsrc (apt install gstreamer1.0-droid)")
    spec = probe.find_property("camera-device")
    if spec is None:
        raise SourceError("the phone's camera service was not running when Pebble started; restart Pebble once the phone is up")
    want = DIRECTIONS[camera]
    for device in range(int(spec.minimum), int(spec.maximum) + 1):
        probe.set_property("camera-device", device)
        probe.get_property("sensor-orientation")
        if int(probe.get_property("sensor-direction")) == want:
            return device
    return FALLBACK_DEVICES[camera]


class DroidSource(GrabbingSource):
    def __init__(self, camera: str, device="auto", width: int = 640, height: int = 480, monotonic: Callable[[], float] = time.monotonic, gst=None, numpy=None):
        super().__init__(camera, monotonic)
        self.device = device
        self.width, self.height = int(width), int(height)
        self._gst_module = gst
        self._np = numpy
        self._pipeline = None
        self._sink = None
        self._bus = None

    def _Gst(self):
        return self._gst_module or _gst()

    def _start_device(self) -> None:
        Gst = self._Gst()
        if self._np is None:
            import numpy

            self._np = numpy
        device = find_device(self.camera, Gst) if str(self.device) == "auto" else int(self.device)
        problem = "it would not start"
        for exact in (True, False):
            pipeline = Gst.parse_launch(pipeline_text(device, self.width, self.height, exact))
            bus = pipeline.get_bus()
            pipeline.set_state(Gst.State.PLAYING)
            result, _, _ = pipeline.get_state(int(START_S * Gst.SECOND))
            error = self._error(bus)
            if result != Gst.StateChangeReturn.FAILURE and error is None:
                self._pipeline, self._sink, self._bus = pipeline, pipeline.get_by_name("sink"), bus
                log.info("eyes: droidcamsrc camera-device=%s opened for the %s camera (%s size)", device, self.camera, "exact" if exact else "nearest")
                return
            problem = error or problem
            pipeline.set_state(Gst.State.NULL)
            pipeline.get_state(int(STOP_S * Gst.SECOND))
            if error and "negotiat" not in error.lower():
                break
        raise SourceError(f"the {self.camera} camera (camera-device {device}) is busy or unavailable: {problem}")

    def _error(self, bus) -> str | None:
        Gst = self._Gst()
        message = bus.pop_filtered(Gst.MessageType.ERROR) if bus is not None else None
        if message is None:
            return None
        error, detail = message.parse_error()
        return f"{getattr(error, 'message', error)}{f' ({detail})' if detail else ''}"

    def _grab(self):
        Gst = self._Gst()
        error = self._error(self._bus)
        if error is not None:
            raise SourceError(error)
        sample = self._sink.try_pull_sample(int(PULL_S * Gst.SECOND))
        if sample is None:
            return None
        return frame_from(sample, self._np, Gst.MapFlags.READ)

    def _stop_device(self) -> None:
        pipeline, self._pipeline, self._sink, self._bus = self._pipeline, None, None, None
        if pipeline is not None:
            Gst = self._Gst()
            pipeline.set_state(Gst.State.NULL)
            pipeline.get_state(int(STOP_S * Gst.SECOND))
