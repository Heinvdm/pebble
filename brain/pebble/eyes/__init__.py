import logging
from pathlib import Path
from typing import Callable

from ..clock import Clock
from ..seams.sight import CAMERAS, DOCK_TAG_ID, DOCK_TAG_SIZE_M, NoEyes
from .scene import TagPlacement
from .service import CameraEyes, camera_settings
from .sources import FrameSource, OpenCVSource, SceneSource, SourceError, StillSource

log = logging.getLogger(__name__)

SOURCES = ("droid", "v4l2", "scene", "image", "browser", "android", "none")
DEFAULT_DEVICES = {"droid": {"front": "auto", "rear": "auto"}, "v4l2": {"front": 0, "rear": 1}}


def make_sources(kind: str, cameras: dict, config: dict | None = None, monotonic: Callable[[], float] | None = None) -> Callable[[str], FrameSource]:
    config = dict(config or {})
    extra = {"monotonic": monotonic} if monotonic is not None else {}

    def source(camera: str) -> FrameSource:
        settings = cameras[camera]
        width, height = settings["width"], settings["height"]
        device = settings.get("device", "auto")
        if str(device) == "auto" and kind != "droid":
            device = DEFAULT_DEVICES["v4l2"][camera]
        if kind == "droid":
            from .droid import DroidSource

            return DroidSource(camera, device, width, height, **extra)
        if kind == "v4l2":
            return OpenCVSource(camera, device, width, height, **extra)
        if kind == "image":
            picture = settings.get("image") or config.get("image")
            if not picture:
                raise SourceError(f"no picture set for the {camera} camera")
            return StillSource(camera, picture, size=(width, height), **extra)
        if kind == "scene":
            scenes = config.get("scene") if isinstance(config.get("scene"), dict) else {}
            placement = scenes.get(camera)
            if placement is None and settings.get("image"):
                return StillSource(camera, settings["image"], size=(width, height), **extra)
            if placement is None and camera == "rear":
                placement = {}
            tag = None if placement is None else TagPlacement(**{k: float(v) for k, v in placement.items() if k in TagPlacement.__dataclass_fields__})
            return SceneSource(camera, width, height, settings["fov_h_deg"], tag, **extra)
        raise SourceError(f"unknown camera source {kind!r}")

    return source


def eyes_from_config(
    config: dict | None,
    clock: Clock | None = None,
    hub=None,
    on_look: Callable | None = None,
    enabled: bool = True,
    camera: str = "front",
    models: Path | None = None,
    start: bool = True,
):
    config = dict(config or {})
    clock = clock or Clock()
    kind = str(config.get("source", "none"))
    cameras = camera_settings({name: config[name] for name in CAMERAS if isinstance(config.get(name), dict)})
    tag_size = float(config.get("tag_size_m", DOCK_TAG_SIZE_M))
    if kind == "none":
        return NoEyes()
    if kind == "browser":
        if hub is None:
            log.warning("eyes: the browser route needs the face page (--screen); Pebble has no eyes")
            return NoEyes()
        from ..web.eyes import BrowserEyes

        page = {name: {"fov_h_deg": values["fov_h_deg"], "mirror": values["mirror"], "rotate": values["rotate"] or None} for name, values in cameras.items()}
        return BrowserEyes(hub, clock, cameras=page, tag_size_m=tag_size, enabled=enabled, camera=camera)
    if kind == "android":
        return android_eyes(config, cameras, clock, hub, on_look, enabled, camera, models, start, tag_size)
    if kind not in SOURCES:
        log.warning("eyes: unknown camera source %r; Pebble has no eyes", kind)
        return NoEyes()
    from .detect import Detector, NoOpenCV
    from .fetch import MODELS

    try:
        detector = Detector(models=models or MODELS, tag_id=int(config.get("tag_id", DOCK_TAG_ID)), tag_size_m=tag_size, threads=int(config.get("threads", 2)), face_width=int(config.get("face_width", 320)))
    except NoOpenCV as error:
        log.warning("eyes: %s; Pebble has no eyes", error)
        return NoEyes()
    on_camera = None
    if hub is not None:
        from ..web.look import LookPush

        push = LookPush(hub)
        on_look, on_camera = on_look or push, push.camera
    eyes = CameraEyes(make_sources(kind, cameras, config, clock.monotonic), detector, clock, cameras, camera, enabled, float(config.get("max_fps", 10)), on_look=on_look, on_camera=on_camera, slow=slow_lane(config, models or MODELS, clock), pose=pose_model(config, models or MODELS), prints=print_model(config, models or MODELS), pose_hz=float(config.get("pose_hz", 5.0)), hazards=hazard_watch(config, models or MODELS, clock), speaking=speaking_meter(config, models or MODELS, clock), floor=floor_scan(config, models or MODELS, clock), undress=undress_watch(config, models or MODELS, clock))
    if start:
        eyes.start()
    return eyes


def undress_watch(config: dict, models: Path, clock: Clock):
    if not config.get("undress", True):
        return None
    from .undress import MODEL, UndressModel, UndressWatch

    path = Path(models) / MODEL
    if not path.exists():
        log.warning("eyes: no privacy cue model (%s); Pebble looks away only when asked, in private rooms, or by the words it sees; run python -m pebble.eyes.fetch", path.name)
        return None
    threads = int(config.get("undress_threads", 1))
    return UndressWatch(lambda: UndressModel(path, threads, str(config.get("undress_backend", "auto"))), clock.monotonic, every_s=float(config.get("undress_every_s", 1.0)))


