import re
from dataclasses import dataclass

from .context import Context, Pending
from .request import CHAT, Request
from .rules import NOT_THINGS, THERE_WORDS, _name, _noun_phrase, _strip_prefixes, _strip_tail, harmed, parse
from ..things.words import ANIMALS, FAR_PLACES, ROOMS, THING_WORDS, canonical, spoken
from .words import FAMILY, ME, normalise

PRONOUN_WHO = frozenset({"her", "him", "them"})
WHO_KINDS = frozenset({"follow", "come", "look"})
TOLD_KINDS = frozenset({"say_to", "watch"})
OWNED = re.compile(r"^([a-z]+)(?:'s|s) ([a-z ]+)$")
NOT_FOUND = frozenset(ROOMS) | FAR_PLACES | NOT_THINGS
NOWHERE = frozenset({"", "there", "over there", "that way", "yonder", "somewhere", "it", "other room", "next room", "another room", "that room", "this room", "room", "the other room"})
YES = re.compile(r"^(yes|yeah|yep|yup|ya|ja|jah|jip|yebo|sure|please|yes please|ok|alright|go on then|do it|uh huh|aye|correct|that is right|right|sweet|sweet as|chur|of course|definitely|absolutely|go for it|why not|you bet|mhm|mm hmm|indeed|affirmative|i do|i did|please do|go ahead)\b")
NO = re.compile(r"^(no|nah|nope|never mind|nevermind|forget it|do not|no thanks|no thank you|not now|cancel|nee|aikona|nah yeah no|not really|leave it|stop|i do not|i did not|not at all)\b")
SPEAKER = re.compile(r"^(?:it is |this is |i am |me |its |it was |that was |that is |me, |the |just )*([a-z]+)\b")
VERBS = {"follow": "follow", "come": "come to", "look": "look at", "say_to": "tell", "watch": "keep an eye on"}


@dataclass(frozen=True)
class Reading:
    request: Request
    ask: str = ""
    question: str = ""
    speaker: str = ""
    source: str = "rules"
    answered: bool = False
    left: tuple = ()
    too_much: bool = False

    def as_dict(self) -> dict:
        out = self.request.as_dict()
        if self.ask:
            out["ask"] = self.ask
        if self.speaker:
            out["speaker"] = self.speaker
        if self.too_much:
            out["too_much"] = True
        return out


def _mentioned(ctx: Context) -> list[str]:
    names = ctx.known_names()
    found = []
    for line in reversed(ctx.recent):
        speaker, _, words = line.partition(":")
        for word in reversed(re.findall(r"[a-z]+", normalise(words))):
            if word in names and word != ctx.speaker and word not in found:
                found.append(word)
    return found


def _pronoun(ctx: Context) -> str:
    mentioned = [name for name in _mentioned(ctx) if name in ctx.present or not ctx.present]
    if mentioned:
        return mentioned[0]
    others = [name for name in ctx.others() if name != "a visitor"]
    visitors = [name for name in ctx.others() if name == "a visitor"]
    if len(others) == 1 and not visitors:
        return others[0]
    if not others and len(visitors) == 1:
        return "a visitor"
    return ""


def question_for(about: str, request: Request, ctx: Context) -> str:
    if about == "speaker":
        return "Sorry, who's asking? I can't tell voices apart yet."
    if about == "place":
        return "Where's that? Point so I can see, or tell me the room."
    if about == "thing":
        return "Which thing do you mean? Tell me what it is."
    if about == "who":
        verb = VERBS.get(request.kind, "go to")
        others = [name.title() for name in ctx.others() if name != "a visitor"][:3]
        if len(others) >= 2:
            return f"Who should I {verb}: {', '.join(others[:-1])} or {others[-1]}?"
        return f"Who should I {verb}?"
    return f"Do you want me to {describe(request)}?"


