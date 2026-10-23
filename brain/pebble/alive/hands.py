import logging
import math
from collections import deque
from dataclasses import dataclass

from ..people.company import Heard
from ..people.stops import StopNote
from ..people.trust import allowed
from ..understand.request import Request
from ..activities.seeing import CAMERA_HEIGHT_M
from .gestures import MIN_SCORE, _swings

log = logging.getLogger(__name__)

HANDS_S = 0.1
SIGHT_AGE_S = 0.5
PERSON_SCORE = 0.4
FACING_DEG = 45.0
SHOULDER_HALF_M = 0.19
WRIST_AHEAD_M = 0.3
ELBOW_AHEAD_M = 0.15
ELBOW_DROP_M = 0.08
SHOO_BELOW_HIPS_M = 0.2
CHEST = 0.65
HEAD_ABOVE_M = 0.15
FRONT_SPAN = 1.6
STILL_M = 0.05
SWING_M = 0.04
SWING_S = 1.6
PALM_HOLD_S = 0.3
RAISED_HOLD_S = 0.2
SHOO_M = 0.06
SHOO_SWINGS = 2
SHOO_GAP_S = 8.0
KEEP_S = 2.0
MOVING_S = 0.5
EPISODE_GAP_S = 0.8
TIE_S = 180.0


@dataclass(frozen=True)
class HandSign:
    kind: str
    track: int | None
    side: str
    at: float


@dataclass
class _Arm:
    rows: deque
    palm_since: float | None = None
    palm_frames: int = 0
    anchor: tuple[float, float] | None = None
    raised_since: float | None = None
    raised_frames: int = 0
    shooed_at: float = -math.inf


@dataclass(frozen=True)
class _Torso:
    centre: float
    half: float
    away: float
    shoulders: float
    chest: float
    head: float
    hips: float
    shoulder_deg: float


def _point(person, name: str):
    for point in person.points:
        if point.name == name and point.score >= MIN_SCORE:
            return point
    return None


def _across(point) -> float:
    return math.tan(math.radians(max(-80.0, min(80.0, point.bearing_deg))))


def _rise(point, pitch: float) -> float:
    return math.tan(math.radians(max(-80.0, min(80.0, point.elevation_deg + pitch))))


def _torso(person, pitch: float, camera_z: float) -> _Torso | None:
    seen = [p for p in (_point(person, "left_shoulder"), _point(person, "right_shoulder")) if p is not None]
    nose = _point(person, "nose")
    if len(seen) == 2:
        half = abs(_across(seen[0]) - _across(seen[1])) / 2.0
        centre = (_across(seen[0]) + _across(seen[1])) / 2.0
    elif seen and nose is not None:
        half = abs(_across(seen[0]) - _across(nose))
        centre = _across(nose)
    else:
        return None
    if half < 1e-3:
        return None
    away = SHOULDER_HALF_M / half
    shoulders = camera_z + away * sum(_rise(p, pitch) for p in seen) / len(seen)
    hips_seen = [p for p in (_point(person, "left_hip"), _point(person, "right_hip")) if p is not None]
    hips = camera_z + away * sum(_rise(p, pitch) for p in hips_seen) / len(hips_seen) if hips_seen else shoulders - 2.4 * SHOULDER_HALF_M
    head = camera_z + away * _rise(nose, pitch) if nose is not None else shoulders + SHOULDER_HALF_M
    return _Torso(centre, half, away, shoulders, hips + CHEST * (shoulders - hips), head, hips, sum(p.elevation_deg for p in seen) / len(seen))


