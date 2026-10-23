import array
import importlib.util
import math
import sys
import wave

import pytest

from pebble.hearing import fetch as fetching
from pebble.hearing.yamnet import NoYamnet, Yamnet, read_labels, read_wav

MODELS = fetching.MODELS
SAMPLES = MODELS / "samples"
EXPECTED = {
    "smoke_alarm.wav": {"Smoke detector, smoke alarm", "Fire alarm", "Alarm", "Beep, bleep"},
    "smoke_alarm_t3.wav": {"Smoke detector, smoke alarm"},
    "glass_breaking.wav": {"Glass", "Shatter", "Breaking"},
    "dog_barking.wav": {"Dog", "Bark", "Bow-wow"},
    "baby_crying.wav": {"Baby cry, infant cry"},
    "tap_water.wav": {"Water tap, faucet", "Sink (filling or washing)", "Water"},
    "speech.wav": {"Speech"},
}

needs_numpy = pytest.mark.skipif(importlib.util.find_spec("numpy") is None, reason="numpy is not installed")
needs_model = pytest.mark.skipif(not Yamnet.available(), reason="YAMNet is not here (tools/export_yamnet.py, python -m pebble.hearing.fetch) or neither onnxruntime nor OpenCV is installed")


def write_wav(path, frames: list[list[int]], width: int, rate: int) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(len(frames[0]))
        out.setsampwidth(width)
        out.setframerate(rate)
        data = bytearray()
        for frame in frames:
            for value in frame:
                if width == 1:
                    data += bytes([value + 128])
                else:
                    data += int(value).to_bytes(width, "little", signed=True)
        out.writeframes(bytes(data))


def test_every_hearing_file_is_pinned_with_a_licence():
    keys = [a.key for a in fetching.ASSETS]
    assert len(keys) == len(set(keys))
    for asset in fetching.ASSETS:
        assert len(asset.sha256) == 64 and int(asset.sha256, 16) >= 0 and asset.size > 0 and asset.licence
        assert asset.url.startswith("https://") or (asset.made and not asset.url)
    assert {a.path for a in fetching.ASSETS if a.sample} == {f"samples/{name}" for name in EXPECTED}
    assert fetching.MODELS.name == "models" and fetching.MODELS.parent.name == "hearing"
    assert callable(fetching.fetch) and callable(fetching.check) and callable(fetching.main)


def test_the_class_map_reader_refuses_other_files(tmp_path):
    good = tmp_path / "good.csv"
    good.write_text('index,mid,display_name\n0,/m/09x0r,Speech\n1,/m/0ytgt,"Child speech, kid speaking"\n', encoding="utf-8")
    assert read_labels(good) == ["Speech", "Child speech, kid speaking"]
    shuffled = tmp_path / "shuffled.csv"
    shuffled.write_text("index,mid,display_name\n1,/m/0ytgt,Child\n0,/m/09x0r,Speech\n", encoding="utf-8")
    other = tmp_path / "other.csv"
    other.write_text("name,score\ndog,1\n", encoding="utf-8")
    for bad in (shuffled, other):
        with pytest.raises(NoYamnet):
            read_labels(bad)


def test_nothing_is_available_without_the_model(tmp_path):
    assert not Yamnet.available(tmp_path)
    with pytest.raises(NoYamnet, match="missing"):
        Yamnet.load(tmp_path)


@needs_numpy
def test_read_wav_gives_16_khz_mono(tmp_path):
    tone = [round(16000 * math.sin(2 * math.pi * 440 * i / 44100)) for i in range(44100)]
    stereo = tmp_path / "stereo.wav"
    write_wav(stereo, [[v, v] for v in tone], 2, 44100)
    rate, samples = read_wav(stereo)
    assert rate == 16000 and len(samples) == 16000
    assert 0.45 < float(abs(samples[1000:-1000]).max()) < 0.52
    deep = tmp_path / "deep.wav"
    write_wav(deep, [[v * 256] for v in tone[:16000]], 3, 16000)
    rate, samples = read_wav(deep)
    assert rate == 16000 and len(samples) == 16000 and 0.48 < float(abs(samples).max()) < 0.5
    narrow = tmp_path / "narrow.wav"
    write_wav(narrow, [[64], [-64]] * 4000, 1, 8000)
    rate, samples = read_wav(narrow)
    assert rate == 16000 and len(samples) == 16000
    rate, kept = read_wav(stereo, rate=None)
    assert rate == 44100 and len(kept) == 44100