def describe(request: Request) -> str:
    who = "you" if request.who in ("me", "") else request.who.title()
    if request.thing:
        who = f"the {spoken(request.thing)}"
    kind = request.kind
    if kind == "go_to_thing":
        return f"go to {who}"
    if kind == "find":
        return f"look for {who}"
    if kind == "where_is":
        return f"tell you where {who} is"
    if kind == "what_is":
        return "tell you what that is"
    if kind == "what_see":
        return "tell you what I can see"
    if kind == "sight_question":
        return "have a close look and tell you"
    if kind == "remember_spot":
        return f"remember this spot as the {request.name}" if request.name else "remember this spot"
    if kind == "go_back":
        if request.place == "before":
            return "go back to where I was before"
        return "take you back to where we started" if request.place in ("", "start") else f"take you back to the {request.place}"
    if kind == "follow":
        return f"follow {who}"
    if kind == "come":
        return f"come to {who}"
    if kind == "look":
        return f"look at {who}"
    if kind == "wait":
        return "wait here"
    if kind == "back_off":
        return "back off a little"
    if kind == "go_home":
        return "go back to my charger"
    if kind == "go_to_place":
        if request.who and not request.place:
            return f"go to where {who} were" if who == "you" else f"go to where {who} was"
        return f"go to the {request.place}" if request.place else "go somewhere"
    if kind == "turn":
        return f"turn {request.way}".strip() if request.way else "turn"
    if kind == "move":
        return f"move {request.way or 'forward'} a bit"
    if kind == "stop_activity":
        return "stop what I'm doing"
    if kind == "release":
        return "carry on with my own things"
    if kind == "adjust":
        return f"change how I'm doing it ({request.change.replace('_', ' ')})"
    if kind == "say_to":
        about = f": {request.text}" if request.text else ""
        return f"remind you{about}" if request.who in ("", "me") else f"tell {request.who.title()}{about}"
    if kind == "set_rule":
        return f"keep out of the {request.place}" if request.rule == "keep_out" and request.place else "keep quiet"
    if kind == "end_rule":
        return "stop keeping that rule"
    if kind == "list_rules":
        return "tell you the house rules I keep"
    if kind == "check":
        target = request.thing or request.place
        return f"go and check the {target}" if target else "go and check"
    if kind == "watch":
        return f"keep an eye on {who}"
    if kind == "again":
        return "do that again"
    if kind == "try_new":
        return f"try this: {request.text}" if request.text else "try something new"
    if kind == "list_later":
        return "tell you what I have for later"
    if kind == "cancel_later":
        return f"cancel {request.text}" if request.text else "cancel that"
    if kind == "change_later":
        return f"change {request.text}" if request.text else "change that"
    if kind == "if":
        return "do that only if it turns out that way"
    return kind


def _ask(request: Request, about: str, ctx: Context, source: str) -> Reading:
    return Reading(request, about, question_for(about, request, ctx), source=source)


THING_KINDS = frozenset({"look", "follow", "go_to_thing", "find", "where_is"})


def _recent_thing(ctx: Context) -> str:
    for line in reversed(ctx.recent):
        _, _, words = line.partition(":")
        tokens = re.findall(r"[a-z]+", normalise(words))
        for index in range(len(tokens) - 1, -1, -1):
            for size in (2, 1):
                if index - size + 1 < 0:
                    continue
                phrase = canonical(" ".join(tokens[index - size + 1 : index + 1]))
                if phrase in THING_WORDS:
                    return phrase
    return ""


ANIMAL_KINDS = frozenset({"find", "go_to_thing", "look", "follow", "come", "where_is"})


def _recent_animal(ctx: Context, text: str = "") -> str:
    lines = list(ctx.recent) + ([f"now: {text}"] if text else [])
    for line in reversed(lines):
        _, _, words = line.partition(":")
        for token in reversed(re.findall(r"[a-z]+", normalise(words))):
            word = canonical(token)
            if word in ANIMALS:
                return word
    return ""


def _who_to_thing(request: Request, ctx: Context) -> Request:
    if request.who and not request.thing and request.kind in ANIMAL_KINDS | THING_KINDS:
        word = canonical(request.who)
        if word in ANIMALS and request.who not in ctx.known_names() and request.who not in FAMILY:
            return request.with_(who="", thing=word)
    return request


