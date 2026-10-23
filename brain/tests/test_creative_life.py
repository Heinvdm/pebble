import asyncio
import dataclasses
import json
from datetime import datetime, timezone

import pytest
from conftest import Rig, run

from pebble.chaos.engine import Chaos
from pebble.chaos.ideas import IdeaDecks
from pebble.chaos.levers import WHIM_MIN_GAP_S, WHIM_SPIN_POWER, WHIMS_MAX_PER_HOUR
from pebble.clock import FakeClock
from pebble.life import whim_acts
from pebble.life.loop import Life, LifeSettings
from pebble.life.states import LifeState
from pebble.screen.gallery import Gallery
from pebble.screen.generator import SceneGenerator
from pebble.screen.stage import SceneStage
from pebble.screen.studio import Studio
from pebble.screen.tools import register_screen_tools
from pebble.seams.face import Touch

NIGHT = datetime(2026, 10, 15, 23, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def quick_whims(monkeypatch):
    monkeypatch.setattr(whim_acts, "WINK_S", 0.0)
    monkeypatch.setattr(whim_acts, "PEEK_S", 0.0)


class CreativeRig:
    def __init__(self, tmp_path, clock, pinned: float | None = 10.0):
        self.rig = rig = Rig(tmp_path, clock)
        self.chaos = Chaos(seed=5, sink=lambda record: rig.blackbox.record("chaos", **record), pinned=pinned)
        decks = IdeaDecks.open(rig.store)
        stage = SceneStage(rig.face)
        generator = SceneGenerator([("conscious", rig.mind)], stage, self.chaos.call_options, lambda kind: self.chaos.cards(decks, kind))
        self.studio = Studio(Gallery.open(rig.store), stage, generator, clock, self.chaos.stream, lambda: self.chaos.level, rig.blackbox.record)
        register_screen_tools(rig.registry, self.studio)
        rig.turns.options = lambda: self.chaos.call_options("tool")
        parts = dataclasses.replace(rig.parts, chaos=self.chaos, studio=self.studio)
        self.life = Life(parts, LifeSettings(waking_s=0.0, sensor_every_s=0.0))
        rig.context.sensors = lambda: self.life.sensors
        rig.context.on_spoke = self.life.spoke
        rig.context.on_task_closed = self.life.task_closed

    def records(self, kind: str) -> list[dict]:
        lines = self.rig.store.path("logs/blackbox.jsonl").read_text(encoding="utf-8").splitlines()
        return [r for r in map(json.loads, lines) if r["kind"] == kind]

    def close(self):
        self.rig.close()


@pytest.fixture
def creative(tmp_path, clock):
    made = []

    def make(clock_=None, **kwargs):
        made.append(CreativeRig(tmp_path, clock_ or clock, **kwargs))
        return made[-1]

    yield make
    for item in made:
        item.close()


async def live(life, clock, seconds: float, step: float = 20.0):
    elapsed = 0.0
    while elapsed < seconds:
        clock.advance(step)
        await life.tick(step)
        await asyncio.sleep(0)
        elapsed += step
    await asyncio.sleep(0.01)
    await life.creative.close()


def test_whims_happen_by_day_within_the_rate_limit(creative):
    c = creative()
    life, rig = c.life, c.rig
    run(live(life, rig.clock, 4 * 3600))
    assert life.state is LifeState.ACTIVE
    whims = c.records("whim")
    assert whims
    times = [datetime.fromisoformat(w["at"]).timestamp() for w in whims]
    for index, at in enumerate(times):
        assert sum(1 for other in times if at - 3600 < other <= at) <= WHIMS_MAX_PER_HOUR
        if index:
            assert at - times[index - 1] >= WHIM_MIN_GAP_S - 1
    assert len(c.records("whim_done")) == len(whims)
    for request in rig.body.dry_run_requests:
        assert max(abs(request[0]), abs(request[1])) <= round(WHIM_SPIN_POWER * rig.body.profile.max_power)
    chaos_lines = c.records("chaos")
    assert any(r["lever"] == "whims" for r in chaos_lines)
    assert c.records("chaos_level")[0]["level"] == 10.0
    assert rig.face.state.chaos == 10.0 and rig.face.state.motion["gaze"] == pytest.approx(2.5)


def test_no_whims_at_night_or_while_someone_is_upset(tmp_path, creative):
    night = creative(FakeClock.at(NIGHT))
    run(live(night.life, night.rig.clock, 3 * 3600))
    assert night.records("whim") == []
    assert night.rig.voice.lines == []
    day = creative()
    day.life.someone_upset(6 * 3600)
    run(live(day.life, day.rig.clock, 3 * 3600))
    assert day.records("whim") == []
    assert day.records("someone_upset")


def test_a_calm_dial_means_no_whims(creative):
    c = creative(pinned=0.0)
    run(live(c.life, c.rig.clock, 3 * 3600))
    assert c.records("whim") == []


def test_touching_the_screen_is_felt(creative):
    c = creative()
    life, rig = c.life, c.rig
    before = rig.parts.inner.mood.valence
    social = rig.parts.inner.needs.social
    life.touched(Touch(0.9, 0.2, "stroke"))
    assert rig.face.current == "love"
    assert rig.face.state.gaze[0] == pytest.approx(0.8) and rig.face.state.gaze[1] == pytest.approx(-0.6)
    assert life.p.inner.mood.valence > before and life.p.inner.needs.social < social
    assert any("stroked your face screen (right)" in e.text for e in life.events.peek())
    assert life.trigger.is_set()
    life.touched(Touch(0.1, 0.1, "tap"))
    assert len([e for e in life.events.peek() if "face screen" in e.text]) == 1
    rig.clock.advance(3)
    life.touched(Touch(0.1, 0.1, "tap"))
    assert rig.face.current == "happy"
    assert len(c.records("touch")) == 2


def test_turns_get_steady_sampling_gallery_and_idea_cards(creative):
    c = creative()
    life, rig = c.life, c.rig
    life._mind_ready = True
    run(life.tick(1.0))
    run(life.tick(1.0))
    run(life.beat())
    request = [r for r in rig.mind.requests if r["purpose"] == "turn"][0]
    assert request["options"]["kind"] == "steady" and request["options"]["temperature"] == 0.3
    assert "face" in request["tools"] and {"draw_scene", "show_scene"} <= set(life.tool_names(False))
    observation = request["messages"][-1]["content"]
    assert "Not just now: drawing" not in observation
    assert "Your drawings:" in observation and "hello" in observation
    assert any(r["lever"] == "choices" for r in c.records("chaos"))
    cards = c.records("idea_card")
    if cards:
        assert "Idea card:" in observation
    turns = c.records("turn")
    assert turns[0]["choice"]["tier"] == 2


def test_night_turns_have_no_drawing_tools(creative):
    c = creative(FakeClock.at(NIGHT))
    life, rig = c.life, c.rig
    life._mind_ready = True
    run(life.tick(1.0))
    run(life.beat())
    request = [r for r in rig.mind.requests if r["purpose"] == "turn"][0]
    assert "draw_scene" not in life.tool_names(False, True)
    assert "Your drawings:" not in request["messages"][-1]["content"]
    assert "drawing" in request["messages"][-1]["content"].split("Not just now: ")[1]


def test_novelty_spreads_the_robots_own_choices(creative):
    c = creative()
    life = c.life
    run(life.tick(1.0))
    picks = []
    for _ in range(30):
        choice = life.choose(quiet=False)
        picks.append(choice.chosen.key)
        c.rig.clock.advance(60)
    assert len(set(picks)) >= 3
    assert life.creative.recent.recent()


def test_dream_remix_needs_night_and_the_dock(creative):
    c = creative(FakeClock.at(NIGHT))
    life, rig = c.life, c.rig
    assert life.creative.dream("2026-10-15", quiet=True, docked=False) is None
    assert life.creative.dream("2026-10-15", quiet=False, docked=True) is None
    report = life.creative.dream("2026-10-15", quiet=True, docked=True)
    assert report["saved_as"] == "dream-2026-10-15"
    assert c.records("dream_remix")
    assert Chaos.disabled().enabled is False


def test_the_owner_pin_in_preferences_is_used(tmp_path, clock):
    rig = Rig(tmp_path, clock)
    try:
        prefs = rig.store.read("preferences.json")
        assert prefs["chaos"] == {"pinned": None}
        rig.parts.books.preferences["chaos"] = {"pinned": 3}
        chaos = Chaos(seed=1)
        life = Life(dataclasses.replace(rig.parts, chaos=chaos), LifeSettings(waking_s=0.0, sensor_every_s=0.0))
        run(life.tick(1.0))
        assert chaos.pinned == 3.0 and chaos.level == 3.0
        rig.parts.books.preferences["chaos"] = {"pinned": "lots"}
        other = Chaos(seed=1)
        Life(dataclasses.replace(rig.parts, chaos=other), LifeSettings())
        assert other.pinned is None
    finally:
        rig.close()


def test_a_drawing_from_a_turn_reaches_the_face(creative):
    from pebble.mind.scripted import DRAW_ACT, ScriptedMind

    c = creative()
    rig = c.rig
    rig.turns.mind = ScriptedMind([DRAW_ACT])
    c.life._mind_ready = True
    run(c.life.tick(1.0))
    result = run(rig.turns.run("Time: noon", c.life.tool_names(False), "newborn", ""))
    assert result.calls[0]["name"] == "face" and result.calls[0]["result"]["saved_as"] == "my-night"
    assert rig.face.scenes[-1]["ended"] and len(rig.face.scenes[-1]["lines"]) == 6


def test_the_eyes_come_back_after_a_touch(creative):
    c = creative()
    c.life.touched(Touch(1.0, 1.0, "tap"))
    assert c.rig.face.state.gaze == (1.0, 1.0)
    c.rig.clock.advance(1)
    run(c.life.tick(1.0))
    assert c.rig.face.state.gaze == (1.0, 1.0)
    c.rig.clock.advance(5)
    run(c.life.tick(5.0))
    assert c.rig.face.state.gaze == (0.0, 0.0)
