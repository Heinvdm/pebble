import math

MAGNUS_B = 17.62
MAGNUS_C = 243.12
FRESH_S = 120.0
WET_LINE_C = 12.0
DRY_C = 6.0
ROOM_KEEP_S = 86400.0


def dew_point(celsius: float | None, humidity_pct: float | None) -> float | None:
    if celsius is None or humidity_pct is None or humidity_pct <= 0.0 or humidity_pct > 100.5:
        return None
    gamma = math.log(min(100.0, humidity_pct) / 100.0) + MAGNUS_B * celsius / (MAGNUS_C + celsius)
    return MAGNUS_C * gamma / (MAGNUS_B - gamma)


class Damp:
    def __init__(self, house):
        self.house = house

    def reading(self, now: float):
        telemetry = getattr(getattr(self.house.p, "body", None), "telemetry", None)
        reader = getattr(telemetry, "air_reading", None)
        if reader is None:
            return None
        air = reader(now, FRESH_S)
        if air is None or air.warming or air.temperature_c is None or air.humidity_pct is None:
            return None
        return air

    def now_dew(self, now: float) -> tuple[float, float] | None:
        air = self.reading(now)
        if air is None:
            return None
        dew = dew_point(air.temperature_c, air.humidity_pct)
        return None if dew is None else (dew, air.humidity_pct)

    def dampest_room(self, now: float) -> str:
        household = getattr(getattr(self.house.life, "commands", None), "household", None)
        climate = getattr(household, "climate", None)
        latest = getattr(climate, "latest", None)
        rooms = getattr(self.house.life.alive, "places", lambda: frozenset())() if getattr(self.house.life, "alive", None) is not None else frozenset()
        if latest is None or not rooms:
            return ""
        best = None
        for room in rooms:
            try:
                measured = latest(room)
            except Exception:
                continue
            dew = getattr(measured, "dew_c", None)
            if measured is None or dew is None or now - float(getattr(measured, "at", 0.0)) > ROOM_KEEP_S:
                continue
            if best is None or dew > best[1]:
                best = (room, dew, float(measured.at))
        if best is None:
            return ""
        return f" Of the rooms I've measured today, the {best[0]}'s air held the most moisture, with a dew point of {round(best[1])} degrees at {self.house.hhmm(best[2])}."

    def answer(self, now: float) -> str:
        found = self.now_dew(now)
        if found is None:
            return "I can't measure the air just now, so I can't tell."
        dew, humidity = found
        whole = round(dew)
        if dew <= DRY_C:
            line = f"The air near me is fairly dry: its dew point is about {whole} degrees, so a window would have to get colder than that to run wet."
        else:
            line = f"The air near me is at {round(humidity)} % humidity, with a dew point of about {whole} degrees. Tonight, any window colder than {whole} degrees would run wet."
        return line + " That's about the air, not the walls or windows themselves, which I can't measure." + self.dampest_room(now)

    def evening_line(self, now: float) -> str:
        found = self.now_dew(now)
        if found is None or found[0] < WET_LINE_C:
            return ""
        whole = round(found[0])
        return f"The air in here is holding a lot of moisture tonight: any window colder than {whole} degrees will run wet. That's measured from the air near me, not the glass."
