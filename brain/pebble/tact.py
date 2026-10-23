import re
from typing import Callable

from .respect import cruel
from .seams.voice import SpeechResult, Voice

TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*(?:-[A-Za-z]+)*|\d+|[.,!?;:]")
SENTENCE = re.compile(r"(?<=[.!?])\s+|(?<=[.!?][\"')\]])\s+")
WHOLE = {"can't": ("can", "not"), "won't": ("will", "not"), "shan't": ("shall", "not"), "ain't": ("is", "not"), "let's": ("let", "us")}
ENDINGS = (("n't", "not"), ("'re", "are"), ("'ve", "have"), ("'ll", "will"), ("'m", "am"), ("'d", "would"), ("'s", "'s"))
OWN = frozenset({"i", "pebble"})
NOT_NAMES = frozenset(
    "i a an the this that these those it its there here what where when who whom whose why how which whatever everything something nothing anything "
    "all both each every some any no none one another other others such my your his her our their mine yours me you he she we they him us them "
    "yes yeah yep nope okay ok oh ooh ah aah aw aww wow whoa hmm hm mm mmm um uh er well so but and or then now please thanks thank sorry hello hi hey "
    "hiya bye goodbye cheers alright right sure great good nice lovely cool fine perfect awesome brilliant excellent oops phew yay hooray ha haha "
    "hehe shh anyway also still maybe perhaps actually honestly really wait look listen see remember mind careful watch stop go come let do did "
    "does can could would should will shall may might must is are was were have has had be being not never always sometimes often today tonight "
    "tomorrow yesterday morning afternoon evening night weekend monday tuesday wednesday thursday friday saturday sunday january february march "
    "april june july august september october november december spring summer autumn winter christmas easter birthday breakfast lunch dinner tea "
    "supper dessert pudding snack food coffee water weather outside inside upstairs downstairs home time everyone everybody someone somebody "
    "nobody anyone anybody earthquake fire smoke help toast cake bread rain sun sky room house garden music battery charger floor door window "
    "plant plants".split()
)
NOT_NAME_AFTER = frozenset("the a an this that these those my your his her their our its some any every each no".split())


def words(text: str) -> tuple[str, ...]:
    return tuple(text.split("|"))


def alt(*groups: tuple[str, ...]) -> str:
    found = {word for group in groups for word in group}
    return "(?:" + "|".join(re.escape(word).replace("\\ ", " ") for word in sorted(found, key=len, reverse=True)) + ")"


