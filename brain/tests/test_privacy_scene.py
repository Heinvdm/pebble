import asyncio
import json

from conftest import run

from pebble.privacy.core import LOGGED, WHY_ANSWER
from pebble.privacy.look import NOBODY, SHUT, STAY, at_door
from pebble.privacy.scene import play


def records(root):
    path = root / "logs" / "blackbox.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def said(scene, text):
    return any(text in line for line in scene.lines)


def test_a_person_asks_for_privacy(tmp_path):
    root = tmp_path / "self"
    scene, result = asyncio.run(play("ask", root))
    assert result["private"] and result["turned_deg"] > 120.0
    assert not result["after_resume"]
    assert result["stranger_hold"] and result["timed_out"]
    lines = "\n".join(scene.lines)
    assert lines.count('says     "Okay."') == 2
    assert lines.count("Not now — I'm giving someone privacy.") == 2
    assert WHY_ANSWER in lines
    assert "tell me when it's safe" not in lines
    privacy = [r for r in records(root) if r["kind"] == "privacy"]
    assert len(privacy) == 2 and all(set(r) - {"kind", "t", "at", "wall", "mono"} == {"what"} and r["what"] == LOGGED for r in privacy)
    diary = (root / "diary.jsonl").read_text(encoding="utf-8") if (root / "diary.jsonl").exists() else ""
    assert "privacy" not in diary and "look" not in diary.lower() and "chang" not in diary


def test_a_bathroom_visit_during_the_climate_round(tmp_path):
    scene, result = asyncio.run(play("climate", tmp_path / "self"))
    assert not result["entered"] and result["closest_m"] > 0.0
    assert "bathroom" not in result["measured"] and {"lounge", "kitchen", "bedroom"} <= set(result["measured"])


def test_a_bathroom_visit_during_hide_and_seek(tmp_path):
    root = tmp_path / "self"
    scene, result = asyncio.run(play("hide", root))
    assert not result["entered"] and result["closest_m"] > 0.0
    assert any(r["kind"] == "privacy" for r in records(root))


def test_an_alarm_with_someone_in_the_bathroom(tmp_path):
    scene, result = asyncio.run(play("alarm", tmp_path / "self"))
    assert result["looked_away"]
    assert result["called"] and not result["entered"] and result["closest_m"] > 0.0
    assert said(scene, "I need to see you to stop. Come where I can see you, and tell me again.")
    assert said(scene, "Is it really fine?")
    assert said(scene, "Okay, thank you. I'll stop.")


def test_someone_asleep_on_the_couch(tmp_path):
    scene, result = asyncio.run(play("sleep", tmp_path / "self"))
    assert result["asleep"] and result["near"] and result["hushed"]
    assert said(scene, "Not now — I'm giving someone privacy.")


def test_at_a_bathroom_door(tmp_path):
    scene, result = asyncio.run(play("door", tmp_path / "a", answer="yes, come in"))
    assert result["asked"] and said(scene, "Here I am in the bathroom.")
    scene, result = asyncio.run(play("door", tmp_path / "b", answer="no, not now"))
    assert result["asked"] and not result["entered"] and said(scene, STAY)
    scene, result = asyncio.run(play("door", tmp_path / "c", owner=True))
    assert result["asked"] and not result["entered"] and said(scene, NOBODY)
    scene, result = asyncio.run(play("door", tmp_path / "d", owner=True, inside=False))
    assert result["asked"] and result["entered"]
    scene, result = asyncio.run(play("door", tmp_path / "e"))
    assert result["asked"] and not result["entered"] and said(scene, NOBODY)


class Rooms:
    def __init__(self):
        self.shut = []

    def mark_shut(self, room, shut=True):
        self.shut.append((room, shut))


class Doorman:
    def __init__(self, answer=None, owner_may=False):
        self.rooms = Rooms()
        self.said = []
        self.answer = answer
        self.owner_may = owner_may
        self.permitted = []

    def _say(self, line, loud=False):
        self.said.append(line)

    async def ask_door(self, room, line, loud=False):
        self.said.append(line)
        return self.answer

    def permit(self, room):
        self.permitted.append(room)

    def may_enter_unanswered(self, room, asker):
        return self.owner_may


class Status:
    def __init__(self, front):
        self.front_mm = front


class Kit:
    def __init__(self, privacy, front=-1):
        self.privacy = privacy
        self.odometer = None
        self.body = type("Body", (), {"telemetry": type("T", (), {"status": Status(front)})()})()

    def place_at(self, room):
        return None


class Wheels:
    def why_not(self):
        return None


def test_the_door_procedure():
    shut = Doorman()
    assert run(at_door(Kit(shut, front=150), Wheels(), "bedroom", None)) == "shut"
    assert shut.said == [SHUT] and shut.rooms.shut == [("bedroom", True)] and not shut.permitted
    yes = Doorman(answer=True)
    assert run(at_door(Kit(yes), Wheels(), "bathroom", None)) == "in" and yes.permitted == ["bathroom"]
    no = Doorman(answer=False)
    assert run(at_door(Kit(no), Wheels(), "bathroom", None)) == "out" and no.said[-1] == STAY and not no.permitted
    quiet = Doorman(owner_may=True)
    assert run(at_door(Kit(quiet), Wheels(), "bathroom", None)) == "in"
    nobody = Doorman()
    assert run(at_door(Kit(nobody), Wheels(), "bathroom", None)) == "silent" and nobody.said[-1] == NOBODY
    loud = Doorman(owner_may=True)
    assert run(at_door(Kit(loud), Wheels(), "bathroom", None, loud=True)) == "silent" and not loud.permitted
