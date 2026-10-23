import secrets

POLY = 0x11B
GENERATOR = 3


def _xtime(value: int) -> int:
    value <<= 1
    return value ^ POLY if value & 0x100 else value


def _tables() -> tuple[list[int], list[int]]:
    exp = [0] * 510
    log = [0] * 256
    value = 1
    for power in range(255):
        exp[power] = value
        log[value] = power
        value ^= _xtime(value)
    for power in range(255, 510):
        exp[power] = exp[power - 255]
    return exp, log


EXP, LOG = _tables()


def mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return EXP[LOG[a] + LOG[b]]


def div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("division by zero in GF(256)")
    if a == 0:
        return 0
    return EXP[(LOG[a] - LOG[b]) % 255]


def coefficients(length: int, threshold: int = 2) -> bytes:
    if threshold < 2:
        raise ValueError("a threshold below 2 is not a secret")
    return secrets.token_bytes(length * (threshold - 1))


def share(secret: bytes, coeffs: bytes, x: int) -> bytes:
    if not 1 <= x <= 255:
        raise ValueError("a share number is 1 to 255")
    length = len(secret)
    if length == 0 or len(coeffs) % length:
        raise ValueError("the coefficients do not fit the secret")
    degree = len(coeffs) // length
    out = bytearray(length)
    for index in range(length):
        value = 0
        for power in range(degree, 0, -1):
            value = mul(value, x) ^ coeffs[(power - 1) * length + index]
        out[index] = mul(value, x) ^ secret[index]
    return bytes(out)


def combine(points: list[tuple[int, bytes]]) -> bytes:
    if len(points) < 2:
        raise ValueError("at least two shares are needed")
    xs = [x for x, _ in points]
    if len(set(xs)) != len(xs) or any(not 1 <= x <= 255 for x in xs):
        raise ValueError("share numbers must differ and be 1 to 255")
    length = len(points[0][1])
    if any(len(y) != length for _, y in points):
        raise ValueError("shares differ in length")
    weights = []
    for j, xj in enumerate(xs):
        weight = 1
        for m, xm in enumerate(xs):
            if m != j:
                weight = mul(weight, div(xm, xm ^ xj))
        weights.append(weight)
    out = bytearray(length)
    for index in range(length):
        value = 0
        for weight, (_, y) in zip(weights, points):
            value ^= mul(weight, y[index])
        out[index] = value
    return bytes(out)


def slope(secret: bytes, x: int, share_bytes: bytes) -> bytes:
    if not 1 <= x <= 255:
        raise ValueError("a share number is 1 to 255")
    if len(secret) != len(share_bytes):
        raise ValueError("the share does not fit the secret")
    return bytes(div(y ^ s, x) for y, s in zip(share_bytes, secret))