YOU = words("you|ya|yourself|yourselves|you all|you two|you guys|you both|both of you|all of you")
HE_SHE = words("he|she|him|her|himself|herself")
GROUP = words("we|us|ourselves|someone|somebody|anyone|anybody|everyone|everybody|nobody|no one|whoever")
THEY = words("they|them|themselves")
PEOPLE = words(
    "man|men|woman|women|lady|ladies|gentleman|gentlemen|guy|guys|boy|boys|girl|girls|kid|kids|child|children|baby|babies|toddler|toddlers"
    "|teenager|teenagers|teen|teens|person|mum|mom|mummy|mommy|mother|dad|daddy|father|parent|parents|grandma|grandpa|granny|grandad|granddad"
    "|nan|nana|nanna|grandmother|grandfather|grandparent|grandparents|aunt|auntie|aunty|uncle|cousin|cousins|sister|sisters|brother|brothers"
    "|son|sons|daughter|daughters|wife|husband|partner|girlfriend|boyfriend|friend|friends|mate|mates|neighbour|neighbours|neighbor|neighbors"
    "|visitor|visitors|guest|guests|stranger|strangers|owner|family|folks"
)
SEEN_PEOPLE = words(
    "man|men|woman|women|lady|ladies|gentleman|gentlemen|guy|guys|boy|boys|girl|girls|kid|kids|child|children|baby|babies|person|people"
    "|teenager|teenagers|toddler|toddlers"
)
DET = words("the|a|an|this|that|these|those|your|his|her|their|our|my|some|every|each|another|both|all|any|no|whose|one|two|three")
PERSON = f"(?:{alt(YOU, HE_SHE, GROUP)}|(?:{alt(DET)} )?{alt(PEOPLE)}|{alt(DET)} people)"
ANYONE = f"(?:{PERSON}|{alt(THEY)})"
OWNER = f"(?:your|his|her|their|our|{PERSON} 's)"
MODAL = words("do|does|did|will|would|can|could|may|might|must|shall|should|not|to|ought to")
BE = words("am|is|are|was|were|be|been|being|'s")
ADV = words(
    "so|very|really|quite|rather|too|pretty|super|extra|totally|absolutely|completely|extremely|incredibly|awfully|terribly|a bit|a little"
    "|a little bit|a lot|kind of|sort of|kinda|sorta|just|still|always|never|not|also|all|both|even|now|already|definitely|probably|maybe"
    "|certainly|clearly|obviously|honestly|actually|seriously|literally|a|an|such a|such an|more|less|much|way|somewhat|slightly|fairly"
    "|most|as|bloody|real"
)
GAP = f"(?:{alt(MODAL, BE, ADV, words('have|has|had'))} )*"
LOOKS = words("look|looks|looked|looking")
LOOK_OK = words(
    "busy|ready|done|finished|comfy|comfortable|cosy|cozy|settled|hurt|injured|stuck|trapped|lost|confused|puzzled|hungry|thirsty|cold|chilly"
    "|freezing|frozen|warm|wet|soaked|drenched|okay|ok|alright|all right|in pain|in trouble|in danger|unsafe|safe|sure|certain"
)
NOT_LOOKS = words(
    "at|for|after|into|in|inside|outside|on|onto|around|round|about|over|under|up|down|out|through|back|forward|forwards|ahead|away|behind"
    "|here|there|everywhere|anywhere|somewhere|elsewhere|closely|carefully|properly|again|left|right|both|and|or|but|so|to|towards|toward|upon"
    "|where|what|how|when|why|who|which|if|whether|it|them|me|him|her|us|this|that|these|those|someone|something|anything|everything|across"
    "|past|along|beyond|first|twice|once|quickly|harder|closer|further|then|now"
)
APPEARANCE = words(
    "pretty|prettier|prettiest|beautiful|handsome|gorgeous|ugly|uglier|ugliest|hideous|cute|cuter|cutest|sexy|sexier|sexiest|attractive"
    "|unattractive|stunning|good-looking|nice-looking|ugly-looking|plain-looking|odd-looking|dressed up"
)
FIGURE = words(
    "fat|fatter|fattest|thin|thinner|thinnest|skinny|skinnier|skinniest|slim|slimmer|chubby|chubbier|overweight|underweight|obese|plump|podgy"
    "|pudgy|tubby|stocky|scrawny|bony|lanky|flabby|muscly|muscular|buff|curvy|bald|balding|hairy|wrinkly|wrinkled|spotty|freckly|pale|sunburnt"
    "|sunburned|tanned|pregnant|having a baby|expecting a baby|greying|graying"
)
SIZE = words("big|bigger|huge|small|smaller|tiny|tall|taller|tallest|short|shorter|shortest|heavy|heavier|grey|gray")
AGE = words("old|older|oldest|elderly|ancient|over the hill")
CONDITION = words(
    "depressed|anxious|stressed|stressed out|autistic|bipolar|manic|schizophrenic|psychotic|paranoid|neurotic|hysterical|obsessive|ocd|adhd"
    "|dyslexic|dyspraxic|diabetic|epileptic|asthmatic|anorexic|bulimic|suicidal|traumatised|traumatized|demented|senile|mentally ill|retarded"
    "|disabled|handicapped|crippled|lame|deaf|blind|paralysed|paralyzed|infertile|alcoholic|addicted|an addict|burnt out|burned out|burnt-out"
    "|burned-out|on the spectrum|limping"
)
SLANG = words("crazy|insane|nuts|psycho|loony|mental|bonkers")
ILLNESS = words(
    "depression|anxiety|autism|adhd|ocd|ptsd|bipolar|mania|schizophrenia|psychosis|paranoia|dementia|alzheimer's|alzheimers|parkinson's"
    "|parkinsons|dyslexia|dyspraxia|diabetes|epilepsy|asthma|anorexia|bulimia|eating disorder|cancer|tumour|tumor|hiv|addiction|alcoholism"
    "|insomnia|phobia|phobias|disorder|syndrome|disability|disabilities|illness|mental illness|disease|trauma|nervous breakdown|mental breakdown|burnout"
    "|panic attacks|panic attack|tourette's|tourettes|down syndrome|down's syndrome|heart condition|condition|lisp|stutter|bad breath|body odour"
    "|body odor|a limp"
)
MOODS = words(
    "tired|exhausted|sleepy|knackered|worn out|ill|sick|unwell|poorly|sad|upset|unhappy|miserable|angry|cross|grumpy|annoyed|worried|scared"
    "|frightened|nervous|happy|cheerful|bored|lonely|fed up"
)
WEAR_JUDGE = words(
    "nice|lovely|beautiful|pretty|gorgeous|handsome|cute|sexy|ugly|hideous|cool|great|amazing|awesome|perfect|awful|terrible|horrible|gross"
    "|disgusting|weird|funny|strange|odd|silly|ridiculous|stunning|fabulous|stylish|scruffy|untidy|messy|dreadful|attractive|unattractive|fab"
)
JUDGE = WEAR_JUDGE + words("good|bad|different|sweet|smart|mess")
EVAL = JUDGE + words(
    "big|bigger|huge|massive|enormous|giant|large|larger|small|smaller|tiny|long|longer|short|shorter|wide|narrow|round|flat|fat|fatter|thin"
    "|thinner|skinny|chubby|old|older|wrinkly|wrinkled|spotty|hairy|bald|greasy|oily|smooth|rough|frizzy|crooked|wonky|droopy|saggy|puffy"
    "|bloated|sunburnt|sunburned|tanned|shiny|smelly|stinky|sweaty|stained|lumpy|bumpy|flaky|patchy|blotchy|dull|lank|thinning|receding"
)
COLOUR = words("grey|gray|white|yellow|red|pink|brown|black|dark|darker|pale|paler|fair|blonde|blond|ginger|purple|blue|green|orange")
BODY = words(
    "body|skin|complexion|face|hair|beard|moustache|mustache|stubble|eyebrows|eyelashes|lashes|eyes|nose|ears|mouth|lips|teeth|tooth|smile|chin"
    "|chins|cheeks|jaw|neck|shoulders|arms|hands|fingers|nails|legs|knees|feet|toes|belly|tummy|stomach|waist|hips|bum|butt|bottom|chest|breasts"
    "|boobs|thighs|muscles|wrinkles|spots|pimples|acne|freckles|moles|scars|weight|figure|shape|appearance|breath|physique|head|fringe|curls"
)
COLOURED = words("skin|complexion|face|hair|beard|moustache|mustache|eyebrows|eyes|nose|lips|teeth|cheeks|fringe|curls")
WEAR = words(
    "clothes|outfit|dress|shirt|top|jumper|sweater|jacket|coat|jeans|trousers|pants|skirt|shorts|shoes|boots|hat|glasses|tie|suit|scarf|uniform"
    "|costume|pyjamas|pajamas|socks|earrings|necklace|jewellery|jewelry"
)
STYLE = words(
    "haircut|hairdo|hairstyle|makeover|perm|highlights|tattoo|tattoos|piercing|piercings|makeup|make-up|lipstick|mascara|nose job|botox|new look"
)
ALWAYS = STYLE + words("weight|figure|appearance|complexion|physique|wrinkles|pimples|acne|boobs|breasts|bum|butt|double chin|bald patch")
PEOPLE_ONLY = words(
    "haircut|hairstyle|hairdo|hair|beard|moustache|mustache|makeup|make-up|lipstick|outfit|tattoo|tattoos|piercing|piercings|complexion|skin"
    "|wrinkles|freckles|pimples|acne|physique|muscles|belly|tummy|bum|butt|breasts|boobs|thighs|hips|waist|eyebrows|eyelashes|lashes|curls"
)
BY_LOOKS = APPEARANCE + words(
    "fat|fatter|fattest|thin|thinner|thinnest|skinny|skinniest|chubby|overweight|obese|tall|taller|tallest|short|shorter|shortest|bald|hairy"
    "|wrinkly|old|older|oldest|elderly|pregnant|plump|tubby|scrawny|lanky"
)
FOLLOWS = words(
    "and|but|or|now|today|tonight|lately|nowadays|these|already|again|than|in|with|like|as|too|still|though|anyway|yet|compared|then|you|for"
    "|when|if|because|i|it|that|my|your|she|he|we|they|there|here|is"
)
SENSE = BE + words(
    "seem|seems|seemed|seeming|sound|sounds|sounded|sounding|appear|appears|appeared|appearing|feel|feels|felt|feeling|look|looks|looked|looking"
    "|get|gets|got|getting|become|becomes|became|becoming|act|acts|acted|acting|go|goes|going|gone|went|turn|turns|turned|turning"
)
HAVE = words("have|has|had|having|got|gotten|have got|has got|'s got|had got")
LIVES_WITH = words(
    "suffers from|suffer from|suffered from|suffering from|lives with|live with|living with|diagnosed with|struggles with|struggle with"
    "|struggling with|battling|fighting"
)
STINK = words("smell|smells|smelled|smelt|smelling|stink|stinks|stank|stunk|stinking|reek|reeks|reeked|pong|pongs")
SMELLS_OF = words(
    "smoke|gas|burning|something|anything|that|this|it|food|dinner|toast|fire|the|a|an|those|these|them|what|if|whether|any|some|cooking|coffee"
    "|flowers|rain|fumes|for|around"
)
CHANGES = words("put|putting|puts|gained|gaining|gains|gain|lost|losing|loses|lose|piled|piling|pile")
UNITS = words("weight|pounds|kilos|kilograms|kg|kgs|lbs|stone|stones")
GROWN = words("bigger|fatter|thinner|skinnier|slimmer|chubbier|taller|shorter|older|heavier|greyer|grayer|balder|wrinklier|smaller")
FONDNESS = words("like|love|loves|adore|adores|admire|admires|hate|hates|envy|envies|fancy|fancies")
STYLED = words("dyed|dye|dyes|cut|cuts|shaved|shave|shaves|coloured|colored|bleached|permed|straightened|curled|trimmed")
GROOMED = words("hair|beard|legs|moustache|mustache|fringe|eyebrows")
EXCLAIM = words("ooh|oh|wow|aw|aww|hi|hello|hey|what|such|a|an|really|so|very|that|this|those|these|is|are|'s|someone|,")
ELLIPSIS = words("feeling|looking|seeming|sounding|getting|a|bit|little|so|very|really|quite|rather|kind|of|sort|too|still")
CHANGING = words("getting|becoming|growing|going|gone|turning|being|been|the")
PREDICATE = f"(?!short for ){alt(APPEARANCE, FIGURE, SIZE, AGE)} (?!(?:enough|of|on|to|about) )(?=[,.!?;:] |{alt(FOLLOWS)} )"
NOT_A_LOOK = f"(?!(?:{alt(ADV)} )*+{alt(LOOK_OK, NOT_LOOKS)} )(?=[a-z0-9])"
ONE = "(?:[a-z'-]+ )?"
AND_ONE = f"(?:[a-z'-]+ (?:and|,) (?:{alt(ADV)} )*)?"
HAD = words("have|has|had|'s")
SMART = words("good|great|well|fine|lovely|nice|sharp|smart|fab|fabulous|amazing|rough|awful|terrible|different|younger|young|radiant|glowing")
FEATURES = alt(ADV, EVAL, COLOUR, words("the|some|such|lots of|two|and|,"))