class HandSigns:
    def __init__(self):
        self.arms: dict[tuple[int | None, str], _Arm] = {}

    def read(self, sight, moving: bool, tilt_deg: float = 0.0) -> list[HandSign]:
        if sight is None or not sight.people:
            return []
        at = sight.at
        camera = getattr(sight, "camera", "front")
        pitch = tilt_deg if camera == "front" else -tilt_deg
        camera_z = CAMERA_HEIGHT_M.get(camera, 0.14)
        found = []
        for person in sight.people:
            if person.score < PERSON_SCORE:
                continue
            torso = _torso(person, pitch, camera_z)
            if torso is None:
                continue
            facing = person.facing_deg is None or abs(person.facing_deg) <= FACING_DEG
            for side in ("left", "right"):
                sign = self._arm(person, side, torso, facing, moving, at, pitch, camera_z)
                if sign is not None:
                    found.append(sign)
        for key in [k for k, arm in self.arms.items() if not arm.rows or at - arm.rows[-1][0] > KEEP_S]:
            del self.arms[key]
        return found

    def _arm(self, person, side: str, torso: _Torso, facing: bool, moving: bool, at: float, pitch: float, camera_z: float) -> HandSign | None:
        wrist = _point(person, f"{side}_wrist")
        key = (person.track, side)
        arm = self.arms.get(key)
        if arm is None:
            arm = self.arms[key] = _Arm(deque())
        if wrist is None:
            arm.palm_since = arm.raised_since = None
            arm.palm_frames = arm.raised_frames = 0
            return None
        near = max(0.1, torso.away - WRIST_AHEAD_M)
        across = near * (_across(wrist) - torso.centre)
        height = camera_z + near * _rise(wrist, pitch)
        arm.rows.append((at, across, height))
        while arm.rows and at - arm.rows[0][0] > SWING_S:
            arm.rows.popleft()
        elbow = _point(person, f"{side}_elbow")
        lifted = elbow is None or camera_z + max(0.1, torso.away - ELBOW_AHEAD_M) * _rise(elbow, pitch) >= torso.shoulders - ELBOW_DROP_M
        raised = facing and lifted and height >= torso.chest
        palm = raised and height <= torso.head + HEAD_ABOVE_M and abs(across) <= FRONT_SPAN * SHOULDER_HALF_M
        up_rows = []
        for row in reversed(arm.rows):
            if row[2] < torso.chest:
                break
            up_rows.append(row)
        swinging = _swings([row[1] for row in up_rows], SWING_M) >= 1 or _swings([row[2] for row in up_rows], SWING_M) >= 1
        if palm and not swinging and arm.palm_since is not None and arm.anchor is not None and max(abs(across - arm.anchor[0]), abs(height - arm.anchor[1])) <= STILL_M:
            arm.palm_frames += 1
        elif palm and not swinging:
            arm.palm_since, arm.anchor, arm.palm_frames = at, (across, height), 1
        else:
            arm.palm_since, arm.anchor, arm.palm_frames = None, None, 0
        if raised:
            if arm.raised_since is None:
                arm.raised_since, arm.raised_frames = at, 0
            arm.raised_frames += 1
        else:
            arm.raised_since, arm.raised_frames = None, 0
        if arm.palm_since is not None and arm.palm_frames >= 2 and at - arm.palm_since >= PALM_HOLD_S:
            return HandSign("stop", person.track, side, at)
        if moving and arm.raised_since is not None and arm.raised_frames >= 2 and at - arm.raised_since >= RAISED_HOLD_S:
            return HandSign("stop", person.track, side, at)
        if facing and torso.hips - SHOO_BELOW_HIPS_M <= height < torso.chest and wrist.elevation_deg < torso.shoulder_deg and at - arm.shooed_at >= SHOO_GAP_S:
            low = [row for row in arm.rows if row[2] < torso.chest]
            outward = [abs(row[1]) for row in low]
            heights = [row[2] for row in low]
            if len(low) >= 4 and _swings(outward, SHOO_M) >= SHOO_SWINGS and max(heights) - min(heights) < max(outward) - min(outward):
                arm.shooed_at = at
                return HandSign("shoo", person.track, side, at)
        return None


class HandWatch:
    def __init__(self, life):
        self.life = life
        self.signs = HandSigns()
        self.seen_at = None
        self.stopping: dict[int | None, float] = {}

    async def run(self) -> None:
        pace = self.life.commands.runner.kit.pace
        while True:
            await pace.sleep(HANDS_S)
            try:
                self.watch()
            except Exception:
                log.exception("watching hands failed")

    def moving(self, now: float) -> bool:
        tel = self.life.p.body.telemetry
        return tel.last_motion_at is not None and now - tel.last_motion_at <= MOVING_S

    def watch(self) -> None:
        p = self.life.p
        eyes = p.eyes
        if eyes is None or not getattr(eyes, "available", False):
            return
        sight = eyes.latest(SIGHT_AGE_S)
        if sight is None or sight.at == self.seen_at:
            return
        self.seen_at = sight.at
        now = p.clock.now()
        for sign in self.signs.read(sight, self.moving(now), p.body.telemetry.tilt or 0.0):
            if sign.kind == "stop":
                self.stop(sign, sight, now)
            elif sign.kind == "shoo":
                self.shoo(sign, sight, now)

    def who(self, track: int | None, sight, now: float):
        company = self.life.company
        speakers = getattr(getattr(self.life.p, "conversation", None), "speakers", None)
        tie = (getattr(speakers, "tracks", None) or {}).get(track) if track is not None else None
        if tie is not None and now - tie[1] <= TIE_S:
            person = company.book.get(tie[0])
            if person is not None:
                return person
        if len([p for p in sight.people if p.score >= PERSON_SCORE]) == 1:
            sole = company.presence.sole(now)
            if sole is not None:
                return company.book.get(sole)
        return None

    def stop(self, sign: HandSign, sight, now: float) -> None:
        company = self.life.company
        person = self.who(sign.track, sight, now)
        label = "someone" if person is None else person.label
        sticky = allowed(company.tier(person, now)).sticky_stop and person is not None
        ongoing = now - self.stopping.get(sign.track, -math.inf) <= EPISODE_GAP_S
        self.stopping[sign.track] = now
        note = company.guard.stop(person.id if person else None, label, sticky, now)
        if ongoing:
            return
        if note.kind == "sticky":
            text = f"{label} held up a hand to stop you; you stopped and stay still until someone you trust says you may move"
        else:
            text = f"{label} held up a hand to stop you; your wheels paused for {company.guard.pause_s:g} seconds"
        heard = Heard(person.id if person else None, label, "held up a hand for stop", StopNote(note.kind, note.by, text))
        self.life.p.blackbox.record("hand_stop", person=heard.person_id, stop=note.kind)
        self.life._stopped(heard, now)

    def shoo(self, sign: HandSign, sight, now: float) -> None:
        commands = self.life.commands
        if getattr(commands.runner.current, "game", False):
            return
        person = self.who(sign.track, sight, now)
        label = "someone" if person is None else person.label
        self.life.p.blackbox.record("gesture", gesture="shoo", person=person.id if person else None, side=sign.side)
        self.life.events.add(now, f"{label} shooed you away with a hand")
        commands._spawn(commands.act(Request("back_off"), commands.asker_for(person.id if person else None), "gesture"))
