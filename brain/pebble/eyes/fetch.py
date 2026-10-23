import argparse
import hashlib
import io
import os
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

MODELS = Path(__file__).resolve().parent / "models"
ZOO_COMMIT = "47534e27c9851bb1128ccc0102f1145e27f23f98"
ZOO_LFS = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{ZOO_COMMIT}/models"
ZOO_RAW = f"https://raw.githubusercontent.com/opencv/opencv_zoo/{ZOO_COMMIT}/models"
SAMPLE_PORTRAIT = "https://storage.googleapis.com/mediapipe-assets/portrait.jpg"
COMMONS = "https://upload.wikimedia.org/wikipedia/commons"
MADE_HERE = "made by tools/export_objects.py (YOLOE-26n prompt-free, 416 px, home vocabulary); copy it along with the brain"
MADE_HAZARDS = "made by tools/export_hazards.py (YOLOE-26s prompt-free, 416 px, its own words for fire, smoke and their lookalikes); copy it along with the brain"
MADE_PRINTS = "made by tools/export_prints.py (DINOv2-small, any picture size, int8); copy it along with the brain"
DEPTH = "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/4472b7362082ad9968fee890ca0f1e5aca36b93d/onnx/model.onnx"
FACE_MESH = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
RTMPOSE = "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/rtmpose-t_simcc-body7_pt-body7_420e-256x192-026a1439_20230504.zip"
NUDENET = "https://files.pythonhosted.org/packages/1c/ee/1aa02d44ba958cc77e16ff1e41a0aac5e721037db7bf62b9c9d124917f87/nudenet-3.4.2-py3-none-any.whl"
CHUNK = 1 << 16
TIMEOUT_S = 60


@dataclass(frozen=True)
class Asset:
    key: str
    path: str
    url: str
    sha256: str
    size: int
    licence: str
    sample: bool = False
    made: str = ""
    member: str = ""
    archive_sha256: str = ""
    archive_size: int = 0


