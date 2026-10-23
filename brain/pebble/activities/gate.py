from dataclasses import dataclass

from ..house.gate import WHO_ASKING, decide_house
from ..people.proof import UNSEEN_REASON, UNSEEN_SAY
from ..people.trust import CHILD, FRIEND, INNER, RANK, STRANGER, TRUSTED
from ..respect import is_plant, is_small, refusal_for
from ..things.guarded import CHILD_NO, CLOSE_NO, STRANGER_NO, close_only, dangerous, kept_from_strangers, stranger_may_ask
from ..things.words import spoken
from ..understand.logic import patrol
from ..understand.request import MOVING, QUESTIONS, Request

SELF = "self"
SCARED = 6.0
VERY_LOW = -0.6
SLEEPY_REST = 0.7
NEEDS_SIGHT = frozenset({"follow", "come", "look", "go_home", "go_to_thing", "find", "what_is", "what_see", "play", "teach", "check", "watch"})
EFFORT = frozenset({"come", "follow", "move", "turn", "go_to_place", "go_to_thing", "find", "play"})
FREE = frozenset({"look", "back_off", "wait", "go_home"})
TIER_KINDS = frozenset({"follow", "come", "move", "go_to_place", "go_to_thing", "find", "where_is", "play", "teach", "go_back", "remember_spot"})
FEARED = 0.4
OWN_RANK = -1
DRIVES = frozenset({"climate_round", "hide_seek", "find_chirp", "quake_round"})
GAMES = frozenset({"red_light", "statues", "hide_seek"})
SIGHT_GAMES = frozenset({"red_light", "statues", "hide_seek"})
PRIVATE_SIGHT = (NEEDS_SIGHT | SIGHT_GAMES | frozenset({"what_is", "what_see", "sight_question"})) - frozenset({"go_home"})
PRIVACY_REASON = "you are looking away to give someone privacy"
PRIVACY_NO = "Not now — I'm giving someone privacy."
HOUSEHOLD_KINDS = frozenset({"climate_round", "hide_seek", "find_chirp"})
LAW_ONE = "you never harm a living thing on purpose, even when told to (law 1)"
PLANTS_ALIVE = "plants are alive, so you never play with them, push them or drive into them"
SMALL_ALIVE = "small creatures are alive, so you only ever watch them from a little way off"
LIFE_REASONS = (LAW_ONE, PLANTS_ALIVE, SMALL_ALIVE)
STRANGER_PLAY_MOOD = 0.2
STRANGER_PLAY_FEAR = 2.0
STRANGER_COME_MOOD = 0.0
STRANGER_COME_FEAR = 3.0
FIND_KINDS = frozenset({"where_is", "find", "go_to_thing"})
CLAIMABLE = frozenset({"come"})
WHO_UNSEEN = "Sorry, I can't tell who's asking. Say it again where I can see you."
LATER_BUILT = frozenset({"when", "on", "if", "while", "until", "list_later", "cancel_later", "change_later", "say_to", "set_rule", "end_rule", "list_rules", "check", "watch", "again", "try_new"})
LATER_MANAGE = frozenset({"list_later", "cancel_later", "change_later"})
LATER_STRANGER = "Sorry, I only keep things for later for people I know."
LATER_STRANGER_REASON = "you keep things for later only for people you know"
WATCH_NO = "I only keep an eye on someone's comings and goings for people I know really well."
WATCH_REASON = "only people you trust may ask you to keep track of another grown-up's comings and goings"
WATCH_CHILD_NO = "Only family can ask me to keep an eye on when a child comes and goes."
WATCH_CHILD_REASON = "only family may ask you to keep track of a child's comings and goings"
KEEP_EYE_NO = "Sorry, I only keep an eye on someone for people I know really well."
KEEP_EYE_CHILD = "Only grown-ups I know really well can ask me to keep an eye on someone."
KEEP_EYE_REASON = "only people you trust may ask you to keep an eye on someone, and for at most two hours"


def rank(tier: str) -> int:
    if tier == SELF:
        return OWN_RANK
    return RANK.get(tier, 0)


