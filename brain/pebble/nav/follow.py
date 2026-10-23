import asyncio
import math

from .geometry import BODY_RADIUS_M, path_length, wrap
from .lead import LeadLock
from .local import Limits
from .navigator import CONTROL_S, LIFE_SLOW, RISE_SPEED, TIGHT_M, TIGHT_SPEED, Trip
from .stuck import StuckWatch
from .words import line, note

FOLLOW_MAX_S = 1200.0
LOST_S = 0.8
ARRIVE_M = 0.35
PEEK_M = 0.45
SWEEP = (60.0, -60.0, 120.0, -120.0, 180.0)
SWEEP_PAUSE_S = 0.5
LISTEN_S = 4.0
WAIT_S = 30.0
UNSURE_ASK_EVERY_S = 20.0
UNSURE_GIVE_UP_S = 12.0
GAP_GAIN = 0.9
FACE_DEG = 15.0
BEHIND_M = 1.8
CALL_AGAIN_S = 60.0
CALL_AFTER_THANKS_S = 4.0
WAITING_SPEED = 0.15
COMING_AFTER_S = 1.0
THANKS_BEHIND_M = 1.0
THANKS_STOOD_S = 1.5
WAGGLE_S = 0.6
WAGGLE_W = 1.6
STAIRS_M = 0.2
NEAR_TRAIL_M = 0.6
HEARD_S = 5.0
SETTLE_S = 1.0
ANIMAL_WAIT_S = 20.0
EDGE_BACK_M = 0.08
SQUEEZE_GAP_M = 0.3
CENTRE_EXTRA_M = 0.25
OPEN_ROOM_M = 0.3
LEAD_CLEAR_M = 0.65
SPRINT_TURN = 1.2
CLOSE_ENOUGH_M = 1.0
CHASE_LEVELS = 3
CHASE_MAX_S = 25.0
CHASE_LOST_MAX_S = 60.0
RECOVERED_M = 1.0
RECOVERED_CRUMBS_M = 0.4
WAIT_SCAN_S = 8.0
WAIT_SWEEP = (60.0, 120.0, 180.0, -120.0, -60.0, 0.0)
BRIDGE_NEAR_M = 0.45
BRIDGE_EVERY_S = 1.5
BRIDGE_AHEAD = 4
GIVE_WAY_S = 20.0
LOST_SPARE_M = 0.3
LOST_NEAR_S = 2.0


