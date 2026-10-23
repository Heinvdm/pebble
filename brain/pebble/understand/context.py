import datetime
from dataclasses import dataclass

from ..mind.budget import MATCHED, PEOPLE, TASK, WORDS
from .request import Request, from_dict

ABOUTS = ("who", "speaker", "place", "confirm", "thing", "name")
PLACES_SHOWN = 15


@dataclass(frozen=True)
class Pending:
    about: str
    request: Request
    question: str
    asker: str | None = None
    at: float = 0.0
    tries: int = 1

    def as_dict(self) -> dict:
        return {"about": self.about, "request": self.request.as_dict(), "question": self.question}


@dataclass(frozen=True)
class Activity:
    kind: str
    by: str = ""
    with_: str = ""

    def text(self) -> str:
        whom = f" {self.with_}" if self.with_ else ""
        asked = f" (asked by {self.by})" if self.by else ""
        return f"{self.kind}{whom}{asked}"


@dataclass(frozen=True)
class Context:
    speaker: str | None = None
    tier: str = "stranger"
    present: tuple[str, ...] = ()
    activity: Activity | None = None
    pending: Pending | None = None
    recent: tuple[str, ...] = ()
    places: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    name: str = "pebble"
    can_see: bool = False
    pointing: bool = False
    life: tuple = ()
    now: str = ""
    refs: str = ""
    skills: str = ""
    card: str = ""
    shown: tuple[str, ...] = ()

    def known_names(self) -> set[str]:
        return {n for n in self.present + self.names if n and n != "a visitor"}

    def others(self) -> list[str]:
        return [n for n in self.present if n != self.speaker]

    def parts(self) -> list[tuple[str, str]]:
        out = [(PEOPLE, f"Speaker: {self.speaker or 'not known'} ({self.tier})")]
        if self.now:
            out.append((WORDS, "Now: " + spoken_now(self.now)))
        out.append((PEOPLE, "Present: " + (", ".join(self.present) if self.present else "nobody seen")))
        places = self.shown or self.places[:PLACES_SHOWN]
        if places:
            out.append((MATCHED, "Places known: " + ", ".join(places)))
        if self.refs:
            out.append((MATCHED, self.refs))
        if self.skills:
            out.append((MATCHED, self.skills))
        out.append((TASK, "Pebble is doing: " + (self.activity.text() if self.activity else "nothing in particular")))
        if self.pointing:
            out.append((TASK, "The speaker is pointing somewhere (\"there\" means where they point)"))
        if self.pending:
            out.append((TASK, f'Pebble just asked: "{self.pending.question}" (about {self.pending.about}, for {self.pending.request.text_json()})'))
        if self.recent:
            out.append((TASK, "Just before: " + " | ".join(self.recent[-3:])))
        if self.card:
            out.append((TASK, self.card))
        return out

    def lines(self) -> list[str]:
        return [line for _, line in self.parts()]


def context_from(data: dict | None) -> Context:
    data = dict(data or {})
    activity = data.get("activity")
    pending = data.get("pending")
    return Context(
        speaker=(data["speaker"] or None) if "speaker" in data else "ina",
        tier=data.get("tier", "trusted"),
        present=tuple(data.get("present", ["ina"])),
        activity=Activity(activity.get("kind", ""), activity.get("by") or "", activity.get("with") or "") if isinstance(activity, dict) else None,
        pending=Pending(pending.get("about", "confirm"), from_dict(pending.get("request") or {"kind": "chat"}), pending.get("question", "")) if isinstance(pending, dict) else None,
        recent=tuple(data.get("recent", [])),
        places=tuple(data.get("places", [])),
        names=tuple(data.get("names", [])),
        can_see=bool(data.get("can_see", False)),
        pointing=bool(data.get("pointing", False)),
        life=tuple((str(item[0]), str(item[1])) for item in data.get("life", []) if isinstance(item, (list, tuple)) and len(item) == 2),
        now=str(data.get("now") or ""),
        refs=str(data.get("refs") or ""),
        skills=str(data.get("skills") or ""),
        shown=tuple(data.get("shown", [])),
    )


def spoken_now(stamp: str) -> str:
    try:
        moment = datetime.datetime.fromisoformat(stamp)
    except ValueError:
        return stamp
    return moment.strftime("%A %Y-%m-%d %H:%M")
