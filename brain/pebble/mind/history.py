import json
import logging
from dataclasses import dataclass

from ..self.notes import Notes
from ..selfstore import SelfStore
from .base import Mind
from .profile import ModelProfile
from .tokens import estimate_messages

log = logging.getLogger(__name__)

HISTORY = "conversation/history.json"
SOFT_SHARE = 0.75
KEEP_TALK = 4


@dataclass(frozen=True)
class Compaction:
    folded: int
    used_mind: bool


class History:
    def __init__(self, store: SelfStore, profile: ModelProfile, name: str = "Pebble"):
        self.store = store
        self.profile = profile
        self.name = name
        data = store.read(HISTORY, {})
        self.turns: list[dict] = [t for t in data.get("turns", []) if isinstance(t, dict) and isinstance(t.get("messages"), list)]
        self.compactions = int(data.get("compactions", 0))
        self.notes = Notes(store, name, str(data.get("summary") or ""))
        self.mover = lambda turns: 0
        self.talker = lambda: None

    @property
    def summary(self) -> str:
        return self.notes.text()

    def save(self) -> None:
        self.store.write(HISTORY, {"format": 2, "compactions": self.compactions, "turns": self.turns})

    def add_turn(self, messages: list[dict], at: str, **details) -> None:
        turn = {"at": at, "messages": messages}
        turn.update({key: value for key, value in details.items() if value not in (None, (), [])})
        self.turns.append(turn)
        self.save()

    def messages(self) -> list[dict]:
        return [message for turn in self.turns for message in turn["messages"]]

    def tokens(self) -> int:
        return estimate_messages(self.messages(), self.profile.chars_per_token)

    def needs_compaction(self, fixed_tokens: int, slack: int = 0) -> bool:
        return bool(self.turns) and fixed_tokens + self.tokens() >= self.profile.limits()[0] + slack

    def soft_due(self, fixed_tokens: int) -> bool:
        if not self.turns:
            return False
        compact, keep = self.profile.limits()
        size = self.tokens()
        return size > keep and fixed_tokens + size >= compact * SOFT_SHARE

    def _talking(self) -> str | None:
        try:
            return self.talker()
        except Exception:
            log.exception("could not tell who Pebble is talking to")
            return None

    def plan(self, everything: bool = False, oldest: int = 0) -> tuple[list[dict], list[dict]]:
        if everything:
            return list(self.turns), []
        if oldest > 0:
            return self.turns[:oldest], self.turns[oldest:]
        keep, size = [], 0
        budget = self.profile.limits()[1]
        for turn in reversed(self.turns):
            cost = estimate_messages(turn["messages"], self.profile.chars_per_token)
            if size + cost > budget:
                break
            keep.insert(0, turn)
            size += cost
        cut = len(self.turns) - len(keep)
        talking = self._talking()
        held = set()
        if talking:
            ours = [n for n, turn in enumerate(self.turns) if turn.get("by") == talking][-KEEP_TALK:]
            held = {n for n in ours if n < cut}
        fold = [turn for n, turn in enumerate(self.turns[:cut]) if n not in held]
        keep = [turn for n, turn in enumerate(self.turns) if n >= cut or n in held]
        if not fold:
            fold, keep = self.turns[:1], self.turns[1:]
        return fold, keep

    async def compact(self, mind: Mind | None = None, at: str = "", everything: bool = False, oldest: int = 0) -> Compaction:
        if not self.turns:
            return Compaction(0, False)
        fold, keep = self.plan(everything, oldest)
        try:
            self.mover(fold)
        except Exception:
            log.exception("could not move old turns into the memory stream")
        self.turns = keep
        self.compactions += 1
        self.save()
        return Compaction(len(fold), False)

    def hard_reset(self) -> None:
        self.turns = []
        self.save()

    def dump(self) -> str:
        return json.dumps({"notes": len(self.notes.items), "turns": len(self.turns)})
