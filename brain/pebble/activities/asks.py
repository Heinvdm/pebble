import re
from dataclasses import dataclass

from .climate import ABOUT, CAN_NOT

LEAD = re.compile(r"^(?:(?:hey|hi|oi|ok|okay|um|uh|er|so|right|and|please|just|yo|alright|well|now|oh|listen|mate)\b\s*)+")
POLITE = re.compile(r"^(?:(?:can|could|would|will) you(?: please)?|would you mind|i want you to|i would like you to|please)\b\s*")
TAIL = re.compile(r"(?:\s+\b(?:please|thanks|thank you|cheers|mate|for me|for us|will you|would you|now))+$")
CONTRACTIONS = (
    ("what's", "what is"), ("whats", "what is"), ("how's", "how is"), ("hows", "how is"), ("it's", "it is"),
    ("let's", "let us"), ("lets", "let us"), ("who's", "who is"), ("whos", "who is"), ("where's", "where is"),
    ("that's", "that is"), ("i'm", "i am"), ("we're", "we are"), ("isn't", "is not"), ("there's", "there is"),
    ("don't", "do not"), ("dont", "do not"), ("wanna", "want to"),
)
SMALL = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100, "a hundred": 100, "a couple of": 2, "couple of": 2,
}
NUMBER = r"(?:\d+|a couple of|couple of|a hundred|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?: (?:one|two|three|four|five|six|seven|eight|nine))?|an|a|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|hundred)"
UNIT_S = {"second": 1, "seconds": 1, "sec": 1, "secs": 1, "minute": 60, "minutes": 60, "min": 60, "mins": 60}
DURATION = re.compile(rf"\b(?P<n>{NUMBER}) (?P<unit>seconds|second|secs|sec|minutes|minute|mins|min)\b")
ROOMS = (
    "main bedroom", "master bedroom", "spare bedroom", "spare room", "living room", "family room", "dining room", "kids room",
    "play room", "games room", "tv room", "kitchen", "lounge", "bedroom", "bathroom", "office", "study", "hallway", "hall",
    "laundry", "garage", "nursery", "toilet", "sunroom", "conservatory", "attic", "basement", "playroom", "den",
)
HERE = ("in here", "here", "this room", "in this room", "where you are", "where we are", "inside")
CLIMATE = r"(?:warm|warmer|warmest|cold|colder|coldest|hot|hotter|hottest|chilly|cool|cooler|freezing|temperature|temp|degrees|humid|humidity|damp|muggy|stuffy|dew point)"
AIR = r"(?:how is the air|what is the air like|air quality|is the air (?:ok|okay|fresh|stuffy|smelly|good|bad|clean))"
ASKING = re.compile(r"^(?:how|what|is|are|which|where|tell me|do you know|any idea)\b")
COMPARE = re.compile(r"^(?:which|what|where)\b.*\b(?P<word>warmest|hottest|coldest|coolest|chilliest|most humid|dampest|most damp|warmer|colder|hotter)\b")
TARGET = re.compile(r"\b(?:is|in|of|inside|for) (?:the|your|my|our|a) (?P<target>[a-z ]+?)(?: (?:like|now|right now|today|tonight|at the moment|room))?$")
MEASURE = re.compile(r"^(?:go and |go |)(?P<verb>measure|check|take a reading of|take readings in|read)\b(?P<rest>.*)$")
ROUND = re.compile(r"^(?:go and |go |)(?:do|start)? ?(?:a|your|the)? ?(?:round of the rooms|climate round|air round|round of the house|round the rooms|rounds)$|^(?:go )?round the rooms$")
ALL_ROOMS = re.compile(r"\b(?:rooms|every room|each room|all the rooms|whole house|the house)\b")
GAMES = (
    ("red_light", re.compile(r"\b(?:red light,? green light|green light,? red light|red light green light)\b")),
    ("statues", re.compile(r"\b(?:musical statues|statues)\b")),
    ("hide_seek", re.compile(r"\b(?:hide and seek|hide n seek|hide and go seek|hide an seek)\b")),
)
PLAY = re.compile(r"\b(?:play|playing|game of|a game|want to|let us|can we|shall we|how about|could we|will you)\b")
NOT_PLAY = re.compile(r"\b(?:stop|do not|no more|not|never|enough)\b")
AGAIN = re.compile(r"^(?:let us |can we |shall we )?(?:play |go )?(?:it |that )?(?:again|one more time|one more game|one more go|another game|another go|another round)$")
DICE = re.compile(r"\b(?:roll|throw|chuck)\b(?P<rest>.*)\b(?:dice|die|d(?P<d>\d+))\b")
SIDES = re.compile(rf"\b(?P<n>{NUMBER}) sided\b")
COUNT = re.compile(rf"\b(?:roll|throw|chuck) (?:the )?(?P<n>{NUMBER}) (?:\d+ sided |[a-z]+ sided )?(?:dice|die)\b")
COIN = re.compile(r"\b(?:flip|toss|throw|spin) (?:a|the|us a|me a) coin\b|^heads or tails$")
POINTS = r"(?:point|points)"
ADD = (
    re.compile(rf"^(?:give|add) (?P<n>{NUMBER}) {POINTS} (?:to|for) (?P<who>[a-z ]+)$"),
    re.compile(rf"^give (?P<who>[a-z ]+?) (?P<n>{NUMBER}) (?:more )?{POINTS}$"),
    re.compile(rf"^(?:that is )?(?P<n>{NUMBER}) {POINTS} (?:to|for) (?P<who>[a-z ]+)$"),
    re.compile(rf"^{POINTS} (?:to|for) (?P<who>[a-z ]+)$"),
    re.compile(rf"^(?P<who>[a-z ]+?) (?:gets|scores|got|scored|wins|won) (?P<n>{NUMBER}) {POINTS}$"),
)
TAKE = (
    re.compile(rf"^(?:take|minus|subtract|knock) (?P<n>{NUMBER}) {POINTS} (?:off|from) (?P<who>[a-z ]+)$"),
    re.compile(rf"^(?P<who>[a-z ]+?) (?:loses|lost) (?P<n>{NUMBER}) {POINTS}$"),
)
SCORE_READ = re.compile(r"^(?:what is|what are|tell us|tell me|read out|read|say) (?:the|our) (?:score|scores)(?: now| so far)?$|^who is (?:winning|ahead|in the lead)$")
SCORE_ONE = re.compile(rf"^how many {POINTS} (?:does|has) (?P<who>[a-z ]+?)(?: have| got)?$")
SCORE_RESET = re.compile(r"^(?:reset|clear|wipe|zero) (?:the |our |all the )?(?:score|scores)$|^start the scores (?:again|over)$|^new scores$")
TIMER = re.compile(r"\b(?:turn timer|time (?:our|each|the|my|your|their) turns?|time each turn|(?:a|per|for each|each) turn)\b")
EACH = re.compile(r"\b(?:each|a turn|per turn|every turn|a go|per go)\b")
NEXT = re.compile(r"^(?:next|next turn|next player|next go|your turn|my turn|go|start|start the timer|start the turn|start the clock)$")
TIMER_STOP = re.compile(r"^(?:stop|cancel|end|turn off|switch off) (?:the )?(?:turn )?timer$|^no more (?:turn )?timer$|^(?:turn )?timer off$")
TIMER_LEFT = re.compile(r"^how (?:much time|long) (?:is |have we got |do we have )?left$|^time left$")
CHIRP = r"(?:chirp|chirps|chirping|chirpy|beeping|beep|beeps|peeping|peep)"
FIND_CHIRP = (
    re.compile(rf"\b(?:find|track down|look for|hunt for|search for|locate)\b.*\b{CHIRP}\b"),
    re.compile(rf"^(?:which|what) (?:smoke |fire )?(?:alarm|alarms|detector|detectors|one)\b.*\b{CHIRP}\b"),
    re.compile(rf"^where is (?:that|the|this) {CHIRP}\b.*\bcoming from$"),
    re.compile(rf"^where is (?:the|that) {CHIRP} (?:smoke |fire )?(?:alarm|detector)$"),
)
PRONOUNS = frozenset({"me", "us", "you", "him", "her", "them", "it", "myself", "everyone", "everybody"})


