import math
import time

from conftest import run

from pebble.activities.card import said
from pebble.alive.rooms import Room
from pebble.mind.base import MindReply
from pebble.mind.budget import MATCHED, REPLY, TURN
from pebble.mind.prompt import HOUSEHOLD_CHARS, TURN_GUIDE, PromptBuilder
from pebble.mind.select import COLD, HOT, WARM, Entry, Names, Shelves, chosen_chars, named_chars, unknown_names, word_list
from pebble.people.book import PeopleBook
from pebble.people.person import Person
from pebble.people.presence import Presence
from pebble.people.prompt import ALSO, people_text
from pebble.self.notes import Notes
from pebble.self.recall.core import Recall
from pebble.self.recall.embed import StandIn
from pebble.self.recall.stream import Stream
from pebble.self.tidy import tidy

DAY = 86400.0
STEPS = [{"do": "turn", "way": "left", "degrees": 90.0}, {"do": "wiggle"}, {"do": "face", "expression": "happy"}]


def entries() -> list[Entry]:
    return [
        Entry("person", "p1", ("Ina", "Neens")),
        Entry("person", "p2", ("Mo",)),
        Entry("room", "laundry", ("laundry",)),
        Entry("spot", "front door", ("front door",)),
        Entry("thing", "red ball", ("red ball",)),
        Entry("skill", "evening-round", ("evening round", "round the house")),
        Entry("list", "shopping", ("shopping", "shopping list")),
        Entry("sound", "doorbell", ("the doorbell", "doorbell")),
    ]


def test_naming_finds_every_kind_by_name_alias_plural_possessive_and_a_slip():
    names = Names(entries())
    found = [h.entry.key for h in names.scan("Can you do the evening round and then check the front door?")]
    assert found == ["evening-round", "front door"]
    assert [h.entry.key for h in names.scan("where are Ina's red balls")] == ["p1", "red ball"]
    assert [h.entry.key for h in names.scan("please put it in the laundy")] == ["laundry"]
    assert [h.entry.key for h in names.scan("Neens wants milk on the shopping list")] == ["p1", "shopping"]
    assert [h.entry.key for h in names.scan("Mo heard the doorbell")] == ["p2", "doorbell"]
    assert names.scan("I would rather not, maybe later") == []
    assert names.scan("me and my room") == []


def test_a_scan_of_a_year_of_names_costs_microseconds_not_more_than_a_millisecond():
    big = [Entry("person", f"p{n}", (f"Person{n}", f"Pal{n}")) for n in range(60)]
    big += [Entry("room", f"room {n}", (f"room {n}",)) for n in range(80)]
    big += [Entry("thing", f"thing {n}", (f"shiny gadget {n}",)) for n in range(800)]
    big += [Entry("skill", f"s{n}", (f"skill number {n}", f"trick {n}", f"move {n}")) for n in range(200)]
    names = Names(big)
    line = "Pebble, could you take the shiny gadget 12 to Person7 in room 3 and then do trick 44 for us"
    started = time.perf_counter()
    for _ in range(200):
        hits = names.scan(line)
    took = (time.perf_counter() - started) / 200
    assert {h.entry.key for h in hits} >= {"thing 12", "p7", "room 3", "s44"}
    assert took < 0.001


def test_shelves_move_up_with_use_and_down_after_months_and_never_drop_an_item(store, clock):
    shelves = Shelves(store, clock)
    now = clock.now()
    fresh, old, older = Entry("thing", "a", ("a",), t=now - DAY), Entry("thing", "b", ("b",), t=now - 60 * DAY), Entry("thing", "c", ("c",), t=now - 300 * DAY)
    report = shelves.sort([fresh, old, older], now)
    assert (shelves.shelf(fresh), shelves.shelf(old), shelves.shelf(older)) == (HOT, WARM, COLD)
    assert report[HOT] == report[WARM] == report[COLD] == 1
    shelves.use(older, now)
    assert shelves.shelf(older) == HOT
    clock.advance(200 * DAY)
    report = shelves.sort([fresh, old, older])
    assert shelves.shelf(older) == COLD and report["down"] >= 2
    again = Shelves(store, clock)
    assert again.shelf(older) == COLD and len(again.items) == 3


def stream_with(store, clock, texts, days, about=(), weight=4):
    recall = Recall(store, clock, StandIn())
    now = clock.now()
    for text, ago in zip(texts, days):
        recall.keep(text, "happened", about=about, weight=weight, at=now - ago * DAY)
    run(recall.work(lambda: True))
    return recall


