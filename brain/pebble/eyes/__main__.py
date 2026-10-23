import argparse
import logging
import sys
import time

from ..body.profile import BodyProfile, resolve_profile
from ..clock import Clock
from ..seams.sight import DOCK_TAG_SIZE_M
from . import SOURCES, make_sources
from .detect import Detector, NoOpenCV
from .service import CameraEyes, camera_settings, orient
from .sources import SourceError


def hints(detector: Detector, image, fov: float) -> list[str]:
    found = detector.tags(image, fov)
    if found:
        roll = found[0].roll_deg
        turn = round(-roll / 90.0) * 90 % 360
        if turn:
            return [f"the tag looks turned by {roll:.0f} degrees; if it hangs upright, add {turn} to this camera's rotate"]
        return []
    if detector.tags(image[:, ::-1].copy(), fov):
        return ["the tag only reads in a mirror: set this camera's mirror to true (or false if it is true)"]
    return []


def check(config: dict, camera: str, seconds: float) -> int:
    clock = Clock()
    cameras = camera_settings({name: config[name] for name in ("front", "rear") if isinstance(config.get(name), dict)})
    try:
        detector = Detector(tag_size_m=float(config.get("tag_size_m", DOCK_TAG_SIZE_M)), threads=int(config.get("threads", 2)))
    except NoOpenCV as error:
        print(error)
        return 2
    print("can see:", ", ".join(k for k, v in detector.can.items() if v) or "nothing", "| problems:", "; ".join(detector.problems) or "none")
    eyes = CameraEyes(lambda name: None, detector, clock, cameras)
    slow = None
    if config.get("slow", True):
        from .fetch import MODELS
        from .slow import NoSlowModel, SlowDetector

        try:
            slow = SlowDetector(MODELS / "objects.onnx", MODELS / "objects_vocab.json", str(config.get("slow_backend", "auto")), int(config.get("slow_threads", 1)))
            print(f"slow lane: {len(slow.classes)} words, {slow.size} px, {slow.backend}")
        except NoSlowModel as error:
            print(f"slow lane off: {error}")
    hazards = None
    if config.get("hazards", True):
        from . import hazard_watch
        from .fetch import MODELS

        hazards = hazard_watch(config, MODELS, clock)
        print("hazard watch:", "on" if hazards is not None else "off (no hazard model)")
    started = time.monotonic()
    try:
        source = make_sources(str(config.get("source")), cameras, config, clock.monotonic)(camera)
        source.open()
    except SourceError as error:
        print(f"the {camera} camera would not open: {error}")
        return 1
    print(f"the {camera} camera opened in {time.monotonic() - started:.1f} s; frames are looked at and dropped, never kept")
    settings = cameras[camera]
    frames, said, closely = 0, set(), 0.0
    try:
        until = time.monotonic() + seconds
        next_line = time.monotonic() + 1.0
        while time.monotonic() < until:
            frame = source.read(1.0)
            if frame is None:
                continue
            frames += 1
            sight = eyes.process(frame)
            if hazards is not None:
                hazards.offer(orient(frame.image, settings["rotate"], settings["mirror"]), camera, frame.captured, 0.0, settings["fov_h_deg"])
            if time.monotonic() < next_line:
                continue
            next_line = time.monotonic() + 1.0
            image = orient(frame.image, settings["rotate"], settings["mirror"])
            height, width = image.shape[:2]
            people = "; ".join(f"{'face' if p.face else 'body'} #{p.track} at {p.bearing_deg:+.0f} deg, up {p.elevation_deg:+.0f}, {p.height_frac:.2f} tall" for p in sight.people) or "nobody"
            tags = "; ".join(f"tag {t.id}: {t.distance_m:.2f} m at {t.bearing_deg:+.1f} deg, turned {t.yaw_deg:+.0f} deg (trust {t.score:.2f})" for t in sight.tags) or "no tag"
            things = ", ".join(f"{t.label}{'*' if t.animal else ''} {t.bearing_deg:+.0f} deg" for t in sight.things) or "no things"
            print(f"{width}x{height} {frames} frames | {people} | {things} | {tags} | ms {eyes.status()['ms']}")
            if slow is not None and time.monotonic() >= closely:
                begun = time.perf_counter()
                found = slow.detect(image)
                took = (time.perf_counter() - begun) * 1000
                closely = time.monotonic() + 2.0
                print(f"  slow lane {took:.0f} ms: " + (", ".join(f"{f.label} {f.box.score:.2f}" for f in found) or "nothing"))
            if hazards is not None and time.monotonic() >= closely - 1.0:
                try:
                    found = hazards.look(image, camera, frame.captured, 0.0, settings["fov_h_deg"])
                except Exception as error:
                    print(f"  hazard watch off: {error}")
                    hazards = None
                    continue
                state = hazards.status()
                print(f"  hazards {state['ms']:.0f} ms{' (watching closely)' if state['close_watch'] else ''}: " + (", ".join(f"{t.label} {t.box.score:.2f}" for t in found) or "nothing"))
            for line in hints(detector, image, settings["fov_h_deg"]):
                if line not in said:
                    said.add(line)
                    print("hint:", line)
    except SourceError as error:
        print(f"the camera stopped: {error}")
        return 1
    finally:
        source.close()
    print(f"{frames / max(0.1, seconds):.1f} frames a second")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.eyes", description="Check Pebble's eyes on this phone: print what each camera sees, as numbers only.")
    sub = parser.add_subparsers(dest="command", required=True)
    look = sub.add_parser("check", help="open one camera and print what it sees")
    look.add_argument("--body", default="droidian", help="body profile name or path (default droidian)")
    look.add_argument("--source", choices=SOURCES[:4], help="override the profile's camera source")
    look.add_argument("--camera", choices=("front", "rear"), default="front")
    look.add_argument("--seconds", type=float, default=15.0)
    look.add_argument("--picture", help="a photo to look at instead of a camera (sets --source image)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    config = dict(BodyProfile.load(resolve_profile(args.body, "body")).eyes)
    if args.source:
        config["source"] = args.source
    if args.picture:
        config["source"], config["image"] = "image", args.picture
    if config.get("source") not in SOURCES[:4]:
        print(f"the {args.body} profile has no camera source this check can open ({config.get('source')!r})")
        return 2
    return check(config, args.camera, args.seconds)


if __name__ == "__main__":
    sys.exit(main())
