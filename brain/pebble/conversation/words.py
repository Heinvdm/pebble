import re

WORD = re.compile(r"[a-z0-9']+")
STOP = frozenset(
    "a an the and or but so if then than that this these those there here it its it's is are was were be been being am do does did done doing have has had having "
    "i me my mine we us our ours you your yours he him his she her hers they them their theirs what which who whom whose when where why how "
    "to of in on at by for with about from up down out over under again into onto off just very really quite too also not no yes yeah yep nope "
    "can could will would shall should may might must ok okay oh um uh erm hmm like well right know think mean get got go going gonna wanna "
    "some any all one two lot lots thing things stuff kind sort bit little much many more most other another such own same now still even "
    "let's lets let say said tell told see saw look make made want need came come back way time day today tonight "
    "haha hehe lol thanks thank still found been good great sure maybe actually wait perfect fine nice cool totally probably definitely "
    "yesterday tomorrow already always never ever something anything everything nothing someone anyone everyone seen seeing heard".split()
)
QUESTION_START = frozenset("what where when why who whom whose which how is are was were do does did can could will would should shall have has may might am isn't aren't don't doesn't didn't can't won't wouldn't anyone anybody somebody".split())
COMMAND_START = frozenset("come go look follow stop wait turn spin tell show find bring sing dance play give help listen move back stay sit let say".split())
TRAILING = frozenset("and but so or because the a an to of with for my your his her their our if that um uh like is are was than then about at in on".split())
SHORT_DONE = frozenset("yes no yeah nope yep thanks okay ok sure alright cool nice great hello hi hey bye goodnight night".split())
VOCATIVE_LEAD = frozenset("hey hi hello oi yo ok okay so and um well right".split())
MENTION_AFTER = frozenset("is was has had does did can could will would just always never seems looks sounds isn't wasn't doesn't didn't likes loves hates knows thinks".split())
MENTION_BEFORE = frozenset("about with to at see saw seen like likes love loves call called named that the our my your his her their poor little silly cute".split())
KIN = ("mum", "mom", "mummy", "mommy", "ma", "dad", "daddy", "babe", "baby", "honey", "darling", "love", "sweetie", "sweetheart", "mate", "bro", "sis", "guys", "buddy", "dude", "grandma", "grandpa", "gran", "nana", "ouma", "oupa", "boet", "china", "kiddo", "son")
CALL_WORDS = frozenset("hello bye goodbye talk later speak call ring hear line phone".split())
BACKCHANNEL = frozenset("yeah yes uh huh mhm mm okay ok right sure really oh wow totally exactly".split())
FUTURE = re.compile(r"\b(tomorrow|tonight|next (week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|on (monday|tuesday|wednesday|thursday|friday|saturday|sunday)|this (weekend|evening|afternoon|morning)|later today|i'm going to|i am going to|i'll|we'll|we're going to|gonna|have to|got to|need to)\b")
POSITIVE = frozenset("love lovely great good nice happy fun funny awesome amazing brilliant excited glad wonderful beautiful yay cool sweet best fantastic delicious perfect thanks thank".split())
NEGATIVE = frozenset("hate awful terrible bad sad angry annoyed annoying upset worried scared tired sick hurt cry crying stupid idiot never horrible worst ugh damn sorry lonely stressed".split())
HOSTILE = re.compile(r"\b(shut up|you never|you always|i can't believe you|leave me alone|get out|i hate you|how dare you|whatever|don't talk to me|are you kidding|stop it|for god's sake|what is wrong with you)\b")
LAUGH = re.compile(r"\b(ha(ha)+|he(he)+|lol|lmao)\b")
DONE_CLAIM = re.compile(r"\b(i(?:'ve| have) (?:noted|saved|added|set|written|put|stored|made a note)|reminder (?:is |has been )?set|i(?:'ve| have) remembered|it's (?:noted|saved) )", re.IGNORECASE)
PROMISED = re.compile(
    r"\b(?:i'll|i will|i'm going to|i am going to|i'm gonna)\s+(?:(?:be sure to|make sure to|try to|definitely|also|just|certainly|happily)\s+)?"
    r"(?P<act>remind|tell|let\b[^.!?]{0,30}?\bknow|wake|check|look|come|find|fetch|bring|ask|call|keep an eye|watch|show|sing|draw|play|read|give|get back)\b",
    re.IGNORECASE,
)
FOR_LATER = re.compile(r"^(?:remind|wake)\b", re.IGNORECASE)
CORRECTING = re.compile(
    r"^\s*(?:(?:sorry|oops|wait|oh|um|hang on)[,!.]*\s+)*(?:"
    r"no[,!.]*\s+(?:i meant|i said|i mean|it'?s|it is|it was|its|the|my|that'?s|that was|not|they|she|he|we|actually|wait|sorry)\b"
    r"|i meant\b|i mean\b|i said\b|actually\b|correction\b|let me correct|that'?s (?:not (?:right|it|what i (?:said|meant))|wrong)\b|wrong\b"
    r"|not (?:the|that|my|your|his|her|on|at)\b[^.!?]{0,40},\s*(?:the|my|your|his|her|on|at)\b)",
    re.IGNORECASE,
)
REFUSING = re.compile(
    r"\bi (?:can't|cannot|won't|will not|shouldn't|mustn't|would rather not|'d rather not)\s+(?:do|go|tell|say|share|help|let|give|take|open|touch|chase|hurt|move|come|follow|look|watch|keep|pass|repeat|record|show|bring|fetch|play|be|pretend|lie)\b"
    r"|\bi'?m not (?:allowed|able|going) to\b|\bi am not (?:allowed|able|going) to\b|\bthat'?s not (?:something i|mine to)\b|\bi'?d rather not\b|\bi (?:have|need) to say no\b|\bi'?ll have to say no\b",
    re.IGNORECASE,
)
SENTENCES = re.compile(r"(?<=[.!?])\s+")


