import html
import math
import struct
import zlib

from .grid import FREE, OCCUPIED, SHIFT, CHUNK, MASK

COLOURS = {
    "free": "#f4f1ea",
    "wall": "#3b3f46",
    "touched": "#c2410c",
    "cliff": "#dc2626",
    "rise": "#ca8a04",
    "hazard": "#7c3aed",
    "path": "#2563eb",
    "trail": "#16a34a",
    "pebble": "#1d4ed8",
    "lead": "#15803d",
    "place": "#0f766e",
    "ground": "#ffffff",
}
KIND_MARK = {"room": "R", "doorway": "D", "corridor": "C", "spot": "S", "start": "S", "dock": "H"}


def _cells(chart):
    grid = chart.grid
    free, walls = [], []
    for (cx, cy), chunk in list(grid.chunks.items()):
        bx, by = cx << SHIFT, cy << SHIFT
        for index, value in enumerate(chunk):
            if value >= OCCUPIED:
                walls.append((bx + (index & MASK), by + (index >> SHIFT)))
            elif value <= FREE:
                free.append((bx + (index & MASK), by + (index >> SHIFT)))
    return free, walls


def _box(chart, extra=()):
    grid = chart.grid
    points = []
    bounds = grid.bounds()
    if bounds is not None:
        free, walls = _cells(chart)
        known = free + walls + list(grid.cliffs) + list(list(grid.touched))
        if known:
            xs = [c[0] for c in known]
            ys = [c[1] for c in known]
            points += [(min(xs) * grid.res, min(ys) * grid.res), ((max(xs) + 1) * grid.res, (max(ys) + 1) * grid.res)]
    points += [(p.x, p.y) for p in list(chart.places)]
    points += list(chart.path[-1:]) + list(extra)
    if not points:
        return -1.0, -1.0, 1.0, 1.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs) - 0.5, min(ys) - 0.5, max(xs) + 0.5, max(ys) + 0.5


def _runs(cells):
    rows: dict[int, list[int]] = {}
    for ix, iy in cells:
        rows.setdefault(iy, []).append(ix)
    out = []
    for iy, xs in rows.items():
        xs.sort()
        start = prev = xs[0]
        for ix in xs[1:]:
            if ix == prev + 1:
                prev = ix
                continue
            out.append((start, prev, iy))
            start = prev = ix
        out.append((start, prev, iy))
    return out


def svg(chart, pose=None, trail=(), title: str = "", width: int = 900, height: int = 412) -> str:
    grid = chart.grid
    res = grid.res
    x0, y0, x1, y1 = _box(chart, [(p[0], p[1]) for p in trail[-1:]] + ([(pose[0], pose[1])] if pose else []))
    span_x, span_y = max(1.0, x1 - x0), max(1.0, y1 - y0)
    scale = min((width - 20) / span_x, (height - 40) / span_y)

    def sx(x):
        return 10 + (x - x0) * scale

    def sy(y):
        return height - 10 - (y - y0) * scale

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Pebble\'s map">', f'<rect width="{width}" height="{height}" fill="{COLOURS["ground"]}"/>']
    free, walls = _cells(chart)
    cell = res * scale
    for colour, cells in (("free", free), ("wall", walls)):
        for a, b, iy in _runs(cells):
            parts.append(f'<rect x="{sx(a * res):.1f}" y="{sy((iy + 1) * res):.1f}" width="{(b - a + 1) * cell + 0.3:.1f}" height="{cell + 0.3:.1f}" fill="{COLOURS[colour]}"/>')
    for colour, cells in (("touched", list(grid.touched)), ("cliff", list(grid.cliffs)), ("rise", list(grid.rises)), ("hazard", list(grid.soft))):
        for ix, iy in cells:
            parts.append(f'<rect x="{sx(ix * res):.1f}" y="{sy((iy + 1) * res):.1f}" width="{cell + 0.3:.1f}" height="{cell + 0.3:.1f}" fill="{COLOURS[colour]}"/>')
    path = list(chart.path)
    if len(path) > 1:
        points = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in path)
        parts.append(f'<polyline points="{points}" fill="none" stroke="{COLOURS["path"]}" stroke-width="2" stroke-linejoin="round"/>')
    if len(trail) > 1:
        points = " ".join(f"{sx(p[0]):.1f},{sy(p[1]):.1f}" for p in trail)
        parts.append(f'<polyline points="{points}" fill="none" stroke="{COLOURS["trail"]}" stroke-width="2" stroke-dasharray="5 4" stroke-linejoin="round"/>')
    for place in list(chart.places):
        mark = KIND_MARK.get(place.kind, "")
        label = html.escape(place.name or place.kind)
        parts.append(f'<circle cx="{sx(place.x):.1f}" cy="{sy(place.y):.1f}" r="{max(4.0, place.radius * scale * (0.3 if place.kind == "room" else 0.6)):.1f}" fill="none" stroke="{COLOURS["place"]}" stroke-width="1.5"/>')
        parts.append(f'<text x="{sx(place.x) + 6:.1f}" y="{sy(place.y) - 6:.1f}" font-family="sans-serif" font-size="12" fill="{COLOURS["place"]}">{mark} {label}</text>')
    if pose is not None:
        px, py, heading = pose
        tip = (sx(px + 0.25 * math.cos(heading)), sy(py + 0.25 * math.sin(heading)))
        left = (sx(px + 0.12 * math.cos(heading + 2.4)), sy(py + 0.12 * math.sin(heading + 2.4)))
        right = (sx(px + 0.12 * math.cos(heading - 2.4)), sy(py + 0.12 * math.sin(heading - 2.4)))
        parts.append(f'<polygon points="{tip[0]:.1f},{tip[1]:.1f} {left[0]:.1f},{left[1]:.1f} {right[0]:.1f},{right[1]:.1f}" fill="{COLOURS["pebble"]}"/>')
    if trail:
        lx, ly = trail[-1][0], trail[-1][1]
        parts.append(f'<circle cx="{sx(lx):.1f}" cy="{sy(ly):.1f}" r="6" fill="{COLOURS["lead"]}"/>')
    metres = 1.0 if scale * 1.0 > 30 else 5.0
    parts.append(f'<line x1="10" y1="{height - 6}" x2="{10 + metres * scale:.1f}" y2="{height - 6}" stroke="#111" stroke-width="2"/>')
    parts.append(f'<text x="12" y="{height - 10}" font-family="sans-serif" font-size="11" fill="#111">{metres:g} m</text>')
    if title:
        parts.append(f'<text x="12" y="18" font-family="sans-serif" font-size="14" fill="#111">{html.escape(title)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def page(chart, pose=None, trail=(), title: str = "Pebble's map", refresh_s: int = 5) -> str:
    legend = " ".join(f'<span><i style="background:{COLOURS[k]}"></i>{html.escape(v)}</span>' for k, v in (("free", "clear floor"), ("wall", "walls and things"), ("touched", "bumped (maybe glass)"), ("cliff", "drops"), ("rise", "small bumps"), ("path", "where Pebble went"), ("trail", "where the person walked")))
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<meta http-equiv=\"refresh\" content=\"{int(refresh_s)}\">"
        f"<title>{html.escape(title)}</title>"
        "<style>html,body{margin:0;height:100%;background:#fff;color:#111;font:13px sans-serif}"
        "main{display:flex;flex-direction:column;height:100%}figure{flex:1;margin:0;min-height:0}"
        "footer{padding:4px 8px;display:flex;flex-wrap:wrap;gap:10px}footer i{display:inline-block;width:10px;height:10px;margin-right:4px;vertical-align:middle}"
        "</style></head><body><main><figure>"
        + svg(chart, pose, trail, title)
        + "</figure><footer>"
        + legend
        + "</footer></main></body></html>"
    )


