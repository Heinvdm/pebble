import argparse
import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Callable, Iterable

from ..eyes.fetch import Asset, FetchError, _open, _pull, present, total, wanted

MODELS = Path(__file__).resolve().parent / "models"
MANIFEST = "speech.json"
GITHUB = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
NEMO_ASR = "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-streaming-fast-conformer-transducer-en-480ms-int8/resolve/df8ed95e44a70924450381e610770f9d656d1e15"
KWS_TAR = f"{GITHUB}/kws-models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2"
KWS_DIR = "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
KWS_TAR_SHA = "f170013b4716e41b62b9bfd809687c207cef798ef9bc6534d524e17af9b6561a"
KWS_TAR_SIZE = 17626723
VAD_LICENCE = "MIT (Silero VAD, Silero Team; snakers4/silero-vad)"
ASR_LICENCE = "CC-BY-4.0 (NVIDIA NeMo stt_en_fastconformer_hybrid_large_streaming_multi, 480 ms, int8 export by k2-fsa sherpa-onnx)"
KWS_LICENCE = "Apache-2.0 (k2-fsa icefall keyword spotter, zipformer 3.3M trained on GigaSpeech)"
SPEAKER_LICENCE = "Apache-2.0 (NVIDIA NeMo TitaNet-S, covered by the NeMo toolkit's licence; export by k2-fsa sherpa-onnx)"
SAMPLE_LICENCE = "CC-BY-4.0 (LibriSpeech, Vassil Panayotov et al., from LibriVox public-domain recordings)"


def _kws(path: str, member: str, sha256: str, size: int) -> Asset:
    return Asset(f"kws_{Path(path).stem}", path, KWS_TAR, sha256, size, KWS_LICENCE, member=f"{KWS_DIR}/{member}", archive_sha256=KWS_TAR_SHA, archive_size=KWS_TAR_SIZE)


ASSETS = (
    Asset("vad", "silero_vad.onnx", f"{GITHUB}/asr-models/silero_vad.onnx", "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6", 643854, VAD_LICENCE),
    Asset("asr_encoder", "asr/encoder.int8.onnx", f"{NEMO_ASR}/encoder.int8.onnx", "100c5616929a131b5b3c8c8ab0d83aaba2cdcae163acd8d190b4e5ffa5f7d051", 131507603, ASR_LICENCE),
    Asset("asr_decoder", "asr/decoder.int8.onnx", f"{NEMO_ASR}/decoder.int8.onnx", "4f04431988472f8c7b815f942aa6901976929c9e22353029681fcdb262da0164", 3955864, ASR_LICENCE),
    Asset("asr_joiner", "asr/joiner.int8.onnx", f"{NEMO_ASR}/joiner.int8.onnx", "d2d8e7290a6a8245a83ed211aa0dd8cdf8effb8a7c64fe392399561111b52f30", 1408182, ASR_LICENCE),
    Asset("asr_tokens", "asr/tokens.txt", f"{NEMO_ASR}/tokens.txt", "618dc110fc2213886b52e063ff42329bbdf37a266ca7705184090fa5f39f3131", 11896, ASR_LICENCE),
    _kws("kws/encoder.int8.onnx", "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx", "1e721676515bcd42a186979733981213c66c80db680e1cc582dfedf3be76e678", 4807159),
    _kws("kws/decoder.onnx", "decoder-epoch-12-avg-2-chunk-16-left-64.onnx", "f61ebd3eed3773a44d088d53dfae92dbb6aec4839f4dcaee2d402414741663a3", 1063189),
    _kws("kws/joiner.int8.onnx", "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx", "eae9da0c7e1e6c6a3f4cc42d167899c388f6c6701b94cb96320e4f55df79624c", 163380),
    _kws("kws/tokens.txt", "tokens.txt", "fd2ded4050a55d2b1578870ba8697d02371980217806b7558bd0a5cc60f3ba53", 5006),
    _kws("kws/bpe.model", "bpe.model", "c8a2a0129c4ab8e463164c142f82d25649661b122c8cd0b7aab5c9e80b90ad24", 244837),
    Asset("speaker", "nemo_en_titanet_small.onnx", f"{GITHUB}/speaker-recongition-models/nemo_en_titanet_small.onnx", "ad4a1802485d8b34c722d2a9d04249662f2ece5d28a7a039063ca22f515a789e", 40257283, SPEAKER_LICENCE),
    Asset("sample_0", "samples/librispeech_0.wav", f"{NEMO_ASR}/test_wavs/0.wav", "6bc58a4efdf20daac252b6b1502632601a71efe0308f6757dc1eda34891a7e4f", 212044, SAMPLE_LICENCE, sample=True),
    Asset("sample_1", "samples/librispeech_1.wav", f"{NEMO_ASR}/test_wavs/1.wav", "5143a6ba93c4b274e2c4ac22deb75c2c48936c853f0519add1de828b6c79cc5a", 534924, SAMPLE_LICENCE, sample=True),
)

