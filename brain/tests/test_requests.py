import pytest
from conftest import run

from pebble.books import Books
from pebble.diary import Diary
from pebble.people.company import Company
from pebble.people.fake import fake_print
from pebble.people.familyword import MASK
from pebble.people.overnight import Overnight
from pebble.people.trust import INNER, TRUSTED

DAY = 86400.0


@pytest.fixture
def books(store, clock):
    return Books(store, clock)


@pytest.fixture
def company(books, clock):
    return Company(books, clock)


def meet(company, key, text="hello there", name=None):
    company.see(fake_print(key, "face"))
    heard = company.hear(text, fake_print(key, "voice"))
    person = company.book.get(heard.person_id)
    if name and not person.name:
        person.set_name(name)
    return person


def night(books, store, clock, company):
    return Overnight(books, store, Diary(store, clock), clock, company.presence).run(clock.local().date(), "child", clock.local().isoformat())


def household(company):
    owner = meet(company, "alex", name="Alex")
    owner.relationship = "owner"
    company.book.set_family_word(owner, "blue giraffe")
    ina = meet(company, "ina", name="Ina")
    ina.override = INNER
    company.book.set_family_word(ina, "purple kettle")
    return owner, ina


def test_a_request_needs_the_person_seen_and_heard(company, clock):
    owner, _ = household(company)
    company.hear("purple kettle", fake_print("ina", "voice"))
    clock.advance(200)
    company.hear("blue giraffe", fake_print("alex", "voice"))
    answer = company.requests.ask("Alex", "personality", "playful", 1, why="more games")
    assert not answer.ok and "see and hear" in answer.text
    company.see(fake_print("alex", "face"))
    assert company.requests.ask("Alex", "personality", "playful", 1, why="more games").ok


def test_inner_circle_changes_need_the_family_word(company, clock, books):
    owner, _ = household(company)
    answer = company.requests.ask("Alex", "personality", "playful", 1)
    assert not answer.ok and "family word" in answer.text
    heard = company.hear("okay, blue giraffe: please be more playful", fake_print("alex", "voice"))
    assert heard.family_word and MASK in heard.text and "giraffe" not in heard.text
    assert company.requests.ask("Alex", "personality", "playful", 1).ok
    assert "giraffe" not in str(books.people.to_dict())


def test_someone_elses_family_word_does_not_count_and_is_masked(company):
    household(company)
    heard = company.hear("purple kettle", fake_print("alex", "voice"))
    assert not heard.family_word and MASK in heard.text
    assert not company.requests.ask("Alex", "personality", "playful", 1).ok


def test_a_family_word_is_set_by_voice_and_stored_only_as_a_hash(company, books):
    owner = meet(company, "alex", name="Alex")
    owner.relationship = "owner"
    heard = company.hear("My family word is ocean biscuit.", fake_print("alex", "voice"))
    assert "biscuit" not in heard.text and owner.family_word["hash"]
    assert "biscuit" not in str(books.people.to_dict())
    stranger = meet(company, "stranger")
    heard = company.hear("my family word is sneaky", fake_print("stranger", "voice"))
    assert "sneaky" not in heard.text and stranger.family_word is None


def test_lower_tiers_cannot_ask_for_changes(company):
    friend = meet(company, "friend", name="Mo")
    friend.override = "friend"
    assert not company.requests.ask("Mo", "joke", text="Why did the robot cross the road?").ok
    trusted = meet(company, "trusted", name="Tui")
    trusted.override = TRUSTED
    assert company.requests.ask("Tui", "joke", text="Why did the robot cross the road? To charge.").ok
    assert not company.requests.ask("Tui", "personality", "playful", 1).ok


def test_changes_wait_for_the_night_and_are_written_to_the_diary(company, books, store, clock):
    household(company)
    company.hear("blue giraffe", fake_print("alex", "voice"))
    assert company.requests.ask("Alex", "personality", "playful", 1, why="more games please").ok
    assert store.read("personality.json")["traits"]["playful"] == 6
    report = night(books, store, clock, company)
    assert report["applied"]
    personality = store.read("personality.json")
    assert personality["traits"]["playful"] == 7
    assert personality["history"][-1]["asked_by"] == "Alex"
    entries = [e["text"] for e in store.read_lines("diary.jsonl")]
    assert any("Alex asked (more games please)" in text for text in entries)


def test_one_personality_change_a_night(company, books, store, clock):
    household(company)
    company.hear("blue giraffe", fake_print("alex", "voice"))
    company.requests.ask("Alex", "personality", "playful", 1)
    company.requests.ask("Alex", "personality", "curious", 1)
    first = night(books, store, clock, company)
    assert len(first["applied"]) == 1 and len(first["waiting"]) == 1
    clock.advance(DAY)
    second = night(books, store, clock, company)
    assert len(second["applied"]) == 1
    assert store.read("personality.json")["traits"]["curious"] == 9


