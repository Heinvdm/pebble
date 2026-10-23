import dataclasses
from datetime import date

import pytest

from pebble.books import Books
from pebble.diary import Diary
from pebble.people.book import PeopleBook
from pebble.people.company import Company
from pebble.people.explain import explain, standing_text
from pebble.people.fake import fake_print
from pebble.people.forget import forget_person
from pebble.people.overnight import Overnight
from pebble.people.person import Person
from pebble.people.prints import normalise
from pebble.people.promises import check as check_promises
from pebble.people.qualities import DAY_CAP, HALF_LIFE_DAYS, NotScored
from pebble.people.trust import CHILD, FRIEND, INNER, STRANGER, TRUSTED, tiers
from pebble.people.visitors import Visitors

DAY = 86400.0


@pytest.fixture
def books(store, clock):
    return Books(store, clock)


@pytest.fixture
def company(books, clock):
    return Company(books, clock)


def meet(company: Company, key: str, text: str = "hello there") -> Person:
    company.see(fake_print(key, "face"))
    heard = company.hear(text, fake_print(key, "voice"))
    return company.book.get(heard.person_id)


def grow(book: PeopleBook, clock, person: Person, days: int, every: int = 1, qualities=("trustworthiness", "kindness")) -> None:
    for _ in range(0, days, every):
        clock.advance(every * DAY)
        for quality in qualities:
            book.evidence(person, quality, True, "senses", "was gentle and kept their word")


def overnight(books, store, clock, company) -> dict:
    night = clock.local().date()
    return Overnight(books, store, Diary(store, clock), clock, company.presence).run(night, "adult", "2026-10-15T23:00:00+00:00")


def test_a_person_is_made_only_when_they_interact(company):
    assert company.see(fake_print("ina", "face")) is None
    assert company.book.people == {}
    assert company.someone_new(company.clock.now())
    ina = meet(company, "ina")
    assert list(company.book.people) == [ina.id]
    assert ina.print_vectors("voice") and ina.print_vectors("face")
    again = meet(company, "ina", "me again")
    assert again.id == ina.id and len(company.book.people) == 1


def test_a_touch_counts_as_meeting_and_a_stroke_as_kindness(company):
    company.see(fake_print("kid", "face"))
    who = company.touched("stroke")
    person = company.book.get(who)
    assert person is not None and person.print_vectors("face")
    assert person.ledger.entries[-1].quality == "kindness" and person.ledger.entries[-1].good


def test_prints_are_numbers_only_and_no_field_judges_a_group():
    banned = {"looks", "appearance", "age", "gender", "sex", "accent", "race", "ethnicity", "religion", "nationality", "photo", "image", "audio", "recording"}
    fields = {f.name for f in dataclasses.fields(Person)}
    assert not fields & banned
    person = Person("p1", 0.0, 0.0)
    assert person.add_print("face", [0.1, 0.2, 0.3, 0.4], 0.0)
    assert not person.add_print("face", "a picture", 0.0)
    assert not person.add_print("voice", [float("nan")] * 8, 0.0)
    assert not set(person.to_dict()) & banned
    assert all(isinstance(v, float) for v in person.prints["face"][0]["vector"])


def test_evidence_is_capped_per_day_and_logged_with_reasons(company, clock):
    ina = meet(company, "ina")
    book = company.book
    for _ in range(6):
        book.evidence(ina, "trustworthiness", True, "senses", "said lovely things")
    counted = [e.counted for e in ina.ledger.entries if e.quality == "trustworthiness"]
    assert sum(counted) == DAY_CAP and counted[-1] == 0.0
    assert all(e.reason == "said lovely things" and e.source == "senses" for e in ina.ledger.entries if e.quality == "trustworthiness")
    reading = book.evidence(ina, "playfulness", True, "model", "joined my game")
    assert reading.weight == 0.5 and reading.counted == 0.5
    clock.advance(DAY)
    assert book.evidence(ina, "trustworthiness", True, "senses", "kept a secret").counted == 1.0
    assert any("stopped counting for the day" in line for line in explain(ina, clock.now()))