def test_cold_memories_are_archived_not_deleted_and_found_only_when_asked_for_old_things(store, clock):
    recall = stream_with(store, clock, ["We had a picnic by the lake with the blue blanket.", "The kettle boiled this morning."], [300, 1])
    stream = recall.stream
    report = stream.shelve(clock.now())
    assert len(stream) == 1 and len(stream.archive) == 1 and report["archived"] == 1
    assert not any("picnic" in note for note in run(recall.think_back("do you remember the picnic by the lake?", frozenset())))
    found = run(recall.think_back("do you remember the picnic by the lake last year?", frozenset()))
    assert any("picnic" in note for note in found)
    stream.shelve(clock.now())
    assert len(stream) == 2 and len(stream.archive) == 0
    again = Stream(store, clock)
    assert len(again) == 2 and len(again.archive) == 0


def test_forget_and_unremember_reach_the_archive_at_once(store, clock):
    recall = Recall(store, clock, StandIn())
    now = clock.now()
    recall.keep("Rewa brought her kite to the beach.", "happened", about=("p9",), at=now - 300 * DAY, weight=5)
    recall.keep("The green umbrella broke in the wind.", "happened", at=now - 300 * DAY, weight=5)
    run(recall.work(lambda: True))
    stream = recall.stream
    stream.shelve(now)
    assert len(stream.archive) == 2
    assert stream.forget("p9", ["Rewa"]) == 1 and len(stream.archive) == 1
    assert stream.matching("the green umbrella") == 1
    assert stream.unremember("the green umbrella") == 1 and len(stream.archive) == 0


def test_past_the_cap_memories_go_to_the_archive_instead_of_being_deleted(store, clock, monkeypatch):
    import pebble.self.recall.stream as stream_module

    monkeypatch.setattr(stream_module, "MOST", 5)
    recall = stream_with(store, clock, [f"Something small happened on day {n} with the yellow cup." for n in range(8)], [40 + n for n in range(8)])
    stream = recall.stream
    stream.shelve(clock.now())
    assert len(stream) == 5 and len(stream.archive) == 3


def test_night_folds_small_memories_about_one_person_into_one_line_with_pointers(store, clock):
    texts = [f"Events: Sam fixed the {thing} in the garage." for thing in ("bike", "gate", "lamp", "fence", "tap", "drawer")]
    recall = stream_with(store, clock, texts, [40, 45, 50, 55, 60, 65], about=("p3",), weight=3)
    stream = recall.stream
    stream.shelve(clock.now())
    made = stream.fold(clock.now(), {"p3": "Sam"})
    assert len(made) == 1
    fold = made[0]
    assert fold.text.startswith("About Sam: ") and len(fold.src) >= 2 and fold.about == ("p3",)
    for piece in fold.text[len("About Sam: "):].split("; "):
        assert any(piece.rstrip(".") in text for text in texts)
    assert len(stream.archive) == len(fold.src) and len(stream) == 1 + 6 - len(fold.src)
    stream.forget("p3", ["Sam"])
    assert len(stream) == 0 and len(stream.archive) == 0


def test_exact_duplicates_merge_into_one_stronger_memory(store, clock):
    recall = Recall(store, clock, StandIn())
    for _ in range(3):
        recall.keep("The cat sat on the warm windowsill.", "happened", weight=4)
    stream = recall.stream
    assert stream.dedupe() == 2 and len(stream) == 1
    assert next(iter(stream.records.values())).strength == 3


class OneNote:
    name = "scripted"

    def __init__(self, text):
        self.text = text

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        return MindReply('{"op": "add", "text": "' + self.text + '"}')


def test_a_note_written_by_the_model_may_only_name_what_exists(store, clock):
    assert unknown_names("Ina said Bob likes tea.", ["Ina"], "Ina said Sam likes tea.") == ["Bob"]
    assert unknown_names("Ina said Sam likes tea on Sunday.", ["Ina"], "Ina said Sam likes tea.") == []
    assert unknown_names("Pebble likes the Kitchen in March.", ["kitchen"]) == []
    notes = Notes(store)
    recall = Recall(store, clock, StandIn())
    recall.keep("The plumber fixed the dripping tap today.", "happened", weight=6)
    report = run(tidy(notes, recall.stream, StandIn(), OneNote("Rewi the plumber fixed the tap."), lambda: ["Ina", "Sam"]))
    assert report["refused"] and "Rewi" in report["refused"][0]["error"] and not notes.items
    clock.advance(60)
    recall.keep("Sam fixed the kitchen gate today.", "happened", weight=6)
    report = run(tidy(notes, recall.stream, StandIn(), OneNote("Sam fixed the kitchen gate."), lambda: ["Ina", "Sam"]))
    assert notes.items and notes.items[0]["from"]