@dataclass(frozen=True)
class Ask:
    kind: str
    room: str = ""
    about: str = ""
    which: str = ""
    game: str = ""
    count: int = 1
    sides: int = 6
    who: str = ""
    points: int = 0
    seconds: float = 0.0


def clean(text: str, name: str = "pebble") -> str:
    out = (text or "").lower().replace("’", "'").replace("‘", "'").replace("-", " ")
    for short, long in CONTRACTIONS:
        out = re.sub(rf"(?<![a-z']){re.escape(short)}(?![a-z'])", long, out)
    out = out.replace("'", "")
    out = re.sub(r"[^a-z0-9 ,]+", " ", out)
    out = re.sub(rf"\b{re.escape(name.lower())}\b", " ", out)
    out = " ".join(out.replace(",", " , ").split())
    out = re.sub(r"(?:^|\s),(?=\s|$)", ",", out).strip(" ,")
    out = LEAD.sub("", out)
    out = POLITE.sub("", out)
    out = TAIL.sub("", out)
    return out.replace(" ,", ",").strip(" ,")


def number(text: str) -> int | None:
    text = text.strip()
    if text.isdigit():
        return int(text)
    if text in SMALL:
        return SMALL[text]
    parts = text.split()
    if len(parts) == 2 and parts[0] in SMALL and parts[1] in SMALL and SMALL[parts[0]] >= 20 and SMALL[parts[1]] < 10:
        return SMALL[parts[0]] + SMALL[parts[1]]
    return None


