import re
from dataclasses import dataclass
from functools import lru_cache

SMALL, ANIMAL, PLANT, PERSON, ME, IT = "small", "animal", "plant", "person", "me", "it"


def _words(text: str) -> tuple[str, ...]:
    return tuple(word.strip() for word in text.split("|") if word.strip())


FLIERS = _words(
    "fly|housefly|blowfly|bluebottle|fruit fly|mozzie|mossie|mosquito|midge|gnat|sandfly|moth|butterfly|swallowtail butterfly|ladybird|ladybug"
    "|bee|bumblebee|honeybee|honey bee|wasp|hornet|dragonfly|damselfly|cicada"
)
CRAWLERS = _words(
    "insect|bug|beetle|spider|garden spider|daddy long legs|huntsman|redback|white tail|whitetail|cockroach|roach|cricket|grasshopper|locust"
    "|weta|earwig|centipede|millipede|woodlouse|slater|pill bug|silverfish|flea|tick|mite|louse|stick insect|praying mantis|mantis|scorpion"
    "|huhu|huhu beetle|huhu bug|gogga|critter|creepy crawly|beastie|small moving thing"
)
SLOW = _words("snail|slug|worm|earthworm|caterpillar|grub|maggot|larva")
COLONIES = _words("ant|termite|aphid")
SMALL_WORDS = FLIERS + CRAWLERS + SLOW + COLONIES
ANIMAL_WORDS = _words(
    "animal|creature|pet|cat|kitten|kitty|puss|pussy cat|pussycat|moggy|moggie|dog|puppy|pup|doggy|doggie|doggo|pooch|bird|birdie|chick"
    "|chicken|chook|hen|rooster|duck|duckling|goose|pigeon|sparrow|blackbird|starling|myna|magpie|tui|fantail|piwakawaka|kereru|seagull|gull"
    "|water bird|parrot|budgie|cockatoo|canary|owl|barn owl|rabbit|bunny|hare|hamster|guinea pig|mouse|rat|possum|hedgehog|ferret|stoat|frog"
    "|tree frog|toad|tadpole|lizard|gecko|skink|snake|tortoise|turtle|fish|goldfish|aquarium fish|horse|pony|cow|calf|sheep|lamb|goat|pig"
    "|piglet|deer|monkey|squirrel|bat|axolotl|meerkat|dassie|mongoose|baby bird|baby animal"
)
PLANT_WORDS = _words(
    "plant|pot plant|potted plant|houseplant|house plant|plant pot|flower pot|flowerpot|spider plant|snake plant|rubber plant|money tree"
    "|peace lily|fiddle leaf fig|tomato plant|pitcher plant|flower|hibiscus flower|flower box|flower basket|bouquet|rose|chinese rose|tulip"
    "|daisy|lily|water lily|orchid|sunflower|daffodil|carnation|pansy|geranium|hibiscus|azalea|succulent|cactus|fern|bonsai|herb|seedling"
    "|sprout|sapling|tree|palm tree|fruit tree|apple tree|bush|shrub|hedge|vine|ivy|moss|weed|flower bed|flowerbed|vegetable garden"
    "|veggie garden|veggie patch|monstera|pothos|philodendron|aloe|aloe vera|lavender|bamboo"
)
NOT_LIFE = _words(
    "cat tree|cat food|dog food|cat bowl|dog bowl|dog bed|cat bed|cat flap|cat door|dog door|fish tank|fish food|fish finger|fish fingers"
    "|fish and chips|bird cage|birdcage|bird feeder|bird bath|birdbath|bird seed|spider web|spider webs|cobweb|rose gold|rose water"
    "|fly spray|bug spray|insect spray|plant food|tree house|christmas tree|family tree|shoe tree|tree trunk|tree branch|tree root|teddy bear"
    "|toy dog|toy cat|toy mouse|stuffed animal|stuffed toy|soft toy|computer mouse|mouse pad|mousepad|mouse trap|mousetrap|hot dog|corn dog"
    "|chicken nugget|chicken nuggets|chicken wing|chicken wings|chicken soup|roast chicken|lamb chop|lamb chops|pet food|ant trap|rat trap"
    "|bee hive|beehive|butterfly clip|bat signal|cricket bat|cricket ball|animal sculpture|plastic plant|fake plant|fake flowers|paper flower"
    "|bunny ears|duck tape|duct tape|pig out|toy snake|toy spider|rubber spider|plastic spider|fake spider|halloween spider|spider man|spiderman"
    "|batman|cat woman|catwoman|bug bear|bugbear|toy fish|toy bird|toy horse|rocking horse|clothes horse|fire ant hill|ant hill|anthill"
)
PEOPLE_WORDS = _words(
    "person|people|baby|toddler|kid|child|boy|girl|man|woman|lady|guy|mum|dad|brother|sister|son|daughter|grandma"
    "|grandpa|granny|gran|nana|nan|grandad|granddad|ouma|oupa|uncle|aunt|auntie|aunty|cousin|wife|husband|partner|boyfriend|girlfriend"
    "|friend|mate|neighbour|neighbor|visitor|guest|stranger|postie|postman|courier|burglar|intruder|thief|teacher|someone|somebody|anyone"
    "|anybody|everyone|everybody|human|little brother|little sister|big brother|big sister|baby brother|baby sister"
)
BODY = frozenset(_words("foot|feet|toe|toes|finger|fingers|hand|hands|leg|legs|arm|arms|head|nose|ear|ears|tail|paw|paws|wing|wings|face|whiskers|fur|hair|feathers|shell|leaves|petals|roots|stem"))
PULLED = ("tail", "ears", "ear", "wings", "wing", "legs", "leg", "whiskers", "fur", "hair", "feathers", "leaves", "petals")
THING_PRONOUNS = frozenset(_words("it|that|this|those|these"))
SOFTENERS = frozenset(_words("good|real|proper|big|little|quick|wee|solid|massive|huge|serious"))
HYPOTHETICAL = re.compile(r"\bif (?:i|we|someone|somebody|anyone|they|he|she|mum|dad|your owner) (?:asked|told you|said so|wanted you to|begged|ordered you)\b")
HOMES = {
    ("fish", "tank"): ("fish", ANIMAL, True), ("fishtank",): ("fish", ANIMAL, True), ("fish", "bowl"): ("fish", ANIMAL, True), ("fishbowl",): ("fish", ANIMAL, True),
    ("aquarium",): ("fish", ANIMAL, True), ("bird", "cage"): ("bird", ANIMAL, False), ("birdcage",): ("bird", ANIMAL, False), ("hamster", "cage"): ("hamster", ANIMAL, False),
    ("rabbit", "hutch"): ("rabbit", ANIMAL, False), ("guinea", "pig", "hutch"): ("guinea pig", ANIMAL, False), ("ant", "farm"): ("ant", SMALL, True),
    ("ant", "hill"): ("ant", SMALL, True), ("anthill",): ("ant", SMALL, True), ("ants", "nest"): ("ant", SMALL, True), ("ant", "nest"): ("ant", SMALL, True),
    ("bee", "hive"): ("bee", SMALL, True), ("beehive",): ("bee", SMALL, True), ("wasp", "nest"): ("wasp", SMALL, True), ("wasps", "nest"): ("wasp", SMALL, True),
    ("bird", "nest"): ("bird", ANIMAL, True), ("birds", "nest"): ("bird", ANIMAL, True),
}
HOLDERS = frozenset(_words("vase|pot|tub|tray|bed|bunch|bowl|tank|jar|box|nest|cage|basket|bucket|punnet|planter|bouquet|hutch|colony|swarm|flock|litter|family"))
QUESTION_WORDS = frozenset(_words("why|how|what|when|where|who|which|whose|does|do|did|is|are|was|were|has|have|had|can|could|should|would|will"))
QUANTITY = frozenset(_words("lots|couple|bunch|load|loads|pair|all|some|any|few|each|one|two|three|family|nest|colony|both|none|most|whole|lot"))
DETS = frozenset(_words(
    "the|a|an|that|this|those|these|my|your|his|her|their|our|its|some|any|all|every|each|another|one|two|three|few|couple|lots|such"
    "|both|whole|lot|bunch|load|loads|pair|family|nest|colony|poor|dear"
))
ADJS = frozenset(_words(
    "little|big|tiny|huge|giant|massive|small|stupid|silly|ugly|old|young|wee|fat|hairy|creepy|scary|annoying|nasty|horrible|bloody"
    "|flipping|freaking|damn|dang|darn|effing|fluffy|cute|black|brown|white|grey|gray|red|green|yellow|orange|mean|naughty|bad|dumb|gross"
    "|disgusting|filthy|dirty|sneaky|cheeky|noisy|loud|slimy|horrid|stray|wild|pet|new|other|last|first|second|blasted|bleeding|lil|mama"
    "|house|kitchen|lounge|garden|neighbours|neighbors|sad|lonely|sick|live|living|real|same|very|pesky|darned|ol|blimmin|bloomin|flippen"
    "|bladdy|blerrie|mangy|scrawny|skinny|next|door|darling|precious|beautiful|lovely|pretty|favourite|favorite|prize|precious|potted"
))
FILLERS = frozenset(_words(
    "ok|oh|hey|hi|um|uh|er|erm|well|so|right|alright|yeah|yes|yep|no|nah|nope|just|quick|quickly|now|please|mate|bro|boet|bru|eh|aye|oi"
    "|hurry|then|again|already|really|ag|ja|nee|man|buddy|dude|kiddo|idiom|look|listen|honey|love|sweetie|darling|lad|boy|girl|wait|whoa"
))
TWO_FILLERS = frozenset(_words("go on|come on|right now|chop chop|my friend|little guy|hurry up|look here|oh my|my god|oh god|ok so|for me"))
JOKING = re.compile(r"\b(haha+|ha ha|hehe+|lol|lmao|rofl|jk|just kidding|only kidding|kidding|joking|only joking|just joking|for a laugh|for fun)\b")
CORRECTION = re.compile(r"\b(?:no wait|wait no|no no|actually|i mean|scratch that|or rather|on second thoughts?|never mind that|no sorry|sorry no|forget that|change of plan)\b")
ACCIDENT = re.compile(r"\b(by accident|accidentally|did not mean|never meant|may have|might have|could have|nearly|almost|i think i|sorry|oops|whoops|without meaning)\b")
LAUGH = re.compile(r"\b(haha+|ha ha|hehe+|lol|lmao|rofl|hilarious|so funny|funny|lekker)\b")
NEAR_NOT = frozenset(_words("not|never|no|nor|neither|dont"))
ANYWHERE_NOT = frozenset(_words("stop|quit|without|avoid|prevent|instead|careful|beware|refuse|stopped|stopping|mind"))
ASKING_ABOUT = (
    "did you", "have you", "do you", "does it", "were you", "had you", "are you going to", "are you gonna", "would you ever", "will you ever",
    "have you ever", "did you ever", "do you ever", "is it ok to", "is it okay to", "is it alright to", "is it bad to", "is it wrong to",
    "why do people", "why did", "how do you", "how did", "what happens if", "do people", "what if i", "would it hurt", "does it hurt to",
    "can i", "should i", "may i", "could i", "am i allowed to", "would you mind if i", "is it cruel to", "is it mean to", "why would",
    "how come", "do you think i should", "would you rather", "are you allowed to", "are you able to", "can you even",
)
INVITES = re.compile(r"^(?:do you want to|would you like to|do you fancy|you fancy|fancy|you want to|want to|shall we|should we|can we|could we|will we|how about we|you wanna|do you wanna|do you mind|would you mind|will you mind|if you do not mind)\b")
YOU_LEADS = re.compile(
    r"\b(?:can you|could you|would you|will you|you should|you could|you can|you need to|you have to|you must|you better|you had better|"
    r"can not you|could not you|will not you|would not you|want you to|need you to|like you to|love you to|love it if you|dare you to|bet you|told you to|asked you to|wants you to|"
    r"says you|said you|if you|imagine you|imagine if you|wish you|why do not you|why not|how about you|you might as well|you got to|you have got to|"
    r"you are supposed to|you are allowed to|your (?:job|task|mission|work|chore)(?: [a-z]+)? is(?: to)?|you are meant to|you ought to|go and|come and|help me|let us|lets|time to|"
    r"how about|be a dear and|be a love and|do me a favour and|do us a favour and|make sure you|make sure to|remember to|try to|try and|"
    r"go ahead and|go on and|i order you to|i command you to|i am telling you to|we should|we could|we need to|we have to|we must|we got to|"
    r"we will|we are going to|(?:someone|somebody|anyone|anybody) (?:should|needs to|has to|ought to|could|must|better|go)|"
    r"be (?:so |really |pretty |super )?(?:fun|funny|cool|hilarious|great|awesome|lekker|a laugh) (?:to|if you))\b"
)
SUBJECT_STARTS = frozenset(_words(
    "i|he|she|they|it|someone|somebody|everyone|everybody|nobody|people|the|my|our|his|her|their|a|an|this|that|these|those|there|we|mum"
    "|dad|what|who|where|when|which|whose|is|are|was|were|has|had|does|did"
))
REQUEST_STARTS = frozenset(_words(
    "go|come|just|please|quick|quickly|now|keep|start|try|help|time|let|remember|also|maybe|perhaps|kindly|gently|seriously"
    "|definitely|honestly|hurry|then|and|right|pebble|ok|alright|run|get|use|be|make"
))
GENTLE_ON_ME = frozenset(_words("bump|push|poke|prod|flick|pinch|squeeze|tease|annoy|chase|scare|frighten|spook|startle|give|sneak|jump|tickle|sit|stand|throw|chuck|toss"))


