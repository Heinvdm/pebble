from dataclasses import dataclass, field

HIGH = "high"
MEDIUM = "medium"
LOW = "low"
SEVERITIES = (HIGH, MEDIUM, LOW)


@dataclass(frozen=True)
class Notice:
    kind: str
    confidence: float
    source: str
    at: float
    text: str
    detail: dict = field(default_factory=dict)
    person: str | None = None

    def as_dict(self) -> dict:
        return {"kind": self.kind, "confidence": round(self.confidence, 2), "source": self.source, "text": self.text, "detail": dict(self.detail), "person": self.person}


@dataclass(frozen=True)
class Kind:
    name: str
    family: str
    severity: str
    plan: str
    noun: str
    word: str = ""


KINDS = {
    k.name: k
    for k in (
        Kind("smoke_alarm", "fire", HIGH, "alarm", "a smoke alarm going off", "SMOKE"),
        Kind("alarm_beeping", "fire", HIGH, "alarm", "steady beeping, like an alarm", "ALARM"),
        Kind("alarm_sound", "fire", HIGH, "alarm", "what sounded like an alarm", "ALARM"),
        Kind("heat_rise", "fire", HIGH, "alarm", "the air near the floor warming fast", "HEAT"),
        Kind("gas_spike", "fire", HIGH, "alarm", "a sudden smell in the air, like smoke or fumes", "SMOKE"),
        Kind("fire_word", "fire", HIGH, "alarm", "someone shouting fire", "FIRE"),
        Kind("smoke_seen", "fire", HIGH, "alarm", "what looks like smoke or flames", "FIRE"),
        Kind("co_alarm", "co", HIGH, "alarm", "a carbon monoxide alarm going off", "CO"),
        Kind("help", "help", HIGH, "help", "someone calling for help", "HELP"),
        Kind("name_shouted", "help", HIGH, "help", "someone shouting my name", "HELP"),
        Kind("screaming", "help", HIGH, "help", "someone screaming", "HELP"),
        Kind("shouting", "help", MEDIUM, "help", "shouting", "HELP"),
        Kind("on_floor", "floor", HIGH, "help", "someone lying on the floor", "HELP"),
        Kind("glass", "glass", MEDIUM, "look", "what sounded like glass breaking"),
        Kind("baby", "baby", LOW, "look", "a baby crying for a while"),
        Kind("dog", "dog", LOW, "look", "a dog barking for a long time"),
        Kind("water", "water", LOW, "tell", "water running for a long time"),
        Kind("quake", "quake", HIGH, "quake", "the floor shaking, like an earthquake", "QUAKE"),
        Kind("stranger", "stranger", MEDIUM, "notify", "a stranger, while nobody familiar is home"),
    )
}


def kind_of(name: str) -> Kind | None:
    return KINDS.get(name)