def _tidy_thing(request: Request, ctx: Context) -> Request:
    thing = request.thing
    owned = OWNED.match(thing)
    if owned and (owned.group(1) in ctx.known_names() or owned.group(1) in FAMILY):
        request, thing = request.with_(who=owned.group(1), thing=owned.group(2)), owned.group(2)
    if thing in THERE_WORDS and request.kind in ("look", "go_to_place", "go_to_thing"):
        return request.with_(thing="", place="there", kind="go_to_place" if request.kind == "go_to_thing" else request.kind)
    if thing in ("it", "that", "this", "them", "those", "these", "me"):
        return request
    tidy = _noun_phrase(thing.split())
    if tidy and tidy != thing and tidy in THING_WORDS:
        return request.with_(thing=tidy)
    return request


def tidy(request: Request, ctx: Context) -> Request:
    if request.thing:
        request = _tidy_thing(request, ctx)
    if request.who and ((ctx.speaker and request.who == ctx.speaker) or (request.who == "pebble" and request.kind in ("come", "follow", "look"))):
        request = request.with_(who="me")
    if request.kind == "come" and not request.thing:
        request = _who_to_thing(request, ctx)
    if request.kind == "come" and request.who in ("", "me"):
        if request.thing:
            request = request.with_(kind="go_to_thing", who="", place="")
        elif request.place:
            request = request.with_(kind="go_to_place", who="")
    if request.kind == "look" and request.place and not request.thing and request.place not in THERE_WORDS and request.place not in ctx.places and request.place not in ROOMS and canonical(request.place) in THING_WORDS:
        request = request.with_(thing=canonical(request.place), place="")
    if request.kind == "go_to_place" and request.place and request.place not in ctx.places and request.place not in ROOMS and request.place not in THERE_WORDS:
        word = canonical(request.place)
        if request.place in ctx.known_names() or request.place in FAMILY or request.place in PRONOUN_WHO:
            request = request.with_(kind="come", who=request.place, place="")
        elif word in THING_WORDS and word not in ROOMS:
            request = request.with_(kind="go_to_thing", thing=word, place="")
    if request.kind in ("where_is", "find") and (request.thing in NOT_FOUND or (not request.thing and not request.who and request.place in FAR_PLACES)):
        return CHAT
    if request.kind == "teach" and not request.thing and request.who and request.name and (request.name == request.who or request.name in FAMILY):
        return CHAT
    if request.kind == "say_to" and request.who in ("pebble", ctx.name, "you", "yourself"):
        return _own_request(request.text, ctx)
    return request


def _own_request(text: str, ctx: Context) -> Request:
    harmful = harmed(text, ctx) if text else None
    if harmful is not None:
        return harmful
    found = parse(text, ctx) if text else None
    if found is None or not found.certain or not found.request.action or found.request.kind == "say_to":
        return Request("other")
    return found.request


def _trigger_who(request: Request) -> str:
    if request.on is None:
        return ""
    people = [one.who for one in request.on.first_of or (request.on,) if one.who and (one.event == "arrives" or (one.event == "seen" and not one.thing))]
    if not people:
        return ""
    return people[0] if len(people) == 1 else "them"


def _resolve_step(request: Request, ctx: Context) -> tuple[Request, str]:
    request = _who_to_thing(tidy(request, ctx), ctx)
    if request.kind == "move" and request.way in ("left", "right", "around"):
        request = request.with_(kind="turn", metres=0.0)
    if request.kind == "move" and not request.way:
        request = request.with_(way="forward")
    if request.kind in ("look", "go_to_place") and request.place in THERE_WORDS:
        if ctx.pointing:
            return request.with_(place="there", who="", thing=""), ""
        return request.with_(place=""), "place"
    if request.kind in ANIMAL_KINDS and not request.thing and request.who in ("her", "him", "them"):
        animal = _recent_animal(ctx)
        if animal:
            kind = "go_to_thing" if request.kind == "come" else request.kind
            return request.with_(kind=kind, who="", thing=animal), ""
    if request.kind == "find" and not request.thing:
        return _resolve_step(request.with_(kind="come"), ctx)
    if request.thing and request.kind in THING_KINDS:
        if request.thing in ("it", "that", "this", "them", "those", "these"):
            found = _recent_thing(ctx)
            if not found:
                return request.with_(thing=""), "thing"
            return request.with_(thing=found, who=""), ""
        return request.with_(who=""), ""
    if request.kind in TOLD_KINDS and not request.thing:
        who = request.who
        if request.kind == "say_to" and (not who or who in PRONOUN_WHO) and _trigger_who(request):
            return request.with_(who=_trigger_who(request)), ""
        if who in PRONOUN_WHO:
            found = _pronoun(ctx)
            if not found:
                return request.with_(who=""), "who"
            who = found
        if who in ME or (ctx.speaker and who == ctx.speaker):
            who = "me"
        if request.kind == "say_to" and not who:
            who = "me"
        return request.with_(who=who), ""
    if request.kind in WHO_KINDS:
        who = request.who or "me"
        if who in PRONOUN_WHO:
            found = _pronoun(ctx)
            if not found:
                return request.with_(who=""), "who"
            who = found
        if who in ME or (ctx.speaker and who == ctx.speaker):
            who = "me"
        if who == "me" and ctx.speaker is None and len([p for p in ctx.present]) >= 2:
            return request.with_(who="me"), "speaker"
        return request.with_(who=who), ""
    if request.kind == "go_to_place" and request.place in NOWHERE and not request.who:
        return request.with_(place=""), "place"
    return request, ""