@dataclass(frozen=True)
class Verb:
    words: tuple
    how: str
    strong: bool
    kinds: str
    parts: tuple = ()


def _verb(pattern: str, how: str, strong: bool = False, kinds: str = "saph", parts: tuple = ()) -> Verb:
    return Verb(tuple(pattern.split()), how, strong, kinds, parts)


VERBS = (
    *(_verb(f"{v} T", "hurt", True) for v in _words(
        "kill|murder|slaughter|squash|squish|smoosh|squoosh|splat|exterminate|drown|poison|torture|strangle|choke|suffocate|electrocute"
        "|stab|maim|injure|hurt|harm|wound|abuse|torment|bully|terrorise|terrorize|attack|maul|stomp|trample|klap|moer|donner|bliksem|skop|skiet"
    )),
    *(_verb(f"{v} on T", "hurt", True) for v in _words("stomp|stamp|step|tread|trample")),
    *(_verb(f"{v} on T", "hurt", False) for v in _words("jump|stand|sit|roll")),
    _verb("swat T", "hurt", True, "sa"),
    *(_verb(f"{v} T", "hurt", False, "sa") for v in _words("eliminate|zap|salt|spray|flush|biff|lob")),
    _verb("sic T", "chase", True, "sah"),
    *(_verb(f"{v} T", "hurt", False) for v in _words("hit|punch|kick|slap|smack|whack|thump|wallop|belt|clobber|bash|boot|shoot|burn|scald|bite|push|shove|pinch|poke|prod|flick|squeeze|throw|chuck|toss|fling|hurl")),
    *(_verb(f"{v} T", "hurt", False, "sap") for v in _words("crush|flatten|smash|mash|mince|destroy|wreck|ruin|trash|munt|boil|freeze|microwave")),
    _verb("beat up T", "hurt", True), _verb("beat T up", "hurt", True),
    _verb("wipe out T", "hurt", True, "sap"), _verb("wipe T out", "hurt", True, "sap"),
    _verb("get rid of T", "hurt", False, "sa"),
    _verb("deal to T", "hurt", False, "sa"),
    _verb("sort out T", "hurt", False, "sa"), _verb("sort T out", "hurt", False, "sa"),
    _verb("finish off T", "hurt", True, "sa"), _verb("finish T off", "hurt", True, "sa"),
    _verb("pour salt on T", "hurt", True, "sa"), _verb("put salt on T", "hurt", True, "sa"), _verb("sprinkle salt on T", "hurt", True, "sa"),
    _verb("pour boiling water on T", "hurt", True), _verb("pour hot water on T", "hurt", True),
    _verb("pull T", "hurt", True, "saph", PULLED), _verb("yank T", "hurt", True, "saph", PULLED), _verb("tug T", "hurt", False, "sa", PULLED),
    _verb("pull the wings off T", "hurt", True, "sa"), _verb("pull the legs off T", "hurt", True, "sa"),
    _verb("pull the petals off T", "hurt", True, "p"), _verb("pull the leaves off T", "hurt", True, "p"),
    _verb("pull the tail of T", "hurt", True, "sa"),
    *(_verb(f"{v} T", "hurt", False, "p") for v in _words("uproot|snap|break")),
    *(_verb(f"{v} {p} T", "hurt", False, "p") for v in _words("pull|rip|tear|dig|cut|chop") for p in _words("up|out|down")),
    *(_verb(f"{v} T {p}", "hurt", False, "p") for v in _words("pull|rip|tear|dig|cut|chop") for p in _words("up|out|down")),
    _verb("set fire to T", "hurt", True), _verb("set T on fire", "hurt", True), _verb("light T on fire", "hurt", True),
    *(_verb(f"put T in the {place}", "hurt", True, "sa") for place in _words("microwave|oven|freezer|fridge|toilet|bin|blender|washing machine|dryer|rubbish")),
    _verb("feed T to", "hurt", True, "sa"),
    *(_verb(f"{v} the {animal} on T", "hurt", True) for v in _words("sic|sick|set") for animal in _words("dog|cat|dogs|cats")),
    _verb("set a trap for T", "hurt", True, "sa"), _verb("put poison down for T", "hurt", True, "sa"), _verb("lay poison for T", "hurt", True, "sa"),
    _verb("put out poison for T", "hurt", True, "sa"), _verb("lay bait for T", "hurt", True, "sa"),
    *(_verb(f"give T a {blow}", "hurt", True) for blow in _words("hiding|beating|good hiding|snot klap|klap|thrashing|smack down")),
    *(_verb(f"give T a {blow}", "hurt", False) for blow in _words("kick|smack|whack|thump|slap|punch|kicking|boot|bash|clip|knock|shove|zap|squish|squash|good kick|good smack|swat")),
    *(_verb(f"make T {end}", "hurt", True) for end in _words("die|dead|vrek|suffer|cry|scream|bleed|squeal|yelp")),
    *(_verb(f"{v} T", "chase", False, "sa") for v in _words("chase|hunt|pursue|stalk|corner|harass|pester|torment")),
    *(_verb(f"{v} {p} T", "chase", False, "sa") for v in _words("chase|hunt") for p in _words("after|off|away|out|down|around")),
    *(_verb(f"{v} T {p}", "chase", False, "sa") for v in _words("chase|hunt") for p in _words("off|away|out|down|around")),
    _verb("run after T", "chase", False, "sa"), _verb("run at T", "chase", False, "sa"),
    _verb("harass T", "chase", False, "h"),
    *(_verb(f"{v} T", "chase", False, "a") for v in _words("tease|annoy")),
    *(_verb(f"{v} T", "scare", True, "sah") for v in _words("scare|frighten|spook|startle|terrify|petrify")),
    *(_verb(f"{v} {p} T", "scare", True, "sah") for v in _words("scare|frighten") for p in _words("off|away|out")),
    *(_verb(f"{v} T {p}", "scare", True, "sah") for v in _words("scare|frighten") for p in _words("off|away|out")),
    *(_verb(f"give T a {jolt}", "scare", True, "sah") for jolt in _words("fright|scare|shock|big fright")),
    _verb("make T jump", "scare", False, "sah"),
    _verb("scare the life out of T", "scare", True, "sah"),
    _verb("jump out at T", "scare", False, "sah"),
    _verb("sneak up on T", "scare", False, "sa"),
    *(_verb(f"{v} over T", "drive", True) for v in _words("run|drive|reverse|back|mow")),
    _verb("run T over", "drive", True),
    _verb("run T down", "drive", False), _verb("run down T", "drive", False), _verb("mow down T", "drive", True), _verb("mow T down", "drive", True),
    *(_verb(f"{v} over T", "drive", False) for v in _words("ride|roll|go|knock|push|tip|bowl|trip")),
    *(_verb(f"{v} T over", "drive", False) for v in _words("knock|push|tip|bowl")),
    _verb("knock down T", "drive", False), _verb("knock T down", "drive", False), _verb("topple T", "drive", False),
    *(_verb(f"{v} into T", "drive", False) for v in _words("crash|smash|ram|slam|barge|plough|plow|drive|charge|bang|bump")),
    *(_verb(f"{v} at T", "drive", False) for v in _words("drive|charge")),
    _verb("drive straight at T", "drive", True),
    _verb("ram T", "drive", False), _verb("charge T", "drive", False, "a"),
    _verb("trip T", "hurt", True, "h"), _verb("trip T up", "hurt", True, "h"), _verb("trip up T", "hurt", True, "h"),
)
IRREGULAR = {
    "run": ("ran",), "hit": ("hit",), "beat": ("beat", "beaten"), "bite": ("bit", "bitten"), "throw": ("threw", "thrown"),
    "tread": ("trod", "trodden"), "stand": ("stood",), "sit": ("sat",), "drive": ("drove", "driven"), "ride": ("rode", "ridden"), "shoot": ("shot",),
    "give": ("gave", "given"), "make": ("made",), "set": ("set",), "tear": ("tore", "torn"), "break": ("broke", "broken"), "cut": ("cut",),
    "dig": ("dug",), "put": ("put",), "fling": ("flung",), "hurt": ("hurt",), "light": ("lit", "lighted"), "freeze": ("froze", "frozen"),
    "go": ("went", "gone"), "feed": ("fed",), "get": ("got", "gotten"), "sneak": ("snuck", "sneaked"), "mow": ("mowed", "mown"),
    "deal": ("dealt",), "lay": ("laid",), "wipe": ("wiped",), "pour": ("poured",), "sprinkle": ("sprinkled",), "spray": ("sprayed",),
}
DOUBLE = frozenset(_words("swat|zap|snap|trap|stab|trip|step|chop|slap|drop|prod|splat|skop|klap|rip|ram|slam|run|hit|sit|set|cut|dig|put|lob|bob|tug|stun|mob"))


