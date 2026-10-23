import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / "export" / "work"
BRAIN_MODELS = HERE.parent / "brain" / "pebble" / "eyes" / "models"
ASSETS = "https://github.com/ultralytics/assets/releases/download/v8.4.0"
LICENCE = "AGPL-3.0 (YOLOE, THU-MIG/yoloe; Ultralytics)"
TEXT_LICENCE = "AGPL-3.0 (YOLOE, THU-MIG/yoloe; Ultralytics); prompt embeddings made with MobileCLIP2 (Apple Machine Learning Research Model licence: non-commercial research only)"
SOURCES = {
    "yoloe-26s-seg-pf.pt": "01605da3f2e0e5325df45d5f5eef8e40b5b5c7d085399be3c33ac638258b150a",
    "yoloe-26n-seg-pf.pt": "ae805a9ac11c85214588b32da8248d68a516e1d071465e1e86a03cbfadb66ba7",
    "yoloe-26s-seg.pt": "48f24206bc8680d60cbbfa296b0140da849669b9515058b72f5a945142df0654",
    "yoloe-26n-seg.pt": "1741c1f8da3cea47e2c01829c334a50dc0b9bbd05e685b90a3ce84fae32c8c1b",
    "mobileclip2_b.ts": "35d7f213e4d75f38514e4656ad3cb91158bd33e3805d8ac349f23b186f66982f",
}
BUILT_IN = (
    ("fire", "fire", "fire"),
    ("flame", "fire", "fire"),
    ("bonfire", "fire", "fire"),
    ("campfire", "fire", "fire"),
    ("forest fire", "fire", "fire"),
    ("wildfire", "fire", "fire"),
    ("smoke", "smoke", "smoke"),
    ("candle", "candle", "lookalike"),
    ("birthday candle", "candle", "lookalike"),
    ("fireplace", "fireplace", "lookalike"),
    ("fire pit", "fire pit", "lookalike"),
    ("wood-burning stove", "wood-burning stove", "lookalike"),
    ("gas stove", "stove burner", "lookalike"),
    ("stove", "stove", "lookalike"),
    ("steam", "steam", "lookalike"),
    ("fog", "fog", "lookalike"),
    ("sunset", "sunset", "lookalike"),
    ("television", "tv", "lookalike"),
    ("lamp", "lamp", "lookalike"),
    ("table lamp", "lamp", "lookalike"),
    ("oil lamp", "lamp", "lookalike"),
    ("insect", "insect", "life"),
    ("spider", "spider", "life"),
    ("snail", "snail", "life"),
    ("plant", "plant", "life"),
    ("flower", "flower", "life"),
)
CREATURES = frozenset({"insect", "spider", "snail"})
PROMPTS = (
    ("fire", "fire", "fire"),
    ("flames", "fire", "fire"),
    ("burning fire", "fire", "fire"),
    ("blaze", "fire", "fire"),
    ("smoke", "smoke", "smoke"),
    ("thick smoke", "smoke", "smoke"),
    ("candle", "candle", "lookalike"),
    ("fireplace", "fireplace", "lookalike"),
    ("gas stove burner", "stove burner", "lookalike"),
    ("steam", "steam", "lookalike"),
    ("television", "tv", "lookalike"),
    ("sunset", "sunset", "lookalike"),
    ("insect", "insect", "life"),
    ("spider", "spider", "life"),
    ("snail", "snail", "life"),
    ("plant", "plant", "life"),
    ("flower", "flower", "life"),
)


def sha256(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def pinned(name: str) -> bool:
    path = WORK / name
    want = SOURCES.get(name)
    if want and path.exists() and sha256(path) != want:
        print(f"{name} does not match its pinned SHA-256; delete it from {WORK} and run again", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Export YOLOE with a small fire and smoke vocabulary (and the things that look like them), plus small life on the floor, to ONNX for Pebble's hazard watch.")
    parser.add_argument("--mode", choices=("builtin", "text"), default="builtin", help="builtin: keep these words from the prompt-free model's own vocabulary (no text model runs); text: compute prompt embeddings with MobileCLIP2 (research-only licence)")
    parser.add_argument("--model", default=None)
    parser.add_argument("--imgsz", type=int, default=416)
    parser.add_argument("--out", default=str(BRAIN_MODELS))
    parser.add_argument("--name", default="hazards")
    args = parser.parse_args()
    model_name = args.model or ("yoloe-26s-seg-pf.pt" if args.mode == "builtin" else "yoloe-26s-seg.pt")
    out = Path(args.out).resolve()
    WORK.mkdir(parents=True, exist_ok=True)
    os.chdir(WORK)

    import onnx
    import ultralytics
    from ultralytics import YOLOE

    model = YOLOE(model_name)
    if not pinned(model_name):
        return 1
    if args.mode == "builtin":
        sys.path.insert(0, str(HERE))
        from export_objects import prune

        names = [model.names[i] for i in range(len(model.names))]
        missing = [raw for raw, _, _ in BUILT_IN if raw not in names]
        if missing:
            print(f"not in {model_name}'s vocabulary: {', '.join(missing)}", file=sys.stderr)
            return 1
        words = BUILT_IN
        prune(model, [names.index(raw) for raw, _, _ in words])
        licence = LICENCE
    else:
        words = PROMPTS
        prompts = [w[0] for w in words]
        model.set_classes(prompts, model.get_text_pe(prompts))
        if not pinned("mobileclip2_b.ts"):
            return 1
        licence = TEXT_LICENCE
    exported = Path(model.export(format="onnx", imgsz=args.imgsz, opset=17, simplify=True, dynamic=False))
    out.mkdir(parents=True, exist_ok=True)
    onnx_path = out / f"{args.name}.onnx"
    graph = onnx.load(str(exported))
    trimmed = WORK / "trimmed.onnx"
    onnx.utils.extract_model(str(exported), str(trimmed), [graph.graph.input[0].name], [graph.graph.output[0].name])
    shutil.move(str(trimmed), onnx_path)
    channels = onnx.load(str(onnx_path)).graph.output[0].type.tensor_type.shape.dim[1].dim_value
    if channels != 4 + len(words) + 32:
        print(f"unexpected output layout: {channels} channels for {len(words)} classes", file=sys.stderr)
        return 1
    source = WORK / model_name
    vocab = {
        "model": model_name,
        "mode": args.mode,
        "licence": licence,
        "source": f"{ASSETS}/{model_name}",
        "source_sha256": sha256(source) if source.exists() else None,
        "ultralytics": ultralytics.__version__,
        "imgsz": args.imgsz,
        "layout": {"boxes": 4, "classes": len(words), "mask": 32, "anchors_last": True, "scores": "probability"},
        "classes": [{"raw": raw, "label": label, "role": role, "animal": label in CREATURES, "depth": 6} for raw, label, role in words],
    }
    vocab_path = out / f"{args.name}_vocab.json"
    vocab_path.write_text(json.dumps(vocab, indent=1), encoding="utf-8")
    for path in (onnx_path, vocab_path):
        print(f"{path.name}: {path.stat().st_size} bytes, SHA-256 {sha256(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
