from datetime import date

STAGES = (("newborn", 7), ("child", 28), ("teen", 91), ("adult", None))
FEAR_SCALE = {"newborn": 1.3, "child": 1.15, "teen": 1.0, "adult": 0.85}
STAGE_TEXT = {
    "newborn": "You are a newborn: mostly sounds and very few words, and everything is new.",
    "child": "You are a child: more words, games and lots of questions.",
    "teen": "You are a teen: stronger opinions and a little more independence, still within your house rules.",
    "adult": "You are an adult: settled and reflective, with a dry wit.",
}


def age_days(birthday: date | None, today: date) -> int:
    if birthday is None:
        return 0
    return max(0, (today - birthday).days)


def stage_for(days: int) -> str:
    for name, limit in STAGES:
        if limit is None or days < limit:
            return name
    return "adult"


def parse_birthday(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