ASSETS = (
    Asset("face", "face_detection_yunet_2023mar.onnx", f"{ZOO_LFS}/face_detection_yunet/face_detection_yunet_2023mar.onnx", "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4", 232589, "MIT"),
    Asset("face_licence", "YUNET_LICENSE", f"{ZOO_RAW}/face_detection_yunet/LICENSE", "c83b8120c50ccbd4c4f96edf53141bdd566ebb8f8e9227e415326aa1b1aba958", 1085, "MIT"),
    Asset("body", "object_detection_nanodet_2022nov.onnx", f"{ZOO_LFS}/object_detection_nanodet/object_detection_nanodet_2022nov.onnx", "4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186", 3800954, "Apache-2.0"),
    Asset("body_licence", "NANODET_LICENSE", f"{ZOO_RAW}/object_detection_nanodet/LICENSE", "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30", 11358, "Apache-2.0"),
    Asset("slow", "objects.onnx", "", "3253625e623bfeabee69c9fcdc92d3d25de897e6a8f2f67620d54ce2a5545815", 12335964, "AGPL-3.0 (YOLOE, THU-MIG; Ultralytics)", made=MADE_HERE),
    Asset("slow_vocab", "objects_vocab.json", "", "dd78badf0cda6a667a3b3121226923a8ff4cd4f9426bfad5086f3ce90754662a", 193437, "AGPL-3.0 (YOLOE, THU-MIG; Ultralytics)", made=MADE_HERE),
    Asset("hazards", "hazards.onnx", "", "1e7d128ee4f48101c493aa015d16ad33ace37cf887d1bfe03b9b9f3049f1ab95", 39238654, "AGPL-3.0 (YOLOE, THU-MIG; Ultralytics)", made=MADE_HAZARDS),
    Asset("hazards_vocab", "hazards_vocab.json", "", "94c78dfb3d9c39dc59e461e4fea895cf41d7e04924834a222ee2a4a61fbfe9b7", 3469, "AGPL-3.0 (YOLOE, THU-MIG; Ultralytics)", made=MADE_HAZARDS),
    Asset("pose", "rtmpose_t_body7_256x192.onnx", RTMPOSE, "a6c2f6a3896a4d51131d14d7a80a3d08b50f559af5a58a45d5b098aef510a70f", 13350364, "Apache-2.0 (RTMPose, OpenMMLab MMPose)", member="20230831/rtmpose_onnx/rtmpose-t_simcc-body7_pt-body7_420e-256x192-026a1439_20230504/end2end.onnx", archive_sha256="937003a70832d9cc34ea16927f504792f3133e92dda1b9c626236bbbe9e805cb", archive_size=12547710),
    Asset("mouth", "face_landmarks_detector.tflite", FACE_MESH, "c7d54204ce0448474c7f3fa9af494787c0965cbdd6f20fc72867e43046bd43d5", 2553590, "Apache-2.0 (MediaPipe Face Landmarker, Google)", member="face_landmarks_detector.tflite", archive_sha256="64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff", archive_size=3758596),
    Asset("undress", "nudenet_320n.onnx", NUDENET, "c15d8273adad2d0a92f014cc69ab2d6c311a06777a55545f2c4eb46f51911f0f", 12150158, "AGPL-3.0 (NudeNet 320n, notAI-tech; built on Ultralytics YOLOv8n)", member="nudenet/320n.onnx", archive_sha256="5937dbd84e5d8e5de038f08ffea5a1bb50a08475776bf2b4795914ce0eaf0331", archive_size=10595223),
    Asset("depth", "depth_anything_v2_small.onnx", DEPTH, "afb6a5c28f3b6bf1618c6e43f02073ef9dfdc70e937502d51603e57b0a1df10c", 99060839, "Apache-2.0 (Depth Anything V2 Small; ONNX export by onnx-community)"),
    Asset("prints", "prints.onnx", "", "f811bf2d9bd546975ff1332b6a8174d3c678956b22725456a68d9fba1ae91085", 24195033, "Apache-2.0 (DINOv2, Meta)", made=MADE_PRINTS),
    Asset("prints_meta", "prints.json", "", "d9752cda61e00f5d7e10ecaa16078637d8f5d977e0e1f6807d553a12d3fd34da", 321, "Apache-2.0 (DINOv2, Meta)", made=MADE_PRINTS),
    Asset("sample_portrait", "samples/portrait.jpg", SAMPLE_PORTRAIT, "a6f11efaa834706db23f275b6115058fa87fc7f14362681e6abe14e82749de3e", 176561, "public domain (official White House portrait)", sample=True),
    Asset("sample_desk", "samples/desk.jpg", f"{COMMONS}/3/38/Home-office-336377.jpg", "408a37024c494dab9942655bdf0e1de5861b874a15edffa32ec451e5b1046d36", 1651458, "CC0 (Wikimedia Commons, Home-office-336377.jpg)", sample=True),
    Asset("sample_cat", "samples/cat.jpg", f"{COMMONS}/9/97/Black_cat_curled_up_on_a_sofa_in_Newcastle_upon_Tyne%2C_UK.jpg", "4aa132fd50523f458d5dccecadcd1ab254e3c028434237a8940af51eb9ab93e7", 943595, "CC0 (Wikimedia Commons, Black cat curled up on a sofa in Newcastle upon Tyne, UK.jpg)", sample=True),
)


class FetchError(Exception):
    pass


def wanted(assets: Iterable[Asset], samples: bool = False) -> tuple[Asset, ...]:
    return tuple(a for a in assets if samples or not a.sample)


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            sha.update(chunk)
    return sha.hexdigest()


def present(asset: Asset, folder: Path, deep: bool = False) -> bool:
    target = Path(folder) / asset.path
    try:
        if target.stat().st_size != asset.size:
            return False
    except OSError:
        return False
    return not deep or digest(target) == asset.sha256


def ready(assets: Iterable[Asset], folder: Path) -> bool:
    return all(present(a, folder) for a in wanted(assets) if a.url)


