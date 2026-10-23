WINDOW_S = 3600.0
FLIPS = 3


def _step(before, after) -> object:
    if isinstance(before, (int, float)) and isinstance(after, (int, float)) and not isinstance(before, bool) and not isinstance(after, bool):
        return (after > before) - (after < before)
    return None


def reversals(steps: list[tuple]) -> int:
    count = 0
    for (a_from, a_to), (b_from, b_to) in zip(steps, steps[1:]):
        direction_a, direction_b = _step(a_from, a_to), _step(b_from, b_to)
        if direction_a is not None and direction_b is not None:
            count += bool(direction_a and direction_b and direction_a != direction_b)
        elif b_to == a_from:
            count += 1
    return count


def held(changes: list[dict], name: str, before, after, now: float) -> str | None:
    steps = [(c.get("from"), c.get("to")) for c in changes if c.get("name") == name and now - float(c.get("at", -1e18)) <= WINDOW_S]
    flips = reversals(steps + [(before, after)])
    if flips >= FLIPS:
        return f"it has gone back and forth {flips} times in the last hour, so it stays as it is for now"
    return None
