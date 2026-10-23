from functools import lru_cache

from .elements import ELEMENTS, GRID, MAX_LINES, MOTIONS, PALETTE, SPEEDS

EXAMPLE = 'sky night\nstars 30 twinkle\nmoon 24 6 r4 pale\nhill 0 26 32 6 green\nrain 40 blue slow\ntext 3 28 "zzz" drift'


@lru_cache(maxsize=1)
def scene_guide() -> str:
    usage = "\n".join(f"{e.usage()}  - {e.about}" for e in ELEMENTS)
    return "\n".join(
        [
            f"You draw tiny animated pictures on a {GRID}x{GRID} pixel screen with a scene language.",
            f"Write 3 to {min(8, MAX_LINES)} lines and nothing else: one element per line, background first.",
            f"x goes 0-{GRID - 1} left to right, y goes 0-{GRID - 1} top to bottom. [square brackets] mean optional; keep the order.",
            "Colours: " + " ".join(PALETTE) + ".",
            "Motions: " + " ".join(MOTIONS) + ". Speeds: " + " ".join(SPEEDS) + ".",
            "Elements:",
            usage,
            "Example:",
            EXAMPLE,
        ]
    )


def scene_request(subject: str, card_line: str = "") -> str:
    parts = [f"Draw: {' '.join(subject.split())[:120]}."]
    if card_line:
        parts.append(card_line + ".")
    parts.append("Write the scene lines now.")
    return "\n".join(parts)
