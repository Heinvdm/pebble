import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

HERE = Path(__file__).resolve().parent
BRAIN = HERE.parent.parent / "brain"
sys.path.insert(0, str(BRAIN))

from pebble.eyes.detect import BODY_BINS, BODY_MEAN, BODY_SIZE, BODY_STD, BODY_STRIDES, Detector
from pebble.eyes.slow import SlowDetector, letterbox

MODELS = BRAIN / "pebble" / "eyes" / "models"


def session(name: str) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.log_severity_level = 3
    return ort.InferenceSession(str(MODELS / name), options, providers=["CPUExecutionProvider"])


def save(folder: Path, name: str, array: np.ndarray) -> dict:
    data = np.ascontiguousarray(array, dtype="<f4")
    (folder / f"{name}.bin").write_bytes(data.tobytes())
    return {"file": f"{name}.bin", "shape": list(data.shape)}


def nanodet(folder: Path, image: np.ndarray, tag: str) -> dict:
    h, w = image.shape[:2]
    k = min(BODY_SIZE / w, BODY_SIZE / h)
    rw, rh = max(1, round(w * k)), max(1, round(h * k))
    canvas = np.zeros((BODY_SIZE, BODY_SIZE, 3), np.float32)
    canvas[:rh, :rw] = (cv2.resize(image, (rw, rh), interpolation=cv2.INTER_AREA).astype(np.float32) - np.array(BODY_MEAN, np.float32)) / np.array(BODY_STD, np.float32)
    blob = canvas.transpose(2, 0, 1)[None]
    s = session("object_detection_nanodet_2022nov.onnx")
    outs = s.run(None, {s.get_inputs()[0].name: blob})
    tensors = [save(folder, f"{tag}_nanodet_{i}", o) for i, o in enumerate(outs)]
    detector = Detector(models=MODELS, faces=False, bodies=True, tags=False)
    people, things = detector.objects(image)
    expected = [[b.x, b.y, b.w, b.h, b.score, 0] for b in people]
    from pebble.eyes.labels import COCO_NAMES

    expected += [[f.box.x, f.box.y, f.box.w, f.box.h, f.box.score, COCO_NAMES.index(f.raw)] for f in things]
    return {"rw": rw, "rh": rh, "tensors": tensors, "expected": expected}


def yunet(folder: Path, image: np.ndarray, tag: str) -> dict:
    size = 640
    h, w = image.shape[:2]
    k = min(size / w, size / h)
    rw, rh = max(1, round(w * k)), max(1, round(h * k))
    canvas = np.zeros((size, size, 3), np.uint8)
    canvas[:rh, :rw] = cv2.resize(image, (rw, rh), interpolation=cv2.INTER_AREA)
    s = session("face_detection_yunet_2023mar.onnx")
    blob = canvas.astype(np.float32).transpose(2, 0, 1)[None]
    names = [o.name for o in s.get_outputs()]
    outs = dict(zip(names, s.run(None, {s.get_inputs()[0].name: blob})))
    tensors = {name: save(folder, f"{tag}_yunet_{name}", outs[name]) for name in names}
    face = cv2.FaceDetectorYN.create(str(MODELS / "face_detection_yunet_2023mar.onnx"), "", (size, size), 0.6, 0.3, 50)
    _, found = face.detect(canvas)
    expected = [] if found is None else [[float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[14])] + [float(v) for v in r[4:14]] for r in found]
    return {"rw": rw, "rh": rh, "tensors": tensors, "expected": expected}


def yoloe(folder: Path, image: np.ndarray, tag: str) -> dict:
    slow = SlowDetector(MODELS / "objects.onnx", MODELS / "objects_vocab.json", backend="onnxruntime", threads=2)
    blob, k, left, top = letterbox(image, slow.size, np, cv2)
    out = slow._run(blob)
    out = out.reshape(out.shape[-2], out.shape[-1])
    count = len(slow.classes)
    keep = np.nonzero(out[4:4 + count].max(axis=0) > 0.2)[0]
    small = out[:, keep]
    tensors = [save(folder, f"{tag}_yoloe", small)]
    h, w = image.shape[:2]
    expected = []
    for f in slow.detect(image):
        index = next(i for i, c in enumerate(slow.classes) if c["label"] == f.label and c.get("raw", c["label"]) == f.raw)
        expected.append([f.box.x, f.box.y, f.box.w, f.box.h, f.box.score, index])
    return {"size": slow.size, "classes": count, "k": k, "left": left, "top": top, "width": w, "height": h, "tensors": tensors, "expected": expected}


def mouths(folder: Path) -> None:
    from pebble.eyes.speaking import MouthModel, shape

    model = MouthModel(MODELS / "face_landmarks_detector.tflite")
    detector = Detector(models=MODELS, faces=True, bodies=False, tags=False)
    pictures = BRAIN / "tests" / "data" / "mouths"
    cases = []
    for kind, number in (("talk", "00"), ("talk", "03"), ("still", "05"), ("chew", "07")):
        image = cv2.imread(str(pictures / kind / f"{number}.jpg"))
        height, width = image.shape[:2]
        faces = detector.faces(image)
        marks = [(u * width, v * height) for u, v in detector.face_marks[0]]
        f = faces[0]
        captured = {}
        real = model.cv2.warpAffine

        def spy(src, m, size, **kw):
            captured["m"] = m.copy()
            return real(src, m, size, **kw)

        model.cv2.warpAffine = spy
        try:
            got = model.read(image, (f.x * width, f.y * height, f.w * width, f.h * height), marks)
        finally:
            model.cv2.warpAffine = real
        model._net.setInput(cv2.cvtColor(real(image, captured["m"], (256, 256), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT), cv2.COLOR_BGR2RGB).astype(np.float32).transpose(2, 0, 1)[None] / 255.0)
        outs = model._net.forward(model._names)
        points = next(o for o in outs if o.size == 478 * 3).reshape(478, 3)
        name = f"mouth_{kind}_{number}"
        save(folder, name, points)
        cases.append({"picture": f"{kind}/{number}.jpg", "marks": [v for p in marks for v in p], "matrix": [float(v) for v in captured["m"].ravel()], "points": f"{name}.bin", "shape": list(shape(points)), "read": list(got) if got else None})
    (folder / "mouths.json").write_text(json.dumps(cases, indent=1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Make test fixtures for the Kotlin decoders from the brain's own models and decoders")
    parser.add_argument("--out", default=str(HERE.parent / "app" / "src" / "test" / "resources" / "decode"))
    args = parser.parse_args()
    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=True)
    index = {}
    for name in ("desk", "portrait", "cat"):
        image = cv2.imread(str(MODELS / "samples" / f"{name}.jpg"))
        index[name] = {"nanodet": nanodet(folder, image, name), "yunet": yunet(folder, image, name), "yoloe": yoloe(folder, image, name)}
    (folder / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    mouths(folder)
    print(f"wrote fixtures to {folder}")


if __name__ == "__main__":
    main()