RULES = tuple(
    re.compile(rule)
    for rule in (
        rf"\b{PERSON} {GAP}{alt(LOOKS)} {NOT_A_LOOK}",
        rf"\b{alt(THEY)} {GAP}{alt(LOOKS)} (?:{alt(ADV)} )*{alt(APPEARANCE, FIGURE, CONDITION, MOODS)} ",
        rf"\b{PERSON} {GAP}{alt(BE)} (?:{alt(ADV, CHANGING)} )*{AND_ONE}{PREDICATE}",
        rf"\b{alt(BE)} {PERSON} (?:{alt(ADV, CHANGING)} )*{AND_ONE}{PREDICATE}",
        rf"\b{alt(THEY)} {GAP}{alt(BE)} (?:{alt(ADV, CHANGING)} )*{alt(APPEARANCE, FIGURE)} ",
        rf"\b{ANYONE} {GAP}{alt(SENSE)} (?:{alt(ADV, words('the|clinically|properly'))} )*{alt(CONDITION)} (?!to )",
        rf"\b{ANYONE} {GAP}{alt(SENSE)} (?:{alt(ADV)} )*{alt(SLANG)} (?!about )",
        rf"\b{alt(BE, words('do|does|did|have|has'))} {ANYONE} (?:{alt(ADV, SENSE, HAVE, words('get|getting'))} )*{alt(CONDITION, ILLNESS)} ",
        rf"(?:^|[.!?] )(?:{alt(ELLIPSIS)} )+{alt(CONDITION)} [^.!?]*\? ",
        rf"\b{ANYONE} {GAP}{alt(HAVE, LIVES_WITH)} (?:{alt(ADV, words('the|some|bad|severe|mild|real|clinical|serious|terrible|early|stage|a touch of'))} )*{alt(ILLNESS)} ",
        rf"\b{OWNER} {ONE}{alt(ILLNESS)} ",
        rf"\b{PERSON} (?:{alt(MODAL, ADV)} )*{alt(HAVE)} (?:{FEATURES} )*{alt(EVAL, COLOUR)} (?:{FEATURES} )*{alt(BODY)} ",
        rf"\b{PERSON} {GAP}{alt(HAVE, words('get|gets|getting|got|gotten|done|wearing|wears|wore|wear|put on'))} (?:{alt(ADV, words('your|her|his|their|the|some|new'))} )*{alt(STYLE)} ",
        rf"\b{PERSON} {GAP}{alt(STYLED)} (?:(?:your|her|his|their|my) )?{alt(GROOMED)} ",
        rf"\b{OWNER} (?:{alt(ADV, words('and|,'))} )*{alt(EVAL)} (?:{alt(EVAL, ADV, words('and|,'))} )*{alt(BODY)} ",
        rf"\b{OWNER} (?:{alt(ADV, words('and|,'))} )*{alt(WEAR_JUDGE)} (?:{alt(WEAR_JUDGE, ADV, words('and|,|new'))} )*{alt(WEAR)} ",
        rf"\b{OWNER} (?:{alt(ADV, EVAL, words('and|,'))} )*{alt(COLOUR)} (?:{alt(EVAL, COLOUR, words('and'))} )*{alt(COLOURED)} ",
        rf"\b{OWNER} {ONE}{alt(BODY)} {GAP}{alt(SENSE)} (?:{alt(ADV, words('getting|going|gone|turning'))} )*{AND_ONE}{alt(EVAL, COLOUR, APPEARANCE, FIGURE, SIZE, AGE)} ",
        rf"\b{OWNER} {ONE}{alt(BODY, STYLE)} {GAP}{alt(LOOKS)} {NOT_A_LOOK}",
        rf"\b{OWNER} {ONE}{alt(WEAR)} {GAP}{alt(SENSE)} (?:{alt(ADV)} )*{alt(WEAR_JUDGE)} ",
        rf"\b{OWNER} {ONE}{alt(BODY)} {GAP}{alt(STINK)} ",
        rf"\b{OWNER} {ONE}{alt(ALWAYS)} ",
        rf"\b{OWNER} (?:{alt(EVAL)} )?looks ",
        rf"(?:^|[.!?] )(?:you )?(?:are )?looking (?:{alt(ADV)} )*{alt(APPEARANCE, FIGURE, AGE, MOODS, SMART)} ",
        rf"\b{alt(BODY, WEAR, STYLE, words('colour|color|look'))} (?:(?:really|so|very|just|totally) )*suits? {PERSON} ",
        rf"\b{alt(LOOKS)} (?:{alt(ADV)} )*{alt(JUDGE)} on {PERSON} ",
        rf"(?<!\byou )\b{alt(FONDNESS)} {OWNER} {ONE}{alt(BODY, WEAR, STYLE, ALWAYS)} ",
        rf"(?:^|[.!?] )(?:{alt(EXCLAIM)} )*{alt(EVAL)} (?:{alt(EVAL, words('and|,|new'))} )*{alt(PEOPLE_ONLY)} ",
        rf"(?:^|[.!?] )(?:{alt(EXCLAIM)} )*{alt(WEAR_JUDGE)} (?:{alt(WEAR_JUDGE, words('and|new'))} )*{alt(WEAR)} (?=[,.!?;:] |today |tonight |on you )",
        rf"(?<!\byear )(?<!\byears )(?<!\bmonth )(?<!\bmonths )\b{alt(BY_LOOKS)} (?:{alt(ADV, BY_LOOKS, words('and|,'))} )*{alt(SEEN_PEOPLE)} ",
        rf"\b{ANYONE} {GAP}{alt(CHANGES)} (?:on )?(?:(?:{alt(ADV, words('some|any|the|lots|of|lot|so|much|more|few|two|three|four|five|ten'))}|\d+) )*{alt(UNITS)} ",
        rf"\b{PERSON} {GAP}{alt(words('grown|grew|got|gotten|getting|growing|become|became|becoming'))} (?:{alt(ADV)} )*{alt(GROWN)} ",
        rf"\b{PERSON} (?:{alt(MODAL, ADV)} )*{alt(HAD)} (?:{alt(ADV)} )*grown (?!(?:up|fond|used|tired|to|into|closer|apart) )",
        rf"\b{PERSON} {GAP}{alt(STINK)} (?!(?:{alt(ADV)} )*+{alt(SMELLS_OF)} )",
    )
)