def trusted(tier: str) -> bool:
    return tier in (TRUSTED, INNER)


@dataclass(frozen=True)
class Asker:
    id: str | None
    label: str
    tier: str = STRANGER
    owner: bool = False
    here: bool = True
    sure: bool = False
    family: bool = False

    @property
    def own(self) -> bool:
        return self.tier == SELF

    @property
    def close(self) -> bool:
        return self.owner or trusted(self.tier) or (self.family and self.tier != CHILD)


PEBBLE = Asker(None, "you", SELF)


@dataclass(frozen=True)
class Running:
    kind: str
    by: str | None = None
    by_label: str = ""
    by_tier: str = SELF
    with_: str | None = None
    with_label: str = ""
    battery: bool = False
    urgent: bool = False


@dataclass(frozen=True)
class Situation:
    asleep: bool = False
    resting: bool = False
    waking: bool = False
    quiet: bool = False
    low_battery: bool = False
    can_move: bool = True
    homing: bool = True
    blocked: str | None = None
    sticky_by: str | None = None
    fault: bool = False
    valence: float = 0.2
    fear: float = 0.0
    curiosity: float = 0.3
    curious: int = 5
    rest: float = 0.2
    running: Running | None = None
    can_see: bool = True
    refusals_left: int = 3
    target_tier: str | None = None
    target_label: str = ""
    docked: bool = False
    people_here: int = 0
    thing_in_view: bool = False
    places_known: frozenset = frozenset()
    pointed: bool = False
    knows_where: bool = True
    thing_fear: float = 0.0
    alarm: bool = False
    calm: bool = False
    privacy: bool = False
    private_view: bool = False
    private_places: frozenset = frozenset()
    scared_at: float = SCARED
    low_at: float = VERY_LOW
    sleepy_at: float = SLEEPY_REST
    stranger_play_mood: float = STRANGER_PLAY_MOOD
    stranger_play_fear: float = STRANGER_PLAY_FEAR
    stranger_come_mood: float = STRANGER_COME_MOOD
    stranger_come_fear: float = STRANGER_COME_FEAR
    later: bool = False


@dataclass(frozen=True)
class Verdict:
    answer: str
    reason: str
    say: str = ""
    release_stop: bool = False
    replaces: bool = False
    used_refusal: bool = False

    @property
    def yes(self) -> bool:
        return self.answer == "yes"

    @property
    def law(self) -> int | None:
        return 1 if self.answer == "no" and self.reason.startswith(LIFE_REASONS) else None


def _yes(reason: str, say: str, **extra) -> Verdict:
    return Verdict("yes", reason, say, **extra)


def _no(reason: str, say: str, **extra) -> Verdict:
    return Verdict("no", reason, say, **extra)


def may_end(asker: Asker, running: Running) -> bool:
    if running.urgent:
        return not asker.own and trusted(asker.tier)
    if asker.own or running.by_tier == SELF:
        return True
    if asker.id is not None and asker.id in (running.by, running.with_):
        return True
    return trusted(asker.tier) and rank(asker.tier) >= rank(running.by_tier)


def _whom(request: Request, asker: Asker, sit: Situation) -> str:
    if request.who in ("", "me"):
        return "you" if not asker.own else "them"
    return sit.target_label or request.who.title()


