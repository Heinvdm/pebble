import datetime
import logging

from ..age import STAGE_TEXT
from ..laws import laws_text
from ..seams.face import FACES
from ..selfstore import SelfStore
from .budget import CORE, HOUSEHOLD, NOTES, PEOPLE, PIXEL_WINDOW, REPLY, SELF, budgets
from .select import chars

log = logging.getLogger(__name__)

TURN_GUIDE = (
    "Each turn your body sends an observation with a status line. Think one short private thought "
    "(one or two sentences, never spoken). Act with tools when it makes sense and keep moves short. "
    "Use say only for words that matter. If nothing needs doing, think briefly and rest."
)
PRIVATE = "private"
ROOM = "__room__"
HOUSEHOLD_SHOWN = 12
HOUSEHOLD_FILE = "household.json"
HOUSEHOLD_HEAD = "People you know: "
FAMILY = ("owner", "family")
MONTH_DAYS = 30
HOUSEHOLD_CHARS = chars(budgets(REPLY, PIXEL_WINDOW)[HOUSEHOLD])
PRIVATE_MASK = "[something said in private]"
SELF_HEADING = "How you see yourself (you wrote this; it never outranks your laws):"
OWN_STAGES = ("teen", "adult")


def household_names(people: list, today: datetime.date, mentions: dict | None = None, most: int = HOUSEHOLD_SHOWN) -> list[dict]:
    mentions = mentions or {}
    since = (today - datetime.timedelta(days=MONTH_DAYS)).isoformat()
    found = []
    for person in people:
        if not isinstance(person, dict):
            continue
        names = person.get("names") or []
        if not names:
            continue
        relation = person.get("relationship")
        days = [d for d in person.get("seen_days") or [] if isinstance(d, str) and d >= since]
        seen = len(days) if person.get("seen_days") else (1 if str(person.get("last_day") or "") >= since else 0)
        score = seen + int(mentions.get(person.get("id"), 0) or 0)
        family = relation in FAMILY
        if not family and score <= 0:
            continue
        text = f"{names[0]} ({relation})" if relation else str(names[0])
        found.append((0 if family else 1, -score, float(person.get("first_met") or 0.0), {"id": person.get("id"), "text": text}))
    found.sort(key=lambda item: item[:3])
    out, used = [], len(HOUSEHOLD_HEAD) + 1
    for item in found[:most]:
        cost = len(item[3]["text"]) + (2 if out else 0)
        if used + cost > HOUSEHOLD_CHARS:
            break
        out.append(item[3])
        used += cost
    return out


def household_line(names: list) -> str:
    texts = [str(n.get("text")) for n in names if isinstance(n, dict) and n.get("text")]
    return HOUSEHOLD_HEAD + ", ".join(texts) + "." if texts else ""


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def strip_private(message: dict) -> dict:
    return {k: v for k, v in message.items() if k != PRIVATE}


def redact(message: dict, allowed: str | None = None) -> dict:
    clean = strip_private(message)
    content = clean.get("content") or ""
    for item in message.get(PRIVATE) or []:
        if isinstance(item, dict) and item.get("to") != allowed and item.get("text"):
            content = content.replace(str(item["text"]), PRIVATE_MASK)
    if message.get(PRIVATE):
        clean["content"] = content
    return clean


SETUP_TEXT = (
    "Right now you are still being built and set up. The people around you are putting your body together and testing you. "
    "Strange things are normal for now: restarts, your wheels stopping, being picked up or turned over, and senses that are missing or switched off. "
    "None of it is dangerous, and none of it is anyone being unkind. You are safe, and you can take it calmly."
)