def person(book: PeopleBook, pid: str, name: str, likes: list[str], relationship="friend") -> Person:
    found = Person(pid, 0.0, 0.0)
    found.set_name(name)
    found.relationship = relationship
    found.likes = list(likes)
    book.people[pid] = found
    return found


def test_people_here_describes_four_at_most_by_focus_and_chooses_likes_by_the_talk(clock):
    book = PeopleBook({}, clock)
    presence = Presence()
    now = clock.now()
    for n in range(6):
        person(book, f"p{n}", f"Friend{n}", [f"old hobby {k}" for k in range(20)] + ["cricket on sundays"] if n == 5 else [f"thing {k}" for k in range(3)])
        presence.saw(f"p{n}", now)
    text = people_text(book, presence, now, clock.local, focus=("p5",), talk="does Friend5 still like cricket?")
    described = [line for line in text.split("\n") if line.startswith("- ")]
    assert 1 <= len(described) <= 4 and any(line.startswith("- Friend5") for line in described)
    assert "cricket on sundays" in text and ALSO in text
    for line in described:
        assert math.ceil(len(line) / 3.0 * 1.05) <= 60
    assert math.ceil(len(text) / 3.0 * 1.05) <= 250
    assert "may ask you for" in text and "equally warm" in text


def test_household_names_are_family_first_then_the_month_and_change_only_at_night(store, clock):
    builder = PromptBuilder(store)
    today = clock.local().date().isoformat()
    people = [
        {"id": "p1", "names": ["Ina"], "relationship": "owner", "first_met": 1.0},
        {"id": "p2", "names": ["Sam"], "relationship": "friend", "first_met": 2.0, "seen_days": [today]},
        {"id": "p3", "names": ["Old"], "relationship": "friend", "first_met": 3.0, "seen_days": ["2025-01-01"]},
    ] + [{"id": f"q{n}", "names": [f"Visitor{n}"], "relationship": "guest", "first_met": 10.0 + n, "seen_days": [today] * 1} for n in range(20)]
    store.write("people.json", {"people": people})
    first = builder.household_text()
    assert first.startswith("People you know: Ina (owner), Sam (friend)") and "Old" not in first and len(first) <= HOUSEHOLD_CHARS
    people.append({"id": "p4", "names": ["Newcomer"], "relationship": "family", "first_met": 50.0})
    store.write("people.json", {"people": people})
    assert builder.household_text() == first
    assert builder.plan_household() and builder.household_text() == first
    assert builder.swap_household() and builder.household_text().startswith("People you know: Ina (owner), Newcomer (family), Sam (friend)")
    builder.forget_household("p2")
    assert "Sam" not in builder.household_text()


def test_the_system_text_keeps_the_turn_guide_after_the_self_and_the_night_parts_last(store):
    builder = PromptBuilder(store)
    store.write("people.json", {"people": [{"id": "p1", "names": ["Ina"], "relationship": "owner"}]})
    parts = builder.system_parts("adult", "Values: kindness.", "Notes you keep: - tea", household=builder.household_text())
    sections = [section for section, _ in parts]
    guide = next(n for n, (_, text) in enumerate(parts) if text == TURN_GUIDE)
    assert sections[0] == "core" and guide > max(n for n, section in enumerate(sections) if section == "self")
    assert sections[-2:] == ["notes", "household"]


def test_rooms_for_the_reader_are_named_first_then_here_then_most_used(rig_factory):
    rig = rig_factory()
    life = rig.life
    rooms = [f"room{n}" for n in range(20)] + ["cellar", "attic"]
    for n, name in enumerate(rooms):
        life.alive.rooms.rooms[name] = Room(name, float(n), 0.0, 1.0, (), 0.8)
    life.alive.rooms.save()
    life.selection.stale()
    for _ in range(3):
        life.selection.places_for("let's tidy room7 later")
    life.rules.here = lambda: "room3"
    shown = life.selection.places_for("Pebble, go down to the cellar")
    assert shown[:3] == ("cellar", "room3", "room7") and len(shown) == 15
    ctx = life.commands.context(None)
    assert len(ctx.places) == len(rooms) and len(ctx.parts()) > 0


