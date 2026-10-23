import argparse
import json
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "app" / "src" / "test" / "resources" / "turn"
MODEL = HERE.parent / "models" / "smart-turn-v3.2-cpu.onnx"
RATE = 16_000
SECONDS = 8
CASES = (("whole", None), ("mid_word", 2.45))


def last_seconds(audio):
    n = SECONDS * RATE
    if len(audio) > n:
        return audio[-n:]
    return np.pad(audio, (n - len(audio), 0), mode="constant", constant_values=0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Make test fixtures for the phone's end-of-turn features from Whisper's own feature extractor")
    parser.add_argument("wav", help="a 16 kHz mono 16-bit recording")
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--model", default=str(MODEL))
    args = parser.parse_args()
    from transformers import WhisperFeatureExtractor

    w = wave.open(args.wav)
    assert w.getframerate() == RATE and w.getnchannels() == 1 and w.getsampwidth() == 2
    pcm = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    audio = pcm.astype(np.float32) / 32768.0
    extractor = WhisperFeatureExtractor(chunk_length=SECONDS)
    session = None
    if Path(args.model).exists():
        import onnxruntime as ort

        session = ort.InferenceSession(args.model, providers=["CPUExecutionProvider"])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = []
    for name, end_s in CASES:
        end = len(audio) if end_s is None else int(end_s * RATE)
        features = extractor(last_seconds(audio[:end]), sampling_rate=RATE, return_tensors="np", padding="max_length", max_length=SECONDS * RATE, truncation=True, do_normalize=True).input_features.astype(np.float32)
        chance = float(session.run(None, {"input_features": features})[0][0].item()) if session is not None else None
        (out / f"{name}.bin").write_bytes(np.ascontiguousarray(features[0], dtype="<f4").tobytes())
        cases.append({"name": name, "samples": end, "file": f"{name}.bin", "probability": chance, "shape": list(features.shape)})
    (out / "speech.pcm").write_bytes(pcm.astype("<i2").tobytes())
    (out / "cases.json").write_text(json.dumps(cases, indent=1), encoding="utf-8")
    print(f"wrote {len(cases)} end-of-turn cases to {out}")


if __name__ == "__main__":
    main()
