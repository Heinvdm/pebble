import argparse
import asyncio
import logging
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ...activities.base import Target
from ...activities.gate import Asker
from ...activities.kinds import Follow
from ...people.trust import TRUSTED
from ...understand.request import Request
from ..geometry import wrap
from ..navigator import FollowControl, Lead
from ..route import plan
from .building import office
from .rig import Rig

log = logging.getLogger(__name__)

TICK_S = 0.1
LIMIT_S = 900.0
DONE_HOLD_S = 5.0
NEAR_MISS_M = 0.45
REACH_M = 1.0
FINISH_M = 1.8
WAIT_RELEASE_M = 1.5
RETURN_NEAR_M = 2.0
NOTICED_S = 2.0
WAIT_GIVE_UP_S = 45.0
SLOW_MM_S = 220.0
TILT_DEG = 8.0
FOV_DEG = 70.0
PERSON_RANGE_M = 6.0
START_S = 2.0
OTHERS_M = 3.0


class Responder:
    def __init__(self, world, lead, kind: str, now):
        self.world = world
        self.lead = lead
        self.kind = kind
        self.now = now
        self.grid = world.truth()
        self.state = "walk"
        self.since = 0.0
        self.waits = 0
        self.returns = 0
        self.noticed_since = None
        self.final = lead.plan[-1] if lead.plan else (lead.x, lead.y)

    def _path(self, goal: tuple[float, float]) -> list:
        lead = self.lead
        path = plan(self.grid, (lead.x / 1000.0, lead.y / 1000.0), (goal[0] / 1000.0, goal[1] / 1000.0))
        if not path:
            return [goal]
        return [(px * 1000.0, py * 1000.0) for px, py in path[1:]]

    def heard(self, text: str) -> None:
        lead = self.lead
        if self.kind == "brisk":
            return
        if text == "Wait for me!" and not lead.done:
            self.waits += 1
            if self.kind == "waits":
                self._hold("hold")
            else:
                lead.speed_mm_s = SLOW_MM_S
        elif (text.endswith("?") or text.startswith("I'll wait here")) and self.state == "walk" and not self._sees():
            self.returns += 1
            self.state = "return"
            lead.hold = False
            lead.guided = True
            lead.route = self._path((self.world.pose.x, self.world.pose.y))

    def _hold(self, state: str) -> None:
        self.state = state
        self.lead.hold = True
        self.since = self.now()

    def _sees(self) -> bool:
        lead, world = self.lead, self.world
        x, y = world.pose.x, world.pose.y
        return math.hypot(lead.x - x, lead.y - y) < 4000.0 and world.sees(lead.x, lead.y, x, y)

    def tick(self) -> None:
        lead, world = self.lead, self.world
        gap = math.hypot(lead.x - world.pose.x, lead.y - world.pose.y) / 1000.0
        if self.state == "return":
            if (self._sees() and gap <= RETURN_NEAR_M) or not lead.route:
                lead.route = []
                self._hold("hold_back")
            return
        noticed = gap <= WAIT_RELEASE_M and visible(world, lead.name)
        self.noticed_since = (self.noticed_since or self.now()) if noticed else None
        if self.state in ("hold", "hold_back") and ((self.noticed_since is not None and self.now() - self.noticed_since >= NOTICED_S) or self.now() - self.since > WAIT_GIVE_UP_S):
            lead.hold = False
            lead.guided = False
            if self.state == "hold_back":
                if lead.plan:
                    lead.route = self._path(lead.plan[lead.leg])
                else:
                    lead.guided = True
                    lead.route = self._path(self.final)
            self.state = "walk"


@dataclass
class Result:
    mode: str
    walker: str
    seed: int
    route_pct: float = 0.0
    finished: bool = False
    seconds: float = 0.0
    gap_mean_m: float = 0.0
    out_of_sight_s: float = 0.0
    stuck: int = 0
    recovered: int = 0
    bumps: int = 0
    near_misses: int = 0
    swaps: int = 0
    pose_error_m: float = 0.0
    heading_error_deg: float = 0.0
    ending: str = ""
    said: list = field(default_factory=list)
    map_m2: float = 0.0
    places: int = 0
    catches: int = 0


def rough_gap(width_frac: float) -> float:
    return 0.4 / (2.0 * max(width_frac, 1e-3) * math.tan(math.radians(FOV_DEG) / 2.0))


def densify(points: list, step: float = 0.1) -> list:
    out = []
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        length = math.hypot(bx - ax, by - ay)
        n = max(1, int(length / step))
        for i in range(n):
            t = i / n
            out.append((ax + (bx - ax) * t, ay + (by - ay) * t))
    out.append(points[-1])
    return out


