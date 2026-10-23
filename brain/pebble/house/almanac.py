import math
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Callable

SUNRISE_ZENITH = 90.833
CIVIL_ZENITH = 96.0
UNIX_JD = 2440587.5
J2000 = 2451545.0
DAY = 86400.0
HOUR = 3600.0
SYNODIC_MONTH = 29.530588853
NEW_MOON_JD = 2451550.1
PHASES = (
    "new moon",
    "waxing crescent",
    "first quarter",
    "waxing gibbous",
    "full moon",
    "waning gibbous",
    "last quarter",
    "waning crescent",
)
TOWNS = {
    "whangarei": (-35.73, 174.32),
    "kerikeri": (-35.22, 173.95),
    "auckland": (-36.85, 174.77),
    "hamilton": (-37.78, 175.28),
    "tauranga": (-37.68, 176.17),
    "rotorua": (-38.14, 176.25),
    "taupo": (-38.69, 176.07),
    "gisborne": (-38.66, 178.02),
    "napier": (-39.49, 176.92),
    "hastings": (-39.64, 176.84),
    "new plymouth": (-39.06, 174.07),
    "whanganui": (-39.93, 175.05),
    "palmerston north": (-40.35, 175.61),
    "levin": (-40.62, 175.29),
    "masterton": (-40.97, 175.65),
    "wellington": (-41.29, 174.78),
    "nelson": (-41.27, 173.28),
    "blenheim": (-41.51, 173.96),
    "greymouth": (-42.45, 171.21),
    "christchurch": (-43.53, 172.64),
    "timaru": (-44.39, 171.25),
    "oamaru": (-45.10, 170.97),
    "queenstown": (-45.03, 168.66),
    "dunedin": (-45.87, 170.50),
    "invercargill": (-46.41, 168.35),
}


@dataclass(frozen=True)
class ClockChange:
    at: float
    before: timedelta
    after: timedelta

    @property
    def forward(self) -> bool:
        return self.after > self.before

    @property
    def hours(self) -> float:
        return abs((self.after - self.before).total_seconds()) / HOUR


def _sun(jd: float) -> tuple[float, float]:
    t = (jd - J2000) / 36525.0
    mean_long = math.radians((280.46646 + t * (36000.76983 + t * 0.0003032)) % 360.0)
    anomaly = math.radians(357.52911 + t * (35999.05029 - 0.0001537 * t))
    eccentricity = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    centre = (
        math.sin(anomaly) * (1.914602 - t * (0.004817 + 0.000014 * t))
        + math.sin(2 * anomaly) * (0.019993 - 0.000101 * t)
        + math.sin(3 * anomaly) * 0.000289
    )
    omega = math.radians(125.04 - 1934.136 * t)
    apparent = mean_long + math.radians(centre - 0.00569 - 0.00478 * math.sin(omega))
    mean_obliquity = 23.0 + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
    obliquity = math.radians(mean_obliquity + 0.00256 * math.cos(omega))
    declination = math.asin(math.sin(obliquity) * math.sin(apparent))
    y = math.tan(obliquity / 2.0) ** 2
    equation = (
        y * math.sin(2 * mean_long)
        - 2 * eccentricity * math.sin(anomaly)
        + 4 * eccentricity * y * math.sin(anomaly) * math.cos(2 * mean_long)
        - 0.5 * y * y * math.sin(4 * mean_long)
        - 1.25 * eccentricity * eccentricity * math.sin(2 * anomaly)
    )
    return declination, math.degrees(equation) * 4.0


def _mean_noon(day: date, lon: float, tz: tzinfo) -> float:
    local_noon = datetime.combine(day, time(12), tz).timestamp() / DAY + UNIX_JD
    return math.floor(local_noon + lon / 360.0 + 0.5) - lon / 360.0


def _event(noon: float, lat: float, zenith: float, sign: int) -> float | None:
    moment = noon
    latitude = math.radians(lat)
    for _ in range(4):
        declination, equation = _sun(moment)
        cos_angle = (math.cos(math.radians(zenith)) - math.sin(latitude) * math.sin(declination)) / (math.cos(latitude) * math.cos(declination))
        if not -1.0 <= cos_angle <= 1.0:
            return None
        moment = noon + (sign * 4.0 * math.degrees(math.acos(cos_angle)) - equation) / 1440.0
    return moment


def _pair(day: date, lat: float, lon: float, tz: tzinfo, zenith: float) -> tuple[datetime | None, datetime | None]:
    noon = _mean_noon(day, lon, tz)
    rise = _event(noon, lat, zenith, -1)
    fall = _event(noon, lat, zenith, 1)
    if rise is None or fall is None:
        return None, None
    return tuple(datetime.fromtimestamp(round((moment - UNIX_JD) * DAY), tz) for moment in (rise, fall))


def sun_times(day: date, lat: float, lon: float, tz: tzinfo) -> tuple[datetime | None, datetime | None]:
    return _pair(day, lat, lon, tz, SUNRISE_ZENITH)


def twilight(day: date, lat: float, lon: float, tz: tzinfo) -> tuple[datetime | None, datetime | None]:
    return _pair(day, lat, lon, tz, CIVIL_ZENITH)


def moon(day: date) -> tuple[str, float]:
    jd = day.toordinal() + 1721425.0
    age = ((jd - NEW_MOON_JD) / SYNODIC_MONTH) % 1.0
    return PHASES[int(age * 8 + 0.5) % 8], round((1.0 - math.cos(2 * math.pi * age)) / 2.0, 3)


def _offset(local: Callable[[float], datetime], ts: float) -> timedelta:
    return local(ts).utcoffset() or timedelta(0)


def _change_minute(local: Callable[[float], datetime], low: float, high: float, before: timedelta) -> float:
    low_minute, high_minute = math.floor(low / 60.0), math.ceil(high / 60.0)
    while high_minute - low_minute > 1:
        middle = (low_minute + high_minute) // 2
        if _offset(local, middle * 60.0) == before:
            low_minute = middle
        else:
            high_minute = middle
    return high_minute * 60.0


def clock_changes(start: float, days: int, local: Callable[[float], datetime]) -> list[ClockChange]:
    end = start + days * DAY
    found = []
    moment = start
    offset = _offset(local, moment)
    while moment < end:
        step = min(moment + HOUR, end)
        later = _offset(local, step)
        if later != offset:
            found.append(ClockChange(_change_minute(local, moment, step, offset), offset, later))
        moment, offset = step, later
    return found


def _plain(name: str) -> str:
    text = "".join(ch for ch in unicodedata.normalize("NFKD", name) if not unicodedata.combining(ch))
    return " ".join(text.casefold().replace("-", " ").split())


def town(name: str) -> tuple[float, float] | None:
    return TOWNS.get(_plain(name))
