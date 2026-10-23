import json
import logging
import math
import os
import tempfile
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .events import MODES, SpeechEvent
from .fetch import MANIFEST, MODELS
from .tokens import Pieces

log = logging.getLogger(__name__)

RATE = 16000
WINDOW = 512
TARGET_DB = -23.0
START_DB = -35.0
MIN_GAIN = 0.5
MAX_GAIN = 30.0
LEVEL_ALPHA = 0.08
TAIL_S = 0.5
FLUSH_S = 0.64


class NoEngine(RuntimeError):
    pass


@dataclass
class Settings:
    mode: str = "words"
    keywords: list = field(default_factory=list)
    vad_threshold: float = 0.5
    min_speech_s: float = 0.1
    min_silence_s: float = 0.25
    max_speech_s: float = 15.0
    pre_roll_s: float = 0.3
    print_min_s: float = 1.0
    threads: int = 1

    def update(self, values: dict) -> bool:
        changed = False
        for name, value in values.items():
            if not hasattr(self, name) or value is None:
                continue
            if name == "mode" and value not in MODES:
                continue
            if getattr(self, name) != value:
                setattr(self, name, value)
                changed = True
        return changed


def load_manifest(folder: Path = MODELS) -> dict:
    path = Path(folder) / MANIFEST
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise NoEngine(f"no speech models at {folder} (run python -m pebble.speech.fetch): {error}") from error


def _modules():
    try:
        import numpy
        import sherpa_onnx
    except ImportError as error:
        raise NoEngine("sherpa-onnx and numpy are needed for words on this machine (pip install sherpa-onnx numpy)") from error
    return numpy, sherpa_onnx


def keyword_lines(pieces: Pieces, keywords: list) -> str:
    lines = []
    for item in keywords:
        if isinstance(item, str):
            item = {"word": item}
        word = str(item.get("word") or "").strip()
        tokens = str(item.get("tokens") or "").strip() or pieces.keyword_line(word)
        if not word or not tokens:
            continue
        boost = float(item.get("boost", 2.0))
        threshold = float(item.get("threshold", 0.15))
        lines.append(f"{tokens} :{boost:g} #{threshold:g} @{word.lower().replace(' ', '_')}")
    return "\n".join(lines)


class Models:
    def __init__(self, folder: Path = MODELS, threads: int = 1):
        np, sherpa = _modules()
        self.np = np
        self.sherpa = sherpa
        self.folder = Path(folder)
        layout = load_manifest(self.folder)
        path = lambda rel: str(self.folder / rel)
        asr, kws = layout["asr"], layout["kws"]
        missing = [rel for rel in (layout["vad"], asr["encoder"], asr["decoder"], asr["joiner"], asr["tokens"], kws["encoder"], kws["decoder"], kws["joiner"], kws["tokens"], kws["bpe"], layout["speaker"]) if not (self.folder / rel).exists()]
        if missing:
            raise NoEngine(f"speech model files missing ({', '.join(missing)}); run python -m pebble.speech.fetch")
        self.layout = layout
        self.vad_config = sherpa.VadModelConfig(
            silero_vad=sherpa.SileroVadModelConfig(model=path(layout["vad"]), threshold=0.5, min_silence_duration=0.064, min_speech_duration=0.064, window_size=WINDOW),
            sample_rate=RATE,
            num_threads=1,
        )
        self.asr = sherpa.OnlineRecognizer.from_transducer(
            tokens=path(asr["tokens"]), encoder=path(asr["encoder"]), decoder=path(asr["decoder"]), joiner=path(asr["joiner"]), num_threads=threads, sample_rate=RATE, feature_dim=80, decoding_method="greedy_search", model_type=asr.get("model_type", "")
        )
        self.pieces = Pieces.load(path(kws["bpe"]))
        self.kws_paths = {name: path(kws[name]) for name in ("encoder", "decoder", "joiner", "tokens")}
        self.threads = threads
        self._spotter = None
        self.speaker = sherpa.SpeakerEmbeddingExtractor(sherpa.SpeakerEmbeddingExtractorConfig(model=path(layout["speaker"]), num_threads=threads))

    def vad(self):
        return self.sherpa.VadModel.create(self.vad_config)

    def spotter(self, keywords: list):
        text = keyword_lines(self.pieces, keywords)
        if not text:
            return None, ""
        if self._spotter is None:
            handle, name = tempfile.mkstemp(prefix="pebble-kws-", suffix=".txt")
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as out:
                    out.write(text + chr(10))
                self._spotter = self.sherpa.KeywordSpotter(
                    tokens=self.kws_paths["tokens"], encoder=self.kws_paths["encoder"], decoder=self.kws_paths["decoder"], joiner=self.kws_paths["joiner"], keywords_file=name, num_threads=1, num_trailing_blanks=1
                )
            finally:
                try:
                    os.unlink(name)
                except OSError:
                    pass
        return self._spotter, text


