import math

from .kit import Kit

SPOT_RADIUS_M = 0.6
SETTLE_M = 1.0
TRIP_S = 150.0
SLACK = 4.0
SLOWEST_M_S = 0.02
DOOR_STOP_M = 0.2
NOT_PLACES = frozenset({"start", "here", "dock", "charger", "home"})


def spot_names(nav) -> list[str]:
    spots = getattr(nav, "spots", None)
    names = spots() if callable(spots) else spots
    return [name for name in names or [] if name and name not in NOT_PLACES]


def spot_at(nav, name: str) -> tuple[float, float] | None:
    spot = getattr(nav, "spot", None)
    if callable(spot):
        return spot(name)
    spots = getattr(nav, "spots", None)
    return spots.get(name) if isinstance(spots, dict) else None


def find_place(kit: Kit, name: str) -> tuple[float, float, float] | None:
    if not name:
        return None
    place = kit.place_at(name)
    if place is not None:
        return place
    if name in NOT_PLACES:
        return None
    found = spot_at(kit.nav, name)
    return None if found is None else (found[0], found[1], SPOT_RADIUS_M)


def known_places(kit: Kit, spots: bool = True) -> list[tuple[str, float, float, float]]:
    out = []
    seen = set()
    for name in kit.rooms():
        place = kit.place_at(name)
        if place is not None and name not in seen:
            seen.add(name)
            out.append((name, place[0], place[1], place[2]))
    for name in spot_names(kit.nav) if spots else []:
        if name in seen:
            continue
        spot = spot_at(kit.nav, name)
        if spot is not None:
            seen.add(name)
            out.append((name, spot[0], spot[1], SPOT_RADIUS_M))
    return out


def where(kit: Kit) -> tuple[float, float] | None:
    odometer = kit.odometer
    if odometer is None or not getattr(odometer, "usable", False):
        return None
    x, y, _ = odometer.pose()
    return x, y


def tour(places: list, start: tuple[float, float] | None) -> list:
    left = list(places)
    out = []
    x, y = start if start is not None else (0.0, 0.0)
    while left:
        pick = min(left, key=lambda item: math.hypot(item[1] - x, item[2] - y))
        out.append(pick)
        left.remove(pick)
        x, y = pick[1], pick[2]
    return out


def can_drive(kit: Kit) -> bool:
    return kit.nav is not None and getattr(kit.nav, "go_to", None) is not None


def budget(kit: Kit, x: float, y: float, top: float | None) -> float:
    here = where(kit)
    driver = getattr(kit.nav, "driver", None)
    if here is None or driver is None:
        return TRIP_S
    speed = top * driver.sprint if top is not None else driver.cruise
    return max(TRIP_S, SLACK * math.hypot(x - here[0], y - here[1]) / max(SLOWEST_M_S, speed) + 30.0)


def private_room(kit: Kit, x: float, y: float) -> str | None:
    privacy = getattr(kit, "privacy", None)
    return privacy.blocks(x, y) if privacy is not None else None


async def go(kit: Kit, x: float, y: float, radius: float, top: float | None = None, max_s: float | None = None, door: bool = False):
    from ..nav.navigator import Trip

    limit = budget(kit, x, y, top) if max_s is None else max_s
    privacy = getattr(kit, "privacy", None)
    if privacy is not None:
        privacy.leave_door()
    rules = getattr(kit, "rules", None)
    kept = rules.kept_at(x, y) if rules is not None else None
    if kept is not None:
        return Trip(False, "kept out", f"you were asked to keep out of the {kept}, so you did not go in")
    room = private_room(kit, x, y)
    if room is not None:
        spot = privacy.door_for(room) if door else None
        if spot is None:
            return Trip(False, "private", f"the {room} is private, so you did not go in")
        trip = await kit.nav.go_to(kit, spot[0], spot[1], stop_m=DOOR_STOP_M, top=top, max_s=limit, settle_m=SETTLE_M)
        if not trip.ok:
            return trip
        privacy.at_door(room)
        return Trip(True, "door", f"you stopped at the door of the {room}, which is private", trip.travelled_m)
    return await kit.nav.go_to(kit, x, y, stop_m=min(0.8, 0.3 + 0.2 * radius), top=top, max_s=limit, settle_m=SETTLE_M)
