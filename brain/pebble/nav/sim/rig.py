import asyncio
import math
import random

from ...activities.kit import Kit
from ...activities.odometer import Odometer
from ...body.api import Body
from ...body.profile import BodyProfile, resolve_profile
from ...clock import FakeClock
from ...link.client import LinkClient
from ...safety.feeds import ListFeed
from ...seams.face import LogFace
from ...seams.sight import NoEyes
from ...sim.firmware import SimFirmware
from ...sim.scene import NOON, LoopbackTransport, VirtualTime
from ...tools.builtin import Permissions
from ..navigator import Navigator
from .eyes import BuildingEyes

GYRO_HZ = 100.0
GYRO_BIAS = (0.004, -0.003, 0.002)
GYRO_NOISE = 0.004
STEP_HZ = 1.8
RUN_STEP_S = 0.05
STEP_PEAK = 2.5


class NavFirmware(SimFirmware):
    def __init__(self, world, now, seed: int = 7, **kwargs):
        super().__init__(world, **kwargs)
        self.now = now
        self.gyro = ListFeed()
        self.accel = ListFeed()
        self.rng = random.Random(seed + 7)
        self._gyro_due = 0.0
        self._phase = 0.0

    def step(self, dt: float) -> list[str]:
        out = super().step(dt)
        at = self.now() + dt
        if at >= self._gyro_due:
            self._gyro_due = at + 1.0 / GYRO_HZ
            yaw = getattr(self.world, "yaw_rate", 0.0)
            tilt = math.radians(self.tilt)
            values = (yaw * math.cos(tilt), 0.0, yaw * math.sin(tilt))
            self.gyro.push(at, *(v + b + self.rng.gauss(0.0, GYRO_NOISE) for v, b in zip(values, GYRO_BIAS)))
            bounce = 0.0
            if getattr(self.world, "carried", False) and getattr(self.world, "carry", None):
                self._phase += 2.0 * math.pi * STEP_HZ / GYRO_HZ
                bounce = STEP_PEAK * max(0.0, math.sin(self._phase)) ** 4 * 2.0
            pull = 9.81 + bounce + self.rng.gauss(0.0, 0.05)
            self.accel.push(at, pull * math.cos(tilt), 0.0, pull * math.sin(tilt))
        return out


class Rig:
    def __init__(self, world, seed: int = 7, say=None, people_near=None, others_near=None, eyes: bool = True, gyro: bool = True, store=None):
        self.clock = FakeClock.at(NOON)
        self.world = world
        self.firmware = NavFirmware(world, self.clock.monotonic, seed)
        self.transport = LoopbackTransport(self.firmware)
        self.pace = VirtualTime(self.clock, self.firmware, self.transport)
        self.link = LinkClient(lambda: self.transport, ping_every_s=3600.0, stale_s=1e9)
        self.body = Body(self.link, self.clock, BodyProfile.load(resolve_profile("pc_sim", "body")))
        self.body.start()
        self.eyes = BuildingEyes(world, self.clock.monotonic, lambda: self.firmware.tilt, seed=seed) if eyes else None
        self.said: list[tuple[float, str]] = []
        self.nav = Navigator(self.body, self.eyes, store, self.pace, gyro=self.firmware.gyro if gyro else None, accel=self.firmware.accel if gyro else None, wall=self.clock.monotonic)
        self.odometer = Odometer.for_body(self.body)
        permissions = Permissions(can_move=True)
        self.kit = Kit(
            self.body,
            permissions,
            lambda: None,
            people_near or (lambda: False),
            LogFace(),
            pace=self.pace,
            eyes=self.eyes if self.eyes is not None else NoEyes(),
            odometer=self.nav.pose,
            say=say or self._say,
            others_near=others_near or (lambda person_id: False),
            nav=self.nav,
        )
        self.background = [asyncio.ensure_future(self.nav.run()), asyncio.ensure_future(self.odometer.run(self.body))]

    def _say(self, text: str) -> None:
        self.said.append((round(self.clock.monotonic() - 1000.0, 1), text))

    def visit(self) -> None:
        nav = self.nav
        x, y, th = self.world.pose.x / 1000.0, self.world.pose.y / 1000.0, self.world.pose.heading
        chart = nav.charts.visit()
        nav._use(chart)
        nav.pose.start_visit(chart.id, x, y, th)
        chart.remember_spot("start", x, y, "start")
        self.odometer.reset(x, y, th)

    async def run(self, seconds: float) -> None:
        end = self.clock.monotonic() + seconds
        while self.clock.monotonic() < end - 1e-9:
            await self.pace.run_until(min(end, self.clock.monotonic() + RUN_STEP_S))

    async def until(self, task, limit_s: float, tick_s: float = 0.5, check=None) -> bool:
        end = self.clock.monotonic() + limit_s
        while self.clock.monotonic() < end:
            await self.run(tick_s)
            if task.done() or (check is not None and check()):
                return True
        return task.done()

    def error(self) -> tuple[float, float]:
        x, y, th = self.nav.pose.pose_rad()
        w = self.world.pose
        return math.hypot(x - w.x / 1000.0, y - w.y / 1000.0), abs(math.degrees(math.atan2(math.sin(th - w.heading), math.cos(th - w.heading))))

    async def close(self) -> None:
        for item in self.background:
            item.cancel()
        await asyncio.gather(*self.background, return_exceptions=True)
        await self.body.close()