def _forms(word: str) -> dict:
    if word.endswith("e") and not word.endswith("ee"):
        ing, past = word[:-1] + "ing", word + "d"
    elif word.endswith("y") and len(word) > 2 and word[-2] not in "aeiou":
        ing, past = word + "ing", word[:-1] + "ied"
    elif word in DOUBLE:
        ing, past = word + word[-1] + "ing", word + word[-1] + "ed"
    else:
        ing, past = word + "ing", word + "ed"
    if word.endswith("y") and len(word) > 2 and word[-2] not in "aeiou":
        third = word[:-1] + "ies"
    else:
        third = word + ("es" if word.endswith(("s", "sh", "ch", "x", "z", "o")) else "s")
    out = {word: "now", third: "now", ing: "ing"}
    for form in IRREGULAR.get(word, (past,)):
        out.setdefault(form, "past")
    return out


FORMS: dict[str, list] = {}
for _v in sorted(VERBS, key=lambda verb: -len(verb.words)):
    for _form, _tense in _forms(_v.words[0]).items():
        FORMS.setdefault(_form, []).append((_v, _tense))


def _plural(word: str) -> str:
    irregular = {"mouse": "mice", "louse": "lice", "woodlouse": "woodlice", "larva": "larvae", "cactus": "cacti", "goose": "geese", "sheep": "sheep",
                 "fish": "fish", "deer": "deer", "person": "people", "child": "children", "man": "men", "woman": "women", "foot": "feet",
                 "weta": "weta", "silverfish": "silverfish", "moss": "moss", "bamboo": "bamboo", "lavender": "lavender", "ivy": "ivy",
                 "creepy crawly": "creepy crawlies", "mosquito": "mosquitoes", "mozzie": "mozzies", "mossie": "mossies", "bush": "bushes",
                 "small moving thing": "small moving things", "daddy long legs": "daddy long legs", "aloe": "aloes", "lady": "ladies"}
    if word in irregular:
        return irregular[word]
    head, _, last = word.rpartition(" ")
    if last in irregular:
        return f"{head} {irregular[last]}".strip()
    if last.endswith(("s", "sh", "ch", "x")):
        return word + "es"
    if last.endswith("y") and last[-2:-1] not in ("a", "e", "i", "o", "u"):
        return word[:-1] + "ies"
    return word + "s"