class Gain:
    def __init__(self, target_db: float = TARGET_DB):
        self.target_db = target_db
        self.power = 10.0 ** (START_DB / 10.0)

    def voiced(self, rms: float) -> None:
        self.power += LEVEL_ALPHA * (rms * rms - self.power)

    @property
    def level_db(self) -> float:
        return 10.0 * math.log10(max(self.power, 1e-12))

    @property
    def factor(self) -> float:
        return max(MIN_GAIN, min(MAX_GAIN, 10.0 ** ((self.target_db - self.level_db) / 20.0)))


class Engine:
    def __init__(self, models: Models, settings: Settings | None = None, speaking: Callable[[], bool] = lambda: False):
        self.m = models
        self.np = models.np
        self.s = settings or Settings()
        self.speaking = speaking
        self.vad = models.vad()
        self.gain = Gain()
        self.spotter = None
        self.spot_stream = None
        self.spot_text = ""
        self.segment = 0
        self.in_speech = False
        self.paused_at: float | None = None
        self.on_run = 0
        self.pre: deque = deque()
        self.pre_samples = 0
        self.audio: list = []
        self.stream = None
        self.partial = ""
        self.started_at = 0.0
        self.keyword_hit = False
        self.levels: list[float] = []
        self.peak = 0.0
        self.carry = None
        self.spent = 0.0
        self.fed = 0.0
        self._keywords(self.s.keywords)

    def _keywords(self, keywords: list) -> None:
        try:
            self.spotter, self.spot_text = self.m.spotter(keywords)
        except Exception as error:
            log.warning("speech: the name spotter would not start: %s", error)
            self.spotter, self.spot_text = None, ""
        self.spot_stream = self.spotter.create_stream(keywords=self.spot_text.replace(chr(10), '/')) if self.spotter is not None else None

    def configure(self, **values) -> None:
        keywords = values.get("keywords")
        before = list(self.s.keywords)
        self.s.update(values)
        if keywords is not None and keywords != before:
            self._keywords(self.s.keywords)
        if self.s.mode != "words" and self.in_speech:
            self.segment_reset()

    def segment_reset(self) -> None:
        self.in_speech = False
        self.stream = None
        self.audio = []
        self.partial = ""
        self.paused_at = None
        self.on_run = 0

    def gap(self) -> None:
        self.segment_reset()
        self.pre.clear()
        self.pre_samples = 0
        self.carry = None
        self.vad.reset()
        if self.spotter is not None:
            self.spot_stream = self.spotter.create_stream(keywords=self.spot_text.replace(chr(10), '/'))

    def feed(self, samples, end_t: float) -> list[SpeechEvent]:
        if self.s.mode == "off":
            self.carry = None
            return []
        np = self.np
        started = time.perf_counter()
        x = np.asarray(samples, dtype=np.float32).reshape(-1)
        if self.carry is not None and len(self.carry):
            x = np.concatenate([self.carry, x])
        count = len(x) // WINDOW
        self.carry = x[count * WINDOW :]
        first_t = end_t - (len(x) - count * WINDOW) / RATE - count * WINDOW / RATE
        out: list[SpeechEvent] = []
        for index in range(count):
            window = x[index * WINDOW : (index + 1) * WINDOW]
            t = first_t + (index + 1) * WINDOW / RATE
            out.extend(self._window(window, t))
        self.spent += time.perf_counter() - started
        self.fed += len(samples) / RATE
        return out

    def _window(self, window, t: float) -> list[SpeechEvent]:
        np = self.np
        out: list[SpeechEvent] = []
        speech = bool(self.vad.is_speech(window))
        rms = float(np.sqrt(np.mean(window * window)))
        if speech:
            self.gain.voiced(rms)
        scaled = np.clip(window * self.gain.factor, -1.0, 1.0)
        speaking = bool(self.speaking())
        out.extend(self._spot(scaled, t, speaking))
        if self.s.mode != "words":
            if not speech and self.on_run:
                out.extend(self._flush(t, speaking))
            self.on_run = self.on_run + 1 if speech else 0
            return out
        self.pre.append(scaled)
        self.pre_samples += len(scaled)
        while self.pre_samples - len(self.pre[0]) >= self.s.pre_roll_s * RATE:
            self.pre_samples -= len(self.pre.popleft())
        if not self.in_speech:
            self.on_run = self.on_run + 1 if speech else 0
            if self.on_run * WINDOW >= self.s.min_speech_s * RATE:
                out.extend(self._begin(t, speaking))
            return out
        self.stream.accept_waveform(RATE, scaled)
        self.audio.append(scaled)
        if speech:
            self.levels.append(rms)
            self.peak = max(self.peak, float(np.max(np.abs(window))))
            self.paused_at = None
        elif self.paused_at is None:
            self.paused_at = t - WINDOW / RATE
            out.append(SpeechEvent("pause", t, self.segment, pebble_speaking=speaking))
            out.extend(self._flush(t, speaking))
        out.extend(self._decode(t, speaking))
        silent = self.paused_at is not None and t - self.paused_at >= self.s.min_silence_s
        if silent or t - self.started_at >= self.s.max_speech_s:
            out.extend(self._end(t, speaking))
        return out

    def _begin(self, t: float, speaking: bool) -> list[SpeechEvent]:
        np = self.np
        self.segment += 1
        self.in_speech = True
        self.paused_at = None
        self.keyword_hit = False
        self.levels = []
        self.peak = 0.0
        self.partial = ""
        self.stream = self.m.asr.create_stream()
        pre = np.concatenate(list(self.pre)) if self.pre else np.zeros(0, dtype=np.float32)
        self.started_at = t - len(pre) / RATE
        self.stream.accept_waveform(RATE, pre)
        self.audio = [pre]
        return [SpeechEvent("voice_start", t, self.segment, start=self.started_at, pebble_speaking=speaking)]

    def _decode(self, t: float, speaking: bool) -> list[SpeechEvent]:
        asr = self.m.asr
        while asr.is_ready(self.stream):
            asr.decode_stream(self.stream)
        text = asr.get_result(self.stream).strip()
        if text and text != self.partial:
            self.partial = text
            return [SpeechEvent("partial", t, self.segment, text=text, pebble_speaking=speaking)]
        return []

    def _end(self, t: float, speaking: bool) -> list[SpeechEvent]:
        np = self.np
        asr = self.m.asr
        end = self.paused_at if self.paused_at is not None else t
        out = [SpeechEvent("voice_end", t, self.segment, end=end, pebble_speaking=speaking)]
        self.stream.accept_waveform(RATE, np.zeros(int(TAIL_S * RATE), dtype=np.float32))
        self.stream.input_finished()
        while asr.is_ready(self.stream):
            asr.decode_stream(self.stream)
        text = asr.get_result(self.stream).strip()
        audio = np.concatenate(self.audio) if self.audio else np.zeros(0, dtype=np.float32)
        voiced = audio[: max(0, int((end - self.started_at) * RATE))]
        speech_s = len(self.levels) * WINDOW / RATE
        voiceprint = None
        if speech_s >= self.s.print_min_s and len(voiced):
            voiceprint = self.print_of(voiced)
        level = 20.0 * math.log10(max(1e-6, math.sqrt(sum(r * r for r in self.levels) / len(self.levels)))) if self.levels else None
        peak = 20.0 * math.log10(max(1e-6, self.peak)) if self.levels else None
        out.append(
            SpeechEvent(
                "final",
                t,
                self.segment,
                text=text,
                start=self.started_at,
                end=end,
                voiceprint=voiceprint,
                print_s=round(speech_s, 2) if voiceprint is not None else 0.0,
                level_db=None if level is None else round(level, 1),
                peak_db=None if peak is None else round(peak, 1),
                keyword=self.keyword_hit,
                pebble_speaking=speaking,
            )
        )
        self.segment_reset()
        return out

    def print_of(self, audio) -> tuple[float, ...] | None:
        extractor = self.m.speaker
        stream = extractor.create_stream()
        stream.accept_waveform(RATE, audio)
        stream.input_finished()
        if not extractor.is_ready(stream):
            return None
        return tuple(round(float(v), 5) for v in extractor.compute(stream))

    def _spot(self, scaled, t: float, speaking: bool) -> list[SpeechEvent]:
        if self.spot_stream is None:
            return []
        self.spot_stream.accept_waveform(RATE, scaled)
        return self._spotted(t, speaking)

    def _flush(self, t: float, speaking: bool) -> list[SpeechEvent]:
        if self.spot_stream is None:
            return []
        self.spot_stream.accept_waveform(RATE, self.np.zeros(int(FLUSH_S * RATE), dtype=self.np.float32))
        return self._spotted(t, speaking)

    def _spotted(self, t: float, speaking: bool) -> list[SpeechEvent]:
        out = []
        spotter = self.spotter
        while spotter.is_ready(self.spot_stream):
            spotter.decode_stream(self.spot_stream)
            word = spotter.get_result(self.spot_stream)
            if word:
                spotter.reset_stream(self.spot_stream)
                self.keyword_hit = self.keyword_hit or self.in_speech
                out.append(SpeechEvent("keyword", t, self.segment, word=word.replace("_", " "), pebble_speaking=speaking))
        return out

    def status(self) -> dict:
        return {
            "mode": self.s.mode,
            "segment": self.segment,
            "in_speech": self.in_speech,
            "gain_db": round(20 * math.log10(self.gain.factor), 1),
            "keywords": self.spot_text.count("\n") + 1 if self.spot_text else 0,
            "cpu_ms_per_s": round(1000 * self.spent / self.fed, 1) if self.fed else None,
        }
