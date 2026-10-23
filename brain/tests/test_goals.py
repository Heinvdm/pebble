import pytest

from pebble.goals import GOAL_CAP, TASK_CAP, GoalBook, Rejected, check_concrete

DONE = "the front sensor reads under 300 mm"


def book(clock) -> GoalBook:
    return GoalBook({}, clock)


def add_task(goals: GoalBook, title: str, source: str = "self", priority: int = 3, **kwargs):
    return goals.add("task", title, kwargs.pop("done_when", f"{title} is checked off by {DONE}"), kwargs.pop("reason", "curiosity"), source, priority, **kwargs)


def test_task_and_goal_caps(clock):
    goals = book(clock)
    for index in range(TASK_CAP):
        add_task(goals, f"look at spot {index}")
    with pytest.raises(Rejected):
        add_task(goals, "one too many")
    for index in range(GOAL_CAP):
        goals.add("goal", f"learn room {index}", f"room {index} has a saved description in places", "curiosity")
    with pytest.raises(Rejected):
        goals.add("goal", "learn the hallway", "the hallway has a saved description", "curiosity")
    assert len(goals.active("task")) == TASK_CAP
    assert len(goals.active("goal")) == GOAL_CAP


def test_people_outrank_own_ideas_at_the_cap(clock):
    goals = book(clock)
    for index in range(TASK_CAP):
        add_task(goals, f"own idea {index}", priority=2 if index == 3 else 4)
    owner = add_task(goals, "fetch nothing, just wave", source="owner", reason="")
    assert owner.status == "active"
    dropped = [item for item in goals.items if item.status == "dropped"]
    assert [item.title for item in dropped] == ["own idea 3"]
    assert "made room" in dropped[0].notes[0]["text"]


def test_people_are_refused_when_everything_is_from_people(clock):
    goals = book(clock)
    for index in range(TASK_CAP):
        add_task(goals, f"owner job {index}", source="owner")
    with pytest.raises(Rejected):
        add_task(goals, "another owner job", source="owner")


def test_expiry_closes_items_and_clears_the_current_one(clock):
    goals = book(clock)
    item = add_task(goals, "look at the plant", hours=1)
    goals.set_current(item.id)
    clock.advance(1800)
    assert goals.expire() == []
    clock.advance(3600)
    expired = goals.expire()
    assert [i.id for i in expired] == [item.id]
    assert item.status == "expired"
    assert goals.current() is None


def test_expiry_is_bounded(clock):
    goals = book(clock)
    item = add_task(goals, "watch the door", hours=10_000)
    assert item.expires_at - item.created_at == 72 * 3600
    owner = add_task(goals, "guard the remote", source="owner", hours=10_000, reason="")
    assert owner.expires_at - owner.created_at == 720 * 3600


@pytest.mark.parametrize(
    "title,done_when",
    [
        ("Understand consciousness", "when Pebble understands it"),
        ("Become alive", "when Pebble feels alive at last"),
        ("Find the meaning of life", "the meaning of life is written down"),
        ("Transcend my limits", "Pebble has transcended everything"),
        ("Be perfect", "every day is perfect from now on"),
        ("Make Ina happy", "Ina is happy forever"),
    ],
)
def test_vague_grand_goals_are_rejected(clock, title, done_when):
    with pytest.raises(Rejected):
        book(clock).add("goal", title, done_when, "it seems important")


@pytest.mark.parametrize(
    "title",
    ["Buy a new charger", "Email Ina about the cat", "Delete the old logs folder", "Edit the core rules", "Download a new voice"],
)
def test_things_outside_its_body_are_rejected(clock, title):
    with pytest.raises(Rejected):
        add_task(book(clock), title)


def test_done_when_must_be_concrete(clock):
    goals = book(clock)
    with pytest.raises(Rejected):
        goals.add("task", "look at the plant", "done", "curiosity")
    with pytest.raises(Rejected):
        goals.add("task", "look at the plant", "look at the plant", "curiosity")
    with pytest.raises(Rejected):
        goals.add("task", "look at the plant", "the plant has been looked at", "")
    check_concrete("look at the plant", "the plant has been looked at")


def test_status_updates_and_failure_streak(clock):
    goals = book(clock)
    first = add_task(goals, "spin once")
    second = add_task(goals, "roll to the wall")
    goals.update(first.id, "failed", "the wheel stalled")
    assert goals.failure_streak == 1
    with pytest.raises(Rejected):
        goals.update(first.id, "done")
    goals.update(second.id, None, "halfway")
    goals.update(second.id, "done")
    assert goals.failure_streak == 0
    assert second.notes[0]["text"] == "halfway"
    with pytest.raises(Rejected):
        goals.update(999, "done")


def test_round_trip(clock):
    goals = book(clock)
    add_task(goals, "look at the plant", serves=("curiosity",))
    again = GoalBook(goals.to_dict(), clock)
    assert again.to_dict() == goals.to_dict()