LAYOUT = {
    "vad": "silero_vad.onnx",
    "asr": {"encoder": "asr/encoder.int8.onnx", "decoder": "asr/decoder.int8.onnx", "joiner": "asr/joiner.int8.onnx", "tokens": "asr/tokens.txt", "model_type": "", "chunk_s": 0.48},
    "kws": {"encoder": "kws/encoder.int8.onnx", "decoder": "kws/decoder.onnx", "joiner": "kws/joiner.int8.onnx", "tokens": "kws/tokens.txt", "bpe": "kws/bpe.model"},
    "speaker": "nemo_en_titanet_small.onnx",
    "speaker_dims": 192,
    "samples": ["samples/librispeech_0.wav", "samples/librispeech_1.wav"],
    "licences": {"vad": VAD_LICENCE, "asr": ASR_LICENCE, "kws": KWS_LICENCE, "speaker": SPEAKER_LICENCE, "samples": SAMPLE_LICENCE},
}


def manifest_text() -> str:
    return json.dumps(LAYOUT, indent=2, ensure_ascii=False) + "\n"


def write_manifest(folder: Path) -> Path:
    target = Path(folder) / MANIFEST
    target.parent.mkdir(parents=True, exist_ok=True)
    text = manifest_text()
    if not target.exists() or target.read_text(encoding="utf-8") != text:
        target.write_text(text, encoding="utf-8", newline="\n")
    return target


def _member(archive: bytes, name: str) -> bytes:
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:bz2") as tar:
            handle = tar.extractfile(name)
            if handle is None:
                raise FetchError(f"{name} is not a file in the archive")
            return handle.read()
    except (KeyError, tarfile.TarError, OSError, EOFError) as error:
        raise FetchError(f"{name} is not in the archive") from error


def _save(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
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


def download(asset: Asset, folder: Path, opener: Callable = _open, archives: dict | None = None) -> Path:
    target = Path(folder) / asset.path
    if asset.member:
        archives = {} if archives is None else archives
        if asset.url not in archives:
            archives[asset.url] = _pull(asset.url, asset.archive_size, asset.archive_sha256, opener, asset.url.rsplit("/", 1)[-1])
        data = _member(archives[asset.url], asset.member)
        if len(data) != asset.size or hashlib.sha256(data).hexdigest() != asset.sha256:
            raise FetchError(f"{asset.path}: the file inside the archive does not match its pinned SHA-256")
    else:
        data = _pull(asset.url, asset.size, asset.sha256, opener, asset.path)
    _save(target, data)
    return target


def fetch(assets: Iterable[Asset], folder: Path, samples: bool = False, force: bool = False, opener: Callable = _open, say: Callable[[str], None] = print) -> bool:
    good = True
    archives: dict = {}
    for asset in wanted(assets, samples):
        if not force and present(asset, folder, deep=True):
            say(f"have   {asset.path}")
            continue
        try:
            download(asset, folder, opener, archives)
            say(f"got    {asset.path} ({asset.size / 1e6:.2f} MB)")
        except (FetchError, OSError, ValueError) as error:
            good = False
            say(f"FAILED {asset.path}: {error}")
    write_manifest(folder)
    return good


def check(assets: Iterable[Asset], folder: Path, samples: bool = False, say: Callable[[str], None] = print) -> bool:
    good = True
    for asset in wanted(assets, samples):
        ok = present(asset, folder, deep=True)
        good = good and ok
        say(f"{'ok     ' if ok else 'MISSING'} {asset.path}")
    manifest = Path(folder) / MANIFEST
    same = manifest.exists() and manifest.read_text(encoding="utf-8") == manifest_text()
    say(f"{'ok     ' if same else 'STALE  '} {MANIFEST}")
    return good and same


def ready(folder: Path = MODELS) -> bool:
    return all(present(a, folder) for a in wanted(ASSETS))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.speech.fetch", description="Download the speech models Pebble's ears use (Silero VAD, NeMo streaming ASR, the name spotter, TitaNet voice prints), pinned and checked by SHA-256.")
    parser.add_argument("--dest", default=str(MODELS), help=f"where to put them (default {MODELS})")
    parser.add_argument("--samples", action="store_true", help="also fetch two short test recordings")
    parser.add_argument("--force", action="store_true", help="download again even when a good copy is there")
    parser.add_argument("--check", action="store_true", help="only check what is there")
    parser.add_argument("--licences", action="store_true", help="print each model's licence")
    args = parser.parse_args(argv)
    dest = Path(args.dest)
    if args.licences:
        for name, text in LAYOUT["licences"].items():
            print(f"{name}: {text}")
        return 0
    if args.check:
        return 0 if check(ASSETS, dest, args.samples) else 1
    print(f"fetching {total(ASSETS, args.samples) / 1e6:.1f} MB into {dest}")
    if fetch(ASSETS, dest, args.samples, args.force):
        print("done")
        return 0
    print("some files could not be fetched; run it again", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
