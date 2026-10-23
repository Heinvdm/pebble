import asyncio

from ..body.api import Body
from ..chaos.levers import WHIM_SPIN_POWER
from ..chaos.whims import WHIM_KINDS
from ..seams.face import Face
from ..seams.voice import Voice
from ..tools.builtin import Permissions

HUMS = ("hm-hm-hmm", "doo-dee-doo", "la-la-laa", "hmm, hmm, hmmm")
SPIN_S = 0.8
PEEK_DEG = 15.0
PEEK_S = 0.9
WINK_S = 1.2


class WhimActs:
    def __init__(self, body: Body, voice: Voice, face: Face, permissions: Permissions, studio=None, stream=None):
        self.body = body
        self.voice = voice
        self.face = face
        self.permissions = permissions
        self.studio = studio
        self.stream = stream

    def spin_power(self) -> int:
        return round(WHIM_SPIN_POWER * self.body.profile.max_power)

    def available(self) -> tuple[str, ...]:
        kinds = {"hum", "wink"}
        if self.permissions.can_move:
            kinds.add("spin")
        if self.body.connected:
            kinds.add("peek")
        if self.studio is not None and self.studio.names():
            kinds.add("doodle")
        return tuple(kind for kind in WHIM_KINDS if kind in kinds)

    async def run(self, kind: str) -> dict:
        if kind == "hum":
            text = self.stream("whims").choice(HUMS) if self.stream else HUMS[0]
            await self.voice.say(text, whisper=False)
            return {"hummed": text}
        if kind == "spin":
            if not self.permissions.can_move:
                return {"skipped": "moving is off"}
            power = self.spin_power()
            report = await self.body.move(-power, power, SPIN_S)
            return report.as_dict()
        if kind == "peek":
            rest = self.body.profile.tilt_rest
            await self.body.tilt(rest + PEEK_DEG)
            await asyncio.sleep(PEEK_S)
            await self.body.tilt(rest)
            return {"peeked": True}
        if kind == "doodle":
            if self.studio is None:
                return {"skipped": "no screen"}
            return await self.studio.doodle()
        if kind == "wink":
            before = self.face.current
            self.face.show("mischief")
            await asyncio.sleep(WINK_S)
            if self.face.current == "mischief":
                self.face.show(before)
            return {"winked": True}
        return {"skipped": f"unknown whim {kind}"}
