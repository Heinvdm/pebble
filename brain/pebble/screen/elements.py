from dataclasses import dataclass, field

GRID = 32
MAX_LINES = 10
MAX_TEXT = 12
TEXT_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 !?.,'+:-"
PALETTE = {
    "black": "#0b0e1a",
    "white": "#f4f4ee",
    "pale": "#e8dfb8",
    "red": "#ef4646",
    "pink": "#ff7eb6",
    "yellow": "#ffd23f",
    "green": "#3fbf5f",
    "blue": "#3b8bf6",
}
MOTIONS = ("still", "twinkle", "drift", "bounce", "pulse", "sway", "spin")
SPEEDS = ("slow", "normal", "fast")
KINDS = ("num", "radius", "colour", "motion", "speed", "text", "word")
LAYERS = ("back", "front")


@dataclass(frozen=True)
class Slot:
    name: str
    kind: str
    lo: int = 0
    hi: int = 0
    words: tuple[str, ...] = ()
    default: object = None

    @property
    def required(self) -> bool:
        return self.default is None

    def choices(self) -> tuple[str, ...]:
        if self.kind == "colour":
            return tuple(PALETTE)
        if self.kind == "motion":
            return MOTIONS
        if self.kind == "speed":
            return SPEEDS
        return self.words

    def describe(self) -> str:
        if self.kind == "num":
            return self.name if (self.lo, self.hi) == (0, GRID - 1) else f"{self.name} {self.lo}-{self.hi}"
        if self.kind == "radius":
            return f"r{self.lo}-r{self.hi}"
        if self.kind == "text":
            return f'"text" up to {MAX_TEXT} letters'
        if self.kind in ("colour", "motion", "speed"):
            return self.kind
        return "|".join(self.words)

    def as_dict(self) -> dict:
        out = {"name": self.name, "kind": self.kind, "default": self.default}
        if self.kind in ("num", "radius"):
            out["lo"], out["hi"] = self.lo, self.hi
        if self.kind == "word":
            out["words"] = list(self.words)
        return out


@dataclass(frozen=True)
class Element:
    name: str
    slots: tuple[Slot, ...]
    about: str
    example: str
    layer: str = "front"
    extra: dict = field(default_factory=dict)

    def slot(self, name: str) -> Slot | None:
        return next((s for s in self.slots if s.name == name), None)

    def usage(self) -> str:
        parts = [self.name]
        for slot in self.slots:
            parts.append(slot.describe() if slot.required else f"[{slot.describe()}]")
        return " ".join(parts)

    def as_dict(self) -> dict:
        return {"slots": [s.as_dict() for s in self.slots], "layer": self.layer, "about": self.about, "example": self.example}


def num(name: str, lo: int, hi: int, default: int | None = None) -> Slot:
    return Slot(name, "num", lo, hi, default=default)


def radius(lo: int, hi: int, default: int) -> Slot:
    return Slot("r", "radius", lo, hi, default=default)


def colour(default: str) -> Slot:
    return Slot("colour", "colour", default=default)


def motion(default: str) -> Slot:
    return Slot("motion", "motion", default=default)


def speed(default: str = "normal") -> Slot:
    return Slot("speed", "speed", default=default)


def word(name: str, words: tuple[str, ...], default: str | None = None) -> Slot:
    return Slot(name, "word", words=words, default=default)


X = num("x", 0, GRID - 1)
Y = num("y", 0, GRID - 1)
TEXT = Slot("text", "text")