def png(chart, path, pose=None, trail=(), others=(), scale: int = 4) -> None:
    grid = chart.grid
    res = grid.res
    x0, y0, x1, y1 = _box(chart, [(p[0], p[1]) for p in trail] + ([(pose[0], pose[1])] if pose else []))
    w = max(8, int((x1 - x0) / res * scale))
    h = max(8, int((y1 - y0) / res * scale))
    pixels = bytearray([255, 255, 255]) * (w * h)

    def put(px, py, colour):
        if 0 <= px < w and 0 <= py < h:
            i = (py * w + px) * 3
            pixels[i:i + 3] = colour

    def fill(ix, iy, colour):
        bx = int((ix * res - x0) / res * scale)
        by = h - 1 - int((iy * res - y0) / res * scale)
        for dx in range(scale):
            for dy in range(scale):
                put(bx + dx, by - dy, colour)

    def rgb(name):
        value = COLOURS[name].lstrip("#")
        return bytes(int(value[i:i + 2], 16) for i in (0, 2, 4))

    free, walls = _cells(chart)
    for cells, name in ((free, "free"), (walls, "wall"), (grid.touched, "touched"), (grid.cliffs, "cliff"), (grid.rises, "rise")):
        colour = rgb(name)
        for ix, iy in cells:
            fill(ix, iy, colour)

    def line(points, colour, thick=1):
        for (ax, ay), (bx, by) in zip(points, points[1:]):
            steps = max(1, int(math.hypot(bx - ax, by - ay) / res * scale))
            for k in range(steps + 1):
                t = k / steps
                px = int((ax + (bx - ax) * t - x0) / res * scale)
                py = h - 1 - int((ay + (by - ay) * t - y0) / res * scale)
                for dx in range(-thick, thick + 1):
                    for dy in range(-thick, thick + 1):
                        put(px + dx, py + dy, colour)

    line(chart.path, rgb("path"))
    line([(p[0], p[1]) for p in trail], rgb("trail"))
    for path_points in others:
        line([(p[0], p[1]) for p in path_points], bytes((150, 150, 150)), 0)
    for place in chart.places:
        px = int((place.x - x0) / res * scale)
        py = h - 1 - int((place.y - y0) / res * scale)
        for a in range(0, 360, 10):
            put(px + int(6 * math.cos(math.radians(a))), py + int(6 * math.sin(math.radians(a))), rgb("place"))
    raw = b"".join(b"\x00" + bytes(pixels[y * w * 3:(y + 1) * w * 3]) for y in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    blob = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as handle:
        handle.write(blob)
