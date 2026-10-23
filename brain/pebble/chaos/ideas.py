from dataclasses import dataclass

from ..selfstore import SelfStore
from .levers import card_chance, second_card_chance

IDEAS = "ideas.json"
DECKS = ("theme", "constraint", "voice")
FOR_KIND = {"drawing": ("theme", "constraint"), "talk": ("theme", "voice"), "joke": ("theme", "voice")}


@dataclass(frozen=True)
class Card:
    deck: str
    id: str
    text: str

    def as_dict(self) -> dict:
        return {"deck": self.deck, "id": self.id, "text": self.text}


class IdeaDecks:
    def __init__(self, decks: dict[str, tuple[Card, ...]] | None = None):
        self.decks = {name: cards for name, cards in (decks or {}).items() if cards}

    @classmethod
    def from_dict(cls, data: dict | None) -> "IdeaDecks":
        decks: dict[str, tuple[Card, ...]] = {}
        for name, cards in ((data or {}).get("decks") or {}).items():
            if name not in DECKS or not isinstance(cards, list):
                continue
            clean = []
            for raw in cards:
                if isinstance(raw, dict) and str(raw.get("text", "")).strip():
                    clean.append(Card(name, str(raw.get("id") or len(clean)), " ".join(str(raw["text"]).split())[:120]))
            decks[name] = tuple(clean)
        return cls(decks)

    @classmethod
    def open(cls, store: SelfStore) -> "IdeaDecks":
        return cls.from_dict(store.read(IDEAS, {}) or {})

    def size(self) -> int:
        return sum(len(cards) for cards in self.decks.values())

    def draw(self, stream, level: float, kind: str = "drawing") -> list[Card]:
        wanted = [deck for deck in FOR_KIND.get(kind, ("theme",)) if deck in self.decks]
        if not wanted or stream.random() >= card_chance(level):
            return []
        first_deck = stream.choice(wanted)
        cards = [self._card(first_deck, stream)]
        others = [deck for deck in wanted if deck != first_deck]
        if others and stream.random() < second_card_chance(level):
            cards.append(self._card(stream.choice(others), stream))
        return cards

    def _card(self, deck: str, stream) -> Card:
        cards = self.decks[deck]
        return cards[stream.randrange(len(cards))]


def card_text(cards: list[Card]) -> str:
    if not cards:
        return ""
    return "Idea card: " + "; ".join(f"{card.deck}: {card.text}" for card in cards)
