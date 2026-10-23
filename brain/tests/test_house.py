import asyncio
from datetime import datetime, timezone

from conftest import Rig

from pebble.clock import FakeClock
from test_house_almanac import NZ
from pebble.hearing.chirp import Chirp
from pebble.hearing.sounds import HouseSounds
from pebble.house.asks import Done
from pebble.house.screen import TextLayer
from pebble.people.fake import fake_print
from pebble.people.proof import SEEN_SPEAKING
from pebble.people.trust import TRUSTED

LABELS = ["Speech", "Silence", "Knock", "Doorbell", "Ding-dong", "Microwave oven", "Beep, bleep", "Frying (food)", "Sizzle", "Boiling", "Meow", "Howl", "Whimper (dog)", "Rain", "Telephone bell ringing", "Cupboard open or close"]
HOP = 0.48


class Bench:
    def __init__(self, tmp_path, at=datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)):
        self.clock = FakeClock.at(at)
        self.rig = Rig(tmp_path, self.clock)
        self.life = self.rig.life
        self.house = self.life.house
        self.house.detector = HouseSounds(LABELS)
        self.published = []
        self.house.layer = TextLayer(lambda event, data: self.published.append(data), self.clock.monotonic)
        self.notices = []
        self.house.tell_owner = lambda title, text: self.notices.append(text) or True
        self.row_at = self.clock.monotonic()

    def person(self, key, name, tier=None, child=False, relationship=None):
        person = self.life.company.book.meet(self.clock.now(), voice=fake_print(key, "voice"), face=fake_print(key, "face"))
        person.set_name(name)
        if child:
            person.relationship = "child"
        elif relationship:
            person.relationship = relationship
        if tier:
            person.override = tier
        return person

    def here(self, person):
        self.life.company.presence.saw(person.id, self.clock.now())
        self.life.company.presence.heard(person.id, self.clock.now())

    async def wake(self):
        for _ in range(2):
            await self.tick(1.0)

    async def tick(self, seconds=1.0, people=()):
        steps = max(1, int(round(seconds)))
        for _ in range(steps):
            self.clock.advance(seconds / steps)
            for person in people:
                self.here(person)
            await self.life.tick(seconds / steps)
        await self.life.commands.settle()

    async def say(self, key, text, addressed=True, seen=True):
        self.rig.voice.lines.clear()
        proof = None
        company = self.life.company
        found = company.book.match("voice", fake_print(key, "voice")) if key and seen else None
        if found is not None and found.person_id in company.presence.here(self.clock.now()):
            company.presence.saw(found.person_id, self.clock.now())
            proof = SEEN_SPEAKING
        self.life.hear(text, fake_print(key, "voice") if key else None, addressed=addressed, proof=proof)
        task = self.life.considering
        await self.life.commands.settle()
        return task.result() if task is not None and task.done() else None, list(self.rig.voice.lines)

    def sound(self, seconds, scores):
        rows = []
        self.row_at = max(self.row_at, self.clock.monotonic())
        t = 0.0
        while t < seconds:
            self.row_at += HOP
            rows.append((self.row_at, [scores.get(name, 0.0) if name != "Silence" else (0.0 if scores else 0.9) for name in LABELS]))
            t += HOP
        self.house.inbox.append(rows)

    def spoken(self):
        return list(self.rig.voice.lines)

    def close(self):
        self.rig.close()


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 60))


