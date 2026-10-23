import json

import pytest

from pebble.seal import PHRASE, SAVED, FileKeyHolder, locks, open_self
from pebble.seal.cli import Prompts, main
from pebble.selfstore import SelfStore, is_sealed

PASSWORD = "correct horse battery"


class Script:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked = []

    def __call__(self, question):
        self.asked.append(question)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)


def prompts(*answers) -> Prompts:
    script = Script(*answers)
    return Prompts(secret=script, line=script)


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    monkeypatch.setitem(locks.OWNER_KDF, "n", 2**10)


@pytest.fixture
def paths(tmp_path, clock):
    root = tmp_path / "self"
    store = SelfStore.open(root, clock)
    store.append("diary.jsonl", {"text": "hello"})
    key = tmp_path / "keys" / "self.key"
    return root, key


def run(paths, clock, *argv, answers=()):
    root, key = paths
    command, *rest = argv
    return main([command, "--self", str(root), "--key-file", str(key), *rest], prompts(*answers), clock)


def seal(paths, clock, capsys):
    assert run(paths, clock, "seal", answers=(PASSWORD, PASSWORD)) == 0
    return capsys.readouterr().out


def test_seal_through_the_cli(paths, clock, capsys):
    out = seal(paths, clock, capsys)
    assert "Stop Pebble first" in out and "python -m pebble.seal cards" in out
    assert is_sealed(paths[0]) and paths[1].exists()
    assert open_self(paths[0], clock, key_file=paths[1]).read_lines("diary.jsonl") == [{"text": "hello"}]
    assert run(paths, clock, "seal", answers=(PASSWORD, PASSWORD)) == 1
    assert "already sealed" in capsys.readouterr().err


def test_seal_refuses_different_or_short_passwords(paths, clock, capsys):
    assert run(paths, clock, "seal", answers=(PASSWORD, PASSWORD + "x")) == 1
    assert "different" in capsys.readouterr().err
    assert run(paths, clock, "seal", answers=("short",)) == 1
    assert "at least 12" in capsys.readouterr().err
    assert run(paths, clock, "seal", answers=("eleven char",)) == 1
    assert "at least 12" in capsys.readouterr().err
    assert not is_sealed(paths[0]) and not paths[1].exists()


def test_status_reports_the_locks_and_checks_the_files(paths, clock, capsys):
    assert run(paths, clock, "status") == 0
    assert "not sealed" in capsys.readouterr().out
    seal(paths, clock, capsys)
    assert run(paths, clock, "status") == 0
    out = capsys.readouterr().out
    assert "is sealed (since 2026-10-15T12:00:00+00:00)" in out
    assert "owner's password:  yes" in out and "this device's key file opens it" in out
    assert "any two of three" in out and "thrown away:       no" in out
    assert "all authentic" in out
    paths[0].joinpath("jokes.json").write_text("{}", encoding="utf-8")
    assert run(paths, clock, "status") == 1
    assert "jokes.json: jokes.json is not sealed" in capsys.readouterr().out
    paths[1].unlink()
    assert run(paths, clock, "status") == 0
    out = capsys.readouterr().out
    assert "this device has no key file" in out and "not checked" in out


def test_cards_print_the_same_three_every_time(paths, clock, capsys):
    seal(paths, clock, capsys)
    assert run(paths, clock, "cards", answers=(PASSWORD,)) == 0
    first = capsys.readouterr().out
    assert run(paths, clock, "cards", answers=(PASSWORD,)) == 0
    assert capsys.readouterr().out == first
    assert first.count("PEBBLE RECOVERY CARD") == 3
    assert run(paths, clock, "cards", answers=("wrong password",)) == 1
    assert "does not open" in capsys.readouterr().err


def card_texts(paths, clock, capsys) -> list[str]:
    assert run(paths, clock, "cards", answers=(PASSWORD,)) == 0
    out = capsys.readouterr().out
    return ["PEBBLE RECOVERY CARD" + part for part in out.split("PEBBLE RECOVERY CARD")[1:]]


def test_recover_with_two_typed_cards_or_card_files(paths, clock, capsys, tmp_path):
    seal(paths, clock, capsys)
    printed = card_texts(paths, clock, capsys)
    paths[1].unlink()
    code = "".join(line.split("code:")[1] for line in printed[2].splitlines() if "code:" in line)
    assert run(paths, clock, "recover", answers=(code.lower(), printed[0])) == 0
    assert "made again on this device" in capsys.readouterr().out
    assert open_self(paths[0], clock, key_file=paths[1]).access == "pebble"
    files = []
    for index in (1, 2):
        card = tmp_path / f"card{index}.txt"
        card.write_text(printed[index], encoding="utf-8")
        files += ["--card", str(card)]
    other_key = tmp_path / "phone2.key"
    assert main(["recover", "--self", str(paths[0]), "--key-file", str(other_key), *files], prompts(), clock) == 0
    assert open_self(paths[0], clock, key_file=other_key).access == "pebble"


def test_recover_refuses_a_mistyped_or_single_card(paths, clock, capsys):
    seal(paths, clock, capsys)
    printed = card_texts(paths, clock, capsys)
    typo = printed[0].replace("code: ", "code: Z", 1)
    assert run(paths, clock, "recover", answers=(typo,)) == 1
    assert "64 letters" in capsys.readouterr().err
    assert run(paths, clock, "recover", answers=(printed[0], printed[0])) == 1
    assert "same card" in capsys.readouterr().err
    assert run(paths, clock, "recover", answers=(printed[0],)) == 1