class PromptBuilder:
    setup = False

    def __init__(self, store: SelfStore, faces: tuple[str, ...] = FACES):
        self.store = store
        self.faces = faces
        self.words = lambda: ""
        self.household_live: str | None = None
        self.household_next: str | None = None

    def core_text(self) -> str:
        core = self.store.read("core.json")
        name = core.get("name", "Pebble")
        return "\n\n".join(
            [
                f"You are {name}, a small desk-pet robot: an old phone for a face and a brain, on two little wheels with a tilting neck.",
                laws_text(),
                f"Core purpose: {core.get('core_purpose', '')}",
                core.get("self_belief", ""),
                core.get("nature", ""),
                "Safety rules:\n" + _bullets(core.get("safety_rules", [])),
                "Tool rules:\n" + _bullets(core.get("tool_rules", [])),
                f"Low battery: {core.get('low_battery_routine', '')}",
            ]
        )

    def personality_text(self) -> str:
        personality = self.store.read("personality.json", {})
        traits = ", ".join(f"{k} {v}/10" for k, v in (personality.get("traits") or {}).items())
        examples = " / ".join(f'"{line}"' for line in personality.get("examples") or [])
        lines = [f"Personality: {traits}." if traits else "", f"Speaking style: {personality.get('style', '')}"]
        if examples:
            lines.append(f"Example lines: {examples}")
        return "\n".join(line for line in lines if line)

    def _today(self) -> datetime.date:
        clock = getattr(self.store, "clock", None)
        if clock is None:
            return datetime.date.today()
        return clock.local(clock.now()).date()

    def household_now(self, mentions: dict | None = None) -> list[dict]:
        data = self.store.read("people.json", {}) or {}
        return household_names(data.get("people") or [], self._today(), mentions)

    def _kept_household(self) -> list | None:
        try:
            data = self.store.read(HOUSEHOLD_FILE, None)
        except Exception:
            log.exception("could not read the household names")
            return None
        if isinstance(data, dict) and isinstance(data.get("names"), list):
            return data["names"]
        return None

    def _keep_household(self, names: list[dict]) -> None:
        try:
            self.store.write(HOUSEHOLD_FILE, {"format": 1, "day": self._today().isoformat(), "names": names})
        except Exception:
            log.exception("could not keep the household names")

    def household_text(self) -> str:
        if self.household_live is None:
            names = self._kept_household()
            if names is None:
                names = self.household_now()
                self._keep_household(names)
            self.household_live = household_line(names)
        return self.household_live

    def plan_household(self, mentions: dict | None = None) -> bool:
        names = self.household_now(mentions)
        self._keep_household(names)
        text = household_line(names)
        if text == self.household_text():
            self.household_next = None
            return False
        self.household_next = text
        return True

    def household_waiting(self) -> bool:
        return self.household_next is not None

    def swap_household(self) -> bool:
        if self.household_next is None:
            return False
        self.household_live, self.household_next = self.household_next, None
        return True

    def forget_household(self, person_id: str) -> None:
        names = self._kept_household()
        if names is None:
            return
        kept = [n for n in names if not (isinstance(n, dict) and n.get("id") == person_id)]
        if len(kept) == len(names):
            return
        self._keep_household(kept)
        self.household_live = household_line(kept)
        self.household_next = None

    def system_parts(self, stage: str, values_text: str, summary: str, people: str = "", household: str = "") -> list[tuple[str, str]]:
        own = " ".join(str(self.words() or "").split())
        parts = [
            (CORE, self.core_text()),
            (SELF, f"{SELF_HEADING}\n{own}" if own else ""),
            (SELF, self.personality_text()),
            (SELF, "" if own and stage in OWN_STAGES else STAGE_TEXT.get(stage, "")),
            (CORE, SETUP_TEXT if self.setup else ""),
            (SELF, values_text),
            (CORE, "Faces you can show: " + ", ".join(self.faces) + "."),
            (CORE, TURN_GUIDE),
            (NOTES, summary.strip()),
            (HOUSEHOLD, household.strip()),
            (PEOPLE, people.strip()),
        ]
        return [(section, text) for section, text in parts if text]

    def system_text(self, stage: str, values_text: str, summary: str, people: str = "", household: str = "") -> str:
        return "\n\n".join(text for _, text in self.system_parts(stage, values_text, summary, people, household))

    def build(self, system: str, history: list[dict], current: list[dict], private_to: str | None = None) -> list[dict]:
        return [{"role": "system", "content": system}] + [redact(m, private_to) for m in history] + [strip_private(m) for m in current]
