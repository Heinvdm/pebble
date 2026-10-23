import sys
from pathlib import Path

from ..eyes import fetch as shared
from ..eyes.fetch import Asset

VENDOR = Path(__file__).resolve().parent / "vendor"
MEDIAPIPE = "1.0.1"
APRILTAG_PORT = "f0fe55676265a1251ad36f18bac9939206a59e19"
APRILTAG_LIB = "4cdba6a8c6cf4efeb032fa5542da927d4677c035"
JSDELIVR = f"https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@{MEDIAPIPE}"
MODELS = "https://storage.googleapis.com/mediapipe-models"
PORT_RAW = f"https://raw.githubusercontent.com/arenaxr/apriltag-js-standalone/{APRILTAG_PORT}"
LIB_RAW = f"https://raw.githubusercontent.com/WiseLabCMU/apriltag/{APRILTAG_LIB}"
TAG_LICENCE = "BSD-3-Clause (port), BSD-2-Clause (AprilTag)"

ASSETS = (
    Asset("vision", f"mediapipe-{MEDIAPIPE}/vision_bundle.js", f"{JSDELIVR}/vision_bundle.js", "98db72469ffb176f5e9f2687be0f70783893aca681f7789c34b872b0a764371a", 155465, "Apache-2.0"),
    Asset("vision_loader", f"mediapipe-{MEDIAPIPE}/vision_wasm_internal.js", f"{JSDELIVR}/wasm/vision_wasm_internal.js", "e170ee67dd4e16c1a6fcd8840a206687e5a59b22c20e4a902bc445b095454d73", 323377, "Apache-2.0"),
    Asset("vision_wasm", f"mediapipe-{MEDIAPIPE}/vision_wasm_internal.wasm", f"{JSDELIVR}/wasm/vision_wasm_internal.wasm", "8da277a733926eacd0474b8704b36742d6ec3231c57a860c5b889dff8f1df886", 11756954, "Apache-2.0"),
    Asset("face_model", "models/blaze_face_short_range.tflite", f"{MODELS}/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite", "b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f", 229746, "Apache-2.0"),
    Asset("body_model", "models/efficientdet_lite0_int8.tflite", f"{MODELS}/object_detector/efficientdet_lite0/int8/1/efficientdet_lite0.tflite", "0720bf247bd76e6594ea28fa9c6f7c5242be774818997dbbeffc4da460c723bb", 4602795, "Apache-2.0"),
    Asset("tag_loader", f"apriltag-{APRILTAG_PORT[:7]}/apriltag_wasm.js", f"{PORT_RAW}/html/apriltag_wasm.js", "587c3b98f7e9a312d9f69dbb541c91741f9ee2df10c356362b05243041e3ddea", 74548, TAG_LICENCE),
    Asset("tag_wasm", f"apriltag-{APRILTAG_PORT[:7]}/apriltag_wasm.wasm", f"{PORT_RAW}/html/apriltag_wasm.wasm", "0283215c40f3bcd265d2650aeb0d4419e87222830fe8a31a1978401a4cac77aa", 118923, TAG_LICENCE),
    Asset("tag_port_licence", f"apriltag-{APRILTAG_PORT[:7]}/LICENSE", f"{PORT_RAW}/LICENSE", "14b8f722e667e13c43a3b5e15283e92ec9a8e3b9d728eca6571d4d3a73a723a7", 1532, "BSD-3-Clause"),
    Asset("tag_lib_licence", f"apriltag-{APRILTAG_PORT[:7]}/APRILTAG_LICENSE.md", f"{LIB_RAW}/LICENSE.md", "3a99f2b7797dfbe2fd36e374e0123c06089fa49e6d7e44b3406570f758105d0b", 1357, "BSD-2-Clause"),
    Asset("sample_portrait", "samples/portrait.jpg", shared.SAMPLE_PORTRAIT, "a6f11efaa834706db23f275b6115058fa87fc7f14362681e6abe14e82749de3e", 176561, "public domain (official White House portrait)", sample=True),
)


def paths() -> dict[str, str]:
    return {a.key: f"vendor/{a.path}" for a in ASSETS}


def ready(vendor: Path = VENDOR) -> bool:
    return shared.ready(ASSETS, vendor)


def main(argv: list[str] | None = None) -> int:
    return shared.cli(argv, ASSETS, VENDOR, "python -m pebble.web.fetch_eyes", "the files the face page needs to see by itself (MediaPipe, its models, the AprilTag detector; the Android route)")


if __name__ == "__main__":
    sys.exit(main())
