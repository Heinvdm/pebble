from dataclasses import dataclass, replace

from ..seams.sight import SeenThing
from .geometry import Box, angles

SAME_OBJECT = 0.4


@dataclass(frozen=True)
class Thing:
    box: Box
    label: str
    animal: bool
    at: float
    lane: str
    depth: int = 6
    track: int | None = None
    held: bool = False
    known: str | None = None
    known_score: float = 0.0


def overlap(a: Box, b: Box) -> float:
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1, y1 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    inner = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = a.w * a.h + b.w * b.h - inner
    return inner / union if union > 0 else 0.0


def merge(fast: list[Thing], slow: list[Thing]) -> list[Thing]:
    out = list(fast)
    taken: set[int] = set()
    for item in sorted(slow, key=lambda t: t.box.score, reverse=True):
        best, best_overlap = None, SAME_OBJECT
        for i, seen in enumerate(fast):
            if i in taken:
                continue
            amount = overlap(item.box, seen.box)
            if amount >= best_overlap:
                best, best_overlap = i, amount
        if best is None:
            out.append(item)
            continue
        taken.add(best)
        seen = fast[best]
        mark = {"known": item.known, "known_score": item.known_score} if item.known else {}
        if item.depth >= seen.depth:
            out[best] = replace(seen, label=item.label, animal=item.animal or seen.animal, lane="slow", depth=item.depth, **mark)
        elif mark:
            out[best] = replace(seen, **mark)
    return out


def seen_things(things: list[Thing], width: int, height: int, fov_h_deg: float) -> tuple[SeenThing, ...]:
    out = []
    for thing in things:
        bearing, elevation = angles(thing.box.cx, thing.box.cy, width, height, fov_h_deg)
        out.append(SeenThing(
            label=thing.label,
            bearing_deg=round(bearing, 2),
            elevation_deg=round(elevation, 2),
            height_frac=round(min(1.0, max(0.0, thing.box.h)), 4),
            width_frac=round(min(1.0, max(0.0, thing.box.w)), 4),
            score=round(min(1.0, max(0.0, thing.box.score)), 3),
            at=thing.at,
            lane=thing.lane,
            animal=thing.animal,
            track=thing.track,
            held=thing.held,
            known=thing.known,
            known_score=round(float(thing.known_score), 3),
        ))
    return tuple(out)