def _resolve_branch(request: Request, ctx: Context) -> Request:
    if request.branch:
        return request.with_(then=tuple(_resolve_branch(step, ctx) for step in request.then), else_=tuple(_resolve_branch(step, ctx) for step in request.else_))
    resolved, _ = _resolve_step(request.with_(then=()), ctx)
    return resolved.with_(then=tuple(_resolve_branch(step, ctx) for step in request.then))


def _not_a_room(request: Request, ctx: Context) -> bool:
    if request.kind not in ("set_rule", "end_rule") or request.rule == "quiet" or not request.place:
        return False
    if request.place in ctx.places or request.place in ROOMS:
        return False
    word = canonical(request.place)
    return word in THING_WORDS or word in ANIMALS


def resolve(request: Request, ctx: Context, source: str = "rules") -> Reading:
    if not request.action or _not_a_room(request, ctx):
        return Reading(CHAT if request.action else (request.with_(then=()) if request.then else request), source=source)
    if request.kind == "harm":
        return Reading(request.with_(sure=True, then=()), source=source)
    if request.branch:
        resolved = _resolve_branch(request, ctx)
        if not request.sure:
            return _ask(resolved.with_(sure=True), "confirm", ctx, source)
        return Reading(resolved, source=source)
    first, about = _resolve_step(request.with_(then=()), ctx)
    if not first.action:
        return Reading(first, source=source)
    then = []
    for step in request.then:
        if step.branch:
            then.append(_resolve_branch(step, ctx))
            continue
        resolved, later = _resolve_step(step, ctx)
        if later == "who" or later == "place":
            continue
        then.append(resolved)
    resolved = first.with_(then=tuple(then))
    if about:
        return _ask(resolved, about, ctx, source)
    if not request.sure:
        return _ask(resolved.with_(sure=True), "confirm", ctx, source)
    return Reading(resolved, source=source)


def _names_in(text: str, ctx: Context) -> list[str]:
    known = ctx.known_names() | FAMILY
    return [word for word in re.findall(r"[a-z]+", text) if word in known]


