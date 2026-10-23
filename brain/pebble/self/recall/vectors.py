import math
import struct

try:
    import numpy
except ImportError:
    numpy = None


def normalize(vector) -> list[float]:
    values = [float(v) if math.isfinite(float(v)) else 0.0 for v in vector]
    size = math.sqrt(sum(v * v for v in values))
    return [v / size for v in values] if size > 0 else values


def pack(vector) -> bytes:
    values = normalize(vector)
    return struct.pack(f"<{len(values)}e", *values)


def unpack(blob: bytes) -> list[float]:
    count = len(blob) // 2
    return list(struct.unpack(f"<{count}e", blob[: count * 2]))


def cosines(query: list[float], rows: list[bytes]) -> list[float]:
    if not rows:
        return []
    query = normalize(query)
    if numpy is not None:
        width = len(query)
        matrix = numpy.frombuffer(b"".join(rows), dtype="<f2").reshape(len(rows), width).astype("float32")
        return [float(x) for x in matrix @ numpy.asarray(query, dtype="float32")]
    out = []
    for row in rows:
        values = unpack(row)
        out.append(sum(a * b for a, b in zip(values, query)))
    return out


def spread(values: list[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high - low <= 1e-9:
        return [0.0 for _ in values]
    return [(v - low) / (high - low) for v in values]