def visible(world, name: str) -> bool:
    person = next((p for p in world.people if p.name == name), None)
    if person is None:
        return False
    x, y = world.point(87.0)
    dx, dy = person.x - x, person.y - y
    if math.hypot(dx, dy) / 1000.0 > PERSON_RANGE_M:
        return False
    angle = abs(wrap(math.atan2(dy, dx) - world.pose.heading))
    if angle > math.radians(FOV_DEG / 2.0):
        return False
    return world.sees(x, y, person.x, person.y)


async def run_case(mode: str, walker: str, seed: int = 7, limit_s: float = LIMIT_S, map_png: str | None = None, echo: bool = False) -> Result:
    world, lead, route = office()
    random.seed(seed)
    rig = Rig(world, seed)
    clock, pace, eyes, nav, kit = rig.clock, rig.pace, rig.eyes, rig.nav, rig.kit
    result = Result(mode, walker, seed)
    responder = Responder(world, lead, walker, clock.monotonic)
    lead.hold = True
    t0 = clock.monotonic() + START_S
    said: list[tuple[float, str]] = []
    seen_others: dict[int, float] = {}

    def trace(text: str) -> None:
        if echo:
            print(f"{clock.monotonic() - t0:7.1f}s  {text}", flush=True)

    def say(text: str) -> None:
        now = clock.monotonic()
        said.append((round(now - t0, 1), text))
        trace(f'says "{text}"')
        responder.heard(text)
        if text.endswith("?"):
            lead.talking_until = lead.t + 2.0

    def people_near() -> bool:
        sight = eyes.latest()
        return bool(sight and (sight.people or any(t.animal for t in sight.things)))

    def others_near(person_id) -> bool:
        sight = eyes.latest()
        now = clock.monotonic()
        if sight is None:
            return False
        for person in sight.people:
            if person.track != lead.track and rough_gap(person.width_frac) <= OTHERS_M:
                seen_others[person.track] = now
        for thing in sight.things:
            if thing.animal and thing.floor_m is not None and thing.floor_m <= OTHERS_M:
                seen_others[-1] = now + 5.0
        return any(now - at <= 3.0 for at in seen_others.values())

    kit.say = say
    kit.people_near = people_near
    kit.others_near = others_near
    odometer = rig.odometer
    await rig.run(START_S)
    lead.hold = False
    rig.visit()
    sx, sy = world.pose.x / 1000.0, world.pose.y / 1000.0
    asker = Asker("ina", "Ina", TRUSTED, False, True)
    if mode == "before":
        activity = Follow(Request("follow", who="me"), asker, Target("ina", "Ina", TRUSTED))
        task = asyncio.ensure_future(activity.run(kit))
    else:
        task = asyncio.ensure_future(nav.follow(kit, Lead("ina", "Ina", lead.track), FollowControl(1.0)))
    points = densify([(x / 1000.0, y / 1000.0) for x, y in route])
    covered: set = set()
    gaps = []
    hidden_since = None
    longest = 0.0
    close_to = set()
    near_misses = 0
    last_xy = (sx, sy)
    done_since = None
    locked_track = None
    swaps = 0
    while True:
        await pace.run_until(clock.monotonic() + TICK_S)
        now = clock.monotonic()
        elapsed = now - t0
        rx, ry = world.pose.x / 1000.0, world.pose.y / 1000.0
        lx, ly = lead.x / 1000.0, lead.y / 1000.0
        gap = math.hypot(lx - rx, ly - ry)
        gaps.append(gap)
        responder.tick()
        for i, point in enumerate(points):
            if i not in covered and abs(point[0] - rx) <= REACH_M and abs(point[1] - ry) <= REACH_M and math.hypot(point[0] - rx, point[1] - ry) <= REACH_M:
                covered.add(i)
        if visible(world, "ina"):
            hidden_since = None
        else:
            hidden_since = now if hidden_since is None else hidden_since
            longest = max(longest, now - hidden_since)
        for person in world.people:
            if person is lead:
                continue
            d = math.hypot(person.x / 1000.0 - rx, person.y / 1000.0 - ry)
            toward = ((rx - last_xy[0]) * (person.x / 1000.0 - rx) + (ry - last_xy[1]) * (person.y / 1000.0 - ry)) / max(d, 1e-6) / TICK_S if d > 0 else 0.0
            if d < NEAR_MISS_M and toward > 0.02 and person.name not in close_to:
                close_to.add(person.name)
                near_misses += 1
                trace(f"near miss with {person.name} at {d:.2f} m")
            elif d >= NEAR_MISS_M + 0.2:
                close_to.discard(person.name)
        last_xy = (rx, ry)
        follower = nav.following
        if follower is not None and follower.lock.track is not None and follower.lock.lost_for(now) < 0.3:
            if locked_track is not None and follower.lock.track != locked_track and follower.lock.track != lead.track:
                swaps += 1
            locked_track = follower.lock.track
        if lead.done and gap <= FINISH_M:
            done_since = now if done_since is None else done_since
            if now - done_since >= DONE_HOLD_S:
                result.finished = True
                break
        else:
            done_since = None
        if task.done() or elapsed >= limit_s:
            break
    if not task.done():
        task.cancel()
    try:
        ending = await task
        result.ending = f"{ending.how}: {ending.text}"
    except asyncio.CancelledError:
        result.ending = "finished" if result.finished else "cut off"
    except Exception as error:
        log.exception("the follow failed")
        result.ending = f"failed ({type(error).__name__}: {error})"
    if result.finished:
        result.ending = "finished"
    await rig.body.drive(0, 0)
    await pace.run_until(clock.monotonic() + 0.3)
    result.route_pct = round(100.0 * len(covered) / max(1, len(points)), 1)
    result.seconds = round(clock.monotonic() - t0, 1)
    result.gap_mean_m = round(sum(gaps) / max(1, len(gaps)), 2)
    result.out_of_sight_s = round(longest, 1)
    result.near_misses = near_misses
    result.swaps = swaps
    result.catches = world.catches
    result.said = said
    result.bumps = world.bumps
    if mode == "before":
        px, py, ph = odometer.pose()
        heading = math.radians(ph)
    else:
        px, py, heading = nav.pose.pose_rad()
        result.stuck = nav.stats.stuck
        result.recovered = nav.stats.recovered
        counts = nav.chart.grid.counts()
        result.map_m2 = counts["free_m2"]
        result.places = len(nav.chart.places)
        if map_png:
            from ..mapview import png

            png(nav.chart, map_png, nav.pose.pose_rad(), nav.trail, [[(x / 1000.0, y / 1000.0) for x, y in route]])
    result.pose_error_m = round(math.hypot(px - world.pose.x / 1000.0, py - world.pose.y / 1000.0), 2)
    result.heading_error_deg = round(abs(math.degrees(wrap(heading - world.pose.heading))), 1)
    await rig.close()
    return result