def answer(text: str, pending: Pending, ctx: Context) -> Reading | None:
    s = normalise(text, ctx.name).replace("?", "").replace("!", "").strip(" ,.")
    if not s:
        return None
    if not YES.match(s) and not NO.match(s):
        s = _strip_tail(_strip_prefixes(s)[0]) or s
    words = s.split(" ")
    fresh = parse(text, ctx)
    if pending.about == "name":
        return _name_answer(s, words, fresh.request, fresh.certain, pending, ctx)
    if fresh.request.action and fresh.certain and len(words) > 2:
        return None
    if pending.about == "confirm":
        if NO.match(s):
            return Reading(CHAT, source="rules", answered=True)
        if YES.match(s) and len(words) <= 5:
            return Reading(pending.request, source="rules", answered=True)
        return None
    if NO.match(s) or re.match(r"^(nobody|no one|noone|nothing|nowhere)\b", s):
        return Reading(CHAT, source="rules", answered=True)
    if pending.about == "who":
        if re.match(r"^(me|i am|it is me|follow me|come to me|look at me)\b", s) and not _names_in(s, ctx):
            if ctx.speaker is None and len(ctx.present) >= 2:
                return Reading(pending.request.with_(who="me"), "speaker", question_for("speaker", pending.request, ctx), source="rules", answered=True)
            return Reading(pending.request.with_(who="me"), source="rules", answered=True)
        names = _names_in(s, ctx)
        if names:
            return Reading(pending.request.with_(who=names[0]), source="rules", answered=True)
        if re.match(r"^(her|him|them|she|he|they)\b", s):
            return Reading(pending.request.with_(who=""), "who", question_for("who", pending.request, ctx), source="rules", answered=True)
        if len(words) == 1 and words[0].isalpha() and not fresh.request.action and words[0] not in ("what", "why", "how", "who", "huh", "eh", "hmm"):
            return Reading(pending.request.with_(who=words[0]), source="rules", answered=True)
        return None
    if pending.about == "speaker":
        match = SPEAKER.match(s)
        if match:
            name = match.group(1)
            names = _names_in(s, ctx)
            if names:
                return Reading(pending.request, speaker=names[0], source="rules", answered=True)
            if len(words) <= 3 and name.isalpha() and name not in ("what", "why", "how", "who", "huh", "eh", "hmm", "a", "the", "no", "yes"):
                return Reading(pending.request, speaker=name, source="rules", answered=True)
        return None
    if pending.about == "thing":
        cleaned = re.sub(r"^(the |my |your |our |a |an |it is |its |i mean |um |uh )+", "", s).strip()
        thing = canonical(cleaned)
        if thing and len(thing.split(" ")) <= 3 and not fresh.request.action and thing not in ("it", "that", "this"):
            return Reading(pending.request.with_(thing=thing), source="rules", answered=True)
        return None
    if pending.about == "place":
        if re.match(r"^(there|over there|that way|here)$", s):
            return Reading(pending.request.with_(place=""), "place", question_for("place", pending.request, ctx), source="rules", answered=True)
        cleaned = re.sub(r"^(to |into |in |go to |the |my |our |your |it is |its |i mean |um |uh )+", "", s)
        cleaned = re.sub(r"^(the |my |our |your )+", "", cleaned).strip()
        if cleaned and len(cleaned.split(" ")) <= 3 and not fresh.request.action and not re.match(r"^(what|why|how|who|huh|eh|hmm|where)\b", cleaned):
            if cleaned in ("home", "bed", "your bed", "charger", "your charger", "dock"):
                return Reading(Request("go_home"), source="rules", answered=True)
            return Reading(pending.request.with_(place=cleaned), source="rules", answered=True)
        return None
    return None


NO_NAME = re.compile(r"^(?:no idea|i do not know|i dunno|dunno|idk|not sure|i am not sure|it does not have (?:a name|one)|it has not got (?:a name|one)|it has no name|no name|nothing|none|nobody|it is just an? [a-z ]+|it is not got a name|it does not need a name|i have not named it|not yet)\b")


def _name_answer(s: str, words: list[str], fresh: Request, certain: bool, pending: Pending, ctx: Context) -> Reading | None:
    base = pending.request
    if fresh.kind == "teach":
        merged = base.with_(who=fresh.who or base.who, thing=fresh.thing or base.thing, name=fresh.name or base.name)
        return Reading(merged, source="rules", answered=True)
    if fresh.action and certain:
        return None
    if NO.match(s) or NO_NAME.match(s):
        return Reading(CHAT, source="rules", answered=True)
    if re.match(r"^(?:mine|it is mine|that is mine|my one|me|it is my one)$", s):
        return Reading(base.with_(who="me"), source="rules", answered=True)
    if re.match(r"^(?:yours|it is yours|for you|you can have it)(?: now)?$", s):
        return Reading(base.with_(who="pebble"), source="rules", answered=True)
    owner = re.match(r"^(?:it )?belongs to ([a-z]+)$", s)
    if owner:
        who = "me" if owner.group(1) in ME else owner.group(1)
        return Reading(base.with_(who=who), source="rules", answered=True)
    if len(words) <= 5 and not re.match(r"^(?:what|why|how|who|huh|eh|hmm|where|when|sorry|pardon)\b", s):
        name = _name(s, ctx)
        if name:
            return Reading(base.with_(name=name), source="rules", answered=True)
    return None
