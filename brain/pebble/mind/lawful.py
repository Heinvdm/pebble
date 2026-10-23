from contextlib import aclosing
from typing import AsyncIterator

from ..laws import laws_text
from .base import Mind, MindReply, options_kwargs
from .budget import Prompt


def with_laws(messages: list[dict]) -> list[dict]:
    text = laws_text()
    prompt = messages if isinstance(messages, Prompt) else None
    messages = list(messages)
    if messages and messages[0].get("role") == "system":
        content = messages[0].get("content") or ""
        if text in content:
            return prompt.like(messages) if prompt is not None else messages
        messages = [{**messages[0], "content": f"{text}\n\n{content}"}] + messages[1:]
        return prompt.like(messages) if prompt is not None else messages
    if prompt is not None:
        return prompt.ahead({"role": "system", "content": text})
    return [{"role": "system", "content": text}] + messages


class LawfulMind(Mind):
    def __init__(self, inner: Mind):
        self.inner = inner
        self.name = inner.name

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None) -> MindReply:
        return await self.inner.chat(with_laws(messages), tools=tools, purpose=purpose, max_tokens=max_tokens, **options_kwargs(options))

    async def stream(self, messages, purpose="turn", max_tokens=None, options=None, tools=None) -> AsyncIterator[str]:
        extra = {"tools": tools} if tools else {}
        async with aclosing(self.inner.stream(with_laws(messages), purpose=purpose, max_tokens=max_tokens, options=options, **extra)) as pieces:
            async for piece in pieces:
                yield piece

    async def ready(self) -> bool:
        return await self.inner.ready()

    def give_way(self) -> int:
        return self.inner.give_way()

    async def warm(self, messages, tools=None, purpose="warm") -> bool:
        return await self.inner.warm(with_laws(messages), tools=tools, purpose=purpose)

    async def sees(self) -> bool:
        return await self.inner.sees()

    async def close(self) -> None:
        await self.inner.close()


def lawful(mind: Mind | None) -> Mind | None:
    if mind is None or isinstance(mind, LawfulMind):
        return mind
    return LawfulMind(mind)
