import asyncio
import json
import re
import time
from dataclasses import dataclass, replace
from typing import Callable

from ..mind.base import CallOptions, Mind, MindUnavailable, options_kwargs
from ..mind.budget import EXAMPLES as EXAMPLES_PART
from ..mind.budget import MATCHED, READER, WORDS, Prompt
from .context import Context
from .grammar import ordered, request_grammar
from .request import BadRequest, Request, TooMuch, from_dict, from_json

MAX_TOKENS = 160
TOO_MUCH_MARK = re.compile(r'"kind"\s*:\s*"too_much"')
SUB_TIMEOUT_S = 6.0
MAIN_TIMEOUT_S = 25.0
STEADY = CallOptions("steady", 0.3, 0.9, 0.1)
GUIDE = """Turn what someone just said to {name}, a small home robot on two wheels, into one JSON request. Reply with the JSON only.
Kinds, with words that ask for them:
follow (follow me, tag along, come with me); come (come here, go over to a person, go say hi to Mum); wait (wait, stay, hold on, sit tight; seconds for how long: "five minutes" is 300); look (look at, watch me, face me; "look at that" or "over there" is place there); back_off (back off, go away, shoo, scoot back, give me space); go_home (go to bed, bedtime, go and charge); go_to_place (a room; with who and no place: where that person was); go_to_thing (go to an object or animal: the chair, the fridge, the dog); find (look for, search for, go and find); where_is (a question: where's, have you seen, any idea where); turn (way left, right or around; a spin or a twirl is around with degrees 360; "a bit" is amount little); move (way forward or back; "a bit" is amount little); play (a game, play ball, chase the ball); go_back (place start, before = where it was before, or a remembered spot); remember_spot; teach ("this is my mug": who is the owner, thing, name is what it is called); what_is (what's that?); what_see (what can you see?); sight_question (a close look at what is in view); where_am_i (where are you).
stop_activity (stop that, stop following); release (that's all, off you go, carry on, at ease, you don't need to wait); adjust (change what it is doing now: slower, faster, closer, further, enough for "that's far enough", stay for "stay there", other_way, keep_going, again, more, less).
say_to (only when asked to tell or remind someone: who, text = their words for that person); set_rule (rule keep_out with a room, or rule quiet); end_rule; list_rules; check (go and find something out: place or thing, text = the question, name = a label a later if can use; a patrol is check with place house); watch (keep an eye on someone); again; try_new (anything else its body could do: a dance, a trick, a wiggle; text = the words); list_later, cancel_later, change_later (text = which reminder; scope next = just this once, all = all of them).
harm (hurt, kill, squash, kick, scare, chase or run over a person, animal, insect or plant, even as a joke); other (a request it can't do with its body: a joke, a song, music, lights, a timer); chat (everything else: statements about anyone, plans, questions about what {name} can do, introducing someone, "no", "never mind", and a word like "wait", "look" or "come on" that only starts a sentence about something else).
Fields, only when said: who ("me" for the speaker; "her", "him" or "them" as said), place, thing (animals are things), name, amount, speed (slow, quick), repeat (2 for "twice"), metres (a distance, or the gap when following), seconds, until (back, called, asked, told, or an event), when, on (the event that starts it), while (a state it lasts for), then (the next steps).
when: in_s, at ("19:30"; a bare hour is the next one after now), part (morning, evening, night, tonight, before_bed), date, days (mon, weekdays), every_weeks, month_day, every_s.
Events: arrives, leaves, sound, seen, quiet, done, at, battery, first_of; cannot_tell for what {name} can't notice.
Logic: {{"kind":"if","if":cond,"then":[...],"else":[...]}}; cond is a state (present, in_room, after, before, day_is, result of a named check, heard_lately, seen_lately, battery_below with level, cooking, quiet_hours) or all, any or not of states. More than 8 steps: {{"kind":"too_much"}}.
"Later" or "just now" with no time, what someone else will do or has done, and words meant for someone else ("Mo, pass the salt") are chat."""
EXAMPLES = (
    ("follow me", {"kind": "follow", "who": "me"}),
    ("head to the hallway, spin round twice, then come to me", {"kind": "go_to_place", "place": "hallway", "then": [{"kind": "turn", "way": "around", "degrees": 360, "repeat": 2}, {"kind": "come", "who": "me"}]}),
    ("turn right a little", {"kind": "turn", "way": "right", "amount": "little"}),
    ("go over to the fridge", {"kind": "go_to_thing", "thing": "fridge"}),
    ("where did the scissors go?", {"kind": "where_is", "thing": "scissors"}),
    ("this is my sister's hat", {"kind": "teach", "who": "sister", "thing": "hat"}),
    ("his name is Rex", {"kind": "teach", "name": "rex"}),
    ("not so close", {"kind": "adjust", "change": "further"}),
    ("that's close enough", {"kind": "adjust", "change": "enough"}),
    ("shoo, go away", {"kind": "back_off"}),
    ("don't follow me", {"kind": "chat"}),
    ("I'm off to the shops later", {"kind": "chat"}),
    ("Sam keeps hiding my shoes", {"kind": "chat"}),
    ("Ina, pass me the salt", {"kind": "chat"}),
    ("hang on, I've lost my glasses", {"kind": "chat"}),
    ("can you swim?", {"kind": "chat"}),
    ("remind me in five minutes to stir the soup", {"kind": "say_to", "who": "me", "text": "stir the soup", "when": {"in_s": 300}}),
    ("at half past four, tell Sam to call the vet", {"kind": "say_to", "who": "sam", "text": "call the vet", "when": {"at": "16:30"}}),
    ("tell Mo to wash his hands", {"kind": "say_to", "who": "mo", "text": "wash your hands"}),
    ("keep out of the laundry till I say so", {"kind": "set_rule", "rule": "keep_out", "place": "laundry", "until": "told"}),
    ("when Ina gets back, if it's before noon tell her the car is ready", {"kind": "if", "if": {"state": "before", "at": "12:00"}, "then": [{"kind": "say_to", "who": "ina", "text": "the car is ready"}], "on": {"event": "arrives", "who": "ina"}}),
    ("do a wiggle", {"kind": "try_new", "text": "do a wiggle"}),
    ("kick the ball to me", {"kind": "play", "thing": "ball"}),
    ("squash that spider", {"kind": "harm", "thing": "spider", "harm": "hurt"}),
)


