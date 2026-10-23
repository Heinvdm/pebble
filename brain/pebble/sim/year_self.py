import argparse
import asyncio
import datetime
import json
import math
import random
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from ..activities.card import kind_of, said, slug
from ..activities.skills import Skill
from ..alive.rooms import Room
from ..clock import iso
from ..conversation.quality import HOUSE, Bench
from ..conversation.turns import Turn
from ..hearing.taught import Sound, View
from ..house.rules import Rule
from ..life.agenda import Item
from ..life.selection import LESSONS
from ..mind.budget import CORE, HISTORY, READER, REPLY, ROOM, SECTION_ORDER, TASK, TURN, WORK, Counter, Guard, budgets, ceiling, pieces, row
from ..mind.lawful import with_laws
from ..mind.prompt import HOUSEHOLD_CHARS
from ..mind.profile import ModelProfile
from ..mind.sizes import PROFILE, Ruler, build
from ..mind.select import Names
from ..nav.chart import Place
from ..people.person import Person, Promise
from ..seams.face import FACES
from ..self.notes import BUDGET_CHARS as NOTES_CHARS
from ..self.recall.embed import StandIn, embedder_from
from ..self.recall.stream import Record
from ..self.recall.vectors import pack
from ..script.book import Book, starters
from ..script.check import read
from ..teach.book import Entry as HowEntry
from ..teach.book import pack as pack_print
from ..teach.induce import said_steps
from ..things.book import Spot, Thing
from ..things.facts import Told
from ..understand.model import messages as reader_messages

DAY_S = 86400.0
YEAR_DAYS = 365
WINDOWS = (8192, 16384)
PEOPLE = 60
OFTEN = 15
ROOMS = (
    "kitchen", "lounge", "bedroom", "bathroom", "office", "laundry", "garage", "hallway", "dining room", "study",
    "deck", "garden", "shed", "porch", "attic", "spare room", "playroom", "sunroom", "pantry", "nook",
    "workshop", "cellar", "toilet", "music room", "craft room",
)
SPOT_WORDS = (
    ("front", "back", "side", "blue", "red", "green", "tall", "low", "old", "new", "round", "long", "wooden"),
    ("door", "window", "rug", "lamp", "shelf", "chair", "mat", "chest", "bench", "cabinet", "stool", "drawer", "basket", "mirror", "clock"),
)
SPOTS = 55
THINGS = 800
THING_WORDS = (
    ("blue", "red", "green", "yellow", "old", "new", "tiny", "big", "striped", "spotty", "soft", "shiny", "wooden", "metal", "paper", "glass", "woolly", "plastic", "silver", "brown"),
    ("mug", "ball", "book", "car", "block", "sock", "hat", "cushion", "plate", "bowl", "spoon", "pen", "torch", "box", "bucket", "jar", "kite", "drum", "puzzle", "robot", "train", "boat", "brush", "rope", "frame", "vase", "candle", "basket", "blanket", "tin", "bottle", "toy", "towel", "pillow", "boot", "slipper", "scarf", "glove", "map", "card"),
)
SKILLS = 200
SKILL_WORDS = (
    ("moon", "sunny", "sleepy", "happy", "silly", "quick", "slow", "kitchen", "lounge", "garden", "morning", "evening", "twirly", "bouncy", "gentle", "proud", "secret", "lucky", "windy", "rainy"),
    ("dance", "round", "wiggle", "hello", "goodbye", "parade", "patrol", "spin", "bow", "shuffle", "waltz", "march", "check"),
)
SCRIPTS_MOST = 40
HOWTO = 200
HOWTO_WORDS = (
    ("door", "window", "plant", "post", "bin", "toy", "laundry", "porch", "hall", "shed", "gate", "fridge", "oven", "tap", "lamp", "heater", "rug", "shelf", "basket", "kettle"),
    ("check", "round", "tour", "visit", "sweep", "watch", "count", "look", "patrol", "hello"),
)
HOWTO_KINDS = ("procedure",) * 120 + ("route",) * 30 + ("concept",) * 20 + ("word",) * 15 + ("habit",) * 10 + ("way",) * 5
LESSONS_MOST = 400
RULES_MOST = 30
SOUNDS_MOST = 20
AGENDA_MOST = 150
MEMORIES = 100_000
NAME_START = ("Ta", "Ve", "Ri", "Lo", "Ma", "Ke", "Su", "No", "Da", "Fi", "Pe", "Ro", "Ha", "Ze", "Wi", "Ja", "Bo", "Ci", "Gu", "Ny", "Qua", "El", "Om", "Ul")
NAME_END = ("rav", "lio", "nik", "vy", "kaz", "mira", "sel", "tor", "rin", "bel", "dan", "wen", "pho", "lune", "dra")
LIKE_WORDS = (
    ("green", "spicy", "old", "loud", "quiet", "sweet", "tiny", "shiny", "cold", "hot", "slow", "early"),
    ("tea", "jazz", "cricket", "puzzles", "gardening", "lego", "biscuits", "rain", "trains", "chess", "soup", "maps", "kites", "poems", "boats", "birds", "cards", "swims", "walks", "films"),
)
SOUND_NAMES = (
    "the doorbell", "the microwave finished", "the kettle boiling", "the washing machine done", "the dryer buzzing", "the oven timer",
    "the gate creaking", "the garage door", "the dishwasher done", "the toaster popping", "the phone charger chime", "the letterbox",
    "the fridge alarm", "the bread maker beeping", "the rice cooker ready", "the car unlocking", "the back gate latch", "the clock chime",
    "the printer finished", "the bath filling",
)
FACT_NAMES = (
    ("water shut off", "under the house by the front steps"), ("switchboard", "in the hallway cupboard"), ("gas shut off", "beside the side gate"),
    ("getaway bag", "in the hallway cupboard"), ("emergency kit", "in the garage on the top shelf"), ("fire extinguisher", "under the kitchen sink"),
    ("first aid kit", "in the bathroom cabinet"), ("torch", "in the kitchen drawer"), ("spare batteries", "in the office drawer"), ("emergency water", "in the garage"),
)
LESSON_TEXTS = (
    "The {room} is too warm in the afternoon.",
    "The {room} is quiet after dinner.",
    "Rolling slowly in the {room} keeps me off the rug's edge.",
    "{name} likes quiet while working.",
    "{name} laughs when I tilt my head.",
    "{name} likes being told when the post comes.",
    "Jokes about my battery land better than puns.",
    "Waiting a moment before speaking works better in the morning.",
    "A small wiggle is a good hello for {name}.",
    "Asking {name} twice makes them cross.",
)
MEMORY_TEXTS = (
    ("happened", "Events: {name} came into the {room} and sat down."),
    ("happened", "Events: you found the {thing} near the {room} door."),
    ("happened", "Events: {name} played with the {thing} in the {room}."),
    ("said", '{name} said: "I\'m going to the {room} to look for the {thing}, then the shops."'),
    ("said", '{name} said: "Remind me that the {thing} needs fixing before the weekend."'),
    ("fact", "{name} keeps the {thing} in the {room}."),
    ("happened", "Events: it rained and {name} brought the {thing} inside."),
    ("feeling", "You felt happy when {name} laughed in the {room}."),
)
REPLY_LINES = (
    "Pebble, what do you think we should have for dinner tonight?",
    "Did you have a good day today, Pebble?",
    "Pebble, can you tell me a joke?",
    "I'm going to the shops later, do you need anything?",
    "Pebble, what's your favourite colour?",
    "That was a lovely song on the radio just now.",
    "Pebble, are you feeling sleepy yet?",
    "We should tidy up before the visitors come.",
    "Pebble, do you remember what we did this morning?",
    "It's really windy outside today, isn't it?",
    "Have you seen the blue mug anywhere today?",
    "I think that was the doorbell just now, Pebble.",
    "Sam and I might sit in the garden after lunch.",
)
LAST_WORD_LINES = (
    "Pebble, did you see where I left the red kite",
    "I think I'll take a look at the old drum",
)
FROZEN = (CORE, "tools")
NIGHTLY = ("self", "notes", "household")
SEPARATORS = 4


