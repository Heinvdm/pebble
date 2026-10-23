import math
from dataclasses import dataclass
from typing import Callable

from ..seams.later import DockAttempt
from ..seams.sight import DOCK_TAG_ID, Eyes, SeenTag
from .base import Activity, Ending
from .kinds import level_head, moved
from .kit import Kit
from .motion import Wheels, clamp, leave_dock, roll_by, turn_by, wrap_deg
from .seeing import body_bearing

REAR_CAMERA_AHEAD_M = 0.045
DOCKED_X_M = 0.08
NEAR_DOCK_X_M = 0.9
STAGING_X_M = 0.45
LINE_UP_X_M = 0.26
KEEP_IN_VIEW_DEG = 22.0
OFF_LINE_M = 0.08
ALIGNED_Y_M = 0.02
ALIGNED_DEG = 9.0
SMOOTH = 5
LINE_ZONE_X_M = 0.65
LINE_GAIN_DEG_PER_M = 300.0
LINE_MAX_DEG = 12.0
GOOD_SCORE = 0.5
REVERSE_POWER = 0.32
FINAL_POWER = 0.26
HOMING_MAX_S = 300.0
TAG_LOST_S = 2.5
MAX_TRIES = 3
SCAN_STEP_DEG = 35.0
SWEEP_DEG = 70.0
TAG_AGE_S = 0.8
STUCK_S = 2.5
PRINT_MARKS_M = (1.0, 0.6, 0.35)
CHARGER_WIDTH_M = 0.2
CHARGER_X_M = 0.05
CHARGER_FOV_DEG = 70.0
NEAR_CHARGER_M = 1.0
PRINT_STEP_DEG = 40.0
SIGHT_TRIES = 40
SIGHT_STEP_M = 0.15
SIGHT_FINAL_M = 0.3
SIGHT_FINAL_S = 15.0


@dataclass(frozen=True)
class DockPose:
    x: float
    y: float
    heading_deg: float