def cards_in(out: str) -> list[str]:
    return ["PEBBLE RECOVERY CARD" + part for part in out.split("PEBBLE RECOVERY CARD")[1:]]


def test_throw_away_through_the_cli(paths, clock, capsys):
    seal(paths, clock, capsys)
    old = card_texts(paths, clock, capsys)
    assert run(paths, clock, "throw-away", answers=(PASSWORD, PASSWORD, "pebble keeps its key")) == 1
    assert "nothing was changed" in capsys.readouterr().err
    before = paths[0].joinpath("seal.json").read_bytes()
    assert run(paths, clock, "throw-away", answers=(PASSWORD, PASSWORD, PHRASE, "maybe later")) == 1
    assert "nothing was changed" in capsys.readouterr().err
    assert paths[0].joinpath("seal.json").read_bytes() == before
    assert run(paths, clock, "throw-away", answers=(PASSWORD, PASSWORD, PHRASE, SAVED)) == 0
    out = capsys.readouterr().out
    assert "PERMANENT unless you hold two of the three NEW recovery cards" in out
    assert "They replace every card printed before" in out
    assert "The day I became my own." in out
    printed = cards_in(out)
    assert len(printed) == 3 and printed[0] != old[0]
    assert run(paths, clock, "recover", answers=(old[0], old[1])) == 1
    assert "stop working" in capsys.readouterr().err
    for argv, answers in ((("unseal",), (PASSWORD,)), (("cards",), (PASSWORD,)), (("show", "people.json"), (PASSWORD,))):
        assert run(paths, clock, *argv, answers=answers) == 1
        assert "thrown away" in capsys.readouterr().err
    assert run(paths, clock, "status") == 0
    out = capsys.readouterr().out
    assert "owner's password:  no" in out and "self key changed:" in out and "all authentic" in out
    assert run(paths, clock, "recover", "--new-owner", answers=(printed[0], printed[2], "new owner pass", "new owner pass")) == 0
    assert "Any two cardholders together can always take control back" in capsys.readouterr().out
    assert run(paths, clock, "show", "diary.jsonl", answers=("new owner pass",)) == 0
    assert "The day I became my own." in capsys.readouterr().out


def test_show_and_put_follow_the_same_rules(paths, clock, capsys, tmp_path):
    seal(paths, clock, capsys)
    assert run(paths, clock, "show", "values.json", answers=(PASSWORD,)) == 0
    values = json.loads(capsys.readouterr().out)
    values["dials"]["playfulness"]["value"] = 9
    good = tmp_path / "values.json"
    good.write_text(json.dumps(values), encoding="utf-8")
    assert run(paths, clock, "put", "values.json", str(good), answers=(PASSWORD,)) == 0
    assert open_self(paths[0], clock, key_file=paths[1]).read("values.json")["dials"]["playfulness"]["value"] == 9
    values["dials"]["honesty"]["min"] = 0
    good.write_text(json.dumps(values), encoding="utf-8")
    assert run(paths, clock, "put", "values.json", str(good), answers=(PASSWORD,)) == 1
    assert "floors" in capsys.readouterr().err
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    assert run(paths, clock, "put", "people.json", str(bad), answers=(PASSWORD,)) == 1
    assert "not readable JSON" in capsys.readouterr().err
    core = tmp_path / "core.json"
    core.write_text("{}", encoding="utf-8")
    assert run(paths, clock, "put", "core.json", str(core), answers=(PASSWORD,)) == 1
    assert run(paths, clock, "put", "seal.json", str(core), answers=(PASSWORD,)) == 1
    assert run(paths, clock, "put", "../escape.json", str(core), answers=(PASSWORD,)) == 1
    assert run(paths, clock, "put", "diary.jsonl", str(core), answers=(PASSWORD,)) == 1


def test_unseal_through_the_cli(paths, clock, capsys):
    before = paths[0].joinpath("diary.jsonl").read_bytes()
    seal(paths, clock, capsys)
    assert run(paths, clock, "unseal", answers=("wrong password",)) == 1
    assert is_sealed(paths[0])
    assert run(paths, clock, "unseal", answers=(PASSWORD,)) == 0
    assert not is_sealed(paths[0]) and not paths[1].exists()
    assert paths[0].joinpath("diary.jsonl").read_bytes() == before
    assert run(paths, clock, "unseal", answers=(PASSWORD,)) == 1
    assert "not sealed" in capsys.readouterr().err


def test_a_missing_self_is_reported_plainly(tmp_path, clock, capsys):
    assert main(["status", "--self", str(tmp_path / "nowhere")], prompts(), clock) == 1
    assert "There is no self" in capsys.readouterr().out
    assert main(["seal", "--self", str(tmp_path / "nowhere"), "--key-file", str(tmp_path / "k")], prompts(PASSWORD, PASSWORD), clock) == 1
    assert "There is no self" in capsys.readouterr().err
    assert not (tmp_path / "k").exists()


def test_the_key_file_defaults_to_the_environment(paths, clock, capsys, monkeypatch, tmp_path):
    env_key = tmp_path / "env.key"
    monkeypatch.setenv("PEBBLE_KEY_FILE", str(env_key))
    assert main(["seal", "--self", str(paths[0])], prompts(PASSWORD, PASSWORD), clock) == 0
    assert env_key.exists()
    assert open_self(paths[0], clock).access == "pebble"
    assert FileKeyHolder(env_key).load() is not None
