import re

from ..activities.gate import Asker, Verdict
from ..people.trust import CHILD, STRANGER
from ..respect import cruel
from ..tact import private_matter, tactless
from ..understand.cover import FUNCTION
from ..understand.logic import _to_or_that
from ..understand.request import Request
from .agenda import words_of

KEEP_S = 3 * 86400.0
FAMILY_TIES = frozenset({"owner", "family", "child"})
EVERYONE = frozenset({"everyone", "everybody", "all", "all of them", "the family", "the kids", "the others"})
THEM = frozenset({"", "them", "they", "him", "her", "he", "she"})
OWN = frozenset({"pebble", "you", "yourself"})
TURNING = frozenset(
    "i me my mine myself we us our ours ourselves you your yours yourself youre youll youve youd he him his himself hes she her hers herself shes "
    "they them their theirs themselves theyre theyll theyve im ive ill id its it say says said saying tell tells told asks asked please".split()
)
THEIRS = {"you": "them", "your": "their", "yours": "theirs", "yourself": "themselves", "you're": "they're", "you've": "they've", "you'll": "they'll"}
TO_YOU = {"he": "you", "him": "you", "his": "your", "she": "you", "hers": "yours", "himself": "yourself", "herself": "yourself", "he's": "you're", "she's": "you're", "he'll": "you'll", "she'll": "you'll"}
HER_ALONE = frozenset({"", "to", "at", "in", "on", "and", "that", "the", "a", "for", "with", "about", "again", "too", "now", "know", "back", "up", "out", "so", "if", "when"})
QUESTION = re.compile(r"^(?:do|does|did|are|is|was|were|can|could|will|would|should|have|has|what|where|when|who|why|how|which|shall|may)\b")
STRANGER_NO = "Sorry, I only pass on messages for people I know."
TO_STRANGER_NO = "I only pass on messages to people I know."
CHILD_NO = "I can pass on your messages to your family."
TACT_NO = "I'd rather not pass that on."
WORDS_NO = "Sorry, I want to pass on your own words, and I didn't get them all. Can you say it again?"
UNSURE = "I wasn't sure who to tell."


def stem(word: str) -> str:
    for end in ("ing", "ed", "es", "s", "e"):
        if word.endswith(end) and len(word) - len(end) >= 3:
            return word[: -len(end)]
    return word


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower().replace("'", "").replace("’", ""))


def new_words(text: str, heard: str, keep=frozenset()) -> list[str]:
    said = {stem(word) for word in words(heard)}
    kept = {word.lower() for word in keep}
    out = []
    for word in words(text):
        if word in FUNCTION or word in TURNING or word in kept or word.isdigit():
            continue
        if stem(word) in said:
            continue
        out.append(word)
    return out


def spoken(text: str, names=()) -> str:
    named = {name.lower() for name in names}
    out = []
    for word in " ".join((text or "").split()).strip(" .!?,").split(" "):
        bare = word.lower().strip(",.!?")
        bare = bare[:-2] if bare.endswith("'s") else bare
        if bare in named or bare == "i" or bare.startswith("i'"):
            word = word[:1].upper() + word[1:]
        out.append(word)
    return " ".join(out)


def to_you(text: str, others: set) -> str:
    said = (text or "").split(" ")
    found = {word.lower().strip(",.!?") for word in said}
    if found & {name.lower() for name in others}:
        return text
    out = []
    for index, word in enumerate(said):
        bare = word.lower().strip(",.!?")
        tail = word[len(word.rstrip(",.!?")):]
        if bare == "her":
            after = said[index + 1].lower().strip(",.!?") if index + 1 < len(said) else ""
            out.append(("you" if after in HER_ALONE else "your") + tail)
        elif bare in TO_YOU:
            out.append(TO_YOU[bare] + tail)
        else:
            out.append(word)
    return " ".join(out)


def theirs(text: str) -> str:
    return " ".join(THEIRS.get(word.lower(), word) for word in (text or "").split(" "))


def ending(text: str) -> str:
    return "?" if QUESTION.match((text or "").lower()) else "."


def family(person) -> bool:
    return person is not None and person.relationship in FAMILY_TIES


