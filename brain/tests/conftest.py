import asyncio
import random
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pebble.blackbox import BlackBox
from pebble.body.api import Body
from pebble.body.profile import BodyProfile
from pebble.body.sensors import FakeBattery, FakeValue, NoImu, PhoneSensors
from pebble.books import Books
from pebble.clock import FakeClock
from pebble.diary import Diary
from pebble.inner.state import InnerState
from pebble.life.loop import Life, LifeParts, LifeSettings
from pebble.life.turn import TurnRunner
from pebble.link.client import LinkClient
from pebble.mind.history import History
from pebble.mind.profile import ModelProfile
from pebble.mind.prompt import PromptBuilder
from pebble.mind.scripted import ScriptedMind
from pebble.seams.face import LogFace
from pebble.seams.voice import TranscriptVoice
from pebble.selfstore import SelfStore
from pebble.tools.builtin import Permissions, ToolContext, build_registry

NOON = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def run(coro, timeout: float = 30.0):
    return asyncio.run(asyncio.wait_for(coro, timeout))


@pytest.fixture
def clock():
    return FakeClock.at(NOON)


@pytest.fixture
def store(tmp_path, clock):
    return SelfStore.open(tmp_path / "self", clock)


def make_profile(**drive) -> BodyProfile:
    return BodyProfile.from_dict({"name": "test", "drive": {"cpm": 20.7, **drive}})


def small_model(**overrides) -> ModelProfile:
    data = {"name": "tiny", "context_tokens": 4096, "compact_at_tokens": 2500, "keep_tokens_after_compaction": 1000, "summary_tokens": 300}
    data.update(overrides)
    return ModelProfile.from_dict(data)


class Rig:
    def __init__(self, tmp_path: Path, clock: FakeClock, battery_pct: float = 80.0, charging: bool = False, mind=None, model=None, dry_run=True):
        self.clock = clock
        self.store = SelfStore.open(tmp_path / "self", clock)
        self.books = Books(self.store, clock)
        self.battery = FakeBattery(battery_pct, charging, 0.0, clock.monotonic)
        self.sensors = PhoneSensors(self.battery, FakeValue(30.0), FakeValue(150.0), NoImu(), clock.now)
        self.body = Body(LinkClient(lambda: None), clock, make_profile(), dry_run=dry_run)
        self.mind = mind or ScriptedMind()
        self.history = History(self.store, model or small_model(), self.books.name)
        self.face = LogFace()
        self.voice = TranscriptVoice(self.store, clock, echo=False)
        self.permissions = Permissions()
        self.context = ToolContext(clock, self.body, self.books, self.face, self.voice, self.permissions, sensors=lambda: None)
        self.registry = build_registry(self.context)
        self.turns = TurnRunner(self.mind, self.history, PromptBuilder(self.store), self.registry, self.store, clock)
        self.blackbox = BlackBox(self.store.path("logs/blackbox.jsonl"), clock)
        self.parts = LifeParts(
            clock=clock,
            store=self.store,
            books=self.books,
            body=self.body,
            sensors=self.sensors,
            inner=InnerState(),
            history=self.history,
            turns=self.turns,
            mind=self.mind,
            permissions=self.permissions,
            face=self.face,
            voice=self.voice,
            diary=Diary(self.store, clock),
            blackbox=self.blackbox,
            rng=random.Random(7),
        )
        self.life = Life(self.parts, LifeSettings(waking_s=0.0, sensor_every_s=0.0))
        self.context.sensors = lambda: self.life.sensors
        self.context.on_spoke = self.life.spoke
        self.context.on_task_closed = self.life.task_closed

    def close(self) -> None:
        self.blackbox.close()


@pytest.fixture
def rig_factory(tmp_path, clock):
    made = []

    def make(**kwargs) -> Rig:
        rig = Rig(tmp_path, clock, **kwargs)
        made.append(rig)
        return rig

    yield make
    for rig in made:
        rig.close()


def pytest_configure(config):
    config.addinivalue_line("markers", "setup_mode: run with Pebble's setup mode as a new self has it, instead of a finished setup")


@pytest.fixture(autouse=True)
def finished_setup(request, monkeypatch):
    if request.node.get_closest_marker("setup_mode") is not None:
        return
    import pebble.setup as setup_mode

    monkeypatch.setattr(setup_mode.Setup, "load", classmethod(lambda cls, store: cls()))
    monkeypatch.setattr(setup_mode, "in_setup", lambda root: False)