def words(text: str) -> list[str]:
    return WORD.findall((text or "").lower())


def content(text: str) -> list[str]:
    return [w for w in words(text) if w not in STOP and len(w) > 2 and not w.isdigit()]


def _near(word: str, name: str) -> bool:
    if word == name or word == name + "s" or word == name + "'s":
        return True
    if len(name) < 5 or abs(len(word) - len(name)) > 1:
        return False
    if len(word) == len(name):
        return sum(a != b for a, b in zip(word, name)) <= 1
    short, long = (word, name) if len(word) < len(name) else (name, word)
    return any(long[:i] + long[i + 1 :] == short for i in range(len(long)))


def name_at(text: str, name: str) -> list[int]:
    name = name.lower().strip()
    found = []
    for index, word in enumerate(words(text)):
        if _near(word, name):
            found.append(index)
    return found


MODALS = frozenset("can could will would does did is are was do".split())
ASKED = frozenset("you we i u ya".split())


def subject_at(said: list[str], spot: int) -> bool:
    after = said[spot + 1] if spot + 1 < len(said) else ""
    if said[spot].endswith("'s"):
        return True
    if after in MODALS and spot + 2 < len(said) and said[spot + 2] in ASKED:
        return False
    return after in MENTION_AFTER


def name_use(text: str, name: str, keyword: bool = False, alone: bool = False) -> str | None:
    said = words(text)
    spots = name_at(text, name)
    if not spots:
        if alone:
            return "vocative"
        if keyword:
            return "vocative" if len(said) <= 6 and you_form(text) else "mention"
        return None
    plain = name.lower().strip()
    for spot in spots:
        before = said[spot - 1] if spot > 0 else ""
        if said[spot] == plain + "s" or subject_at(said, spot) or before in MENTION_BEFORE:
            continue
        if all(w in VOCATIVE_LEAD for w in said[:spot]):
            return "vocative"
        if spot == len(said) - 1 and (len(said) <= 4 or you_form(text) or is_question(text)):
            return "vocative"
    return "mention"


def body(text: str, names) -> str:
    skip = {n.lower().strip() for n in names if n} | set(KIN)
    said = words(text)
    start = 0
    while start < len(said) and (said[start] in VOCATIVE_LEAD or said[start] in skip or any(_near(said[start], n) for n in skip if len(n) >= 5)):
        if said[start] not in VOCATIVE_LEAD and subject_at(said, start):
            break
        start += 1
    end = len(said)
    if end - start > 1 and (said[end - 1] in skip or any(_near(said[end - 1], n) for n in skip if len(n) >= 5)):
        end -= 1
    return " ".join(said[start:end])


