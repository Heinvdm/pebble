import math
from collections import deque

from ..activities.base import Ending
from ..activities.trying import Try
from ..alive.gestures import GestureReader, body_point

LOOK_S = 0.2
HISTORY_S = 8.0
TURN_BACK_S = 8.0
CROUCH_GAP_S = 4.0
NOD_S = 2.5
NOD_SWINGS = 2
NOD_DEG = 0.8
STEP_S = 5.0
STEP_DROP = 0.12
MOVES_MOST = 8
COPIES = {
    "turn round": [{"do": "turn", "way": "around", "degrees": 360}],
    "wave": [{"do": "wiggle"}],
    "crouch": [{"do": "tilt", "way": "down", "degrees": 25}, {"do": "wait", "seconds": 1}, {"do": "tilt", "way": "up", "degrees": 5}],
    "nod": [{"do": "tilt", "way": "down", "degrees": 15}, {"do": "tilt", "way": "up", "degrees": 10}],
    "point left": [{"do": "turn", "way": "left", "degrees": 45}],
    "point right": [{"do": "turn", "way": "right", "degrees": 45}],
    "step": [{"do": "move", "way": "back", "metres": 0.1}, {"do": "move", "way": "forward", "metres": 0.1}],
}


def swings(values: list, amplitude: float) -> int:
    if len(values) < 3:
        return 0
    turns, direction, edge = 0, 0, values[0]
    for value in values[1:]:
        if direction >= 0 and value < edge - amplitude:
            turns += 1 if direction > 0 else 0
            direction, edge = -1, value
        elif direction <= 0 and value > edge + amplitude:
            turns += 1 if direction < 0 else 0
            direction, edge = 1, value
        elif (direction > 0 and value > edge) or (direction < 0 and value < edge):
            edge = value
    return turns


class Moves:
    def __init__(self):
        self.gestures = GestureReader()
        self.rows: deque = deque()
        self.away_since: float | None = None
        self.crouched = -math.inf
        self.nodded = -math.inf
        self.stepped = -math.inf
        self.tall: float | None = None

    def read(self, person, at: float) -> list[str]:
        found = []
        nose = body_point(person, "nose")
        left, right = body_point(person, "left_shoulder"), body_point(person, "right_shoulder")
        lift = None
        if nose is not None and left is not None and right is not None:
            lift = nose.elevation_deg - (left.elevation_deg + right.elevation_deg) / 2.0
        self.rows.append((at, person.facing_deg, person.height_frac, lift))
        while self.rows and at - self.rows[0][0] > HISTORY_S:
            self.rows.popleft()
        facing = person.facing_deg
        if facing is not None:
            if abs(facing) >= 120.0 and self.away_since is None:
                self.away_since = at
            elif abs(facing) <= 60.0 and self.away_since is not None:
                if at - self.away_since <= TURN_BACK_S:
                    found.append("turn round")
                self.away_since = None
        for gesture in self.gestures.read(person, at):
            if gesture.kind == "wave":
                found.append("wave")
            elif gesture.kind == "point":
                found.append("point left" if gesture.side == "left" else "point right")
        if person.posture == "crouching" and person.posture_score >= 0.5 and at - self.crouched >= CROUCH_GAP_S:
            self.crouched = at
            found.append("crouch")
        lifts = [row[3] for row in self.rows if row[3] is not None and at - row[0] <= NOD_S]
        if at - self.nodded >= NOD_S and swings(lifts, NOD_DEG) >= NOD_SWINGS and person.posture != "crouching":
            self.nodded = at
            self.rows = deque((t, f, h, None) for t, f, h, _ in self.rows)
            found.append("nod")
        heights = [row[2] for row in self.rows if at - row[0] <= STEP_S]
        if self.tall is None or person.height_frac > self.tall:
            self.tall = person.height_frac if self.tall is None else max(self.tall * 0.98, person.height_frac)
        if heights and at - self.stepped >= STEP_S and person.posture != "crouching":
            low = min(heights)
            first, last = heights[0], heights[-1]
            if first > 0 and (first - low) / first >= STEP_DROP and (last - low) / first >= STEP_DROP * 0.8:
                self.stepped = at
                self.rows.clear()
                found.append("step")
        return found


class Mimic(Try):
    kind = "copy_me"

    def __init__(self, request, asker, target=None, battery=False, steps=(), name="copy me", gate=None, run_step=None, seconds: float = 45.0):
        super().__init__(request, asker, target, battery, steps, name, gate, run_step)
        self.seconds = seconds
        self.track: int | None = None
        self.copied: list = []
        self.moves: list = []
        self.done = False

    def describe(self) -> str:
        return "playing copy me"

    def adjust(self, request):
        if request.change in ("enough", "stay"):
            self.done = True
            return "Okay, that was fun.", None
        return "", None

    def _person(self, sight):
        if not sight.people:
            return None
        if self.track is not None:
            for person in sight.people:
                if person.track == self.track:
                    return person
        return max(sight.people, key=lambda p: p.height_frac)

    async def run(self, kit) -> Ending:
        moves = Moves()
        end = kit.pace.now() + self.seconds
        try:
            while kit.pace.now() < end and not self.done and len(self.moves) < MOVES_MOST:
                sight = kit.eyes.latest(0.6)
                person = self._person(sight) if sight is not None else None
                if person is not None:
                    for move in moves.read(person, kit.pace.now()):
                        steps = COPIES.get(move) or []
                        did = []
                        for step in steps:
                            refused, target = await self.gate(step, self.asker)
                            if refused is not None:
                                continue
                            await self.run_step(step, kit, self, target)
                            did.append(dict(step))
                        if did:
                            self.moves.append(move)
                            self.copied.extend(did)
                            end = max(end, kit.pace.now() + 15.0)
                await kit.pace.sleep(LOOK_S)
            return Ending("done", f"you played copy me and copied {len(self.moves)} moves" + (f" ({', '.join(self.moves)})" if self.moves else ""), "")
        finally:
            if self.tilted:
                await kit.body.tilt(kit.body.profile.tilt_rest)
