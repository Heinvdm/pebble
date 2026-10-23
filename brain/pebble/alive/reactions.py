import re

from ..respect import harsh
from ..tact import tactless

HOUR_S = 3600.0
SPOKEN_PER_HOUR = 4
SPOKEN_GAP_S = 90.0
BODY = re.compile(
    r"\b(fat|skinny|chubby|ugly|wrinkl\w*|bald\w*|hair\w*|weight|bodies|body|skin|teeth|belly|tummy|bum|butt|chest|breasts?|makeup|spotty|pimples?|tattoos?|beard|moustache|pregnant|disabled|wheelchair|limp)\b"
)
SOFT = re.compile(
    r"\b(?:you|she|he|they|her|his|their|your|someone|somebody|person|people|man|woman|boy|girl|kid|child)\b(?:\W+\w+){0,3}?\W+(?:look|looks|looked|thin|slim|pretty|beautiful|handsome|cute|gorgeous|hot|sexy|old|young|tall|short|face|nose|legs?|arms?|figure|outfit|clothes|dress)\b"
)


def about_looks(text: str) -> bool:
    lowered = text.lower()
    return bool(BODY.search(lowered) or SOFT.search(lowered)) or tactless(text)


class Reactions:
    def __init__(self, per_hour: int = SPOKEN_PER_HOUR, gap_s: float = SPOKEN_GAP_S):
        self.per_hour = per_hour
        self.gap_s = gap_s
        self.spoken: list[float] = []
        self.refused: dict[str, int] = {}

    def may_speak(self, now: float, quiet: bool, hushed: bool = False) -> bool:
        self.spoken = [at for at in self.spoken if now - at < HOUR_S]
        if quiet or hushed:
            return False
        if len(self.spoken) >= self.per_hour:
            return False
        return not self.spoken or now - self.spoken[-1] >= self.gap_s

    def speak(self, text: str, now: float, quiet: bool, hushed: bool = False, chance: float = 1.0, roll: float = 0.0) -> str:
        if not text or about_looks(text):
            self.refused["looks"] = self.refused.get("looks", 0) + 1
            return ""
        if harsh(text):
            self.refused["life"] = self.refused.get("life", 0) + 1
            return ""
        why = "chance" if roll >= chance else ("quiet" if quiet else ("hushed" if hushed else ("budget" if not self.may_speak(now, quiet, hushed) else "")))
        if why:
            self.refused[why] = self.refused.get(why, 0) + 1
            return ""
        self.spoken.append(now)
        return text

    def left(self, now: float) -> int:
        return max(0, self.per_hour - len([at for at in self.spoken if now - at < HOUR_S]))

    def next_in(self, now: float) -> float:
        if not self.spoken:
            return 0.0
        return max(0.0, self.gap_s - (now - self.spoken[-1])) if len(self.spoken) < self.per_hour else max(0.0, HOUR_S - (now - self.spoken[0]))
