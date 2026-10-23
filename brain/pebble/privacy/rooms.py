import math

ALWAYS = frozenset({"bathroom"})
WHEN_USED = frozenset({"bedroom"})
OCCUPIED_S = 1800.0
SHUT_S = 1800.0
DOOR_M = 0.25
DOORWAY_REACH_M = 1.0
STEP_M = 0.1


class PrivateRooms:
    def __init__(self, rooms=None, monotonic=lambda: 0.0, doorways=lambda: []):
        self.rooms = rooms
        self.monotonic = monotonic
        self.doorways = doorways
        self.seen: dict = {}
        self.shut: dict = {}

    def _all(self) -> dict:
        found = getattr(self.rooms, "rooms", None)
        return dict(found) if isinstance(found, dict) else {}

    def place(self, name: str):
        return self._all().get(name)

    def saw(self, who: str, room: str | None, mono: float | None = None) -> None:
        mono = self.monotonic() if mono is None else mono
        if room is None:
            self.seen.pop(who, None)
        else:
            self.seen[who] = (room, mono)

    def occupants(self, room: str, mono: float | None = None) -> list[str]:
        mono = self.monotonic() if mono is None else mono
        return [who for who, (where, at) in self.seen.items() if where == room and mono - at <= OCCUPIED_S]

    def occupied(self, room: str, mono: float | None = None) -> bool:
        return bool(self.occupants(room, mono))

    def door_shut(self, room: str, mono: float | None = None) -> bool:
        mono = self.monotonic() if mono is None else mono
        at = self.shut.get(room)
        return at is not None and mono - at <= SHUT_S

    def mark_shut(self, room: str, shut: bool = True) -> None:
        if shut:
            self.shut[room] = self.monotonic()
        else:
            self.shut.pop(room, None)

    def private(self, room: str | None, mono: float | None = None) -> bool:
        if not room:
            return False
        if room in ALWAYS:
            return True
        return room in WHEN_USED and (self.occupied(room, mono) or self.door_shut(room, mono))

    def kind(self, room: str | None) -> bool:
        return bool(room) and (room in ALWAYS or room in WHEN_USED)

    def room_at(self, x: float, y: float) -> str | None:
        best = None
        for name, room in self._all().items():
            gap = math.hypot(room.x - x, room.y - y)
            if gap <= room.radius and (best is None or gap < best[0]):
                best = (gap, name)
        return best[1] if best else None

    def private_at(self, x: float, y: float, mono: float | None = None) -> str | None:
        for name, room in self._all().items():
            if self.private(name, mono) and math.hypot(room.x - x, room.y - y) <= room.radius:
                return name
        return None

    def door(self, room: str, x: float, y: float) -> tuple[float, float] | None:
        found = self.place(room)
        if found is None:
            return None
        outside = found.radius + DOOR_M
        best = None
        for dx, dy in self.doorways():
            gap = math.hypot(dx - found.x, dy - found.y)
            if gap <= found.radius + DOORWAY_REACH_M:
                away = math.hypot(dx - x, dy - y)
                if best is None or away < best[0]:
                    best = (away, dx, dy)
        if best is not None:
            gx, gy = best[1] - found.x, best[2] - found.y
            gap = math.hypot(gx, gy) or 1.0
            reach = max(gap, outside)
            return found.x + gx / gap * reach, found.y + gy / gap * reach
        gx, gy = x - found.x, y - found.y
        gap = math.hypot(gx, gy)
        if gap < 1e-6:
            return found.x + outside, found.y
        return found.x + gx / gap * outside, found.y + gy / gap * outside

    def crossing(self, x0: float, y0: float, x1: float, y1: float, allowed=(), mono: float | None = None) -> str | None:
        length = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(length / STEP_M))
        for name, room in self._all().items():
            if name in allowed or not self.private(name, mono):
                continue
            if math.hypot(room.x - x0, room.y - y0) <= room.radius:
                continue
            for i in range(1, steps + 1):
                t = i / steps
                if math.hypot(room.x - (x0 + (x1 - x0) * t), room.y - (y0 + (y1 - y0) * t)) <= room.radius:
                    return name
        return None
