import math

HEARD_SHARE = 0.1
HEARD_KEEP_S = 90.0
CLOSED_AFTER_S = 180.0
ALONE_S = 300.0
AGAIN_S = 300.0
NOTICE_AFTER = 3


class CookingWatch:
    def __init__(self, house):
        self.house = house
        self.open = False
        self.began = 0.0
        self.heard_at = -math.inf
        self.seen_at = -math.inf
        self.minded_at = -math.inf
        self.said_at = -math.inf
        self.said = 0
        self.cook: str | None = None
        self.word = "cooking"
        self.noticed = False

    @property
    def on(self) -> bool:
        return bool(self.house.book.settings.get("cooking_watch", True))

    def active(self) -> bool:
        return self.open and self.said > 0

    def minded(self, mono: float, who: str | None = None) -> None:
        self.minded_at = mono
        if who:
            self.cook = who

    def tick(self, now: float, mono: float) -> None:
        if not self.on:
            self.open = False
            return
        house = self.house
        sounds = house.detector
        share = sounds.cooking_share() if sounds is not None else 0.0
        if share >= HEARD_SHARE:
            self.heard_at = mono
            self.word = sounds.cooking_word()
        cooks = house.cooks()
        if cooks:
            self.seen_at = mono
            self.minded(mono, cooks[0])
        elif house.someone_in_kitchen(now):
            self.minded_at = mono
        heard = mono - self.heard_at <= HEARD_KEEP_S
        seen = mono - self.seen_at <= HEARD_KEEP_S
        if not self.open:
            if heard or seen:
                self.open, self.began, self.said, self.noticed = True, mono, 0, False
                if self.minded_at < self.began - ALONE_S:
                    self.minded_at = mono
                house.record("cooking_watch", open=True, heard=heard, seen=seen)
            return
        if not heard and not seen and mono - max(self.heard_at, self.seen_at) >= CLOSED_AFTER_S:
            self.open = False
            house.record("cooking_watch", open=False, said=self.said)
            if self.said:
                house.note("the cooking sounds you were mentioning have stopped", False)
            return
        if share < HEARD_SHARE or house.alarm_going():
            return
        if mono - self.minded_at < ALONE_S or mono - self.said_at < AGAIN_S:
            return
        self._say(now, mono)

    def _say(self, now: float, mono: float) -> None:
        house = self.house
        minutes = max(5, int(round((mono - self.minded_at) / 60.0 / 5.0)) * 5)
        sound = {"sizzling": "Something's still sizzling", "boiling": "Something's still boiling"}.get(self.word, "I can still hear cooking")
        if self.said == 0:
            line = f"{sound}, and I haven't seen anyone in the kitchen for {minutes} minutes. I can't tell if that's okay, and I'm not a smoke alarm."
        else:
            line = f"{sound}, and I still haven't seen anyone in the kitchen. It's been {minutes} minutes."
        self.said += 1
        self.said_at = mono
        close = house.household_here(now)
        cook = house.person(self.cook) if self.cook else None
        to = cook.label if cook is not None and cook in close else (close[0].label if len(close) == 1 else None)
        house.say(line, to=to, urgent=True, why="cooking watch")
        house.note(f"cooking sounds have gone on with nobody seen in the kitchen for {minutes} minutes, so you said so (time {self.said})", True)
        house.record("cooking_said", minutes=minutes, times=self.said, sound=self.word)
        if self.said >= NOTICE_AFTER and not self.noticed and not close:
            self.noticed = True
            house.tell_owner("Pebble: cooking with nobody there", f"Pebble has heard cooking for a while with nobody in the kitchen ({minutes} minutes so far, at {house.hhmm(now)}). It is not a smoke alarm and can't tell if this is okay.")
