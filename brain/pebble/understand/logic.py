import re
from dataclasses import replace
from datetime import date, datetime

from ..things.words import spoken
from .request import DAYS, TOO_MUCH, Cond, Request, Trigger, When, too_big, unless

CANNOT_TELL_EVENT = "I can't tell when that happens."
MIN_EVERY_S = 300.0
NOBODY = ("nobody", "no one", "noone", "no body")
ANYBODY = ("anyone", "anybody", "someone", "somebody", "everyone", "everybody")
LOOK_ROUND = re.compile(r"^(?:(?:have|take|do|go for|go on|make) (?:a |your |the |my )?)?(?:look|walk|wander|patrol|check|round|rounds)(?: (?:a)?round| about)?(?: (?:the|my|your|our) [a-z ]+| it| everywhere)?$")
ASKED = re.compile(r"^(?:(?:remind|tell) (?:me|you)(?: to| that| about)?|let (?:me|you) know(?: that| about)?)(?: |$)")
CANNOT_TELL_STATE = "I can't tell that."
DAY_NAMES = dict(zip(DAYS, ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")))
DAY_LOWER = frozenset(day.lower() for day in DAY_NAMES.values())
WEEKDAYS = DAYS[:5]
WEEKENDS = DAYS[5:]
NTH = {2: "other", 3: "third", 4: "fourth"}
ORDINAL = {1: "st", 2: "nd", 3: "rd", 21: "st", 22: "nd", 23: "rd", 31: "st"}
SOUNDS = {"knock": "a knock at the door", "doorbell": "the doorbell", "smoke alarm": "the smoke alarm", "alarm": "an alarm", "phone": "a phone ring"}
MINE = {"my": "your", "me": "you", "i": "you", "i'm": "you're", "im": "you're", "i've": "you've", "i'll": "you'll", "myself": "yourself", "mine": "yours", "am": "are"}
DOING = re.compile(r"^(?:take|call|ring|phone|text|email|put|feed|buy|get|check|pay|send|walk|charge|lock|unlock|watch|ask|start|stretch|drink|eat|renew|go|pick|book|water|empty|clean|turn|bring|make|collect|wash|tell|visit|move|leave|look|find|fetch|post|write|read|cook|order|cancel|close|open|shut|switch|plug|unplug|change|fill|grab|hang|sort|tidy|do|finish|ring|have|let|meet|wake|brush|sign|set|log|reply|return|vote|apply|wrap|print|study|practise|practice)\b")


def plural(count: float, word: str) -> str:
    whole = int(round(count))
    return f"{whole} {word}" if whole == 1 else f"{whole} {word}s"


def span_words(seconds: float) -> str:
    seconds = float(seconds)
    if seconds < 90:
        return plural(seconds, "second")
    if seconds < 5400 and seconds % 3600:
        return plural(seconds / 60.0, "minute")
    if seconds == 5400:
        return "an hour and a half"
    if seconds < 86400 * 2:
        return "an hour" if round(seconds / 3600.0) == 1 else plural(seconds / 3600.0, "hour")
    return plural(seconds / 86400.0, "day")


def every_words(seconds: float) -> str:
    seconds = float(seconds)
    if seconds == 3600:
        return "every hour"
    if seconds == 1800:
        return "every half hour"
    if seconds == 86400:
        return "every day"
    return "every " + span_words(seconds)


def clock_words(hhmm: str) -> str:
    hour, minute = (int(part) for part in hhmm.split(":", 1))
    if (hour, minute) == (12, 0):
        return "midday"
    if (hour, minute) == (0, 0):
        return "midnight"
    base = f"{hour % 12 or 12}" if minute == 0 else f"{hour % 12 or 12}:{minute:02d}"
    if 5 <= hour < 12:
        return f"{base} in the morning"
    if 12 <= hour < 18:
        return f"{base} in the afternoon"
    if 18 <= hour < 21:
        return f"{base} in the evening"
    return f"{base} at night"


def clock_short(hhmm: str) -> str:
    hour, minute = (int(part) for part in hhmm.split(":", 1))
    return f"{hour % 12 or 12}" if minute == 0 else f"{hour % 12 or 12}:{minute:02d}"


def date_words(day: date, today: date) -> str:
    gap = (day - today).days
    if gap == 0:
        return "today"
    if gap == 1:
        return "tomorrow"
    if 1 < gap < 7:
        return f"this {day.strftime('%A')}"
    return f"{day.strftime('%A')} {day.day} {day.strftime('%B')}"


def moment_words(moment: datetime, now: datetime) -> str:
    hhmm = f"{moment.hour:02d}:{moment.minute:02d}"
    gap = (moment.date() - now.date()).days
    if gap == 0:
        if moment.hour >= 18:
            return f"at {clock_short(hhmm)} tonight"
        return f"at {clock_words(hhmm)} today"
    if gap == 1:
        return f"tomorrow at {clock_words(hhmm)}"
    if 1 < gap < 7:
        return f"on {moment.strftime('%A')} at {clock_words(hhmm)}"
    return f"on {moment.strftime('%A')} {moment.day} {moment.strftime('%B')} at {clock_words(hhmm)}"


def first_words(moment: datetime, now: datetime) -> str:
    day = date_words(moment.date(), now.date())
    if day in ("today", "tomorrow"):
        return f"The first one is {day}."
    return f"The first one is {day}." if day.startswith("this ") else f"The first one is on {day}."


def _days_words(days: tuple, every_weeks: int) -> str:
    lead = "every " + (NTH[every_weeks] + " " if every_weeks in NTH else "")
    if set(days) == set(DAYS):
        return "every day" if not every_weeks else lead + "day"
    if tuple(days) == WEEKDAYS:
        return lead + "weekday"
    if tuple(days) == WEEKENDS:
        return lead + "Saturday and Sunday"
    names = [DAY_NAMES[day] for day in days]
    return lead + (" and ".join(names) if len(names) <= 2 else ", ".join(names[:-1]) + " and " + names[-1])


def _month_words(month_day: int) -> str:
    if month_day < 0:
        return "on the last day of every month"
    return f"on the {month_day}{ORDINAL.get(month_day, 'th')} of every month"


def when_words(when: When, first: datetime | None, now: datetime, hhmm: str = "") -> str:
    hhmm = when.at or hhmm
    if when.every_s:
        out = every_words(when.every_s)
        if when.days:
            out += " on " + _days_words(when.days, 0)[6:] + ("s" if len(when.days) == 1 else "")
        begin = when.from_ or (hhmm if when.part and not when.from_ else "")
        if begin:
            out += f" from {clock_words(begin)}"
        elif first is not None:
            out += f", starting {moment_words(first, now)}"
        if when.to:
            out += f" until {clock_words(when.to)}"
        elif not begin and not (when.days or when.until_date or when.times):
            out += " until this time tomorrow"
        return out + _end_words(when, now)
    if when.repeats:
        if when.month_day:
            out = _month_words(when.month_day)
            if when.days:
                out += " that's a " + _days_words(when.days, 0)[6:]
        else:
            out = _days_words(when.days, when.every_weeks)
        if hhmm:
            out += f" at {clock_words(hhmm)}"
        return out + _end_words(when, now)
    if first is None:
        return "later"
    if when.in_s and not (when.at or when.part or when.date):
        return f"in {span_words(when.in_s)}"
    return moment_words(first, now)


def _end_words(when: When, now: datetime) -> str:
    out = ""
    if when.until_date:
        out += f" until {date_words(date.fromisoformat(when.until_date), now.date())}"
    if when.times:
        out += ", once" if when.times == 1 else f", {when.times} times"
    return out


def name(who: str, you: bool = False) -> str:
    if who in ("", "me"):
        return "you"
    return " ".join(part.capitalize() for part in who.split())


def _thing(thing: str) -> str:
    if thing in ("it", "that", "them"):
        return thing
    return SOUNDS.get(thing) or f"the {spoken(thing)}"


def patrol(request: Request) -> bool:
    if request.kind != "check" or request.thing:
        return False
    return not request.text or bool(LOOK_ROUND.match(" ".join(request.text.lower().split()).strip(" .!")))


def _cond(cond: Cond) -> Cond:
    if cond.join:
        return replace(cond, parts=tuple(_cond(part) for part in cond.parts))
    if cond.state in ("present", "in_room") and cond.who in NOBODY + ANYBODY:
        nobody = cond.who in NOBODY
        cond = replace(cond, who="")
        if cond.place:
            cond = replace(cond, state="in_room")
            return unless(cond) if nobody else cond
    if cond.state == "present" and cond.place and not cond.who:
        cond = replace(cond, state="in_room")
    if cond.state != "result" and cond.is_:
        negated = cond.is_ == "no"
        cond = replace(cond, is_="")
        if negated:
            return unless(cond)
    return cond


def _step(step: Request) -> Request:
    changes = {}
    if step.if_ is not None:
        changes["if_"] = _cond(step.if_)
    if step.while_ is not None:
        changes["while_"] = _cond(step.while_)
    if step.kind == "say_to" and step.who in ("", "me") and step.text:
        changes["text"] = ASKED.sub("", step.text.strip(), 1).strip()
    if step.then:
        changes["then"] = tuple(_step(inner) for inner in step.then)
    if step.else_:
        changes["else_"] = tuple(_step(inner) for inner in step.else_)
    return step.with_(**changes) if changes else step


def tidy(request: Request) -> Request:
    request = _step(request)
    when = request.when
    if when is not None and when.every_s and when.every_s < MIN_EVERY_S:
        when = replace(when, every_s=0.0, from_="", to="")
        request = request.with_(when=when if when.as_dict() else None)
    return request


def event_words(trigger: Trigger) -> str:
    if trigger.first_of:
        return " or ".join(event_words(one) for one in trigger.first_of) + ", whichever comes first"
    event, who = trigger.event, name(trigger.who)
    if event == "arrives":
        return "when you get home" if who == "you" else f"when {who} gets home"
    if event == "leaves":
        whom = "you" if who == "you" else "them"
        gone = "when you go out" if who == "you" else f"when {who} goes out"
        return f"{gone} (that's my guess, once I haven't seen {whom} for 10 minutes)"
    if event == "sound":
        return f"when I hear {_thing(trigger.thing or trigger.what or 'that sound')}"
    if event == "seen":
        if trigger.who and not trigger.thing:
            return "when I see you" if who == "you" else f"when I see {who}"
        return f"when I see {_thing(trigger.thing or trigger.what or 'it')}"
    if event == "quiet":
        return f"once it's been quiet for {plural(trigger.minutes or 10, 'minute')}"
    if event == "done":
        return "when I've finished what I'm doing"
    if event == "at":
        return f"at {clock_words(trigger.at)}" if trigger.at else "at that time"
    if event == "battery":
        return f"when my battery drops below {int(trigger.level or 20)} percent"
    if event == "tv_off":
        return "when the room has been quiet for 10 minutes (I can't tell the TV itself)"
    return "when that happens"


def happened_words(trigger: Trigger) -> str:
    event, who = trigger.event, name(trigger.who)
    if event == "arrives":
        return "you're home" if who == "you" else f"{who}'s home"
    if event == "leaves":
        return f"I think {'you have' if who == 'you' else who + ' has'} gone out (that's a guess)"
    if event == "sound":
        return f"I heard {_thing(trigger.thing or trigger.what or 'that sound')}"
    if event == "seen":
        if trigger.who and not trigger.thing:
            return f"there's {who}"
        return f"there's {_thing(trigger.thing or trigger.what or 'it')}"
    if event in ("quiet", "tv_off"):
        return "it's gone quiet"
    if event == "battery":
        return "my battery's getting low"
    if event == "at":
        return f"it's {clock_short(trigger.at)}" if trigger.at else "it's time"
    return "that's happened"


def missed_words(trigger: Trigger) -> str:
    if trigger.first_of:
        return " and ".join(missed_words(one) for one in trigger.first_of)
    event, who = trigger.event, name(trigger.who)
    if event == "arrives":
        return "you didn't come home while I was watching" if who == "you" else f"{who} didn't come home while I was watching"
    if event == "leaves":
        return f"{who} didn't seem to go out while I was watching"
    if event == "sound":
        return f"I didn't hear {_thing(trigger.thing or trigger.what or 'that sound')} while I was listening"
    if event == "seen":
        if trigger.who and not trigger.thing:
            return f"I didn't see {who} while I was watching"
        return f"I didn't see {_thing(trigger.thing or trigger.what or 'it')} while I was watching"
    if event in ("quiet", "tv_off"):
        return "it didn't go quiet while I was listening"
    if event == "battery":
        return "my battery didn't get that low"
    return "it didn't happen while I was watching"


def _cond_leaf(cond: Cond, negate: bool) -> str:
    state, who = cond.state, name(cond.who)
    you = who == "you"
    if state == "present":
        if you:
            return "you aren't home" if negate else "you're home"
        return f"{who} isn't home" if negate else f"{who} is home"
    if state == "in_room":
        place = f"the {cond.place}" if cond.place else "that room"
        if not cond.who:
            return f"nobody is in {place}" if negate else f"someone is in {place}"
        verb = ("aren't" if negate else "are") if you else ("isn't" if negate else "is")
        return f"{who} {verb} in {place}"
    if state == "after":
        return f"it isn't {clock_words(cond.at)} yet" if negate else f"it's after {clock_words(cond.at)}"
    if state == "before":
        return f"it's after {clock_words(cond.at)}" if negate else f"it's before {clock_words(cond.at)}"
    if state == "time_between":
        return f"it isn't between {clock_words(cond.from_)} and {clock_words(cond.to)}" if negate else f"it's between {clock_words(cond.from_)} and {clock_words(cond.to)}"
    if state == "day_is":
        day = cond.day
        if day == "holiday":
            return "today isn't a public holiday" if negate else "today's a public holiday"
        if day == "tomorrow_holiday":
            return "tomorrow isn't a public holiday" if negate else "tomorrow's a public holiday"
        if day == "weekday":
            return "it isn't a weekday" if negate else "it's a weekday"
        if day == "weekend":
            return "it isn't the weekend" if negate else "it's the weekend"
        word = DAY_NAMES.get(day, day)
        return f"it isn't {word}" if negate else f"it's {word}"
    if state == "result":
        answer = cond.is_ or "yes"
        return f"the answer I find isn't {answer}" if negate else f"the answer I find is {answer}"
    if state == "heard_lately":
        minutes = plural(cond.minutes or 30, "minute")
        return f"I haven't heard {_thing(cond.thing or cond.what or 'it')} in the last {minutes}" if negate else f"I've heard {_thing(cond.thing or cond.what or 'it')} in the last {minutes}"
    if state == "seen_lately":
        thing = _thing(cond.thing or cond.what or "it")
        return f"I can't see {thing}" if negate else f"I can see {thing}"
    if state == "battery_below":
        level = int(cond.level or 20)
        return f"my battery isn't below {level} percent" if negate else f"my battery is below {level} percent"
    if state == "doing":
        what = (cond.what or "").replace("_", " ")
        if what:
            return f"I'm not {what}" if negate else f"I'm {what}"
        return "I'm not busy" if negate else "I'm busy"
    if state == "cooking":
        return "nobody's cooking" if negate else "someone's cooking"
    if state == "quiet_hours":
        return "it isn't my quiet time" if negate else "it's my quiet time"
    if state == "room_quiet":
        minutes = plural(cond.minutes or 10, "minute")
        return f"it hasn't been quiet for {minutes}" if negate else f"it's been quiet for {minutes}"
    if state == "looks":
        what = cond.what or "like that"
        target = f"the {cond.place}" if cond.place else (f"the {cond.thing}" if cond.thing else "it")
        return f"{target} doesn't look {what}" if negate else f"{target} looks {what}"
    return "something I can't tell"


def cond_words(cond: Cond, negate: bool = False) -> str:
    if cond.join == "not":
        return cond_words(cond.parts[0], not negate)
    if cond.join in ("all", "any"):
        joiner = " and " if (cond.join == "all") != negate else " or "
        parts = [cond_words(part, negate) for part in cond.parts]
        return joiner.join(parts) if len(parts) <= 2 else ", ".join(parts[:-1]) + joiner + parts[-1]
    return _cond_leaf(cond, negate)


def yours(text: str) -> str:
    words = text.split(" ")
    return " ".join(MINE.get(word.lower(), word) for word in words)


def reminder_words(text: str, names: tuple = ()) -> str:
    said = " ".join(text.split()).strip(" .!")
    if not said:
        return ""
    shown = []
    for word in yours(said).split(" "):
        bare = word.lower().strip(",.!?")
        bare = bare[:-2] if bare.endswith("'s") else bare
        if bare in names or bare in DAY_LOWER:
            word = word[:1].upper() + word[1:]
        shown.append(word)
    return " ".join(shown)


def wake_up(text: str) -> bool:
    return bool(re.match(r"^(?:wake(?: me)?(?: up)?|get up|time to get up)$", " ".join((text or "").lower().split()).strip(" .!")))


def _to_or_that(text: str, names: tuple) -> str:
    said = reminder_words(text, names)
    if not said:
        return ""
    first = said.split(" ")[0].lower().strip(",.!?")
    bare = first[:-2] if first.endswith("'s") else first
    body = said if bare in names or bare in DAY_LOWER else said[:1].lower() + said[1:]
    return f"to {body}" if DOING.match(body.lower()) else f"that {body}"


def step_words(step: Request, names: tuple = ()) -> str:
    kind = step.kind
    if kind == "say_to":
        if step.who not in ("", "me"):
            about = f": {step.text}" if step.text else ""
            return f"tell {name(step.who)}{about}"
        if wake_up(step.text):
            return "wake you"
        about = _to_or_that(step.text, names)
        return f"remind you {about}" if about else "remind you"
    if kind == "go_to_place":
        return f"go to the {step.place}" if step.place else "go there"
    if kind == "come":
        return "come to you" if step.who in ("", "me") else f"go to {name(step.who)}"
    if kind == "go_home":
        return "go back to my charger"
    if kind == "wait":
        return "wait here"
    if kind == "check":
        if patrol(step) and step.place in ("", "house", "home"):
            return "have a look round the house"
        if patrol(step):
            return f"have a look round the {step.place}"
        target = step.thing or step.place
        return f"go and check the {target}" if target else "go and check"
    if kind == "follow":
        return "follow you" if step.who in ("", "me") and not step.thing else f"follow {('the ' + spoken(step.thing)) if step.thing else name(step.who)}"
    if kind == "look":
        return "look at you" if step.who in ("", "me") and not step.thing else f"look at {('the ' + spoken(step.thing)) if step.thing else name(step.who)}"
    if kind == "turn":
        return "spin round" if step.way == "around" else f"turn {step.way}".strip()
    if kind == "if":
        return tree_words(step, names)
    if kind == "go_to_thing":
        return f"go to the {spoken(step.thing)}"
    if kind == "find":
        return f"look for the {spoken(step.thing)}" if step.thing else "look for it"
    if kind == "back_off":
        return "back off"
    if kind == "play":
        return "play"
    if kind in ("stop_activity", "release"):
        return "stop what I'm doing"
    if kind == "set_rule":
        return f"keep out of the {step.place}" if step.rule == "keep_out" and step.place else "keep quiet"
    if kind == "end_rule":
        return "stop keeping quiet" if step.rule == "quiet" else (f"let myself go in the {step.place} again" if step.place else "end a house rule")
    if kind == "list_rules":
        return "tell you the house rules"
    return kind.replace("_", " ")


def _steps_words(steps, names: tuple) -> str:
    said = [step_words(step, names) for step in steps]
    return ", then ".join(said)


def tree_words(request: Request, names: tuple = ()) -> str:
    if request.branch:
        cond = request.if_
        then = _steps_words(request.then, names)
        other = _steps_words(request.else_, names)
        if cond.join == "not" and not request.else_:
            return f"unless {cond_words(cond.parts[0])}, I'll {then}"
        out = f"if {cond_words(cond)}, I'll {then}" if then else f"if {cond_words(cond, True)}, I'll {other}"
        if then and other:
            out += f"; if not, I'll {other}"
        return out
    out = f"I'll {_steps_words([request.with_(then=())] + list(request.then), names)}"
    if request.while_ is not None:
        out += f" while {cond_words(request.while_)}"
    if request.until_on is not None:
        out += f" until {happened_words(request.until_on)}"
    return out


def whole_words(request: Request, when_text: str = "", names: tuple = ()) -> str:
    body = tree_words(request, names)
    if request.on is not None and not when_text:
        lead = event_words(request.on)
    else:
        lead = when_text
    if not lead:
        return body[:1].upper() + body[1:]
    if body.startswith("I'll "):
        return f"{lead[:1].upper() + lead[1:]}, {body}"
    return f"{lead[:1].upper() + lead[1:]}, {body}"


def too_much(request: Request) -> str:
    return TOO_MUCH if too_big(request) else ""


def unsensed(request: Request) -> str:
    events = []
    for part in (request.on, request.until_on):
        if part is not None:
            events.extend(part.first_of or (part,))
    for step in request.steps():
        if step.until_on is not None:
            events.extend(step.until_on.first_of or (step.until_on,))
    if any(event.event == "cannot_tell" for event in events):
        return CANNOT_TELL_EVENT
    for step in request.steps():
        for cond in (step.if_, step.while_):
            if cond is not None and any(leaf.state == "cannot_tell" for leaf in leaves(cond)):
                return CANNOT_TELL_STATE
    return ""


def leaves(cond: Cond) -> list[Cond]:
    if cond.join:
        return [leaf for part in cond.parts for leaf in leaves(part)]
    return [cond]


def conditions(request: Request) -> list[Cond]:
    out = []
    for step in request.steps():
        for cond in (step.if_, step.while_):
            if cond is not None:
                out.extend(leaves(cond))
    return out


def events(request: Request) -> list[Trigger]:
    out = []
    for step in request.steps():
        for part in (step.on, step.until_on):
            if part is not None:
                out.extend(part.first_of or (part,))
    return out
