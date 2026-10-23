import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BRAIN = HERE.parent.parent / "brain"
sys.path.insert(0, str(BRAIN))
sys.path.insert(0, str(BRAIN / "tests"))

from floor_render import Scene
from pebble.eyes.floor import SIZE, DepthModel, NoDepthModel, rays

MODELS = BRAIN / "pebble" / "eyes" / "models"
HALF_MODEL = HERE.parent / "models" / "depth_anything_v2_small_fp16.onnx"
ROWS, COLS = SIZE
HALF_PITCHES = (0.0, 8.0)
HALF_TOLERANCE_M = 0.05
HALF_QUALITY = 0.01

BOX = [(1.2, 1.6, -0.6, -0.2, 0, 0.4)]
TOY = [(0.9, 1.0, -0.05, 0.05, 0, 0.06)]
EXACT = (
    ("wall_p8", Scene(wall_x=0.9), 70.0, 0.14, 8.0, 32, 2.0),
    ("box_p8", Scene(boxes=BOX, wall_x=1.9), 70.0, 0.14, 8.0, 32, 2.0),
    ("box_p0", Scene(boxes=BOX, wall_x=1.9), 70.0, 0.14, 0.0, 32, 2.0),
    ("box_m6", Scene(boxes=BOX, wall_x=1.9), 70.0, 0.14, -6.0, 32, 2.0),
    ("corridor_p8", Scene(wall_x=6.0, side_y=(-0.7, 0.7)), 70.0, 0.14, 8.0, 32, 2.0),
    ("toy_p8", Scene(boxes=TOY, wall_x=6.0), 70.0, 0.14, 8.0, 32, 2.0),
    ("drop_p8", Scene(drop_x=1.2, wall_x=4.0), 70.0, 0.14, 8.0, 32, 2.0),
    ("drop_m6", Scene(drop_x=1.2, wall_x=4.0), 70.0, 0.14, -6.0, 32, 2.0),
    ("high_f65", Scene(boxes=BOX, wall_x=1.9), 65.0, 0.3, 14.0, 16, 1.5),
)
MODELLED = (
    ("model_wall", Scene(wall_x=0.9)),
    ("model_toy", Scene(boxes=[TOY[0] + ((40, 180, 230),)], wall_x=3.0)),
    ("model_corridor", Scene(wall_x=6.0, side_y=(-0.7, 0.7))),
    ("model_drop", Scene(drop_x=1.2, wall_x=4.0)),
)


def save(folder: Path, name: str, depth) -> str:
    data = np.ascontiguousarray(depth, dtype="<f4")
    assert data.shape == (ROWS, COLS), data.shape
    (folder / f"{name}.bin").write_bytes(data.tobytes())
    return f"{name}.bin"


def case(folder: Path, name: str, depth, fov: float, height: float, pitch: float, bins: int, reach: float) -> dict:
    found, quality = rays(depth.astype(np.float32), fov, height, pitch, bins, reach)
    return {
        "name": name,
        "file": save(folder, name, depth),
        "rows": ROWS,
        "cols": COLS,
        "fov": fov,
        "height": height,
        "pitch": pitch,
        "bins": bins,
        "reach": reach,
        "quality": quality,
        "rays": None if found is None else [[r.bearing_deg, r.distance_m, r.score] for r in found],
    }


def half_cases(folder: Path, full) -> list:
    try:
        half = DepthModel(HALF_MODEL, 2)
    except NoDepthModel as error:
        print(f"skipping the half-size model cases: {error}")
        return []
    cases = []
    for name, scene in MODELLED:
        for pitch in HALF_PITCHES:
            picture = scene.render(pitch_deg=pitch)
            want, quality = rays(full(picture), 70.0, 0.14, pitch)
            label = f"half_{name.removeprefix('model_')}_p{pitch:g}"
            cases.append({
                "name": label,
                "file": save(folder, label, half(picture)),
                "rows": ROWS,
                "cols": COLS,
                "fov": 70.0,
                "height": 0.14,
                "pitch": pitch,
                "bins": 32,
                "reach": 2.0,
                "full_quality": quality,
                "full_rays": None if want is None else [[r.bearing_deg, r.distance_m, r.score] for r in want],
                "tolerance_m": HALF_TOLERANCE_M,
                "quality_tolerance": HALF_QUALITY,
            })
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Make test fixtures for the Kotlin floor scan from the brain's own floor scan")
    parser.add_argument("--out", default=str(HERE.parent / "app" / "src" / "test" / "resources" / "floor"))
    parser.add_argument("--half", action="store_true", help="only remake the cases that check the phone's half-size depth model against the PC's")
    args = parser.parse_args()
    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=True)
    if args.half:
        try:
            full = DepthModel(MODELS / "depth_anything_v2_small.onnx", 2)
        except NoDepthModel as error:
            print(f"no half-size cases without the PC's model: {error}")
            return
        halves = half_cases(folder, full)
        (folder / "half.json").write_text(json.dumps(halves, indent=1), encoding="utf-8")
        print(f"wrote {len(halves)} half-size model cases to {folder}")
        return
    cases = []
    for name, scene, fov, height, pitch, bins, reach in EXACT:
        scene.render(height=height, pitch_deg=pitch, width=COLS, rows=ROWS, fov_h_deg=fov)
        cases.append(case(folder, name, (3.0 / scene.depth + 0.2).astype(np.float32), fov, height, pitch, bins, reach))
    try:
        model = DepthModel(MODELS / "depth_anything_v2_small.onnx", 2)
    except NoDepthModel as error:
        print(f"skipping the model cases: {error}")
        model = None
    if model is not None:
        for name, scene in MODELLED:
            cases.append(case(folder, name, model(scene.render()), 70.0, 0.14, 8.0, 32, 2.0))
        halves = half_cases(folder, model)
        (folder / "half.json").write_text(json.dumps(halves, indent=1), encoding="utf-8")
        print(f"wrote {len(halves)} half-size model cases to {folder}")
    (folder / "index.json").write_text(json.dumps(cases, indent=1), encoding="utf-8")
    print(f"wrote {len(cases)} floor cases to {folder}")


if __name__ == "__main__":
    main()
