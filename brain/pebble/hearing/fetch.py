import sys
from pathlib import Path

from ..eyes.fetch import Asset, check, cli, fetch

MODELS = Path(__file__).resolve().parent / "models"
TF_MODELS = "c14bf9ad91962cf189f9f58db2132c06247fcd53"
TF_RAW = f"https://raw.githubusercontent.com/tensorflow/models/{TF_MODELS}"
COMMONS = "https://upload.wikimedia.org/wikipedia/commons"
YAMNET = "Apache-2.0 (YAMNet, Google; tensorflow/models research/audioset/yamnet)"
MADE_HERE = "made by tools/export_yamnet.py from Google's yamnet.h5 (pinned by SHA-256), log-mel front end inside the graph; copy it along with the brain"


def cut(source: str, start: int, end: int) -> str:
    return f"cut by tools/export_yamnet.py samples from {source} (pinned by SHA-256), {start} to {end} s, 16 kHz mono 16-bit, decoded with PyAV 19.0.1; copy it along with the brain"


ASSETS = (
    Asset("sounds", "yamnet.onnx", "", "e03465b66842466f7d16f28c237f1662adafa8e25772ef1f8d044b07f970659d", 15814946, YAMNET, made=MADE_HERE),
    Asset("sounds_classes", "yamnet_class_map.csv", f"{TF_RAW}/research/audioset/yamnet/yamnet_class_map.csv", "cdf24d193e196d9e95912a2667051ae203e92a2ba09449218ccb40ef787c6df2", 14096, YAMNET),
    Asset("sounds_licence", "YAMNET_LICENSE", f"{TF_RAW}/LICENSE", "5b17814bf0de8cf65069bc6d7cc38cff19fcaa864d243423ad3ef3db01b52385", 11512, "Apache-2.0"),
    Asset("sample_glass", "samples/glass_breaking.wav", f"{COMMONS}/f/f6/Glass_breaking_4_%28Gravity_Sound%29.wav", "8dcd95d0786e1d0225f3317ee0d98dde70aab7815113c011a9a84904e67a32b0", 394304, "CC BY 4.0, \"glass breaking 4\" by Gravity Sound (Wikimedia Commons, Glass breaking 4 (Gravity Sound).wav)", sample=True),
    Asset("sample_dog", "samples/dog_barking.wav", f"{COMMONS}/c/c6/Voice_Test_Error.wav", "6f5ce83eafc979c664a6782aefa892dbf1fd979c76b47e9b6208a9e6d0b019f8", 310016, "CC0, Kineticsquid (Wikimedia Commons, Voice Test Error.wav, dogs barking)", sample=True),
    Asset("sample_alarm", "samples/smoke_alarm.wav", "", "06f2469e31f25df461db69258d23cf022ff998605bf52ebd7d0b7d9e71549036", 96044, "public domain, cori (PDSounds 695, via Wikimedia Commons, Smoke alarm.ogg)", sample=True, made=cut("Wikimedia Commons Smoke_alarm.ogg", 3, 6)),
    Asset("sample_baby", "samples/baby_crying.wav", "", "412d3a0c017e1952c3f4dd1a08b119de873ba51c59bb563f0cb936d4228c8399", 96044, "CC0, the_yura (Freesound, via Wikimedia Commons, Crying newborn baby.ogg)", sample=True, made=cut("Wikimedia Commons Crying_newborn_baby.ogg", 9, 12)),
    Asset("sample_water", "samples/tap_water.wav", "", "6a23c194454e8e26cfec39ce3fba5da79a4ecbf23198099251fe9916146a22e0", 96044, "public domain, stephan (PDSounds 88, via Wikimedia Commons, Faucet water into sink.ogg)", sample=True, made=cut("Wikimedia Commons Faucet_water_into_sink.ogg", 0, 3)),
    Asset("sample_speech", "samples/speech.wav", "", "ba59ab69370b64b59a1d60984afc0a90f1918ec4e4c6d3ad5a996440263677c6", 96044, "public domain, VOA Learning English (Wikimedia Commons, Puppy football lasts only one game.ogg)", sample=True, made=cut("Wikimedia Commons Puppy_football_lasts_only_one_game.ogg", 0, 3)),
    Asset("sample_alarm_t3", "samples/smoke_alarm_t3.wav", "", "e427151989157ca82e5a48e9f64acb9acc257e9fce106547107a133ee19cc7ea", 512044, "CC0, SpliceSound (Freesound 369848, Smoke detector alarm, close perspective; a real smoke alarm sounding the temporal-three pattern)", sample=True, made=cut("the Freesound 369848 preview 369848_1480854-hq.mp3", 0, 16)),
)

__all__ = ["ASSETS", "MODELS", "Asset", "check", "cli", "fetch", "main"]


def main(argv: list[str] | None = None) -> int:
    return cli(argv, ASSETS, MODELS, "python -m pebble.hearing.fetch", "the sound model Pebble's hearing uses (YAMNet)")


if __name__ == "__main__":
    sys.exit(main())