def test_flattery_cannot_buy_trust_in_a_day(company, clock):
    ina = meet(company, "ina")
    for _ in range(200):
        company.book.evidence(ina, "trustworthiness", True, "model", "flattered me")
        company.book.evidence(ina, "kindness", True, "model", "flattered me")
    assert tiers(company.book, clock.now())[ina.id] != TRUSTED
    assert ina.ledger.standing("trustworthiness", clock.now()).amount == pytest.approx(DAY_CAP)


def test_evidence_fades_over_months(company, clock):
    ina = meet(company, "ina")
    company.book.evidence(ina, "reliability", True, "senses", "came back on time")
    fresh = ina.ledger.standing("reliability", clock.now()).good
    clock.advance(HALF_LIFE_DAYS * DAY)
    assert ina.ledger.standing("reliability", clock.now()).good == pytest.approx(fresh / 2, rel=1e-3)


def test_children_get_warmth_never_scores(company, clock):
    kid = meet(company, "kid")
    kid.relationship = "child"
    kid.ledger.entries.clear()
    with pytest.raises(NotScored):
        company.book.evidence(kid, "kindness", False, "senses", "dropped me")
    company.touched("stroke")
    company.felt("dropped")
    kid.add_promise("them", "tidy the blocks", clock.now() + 60, clock.now())
    clock.advance(DAY)
    meet(company, "kid")
    clock.advance(4000)
    check_promises(company.book, company.presence, clock.now())
    assert kid.ledger.entries == []
    assert tiers(company.book, clock.now())[kid.id] == CHILD
    assert "never score children" in explain(kid, clock.now())[0]


def test_explain_counts_promises_without_pronouns(company, clock):
    ina = meet(company, "ina")
    ina.set_name("Ina")
    for index in range(15):
        promise = ina.add_promise("them", f"back at six ({index})", clock.now() + 60, clock.now())
        promise.status = "broken" if index == 3 else "kept"
    assert "Ina has kept 14 of 15 promises." in explain(ina, clock.now())


def test_promises_are_checked_by_who_is_there_when_due(company, clock):
    ina = meet(company, "ina")
    ina.set_name("Ina")
    kept = ina.add_promise("them", "back at six", clock.now() + 3600, clock.now())
    broken = ina.add_promise("them", "bring a sock", clock.now() + 2 * 3600, clock.now())
    mine = ina.add_promise("me", "remind Ina about the plants", clock.now() + 600, clock.now())
    clock.advance(3600 - 300)
    meet(company, "ina", "I'm back!")
    news = check_promises(company.book, company.presence, clock.now())
    assert kept.status == "kept" and mine.status == "reminded"
    assert any("due now" in n.text for n in news)
    clock.advance(4 * 3600)
    check_promises(company.book, company.presence, clock.now())
    assert broken.status == "broken"
    reasons = [(e.quality, e.good, e.source) for e in ina.ledger.entries if e.source == "promise"]
    assert ("reliability", True, "promise") in reasons and ("reliability", False, "promise") in reasons


def test_tiers_from_meetings_introductions_evidence_and_the_owner(company, books, clock):
    book = company.book
    owner = meet(company, "alex")
    owner.relationship = "owner"
    stranger = meet(company, "visitor")
    regular = meet(company, "regular")
    table = tiers(book, clock.now())
    assert table[owner.id] == INNER and table[stranger.id] == STRANGER and table[regular.id] == STRANGER
    for _ in range(3):
        clock.advance(DAY)
        meet(company, "regular")
    assert tiers(book, clock.now())[regular.id] == FRIEND
    sister = meet(company, "sister")
    sister.introduced_by = owner.id
    assert tiers(book, clock.now())[sister.id] == FRIEND
    rude = meet(company, "rude")
    for _ in range(3):
        clock.advance(DAY)
        meet(company, "rude")
        book.evidence(rude, "respect", False, "senses", "shouted at me")
    assert tiers(book, clock.now())[rude.id] == STRANGER
    good = meet(company, "good")
    grow(book, clock, good, 6)
    assert tiers(book, clock.now())[good.id] != TRUSTED
    grow(book, clock, good, 12)
    assert tiers(book, clock.now())[good.id] == TRUSTED