def android_eyes(config: dict, cameras: dict, clock: Clock, hub, on_look, enabled: bool, camera: str, models: Path | None, start: bool, tag_size: float):
    from ..android.bridge import NoBridge
    from .android import AndroidEyes, load_words
    from .fetch import MODELS

    on_camera = None
    if hub is not None:
        from ..web.look import LookPush

        push = LookPush(hub)
        on_look, on_camera = on_look or push, push.camera
    slow = {key: value for key, value in config.items() if key.startswith("slow")}
    eyes = AndroidEyes(
        clock,
        cameras,
        camera,
        enabled,
        int(config.get("tag_id", DOCK_TAG_ID)),
        tag_size,
        float(config.get("max_fps", 10)),
        slow=slow,
        hazards={key: value for key, value in config.items() if key.startswith("hazard")},
        speaking={key: value for key, value in config.items() if key.startswith("speaking")},
        floor={key: value for key, value in config.items() if key.startswith("floor")},
        words=load_words(Path(models or MODELS) / "objects_vocab.json"),
        on_look=on_look,
        on_camera=on_camera,
        detect=config.get("detect") if isinstance(config.get("detect"), dict) else None,
    )
    if start:
        try:
            eyes.start()
        except NoBridge as error:
            log.warning("eyes: %s; Pebble has no eyes", error)
            return NoEyes()
        except Exception as error:
            log.warning("eyes: the phone's cameras could not start (%s); Pebble has no eyes", error)
            return NoEyes()
    return eyes


def pose_model(config: dict, models: Path):
    if not config.get("pose", True):
        return None
    from .pose import NoPoseModel, PoseModel

    try:
        return PoseModel(Path(models) / "rtmpose_t_body7_256x192.onnx", str(config.get("pose_backend", "auto")), int(config.get("pose_threads", 1)))
    except NoPoseModel as error:
        log.warning("eyes: no body points: %s", error)
        return None


def print_model(config: dict, models: Path):
    if not config.get("prints", True):
        return None
    model, meta = Path(models) / "prints.onnx", Path(models) / "prints.json"
    if not model.exists():
        log.warning("eyes: no print model in %s (tools/export_prints.py makes it); Pebble cannot tell one thing from another of its kind", models)
        return None
    threads = int(config.get("print_threads", 2))

    def make():
        from .prints import PrintModel

        return PrintModel(model, meta, threads)

    return make


def floor_scan(config: dict, models: Path, clock: Clock):
    if not config.get("floor", True):
        return None
    from .floor import DepthModel, FloorScan

    path = Path(models) / "depth_anything_v2_small.onnx"
    if not path.exists():
        log.warning("eyes: no floor scan: the depth model is missing (%s); run python -m pebble.eyes.fetch", path.name)
        return None
    threads = int(config.get("floor_threads", 2))
    gate = str(config.get("floor_gate", "moving"))
    return FloorScan(lambda: DepthModel(path, threads), clock.monotonic, every_s=float(config.get("floor_every_s", 0.2)), reach_m=float(config.get("floor_reach_m", 2.0)), bins=int(config.get("floor_bins", 32)), gate=gate if gate in ("moving", "always", "off") else "moving")


def speaking_meter(config: dict, models: Path, clock: Clock):
    if not config.get("speaking", True):
        return None
    from .speaking import MouthModel, NoMouthModel, SpeakingMeter

    path = Path(models) / "face_landmarks_detector.tflite"
    threads = int(config.get("speaking_threads", 1))
    try:
        MouthModel(path, threads)
    except NoMouthModel as error:
        log.warning("eyes: no speaking: %s", error)
        return None
    gate = "always" if str(config.get("speaking_gate", "voice")) == "always" else "voice"
    return SpeakingMeter(lambda: MouthModel(path, threads), gate=gate, max_faces=int(config.get("speaking_faces", 2)), monotonic=clock.monotonic)


def hazard_watch(config: dict, models: Path, clock: Clock):
    if not config.get("hazards", True):
        return None
    model, vocab = Path(models) / "hazards.onnx", Path(models) / "hazards_vocab.json"
    if not model.exists() or not vocab.exists():
        log.warning("eyes: no hazard model in %s (tools/export_hazards.py makes it); Pebble cannot watch for smoke and flames", models)
        return None
    from .hazards import HazardWatch
    from .slow import SlowDetector

    threads = int(config.get("hazard_threads", 1))
    return HazardWatch(lambda: SlowDetector(model, vocab, "auto", threads, float(config.get("hazard_score", 0.25))), clock.monotonic, every_s=float(config.get("hazard_every_s", 3.0)))


def slow_lane(config: dict, models: Path, clock: Clock):
    if not config.get("slow", True):
        return None
    from .slow import SlowDetector, SlowLane

    model, vocab = Path(models) / "objects.onnx", Path(models) / "objects_vocab.json"
    if not model.exists() or not vocab.exists():
        log.warning("eyes: no slow-lane model in %s (tools/export_objects.py makes it); only the 80 everyday things are named", models)
        return None
    backend = str(config.get("slow_backend", "auto"))
    threads = int(config.get("slow_threads", 1))
    score = float(config.get("slow_score", 0.45))
    return SlowLane(
        lambda: SlowDetector(model, vocab, backend, threads, score),
        clock.monotonic,
        every_s=float(config.get("slow_every_s", 1.0)),
        keep_s=float(config.get("slow_keep_s", 3.0)),
        change=float(config.get("slow_change", 0.06)),
        nice=int(config.get("slow_nice", 10)),
    )


def close_eyes(eyes) -> None:
    close = getattr(eyes, "close", None)
    if callable(close):
        close()


__all__ = ["CameraEyes", "FrameSource", "SourceError", "close_eyes", "eyes_from_config", "make_sources"]
