import re

from ..understand.house import HouseAsk, clean

HIGH_WORDS = r"(?:high|high pitched|really high|very high|squeaky|shrill)"
NOISE_WORDS = r"(?:sound|sounds|noise|noises|tone|tones|whine|whining|beep|beeping|whistle|whistling|squeal|hum)"
THINGS = r"(?:charger|phone charger|laptop charger|power supply|adapter|power adapter|plug|tv|telly|television|screen|monitor|fridge|light|lamp|router|something|anything)"
HIGH = (
    re.compile(rf"^(?:can |do )?(?:you )?hear (?:anything|something|a|any|that) {HIGH_WORDS}(?: {NOISE_WORDS})?(?: in here| here| now| at the moment)?$"),
    re.compile(rf"^(?:can |do )?(?:you )?hear (?:a|any|that|the) (?:{HIGH_WORDS} )?(?:whine|whining|squeal|mosquito|mosquito tone)(?: in here| here| now)?$"),
    re.compile(rf"^is (?:my|the|our|that|a|this) {THINGS} (?:whining|whistling|squealing|making a {HIGH_WORDS} (?:noise|sound))$"),
    re.compile(rf"^is (?:there|something) (?:a |any )?(?:{HIGH_WORDS} )?(?:whine|whining|squeal|{HIGH_WORDS} {NOISE_WORDS})(?: in here| here)?$"),
    re.compile(rf"^(?:what is|what s|whats) (?:that|this) {HIGH_WORDS} {NOISE_WORDS}$"),
    re.compile(rf"^(?:is anything|is something) (?:making|sending) (?:a |any )?(?:{HIGH_WORDS} {NOISE_WORDS}|data tones|ultrasound)(?: in here| here)?$"),
)
REACH = (
    re.compile(r"^how high can you hear$"),
    re.compile(r"^how (?:high|far up) (?:does|do) your (?:hearing|ears|microphones?) go$"),
)
LIGHT_ON = (
    re.compile(r"^(?:a )?(?:light|torch)(?: on)?$"),
    re.compile(r"^(?:can|could|may) (?:i|we) (?:have|get) (?:some |a )?(?:light|torch)$"),
    re.compile(r"^(?:i|we) need (?:some |a )?(?:light|torch)$"),
    re.compile(r"^(?:turn|switch|put|flick) (?:on )?your (?:light|torch|flashlight)(?: on)?$"),
    re.compile(r"^(?:shine|use) your (?:light|torch|flashlight)$"),
    re.compile(r"^light the way$"),
    re.compile(r"^be (?:my|our|a) (?:torch|night light|light)$"),
)
LIGHT_OFF = (
    re.compile(r"^(?:light|torch) off$"),
    re.compile(r"^(?:turn|switch|put|flick) (?:off )?your (?:light|torch|flashlight)(?: off| out)?$"),
    re.compile(r"^(?:you can )?(?:turn|switch) (?:off )?(?:the |your )?(?:light|torch) (?:off|out) now$"),
    re.compile(r"^(?:that is|that s|thats) enough light$"),
    re.compile(r"^(?:no more|stop the|stop your) (?:light|torch)$"),
)
PROBE = (
    re.compile(r"^(?:check|test|measure) (?:your|the) (?:hearing|microphones?|mics?|ears)$"),
    re.compile(r"^(?:run|start|do) (?:the |a )?(?:microphone|mic|hearing) (?:check|test|probe)$"),
)
TV_ON = (
    re.compile(r"^(?:start|do|run|begin)(?: the| a)? (?:television|tv|telly) (?:check|test)$"),
    re.compile(r"^(?:the )?(?:television|tv|telly) (?:check|test)(?: now| please)?$"),
)
TV_OFF = (
    re.compile(r"^(?:stop|end|cancel|finish) (?:the )?(?:television|tv|telly) (?:check|test)$"),
)


def _first(patterns, s: str) -> bool:
    return any(pattern.match(s) for pattern in patterns)


def read_senses(text: str, name: str = "pebble") -> HouseAsk | None:
    s = clean(text, name)
    if not s or len(s) > 120:
        return None
    if _first(TV_OFF, s):
        return HouseAsk("tv_check_end", text=s)
    if _first(TV_ON, s):
        return HouseAsk("tv_check", text=s)
    if _first(PROBE, s):
        return HouseAsk("mic_probe", text=s)
    if _first(LIGHT_OFF, s):
        return HouseAsk("torch_off", text=s)
    if _first(LIGHT_ON, s):
        return HouseAsk("torch_on", text=s)
    if _first(REACH, s):
        return HouseAsk("high_ask", topic="reach", text=s)
    if _first(HIGH, s):
        return HouseAsk("high_ask", text=s)
    return None