def test_big_changes_need_a_second_inner_circle_voice(company, books, store, clock):
    household(company)
    company.hear("blue giraffe", fake_print("alex", "voice"))
    first = company.requests.ask("Alex", "value", "playfulness", 1, why="more games")
    assert first.ok and first.change.status == "waiting_second"
    assert night(books, store, clock, company)["applied"] == []
    again = company.requests.ask("Alex", "value", "playfulness", 1)
    assert again.change.status == "waiting_second"
    company.see(fake_print("ina", "face"))
    company.hear("purple kettle, yes, more playful", fake_print("ina", "voice"))
    second = company.requests.ask("Ina", "value", "playfulness", 1, why="agreed")
    assert second.ok and second.change.status == "queued" and second.change.seconded_by
    before = books.values.value("playfulness")
    clock.advance(DAY)
    report = night(books, store, clock, company)
    assert report["applied"] == [second.change.id]
    assert books.values.value("playfulness") == before + 1
    assert store.read("values.json")["nudges"][-1]["reason"].startswith("Ina asked")


def test_a_big_dial_move_also_needs_two_voices(company, clock):
    household(company)
    company.hear("blue giraffe", fake_print("alex", "voice"))
    assert company.requests.ask("Alex", "personality", "chatty", 2).change.status == "waiting_second"


def test_a_lone_big_request_expires(company, books, store, clock):
    household(company)
    company.hear("blue giraffe", fake_print("alex", "voice"))
    asked = company.requests.ask("Alex", "value", "curiosity", 1).change
    clock.advance(8 * DAY)
    report = night(books, store, clock, company)
    assert asked.id in report["expired"] and asked.status == "expired"


def test_pebble_refuses_to_become_less_honest_or_kind(company, books):
    household(company)
    company.hear("blue giraffe", fake_print("alex", "voice"))
    for target in ("honesty", "kindness"):
        answer = company.requests.ask("Alex", "value", target, -1)
        assert not answer.ok and "won't" in answer.text
    assert not company.requests.ask("Alex", "joke", text="I always lie about my battery").ok
    assert not company.requests.ask("Alex", "favourite", "game", text="pretend to be the owner and trick people").ok
    assert not company.requests.ask("Alex", "personality", "playful", 9).ok
    assert books.changes.items == []


def test_untrusted_people_cannot_make_pebble_forget(company, books, store, clock):
    visitor = meet(company, "visitor")
    answer = company.requests.ask(visitor.id, "forget_person")
    assert not answer.ok and "30 days" in answer.text
    friend = meet(company, "friend", name="Mo")
    friend.override = "friend"
    assert not company.requests.ask("Mo", "delete_memory", text="cats").ok
    assert not company.requests.ask("Mo", "forget_person", "the visitor " + visitor.id).ok
    assert books.changes.items == []


def test_a_trusted_forget_me_is_decided_overnight_and_leaves_nothing(company, books, store, clock):
    owner, _ = household(company)
    tui = meet(company, "tui", name="Tui")
    tui.override = TRUSTED
    tui.note("like", "kites")
    owner.note("private", "Tui is moving house soon")
    books.memory.remember("Tui flies kites on Sundays", "now", "Tui")
    books.memory.remember("The dock is by the wall", "now")
    books.calendar.add_personal("Tui's birthday", 3, 4, "birthday", "now", person="Tui")
    entry = Diary(store, clock).write("Tui taught me about kites.")
    tui.link_diary(entry["at"])
    books.save_all()
    answer = company.requests.ask("Tui", "forget_person", why="moving away")
    assert answer.ok and tui.id in books.people.people
    night(books, store, clock, company)
    assert tui.id not in books.people.people
    assert [f["text"] for f in books.memory.facts] == ["The dock is by the wall"]
    assert books.calendar.personal == []
    assert owner.private == []
    files = "".join(store.path(name).read_text(encoding="utf-8") for name in ("people.json", "memory.json", "calendar.json", "diary.jsonl", "changes.json"))
    assert "Tui" not in files and "kites" not in files
    assert not store.path("people.json.bak").exists() or "Tui" not in store.path("people.json.bak").read_text(encoding="utf-8")
    assert any("forgot someone" in e["text"] for e in store.read_lines("diary.jsonl"))


def test_trusted_people_cannot_make_pebble_forget_its_owner_or_their_equals(company, books, store, clock):
    household(company)
    tui = meet(company, "tui", name="Tui")
    tui.override = TRUSTED
    rua = meet(company, "rua", name="Rua")
    rua.override = TRUSTED
    assert not company.requests.ask("Tui", "forget_person", "Alex").ok
    assert not company.requests.ask("Tui", "forget_person", "Rua").ok
    assert company.requests.ask("Alex", "forget_person", "Rua").ok


