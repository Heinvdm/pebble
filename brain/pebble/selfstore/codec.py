import base64
import binascii
import re
from pathlib import PurePosixPath

from .atomic import TamperedFile, TornLine

MAGIC = b"PEBBLE-SEALED-1\n"
LINE_MARK = "sealed1:"
LINE_END = "."
FILE_AAD = b"pebble-self-file\x00"
LINE_AAD = b"pebble-self-line\x00"
_ROTATED = re.compile(r"^(.*\.jsonl)\.\d+$")


class BadSeal(ValueError):
    pass


def logical(name: str) -> str:
    text = PurePosixPath(str(name).replace("\\", "/")).as_posix()
    rotated = _ROTATED.match(text)
    if rotated:
        return rotated.group(1)
    if text.endswith(".bak"):
        return text[: -len(".bak")]
    return text


def is_line_file(name: str) -> bool:
    return logical(name).endswith(".jsonl")


class PlainCodec:
    sealed = False

    def encode(self, name: str, data: bytes) -> bytes:
        return data

    def decode(self, name: str, blob: bytes) -> bytes:
        return blob

    def encode_line(self, name: str, text: str) -> str:
        return text

    def decode_line(self, name: str, text: str) -> str:
        return text


PLAIN = PlainCodec()


class SealedCodec:
    sealed = True

    def __init__(self, cipher):
        self._cipher = cipher

    def encode(self, name: str, data: bytes) -> bytes:
        return MAGIC + self._cipher.seal(bytes(data), FILE_AAD + logical(name).encode("utf-8"))

    def decode(self, name: str, blob: bytes) -> bytes:
        if not blob.startswith(MAGIC):
            raise TamperedFile(f"{name} is not sealed")
        try:
            return self._cipher.open(blob[len(MAGIC):], FILE_AAD + logical(name).encode("utf-8"))
        except BadSeal as error:
            raise TamperedFile(f"{name} does not open: it was edited or copied from another file") from error

    def encode_line(self, name: str, text: str) -> str:
        sealed = self._cipher.seal(text.encode("utf-8"), LINE_AAD + logical(name).encode("utf-8"))
        return LINE_MARK + base64.urlsafe_b64encode(sealed).decode("ascii") + LINE_END

    def decode_line(self, name: str, text: str) -> str:
        text = text.strip()
        if not text.startswith(LINE_MARK):
            raise TamperedFile(f"a line in {name} is not sealed")
        if not text.endswith(LINE_END):
            raise TornLine(f"a line in {name} was cut short")
        body = text[len(LINE_MARK): -len(LINE_END)]
        try:
            blob = base64.urlsafe_b64decode(body.encode("ascii"))
        except (binascii.Error, ValueError, UnicodeEncodeError) as error:
            raise TamperedFile(f"a line in {name} is damaged") from error
        try:
            data = self._cipher.open(blob, LINE_AAD + logical(name).encode("utf-8"))
        except BadSeal as error:
            raise TamperedFile(f"a line in {name} does not open: it was edited or moved") from error
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise TamperedFile(f"a line in {name} is damaged") from error