def test_household_lists_children_add_and_read_strangers_neither(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        mo = bench.person("mo", "Mo", child=True)
        bench.here(mo)
        done, said = await bench.say("mo", "add milk and bread to the shopping list")
        assert isinstance(done, Done) and done.request.action
        assert said == ["Okay, milk and bread are on the shopping list."]
        _, said = await bench.say("mo", "what's on the list?")
        assert said == ["The shopping list has 2 things: milk and bread."]
        _, said = await bench.say("mo", "clear the list")
        assert said == ["Only a grown-up I know can do that."]
        bench.life.company.presence.left(mo.id)
        _, said = await bench.say("stranger", "add chocolate to the list")
        assert said == ["Sorry, that's just for the people who live here."]
        _, said = await bench.say("stranger", "what's on the list?")
        assert said == ["Sorry, that's just for the people who live here."]
        assert [e["text"] for e in bench.house.lists.items("shopping")] == ["milk", "bread"]

    run(play())
    bench.close()


def test_every_add_is_read_back_and_doubles_are_caught(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        _, said = await bench.say("ina", "we're out of dishwasher tablets")
        assert said == ["Okay, dishwasher tablets are on the shopping list."]
        _, said = await bench.say("ina", "add dishwasher tablet and eggs")
        assert said == ["Okay, eggs are on the shopping list. Dishwasher tablet is already on it."]
        _, said = await bench.say("ina", "put fix the gate on the to do list")
        assert said == ["Okay, fix the gate is on the to-do list."]
        _, said = await bench.say("ina", "take eggs off the list")
        assert said == ["Okay, I've taken eggs off the shopping list."]
        _, said = await bench.say("ina", "I got the job")
        assert said == []

    run(play())
    bench.close()


def test_the_list_goes_to_a_phone_as_a_code_and_leaves_the_screen(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        await bench.say("ina", "add milk, eggs and bread to the list")
        _, said = await bench.say("ina", "I'm going to the shop")
        assert said and "Point your phone's camera at my screen" in said[0]
        shown = [m for m in bench.published if m.get("op") == "show"]
        assert shown[-1]["kind"] == "list" and shown[-1]["lines"] == ["milk", "eggs", "bread"] and shown[-1]["qr"]
        assert shown[-1]["hold"] <= 30.0
        await bench.tick(31.0, people=[ina])
        assert bench.house.layer.showing() is None

    run(play())
    bench.close()


def test_going_to_the_shop_with_an_empty_list_is_just_talk(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        done, said = await bench.say("ina", "I'm going to the shop")
        assert not isinstance(done, Done) and said == []

    run(play())
    bench.close()


def test_visitors_mode_stops_new_prints_and_only_trusted_people_switch_it(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        sam = bench.person("sam", "Sam", relationship="friend")
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(sam)
        _, said = await bench.say("sam", "visitors mode on")
        assert said == ["Sorry, only someone I know really well can ask me that."]
        bench.here(ina)
        _, said = await bench.say("ina", "we've got people over tonight")
        assert said[0].startswith("Okay, visitors mode is on.")
        assert any(m.get("op") == "badge" and m.get("text") == "Visitors" for m in bench.published)
        before = len(bench.life.company.book.people)
        heard = bench.life.hear("hi there", fake_print("guest", "voice"), addressed=True)
        assert heard.person_id is None and len(bench.life.company.book.people) == before
        _, said = await bench.say(None, "what do you keep?")
        assert "not learning any new faces" in said[0]
        _, said = await bench.say("ina", "the visitors have gone")
        assert said == ["Okay, visitors mode is off."]
        assert {"op": "badge", "text": None} in bench.published

    run(play())
    bench.close()


def test_visitors_mode_ends_by_itself_after_twelve_hours(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        await bench.say("ina", "visitors mode on")
        assert bench.house.visitors.on
        bench.clock.advance(12 * 3600.0 + 5)
        await bench.tick(3.0)
        assert not bench.house.visitors.on

    run(play())
    bench.close()


def test_house_facts_are_told_by_trusted_people_and_answered_to_the_household(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        mo = bench.person("mo", "Mo", child=True)
        bench.here(mo)
        _, said = await bench.say("mo", "the switchboard is in the garage")
        assert said[0].startswith("Thanks, but") or "only" in said[0]
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        _, said = await bench.say("ina", "the water shut-off is under the laundry sink")
        assert said == ["Okay: the water shut-off is under the laundry sink. I'll tell anyone who lives here who asks."]
        bench.life.company.presence.left(ina.id)
        _, said = await bench.say("mo", "where's the water shut-off?")
        assert said == ["Ina told me the water shut-off is under the laundry sink."]
        _, said = await bench.say("mo", "where's the toby?")
        assert said == ["Ina told me the water shut-off is under the laundry sink."]
        bench.life.company.presence.left(mo.id)
        _, said = await bench.say("stranger", "where's the water shut-off?")
        assert said == ["I'd rather not say where things are to someone I don't know yet."]
        bench.house.forget(ina.id, ["Ina"])
        assert bench.life.p.books.things.facts.answer("water shut off", bench.clock.now()) == "I was told the water shut-off is under the laundry sink."

    run(play())
    bench.close()


def test_a_daytime_knock_is_told_to_whoever_is_home(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        bench.rig.voice.lines.clear()
        bench.sound(2.0, {"Knock": 0.6})
        await bench.tick(1.0, people=[ina])
        assert bench.spoken() == ["Ina, someone's knocking at the door."]
        bench.rig.voice.lines.clear()
        bench.sound(1.0, {"Cupboard open or close": 0.7, "Knock": 0.3})
        await bench.tick(1.0, people=[ina])
        assert bench.spoken() == []

    run(play())
    bench.close()


def test_one_night_knock_is_kept_for_the_morning_three_are_told_at_once(tmp_path):
    bench = Bench(tmp_path, at=datetime(2026, 10, 16, 2, 0, tzinfo=timezone.utc))

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        ina.relationship = "owner"
        bench.rig.voice.lines.clear()
        bench.sound(1.5, {"Knock": 0.7})
        await bench.tick(30.0)
        assert bench.spoken() == [] and bench.notices == []
        bench.sound(1.5, {"Knock": 0.7})
        await bench.tick(20.0)
        assert bench.spoken() == []
        bench.sound(1.5, {"Knock": 0.7})
        await bench.tick(1.0)
        assert bench.spoken() == ["Someone has been knocking at the door: three times in two minutes. I won't open it."]
        assert len(bench.notices) == 1 and "did not open the door" in bench.notices[0]
        assert not any("whisper" in str(line) for line in bench.spoken())

    run(play())
    bench.close()


def test_while_you_were_out_tells_house_things_never_other_peoples_comings_and_goings(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        sam = bench.person("sam", "Sam", TRUSTED)
        bench.here(ina)
        await bench.tick(2.0, people=[ina])
        bench.life.company.presence.left(ina.id)
        await bench.tick(200.0)
        bench.sound(2.0, {"Knock": 0.7})
        await bench.tick(5.0)
        bench.here(sam)
        await bench.tick(60.0, people=[sam])
        bench.life.company.presence.left(sam.id)
        await bench.tick(1700.0)
        bench.rig.voice.lines.clear()
        await bench.tick(25.0, people=[ina])
        said = bench.spoken()
        assert len(said) == 1 and said[0].startswith("Ina, since I last saw you: a knock at the door at ")
        assert "Sam" not in said[0]
        _, said = await bench.say("ina", "anything happen while I was out?")
        assert said[0].startswith("Since I last saw you: a knock at the door")

    run(play())
    bench.close()


def test_childrens_arrivals_go_only_to_their_grown_ups_and_only_when_turned_on(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        owner = bench.person("ina", "Ina")
        owner.relationship = "owner"
        mo = bench.person("mo", "Mo", child=True)
        sam = bench.person("sam", "Sam", TRUSTED)
        for person in (owner, mo, sam):
            bench.here(person)
        await bench.tick(2.0, people=[owner, mo, sam])
        for person in (owner, mo, sam):
            bench.life.company.presence.left(person.id)
        await bench.tick(1900.0)
        await bench.tick(5.0, people=[mo])
        assert not [e for e in bench.house.away.entries if e["kind"] == "child_home"]
        bench.house.change_settings(None, children_arrivals=True)
        bench.life.company.presence.left(mo.id)
        await bench.tick(1900.0)
        await bench.tick(5.0, people=[mo])
        entries = [e for e in bench.house.away.entries if e["kind"] == "child_home"]
        assert entries and entries[0]["for"] == [owner.id]
        assert "Mo got home" in bench.house.away.summary(owner.id, 0.0, bench.clock.now())
        assert "Mo" not in bench.house.away.summary(sam.id, 0.0, bench.clock.now())

    run(play())
    bench.close()


def test_cooking_with_nobody_in_the_kitchen_is_mentioned_every_five_minutes_and_never_called_safe(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.rig.voice.lines.clear()
        said = []
        for _ in range(16 * 60 // 5):
            bench.sound(5.0, {"Sizzle": 0.6})
            await bench.tick(5.0)
            said += bench.spoken()
            bench.rig.voice.lines.clear()
        assert len(said) == 3
        assert said[0] == "Something's still sizzling, and I haven't seen anyone in the kitchen for 5 minutes. I can't tell if that's okay, and I'm not a smoke alarm."
        assert said[1].endswith("It's been 10 minutes.") and said[2].endswith("It's been 15 minutes.")
        assert not any("safe" in line.lower() for line in said)
        bench.here(ina)
        done, line = await bench.say("ina", "I'm watching it")
        assert isinstance(done, Done) and line[0].startswith("Okay, thanks.")
        bench.life.company.presence.left(ina.id)
        bench.rig.voice.lines.clear()
        for _ in range(4 * 60 // 5):
            bench.sound(5.0, {"Sizzle": 0.6})
            await bench.tick(5.0)
        assert not [line for line in bench.spoken() if "sizzling" in line]
        for _ in range(5 * 60 // 5):
            bench.sound(5.0, {})
            await bench.tick(5.0)
        assert not [line for line in bench.spoken() if "sizzling" in line] and not bench.house.cooking.open

    run(play())
    bench.close()


def test_im_watching_it_is_only_taken_while_the_cooking_watch_has_spoken(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        done, said = await bench.say("ina", "I'm watching it")
        assert not isinstance(done, Done) and said == []

    run(play())
    bench.close()


def test_a_steady_chirp_is_told_and_the_finder_is_offered_when_there_is_one(tmp_path):
    bench = Bench(tmp_path)

    class Hearing:
        def __init__(self, items):
            self.items = items

        def chirps(self, since=float("-inf")):
            return [c for c in self.items if c.at > since]

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        now = bench.clock.now()
        bench.house.hearing = Hearing([Chirp(now - 80, -40.0, 3200.0, None, 0.3), Chirp(now - 40, -40.0, 3200.0, 40.0, 0.6), Chirp(now, -40.0, 3200.0, 40.0, 0.9)])

        class Finder:
            finds_chirps = True

        bench.life.commands.household = Finder()
        await bench.tick(1.0, people=[ina])
        said = bench.spoken()
        assert said == ["Ina, I can hear an alarm chirping about every 40 seconds. That usually means its battery is low. Some alarms chirp like that when they need replacing, so check its label. Shall I find which one?"]
        assert bench.house.asks.pending.kind == "find_chirp"

    run(play())
    bench.close()


def test_light_questions_use_the_light_sensor(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        _, said = await bench.say("ina", "is the light on?")
        assert said[0].startswith("There's light here, about 150 lux at my screen")

    run(play())
    bench.close()


def test_sunset_needs_the_owners_town_and_then_is_worked_out_offline(tmp_path):
    bench = Bench(tmp_path, at=datetime(2026, 10, 15, 12, 0, tzinfo=NZ))

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        _, said = await bench.say("ina", "when's sunset?")
        assert said[0].startswith("I don't know where home is yet")
        bench.house.change_settings(None, town="christchurch")
        _, said = await bench.say("ina", "when's sunset?")
        assert said[0].startswith("Sunset is at ") and said[0].endswith(" today.")
        _, said = await bench.say("ina", "is it a public holiday on monday?")
        assert said == ["No, this Monday isn't a public holiday."]
        _, said = await bench.say("ina", "when is labour day?")
        assert said == ["Labour Day is on Monday 26 October."]
        _, said = await bench.say("ina", "when do the clocks change?")
        assert said == ["The clocks go back an hour on Sunday 4 April, early in the morning."]

    run(play())
    bench.close()


def test_something_asked_for_is_told_when_the_person_is_back_even_after_a_short_while(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        bench.here(ina)
        _, said = await bench.say("ina", "tell me when the microwave's done")
        assert said == ["Okay, I'll tell you when I hear the microwave finish."]
        bench.life.company.presence.left(ina.id)
        await bench.tick(130.0)
        bench.sound(20.0, {"Microwave oven": 0.5})
        await bench.tick(1.0)
        bench.sound(1.5, {"Beep, bleep": 0.6})
        await bench.tick(2.0)
        bench.rig.voice.lines.clear()
        await bench.tick(3.0, people=[ina])
        said = bench.spoken()
        assert len(said) == 1 and said[0].startswith("Ina, earlier, the microwave finished at ")
        await bench.tick(30.0, people=[ina])
        assert len(bench.spoken()) == 1

    run(play())
    bench.close()


def test_when_it_cannot_tell_who_is_asking_it_says_so_and_a_name_alone_does_not_count(tmp_path):
    bench = Bench(tmp_path)

    async def play():
        await bench.wake()
        ina = bench.person("ina", "Ina", TRUSTED)
        mo = bench.person("mo", "Mo", child=True)
        bench.here(ina)
        bench.here(mo)
        _, said = await bench.say(None, "add milk to the list")
        assert said == ["Sorry, I can't tell who's asking. Say it again where I can see you."]
        _, said = await bench.say(None, "it's Ina")
        assert said != ["Okay, milk is on the shopping list."]
        assert bench.house.lists.items("shopping") == []
        _, said = await bench.say("ina", "add milk to the list")
        assert said == ["Okay, milk is on the shopping list."]
        assert bench.house.lists.items("shopping")[0]["by"] == ina.id

    run(play())
    bench.close()