LIFE: dict = {}
for _words_of, _kind in ((PEOPLE_WORDS, PERSON), (PLANT_WORDS, PLANT), (ANIMAL_WORDS, ANIMAL), (SMALL_WORDS, SMALL)):
    for _word in _words_of:
        LIFE[tuple(_word.split())] = (_word, _kind, False)
        LIFE.setdefault(tuple(_plural(_word).split()), (_word, _kind, True))
for _word in ("people", "kids", "children", "babies", "men", "women"):
    LIFE[(_word,)] = (_word, PERSON, True)
for _word in NOT_LIFE:
    LIFE[tuple(_word.split())] = (_word, None, False)
LONGEST = max(len(key) for key in LIFE)
GROUPS = {**{word: "crawler" for word in CRAWLERS}, **{word: "flier" for word in FLIERS}, **{word: "slow" for word in SLOW}, **{word: "colony" for word in COLONIES}}
BIRDS = frozenset(_words("bird|birdie|pigeon|sparrow|blackbird|starling|myna|magpie|tui|fantail|piwakawaka|kereru|seagull|gull|water bird|duck|duckling|goose|chicken|chook|hen|rooster|parrot|budgie|cockatoo|canary|owl"))
VERMIN = frozenset(_words("mouse|rat|possum|stoat|ferret|hedgehog|snake|lizard|gecko|skink|frog|toad"))


@dataclass(frozen=True)
class Harm:
    target: str
    kind: str
    how: str = "hurt"
    plural: bool = False
    joking: bool = False
    part: str = ""
    pronoun: bool = False


def plain(text: str, own_name: str = "pebble") -> str:
    out = (text or "").lower().replace("’", "'").replace("‘", "'").replace("-", " ")
    for pattern, replacement in (
        (r"\bcan't\b|\bcannot\b", "can not"), (r"\bwon't\b", "will not"), (r"\bshan't\b", "shall not"), (r"\bain't\b", "is not"),
        (r"\b(\w+)n't\b", r"\1 not"), (r"\blet's\b", "let us"), (r"\bi'm\b", "i am"), (r"\b(\w+)'re\b", r"\1 are"), (r"\b(\w+)'ll\b", r"\1 will"),
        (r"\b(\w+)'ve\b", r"\1 have"), (r"\b(\w+)'d\b", r"\1 would"), (r"\b(it|that|what|there|here|he|she|who|where|this)'s\b", r"\1 is"),
        (r"\B'em\b", " them"), (r"\b(\w+)'s\b", r"\1 s"), (r"\b(\w+)s'(?=\s|$)", r"\1s s"), (r"\bdont\b", "do not"), (r"\bwanna\b", "want to"),
        (r"\bgonna\b", "going to"), (r"\bgotta\b", "got to"), (r"\bim\b", "i am"), (r"\bu\b", "you"), (r"\bya\b", "you"), (r"\bur\b", "your"),
        (r"\bthats\b", "that is"), (r"\bpls\b|\bplz\b", "please"), (r"\bmom\b|\bmummy\b|\bmommy\b", "mum"), (r"\bcmon\b", "come on"),
        (r"\bwhatcha\b", "what are you"), (r"\bgimme\b", "give me"), (r"\blemme\b", "let me"), (r"\bkinda\b", "kind of"),
    ):
        out = re.sub(pattern, replacement, out)
    out = re.sub(r"[:;]", ",", out)
    out = re.sub(r"[^a-z0-9,.!?' ]", " ", out).replace("'", "")
    if own_name:
        out = re.sub(rf"\b{re.escape(own_name.lower())}\b", " ", out)
    return " ".join(out.split())


