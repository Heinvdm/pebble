from datetime import datetime
from typing import Callable

from ..clock import from_iso

CLOCK_SLACK_S = 60.0


def _when(local: datetime) -> str:
    return local.strftime("%H:%M on %d %b %Y")


def _duration(seconds: float) -> str:
    if seconds < 120:
        return "a moment"
    if seconds < 7200:
        return f"{int(seconds // 60)} minutes"
    if seconds < 172800:
        return f"{int(seconds // 3600)} hours"
    return f"{int(seconds // 86400)} days"


def wake_note(state: dict | None, now: float, local: Callable[[float], datetime], first_boot: bool) -> str:
    if first_boot:
        return "This is your very first boot. Everything is new."
    saved_at = (state or {}).get("saved_at")
    if not saved_at:
        return "You are waking up, but there is no record of when you last saved."
    try:
        saved = from_iso(saved_at)
    except ValueError:
        return "You are waking up; your last save time is unreadable."
    when = _when(local(saved))
    if (state or {}).get("clean_shutdown"):
        note = f"You woke up after a clean shutdown at {when}."
    else:
        note = f"You restarted after power loss; last saved at {when}."
    if now + CLOCK_SLACK_S < saved:
        return note + " The clock reads earlier than that, so go by your last save time until the clock is fixed."
    return note + f" You were off for about {_duration(now - saved)}."