def test_trust_can_grow_on_its_own_but_the_inner_circle_is_given_by_the_owner_only(company, clock):
    book = company.book
    owner = meet(company, "owner")
    owner.relationship = "owner"
    people = [meet(company, f"friend{i}") for i in range(5)]
    for day in range(0, 120, 5):
        clock.advance(5 * DAY)
        for index, person in enumerate(people):
            book.evidence(person, "trustworthiness", index != 4 or day % 10 == 0, "senses", "kept their word")
            book.evidence(person, "kindness", True, "senses", "was gentle")
    table = tiers(book, clock.now())
    assert table[owner.id] == INNER
    assert all(table[p.id] == TRUSTED for p in people[:4])
    assert not any(table[p.id] == INNER for p in people)
    for person in people:
        person.override = INNER
    after = tiers(book, clock.now())
    assert sum(1 for p in people if after[p.id] == INNER) == 3
    assert sum(1 for tier in after.values() if tier == INNER) == 4


def test_stranger_prints_expire_unless_they_come_back(company, books, store, clock):
    passer = meet(company, "passer")
    returner = meet(company, "returner")
    friend = meet(company, "friend")
    friend.set_name("Mo")
    friend.override = FRIEND
    clock.advance(20 * DAY)
    meet(company, "returner")
    clock.advance(11 * DAY)
    report = overnight(books, store, clock, company)
    assert passer.id not in books.people.people
    assert returner.has_prints() and friend.has_prints()
    clock.advance(31 * DAY)
    named = meet(company, "named")
    named.set_name("Zed")
    clock.advance(31 * DAY)
    overnight(books, store, clock, company)
    assert named.id in books.people.people and not named.has_prints()
    assert passer.id in report["prints_expired"] or passer.id not in books.people.people


def test_standing_is_told_only_to_the_person_asking(company, clock):
    from pebble.people.tools import register_people_tools
    from pebble.tools.registry import ToolRegistry
    from conftest import run

    registry = ToolRegistry()
    register_people_tools(registry, company)
    ina = meet(company, "ina")
    ina.set_name("Ina")
    sam = meet(company, "sam")
    sam.set_name("Sam")
    company.book.evidence(ina, "kindness", True, "senses", "stroked me")
    assert not run(registry.call("my_standing", {"person": "Ina"}))["ok"]
    company.asking = {ina.id: False}
    result = run(registry.call("my_standing", {"person": "Ina"}))
    assert "kindness" in result["standing"] and result["for"] == "Ina"
    clock.advance(200)
    company.see(fake_print("sam", "face"))
    company.hear("how does Ina rate?", fake_print("sam", "voice"))
    company.asking = {sam.id: False}
    refused = run(registry.call("my_standing", {"person": "Ina"}))
    assert not refused["ok"]
    assert "new to me" in standing_text(sam, STRANGER, clock.now())


def test_prompt_shows_warmth_rules_and_keeps_scores_out(company, clock):
    ina = meet(company, "ina")
    ina.set_name("Ina")
    ina.note("like", "cats")
    company.book.evidence(ina, "respect", False, "senses", "shouted at me")
    text = company.prompt_text(clock.now(), clock.local)
    assert "Ina" in text and "cats" in text and "equally warm" in text
    assert "respect" not in text and "%" not in text and "shouted" not in text


def test_private_notes_reach_the_prompt_only_when_that_person_is_alone(company, clock):
    ina = meet(company, "ina")
    ina.set_name("Ina")
    ina.note("private", "planning a surprise party for Sam")
    assert "surprise party" in company.prompt_text(clock.now(), clock.local)
    meet(company, "sam")
    assert "surprise party" not in company.prompt_text(clock.now(), clock.local)
    clock.advance(400)
    meet(company, "sam")
    assert "surprise party" not in company.prompt_text(clock.now(), clock.local)
    clock.advance(400)
    meet(company, "ina")
    assert "surprise party" in company.prompt_text(clock.now(), clock.local)


def test_people_survive_a_save_and_reload(company, books, store, clock):
    ina = meet(company, "ina")
    ina.set_name("Ina")
    ina.note("wish", "more songs")
    ina.add_promise("them", "back at six", clock.now() + 60, clock.now())
    company.book.evidence(ina, "kindness", True, "senses", "stroked me")
    books.save("people")
    again = Books(store, clock).people.find("Ina")
    assert again.to_dict() == ina.to_dict()