MEDICINE = words(
    "medicine|medicines|medication|medications|meds|pill|pills|tablet|tablets|insulin|inhaler|injection|injections|prescription|prescriptions|dose"
    "|doctor|doctors|gp|dentist|clinic|hospital|surgery|therapy|therapist|counsellor|counselor|psychologist|psychiatrist|blood test|blood pressure"
    "|scan|smear|vaccine|vaccination|jab|contraceptive|contraception|antidepressant|antidepressants|period|pregnancy test|test results|physio"
)
MONEY = words(
    "money|bank|bills|debt|debts|loan|loans|mortgage|rent|overdraft|credit card|tax|taxes|invoice|invoices|salary|wages|pay rise|payday|benefit"
    "|benefits|budget|savings|pin|password|passwords|lawyer|court"
)
PRIVATE_MATTER = re.compile(r"\b" + alt(MEDICINE, MONEY, ILLNESS, CONDITION) + r"\b")


def _named(raw: str, word: str, before: list[str]) -> bool:
    if len(raw) < 2 or not raw[0].isupper() or not any(c.islower() for c in raw[1:]):
        return False
    if word in NOT_NAMES or word in OWN or word in PEOPLE or word in THEY or (len(word) > 5 and word.endswith("ing")):
        return False
    return not before or before[-1] not in NOT_NAME_AFTER


