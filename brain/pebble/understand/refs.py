import re
from dataclasses import dataclass

from ..things.words import ROOMS, THING_WORDS, canonical, spoken
from .context import Context
from .request import Request
from .resolve import describe
from .rules import parse
from .telling import _start
from .words import FAMILY, ME

DONE_KEEP_S = 1800.0
DONE_MOST = 3
SEEN_KEEP_S = 3600.0
TALKED_KEEP_S = 300.0
BLOCK_DONE = 3
BLOCK_SEEN = 3
NOT_AGAIN = frozenset({"again", "stop_activity", "release", "adjust", "chat", "other", "harm", "look_away", "list_later", "cancel_later", "change_later", "list_rules", "end_rule", "set_rule", "say_to", "if"})
WHO_AGAIN = frozenset({"come", "follow", "look", "watch"})
FLIP = {"left": "right", "right": "left", "around": "right", "forward": "back", "back": "forward"}
LOW_POSTURES = {"sitting": "sitting", "lying": "lying down", "crouching": "crouching", "standing": "standing"}
AGAIN = re.compile(r"^(?:and |now )?(?:(?:do|try) (?:that|it|this|the same(?: thing)?) (?:again|one more time|once more|over)|again|(?:once|one) more(?: time)?|same again|again please|do (?:it|that) all again)$")
SAME_FOR = re.compile(r"^(?:now )?do (?:the same(?: thing)?|that|it)(?: again)? (?:for|to|with) (?P<who>[a-z]+)$")
OTHER_WAY = re.compile(r"^(?:(?:go|turn|spin|do it|try|now) )?(?:the )?(?:other way(?: around)?|opposite way|other direction|opposite direction)(?: this time| instead)?$")
BEFORE = re.compile(r"^(?:go|head|get|come|pop|nip|roll) back (?:to )?(?:where|the (?:spot|place) where|the (?:spot|place)) you (?:were|was)(?: (?:before|earlier|a minute ago|just now|first|sitting))?$")
AND_AGAIN = re.compile(r"^(?P<rest>.+?),? (?:and then |and |then )(?:do (?:it|that|the same(?: thing)?) (?:again|once more)|again)$")
WHERE_LEFT = re.compile(r"^(?:go|head|pop|nip|run|roll|drive)(?: over)?(?: to)? where (?P<who>[a-z]+) (?:left|put|dropped|leaves) (?:his|her|their|my|the|your) (?P<thing>[a-z]+(?: [a-z]+)?)$")
WHERE_WAS = re.compile(r"^(?:go|head|pop|nip|run|roll|drive)(?: over)?(?: to)? (?:where|the (?:spot|place) where) (?P<who>[a-z]+) (?:was|were)(?: (?:sitting|sat|standing|lying|playing|working|reading|before|earlier|just now|a minute ago))*$")


@dataclass
class Done:
    at: float
    request: Request


@dataclass
class Seen:
    at: float
    x: float
    y: float
    room: str
    label: str
    posture: str = ""


@dataclass
class Spot:
    at: float
    x: float
    y: float
    room: str


def ago(seconds: float) -> str:
    if seconds < 60.0:
        return "just now"
    minutes = int(round(seconds / 60.0))
    return "a minute ago" if minutes == 1 else f"{minutes} minutes ago"


def flipped(request: Request) -> Request | None:
    if request.kind not in ("turn", "move") or request.way not in FLIP:
        return None
    if request.kind == "move" and request.way == "around":
        return None
    return request.with_(way=FLIP[request.way])


def again_for(request: Request, last: Request) -> Request:
    who = request.who
    if who and who != "me" and last.kind in WHO_AGAIN and not last.thing:
        return last.with_(who=who)
    return last


def ref_words(text: str, ctx: Context) -> Request | None:
    raw = " ".join((text or "").split())
    if raw.endswith("?"):
        return None
    s = _start(raw, ctx)
    if not s:
        return None
    if AGAIN.match(s):
        return Request("again")
    found = AND_AGAIN.match(s)
    if found is not None:
        first = parse(found.group("rest"), ctx)
        if first.certain and first.request.action and not first.request.then and first.request.kind not in NOT_AGAIN:
            return first.request.with_(then=(Request("again"),))
        return None
    found = WHERE_LEFT.match(s)
    if found is not None and (found.group("who") in ctx.known_names() or found.group("who") in FAMILY or found.group("who") in ME):
        return Request("go_to_thing", thing=canonical(found.group("thing")))
    found = SAME_FOR.match(s)
    if found is not None:
        who = found.group("who")
        if who in ME or who == ctx.speaker:
            return Request("again", who="me")
        if who in ctx.known_names() or who in FAMILY:
            return Request("again", who=who)
        return None
    if OTHER_WAY.match(s):
        return Request("adjust", change="other_way")
    if BEFORE.match(s):
        return Request("go_back", place="before")
    found = WHERE_WAS.match(s)
    if found is not None:
        who = found.group("who")
        if who in ("you", "pebble", ctx.name):
            return Request("go_back", place="before")
        if who in ME or who in ("i", "we") or who == ctx.speaker:
            return Request("go_to_place", who="me")
        if who in ctx.known_names() or who in FAMILY:
            return Request("go_to_place", who=who)
    return None