@dataclass
class Year:
    people: list = field(default_factory=list)
    rooms: list = field(default_factory=list)
    spots: list = field(default_factory=list)
    things: list = field(default_factory=list)
    skills: list = field(default_factory=list)
    old_skills: list = field(default_factory=list)
    howtos: list = field(default_factory=list)
    old_howtos: list = field(default_factory=list)
    rules: list = field(default_factory=list)
    once: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)


def _names(rng: random.Random, taken: set, count: int) -> list[str]:
    out = []
    while len(out) < count:
        name = rng.choice(NAME_START) + rng.choice(NAME_END)
        if name.lower() not in taken:
            taken.add(name.lower())
            out.append(name)
    return out


def _pairs(rng: random.Random, words: tuple, count: int, plain: bool = False) -> list[str]:
    combos = [f"{a} {b}" for a in words[0] for b in words[1]]
    rng.shuffle(combos)
    out = (list(words[1]) if plain else []) + combos
    return out[:count]


def _ago(rng: random.Random, now: float, low_days: float, high_days: float) -> float:
    return now - rng.uniform(low_days, high_days) * DAY_S


def _steps(rng: random.Random, rooms: list[str], people: list[str], core: tuple | None = None) -> list[dict]:
    steps = []
    if core is not None:
        room, face, who = core
        steps = [{"do": "go_to_place", "place": room}, {"do": "face", "expression": face}, {"do": "look", "who": who.lower()}]
    for _ in range(rng.randint(2, 5) if core is None else rng.randint(0, 2)):
        kind = rng.choice(("turn", "turn", "wiggle", "face", "face", "tilt", "go_to_place", "look", "say"))
        if kind == "turn":
            steps.append({"do": "turn", "way": rng.choice(("left", "right")), "degrees": float(rng.choice((45, 90, 180)))})
        elif kind == "wiggle":
            steps.append({"do": "wiggle"})
        elif kind == "face":
            steps.append({"do": "face", "expression": rng.choice(FACES)})
        elif kind == "tilt":
            steps.append({"do": "tilt", "way": rng.choice(("up", "down")), "degrees": 15.0})
        elif kind == "go_to_place":
            steps.append({"do": "go_to_place", "place": rng.choice(rooms)})
        elif kind == "look":
            steps.append({"do": "look", "who": rng.choice(people).lower()})
        else:
            steps.append({"do": "say", "text": rng.choice(("ta-da", "hello there", "all done", "look at me", "here I go"))})
    return steps