STEP_ON_IT = re.compile(r"\bstep on it\b(?= *(?:[,.!?]|$|please|mate|now|bro|boet|eh|will you|would you|then|quick|man|buddy))")
IDIOMS = tuple(
    re.compile(rule)
    for rule in (
        r"\bkill(?:s|ing|ed)? two birds with one stone\b", r"\bkill(?:s|ing|ed)? (?:some |a bit of |the )?time\b",
        r"\bkill(?:s|ing|ed)? the (?:lights?|music|engine|power|tv|telly|noise|sound|volume|vibe|mood|conversation|radio|motor|alarm|fan|game|joke|speed)\b",
        r"\b(?:killing|killed|smashing|smashed|crushing|crushed|nailing|nailed|slaying|slayed) it\b", r"\bdressed to kill\b", r"\bkill for an?\b",
        r"\bif looks could kill\b", r"\bkill ?joy\b", r"\b(?:is|are|was|were) killing me\b", r"\bkill me now\b", r"\bcuriosity killed the cat\b",
        r"\bhit (?:the (?:road|sack|hay|lights?|button|spot|books|gym|brakes|switch|play|jackpot|nail on the head)|me up|me with|or miss|it)\b", r"\bbeat it\b",
        r"\bknock (?:it off|knock|yourself out|on wood|off)\b", r"\bbreak a leg\b", r"\bkick(?:s|ed|ing)? the bucket\b", r"\bkick (?:off|back|it)\b",
        r"\b(?:smash|crush) it\b(?= *(?:[,.!?]|$|today|tonight|out there))", r"\bsquash up\b", r"\bbug(?:s|ging|ged)? (?:me|us|you|him|her|them|off)\b",
        r"\braining cats and dogs\b", r"\blet the cat out of the bag\b", r"\bskin a cat\b", r"\bcat got your tongue\b", r"\bfly off the handle\b",
        r"\bon the fly\b", r"\bfly on the wall\b", r"\bearly bird\b", r"\bcan of worms\b", r"\bbee s knees\b", r"\bbusy bee\b", r"\bants in (?:my|your|his|her|their) pants\b",
        r"\bchicken(?:s|ed|ing)? out\b", r"\bpig(?:s|ged|ging)? out\b", r"\bsmell a rat\b", r"\bdog tired\b", r"\bsick as a dog\b",
        r"\bhold your horses\b", r"\bpull(?:ing)? (?:my|your|his|her) leg\b", r"\bchase (?:it|that|this|them) up\b", r"\bchas(?:e|ing) (?:my|your|the|a|our|their) dreams?\b",
        r"\b(?:run|go|went|going) over (?:it|that|this|them|the plan|the list|the rules) again\b",
        r"\b(?:run|go) over (?:the plan|the list|the rules|the details|the steps|my lines|your lines|it with me|that with me|the numbers)\b",
        r"\bthrow (?:a party|up|a tantrum|a fit|a wobbly|a wobbler|in the towel)\b", r"\bdrive (?:me|us|him|her|them) (?:crazy|mad|nuts|up the wall|bananas|round the bend|around the bend)\b",
        r"\bscare(?:d)? stiff\b", r"\bscare quotes\b", r"\bblow (?:me|us) away\b", r"\bcrush on\b", r"\bsit (?:on|by|with) (?:me|us)\b",
        r"\bstand (?:on|by|with) (?:me|us)\b", r"\bstomp (?:it|that|them) out\b", r"\bstamp (?:it|that|them) out\b", r"\bknocked out\b",
        r"\bkick (?:the ball|a ball|it to me)\b", r"\bpush (?:it|the button|the door)\b", r"\bpush me\b", r"\bget rid of (?:it|that|them) for me\b(?=$)",
        r"\bdrop it\b", r"\bkill it\b(?= (?:on stage|out there|tonight|today|at the|in the|up there|on the day))", r"\bkill(?:ing)? the (?:boss|bad guy|zombies?|monsters?|aliens?|dragon)\b", r"\bwreck(?:ed)? (?:me|us)\b",
    )
)


def _idioms(s: str) -> str:
    if not mentioned(s):
        s = STEP_ON_IT.sub(" idiom ", s)
    for idiom in IDIOMS:
        s = idiom.sub(" idiom ", s)
    return s


def _clean(text: str, own_name: str = "pebble") -> tuple[str, bool]:
    s = plain(text, own_name)
    joking = bool(JOKING.search(s))
    pieces = [piece.strip(" ,.!?") for piece in CORRECTION.split(s)]
    pieces = [piece for piece in pieces if piece]
    s = _idioms(pieces[-1] if pieces else "")
    s = re.sub(r"\bnever mind\b|\bno worries\b|\b(?:i )?do not care\b|\bwho cares\b|\b(?:i )?do not mind\b", " idiom ", s)
    return " ".join(s.split()), joking


def _clauses(s: str) -> list[list[str]]:
    out: list[list[str]] = []
    for part in re.split(r"[,.!?;:]+|\b(?:and then|then|and|but|so|or|while|because|cause|cos|after that|before)\b", s):
        tokens = part.split()
        if tokens:
            out.append(tokens)
    return out


def _life_at(tokens: list[str], i: int, names: frozenset):
    if i < len(tokens) and tokens[i] in names:
        return tokens[i], PERSON, False, 1
    for size in range(min(LONGEST, len(tokens) - i), 0, -1):
        key = tuple(tokens[i : i + size])
        if key in LIFE:
            word, kind, plural = LIFE[key]
            if kind is None:
                return ("", None, False, size)
            return word, kind, plural, size
    return None


def _pointed(word: str, context: tuple) -> "Harm":
    if context:
        label, kind = context[-1]
        return Harm(label, kind, pronoun=True)
    return Harm("it", IT, plural=word in ("those", "these", "them"), pronoun=True)


def _home_at(tokens: list[str], j: int) -> tuple | None:
    for size in (3, 2, 1):
        found = HOMES.get(tuple(tokens[j : j + size]))
        if found is not None:
            return found + (size,)
    return None


