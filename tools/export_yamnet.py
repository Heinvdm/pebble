import argparse
import hashlib
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / "export" / "work" / "yamnet"
BRAIN_MODELS = HERE.parent / "brain" / "pebble" / "hearing" / "models"
UA = "pebble-fetch/1 (personal robot)"
WEIGHTS_URL = "https://storage.googleapis.com/audioset/yamnet.h5"
WEIGHTS_SHA256 = "13c3308955bbfaef262f175ac9c40e47b134573a93984f009220dd7cc12a1744"
WEIGHTS_SIZE = 15296092
LICENCE = "Apache-2.0 (YAMNet, Google; tensorflow/models research/audioset/yamnet)"
COMMONS = "https://upload.wikimedia.org/wikipedia/commons"
FREESOUND = "https://cdn.freesound.org/previews"

RATE = 16000
WINDOW = 15600
FRAME = 400
HOP = 160
FFT = 512
BANDS = 64
LOW_HZ = 125.0
HIGH_HZ = 7500.0
LOG_OFFSET = 0.001
EPSILON = 1e-4
CLASSES = 521
LAYERS = ((2, 32), (1, 64), (2, 128), (1, 128), (2, 256), (1, 256), (2, 512), (1, 512), (1, 512), (1, 512), (1, 512), (1, 512), (2, 1024), (1, 1024))
OPSET = 13
IR_VERSION = 8

FADE_S = 0.01
ALIAS_TAPS = 63
SAMPLES = (
    ("smoke_alarm.wav", f"{COMMONS}/b/b0/Smoke_alarm.ogg", "159a970c1f006cb3463626f541e0f7c356f0a4b3b1b7afd3252965071cc42be7", 489435, 3.0, 3.0),
    ("baby_crying.wav", f"{COMMONS}/2/2b/Crying_newborn_baby.ogg", "f32ddad349ed2a94621ed5dae8863a97f94f8f55cc75e9f18c58de0bfbc1d036", 510174, 9.0, 3.0),
    ("tap_water.wav", f"{COMMONS}/1/19/Faucet_water_into_sink.ogg", "27f96eb4677dda993d66dc7b01f5fde99f76c0828e2484c265c198e71545c40f", 1492492, 0.0, 3.0),
    ("speech.wav", f"{COMMONS}/d/da/Puppy_football_lasts_only_one_game.ogg", "68f0d92002a383d5ca392d72009cc9e812518430509f64b3944250a93d56e356", 56943, 0.0, 3.0),
    ("smoke_alarm_t3.wav", f"{FREESOUND}/369/369848_1480854-hq.mp3", "1441426cd8d1109e72798c907e71e515a73901e6058a00cf0fad3308a9002793", 375600, 0.0, 16.0),
)


