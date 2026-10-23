import asyncio
import base64
import logging
import re

from ..alive.reactions import about_looks

log = logging.getLogger(__name__)

MAX_SIDE = 640
CLOSE_SIDE = 1024
CLOSE_ZOOM = 4.0
TURN_DEG = 180.0
TIMEOUT_S = 60.0
ANSWER_TOKENS = 60
SYSTEM = (
    "You are looking through the camera of Pebble, a small home robot that sits on the floor. "
    "Answer the question about this picture in one short sentence of plain words. "
    "Only say what the picture clearly shows. If it does not show it clearly, say you can't tell. "
    "Never describe what anyone looks like, and never guess who someone is."
)
UNSURE = re.compile(r"\b(can't tell|cannot tell|can not tell|not sure|unclear|hard to (?:say|tell)|can't see|cannot see|can not see|don't know|do not know|unable|impossible to (?:say|tell))\b")
YES = re.compile(r"^\s*(yes|yeah|yep)\b", re.IGNORECASE)
FAR_PLACES = re.compile(r"\b(?:over there|across the room|on the (?:far |other )?wall|on the fridge|on the noticeboard|on the board|from here|far away|in the distance|up there|up on the shelf|on the top shelf|on the other side)\b")
FAR_THINGS = re.compile(r"\b(?:white ?board|black ?board|chalk ?board|notice ?board|board|clock|oven clock|wall clock|calendar|sign|poster|notice|menu|chart|timetable|screen|tv|telly|television)\b")
READING = re.compile(r"\b(?:say|says|said|read|written|writing|words?|numbers?|date|time|spell|label)\b")


def picture_message(question: str, jpeg: bytes) -> dict:
    url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
    return {"role": "user", "content": [{"type": "text", "text": question}, {"type": "image_url", "image_url": {"url": url}}]}


def wants_close(question: str) -> bool:
    text = " ".join(re.sub(r"[^a-z0-9 ]+", " ", str(question).lower()).split())
    if FAR_PLACES.search(text):
        return True
    return bool(READING.search(text) and FAR_THINGS.search(text))


class PictureQuestions:
    def __init__(self, eyes, mind, timeout_s: float = TIMEOUT_S, max_side: int = MAX_SIDE, closer=None, turn=None):
        self.eyes = eyes
        self.mind = mind
        self.timeout_s = timeout_s
        self.max_side = max_side
        self._closer = closer
        self._looked = closer is not None
        self.turn = turn
        self.close_how = ""
        self.guard = None

    def refused(self) -> str | None:
        guard = self.guard
        return guard.refusal() if guard is not None else None

    def closer(self):
        if not self._looked:
            self._looked = True
            from ..android.closeup import closeup_for

            self._closer = closeup_for(self.eyes)
        return self._closer

    async def can_look(self) -> bool:
        if not getattr(self.eyes, "available", False) or getattr(self.eyes, "snapshot", None) is None:
            return False
        sees = getattr(self.mind, "sees", None)
        if sees is None:
            return False
        try:
            return bool(await sees())
        except Exception:
            return False

    async def close_picture(self) -> bytes | None:
        closer = self.closer()
        if closer is None or not closer.available():
            self.close_how = "no close look on this body"
            return None
        if self.turn is None:
            self.close_how = "nothing to turn me round"
            return None
        if not await self.turn(TURN_DEG):
            self.close_how = "I could not turn round"
            return None
        picture = None
        try:
            picture = await closer.take(CLOSE_SIDE, CLOSE_ZOOM)
        except Exception:
            log.warning("the close look failed")
        finally:
            await self.turn(-TURN_DEG)
        self.close_how = "a close look with the back camera" if picture is not None else "the close look gave no picture"
        return picture

    async def ask(self, question: str, camera: str | None = None, close: bool | None = None) -> tuple[str, bool]:
        refused = self.refused()
        if refused:
            return refused, False
        if not await self.can_look():
            return "I can't look at pictures closely just now.", False
        self.close_how = ""
        picture = None
        if camera is None and (wants_close(question) if close is None else close):
            picture = await self.close_picture()
        if picture is None:
            try:
                picture = await self.eyes.snapshot(max_side=self.max_side, camera=camera)
            except Exception:
                picture = None
        refused = self.refused()
        if refused:
            return refused, False
        if picture is None:
            return "I can't get a clear look just now.", False
        if self.close_how:
            log.info("picture question: %s", self.close_how)
        messages = [{"role": "system", "content": SYSTEM}, picture_message(question, picture)]
        picture = None
        try:
            reply = await asyncio.wait_for(self.mind.chat(messages, purpose="look", max_tokens=ANSWER_TOKENS), self.timeout_s)
            text = " ".join((reply.text or "").split())
        except Exception:
            log.warning("the picture question could not be answered")
            text = ""
        finally:
            messages = None
        if not text or UNSURE.search(text.lower()) or about_looks(text):
            return "I can't tell from here.", False
        return text, True

    async def yes(self, question: str, camera: str | None = None) -> bool | None:
        answer, sure = await self.ask(question + " Answer yes or no first.", camera)
        if not sure:
            return None
        if YES.match(answer):
            return True
        if re.match(r"^\s*(no|nope)\b", answer, re.IGNORECASE):
            return False
        return None
