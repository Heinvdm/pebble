import hashlib
import logging
import re
import unicodedata
from pathlib import Path

from .vectors import normalize

log = logging.getLogger(__name__)

DIM = 384
MODELS = Path(__file__).resolve().parent / "models"
MODEL_FILE = "arctic_embed_xs_int8.onnx"
VOCAB_FILE = "arctic_embed_xs_vocab.txt"
ONNX_NAME = "snowflake-arctic-embed-xs-int8"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
MAX_TOKENS = 128
WORD = re.compile(r"[a-z0-9']+")
ENDINGS = ("ing", "ed", "es", "ly", "s")


def _stem(word: str) -> str:
    word = word.strip("'")
    for ending in ENDINGS:
        if len(word) > len(ending) + 2 and word.endswith(ending):
            return word[: -len(ending)]
    return word


def _slot(feature: str) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    number = int.from_bytes(digest, "little")
    return number % DIM, (1.0 if (number >> 63) & 1 else -1.0)


class StandIn:
    name = "stand-in"
    dim = DIM
    related = 0.08

    def embed(self, texts: list[str], query: bool = False) -> list[list[float]]:
        out = []
        for text in texts:
            vector = [0.0] * DIM
            words = [_stem(w) for w in WORD.findall(str(text or "").lower())]
            words = [w for w in words if w]
            for word in words:
                index, sign = _slot("w:" + word)
                vector[index] += sign
                padded = f"<{word}>"
                for start in range(len(padded) - 2):
                    index, sign = _slot("c:" + padded[start : start + 3])
                    vector[index] += 0.3 * sign
            for left, right in zip(words, words[1:]):
                index, sign = _slot(f"b:{left} {right}")
                vector[index] += 0.5 * sign
            out.append(normalize(vector))
        return out


def _punctuation(char: str) -> bool:
    code = ord(char)
    if 33 <= code <= 47 or 58 <= code <= 64 or 91 <= code <= 96 or 123 <= code <= 126:
        return True
    return unicodedata.category(char).startswith("P")


def _cjk(code: int) -> bool:
    return 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF or 0x20000 <= code <= 0x2A6DF or 0xF900 <= code <= 0xFAFF or 0x2F800 <= code <= 0x2FA1F


class WordPiece:
    def __init__(self, vocab: dict[str, int]):
        self.vocab = vocab
        self.unk = vocab["[UNK]"]
        self.cls = vocab["[CLS]"]
        self.sep = vocab["[SEP]"]

    @classmethod
    def load(cls, path: Path) -> "WordPiece":
        vocab = {}
        for index, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
            token = line.rstrip("\n")
            if token and token not in vocab:
                vocab[token] = index
        return cls(vocab)

    def basic(self, text: str) -> list[str]:
        cleaned = []
        for char in str(text or ""):
            code = ord(char)
            if code == 0 or code == 0xFFFD or (unicodedata.category(char).startswith("C") and char not in "\t\n\r"):
                continue
            cleaned.append(f" {char} " if _cjk(code) else (" " if char.isspace() else char))
        text = unicodedata.normalize("NFD", "".join(cleaned).lower())
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")
        tokens = []
        for word in text.split():
            current = ""
            for char in word:
                if _punctuation(char):
                    if current:
                        tokens.append(current)
                        current = ""
                    tokens.append(char)
                else:
                    current += char
            if current:
                tokens.append(current)
        return tokens

    def pieces(self, word: str) -> list[int]:
        if len(word) > 100:
            return [self.unk]
        out, start = [], 0
        while start < len(word):
            end, found = len(word), None
            while start < end:
                piece = word[start:end] if start == 0 else "##" + word[start:end]
                if piece in self.vocab:
                    found = self.vocab[piece]
                    break
                end -= 1
            if found is None:
                return [self.unk]
            out.append(found)
            start = end
        return out

    def ids(self, text: str, longest: int = MAX_TOKENS) -> list[int]:
        out = []
        for word in self.basic(text):
            out.extend(self.pieces(word))
        return [self.cls] + out[: longest - 2] + [self.sep]


class OnnxEmbedder:
    name = ONNX_NAME
    dim = DIM
    related = 0.55

    def __init__(self, folder: Path = MODELS, threads: int = 1):
        import numpy
        import onnxruntime

        self.numpy = numpy
        self.tokens = WordPiece.load(Path(folder) / VOCAB_FILE)
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = max(1, int(threads))
        options.inter_op_num_threads = 1
        self.session = onnxruntime.InferenceSession(str(Path(folder) / MODEL_FILE), options, providers=["CPUExecutionProvider"])
        self.inputs = {item.name for item in self.session.get_inputs()}

    def embed(self, texts: list[str], query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        np = self.numpy
        rows = [self.tokens.ids((QUERY_PREFIX if query else "") + str(text or "")) for text in texts]
        width = max(len(row) for row in rows)
        ids = np.zeros((len(rows), width), dtype="int64")
        mask = np.zeros((len(rows), width), dtype="int64")
        for index, row in enumerate(rows):
            ids[index, : len(row)] = row
            mask[index, : len(row)] = 1
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = self.session.run(None, {k: v for k, v in feed.items() if k in self.inputs})[0]
        first = hidden[:, 0, :] if hidden.ndim == 3 else hidden
        sizes = np.linalg.norm(first, axis=1, keepdims=True)
        sizes[sizes == 0] = 1.0
        return (first / sizes).astype("float32").tolist()


def ready(folder: Path = MODELS) -> bool:
    return (Path(folder) / MODEL_FILE).exists() and (Path(folder) / VOCAB_FILE).exists()


def embedder_from(kind: str = "auto", folder: Path = MODELS):
    if kind in ("standin", "stand-in", "none"):
        return StandIn()
    if kind == "onnx" or (kind == "auto" and ready(folder)):
        try:
            return OnnxEmbedder(folder)
        except Exception as error:
            if kind == "onnx":
                raise
            log.warning("the sentence model could not start (%s); using the stand-in", error)
    return StandIn()