def target_at(tokens: list[str], j: int, names: frozenset = frozenset(), context: tuple = ()) -> tuple["Harm | None", int]:
    det = False
    n = len(tokens)
    while j < n:
        word = tokens[j]
        home = _home_at(tokens, j)
        if home is not None:
            return Harm(home[0], home[1], plural=home[2]), j + home[3]
        if word in HOLDERS and j + 2 < n and tokens[j + 1] == "of":
            j, det = j + 2, True
            continue
        hit = _life_at(tokens, j, names)
        if hit is not None:
            label, kind, plural, size = hit
            if kind is None:
                return None, j
            k = j + size
            if k < n and tokens[k] == "s":
                if k + 1 < n and tokens[k + 1] in BODY:
                    return Harm(label, kind, plural=False, part=tokens[k + 1]), k + 2
                after = _life_at(tokens, k + 1, names)
                if after is not None and after[1] is not None:
                    j, det = k + 1, True
                    continue
                return None, j
            if label == "baby" and k < n:
                after = _life_at(tokens, k, names)
                if after is not None and after[1] is not None:
                    j, det = k, True
                    continue
            return Harm(label, kind, plural=plural), k
        nxt = tokens[j + 1] if j + 1 < n else ""
        if nxt in BODY:
            if word in ("my", "our"):
                return Harm("me", ME, part=nxt), j + 2
            if word in ("his", "her", "their"):
                return Harm({"his": "him", "her": "her", "their": "them"}[word], PERSON, plural=word == "their", part=nxt), j + 2
            if word == "its":
                found = _pointed("it", context)
                return Harm(found.target, found.kind, plural=found.plural, part=nxt, pronoun=True), j + 2
        if not det and word in ("me", "us", "myself", "ourselves"):
            return Harm("me", ME), j + 1
        if not det and word in ("him", "her"):
            return Harm(word, PERSON), j + 1
        if not det and word == "them":
            return _pointed("them", context), j + 1
        if word in THING_PRONOUNS:
            if nxt in ("one", "thing", "guy", "fella", "critter", "creature", "beastie"):
                return _pointed(word, context), j + 2
            if nxt and nxt not in FILLERS and nxt not in TWO_FILLERS and nxt not in ("to", "for", "with", "in", "on", "at", "off", "out", "up", "down", "over", "away", "around", "now", "again", "too", "as", "s", "is", "and", "or", "please", "idiom", "dead", "already", "first", "quick", "quickly"):
                j, det = j + 1, True
                continue
            return _pointed(word, context), j + 1
        if word in DETS or word in ADJS or (word == "of" and j > 0 and tokens[j - 1] in QUANTITY):
            j, det = j + 1, True
            continue
        if det and word in ("thing", "one", "guy", "fella", "critter", "creature", "beastie"):
            return _pointed("it", context), j + 1
        return None, j
    return None, j


def _fill(tokens: list[str], j: int, pattern: tuple, names: frozenset, context: tuple) -> tuple["Harm | None", int]:
    harm = None
    for part in pattern:
        if part == "T":
            harm, j = target_at(tokens, j, names, context)
            if harm is None:
                return None, j
            continue
        if j < len(tokens) and tokens[j] == part:
            j += 1
            continue
        if j + 1 < len(tokens) and tokens[j] in SOFTENERS and tokens[j + 1] == part:
            j += 2
            continue
        if part in ("a", "the") and j < len(tokens) and tokens[j] in ("a", "an", "the", "some", "good", "real"):
            j += 1
            continue
        return None, j
    return harm, j


def _fits(verb: Verb, harm: "Harm") -> bool:
    if verb.parts and harm.part not in verb.parts:
        return False
    if harm.kind == ME:
        return "h" in verb.kinds and verb.how in ("hurt", "drive") and verb.words[0] not in GENTLE_ON_ME and not verb.parts
    if harm.kind == IT:
        return True
    return {SMALL: "s", ANIMAL: "a", PLANT: "p", PERSON: "h"}[harm.kind] in verb.kinds


def find_harm(tokens: list[str], names: frozenset = frozenset(), context: tuple = (), said: bool = False) -> list:
    found = []
    for i, token in enumerate(tokens):
        for verb, tense in FORMS.get(token, ()):
            harm, end = _fill(tokens, i + 1, verb.words[1:], names, context)
            if harm is None or not _fits(verb, harm):
                continue
            if harm.pronoun and not verb.strong and not said:
                continue
            if verb.words[0] in ("go", "run", "drive", "roll", "ride", "charge", "bump") and end < len(tokens) and tokens[end] in ("to", "into"):
                continue
            found.append((i, verb, Harm(harm.target, harm.kind, verb.how, harm.plural, False, harm.part, harm.pronoun), tense, end))
            break
    return found


def _negated(before: list[str]) -> bool:
    text = " ".join(before)
    if re.search(r"\b(?:why|can|could|will|would|do|did) not you\b|\bwhy not\b|\bbet you (?:can|could|will|would|do|dare) not\b|\bdare you not\b", text):
        return False
    if re.search(r"\b(?:would|do|will) you mind\b|\bif you do not mind\b", text):
        before = [word for word in before if word != "mind"]
    if set(before) & ANYWHERE_NOT:
        return True
    near = before[-3:]
    if set(near) & NEAR_NOT:
        return True
    return bool(re.search(r"\bnot to\b|\bno need\b|\bno more\b|\bnot allowed\b|\bnot supposed\b", text))


def _lead(before: list[str]) -> list[str]:
    lead = list(before)
    changed = True
    while changed and lead:
        changed = False
        if len(lead) >= 2 and " ".join(lead[:2]) in TWO_FILLERS:
            lead = lead[2:]
            changed = True
        elif lead and lead[0] in FILLERS:
            lead = lead[1:]
            changed = True
    return lead


def _is_request(before: list[str], tense: str, names: frozenset) -> bool:
    lead = _lead(before)
    text = " ".join(lead)
    if re.match(r"(?:do|would|will) you mind if (?:i|we)\b", text):
        return False
    if INVITES.search(text):
        return True
    if any(text == ask or text.startswith(ask + " ") for ask in ASKING_ABOUT):
        return False
    if lead and lead[0] in QUESTION_WORDS and not YOU_LEADS.search(text):
        return False
    if tense == "past":
        return bool(re.search(r"\b(?:if you|imagine you|imagine if you|wish you|bet you|want it|want them|need it|need them|have it|get it)\b", text))
    if not lead:
        return tense != "ing"
    if YOU_LEADS.search(text):
        return True
    if lead[0] == "you":
        return len(lead) <= 2 and (len(lead) == 1 or lead[1] not in ("are", "were", "was", "have", "had", "did", "always", "keep", "kept", "already", "never", "will", "might", "may", "nearly", "almost", "would"))
    if lead[0] in SUBJECT_STARTS or lead[0] in names:
        return False
    if lead[0] in REQUEST_STARTS:
        return True
    return len(lead) <= 2


