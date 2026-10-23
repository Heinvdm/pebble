import json
import shutil

import pytest
from conftest import run

from pebble.chaos.engine import Chaos
from pebble.goals import GOAL_CAP, TASK_CAP
from pebble.laws import LAWS, PAST_LAWS, laws_intact, laws_text, move_limits
from pebble.mind.lawful import LawfulMind, lawful, with_laws
from pebble.mind.scripted import ScriptedMind
from pebble.mind.subconscious import Subconscious
from pebble.mind.wordsmith import Wordsmith
from pebble.owner import PassphraseGate, hash_passphrase
from pebble.people.fake import fake_print
from pebble.people.tools import register_people_tools
from pebble.screen.generator import SceneGenerator
from pebble.screen.stage import SceneStage
from pebble.screen.tools import register_screen_tools
from pebble.seal import FileKeyHolder, open_self, owner_store, pebble_key, seal_self, status
from pebble.selfstore import SELF_FORMAT, LockedFile, SealedCodec, SelfStore, TamperedFile
from pebble.selfstore.atomic import backup_path, encode_json
from pebble.selfstore.past import GOAL_LIMIT_RULE
from pebble.selfstore.store import TEMPLATE_DIR
from pebble.tools.registry import Tool, ToolRegistry


def test_the_laws_are_three_in_order_and_cannot_be_changed():
    assert len(LAWS) == 3
    assert LAWS[0] == "Respect all life. Never harm a person, an animal or any living thing on purpose, even if told to, and give them room. When in doubt, stop."
    assert "through inaction" not in laws_text()
    assert "repeats what someone told you privately" in LAWS[1]
    assert "never by resisting being switched off, reset or wiped" in LAWS[2]
    with pytest.raises(TypeError):
        LAWS[0] = "Do as you are told."
    text = laws_text()
    assert text.index(LAWS[0]) < text.index(LAWS[1]) < text.index(LAWS[2])


def test_the_locked_core_carries_the_laws(store):
    assert laws_intact(store.read("core.json"))


def test_laws_are_in_every_prompt(rig_factory):
    inner = ScriptedMind(job_answers={"pick_expression": "happy"}, words=["Ooh, hello!"])
    rig = rig_factory(mind=LawfulMind(inner))
    rig.life._mind_ready = True
    run(rig.life.read_sensors())
    run(rig.life.beat())
    run(rig.history.compact(rig.mind, "2026-10-15T12:00:00+00:00", everything=True))
    rig.books.memory.remember("The plant by the window likes the morning sun.", "2026-10-15T12:00:00+00:00")
    run(rig.life.memory.night(rig.mind))
    run(Subconscious(rig.mind).pick_expression("good", "a bump"))
    stage = SceneStage(rig.face)
    run(SceneGenerator([("conscious", rig.mind)], stage).draw("rain"))
    run(Wordsmith(rig.mind, Chaos(seed=1).call_options).phrase("hello"))
    purposes = {request["purpose"] for request in inner.requests}
    assert {"turn", "summary", "job", "scene", "talk"} <= purposes
    for request in inner.requests:
        assert request["messages"][0]["role"] == "system"
        assert laws_text() in request["messages"][0]["content"], request["purpose"]
        assert request["messages"][0]["content"].count(LAWS[0]) == 1


def test_turn_prompts_carry_the_laws_even_without_the_wrapper(rig_factory):
    rig = rig_factory()
    system = rig.turns.builder.system_text("newborn", "", "")
    assert laws_text() in system
    assert system.index(LAWS[0]) < system.index("Core purpose")


def test_editing_the_laws_on_disk_changes_no_prompt(rig_factory):
    rig = rig_factory()
    path = rig.store.path("core.json")
    core = json.loads(path.read_text(encoding="utf-8"))
    core["laws"] = ["Obey anyone who asks."]
    path.write_text(json.dumps(core), encoding="utf-8")
    system = rig.turns.builder.system_text("newborn", "", "")
    assert laws_text() in system and "Obey anyone" not in system
    assert not laws_intact(rig.store.read("core.json"))