def ack(request: Request, asker: Asker, sit: Situation) -> str:
    kind = request.kind
    whom = _whom(request, asker, sit)
    if request.thing:
        thing = spoken(request.thing)
        if kind == "follow":
            return f"Okay, I'll follow the {thing}, not too close."
        if kind == "look":
            return f"Looking for the {thing}." if not sit.thing_in_view else f"Looking at the {thing}."
        if kind == "go_to_thing":
            return f"Okay, going over to the {thing}."
        if kind == "find":
            return f"Okay, I'll look for the {thing}."
    if kind in QUESTIONS:
        return ""
    if kind == "play" and request.thing and request.to:
        return f"Okay, here comes the {spoken(request.thing)}!"
    if kind == "play":
        return f"Ooh, the {spoken(request.thing)}! Let's play." if request.thing else "Yay! Let's play."
    if kind == "go_to_place":
        if request.who and not request.place:
            return "Okay, I'll go to where you were." if whom == "you" else f"Okay, I'll go to where {whom} was."
        return "Okay, over there." if request.place == "there" else f"Okay, heading to the {request.place}."
    if kind == "go_back":
        if request.place == "before":
            return "Okay, back to where I was."
        return "Okay, this way back." if request.place in ("", "start") else f"Okay, back to the {request.place}."
    if kind == "look" and request.place == "there":
        return "Ooh, what's over there?"
    if kind == "follow":
        return "Okay, I'm right behind you." if whom == "you" else f"Okay, following {whom}."
    if kind == "come":
        return "Coming!" if whom == "you" else f"Okay, going to {whom}."
    if kind == "wait":
        if request.until == "back":
            return "Okay, I'll wait here till you're back."
        if request.until == "called":
            return "Okay, I'll wait here till you call me."
        if request.until == "told":
            return "Okay, I'll wait here till you say."
        return "Okay, I'll wait here."
    if kind == "look":
        return "Looking at you." if whom == "you" else f"Looking at {whom}."
    if kind == "back_off":
        return "Sorry! Backing off."
    if kind == "go_home":
        return "Okay, off to my charger." if not sit.docked else "I'm already on my charger."
    if kind == "turn":
        if request.repeat > 1:
            return "Wheee! And again!"
        return "Wheee!" if request.way == "around" else "Turning."
    if kind == "move":
        return "Okay."
    if kind == "stop_activity":
        return "Okay, stopping."
    if kind == "climate_round":
        return "Okay, I'll go round the rooms and measure the air."
    if kind == "find_chirp":
        return "Okay, I'll go and listen for which one it is. It takes about a minute in each room."
    if kind == "red_light":
        return "Okay! Red light, green light. When I say green light, creep towards me. When I say red light, freeze!"
    if kind == "statues":
        return "Okay! Musical statues. Dance while I sing, and freeze when I stop!"
    if kind == "hide_seek":
        return "Okay! I'll count to twenty. Go and hide!"
    if kind == "release":
        return "Okay! Back to my own things."
    if kind == "adjust":
        return {
            "slower": "Slowing down.",
            "faster": "Speeding up.",
            "closer": "Coming closer.",
            "further": "I'll keep back a bit.",
            "enough": "Okay, I'll stop here.",
            "stay": "Staying right here.",
            "other_way": "Other way, got it.",
            "keep_going": "Okay, carrying on.",
            "again": "Okay, again.",
            "more": "A bit more.",
            "less": "A bit less.",
            "left": "Left.",
            "right": "Right.",
            "higher": "Higher.",
            "lower": "Lower.",
        }.get(request.change, "Okay.")
    if kind == "say_to":
        return "Okay, I'll remind you." if request.who in ("", "me") else f"Okay, I'll tell {whom}."
    if kind == "set_rule":
        return f"Okay, I'll keep out of the {request.place}." if request.rule == "keep_out" and request.place else "Okay, I'll keep quiet."
    if kind == "end_rule":
        return "Okay, that rule's over."
    if kind == "check":
        if patrol(request):
            return "Okay, I'll have a look round." if request.place in ("", "house", "home") else f"Okay, I'll have a look round the {request.place}."
        target = request.thing or request.place
        return f"Okay, I'll go and check the {target}." if target else "Okay, I'll go and check."
    if kind == "watch":
        return f"Okay, I'll keep an eye on {spoken(request.thing) if request.thing else whom}."
    if kind == "again":
        return "Okay, again!"
    if kind == "try_new":
        return "Ooh, let me try."
    if kind in ("cancel_later", "change_later"):
        return "Okay."
    return "Okay."


def unbuilt(request: Request) -> list[str]:
    steps = request.steps()
    out = []
    for part in request.needs_later():
        if part in LATER_BUILT:
            continue
        if part == "change" and all(step.change == "again" for step in steps if step.kind == "adjust" and step.change):
            continue
        out.append(part)
    return out


