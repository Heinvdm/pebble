import re
from dataclasses import dataclass

LIST = re.compile(r"^(?:(?:what|which) (?:programs?|scripts?) (?:are you|do you|have you got)(?: got)? ?(?:running|run|have|on)?|are you running any (?:programs?|scripts?)|(?:list|tell me) (?:all )?your (?:programs?|scripts?)|what are your (?:programs?|scripts?))\b")
ALL = re.compile(r"^(?:stop|end|turn off|switch off|cancel) (?:all (?:of )?)?(?:your|the|my|those|these) (?:programs?|scripts?)\b|^(?:stop|end) all (?:the )?(?:programs?|scripts?)\b")
OFF = re.compile(r"^(?:no (?:more )?(?:programs?|scripts?)(?: please| for now| tonight)?|(?:don't|do not) run (?:any )?(?:more )?(?:programs?|scripts?)|switch (?:your )?programs off|turn (?:your )?programs off)$")
ON = re.compile(r"^(?:you can (?:run|start) (?:your )?(?:programs?|scripts?) again|(?:programs?|scripts?) (?:back )?on|turn (?:your )?(?:programs?|scripts?) (?:back )?on|switch (?:your )?(?:programs?|scripts?) (?:back )?on|start (?:your )?(?:programs?|scripts?) again)\b")
ONE = re.compile(r"^(?:stop|end|turn off|switch off|cancel|finish) (?:the |my |your |that |our )?(.+?)$")
POLITE = re.compile(r"^(?:(?:hey |ok |okay |please |pebble,? )+)|(?:,? (?:please|now|pebble|thanks|thank you))+$")
ASK = re.compile(
    r"\b(?:(?:make|write|build|create|program) (?:me |us |for me )?(?:a |an )?(?:little |new )?(?:program|script)|"
    r"count (?:how many|the number|every|each|up to|to (?:\d+|ten|twenty|fifty|a hundred))|count (?:the |my |all the )?[a-z]+ .{0,60}(?:tell|let) me|keep (?:a )?count|keep (?:the )?score|keep track of how many|tally (?:up )?(?:how many|the)|how many times .{3,60} (?:tell|let) me|"
    r"(?:play|let's play|can we play|shall we play|wanna play|fancy|do) (?:a game of |a round of |some )?(?:simon says|red light,? green light|treasure hunt|a treasure hunt|a quiz)|"
    r"quiz me|give (?:me|us) a quiz|(?:every|each) time .{3,60}(?:count|tell me|let me know|say)|"
    r"every morning,? (?:say hello|greet)|tell me a story with (?:your )?faces|story time with (?:your )?faces)\b"
)
LOOPY = re.compile(r"\b(?:count|counting|how many|keep score|every time|each time|until .{2,40} then|tally|times in a row)\b")


@dataclass(frozen=True)
class Said:
    kind: str
    name: str = ""


def plain(text: str) -> str:
    said = " ".join(re.findall(r"[a-z0-9',]+", str(text or "").lower().replace("’", "'")))
    for _ in range(3):
        said = POLITE.sub("", said).strip(" ,")
    return said.replace(",", "")


def read(text: str) -> Said | None:
    said = plain(text)
    if not said:
        return None
    if LIST.match(said):
        return Said("list")
    if OFF.match(said):
        return Said("off")
    if ON.match(said):
        return Said("on")
    if ALL.match(said):
        return Said("all")
    found = ONE.match(said)
    if found:
        name = re.sub(r" (?:program|script)$", "", found.group(1).strip())
        if name and name not in ("it", "that", "this", "now", "following", "following me", "moving", "talking"):
            return Said("one", name)
    return None


def asks_for_program(text: str) -> bool:
    said = " ".join(str(text or "").lower().replace("’", "'").split())
    if re.match(r"^(?:don't|do not|never|stop|no)\b", said):
        return False
    return bool(ASK.search(said))


def loopy(text: str) -> bool:
    return bool(LOOPY.search(" ".join(str(text or "").lower().split())))