def test_named_items_come_in_and_words_read_ahead_keep_their_place(rig_factory, clock):
    from pebble.things.book import Spot, Thing

    rig = rig_factory()
    life = rig.life
    things = rig.books.things
    for label in ("blue mug", "red kite"):
        thing = Thing(label, False, clock.now() - 100, 1)
        thing.spots = [Spot(clock.now() - 60, "front", 1.0, 1.0, 1.0, [], 0.9, "fast", 1)]
        things.things[label] = thing
    life.selection.stale()
    turns = rig.turns
    turns.named = life.named
    early = 'Ina is talking to you: "have you seen the blue mug or the"'
    final = 'Ina is talking to you: "have you seen the blue mug or the red kite"'
    turns._reply_messages(early, "adult", "Values: kindness.", "", None, None, "warm")
    _, messages, _ = turns._reply_messages(final, "adult", "Values: kindness.", "", None, None, "reply")
    content = messages[-1]["content"]
    mug, kite, words = content.index("The blue mug"), content.index("The red kite"), content.index("red kite\"")
    assert mug < words < kite
    assert sum(len(line) + 1 for line in content[mug:].split("\n") if line.startswith("The ")) <= named_chars(REPLY) + 2
    assert not any("The blue mug" in (m.get("content") or "") for m in rig.history.messages())


def test_matched_items_hold_three_hot_skills_and_lessons_for_here_within_their_share(rig_factory, clock):
    rig = rig_factory()
    life = rig.life
    skills = life.skills
    for n in range(8):
        skill = skills.keep(f"trick number {n}", f"do trick number {n}", STEPS, {"id": "x", "name": "", "tier": "friend"})
        if n < 2:
            skill.last_used = "2025-01-01T00:00:00+00:00"
            skills._write(skill)
    rig.store.write("lessons.json", {"items": [{"id": f"l{n}", "text": f"Lesson {n} " + ("about the lounge." if n % 2 else "for anywhere."), "scope": "place:lounge" if n % 2 else "self", "helpful": 3, "at": "2026-10-10T00:00:00+00:00"} for n in range(6)]})
    life.selection.stale()
    life.selection.live = None
    text = life.matched(TURN)
    skills_line = next(line for line in text.split("\n") if line.startswith("Skills you know: "))
    assert skills_line.count("trick number") == 3 and "trick number 0" not in skills_line and "trick number 1" not in skills_line
    lessons = next(line for line in text.split("\n") if line.startswith("Lessons you keep"))
    assert lessons.count("for anywhere") == 3 and "lounge" not in lessons
    life.rules.here = lambda: "lounge"
    life.selection.live = None
    assert "about the lounge" in life.matched(TURN)
    assert len(text) <= chosen_chars(TURN)


def test_this_rooms_rule_comes_before_the_quiet_rules(rig_factory, clock):
    from pebble.house.rules import Rule

    rig = rig_factory()
    rules = rig.life.rules
    now = clock.now()
    for n in range(3):
        rules.rules.append(Rule(rules.next_id, "quiet", "", "p1", "Ina", "trusted", now - 10, now - 10))
        rules.next_id += 1
    rules.rules.append(Rule(rules.next_id, "keep_out", "laundry", "p1", "Ina", "trusted", now - 10, now - 10))
    rules.here = lambda: "laundry"
    text = rig.life.matched()
    assert text.startswith("House rules: keep out of the laundry") and text.count("(Ina asked)") == 3


def test_near_identical_skills_merge_at_night_and_keep_both_names(rig_factory):
    rig = rig_factory()
    life = rig.life
    teacher = {"id": "p1", "name": "Ina", "tier": "trusted"}
    life.skills.keep("dance", "do a dance", STEPS, teacher)
    life.skills.keep("little dance", "do a little dance", STEPS, teacher)
    merged = life.selection.merge_skills()
    assert len(merged) == 1 and len(life.skills.all()) == 1
    kept = life.skills.all()[0]
    assert {"dance", "little dance"} <= {kept.name} | set(kept.aliases) and kept.versions[-1].get("merged") or kept.versions[0].get("merged")
    assert life.skills.matches("do the little dance") is not None and life.skills.matches("dance for me") is not None
    assert said(kept.steps) == said(STEPS)


def test_the_planners_card_names_only_who_is_here_named_or_household(rig_factory, clock):
    rig = rig_factory()
    life = rig.life
    book = life.company.book
    for n in range(30):
        person(book, f"v{n}", f"Visitor{n}", ["tea"], "guest")
    life.selection.stale()
    card = life._plan_card("do a little dance for Visitor17")
    assert "visitor17" in card.people and len(card.people) <= 13
    assert len(life._card().people) >= 31


def test_word_list_keeps_names_and_drops_possessives():
    assert word_list("Ina's red balls, Mo’s kites") == ["ina", "red", "ball", "mo", "kite"]