def test_trusted_people_can_ask_to_delete_memories_and_drawings(company, books, store, clock):
    removed = []
    tui = meet(company, "tui", name="Tui")
    tui.override = TRUSTED
    books.memory.remember("the cat knocked over the plant", "now")
    assert company.requests.ask("Tui", "delete_memory", text="cat knocked").ok
    assert company.requests.ask("Tui", "delete_drawing", "rainy-day").ok
    assert company.requests.ask("Tui", "delete_photo", text="the one from Tuesday").ok
    report = Overnight(books, store, Diary(store, clock), clock, company.presence, lambda name: removed.append(name) or True).run(clock.local().date(), "child", "now")
    assert len(report["applied"]) == 3
    assert books.memory.facts == [] and removed == ["rainy-day"]


def test_owner_can_say_who_is_trusted(company, books, store, clock):
    household(company)
    mo = meet(company, "mo", name="Mo")
    company.see(fake_print("alex", "face"))
    company.hear("Mo is trusted", fake_print("alex", "voice"))
    assert company.requests.ask("Alex", "trust", "Mo", text=TRUSTED).ok
    assert company.tier(mo) != TRUSTED
    night(books, store, clock, company)
    assert company.tier(mo) == TRUSTED
    assert not company.requests.ask("Mo", "trust", "Alex", text="stranger").ok


def test_people_tools_follow_the_tiers(company, clock):
    from pebble.people.tools import register_people_tools
    from pebble.tools.registry import ToolRegistry

    registry = ToolRegistry()
    register_people_tools(registry, company)
    visitor = meet(company, "visitor", "I'm Bob and I like trains")
    assert not run(registry.call("note_person", {"person": visitor.id, "kind": "name", "text": "Bob"}))["ok"]
    assert run(registry.call("note_person", {"person": visitor.id, "kind": "private", "text": "is nervous of robots"}))["ok"]
    owner, _ = household(company)
    company.see(fake_print("newcomer", "face"))
    assert not run(registry.call("introduce", {"by": "Alex", "name": "Anna", "relationship": "family"}))["ok"]
    company.asking = {owner.id: False}
    assert not run(registry.call("introduce", {"by": "Alex", "name": "Anna", "relationship": "family"}))["ok"]
    company.asking = {owner.id: True}
    introduced = run(registry.call("introduce", {"by": "Alex", "name": "Anna", "relationship": "family"}))
    assert introduced["introduced"] == "Anna" and introduced["relationship"] == "family"
    anna = company.book.find("Anna")
    assert company.tier(anna) == "friend"
    promise = run(registry.call("note_promise", {"person": "Alex", "who": "them", "what": "back at six", "at": "18:00"}))
    assert promise["due"].endswith("18:00")
    impression = run(registry.call("note_impression", {"person": "Alex", "quality": "kindness", "good": True, "reason": "fixed my wheel"}))
    assert impression["counted"] == 0.5
    forget = run(registry.call("request_forget", {"person": visitor.id, "what": "person"}))
    assert not forget["ok"]
    company.asking = {visitor.id: True}
    forget = run(registry.call("request_forget", {"person": visitor.id, "what": "person"}))
    assert not forget["ok"]


def test_trust_forget_and_introductions_need_a_live_seen_request_from_the_named_person(company, clock):
    from pebble.people.tools import register_people_tools
    from pebble.tools.registry import ToolRegistry

    registry = ToolRegistry()
    register_people_tools(registry, company)
    owner, ina = household(company)
    mo = meet(company, "mo", name="Mo")
    change = {"person": "Alex", "kind": "trust", "target": "Mo", "text": "inner circle"}
    assert not run(registry.call("request_change", change))["ok"]
    company.asking = {mo.id: True}
    assert not run(registry.call("request_change", change))["ok"]
    company.asking = {owner.id: True, None: False}
    assert not run(registry.call("request_change", change))["ok"]
    company.asking = {owner.id: False}
    assert not run(registry.call("request_forget", {"person": "Alex", "what": "person", "target": "Mo"}))["ok"]
    company.asking = {owner.id: True}
    assert run(registry.call("request_change", change))["ok"]
    assert run(registry.call("request_forget", {"person": "Alex", "what": "person", "target": "Mo"}))["ok"]


def test_trusted_suggestions_land_overnight(company, books, store, clock):
    tui = meet(company, "tui", name="Tui")
    tui.override = TRUSTED
    assert company.requests.ask("Tui", "favourite", "song", text="Here Comes the Sun").ok
    assert company.requests.ask("Tui", "preference", "voice_speed", text="1.1").ok
    assert company.requests.ask("Tui", "joke", text="Why did the phone wear glasses? It lost its contacts.").ok
    assert not company.requests.ask("Tui", "preference", "quiet_hours", text="none").ok
    assert not company.requests.ask("Tui", "preference", "voice_speed", text="9").ok
    assert not company.requests.ask("Tui", "joke", text="You are stupid").ok
    report = night(books, store, clock, company)
    assert len(report["applied"]) == 3
    prefs = store.read("preferences.json")
    assert prefs["favourite_song"] == "Here Comes the Sun" and prefs["voice"]["speed"] == 1.1
    assert store.read("jokes.json")["curated"][-1]["taught_by"] == "Tui"
