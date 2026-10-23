import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field

from ..laws import FOLLOWED_NEAR_M
from ..link.protocol import Event, Status
from ..things.words import canonical, matches
from .chart import HOME, Charts
from .drive import Driver
from .geometry import BODY_RADIUS_M, TRACK_M, ahead, body_angle, camera_spot, path_length, wrap
from .grid import Clearance
from .life import LifeWatch, careful_near, remember_careful
from .lead import Seen, place_people
from .walls import lines
from .local import ARRIVE_SLACK_M, Limits, LocalPlanner
from .pose import LANDSCAPE, Pose
from .route import plan
from .senses import Senses
from .stuck import StuckWatch
from .words import line, note

log = logging.getLogger(__name__)

CONTROL_S = 0.1
HISTORY_N = 120
CLEAR_SELF_S = 0.25
SELF_M = 0.09
PEOPLE_TRAIL = 60
PEOPLE_SKIP_S = 1.5
FLOOR_STALE_S = 1.5
SIGHT_EVERY_S = 0.1
CLEAR_RADIUS_M = 1.25
CLEAR_EVERY_S = 0.3
CLEAR_MOVE_M = 0.15
ROOMS_EVERY_S = 2.0
SAVE_EVERY_S = 120.0
PEOPLE_KEEP_S = 0.6
ANIMAL_KEEP_S = 3.0
OTHER_RADIUS_M = 0.42
LEAD_RADIUS_M = 0.3
ANIMAL_GAP_M = 0.8
DOG_GAP_M = 1.2
LOOKAHEAD_M = 2.5
SHORTCUT_M = 3.5
GOAL_SLOW = 0.5
GO_MAX_S = 240.0
REPLAN_S = 2.0
DETOUR_MOVE_M = 0.3
TURN_FIRST_RAD = math.radians(45.0)
GAIN_M = 0.2
NO_GAIN_S = 15.0
BLOCKED_S = 2.0
RECOVER_M = 0.4
BACK_OFF_M = 0.12
BACK_SPEED = 0.05
HELP_WAIT_S = 45.0
NEAR_OTHERS_M = 2.0
RISE_AHEAD_M = 0.45
RISE_SPEED = 0.07
TIGHT_M = 0.24
TIGHT_SPEED = 0.12
SPRINT_CLEAR_M = 0.10
SPRINT_ANGLE = 0.6
SETTLE_STILL_S = 0.9
ANIMAL_SPARE_M = 0.05
ANIMAL_SIDE_RAD = math.radians(70.0)
FRONT_REACH_M = 0.1
STEER_AHEAD_M = 1.5
ANIMAL_WAIT_S = 20.0
LIFE_SLOW = 0.4
LIFE_NOTE_S = 60.0
CAREFUL_SPEED = 0.08
GIVE_WAY_M = 0.2
STAND_SPARE_M = 0.04
STAND_STEP_M = 0.05
GIVE_WAY_BEHIND = (0.15, 0.25, 0.32)
STEER_LOOK_S = 0.6
SOFTEN_M = 0.6
SQUARE_SCORE = 0.6
SQUARE_NEAR_M = 0.5
TURN_PROGRESS_RAD = math.radians(2.0)
TURN_STUCK_S = 1.0
WRIGGLE_SPEED = 0.08
WRIGGLE_S = 1.5
WRIGGLE_M = 0.06
SPIN_CHANGE = 0.01
SPIN_SHIFT_DEG = 0.3
SPIN_S = 0.8
WIGGLE_W = 1.4
WIGGLE_STEP_S = 0.15
WIGGLE_RAD = math.radians(18.0)
FURNITURE = frozenset({"chair", "armchair", "couch", "table", "dining table", "desk", "bed", "fridge", "oven", "microwave", "tv", "toilet", "sink", "bench", "potted plant", "plant", "plant pot", "cabinet", "bookcase", "wardrobe", "sofa"})


@dataclass(frozen=True)
class Trip:
    ok: bool
    how: str
    text: str
    travelled_m: float = 0.0


@dataclass(frozen=True)
class Lead:
    person_id: str | None
    name: str = ""
    track: int | None = None


@dataclass
class FollowControl:
    gap_m: float = 1.0
    top: float | None = None


@dataclass
class Stats:
    stuck: int = 0
    recovered: int = 0
    bumps: int = 0
    edges: int = 0
    asked_help: int = 0
    replans: int = 0
    shortcuts: int = 0
    glass: int = 0
    squared: int = 0
    life_accidents: int = 0
    said: list = field(default_factory=list)


class _Pace:
    def __init__(self, monotonic=time.monotonic):
        self.monotonic = monotonic

    def now(self) -> float:
        return self.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(max(0.0, seconds))


def _hazard(label: str) -> bool:
    from ..activities.hazards import hazard

    return hazard(label)


def _someone_low(sight) -> bool:
    from ..activities.hazards import someone_low

    return someone_low(sight)


def _floor_reach(eyes) -> float:
    status = getattr(eyes, "status", None)
    if status is not None:
        try:
            reach = ((status() or {}).get("floor") or {}).get("reach_m")
            if reach:
                return float(reach)
        except Exception:
            pass
    return getattr(eyes, "floor_reach_m", 2.0)