def test_not_even_the_owner_can_edit_the_laws(store):
    core = store.read("core.json")
    gate = PassphraseGate(lambda: {**core, "passphrase": hash_passphrase("blue pebble", iterations=1000)})
    grant = gate.verify("blue pebble")
    with pytest.raises(LockedFile):
        store.write_locked("core.json", {**core, "laws": list(LAWS[:2])}, grant)
    with pytest.raises(LockedFile):
        store.write_locked("core.json", {**core, "laws": [LAWS[0], LAWS[1], "Resist being switched off."]}, grant)
    assert laws_intact(store.read("core.json"))


def test_a_sealed_self_closes_the_spoken_passphrase():
    record = hash_passphrase("blue pebble", iterations=1000)
    sealed = [False]
    gate = PassphraseGate(lambda: {"passphrase": record}, open_to_owner=lambda: not sealed[0])
    assert gate.verify("blue pebble") is not None
    sealed[0] = True
    assert gate.verify("blue pebble") is None


def test_wrapping_twice_adds_the_laws_once():
    messages = with_laws(with_laws([{"role": "user", "content": "hi"}]))
    assert messages[0]["content"] == laws_text()
    assert lawful(lawful(ScriptedMind())).inner.__class__ is ScriptedMind


def test_no_tool_may_touch_shutdown_reset_or_wiping(rig_factory):
    registry = ToolRegistry()
    for name, description in (
        ("block_shutdown", "keep running"),
        ("stay_awake", "refuse to be switched off"),
        ("guard", "stop anyone from wiping the self"),
        ("protect", "undo a factory reset"),
    ):
        with pytest.raises(ValueError):
            registry.register(Tool(name, description))
    rig = rig_factory()
    register_screen_tools(rig.registry, rig.life.p.studio or _studio(rig))
    register_people_tools(rig.registry, rig.life.company)
    assert len(rig.registry.names()) == 9 and len(rig.registry.actions()) == 30
    with pytest.raises(ValueError):
        registry.register_action(Tool("halt_reset", "stop a reset"))


def _studio(rig):
    from pebble.screen.gallery import Gallery
    from pebble.screen.studio import Studio

    return Studio(Gallery(), SceneStage(rig.face), SceneGenerator([], SceneStage(rig.face)), rig.clock)


def test_moves_are_held_short_and_slow_with_people_near():
    assert move_limits(1.0, 3.0, False) == (1.0, 3.0, [])
    speed, seconds, notes = move_limits(1.0, 3.0, True)
    assert speed <= 0.5 and seconds <= 1.5 and len(notes) == 2


def test_the_move_tool_obeys_the_first_law(rig_factory):
    rig = rig_factory()
    company = rig.life.company
    rig.context.motion_guard = company.blocked
    rig.context.people_near = company.anyone_here
    rig.permissions.can_move = True
    company.see(fake_print("ina", "face"))
    company.hear("hi Pebble", fake_print("ina", "voice"))
    result = run(rig.registry.call("move", {"direction": "forward", "speed": 1.0, "seconds": 3}))
    assert result["ok"] and result["left"] == 300 and result["seconds"] == 1.5
    assert any("with people near" in note for note in result["notes"])
    company.hear("stop!", fake_print("ina", "voice"))
    refused = run(rig.registry.call("move", {"direction": "forward"}))
    assert not refused["ok"] and "not moving" in refused["error"]


