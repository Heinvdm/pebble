import asyncio
import json
import logging
import math
from dataclasses import dataclass, field
from typing import Callable

from ..activities.base import Activity, Ending
from ..activities.motion import Odometry, Wheels
from ..activities.trying import Try
from ..people.trust import STRANGER
from ..understand.request import BadRequest, Request, from_dict
from .book import SLOT
from .record import length

log = logging.getLogger(__name__)

PAD_POWER = 0.45
PAD_HOLD_S = 0.6
PAD_IDLE_S = 20.0
PAD_QUICK = 0.75
DEAD = 0.12
WAYPOINT_M = 0.2
WAYPOINT_STOP_M = 0.08
START_NEAR_M = 0.6
LEG_S = 45.0
WAIT_STEP_S = 0.2
STEP_WAIT_S = 600.0
REFLEXES = ("edge", "bump", "stall", "fault")


@dataclass
class Played:
    ok: bool
    how: str
    done: int = 0
    say: str = ""
    endings: list = field(default_factory=list)


def fill(steps: list, slots: dict) -> list:
    if not slots:
        return [json.loads(json.dumps(step)) for step in steps]
    text = json.dumps(steps)
    for slot, value in slots.items():
        text = text.replace("{" + slot + "}", str(value).replace('"', "'"))
    return json.loads(text)


def holes(steps: list) -> list[str]:
    return sorted(set(SLOT.findall(json.dumps(steps))))


def segments(steps: list) -> list[tuple[str, object]]:
    out: list[tuple[str, object]] = []
    for step in steps:
        name = step.get("do")
        if name == "request":
            out.append(("request", step))
        elif name == "route":
            out.append(("route", step))
        elif name == "spot":
            out.append(("spot", step))
        elif out and out[-1][0] == "card":
            out[-1][1].append(step)
        else:
            out.append(("card", [step]))
    return out


def thin(points: list, gap: float = WAYPOINT_M) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for point in points:
        x, y = float(point[0]), float(point[1])
        if not out or math.hypot(x - out[-1][0], y - out[-1][1]) >= gap:
            out.append((x, y))
    if points:
        last = (float(points[-1][0]), float(points[-1][1]))
        if out[-1] != last:
            out.append(last)
    return out