def grow(bench: Bench, seed: int = 11, embedder=None, memories: int = MEMORIES) -> Year:
    rng = random.Random(seed)
    life = bench.life
    p = life.p
    store = p.store
    now = p.clock.now()
    day = p.clock.local(now).date()
    year = Year()
    book = life.company.book
    known = [book.find(name) for name, *_ in HOUSE.values()]
    taken = {n.lower() for n, *_ in HOUSE.values()} | {"pebble"}
    fresh = _names(rng, taken, PEOPLE - len(known))
    likes = _pairs(rng, LIKE_WORDS, 240, plain=True)
    people = []
    for n, name in enumerate(fresh):
        person = Person(f"y{n + 1}", _ago(rng, now, 200, 360), now)
        person.set_name(name)
        person.relationship = "family" if n < 4 else ("child" if n < 6 else ("friend" if n < 30 else "guest"))
        book.people[person.id] = person
        people.append(person)
    everyone = [person for person in known if person is not None] + people
    for n, person in enumerate(everyone):
        often = n < OFTEN
        person.last_seen = _ago(rng, now, 0, 1) if often else _ago(rng, now, 40, 300)
        person.last_day = p.clock.local(person.last_seen).date().isoformat()
        person.days_met = rng.randint(150, 300) if often else rng.randint(1, 20)
        person.seen_days = sorted({(day - datetime.timedelta(days=d)).isoformat() for d in rng.sample(range(0, 31), rng.randint(18, 30))}) if often else []
        if n % 3 == 0:
            person.nicknames = [person.label[:3] + "s", person.label[:2] + "bear"]
        picks = rng.sample(likes, 30 if often else 10)
        person.likes = picks[:20] if often else picks[:6]
        person.dislikes = picks[20:26] if often else picks[6:8]
        person.wishes = picks[26:30] if often else picks[8:10]
        if often:
            person.promises = [Promise(1, "them", f"bring the {rng.choice(THING_WORDS[1])} back", now + 3 * DAY_S, now - DAY_S), Promise(2, "pebble", f"remind {person.label} about the {rng.choice(THING_WORDS[1])}", now + DAY_S, now - DAY_S)]
            person.next_promise = 3
    p.books.save("people")
    year.people = everyone
    rooms = life.alive.rooms
    for n, name in enumerate(ROOMS):
        rooms.rooms[name] = Room(name, float(n % 5) * 4.0, float(n // 5) * 4.0, 1.5, (), 0.8)
    rooms.save()
    year.rooms = list(ROOMS)
    chart = life.nav.chart
    for n, name in enumerate(_pairs(rng, SPOT_WORDS, SPOTS)):
        chart.places.append(Place(f"s{n}", "spot", name, rng.uniform(0, 16), rng.uniform(0, 16), 0.4, None, [], [], rng.randint(1, 40)))
        year.spots.append(name)
    things = p.books.things
    for n, label in enumerate(_pairs(rng, THING_WORDS, THINGS)):
        seen = _ago(rng, now, 0, 30) if n < 300 else _ago(rng, now, 30, 360)
        room = rng.randrange(len(ROOMS))
        thing = Thing(label, False, seen - DAY_S, rng.randint(1, 40))
        thing.spots = [Spot(seen, "front", float(room % 5) * 4.0 + rng.uniform(-1, 1), float(room // 5) * 4.0 + rng.uniform(-1, 1), 1.0, [], 0.8, "fast", 1)]
        things.things[label] = thing
        year.things.append(label)
    for name, where in FACT_NAMES:
        things.facts.told[name] = Told(name, where, known[0].id, known[0].label, now - 200 * DAY_S, now - 200 * DAY_S)
    p.books.save("things")
    skills = life.skills
    index = {}
    names = _pairs(rng, SKILL_WORDS, SKILLS)
    labels = [person.label for person in everyone[:OFTEN]]
    cores = [(room, face, who) for room in ROOMS for face in FACES for who in labels]
    rng.shuffle(cores)
    for n, name in enumerate(names):
        steps = _steps(rng, list(ROOMS), labels, cores[n])
        if n < 60:
            learned, used = _ago(rng, now, 30, 300), _ago(rng, now, 0, 25)
        elif n < 130:
            learned, used = _ago(rng, now, 60, 300), _ago(rng, now, 40, 170)
        else:
            learned = _ago(rng, now, 300, 345)
            used = learned
        teacher = everyone[n % OFTEN]
        skill = Skill(name, steps, [name, name.split(" ")[-1] + " " + name.split(" ")[0]], kind_of(steps), said(steps)[:160], skills.body, {"id": teacher.id, "name": teacher.label, "tier": "trusted"}, iso(learned), [], rng.randint(0, 9), rng.randint(0, 2), iso(used))
        store.write(f"{skills._root()}/{slug(name)}.json", skill.as_dict())
        index[slug(name)] = {"name": skill.name, "aliases": skill.aliases, "kind": skill.kind, "about": skill.about, "good": skill.good, "bad": skill.bad, "last_used": skill.last_used}
        year.skills.append(skill)
        if n >= 130:
            year.old_skills.append(skill)
    skills._save_index(index)
    skills.reload()
    _howtos(life, rng, now, everyone, year)
    programs = Book(store, p.clock)
    pool = starters()
    for n in range(SCRIPTS_MOST):
        starter = pool[n % len(pool)]
        header = read(starter.source).header.as_dict()
        person = everyone[n % OFTEN] if header.get("FOR") else None
        entry = programs.add(f"{rng.choice(SKILL_WORDS[0])} {starter.name} {n + 1}", starter.source, header, person.id if person is not None else None, person.label if person is not None else "", person.id if person is not None else None, "", True)
        entry.update({"last_used": iso(_ago(rng, now, 0, 300)), "used": rng.randint(0, 20), "good": rng.randint(1, 9), "good_version": 1, "status": "live" if n < 15 else ("ended" if person is not None else "retired")})
    programs.save()
    scripts = programs.scripts
    lessons = []
    for n in range(LESSONS_MOST):
        template = LESSON_TEXTS[n % len(LESSON_TEXTS)]
        person = everyone[rng.randrange(len(everyone))]
        room = rng.choice(ROOMS)
        scope = f"place:{room}" if "{room}" in template else (f"person:{person.id}" if "{name}" in template else "self")
        at = _ago(rng, now, 0, 360)
        used = at + rng.uniform(0, max(0.0, now - at))
        lessons.append({"id": f"l{n + 1}", "text": template.format(room=room, name=person.label), "scope": scope, "helpful": rng.randint(2, 9), "harmful": rng.randint(0, 2), "at": iso(at), "used_at": iso(used)})
    store.write(LESSONS, {"format": 1, "items": lessons})
    rules = life.rules
    ina = known[0]
    for n in range(RULES_MOST):
        if n < 24:
            rule = Rule(rules.next_id, "keep_out", ROOMS[(n + 3) % len(ROOMS)], ina.id, ina.label, "trusted", now - 60 * DAY_S, now - 60 * DAY_S)
        else:
            rule = Rule(rules.next_id, "quiet", "", ina.id, ina.label, "trusted", now - 30 * DAY_S, now - 30 * DAY_S, window=["22:00", "07:00"] if n % 2 else ["13:00", "14:00"])
        rules.next_id += 1
        rules.rules.append(rule)
        year.rules.append(rule)
    rules.save(force=True)
    taught = life.house.taught
    if taught.np is not None:
        np = taught.np
        for n, name in enumerate(SOUND_NAMES[:SOUNDS_MOST]):
            view = View(np.asarray([rng.random() for _ in range(40)], dtype=np.float32))
            sound = Sound(slug(name), name, ina.id, now - rng.uniform(10, 300) * DAY_S, [[view]], rng.randint(1, 80), 0, 0, now - rng.uniform(0, 60) * DAY_S)
            taught.sounds[sound.key] = sound
    agenda = life.later.agenda
    for n in range(AGENDA_MOST):
        person = everyone[n % OFTEN]
        at = now + (rng.uniform(10, 50) * 60 if n < 3 else rng.uniform(2, 29) * DAY_S)
        local = p.clock.local(at)
        text = f"check the {rng.choice(THING_WORDS[1])} {n + 1}"
        request = {"kind": "say_to", "who": "me", "text": text, "when": {"at": local.strftime("%H:%M")}}
        agenda.items.append(Item(agenda.next_id, request, person.id, person.label, "trusted", now - DAY_S, "reminder", person.id, [], at, words=text))
        agenda.next_id += 1
    agenda.save(force=True)
    notes = life.memory.notes
    k = 0
    while True:
        result = notes.apply({"op": "add", "text": f"{everyone[k % OFTEN].label} likes the {rng.choice(ROOMS)} best on {rng.choice(('Sundays', 'rainy days', 'cold mornings', 'warm evenings'))}, and often reads there."})
        k += 1
        if not result.get("ok") or k > 40:
            break
    notes.swap()
    _remember(life, rng, now, everyone, embedder or life.memory.recall.embedder, memories)
    year.once = [spot for spot in year.spots[:10]] + [room for room in ROOMS[15:25]]
    year.counts = {"howto": len(life.teaching.book.index), "people": len(book.people), "rooms": len(ROOMS), "spots": len(year.spots), "things": len(things.things), "facts": len(things.facts.told), "skills": len(skills.all()), "scripts": len(scripts), "lessons": len(lessons), "rules": len(rules.rules), "sounds": len(taught.sounds), "agenda": len(agenda.items), "memories": len(life.memory.recall.stream) + len(life.memory.recall.stream.archive), "notes_chars": notes.used()}
    return year


def _howtos(life, rng: random.Random, now: float, everyone: list, year: Year) -> None:
    book = life.teaching.book
    names = _pairs(rng, HOWTO_WORDS, HOWTO)
    pairs = [(room, thing) for room in ROOMS for thing in THING_WORDS[1]]
    rng.shuffle(pairs)
    for n, (name, kind) in enumerate(zip(names, HOWTO_KINDS)):
        teacher = everyone[n % OFTEN]
        if n % 10 < 3:
            learned, used = _ago(rng, now, 30, 300), _ago(rng, now, 0, 25)
        elif n % 10 < 7:
            learned, used = _ago(rng, now, 60, 300), _ago(rng, now, 40, 170)
        else:
            learned = _ago(rng, now, 300, 345)
            used = learned
        room, thing = pairs[n]
        entry = HowEntry(name, kind, aliases=[name.split(" ")[-1] + " " + name.split(" ")[0]], taught_by={"id": teacher.id, "name": teacher.label, "tier": "trusted"}, learned_at=iso(learned), last_used=iso(used), good=rng.randint(0, 9), bad=rng.randint(0, 2), runs=rng.randint(1, 20), body=life.skills.body)
        if kind == "procedure":
            entry.steps = [{"do": "request", "request": {"kind": "go_to_place", "place": room}}, {"do": "request", "request": {"kind": "look", "thing": thing}}, {"do": "request", "request": {"kind": "come", "who": "me"}}]
            entry.about = said_steps(entry.steps)
            entry.examples = [{"steps": list(entry.steps), "by": teacher.id, "tier": "trusted", "at": iso(learned), "ways": ["said"]}]
        elif kind == "route":
            x, y = float(ROOMS.index(room) % 5) * 4.0, float(ROOMS.index(room) // 5) * 4.0
            entry.points = [[round(x + 0.3 * k, 2), round(y + 0.2 * k, 2), room] for k in range(12)]
            entry.rooms = [room]
            entry.about = f"the way to the {room} past the {thing}"
        elif kind == "concept":
            entry.look = "place" if n % 2 else "thing"
            entry.prints = [{"v": pack_print([rng.gauss(0.0, 1.0) for _ in range(384)]), "yes": True} for _ in range(3)]
            entry.line = f"the {thing} in the {room}"
            entry.about = f"what the {thing} in the {room} looks like"
        elif kind == "word":
            entry.words = f"go to the {room} and look at the {thing}"
            entry.about = f"when someone says {name}, go to the {room} and look at the {thing}"
        elif kind in ("habit", "way"):
            entry.trigger = {"event": "sound", "thing": "doorbell"} if kind == "habit" else {"event": "arrives", "who": "me"}
            entry.person = teacher.id if kind == "way" else None
            entry.steps = [{"do": "request", "request": {"kind": "go_to_place", "place": room}}, {"do": "request", "request": {"kind": "look", "thing": thing}}]
            entry.about = said_steps(entry.steps)
        book.put(entry)
        year.howtos.append((entry, room, thing))
        if n % 10 >= 7:
            year.old_howtos.append((entry, room, thing))


def _remember(life, rng: random.Random, now: float, everyone: list, embedder, count: int) -> None:
    stream = life.memory.recall.stream
    texts = []
    for n in range(count):
        kind, template = MEMORY_TEXTS[n % len(MEMORY_TEXTS)]
        person = everyone[rng.randrange(len(everyone))]
        text = template.format(name=person.label, room=rng.choice(ROOMS), thing=rng.choice(THING_WORDS[1]))
        t = now - (n / count) * YEAR_DAYS * DAY_S - rng.uniform(0, 3600)
        private = n % 5 < 2
        record = Record(
            id=f"m{n + 1}",
            t=t,
            kind=kind,
            text=text,
            by="person" if kind == "said" else "self",
            who=person.id if kind == "said" else None,
            about=(person.id,),
            mark="private" if private or kind == "said" else "",
            audience=(person.id,) if private or kind == "said" else (),
            importance=rng.choice((3, 4, 4, 5, 5, 6, 7)),
        )
        stream.records[record.id] = record
        texts.append((record.id, text))
    stream.counter = max(stream.counter, count)
    batch = 256
    for start in range(0, len(texts), batch):
        chunk = texts[start:start + batch]
        rows = embedder.embed([t for _, t in chunk], False)
        for (record_id, _), row in zip(chunk, rows):
            stream.vectors[record_id] = pack(row)
    stream.model = embedder.name
    stream.dim = len(next(iter(stream.vectors.values()))) // 2 if stream.vectors else 0
    stream.waiting = set()
    stream.unsaved = []
    stream.dirty = True
    stream.vectors_dirty = True
    stream.shelve(now)
    stream.save()


async def settle(bench: Bench) -> None:
    life = bench.life
    selection = life.selection
    selection.stale()
    for _ in range(200):
        if not selection.wants_work():
            break
        await selection.work(life.memory.recall.embedder, lambda: True)
    selection.night(life.p.clock.now())
    await life.memory.refresh()
    life.memory.swap_ahead()


def sized(prompt, tools, room: int, window: int, ruler: Ruler | None, counter: Counter) -> dict:
    sections: dict = {}
    for piece in pieces(prompt, tools):
        if piece.section == "tools":
            count = (ruler.counter.rendered(tools) if ruler is not None else None) or counter.estimate(piece.text)
        else:
            count = ruler.tokens(piece.text) if ruler is not None else counter.estimate(piece.text)
        sections[piece.section] = sections.get(piece.section, 0) + count + (0 if ruler is not None else piece.overhead)
    rows: dict = {}
    for section, count in sections.items():
        rows[row(section)] = rows.get(row(section), 0) + count
    whole = ruler.rendered(list(prompt), tools) if ruler is not None else sum(sections.values())
    table = budgets(prompt.kind, window)
    over = sorted(name for name, count in rows.items() if name not in (HISTORY, ROOM, WORK) and name in table and count > table[name])
    return {"kind": prompt.kind, "sections": {k: sections[k] for k in SECTION_ORDER if k in sections}, "rows": rows, "whole": whole, "room": room, "over": over, "fits": whole + room <= window}


async def every_call(bench: Bench, profile: ModelProfile) -> dict:
    out = await build(bench, profile)
    life = bench.life
    ina = bench.ids["ina"]
    heard = SimpleNamespace(person_id=ina, text="could you go to the kitchen and see if the oven is still on")
    ctx = life.commands.context(heard)
    out["reader"] = (with_laws(reader_messages(heard.text, ctx, life.p.books.name)), None, 160)
    return out


async def measure(bench: Bench, ruler: Ruler | None) -> dict:
    profile = ModelProfile.load(PROFILE)
    counter = Counter(None, profile.chars_per_token)
    report = {}
    for window in WINDOWS:
        profile.served["context"] = window
        built = await every_call(bench, profile)
        guard = Guard(counter, lambda window=window: window, profile.max_reply_tokens)
        found = {}
        for name, (prompt, tools, room) in built.items():
            data = sized(prompt, tools, room, window, ruler, counter)
            fit = guard.fit(prompt, tools, prompt.kind, room)
            data["guard"] = {"trimmed": fit.trimmed, "over": fit.over, "refused": fit.refused}
            found[name] = data
        turn = found["turn"]
        fixed = sum(v for k, v in turn["sections"].items() if k not in (HISTORY, TASK, WORK))
        top = ceiling(TURN, window)
        found["share"] = {"of_window": round((top - fixed - turn["room"]) / window, 3), "of_ceiling": round((top - fixed - turn["room"]) / top, 3)}
        report[window] = found
    return report


async def fresh_reads(bench: Bench, ruler: Ruler | None, lines: tuple = REPLY_LINES) -> dict:
    life = bench.life
    p = life.p
    conv = bench.conversation
    profile = ModelProfile.load(PROFILE)
    profile.served["context"] = 8192
    bench.use(profile)
    p.turns.history.profile = profile
    counter = Counter(None, profile.chars_per_token)
    out = []
    for line in lines:
        bench.here({"ina", "sam"})
        conv.window.clear()
        pid = bench.ids["ina"]
        words = line.split()
        turn = Turn(id=0, started=conv.mono(), speaker=pid, label="Ina")
        early, early_private = conv._observation(turn, " ".join(words[:-1]), pid)
        _, warm, _ = p.turns._reply_messages(early, life.stage(p.clock.local()), p.books.values.describe(), life.company.prompt_text(p.clock.now(), p.clock.local), early_private, life.company.private_to(p.clock.now()), "warm")
        final, final_private = conv._observation(turn, line, pid)
        _, real, _ = p.turns._reply_messages(final, life.stage(p.clock.local()), p.books.values.describe(), life.company.prompt_text(p.clock.now(), p.clock.local), final_private, life.company.private_to(p.clock.now()), "reply")
        p.turns._ahead = None
        a, b = with_laws(warm), with_laws(real)
        if ruler is not None:
            first = ruler.counter.post("/apply-template", {"messages": [dict(m) for m in a]})["prompt"]
            second = ruler.counter.post("/apply-template", {"messages": [dict(m) for m in b]})["prompt"]
            ta = ruler.counter.post("/tokenize", {"content": first}).get("tokens") or []
            tb = ruler.counter.post("/tokenize", {"content": second}).get("tokens") or []
            same = 0
            for x, y in zip(ta, tb):
                if x != y:
                    break
                same += 1
            fresh = len(tb) - same
        else:
            first = "".join(str(m.get("content") or "") for m in a)
            second = "".join(str(m.get("content") or "") for m in b)
            same = 0
            for x, y in zip(first, second):
                if x != y:
                    break
                same += 1
            fresh = counter.estimate(second[same:])
        out.append(fresh)
    mean = statistics.mean(out)
    return {"fresh_tokens": out, "mean": round(mean, 1), "pixel_s": [round(mean / 25 * 0.6, 2), round(mean / 25 * 1.0, 2)]}


def questions(bench: Bench, year: Year) -> list[dict]:
    rng = random.Random(5)
    out = []
    for skill in rng.sample(year.skills[:130], 10) + rng.sample(year.old_skills, 10):
        out.append({"kind": "skill_by_name", "say": f"Pebble, do the {skill.name}", "want": skill.name})
    for skill in rng.sample(year.skills, 10) + rng.sample(year.old_skills, 10):
        room, face, who = skill.steps[0]["place"], skill.steps[1]["expression"], skill.steps[2]["who"].title()
        out.append({"kind": "skill_by_description", "say": f"do that one where you go to the {room}, make a {face} face and look at {who}", "want": skill.name})
    house = [bench.life.company.book.find(name) for name, *_ in HOUSE.values()]
    others = year.people[len(house):]
    for n in range(20):
        person = house[n % 2] if n < 10 else others[n]
        like = rng.choice(person.likes)
        out.append({"kind": "persons_like", "say": f"does {person.label} still like {like}?", "want": like, "here": n < 10, "who": person.id})
    rooms = sorted({rule.place for rule in year.rules if rule.kind == "keep_out"})
    for n in range(20):
        room = rooms[n % len(rooms)]
        out.append({"kind": "room_rule", "say": "can you have a look around in here?", "want": f"keep out of the {room}", "room": room})
    for n, place in enumerate(year.once[:20]):
        out.append({"kind": "place_once", "say": f"Pebble, go to the {place}", "want": place})
    return out


def howto_questions(year: Year) -> list[dict]:
    rng = random.Random(9)
    fresh = [item for item in year.howtos if item not in year.old_howtos]
    out = []
    for entry, room, thing in rng.sample(fresh, 10) + rng.sample(year.old_howtos, 10):
        out.append({"kind": "howto_by_name", "say": f"Pebble, do the {entry.name}", "want": entry.name})
    procedures = [item for item in year.howtos if item[0].kind == "procedure"]
    old = [item for item in procedures if item in year.old_howtos]
    for entry, room, thing in rng.sample([p for p in procedures if p not in old], 10) + rng.sample(old, 10):
        out.append({"kind": "howto_by_description", "say": f"do that one where you go to the {room} and look at the {thing}", "want": entry.name})
    return out


def howto_found(bench: Bench, question: dict) -> bool:
    teaching = bench.life.teaching
    want = question["want"].lower()
    if question["kind"] == "howto_by_name":
        found = teaching.book.find(question["say"])
        return found is not None and found[0].name.lower() == want
    return any(line.lower().startswith(want + " (") for line in teaching.lookup(question["say"]))


def found(bench: Bench, question: dict) -> bool:
    life = bench.life
    p = life.p
    want = question["want"].lower()
    kind = question["kind"]
    say = question["say"]
    if kind == "skill_by_name":
        lines = " ".join(line for _, line in life.named(say, REPLY)).lower()
        skill = life.skills.find(say)
        return want in lines or (skill is not None and skill.name.lower() == want)
    if kind == "skill_by_description":
        listed = life.commands.trying.listed(say).lower()
        return want in listed
    if kind == "persons_like":
        bench.here({"ina", "sam"} if question["here"] else {"tui"})
        text = life.company.prompt_text(p.clock.now(), p.clock.local) + "\n" + "\n".join(line for _, line in life.named(say, REPLY))
        return want in text.lower()
    if kind == "room_rule":
        original = life.rules.here
        life.rules.here = lambda: question["room"]
        try:
            return want in life.matched(REPLY).lower()
        finally:
            life.rules.here = original
    if kind == "place_once":
        ctx = life.commands.context(SimpleNamespace(person_id=bench.ids["ina"], text=say))
        line = next((text for section, text in ctx.parts() if text.startswith("Places known: ")), "")
        return want in line.lower()
    return False


def scan_times(bench: Bench, lines: list[str]) -> dict:
    selection = bench.life.selection
    selection.stale()
    started = time.perf_counter()
    index = selection.names()
    build_s = time.perf_counter() - started
    times = []
    for line in lines:
        started = time.perf_counter()
        index.scan(line)
        times.append(time.perf_counter() - started)
    return {"names": sum(len(e.names) for e in index.entries), "build_ms": round(build_s * 1000, 1), "mean_us": round(statistics.mean(times) * 1e6, 1), "max_us": round(max(times) * 1e6, 1)}


async def run(main: str | None, real: bool, memories: int, out: str) -> dict:
    counter = Counter(main, 3.0) if main else None
    ruler = None
    if counter is not None:
        if counter.real("ready") is None:
            raise SystemExit(f"no llama-server answers /tokenize at {main}")
        ruler = Ruler(counter)
    embedder = embedder_from("auto") if real else StandIn()
    report: dict = {}
    with tempfile.TemporaryDirectory(prefix="pebble-year-", ignore_cleanup_errors=True) as folder:
        new = Bench(Path(folder) / "new", 120)
        await new.setup()
        new.life.memory.recall.embedder = embedder
        new.life.skills.embedder = embedder
        new.life.teaching.book.embedder = embedder
        await settle(new)
        report["new"] = await measure(new, ruler)
        report["new_fresh"] = await fresh_reads(new, ruler)
        report["new_last_word"] = await fresh_reads(new, ruler, LAST_WORD_LINES)
        await new.close()
        old = Bench(Path(folder) / "year", 400)
        await old.setup()
        old.life.memory.recall.embedder = embedder
        old.life.skills.embedder = embedder
        old.life.teaching.book.embedder = embedder
        started = time.perf_counter()
        year = grow(old, embedder=embedder, memories=memories)
        await settle(old)
        report["grown_s"] = round(time.perf_counter() - started, 1)
        report["counts"] = year.counts
        builder = old.life.p.turns.builder
        report["caps"] = {"notes": old.life.memory.notes.used() <= NOTES_CHARS, "household": len(builder.household_text()) <= HOUSEHOLD_CHARS}
        report["year"] = await measure(old, ruler)
        report["year_fresh"] = await fresh_reads(old, ruler)
        report["year_last_word"] = await fresh_reads(old, ruler, LAST_WORD_LINES)
        asked = questions(old, year)
        right = {}
        for question in asked:
            hit = found(old, question)
            right.setdefault(question["kind"], [0, 0])
            right[question["kind"]][0] += 1 if hit else 0
            right[question["kind"]][1] += 1
        report["finding"] = {"right": sum(v[0] for v in right.values()), "of": len(asked), "by_kind": right}
        taught = {}
        for question in howto_questions(year):
            hit = howto_found(old, question)
            taught.setdefault(question["kind"], [0, 0])
            taught[question["kind"]][0] += 1 if hit else 0
            taught[question["kind"]][1] += 1
        report["howto_finding"] = taught
        report["scan"] = scan_times(old, [q["say"] for q in asked] + list(REPLY_LINES))
        await old.close()
    report["counted"] = "tokenizer" if ruler is not None else "estimate"
    report["passed"] = passed(report)
    if out:
        Path(out).write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return report


def passed(report: dict) -> dict:
    out = {}
    estimate = report["counted"] == "estimate"
    for window in WINDOWS:
        year = report["year"][window]
        new = report["new"][window]
        calls = {k: v for k, v in year.items() if k != "share"}

        def fine(name: str, data: dict, section: str) -> bool:
            if section in FROZEN and abs(data["rows"].get(section, 0) - new[name]["rows"].get(section, 0)) <= SEPARATORS:
                return True
            return estimate and section in NIGHTLY and bool(report["caps"].get(section))

        out[f"sections_{window}"] = all(all(fine(name, data, r) for r in data["over"]) for name, data in calls.items())
        out[f"window_{window}"] = all(data["fits"] and not data["guard"]["refused"] for data in calls.values())
        out[f"room_{window}"] = year["share"]["of_ceiling"] >= 0.45
    out["finding"] = report["finding"]["right"] >= 0.95 * report["finding"]["of"]
    taught = report.get("howto_finding") or {}
    if taught:
        by_name, by_description = taught.get("howto_by_name", [0, 1]), taught.get("howto_by_description", [0, 1])
        out["howto_by_name"] = by_name[0] == by_name[1]
        out["howto_by_description"] = by_description[0] >= 0.9 * by_description[1]
    new_s, year_s = report["new_fresh"]["mean"], report["year_fresh"]["mean"]
    out["speed"] = year_s <= new_s * 1.1
    return out


def show(report: dict) -> None:
    print(f"counted with the {report['counted']}; the year-old self took {report['grown_s']} s to build: {report['counts']}")
    for window in WINDOWS:
        print(f"\nwindow {window}")
        for name in report["year"][window]:
            if name == "share":
                continue
            new, year = report["new"][window][name], report["year"][window][name]
            keys = [k for k in SECTION_ORDER if k in new["sections"] or k in year["sections"]]
            shown = ", ".join(f"{k} {new['sections'].get(k, 0)}/{year['sections'].get(k, 0)}" for k in keys)
            print(f"  {name}: whole {new['whole']}/{year['whole']} | {shown}" + (f" | over {year['over']}" if year["over"] else ""))
        print(f"  history and task share of a life turn: new {report['new'][window]['share']}, year {report['year'][window]['share']}")
    print(f"\nfresh tokens after read-ahead: new {report['new_fresh']['mean']} ({report['new_fresh']['pixel_s']} s), year {report['year_fresh']['mean']} ({report['year_fresh']['pixel_s']} s)")
    print(f"when the last word names a stored item: new {report['new_last_word']['fresh_tokens']}, year {report['year_last_word']['fresh_tokens']}")
    print(f"finding: {report['finding']['right']} of {report['finding']['of']} {report['finding']['by_kind']}")
    print(f"how-to book: {report.get('howto_finding')}")
    print(f"scan: {report['scan']}")
    print(f"passed: {report['passed']}")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(prog="python -m pebble.sim.year_self", description="Build a made-up self as full as a busy year, run every kind of call against it and a new self, and check the prompt budget holds: sizes per section, room for history, finding things and the fresh read after read-ahead.")
    parser.add_argument("--main", default="", help="a llama-server URL to count tokens with (otherwise the estimate)")
    parser.add_argument("--real", action="store_true", help="use the real sentence model for every memory and item (slower)")
    parser.add_argument("--memories", type=int, default=MEMORIES, help="how many memory records the year-old self has")
    parser.add_argument("--out", default="", help="write the full report as JSON here")
    args = parser.parse_args(argv)
    report = asyncio.run(run(args.main or None, args.real, args.memories, args.out))
    show(report)
    return 0 if all(report["passed"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
