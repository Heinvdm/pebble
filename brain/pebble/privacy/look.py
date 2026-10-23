import math

from ..activities.base import Activity, Ending
from ..activities.kinds import moved
from ..activities.kit import Kit
from ..activities.motion import Wheels, turn_by, wrap_deg

AWAY_DEG = 150.0
DOWN_DEG = 20.0
TURN_POWER = 0.3
SHUT_MM = 300
ASK = "Can I come in?"
SHUT = "The door's shut. I'm just outside."
STAY = "Okay, I'll stay out here."
NOBODY = "Nobody answered, so I'll wait out here."


def away_from(angle: float | None) -> float:
    if angle is None:
        return AWAY_DEG
    return angle - 180.0 if angle >= 0 else angle + 180.0


class LookAway(Activity):
    kind = "look_away"
    quiet = True

    def __init__(self, request, asker, target=None, battery: bool = False, angle_deg: float | None = None):
        super().__init__(request, asker, target, battery)
        self.angle_deg = angle_deg

    def describe(self) -> str:
        return "looking away to give someone privacy"

    def adjust(self, request):
        return "", None

    async def run(self, kit: Kit) -> Ending:
        wheels = Wheels(kit).open()
        try:
            if wheels.why_not() is None and not kit.body.telemetry.docked:
                _, problem = await turn_by(kit, wheels, away_from(self.angle_deg), power=TURN_POWER, timeout_s=12.0)
                moved(kit)
                if not problem or problem == "the turn took too long":
                    return Ending("done", "you turned away to give someone privacy")
            profile = kit.body.profile
            await kit.body.tilt(max(profile.tilt_min, profile.tilt_rest - DOWN_DEG))
            privacy = getattr(kit, "privacy", None)
            if privacy is not None:
                privacy.head_down = True
            moved(kit)
            return Ending("done", "you looked down to give someone privacy")
        finally:
            await wheels.halt()
            wheels.close()


def front_mm(kit: Kit) -> int | None:
    status = kit.body.telemetry.status
    return status.front_mm if status else None


async def face_room(kit: Kit, wheels: Wheels, room: str) -> None:
    place = kit.place_at(room)
    odometer = kit.odometer
    if place is None or odometer is None or not getattr(odometer, "usable", False) or wheels.why_not() is not None:
        return
    x, y, heading = odometer.pose()
    aim = wrap_deg(math.degrees(math.atan2(place[1] - y, place[0] - x)) - heading)
    if abs(aim) > 10.0:
        await turn_by(kit, wheels, aim, power=TURN_POWER, timeout_s=8.0)
        moved(kit)


async def at_door(kit: Kit, wheels: Wheels, room: str, asker, line: str = ASK, loud: bool = False) -> str:
    privacy = kit.privacy
    await face_room(kit, wheels, room)
    front = front_mm(kit)
    if front is not None and 0 <= front < SHUT_MM:
        privacy.rooms.mark_shut(room)
        privacy._say(SHUT, loud)
        return "shut"
    privacy.rooms.mark_shut(room, False)
    answer = await privacy.ask_door(room, line, loud)
    if answer is True:
        privacy.permit(room)
        return "in"
    if answer is False:
        privacy._say(STAY, loud)
        return "out"
    if not loud and privacy.may_enter_unanswered(room, asker):
        privacy.permit(room)
        return "in"
    if not loud:
        privacy._say(NOBODY)
    return "silent"


async def to_door(kit: Kit, room: str, top: float | None = None, max_s: float = 150.0):
    privacy = kit.privacy
    spot = privacy.door_for(room)
    going = getattr(kit.nav, "go_to", None)
    if spot is None or going is None:
        return None
    return await going(kit, spot[0], spot[1], stop_m=0.2, top=top, max_s=max_s, settle_m=0.5)
