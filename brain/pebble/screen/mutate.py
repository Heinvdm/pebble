from ..chaos.levers import mutation_jitter, mutation_tweaks
from .elements import MAX_LINES, REGISTRY
from .parse import Scene, SceneLine

MUTABLE = ("num", "radius", "colour", "motion", "speed", "word")


def _tweak(line: SceneLine, rng, jitter: int) -> SceneLine:
    element = REGISTRY[line.element]
    slots = [slot for slot in element.slots if slot.kind in MUTABLE]
    if not slots:
        return line
    slot = slots[rng.randrange(len(slots))]
    values = dict(line.values)
    current = values[slot.name]
    if slot.kind in ("num", "radius"):
        step = rng.randint(-jitter, jitter) or 1
        values[slot.name] = max(slot.lo, min(slot.hi, current + step))
    else:
        others = [choice for choice in slot.choices() if choice != current]
        if others:
            values[slot.name] = others[rng.randrange(len(others))]
    return SceneLine(line.element, values)


def mutate(scene: Scene, rng, level: float) -> Scene:
    lines = list(scene.lines)
    if not lines:
        return scene
    jitter = mutation_jitter(level)
    for _ in range(mutation_tweaks(level)):
        index = rng.randrange(len(lines))
        lines[index] = _tweak(lines[index], rng, jitter)
    return Scene(tuple(lines))


def _layers(scene: Scene) -> tuple[list[SceneLine], list[SceneLine]]:
    back = [line for line in scene.lines if REGISTRY[line.element].layer == "back"]
    front = [line for line in scene.lines if REGISTRY[line.element].layer == "front"]
    return back, front


def remix(first: Scene, second: Scene) -> Scene:
    back, _ = _layers(first)
    _, front = _layers(second)
    lines = (back + front)[:MAX_LINES]
    return Scene(tuple(lines))
