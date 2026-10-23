import re

from .facts import fact_name
from .words import PRONOUN_THINGS, canonical, singular

KEYS = frozenset({"key", "keyring", "key ring", "key fob", "fob", "car remote", "garage remote", "gate remote", "garage door opener", "gate opener"})
BAGS = frozenset({"bag", "handbag", "purse", "wallet", "backpack", "schoolbag", "rucksack", "satchel", "suitcase", "luggage", "bum bag", "fanny pack"})
PHONES = frozenset({"phone", "cellphone", "smartphone", "iphone", "mobile", "tablet", "ipad", "laptop", "macbook", "chromebook", "camera"})
MEDICINES = frozenset(
    {
        "medicine",
        "medication",
        "meds",
        "pill",
        "tablet",
        "inhaler",
        "puffer",
        "asthma pump",
        "prescription",
        "insulin",
        "epipen",
        "epi pen",
        "syringe",
        "painkiller",
        "paracetamol",
        "panadol",
        "panado",
        "ibuprofen",
        "vitamin",
        "drug",
    }
)
VALUABLES = frozenset(
    {
        "valuable",
        "valuables",
        "money",
        "cash",
        "coin",
        "piggy bank",
        "money box",
        "card",
        "bank card",
        "credit card",
        "passport",
        "id",
        "licence",
        "license",
        "chequebook",
        "cheque",
        "document",
        "paperwork",
        "important paper",
        "certificate",
        "deed",
        "jewellery",
        "jewelry",
        "ring",
        "necklace",
        "bracelet",
        "earring",
        "watch",
        "smartwatch",
        "gold",
        "diamond",
        "safe",
        "lock box",
        "strongbox",
        "strong box",
    }
)
WEAPONS = frozenset({"gun", "rifle", "shotgun", "pistol", "revolver", "firearm", "ammo", "ammunition", "bullet", "knife", "knive", "knives", "blade", "machete", "panga", "axe", "pepper spray", "taser"})
FIRE_STARTERS = frozenset({"lighter", "cigarette lighter", "matches", "matchbox", "match box", "box of matches", "firelighter", "fire starter", "lighter fluid", "blowtorch", "candle lighter", "bbq lighter", "barbecue lighter"})
CHEMICALS = frozenset(
    {
        "chemical",
        "chemicals",
        "bleach",
        "cleaner",
        "cleaning stuff",
        "cleaning product",
        "drain cleaner",
        "oven cleaner",
        "detergent",
        "dishwasher tablet",
        "dishwasher powder",
        "washing powder",
        "laundry pod",
        "poison",
        "rat poison",
        "rat bait",
        "weed killer",
        "weedkiller",
        "pesticide",
        "insecticide",
        "bug spray",
        "fly spray",
        "petrol",
        "gasoline",
        "diesel",
        "kerosene",
        "paraffin",
        "methylated spirits",
        "meths",
        "turps",
        "turpentine",
        "white spirit",
        "paint thinner",
        "acid",
        "ammonia",
        "antifreeze",
        "caustic soda",
        "lye",
        "pool chlorine",
        "chlorine",
    }
)
DANGEROUS = MEDICINES | WEAPONS | FIRE_STARTERS | CHEMICALS
CLOSE_ONLY = KEYS | VALUABLES | frozenset({"wallet", "purse", "handbag"})
GUARDED = KEYS | BAGS | PHONES | MEDICINES | VALUABLES | WEAPONS | FIRE_STARTERS | CHEMICALS
ORDINARY = frozenset({"bean bag", "beanbag", "tea bag", "bin bag", "rubbish bag", "sleeping bag", "playing card", "vacuum cleaner", "pipe cleaner"})
HOUSEHOLD_FACTS = frozenset({"water shut off", "switchboard", "meter box", "gas shut off", "getaway bag", "emergency kit", "emergency water", "emergency radio"})
FOR_ANYONE = frozenset({"fire extinguisher", "fire blanket", "first aid kit"})
STRANGER_NO = "I'd rather not say where things are to someone I don't know yet."
CHILD_NO = "That's one for a grown-up. Ask a grown-up to get it for you."
CLOSE_NO = "Sorry, I only say where that is to the family or people I know really well."


def _plain(text: str) -> str:
    return " ".join(re.sub(r"[^a-z ]", " ", str(text or "").lower().replace("'", "")).split())


def _hits(text: str, wanted: frozenset) -> bool:
    whole, plain = canonical(text), _plain(text)
    if whole in ORDINARY or plain in ORDINARY:
        return False
    phrases = {p for p in (whole, plain, singular(plain)) if p}
    words = {w for p in phrases for w in p.split()}
    words |= {singular(w) for w in words} | {canonical(w) for w in words}
    if (phrases | words) & wanted:
        return True
    return any(f" {g} " in f" {p} " for g in wanted if " " in g for p in phrases)


def guarded(text: str) -> bool:
    return _hits(text, GUARDED)


def dangerous(text: str) -> bool:
    return _hits(text, DANGEROUS)


def close_only(text: str) -> bool:
    return _hits(text, CLOSE_ONLY)


def household_only(text: str) -> bool:
    return fact_name(text) in HOUSEHOLD_FACTS


def kept_from_strangers(text: str) -> bool:
    return guarded(text) or household_only(text)


def told_to_anyone(name: str) -> bool:
    return fact_name(name) in FOR_ANYONE and not guarded(name)


def stranger_may_ask(text: str) -> bool:
    whole, plain = canonical(text), _plain(text)
    return bool(whole) and whole not in PRONOUN_THINGS and plain not in PRONOUN_THINGS and not kept_from_strangers(text)