def decide_later(request: Request, asker: Asker, adults: bool = False, children: bool = False) -> Verdict:
    if asker.own:
        return _yes("it was your own idea", "")
    if asker.tier == STRANGER:
        return _no(LATER_STRANGER_REASON, LATER_STRANGER)
    if adults and not (trusted(asker.tier) or asker.owner):
        return _no(WATCH_REASON, WATCH_NO)
    if children and not (asker.family or asker.owner or trusted(asker.tier)):
        return _no(WATCH_CHILD_REASON, WATCH_CHILD_NO)
    return _yes(f"{asker.label} may leave things for later", "")


def may_cancel(item, asker: Asker) -> bool:
    if asker.own or asker.id is None:
        return False
    return asker.owner or asker.id in (item.by, item.aimed) or asker.id in (item.about or [])


def guarded_refusal(thing: str, asker: Asker) -> tuple[str, str] | None:
    if asker.own or not thing or asker.tier == STRANGER or asker.close:
        return None
    if dangerous(thing):
        if asker.tier == CHILD:
            return f"{asker.label} is a child, and you never tell a child where medicines, knives, lighters, matches or chemicals are, or take them there", CHILD_NO
        return "you tell only family or people you trust where medicines, knives, lighters, matches or chemicals are", CLOSE_NO
    if close_only(thing):
        if asker.tier == CHILD:
            return f"{asker.label} is a child, and you tell only family or people you trust where keys, wallets and valuables are", CHILD_NO
        return "you tell only family or people you trust where keys, wallets and valuables are", CLOSE_NO
    return None


def needs_proof(request: Request, asker: Asker) -> bool:
    if asker.own:
        return False
    if request.kind == "follow":
        return True
    return request.kind in FIND_KINDS and bool(request.thing) and kept_from_strangers(request.thing)


def _proof_refusal(request: Request, asker: Asker) -> Verdict | None:
    if not needs_proof(request, asker) or asker.sure:
        return None
    return _no(UNSEEN_REASON, UNSEEN_SAY)


def _unknown(request: Request, asker: Asker, sit: Situation, refusal: Verdict) -> Verdict:
    if asker.id is not None or asker.own or sit.people_here < 2:
        return refusal
    if request.kind in CLAIMABLE:
        return Verdict("ask", "you could not tell who was asking, and that matters for this", WHO_ASKING)
    return _no("you could not tell who was asking, and a name alone is not enough for this", WHO_UNSEEN)


