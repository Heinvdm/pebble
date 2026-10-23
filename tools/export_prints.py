import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / "export" / "work"
BRAIN_MODELS = HERE.parent / "brain" / "pebble" / "eyes" / "models"
REPO = "facebook/dinov2-small"
REVISION = "ed25f3a31f01632728cabb09d1542f84ab7b0056"
LICENCE = "Apache-2.0 (DINOv2, Meta)"


def sha256(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Export DINOv2-small to ONNX for Pebble's object prints, with any picture size, then make an int8 copy.")
    parser.add_argument("--out", default=str(BRAIN_MODELS))
    parser.add_argument("--name", default="prints")
    parser.add_argument("--trace", type=int, default=140, help="picture size used while tracing (not 224, so the position embedding is interpolated)")
    args = parser.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    os.chdir(WORK)

    import torch
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from transformers import AutoModel

    torch.manual_seed(0)
    model = AutoModel.from_pretrained(REPO, revision=REVISION).eval()

    class Prints(torch.nn.Module):
        def __init__(self, inner):
            super().__init__()
            self.inner = inner

        def forward(self, pixels):
            tokens = self.inner(pixel_values=pixels).last_hidden_state
            return tokens[:, 0], tokens[:, 1:].mean(dim=1)

    wrapped = Prints(model).eval()
    example = torch.rand(2, 3, args.trace, args.trace)
    full = WORK / f"{args.name}_fp32.onnx"
    torch.onnx.export(
        wrapped,
        (example,),
        str(full),
        input_names=["pixels"],
        output_names=["cls", "mean"],
        dynamic_axes={"pixels": {0: "batch", 2: "height", 3: "width"}, "cls": {0: "batch"}, "mean": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )
    small = out / f"{args.name}.onnx"
    quantize_dynamic(str(full), str(small), weight_type=QuantType.QInt8)
    meta = {"model": REPO, "revision": REVISION, "licence": LICENCE, "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225], "patch": 14, "outputs": ["cls", "mean"], "int8": "dynamic, weights QInt8"}
    meta_path = out / f"{args.name}.json"
    meta_path.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    for path in (full, small, meta_path):
        print(f"{path.name}: {path.stat().st_size} bytes, SHA-256 {sha256(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