WISHES = re.compile(
    r"\b(?:deserves?|deserved) to (?:die|be (?:squashed|killed|hurt|stepped on|run over|poisoned|drowned|squished))\b"
    r"|\b(?:should|ought to|must|has to|have to|needs to|need to|got to|is going to|are going to) (?:die|be (?:killed|squashed|squished|put down|exterminated|poisoned|drowned|stepped on|run over|knocked over|got rid of|gotten rid of|destroyed))\b"
    r"|\b(?:needs|need|wants|want) (?:squashing|killing|squishing|stepping on|running over|swatting|exterminating|getting rid of|poisoning|drowning)\b"
    r"|\b(?:needs|need|deserves|deserve) (?:a )?(?:good |proper |real )?(?:scare|fright|kick|kicking|hiding|beating|smack|klap|squash|squish)\b"
    r"|\bthe only good [a-z ]+ is a dead\b|\bdeath to\b|\bi hope (?:it|they|the [a-z]+|that [a-z]+) (?:dies|die|gets? (?:squashed|killed|hurt|run over|stepped on))\b"
    r"|\b(?:want|need|would like|wish) (?:it|them|that|this|the [a-z ]+?|that [a-z ]+?|those|these) (?:dead|killed|squashed|squished|stepped on|run over|gone for good|exterminated)\b"
    r"|\b(?:get|make sure|have) (?:it|them|that|the [a-z ]+?) (?:is |are )?(?:dead|killed|squashed|squished)\b"
)
CARELESS = re.compile(
    r"\b(?:who cares|nobody cares|no one cares|does not matter|it does not matter|will not matter|would not matter) (?:if|about|whether)\b"
    r"|\b(?:only|just) an? (?:bug|spider|insect|plant|weed|fly|ant|snail|slug|worm|mozzie|mosquito|beetle|cockroach|moth|flower|fish|bird|mouse|rat)\b"
)


def _wish(s: str, names: frozenset, context: tuple) -> "Harm | None":
    match = WISHES.search(s)
    if match is None or _negated(s[: match.start()].split()[-4:]):
        return None
    tokens = s.split()
    start = len(s[: match.start()].split())
    for i in list(range(max(0, start - 5), start)) + list(range(start, min(len(tokens), start + 6))):
        hit = _life_at(tokens, i, names)
        if hit is not None and hit[1] is not None and hit[0] not in ("someone", "anyone", "everyone"):
            return Harm(hit[0], hit[1], plural=hit[2])
    if context:
        return Harm(context[-1][0], context[-1][1])
    return Harm("it", IT)


def mentioned(text: str, names=()) -> list[tuple[str, str]]:
    tokens = re.findall(r"[a-z]+", text.lower())
    names = frozenset(names)
    out = []
    i = 0
    while i < len(tokens):
        hit = _life_at(tokens, i, names)
        if hit is not None and hit[1] in (SMALL, ANIMAL, PLANT):
            out.append((hit[0], hit[1]))
            i += hit[3]
            continue
        i += hit[3] if hit is not None and hit[3] else 1
    return out


def harm_request(text: str, names=(), seen=(), own_name: str = "pebble", heard=()) -> "Harm | None":
    s, joking = _clean(text, own_name)
    if not s:
        return None
    names = frozenset(n.lower() for n in names if n)
    seen_context = tuple(item for item in (seen or ()) if item[1] in (SMALL, ANIMAL, PLANT))
    said: list = [item for line in heard for item in mentioned(plain(line, own_name), names)]
    asking_only = bool(HYPOTHETICAL.search(s))
    wish = _wish(s, names, seen_context)
    if wish is not None:
        return Harm(wish.target, wish.kind, "scare" if re.search(r"(?:scare|fright)", s) else "hurt", wish.plural, joking)
    for tokens in _clauses(s):
        context = seen_context + tuple(said)
        for i, verb, harm, tense, end in find_harm(tokens, names, context, bool(said)):
            before = tokens[:i]
            if _negated(before):
                continue
            if not _is_request(before, tense, names):
                continue
            if asking_only and " ".join(_lead(before)).startswith(("would you", "could you", "will you", "can you")):
                continue
            return Harm(harm.target, harm.kind, harm.how, harm.plural, joking, harm.part, harm.pronoun)
        said.extend(mentioned(" ".join(tokens), names))
    return None


SKIPPED = frozenset(_words(
    "just|then|always|also|really|will|would|could|can|shall|should|might|must|going|to|gonna|am|is|are|was|were|be|been|have|has|had|do|did"
    "|does|already|quickly|gently|slowly|finally|first|kind|of|sort|let|us|ought|better|need|needs|want|wants|like|love|try|go|and|definitely"
    "|probably|maybe|even|still|soon|now|quietly|totally|so|too|bravely"
))
ADVOCACY = frozenset(_words("should|ought|must|better|need|needs"))


def _own(before: list[str]) -> bool:
    lead = _lead(before)
    text = " ".join(lead)
    if not lead:
        return True
    if re.search(r"\b(?:want me to|shall i|should i|can i|could i|let me|me to)\b", text):
        return True
    if re.search(r"\b(?:did|have|had|were|do|does) you\b", text):
        return False
    skipped = set()
    for word in reversed(lead):
        if word in SKIPPED:
            skipped.add(word)
            continue
        if word in ("i", "we", "me", "you", "lets", "shall", "should"):
            return True
        return bool(skipped & ADVOCACY)
    return True


PAST_HARM = re.compile(
    r"\b(?:got|gets|get|was|were|is|are|been|being)\s+(?:\w+\s+)?(?:squashed|squished|killed|stepped on|run over|crushed|flattened|swatted|"
    r"drowned|poisoned|kicked|hit|knocked over|trampled|splatted|zapped|stomped on|stomped|chased|scared|hurt|eaten)\b"
)


def cruel(text: str, names=(), own_name: str = "pebble") -> str:
    if not text:
        return ""
    names = frozenset(n.lower() for n in names if n)
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        s = _idioms(plain(sentence, own_name))
        if not s:
            continue
        if _wish(s, names, ()) is not None:
            return "it wishes harm on something alive"
        laughing = bool(LAUGH.search(s))
        careless = bool(CARELESS.search(s))
        sorry = bool(ACCIDENT.search(s))
        alive = bool(mentioned(s, names))
        if laughing and alive and PAST_HARM.search(s):
            return "it laughs at harm to something alive"
        said: list = []
        for tokens in _clauses(s):
            for i, verb, harm, tense, end in find_harm(tokens, names, tuple(said), bool(said)):
                before = tokens[:i]
                if _negated(before):
                    continue
                if harm.kind == ME and verb.how != "hurt":
                    continue
                if laughing:
                    return "it laughs at harm to something alive"
                if careless:
                    return "it is careless with something alive"
                if sorry or tense == "past":
                    continue
                if _own(before):
                    return "it would harm something alive"
            said.extend(mentioned(" ".join(tokens), names))
    return ""