def sha256(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def pinned(url: str, digest: str, size: int, folder: Path, name: str) -> Path:
    target = folder / name
    if target.exists() and target.stat().st_size == size and sha256(target) == digest:
        return target
    folder.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read(size + 1)
    got = hashlib.sha256(data).hexdigest()
    if len(data) != size or got != digest:
        raise SystemExit(f"{url}: got {len(data)} bytes with SHA-256 {got}, expected {size} bytes with {digest}")
    handle, temp = tempfile.mkstemp(prefix=".part-", dir=folder)
    with os.fdopen(handle, "wb") as out:
        out.write(data)
    os.replace(temp, target)
    return target


def hertz_to_mel(hz):
    import numpy as np

    return 1127.0 * np.log1p(np.asarray(hz, np.float64) / 700.0)


def mel_matrix():
    import numpy as np

    bins = FFT // 2 + 1
    linear = np.linspace(0.0, RATE / 2.0, bins)[1:]
    spectrum = hertz_to_mel(linear)[:, None]
    edges = np.linspace(hertz_to_mel(LOW_HZ), hertz_to_mel(HIGH_HZ), BANDS + 2)
    lower, centre, upper = edges[:-2][None, :], edges[1:-1][None, :], edges[2:][None, :]
    rising = (spectrum - lower) / (centre - lower)
    falling = (upper - spectrum) / (upper - centre)
    weights = np.maximum(0.0, np.minimum(rising, falling))
    return np.vstack([np.zeros((1, BANDS)), weights]).astype(np.float32)


def stft_kernels():
    import numpy as np

    n = np.arange(FRAME, dtype=np.float64)
    hann = 0.5 - 0.5 * np.cos(2.0 * np.pi * n / FRAME)
    angle = 2.0 * np.pi * np.outer(np.arange(FFT // 2 + 1), n) / FFT
    real = (np.cos(angle) * hann)[:, None, :].astype(np.float32)
    imag = (-np.sin(angle) * hann)[:, None, :].astype(np.float32)
    return real, imag


def build(weights: Path):
    import h5py
    import numpy as np
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    store = h5py.File(weights, "r")
    nodes, inits = [], []

    def weight(layer: str, name: str):
        return np.asarray(store[f"{layer}/{layer}/{name}:0"], np.float32)

    def const(name: str, value):
        inits.append(numpy_helper.from_array(np.ascontiguousarray(value), name))
        return name

    def node(op: str, inputs: list, output: str, **attrs) -> str:
        nodes.append(helper.make_node(op, inputs, [output], name=output, **attrs))
        return output

    def folded(kernel, bn: str):
        scale = 1.0 / np.sqrt(weight(bn, "moving_variance").astype(np.float64) + EPSILON)
        kernel = (kernel.astype(np.float64) * scale[:, None, None, None]).astype(np.float32)
        bias = (weight(bn, "beta").astype(np.float64) - weight(bn, "moving_mean").astype(np.float64) * scale).astype(np.float32)
        return kernel, bias

    def conv(x: str, kernel, bias, name: str, stride: int, groups: int = 1) -> str:
        size = kernel.shape[-1]
        pads = [0, 0, 0, 0] if size == 1 else ([0, 0, 1, 1] if stride == 2 else [1, 1, 1, 1])
        out = node("Conv", [x, const(f"{name}.w", kernel), const(f"{name}.b", bias)], f"{name}.conv", kernel_shape=[size, size], strides=[stride, stride], pads=pads, group=groups)
        return node("Relu", [out], f"{name}.relu")

    real, imag = stft_kernels()
    signal = node("Reshape", ["waveform", const("signal_shape", np.array([1, 1, WINDOW], np.int64))], "signal")
    re = node("Conv", [signal, const("stft_real", real)], "stft_re", kernel_shape=[FRAME], strides=[HOP])
    im = node("Conv", [signal, const("stft_imag", imag)], "stft_im", kernel_shape=[FRAME], strides=[HOP])
    power = node("Add", [node("Mul", [re, re], "re2"), node("Mul", [im, im], "im2")], "power")
    magnitude = node("Sqrt", [power], "magnitude")
    frames = node("Transpose", [magnitude], "frames", perm=[0, 2, 1])
    mel = node("MatMul", [frames, const("mel", mel_matrix())], "mel_spectrum")
    log_mel = node("Log", [node("Add", [mel, const("log_offset", np.array(LOG_OFFSET, np.float32))], "mel_offset")], "log_mel")
    patch_frames = (WINDOW - FRAME) // HOP + 1
    x = node("Reshape", [log_mel, const("patch_shape", np.array([1, 1, patch_frames, BANDS], np.int64))], "patch")
    channels = 1
    for index, (stride, filters) in enumerate(LAYERS, 1):
        layer = f"layer{index}"
        if index == 1:
            kernel, bias = folded(weight(f"{layer}/conv", "kernel").transpose(3, 2, 0, 1), f"{layer}/conv/bn")
            x = conv(x, kernel, bias, layer, stride)
        else:
            kernel, bias = folded(weight(f"{layer}/depthwise_conv", "depthwise_kernel").transpose(2, 3, 0, 1), f"{layer}/depthwise_conv/bn")
            x = conv(x, kernel, bias, f"{layer}.dw", stride, groups=channels)
            kernel, bias = folded(weight(f"{layer}/pointwise_conv", "kernel").transpose(3, 2, 0, 1), f"{layer}/pointwise_conv/bn")
            x = conv(x, kernel, bias, f"{layer}.pw", 1)
        channels = filters
    pooled = node("GlobalAveragePool", [x], "pooled")
    embeddings = node("Flatten", [pooled], "embeddings", axis=1)
    logits = node("Gemm", [embeddings, const("logits.w", weight("logits", "kernel")), const("logits.b", weight("logits", "bias"))], "logits")
    node("Sigmoid", [logits], "scores")
    graph = helper.make_graph(
        nodes,
        "yamnet",
        [helper.make_tensor_value_info("waveform", TensorProto.FLOAT, [1, WINDOW])],
        [helper.make_tensor_value_info("scores", TensorProto.FLOAT, [1, CLASSES]), helper.make_tensor_value_info("embeddings", TensorProto.FLOAT, [1, channels])],
        inits,
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", OPSET)], producer_name="pebble tools/export_yamnet.py", producer_version="1")
    model.ir_version = IR_VERSION
    meta = {
        "source": WEIGHTS_URL,
        "source_sha256": WEIGHTS_SHA256,
        "licence": LICENCE,
        "rate": str(RATE),
        "window": str(WINDOW),
        "hop": str(RATE * 48 // 100),
        "classes": "yamnet_class_map.csv",
    }
    for key, value in meta.items():
        entry = model.metadata_props.add()
        entry.key, entry.value = key, value
    onnx.checker.check_model(model)
    return model


def export_model(args) -> int:
    import onnx

    weights = Path(args.weights) if args.weights else pinned(WEIGHTS_URL, WEIGHTS_SHA256, WEIGHTS_SIZE, WORK, "yamnet.h5")
    if weights.stat().st_size != WEIGHTS_SIZE or sha256(weights) != WEIGHTS_SHA256:
        print(f"{weights} does not match its pinned SHA-256", file=sys.stderr)
        return 1
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{args.name}.onnx"
    onnx.save(build(weights), str(target))
    print(f"{target.name}: {target.stat().st_size} bytes, SHA-256 {sha256(target)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build YAMNet (Google, AudioSet, 521 sounds) as ONNX for Pebble's hearing from Google's own Keras weights, with the log-mel front end inside the graph.")
    parser.add_argument("what", nargs="?", default="model", choices=["model", "samples"])
    parser.add_argument("--weights", default="", help="a local copy of yamnet.h5 (checked against its pinned SHA-256); by default it is downloaded")
    parser.add_argument("--out", default=str(BRAIN_MODELS))
    parser.add_argument("--name", default="yamnet")
    args = parser.parse_args()
    if args.what == "samples":
        return export_samples(args)
    return export_model(args)


def decode(path: Path):
    import av
    import numpy as np

    with av.open(str(path)) as box:
        stream = next(s for s in box.streams if s.type == "audio")
        rate = stream.codec_context.sample_rate
        chunks = []
        for frame in box.decode(stream):
            values = frame.to_ndarray()
            if values.dtype.kind in "iu":
                values = values.astype(np.float64) / float(np.iinfo(values.dtype).max + 1)
            channels = len(frame.layout.channels)
            values = values.reshape(channels, -1) if frame.format.is_planar else values.reshape(-1, channels).T
            chunks.append(values.astype(np.float64))
    return np.concatenate(chunks, axis=1).mean(axis=0), rate


def resample(values, rate: int, target: int = RATE):
    import numpy as np

    values = np.asarray(values, np.float64)
    if rate == target:
        return values
    if target < rate:
        cutoff = 0.475 * target / rate
        n = np.arange(ALIAS_TAPS) - (ALIAS_TAPS - 1) / 2.0
        taps = 2.0 * cutoff * np.sinc(2.0 * cutoff * n) * np.hamming(ALIAS_TAPS)
        values = np.convolve(values, taps / taps.sum(), mode="same")
    count = max(1, int(round(values.size * target / rate)))
    return np.interp(np.arange(count) * (rate / target), np.arange(values.size), values)


def write_wav(path: Path, values) -> None:
    import wave

    import numpy as np

    pcm = np.clip(np.round(np.asarray(values) * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(pcm.tobytes())


def export_samples(args) -> int:
    import av
    import numpy as np

    out = Path(args.out).resolve() / "samples"
    out.mkdir(parents=True, exist_ok=True)
    for name, url, digest, size, start, seconds in SAMPLES:
        source = pinned(url, digest, size, WORK / "sources" / name.rsplit(".", 1)[0], url.rsplit("/", 1)[-1])
        values, rate = decode(source)
        mono = resample(values, rate)
        clip = mono[int(round(start * RATE)):int(round((start + seconds) * RATE))].copy()
        fade = int(FADE_S * RATE)
        ramp = np.linspace(0.0, 1.0, fade)
        clip[:fade] *= ramp
        clip[-fade:] *= ramp[::-1]
        target = out / name
        write_wav(target, clip)
        print(f"samples/{name}: {target.stat().st_size} bytes, SHA-256 {sha256(target)} (from {url}, {start:g} to {start + seconds:g} s, PyAV {av.__version__})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