def _open(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "pebble-fetch/1 (personal robot)"})
    return urllib.request.urlopen(request, timeout=TIMEOUT_S)


def _pull(url: str, size: int, sha256: str, opener: Callable, label: str) -> bytes:
    sha = hashlib.sha256()
    data = bytearray()
    with opener(url) as response:
        for chunk in iter(lambda: response.read(CHUNK), b""):
            data.extend(chunk)
            if len(data) > size:
                raise FetchError(f"{label}: bigger than the pinned {size} bytes")
            sha.update(chunk)
    if len(data) != size or sha.hexdigest() != sha256:
        raise FetchError(f"{label}: got {len(data)} bytes with SHA-256 {sha.hexdigest()}, expected {size} bytes with {sha256}")
    return bytes(data)


def download(asset: Asset, folder: Path, opener: Callable = _open) -> Path:
    target = Path(folder) / asset.path
    target.parent.mkdir(parents=True, exist_ok=True)
    if asset.member:
        archive = _pull(asset.url, asset.archive_size, asset.archive_sha256, opener, asset.url.rsplit("/", 1)[-1])
        try:
            data = zipfile.ZipFile(io.BytesIO(archive)).read(asset.member)
        except (KeyError, zipfile.BadZipFile) as error:
            raise FetchError(f"{asset.path}: {asset.member} is not in the archive") from error
        if len(data) != asset.size or hashlib.sha256(data).hexdigest() != asset.sha256:
            raise FetchError(f"{asset.path}: the file inside the archive does not match its pinned SHA-256")
    else:
        data = _pull(asset.url, asset.size, asset.sha256, opener, asset.path)
    handle, temp = tempfile.mkstemp(prefix=".part-", dir=target.parent)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
        os.replace(temp, target)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise
    return target


def fetch(assets: Iterable[Asset], folder: Path, samples: bool = False, force: bool = False, opener: Callable = _open, say: Callable[[str], None] = print) -> bool:
    good = True
    for asset in wanted(assets, samples):
        if not force and present(asset, folder, deep=True):
            say(f"have   {asset.path}")
            continue
        if not asset.url:
            say(f"absent {asset.path}: {asset.made or 'no download for it'}")
            continue
        try:
            download(asset, folder, opener)
            say(f"got    {asset.path} ({asset.size / 1e6:.2f} MB)")
        except (FetchError, OSError, ValueError) as error:
            good = False
            say(f"FAILED {asset.path}: {error}")
    return good


def check(assets: Iterable[Asset], folder: Path, samples: bool = False, say: Callable[[str], None] = print) -> bool:
    good = True
    for asset in wanted(assets, samples):
        ok = present(asset, folder, deep=True)
        good = good and ok
        say(f"{'ok     ' if ok else 'MISSING'} {asset.path}")
    return good


def total(assets: Iterable[Asset], samples: bool = False) -> int:
    return sum(a.size for a in wanted(assets, samples))


def cli(argv: list[str] | None, assets: tuple[Asset, ...], folder: Path, prog: str, what: str) -> int:
    parser = argparse.ArgumentParser(prog=prog, description=f"Download {what}, pinned and checked by SHA-256.")
    parser.add_argument("--dest", default=str(folder), help=f"where to put them (default {folder})")
    parser.add_argument("--samples", action="store_true", help="also fetch a test photo of a person")
    parser.add_argument("--force", action="store_true", help="download again even when a good copy is there")
    parser.add_argument("--check", action="store_true", help="only check what is there")
    args = parser.parse_args(argv)
    dest = Path(args.dest)
    if args.check:
        return 0 if check(assets, dest, args.samples) else 1
    print(f"fetching {total(assets, args.samples) / 1e6:.1f} MB into {dest}")
    if fetch(assets, dest, args.samples, args.force):
        print("done")
        return 0
    print("some files could not be fetched; run it again", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    return cli(argv, ASSETS, MODELS, "python -m pebble.eyes.fetch", "the face and person models Pebble's eyes use (YuNet, NanoDet)")


if __name__ == "__main__":
    sys.exit(main())