class Navigator:
    def __init__(self, body, eyes=None, store=None, pace=None, gyro=None, accel=None, sprint_power: float = 1000.0, now_text=lambda: "", edge_mm: float = 75.0, wall=None, tap=None):
        self.body = body
        self.wall = wall
        self.tap = tap
        self.eyes = eyes
        self.store = store
        self.pace = pace or _Pace()
        self.pose = Pose.for_body(body, gyro=gyro, accel=accel, monotonic=self.pace.now, prior=LANDSCAPE, edge_mm=edge_mm)
        self.pose.listeners.append(self._pose_said)
        self.charts = Charts(store, now_text)
        self.senses = Senses(self.charts.home().grid, _hazard, floor_reach_m=_floor_reach(eyes))
        self.driver = Driver(body, sprint_power)
        self.local = LocalPlanner()
        self.stats = Stats()
        self.people: list[Seen] = []
        self.people_at = -math.inf
        self.animals: list[tuple[float, float, float, str]] = []
        self.life = LifeWatch()
        self.urgent = lambda: False
        self.keep_out = lambda: []
        self.on_life = lambda event: None
        self.life_noted: dict = {}
        self.sight = None
        self.sight_at = -math.inf
        self.bumps: list[tuple[float, str]] = []
        self.edges: list[float] = []
        self.rises_at = -math.inf
        self.trail: list[tuple[float, float]] = []
        self.notes: list[str] = []
        self._clear: Clearance | None = None
        self._cleared_at = -math.inf
        self.seen_people: deque = deque(maxlen=PEOPLE_TRAIL)
        self.history: deque = deque(maxlen=HISTORY_N)
        self.floor_at = None
        self.moving_told: bool | None = None
        self.motion_still_since: float | None = None
        self._clear_key = None
        self._rooms_at = -math.inf
        self._saved_at = self.pace.now()
        self.following = None
        self.running = False
        self._detour_path = None
        self._detour_at = -math.inf
        self._gave_from = None
        self._detour_goal = (0.0, 0.0)
        if body.telemetry.docked:
            self.charts.use(self.charts.home())

    @classmethod
    def for_life(cls, body, eyes=None, store=None, pace=None, now_text=lambda: "", wall=None, **kwargs) -> "Navigator":
        from .phone import motion_feeds

        edge = 75.0
        try:
            edge = float((body.profile.firmware_settings or {}).get("edge", 75.0))
        except (TypeError, ValueError):
            pass
        gyro, accel, tap = motion_feeds(body.profile)
        return cls(body, eyes, store, pace, gyro, accel, now_text=now_text, edge_mm=edge, wall=wall, tap=tap, **kwargs)

    @property
    def chart(self):
        if self.charts.current is None:
            return self.charts.home()
        return self.charts.current

    def _pose_said(self, what: str) -> None:
        if what == "home":
            self._use(self.charts.home())
        elif what == "carried":
            self.notes.append(note("carried"))

    def _use(self, chart) -> None:
        self.charts.use(chart)
        self.senses.grid = chart.grid
        self._clear = None

    def ensure_frame(self) -> bool:
        if self.pose.cpm <= 0:
            return False
        if self.pose.frame == HOME:
            if self.charts.current is not self.charts.home():
                self._use(self.charts.home())
            return True
        if self.pose.frame is not None and self.pose.frame in self.charts.charts:
            if self.charts.current is not self.charts.charts[self.pose.frame]:
                self._use(self.charts.charts[self.pose.frame])
            return True
        chart = self.charts.visit()
        self._use(chart)
        self.pose.start_visit(chart.id)
        chart.remember_spot("start", 0.0, 0.0, "start")
        return True

    def felt(self, kind: str) -> None:
        self.pose.felt(kind)

    def take_notes(self) -> list[str]:
        out, self.notes = self.notes, []
        return out

    async def run(self) -> None:
        self.running = True
        queue = self.body.link.subscribe((Status,))
        events = self.body.subscribe_events()
        if self.tap is not None:
            self.tap.start()
        try:
            while True:
                status = await queue.get()
                self.on_status(status)
                while not events.empty():
                    message = events.get_nowait()
                    if isinstance(message, Event):
                        self.on_event(message)
                now = self.pace.now()
                if now - self.sight_at >= SIGHT_EVERY_S:
                    self.sight_at = now
                    self.on_sight(now)
                if now - self._rooms_at >= ROOMS_EVERY_S:
                    self._rooms_at = now
                    self.chart.name_rooms()
                    self.chart.grid.forget(now)
                if self.store is not None and now - self._saved_at >= SAVE_EVERY_S:
                    self._saved_at = now
                    self.save()
        finally:
            self.running = False
            self.body.link.unsubscribe(queue)
            self.body.unsubscribe_events(events)
            if self.tap is not None:
                self.tap.stop()

    def pose_at(self, at: float) -> tuple[float, float, float]:
        if not self.history:
            return self.pose.pose_rad()
        best = min(self.history, key=lambda item: abs(item[0] - at))
        return best[1], best[2], best[3]

    def _tell_moving(self) -> None:
        moving = self.driver.sent != (0, 0)
        if moving != self.moving_told:
            self.moving_told = moving
            told = getattr(self.eyes, "set_moving", None)
            if told is not None:
                try:
                    told(moving)
                except Exception:
                    log.exception("nav: the eyes would not take set_moving")

    def scan_floor(self) -> None:
        ask = getattr(self.eyes, "scan_floor", None)
        if ask is not None:
            try:
                ask()
            except Exception:
                log.exception("nav: the eyes would not scan the floor")

    def spinning(self) -> bool:
        motion = getattr(self.eyes, "motion", None)
        if motion is None or self.driver.sent == (0, 0):
            self.motion_still_since = None
            return False
        try:
            reading = motion()
        except Exception:
            return False
        if not reading or reading.get("sure", 0.0) < 0.3:
            return False
        still = reading.get("change", 1.0) < SPIN_CHANGE and abs((reading.get("shift_deg") or (0.0, 0.0))[0]) < SPIN_SHIFT_DEG
        now = self.pace.now()
        if not still:
            self.motion_still_since = None
            return False
        if self.motion_still_since is None:
            self.motion_still_since = now
        return now - self.motion_still_since >= SPIN_S

    def slipping(self) -> bool:
        return self.pose.slipping or self.spinning()

    def on_status(self, status: Status) -> None:
        self.pose.update(status)
        self._tell_moving()
        if self.pose.carried or status.dock == 1 or not self.pose.local_usable:
            return
        x, y, th = self.pose.pose_rad()
        self.history.append((self.pace.now(), x, y, th))
        if self.pace.now() - self._cleared_at >= CLEAR_SELF_S:
            self._cleared_at = self.pace.now()
            self.chart.grid.clear(*ahead(x, y, th, 0.01), SELF_M)
        self.senses.tof(status.front_mm, x, y, th)
        if self.senses.down(status.down_mm, x, y, th, self.pose.edge_mm):
            self.rises_at = self.pace.now()
        self.chart.moved(x, y, th)

    def on_event(self, event: Event) -> None:
        if not self.pose.local_usable or self.pose.carried:
            return
        x, y, th = self.pose.pose_rad()
        now = self.pace.now()
        if event.name == "edge":
            self.senses.edge(x, y, th)
            self.edges.append(now)
            self.stats.edges += 1
        elif event.name == "bump":
            side = event.args[0] if event.args else "B"
            status = self.body.telemetry.status
            front = status.front_mm if status else None
            unseen = (front is None or front < 0 or front > 250) and self.senses.looked_clear(x, y, th) and not self.senses.wall_near(side, x, y, th)
            self.senses.bump(side, x, y, th, now, unseen)
            if unseen:
                self.stats.glass += 1
                self.notes.append(note("glass"))
            self.bumps.append((now, side))
            self.stats.bumps += 1
            del self.bumps[:-20]
            plant = self.life.bumped(x, y, th, now)
            if plant is not None:
                self._life_accident(plant, x, y, "bumped")

    def on_sight(self, now: float) -> None:
        eyes = self.eyes
        if eyes is None or not getattr(eyes, "available", False):
            return
        sight = eyes.latest(0.5)
        if sight is None:
            return
        self.sight = sight
        if not self.pose.local_usable or self.pose.carried or self.body.telemetry.docked:
            return
        x, y, th = self.pose.pose_rad()
        status = self.body.telemetry.status
        front = status.front_mm if status else None
        self.people = place_people(sight, x, y, th, self.body.telemetry.tilt, front)
        self.people_at = now
        for seen in self.people:
            self.seen_people.append((now, seen.x, seen.y))
        floor_at = getattr(sight, "floor_at", None)
        if sight.floor and floor_at != self.floor_at:
            self.floor_at = floor_at
            fx, fy, fth = x, y, th
            if floor_at is not None:
                offset = (self.wall() - now) if self.wall is not None else 0.0
                taken = floor_at - offset
                if now - taken <= FLOOR_STALE_S:
                    fx, fy, fth = self.pose_at(taken)
                else:
                    fx = None
            if fx is not None:
                skip = [(px, py) for at, px, py in self.seen_people if now - at <= PEOPLE_SKIP_S]
                turn = self._square_up(sight, fx, fy, fth, skip)
                if turn:
                    self.pose.nudge_heading(turn)
                    fth = wrap(fth + turn)
                self.senses.floor(sight, fx, fy, fth, skip)
        following = self.following
        exempt = following.exempt if following is not None else ""
        self.senses.floor_things(sight, x, y, th, now, lambda label: bool(exempt) and (matches(exempt, label) or matches(label, exempt)))
        self.animals = [a for a in self.animals if now - a[2] <= ANIMAL_KEEP_S]
        cx, cy, _ = camera_spot(x, y, th, sight.camera)
        self.life.saw(sight, now, cx, cy, th, self.chart.grid)
        for spot in self.life.passed(x, y, now):
            self._life_accident(spot, x, y, "went over")
        for thing in sight.things:
            if thing.floor_m is None or thing.floor_bearing_deg is None:
                continue
            angle = th + body_angle(thing.floor_bearing_deg, sight.camera)
            px, py = cx + thing.floor_m * math.cos(angle), cy + thing.floor_m * math.sin(angle)
            if self.life.kind_of(thing) is not None:
                if canonical(thing.label) in FURNITURE or thing.label in FURNITURE:
                    self.chart.saw(thing.label, px, py)
                continue
            if thing.animal:
                self.animals.append((px, py, now, canonical(thing.label)))
            elif canonical(thing.label) in FURNITURE or thing.label in FURNITURE:
                self.chart.saw(thing.label, px, py)

    def _square_up(self, sight, x: float, y: float, th: float, skip) -> float | None:
        cx, cy, _ = camera_spot(x, y, th, sight.camera)
        points = []
        for ray in sorted(sight.floor, key=lambda r: r.bearing_deg):
            if ray.distance_m >= self.senses.floor_open_m or ray.distance_m > self.senses.floor_reach_m or ray.score < SQUARE_SCORE or ray.distance_m < SQUARE_NEAR_M:
                continue
            angle = th + body_angle(ray.bearing_deg, sight.camera)
            px, py = cx + ray.distance_m * math.cos(angle), cy + ray.distance_m * math.sin(angle)
            if any(math.hypot(px - sx, py - sy) < 0.5 for sx, sy in skip):
                continue
            points.append((px, py))
        turn = self.chart.axis.offer(lines(points), self.pose.drift_m())
        if turn:
            self.stats.squared += 1
        return turn

    def last_person(self, max_age: float) -> tuple[float, float] | None:
        if not self.seen_people:
            return None
        at, x, y = self.seen_people[-1]
        return (x, y) if self.pace.now() - at <= max_age else None

    def fresh_people(self, max_age: float = PEOPLE_KEEP_S) -> list[Seen]:
        if self.pace.now() - self.people_at > max_age:
            return []
        return list(self.people)

    def obstacles(self, lead_track: int | None = None, exempt: str = "") -> list[tuple[float, float, float]]:
        out = []
        for seen in self.fresh_people():
            if lead_track is not None and seen.track == lead_track:
                out.append((seen.x, seen.y, LEAD_RADIUS_M))
            else:
                out.append((seen.x, seen.y, OTHER_RADIUS_M))
        for px, py, _, label in self.animals:
            if exempt and matches(exempt, label):
                continue
            gap = DOG_GAP_M if label in ("dog", "puppy") else ANIMAL_GAP_M
            out.append((px, py, max(0.2, gap - BODY_RADIUS_M)))
        out.extend(self.life.obstacles(exempt, self._urgent()))
        try:
            out.extend(self.keep_out())
        except Exception:
            log.exception("nav: the private rooms could not be kept out of")
        return out

    def _urgent(self) -> bool:
        try:
            return bool(self.urgent())
        except Exception:
            return False

    def life_guard(self, exempt: str = "") -> tuple[str | None, str | None]:
        if not self.pose.local_usable:
            return None, None
        x, y, th = self.pose.pose_rad()
        return self.life.guard(x, y, th, self._urgent(), exempt)

    def _life_slowed(self, kit, label: str | None) -> None:
        now = self.pace.now()
        if label and now - self.life_noted.get(label, -math.inf) >= LIFE_NOTE_S:
            self.life_noted[label] = now
            self._note(kit, note("life", where=label))

    def _life_accident(self, spot, x: float, y: float, how: str) -> None:
        self.stats.life_accidents += 1
        remember_careful(self.chart.careful, spot.x, spot.y, spot.label)
        self.charts.dirty = True
        text = note("plant_bumped" if how == "bumped" else "life_accident", where=spot.label)
        self.notes.append(text)
        try:
            self.on_life({"how": how, "label": spot.label, "kind": spot.kind, "x": round(spot.x, 2), "y": round(spot.y, 2), "note": text})
        except Exception:
            log.exception("nav: could not report what happened to the %s", spot.label)

    def animal_guard(self) -> tuple[str | None, str | None]:
        from ..activities.seeing import animal_gap, animal_slow, animals_ahead

        slow = block = None
        sight = self.sight
        if sight is not None and self.pace.now() - self.sight_at <= 1.0:
            for thing, gap in animals_ahead(sight, self.body.telemetry.tilt):
                label = canonical(thing.label)
                if gap < animal_slow(label):
                    slow = slow or label
                if gap < animal_gap(label) + ANIMAL_SPARE_M:
                    block = block or label
        x, y, th = self.pose.pose_rad()
        side = self.animal_side()
        for px, py, _, label in self.animals:
            gap = math.hypot(px - x, py - y) - FRONT_REACH_M
            if abs(wrap(math.atan2(py - y, px - x) - th)) > side:
                continue
            if gap < animal_slow(label):
                slow = slow or label
            if gap < animal_gap(label) + ANIMAL_SPARE_M:
                block = block or label
        return slow, block

    def animal_side(self) -> float:
        from ..activities.seeing import camera_fov_deg, view_cone_deg

        return max(ANIMAL_SIDE_RAD, math.radians(view_cone_deg(camera_fov_deg(self.eyes, getattr(self.body, "profile", None)))))

    def too_close(self) -> bool:
        from ..activities.seeing import animal_gap

        x, y, th = self.pose.pose_rad()
        side = self.animal_side()
        for px, py, _, label in self.animals:
            if abs(wrap(math.atan2(py - y, px - x) - th)) > side:
                continue
            if math.hypot(px - x, py - y) - FRONT_REACH_M < animal_gap(label):
                return True
        return False

    def give_way(self, block: str | None) -> float:
        if not block or not self.too_close():
            self._gave_from = None
            return 0.0
        x, y, th = self.pose.pose_rad()
        if self._gave_from is None:
            self._gave_from = (x, y)
        if math.hypot(x - self._gave_from[0], y - self._gave_from[1]) >= GIVE_WAY_M:
            return 0.0
        grid = self.chart.grid
        for d in GIVE_WAY_BEHIND:
            if not grid.free_at(*ahead(x, y, th, -d)):
                return 0.0
        return -BACK_SPEED

    def in_the_way(self, lead_track: int | None = None, reach: float = 1.3) -> str | None:
        x, y, th = self.pose.pose_rad()
        for seen in self.fresh_people():
            if lead_track is not None and seen.track == lead_track:
                continue
            gap = math.hypot(seen.x - x, seen.y - y)
            if gap <= reach and abs(wrap(math.atan2(seen.y - y, seen.x - x) - th)) <= math.radians(80.0):
                return "someone"
        for px, py, _, label in self.animals:
            gap = math.hypot(px - x, py - y)
            if gap <= reach + 0.5 and abs(wrap(math.atan2(py - y, px - x) - th)) <= math.radians(80.0):
                return label
        return None

    def clearance(self, extra: list[tuple[float, float, float]], force: bool = False) -> Clearance:
        x, y, _ = self.pose.pose_rad()
        now = self.pace.now()
        key = self._clear_key
        stale = (
            force
            or self._clear is None
            or key is None
            or now - key[0] >= CLEAR_EVERY_S
            or math.hypot(x - key[1], y - key[2]) >= CLEAR_MOVE_M
            or self.chart.grid.version != key[3]
            or extra != key[4]
        )
        if stale:
            self._clear = Clearance(self.chart.grid, x, y, CLEAR_RADIUS_M, extra, now)
            self._clear_key = (now, x, y, self.chart.grid.version, list(extra))
        return self._clear

    def others_near(self, kit, lead: Lead | None) -> bool:
        if lead is not None:
            near = bool(getattr(kit, "others_near", lambda pid: kit.people_near())(lead.person_id))
        else:
            near = bool(kit.people_near())
        if near:
            return True
        x, y, _ = self.pose.pose_rad()
        lead_track = self.lead_track(lead)
        for seen in self.fresh_people():
            if lead is not None and seen.track == lead_track:
                continue
            if math.hypot(seen.x - x, seen.y - y) <= NEAR_OTHERS_M:
                return True
        return any(math.hypot(a[0] - x, a[1] - y) <= NEAR_OTHERS_M * 1.5 for a in self.animals)

    def _followed(self, lead: Lead | None):
        follower = self.following
        if lead is None or follower is None or follower.lead is not lead:
            return None
        return follower

    def lead_track(self, lead: Lead | None) -> int | None:
        follower = self._followed(lead)
        if follower is not None and follower.lock.track is not None:
            return follower.lock.track
        return lead.track if lead is not None else None

    def lead_near(self, lead: Lead | None) -> bool:
        follower = self._followed(lead)
        if follower is None:
            return False
        if follower.lead_within(FOLLOWED_NEAR_M):
            return True
        x, y, _ = self.pose.pose_rad()
        track = self.lead_track(lead)
        return any(seen.track == track and math.hypot(seen.x - x, seen.y - y) <= FOLLOWED_NEAR_M for seen in self.fresh_people())

    def rise_ahead(self) -> bool:
        if self.pace.now() - self.rises_at < 1.0:
            return True
        x, y, th = self.pose.pose_rad()
        grid = self.chart.grid
        if not grid.rises:
            return False
        for d in (0.15, 0.25, 0.35, RISE_AHEAD_M):
            if grid.cell(*ahead(x, y, th, d)) in grid.rises:
                return True
        return False

    def threshold_normal(self) -> float | None:
        x, y, th = self.pose.pose_rad()
        grid = self.chart.grid
        px, py = ahead(x, y, th, 0.3)
        cells = [grid.centre(*c) for c in grid.rises if math.hypot(grid.centre(*c)[0] - px, grid.centre(*c)[1] - py) <= 0.5]
        if len(cells) < 3:
            return None
        mx = sum(c[0] for c in cells) / len(cells)
        my = sum(c[1] for c in cells) / len(cells)
        sxx = sum((c[0] - mx) ** 2 for c in cells)
        syy = sum((c[1] - my) ** 2 for c in cells)
        sxy = sum((c[0] - mx) * (c[1] - my) for c in cells)
        along = 0.5 * math.atan2(2 * sxy, sxx - syy)
        normal = along + math.pi / 2.0
        if math.cos(wrap(normal - th)) < 0:
            normal += math.pi
        return wrap(normal)

    def speed_cap(self, kit, lead: Lead | None, sprint_ok: bool) -> float:
        others = self.others_near(kit, lead)
        near = self.lead_near(lead) or others
        creep = _someone_low(self.sight)
        cap = self.driver.wheel_cap(near, sprint_ok, creep)
        if self.pose.local_usable and careful_near(self.chart.careful, *self.pose.pose_rad()[:2]) is not None:
            cap = min(cap, CAREFUL_SPEED)
        return cap

    def line_clear(self, a: tuple[float, float], b: tuple[float, float], clearance: Clearance, room: float = BODY_RADIUS_M + 0.02, near: list[tuple[float, float]] | None = None, near_m: float = 0.6) -> bool:
        grid = self.chart.grid
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 1e-6:
            return True
        steps = max(1, int(length / 0.05))
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        for i in range(1, steps + 1):
            t = i / steps
            px, py = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            if clearance.inside(px, py, 0.1):
                if clearance.at(px, py) < room:
                    return False
            else:
                for side in (0.0, room, -room):
                    if grid.occupied_at(px - uy * side, py + ux * side):
                        return False
            if near is not None and not grid.free_at(px, py):
                if not any(abs(px - q[0]) <= near_m and abs(py - q[1]) <= near_m and math.hypot(px - q[0], py - q[1]) <= near_m for q in near):
                    return False
        return True

    async def turn_to(self, kit, wheels, heading: float, tolerance: float = 0.1, timeout_s: float = 5.0, lead: Lead | None = None) -> str | None:
        start = self.pace.now()
        moved_at, last = start, self.pose.pose_rad()[2]
        try:
            while True:
                reason = wheels.why_not()
                if reason:
                    return reason
                now = self.pace.now()
                if wheels.held():
                    await self.driver.halt()
                    await self.pace.sleep(CONTROL_S)
                    if now - start > timeout_s:
                        return "held"
                    moved_at = now
                    continue
                _, _, th = self.pose.pose_rad()
                error = wrap(heading - th)
                if abs(error) <= tolerance:
                    return None
                if now - start > timeout_s:
                    return "the turn took too long"
                if abs(wrap(th - last)) > TURN_PROGRESS_RAD:
                    moved_at, last = now, th
                elif now - moved_at > TURN_STUCK_S:
                    return "stuck"
                w = max(-2.2, min(2.2, 2.5 * error))
                if abs(w) < 0.9:
                    w = math.copysign(0.9, w)
                await self.driver.send(0.0, w, self.speed_cap(kit, lead, False), now)
                await self.pace.sleep(CONTROL_S)
        finally:
            await self.driver.halt()

    async def turn_free(self, kit, wheels, heading: float, lead: Lead | None = None) -> str | None:
        problem = await self.turn_to(kit, wheels, heading, lead=lead)
        if problem != "stuck":
            return problem
        self.stats.stuck += 1
        if await self.wriggle(kit, wheels):
            self.stats.recovered += 1
            return await self.turn_to(kit, wheels, heading, lead=lead)
        return problem

    async def wriggle(self, kit, wheels) -> bool:
        x0, y0, _ = self.pose.pose_rad()
        status = self.body.telemetry.status
        front = status.front_mm if status else None
        tries = (WRIGGLE_SPEED, -WRIGGLE_SPEED) if front is None or front < 0 or front > 150 else (-WRIGGLE_SPEED,)
        for speed in tries:
            start = self.pace.now()
            try:
                while self.pace.now() - start < WRIGGLE_S:
                    if wheels.why_not():
                        return False
                    x, y, _ = self.pose.pose_rad()
                    if math.hypot(x - x0, y - y0) >= WRIGGLE_M:
                        return True
                    await self.driver.send(speed, 0.0, abs(speed), self.pace.now())
                    await self.pace.sleep(CONTROL_S)
            finally:
                await self.driver.halt()
            x, y, _ = self.pose.pose_rad()
            if math.hypot(x - x0, y - y0) >= WRIGGLE_M * 0.5:
                return True
        return False

    async def quick_wiggle(self, kit, wheels, lead: Lead | None = None) -> None:
        if self.pose.gyro is None or self.pose.axis is not None or kit.body.telemetry.docked or wheels.why_not():
            return
        cap = self.speed_cap(kit, lead, False)
        for w in (WIGGLE_W, -WIGGLE_W, -WIGGLE_W, WIGGLE_W):
            await self.driver.send(0.0, w, cap, self.pace.now())
            await self.pace.sleep(WIGGLE_STEP_S)
            if self.pose.axis is not None:
                break
        await self.driver.halt()

    async def back_off(self, kit, wheels, metres: float = BACK_OFF_M) -> float:
        x0, y0, _ = self.pose.pose_rad()
        start = self.pace.now()
        try:
            while self.pace.now() - start < metres / BACK_SPEED + 1.5:
                if wheels.why_not():
                    break
                x, y, _ = self.pose.pose_rad()
                if math.hypot(x - x0, y - y0) >= metres:
                    break
                await self.driver.send(-BACK_SPEED, 0.0, BACK_SPEED, self.pace.now())
                await self.pace.sleep(CONTROL_S)
        finally:
            await self.driver.halt()
        x, y, _ = self.pose.pose_rad()
        return math.hypot(x - x0, y - y0)

    def blocked_side(self) -> float:
        now = self.pace.now()
        recent = [side for at, side in self.bumps if now - at <= 3.0]
        if recent:
            return 1.0 if recent[-1] == "L" else (-1.0 if recent[-1] == "R" else 0.0)
        x, y, th = self.pose.pose_rad()
        clear = self.clearance([], force=False)
        left = clear.at(*ahead(x, y, th, 0.15, 0.12))
        right = clear.at(*ahead(x, y, th, 0.15, -0.12))
        return 1.0 if left < right else -1.0

    def where_stuck(self) -> str:
        x, y, th = self.pose.pose_rad()
        best = None
        for kind, spots in self.chart.seen.items():
            for spot in spots:
                gap = math.hypot(spot[0] - x, spot[1] - y)
                if gap <= 1.2 and (best is None or gap < best[0]):
                    best = (gap, kind)
        sight = self.sight
        if sight is not None:
            for thing in sight.things:
                if thing.floor_m is not None and thing.floor_m <= 0.8 and not thing.animal:
                    if best is None or thing.floor_m < best[0]:
                        best = (thing.floor_m, canonical(thing.label))
        if best is None:
            return ""
        return f"by the {best[1]}"

    async def escape(self, kit, wheels, level: int, say, lead: Lead | None = None) -> str:
        if level == 0:
            self.stats.stuck += 1
            moved = await self.back_off(kit, wheels)
            if moved < 0.03:
                await self.wriggle(kit, wheels)
            return "backed"
        _, _, th = self.pose.pose_rad()
        side = self.blocked_side()
        if level == 1:
            x, y, _ = self.pose.pose_rad()
            self.chart.grid.soften(x, y, SOFTEN_M)
            self._clear = None
            await self.back_off(kit, wheels, 0.06)
            await self.turn_to(kit, wheels, wrap(th - side * math.radians(40.0)), lead=lead)
            return "turned"
        if level == 2:
            await self.turn_to(kit, wheels, wrap(th + side * math.radians(80.0)), lead=lead)
            return "other_side"
        if level in (3, 4):
            if level == 4:
                await self.back_off(kit, wheels, 0.2)
            self.stats.replans += 1
            return "replan"
        self.stats.asked_help += 1
        where = self.where_stuck()
        text = line("stuck", where=where) if where else line("stuck_plain")
        say(text)
        self.stats.said.append(text)
        self.notes.append(note("stuck", where=where or "somewhere"))
        return "help"

    def carrot_on(self, points: list[tuple[float, float]], clearance: Clearance, lookahead: float = LOOKAHEAD_M, near: list | None = None, shortcut: float = SHORTCUT_M) -> tuple[tuple[float, float], int]:
        x, y, _ = self.pose.pose_rad()
        best, best_index = points[0], 0
        travelled = math.hypot(points[0][0] - x, points[0][1] - y)
        for index, point in enumerate(points):
            if index > 0:
                travelled += math.hypot(point[0] - points[index - 1][0], point[1] - points[index - 1][1])
            if travelled > lookahead and index > 0:
                break
            if self.line_clear((x, y), point, clearance, near=near):
                best, best_index = point, index
        for index in range(len(points) - 1, best_index, -1):
            point = points[index]
            if math.hypot(point[0] - x, point[1] - y) > shortcut:
                continue
            if self.line_clear((x, y), point, clearance, near=near):
                return point, index
        return best, best_index

    def point_at(self, angle_deg: float, metres: float) -> tuple[float, float] | None:
        if not self.pose.local_usable and not self.ensure_frame():
            return None
        x, y, th = self.pose.pose_rad()
        angle = th + math.radians(angle_deg)
        return x + metres * math.cos(angle), y + metres * math.sin(angle)

    async def drive(self, kit, wheels, forward: float, turn: float, top: float = 1.0, exempt: str = "", lead: Lead | None = None, goal: tuple[float, float] | None = None) -> str | None:
        reason = wheels.why_not()
        if reason:
            await self.driver.halt()
            return reason
        if wheels.held():
            await self.driver.halt()
            return None
        if not self.pose.local_usable:
            self.ensure_frame()
        if goal is not None and self.pose.local_usable:
            await self._head_for(kit, goal, top, exempt, lead)
            return None
        power = self.body.profile.max_power
        limit = max(0.0, min(top, 1.0))
        left, right = forward - turn, forward + turn
        biggest = max(abs(left), abs(right))
        if biggest > limit > 0:
            left, right = left * limit / biggest, right * limit / biggest
        vl = math.copysign(self.driver.speed_of(left * power), left)
        vr = math.copysign(self.driver.speed_of(right * power), right)
        v, w = (vl + vr) / 2.0, (vr - vl) / TRACK_M
        cap = self.speed_cap(kit, lead, False)
        if self.rise_ahead():
            v = min(v, RISE_SPEED)
        slow, block = self.animal_guard()
        back = self.give_way(block)
        if back:
            await self.driver.send(back, 0.0, cap, self.pace.now())
            return None
        if block:
            v = min(v, 0.0)
        elif slow:
            v = min(v, cap * 0.5)
        crawl, stop = self.life_guard(exempt)
        if stop:
            v = min(v, 0.0)
        elif crawl:
            v = min(v, cap * LIFE_SLOW)
        self._life_slowed(kit, crawl or stop)
        lead_track = lead.track if lead is not None else None
        clearance = self.clearance(self.obstacles(lead_track, exempt))
        v, w = self.steer(clearance, v, w, cap)
        await self.driver.send(v, w, cap, self.pace.now())
        return None

    async def _head_for(self, kit, goal: tuple[float, float], top: float, exempt: str, lead: Lead | None) -> None:
        now = self.pace.now()
        x, y, th = self.pose.pose_rad()
        left = math.hypot(goal[0] - x, goal[1] - y)
        lead_track = lead.track if lead is not None else None
        clearance = self.clearance(self.obstacles(lead_track, exempt))
        carrot = goal
        if not self.line_clear((x, y), goal, clearance):
            carrot = self._detour(goal, clearance, now)
        else:
            self._detour_path = None
        sprint_ok = self._straight(carrot, clearance)
        cap = self.speed_cap(kit, lead, sprint_ok)
        v_max = min(cap, self.driver.speed_of(max(0.0, min(top, 1.0)) * self.body.profile.max_power))
        v_max = min(v_max, math.sqrt(2.0 * GOAL_SLOW * left) + 0.03)
        if self.rise_ahead():
            v_max = min(v_max, RISE_SPEED)
        if self.local.here(clearance, x, y, th) < TIGHT_M:
            v_max = min(v_max, TIGHT_SPEED)
        slow, block = self.animal_guard()
        back = self.give_way(block)
        if back:
            await self.driver.send(back, 0.0, cap, now)
            return
        if block:
            v_max = 0.0
        elif slow:
            v_max = min(v_max, cap * 0.5)
        crawl, stop = self.life_guard(exempt)
        if stop:
            v_max = 0.0
        elif crawl:
            v_max = min(v_max, cap * LIFE_SLOW)
        self._life_slowed(kit, crawl or stop)
        if abs(wrap(math.atan2(carrot[1] - y, carrot[0] - x) - th)) > TURN_FIRST_RAD:
            v_max = 0.0
        choice = self.local.choose(clearance, x, y, th, self.driver.v, self.driver.w, carrot, Limits(v_max, cap))
        if choice.blocked:
            self._detour_at = -math.inf
            await self.driver.send(0.0, 0.0, cap, now)
            return
        await self.driver.send(choice.v, choice.w, cap, now)

    def _detour(self, goal: tuple[float, float], clearance: Clearance, now: float) -> tuple[float, float]:
        x, y, _ = self.pose.pose_rad()
        path = self._detour_path
        if path is None or now - self._detour_at >= REPLAN_S or math.hypot(goal[0] - self._detour_goal[0], goal[1] - self._detour_goal[1]) > DETOUR_MOVE_M:
            path = plan(self.chart.grid, (x, y), goal, now)
            self._detour_path, self._detour_at, self._detour_goal = path, now, goal
        if not path:
            return goal
        while len(path) > 1 and math.hypot(path[0][0] - x, path[0][1] - y) < 0.2:
            path.pop(0)
        carrot, _ = self.carrot_on(path, clearance)
        return carrot

    def steer(self, clearance: Clearance, v: float, w: float, cap: float) -> tuple[float, float]:
        safe_v, safe_w = self.safe(clearance, v, w, cap)
        if v <= 0.02 or (abs(safe_v - v) < 1e-6 and abs(safe_w - w) < 1e-6):
            return safe_v, safe_w
        x, y, th = self.pose.pose_rad()
        aim = th + w * STEER_LOOK_S
        goal = (x + STEER_AHEAD_M * math.cos(aim), y + STEER_AHEAD_M * math.sin(aim))
        choice = self.local.choose(clearance, x, y, th, self.driver.v, self.driver.w, goal, Limits(min(v, cap), cap))
        if choice.blocked:
            return 0.0, safe_w
        return choice.v, choice.w

    def safe(self, clearance: Clearance, v: float, w: float, cap: float) -> tuple[float, float]:
        x, y, th = self.pose.pose_rad()
        local = self.local

        def ok(vv, ww):
            free, _ = local.free_along(clearance, x, y, th, vv, ww, 1.2)
            if free == math.inf:
                return True
            room = max(0.0, free - 0.03)
            return abs(vv) * 0.2 + vv * vv / 1.0 <= room and abs(vv) <= 0.04 + 0.6 * room

        if v <= 0.0 or ok(v, w):
            return v, w
        best = None
        for scale in (0.75, 0.5, 0.3, 0.15):
            for bend in (0.0, 0.6, -0.6, 1.2, -1.2, 1.8, -1.8):
                vv, ww = v * scale, w + bend
                if ok(vv, ww):
                    score = abs(vv - v) * 2.0 + abs(ww - w) * 0.3
                    if best is None or score < best[0]:
                        best = (score, vv, ww)
            if best is not None:
                break
        if best is None:
            return 0.0, w
        return best[1], best[2]

    def _roomy(self, x: float, y: float, now: float) -> bool:
        grid = self.chart.grid
        return not any(grid.blocked(ix, iy, now) for ix, iy in grid._disc(x, y, BODY_RADIUS_M + STAND_SPARE_M))

    def standable(self, x: float, y: float, reach: float, now: float) -> tuple[float, float]:
        grid = self.chart.grid
        px, py, _ = self.pose.pose_rad()
        far = math.hypot(x - px, y - py)
        if far < 1e-6:
            return x, y
        ux, uy = (px - x) / far, (py - y) / far
        hit = not self._roomy(x, y, now)
        for i in range(1, int(min(reach, far) / STAND_STEP_M) + 1):
            qx, qy = x + ux * STAND_STEP_M * i, y + uy * STAND_STEP_M * i
            if grid.blocked(*grid.cell(qx, qy), now):
                hit = True
            elif hit and grid.free_at(qx, qy) and self._roomy(qx, qy, now):
                return qx, qy
        return x, y

    async def go_to(self, kit, x: float, y: float, stop_m: float = 0.3, top: float | None = None, exempt: str = "", max_s: float = GO_MAX_S, settle_m: float = 0.0) -> Trip:
        if not self.ensure_frame():
            return Trip(False, "lost_pose", "you do not know where you are")
        from ..activities.motion import Wheels

        wheels = Wheels(kit, exempt=exempt).open()
        if self.pose.gyro is not None and not self.pose.bias_known and wheels.why_not() is None:
            await self.driver.halt()
            await self.pace.sleep(SETTLE_STILL_S + 0.4)
        start = self.pace.now()
        x0, y0, _ = self.pose.pose_rad()
        travelled_from = self.pose.total_m
        watch = StuckWatch()
        level = 0
        best, best_at = math.inf, start
        stuck_at = (x0, y0)
        noted: set = set()
        animal_since = None
        blocked_since = None
        path = None
        planned_at = -math.inf
        edges = 0
        gx, gy = x, y
        say = getattr(kit, "say", lambda text: None)

        def trip(ok: bool, how: str, text: str) -> Trip:
            return Trip(ok, how, text, round(self.pose.total_m - travelled_from, 2))

        try:
            while True:
                now = self.pace.now()
                if now - start > max_s:
                    return trip(False, "timeout", "it took too long to get there")
                if kit.battery_low():
                    return trip(False, "battery", "your battery got low")
                reason = wheels.why_not()
                if reason:
                    return trip(False, "stopped", reason)
                for reflex in wheels.reflexes():
                    if reflex == "edge":
                        edges += 1
                        path = None
                        if edges >= 2:
                            return trip(False, "edge", "your drop sensor found an edge on the way")
                    elif reflex in ("bump", "stall"):
                        watch.bumped(now)
                        path = None
                    elif reflex == "fault":
                        return trip(False, "stopped", "your body reported a sensor fault")
                held = wheels.held()
                if held == "edge":
                    await self.driver.halt()
                    await self.back_off(kit, wheels, 0.08)
                    path = None
                    continue
                if held or self.pose.carried:
                    await self.driver.halt()
                    await self.pace.sleep(CONTROL_S)
                    continue
                px, py, th = self.pose.pose_rad()
                gap = math.hypot(gx - px, gy - py)
                if gap <= stop_m:
                    if (gx, gy) != (x, y):
                        return trip(True, "near", "you got as close as you could")
                    return trip(True, "arrived", "you got there")
                if path is None or now - planned_at >= REPLAN_S:
                    if settle_m > 0.0:
                        gx, gy = self.standable(x, y, settle_m, now)
                    path = plan(self.chart.grid, (px, py), (gx, gy), now)
                    planned_at = now
                    if path is None:
                        return trip(False, "no_way", "you could not find a way there on your map")
                    left = path_length(path)
                    if left < best - GAIN_M:
                        best, best_at = left, now
                        if level and math.hypot(px - stuck_at[0], py - stuck_at[1]) >= RECOVER_M:
                            self.stats.recovered += 1
                            self.notes.append(note("recovered"))
                            level = 0
                while len(path) > 1 and math.hypot(path[0][0] - px, path[0][1] - py) < 0.25:
                    path.pop(0)
                obstacles = self.obstacles(None, exempt)
                clearance = self.clearance(obstacles)
                carrot, index = self.carrot_on(path, clearance)
                if index == 0 and not self.line_clear((px, py), carrot, clearance) and now - planned_at > REPLAN_S / 2.0:
                    planned_at = now - REPLAN_S
                sprint_ok = self._straight(carrot, clearance)
                cap = self.speed_cap(kit, None, sprint_ok)
                v_max = cap if top is None else min(cap, top * self.driver.sprint)
                v_max = min(v_max, math.sqrt(2.0 * GOAL_SLOW * max(0.0, gap - stop_m)) + 0.03)
                if self.rise_ahead():
                    v_max = min(v_max, RISE_SPEED)
                if self.local.here(clearance, px, py, th) < TIGHT_M:
                    v_max = min(v_max, TIGHT_SPEED)
                slow, block = self.animal_guard()
                if slow:
                    v_max = min(v_max, cap * 0.5)
                    if slow not in noted:
                        noted.add(slow)
                        self._note(kit, note("animal", where=slow))
                if block:
                    v_max = 0.0
                    best_at = now
                    animal_since = now if animal_since is None else animal_since
                    if now - animal_since > ANIMAL_WAIT_S:
                        return trip(False, "blocked", f"the {block} stayed in your way")
                    back = self.give_way(block)
                    if back:
                        await self.driver.send(back, 0.0, cap, now)
                        watch.reset(now)
                        await self.pace.sleep(CONTROL_S)
                        continue
                else:
                    animal_since = None
                    self.give_way(None)
                crawl, stop = self.life_guard(exempt)
                if stop:
                    v_max = 0.0
                    best_at = now
                elif crawl:
                    v_max = min(v_max, cap * LIFE_SLOW)
                self._life_slowed(kit, crawl or stop)
                final = index == len(path) - 1 or math.hypot(carrot[0] - gx, carrot[1] - gy) < 1e-6
                if abs(wrap(math.atan2(carrot[1] - py, carrot[0] - px) - th)) > TURN_FIRST_RAD:
                    v_max = 0.0
                choice = self.local.choose(clearance, px, py, th, self.driver.v, self.driver.w, carrot, Limits(v_max, cap), stop_m if final else 0.0)
                if not choice.blocked and abs(choice.v) < 0.005 and abs(self.driver.v) < 0.005 and gap <= stop_m + ARRIVE_SLACK_M:
                    if (gx, gy) != (x, y):
                        return trip(True, "near", "you got as close as you could")
                    return trip(True, "arrived", "you got there")
                stuck = None
                if choice.blocked:
                    await self.driver.halt()
                    if blocked_since is None:
                        blocked_since = now
                        planned_at = now - REPLAN_S
                    elif now - blocked_since > BLOCKED_S:
                        stuck = "blocked"
                        blocked_since = None
                else:
                    blocked_since = None
                    await self.driver.send(choice.v, choice.w, cap, now)
                    stuck = watch.tick(now, px, py, choice.v, choice.w, self.pose.speed, self.pose.wheel_rate, self.slipping(), choice.v > 0.02)
                if stuck is None and now - best_at > NO_GAIN_S:
                    stuck = "no_gain"
                if stuck is not None:
                    await self.driver.halt()
                    stuck_at = (px, py)
                    action = await self.escape(kit, wheels, level, say)
                    level += 1
                    path = None
                    best, best_at = math.inf, self.pace.now()
                    watch.reset(self.pace.now())
                    if action == "help":
                        waited = await self._wait_for_help(kit, wheels)
                        if not waited:
                            return trip(False, "stuck", f"you got stuck {self.where_stuck() or 'on the way'} and asked for help")
                        level = 0
                    continue
                await self.pace.sleep(CONTROL_S)
        finally:
            await self.driver.halt()
            wheels.close()

    def _straight(self, carrot: tuple[float, float], clearance: Clearance, angle: float = None) -> bool:
        x, y, th = self.pose.pose_rad()
        if abs(wrap(math.atan2(carrot[1] - y, carrot[0] - x) - th)) > (SPRINT_ANGLE if angle is None else angle):
            return False
        for d in (0.0, 0.4):
            px, py = ahead(x, y, th, d)
            if clearance.at(px, py) < BODY_RADIUS_M + SPRINT_CLEAR_M:
                return False
        return True

    async def _wait_for_help(self, kit, wheels) -> bool:
        x0, y0, _ = self.pose.pose_rad()
        start = self.pace.now()
        carried = False
        while self.pace.now() - start < HELP_WAIT_S:
            if wheels.why_not():
                return False
            if self.pose.carried:
                carried = True
            elif carried:
                return True
            x, y, _ = self.pose.pose_rad()
            if math.hypot(x - x0, y - y0) > 0.3:
                return True
            await self.pace.sleep(0.5)
        return False

    def _note(self, kit, text: str) -> None:
        self.notes.append(text)
        try:
            kit.note(text)
        except Exception:
            pass

    def remember_spot(self, name: str) -> bool:
        if not self.ensure_frame():
            return False
        x, y, _ = self.pose.pose_rad()
        self.chart.remember_spot(name or "here", x, y)
        self.charts.dirty = True
        return True

    def spot(self, name: str) -> tuple[float, float] | None:
        place = self.chart.place(name)
        return (place.x, place.y) if place is not None else None

    def spots(self) -> list[str]:
        return self.chart.spots()

    def place_at(self, x: float, y: float) -> str | None:
        return self.chart.place_at(x, y)

    async def go_back(self, kit, to: str = "start") -> Trip:
        if not self.pose.local_usable:
            return Trip(False, "lost_pose", "you have lost track of where you are")
        if to in ("start", "", None):
            target = self.spot("start")
            if target is None:
                target = self.chart.path[0] if self.chart.path else None
        else:
            target = self.spot(to)
            if target is None and to in ("home", "dock", "charger") and self.pose.frame == HOME:
                target = (0.45, 0.0)
        if target is None:
            return Trip(False, "no_way", f"you do not know where {to} is")
        trip = await self.go_to(kit, target[0], target[1], 0.35)
        if trip.ok:
            return Trip(True, "arrived", f"you went back to {'where you started' if to in ('start', '', None) else 'the ' + to}", trip.travelled_m)
        if trip.how == "no_way":
            back = await self._retrace(kit, target)
            if back is not None:
                return back
        return trip

    async def _retrace(self, kit, target) -> Trip | None:
        path = list(reversed(self.chart.path))
        if len(path) < 2:
            return None
        for index, point in enumerate(path):
            if math.hypot(point[0] - target[0], point[1] - target[1]) < 0.4:
                path = path[: index + 1]
                break
        for point in path[:: max(1, len(path) // 12)]:
            trip = await self.go_to(kit, point[0], point[1], 0.35, max_s=60.0)
            if not trip.ok and trip.how not in ("no_way",):
                return trip
        return Trip(True, "arrived", "you retraced your own path back", 0.0)

    async def follow(self, kit, lead: Lead, control: FollowControl | None = None) -> Trip:
        from .follow import Follower

        follower = Follower(self, kit, lead, control or FollowControl())
        self.following = follower
        try:
            return await follower.run()
        finally:
            self.following = None
            self.trail = list(follower.lock.path)
            self.charts.dirty = True

    def save(self) -> bool:
        try:
            return self.charts.save()
        except Exception:
            log.exception("nav: the map could not be saved")
            return False

    def status(self) -> dict:
        x, y, heading = self.pose.pose()
        return {
            "frame": self.pose.frame,
            "known": self.pose.usable,
            "x": round(x, 2),
            "y": round(y, 2),
            "heading_deg": round(heading, 1),
            "drift_m": round(self.pose.drift_m(), 2),
            "gyro": self.pose.axis is not None,
            "carried": self.pose.carried,
            "chart": self.chart.id,
            "map": self.chart.grid.counts(),
            "places": [p.as_dict() for p in self.chart.places if p.kind != "corridor"][:30],
            "stats": {k: v for k, v in self.stats.__dict__.items() if k != "said"},
        }

    def map_page(self) -> str:
        from .mapview import page

        for _ in range(3):
            try:
                x, y, th = self.pose.pose_rad()
                following = self.following
                trail = list(following.lock.path) if following is not None else list(self.trail)
                return page(self.chart, (x, y, th) if self.pose.local_usable else None, trail[-600:])
            except RuntimeError:
                continue
        return page(self.chart.__class__(self.chart.id), None, [])

    def routes(self) -> dict:
        import json

        return {
            "/map": lambda: ("text/html; charset=utf-8", self.map_page().encode("utf-8")),
            "/map.json": lambda: ("application/json", json.dumps(self.status()).encode("utf-8")),
        }