def other_vocative(text: str, names: list[str]) -> str | None:
    said = words(text)
    if not said:
        return None
    directed = you_form(text) or is_question(text) or is_command(" ".join(said[1:]))
    for name in list(names) + list(KIN):
        clean = name.lower().strip()
        if not clean:
            continue
        lead = 1 if said[0] in VOCATIVE_LEAD and len(said) > 1 else 0
        if said[lead] == clean and len(said) > lead + 1 and not subject_at(said, lead):
            return name
        if lead and said[lead] == clean and len(said) == lead + 1:
            return name
        if said[-1] == clean and len(said) > 2 and directed and said[-2] not in MENTION_BEFORE:
            return name
    return None


def is_question(text: str) -> bool:
    said = words(text)
    if not said:
        return False
    lead = said[1:] if said[0] in VOCATIVE_LEAD and len(said) > 1 else said
    return bool(lead) and (lead[0] in QUESTION_START or "?" in (text or "") or any(w in ("anyone", "anybody") for w in lead))


def you_form(text: str) -> bool:
    said = words(text)
    if not said:
        return False
    lead = said[1:] if said[0] in VOCATIVE_LEAD and len(said) > 1 else said
    return bool(lead) and ("you" in lead or "your" in lead or "you're" in lead or lead[0] in COMMAND_START)


def is_command(text: str) -> bool:
    said = words(text)
    lead = said[1:] if said and said[0] in VOCATIVE_LEAD and len(said) > 1 else said
    return bool(lead) and lead[0] in COMMAND_START


def complete(text: str) -> bool:
    said = words(text)
    if not said:
        return False
    if said[-1] in TRAILING:
        return False
    if len(said) == 1:
        return said[0] in SHORT_DONE
    if is_question(text) and len(said) >= 3:
        return True
    return is_command(text) and len(said) >= 2


def to_room(text: str) -> bool:
    said = words(text)
    return any(w in ("anyone", "anybody", "somebody", "someone", "everyone", "guys") for w in said) and is_question(text)


def mood_of(text: str) -> float:
    said = words(text)
    if not said:
        return 0.0
    good = sum(1 for w in said if w in POSITIVE)
    bad = sum(1 for w in said if w in NEGATIVE)
    bad += 2 * len(HOSTILE.findall(text.lower()))
    return max(-1.0, min(1.0, (good - bad) / max(3.0, len(said) / 3.0)))


def hostile(text: str) -> bool:
    return bool(HOSTILE.search((text or "").lower()))


def laughing(text: str) -> bool:
    return bool(LAUGH.search((text or "").lower()))


def backchannel(text: str) -> bool:
    said = words(text)
    return bool(said) and len(said) <= 3 and all(w in BACKCHANNEL for w in said)


def call_words(text: str) -> bool:
    said = words(text)
    return bool(said) and (said[0] in ("hello", "hi") and len(said) <= 3 or any(w in CALL_WORDS for w in said[-3:]) and ("bye" in said or "later" in said or "talk" in said))


def overlap(a: str, b: str) -> float:
    left, right = words(a), set(words(b))
    if not left:
        return 0.0
    return sum(1 for w in left if w in right) / len(left)


def future(text: str) -> bool:
    return bool(FUTURE.search((text or "").lower()))


ABOUT_IT = re.compile(r"\b(does it|is it|can it|will it|did it|it knows|it understands|does he|does she|can he|can she|is he|is she|the robot|this robot|that robot|this thing|that thing|the little guy|this little thing)\b")


def about_it(text: str) -> bool:
    return bool(ABOUT_IT.search((text or "").lower()))


ROOM_FORMS = (
    (re.compile(r"^(?:has|have|did) (?:anyone|anybody|someone|somebody|you guys|any of you) (?:seen|spotted|found) (.+)$"), "have you seen {0}"),
    (re.compile(r"^(?:anyone|anybody|someone|somebody) (?:seen|spotted|found) (.+)$"), "have you seen {0}"),
    (re.compile(r"^(?:does|do) (?:anyone|anybody|someone|somebody|you guys) know where (.+?) (?:is|are|went|has gone|have gone)$"), "where is {0}"),
    (re.compile(r"^(?:where's|where is|where are) (.+?) (?:anyone|anybody|guys)$"), "where is {0}"),
)


def as_asked_of_me(text: str) -> str:
    said = " ".join(words(text))
    for pattern, template in ROOM_FORMS:
        match = pattern.match(said)
        if match is not None:
            return template.format(match.group(1))
    return said
