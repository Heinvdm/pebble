import asyncio
import hashlib
import io
import json
import struct
import tarfile
import wave
from pathlib import Path

import pytest

from pebble.clock import FakeClock
from pebble.speech import fetch as speech_fetch
from pebble.speech.ears import SherpaEars
from pebble.speech.events import SpeechEvent, parse
from pebble.speech.phone import PhoneSpeech
from pebble.speech.tokens import Pieces, read_pieces

MODELS = speech_fetch.MODELS


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _piece(text: str, score: float, kind: int = 1) -> bytes:
    raw = text.encode("utf-8")
    inner = b"\x0a" + _varint(len(raw)) + raw + b"\x15" + struct.pack("<f", score) + b"\x18" + _varint(kind)
    return b"\x0a" + _varint(len(inner)) + inner


def tiny_model() -> bytes:
    pieces = [("<unk>", 0.0, 2), ("▁PE", -2.0, 1), ("B", -3.0, 1), ("LE", -2.5, 1), ("▁", -3.5, 1), ("P", -4.0, 1), ("E", -4.0, 1), ("L", -4.0, 1), ("▁PEBBLE", -1.0, 1), ("S", -3.0, 1)]
    return b"".join(_piece(*p) for p in pieces)


def test_unigram_reader_finds_the_best_split(tmp_path):
    pieces = read_pieces(tiny_model())
    assert ("▁PEBBLE", -1.0, 1) in [(p, round(s, 3), k) for p, s, k in pieces]
    model = Pieces(pieces)
    assert model.encode("Pebble") == ["▁PEBBLE"]
    assert model.encode("pebbles") == ["▁PEBBLE", "S"]
    assert model.encode("PEBLE") == ["▁PE", "B", "LE"]
    assert model.encode("pebble, x!") == ["▁PEBBLE", "▁", "<unk>"]
    path = tmp_path / "bpe.model"
    path.write_bytes(tiny_model())
    assert Pieces.load(path).keyword_line("Pebble") == "▁PEBBLE"


@pytest.mark.skipif(not (MODELS / "kws" / "bpe.model").exists(), reason="speech models not fetched")
def test_the_real_spotter_vocabulary_spells_names_like_sentencepiece():
    model = Pieces.load(MODELS / "kws" / "bpe.model")
    assert model.keyword_line("Pebble") == "▁P E B B LE"
    assert model.keyword_line("merry christmas") == "▁ME R RY ▁ CH R IST MA S"


def test_speech_events_parse_and_reject():
    event = parse(json.dumps({"kind": "final", "t": 12.5, "segment": 3, "text": "  what   do you think ", "start": 10.0, "end": 12.2, "print": [0.1] * 192, "print_s": 1.4, "level_db": -22.0, "keyword": True, "pebble_speaking": False}))
    assert event.kind == "final" and event.text == "what do you think" and len(event.voiceprint) == 192 and event.keyword
    assert parse('{"kind": "final"}') is None
    assert parse("not json") is None
    assert parse({"kind": "spoken", "t": 1.0, "id": "r1.1", "state": "nonsense"}) is None
    word = parse({"kind": "spoken", "t": 1.0, "id": "r1.1", "state": "word", "start": 0, "end": 7})
    assert word.part == "r1.1" and word.chars == 7
    assert parse({"kind": "final", "t": 1.0, "print": [1.0, float("nan"), 2.0, 3.0]}).voiceprint is None
    assert SpeechEvent("pause", 2.0, 4).as_dict() == {"kind": "pause", "t": 2.0, "segment": 4}


def test_phone_speech_hops_onto_the_loop():
    got = []

    async def go():
        phone = PhoneSpeech()
        phone.bind(asyncio.get_running_loop(), got.append)
        await asyncio.to_thread(phone.event, json.dumps({"kind": "voice_start", "t": 3.0, "segment": 1}))
        phone.event("{broken")
        await asyncio.sleep(0.01)
        return phone

    phone = asyncio.run(go())
    assert [e.kind for e in got] == ["voice_start"]
    assert phone.status() == {"received": 1, "bad": 1, "dropped": 0}


def _tar_with(name: str, data: bytes) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:bz2") as tar:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return raw.getvalue()