ELEMENTS = (
    Element("sky", (word("look", ("day", "night", "dusk", "dawn", "storm", "space")),), "fills the whole background", "sky night", "back"),
    Element("stars", (num("n", 1, 60, 20), colour("white"), motion("twinkle")), "a field of little stars", "stars 30 twinkle", "back"),
    Element("moon", (X, Y, radius(1, 8, 3), colour("pale"), motion("still")), "a moon with craters", "moon 24 6 r4 pale"),
    Element("sun", (X, Y, radius(1, 8, 4), colour("yellow"), motion("spin")), "a sun with rays", "sun 6 6 r4 yellow spin"),
    Element("cloud", (X, Y, num("w", 4, 20, 8), colour("white"), motion("drift")), "a puffy cloud w wide", "cloud 4 5 10 white drift"),
    Element("rain", (num("n", 1, 60, 30), colour("blue"), speed()), "rain falling over everything", "rain 40 blue slow", "back"),
    Element("snow", (num("n", 1, 60, 30), colour("white"), speed("slow")), "snow drifting down", "snow 25 white slow", "back"),
    Element("fire", (X, Y, num("w", 2, 16, 6), colour("red")), "flickering flames standing on y", "fire 16 28 8 red"),
    Element("waves", (num("y", 0, GRID - 1, 24), colour("blue"), speed()), "sea from y to the bottom", "waves 22 blue slow", "back"),
    Element("hill", (X, Y, num("w", 1, GRID), num("h", 1, GRID), colour("green")), "a rounded hill w wide and h tall", "hill 0 26 32 6 green", "back"),
    Element("grass", (num("y", 0, GRID - 1, 28), colour("green"), motion("sway")), "grass from y to the bottom", "grass 28 green sway", "back"),
    Element("tree", (X, Y, num("h", 4, 24, 10), colour("green"), motion("sway")), "a tree standing on y, h tall", "tree 6 27 12 green sway"),
    Element("flower", (X, Y, colour("pink"), motion("sway")), "a flower standing on y", "flower 20 28 pink sway"),
    Element("heart", (X, Y, radius(1, 8, 3), colour("red"), motion("pulse")), "a heart", "heart 16 14 r5 red pulse"),
    Element("star", (X, Y, radius(1, 8, 3), colour("yellow"), motion("twinkle")), "one big star shape", "star 16 10 r4 yellow spin"),
    Element("circle", (X, Y, radius(1, 16, 3), colour("white"), motion("still")), "a filled circle", "circle 16 16 r6 blue bounce"),
    Element("ring", (X, Y, radius(1, 16, 4), colour("white"), motion("pulse")), "a circle outline", "ring 16 16 r8 pink pulse"),
    Element("rect", (X, Y, num("w", 1, GRID), num("h", 1, GRID), colour("white"), motion("still")), "a filled box from x y, w by h", "rect 0 28 32 4 black"),
    Element("line", (X, Y, num("x2", 0, GRID - 1), num("y2", 0, GRID - 1), colour("white"), motion("still")), "a line from x y to x2 y2", "line 2 30 29 30 white"),
    Element("dot", (X, Y, colour("white"), motion("twinkle")), "one pixel", "dot 9 4 yellow twinkle"),
    Element("text", (X, Y, TEXT, colour("white"), motion("still")), "a few words from x y (4 px a letter)", 'text 3 28 "zzz" drift'),
    Element("sparkle", (X, Y, colour("yellow"), motion("twinkle")), "a glinting sparkle", "sparkle 26 4 white twinkle"),
    Element("bubbles", (num("n", 1, 40, 12), colour("white"), speed()), "bubbles rising", "bubbles 15 white slow", "back"),
    Element("fish", (X, Y, colour("yellow"), motion("drift")), "a little fish swimming", "fish 10 24 yellow drift"),
    Element("bird", (X, Y, colour("black"), motion("drift")), "a bird flapping", "bird 8 8 black drift"),
    Element("eyes", (X, Y, word("look", ("open", "happy", "sleepy", "wide", "closed"), "open"), colour("white"), motion("still")), "a pair of eyes that blink", "eyes 16 12 happy white"),
    Element("mouth", (X, Y, word("shape", ("smile", "frown", "flat", "o", "wavy"), "smile"), colour("white"), motion("still")), "a mouth", "mouth 16 20 smile white"),
    Element("zzz", (X, Y, colour("white")), "sleepy z's rising from x y", "zzz 22 10 white"),
    Element("lightning", (X, colour("yellow")), "a bolt that strikes now and then at x", "lightning 20 yellow", "back"),
    Element("rainbow", (X, Y, radius(4, 16, 10), motion("still")), "a rainbow arc centred on x y", "rainbow 16 28 r12"),
    Element("particles", (num("n", 1, 60, 20), colour("pale"), motion("drift")), "floating specks everywhere", "particles 25 pink drift", "back"),
    Element("confetti", (num("n", 1, 60, 30), speed()), "colourful confetti falling", "confetti 40 fast", "back"),
    Element("firework", (X, Y, colour("pink")), "a firework bursting at x y now and then", "firework 16 8 pink"),
    Element("note", (X, Y, colour("white"), motion("bounce")), "a music note", "note 24 8 white bounce"),
)
REGISTRY = {element.name: element for element in ELEMENTS}


class RegistryError(ValueError):
    pass


def _accepts(slot: Slot, other: Slot) -> bool:
    if slot.kind != other.kind:
        return False
    if slot.kind == "word":
        return bool(set(slot.words) & set(other.words))
    return True


def check_registry(elements: tuple[Element, ...] = ELEMENTS) -> None:
    names = set()
    fixed = set(PALETTE) | set(MOTIONS) | set(SPEEDS)
    for element in elements:
        if element.name in names:
            raise RegistryError(f"{element.name} is listed twice")
        names.add(element.name)
        if element.layer not in LAYERS:
            raise RegistryError(f"{element.name} has an unknown layer")
        for index, slot in enumerate(element.slots):
            if slot.kind not in KINDS:
                raise RegistryError(f"{element.name}.{slot.name} has an unknown kind")
            if slot.kind == "word" and (not slot.words or set(slot.words) & fixed):
                raise RegistryError(f"{element.name}.{slot.name} words must be new words")
            if slot.default is not None and slot.kind in ("num", "radius") and not slot.lo <= slot.default <= slot.hi:
                raise RegistryError(f"{element.name}.{slot.name} default is out of range")
            if slot.default is not None and slot.kind not in ("num", "radius", "text") and slot.default not in slot.choices():
                raise RegistryError(f"{element.name}.{slot.name} default is not a choice")
            if slot.required and any(not s.required for s in element.slots[:index]):
                raise RegistryError(f"{element.name}.{slot.name}: required slots come before optional ones")
            if not slot.required:
                for later in element.slots[index + 1 :]:
                    if _accepts(slot, later):
                        raise RegistryError(f"{element.name}.{slot.name} and {later.name} could be confused")


def registry_dict() -> dict:
    return {
        "grid": GRID,
        "maxLines": MAX_LINES,
        "maxText": MAX_TEXT,
        "textChars": TEXT_CHARS,
        "palette": dict(PALETTE),
        "motions": list(MOTIONS),
        "speeds": list(SPEEDS),
        "elements": {element.name: element.as_dict() for element in ELEMENTS},
    }


check_registry()
