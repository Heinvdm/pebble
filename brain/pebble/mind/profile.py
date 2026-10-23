import json
from dataclasses import dataclass, field
from pathlib import Path

from .budget import compaction

MIN_COMPACT_TOKENS = 200


@dataclass(frozen=True)
class ModelProfile:
    name: str
    role: str = "conscious"
    endpoint: str = "http://127.0.0.1:8080"
    model: str = ""
    model_file: str = ""
    context_tokens: int = 4096
    compact_at_tokens: int = 0
    keep_tokens_after_compaction: int = 0
    summary_tokens: int = 300
    max_reply_tokens: int = 200
    temperature: float = 0.7
    timeout_s: float = 120.0
    chars_per_token: float = 4.0
    system_role: bool = True
    tools: bool = True
    extra_body: dict = field(default_factory=dict)
    reply_shares_turn: bool = False
    steady_tools: bool = False
    people_in_message: bool = False
    read_ahead: bool = False
    reader_examples: int = 0
    fold_picks: bool = False
    notes: str = ""
    served: dict = field(default_factory=dict, compare=False, repr=False)

    def window(self) -> int:
        context = self.served.get("context")
        return context if isinstance(context, int) and context > 0 else self.context_tokens

    @property
    def set_by_hand(self) -> bool:
        return self.compact_at_tokens > 0 or self.keep_tokens_after_compaction > 0

    def limits(self) -> tuple[int, int]:
        window = self.window()
        if not self.set_by_hand:
            return compaction(window)
        if window >= self.context_tokens:
            return self.compact_at_tokens, self.keep_tokens_after_compaction
        room = self.context_tokens - self.compact_at_tokens
        compact = max(MIN_COMPACT_TOKENS, window - room)
        keep = max(1, min(compact - 1, self.keep_tokens_after_compaction * compact // self.compact_at_tokens))
        return compact, keep

    @classmethod
    def from_dict(cls, data: dict) -> "ModelProfile":
        known = {name: data[name] for name in cls.__dataclass_fields__ if name in data and name != "served"}
        profile = cls(**known)
        if profile.context_tokens <= 0:
            raise ValueError("model profile needs a context window")
        if profile.set_by_hand and not 0 < profile.keep_tokens_after_compaction < profile.compact_at_tokens < profile.context_tokens:
            raise ValueError("model profile needs keep < compact_at < context tokens, or neither so the budget table sets them")
        return profile

    @classmethod
    def load(cls, path: Path) -> "ModelProfile":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
