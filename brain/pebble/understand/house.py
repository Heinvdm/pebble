import re
from dataclasses import dataclass

from .words import normalise

ITEM_MAX = 40
ITEMS_MAX = 6
LEAD = re.compile(r"^(?:hey|hi|oi|ok|um|uh|er|erm|so|right|and|please|just|yo|alright|well|now|also|oh|listen|mate)\b\s*")
POLITE = re.compile(r"^(?:(?:can|could|would|will) you(?: please)?|would you mind|do you mind|i need you to|i want you to|i would like you to|be a dear and|kindly|please)\b\s*")
TAIL = re.compile(r"\s*\b(?:please|thanks|thank you|cheers|mate|for me|will you|would you|ta)$")
SHOPPING = ("shopping", "grocery", "groceries", "supermarket", "shop", "food")
TODO = ("to do", "todo", "jobs", "job", "chores", "chore", "things to do")
LIST_NAME = r"(?:(?P<list>[a-z]+(?: [a-z]+)?) )?"
OWNERS = r"(?:the|my|our|your)"
NOT_ITEMS = frozenset({"it", "that", "this", "them", "me", "him", "her", "us", "you", "some", "more", "a task", "a reminder", "an event", "a note", "a list", "the list", "list", "one", "anything", "something", "nothing", "everything", "reminder", "reminders", "task", "tasks", "event", "events", "note", "notes", "timer", "timers", "alarm", "alarms", "music", "song", "songs", "friend", "friends", "contact", "photo", "photos", "picture", "pictures", "drawing", "joke", "jokes", "people", "guests", "visitors"})
NUMBER_WORDS = frozenset({"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "twenty", "hundred", "thousand"})
FACT_THINGS = (
    "water shut off valve",
    "water shut off",
    "water main",
    "water mains",
    "mains water tap",
    "mains tap",
    "water toby",
    "toby",
    "stopcock",
    "switchboard",
    "switch board",
    "fuse box",
    "fuses",
    "circuit breakers",
    "meter box",
    "power box",
    "gas shut off",
    "gas valve",
    "gas bottle valve",
    "getaway bag",
    "grab bag",
    "go bag",
    "emergency bag",
    "emergency kit",
    "civil defence kit",
    "survival kit",
    "fire extinguisher",
    "extinguisher",
    "fire blanket",
    "first aid kit",
    "first aid box",
    "torch",
    "torches",
    "spare batteries",
    "emergency water",
    "emergency radio",
)
WHERE_WORDS = r"(?:in|under|on|behind|by|next to|beside|at|near|inside|outside|above|below|underneath|on top of|to the left of|to the right of|left of|right of|round the back of|around the back of|out the back|up in|down in|in the back of)"
NAMES_ALARM = re.compile(r"\b(?:smoke|fire|carbon|monoxide|co) ?alarm|\balarm\b|\bsiren\b")
SOUND_WORDS = r"(?:sound|noise|beep|beeping|beeps|tune|music|jingle|chime|ding|ringing|buzz|buzzer|melody)"
ENDING_WORDS = r"(?:finishing|finished|done|ending|ready|beeping|ringing|going off|playing)"
YES = re.compile(r"^(?:yes|yeah|yep|yup|ya|ja|aye|sure|ok|ok then|yes please|please|go on|go ahead|do it|sounds good|good idea|why not|of course|definitely|that would be good|yes it was|it was|correct|right|that is right|that is it|spot on)$")
NO = re.compile(r"^(?:no|nah|nope|no thanks|no thank you|not now|maybe later|later|not today|not yet|no it was not|it was not|wrong|that is wrong|not that one)$")
NEVER = re.compile(r"^(?:never|no never|stop asking|do not ask again|do not ask me again|no and stop asking|never ask again)$")
CLAIM_NAME = re.compile(r"^(?:it is|this is|it s|me|i am|i m)?\s*(?P<name>[a-z]+)$")


@dataclass(frozen=True)
class HouseAsk:
    kind: str
    item: str = ""
    items: tuple = ()
    list: str = ""
    where: str = ""
    topic: str = ""
    when: str = ""
    only_if_listed: bool = False
    text: str = ""


def clean(text: str, name: str = "pebble", commas: bool = False) -> str:
    out = normalise(text, name)
    if commas:
        out = re.sub(r"\s*,\s*(?:and\s+)?", " and ", out)
    out = re.sub(r"[,.!?;:\"]+", " ", out)
    out = re.sub(r"\bwifi\b|\bwi fi\b|\bwhy fi\b", "wifi", out)
    out = re.sub(r"\bto do\b|\btodo\b", "to do", out)
    out = re.sub(r"\bwhen'?s\b", "when is", out)
    out = " ".join(out.split())
    for _ in range(4):
        before = out
        out = LEAD.sub("", out)
        out = POLITE.sub("", out)
        out = TAIL.sub("", out)
        out = out.strip()
        if out == before:
            break
    return out


def list_name(raw: str | None) -> str:
    name = " ".join((raw or "").split())
    if not name:
        return "shopping"
    if name in SHOPPING or name.endswith(" shopping"):
        return "shopping"
    if name in TODO:
        return "to do"
    return name


def items_of(raw: str) -> tuple:
    text = re.sub(r"^(?:some|more|a few|a couple of|a|an|the|another|new|extra)\s+", "", raw.strip())
    parts = [p.strip() for p in re.split(r",|\band\b|\bplus\b|\balso\b", text) if p.strip()]
    out = []
    for part in parts:
        part = re.sub(r"^(?:some|more|a few|a couple of|a|an|the|another|new|extra)\s+", "", part)
        part = part.strip("'\" ")
        if not part or part in NOT_ITEMS or part.isdigit() or part in NUMBER_WORDS or len(part) > ITEM_MAX or len(part.split()) > 5:
            return ()
        out.append(part)
    return tuple(dict.fromkeys(out))[:ITEMS_MAX]


ADD = (
    re.compile(rf"^(?:add|put|stick|pop|chuck|write|write down|jot down|note down|note|bung) (?P<item>.+?) (?:on|onto|to|in|into) {OWNERS} {LIST_NAME}list$"),
    re.compile(r"^add (?P<item>[a-z' ]+)$"),
    re.compile(r"^(?:we are|we have|we have run|we are running|we are nearly|we are almost|we are getting|i am|i have run) (?:right |completely |totally |all )?(?:out of|out|low on|short of|running low on|running out of) (?P<item>[a-z' ]+)$"),
    re.compile(r"^(?:we are |we re )?(?:all )?out of (?P<item>[a-z' ]+)$"),
    re.compile(r"^we need (?:more |some |new |a new |another )(?P<item>[a-z' ]+)$"),
    re.compile(r"^we have no (?P<item>[a-z' ]+?) left$"),
    re.compile(r"^remind me to (?:buy|get|pick up|grab) (?P<item>[a-z' ]+)$"),
)
REMOVE = (
    re.compile(rf"^(?:take|cross|tick|scratch|strike|knock|scrub) (?P<item>.+?) off(?: {OWNERS} {LIST_NAME}list)?$"),
    re.compile(rf"^(?:remove|delete|drop|take) (?P<item>.+?) (?:from|off) {OWNERS} {LIST_NAME}list$"),
)
GOT = re.compile(r"^(?:i|we) (?:have )?(?:got|bought|picked up|grabbed) (?:the |some |more )?(?P<item>[a-z' ]+?)(?: now| already| today)?$")
READ = (
    re.compile(rf"^what is on {OWNERS} {LIST_NAME}list$"),
    re.compile(rf"^(?:what is|what are|what s|what) (?:on|in) {OWNERS} {LIST_NAME}list$"),
    re.compile(rf"^(?:read|tell) (?:me |us )?(?:out )?{OWNERS} {LIST_NAME}list(?: out| to me)?$"),
    re.compile(r"^what do (?:we|i) need(?: from the (?:shop|shops|supermarket|store))?$"),
    re.compile(rf"^(?:is there )?anything on {OWNERS} {LIST_NAME}list$"),
    re.compile(rf"^how (?:many|long) (?:things |items )?(?:is|are) (?:on )?{OWNERS} {LIST_NAME}list$"),
    re.compile(r"^(?:the )?list$"),
)
SHOW = (
    re.compile(rf"^(?:show|give|send|hand) (?:me |us )?{OWNERS} {LIST_NAME}list(?: on (?:the|your) screen)?$"),
    re.compile(rf"^(?:can|could|may) (?:i|we) (?:have|get|take|see) {OWNERS} {LIST_NAME}list$"),
    re.compile(rf"^put {OWNERS} {LIST_NAME}list on (?:the|your) screen$"),
    re.compile(r"^(?:i am|we are) (?:just )?(?:going|heading|off|popping|nipping|running|about to go|going out) (?:out )?(?:to|down to|up to) the (?:shop|shops|supermarket|dairy|store|grocer|grocery store|market)(?: now| soon)?$"),
)
CLEAR = (
    re.compile(rf"^(?:clear|empty|wipe|reset|delete|scrap|clean out) {OWNERS} (?:whole )?{LIST_NAME}list$"),
    re.compile(rf"^start a new {LIST_NAME}list$"),
    re.compile(r"^(?:i|we) (?:have )?(?:got|bought) everything(?: on the list)?$"),
)
VISITORS_ON = (
    re.compile(r"^(?:we have|we have got|we got|we are having|i have|i have got|i am having) (?:some )?(?:people|guests|visitors|friends|company|family|folks) (?:over|coming|coming over|around|here|staying)(?: tonight| today| this evening| for dinner| for lunch| for a bit| soon| now)?$"),
    re.compile(r"^(?:some )?(?:guests|visitors|people|friends|family) (?:are )?(?:coming|here|over|arriving)(?: over| around| soon| tonight| today| now)?$"),
    re.compile(r"^(?:turn on|switch on|start|go into|put on) (?:the )?visitors? mode$"),
    re.compile(r"^visitors? mode(?: on| please)?$"),
)
VISITORS_OFF = (
    re.compile(r"^(?:turn off|switch off|stop|end|leave|come out of|finish|cancel) (?:the )?visitors? mode$"),
    re.compile(r"^visitors? mode off$"),
    re.compile(r"^(?:the |our )?(?:guests|visitors|people|friends|family|everyone|they) (?:have|has|are|all have) (?:all )?(?:gone|left|gone home)$"),
    re.compile(r"^they have (?:all )?(?:gone|left|gone home)$"),
)
KEEPS = (
    re.compile(r"^what do you (?:keep|remember|store|record|save|write down)(?: about (?:me|us|people|anyone|visitors|guests))?$"),
    re.compile(r"^are you (?:recording|filming|listening to us|spying on us|keeping what we say|taping)(?: me| us| this| everything)?$"),
    re.compile(r"^do you (?:record|keep|save|store|remember) (?:what we say|everything|us|me|anything|what i say|conversations|my face|faces|voices)$"),
    re.compile(r"^is (?:it|he|she|that thing|the robot) recording(?: us| me)?$"),
)
WIFI = (
    re.compile(r"^(?:show|give|tell) (?:me |us )?(?:the )?(?:guest )?wifi(?: password| code| details| card| login)?$"),
    re.compile(r"^what is (?:the|your) (?:guest )?wifi(?: password| code| called)?$"),
    re.compile(r"^(?:can|could|may) (?:i|we) (?:have|get|use|join) (?:the )?(?:guest )?wifi(?: password| code)?$"),
    re.compile(r"^how do (?:i|we) (?:get on|join|connect to|log on to|log onto) (?:the |your )?(?:guest )?wifi$"),
    re.compile(r"^(?:the )?guest wifi$"),
)
FACT = (
    re.compile(rf"^(?:remember (?:that )?)?(?:the|our|my) (?P<thing>{'|'.join(FACT_THINGS)})(?: is| s|'s| are) (?:kept )?(?P<where>{WHERE_WORDS} .+)$"),
    re.compile(rf"^remember (?:that )?(?:the|our|my) (?P<thing>[a-z ]{{2,30}}?)(?: is| s|'s| are) (?:kept )?(?P<where>{WHERE_WORDS} .+)$"),
    re.compile(rf"^(?:we|i) keep (?:the|our|my) (?P<thing>{'|'.join(FACT_THINGS)}) (?P<where>{WHERE_WORDS} .+)$"),
)
TEACH = (
    re.compile(rf"^(?:that|this) {SOUND_WORDS} (?:is|was|means|meant|is from) (?P<name>.+)$"),
    re.compile(rf"^(?:that|this) (?:is|was) (?P<name>(?:the |my |our )?[a-z' ]+? {ENDING_WORDS})$"),
    re.compile(rf"^(?:that|this) (?:is|was) the {SOUND_WORDS} (?:of|from) (?P<name>.+)$"),
    re.compile(rf"^(?:remember|learn) (?:this|that) {SOUND_WORDS}(?: it is| it means| it was| is| means| as)? (?P<name>.+)$"),
)
FORGET_SOUND = (
    re.compile(rf"^(?:forget|unlearn|delete|stop listening for|stop telling (?:me|us) about) (?:the |that |this )?(?P<name>[a-z' ]+?) {SOUND_WORDS}$"),
    re.compile(rf"^forget (?:that|this|the last) {SOUND_WORDS}$"),
)
SOUNDS_ASK = (
    re.compile(r"^(?:what|which) (?:sounds|noises) (?:do you know|have you learnt|have you learned|can you tell|have i taught you|have we taught you)$"),
    re.compile(r"^how (?:often|many times) (?:were|have) you (?:been )?right about (?:the )?(?P<name>[a-z' ]+?)(?: sound)?$"),
)
ALARM_TEST = (
    re.compile(r"^(?:we are|i am|we will be|i will be|we are going to be|i am going to be|we are about to|i am about to|we are going to|i am going to) (?:test|testing|be testing) (?:the |our |all the |all our |each )?(?:smoke |fire |co |carbon monoxide )?alarms?$"),
    re.compile(r"^(?:smoke |fire )?alarm test(?: time| now| please)?$"),
    re.compile(r"^(?:let us|time to|we should|i will|we will) test the (?:smoke |fire )?alarms?(?: now)?$"),
    re.compile(r"^(?:start|begin|do) (?:the |an |a )?(?:smoke |fire )?alarm test$"),
    re.compile(r"^testing (?:the |our )?(?:smoke |fire )?alarms?$"),
)
ALARM_TEST_END = (
    re.compile(r"^(?:we are|i am|we have|i have) (?:all )?(?:done|finished) (?:testing|with the test|with the alarms|the test|the alarms)(?: now)?$"),
    re.compile(r"^(?:the )?(?:alarm )?(?:test|testing) is (?:over|done|finished)$"),
    re.compile(r"^(?:stop|end|finish|cancel) (?:the )?(?:smoke )?alarm test$"),
    re.compile(r"^(?:that is|that was) (?:all )?the (?:last )?alarms?$"),
    re.compile(r"^test (?:over|done|finished)$"),
)
ALARMS_ASK = (
    re.compile(r"^which (?:smoke )?alarms? (?:went off|did you hear|have gone off|sounded|have you heard)(?: today| this month| this week| lately)?$"),
    re.compile(r"^when did (?:we|i|anyone|someone|you) (?:last )?test the (?:smoke )?alarms?(?: last)?$"),
    re.compile(r"^(?:is|was) (?:an|the|a) (?:smoke )?alarm chirping$"),
    re.compile(r"^what is (?:that|the) chirping(?: noise| sound)?$"),
    re.compile(r"^did (?:you hear )?(?:the|an|a|any) (?:smoke )?alarms? go off(?: today)?$"),
)
WHILE_OUT = (
    re.compile(r"^(?:did )?anything (?:happen|exciting happen|go on|interesting happen)(?: while (?:i|we) (?:was|were) (?:out|away|gone))?(?: today)?$"),
    re.compile(r"^what (?:did|have) (?:i|we) miss(?:ed)?$"),
    re.compile(r"^what (?:happened|went on) while (?:i|we) (?:was|were) (?:out|away|gone)$"),
    re.compile(r"^any news$"),
    re.compile(r"^did (?:anyone|somebody|someone) (?:knock|come to the door|ring the (?:doorbell|door bell|bell))(?: today)?$"),
    re.compile(r"^did the (?:doorbell|door bell|door) (?:go|ring)(?: today)?$"),
)
TELL_WHEN = (
    re.compile(r"^(?:tell|let) me (?:know )?when (?:the )?(?P<name>[a-z' ]+?)(?: is| s|'s| has)? (?:done|finished|ready|finishes|beeps|goes off)$"),
    re.compile(r"^(?:tell|let) me (?:know )?if (?:it )?(?:starts )?(?:to )?rain(?:s|ing)?$"),
    re.compile(r"^(?:the )?washing(?: is|'s| s) (?:out|on the line|hanging out)$"),
    re.compile(r"^(?:i|we) (?:have )?(?:hung|put|pegged) (?:out )?(?:the )?washing(?: out)?(?: on the line)?$"),
)
LIGHT = (
    re.compile(r"^(?:is|are) (?:the )?lights? (?:on|off)(?: in here| here)?$"),
    re.compile(r"^is it (?:dark|light|bright|dim)(?: in here| here| now| in this room)?$"),
    re.compile(r"^how (?:bright|dark|light) is it(?: in here| here)?$"),
    re.compile(r"^did (?:i|we|someone|somebody|anyone) (?:leave|turn) the lights? (?:on|off)$"),
    re.compile(r"^are (?:all )?the lights off$"),
)
DAYS = r"(?:today|tomorrow|tonight|this evening|monday|tuesday|wednesday|thursday|friday|saturday|sunday|this weekend|next week)"
WHEN_WORDS = ("today", "tomorrow", "tonight", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
HOLIDAYS = r"(?:matariki|easter|easter monday|good friday|labour day|anzac day|waitangi day|king s birthday|kings birthday|christmas|christmas day|boxing day|new year|new year s day|new years day)"
ALMANAC = (
    ("sunset", re.compile(rf"^(?:what time|when) (?:is|does|will) (?:the )?(?:sunset|sun set|sun go down|it get dark|it be dark)(?: (?:on )?{DAYS})?$")),
    ("sunset", re.compile(rf"^what time does it get dark(?: (?:on )?{DAYS})?$")),
    ("sunset", re.compile(rf"^when does it get dark(?: (?:on )?{DAYS})?$")),
    ("sunset", re.compile(r"^how long (?:until|till|is it till|is it until|before) (?:sunset|dark|it gets dark)$")),
    ("sunrise", re.compile(rf"^(?:what time|when) (?:is|does|will) (?:the )?(?:sunrise|sun rise|sun come up|it get light)(?: (?:on )?{DAYS})?$")),
    ("holiday", re.compile(rf"^is (?:it |there )?(?:a )?(?:public )?holiday(?: (?:on )?{DAYS})?$")),
    ("holiday", re.compile(rf"^is (?P<when>{DAYS}) a (?:public )?holiday$")),
    ("next_holiday", re.compile(r"^(?:when is|what is) the next (?:public )?holiday$")),
    ("named_holiday", re.compile(rf"^when is (?P<holiday>{HOLIDAYS})(?: this year| next year)?$")),
    ("clocks", re.compile(r"^when do (?:the )?clocks (?:change|go forward|go back|go forwards|go backwards)(?: this year)?$")),
    ("clocks", re.compile(r"^(?:when (?:does|is) )?daylight sav(?:ing|ings)(?: time)?(?: start| end| begin| finish| change)?$")),
    ("clocks", re.compile(r"^do the clocks (?:change|go forward|go back)(?: soon| this weekend| tonight)?$")),
    ("moon", re.compile(r"^(?:is it|is there|will there be) a full moon(?: tonight| this week)?$")),
    ("moon", re.compile(r"^what (?:is the moon doing|phase is the moon|is the moon like|is the moon)(?: tonight)?$")),
    ("moon", re.compile(r"^what moon is it(?: tonight)?$")),
)
DAMP = (
    re.compile(r"^what is the dew point(?: here| in here| tonight)?$"),
    re.compile(r"^will (?:the |my |our )?windows? (?:run wet|be wet|get wet|fog up|steam up|have condensation|drip|sweat)(?: tonight)?$"),
    re.compile(r"^(?:will there be|is there going to be|any) condensation(?: tonight| on the windows)?$"),
    re.compile(r"^is it damp(?: in here| here| tonight)?$"),
    re.compile(r"^how damp is it(?: in here| here)?$"),
    re.compile(r"^is (?:it|there) (?:a )?(?:mould|mold) (?:risk|weather)(?: tonight)?$"),
)
CURTAINS_ON = (
    re.compile(r"^remind me to (?:close|shut|draw|pull) the curtains(?: at sunset| before dark| when it gets dark| every evening| at dusk| every night)?$"),
    re.compile(r"^(?:tell|remind) me (?:at sunset|before dark|when it gets dark|at dusk|every evening) to (?:close|shut|draw|pull) the curtains$"),
    re.compile(r"^curtain reminders? (?:on|please)$"),
)
CURTAINS_OFF = (
    re.compile(r"^(?:stop|no more|do not keep|do not) remind(?:ing)? me (?:about|to close|to shut|to draw) the curtains$"),
    re.compile(r"^(?:no more|stop the|stop|cancel the) curtain reminders?$"),
    re.compile(r"^curtain reminders? off$"),
)
NOISE = (
    re.compile(r"^how (?:loud|noisy) was it (?:last night|today|this morning|yesterday|overnight|tonight)$"),
    re.compile(r"^was it (?:loud|noisy) (?:last night|today|overnight)$"),
    re.compile(r"^how (?:loud|noisy) has it been(?: today| tonight)?$"),
    re.compile(r"^(?:show me the |what is in the |read me the )?noise diary$"),
)
CAPTIONS_ON = (
    re.compile(r"^(?:turn on |switch on |show (?:me )?|put on |start )?(?:the )?(?:captions|subtitles)(?: on)?$"),
    re.compile(r"^(?:show|write) (?:me )?what (?:people|they|everyone|everybody) (?:are|is) saying$"),
)
CAPTIONS_OFF = (
    re.compile(r"^(?:turn off|switch off|stop|hide|no more|end) (?:the )?(?:captions|subtitles)$"),
    re.compile(r"^(?:captions|subtitles) off$"),
)
COOKING_OK = re.compile(
    r"^(?:(?:i am|we are|someone is|ina is|sam is) (?:watching it|on it|cooking|here|keeping an eye on it|in the kitchen|minding it|watching the (?:pot|pan|stove|food))"
    r"|(?:i have|we have) got it|i know|we know|leave it|it is under control|all good|no worries"
    r"|it is (?:fine|ok|simmering|meant to|supposed to)(?: [a-z ]+)?|(?:that is|it is) (?:meant|supposed) to(?: [a-z ]+)?)$"
)


def _first(patterns, s):
    for pattern in patterns:
        match = pattern.match(s)
        if match:
            return match
    return None


def _named(raw: str) -> str:
    name = " ".join(raw.split())
    name = re.sub(r"^(?:just |only )", "", name)
    return name[:ITEM_MAX]


def read(text: str, name: str = "pebble", cooking: bool = False) -> HouseAsk | None:
    s = clean(text, name)
    if not s or len(s) > 160:
        return None
    found = _lists(clean(text, name, commas=True))
    if found is not None:
        return found
    for kind, patterns in (("visitors_on", VISITORS_ON), ("visitors_off", VISITORS_OFF), ("keeps", KEEPS), ("guest_wifi", WIFI), ("alarm_test_end", ALARM_TEST_END), ("alarm_test", ALARM_TEST), ("alarms_ask", ALARMS_ASK), ("while_out", WHILE_OUT), ("light_ask", LIGHT), ("damp", DAMP), ("curtains_off", CURTAINS_OFF), ("curtains_on", CURTAINS_ON), ("noise_ask", NOISE), ("captions_off", CAPTIONS_OFF), ("captions_on", CAPTIONS_ON), ("sounds_ask", SOUNDS_ASK)):
        match = _first(patterns, s)
        if match is not None:
            item = match.groupdict().get("name") or ""
            return HouseAsk(kind, item=_named(item), text=s)
    match = _first(FACT, s)
    if match is not None:
        thing = " ".join(match.group("thing").split())
        where = " ".join(match.group("where").split())[:60]
        if thing not in NOT_ITEMS and not thing.startswith(("way ", "time ")):
            return HouseAsk("house_fact", item=thing, where=where, text=s)
    match = _first(FORGET_SOUND, s)
    if match is not None:
        return HouseAsk("forget_sound", item=_named(match.groupdict().get("name") or ""), text=s)
    match = _first(TEACH, s)
    if match is not None:
        named = _named(match.group("name"))
        if named and not NAMES_ALARM.search(named) and named not in NOT_ITEMS and len(named.split()) <= 6:
            return HouseAsk("teach_sound", item=named, text=s)
        if named and NAMES_ALARM.search(named):
            return HouseAsk("teach_sound", item=named, topic="alarm", text=s)
    match = _first(TELL_WHEN, s)
    if match is not None:
        target = _named(match.groupdict().get("name") or "")
        return HouseAsk("tell_when", item=target or "rain", text=s)
    for topic, pattern in ALMANAC:
        match = pattern.match(s)
        if match is not None:
            groups = match.groupdict()
            when = groups.get("when") or next((w for w in WHEN_WORDS if s.endswith(" " + w)), "")
            return HouseAsk("almanac", item=(groups.get("holiday") or "").replace("king s", "kings").replace("new year s", "new years"), topic=topic, when=when, text=s)
    if cooking and COOKING_OK.match(s):
        return HouseAsk("cooking_ok", text=s)
    match = GOT.match(s)
    if match is not None:
        items = items_of(match.group("item"))
        if items:
            return HouseAsk("list_remove", item=items[0], items=items, only_if_listed=True, text=s)
    return None


def _lists(s: str) -> HouseAsk | None:
    match = _first(CLEAR, s)
    if match is not None:
        return HouseAsk("list_clear", list=list_name(match.groupdict().get("list")), text=s)
    match = _first(REMOVE, s)
    if match is not None:
        items = items_of(match.group("item"))
        if items:
            return HouseAsk("list_remove", item=items[0], items=items, list=list_name(match.groupdict().get("list")) if match.groupdict().get("list") else "", text=s)
    match = _first(READ, s)
    if match is not None:
        return HouseAsk("list_read", list=list_name(match.groupdict().get("list")), text=s)
    match = _first(SHOW, s)
    if match is not None:
        going = not match.re.pattern.startswith("^(?:show") and "list" not in s
        return HouseAsk("list_show", list=list_name(match.groupdict().get("list")), topic="going" if going else "", text=s)
    for index, pattern in enumerate(ADD):
        match = pattern.match(s)
        if match is None:
            continue
        items = items_of(match.group("item"))
        if not items:
            return None
        if index == 1 and (len(items) > 3 or any(w in s for w in (" to ", " up ", " together", " plus "))):
            return None
        return HouseAsk("list_add", item=items[0], items=items, list=list_name(match.groupdict().get("list")), text=s)
    return None


def answer_word(text: str, name: str = "pebble") -> str | None:
    s = clean(text, name)
    if not s:
        return None
    if NEVER.match(s):
        return "never"
    if YES.match(s):
        return "yes"
    if NO.match(s):
        return "no"
    return None


def claimed_name(text: str, name: str = "pebble") -> str | None:
    s = clean(text, name)
    match = CLAIM_NAME.match(s)
    if match is None or match.group("name") in ("yes", "no", "ok", "me", "it", "that", "this", "here"):
        return None
    return match.group("name")
