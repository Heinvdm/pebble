import logging
import math
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, time, timedelta

from ..activities.commands import for_mind
from ..activities.gate import PEBBLE, Asker, Verdict
from ..life.conditions import evaluate
from ..life.events import match
from ..life.times import hm, instant, next_time, part_time
from ..people.trust import CHILD, FRIEND, INNER, RANK, STRANGER, TRUSTED
from ..things.words import listing
from ..understand.logic import _days_words, clock_words, cond_words, event_words, happened_words, moment_words, span_words
from ..understand.request import BadRequest, Request, When, cond_from, trigger_from

log = logging.getLogger(__name__)

RULES = "house_rules.json"
DAY_S = 86400.0
WEEK_S = 7 * DAY_S
CHILD_S = 3600.0
WHILE_MOST_S = 4 * 3600.0
EVENT_MOST_S = DAY_S
WHILE_EVERY_S = 3.0
SWEEP_S = 60.0
SETTLE_S = 1.0
PER_PERSON = 10
IN_ALL = 40
MATCHED_MOST = 3
MARGIN_M = 0.5
SMALLEST_M = 0.3
AHEAD_M = 0.4
STEP_M = 0.1
OWNER_RANK = 4
PART_ENDS = {"morning": "12:00", "midday": "13:00", "afternoon": "18:00", "evening": "21:00", "night": "07:00", "tonight": "07:00", "before_bed": "07:00"}
STRANGER_NO = "Sorry, I only keep house rules for people I know."
CHILD_ROOM_NO = "Only a grown-up can ask me to keep out of a room. I can keep quiet for you, though."
WHICH_ROOM = "Which room should I keep out of? Say it like: stay out of the kitchen."
NOT_KEPT = "I'm not keeping any house rules just now."
NONE_LIKE = "I'm not keeping a rule like that."
STRANGER_LIST = "I only talk about the house rules with people I know."
FULL = "I'm already keeping as many house rules as I can."
YOURS_FULL = f"You've already got {PER_PERSON} house rules with me. If you end one, I'll take this."
CAPPED = {
    CHILD: "That's as long as I keep a quiet rule for you.",
    FRIEND: "A longer rule needs someone I know really well.",
    TRUSTED: "Only the owner can make a rule that lasts for good.",
    INNER: "Only the owner can make a rule that lasts for good.",
}


@dataclass
class Rule:
    id: int
    kind: str
    place: str
    by: str | None
    by_label: str
    tier: str
    made: float
    starts: float
    ends: float | None = None
    window: list = field(default_factory=list)
    days: list = field(default_factory=list)
    while_: dict | None = None
    until: dict | None = None
    told: bool = False
    holding: bool = False
    state: str = "on"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Rule | None":
        try:
            names = {f.name for f in fields(cls)}
            rule = cls(**{k: v for k, v in data.items() if k in names})
            if rule.kind not in ("keep_out", "quiet"):
                return None
            rule.cond()
            rule.trigger()
            return rule
        except (TypeError, ValueError, BadRequest):
            return None

    def cond(self):
        return cond_from(self.while_) if self.while_ else None

    def trigger(self):
        return trigger_from(self.until) if self.until else None

    def what(self) -> str:
        return f"keep out of the {self.place}" if self.kind == "keep_out" else "keep quiet"

    def about(self) -> str:
        return f"the {self.place}" if self.kind == "keep_out" else "keeping quiet"


def limit_s(asker: Asker) -> float | None:
    if asker.owner:
        return None
    if asker.tier in (TRUSTED, INNER):
        return WEEK_S
    if asker.tier == FRIEND:
        return DAY_S
    if asker.tier == CHILD:
        return CHILD_S
    return 0.0


def rank_of(tier: str, owner: bool) -> int:
    return OWNER_RANK if owner else RANK.get(tier, 0)


def _until(trigger) -> str:
    words = event_words(trigger)
    return "until " + (words[5:] if words.startswith("when ") else words)


def _clock_end(moment: datetime, now: datetime) -> str:
    said = moment_words(moment, now)
    for lead in ("at ", "on "):
        if said.startswith(lead):
            return said[len(lead):]
    return said