def test_fetch_takes_members_out_of_a_pinned_archive(tmp_path):
    payload = b"spotter weights"
    archive = _tar_with("model/encoder.onnx", payload)
    asset = speech_fetch.Asset("x", "kws/encoder.onnx", "https://example.invalid/model.tar.bz2", hashlib.sha256(payload).hexdigest(), len(payload), "test", member="model/encoder.onnx", archive_sha256=hashlib.sha256(archive).hexdigest(), archive_size=len(archive))
    calls = []

    def opener(url):
        calls.append(url)
        return io.BytesIO(archive)

    said = []
    assert speech_fetch.fetch((asset, asset), tmp_path, opener=opener, say=said.append)
    assert (tmp_path / "kws" / "encoder.onnx").read_bytes() == payload
    assert len(calls) == 1
    assert json.loads((tmp_path / "speech.json").read_text(encoding="utf-8"))["asr"]["encoder"] == "asr/encoder.int8.onnx"
    bad = speech_fetch.Asset("y", "kws/joiner.onnx", "https://example.invalid/model.tar.bz2", "0" * 64, 3, "test", member="model/encoder.onnx", archive_sha256=hashlib.sha256(archive).hexdigest(), archive_size=len(archive))
    assert not speech_fetch.fetch((bad,), tmp_path, opener=lambda url: io.BytesIO(archive), say=said.append)
    assert not (tmp_path / "kws" / "joiner.onnx").exists()


def test_the_manifest_in_the_tree_matches_the_fetcher():
    path = MODELS / "speech.json"
    assert path.exists()
    assert path.read_text(encoding="utf-8") == speech_fetch.manifest_text()
    layout = json.loads(path.read_text(encoding="utf-8"))
    assert layout["speaker_dims"] == 192 and set(layout["licences"]) == {"vad", "asr", "kws", "speaker", "samples"}


class FakeLife:
    def __init__(self, quiet):
        self.quiet = quiet

        class Hours:
            def contains(_, moment):
                return self.quiet

        self.quiet_hours = Hours()


def test_sherpa_ears_follow_the_policy_and_safety_wakes():
    clock = FakeClock()
    ears = SherpaEars(clock)
    assert ears.wanted_mode() == "off"
    ears.life = FakeLife(False)
    assert ears.wanted_mode() == "words"
    ears.life.quiet = True
    assert ears.wanted_mode() == "off"
    ears.policy = lambda quiet, awake: "keywords"
    assert ears.wanted_mode() == "keywords"
    ears.wake_for(30)
    assert ears.wanted_mode() == "words"
    clock.advance(31)
    assert ears.wanted_mode() == "keywords"
    ears.policy = lambda quiet, awake: "nonsense"
    assert ears.wanted_mode() == "off"


def _engine():
    pytest.importorskip("sherpa_onnx")
    pytest.importorskip("numpy")
    if not speech_fetch.ready(MODELS):
        pytest.skip("speech models not fetched")
    from pebble.speech.engine import Engine, Models, Settings

    return Engine(Models(MODELS), Settings(keywords=[{"word": "yellow lamps"}, {"word": "pebble"}]))


def _sample(name: str):
    import numpy

    path = MODELS / "samples" / name
    if not path.exists():
        pytest.skip("speech samples not fetched")
    with wave.open(str(path)) as handle:
        x = numpy.frombuffer(handle.readframes(handle.getnframes()), dtype=numpy.int16).astype(numpy.float32) / 32768.0
    return numpy.concatenate([numpy.zeros(8000, numpy.float32), x, numpy.zeros(16000, numpy.float32)])


def test_the_pc_engine_hears_words_a_keyword_and_a_voice_print():
    engine = _engine()
    x = _sample("librispeech_0.wav")
    events = []
    t = 100.0
    for i in range(0, len(x), 1600):
        piece = x[i : i + 1600]
        t += len(piece) / 16000
        events.extend(engine.feed(piece, t))
    kinds = [e.kind for e in events]
    assert kinds[0] == "voice_start" and "partial" in kinds and "voice_end" in kinds
    final = next(e for e in events if e.kind == "final")
    assert "yellow lamps" in final.text and "nightfall" in final.text
    assert final.voiceprint is not None and len(final.voiceprint) == 192 and final.print_s > 4.0
    assert any(e.kind == "keyword" and e.word == "yellow lamps" for e in events)
    assert not any(e.kind == "keyword" and e.word == "pebble" for e in events)
    end = next(e for e in events if e.kind == "voice_end")
    assert end.t - end.end == pytest.approx(0.25, abs=0.07)


def test_the_pc_engine_in_keyword_mode_hears_no_words():
    engine = _engine()
    engine.configure(mode="keywords")
    x = _sample("librispeech_0.wav")
    events = []
    t = 0.0
    for i in range(0, len(x), 1600):
        piece = x[i : i + 1600]
        t += len(piece) / 16000
        events.extend(engine.feed(piece, t))
    assert {e.kind for e in events} == {"keyword"}
    engine.configure(mode="off")
    assert engine.feed(x[:16000], t + 1.0) == []
