import re

ANIMALS = frozenset(
    {
        "cat",
        "dog",
        "bird",
        "horse",
        "sheep",
        "cow",
        "rabbit",
        "bunny",
        "hamster",
        "guinea pig",
        "chicken",
        "hen",
        "duck",
        "goat",
        "pig",
        "parrot",
        "budgie",
        "tortoise",
        "turtle",
        "lizard",
        "ferret",
        "rat",
        "fish",
    }
)
FAST_LABELS = frozenset(
    {
        "bicycle",
        "car",
        "bench",
        "bird",
        "cat",
        "dog",
        "horse",
        "sheep",
        "cow",
        "backpack",
        "umbrella",
        "bag",
        "tie",
        "suitcase",
        "frisbee",
        "ball",
        "skateboard",
        "racket",
        "bottle",
        "glass",
        "cup",
        "fork",
        "knife",
        "spoon",
        "bowl",
        "banana",
        "apple",
        "sandwich",
        "orange",
        "broccoli",
        "carrot",
        "hot dog",
        "pizza",
        "doughnut",
        "cake",
        "chair",
        "couch",
        "plant",
        "bed",
        "table",
        "toilet",
        "tv",
        "laptop",
        "computer mouse",
        "remote control",
        "keyboard",
        "phone",
        "microwave",
        "oven",
        "toaster",
        "sink",
        "fridge",
        "book",
        "clock",
        "vase",
        "scissors",
        "teddy bear",
        "hair dryer",
        "toothbrush",
    }
)
HOUSEHOLD = frozenset(
    {
        "slipper",
        "jandal",
        "shoe",
        "sock",
        "boot",
        "key",
        "keys",
        "glasses",
        "sunglasses",
        "wallet",
        "purse",
        "hat",
        "jacket",
        "jumper",
        "hoodie",
        "blanket",
        "pillow",
        "cushion",
        "towel",
        "toy",
        "lego",
        "block",
        "doll",
        "plant pot",
        "pot",
        "box",
        "basket",
        "lamp",
        "rug",
        "mat",
        "desk",
        "shelf",
        "bookshelf",
        "cupboard",
        "drawer",
        "door",
        "window",
        "stool",
        "armchair",
        "beanbag",
        "speaker",
        "charger",
        "cable",
        "pen",
        "pencil",
        "paper",
        "newspaper",
        "magazine",
        "mug",
        "plate",
        "jar",
        "kettle",
        "water bottle",
        "bin",
        "rubbish bin",
        "broom",
        "vacuum",
        "headphones",
        "earphones",
        "tablet",
        "camera",
        "guitar",
        "drum",
        "bucket",
        "bowl",
        "lunchbox",
        "dummy",
        "bottle",
        "teddy",
        "stuffed toy",
        "ball",
    }
)
THING_WORDS = FAST_LABELS | HOUSEHOLD | ANIMALS
LANDMARKS = frozenset({"couch", "chair", "armchair", "table", "bed", "tv", "fridge", "plant", "toilet", "sink", "oven", "bench", "desk", "shelf", "bookshelf", "cupboard", "lamp", "door", "window", "beanbag", "stool"})
ROOMS = frozenset(
    {
        "kitchen",
        "lounge",
        "living room",
        "family room",
        "sitting room",
        "bedroom",
        "bathroom",
        "hallway",
        "hall",
        "garage",
        "garden",
        "laundry",
        "study",
        "office",
        "dining room",
        "front door",
        "back door",
        "deck",
        "porch",
        "stairs",
        "upstairs",
        "downstairs",
        "outside",
        "inside",
        "room",
        "other room",
        "next room",
        "yard",
        "backyard",
        "patio",
        "stoep",
        "veranda",
        "nursery",
        "toilet room",
        "spare room",
        "loo",
    }
)
FAR_PLACES = frozenset({"beach", "shop", "shops", "school", "park", "town", "work", "supermarket", "mall", "church", "doctor", "airport", "station", "library", "city", "pool", "gym", "dairy", "bank", "post office"})
SYNONYMS = {
    "sofa": "couch",
    "settee": "couch",
    "lounge suite": "couch",
    "telly": "tv",
    "television": "tv",
    "tele": "tv",
    "remote": "remote control",
    "the remote": "remote control",
    "clicker": "remote control",
    "mobile": "phone",
    "mobile phone": "phone",
    "cellphone": "phone",
    "cell phone": "phone",
    "cell": "phone",
    "smartphone": "phone",
    "tablet computer": "tablet",
    "ipad": "tablet",
    "iphone": "phone",
    "kitty": "cat",
    "puss": "cat",
    "pussy cat": "cat",
    "pussycat": "cat",
    "moggy": "cat",
    "moggie": "cat",
    "kitten": "cat",
    "kitty cat": "cat",
    "doggy": "dog",
    "doggie": "dog",
    "pup": "dog",
    "puppy": "dog",
    "doggo": "dog",
    "pooch": "dog",
    "pot plant": "plant",
    "potted plant": "plant",
    "houseplant": "plant",
    "house plant": "plant",
    "mug": "cup",
    "specs": "glasses",
    "spectacles": "glasses",
    "handbag": "bag",
    "refrigerator": "fridge",
    "tennis ball": "ball",
    "football": "ball",
    "soccer ball": "ball",
    "rugby ball": "ball",
    "sports ball": "ball",
    "jandals": "jandal",
    "flip flop": "jandal",
    "flip flops": "jandal",
    "flipflop": "jandal",
    "slops": "jandal",
    "plakkies": "jandal",
    "takkies": "shoe",
    "tekkies": "shoe",
    "sneaker": "shoe",
    "sneakers": "shoe",
    "trainer": "shoe",
    "trainers": "shoe",
    "dining table": "table",
    "teddy": "teddy bear",
    "keys": "key",
    "car keys": "key",
    "house keys": "key",
    "hair drier": "hair dryer",
    "mouse": "computer mouse",
    "laptop computer": "laptop",
    "trash can": "rubbish bin",
    "dustbin": "rubbish bin",
    "pram": "pram",
}
PLURAL_FIXED = frozenset({"news", "series", "species", "thanks", "glasses", "sunglasses", "scissors", "headphones", "earphones", "pants", "trousers", "jeans", "shorts", "binoculars", "tongs", "lego", "slops", "plakkies", "takkies"})
DETERMINERS = re.compile(r"^(?:the|my|your|our|his|her|their|a|an|this|that|these|those|some|any|its|mums|dads|me)\s+")
PRONOUN_THINGS = frozenset({"it", "that", "this", "that one", "this one", "them", "those", "these", "the thing", "that thing", "this thing"})
VOWEL = re.compile(r"^[aeiou]")