def next_window(frm: str, to: str, now: float, local) -> tuple[float, float]:
    today = local(now).date()
    start, end = hm(frm), hm(to)
    for offset in (-1, 0, 1, 2):
        day = today + timedelta(days=offset)
        begin = instant(datetime.combine(day, start), local)
        finish = instant(datetime.combine(day + timedelta(days=1 if end <= start else 0), end), local)
        if finish > now:
            return max(begin, now), finish
    return now, now


def in_window(rule: Rule, moment: datetime) -> bool:
    days = rule.days
    if not rule.window:
        return not days or moment.strftime("%a").lower()[:3] in days
    start, end = hm(rule.window[0]), hm(rule.window[1])
    now = moment.time().replace(tzinfo=None)
    if start < end:
        inside, day = start <= now < end, moment.date()
    else:
        inside = now >= start or now < end
        day = moment.date() if now >= start else moment.date() - timedelta(days=1)
    return inside and (not days or day.strftime("%a").lower()[:3] in days)


class HouseRules:
    def __init__(self, life):
        self.life = life
        p = life.p
        self.store = p.store
        self.clock = p.clock
        data = {}
        try:
            data = self.store.read(RULES, {}) or {}
        except Exception:
            log.exception("the house rules could not be read; starting with none")
        self.rules: list[Rule] = [rule for rule in (Rule.from_dict(d) for d in data.get("rules") or []) if rule is not None]
        self.next_id = max([int(data.get("next_id") or 1)] + [rule.id + 1 for rule in self.rules])
        self.dirty = False
        self.swept = -math.inf
        self.checked = -math.inf
        self.went_in: dict = {}
        self.charging = ""

    @property
    def commands(self):
        return self.life.commands

    @property
    def company(self):
        return self.life.company

    def now(self) -> float:
        return self.clock.now()

    def local(self, ts: float | None = None) -> datetime:
        return self.clock.local(self.now() if ts is None else ts)

    def record(self, kind: str, **data) -> None:
        self.life.p.blackbox.record(kind, **data)

    def note(self, text: str, major: bool = False) -> None:
        self.commands.note(text, major)

    def say(self, text: str) -> None:
        if not text:
            return
        commands = self.commands
        commands.recent.append(f"pebble: {text[:160]}")
        del commands.recent[:-6]
        commands._spawn(commands.speak(text, False))

    def owe(self, person_id: str | None, text: str) -> None:
        later = getattr(self.life, "later", None)
        if later is not None and person_id:
            later.agenda.owe(person_id, text, self.now())

    def save(self, force: bool = False) -> None:
        if not self.dirty and not force:
            return
        data = {"format": 1, "rules": [rule.to_dict() for rule in self.rules if rule.state == "on"], "next_id": self.next_id}
        try:
            self.store.write(RULES, data)
            self.dirty = False
        except Exception:
            log.exception("the house rules could not be saved")

    def tier_of(self, person_id: str | None) -> tuple[str, bool]:
        person = self.company.book.get(person_id) if person_id else None
        if person is None:
            return STRANGER, False
        return self.company.tier(person, self.now()), person.is_owner

    def on(self) -> list[Rule]:
        return [rule for rule in self.rules if rule.state == "on"]

    def holding(self, now: float | None = None) -> list[Rule]:
        now = self.now() if now is None else now
        moment = self.local(now)
        out = []
        for rule in self.on():
            if now < rule.starts or (rule.ends is not None and now >= rule.ends):
                continue
            if (rule.window or rule.days) and not in_window(rule, moment):
                continue
            if rule.while_ and not rule.holding:
                continue
            out.append(rule)
        return out

    def exempt(self) -> str:
        life = self.life
        if life.alarm():
            return "alarm"
        current = life.commands.runner.current
        if current is None:
            return ""
        if current.urgent:
            return "alarm"
        if current.kind == "go_home" or current.homing or current.battery:
            return "charger"
        if current.kind == "back_off":
            return "space"
        return ""

    def kept_out(self) -> dict:
        if self.exempt():
            return {}
        out = {}
        for rule in self.holding():
            if rule.kind == "keep_out":
                out.setdefault(rule.place, rule.by_label)
        return out

    def quiet_now(self) -> bool:
        if self.life.alarm():
            return False
        return any(rule.kind == "quiet" for rule in self.holding())

    def _rooms(self) -> dict:
        alive = getattr(self.life, "alive", None)
        rooms = getattr(getattr(alive, "rooms", None), "rooms", None)
        return dict(rooms) if isinstance(rooms, dict) else {}

    def _pose(self) -> tuple[float, float] | None:
        odometer = getattr(self.life, "odometer", None)
        if odometer is None or not getattr(odometer, "usable", False):
            return None
        x, y, _ = odometer.pose()
        return x, y

    def here(self) -> str | None:
        alive = getattr(self.life, "alive", None)
        try:
            return alive.rooms.where_am_i() if alive is not None else None
        except Exception:
            return None

    def circles(self) -> list:
        pose = self._pose()
        if pose is None:
            return []
        rooms = self._rooms()
        out = []
        for place in self.kept_out():
            room = rooms.get(place)
            if room is None or math.hypot(room.x - pose[0], room.y - pose[1]) <= room.radius:
                continue
            out.append((room.x, room.y, max(SMALLEST_M, room.radius - MARGIN_M)))
        return out

    def fence(self, goal: tuple[float, float] | None) -> tuple[str, str] | None:
        pose = self._pose()
        if goal is None or pose is None:
            return None
        kept = self.kept_out()
        if not kept:
            return None
        x, y = pose
        gap = math.hypot(goal[0] - x, goal[1] - y)
        if gap > AHEAD_M:
            goal = (x + (goal[0] - x) / gap * AHEAD_M, y + (goal[1] - y) / gap * AHEAD_M)
        rooms = self._rooms()
        steps = max(1, int(min(gap, AHEAD_M) / STEP_M))
        for place in kept:
            room = rooms.get(place)
            if room is None or math.hypot(room.x - x, room.y - y) <= room.radius:
                continue
            for i in range(1, steps + 1):
                t = i / steps
                if math.hypot(room.x - (x + (goal[0] - x) * t), room.y - (y + (goal[1] - y) * t)) <= room.radius:
                    rule = self._rule_for(place)
                    return place, self.line(rule) if rule is not None else f"I was asked to stay out of the {place}."
        return None

    def kept_at(self, x: float, y: float) -> str | None:
        rooms = self._rooms()
        for place in self.kept_out():
            room = rooms.get(place)
            if room is not None and math.hypot(room.x - x, room.y - y) <= room.radius:
                return place
        return None

    def _rule_for(self, place: str, kind: str = "keep_out") -> Rule | None:
        found = [rule for rule in self.holding() if rule.kind == kind and rule.place == place]
        return found[0] if found else None

    def lasting(self, rule: Rule, now: float | None = None, you: bool = False) -> str:
        now = self.now() if now is None else now
        moment = self.local(now).replace(tzinfo=None)
        if rule.while_:
            return f"while {cond_words(rule.cond())}"
        if rule.until:
            return _until(rule.trigger())
        if rule.days:
            out = _days_words(tuple(rule.days), 0)
            if rule.window:
                out += f" from {clock_words(rule.window[0])} until {clock_words(rule.window[1])}"
            return out
        if rule.told:
            whom = "you say" if you else f"{rule.by_label} says"
            return f"until {whom} I can {'go in' if rule.kind == 'keep_out' else 'talk again'}"
        if rule.ends is not None:
            end = _clock_end(self.local(rule.ends).replace(tzinfo=None), moment)
            if rule.starts > now + 60.0:
                return f"from {_clock_end(self.local(rule.starts).replace(tzinfo=None), moment)} until {end}"
            return f"until {end}"
        return ""

    def line(self, rule: Rule) -> str:
        span = self.lasting(rule)
        span = f" {span}" if span else ""
        if rule.kind == "keep_out":
            return f"{rule.by_label} asked me to stay out of the {rule.place}{span}."
        return f"{rule.by_label} asked me to keep quiet{span}."

    def places_of(self, request: Request) -> set:
        kind = request.kind
        if kind == "go_to_place" and request.place:
            return {request.place}
        if kind == "check" and request.place and request.place not in ("house", "home", "the house", "everywhere") and not request.thing:
            return {request.place}
        if kind == "climate_round" and request.place:
            return {request.place}
        return set()

    def blocking(self, request: Request, asker: Asker, made: float | None = None) -> Rule | None:
        if self.exempt():
            return None
        places = self.places_of(request)
        if not places:
            return None
        for rule in self.holding():
            if rule.kind != "keep_out" or rule.place not in places:
                continue
            if asker.own or rule.by != asker.id or (made is not None and rule.made > made):
                return rule
        return None

    async def check(self, request: Request, asker: Asker, how: str, newest: bool = True) -> Verdict | None:
        places = self.places_of(request)
        if not places or self.exempt():
            return None
        found = [rule for rule in self.holding() if rule.kind == "keep_out" and rule.place in places]
        if not found:
            return None
        others = [rule for rule in found if asker.own or rule.by != asker.id or not newest]
        if not others:
            for rule in found:
                self.end(rule, f"{asker.label} asked you to go there instead, and the newest wish wins")
            said = f"Okay, that ends your rule about the {found[0].place}."
            self.say(said)
            self.record("rule_replaced", rule=found[0].id, person=asker.id)
            return None
        rule = others[0]
        reason = f"{rule.by_label} asked you to stay out of the {rule.place}"
        self.record("rule_kept", rule=rule.id, person=asker.id, asked=request.kind)
        if asker.own:
            return Verdict("no", reason, "")
        said = self.line(rule)
        if self.may_lift(asker, rule):
            said += " If it's fine now, tell me I can go in."
        self.note(f"{asker.label} asked you to {for_mind(request)}, but {reason}, so you said no")
        self.life.p.face.show("thinking")
        self.say(said)
        return Verdict("no", reason, said)

    def may_lift(self, asker: Asker, rule: Rule) -> bool:
        if asker.own or asker.id is None or asker.tier in (STRANGER,):
            return False
        if asker.id == rule.by or asker.owner:
            return True
        tier, owner = self.tier_of(rule.by)
        if owner or asker.tier == CHILD:
            return False
        return rank_of(asker.tier, asker.owner) > rank_of(tier, owner)

    async def route(self, request: Request, asker: Asker, how: str) -> Verdict | None:
        kind = request.kind
        if kind not in ("set_rule", "end_rule", "list_rules"):
            return None
        if kind == "set_rule" and request.on is not None:
            return None
        if asker.own:
            return Verdict("no", "house rules come from the people you live with", "")
        if kind == "list_rules":
            verdict = self.list_for(asker)
        elif kind == "end_rule":
            verdict = self.lift(request, asker)
        else:
            verdict = self.set(request, asker)
        if request.then and verdict.answer != "no":
            first, rest = request.then[0], tuple(request.then[1:])
            await self.commands.act(first.with_(then=rest + first.then), self.commands.fresh(asker), "then")
        return verdict

    def _refuse(self, asker: Asker, reason: str, said: str) -> Verdict:
        self.record("rule_refused", person=asker.id, tier=asker.tier, reason=reason)
        self.note(f"{asker.label} asked you to keep a house rule; you said no ({reason})")
        self.say(said)
        self.commands.refused_to(asker, said, "keep a house rule")
        return Verdict("no", reason, said)

    def set(self, request: Request, asker: Asker) -> Verdict:
        now = self.now()
        if asker.tier == STRANGER:
            return self._refuse(asker, "you keep house rules only for people you know", STRANGER_NO)
        if request.rule == "keep_out" and asker.tier == CHILD:
            return self._refuse(asker, "only grown-ups may keep you out of a room", CHILD_ROOM_NO)
        if request.rule == "keep_out" and not request.place:
            return self._refuse(asker, "they did not say which room", WHICH_ROOM)
        mine = [rule for rule in self.on() if rule.by == asker.id]
        same = [rule for rule in mine if rule.kind == request.rule and (rule.kind == "quiet" or rule.place == request.place)]
        if len(self.on()) - len(same) >= IN_ALL:
            return self._refuse(asker, "you keep as many rules as you can", FULL)
        if len(mine) - len(same) >= PER_PERSON:
            return self._refuse(asker, "they have as many rules as they can", YOURS_FULL)
        rule, capped = self._made(request, asker, now)
        for old in same:
            self.end(old, "a newer rule from the same person replaced it")
        self.rules.append(rule)
        self.next_id += 1
        self.dirty = True
        if rule.while_:
            self._check_while(rule)
        self.save(force=True)
        said = self.read_back(rule, request, capped, asker)
        if same:
            said += " That replaces the one you asked for before."
        self.record("rule_set", rule=rule.id, what=rule.kind, person=asker.id, tier=asker.tier, ends=round(rule.ends, 1) if rule.ends else None, capped=bool(capped))
        self.note(f"{asker.label} gave you a house rule: {rule.what()}" + (f" {self.lasting(rule)}" if self.lasting(rule) else ""))
        self.say(said)
        if rule.kind == "keep_out" and rule.starts <= now and self.here() == rule.place:
            self._leave(rule)
        return Verdict("yes", f"{asker.label} may set that house rule", said)

    def _made(self, request: Request, asker: Asker, now: float) -> tuple[Rule, str]:
        local = self.clock.local
        later = getattr(self.life, "later", None)
        parts = later.agenda.parts_for(asker.id) if later is not None else {}
        starts, ends, window, days, told, until = now, None, [], [], False, None
        when = request.when
        if when is not None:
            if when.in_s:
                starts = now + when.in_s
            frm = when.from_ or (part_time(when.part, parts) if when.part else "") or (when.at if when.to else "")
            to = when.to or (PART_ENDS.get(when.part, "") if when.part else "")
            if when.date:
                day = date.fromisoformat(when.date)
                starts = max(now, instant(datetime.combine(day, time(0)), local))
                ends = instant(datetime.combine(day + timedelta(days=1), time(0)), local)
            elif when.days:
                days = list(when.days)
                if frm and to:
                    window = [frm, to]
            elif frm and to:
                starts, ends = next_window(frm, to, now, local)
            elif when.at:
                found = next_time(When(at=when.at), now - 1.0, now, local, parts)
                if found is not None:
                    starts = found[0]
            if when.until_date:
                last = instant(datetime.combine(date.fromisoformat(when.until_date) + timedelta(days=1), time(0)), local)
                ends = last if ends is None else min(ends, last)
        if request.seconds:
            ends = starts + request.seconds if ends is None else min(ends, starts + request.seconds)
        cap = None
        if request.until_on is not None:
            until = request.until_on.as_dict()
            cap = starts + EVENT_MOST_S
        elif request.until == "back":
            until = {"event": "arrives", "who": "me"}
            cap = starts + EVENT_MOST_S
        elif request.until in ("told", "called", "asked"):
            told = True
        if request.while_ is not None:
            cap = starts + WHILE_MOST_S if cap is None else min(cap, starts + WHILE_MOST_S)
        if cap is not None:
            ends = cap if ends is None else min(ends, cap)
        most = limit_s(asker)
        capped = ""
        if most is not None:
            hard = starts + most
            if ends is None or ends > hard + 1.0:
                ends = hard
                capped = CAPPED.get(asker.tier, "")
        rule = Rule(self.next_id, request.rule, request.place if request.rule == "keep_out" else "", asker.id, asker.label, asker.tier, now, starts, ends, window, days, request.while_.as_dict() if request.while_ is not None else None, until, told)
        return rule, capped

    def read_back(self, rule: Rule, request: Request, capped: str, asker: Asker) -> str:
        now = self.now()
        moment = self.local(now).replace(tzinfo=None)
        if request.seconds and not (rule.while_ or rule.until or rule.days or capped):
            span = f"for {span_words(request.seconds)}"
        else:
            span = self.lasting(rule, now, you=True)
        out = f"Okay: I'll {rule.what()}" + (f" {span}" if span else "") + "."
        if capped:
            if not span.startswith("until") or rule.told or rule.until:
                out += f" I'll keep it until {_clock_end(self.local(rule.ends).replace(tzinfo=None), moment)} at the most."
            out += f" {capped}"
        return out

    def _leave(self, rule: Rule) -> None:
        rooms = self._rooms()
        pose = self._pose()
        commands = self.commands
        if pose is None or commands.runner.busy:
            return
        kept = set(self.kept_out())
        privacy = getattr(self.life, "privacy", None)
        private = privacy.private_places() if privacy is not None else frozenset()
        choices = [(math.hypot(room.x - pose[0], room.y - pose[1]), name) for name, room in rooms.items() if name not in kept and name not in private]
        if not choices:
            return
        place = min(choices)[1]
        self.note(f"you are in the {rule.place}, which you were just asked to keep out of, so you head to the {place}")
        commands._spawn(commands.act(Request("go_to_place", place=place), PEBBLE, "rule"))

    def lift(self, request: Request, asker: Asker) -> Verdict:
        if asker.tier == STRANGER:
            return self._refuse(asker, "only people you know change the house rules", "Only the people I know can change the house rules.")
        rules = self.on()
        if not rules:
            self.say(NOT_KEPT)
            return Verdict("no", "there were no rules to end", NOT_KEPT)
        if request.rule == "quiet":
            found = [rule for rule in rules if rule.kind == "quiet"]
        elif request.place:
            found = [rule for rule in rules if rule.kind == "keep_out" and rule.place == request.place]
        elif request.rule == "keep_out":
            found = [rule for rule in rules if rule.kind == "keep_out"]
            if len({rule.place for rule in found}) > 1:
                said = "Which room: the " + listing(sorted({rule.place for rule in found})).replace(" and ", " or the ") + "?"
                self.say(said)
                return Verdict("ask", "more than one room is kept out of", said)
        else:
            found = [rule for rule in rules if rule.by == asker.id] or rules
        if not found:
            self.say(NONE_LIKE)
            return Verdict("no", "no rule matched", NONE_LIKE)
        ended = [rule for rule in found if self.may_lift(asker, rule)]
        kept = [rule for rule in found if rule not in ended]
        later = getattr(self.life, "later", None)
        for rule in ended:
            self.end(rule, f"{asker.label} lifted it")
            if rule.by != asker.id and not (later is not None and later.senses.with_pebble(rule.by, self.now())):
                self.owe(rule.by, f"{asker.label} lifted your house rule about {rule.about()}.")
        self.save(force=True)
        said = ""
        if ended:
            kinds = {(rule.kind, rule.place) for rule in ended}
            if len(kinds) > 1:
                said = "Okay, I've ended those house rules."
            elif ended[0].kind == "quiet":
                said = "Okay, I don't have to keep quiet any more."
            else:
                said = f"Okay, I can go in the {ended[0].place} again."
        if kept:
            rule = kept[0]
            if ended:
                still = "still keeps me out of the " + rule.place if rule.kind == "keep_out" else "still has me keeping quiet"
                span = self.lasting(rule)
                said += f" {rule.by_label}'s rule {still}" + (f" {span}" if span else "") + "."
            else:
                said = f"That's {rule.by_label}'s rule, so only {rule.by_label} or someone closer to me can end it."
        said = said.strip()
        self.record("rule_lifted", rules=[rule.id for rule in ended], kept=len(kept), person=asker.id)
        self.note(f"{asker.label} asked you to end a house rule: {said}")
        self.say(said)
        return Verdict("yes" if ended else "no", "ended" if ended else "they may not end that rule", said)

    def list_for(self, asker: Asker) -> Verdict:
        if asker.tier == STRANGER:
            self.say(STRANGER_LIST)
            return Verdict("no", "a stranger asked about the house rules", STRANGER_LIST)
        rules = self.on()
        if not rules:
            self.say(NOT_KEPT)
            return Verdict("yes", "no rules", NOT_KEPT)
        said = []
        for rule in rules:
            span = self.lasting(rule, you=rule.by == asker.id)
            said.append(f"I {rule.what()}" + (f" {span}" if span else "") + f", for {'you' if rule.by == asker.id else rule.by_label}")
        count = "one house rule" if len(rules) == 1 else f"{len(rules)} house rules"
        text = f"I'm keeping {count}: " + "; ".join(said) + "."
        self.say(text)
        self.record("rules_listed", person=asker.id, count=len(rules))
        return Verdict("yes", "listed", text)

    def end(self, rule: Rule, why: str) -> None:
        if rule.state != "on":
            return
        rule.state = "ended"
        self.rules = [other for other in self.rules if other is not rule]
        self.dirty = True
        self.record("rule_ended", rule=rule.id, what=rule.kind)
        self.note(f"the house rule to {rule.what()} for {rule.by_label} is over: {why}")

    def forget(self, person_id: str, names: list) -> None:
        for rule in [rule for rule in self.on() if rule.by == person_id]:
            self.end(rule, "you forgot the person who set it")
        self.save(force=True)

    def _check_while(self, rule: Rule) -> None:
        later = getattr(self.life, "later", None)
        if later is None:
            rule.holding = True
            return
        value = evaluate(rule.cond(), lambda cond: later.senses.state(cond, rule.by))
        if value is False:
            if rule.holding:
                self.end(rule, f"{cond_words(rule.cond(), True)} now")
            return
        rule.holding = True

    def tick(self, now: float, happened: list = ()) -> None:
        mono = self.clock.monotonic()
        if mono - self.swept >= SWEEP_S:
            self.swept = mono
            for rule in list(self.on()):
                if rule.by is None:
                    continue
                tier, _ = self.tier_of(rule.by)
                if tier == STRANGER:
                    self.end(rule, "the person who set it is now a stranger to you")
        checking = mono - self.checked >= WHILE_EVERY_S
        if checking:
            self.checked = mono
        later = getattr(self.life, "later", None)
        for rule in list(self.on()):
            if rule.ends is not None and now >= rule.ends:
                self.end(rule, "its time ran out")
                continue
            if now < rule.starts:
                continue
            if rule.until and later is not None:
                trigger = rule.trigger()
                whom = {"me": rule.by, "": rule.by}
                for one in trigger.first_of or (trigger,):
                    if one.who and one.who not in whom:
                        person = self.company.book.find(one.who)
                        whom[one.who] = person.id if person is not None else None
                hit = next((h for h in happened if getattr(h, "at", now) > rule.made + SETTLE_S and match(trigger, h, whom)), None)
                if hit is None:
                    hit = next((one for one in trigger.first_of or (trigger,) if one.event in ("quiet", "battery", "tv_off") and later.senses.edge(one, rule.starts)), None)
                if hit is not None:
                    part = hit if hasattr(hit, "first_of") else trigger
                    self.end(rule, happened_words(part))
                    continue
            if rule.while_ and checking:
                self._check_while(rule)
        self._alarm_watch()
        self.save()

    def _alarm_watch(self) -> None:
        if self.exempt() == "alarm":
            room = self.here()
            if room is not None and room not in self.went_in:
                rule = self._rule_for(room)
                if rule is not None:
                    self.went_in[room] = rule
                    self.record("rule_broken_for_alarm", rule=rule.id)
            return
        if not self.went_in:
            return
        gone, self.went_in = self.went_in, {}
        for room, rule in gone.items():
            said = f"I went into the {room} because of the alarm, even though {rule.by_label} asked me to stay out."
            self.say(said)
            self.note(f"during the alarm you went into the {room}, which {rule.by_label} had asked you to keep out of; you said why")
            later = getattr(self.life, "later", None)
            if rule.by and later is not None and not later.senses.with_pebble(rule.by, self.now()):
                self.owe(rule.by, said)

    def for_charger(self) -> str:
        rooms = self._rooms()
        kept = [rule for rule in self.holding() if rule.kind == "keep_out"]
        for rule in kept:
            room = rooms.get(rule.place)
            if room is not None and math.hypot(room.x, room.y) <= room.radius:
                self.record("rule_broken_for_charger", rule=rule.id)
                return f"My battery's low and my charger is in the {rule.place}, so I'm going in to charge, even though {rule.by_label} asked me to stay out."
        return ""

    def matched(self) -> str:
        rules = self.holding()
        if not rules:
            return ""
        current = self.commands.runner.current
        here = self.here()
        places = {here}
        if current is not None:
            places.add(current.request.place)
        plan = self.commands.plan
        if plan is not None:
            places.update(step.place for step in plan.steps)
        wanted = [rule for rule in rules if rule.kind != "quiet" and here and rule.place == here]
        wanted += [rule for rule in rules if rule.kind != "quiet" and rule.place in places and rule not in wanted]
        wanted += [rule for rule in rules if rule.kind == "quiet"]
        if not wanted:
            return ""
        said = []
        for rule in wanted[:MATCHED_MOST]:
            span = self.lasting(rule)
            said.append(f"{rule.what()}" + (f" {span}" if span else "") + f" ({rule.by_label} asked)")
        return "House rules: " + "; ".join(said) + "."
