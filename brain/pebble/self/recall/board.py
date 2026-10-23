from dataclasses import dataclass

from ...mind.budget import BOARD, PIXEL_WINDOW, REPLY, budgets
from ...mind.select import chars
from .stream import Record, visible

MOST = 3
BOARD_LINE = "Things on your mind (others' words stay theirs): "
DEEP_LINE = "You thought back (others' words stay theirs): "
ROW_CHARS = chars(budgets(REPLY, PIXEL_WINDOW)[BOARD])
BUDGET_CHARS = ROW_CHARS - len(BOARD_LINE)


@dataclass(frozen=True)
class Note:
    text: str
    kind: str = "memory"
    record: Record | None = None

    def allowed(self, audience: frozenset, now: float) -> bool:
        return self.record is None or visible(self.record, audience, now)


def fit(notes: list[Note], budget: int = BUDGET_CHARS, most: int = MOST) -> list[Note]:
    kept, used = [], 0
    for note in notes:
        text = " ".join(note.text.split())
        if not text or any(text == other.text for other in kept):
            continue
        if used + len(text) > budget:
            continue
        kept.append(Note(text, note.kind, note.record))
        used += len(text) + 3
        if len(kept) >= most:
            break
    return kept


def block(notes: list[Note], lead: str = BOARD_LINE) -> str:
    return lead + " / ".join(n.text for n in notes) if notes else ""


class Board:
    def __init__(self):
        self.live: tuple[Note, ...] = ()
        self.next: tuple[Note, ...] | None = None
        self.offers = 0

    def offer(self, notes: list[Note]) -> bool:
        chosen = tuple(fit(notes))
        if chosen == self.live:
            self.next = None
            return False
        self.next = chosen
        self.offers += 1
        return True

    def waiting(self) -> bool:
        return self.next is not None

    def swap(self) -> bool:
        if self.next is None:
            return False
        self.live, self.next = self.next, None
        return True

    def notes(self, audience: frozenset, now: float) -> list[Note]:
        return [n for n in self.live if n.allowed(audience, now)]

    def text(self, audience: frozenset, now: float) -> str:
        return block(self.notes(audience, now))