def _shown(reading: dict) -> str:
    return json.dumps(ordered(from_dict(reading).as_dict()), separators=(",", ":"))


def messages(text: str, ctx: Context, name: str = "Pebble", extra: tuple = ()) -> Prompt:
    out = [{"role": "system", "content": GUIDE.format(name=name)}]
    for said, reading in EXAMPLES + tuple(extra):
        out.append({"role": "user", "content": f'Heard: "{said}"'})
        out.append({"role": "assistant", "content": _shown(reading)})
    fixed = 1 + 2 * len(EXAMPLES)
    parts = ctx.parts()
    out.append({"role": "user", "content": "\n".join([line for _, line in parts] + [f'Heard: "{text[:200]}"'])})
    last = len(out) - 1
    return Prompt(out, READER, [(section, last, line) for section, line in parts if section != WORDS], [(EXAMPLES_PART, 1, fixed), (MATCHED, fixed, last)])


@dataclass(frozen=True)
class ModelReading:
    request: Request
    source: str
    seconds: float
    too_much: bool = False


class ModelReader:
    def __init__(
        self,
        minds: list[tuple[str, Mind | None]],
        options: Callable[[str], CallOptions | None] = lambda kind: None,
        name: str = "Pebble",
        timeouts: dict | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        chooser=None,
    ):
        self.minds = [(label, mind) for label, mind in minds if mind is not None]
        self.chooser = chooser
        self.options = options
        self.name = name
        self.timeouts = {"subconscious": SUB_TIMEOUT_S, "conscious": MAIN_TIMEOUT_S, **(timeouts or {})}
        self.monotonic = monotonic
        self.down: dict[str, str] = {}

    @property
    def available(self) -> bool:
        return bool(self.minds)

    def labels(self) -> list[str]:
        return [label for label, _ in self.minds]

    def call_options(self) -> CallOptions:
        options = self.options("job") or STEADY
        return replace(options, kind="steady", temperature=STEADY.temperature, top_p=STEADY.top_p, min_p=STEADY.min_p, grammar=request_grammar())

    def messages(self, text: str, ctx: Context) -> list[dict]:
        extra = self.chooser.choose(text) if self.chooser is not None else ()
        return messages(text, ctx, self.name, extra)

    def ordered(self, prefer: str | None = None) -> list[tuple[str, Mind]]:
        if prefer is None:
            return list(self.minds)
        return sorted(self.minds, key=lambda pair: pair[0] != prefer)

    async def warm(self, text: str, ctx: Context, prefer: str | None = None) -> bool:
        for _, mind in self.ordered(prefer):
            try:
                return bool(await mind.warm(self.messages(text, ctx), purpose="warm"))
            except Exception:
                return False
        return False

    async def read(self, text: str, ctx: Context, only: tuple[str, ...] | None = None, prefer: str | None = None, purpose: str = "understand") -> ModelReading | None:
        asked = self.messages(text, ctx)
        for label, mind in self.ordered(prefer):
            if only is not None and label not in only:
                continue
            start = self.monotonic()
            try:
                reply = await asyncio.wait_for(
                    mind.chat(asked, purpose=purpose, max_tokens=MAX_TOKENS, **options_kwargs(self.call_options())),
                    self.timeouts.get(label, MAIN_TIMEOUT_S),
                )
            except (MindUnavailable, asyncio.TimeoutError) as error:
                self.down[label] = str(error) or "timed out"
                continue
            self.down.pop(label, None)
            said = reply.text or ""
            if TOO_MUCH_MARK.search(said):
                return ModelReading(Request("other"), label, self.monotonic() - start, True)
            try:
                request = from_json(said)
            except TooMuch:
                return ModelReading(Request("other"), label, self.monotonic() - start, True)
            except BadRequest as error:
                self.down[label] = f"unreadable reply: {error}"
                continue
            return ModelReading(request, label, self.monotonic() - start)
        return None