class Messenger:
    def __init__(self, later):
        self.later = later

    @property
    def life(self):
        return self.later.life

    @property
    def company(self):
        return self.later.company

    @property
    def agenda(self):
        return self.later.agenda

    def names(self) -> tuple:
        return self.later.names()

    def told(self, request: Request) -> list[Request]:
        return [step for step in request.steps() if step.kind == "say_to" and step.who not in ("", "me")]

    def person(self, who: str):
        return self.company.book.find(who) if who else None

    def keep_names(self, asker: Asker, person) -> set:
        out = set()
        for someone in (self.company.book.get(asker.id) if asker.id else None, person):
            if someone is not None:
                out.update(n.lower() for n in someone.names + someone.nicknames)
        return out

    def refusal(self, request: Request, asker: Asker, heard: str) -> tuple[str, str] | None:
        told = self.told(request)
        if not told:
            return None
        if asker.own:
            return "you pass on messages only for the people who ask", ""
        if asker.tier == STRANGER:
            return "you pass on messages only for people you know", STRANGER_NO
        for step in told:
            who = step.who
            person = None
            if who not in EVERYONE and who not in THEM:
                person = self.person(who)
                if person is None:
                    return f"you don't know who {who.title()} is", f"I don't know who {who.title()} is, so I can't pass that on."
                if self.company.tier(person) == STRANGER:
                    return "you pass on messages only to people you know", TO_STRANGER_NO
                if asker.tier == CHILD and not family(person):
                    return f"{asker.label} is a child, and a child's messages go only to their family", CHILD_NO
            if not step.text.strip():
                whom = person.label if person is not None else "them"
                return "there were no words to pass on", f"What should I tell {whom}?"
            if tactless(step.text) or cruel(step.text, self.names()):
                return "the message would be unkind or about someone's looks", TACT_NO
            if heard and new_words(step.text, heard, self.keep_names(asker, person)):
                return "the message had words the person did not say", WORDS_NO
        return None

    def only_told(self, request: Request, person) -> bool:
        told = self.told(request)
        if not told or any(step.kind == "say_to" and step.who in ("", "me") for step in request.steps()):
            return False
        names = {n.lower() for n in person.names + person.nicknames}
        return all(step.who in names or step.who in THEM for step in told)

    def recipients(self, who: str, happened=None) -> tuple[list, str]:
        if who in EVERYONE:
            return ["everyone"], ""
        if who in THEM:
            found = self.company.book.get(happened.who) if happened is not None and getattr(happened, "who", "") else None
            return ([found], "") if found is not None else ([], UNSURE)
        person = self.person(who)
        if person is None:
            return [], f"I don't know who {who.title()} is."
        return [person], ""

    def can_seek(self, person) -> bool:
        life = self.life
        alive = getattr(life, "alive", None)
        if alive is None or alive.usual_room(person.id) is None:
            return False
        sit = life.situation()
        return not life.commands.runner.busy and not sit.quiet and sit.can_move and not life.alarm()

    async def now(self, request: Request, asker: Asker, how: str) -> Verdict:
        later = self.later
        when = later.clock.now()
        step = request.with_(then=())
        problem = self.refusal(step, asker, "") if how in ("then", "later") else None
        if problem is not None:
            return await later._refuse(step, asker, *problem)
        if step.who in EVERYONE:
            said = f"Everyone, {asker.label} says: {spoken(step.text, self.names())}{ending(step.text)}"
            later.say(said)
            later.record("message_said", to="everyone", person=asker.id)
            later.note(f"{asker.label} asked you to tell everyone something; you said it to the room")
            return await self._then(request, asker, Verdict("yes", "you told everyone", said))
        people, problem = self.recipients(step.who)
        if not people:
            return await later._refuse(step, asker, "you could not tell who it was for", problem)
        full = later.agenda.full(asker.id)
        if full:
            return await later._refuse(step, asker, "you are keeping as much for later as you can", full)
        person = people[0]
        remind = bool(re.search(r"\bremind\b", (later.commands.question_text or "").lower()))
        due = self.hold(asker.id, asker.label, asker.tier, asker.family, person, step.text, remind, when)
        said = ""
        if later.senses.with_pebble(person.id, when):
            later._deliver(when, force=person.id)
            if due in later.out and not due.offered:
                said = f"Okay, I'll tell {person.label} when I can talk again."
        elif self.can_seek(person):
            said = f"Okay, I'll go and find {person.label} and tell them."
        else:
            said = f"Okay, I'll tell {person.label} next time I see them."
        if said:
            later.say(said)
        later.record("message_kept", item=due.item, person=asker.id, to=person.id, remind=remind)
        later.note(f"{asker.label} gave you a message for {person.label}" + ("; you will find them" if "find" in said else ""))
        return await self._then(request, asker, Verdict("yes", f"{asker.label} may send {person.label} a message", said))

    async def _then(self, request: Request, asker: Asker, verdict: Verdict) -> Verdict:
        if request.then:
            await self.later._chain(list(request.then), asker, "then")
        return verdict

    def hold(self, by: str | None, by_label: str, tier: str, by_family: bool, person, text: str, remind: bool, now: float):
        from .later import Due

        others = {n for someone in self.company.book.people.values() if someone.id != person.id for n in someone.names + someone.nicknames}
        text = to_you(text, others - {by_label})
        request = Request("say_to", who=person.label.lower(), text=text)
        item = self.agenda.new(request, by, by_label, tier, "message", person.id, [], private_matter(text), words_of(request), by_family)
        item.remind = remind
        item.runs_out = now + KEEP_S
        self.agenda.add(item)
        self.agenda.save(force=True)
        due = Due(item.id, person.id, person.label, text, now, item.runs_out, True, kind="message", by=by, by_label=by_label, remind=remind)
        self.later.out.append(due)
        return due

    def held(self, item) -> bool:
        if item.kind != "message" or item.runs_out is None:
            return False
        request = item.req()
        return request.when is None and request.on is None

    def restore(self, now: float) -> None:
        from .later import Due

        for item in list(self.agenda.waiting()):
            if not self.held(item) or any(due.item == item.id for due in self.later.out):
                continue
            person = self.company.book.get(item.aimed) if item.aimed else None
            if person is None:
                self.agenda.remove(item, "dropped")
                continue
            text = item.req().text
            self.later.out.append(Due(item.id, person.id, person.label, text, now, item.runs_out, True, kind="message", by=item.by, by_label=item.by_label, remind=item.remind))

    def fired(self, item, step: Request, happened, now: float) -> None:
        later = self.later
        asker = later.asker_of(item)
        if step.who in EVERYONE:
            later.say(f"Everyone, {item.by_label} says: {spoken(step.text, self.names())}{ending(step.text)}")
            later.record("message_said", to="everyone", item=item.id)
            return
        people, problem = self.recipients(step.who, happened)
        if not people:
            later.agenda.owe(item.by, f"I couldn't pass on your message ({step.text}). {problem}", now)
            later.record("message_dropped", item=item.id, why="who")
            return
        person = people[0]
        refused = self.refusal(step.with_(who=person.label.lower()), asker, "")
        if refused is not None:
            later.agenda.owe(item.by, f"I didn't pass on your message to {person.label}: {refused[1][:1].lower() + refused[1][1:]}", now)
            later.record("message_dropped", item=item.id, why="refused")
            return
        self.hold(item.by, item.by_label, asker.tier, item.family, person, step.text, item.remind, now)

    def line(self, due) -> str:
        names = self.names()
        text = spoken(due.text, names)
        if due.remind:
            return f"{due.label}, {due.by_label} asked me to remind you {_to_or_that(due.text, names)}."
        first = text.split(" ")[0].lower().strip(",.!?")
        if first == due.by_label.lower() or first.startswith(due.by_label.lower() + "'"):
            return f"{due.label}, a message from {due.by_label}: {text}{ending(due.text)}"
        return f"{due.label}, {due.by_label} says: {text}{ending(due.text)}"

    def offer(self, dues: list) -> str:
        label = dues[0].label
        senders = list(dict.fromkeys(due.by_label for due in dues if due.kind == "message"))
        if len(senders) == 1 and len(dues) == 1:
            return f"{label}, I've got a message from {senders[0]} for you."
        return f"{label}, I've got some messages for you."

    def delivered(self, dues: list, now: float) -> None:
        later = self.later
        for due in dues:
            item = next((i for i in self.agenda.waiting() if i.id == due.item), None)
            if item is not None:
                self.agenda.remove(item, "done")
            later.record("message_said", item=due.item, to=due.person, by=due.by)
            if due.by and due.by != due.person and not later.senses.with_pebble(due.by, now):
                later.agenda.owe(due.by, f"I told {due.label}.", now)
        self.agenda.save(force=True)

    def expired(self, due, now: float) -> None:
        later = self.later
        item = next((i for i in self.agenda.waiting() if i.id == due.item), None)
        if item is not None:
            self.agenda.remove(item, "expired")
        later.agenda.owe(due.by, f"I couldn't give {due.label} your message ({due.text}): I didn't see them for three days, so I've dropped it.", now)
        later.record("message_dropped", item=due.item, why="three days")

    def read_back(self, item, lead: str) -> str:
        request = item.req()
        step = self.told(request)[0] if self.told(request) else request
        who = step.who.title() if step.who not in THEM else "them"
        if step.who in EVERYONE:
            who = "everyone"
        if item.remind:
            body = f"I'll remind {who} {_to_or_that(theirs(step.text), self.names())}"
        else:
            body = f"I'll tell {who}: {step.text}" if step.text else f"I'll tell {who}"
        return f"{lead[:1].upper() + lead[1:]}, {body}" if lead else body