def duration(text: str) -> float | None:
    if re.search(r"\bhalf a minute\b", text):
        return 30.0
    if re.search(r"\b(?:a|one) minute and a half\b|\bone and a half minutes\b|\b90 seconds\b", text):
        return 90.0
    match = DURATION.search(text)
    if match is None:
        return None
    n = number(match.group("n"))
    return None if n is None else float(n * UNIT_S[match.group("unit")])


def room_in(text: str, places: list[str]) -> str:
    names = sorted({p.lower() for p in places} | set(ROOMS), key=len, reverse=True)
    for name in names:
        if re.search(rf"\b{re.escape(name)}\b", text):
            return "lounge" if name == "living room" and "lounge" in places else name
    match = re.search(r"\b(?P<who>[a-z]+)s (?:room|bedroom)\b", text)
    if match is not None and match.group("who") not in ("kid", "guest", "spare"):
        return match.group(0)
    return ""


def _climate(text: str, places: list[str]) -> Ask | None:
    compare = COMPARE.search(text)
    if compare is not None and re.search(r"\b(?:room|rooms|place|it|where)\b", text):
        word = compare.group("word")
        which = "humid" if word in ("most humid", "dampest", "most damp") else ("cold" if word in ("coldest", "coolest", "chilliest", "colder") else "warm")
        return Ask("climate_compare", which=which)
    air = re.search(AIR, text) is not None
    word = re.search(rf"\b{CLIMATE}\b", text)
    if not ASKING.search(text) or (word is None and not air):
        return None
    about = "air" if air and word is None else ABOUT.get(word.group(0), "temperature") if word is not None else "air"
    if word is not None and word.group(0) in ("temp", "degrees", "freezing"):
        about = "temperature"
    if word is not None and word.group(0) == "dew point":
        about = "humidity"
    for thing, _ in CAN_NOT.items():
        if re.search(rf"\b{thing}\b", text):
            return Ask("climate", room=thing, about=about)
    room = room_in(text, places)
    if room:
        return Ask("climate", room=room, about=about)
    target = TARGET.search(text)
    if target is not None and target.group("target").strip() not in HERE and target.group("target").strip() not in ("air", "temperature", "humidity", "weather"):
        return None
    if re.search(r"\b(?:you|your)\b", text) and not re.search(r"\b(?:where you are|near you|by you)\b", text):
        return None
    return Ask("climate", room="here", about=about)


