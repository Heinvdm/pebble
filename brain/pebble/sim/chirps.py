import math
import random
from dataclasses import dataclass

from ..hearing.chirp import Chirp

WALL_DB = 8.0
QUIETEST_DB = -75.0
JITTER_DB = 1.5
KEEP_S = 600.0
KEEP_N = 64


@dataclass
class SimAlarm:
    name: str
    x: float
    y: float
    period_s: float = 40.0
    level_db: float = -30.0
    freq_hz: float = 3200.0
    phase_s: float = 5.0
    chirping: bool = True


class SimChirps:
    def __init__(self, world, now, alarms: list[SimAlarm], seed: int = 7, jitter_db: float = JITTER_DB):
        self.world = world
        self.now = now
        self.alarms = list(alarms)
        self.rng = random.Random(seed)
        self.jitter_db = jitter_db
        self.heard: list[Chirp] = []
        self.due: dict[str, float] = {}
        self.counts: dict[str, int] = {}
        self.start: float | None = None
        self.muted = False

    def level_at(self, alarm: SimAlarm) -> float:
        pose = self.world.pose
        metres = max(0.3, math.hypot(alarm.x - pose.x, alarm.y - pose.y) / 1000.0)
        level = alarm.level_db - 20.0 * math.log10(metres)
        sees = getattr(self.world, "sees", None)
        if sees is not None and not sees(pose.x, pose.y, alarm.x, alarm.y):
            level -= WALL_DB
        return level + self.rng.gauss(0.0, self.jitter_db)

    def pump(self) -> None:
        now = self.now()
        if self.start is None:
            self.start = now
        for alarm in self.alarms:
            due = self.due.get(alarm.name, self.start + alarm.phase_s)
            while due <= now:
                if alarm.chirping:
                    count = self.counts.get(alarm.name, 0) + 1
                    self.counts[alarm.name] = count
                    level = self.level_at(alarm)
                    if level >= QUIETEST_DB and not self.muted:
                        score = 0.3 if count == 1 else (0.6 if count == 2 else 0.9)
                        self.heard.append(Chirp(due, round(level, 1), alarm.freq_hz, alarm.period_s if count > 1 else None, score))
                due += alarm.period_s
            self.due[alarm.name] = due
        self.heard = [chirp for chirp in self.heard if chirp.at >= now - KEEP_S][-KEEP_N:]

    def chirps(self, since: float) -> list[Chirp]:
        self.pump()
        return [chirp for chirp in self.heard if chirp.at >= since]

    async def run(self, pace, every: float = 0.25) -> None:
        while True:
            self.pump()
            await pace.sleep(every)
