import math
from collections import deque
from dataclasses import dataclass, field

NIGHT_KNOCKS = 3
NIGHT_WINDOW_S = 120.0
NIGHT_TOLD_GAP_S = 1800.0
SAME_GAP_S = 120.0
WAIT_FOR_PAUSE_S = 20.0
NOW = {
    "knock": "Someone's knocking at the door.",
    "doorbell": "The doorbell just rang.",
    "microwave": "The microwave's done.",
    "phone": "A phone's ringing.",
    "kettle": "The kettle's whistling.",
    "alarm_clock": "An alarm clock has been ringing for five minutes.",
}
URGENT = frozenset({"knock", "doorbell", "alarm_clock"})
LOGGED = {"knock": "a knock at the door", "doorbell": "the doorbell rang", "microwave": "the microwave finished", "phone": "a phone rang", "kettle": "the kettle whistled", "alarm_clock": "an alarm clock rang for a long time"}
DOOR = {"knock": "a knock at the door", "doorbell": "the doorbell ring"}
NOT_IN_QUIET = frozenset({"microwave", "phone", "kettle"})


@dataclass
class Line:
    text: str
    to: str | None
    urgent: bool
    kind: str
    due: float
    people: tuple = ()


@dataclass
class Teller:
    house: object
    outbox: list = field(default_factory=list)
    knocks: deque = field(default_factory=deque)
    night_told: float = -math.inf
    said: dict = field(default_factory=dict)

    @property
    def life(self):
        return self.house.life

    def sound(self, event: str, mono: float, now: float, quiet: bool, detail: dict | None = None) -> None:
        house = self.house
        if event in DOOR and quiet:
            self._night_knock(mono, now, event)
            return
        if event == "rain":
            if (detail or {}).get("phase") == "start":
                house.away.add("rain", "it started raining", now)
                self._rain(mono, now, quiet)
            return
        if event in ("meowing", "dog_crying"):
            house.pets.spell(event, detail or {}, mono, now)
            return
        if event == "thunder":
            house.away.add("thunder", "thunder", now)
            return
        if event == "alarm_clock" and (detail or {}).get("phase") != "start":
            return
        house.away.add(event, LOGGED.get(event, event), now)
        if event == "knock":
            house.note("you heard someone knocking at the door", True)
        if quiet and event in NOT_IN_QUIET:
            return
        watchers = house.watchers.take(event, now)
        if watchers:
            self.to_people(NOW.get(event, ""), watchers, event, mono, LOGGED.get(event, event))
            return
        if event == "phone" and house.someone_on_phone():
            return
        self.to_household(NOW.get(event, ""), event, mono, urgent=event in URGENT)

    def _night_knock(self, mono: float, now: float, event: str = "knock") -> None:
        house = self.house
        self.knocks.append((mono, event))
        while self.knocks and mono - self.knocks[0][0] > NIGHT_WINDOW_S:
            self.knocks.popleft()
        heard = DOOR.get(event, DOOR["knock"])
        house.away.add(event, "the doorbell rang" if event == "doorbell" else heard, now)
        stamp = house.hhmm(now)
        if len(self.knocks) < NIGHT_KNOCKS or mono - self.night_told < NIGHT_TOLD_GAP_S:
            house.note(f"you heard {heard} at {stamp}, in quiet hours; you noted it for the morning", False)
            house.diary(f"During the night I heard {heard} ({stamp}).")
            return
        ringing = any(kind == "doorbell" for _, kind in self.knocks)
        what = "knocking or ringing at the door" if ringing else "knocking at the door"
        self.night_told = mono
        self.knocks.clear()
        inner = house.inner_here(now)
        to = inner[0].label if inner else None
        line = f"Someone has been {what}: three times in two minutes. I won't open it."
        house.say(line, to=to, urgent=True, why="night knocks")
        house.tell_owner(f"Pebble: {what}", f"Pebble heard {what} three times in two minutes at {stamp}. It did not open the door.")
        house.note(f"someone was {what} three times in two minutes at {stamp}, at night; you said so out loud and told your owner if notices are on", True)
        house.diary(f"In the night someone was {what} three times in two minutes ({stamp}). I said so, and I did not open the door.")

    def _rain(self, mono: float, now: float, quiet: bool) -> None:
        house = self.house
        watchers = house.watchers.take("rain", now)
        if not watchers or quiet:
            return
        self.to_people("It's started raining, and you said the washing is out.", watchers, "rain", mono, "it started raining")

    def to_people(self, text: str, people: list, kind: str, mono: float, logged: str = "") -> None:
        house = self.house
        now = house.clock.now()
        here = {p.id for p in house.household_here(now)}
        for person_id, label in people:
            if person_id in here:
                self._queue(Line(text, label, kind in URGENT, kind, mono, (person_id,)))
            else:
                house.away.add(kind, logged or house.away_words(kind, text), now, person=person_id)

    def to_household(self, text: str, kind: str, mono: float, urgent: bool = False) -> bool:
        house = self.house
        now = house.clock.now()
        if not text or mono - self.said.get(kind, -math.inf) < SAME_GAP_S:
            return False
        here = house.household_here(now)
        if not here:
            return False
        self.said[kind] = mono
        to = here[0].label if len(here) == 1 else None
        self._queue(Line(text, to, urgent, kind, mono))
        return True

    def _queue(self, line: Line) -> None:
        self.outbox.append(line)
        self.flush(line.due)

    def flush(self, mono: float) -> None:
        house = self.house
        kept = []
        for line in self.outbox:
            if not line.urgent and house.talking() and mono - line.due < WAIT_FOR_PAUSE_S:
                kept.append(line)
                continue
            house.say(line.text, to=line.to, urgent=line.urgent, why=line.kind)
        self.outbox = kept
