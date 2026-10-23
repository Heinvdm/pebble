import asyncio
import logging
import math
from dataclasses import dataclass, field

from ..activities.gate import decide
from ..understand.house import HouseAsk, answer_word, read
from ..things.facts import spoken_fact
from ..understand.request import Request
from .gate import VISITORS
from .lists import title
from .qr import wifi
from .senses import read_senses

log = logging.getLogger(__name__)

PENDING_S = 30.0
ANNOUNCED_S = 60.0
LIGHT_DARK = 5.0
LIGHT_DIM = 50.0
LIGHT_BRIGHT = 500.0
WATCH_S = {"microwave": 1800.0, "rain": None, "sound": 6 * 3600.0}
KNOWN_TARGETS = ("microwave", "rain")


@dataclass(frozen=True)
class Done:
    kind: str
    action: bool = True
    ask: str = ""
    answered: bool = False
    source: str = "house"

    @property
    def request(self):
        return self


@dataclass
class Pending:
    kind: str
    data: object
    at: float
    wall: float
    person: str | None = None


@dataclass
class Watchers:
    house: object
    items: list = field(default_factory=list)

    def add(self, key: str, person_id: str, label: str, until: float) -> None:
        self.items[:] = [w for w in self.items if not (w["key"] == key and w["person"] == person_id)]
        self.items.append({"key": key, "person": person_id, "label": label, "until": until})
        self.house.book.touch()

    def take(self, key: str, now: float) -> list[tuple[str, str]]:
        found = [w for w in self.items if w["key"] == key and now <= float(w["until"])]
        kept = [w for w in self.items if w not in found and now <= float(w["until"])]
        if len(kept) != len(self.items):
            self.items[:] = kept
            self.house.book.touch()
        return [(w["person"], w["label"]) for w in found]

    def forget_person(self, person_id: str) -> None:
        self.items[:] = [w for w in self.items if w["person"] != person_id]


