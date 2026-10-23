import base64
import binascii
import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field

from . import shamir
from .errors import CardError

COUNT = 3
THRESHOLD = 2
SET_BYTES = 5
SHARE_BYTES = 32
CHECK_BYTES = 2
CODE_LENGTH = 64
ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
TYPOS = str.maketrans("018", "OIB")
_CODE_LINE = re.compile(r"code\s*:", re.IGNORECASE)


@dataclass(frozen=True)
class Card:
    set_id: str
    number: int
    share: bytes

    def __repr__(self) -> str:
        return f"Card(set_id={self.set_id!r}, number={self.number})"


def new_set_id() -> str:
    return base64.b32encode(secrets.token_bytes(SET_BYTES)).decode("ascii")


def pretty_set(set_id: str) -> str:
    return f"{set_id[:4]}-{set_id[4:]}"


def _set_bytes(set_id: str) -> bytes:
    try:
        raw = base64.b32decode(set_id.encode("ascii"))
    except (binascii.Error, ValueError, UnicodeEncodeError) as error:
        raise CardError(f"{set_id!r} is not a card set") from error
    if len(raw) != SET_BYTES:
        raise CardError(f"{set_id!r} is not a card set")
    return raw


def check_of(set_bytes: bytes, number: int, share: bytes) -> bytes:
    return hashlib.sha256(b"pebble-card-v1\x00" + set_bytes + bytes([number]) + share).digest()[:CHECK_BYTES]


def code_of(card: Card) -> str:
    set_bytes = _set_bytes(card.set_id)
    payload = set_bytes + bytes([card.number]) + card.share + check_of(set_bytes, card.number, card.share)
    return base64.b32encode(payload).decode("ascii")


def deal(secret: bytes, coeffs: bytes, set_id: str) -> list[Card]:
    if len(secret) != SHARE_BYTES:
        raise CardError(f"a card carries {SHARE_BYTES} bytes")
    return [Card(set_id, number, shamir.share(secret, coeffs, number)) for number in range(1, COUNT + 1)]


def render(card: Card) -> str:
    code = code_of(card)
    groups = [code[i:i + 4] for i in range(0, len(code), 4)]
    lines = ["-".join(groups[i:i + 4]) for i in range(0, len(groups), 4)]
    rule = "=" * 60
    return "\n".join([
        rule,
        f"PEBBLE RECOVERY CARD {card.number} OF {COUNT}          set {pretty_set(card.set_id)}",
        rule,
        "Any two of the three cards open Pebble's sealed self and its locked room.",
        "One card alone tells nothing. Keep the cards in different places.",
        "",
        *[f"  code: {line}" for line in lines],
        "",
        "Typing it back: spaces, dashes and capitals do not matter.",
        "Use: python -m pebble.seal recover",
        rule,
    ])


def clean_code(text: str) -> str:
    lines = [line for line in str(text).splitlines() if _CODE_LINE.search(line)]
    raw = " ".join(_CODE_LINE.split(line, 1)[1] for line in lines) if lines else str(text)
    return "".join(ch for ch in raw.upper() if not ch.isspace() and ch not in "-_.").translate(TYPOS)


def parse(text: str) -> Card:
    code = clean_code(text)
    if not code:
        raise CardError("That card is empty.")
    strange = sorted({ch for ch in code if ch not in ALPHABET})
    if strange:
        raise CardError(f"That card has characters no card uses: {' '.join(strange)}. Read it again.")
    if len(code) != CODE_LENGTH:
        raise CardError(f"A card code has {CODE_LENGTH} letters and digits; this one has {len(code)}. Look for a missing or doubled group.")
    payload = base64.b32decode(code.encode("ascii"))
    set_bytes = payload[:SET_BYTES]
    number = payload[SET_BYTES]
    share = payload[SET_BYTES + 1: SET_BYTES + 1 + SHARE_BYTES]
    check = payload[SET_BYTES + 1 + SHARE_BYTES:]
    if check != check_of(set_bytes, number, share):
        raise CardError("The card's check does not match: a letter is probably mistyped. Read it again carefully.")
    if not 1 <= number <= COUNT:
        raise CardError(f"Card number {number} does not exist; cards are 1 to {COUNT}.")
    return Card(base64.b32encode(set_bytes).decode("ascii"), number, share)


def join(cards: list[Card]) -> bytes:
    if len(cards) < THRESHOLD:
        raise CardError("Two different cards are needed; one card alone opens nothing.")
    sets = {card.set_id for card in cards}
    if len(sets) > 1:
        raise CardError("These cards come from different sets: " + ", ".join(pretty_set(s) for s in sorted(sets)) + ".")
    numbers = [card.number for card in cards]
    if len(set(numbers)) != len(numbers):
        raise CardError("That is the same card twice; two different cards are needed.")
    return shamir.combine([(card.number, card.share) for card in cards])


@dataclass(frozen=True)
class Recovery:
    secret: bytes = field(repr=False)
    coeffs: bytes = field(repr=False)
    set_id: str

    @classmethod
    def generate(cls) -> "Recovery":
        return cls(secrets.token_bytes(SHARE_BYTES), shamir.coefficients(SHARE_BYTES, THRESHOLD), new_set_id())

    @classmethod
    def from_cards(cls, cards: list[Card]) -> "Recovery":
        secret = join(cards)
        first = cards[0]
        return cls(secret, shamir.slope(secret, first.number, first.share), first.set_id)

    def cards(self) -> list[Card]:
        return deal(self.secret, self.coeffs, self.set_id)

    def pack(self) -> bytes:
        return json.dumps({"secret": self.secret.hex(), "coefficients": self.coeffs.hex(), "set_id": self.set_id}, sort_keys=True).encode("utf-8")

    @classmethod
    def unpack(cls, data: bytes) -> "Recovery":
        try:
            record = json.loads(bytes(data).decode("utf-8"))
            recovery = cls(bytes.fromhex(record["secret"]), bytes.fromhex(record["coefficients"]), str(record["set_id"]))
        except (UnicodeDecodeError, ValueError, KeyError, TypeError) as error:
            raise CardError("the recovery record is damaged") from error
        if len(recovery.secret) != SHARE_BYTES or len(recovery.coeffs) != SHARE_BYTES * (THRESHOLD - 1):
            raise CardError("the recovery record is damaged")
        return recovery