@pytest.fixture(scope="module")
def yamnet():
    if not Yamnet.available():
        pytest.skip("YAMNet is not here")
    return Yamnet.load(threads=1)


@needs_model
def test_the_class_map_has_521_sounds_in_order(yamnet):
    assert len(yamnet.labels) == 521 and yamnet.window == 15600 and yamnet.rate == 16000 and yamnet.hop == 7680
    assert yamnet.labels[0] == "Speech" and yamnet.labels[494] == "Silence" and yamnet.labels[393] == "Smoke detector, smoke alarm"


@needs_model
def test_scores_are_521_probabilities(yamnet):
    np = pytest.importorskip("numpy")
    quiet = yamnet.scores([0.0] * yamnet.window)
    assert len(quiet) == 521 and all(0.0 <= s <= 1.0 for s in quiet)
    assert yamnet.top(quiet, 1)[0][1] == "Silence" and quiet[494] > 0.9
    t = np.arange(yamnet.window) / 16000.0
    tone = 0.5 * np.sin(2 * np.pi * 440 * t)
    scores = yamnet.scores(tone)
    assert 0.5 < sum(scores) < 30 and max(scores) > 0.5
    assert yamnet.labels[int(np.argmax(scores))] != "Silence"


@needs_model
def test_scores_fit_the_window_and_take_int16(yamnet):
    np = pytest.importorskip("numpy")
    rng = np.random.default_rng(5)
    longer = (rng.standard_normal(yamnet.window + 4000) * 0.1).astype(np.float32)
    assert np.allclose(yamnet.scores(longer), yamnet.scores(longer[-yamnet.window:]), atol=1e-6)
    short = longer[:9000]
    padded = np.concatenate([short, np.zeros(yamnet.window - short.size, np.float32)])
    assert np.allclose(yamnet.scores(short), yamnet.scores(padded), atol=1e-6)
    pcm = array.array("h", (int(v * 32767) for v in longer[:yamnet.window]))
    assert np.allclose(yamnet.scores(pcm), yamnet.scores(np.array(pcm, np.float32) / 32768.0), atol=1e-6)
    assert len(yamnet.frames(longer)) == 2 and len(yamnet.frames(short)) == 1


@needs_model
@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_sample_is_heard_as_what_it_is(yamnet, name):
    np = pytest.importorskip("numpy")
    path = SAMPLES / name
    if not path.exists():
        pytest.skip(f"{name} is not here (python -m pebble.hearing.fetch --samples)")
    rate, samples = read_wav(path)
    loudest = np.array(yamnet.frames(samples)).max(axis=0)
    top = [label for _, label, _ in yamnet.top(loudest.tolist(), 5)]
    assert EXPECTED[name] & set(top), f"{name}: top five were {top}"


@needs_model
def test_opencv_hears_the_same(yamnet):
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2", reason="OpenCV is not installed")
    pytest.importorskip("onnxruntime", reason="onnxruntime is not installed")
    other = Yamnet.load(backend="opencv")
    t = np.arange(other.window) / 16000.0
    sound = (0.3 * np.sin(2 * np.pi * 3100 * t) * (np.sin(2 * np.pi * 3 * t) > 0)).astype(np.float32)
    assert other.backend.startswith("opencv") and yamnet.backend.startswith("onnxruntime")
    assert np.abs(np.array(other.scores(sound)) - np.array(yamnet.scores(sound))).max() < 1e-3


@needs_model
def test_opencv_steps_in_without_onnxruntime(monkeypatch):
    pytest.importorskip("cv2", reason="OpenCV is not installed")
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    assert Yamnet.load().backend.startswith("opencv")
    with pytest.raises(NoYamnet, match="onnxruntime is not installed"):
        Yamnet.load(backend="onnxruntime")