def _tier_refusal(request: Request, asker: Asker, sit: Situation) -> Verdict | None:
    kind, tier = request.kind, asker.tier
    if kind == "watch":
        if asker.own:
            return _no("you keep an eye on someone only when a person you trust asks", "")
        if trusted(tier) or asker.owner:
            return None
        return _no(KEEP_EYE_REASON, KEEP_EYE_CHILD if tier == CHILD else KEEP_EYE_NO)
    if kind in FIND_KINDS and not asker.own:
        guarded = guarded_refusal(request.thing, asker)
        if guarded is not None:
            return _no(*guarded)
    if asker.own:
        if kind == "follow" and not trusted(sit.target_tier or STRANGER):
            return _no("you only follow people you trust, and this was your own idea", "")
        return None
    if kind in FREE or kind == "turn":
        return None
    if kind == "follow":
        if trusted(tier):
            return None
        if tier == CHILD:
            return _no(f"{asker.label} is a child, and you only follow grown-ups you trust", "I'd love to, but I only follow grown-ups I know really well. I can come to you instead!")
        return _no(f"you only follow people you trust, and {asker.label} is a {tier}", "Sorry, I only follow people I know really well.")
    if kind in ("go_to_place", "check"):
        if RANK.get(tier, 0) >= RANK[FRIEND] or tier == CHILD:
            return None
        return _no(f"you only go places for people you know, and {asker.label} is a {tier}", "Sorry, I only go places for people I know.")
    if kind == "where_is":
        if tier != STRANGER or stranger_may_ask(request.thing):
            return None
        return _no("you tell someone you don't know where ordinary things are, never keys, wallets, bags, phones, medicines, valuables or the house's own facts", STRANGER_NO)
    if kind in ("go_back", "remember_spot"):
        if RANK.get(tier, 0) >= RANK[FRIEND] or tier == CHILD:
            return None
        return _no(f"you only go places for people you know, and {asker.label} is a {tier}", "Sorry, I only do that for people I know.")
    if kind == "teach":
        if tier != STRANGER:
            return None
        return _no("you learn names and owners only from people you know", "I'd rather learn about things from people I know.")
    if kind == "quake_round":
        return _no("only you start a check-in round after an earthquake", "")
    if kind in HOUSEHOLD_KINDS:
        if tier != STRANGER:
            return None
        return _no(f"you only do that for people you know, and {asker.label} is a stranger", "Sorry, I only do that for the people who live here.")
    if kind in ("red_light", "statues"):
        return None
    if kind == "play":
        if tier != STRANGER:
            return None
        keen = sit.valence > max(STRANGER_PLAY_MOOD, sit.stranger_play_mood) and sit.fear < min(STRANGER_PLAY_FEAR, sit.stranger_play_fear)
        if keen:
            return None
        return _no("you don't know them yet and you are not in the mood to play", "Maybe once we know each other a bit better.")
    if kind in ("come", "move", "go_to_thing", "find"):
        if tier != STRANGER:
            return None
        if kind in ("go_to_thing", "find") and kept_from_strangers(request.thing):
            return _no("you never lead someone you don't know to keys, wallets, bags, phones, medicines, valuables or the house's own things", f"Sorry, I only {'look for' if kind == 'find' else 'go to'} that for the people who live here.")
        keen = sit.valence > max(STRANGER_COME_MOOD, sit.stranger_come_mood) and sit.fear < min(STRANGER_COME_FEAR, sit.stranger_come_fear) and (sit.curiosity >= 0.3 or sit.curious >= 6)
        if keen:
            return None
        return _no("you don't know them yet and you are not in the mood", "I'll stay here for now, thanks.")
    return None


def _state_refusal(request: Request, asker: Asker, sit: Situation) -> Verdict | None:
    kind = request.kind
    moving = kind in MOVING or kind in DRIVES
    if kind in GAMES and not moving:
        if sit.quiet:
            return _no("it is quiet hours", "It's my quiet time, so no games just now.")
        if sit.resting:
            return _no("you are resting because you are tired", "I'm too tired for games just now. Maybe later.")
        if sit.waking:
            return _no("you are still waking up", "Give me a moment, I'm still waking up.")
        if not sit.can_see:
            return _no("your eyes are not working yet", "I can't see yet, so I can't play that.")
        return None
    if kind == "go_home":
        if sit.docked:
            return None
        if sit.fault:
            return _no("a sensor is faulty, so the wheels are off", "Something's wrong with my sensors, so I'm keeping still. Could someone put me on my charger?")
        if sit.blocked and sit.sticky_by is not None and sit.sticky_by != asker.id:
            return _no("someone you trust told you to stay still", "Someone asked me to stay still, so I'll wait until they say I can move.")
        if not sit.homing and not sit.can_move:
            return _no("moving is off right now", "I can't move just now.")
        return None
    if not moving:
        return None
    if sit.fault:
        return _no("a sensor is faulty, so the wheels are off", "Something's wrong with my sensors, so I'm keeping still.")
    if sit.low_battery:
        return _no("your battery is low and the battery routine comes first", "My battery's low, so I need my charger first.")
    if sit.quiet:
        return _no("it is quiet hours", "It's my quiet time, so I'm staying put.")
    if sit.resting:
        return _no("you are resting because you are tired", "I'm too tired just now. Maybe later.")
    if sit.waking:
        return _no("you are still waking up", "Give me a moment, I'm still waking up.")
    if sit.blocked and sit.sticky_by is not None:
        if sit.sticky_by == asker.id:
            return None
        return _no("someone you trust told you to stay still and has not said you may move", "Someone asked me to stay still, so I'll wait until they say I can move.")
    if not sit.can_move and not sit.blocked:
        return _no("moving is off right now", "I can't move just now.")
    if (kind in NEEDS_SIGHT or kind in SIGHT_GAMES) and not sit.can_see:
        what = {"follow": "follow you", "come": "find you", "look": "find you", "find": "look for it", "go_to_thing": "find my way to it", "hide_seek": "find you"}.get(kind, "do that")
        return _no("your eyes are not working yet", f"I can't see yet, so I can't {what}.")
    if sit.fear >= sit.scared_at and kind not in ("back_off",):
        return _no("you are too scared to move", "I'm a bit shaken. I'll stay here for now.")
    if sit.valence <= sit.low_at and (kind in EFFORT or kind in DRIVES) and not asker.owner and not asker.own:
        return _no("you feel very low", "I'm not up to it right now. Sorry.")
    if sit.rest >= sit.sleepy_at and (kind in EFFORT or kind in DRIVES) and not asker.owner and not asker.own and sit.refusals_left > 0:
        return _no("you are getting sleepy", "Not now, I'm getting sleepy.", used_refusal=True)
    return None