def mentioned(text: str, places: tuple = ()) -> str:
    words = re.findall(r"[a-z]+", (text or "").lower())
    found = ""
    for index in range(len(words)):
        for size in (2, 1):
            if index + size > len(words):
                continue
            phrase = " ".join(words[index : index + size])
            if phrase in places or phrase in ROOMS - {"room", "inside", "outside"}:
                found = f"the {phrase}"
                break
            word = canonical(phrase)
            if word in THING_WORDS and word not in ("it", "that", "this", "thing"):
                found = f"the {spoken(word)}"
                break
    return found


class Refs:
    def __init__(self):
        self.done: dict[str, list[Done]] = {}
        self.labels: dict[str, str] = {}
        self.seen: dict[str, Seen] = {}
        self.before: Spot | None = None
        self.talked: tuple[str, float] | None = None

    def did(self, person: str | None, label: str, request: Request, now: float) -> None:
        if person is None or request.kind in NOT_AGAIN or not request.action:
            return
        kept = [item for item in self.done.get(person, []) if now - item.at <= DONE_KEEP_S]
        kept.append(Done(now, request))
        self.done[person] = kept[-DONE_MOST:]
        self.labels[person] = label

    def last(self, person: str | None, now: float) -> Request | None:
        items = [item for item in self.done.get(person, []) if now - item.at <= DONE_KEEP_S] if person else []
        return items[-1].request if items else None

    def trip(self, x: float, y: float, room: str | None, now: float) -> None:
        self.before = Spot(now, x, y, room or "")

    def saw(self, person: str, label: str, x: float, y: float, room: str | None, posture: str | None, now: float) -> None:
        self.seen[person] = Seen(now, x, y, room or "", label, posture or "")

    def where(self, person: str | None, now: float) -> Seen | None:
        found = self.seen.get(person) if person else None
        if found is None or now - found.at > SEEN_KEEP_S:
            return None
        return found

    def mention(self, words: str, now: float) -> None:
        if words:
            self.talked = (words, now)

    def forget(self, person: str) -> None:
        self.done.pop(person, None)
        self.labels.pop(person, None)
        self.seen.pop(person, None)

    def sweep(self, now: float) -> None:
        for person in list(self.done):
            kept = [item for item in self.done[person] if now - item.at <= DONE_KEEP_S]
            if kept:
                self.done[person] = kept
            else:
                self.done.pop(person, None)
        for person in [p for p, seen in self.seen.items() if now - seen.at > SEEN_KEEP_S]:
            self.seen.pop(person, None)
        if self.talked is not None and now - self.talked[1] > TALKED_KEEP_S:
            self.talked = None

    def _done_words(self, person: str, item: Done, now: float) -> str:
        request = item.request
        label = self.labels.get(person, "someone").lower()
        if request.who in ("", "me") and request.kind in WHO_AGAIN and not request.thing:
            request = request.with_(who=label)
        said = describe(request).replace(" you", f" {label}") if request.kind == "say_to" else describe(request)
        if request.repeat > 1:
            said += " twice" if request.repeat == 2 else f" {request.repeat} times"
        return f"{label}: {said} ({ago(now - item.at)})"

    def block(self, now: float, person: str | None = None) -> str:
        self.sweep(now)
        parts = []
        done = [(person, item) for person, items in self.done.items() for item in items]
        done.sort(key=lambda pair: (pair[0] != person, -pair[1].at))
        if done:
            parts.append("Done lately for " + "; ".join(self._done_words(person, item, now) for person, item in done[:BLOCK_DONE]))
        if self.before is not None:
            where = f"in the {self.before.room}" if self.before.room else "at a spot it remembers"
            parts.append(f"Before its last trip Pebble was {where}")
        seen = sorted(self.seen.values(), key=lambda item: -item.at)[:BLOCK_SEEN]
        if seen:
            said = []
            for item in seen:
                where = f" in the {item.room}" if item.room else ""
                how = f", {LOW_POSTURES[item.posture]}" if item.posture in LOW_POSTURES else ""
                said.append(f"{item.label.lower()}{where}{how} ({ago(now - item.at)})")
            parts.append("Last seen: " + "; ".join(said))
        if self.talked is not None:
            parts.append(f"Last talked about: {self.talked[0]}")
        return ("References: " + ". ".join(parts) + ".") if parts else ""
