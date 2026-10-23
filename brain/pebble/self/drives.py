from dataclasses import dataclass

PRESSING = 0.6
RECENT_S = 6 * 3600.0
KEEP = 200
TIMES = {1: "once", 2: "twice"}


@dataclass(frozen=True)
class Drive:
    name: str
    pressure: float
    why: str = ""


class Recent:
    def __init__(self):
        self.seen: list[tuple[str, float]] = []

    def add(self, kind: str, at: float) -> None:
        self.seen.append((kind, at))
        del self.seen[:-KEEP]

    def count(self, kind: str, now: float, window_s: float = RECENT_S) -> int:
        return sum(1 for seen, at in self.seen if seen == kind and now - at <= window_s)


def _times(count: int) -> str:
    return TIMES.get(count, f"{count} times")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _safety(fear: float, recent: Recent, now: float) -> Drive:
    bumps, edges, falls, alarms = recent.count("bump", now), recent.count("edge", now), recent.count("fall", now), recent.count("alarm", now)
    pressure = _clamp(max(fear / 10.0, 0.15 * bumps + 0.25 * edges + 0.35 * falls + 0.4 * alarms))
    parts = []
    if bumps:
        parts.append(f"I bumped into things {_times(bumps)}")
    if edges:
        parts.append(f"I came close to an edge {_times(edges)}")
    if falls:
        parts.append(f"I fell {_times(falls)}")
    if alarms:
        parts.append("there was an alarm")
    why = " and ".join(parts)
    if why and (fear >= 4.0 or pressure >= PRESSING):
        why += ", and I feel shaky"
    elif not why and fear >= 4.0:
        why = "I feel shaky"
    return Drive("safety", pressure, why)


def _warmth(temperature_c: float | None, heat: str) -> Drive:
    pressure = {"hot": 0.9, "warm": 0.5}.get(heat, 0.0)
    if temperature_c is not None:
        pressure = max(pressure, _clamp((temperature_c - 35.0) / 10.0))
    return Drive("warmth", pressure, "I'm getting warm" if pressure >= PRESSING else "")


def drives(needs, fear: float, temperature_c: float | None, heat: str, recent: Recent, now: float) -> tuple[Drive, ...]:
    energy = _clamp(1.0 - needs.energy)
    loud, shaken, handled, dreams = recent.count("loud", now), recent.count("shaken", now), recent.count("handled", now), recent.count("dream", now, 12 * 3600.0)
    comfort = _clamp(0.2 * loud + 0.3 * shaken - 0.1 * handled)
    comfort_why = "it has been noisy" if loud >= max(1, shaken) else ("I was shaken about" if shaken else "")
    return (
        Drive("energy", energy, "my battery is getting low" if energy >= PRESSING else ""),
        _warmth(temperature_c, heat),
        Drive("rest", _clamp(needs.rest), "I'm getting tired" if needs.rest >= PRESSING else ""),
        Drive("company", _clamp(needs.social), "nobody has talked with me for a while" if needs.social >= PRESSING else ""),
        Drive("curiosity", _clamp(needs.curiosity), "I'd like something new to look at" if needs.curiosity >= PRESSING else ""),
        _safety(fear, recent, now),
        Drive("comfort", comfort, comfort_why if comfort >= PRESSING else ""),
        Drive("inner", _clamp(0.3 * dreams), "I keep thinking about my dream" if dreams else ""),
    )


def unmet(found: tuple[Drive, ...]) -> float:
    return max((d.pressure for d in found if d.name in ("energy", "warmth", "rest", "company", "curiosity", "safety")), default=0.0)


def pressing(found: tuple[Drive, ...]) -> list[Drive]:
    return sorted((d for d in found if d.pressure >= PRESSING and d.why), key=lambda d: -d.pressure)