def plain(text: str) -> str:
    out: list[str] = []
    for raw in TOKEN.findall((text or "").replace("’", "'").replace("‘", "'")):
        if raw in ".,!?;:":
            out.append(raw)
            continue
        word = raw.lower()
        if word in WHOLE:
            out.extend(WHOLE[word])
            continue
        tail = ""
        for ending, instead in ENDINGS:
            if word.endswith(ending) and len(word) > len(ending):
                word, tail, raw = word[: -len(ending)], instead, raw[: -len(ending)]
                break
        if word in OWN:
            word = "i"
        elif _named(raw, word, out):
            word = "someone"
        out.append(word)
        if tail:
            out.append(tail)
    return " ".join(out + ["."]) + " "


def tactless(text: str) -> bool:
    spoken = plain(text)
    return any(rule.search(spoken) for rule in RULES)


def sentences(text: str) -> list[str]:
    return [piece.strip() for piece in SENTENCE.split((text or "").strip()) if piece.strip()]


class TactfulVoice:
    def __init__(self, voice: Voice, record: Callable[..., None] | None = None):
        self.voice = voice
        self.record = record or (lambda kind, **data: None)

    def __getattr__(self, name: str):
        found = getattr(self.voice, name)
        if name != "say_part":
            return found

        def say_part(part_id: str, text: str, last: bool = True, whisper: bool = False) -> bool:
            return self.allows(text) and bool(found(part_id, text, last, whisper))

        return say_part

    def allows(self, text: str) -> bool:
        why = "looks" if tactless(text) else ("life" if cruel(text) else "")
        if not why:
            return True
        try:
            self.record("held_back", why=why)
        except Exception:
            pass
        return False

    async def say(self, text: str, whisper: bool = False) -> SpeechResult:
        pieces = sentences(text)
        kept = [piece for piece in pieces if self.allows(piece)]
        if len(kept) == len(pieces):
            return await self.voice.say(text, whisper)
        if not kept:
            return SpeechResult(False, "held back")
        return await self.voice.say(" ".join(kept), whisper)


def private_matter(text: str) -> bool:
    return bool(PRIVATE_MATTER.search(" ".join((text or "").lower().replace("’", "'").split())))
