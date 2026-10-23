import struct
import unicodedata
from pathlib import Path

SPACE = "▁"
NORMAL = 1
UNKNOWN = 2
USER = 4


class BadModel(ValueError):
    pass


def _varint(data: bytes, at: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if at >= len(data):
            raise BadModel("the model file ends in the middle of a number")
        byte = data[at]
        at += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, at
        shift += 7


def _fields(data: bytes):
    at = 0
    while at < len(data):
        key, at = _varint(data, at)
        number, kind = key >> 3, key & 7
        if kind == 0:
            value, at = _varint(data, at)
        elif kind == 1:
            value, at = data[at : at + 8], at + 8
        elif kind == 2:
            size, at = _varint(data, at)
            value, at = data[at : at + size], at + size
        elif kind == 5:
            value, at = data[at : at + 4], at + 4
        else:
            raise BadModel(f"unexpected field kind {kind}")
        yield number, kind, value


def read_pieces(data: bytes) -> list[tuple[str, float, int]]:
    pieces = []
    for number, kind, value in _fields(data):
        if number != 1 or kind != 2:
            continue
        piece, score, sort = "", 0.0, NORMAL
        for inner, inner_kind, item in _fields(value):
            if inner == 1 and inner_kind == 2:
                piece = item.decode("utf-8")
            elif inner == 2 and inner_kind == 5:
                score = struct.unpack("<f", item)[0]
            elif inner == 3 and inner_kind == 0:
                sort = item
        pieces.append((piece, score, sort))
    if not pieces:
        raise BadModel("no pieces in the model file")
    return pieces


class Pieces:
    def __init__(self, pieces: list[tuple[str, float, int]], upper: bool = True):
        self.score = {piece: score for piece, score, sort in pieces if sort in (NORMAL, USER)}
        self.unknown = next((piece for piece, _, sort in pieces if sort == UNKNOWN), "<unk>")
        self.unknown_score = min(self.score.values(), default=0.0) - 10.0
        self.longest = max((len(piece) for piece in self.score), default=1)
        self.upper = upper

    @classmethod
    def load(cls, path, upper: bool = True) -> "Pieces":
        return cls(read_pieces(Path(path).read_bytes()), upper)

    def normalise(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text)
        if self.upper:
            text = text.upper()
        kept = "".join(ch if ch.isalnum() or ch == "'" else " " for ch in text)
        return " ".join(kept.split())

    def encode_word(self, word: str) -> list[str]:
        text = SPACE + word
        size = len(text)
        best: list[tuple[float, int, str] | None] = [None] * (size + 1)
        best[0] = (0.0, 0, "")
        for end in range(1, size + 1):
            for start in range(max(0, end - self.longest), end):
                if best[start] is None:
                    continue
                piece = text[start:end]
                score = self.score.get(piece)
                if score is None:
                    if end - start != 1:
                        continue
                    score, piece = self.unknown_score, self.unknown
                total = best[start][0] + score
                if best[end] is None or total > best[end][0]:
                    best[end] = (total, start, piece)
        out = []
        at = size
        while at > 0:
            _, start, piece = best[at]
            out.append(piece)
            at = start
        return out[::-1]

    def encode(self, text: str) -> list[str]:
        out: list[str] = []
        for word in self.normalise(text).split():
            out.extend(self.encode_word(word))
        return out

    def keyword_line(self, text: str) -> str:
        return " ".join(self.encode(text))
