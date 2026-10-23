from dataclasses import dataclass
from enum import Enum


class LifeState(str, Enum):
    WAKING = "waking"
    ACTIVE = "active"
    RESTING = "resting"
    DOCKING = "docking"
    ASLEEP = "asleep"


@dataclass(frozen=True)
class Situation:
    quiet: bool
    rest: float
    energy: float
    docked: bool
    low_battery: bool
    in_state_s: float
    strong_event: bool = False
    alarm: bool = False
    waking_s: float = 60.0
    settle_s: float = 300.0


TIRED = 0.85
RESTED = 0.3
MORNING_REST = 0.5
CHARGE_MORE = 0.3


def next_state(current: LifeState, s: Situation) -> tuple[LifeState, str]:
    if s.alarm:
        return (current, "") if current is LifeState.ACTIVE else (LifeState.ACTIVE, "something needs it awake")
    if s.low_battery and not s.docked and current is not LifeState.DOCKING:
        return LifeState.DOCKING, "the battery is low, so it is heading for the charger"
    if current is LifeState.DOCKING:
        if s.docked:
            return LifeState.RESTING, "it is on the charger"
        if not s.low_battery:
            return LifeState.ACTIVE, "the battery recovered"
        return current, ""
    if current is LifeState.ASLEEP:
        if s.strong_event:
            return LifeState.WAKING, "something woke it"
        if not s.quiet and s.rest < MORNING_REST:
            return LifeState.WAKING, "morning"
        return current, ""
    if current is LifeState.WAKING:
        if s.in_state_s >= s.waking_s:
            return (LifeState.RESTING, "it is quiet hours") if s.quiet else (LifeState.ACTIVE, "it is fully awake")
        return current, ""
    if s.quiet:
        if current is LifeState.ACTIVE:
            return LifeState.RESTING, "it is quiet hours"
        if current is LifeState.RESTING and s.in_state_s >= s.settle_s:
            return LifeState.ASLEEP, "it fell asleep"
        return current, ""
    if current is LifeState.ACTIVE and s.rest >= TIRED:
        return LifeState.RESTING, "it is tired"
    if current is LifeState.RESTING and s.rest <= RESTED and not (s.docked and s.energy < CHARGE_MORE):
        return LifeState.ACTIVE, "it feels rested"
    return current, ""