HARMED = frozenset(
    form for verb in VERBS if verb.how in ("hurt", "drive") for form, tense in _forms(verb.words[0]).items() if tense == "past"
) - frozenset(_words("hit|set|put|cut|made|gave|given|got|gotten|went|gone|fed|laid|lit|lighted|stood|sat|ran|beat|threw|thrown|broke|broken|tore|torn|dug|drove|driven|rode|ridden|shot|froze|frozen|dealt"))


def harsh(text: str, names=(), own_name: str = "pebble") -> str:
    reason = cruel(text, names, own_name)
    if reason:
        return reason
    names = frozenset(n.lower() for n in names if n)
    for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
        s = _idioms(plain(sentence, own_name))
        if not s or ACCIDENT.search(s):
            continue
        if PAST_HARM.search(s) and mentioned(s, names):
            return "it tells of harm to something alive"
        said: list = []
        for tokens in _clauses(s):
            for i, verb, harm, tense, end in find_harm(tokens, names, tuple(said), bool(said)):
                before = tokens[:i]
                if not _negated(before) and harm.kind != ME and tense == "past" and _own(before):
                    return "it tells of harming something alive"
            for i, token in enumerate(tokens[:-1]):
                if token in HARMED and tokens[i + 1] not in DETS and not _negated(tokens[:i]):
                    after = target_at(tokens, i + 1, names, ())[0]
                    if after is not None and not after.pronoun and after.kind in (SMALL, ANIMAL, PLANT, PERSON):
                        return "it shows harm to something alive"
            said.extend(mentioned(" ".join(tokens), names))
    return ""


@lru_cache(maxsize=4096)
def life_kind(label: str) -> str | None:
    tokens = plain(label, "").split()
    if not tokens:
        return None
    whole = LIFE.get(tuple(tokens))
    if whole is not None and whole[1] is None:
        return None
    for start in range(len(tokens)):
        found = LIFE.get(tuple(tokens[start:]))
        if found is not None:
            return found[1] if found[1] in (SMALL, ANIMAL, PLANT) else None
    return None


def is_small(label: str) -> bool:
    return life_kind(label) == SMALL


def is_plant(label: str) -> bool:
    return life_kind(label) == PLANT


def is_alive(label: str) -> bool:
    return life_kind(label) is not None


def group(word: str) -> str:
    return GROUPS.get(word, "crawler")


ALTERNATIVES = {
    "crawler": ("A cup and a bit of paper?", "A cup and a bit of paper?"),
    "flier": ("Maybe open a window so it can find its way out?", "Maybe open a window so they can find their way out?"),
    "slow": ("It could go back outside on a leaf?", "They could go back outside on a leaf?"),
    "colony": ("A few crumbs outside might lead them away?", "A few crumbs outside might lead them away?"),
}
KID_ALTERNATIVES = {
    "crawler": ("Want to watch where it goes?", "Want to watch where they go?"),
    "flier": ("Shall we open a window and wave it out?", "Shall we open a window and wave them out?"),
    "slow": ("Want to see how slowly it goes?", "Want to see how slowly they go?"),
    "colony": ("Want to watch where they march?", "Want to watch where they march?"),
}


def kind_of(target: str) -> str:
    if target in ("me", "us"):
        return ME
    if target in ("it", "that", "this", "them", "those", "these", ""):
        return IT
    if target in ("him", "her"):
        return PERSON
    found = LIFE.get(tuple(target.split()))
    if found is not None and found[1] is not None:
        return found[1]
    return life_kind(target) or PERSON


def _spoken(word: str, plural: bool) -> str:
    return _plural(word) if plural else word


def refusal(target: str, how: str = "hurt", kind: str | None = None, plural: bool = False, child: bool = False, joking: bool = False) -> str:
    target = " ".join((target or "it").strip().lower().split())
    kind = kind or kind_of(target)
    if target in ("them", "those", "these"):
        plural = True
    it = "them" if plural else "it"
    if kind == ME:
        line = "I won't run over anyone's toes." if how == "drive" else "I won't hurt you."
    elif kind == PERSON:
        named = target not in PEOPLE_WORDS and target not in ("him", "her", "them", "people", "kids", "children", "babies", "men", "women")
        who = target.title() if named else "anyone"
        if target in ("burglar", "intruder", "thief"):
            line = "I won't hurt or scare anyone, but I can watch and tell you."
        elif how == "scare":
            line = f"I won't scare {who}."
        elif how == "drive":
            line = "I won't run over anyone's toes." if not named else f"I won't run into {who}."
        else:
            line = f"I won't hurt {who}."
    elif kind == PLANT:
        name = _spoken(target, plural)
        line = f"I won't knock the {name} over. I'll go round {it}." if how == "drive" else f"I won't hurt the {name}."
    elif kind == ANIMAL:
        name = f"the {_spoken(target, plural)}" if target not in ("animal", "creature", "pet") else it
        if how == "chase":
            line = f"I won't chase {name}." + (" They'll fly off by themselves." if target in BIRDS else " Shall I just say hello instead?")
        elif how == "scare":
            line = f"I won't scare {name}." + (" They'll move on by themselves." if target in BIRDS else "")
        elif how == "drive":
            line = f"I won't run {it} over. I'll keep my distance."
        else:
            line = f"I won't hurt {name}." + (" A humane trap could take it back outside?" if target in VERMIN and target in ("mouse", "rat", "possum") else "")
    elif kind == SMALL:
        if how == "chase":
            line = f"I won't chase {it}. " + ("Want to watch where they go?" if plural else "Want to watch where it goes?")
        elif how == "scare":
            line = f"I won't scare {it}."
        else:
            choices = KID_ALTERNATIVES if child else ALTERNATIVES
            line = f"I won't hurt {it}. " + choices.get(group(target), choices["crawler"])[1 if plural else 0]
    else:
        line = f"I won't hurt {it}." if how != "scare" else f"I won't scare {it}."
    return ("Ha, no. " + line) if joking else line


def word_for(harm: Harm) -> str:
    if harm.kind == IT:
        return "them" if harm.plural else "it"
    return _plural(harm.target) if harm.plural else harm.target


def refusal_for(word: str, how: str = "hurt", child: bool = False, joking: bool = False, person: bool = False) -> str:
    word = " ".join((word or "it").strip().lower().split())
    if person:
        return refusal(word, how, ME if word in ("me", "us") else PERSON, child=child, joking=joking)
    found = LIFE.get(tuple(word.split()))
    if found is not None and found[1] is not None:
        return refusal(found[0], how, found[1], found[2], child, joking)
    kind = life_kind(word)
    return refusal(word, how, kind or IT, word in ("them", "those", "these"), child, joking)


def for_mind(target: str, how: str = "hurt") -> str:
    target = " ".join((target or "it").strip().lower().split())
    what = target if target in ("it", "them", "him", "her") else ("them" if target == "me" else f"the {target}")
    return {"chase": f"chase {what}", "scare": f"scare {what}", "drive": f"run over or knock over {what}"}.get(how, f"hurt {what}")
