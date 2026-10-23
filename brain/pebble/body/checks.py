EDGE_MM = (40, 150)
STOP_MM = (30, 300)
CPM = (5.0, 60.0)
TILT_DEG = (-35, 90)
TRIM_DEG = 10
REFLEX_KEYS = ("cpm", "edge", "stop", "tmin", "tmax", "trim", "rest")


def _number(settings: dict, key: str, problems: list[str]) -> float | None:
    raw = settings.get(key)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        problems.append(f"{key} could not be read ({raw!r})")
        return None
    if value != value:
        problems.append(f"{key} could not be read ({raw!r})")
        return None
    return value


def _within(problems: list[str], key: str, value: float | None, low: float, high: float) -> None:
    if value is not None and not low <= value <= high:
        problems.append(f"{key} {value:g} is outside {low:g} to {high:g}")


def unsafe_settings(settings: dict) -> list[str]:
    problems: list[str] = []
    values = {key: _number(settings, key, problems) for key in REFLEX_KEYS}
    _within(problems, "edge", values["edge"], *EDGE_MM)
    _within(problems, "stop", values["stop"], *STOP_MM)
    cpm = values["cpm"]
    if cpm is not None and cpm != 0.0:
        _within(problems, "cpm", cpm, *CPM)
    _within(problems, "trim", values["trim"], -TRIM_DEG, TRIM_DEG)
    _within(problems, "tmin", values["tmin"], *TILT_DEG)
    _within(problems, "tmax", values["tmax"], *TILT_DEG)
    tmin, tmax, rest = values["tmin"], values["tmax"], values["rest"]
    if tmin is not None and tmax is not None:
        if tmin >= tmax:
            problems.append(f"tmin {tmin:g} is not below tmax {tmax:g}")
        elif rest is not None and not tmin <= rest <= tmax:
            problems.append(f"rest {rest:g} is outside the tilt range {tmin:g} to {tmax:g}")
    return problems


def safe_setting(key: str, value) -> bool:
    if key not in REFLEX_KEYS:
        return False
    if key in ("tmin", "tmax", "rest"):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False
        return TILT_DEG[0] <= number <= TILT_DEG[1]
    sample = {"cpm": "0", "edge": "75", "stop": "60", "tmin": "-35", "tmax": "90", "trim": "0", "rest": "8"}
    sample[key] = str(value)
    return not unsafe_settings(sample)