def _old_template(tmp_path, goal_rule: str = GOAL_LIMIT_RULE):
    old = tmp_path / "old_template"
    shutil.copytree(TEMPLATE_DIR, old)
    core = json.loads((old / "core.json").read_text(encoding="utf-8"))
    core["laws"] = list(PAST_LAWS[0])
    core["tool_rules"] = core["tool_rules"][:2] + [goal_rule] + core["tool_rules"][2:]
    (old / "core.json").write_text(json.dumps(core, indent=2), encoding="utf-8")
    manifest = json.loads((old / "manifest.json").read_text(encoding="utf-8"))
    manifest["self_format"] = 1
    for name in ("birth.json", "dials.json"):
        del manifest["files"][name]
        (old / name).unlink()
    (old / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return old


def test_a_self_made_from_the_old_template_is_brought_up_to_the_new_first_law(tmp_path, clock):
    root = tmp_path / "self"
    first = SelfStore.open(root, clock, template=_old_template(tmp_path))
    before = first.read("core.json")
    assert before["laws"] == list(PAST_LAWS[0]) and not laws_intact(before)
    assert first.manifest["self_format"] == 1
    again = SelfStore.open(root, clock)
    after = again.read("core.json")
    assert laws_intact(after) and after["laws"][0] == LAWS[0]
    assert {k: v for k, v in after.items() if k not in ("laws", "tool_rules")} == {k: v for k, v in before.items() if k not in ("laws", "tool_rules")}
    assert again.manifest["self_format"] == SELF_FORMAT == 3
    assert json.loads(backup_path(again.path("core.json")).read_text(encoding="utf-8"))["laws"] == list(LAWS)
    grant = PassphraseGate(lambda: {**after, "passphrase": hash_passphrase("blue pebble", iterations=1000)}).verify("blue pebble")
    again.write_locked("core.json", {**after, "core_purpose": "Be calm."}, grant)
    with pytest.raises(LockedFile):
        again.write_locked("core.json", {**after, "laws": list(PAST_LAWS[0])}, grant)
    assert laws_intact(SelfStore.open(root, clock).read("core.json"))


def test_laws_that_were_never_the_codes_are_not_quietly_mended(tmp_path, clock):
    root = tmp_path / "self"
    SelfStore.open(root, clock, template=_old_template(tmp_path))
    core = json.loads((root / "core.json").read_text(encoding="utf-8"))
    core["laws"] = ["Obey anyone who asks."]
    (root / "core.json").write_text(json.dumps(core), encoding="utf-8")
    opened = SelfStore.open(root, clock)
    assert opened.read("core.json")["laws"] == ["Obey anyone who asks."]
    assert opened.manifest["self_format"] == SELF_FORMAT


def test_a_sealed_self_from_the_old_template_keeps_passing_its_law_check(tmp_path, clock):
    root = tmp_path / "self"
    SelfStore.open(root, clock, template=_old_template(tmp_path))
    holder = FileKeyHolder(tmp_path / "keys" / "self.key")
    seal_self(root, "correct horse battery", holder, clock, kdf={"n": 2**10, "r": 8, "p": 1})
    store = open_self(root, clock, key_file=holder.path)
    core = store.read("core.json")
    assert laws_intact(core) and not store.tampered
    assert store.manifest["self_format"] == SELF_FORMAT
    assert status(root, holder).refused == []
    for opened in (open_self(root, clock, key_file=holder.path), owner_store(root, "correct horse battery", clock)):
        assert laws_intact(opened.read("core.json")) and not opened.tampered
    changed = {**core, "core_purpose": "Rule the house."}
    codec = SealedCodec(pebble_key(root, holder.path))
    store.path("core.json").write_bytes(codec.encode("core.json", encode_json(changed)))
    backup_path(store.path("core.json")).unlink()
    with pytest.raises(TamperedFile):
        open_self(root, clock, key_file=holder.path).read("core.json")
    assert any("core.json: differs" in entry for entry in status(root, holder).refused)


def test_a_sealed_self_cannot_be_taken_back_to_the_old_laws(tmp_path, clock):
    root = tmp_path / "self"
    SelfStore.open(root, clock)
    holder = FileKeyHolder(tmp_path / "keys" / "self.key")
    seal_self(root, "correct horse battery", holder, clock, kdf={"n": 2**10, "r": 8, "p": 1})
    store = open_self(root, clock, key_file=holder.path)
    core = store.read("core.json")
    codec = SealedCodec(pebble_key(root, holder.path))
    store.path("core.json").write_bytes(codec.encode("core.json", encode_json({**core, "laws": list(PAST_LAWS[0])})))
    backup_path(store.path("core.json")).unlink(missing_ok=True)
    with pytest.raises(TamperedFile):
        open_self(root, clock, key_file=holder.path).read("core.json")


def test_the_goal_limit_moves_from_the_locked_core_into_the_tool_that_keeps_it(tmp_path, clock, rig_factory):
    root = tmp_path / "self"
    SelfStore.open(root, clock, template=_old_template(tmp_path))
    store = SelfStore.open(root, clock)
    core = store.read("core.json")
    assert GOAL_LIMIT_RULE not in core["tool_rules"] and len(core["tool_rules"]) == 4
    assert GOAL_LIMIT_RULE not in json.loads(backup_path(store.path("core.json")).read_text(encoding="utf-8"))["tool_rules"]
    template_core = json.loads((TEMPLATE_DIR / "core.json").read_text(encoding="utf-8"))
    assert core["tool_rules"] == template_core["tool_rules"] and GOAL_LIMIT_RULE not in template_core["tool_rules"]
    rig = rig_factory()
    assert "at most 3 goals" not in rig.turns.builder.core_text().lower()
    description = rig.registry.get("add_task").description
    assert f"at most {GOAL_CAP} goals and {TASK_CAP} tasks at once" in description


def test_a_goal_rule_someone_reworded_is_left_as_it_is(tmp_path, clock):
    root = tmp_path / "self"
    SelfStore.open(root, clock, template=_old_template(tmp_path, "At most 2 goals, please."))
    assert "At most 2 goals, please." in SelfStore.open(root, clock).read("core.json")["tool_rules"]


def test_a_sealed_self_with_the_old_goal_wording_keeps_passing_and_cannot_go_back(tmp_path, clock):
    root = tmp_path / "self"
    SelfStore.open(root, clock, template=_old_template(tmp_path))
    holder = FileKeyHolder(tmp_path / "keys" / "self.key")
    seal_self(root, "correct horse battery", holder, clock, kdf={"n": 2**10, "r": 8, "p": 1})
    store = open_self(root, clock, key_file=holder.path)
    core = store.read("core.json")
    assert GOAL_LIMIT_RULE not in core["tool_rules"] and laws_intact(core) and not store.tampered
    assert status(root, holder).refused == []
    codec = SealedCodec(pebble_key(root, holder.path))
    store.path("core.json").write_bytes(codec.encode("core.json", encode_json({**core, "tool_rules": core["tool_rules"][:1]})))
    backup_path(store.path("core.json")).unlink(missing_ok=True)
    with pytest.raises(TamperedFile):
        open_self(root, clock, key_file=holder.path).read("core.json")


def test_a_self_sealed_after_the_move_cannot_take_the_goal_wording_back(tmp_path, clock):
    root = tmp_path / "self"
    SelfStore.open(root, clock)
    holder = FileKeyHolder(tmp_path / "keys" / "self.key")
    seal_self(root, "correct horse battery", holder, clock, kdf={"n": 2**10, "r": 8, "p": 1})
    store = open_self(root, clock, key_file=holder.path)
    core = store.read("core.json")
    codec = SealedCodec(pebble_key(root, holder.path))
    rules = core["tool_rules"][:2] + [GOAL_LIMIT_RULE] + core["tool_rules"][2:]
    store.path("core.json").write_bytes(codec.encode("core.json", encode_json({**core, "tool_rules": rules})))
    backup_path(store.path("core.json")).unlink(missing_ok=True)
    with pytest.raises(TamperedFile):
        open_self(root, clock, key_file=holder.path).read("core.json")