def gap_to_path(x: float, y: float, points: list) -> float:
    best = math.inf
    for a, b in zip(points, points[1:]):
        ax, ay, bx, by = float(a[0]), float(a[1]), float(b[0]), float(b[1])
        dx, dy = bx - ax, by - ay
        size = dx * dx + dy * dy
        t = 0.0 if size <= 1e-9 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / size))
        best = min(best, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
    if len(points) == 1:
        best = math.hypot(x - float(points[0][0]), y - float(points[0][1]))
    return best


class Route(Activity):
    kind = "route"

    def __init__(self, request: Request, asker, target=None, battery: bool = False, points=(), name: str = "", back: bool = False):
        super().__init__(request, asker, target, battery)
        self.points = [list(p) for p in points]
        self.name = name
        self.back = back
        self.track: list[tuple[float, float]] = []

    def describe(self) -> str:
        return f"going back the way we came from the {self.name}" if self.back else f"taking the way to the {self.name}"

    async def run(self, kit) -> Ending:
        nav = kit.nav
        odometer = kit.odometer
        if nav is None or odometer is None or not getattr(odometer, "local_usable", getattr(odometer, "usable", False)):
            return Ending("failed", "you had lost track of where you were", "I've lost track of where I am.")
        points = thin(list(reversed(self.points)) if self.back else self.points)
        if not points:
            return Ending("failed", "the way had no points", "I don't know that way.")
        x, y, _ = odometer.pose()
        start = 0
        joining = False
        if math.hypot(points[0][0] - x, points[0][1] - y) > START_NEAR_M:
            start = min(range(len(points)), key=lambda i: math.hypot(points[i][0] - x, points[i][1] - y))
            joining = math.hypot(points[start][0] - x, points[start][1] - y) > START_NEAR_M
        for px, py in points[start:]:
            if joining:
                trip = await nav.go_to(kit, px, py, stop_m=WAYPOINT_STOP_M)
                joining = False
            else:
                trip = await nav.go_to(kit, px, py, stop_m=WAYPOINT_STOP_M, max_s=LEG_S)
            x, y, _ = odometer.pose()
            self.track.append((x, y))
            if not trip.ok and trip.how not in ("near",):
                how = {"stopped": "stopped", "timeout": "timeout", "battery": "battery", "stuck": "reflex", "edge": "reflex", "lost_pose": "failed", "no_way": "blocked"}.get(trip.how, "blocked")
                return Ending(how, trip.text or f"you could not keep to the way ({trip.how})", "" if trip.how == "stopped" else "Something's in the way, so I stopped here.")
        return Ending("done", f"you went {'back ' if self.back else ''}along the way to the {self.name}, about {round(length(self.points))} m", "")


class Drive(Activity):
    kind = "drive"

    def __init__(self, request: Request, asker, target=None, battery: bool = False, on_step: Callable[[dict], None] | None = None):
        super().__init__(request, asker, target, battery)
        self.on_step = on_step or (lambda step: None)
        self.forward = 0.0
        self.turn = 0.0
        self.at = -math.inf
        self.mode = "still"
        self.peak = 0.0
        self.steps: list[dict] = []

    def describe(self) -> str:
        return "being driven with the touch pad"

    def push(self, forward: float, turn: float, now: float) -> None:
        self.forward = max(-1.0, min(1.0, float(forward)))
        self.turn = max(-1.0, min(1.0, float(turn)))
        self.at = now

    def _mode(self, forward: float, turn: float) -> str:
        if abs(forward) < DEAD and abs(turn) < DEAD:
            return "still"
        if abs(turn) > abs(forward):
            return "left" if turn > 0 else "right"
        return "forward" if forward > 0 else "back"

    def _close(self, odometry: Odometry) -> None:
        mode = self.mode
        if mode == "still":
            return
        step = None
        if mode in ("left", "right"):
            turned = odometry.turned_deg()
            if turned is not None and abs(turned) >= 1.0:
                step = {"do": "turn", "way": "left" if turned > 0 else "right", "degrees": round(abs(turned), 1)}
        else:
            travelled = odometry.travelled_mm()
            if travelled is not None and abs(travelled) >= 5.0:
                step = {"do": "move", "way": "forward" if travelled > 0 else "back", "metres": round(abs(travelled) / 1000.0, 3)}
        if step is not None:
            if self.peak >= PAD_QUICK:
                step["speed"] = "quick"
            self.steps.append(step)
            try:
                self.on_step(step)
            except Exception:
                log.exception("could not keep a step from the touch pad")
        self.peak = 0.0

    async def run(self, kit) -> Ending:
        wheels = Wheels(kit).open()
        odometry = Odometry(kit)
        try:
            while True:
                now = kit.pace.now()
                fresh = now - self.at <= PAD_HOLD_S
                forward, turn = (self.forward, self.turn) if fresh else (0.0, 0.0)
                mode = self._mode(forward, turn)
                if mode != self.mode:
                    self._close(odometry)
                    odometry.mark()
                    self.mode = mode
                if mode == "still":
                    await wheels.halt()
                    if now - self.at > PAD_IDLE_S:
                        return Ending("done", f"you were driven with the touch pad ({len(self.steps)} moves)", "")
                else:
                    self.peak = max(self.peak, abs(forward), abs(turn))
                    problem = await wheels.drive(forward * PAD_POWER, turn * PAD_POWER, PAD_POWER)
                    if problem:
                        self._close(odometry)
                        self.mode = "still"
                        return Ending("blocked", f"the touch pad drive stopped ({problem})", "")
                    hit = [r for r in wheels.reflexes() if r in REFLEXES]
                    if hit:
                        await wheels.halt()
                        self._close(odometry)
                        self.mode = "still"
                        return Ending("reflex", f"your body stopped the wheels ({hit[0]})", "")
                await kit.pace.sleep(kit.control_s)
        finally:
            if self.mode != "still":
                self._close(odometry)
            await wheels.halt()
            wheels.close()


class Player:
    def __init__(self, teaching):
        self.teaching = teaching
        self.running: tuple | None = None
        self.task: asyncio.Task | None = None
        self.stopped = False
        self.waits: dict = {}

    @property
    def commands(self):
        return self.teaching.commands

    def busy(self) -> bool:
        return self.task is not None and not self.task.done()

    def stop(self) -> None:
        self.stopped = True
        if self.task is not None and not self.task.done():
            self.task.cancel()

    def start(self, steps: list, asker, label: str, slots: dict | None = None, points=None, done: Callable | None = None) -> asyncio.Task | None:
        self.stop()
        self.stopped = False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        self.running = (label, asker)
        self.task = loop.create_task(self._play(steps, asker, label, slots or {}, points, done))
        return self.task

    async def _play(self, steps, asker, label, slots, points, done) -> Played:
        try:
            played = await self.play(steps, asker, label, slots, points)
        except asyncio.CancelledError:
            played = Played(False, "stopped")
        except Exception:
            log.exception("playing taught steps failed")
            played = Played(False, "failed")
        finally:
            self.running = None
        if any(ending is not None and ending.how == "reflex" for ending in played.endings):
            self.teaching.bumped(label)
        if done is not None:
            try:
                result = done(played)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                log.exception("the end of a taught run could not be handled")
        return played

    def ended(self, activity: Activity) -> None:
        found = self.waits.get(id(activity))
        if found is not None and found[0] is activity:
            found[1].set()

    async def wait(self, activity: Activity) -> Ending | None:
        runner = self.commands.runner
        if runner.current is activity or not getattr(activity, "_reported", False):
            event = asyncio.Event()
            self.waits[id(activity)] = (activity, event)
            try:
                if runner.current is activity or not getattr(activity, "_reported", False):
                    await event.wait()
            finally:
                self.waits.pop(id(activity), None)
        for done, ending in reversed(runner.history):
            if done is activity:
                return ending
        return activity.cause

    async def play(self, steps: list, asker, label: str, slots: dict | None = None, points=None) -> Played:
        commands = self.commands
        teaching = self.teaching
        steps = fill(steps, slots or {})
        if holes(steps):
            return Played(False, "slots", say="I don't know which one you mean.")
        card = teaching.card()
        count = 0
        endings = []
        for kind, part in segments(steps):
            if self.stopped:
                return Played(False, "stopped", count, endings=endings)
            asker = commands.fresh(asker)
            if asker.id is not None and asker.tier == STRANGER and not asker.owner:
                return Played(False, "refused", count, "I only do that for people I know.", endings)
            if kind == "card":
                kept, errors = card.check(part)
                if errors:
                    teaching.record("howto_steps_dropped", name=label, errors=len(errors))
                if not kept:
                    return Played(False, "refused", count, "I can't do that in this body.", endings)
                verdict = commands.decide_now(Request("try_new", text=label[:160]), asker)
                if not verdict.yes:
                    await commands._answer(Request("try_new", text=label[:160]), asker, verdict, "taught")
                    return Played(False, "refused", count, verdict.say, endings)
                trying = commands.trying
                activity = Try(Request("try_new", text=label[:160], name=label), asker, None, False, kept, label, trying.gate, trying.run_step)
                activity.skill = label
                activity.taught = True
                commands.runner.start(activity)
                ending = await self.wait(activity)
                endings.append(ending)
                count += len(kept)
                if ending is None or ending.how != "done":
                    return Played(False, ending.how if ending is not None else "stopped", count, ending.say if ending is not None else "", endings)
                continue
            if kind == "route":
                route = teaching.book.get(str(part.get("route") or ""))
                if route is None or route.kind != "route":
                    return Played(False, "failed", count, "I don't know that way any more.", endings)
                refused = await teaching.route_refused(route, asker)
                if refused is not None:
                    return Played(False, "refused", count, refused, endings)
                activity = Route(Request("go_to_place", place=route.name), asker, None, False, route.points, route.name)
                commands.runner.start(activity)
                ending = await self.wait(activity)
                endings.append(ending)
                count += 1
                if ending is None or ending.how != "done":
                    return Played(False, ending.how if ending is not None else "stopped", count, ending.say if ending is not None else "", endings)
                continue
            if kind == "spot":
                part = {"do": "request", "request": {"kind": "go_back", "place": part.get("spot", "")}}
            try:
                request = from_dict(part.get("request") or {})
            except BadRequest:
                return Played(False, "failed", count, "Part of that doesn't make sense to me any more.", endings)
            if request.kind == "harm":
                verdict = await commands.act(request, asker, "taught")
                return Played(False, "refused", count, verdict.say, endings)
            private = next((step.place for step in request.steps() if teaching.private(step.place)), "")
            if private:
                teaching.record("howto_refused", name=label, why="private room")
                return Played(False, "refused", count, f"That's in the {private}, and it's private, so I won't go in.", endings)
            before = commands.runner.current
            verdict = await commands.act(request, asker, "taught")
            if verdict.answer != "yes":
                return Played(False, "refused", count, verdict.say, endings)
            count += 1
            activity = commands.runner.current
            if activity is not None and activity is not before:
                ending = await self.wait(activity)
                endings.append(ending)
                if ending is None or ending.how not in ("done",):
                    return Played(False, ending.how if ending is not None else "stopped", count, ending.say if ending is not None else "", endings)
        return Played(True, "done", count, endings=endings)
