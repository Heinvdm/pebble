from dataclasses import dataclass, field


@dataclass(frozen=True)
class Snapshot:
    battery_pct: float | None = None
    battery_trend: str | None = None
    pack_mv: int | None = None
    docked: bool | None = None
    tilt_deg: float | None = None
    light_lux: float | None = None
    temperature_c: float | None = None
    last_motion_s: float | None = None
    needs: dict = field(default_factory=dict)
    mood: str = "okay, steady"
    fear: float = 0.0
    fear_label: str = "calm"
    task: str | None = None
    age_days: int = 0
    stage: str = "newborn"
    today: tuple[str, ...] = ()
    soon: tuple[tuple[str, int], ...] = ()
    state: str = "active"
    link_up: bool = True


def _light(lux: float | None) -> str:
    if lux is None:
        return "light n/a"
    if lux < 10:
        return "light dark"
    if lux < 50:
        return "light dim"
    if lux < 300:
        return "light indoor"
    if lux < 1000:
        return "light bright"
    return "light sunny"


def _ago(seconds: float | None) -> str:
    if seconds is None:
        return "no motion yet"
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"moved {int(seconds)} s ago"
    if seconds < 3600:
        return f"moved {int(seconds // 60)} min ago"
    if seconds < 172800:
        return f"moved {int(seconds // 3600)} h ago"
    return f"moved {int(seconds // 86400)} days ago"


def _battery(s: Snapshot) -> str:
    if s.battery_pct is None:
        return "battery n/a"
    trend = f" {s.battery_trend}" if s.battery_trend else ""
    return f"battery {round(s.battery_pct)}%{trend}"


def format_status(s: Snapshot) -> str:
    body = [
        _battery(s),
        "pack n/a" if not s.pack_mv else f"pack {s.pack_mv / 1000:.2f}V",
        "dock ?" if s.docked is None else ("docked" if s.docked else "off dock"),
        "tilt n/a" if s.tilt_deg is None else f"tilt {round(s.tilt_deg)}deg",
        _light(s.light_lux),
        "phone n/a" if s.temperature_c is None else f"phone {round(s.temperature_c)}C",
        _ago(s.last_motion_s),
    ]
    if not s.link_up:
        body.append("body link down")
    needs = " ".join(f"{name} {value}" for name, value in s.needs.items()) or "n/a"
    parts = [
        ", ".join(body),
        f"needs: {needs}",
        f"mood: {s.mood}",
        f"fear {round(s.fear)}/10 {s.fear_label}",
        f"task: {s.task or 'none'}",
        f"age: {s.age_days} days ({s.stage})",
        f"state: {s.state}",
    ]
    if s.today:
        parts.append("today: " + "; ".join(s.today))
    if s.soon:
        parts.append("soon: " + "; ".join(f"{title} in {days} day{'s' if days != 1 else ''}" for title, days in s.soon))
    return " | ".join(parts)