def table(results: list[Result]) -> str:
    rows = ["| Follow code | Person | Route completed | Finished | Average gap | Longest out of sight | Stuck / got free | Bumps | Near misses | Swapped person | Pose error at end | Time |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    groups: dict = {}
    for result in results:
        groups.setdefault((result.mode, result.walker), []).append(result)
    for (mode, walker), items in groups.items():
        n = len(items)

        def mean(name):
            return sum(getattr(r, name) for r in items) / n

        rows.append(
            f"| {mode} | {walker} | {mean('route_pct'):.0f} % | {sum(r.finished for r in items)} of {n} | {mean('gap_mean_m'):.1f} m | {mean('out_of_sight_s'):.0f} s | {mean('stuck'):.1f} / {mean('recovered'):.1f} | {mean('bumps'):.1f} | {mean('near_misses'):.1f} | {sum(r.swaps for r in items)} | {mean('pose_error_m'):.2f} m | {mean('seconds'):.0f} s |"
        )
    return "\n".join(rows)


async def main_async(args) -> int:
    results = []
    out = Path(args.out) if args.out else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
    for mode in args.modes:
        for walker in args.walkers:
            if mode == "before" and walker != "brisk" and not args.all:
                continue
            for seed in range(args.seed, args.seed + args.seeds):
                png = str(out / f"map_{mode}_{walker}_{seed}.png") if out is not None and mode == "after" else None
                result = await run_case(mode, walker, seed, args.limit, png, args.echo)
                results.append(result)
                print(f"{mode:6} {walker:6} seed {seed}: route {result.route_pct:5.1f} %, {'finished' if result.finished else 'not finished'}, gap {result.gap_mean_m:.1f} m, hidden {result.out_of_sight_s:.0f} s, stuck {result.stuck}/{result.recovered}, bumps {result.bumps}, near misses {result.near_misses}, swaps {result.swaps}, pose error {result.pose_error_m:.2f} m, {result.seconds:.0f} s ({result.ending})", flush=True)
                if args.echo or args.said:
                    for at, text in result.said:
                        print(f"    {at:6.1f}s  {text}")
    print()
    print(table(results))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.nav.sim.trial", description="Follow a person through an unknown office building in the sim and measure it.")
    parser.add_argument("--modes", nargs="+", default=["before", "after"], choices=["before", "after"])
    parser.add_argument("--walkers", nargs="+", default=["brisk", "waits", "slows"], choices=["brisk", "waits", "slows"])
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--limit", type=float, default=LIMIT_S)
    parser.add_argument("--out", default="")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--echo", action="store_true")
    parser.add_argument("--said", action="store_true")
    args = parser.parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