def wrap_rad(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def pose_from_tag(tag: SeenTag) -> DockPose:
    bearing = math.radians(tag.bearing_deg)
    yaw = math.radians(tag.yaw_deg)
    heading = bearing - yaw
    camera_x = tag.distance_m * math.cos(yaw)
    camera_y = -tag.distance_m * math.sin(yaw)
    x = camera_x - REAR_CAMERA_AHEAD_M * math.cos(heading)
    y = camera_y - REAR_CAMERA_AHEAD_M * math.sin(heading)
    return DockPose(x, y, math.degrees(wrap_rad(heading)))


def dock_tag(kit: Kit) -> SeenTag | None:
    sight = kit.eyes.latest(TAG_AGE_S)
    if sight is None or sight.camera != "rear":
        return None
    tags = [tag for tag in sight.tags if tag.id == DOCK_TAG_ID]
    return tags[0] if tags else None


def smoothed(poses: list[DockPose]) -> DockPose:
    def middle(values: list[float]) -> float:
        ordered = sorted(values)
        return ordered[len(ordered) // 2]

    return DockPose(middle([p.x for p in poses]), middle([p.y for p in poses]), middle([p.heading_deg for p in poses]))


def steer_back(pose: DockPose) -> tuple[float, float]:
    towards_tag = math.degrees(math.atan2(-pose.y, -pose.x))
    goal_x = max(LINE_UP_X_M, pose.x * 0.5)
    wanted = math.degrees(math.atan2(-pose.y, goal_x - pose.x))
    wanted = towards_tag + clamp(wrap_deg(wanted - towards_tag), -KEEP_IN_VIEW_DEG, KEEP_IN_VIEW_DEG)
    travel = wrap_deg(pose.heading_deg + 180.0)
    error = wrap_deg(wanted - travel)
    turn = clamp(math.radians(error) * 0.9, -0.3, 0.3)
    if abs(error) > 30.0:
        return 0.0, math.copysign(max(abs(turn), 0.24), turn)
    return -REVERSE_POWER * max(0.5, math.cos(math.radians(error))), turn


def follow_line(pose: DockPose) -> tuple[float, float]:
    wanted = clamp(pose.y * LINE_GAIN_DEG_PER_M, -LINE_MAX_DEG, LINE_MAX_DEG)
    error = wrap_deg(wanted - pose.heading_deg)
    turn = clamp(math.radians(error) * 1.2, -0.25, 0.25)
    if abs(error) > 25.0:
        return 0.0, math.copysign(max(abs(turn), 0.22), turn)
    return -REVERSE_POWER * 0.85, turn


def back_towards(tag: SeenTag) -> tuple[float, float]:
    turn = clamp(-math.radians(tag.bearing_deg) * 0.9, -0.3, 0.3)
    if abs(tag.bearing_deg) > 20.0:
        return 0.0, math.copysign(max(abs(turn), 0.24), turn)
    return -REVERSE_POWER, turn


def charger_gap_m(seen, fov_deg: float = CHARGER_FOV_DEG) -> float:
    return CHARGER_WIDTH_M / (2.0 * max(seen.width_frac, 1e-3) * math.tan(math.radians(fov_deg) / 2.0))


class DockHoming:
    def __init__(self, kit: Kit, wheels: Wheels):
        self.kit = kit
        self.wheels = wheels
        self.notes: list[str] = []
        self.printed: set[float] = set()
        self.by_sight_only = False

    async def print_dock(self, mark: float) -> None:
        self.printed.add(mark)
        printer = getattr(self.kit.eyes, "dock_print", None)
        if printer is None:
            return
        await self.wheels.halt()
        try:
            vec = await printer()
        except Exception:
            vec = None
        if vec:
            self.kit.dock_print(vec)

    async def look_for_charger(self, camera: str):
        finder = getattr(self.kit.eyes, "look_for", None)
        if finder is None:
            return None
        try:
            return await finder("charger", camera)
        except Exception:
            return None

    async def find_by_print(self):
        for _ in range(int(360 / PRINT_STEP_DEG) + 1):
            seen = await self.look_for_charger("front")
            if seen is not None:
                return seen
            _, problem = await turn_by(self.kit, self.wheels, PRINT_STEP_DEG)
            moved(self.kit)
            if problem and problem != "the turn took too long":
                self.notes.append(problem)
                return None
        return None

    async def approach_by_print(self, seen) -> SeenTag | None:
        kit = self.kit
        for _ in range(8):
            angle = body_bearing(seen.bearing_deg, "front")
            if abs(angle) > 4.0:
                await turn_by(kit, self.wheels, angle)
                moved(kit)
            gap = charger_gap_m(seen)
            if gap <= NEAR_CHARGER_M + 0.15:
                break
            _, problem = await roll_by(kit, self.wheels, min(0.6, gap - NEAR_CHARGER_M) * 1000.0, 0.4)
            moved(kit)
            if problem:
                self.notes.append(f"the drive towards the charger stopped ({problem})")
                break
            again = await self.look_for_charger("front")
            if again is None:
                break
            seen = again
        await turn_by(kit, self.wheels, 180.0)
        moved(kit)
        await kit.eyes.use_camera("rear")
        return await self.look_for_tag(SWEEP_DEG)

    async def by_sight(self) -> tuple[bool, str]:
        kit = self.kit
        await kit.eyes.use_camera("rear")
        misses = 0
        staged = False
        for _ in range(SIGHT_TRIES):
            if kit.body.telemetry.docked:
                self.by_sight_only = True
                return True, "reversed onto the charger by sight alone, without its tag (less precise)"
            reason = self.wheels.why_not()
            if reason:
                return False, reason
            seen = await self.look_for_charger("rear")
            if seen is None:
                misses += 1
                if misses >= 4:
                    return False, "lost sight of the charger"
                await turn_by(kit, self.wheels, 20.0 if misses % 2 else -40.0)
                moved(kit)
                continue
            misses = 0
            angle = body_bearing(seen.bearing_deg, "rear")
            error = wrap_deg(angle - 180.0)
            gap = charger_gap_m(seen, 65.0)
            odometer = self.odometer
            if not staged and odometer is not None and odometer.usable and gap > STAGING_X_M + 0.15:
                staged = True
                x, y, heading = odometer.pose()
                aim = math.radians(heading + angle)
                reach = gap + REAR_CAMERA_AHEAD_M
                odometer.relocate(CHARGER_X_M - reach * math.cos(aim), -reach * math.sin(aim), heading)
                self.notes.append("placed yourself by the charger's look and lined up in front of it")
                problem = await self.drive_to(STAGING_X_M, 0.0, 0.0)
                moved(kit)
                if problem:
                    self.notes.append(f"lining up stopped ({problem})")
                continue
            if abs(error) > 4.0:
                await turn_by(kit, self.wheels, error * 0.8)
                moved(kit)
            if gap > SIGHT_FINAL_M:
                _, problem = await roll_by(kit, self.wheels, -min(SIGHT_STEP_M, gap - SIGHT_FINAL_M + 0.05) * 1000.0, REVERSE_POWER)
                moved(kit)
                if problem and problem != "the wheels stopped making progress":
                    return False, problem
                continue
            end = kit.pace.now() + SIGHT_FINAL_S
            last = kit.body.telemetry.encoders()
            still_since = None
            while kit.pace.now() < end and not kit.body.telemetry.docked:
                if await self.wheels.drive(-FINAL_POWER, 0.0, 0.5):
                    break
                await kit.pace.sleep(kit.control_s)
                now_counts = kit.body.telemetry.encoders()
                if now_counts is not None and now_counts == last:
                    still_since = still_since or kit.pace.now()
                    if kit.pace.now() - still_since > STUCK_S:
                        break
                else:
                    still_since = None
                last = now_counts
            await self.wheels.halt()
            if kit.body.telemetry.docked:
                self.by_sight_only = True
                return True, "reversed onto the charger by sight alone, without its tag (less precise)"
            await roll_by(kit, self.wheels, 250.0, 0.35)
            moved(kit)
        return False, "could not get onto the charger by sight"

    @property
    def odometer(self):
        return getattr(self.kit, "odometer", None)

    async def look_for_tag(self, sweep_deg: float) -> SeenTag | None:
        await self.kit.pace.sleep(0.4)
        tag = dock_tag(self.kit)
        if tag is not None or sweep_deg <= 0:
            return tag
        turned = 0.0
        for step in (sweep_deg / 2.0, -sweep_deg, sweep_deg / 2.0) if sweep_deg < 360 else ():
            done, problem = await turn_by(self.kit, self.wheels, step)
            turned += done
            await self.kit.pace.sleep(0.4)
            tag = dock_tag(self.kit)
            if tag is not None or problem and problem != "the turn took too long":
                return tag
        if sweep_deg >= 360:
            while turned < 360.0:
                done, problem = await turn_by(self.kit, self.wheels, SCAN_STEP_DEG)
                turned += abs(done) if done else SCAN_STEP_DEG
                await self.kit.pace.sleep(0.4)
                tag = dock_tag(self.kit)
                if tag is not None:
                    return tag
                if problem and problem != "the turn took too long":
                    self.notes.append(problem)
                    return None
        return tag

    async def drive_to(self, x: float, y: float, face_deg: float | None) -> str | None:
        odometer = self.odometer
        if odometer is None or not odometer.usable:
            return "you do not know where you are"
        px, py, heading = odometer.pose()
        dx, dy = x - px, y - py
        distance = math.hypot(dx, dy)
        going = getattr(self.kit.nav, "go_to", None)
        if going is not None and distance > 0.6:
            trip = await going(self.kit, x, y, stop_m=0.15)
            if not trip.ok:
                return trip.text or trip.how
            px, py, heading = odometer.pose()
            dx, dy = x - px, y - py
            distance = math.hypot(dx, dy)
        if distance > 0.03:
            aim = math.degrees(math.atan2(dy, dx))
            _, problem = await turn_by(self.kit, self.wheels, wrap_deg(aim - heading))
            if problem and problem != "the turn took too long":
                return problem
            _, problem = await roll_by(self.kit, self.wheels, distance * 1000.0, 0.4)
            if problem:
                return problem
        if face_deg is not None:
            _, _, heading = odometer.pose()
            _, problem = await turn_by(self.kit, self.wheels, wrap_deg(face_deg - heading))
            if problem and problem != "the turn took too long":
                return problem
        return None

    async def find(self) -> SeenTag | None:
        tag = await self.look_for_tag(0)
        if tag is not None:
            return tag
        odometer = self.odometer
        if odometer is not None and odometer.usable:
            x, y, _ = odometer.pose()
            if math.hypot(x, y) > NEAR_DOCK_X_M + 0.2:
                problem = await self.drive_to(NEAR_DOCK_X_M, 0.0, 0.0)
                if problem:
                    self.notes.append(f"the drive back towards the charger stopped ({problem})")
            else:
                _, _, heading = odometer.pose()
                facing = math.degrees(math.atan2(y, x))
                await turn_by(self.kit, self.wheels, wrap_deg(facing - heading))
            tag = await self.look_for_tag(SWEEP_DEG)
            if tag is not None:
                return tag
        return await self.look_for_tag(360.0)

    async def run(self) -> tuple[bool, str]:
        kit = self.kit
        if kit.body.telemetry.docked:
            return True, "already on the charger"
        start = kit.pace.now()
        tries = 0
        await leave_dock(kit, self.wheels)
        tag = await self.find()
        if tag is None:
            seen = await self.find_by_print()
            if seen is not None:
                self.notes.append("found the charger by how it looks")
                tag = await self.approach_by_print(seen)
                if tag is None:
                    return await self.by_sight()
        if tag is None:
            far = "" if self.odometer is not None and self.odometer.usable else " and you lost track of where it is"
            return False, f"could not see the charger's tag from here{far}"
        seen_at = kit.pace.now()
        last_x, stuck_since = None, None
        recent: list[DockPose] = []
        committed = False
        while True:
            now = kit.pace.now()
            if kit.body.telemetry.docked:
                await self.wheels.halt()
                return True, "reversed onto the charger"
            if now - start > HOMING_MAX_S:
                return False, "it took too long to line up with the charger"
            reason = self.wheels.why_not()
            if reason:
                await self.wheels.halt()
                return False, reason
            hits = [r for r in self.wheels.reflexes() if r in ("edge", "fault")]
            if hits:
                return False, f"my body stopped ({hits[0]})"
            tag = dock_tag(kit)
            if tag is None:
                await self.wheels.halt()
                if now - seen_at > TAG_LOST_S:
                    tag = await self.look_for_tag(SWEEP_DEG)
                    if tag is None:
                        return False, "lost sight of the charger's tag"
                    seen_at = kit.pace.now()
                await kit.pace.sleep(kit.control_s)
                continue
            seen_at = now
            if tag.score < GOOD_SCORE:
                forward, turn = back_towards(tag)
                await self.wheels.drive(forward, turn, 0.5)
                await kit.pace.sleep(kit.control_s)
                continue
            recent.append(pose_from_tag(tag))
            del recent[:-SMOOTH]
            pose = smoothed(recent)
            if self.odometer is not None:
                self.odometer.relocate(pose.x, pose.y, pose.heading_deg)
            for mark in PRINT_MARKS_M:
                if mark not in self.printed and abs(pose.x - mark) <= 0.08 and abs(pose.y) <= 0.15:
                    await self.print_dock(mark)
            near = pose.x <= LINE_UP_X_M
            if len(recent) < SMOOTH and not committed:
                await self.wheels.halt()
                await kit.pace.sleep(kit.control_s)
                continue
            off = not committed and abs(pose.y) > (ALIGNED_Y_M if near else OFF_LINE_M + 0.25 * max(0.0, pose.x - STAGING_X_M))
            crooked = near and not committed and abs(pose.heading_deg) > ALIGNED_DEG
            if off or crooked:
                tries += 1
                if tries > MAX_TRIES:
                    return False, "could not line up with the charger"
                self.notes.append(f"off the line by {round(pose.y * 1000)} mm at {round(pose.heading_deg)} degrees; lining up again")
                problem = await self.drive_to(STAGING_X_M, 0.0, 0.0)
                if problem:
                    self.notes.append(f"lining up stopped ({problem})")
                seen_at = kit.pace.now()
                last_x, stuck_since = None, None
                recent.clear()
                continue
            if near:
                committed = True
                turn = clamp(math.radians(-pose.heading_deg) * 0.6 + pose.y * 2.0, -0.12, 0.12)
                await self.wheels.drive(-FINAL_POWER, turn, 0.5)
                if last_x is not None and abs(pose.x - last_x) < 0.002:
                    stuck_since = stuck_since or now
                    if now - stuck_since > STUCK_S:
                        tries += 1
                        if tries > MAX_TRIES:
                            return False, "touched the wall but the charger did not connect"
                        self.notes.append("touched the wall without docking; lining up again")
                        await self.drive_to(STAGING_X_M, 0.0, 0.0)
                        last_x, stuck_since = None, None
                        committed = False
                        recent.clear()
                        continue
                else:
                    stuck_since = None
                last_x = pose.x
            else:
                forward, turn = follow_line(pose) if pose.x <= LINE_ZONE_X_M else steer_back(pose)
                await self.wheels.drive(forward, turn, 0.5)
            await kit.pace.sleep(kit.control_s)


class GoHome(Activity):
    kind = "go_home"
    homing = True
    sight = True

    def describe(self) -> str:
        return "heading to the charger"

    def adjust(self, request):
        if request.change in ("enough", "stay"):
            return "Okay, I'll stop here.", None
        return "", None

    async def run(self, kit: Kit) -> Ending:
        if kit.body.telemetry.docked:
            return Ending("done", "you were already on your charger", "")
        if not kit.eyes.available:
            return Ending("no_sight", "you cannot see your charger's tag yet", "I can't see my charger yet. Could someone put me on it?")
        wheels = Wheels(kit, homing=True).open()
        switched = await kit.eyes.use_camera("rear")
        try:
            if not switched:
                return Ending("no_sight", "the rear camera would not start", "I can't look behind me just now. Could someone put me on my charger?")
            await level_head(kit)
            homing = DockHoming(kit, wheels)
            ok, why = await homing.run()
            detail = f" ({'; '.join(homing.notes[-2:])})" if homing.notes else ""
            if ok:
                return Ending("done", f"you {why}{detail}", "Home again.")
            return Ending("failed", f"you could not dock: {why}{detail}", "I can't get onto my charger by myself. Could someone put me on it?")
        finally:
            await wheels.halt()
            wheels.close()
            await kit.eyes.use_camera("front")


class LearnDock(Activity):
    kind = "learn_dock"
    homing = True
    sight = True

    def describe(self) -> str:
        return "taking a good look at the charger"

    async def run(self, kit: Kit) -> Ending:
        printer = getattr(kit.eyes, "dock_print", None)
        if not kit.body.telemetry.docked:
            return Ending("failed", "you were not on your charger", "")
        if printer is None or not kit.eyes.available:
            return Ending("no_sight", "your eyes cannot print the charger", "")
        wheels = Wheels(kit, homing=True).open()
        prints = 0
        ok, why = False, "did not start"
        try:
            if not await kit.eyes.use_camera("rear"):
                return Ending("no_sight", "the rear camera would not start", "")
            await level_head(kit)
            problem = await leave_dock(kit, wheels)
            at = DOCKED_X_M + 0.13
            for mark in sorted(PRINT_MARKS_M):
                if problem:
                    break
                _, problem = await roll_by(kit, wheels, (mark - at) * 1000.0, 0.35)
                at = mark
                moved(kit)
                await kit.pace.sleep(0.4)
                try:
                    vec = await printer()
                except Exception:
                    vec = None
                if vec:
                    kit.dock_print(vec)
                    prints += 1
            homing = DockHoming(kit, wheels)
            ok, why = await homing.run()
        finally:
            await wheels.halt()
            wheels.close()
            await kit.eyes.use_camera("front")
        back = "went back onto it" if ok else f"could not get back on ({why})"
        return Ending("done" if ok else "failed", f"you took {prints} good looks at your charger and {back}", "" if ok else "I can't get back onto my charger by myself. Could someone put me on it?")


class TagDockSeeker:
    def __init__(self, eyes: Eyes, start: Callable[[], bool]):
        self.eyes = eyes
        self.start = start

    async def seek(self) -> DockAttempt:
        if not self.eyes.available:
            return DockAttempt(False, "Pebble cannot see yet, so it cannot find its dock's tag by itself")
        if self.start():
            return DockAttempt(True, "heading for the dock, steering by its tag with the rear camera")
        return DockAttempt(False, "Pebble could not start heading for its dock")
