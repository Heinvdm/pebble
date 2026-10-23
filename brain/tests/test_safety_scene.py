import asyncio
import json
import re

from pebble.safety.scene import play


def stamp(lines, needle):
    for line in lines:
        if needle in line:
            return float(line.split("s", 1)[0])
    raise AssertionError(f"{needle!r} never happened:\n" + "\n".join(lines))


def records(root):
    path = root / "logs" / "blackbox.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_smoke_alarm_next_door_with_ina_home(tmp_path):
    show = asyncio.run(play("smoke", tmp_path / "self"))
    lines = show.scene.lines
    asked = stamp(lines, "I can hear a smoke alarm going off. Is everything okay?")
    siren = stamp(lines, "loud alarm sound on")
    found = stamp(lines, "Ina, the smoke alarm is going off! Please check, and tell me when it's safe.")
    confirm = stamp(lines, "Is it really fine?")
    stood = stamp(lines, "Okay, thank you. I'll stop.")
    assert 5.0 < asked < 15.0
    assert asked + 14.0 <= siren <= asked + 18.0
    assert siren < found < confirm < stood
    assert not show.notifier.sent
    assert show.safety.sounder.on is False
    assert show.scene.life.p.face.state.alarm == ""
    kinds = [r["kind"] for r in records(tmp_path / "self")]
    assert "safety_incident" in kinds and "safety_seek_done" in kinds
    ends = [r for r in records(tmp_path / "self") if r["kind"] == "safety_end"]
    assert ends[-1]["how"] == "stood down"
    diary = (tmp_path / "self" / "diary.jsonl").read_text(encoding="utf-8")
    assert "I raised the alarm: a smoke alarm going off." in diary
    assert "Ina told me it was fine, so I stood down." in diary


def test_smoke_alarm_with_nobody_home_sends_the_notice(tmp_path):
    show = asyncio.run(play("alone", tmp_path / "self"))
    lines = show.scene.lines
    siren = stamp(lines, "loud alarm sound on")
    told = stamp(lines, "to the owner's phone")
    assert siren < told < siren + 70.0
    assert len(show.notifier.sent) == 1
    title, text = show.notifier.sent[0]
    assert re.fullmatch(r"Pebble noticed a smoke alarm going off at home at \d\d:\d\d and could not find anyone\. Nobody has told it that it's fine yet\.", text)
    assert "I haven't noticed a smoke alarm going off for a few minutes, so I've stopped my alarm." in "\n".join(lines)
    assert show.safety.sounder.on is False


def test_smoke_alarm_at_night_is_never_held_back(tmp_path):
    show = asyncio.run(play("smoke", tmp_path / "self", night=True))
    lines = show.scene.lines
    assert "resting" in lines[0]
    assert stamp(lines, "I can hear a smoke alarm going off. Is everything okay?") < stamp(lines, "loud alarm sound on") < stamp(lines, "Ina, the smoke alarm is going off!")
    assert stamp(lines, "Okay, thank you. I'll stop.") > 0