def test_only_the_passphrase_names_the_owner(company, clock):
    from pebble.owner import PassphraseGate, hash_passphrase

    ina = meet(company, "ina")
    with pytest.raises(PermissionError):
        company.book.make_owner(ina, None)
    grant = PassphraseGate(lambda: {"passphrase": hash_passphrase("blue pebble", iterations=1000)}).verify("blue pebble")
    company.book.make_owner(ina, grant)
    assert company.book.owner() is ina and tiers(company.book, clock.now())[ina.id] == INNER


class FixedFaces:
    available = True

    def __init__(self, faces: dict):
        self.faces = faces

    def voice_print(self, audio):
        return None

    def face_print(self, image):
        return self.faces.get(image)


def test_someone_seen_but_not_known_gets_a_short_record_that_fades(company, books, store, clock):
    eyes = FixedFaces({"passer": fake_print("passer", "face"), "other": fake_print("other", "face")})
    assert company.see(eyes.face_print("passer")) is None
    assert company.book.people == {}
    seen = list(company.book.sightings.items.values())
    assert len(seen) == 1 and seen[0].vectors() == [normalise(eyes.face_print("passer"))]
    assert not company.seen_before(clock.now())
    first = seen[0].id
    for _ in range(4):
        clock.advance(DAY)
        company.see(eyes.face_print("passer"))
    again = company.book.sightings.items[first]
    assert list(company.book.sightings.items) == [first]
    assert again.last_seen == clock.now() and again.visits == 5 and again.days == 5
    assert company.seen_before(clock.now()) and company.someone_new(clock.now())
    assert company.book.people == {} and tiers(company.book, clock.now()) == {}
    assert "seen them before" in company.prompt_text(clock.now(), clock.local)
    company.see(eyes.face_print("other"))
    assert len(company.book.sightings.items) == 2 and not company.seen_before(clock.now())
    books.save("people")
    assert first in Books(store, clock).people.sightings.items
    clock.advance(29 * DAY)
    company.see(eyes.face_print("other"))
    clock.advance(2 * DAY)
    report = overnight(books, store, clock, company)
    assert first in report["prints_expired"] and first not in company.book.sightings.items
    assert len(company.book.sightings.items) == 1
    clock.advance(31 * DAY)
    overnight(books, store, clock, company)
    assert company.book.sightings.items == {}
    assert Books(store, clock).people.sightings.items == {}


def test_visitors_mode_and_setup_keep_no_record_of_a_face_seen(company, books, clock):
    company.visitors = Visitors()
    company.visitors.start(clock.now(), None)
    company.see(fake_print("guest", "face"))
    assert company.someone_new(clock.now()) and company.book.sightings.items == {}
    company.visitors.stop()
    company.see(fake_print("guest", "face"))
    sighting = next(iter(company.book.sightings.items.values()))
    seen_at = clock.now()
    company.visitors.start(clock.now(), None)
    clock.advance(DAY)
    company.see(fake_print("guest", "face"))
    company.see(fake_print("another guest", "face"))
    assert len(company.book.sightings.items) == 1
    assert sighting.visits == 1 and sighting.last_seen == seen_at and len(sighting.prints) == 1
    company.visitors.stop()
    company.book.setup = True
    company.see(fake_print("helper", "face"))
    assert len(company.book.sightings.items) == 1
    assert books.people.to_dict()["seen"] == []


def test_meeting_someone_seen_before_keeps_one_record_and_gains_no_trust(company, clock):
    for _ in range(3):
        company.see(fake_print("neighbour", "face"))
        clock.advance(DAY)
    met_at = clock.now()
    neighbour = meet(company, "neighbour")
    assert company.book.sightings.items == {}
    assert neighbour.first_met == met_at and neighbour.days_met == 1
    assert tiers(company.book, clock.now())[neighbour.id] == STRANGER
    assert company.see(fake_print("neighbour", "face")) == neighbour.id
    assert company.book.sightings.items == {}


def test_forgetting_someone_drops_a_sighting_of_their_face(company, books, store, clock):
    ina = meet(company, "ina")
    company.book.sightings.add(normalise(fake_print("ina", "face")), clock.now(), company.book.day())
    forget_person(books, store, ina, company.presence, clock.now())
    assert company.book.sightings.items == {}
    assert Books(store, clock).people.to_dict()["seen"] == []
