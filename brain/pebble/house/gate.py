from ..people.proof import UNSEEN_REASON, UNSEEN_SAY
from ..people.trust import CHILD, FRIEND, INNER, RANK, STRANGER, TRUSTED

ANYONE = "anyone"
HOUSEHOLD = "household"
GROWN = "grown"
CLOSE = "trusted"
OWNER = "owner"
VISITORS = "visitors"
TEACHER_KINDS = frozenset({"forget_sound"})
AWAKE_KINDS = frozenset({"torch_on", "torch_off"})
TIERS = {
    "list_add": HOUSEHOLD,
    "list_remove": HOUSEHOLD,
    "list_read": HOUSEHOLD,
    "list_show": HOUSEHOLD,
    "list_clear": GROWN,
    "visitors_on": CLOSE,
    "visitors_off": CLOSE,
    "keeps": ANYONE,
    "guest_wifi": HOUSEHOLD,
    "house_fact": CLOSE,
    "teach_sound": HOUSEHOLD,
    "forget_sound": CLOSE,
    "sounds_ask": HOUSEHOLD,
    "alarm_test": CLOSE,
    "alarm_test_end": ANYONE,
    "alarms_ask": HOUSEHOLD,
    "while_out": HOUSEHOLD,
    "tell_when": HOUSEHOLD,
    "light_ask": ANYONE,
    "almanac": ANYONE,
    "damp": ANYONE,
    "curtains_on": HOUSEHOLD,
    "curtains_off": HOUSEHOLD,
    "noise_ask": HOUSEHOLD,
    "captions_on": ANYONE,
    "captions_off": ANYONE,
    "cooking_ok": ANYONE,
    "high_ask": HOUSEHOLD,
    "torch_on": ANYONE,
    "torch_off": ANYONE,
    "mic_probe": OWNER,
    "tv_check": OWNER,
    "tv_check_end": ANYONE,
}
REFUSALS = {
    HOUSEHOLD: ("only people you know may ask that, and you don't know {label} yet", "Sorry, that's just for the people who live here."),
    GROWN: ("only grown-ups you know may ask that", "Only a grown-up I know can do that."),
    CLOSE: ("only someone you trust may ask that", "Sorry, only someone I know really well can ask me that."),
    OWNER: ("only your owner may ask that", "Only my owner can ask me to do that."),
}
WHO_ASKING = "Sorry, who's asking? I can't tell voices apart yet."
WHO_UNSEEN = "Sorry, I can't tell who's asking. Say it again where I can see you."
SEEN = frozenset({CLOSE, OWNER})


def house_kind(kind: str) -> bool:
    return kind in TIERS


def needs(request) -> str:
    need = TIERS.get(request.kind, ANYONE)
    if request.kind == "guest_wifi" and request.who == VISITORS:
        return ANYONE
    return need


def allowed(need: str, tier: str, owner: bool = False) -> bool:
    if need == ANYONE or owner:
        return True
    if need == HOUSEHOLD:
        return tier != STRANGER
    if need == GROWN:
        return tier != CHILD and RANK.get(tier, 0) >= RANK[FRIEND]
    if need == OWNER:
        return False
    return tier in (TRUSTED, INNER)


def decide_house(request, asker, sit) -> tuple[str, str, str] | None:
    kind = request.kind
    if kind not in TIERS:
        return None
    own = getattr(asker, "own", False)
    if own:
        return ("yes", "your own idea", "")
    if getattr(sit, "asleep", False) and kind not in AWAKE_KINDS:
        return ("no", "you were asleep", "Mm... I'm asleep.")
    if kind == "alarm_test" and getattr(sit, "alarm", False):
        return ("no", "an alarm is going right now, so this cannot be a test", "Not now. An alarm is going, so I'm treating it as real.")
    tier = getattr(asker, "tier", STRANGER)
    owner = bool(getattr(asker, "owner", False))
    need = needs(request)
    if kind in TEACHER_KINDS and request.who and getattr(asker, "id", None) == request.who:
        need = ANYONE
    if allowed(need, tier, owner):
        if need in SEEN and not getattr(asker, "sure", False):
            return ("no", UNSEEN_REASON, UNSEEN_SAY)
        return ("yes", f"{getattr(asker, 'label', 'someone')} may ask that", "")
    if getattr(asker, "id", None) is None and getattr(sit, "people_here", 0) >= 2:
        return ("no", "you could not tell who was asking, and a name alone is not enough for this", WHO_UNSEEN)
    reason, say = REFUSALS[need]
    return ("no", reason.format(label=getattr(asker, "label", "someone")), say)
