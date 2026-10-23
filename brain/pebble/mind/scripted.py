import copy
import json
from dataclasses import dataclass

from .base import Mind, MindReply, MindUnavailable, ToolCall

CANNED_SCENES = (
    'sky night\nstars 30 twinkle\nmoon 24 6 r4 pale\nhill 0 26 32 6 green\nrain 40 blue slow\ntext 3 28 "zzz" drift',
    "sky day\nsun 6 6 r4 yellow spin\ncloud 16 5 10 white drift\ngrass 27 green sway\nflower 12 27 pink sway\nbird 22 10 black drift",
    "waves 0 blue slow\nbubbles 14 white slow\nfish 8 12 yellow drift\nfish 22 20 pink drift",
    "sky dusk\nheart 16 14 r6 red pulse\nsparkle 6 6 pink twinkle\nparticles 18 pink drift",
)
STREAM_CHUNK = 7
WORD_PURPOSES = frozenset({"talk", "joke"})


@dataclass(frozen=True)
class Act:
    thought: str
    calls: tuple = ()
    after: str = ""


DRAW_ACT = Act(
    "A little picture would be nice.",
    (("face", {"draw": "a quiet night with rain", "picture": "my-night"}),),
    "There. Drawn.",
)
DEFAULT_ACTS = (
    Act("Awake. Checking my body first.", (("face", {"expression": "curious"}), ("status", {"about": "sensors"})), "Everything reads fine."),
    Act("Something to look at up there.", (("face", {"tilt": 20}),), "Nothing much up there."),
    Act("A short roll forward to see what is there.", (("do", {"words": "roll forward a little"}),), "That was a little roll."),
    Act("Worth noting down.", (("remember", {"fact": "Pebble ran with the scripted test mind today."}),), "Noted."),
    Act(
        "The wall by the dock is close. A small project.",
        (("do", {"words": "Look at the wall by the dock", "done_when": "the front sensor reads under 300 mm while facing the wall", "hours": 24}),),
        "Something to do later.",
    ),
    Act("A quiet moment.", (("face", {"expression": "neutral", "tilt": 8}),), "Resting my eyes."),
)
HELLO_ACT = Act("Someone is here. A small hello.", (("say", {"text": "Hello! I'm Pebble."}),), "Said hello.")
APP_ACTS = DEFAULT_ACTS[:2] + (DRAW_ACT, HELLO_ACT) + DEFAULT_ACTS[2:]


def _last_user(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content") or ""
    return ""


class ScriptedMind(Mind):
    name = "scripted"

    def __init__(self, acts=None, job_answers: dict | None = None, scenes=None, words=None, replies=None, holds=None, senses=None, changes=None):
        self.acts = list(acts if acts is not None else DEFAULT_ACTS)
        self.job_answers = dict(job_answers or {})
        self.scenes = list(scenes if scenes is not None else CANNED_SCENES)
        self.words = list(words or [])
        self.replies = list(replies or [])
        self.holds = list(holds or [])
        self.senses = list(senses or [])
        self.changes = list(changes or [])
        self._reply_index = 0
        self._word_index = 0
        self.requests: list[dict] = []
        self.unavailable = False
        self._index = 0
        self._scene_index = 0
        self._call_count = 0
        self._after = ""

    async def ready(self) -> bool:
        return not self.unavailable

    async def warm(self, messages, tools=None, purpose="warm"):
        self.requests.append({"purpose": purpose, "messages": copy.deepcopy(messages), "tools": [t["function"]["name"] for t in tools or []], "options": None})
        return not self.unavailable

    async def stream(self, messages, purpose="turn", max_tokens=None, options=None, tools=None):
        reply = await self.chat(messages, tools, purpose, max_tokens, options)
        text = reply.text or ""
        for start in range(0, len(text), STREAM_CHUNK):
            yield text[start : start + STREAM_CHUNK]

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None) -> MindReply:
        self.requests.append(
            {
                "purpose": purpose,
                "messages": copy.deepcopy(messages),
                "tools": [t["function"]["name"] for t in tools or []],
                "options": None if options is None else options.summary(),
                "max_tokens": max_tokens,
            }
        )
        if self.unavailable:
            raise MindUnavailable("the scripted mind is switched off")
        if purpose == "scene":
            if not self.scenes:
                return MindReply("")
            scene = self.scenes[self._scene_index % len(self.scenes)]
            self._scene_index += 1
            return MindReply(scene)
        if purpose == "summary":
            return MindReply(self._summary(messages))
        if purpose in WORD_PURPOSES:
            return MindReply(self._words(messages))
        if purpose == "reply":
            return MindReply(self._reply())
        if purpose == "hold":
            return MindReply(self.holds.pop(0) if self.holds else "")
        if purpose == "sense":
            return self._sense()
        if purpose == "job":
            return MindReply(json.dumps(self._job(messages)))
        if messages and messages[-1].get("role") == "tool":
            return MindReply(self._after)
        if not self.acts:
            return MindReply("Nothing to do.")
        act = self.acts[self._index % len(self.acts)]
        self._index += 1
        allowed = {t["function"]["name"] for t in tools or []}
        calls = []
        for name, arguments in act.calls:
            if name in allowed:
                self._call_count += 1
                calls.append(ToolCall(f"scripted_{self._call_count}", name, dict(arguments), json.dumps(arguments)))
        self._after = act.after
        return MindReply(act.thought, tuple(calls))

    def _sense(self) -> MindReply:
        if not self.senses:
            return MindReply("A")
        sensed = self.senses.pop(0)
        if isinstance(sensed, str):
            return MindReply(sensed)
        best = max(sensed, key=sensed.get)
        return MindReply(best, extra={"probs": [[(letter, chance) for letter, chance in sensed.items()]]})

    def _words(self, messages: list[dict]) -> str:
        if self.words:
            answer = self.words[self._word_index % len(self.words)]
            self._word_index += 1
            return answer
        first = _last_user(messages).splitlines()[0] if _last_user(messages) else ""
        return first.split(": ", 1)[-1]

    def _reply(self) -> str:
        if not self.replies:
            return "Hmm. I'm not sure what to say."
        answer = self.replies[self._reply_index % len(self.replies)]
        self._reply_index += 1
        return answer

    def _summary(self, messages: list[dict]) -> str:
        if self.changes:
            return json.dumps(self.changes.pop(0))
        text = _last_user(messages)
        if "New memory:" in text:
            memory = text.split("New memory:", 1)[1].splitlines()[0].strip()
            return json.dumps({"op": "add", "text": memory[:150]})
        return json.dumps({"op": "none"})

    def _job(self, messages: list[dict]) -> dict:
        try:
            request = json.loads(_last_user(messages))
        except ValueError:
            return {}
        job = request.get("job")
        if job in self.job_answers:
            return {"choice": self.job_answers[job]}
        choices = request.get("choices") or []
        return {"choice": choices[0]} if choices else {}