def _measure(text: str, places: list[str]) -> Ask | None:
    if ROUND.match(text):
        return Ask("climate_round")
    match = MEASURE.match(text)
    if match is None:
        return None
    rest = match.group("rest")
    climate = re.search(rf"\b(?:air|temperature|temp|humidity|{CLIMATE})\b", rest) is not None
    if not climate and (match.group("verb") != "measure" or (not ALL_ROOMS.search(rest) and not room_in(rest, places))):
        return None
    if re.search(r"\b(?:fridge|freezer|oven|water|bath|food|tea|coffee|baby|bottle)\b", rest):
        return None
    room = room_in(rest, places)
    if room:
        return Ask("climate_round", room=room)
    if ALL_ROOMS.search(rest):
        return Ask("climate_round")
    return Ask("climate", room="here", about=ABOUT.get((re.search(rf"\b{CLIMATE}\b", rest) or re.search(r"air", rest)).group(0), "air"))


def _game(text: str, last_game: str) -> Ask | None:
    if last_game and AGAIN.match(text):
        return Ask("game", game=last_game)
    for kind, pattern in GAMES:
        if pattern.search(text):
            if NOT_PLAY.search(text):
                return None
            bare = pattern.sub("", text).strip(" ,!")
            if PLAY.search(text) or not bare:
                return Ask("game", game=kind)
    return None


def _dice(text: str) -> Ask | None:
    if COIN.search(text):
        return Ask("coin")
    match = DICE.search(text)
    if match is None:
        return None
    sides = 6
    if match.group("d"):
        sides = int(match.group("d"))
    sided = SIDES.search(text)
    if sided is not None:
        sides = number(sided.group("n")) or 6
    count = 1
    counted = COUNT.search(text)
    if counted is not None:
        count = number(counted.group("n")) or 1
    return Ask("dice", count=count, sides=sides)


def _who(raw: str) -> str:
    who = re.sub(r"^(?:the )?", "", raw.strip())
    who = re.sub(r"\b(?:please|now|then|too)$", "", who).strip()
    return who if 0 < len(who.split()) <= 3 else ""


def _scores(text: str, has_scores: bool) -> Ask | None:
    for pattern in ADD:
        match = pattern.match(text)
        if match is not None:
            n = number(match.groupdict().get("n") or "one") or 1
            return Ask("score_add", who=_who(match.group("who")), points=n)
    for pattern in TAKE:
        match = pattern.match(text)
        if match is not None:
            n = number(match.groupdict().get("n") or "one") or 1
            return Ask("score_add", who=_who(match.group("who")), points=-n)
    if SCORE_RESET.match(text):
        return Ask("score_reset")
    one = SCORE_ONE.match(text)
    if one is not None and has_scores:
        return Ask("score_one", who=_who(one.group("who")))
    if SCORE_READ.match(text) and has_scores:
        return Ask("score_read")
    return None


def _timer(text: str, timer_set: bool, timer_running: bool) -> Ask | None:
    if timer_set and NEXT.match(text):
        return Ask("turn_next")
    if timer_set and TIMER_STOP.match(text):
        return Ask("turn_stop")
    if timer_running and TIMER_LEFT.match(text):
        return Ask("turn_left")
    seconds = duration(text)
    if TIMER.search(text) or (seconds is not None and EACH.search(text) and re.search(r"\b(?:turn|turns|go|goes|each)\b", text) and not re.search(r"\b(?:remind|wait|cook|bake|boil)\b", text)):
        if re.search(r"\b(?:stop|cancel|no more|off)\b", text):
            return Ask("turn_stop") if timer_set else None
        return Ask("turn_set", seconds=seconds or 60.0)
    return None


def read(text: str, places: list[str] | None = None, name: str = "pebble", has_scores: bool = False, timer_set: bool = False, timer_running: bool = False, last_game: str = "") -> Ask | None:
    s = clean(text, name)
    if not s:
        return None
    places = list(places or [])
    for pattern in FIND_CHIRP:
        if pattern.search(s):
            return Ask("find_chirp")
    for step in (
        lambda: _timer(s, timer_set, timer_running),
        lambda: _scores(s, has_scores),
        lambda: _dice(s),
        lambda: _game(s, last_game),
        lambda: _measure(s, places),
        lambda: _climate(s, places),
    ):
        found = step()
        if found is not None:
            if found.kind == "score_add" and (not found.who or found.who in PRONOUNS):
                return Ask("score_add", who=found.who if found.who in ("me", "myself") else "", points=found.points)
            return found
    return None
