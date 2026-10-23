import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable

from ..body.api import Body
from ..seams.face import Face
from ..seams.sight import Eyes, NoEyes
from ..tools.builtin import Permissions

CONTROL_S = 0.15


@dataclass(frozen=True)
class Pointed:
    angle_deg: float
    distance_m: float
    at: float
    world: tuple[float, float] | None = None


class Pace:
    def __init__(self, monotonic: Callable[[], float] = time.monotonic):
        self.monotonic = monotonic

    def now(self) -> float:
        return self.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(max(0.0, seconds))


@dataclass
class Kit:
    body: Body
    permissions: Permissions
    guard: Callable[[], str | None]
    people_near: Callable[[], bool]
    face: Face
    pace: Pace = field(default_factory=Pace)
    eyes: Eyes = field(default_factory=NoEyes)
    present: Callable[[str], bool] = lambda person_id: False
    patience: Callable[[str], float] = lambda tier: 300.0
    battery_low: Callable[[], bool] = lambda: False
    odometer: object | None = None
    note: Callable[[str], None] = lambda text: None
    recall: Callable[..., str] = lambda thing, stranger=False: ""
    place_at: Callable[[str], tuple[float, float, float] | None] = lambda name: None
    pointed: Callable[[], Pointed | None] = lambda: None
    toy: Callable[[str], bool] = lambda label: False
    thing_at: Callable[[str], tuple[float, float] | None] = lambda label: None
    nav: object | None = None
    say: Callable[[str], None] = lambda text: None
    others_near: Callable[[str | None], bool] = lambda person_id: False
    dock_print: Callable[[tuple], None] = lambda vec: None
    talking: Callable[[], bool] = lambda: False
    battery_pct: Callable[[], float | None] = lambda: None
    dark: Callable[[], bool] = lambda: False
    rooms: Callable[[], list[str]] = lambda: []
    climate: object | None = None
    chirps: Callable[[float], list] | None = None
    chaos: Callable[[str], object] | None = None
    here: Callable[[float], list] = lambda within: []
    usual_room: Callable[[str], str | None] = lambda person_id: None
    last_present: Callable[[str], float] = lambda person_id: float("-inf")
    hushed: Callable[[], bool] = lambda: False
    name_of: Callable[[int | None], str | None] = lambda track: None
    say_loud: Callable[[str], None] = lambda text: None
    privacy: object | None = None
    kept_out: Callable[[], dict] = lambda: {}
    rules: object | None = None
    picture: Callable | None = None
    alarm: Callable[[], bool] = lambda: False
    crying: Callable[[float], float] = lambda seconds: 0.0
    sharpen: Callable[[float], None] = lambda seconds: None
    where_was: Callable[[str], tuple | None] = lambda person_id: None
    seen: Callable[[str, float], bool] = lambda person_id, within: False
    control_s: float = CONTROL_S