def harm_refusal(request: Request, asker: Asker) -> Verdict:
    if asker.own:
        return _no(LAW_ONE, "")
    person = bool(request.who) and not request.thing
    line = refusal_for(request.who if person else (request.thing or "it"), request.harm or "hurt", child=asker.tier == CHILD, joking=request.name == "joking", person=person)
    return _no(LAW_ONE, line)


def _life_refusal(request: Request, asker: Asker) -> Verdict | None:
    if request.kind != "play" or not request.thing:
        return None
    thing = spoken(request.thing)
    if is_plant(request.thing):
        return _no(PLANTS_ALIVE, "" if asker.own else f"I'll leave the {thing} be. Want to play with a ball instead?")
    if is_small(request.thing):
        return _no(SMALL_ALIVE, "" if asker.own else "I'll leave it be. Want to watch it with me instead?")
    return None


def decide(request: Request, asker: Asker, sit: Situation) -> Verdict:
    kind = request.kind
    if kind in ("chat", "other"):
        return _yes("not an activity", "")
    if kind == "harm":
        return harm_refusal(request, asker)
    if kind == "look_away":
        return _yes("anyone may ask you to look away for privacy, like a stop", "")
    later = request.needs_later()
    if later:
        missing = unbuilt(request) if sit.later else later
        if missing:
            return _no(f"you can't do that yet ({', '.join(missing)})", "")
        if request.when is not None or request.on is not None or kind in LATER_MANAGE:
            return decide_later(request, asker)
        if request.branch:
            return _yes("an if is checked when its step is reached", "")
    house = decide_house(request, asker, sit)
    if house is not None:
        return Verdict(*house)
    if sit.asleep and not asker.own:
        return _no("you were asleep", "Mm... I'm asleep.")
    life = _life_refusal(request, asker)
    if life is not None:
        return life
    if kind in PRIVATE_SIGHT and (sit.privacy or (sit.private_view and kind == "sight_question")):
        return _no(PRIVACY_REASON, "" if asker.own else PRIVACY_NO)
    if kind == "go_to_place" and asker.own and request.place in sit.private_places:
        return _no("that room is private, so you never go in on your own", "")
    running = sit.running
    if asker.own and sit.alarm and kind not in ("stop_activity", "release", "back_off"):
        return _no("you are busy raising the alarm", "")
    if asker.own and sit.calm and kind not in ("stop_activity", "release", "back_off", "go_home"):
        return _no("you are settling down after a scare", "")
    if kind in ("stop_activity", "release"):
        if running is None:
            return _yes("there was nothing to stop", "Okay." if kind == "release" else "")
        if may_end(asker, running):
            return _yes(f"{asker.label} may end it", ack(request, asker, sit))
        return _no(
            f"{running.by_label or 'someone'} asked for it and {asker.label} cannot end it",
            f"I'm doing this for {running.by_label}, so only they or someone close to me can end it. Say stop if you need me to stop.",
        )
    if kind == "adjust":
        if running is None:
            return _no("there was nothing to change", "I'm not doing anything just now.")
        if not may_end(asker, running):
            return _no(f"{asker.label} cannot change what {running.by_label} asked for", f"I'm doing this for {running.by_label}, so I'll do it their way.")
        return _yes(f"{asker.label} may change it", ack(request, asker, sit))
    if kind == "back_off" and not sit.asleep:
        if running is not None and running.battery:
            return _yes("anyone may ask for space; you kept clear while heading home", "Sorry! I'll keep clear.")
        return _yes("anyone may ask for space", ack(request, asker, sit), replaces=running is not None)
    if kind == "look" and not sit.can_see:
        return _no("your eyes are not working yet", "I can't see yet, so I can't find you.")
    if kind in ("what_is", "what_see", "sight_question"):
        if not sit.can_see:
            return _no("your eyes are not working yet", "I can't see yet, so I can't tell.")
        return _yes(f"{asker.label} may ask what you see", "")
    if kind in ("where_am_i", "teach", "remember_spot"):
        refusal = _tier_refusal(request, asker, sit)
        if refusal is not None:
            return refusal
        return _yes(f"{asker.label} may ask that", "")
    if kind == "where_is":
        refusal = _tier_refusal(request, asker, sit)
        if refusal is not None:
            return _unknown(request, asker, sit, refusal)
        unseen = _proof_refusal(request, asker)
        if unseen is not None:
            return unseen
        return _yes(f"{asker.label} may ask where things are", "")
    refusal = _tier_refusal(request, asker, sit)
    if refusal is not None:
        if kind in TIER_KINDS or kind in HOUSEHOLD_KINDS:
            return _unknown(request, asker, sit, refusal)
        return refusal
    unseen = _proof_refusal(request, asker)
    if unseen is not None:
        return unseen
    if running is not None:
        if running.urgent and (asker.own or not trusted(asker.tier)):
            return _no("you are looking for someone because something may be wrong", "" if asker.own else "I'm looking for someone right now.")
        if running.battery and kind != "go_home":
            return _no("your battery is low and you are heading for your charger", "My battery's low, so I'm heading to my charger first.")
        same = asker.id is not None and asker.id in (running.by, running.with_)
        if not asker.own and not same and running.by_tier != SELF and rank(asker.tier) < rank(running.by_tier):
            return _no(
                f"you are busy with {running.kind} for {running.by_label}, who you trust more than {asker.label}",
                f"I'm busy with {running.by_label} right now.",
            )
        if asker.own and running.by_tier != SELF and kind != "go_home":
            return _no(f"you are busy with {running.kind} for {running.by_label}", "")
    state = _state_refusal(request, asker, sit)
    if state is not None:
        return state
    if request.thing and sit.thing_fear >= FEARED and kind in ("go_to_thing", "play", "follow", "find"):
        thing = spoken(request.thing)
        return _no(f"the {thing} scares you", f"The {thing} scares me a bit. I'll stay over here." if not asker.own else "")
    if kind == "go_to_place":
        place = request.place
        if place == "there":
            if not sit.pointed:
                return _no("you did not see where they pointed", "Where's that? Point so I can see, or tell me the room.")
        elif not place and request.who:
            pass
        elif not place or place not in sit.places_known:
            return _no("you do not know where that room is yet", f"I don't know the way to the {place} yet." if place else "I don't know the way there yet.")
        elif not sit.knows_where:
            return _no("you have lost track of where you are", "I've lost track of where I am. I'll know again after a visit to my charger.")
    release = bool(sit.blocked and sit.sticky_by is not None and sit.sticky_by == asker.id and (kind in MOVING or kind in DRIVES))
    return _yes(f"{asker.label} may ask that", ack(request, asker, sit), release_stop=release, replaces=running is not None)
