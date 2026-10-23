import json
import subprocess
import sys
from pathlib import Path

BRAIN = Path(__file__).resolve().parents[1]


def test_end_to_end_against_the_sim(tmp_path):
    self_dir = tmp_path / "self"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pebble",
            "--sim",
            "--mind",
            "scripted",
            "--dry-run",
            "--self",
            str(self_dir),
            "--beats",
            "4",
            "--heartbeat",
            "0.3",
            "--seed",
            "3",
        ],
        cwd=BRAIN,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert "Traceback" not in result.stderr, result.stderr[-3000:]
    manifest = json.loads((self_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["self_format"] == 3
    for name in manifest["files"]:
        assert (self_dir / name).exists(), name
    core = json.loads((self_dir / "core.json").read_text(encoding="utf-8"))
    assert core["birthday"]
    state = json.loads((self_dir / "state.json").read_text(encoding="utf-8"))
    assert state["clean_shutdown"] is True
    assert state["boots"] == 1
    history = json.loads((self_dir / "conversation" / "history.json").read_text(encoding="utf-8"))
    assert history["turns"]
    first = history["turns"][0]["messages"][0]["content"]
    assert "first boot" in first
    assert "pack 3." in first and "docked" in first
    blackbox = (self_dir / "logs" / "blackbox.jsonl").read_text(encoding="utf-8").splitlines()
    kinds = [json.loads(line)["kind"] for line in blackbox]
    assert kinds[0] == "start" and kinds[-1] == "end"
    assert "turn" in kinds
    assert (self_dir / "logs" / "monologue.jsonl").exists()


def test_restart_after_a_clean_run_wakes_up_as_the_same_self(tmp_path):
    self_dir = tmp_path / "self"
    command = [sys.executable, "-m", "pebble", "--sim", "--mind", "scripted", "--dry-run", "--self", str(self_dir), "--beats", "1", "--heartbeat", "0.2"]
    first = subprocess.run(command, cwd=BRAIN, capture_output=True, text=True, timeout=120)
    assert first.returncode == 0, first.stderr[-3000:]
    birthday = json.loads((self_dir / "core.json").read_text(encoding="utf-8"))["birthday"]
    second = subprocess.run(command, cwd=BRAIN, capture_output=True, text=True, timeout=120)
    assert second.returncode == 0, second.stderr[-3000:]
    assert "clean shutdown" in second.stderr
    assert json.loads((self_dir / "core.json").read_text(encoding="utf-8"))["birthday"] == birthday
    assert json.loads((self_dir / "state.json").read_text(encoding="utf-8"))["boots"] == 2
