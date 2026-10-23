import math

GONE_S = 120.0
LONGEST_S = 2 * 3600.0
LINE_MAX = 90


class Captions:
    def __init__(self, house):
        self.house = house
        self.for_id: str | None = None
        self.since = -math.inf
        self.lines: list[str] = []
        self.shown = ""

    @property
    def on(self) -> bool:
        return self.for_id is not None

    def start(self, person_id: str | None, mono: float) -> str:
        if person_id is None:
            return "I can't tell who's asking, and captions only show while the person who asked is here. Tell me your name first?"
        self.for_id, self.since, self.lines = person_id, mono, []
        self.house.record("captions", on=True, person=person_id)
        return "Okay. I'll show what people say on my screen while you're here. I don't keep any of it, and I'm not always right."

    def stop(self, why: str = "asked") -> str:
        if self.for_id is None:
            return "Captions weren't on."
        self.for_id, self.lines = None, []
        if self.shown:
            self.house.layer.clear(self.shown)
            self.shown = ""
        self.house.record("captions", on=False, why=why)
        return "Okay, captions off."

    def heard(self, heard, mono: float) -> None:
        if self.for_id is None or getattr(heard, "private", False):
            return
        text = " ".join(str(getattr(heard, "text", "")).split())[:LINE_MAX]
        if not text:
            return
        label = getattr(heard, "label", "")
        line = f"{label}: {text}" if label and label != "someone" else text
        self.lines = (self.lines + [line])[-2:]
        self.shown = self.house.layer.caption(list(self.lines))

    def tick(self, now: float, mono: float) -> None:
        if self.for_id is None:
            return
        presence = self.house.life.company.presence
        if now - presence.last_present(self.for_id) > GONE_S or mono - self.since > LONGEST_S:
            self.stop("the person who asked is not here")
