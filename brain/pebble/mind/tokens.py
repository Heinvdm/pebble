import json
import math

CHARS_PER_TOKEN = 4.0
MESSAGE_OVERHEAD = 4


def estimate_text(text: str | None, chars_per_token: float = CHARS_PER_TOKEN) -> int:
    if not text:
        return 0
    return math.ceil(len(text) / chars_per_token)


def estimate_message(message: dict, chars_per_token: float = CHARS_PER_TOKEN) -> int:
    total = MESSAGE_OVERHEAD + estimate_text(message.get("content") or "", chars_per_token)
    if message.get("tool_calls"):
        total += estimate_text(json.dumps(message["tool_calls"]), chars_per_token)
    return total


def estimate_messages(messages: list[dict], chars_per_token: float = CHARS_PER_TOKEN) -> int:
    return sum(estimate_message(m, chars_per_token) for m in messages)
