import hashlib
import hmac
import re
import secrets

ITERATIONS = 3_000
MAX_WORDS = 3
MASK = "[family word]"
_WORD = re.compile(r"[^\w']+", re.UNICODE)


class BadFamilyWord(ValueError):
    pass


def words_of(text: str) -> list[str]:
    return [w for w in (_WORD.sub("", raw).lower() for raw in str(text).split()) if w]


def _digest(words: list[str], salt: bytes, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", " ".join(words).encode("utf-8"), salt, iterations).hex()


def make(phrase: str, iterations: int = ITERATIONS) -> dict:
    words = words_of(phrase)
    if not 1 <= len(words) <= MAX_WORDS:
        raise BadFamilyWord(f"a family word is one to {MAX_WORDS} words")
    if sum(len(w) for w in words) < 4:
        raise BadFamilyWord("a family word needs at least four letters")
    salt = secrets.token_bytes(16)
    return {"algorithm": "pbkdf2_sha256", "iterations": iterations, "salt": salt.hex(), "words": len(words), "hash": _digest(words, salt, iterations)}


def _valid(record) -> bool:
    return isinstance(record, dict) and bool(record.get("hash")) and bool(record.get("salt")) and int(record.get("words", 0)) >= 1


def screen(text: str, record: dict | None) -> tuple[str, bool]:
    if not _valid(record):
        return text, False
    tokens = str(text).split()
    size = int(record["words"])
    salt = bytes.fromhex(record["salt"])
    iterations = int(record.get("iterations", ITERATIONS))
    for start in range(0, len(tokens) - size + 1):
        window = words_of(" ".join(tokens[start : start + size]))
        if len(window) != size:
            continue
        if hmac.compare_digest(_digest(window, salt, iterations), record["hash"]):
            return " ".join(tokens[:start] + [MASK] + tokens[start + size :]), True
    return text, False


def matches(record: dict | None, phrase: str) -> bool:
    if not _valid(record):
        return False
    words = words_of(phrase)
    if len(words) != int(record["words"]):
        return False
    return hmac.compare_digest(_digest(words, bytes.fromhex(record["salt"]), int(record.get("iterations", ITERATIONS))), record["hash"])