def singular(word: str) -> str:
    if word in PLURAL_FIXED or " " in word and word.split(" ")[-1] in PLURAL_FIXED:
        return word
    head, _, last = word.rpartition(" ")
    if last.endswith("ies") and len(last) > 4:
        last = last[:-3] + "y"
    elif re.search(r"(ches|shes|sses|xes)$", last):
        last = last[:-2]
    elif last.endswith("s") and not re.search(r"(ss|us|is)$", last) and len(last) > 3:
        last = last[:-1]
    return f"{head} {last}".strip()


def canonical(text: str) -> str:
    word = " ".join(str(text or "").lower().replace("-", " ").split())
    word = re.sub(r"[^a-z' ]", "", word).strip()
    previous = None
    while previous != word:
        previous = word
        word = DETERMINERS.sub("", word).strip()
    word = word.replace("'s ", " ").replace("'", "")
    if word in SYNONYMS:
        return SYNONYMS[word]
    one = singular(word)
    return SYNONYMS.get(one, one)


def known(word: str) -> bool:
    return canonical(word) in THING_WORDS


def is_animal(word: str) -> bool:
    return canonical(word) in ANIMALS


def matches(wanted: str, label: str) -> bool:
    want, have = canonical(wanted), canonical(label)
    if not want or not have:
        return False
    if want == have:
        return True
    have_words = have.split(" ")
    want_words = want.split(" ")
    return want_words[-1] == have_words[-1] and (len(want_words) == 1 or set(want_words) <= set(have_words))


def spoken(label: str) -> str:
    word = " ".join(str(label or "").lower().split())
    return "TV" if word == "tv" else word


def with_article(label: str) -> str:
    word = spoken(label)
    if word in PLURAL_FIXED or word.endswith("s") and word not in ("bus",):
        return f"some {word}"
    return f"{'an' if VOWEL.match(word) else 'a'} {word}"


def listing(words: list[str]) -> str:
    if not words:
        return ""
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " and " + words[-1]