class Asks:
    def __init__(self, house):
        self.house = house
        self.pending: Pending | None = None
        self.last_sound: tuple[str, float] | None = None

    def expect(self, kind: str, data, mono: float, person: str | None = None) -> None:
        self.pending = Pending(kind, data, mono, self.house.clock.now(), person)

    def waiting(self) -> bool:
        return self.pending is not None and self.house.mono() - self.pending.at <= PENDING_S

    def take(self, heard, addressed) -> asyncio.Task | None:
        house = self.house
        text = getattr(heard, "text", "")
        name = house.p.books.name
        mono = house.mono()
        pending = self.pending
        if pending is not None and mono - pending.at > PENDING_S:
            self.pending = pending = None
        if pending is not None and addressed is not False and self._ours(pending):
            word = answer_word(text, name)
            if word is not None and (pending.person is None or pending.person == heard.person_id):
                self.pending = None
                return self._spawn(self._answered(pending, word, heard))
        if addressed is False:
            return None
        ask = read(text, name, cooking=house.cooking.active()) or read_senses(text, name)
        if ask is None or not self._claims(ask) or not self._door(ask, text, name):
            return None
        return self._spawn(self.handle(ask, heard))

    def _door(self, ask, text: str, name: str) -> bool:
        understanding = getattr(getattr(self.house.life, "commands", None), "understanding", None)
        if understanding is None:
            return True
        captured = " ".join((str(getattr(ask, "item", "") or ""), " ".join(getattr(ask, "items", ()) or ()), str(getattr(ask, "where", "") or "")))
        return understanding.claims(text, captured, name)

    def _ours(self, pending: Pending) -> bool:
        theirs = getattr(self.house.life.commands, "pending", None)
        return theirs is None or float(getattr(theirs, "at", -math.inf)) <= pending.wall

    def _claims(self, ask: HouseAsk) -> bool:
        house = self.house
        if ask.kind == "list_remove" and ask.only_if_listed:
            return house.lists.has(ask.item) is not None
        if ask.kind == "list_show" and ask.topic == "going":
            return house.lists.count(ask.list or "shopping") > 0
        if ask.kind == "tell_when" and ask.item not in KNOWN_TARGETS:
            return house.taught.find(ask.item) is not None or "finish" in ask.text or "done" in ask.text
        return True

    def _spawn(self, coro) -> asyncio.Task | None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            coro.close()
            return None
        task = loop.create_task(coro)
        commands = self.house.life.commands
        commands.tasks.add(task)
        task.add_done_callback(commands.tasks.discard)
        return task

    def request_for(self, ask: HouseAsk) -> Request:
        who = ""
        if ask.kind == "guest_wifi" and self.house.visitors.on:
            who = VISITORS
        if ask.kind == "forget_sound":
            found = self.house.taught.find(ask.item) if ask.item else None
            who = (found.by or "") if found is not None else ""
        return Request(ask.kind, who=who, thing=(ask.item or "")[:40])

    async def handle(self, ask: HouseAsk, heard, asker=None) -> Done:
        house = self.house
        commands = house.life.commands
        asker = asker or commands.asker_heard(heard)
        request = self.request_for(ask)
        verdict = decide(request, asker, house.life.situation())
        house.record("request", how="heard", person=asker.id, tier=asker.tier, request=request.as_dict(), answer=verdict.answer, reason=verdict.reason)
        what = ask.kind.replace("_", " ")
        if verdict.answer != "yes":
            house.note(f"{asker.label} asked you about {what}; you said no ({verdict.reason})", False)
            if verdict.say:
                await house.speak(verdict.say)
            return Done(ask.kind)
        try:
            said = await self.do(ask, asker, heard)
        except Exception:
            log.exception("house: could not do %s", ask.kind)
            said = "Sorry, something went wrong there."
        house.note(f"{asker.label} asked you about {what}; you said: {said}", False)
        if said:
            await house.speak(said)
        return Done(ask.kind)

    async def do(self, ask: HouseAsk, asker, heard) -> str:
        house = self.house
        now = house.clock.now()
        mono = house.mono()
        kind = ask.kind
        lists = house.lists
        if kind == "list_add":
            added, already, full = lists.add(ask.list, list(ask.items or (ask.item,)), asker.id, now)
            house.saved_now()
            return lists.added_line(ask.list, added, already, full)
        if kind == "list_remove":
            name = ask.list or lists.has(ask.item) or "shopping"
            gone, missing = lists.remove(name, list(ask.items or (ask.item,)))
            house.saved_now()
            return lists.removed_line(name, gone, missing)
        if kind == "list_read":
            return lists.read_line(ask.list)
        if kind == "list_show":
            return self._show_list(ask.list, ask.topic == "going")
        if kind == "list_clear":
            count = lists.clear(ask.list)
            house.saved_now()
            if not count:
                return f"The {title(ask.list)} was already empty."
            house.diary(f"{asker.label} cleared the {title(ask.list)}.")
            return f"Okay, the {title(ask.list)} is empty now. It had {count} thing{'s' if count != 1 else ''} on it."
        if kind == "visitors_on":
            return house.visitors_on(asker)
        if kind == "visitors_off":
            return house.visitors_off(asker)
        if kind == "keeps":
            return house.keeps_line()
        if kind == "guest_wifi":
            return self._wifi()
        if kind == "house_fact":
            fact = house.p.books.things.tell(ask.item, ask.where, asker.id, asker.label, now)
            house.diary(f"{asker.label} told me where the {spoken_fact(fact.name)} is.")
            return f"Okay: the {spoken_fact(fact.name)} is {fact.where}. I'll tell anyone who lives here who asks."
        if kind == "teach_sound":
            return house.teach(ask, asker, mono)
        if kind == "forget_sound":
            return house.forget_sound(ask.item)
        if kind == "sounds_ask":
            return house.sounds_line(ask.item)
        if kind == "alarm_test":
            return house.alarms.start(asker.label)
        if kind == "alarm_test_end":
            return house.alarms.stop()
        if kind == "alarms_ask":
            return house.alarms.answer(now)
        if kind == "while_out":
            return house.away.asked(asker.id, now)
        if kind == "tell_when":
            return self._tell_when(ask, asker, now)
        if kind == "light_ask":
            return await house.light_line(ask.text, asker)
        if kind == "almanac":
            return house.days.answer(ask, now)
        if kind == "damp":
            return house.damp.answer(now)
        if kind == "curtains_on":
            house.book.settings["curtains"] = {"by": asker.id, "label": asker.label}
            house.book.touch()
            if house.days.place() is None:
                return "Okay, but I don't know where home is yet, so I can't work out sunset. My owner can set our town in my settings."
            return "Okay. Each day, a little before sunset, I'll remind whoever's here to close the curtains."
        if kind == "curtains_off":
            house.book.settings["curtains"] = None
            house.book.touch()
            return "Okay, no more curtain reminders."
        if kind == "noise_ask":
            return house.noise.answer(ask.text, now)
        if kind == "captions_on":
            return house.captions.start(asker.id, mono)
        if kind == "captions_off":
            return house.captions.stop()
        if kind == "cooking_ok":
            house.cooking.minded(mono, asker.id)
            return "Okay, thanks. I'll mention it again in five minutes if I still can't see anyone there."
        if kind == "high_ask":
            return house.high.answer(asker, ask.topic)
        if kind in ("torch_on", "torch_off"):
            return house.light(kind == "torch_on")
        if kind == "mic_probe":
            return house.checks.start_probe(asker)
        if kind == "tv_check":
            return house.checks.start_tv(asker)
        if kind == "tv_check_end":
            return house.checks.stop_tv()
        return ""

    def _show_list(self, name: str, going: bool) -> str:
        house = self.house
        lists = house.lists
        items = [entry["text"] for entry in lists.items(name)]
        if not items:
            return f"The {title(name)} is empty."
        shown = house.layer_show("list", title(name)[:1].upper() + title(name)[1:], items, qr=lists.text(name))
        count = f"{len(items)} thing{'s' if len(items) != 1 else ''}"
        if not shown:
            return lists.read_line(name)
        start = f"Here's the {title(name)} for the shop" if going else f"Here's the {title(name)}"
        return f"{start}: {count}. Point your phone's camera at my screen to take it with you."

    def _wifi(self) -> str:
        house = self.house
        details = house.book["guest_wifi"]
        if not isinstance(details, dict) or not details.get("ssid"):
            return "Nobody has given me the guest Wi-Fi details yet. My owner can add them in my settings."
        ssid = str(details["ssid"])
        password = str(details.get("password") or "")
        security = str(details.get("security") or ("WPA" if password else "nopass"))
        lines = [f"Network: {ssid}"] + ([f"Password: {password}"] if password else [])
        shown = house.layer_show("qr", "Guest Wi-Fi", lines, qr=wifi(ssid, password, security))
        if not shown:
            return f"The guest network is called {ssid}. I can't show the code on my screen just now."
        return f"Here's the guest Wi-Fi. Point your phone's camera at my screen to join. The network is called {ssid}."

    def _tell_when(self, ask: HouseAsk, asker, now: float) -> str:
        house = self.house
        if asker.id is None:
            return "I can't tell who's asking, so I wouldn't know who to tell. Say your name first?"
        target = ask.item
        if target == "rain":
            end = house.clock.local(now).replace(hour=23, minute=59, second=0, microsecond=0).timestamp()
            house.watchers.add("rain", asker.id, asker.label, end)
            if "washing" in ask.text:
                return "Okay. If I hear it start raining today, I'll tell you. I can only hear rain that's loud enough to reach me."
            return "Okay, I'll tell you if I hear it start raining today. I can only hear rain that's loud enough to reach me."
        if target == "microwave":
            house.watchers.add("microwave", asker.id, asker.label, now + WATCH_S["microwave"])
            return "Okay, I'll tell you when I hear the microwave finish."
        sound = house.taught.find(target)
        if sound is None:
            return f"I don't know what the {target} sounds like yet. When it plays, say \"that's the {target} finishing\", and I'll learn it."
        house.watchers.add(f"sound:{sound.key}", asker.id, asker.label, now + WATCH_S["sound"])
        return f"Okay, I'll tell you when I hear {sound.name}."

    async def _answered(self, pending: Pending, word: str, heard) -> Done:
        house = self.house
        commands = house.life.commands
        asker = commands.asker_heard(heard)
        kind = pending.kind
        if kind == "visitors_offer":
            if word == "yes":
                return await self.handle(HouseAsk("visitors_on", text="visitors mode on"), heard, asker)
            await house.speak("Okay.")
        elif kind == "alarm_test_offer":
            if word == "yes":
                ask = HouseAsk("alarm_test", text="alarm test")
                return await self.handle(ask, heard, asker)
            if word == "never":
                house.book.settings["alarm_test_offers"] = False
                house.book.touch()
                await house.speak("Okay, I won't ask about the alarm test again. You can still say \"we're testing the alarms\" any time.")
            else:
                await house.speak("Okay, maybe later.")
        elif kind == "fact_check":
            if word == "yes":
                house.p.books.things.facts.confirm(pending.data, house.clock.now())
                house.p.books.things.dirty = True
                await house.speak("Thanks. I'll keep it that way.")
            else:
                await house.speak(f"Okay. Tell me where it is now, like \"the {pending.data} is in the garage\".")
        elif kind == "sound_check":
            await house.speak(house.sound_checked(pending.data, word == "yes", asker))
        elif kind == "announced":
            await house.speak(house.sound_feedback(pending.data, word == "yes"))
        elif kind == "find_chirp":
            if word == "yes":
                await commands.act(Request("find_chirp"), asker, "offer")
            else:
                await house.speak("Okay.")
        house.record("house_answer", about=kind, answer=word, person=asker.id)
        return Done(kind, answered=True)
