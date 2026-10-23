import re
from functools import lru_cache

LEVELS = "LMQH"
FORMAT_LEVEL = {"L": 1, "M": 0, "Q": 3, "H": 2}
ECC_PER_BLOCK = {
    "L": (7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    "M": (10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28),
    "Q": (13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    "H": (17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
}
BLOCKS = {
    "L": (1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25),
    "M": (1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49),
    "Q": (1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68),
    "H": (1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81),
}
MASKS = (
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: r * c % 2 + r * c % 3 == 0,
    lambda r, c: (r * c % 2 + r * c % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + r * c % 3) % 2 == 0,
)
PAD = (0xEC, 0x11)
WIFI_SPECIAL = '\\;,:"'
RUN = re.compile(r"0{5,}|1{5,}")
LIGHT_BEFORE = "00001011101"
LIGHT_AFTER = "10111010000"
LIGHT_BOTH = "000010111010000"


class TooLong(ValueError):
    pass


def _tables() -> tuple[list[int], list[int]]:
    exp = [0] * 512
    log = [0] * 256
    value = 1
    for i in range(255):
        exp[i] = value
        log[value] = i
        value <<= 1
        if value & 0x100:
            value ^= 0x11D
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    return exp, log


EXP, LOG = _tables()


def _mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return EXP[LOG[a] + LOG[b]]


def _level(ecc: str) -> str:
    level = str(ecc).strip().upper()
    if len(level) != 1 or level not in LEVELS:
        raise ValueError(f"unknown error correction level: {ecc!r}")
    return level


def _raw_modules(version: int) -> int:
    modules = (16 * version + 128) * version + 64
    if version >= 2:
        count = version // 7 + 2
        modules -= (25 * count - 10) * count - 55
        if version >= 7:
            modules -= 36
    return modules


def _data_codewords(version: int, level: str) -> int:
    index = version - 1
    return _raw_modules(version) // 8 - ECC_PER_BLOCK[level][index] * BLOCKS[level][index]


def _count_bits(version: int) -> int:
    return 8 if version < 10 else 16


def _capacity(version: int, level: str) -> int:
    return (_data_codewords(version, level) * 8 - 4 - _count_bits(version)) // 8


def capacity(ecc: str = "M", version: int = 40) -> int:
    level = _level(ecc)
    if isinstance(version, bool) or not isinstance(version, int) or not 1 <= version <= 40:
        raise ValueError(f"version must be 1 to 40, not {version!r}")
    return _capacity(version, level)


def _fit(length: int, level: str) -> int:
    for version in range(1, 41):
        if length <= _capacity(version, level):
            return version
    raise TooLong(f"{length} bytes is more than one code holds at level {level} ({_capacity(40, level)} bytes)")


@lru_cache(maxsize=None)
def _divisor(degree: int) -> tuple[int, ...]:
    poly = [1]
    for i in range(degree):
        poly = [a ^ _mul(b, EXP[i]) for a, b in zip(poly + [0], [0] + poly)]
    rest = poly[1:]
    return tuple(int.from_bytes(bytes(_mul(factor, g) for g in rest), "big") for factor in range(256))


def _error_words(data: bytes, degree: int) -> bytes:
    table = _divisor(degree)
    shift = 8 * (degree - 1)
    full = (1 << (8 * degree)) - 1
    rest = 0
    for byte in data:
        rest = ((rest << 8) & full) ^ table[(rest >> shift) ^ byte]
    return rest.to_bytes(degree, "big")


def _payload(data: bytes, version: int, level: str) -> bytes:
    total = _data_codewords(version, level)
    count = _count_bits(version)
    length = 4 + count + 8 * len(data)
    value = ((0b0100 << count | len(data)) << (8 * len(data))) | int.from_bytes(data, "big")
    end = min(4, total * 8 - length)
    value <<= end
    length += end
    tail = -length % 8
    value <<= tail
    length += tail
    head = value.to_bytes(length // 8, "big")
    return head + bytes(PAD[i % 2] for i in range(total - len(head)))


def _codewords(data: bytes, version: int, level: str) -> bytes:
    index = version - 1
    degree = ECC_PER_BLOCK[level][index]
    blocks = BLOCKS[level][index]
    raw = _raw_modules(version) // 8
    short = blocks - raw % blocks
    size = raw // blocks - degree
    parts, checks, at = [], [], 0
    for i in range(blocks):
        take = size if i < short else size + 1
        part = data[at:at + take]
        at += take
        parts.append(part)
        checks.append(_error_words(part, degree))
    out = bytearray()
    for i in range(size + 1):
        for part in parts:
            if i < len(part):
                out.append(part[i])
    for i in range(degree):
        for check in checks:
            out.append(check[i])
    return bytes(out)


def _alignment(version: int) -> list[int]:
    if version == 1:
        return []
    count = version // 7 + 2
    step = (version * 8 + count * 3 + 5) // (count * 4 - 4) * 2
    size = 4 * version + 17
    return [6] + [size - 7 - i * step for i in range(count - 1)][::-1]


def _format_cells(size: int) -> list[tuple[int, int]]:
    first = [(i, 8) for i in range(6)] + [(7, 8), (8, 8), (8, 7)] + [(8, 14 - i) for i in range(9, 15)]
    second = [(8, size - 1 - i) for i in range(8)] + [(size - 15 + i, 8) for i in range(8, 15)]
    return first + second


def _format_bits(level: str, mask: int) -> int:
    data = FORMAT_LEVEL[level] << 3 | mask
    rest = data
    for _ in range(10):
        rest = (rest << 1) ^ ((rest >> 9) * 0x537)
    return (data << 10 | rest) ^ 0x5412


def _version_bits(version: int) -> int:
    rest = version
    for _ in range(12):
        rest = (rest << 1) ^ ((rest >> 11) * 0x1F25)
    return version << 12 | rest


@lru_cache(maxsize=8)
def _layout(version: int):
    size = 4 * version + 17
    dark = [0] * size
    fixed = [0] * size
    column = [1 << (size - 1 - c) for c in range(size)]

    def put(r: int, c: int, on) -> None:
        bit = column[c]
        fixed[r] |= bit
        if on:
            dark[r] |= bit
        else:
            dark[r] &= ~bit

    for i in range(size):
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    for top, left in ((0, 0), (0, size - 7), (size - 7, 0)):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = top + dr, left + dc
                if 0 <= r < size and 0 <= c < size:
                    put(r, c, max(abs(dr - 3), abs(dc - 3)) not in (2, 4))
    spots = _alignment(version)
    last = len(spots) - 1
    for i, r in enumerate(spots):
        for j, c in enumerate(spots):
            if (i, j) in ((0, 0), (0, last), (last, 0)):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    put(r + dr, c + dc, max(abs(dr), abs(dc)) != 1)
    for r, c in _format_cells(size):
        put(r, c, False)
    put(size - 8, 8, True)
    if version >= 7:
        bits = _version_bits(version)
        for i in range(18):
            on = bits >> i & 1
            a, b = size - 11 + i % 3, i // 3
            put(b, a, on)
            put(a, b, on)
    where, which = [], []
    for right in range(size - 1, 0, -2):
        if right <= 6:
            right -= 1
        up = ((right + 1) & 2) == 0
        for step in range(size):
            r = size - 1 - step if up else step
            for c in (right, right - 1):
                if not fixed[r] & column[c]:
                    where.append(r)
                    which.append(column[c])
    return size, tuple(dark), tuple(fixed), tuple(where), tuple(which)


@lru_cache(maxsize=8)
def _masks(version: int) -> tuple[tuple[int, ...], ...]:
    size, _, fixed, _, _ = _layout(version)
    repeat = size // 6 + 1
    masks = []
    for test in MASKS:
        rows = []
        for r in range(size):
            pattern = "".join("1" if test(r, c) else "0" for c in range(6))
            rows.append(int((pattern * repeat)[:size], 2) & ~fixed[r])
        masks.append(tuple(rows))
    return tuple(masks)


def _place(version: int, codewords: bytes) -> list[int]:
    _, dark, _, where, which = _layout(version)
    rows = list(dark)
    bits = format(int.from_bytes(codewords, "big"), f"0{len(codewords) * 8}b")
    for r, bit, value in zip(where, which, bits):
        if value == "1":
            rows[r] |= bit
    return rows


def _with_format(rows: list[int], size: int, level: str, mask: int) -> list[int]:
    value = _format_bits(level, mask)
    for i, (r, c) in enumerate(_format_cells(size)):
        if value >> (i % 15) & 1:
            rows[r] |= 1 << (size - 1 - c)
    return rows


def _penalty(rows: list[int], size: int) -> int:
    lines = [format(row, f"0{size}b") for row in rows]
    lines += ["".join(column) for column in zip(*lines)]
    runs = RUN.findall("|".join(lines))
    score = sum(map(len, runs)) - 2 * len(runs)
    padded = "0000" + "0000|0000".join(lines) + "0000"
    finders = padded.count(LIGHT_BEFORE) + padded.count(LIGHT_AFTER)
    at = padded.find(LIGHT_BOTH)
    while at >= 0:
        finders -= 1
        at = padded.find(LIGHT_BOTH, at + 11)
    score += 40 * finders
    edge = (1 << (size - 1)) - 1
    for upper, lower in zip(rows, rows[1:]):
        changes = (upper ^ (upper >> 1)) | (upper ^ lower) | (lower ^ (lower >> 1))
        score += 3 * (size - 1 - (changes & edge).bit_count())
    dark = sum(row.bit_count() for row in rows)
    total = size * size
    return score + 10 * (abs(dark * 20 - total * 10) // total)


def encode(text: str, ecc: str = "M") -> list[str]:
    level = _level(ecc)
    data = text.encode("utf-8")
    version = _fit(len(data), level)
    base = _place(version, _codewords(_payload(data, version, level), version, level))
    size = len(base)
    best, best_score = base, None
    for mask, pattern in enumerate(_masks(version)):
        rows = _with_format([row ^ flip for row, flip in zip(base, pattern)], size, level, mask)
        score = _penalty(rows, size)
        if best_score is None or score < best_score:
            best, best_score = rows, score
    return [format(row, f"0{size}b") for row in best]


def _escape(value: str) -> str:
    return "".join("\\" + ch if ch in WIFI_SPECIAL else ch for ch in value)


def wifi(ssid: str, password: str, security: str = "WPA", hidden: bool = False) -> str:
    kind = str(security or "nopass").strip()
    kind = "nopass" if kind.lower() == "nopass" else kind.upper()
    fields = [f"T:{_escape(kind)}", f"S:{_escape(ssid or '')}"]
    if kind != "nopass":
        fields.append(f"P:{_escape(password or '')}")
    if hidden:
        fields.append("H:true")
    return "WIFI:" + ";".join(fields) + ";;"


def _size(text: str) -> int:
    return len(text.encode("utf-8"))


def _cut(line: str, room: int) -> list[str]:
    chunks = []
    while _size(line) > room:
        end = len(line.encode("utf-8")[:room].decode("utf-8", "ignore"))
        space = line.rfind(" ", 0, end + 1)
        if space > end // 2:
            chunks.append(line[:space])
            line = line[space + 1:]
        else:
            chunks.append(line[:end])
            line = line[end:]
    chunks.append(line)
    return chunks


def _split(text: str, room: int) -> list[str]:
    pieces, lines, used = [], [], 0
    for line in text.split("\n"):
        need = _size(line)
        if lines and used + 1 + need <= room:
            lines.append(line)
            used += 1 + need
            continue
        if lines:
            pieces.append("\n".join(lines))
        chunks = _cut(line, room)
        pieces.extend(chunks[:-1])
        lines, used = [chunks[-1]], _size(chunks[-1])
    pieces.append("\n".join(lines))
    return pieces


def parts(text: str, limit: int = 600) -> list[str]:
    if _size(text) <= limit:
        return [text]
    count = 2
    while True:
        room = limit - _size(f"({count}/{count}) ")
        if room < 4:
            raise ValueError(f"{limit} bytes is too small to split this text into parts")
        pieces = _split(text, room)
        if len(str(len(pieces))) <= len(str(count)):
            return [f"({i}/{len(pieces)}) {piece}" for i, piece in enumerate(pieces, 1)]
        count = len(pieces)
