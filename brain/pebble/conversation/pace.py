from dataclasses import dataclass


@dataclass(frozen=True)
class Pace:
    rung: str
    quiet_s: float
    turn_gap_s: float
    turns: bool
    reply_tokens: int
    answer: str
    small_first: bool


COOL = Pace("cool", 30.0, 0.0, True, 90, "", False)
WARM = Pace("warm", 60.0, 60.0, True, 70, "in one or two short sentences", False)
HOT = Pace("hot", 60.0, 60.0, False, 50, "in one short sentence", True)
LADDER = {pace.rung: pace for pace in (COOL, WARM, HOT)}


def rung_of(level: str, slow: bool = False) -> str:
    if level == "hot":
        return "hot"
    return "warm" if level == "warm" or slow else "cool"


def pace_for(level: str, slow: bool = False) -> Pace:
    return LADDER[rung_of(level, slow)]


def pace_of(heat) -> Pace:
    if heat is None:
        return COOL
    try:
        reading = heat.now()
    except Exception:
        return COOL
    return pace_for(str(getattr(reading, "level", "cool") or "cool"), bool(getattr(reading, "slow", False)))