class Follower:
    def __init__(self, nav, kit, lead, control):
        self.nav = nav
        self.kit = kit
        self.lead = lead
        self.control = control
        self.lock = LeadLock(lead.name, lead.track)
        self.exempt = ""
        self.state = "follow"
        self.say_fn = getattr(kit, "say", lambda text: None)
        self.started = 0.0
        self.watch = StuckWatch()
        self.level = 0
        self.progress_from = (0.0, 0.0)
        self.called_wait = False
        self.called_at = -math.inf
        self.said_coming = False
        self.waggle_until = -math.inf
        self.thanked_at = -math.inf
        self.asked_at = -math.inf
        self.unsure_since: float | None = None
        self.call_at: float | None = None
        self.print_task: asyncio.Task | None = None
        self.remembered = False
        self.said: list[tuple[float, str]] = []
        self.stairs_said = False
        self.wait_said = False
        self.last_sight_at = None
        self.lost_episodes = 0
        self.bridged_at = -math.inf
        self.limit = ""
        self.keep = 0.0
        self.animals_noted: set = set()
        self.animal_since: float | None = None
        self.chase_since = 0.0
        self.chase_consumed = 0
        self.consumed_at = 0
        self.blocked_by_since: float | None = None
        self.seen_gap = 0.0

    def say(self, kind: str, where: str = "") -> None:
        text = line(kind, self.lead.name, where)
        if not text:
            return
        self.said.append((self.nav.pace.now(), text))
        self.nav.stats.said.append(text)
        try:
            self.say_fn(text)
        except Exception:
            pass

    def note(self, kind: str, where: str = "") -> None:
        self.nav.notes.append(note(kind, self.lead.name, where))
        try:
            self.kit.note(note(kind, self.lead.name, where))
        except Exception:
            pass

    def name(self) -> str:
        return self.lead.name or "them"

    def lead_within(self, reach: float) -> bool:
        lock = self.lock
        now = self.nav.pace.now()
        if lock.x is None or lock.unsure or self.state not in ("follow", "chase"):
            return True
        if lock.lost_for(now) > LOST_S:
            return lock.lost_for(now) <= LOST_S + LOST_NEAR_S and self.seen_gap <= reach + LOST_SPARE_M
        x, y, _ = self.nav.pose.pose_rad()
        spots = [(lock.x, lock.y), lock.predict(now) or (lock.x, lock.y)]
        return any(math.hypot(px - x, py - y) <= reach for px, py in spots)

    async def run(self) -> Trip:
        nav, kit = self.nav, self.kit
        from ..activities.motion import Wheels

        if not getattr(nav.eyes, "available", False):
            return Trip(False, "no_sight", "you cannot see yet")
        if not nav.ensure_frame():
            return Trip(False, "lost_pose", "your wheel counts are not calibrated, so you cannot keep track of where you are")
        await nav.eyes.use_camera("front")
        rest = kit.body.profile.tilt_rest
        tilt = kit.body.telemetry.tilt
        if tilt is None or abs(tilt - rest) > 4.0:
            await kit.body.tilt(rest)
            await nav.pace.sleep(0.6)
        wheels = Wheels(kit).open()
        self.started = nav.pace.now()
        travelled_from = nav.pose.total_m
        self.wheels = wheels
        try:
            ending = await self._loop(wheels)
            return Trip(ending.ok, ending.how, ending.text, round(nav.pose.total_m - travelled_from, 2))
        finally:
            await nav.driver.halt()
            wheels.close()
            if self.print_task is not None and not self.print_task.done():
                self.print_task.cancel()
            forget = getattr(nav.eyes, "forget_print", None)
            if forget is not None and self.remembered:
                try:
                    forget("lead")
                except Exception:
                    pass

    async def _acquire(self, wheels) -> bool:
        nav = self.nav
        for _ in range(6):
            await nav.pace.sleep(CONTROL_S)
            seen = nav.fresh_people()
            if seen and self.lock.start(seen, nav.pace.now(), self.lead.track) is not None:
                return True
        _, _, th = nav.pose.pose_rad()
        for step in (40.0, 80.0, 120.0, 160.0, 200.0, 240.0, 280.0, 320.0):
            if wheels.why_not():
                return False
            await nav.turn_to(self.kit, wheels, wrap(th + math.radians(step)), lead=self.lead)
            await nav.pace.sleep(0.5)
            seen = nav.fresh_people()
            if seen and self.lock.start(seen, nav.pace.now(), self.lead.track) is not None:
                return True
        return False

    async def _loop(self, wheels) -> Trip:
        nav, kit = self.nav, self.kit
        if not nav.pose.bias_known and nav.pose.gyro is not None:
            await nav.driver.halt()
            await nav.pace.sleep(SETTLE_S)
        if not await self._acquire(wheels):
            return Trip(False, "lost", f"you looked around once but could not see {self.name()}")
        await nav.quick_wiggle(kit, wheels, self.lead)
        if kit.body.telemetry.docked and wheels.why_not() is None:
            from ..activities.motion import leave_dock

            await leave_dock(kit, wheels)
        self.progress_from = nav.pose.pose_rad()[:2]
        while True:
            now = nav.pace.now()
            if now - self.started > FOLLOW_MAX_S:
                return Trip(False, "timeout", f"you followed {self.name()} for a long time and stopped")
            if kit.battery_low():
                return Trip(False, "battery", "your battery got low")
            reason = wheels.why_not()
            if reason:
                return Trip(False, "stopped", reason)
            for reflex in wheels.reflexes():
                if reflex in ("bump", "stall"):
                    self.watch.bumped(now)
                elif reflex == "fault":
                    return Trip(False, "stopped", "your body reported a sensor fault")
                elif reflex == "edge":
                    self.watch.bumped(now)
            held = wheels.held()
            if held == "edge":
                await nav.driver.halt()
                if self._stairs() and not self.stairs_said:
                    self.stairs_said = True
                    self.say("stairs")
                    self.note("stairs")
                await nav.back_off(kit, wheels, EDGE_BACK_M)
                await nav.pace.sleep(CONTROL_S)
                continue
            if held:
                await nav.driver.halt()
                await nav.pace.sleep(CONTROL_S)
                continue
            if nav.pose.carried:
                await nav.driver.halt()
                self.state = "carried"
                await nav.pace.sleep(CONTROL_S)
                continue
            if self.state == "carried":
                self.note("carried")
                self.state = "look"
            self._perceive(now)
            maybe = self.lock.maybe
            if maybe is not None and now - maybe[1] <= 1.0 and self.lock.lost_for(now) > LOST_S and now - self.asked_at >= UNSURE_ASK_EVERY_S:
                self.asked_at = now
                self.call_at = now
                self.say("who")
                self.note("unsure")
            if self.lock.unsure:
                trip = await self._unsure(wheels)
                if trip is not None:
                    return trip
                continue
            if self.lock.lost_for(now) <= LOST_S:
                if self.state in ("look", "wait"):
                    self.say("found")
                self.state = "follow"
            elif self.state == "follow":
                self.state = "chase"
                self.chase_since = now
                self.chase_consumed = self.lock.consumed
                self.lost_episodes += 1
            if self.state == "chase":
                if self.lock.consumed > self.chase_consumed:
                    self.chase_consumed = self.lock.consumed
                    self.chase_since = now
                if now - self.chase_since > CHASE_MAX_S or self.lock.lost_for(now) > CHASE_LOST_MAX_S:
                    self.state = "look"
            if self.state == "look":
                found = await self._look_around(wheels)
                if found:
                    self.state = "follow"
                    continue
                self.state = "wait"
            if self.state == "wait":
                trip = await self._wait(wheels)
                if trip is not None:
                    return trip
                self.state = "follow"
                continue
            if self._stairs():
                await nav.driver.halt()
                if not self.stairs_said:
                    self.stairs_said = True
                    self.say("stairs")
                    self.note("stairs")
                await nav.pace.sleep(CONTROL_S)
                continue
            trip = await self._drive(wheels, now)
            if trip is not None:
                return trip
            await nav.pace.sleep(CONTROL_S)

    def _perceive(self, now: float) -> None:
        nav = self.nav
        sight = nav.sight
        if sight is None or sight.at == self.last_sight_at:
            return
        self.last_sight_at = sight.at
        seen = nav.fresh_people()
        heard = None
        if self.call_at is not None and now - self.call_at <= HEARD_S:
            talkers = [s for s in seen if s.speaking is not None and s.speaking >= 0.5]
            if len(talkers) == 1:
                heard = talkers[0].track
        self.lock.update(seen, now, heard)
        if self.lock.x is not None:
            nav.trail = self.lock.path
            if self.lock.seen_at == now:
                x, y, _ = nav.pose.pose_rad()
                self.seen_gap = math.hypot(self.lock.x - x, self.lock.y - y)
        track = self.lock.wants_print(now)
        fingerprint = getattr(nav.eyes, "fingerprint", None)
        if track is not None and fingerprint is not None and (self.print_task is None or self.print_task.done()):
            self.print_task = asyncio.ensure_future(self._print(track))

    async def _print(self, track: int) -> None:
        nav = self.nav
        try:
            vec = await nav.eyes.fingerprint(track)
        except Exception:
            return
        if vec is None:
            return
        before = len(self.lock.views)
        self.lock.took_print(track, vec, nav.pace.now())
        if len(self.lock.views) > before:
            remember = getattr(nav.eyes, "remember_print", None)
            if remember is not None:
                try:
                    remember("lead", vec, replace=not self.remembered)
                    self.remembered = True
                except Exception:
                    pass

    def _stairs(self) -> bool:
        grid = self.nav.chart.grid
        if not grid.cliffs or self.lock.x is None:
            return False
        points = [(c[0], c[1]) for c in self.lock.trail[:12]]
        for px, py in points:
            ix, iy = grid.cell(px, py)
            for dx in (-2, -1, 0, 1, 2):
                for dy in (-2, -1, 0, 1, 2):
                    if (ix + dx, iy + dy) in grid.cliffs:
                        return True
        return False

    def _targets(self, x: float, y: float) -> tuple[list[tuple[float, float]], float, bool]:
        lock = self.lock
        lock.consume(x, y, ARRIVE_M)
        seen = lock.lost_for(self.nav.pace.now()) <= LOST_S
        crumbs = [(c[0], c[1]) for c in lock.trail]
        points = list(crumbs)
        if seen and lock.x is not None:
            points.append((lock.x, lock.y))
        if not points and lock.x is not None:
            points = [(lock.x, lock.y)]
        along = path_length([(x, y)] + points) if points else 0.0
        if not seen:
            return points, along, False
        keep = self.control.gap_m + CENTRE_EXTRA_M
        if keep > SQUEEZE_GAP_M + CENTRE_EXTRA_M and not self._open_between(x, y, lock.x, lock.y):
            keep = SQUEEZE_GAP_M + CENTRE_EXTRA_M
        self.keep = keep
        stop = along - keep
        out = []
        walked = 0.0
        previous = (x, y)
        for point in points:
            step = math.hypot(point[0] - previous[0], point[1] - previous[1])
            if walked + step > stop:
                if stop > walked and step > 1e-6:
                    t = (stop - walked) / step
                    out.append((previous[0] + (point[0] - previous[0]) * t, previous[1] + (point[1] - previous[1]) * t))
                break
            out.append(point)
            walked += step
            previous = point
        return out, along, True

    def _open_between(self, x: float, y: float, lx: float, ly: float) -> bool:
        grid = self.nav.chart.grid
        reach = math.hypot(lx - x, ly - y)
        if reach <= LEAD_CLEAR_M:
            return True
        ux, uy = (lx - x) / reach, (ly - y) / reach
        steps = int((reach - LEAD_CLEAR_M) / 0.05)
        for i in range(1, steps + 1):
            px, py = x + ux * 0.05 * i, y + uy * 0.05 * i
            for side in (OPEN_ROOM_M, -OPEN_ROOM_M):
                if grid.occupied_at(px - uy * side, py + ux * side):
                    return False
        return True

    async def _drive(self, wheels, now: float) -> Trip | None:
        nav, kit = self.nav, self.kit
        lock = self.lock
        x, y, th = nav.pose.pose_rad()
        points, along, seen = self._targets(x, y)
        gap = self.control.gap_m
        obstacles = nav.obstacles(lock.track)
        clearance = nav.clearance(obstacles)
        near_trail = [(c[0], c[1]) for c in lock.trail] + ([(lock.x, lock.y)] if lock.x is not None else [])
        gap = self.keep or gap
        straight = math.hypot(lock.x - x, lock.y - y) if lock.x is not None else math.inf
        if not points or (seen and min(along, straight) <= gap + 0.05):
            v_max = 0.0
            goal = None
            face = math.atan2(lock.y - y, lock.x - x) if lock.x is not None else None
            if face is not None and abs(wrap(face - th)) < math.radians(FACE_DEG):
                face = None
        else:
            goal, index = nav.carrot_on(points, clearance, near=near_trail)
            blocked = index == 0 and not nav.line_clear((x, y), goal, clearance)
            stalled = index == 0 and len(points) > 1 and math.hypot(goal[0] - x, goal[1] - y) < BRIDGE_NEAR_M
            if (blocked or stalled) and now - self.bridged_at >= BRIDGE_EVERY_S:
                self.bridged_at = now
                if self._bridge(x, y, points, 0 if blocked else None):
                    points, along, seen = self._targets(x, y)
                    goal, index = nav.carrot_on(points, clearance, near=near_trail + [(p[0], p[1]) for p in points])
            if index > 1:
                nav.stats.shortcuts += 1
            face = None
            if seen:
                v_max = max(0.0, lock.speed() + GAP_GAIN * (min(along, straight) - gap))
            else:
                end = points[-1]
                left = math.hypot(end[0] - x, end[1] - y)
                if left <= ARRIVE_M and len(points) <= 1:
                    await nav.driver.halt()
                    self.state = "look"
                    return None
                v_max = math.sqrt(2.0 * 0.5 * max(0.0, path_length([(x, y)] + points) - ARRIVE_M * 0.5)) + 0.04
        privacy = getattr(kit, "privacy", None)
        room = privacy.fence(goal) if goal is not None and privacy is not None else None
        if room is not None:
            await nav.driver.halt()
            return Trip(True, "private", f"{self.name()} went into the {room}, which is private, so you waited outside")
        rules = getattr(kit, "rules", None)
        kept = rules.fence(goal) if goal is not None and rules is not None else None
        if kept is not None:
            await nav.driver.halt()
            return Trip(True, "kept out", f"{self.name()} went into the {kept[0]}, which you were asked to keep out of, so you waited outside: {kept[1]}")
        sprint_ok = goal is not None and nav._straight(goal, clearance, SPRINT_TURN)
        cap = nav.speed_cap(kit, self.lead, sprint_ok)
        self.limit = "sprint" if cap >= nav.driver.sprint - 1e-6 else ("cruise" if cap >= nav.driver.cruise - 1e-6 else "people")
        if self.control.top is not None:
            cap = min(cap, max(0.03, self.control.top) * nav.driver.sprint)
        if v_max < cap:
            self.limit = "gap"
        v_max = min(v_max, cap)
        if nav.rise_ahead():
            self.limit = "bump"
            v_max = min(v_max, RISE_SPEED)
            normal = nav.threshold_normal()
            if normal is not None and abs(wrap(normal - th)) > math.radians(25.0) and nav.driver.v < 0.1:
                face = normal
                goal = None
                v_max = 0.0
                self.note("threshold")
        if nav.local.here(clearance, x, y, th) < TIGHT_M:
            self.limit = "tight"
            v_max = min(v_max, TIGHT_SPEED)
        slow, block = nav.animal_guard()
        if slow:
            self.limit = "animal"
            v_max = min(v_max, cap * 0.5)
            if slow not in self.animals_noted:
                self.animals_noted.add(slow)
                self.note("animal", slow)
        if block:
            v_max = 0.0
            self.animal_since = now if self.animal_since is None else self.animal_since
            if now - self.animal_since > ANIMAL_WAIT_S:
                return Trip(False, "blocked", f"the {block} stayed in your way, so you stopped following {self.name()}")
            back = nav.give_way(block)
            if back:
                await nav.driver.send(back, 0.0, cap, now)
                self.watch.reset(now)
                return None
        else:
            self.animal_since = None
            nav.give_way(None)
        crawl, stop = nav.life_guard()
        if stop:
            v_max = 0.0
        elif crawl:
            v_max = min(v_max, cap * LIFE_SLOW)
        if (crawl or stop) and (crawl or stop) not in self.animals_noted:
            self.animals_noted.add(crawl or stop)
            self.note("life", crawl or stop)
        if goal is None and face is None:
            await nav.driver.send(0.0, 0.0, cap, now)
            self._social(now, along, seen)
            self.watch.tick(now, x, y, 0.0, 0.0, nav.pose.speed, nav.pose.wheel_rate, nav.slipping(), False)
            return None
        choice = nav.local.choose(clearance, x, y, th, nav.driver.v, nav.driver.w, goal, Limits(v_max, cap), 0.0, face)
        stuck = "blocked" if choice.blocked and v_max > 0.0 else None
        v, w = choice.v, choice.w
        if v_max > 0.0 and stuck is not None:
            who = nav.in_the_way(lock.track)
            if who is not None:
                if self.blocked_by_since is None:
                    self.blocked_by_since = now
                if now - self.blocked_by_since <= GIVE_WAY_S:
                    await nav.driver.halt()
                    self.watch.reset(now)
                    return None
        else:
            self.blocked_by_since = None
        if now < self.waggle_until and v > 0.03:
            phase = math.sin((self.waggle_until - now) * 2.0 * math.pi * 3.0)
            ww = w + math.copysign(WAGGLE_W, phase)
            free, _ = nav.local.free_along(clearance, x, y, th, v, ww, 0.6)
            if free == math.inf:
                w = ww
        if stuck is None:
            await nav.driver.send(v, w, cap, now)
            trying = v_max > 0.03 and goal is not None
            stuck = self.watch.tick(now, x, y, v, w, nav.pose.speed, nav.pose.wheel_rate, nav.slipping(), trying)
        if stuck is not None:
            return await self._unstick(wheels, stuck)
        moved = math.hypot(x - self.progress_from[0], y - self.progress_from[1])
        if self.level and (moved >= RECOVERED_M or (self.lock.consumed >= self.consumed_at + 2 and moved >= RECOVERED_CRUMBS_M)):
            nav.stats.recovered += 1
            self.note("recovered")
            self.level = 0
        if not self.level:
            self.progress_from = (x, y)
            self.consumed_at = self.lock.consumed
        self._social(now, along, seen)
        return None

    def _bridge(self, x: float, y: float, points: list, far: int | None = None) -> bool:
        from .route import plan

        nav, lock = self.nav, self.lock
        if far is None:
            far = min(len(points) - 1, BRIDGE_AHEAD)
        target = points[far]
        path = plan(nav.chart.grid, (x, y), target, nav.pace.now())
        if path is None or len(path) < 2:
            return False
        now = nav.pace.now()
        crumbs = []
        for (ax, ay), (bx, by) in zip(path, path[1:]):
            length = math.hypot(bx - ax, by - ay)
            n = max(1, int(length / 0.3))
            for i in range(1, n + 1):
                crumbs.append((ax + (bx - ax) * i / n, ay + (by - ay) * i / n, now))
        keep = lock.trail[far:] if far < len(lock.trail) else []
        lock.trail = crumbs[:-1] + keep if keep else crumbs
        nav.stats.replans += 1
        return True

    async def _unstick(self, wheels, why: str) -> Trip | None:
        nav = self.nav
        await nav.driver.halt()
        if self.state == "chase" and self.lock.trail:
            x, y, _ = nav.pose.pose_rad()
            end = self.lock.trail[-1]
            near = len(self.lock.trail) <= 2 and math.hypot(end[0] - x, end[1] - y) <= CLOSE_ENOUGH_M and nav.line_clear((x, y), (end[0], end[1]), nav.clearance(nav.obstacles(self.lock.track)), 0.05)
            if near or self.level >= CHASE_LEVELS:
                self.state = "look"
                self.level = 0
                self.watch.reset(nav.pace.now())
                return None
        if self.level == 0:
            self.note("stuck", nav.where_stuck())
        action = await nav.escape(self.kit, wheels, self.level, self.say_fn, self.lead)
        self.level += 1
        self.watch.reset(nav.pace.now())
        if action == "help":
            if await nav._wait_for_help(self.kit, wheels):
                self.level = 0
                return None
            return Trip(False, "stuck", f"you got stuck {nav.where_stuck() or 'on the way'} while following {self.name()} and asked for help")
        if action == "replan":
            await self._replan(wheels)
        return None

    async def _replan(self, wheels) -> None:
        nav, lock = self.nav, self.lock
        if not lock.trail and lock.x is None:
            return
        target = (lock.trail[min(len(lock.trail) - 1, 6)][0], lock.trail[min(len(lock.trail) - 1, 6)][1]) if lock.trail else (lock.x, lock.y)
        x, y, _ = nav.pose.pose_rad()
        from .route import plan

        path = plan(nav.chart.grid, (x, y), target, nav.pace.now())
        if path is None or len(path) < 2:
            return
        lock.trail = [(px, py, nav.pace.now()) for px, py in path[1:-1]] + lock.trail

    def _social(self, now: float, along: float, seen: bool) -> None:
        lock = self.lock
        behind = along - (self.keep or self.control.gap_m + CENTRE_EXTRA_M)
        again = CALL_AFTER_THANKS_S if self.thanked_at >= self.called_at else CALL_AGAIN_S
        if seen and behind > BEHIND_M and lock.speed() > 0.4 and not self.called_wait and now - self.called_at >= again:
            self.called_wait = True
            self.called_at = now
            self.said_coming = False
            self.say("wait_for_me")
            self.note("wait_for_me")
        if self.called_wait and not self.said_coming and seen and lock.speed() < WAITING_SPEED and lock.stood_for(now) >= COMING_AFTER_S and behind > 1.0:
            self.said_coming = True
            self.say("coming")
            self.waggle_until = now + WAGGLE_S
        if seen and self.called_wait and behind <= THANKS_BEHIND_M and lock.stood_for(now) >= THANKS_STOOD_S:
            self.thanked_at = now
            self.called_wait = False
            self.say("thanks")
            self.note("thanks")

    async def _look_around(self, wheels) -> bool:
        nav, kit, lock = self.nav, self.kit, self.lock
        x, y, th = nav.pose.pose_rad()
        heading = self._lead_heading()
        if heading is None:
            heading = th
        await nav.turn_free(kit, wheels, heading, lead=self.lead)
        if await self._glance(0.4):
            return True
        clearance = nav.clearance(nav.obstacles(lock.track))
        tip = (x + PEEK_M * math.cos(heading), y + PEEK_M * math.sin(heading))
        if nav.line_clear((x, y), tip, clearance):
            trip = await self._creep_to(wheels, tip)
            if trip and await self._glance(0.4):
                return True
        self.say("call")
        self.call_at = nav.pace.now()
        look_for = getattr(nav.eyes, "look_for", None)
        if look_for is not None and lock.views and self.remembered:
            try:
                hit = await asyncio.wait_for(look_for("lead"), 6.0)
            except Exception:
                hit = None
            if hit is not None:
                from .geometry import body_angle

                _, _, th_now = nav.pose.pose_rad()
                await nav.turn_to(kit, wheels, wrap(th_now + body_angle(hit.bearing_deg, "front")), lead=self.lead)
                if await self._glance(0.6):
                    return True
        for step in SWEEP:
            if wheels.why_not():
                return False
            await nav.turn_free(kit, wheels, wrap(heading + math.radians(step)), lead=self.lead)
            if await self._glance(SWEEP_PAUSE_S):
                return True
        if await self._glance(LISTEN_S):
            return True
        return False

    async def _creep_to(self, wheels, tip) -> bool:
        nav = self.nav
        start = nav.pace.now()
        while nav.pace.now() - start < 4.0:
            if wheels.why_not() or wheels.held():
                break
            x, y, th = nav.pose.pose_rad()
            if math.hypot(tip[0] - x, tip[1] - y) < 0.1:
                await nav.driver.halt()
                return True
            clearance = nav.clearance(nav.obstacles(self.lock.track))
            cap = nav.speed_cap(self.kit, self.lead, False)
            choice = nav.local.choose(clearance, x, y, th, nav.driver.v, nav.driver.w, tip, Limits(min(cap, 0.12), cap), 0.1)
            if choice.blocked:
                break
            await nav.driver.send(choice.v, choice.w, cap, nav.pace.now())
            await nav.pace.sleep(CONTROL_S)
            self._perceive(nav.pace.now())
            if self.lock.lost_for(nav.pace.now()) <= LOST_S:
                await nav.driver.halt()
                return True
        await nav.driver.halt()
        return False

    async def _glance(self, seconds: float) -> bool:
        nav = self.nav
        end = nav.pace.now() + seconds
        while nav.pace.now() < end:
            await nav.pace.sleep(CONTROL_S)
            now = nav.pace.now()
            self._perceive(now)
            if self.lock.lost_for(now) <= LOST_S and not self.lock.unsure:
                return True
        return False

    def _lead_heading(self) -> float | None:
        lock = self.lock
        heading = lock.heading()
        if heading is None and len(lock.path) >= 2:
            (ax, ay), (bx, by) = lock.path[-2], lock.path[-1]
            if math.hypot(bx - ax, by - ay) > 0.05:
                heading = math.atan2(by - ay, bx - ax)
        return heading

    async def _wait(self, wheels) -> Trip | None:
        nav, kit = self.nav, self.kit
        await nav.driver.halt()
        if not self.wait_said:
            self.wait_said = True
            self.say("waiting")
        face = None
        if self.lock.x is not None:
            x, y, _ = nav.pose.pose_rad()
            face = math.atan2(self.lock.y - y, self.lock.x - x) if math.hypot(self.lock.x - x, self.lock.y - y) > 0.4 else self._lead_heading()
        start = nav.pace.now()
        scanned = start
        sweep = 0
        if face is not None and not wheels.why_not():
            await nav.turn_free(kit, wheels, face, lead=self.lead)
        while nav.pace.now() - start < WAIT_S:
            if wheels.why_not():
                return Trip(False, "stopped", wheels.why_not())
            if kit.battery_low():
                return Trip(False, "battery", "your battery got low while you waited")
            await nav.pace.sleep(CONTROL_S)
            now = nav.pace.now()
            self._perceive(now)
            if self.lock.lost_for(now) <= LOST_S and not self.lock.unsure:
                if not self._stairs():
                    self.say("found")
                    self.wait_said = False
                    self.stairs_said = False
                    return None
            if face is not None and now - scanned >= WAIT_SCAN_S and not wheels.why_not():
                sweep += 1
                for step in WAIT_SWEEP:
                    await nav.turn_free(kit, wheels, wrap(face + math.radians(step if sweep % 2 else -step)), lead=self.lead)
                    if await self._glance(0.5):
                        self.say("found")
                        self.wait_said = False
                        return None
                scanned = nav.pace.now()
        return Trip(False, "lost", f"you lost sight of {self.name()}, looked around once, called once and waited {round(WAIT_S)} seconds")

    async def _unsure(self, wheels) -> Trip | None:
        nav = self.nav
        now = nav.pace.now()
        await nav.driver.halt()
        if self.unsure_since is None:
            self.unsure_since = now
            self.note("unsure")
        if now - self.asked_at >= UNSURE_ASK_EVERY_S:
            self.asked_at = now
            self.say("who")
            self.call_at = now
        await nav.pace.sleep(CONTROL_S)
        self._perceive(nav.pace.now())
        if not self.lock.unsure:
            self.unsure_since = None
            return None
        if nav.pace.now() - self.unsure_since > UNSURE_GIVE_UP_S:
            self.lock.unsure = False
            self.lock.seen_at = (self.lock.seen_at or now) - 10.0
            self.unsure_since = None
            self.state = "wait"
        return None
