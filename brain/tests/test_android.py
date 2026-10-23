import asyncio
import json
import os
import secrets
import shutil
import struct
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from pebble.android import bridge as bridges
from pebble.android import main as android_main
from pebble.android import seal as android_seal
from pebble.android.hearing import AndroidEars
from pebble.android.power import AndroidPower
from pebble.android.voice import AndroidVoice
from pebble.body.profile import BodyProfile, resolve_profile
from pebble.body.sensors import PhoneSensors
from pebble.clock import Clock, FakeClock
from pebble.eyes import eyes_from_config
from pebble.eyes.android import AndroidEyes, load_words, tag_seen
from pebble.eyes.fetch import MODELS
from pebble.life.quiet import QuietHours
from pebble.seal import AndroidAppKeyHolder, KeystoreUnavailable, holder_for, key_holder, open_self, seal_self, status
from pebble.seal.errors import DeviceKeyDamaged, SealError
from pebble.seal.keys import APP_KEY_HEADER
from pebble.seams.hearing import hearing_from
from pebble.seams.later import power_from
from pebble.seams.sight import NoEyes
from pebble.seams.voice import TranscriptVoice, voice_from
from pebble.self.recall.embed import DIM, ONNX_NAME, OnnxEmbedder, StandIn, embedder_from
from pebble.selfstore import SelfIsSealed, SelfStore

PASSWORD = "correct horse battery"
FAST = {"n": 2**10, "r": 8, "p": 1}


def run(coro, timeout: float = 30.0):
    return asyncio.run(asyncio.wait_for(coro, timeout))


class FakePhone:
    def __init__(self, folder: Path, strongbox: bool = True):
        self.folder = Path(folder)
        self.aes: bytes | None = None
        self.strongbox = strongbox
        self.spoken: list[tuple[str, bool]] = []
        self.listening: list[bool] = []
        self.ears = None
        self.power: list[str] = []
        self.eyes_calls: list[tuple] = []
        self.sink = None
        self.speech_configs: list[dict] = []
        self.parts: list[tuple] = []
        self.stops = 0
        self.held = {"id": 7, "camera": "front", "t": 0.0, "w": 640, "h": 480, "fov": 70.0, "tags": []}
        self.proposals = []
        self.battery_json = json.dumps({"percent": 64, "charging": True, "temperature_c": 31.5})
        self.temperature_value = 38.25
        self.light_value = 120.0
        self.motion_json = json.dumps({"accel": [0.1, 9.7, 0.3], "gyro": [0.0, 0.01, 0.0]})

    def keyFile(self) -> str:
        return str(self.folder / "keys" / "pebble-device.key")

    def keyExists(self) -> bool:
        return self.aes is not None

    def keyCreate(self) -> bool:
        self.aes = AESGCM.generate_key(256)
        return self.strongbox

    def keyWrap(self, data) -> bytes:
        iv = secrets.token_bytes(12)
        return iv + AESGCM(self.aes).encrypt(iv, bytes(data), b"pebble-device-key v1")

    def keyUnwrap(self, blob) -> bytes:
        blob = bytes(blob)
        return AESGCM(self.aes).decrypt(blob[:12], blob[12:], b"pebble-device-key v1")

    def keyDelete(self) -> None:
        self.aes = None

    def keyInfo(self) -> str:
        return json.dumps({"exists": self.aes is not None, "strongbox": self.strongbox, "secure": True})

    def battery(self) -> str:
        return self.battery_json

    def temperature(self) -> float:
        return self.temperature_value

    def light(self) -> float:
        return self.light_value

    def motion(self) -> str:
        return self.motion_json

    def speak(self, text: str, whisper: bool) -> bool:
        self.spoken.append((text, whisper))
        return True

    def listen(self, on: bool) -> None:
        self.listening.append(bool(on))

    def speechConfig(self, text: str) -> None:
        self.speech_configs.append(json.loads(text))

    def earsState(self) -> str:
        return json.dumps({"listening": bool(self.listening and self.listening[-1]), "mode": next((c["mode"] for c in reversed(self.speech_configs) if "mode" in c), "off"), "aec": True, "engine": "fake"})

    def sayPart(self, part_id: str, text: str, last: bool, whisper: bool) -> bool:
        self.parts.append((part_id, text, last, whisper))
        return True

    def stopSpeaking(self) -> float:
        self.stops += 1
        return 3.0

    def earsSink(self, sink) -> None:
        self.ears = sink

    def hearingInfo(self) -> str:
        return json.dumps({"on_device": True})

    def powerOff(self, mode: str) -> str:
        self.power.append(mode)
        return "screen off, models stopped"

    def eyesSink(self, sink) -> None:
        self.sink = sink

    def eyesStart(self, config: str) -> None:
        self.eyes_calls.append(("start", json.loads(config)))

    def eyesStop(self) -> None:
        self.eyes_calls.append(("stop",))

    def eyesUse(self, camera: str) -> None:
        self.eyes_calls.append(("use", camera))

    def eyesEnable(self, on: bool) -> None:
        self.eyes_calls.append(("enable", on))

    def eyesBusy(self, busy: bool) -> None:
        self.eyes_calls.append(("busy", busy))

    def eyesMoved(self) -> None:
        self.eyes_calls.append(("moved",))

    def eyesLookClosely(self, demand: int) -> None:
        self.eyes_calls.append(("closely", demand))

    def eyesStatus(self) -> str:
        return json.dumps({"backend": "fake"})

    def eyesPrints(self, top: int) -> None:
        self.eyes_calls.append(("prints", top))

    def eyesHold(self) -> str:
        self.eyes_calls.append(("hold",))
        return json.dumps(self.held)

    def eyesEmbed(self, held_id: int, boxes: str, size: int) -> str:
        self.eyes_calls.append(("embed", held_id, size))
        return json.dumps([print_of(b) for b in json.loads(boxes)])

    def eyesPropose(self, held_id: int, score: float) -> str:
        self.eyes_calls.append(("propose", held_id, score))
        return json.dumps(self.proposals)

    def eyesRelease(self, held_id: int) -> None:
        self.eyes_calls.append(("release", held_id))

    jpeg = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"a picture" + bytes([0xFF, 0xD9])

    def eyesMouths(self, on: bool, tail_s: float) -> None:
        self.eyes_calls.append(("mouths", on, tail_s))

    def eyesHazardsEvery(self, seconds: float) -> None:
        self.eyes_calls.append(("hazards_every", seconds))

    def eyesSnapshot(self, camera: str, max_side: int, max_age_s: float) -> bytes:
        self.eyes_calls.append(("snapshot", camera, max_side, max_age_s))
        return self.jpeg

    def eyesMoving(self, on: bool) -> None:
        self.eyes_calls.append(("moving", on))

    def eyesScanFloor(self) -> None:
        self.eyes_calls.append(("scan_floor",))

    def eyesHead(self, head: str) -> None:
        self.eyes_calls.append(("head", json.loads(head)))


def print_of(box) -> list:
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    vec = [0.0] * 384
    vec[int(cx * 10) % 384] = 1.0
    vec[100 + int(cy * 10) % 100] = 1.0
    return vec


@pytest.fixture
def phone(tmp_path):
    found = FakePhone(tmp_path / "phone")
    bridges.install(found)
    yield found
    bridges.install(None)


@pytest.fixture(autouse=True)
def no_holder_env(monkeypatch):
    monkeypatch.delenv("PEBBLE_KEY_HOLDER", raising=False)
    monkeypatch.delenv("PEBBLE_KEY_FILE", raising=False)


def make_self(root: Path) -> None:
    SelfStore.open(root, Clock())


def test_the_app_holder_wraps_a_random_key_and_keeps_only_the_wrapped_copy(phone):
    holder = AndroidAppKeyHolder()
    assert holder.load() is None
    key = holder.load_or_create()
    assert len(key) == 32 and holder.load() == key and holder.load_or_create() == key
    text = Path(phone.keyFile()).read_text(encoding="ascii")
    assert text.startswith(APP_KEY_HEADER) and key.hex() not in text and key not in Path(phone.keyFile()).read_bytes()
    assert holder.secure_hardware() is True
    assert "Pebble app's keystore" in holder.where()
    holder.delete()
    assert holder.load() is None and phone.aes is None


def test_a_lost_keystore_key_is_damage_not_a_silent_new_key(phone):
    holder = AndroidAppKeyHolder()
    holder.load_or_create()
    phone.keyDelete()
    with pytest.raises(DeviceKeyDamaged, match="keystore key that opens it is gone"):
        holder.load()


def test_outside_the_app_the_holder_says_where_it_works():
    bridges.install(None)
    holder = key_holder(None, "android-app")
    assert isinstance(holder, AndroidAppKeyHolder) and holder.where() == "the Pebble app's keystore"
    with pytest.raises(KeystoreUnavailable, match="only the Pebble Android app"):
        holder.load()


def test_a_self_sealed_with_the_app_keystore_opens_on_its_phone_and_nowhere_else(tmp_path, phone, monkeypatch):
    monkeypatch.setattr("pebble.seal.locks.DEFAULT_KDF", FAST, raising=False)
    root = tmp_path / "self"
    make_self(root)
    seal_self(root, PASSWORD, AndroidAppKeyHolder(), kdf=FAST)
    assert holder_for(root).kind == "android-app"
    store = open_self(root, Clock())
    assert store.read("core.json")["laws"]
    found = status(root, holder_for(root))
    assert found.sealed and found.device == "opens" and found.secure is True and found.lock_holder == "android-app"
    copy = tmp_path / "stolen"
    shutil.copytree(root, copy)
    shutil.copytree(phone.folder, tmp_path / "stolen-phone")
    other = FakePhone(tmp_path / "stolen-phone")
    other.keyCreate()
    bridges.install(other)
    with pytest.raises((SealError, SelfIsSealed)):
        open_self(copy, Clock())
    bridges.install(None)
    with pytest.raises((SealError, SelfIsSealed)):
        open_self(copy, Clock())


def test_the_app_seal_calls_seal_print_cards_and_recover_on_a_new_phone(tmp_path, phone):
    root = tmp_path / "self"
    make_self(root)
    assert json.loads(android_seal.finish_setup(str(root)))["ok"]
    sealed = json.loads(android_seal.seal(str(root), PASSWORD))
    assert sealed["ok"], sealed
    assert len(sealed["cards"]) == 3
    again = json.loads(android_seal.cards(str(root), PASSWORD))
    assert again["ok"] and again["cards"] == sealed["cards"]
    shown = json.loads(android_seal.status(str(root)))
    assert shown["ok"] and shown["status"]["sealed"] and shown["status"]["device"] == "opens"
    new_phone = FakePhone(tmp_path / "new-phone")
    bridges.install(new_phone)
    with pytest.raises((SealError, SelfIsSealed)):
        open_self(root, Clock())
    refused = json.loads(android_seal.recover(str(root), "not a card", sealed["cards"][1], new_phone))
    assert not refused["ok"]
    recovered = json.loads(android_seal.recover(str(root), sealed["cards"][0], sealed["cards"][2], new_phone))
    assert recovered["ok"], recovered
    assert open_self(root, Clock()).read("core.json")["laws"]
    wrong = json.loads(android_seal.seal(str(root), PASSWORD))
    assert not wrong["ok"] and "already sealed" in wrong["message"]


def test_a_key_file_lock_moves_into_the_app_keystore(tmp_path, phone):
    from pebble.seal import FileKeyHolder

    root = tmp_path / "self"
    make_self(root)
    key_file = tmp_path / "pc" / "self.key"
    seal_self(root, PASSWORD, FileKeyHolder(key_file), kdf=FAST)
    moved = json.loads(android_seal.move_lock(str(root), str(key_file)))
    assert moved["ok"], moved
    assert not key_file.exists() and holder_for(root).kind == "android-app"
    assert open_self(root, Clock()).read("core.json")


def test_android_sensors_fill_the_snapshot(phone):
    profile = BodyProfile.load(resolve_profile("android", "body"))
    sensors = PhoneSensors.from_config(profile.sensors)
    snapshot = sensors.read()
    assert snapshot.battery.percent == 64 and snapshot.battery.charging is True and snapshot.battery.source == "android"
    assert snapshot.temperature_c == 38.25 and snapshot.light_lux == 120.0
    assert snapshot.imu.accel == (0.1, 9.7, 0.3)
    phone.temperature_value = float("nan")
    phone.light_value = -1.0
    phone.motion_json = ""
    phone.battery_json = json.dumps({"percent": -1})
    snapshot = sensors.read()
    assert snapshot.battery is None and snapshot.temperature_c is None and snapshot.light_lux is None and snapshot.imu is None


def test_the_phone_speaks_and_the_transcript_is_still_kept(tmp_path, phone):
    store = SelfStore.open(tmp_path / "self", FakeClock())
    voice = voice_from({"kind": "android"}, store, FakeClock())
    assert isinstance(voice, AndroidVoice)
    result = run(voice.say("  Hello   there ", whisper=True))
    assert result.spoken and result.engine == "android-tts"
    assert phone.spoken == [("Hello there", True)]
    assert voice.lines == ["Hello there"]
    assert isinstance(voice_from({}, store, FakeClock()), TranscriptVoice)


def test_power_on_android_rests_the_phone(phone):
    power = power_from({"kind": "android"})
    assert isinstance(power, AndroidPower) and power.shutdown()
    assert phone.power == ["rest"]
    assert not AndroidPower("none").shutdown()


class EarLife:
    def __init__(self):
        self.quiet_hours = QuietHours.from_preferences({"quiet_hours": {"start": "22:00", "end": "07:00"}})
        self.heard: list[str] = []

    def hear(self, text: str, voice=None, loud: bool = False):
        self.heard.append(text)


def test_ears_listen_by_day_feed_life_and_stop_in_quiet_hours(phone):
    clock = FakeClock.at(datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc))
    ears = hearing_from({"kind": "android"}, clock)
    assert isinstance(ears, AndroidEars)
    ears.check_s = 0.01
    life = EarLife()

    async def scenario():
        task = asyncio.create_task(ears.run(life))
        await asyncio.sleep(0.05)
        assert phone.listening == [True] and phone.ears is ears
        threading.Thread(target=phone.ears.heard, args=("  follow   me ",)).start()
        await asyncio.sleep(0.05)
        assert life.heard == ["follow me"]
        clock.advance(11 * 3600)
        await asyncio.sleep(0.05)
        assert phone.listening[-1] is False
        phone.ears.heard("are you awake")
        await asyncio.sleep(0.02)
        assert life.heard == ["follow me"] and ears.dropped == 1
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert phone.ears is None

    run(scenario())
    assert hearing_from({}, clock) is None


def test_ears_can_be_woken_at_night_for_a_while(phone):
    clock = FakeClock.at(datetime(2026, 10, 15, 23, 0, tzinfo=timezone.utc))
    ears = AndroidEars(clock, check_s=0.01)
    life = EarLife()

    async def scenario():
        task = asyncio.create_task(ears.run(life))
        await asyncio.sleep(0.05)
        assert not ears.listening and phone.listening == []
        ears.wake_for(30)
        await asyncio.sleep(0.05)
        assert ears.listening and phone.listening == [True]
        phone.ears.heard("help")
        await asyncio.sleep(0.02)
        assert life.heard == ["help"]
        clock.advance(31)
        await asyncio.sleep(0.05)
        assert not ears.listening and phone.listening[-1] is False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    run(scenario())


def frame(camera="front", t=None, **parts) -> str:
    data = {"camera": camera, "t": time.monotonic() if t is None else t, "w": 640, "h": 480}
    data.update(parts)
    return json.dumps(data)


def make_eyes(phone, **kwargs) -> AndroidEyes:
    words = load_words(MODELS / "objects_vocab.json")
    eyes = AndroidEyes(Clock(), words=words, **kwargs)
    eyes.start()
    return eyes


def test_android_eyes_turn_raw_boxes_into_people_and_things(phone):
    eyes = make_eyes(phone)
    assert phone.eyes_calls[0][0] == "start" and phone.sink is eyes
    config = phone.eyes_calls[0][1]
    assert config["slow"]["on"] and config["slow"]["classes"] == len(eyes.classes) and config["tag_id"] == 0
    assert eyes.feed(frame(faces=[[0.45, 0.2, 0.1, 0.13, 0.9]], objects=[[0.4, 0.15, 0.2, 0.8, 0.8, 0], [0.7, 0.6, 0.1, 0.2, 0.7, 15], [0.1, 0.1, 0.1, 0.1, 0.9, 5]]))
    sight = eyes.latest(1.0)
    assert sight.camera == "front" and len(sight.people) == 1
    person = sight.people[0]
    assert person.face and person.bearing_deg == pytest.approx(0, abs=0.5) and person.height_frac == pytest.approx(0.8)
    assert [t.label for t in sight.things] == ["cat"] and sight.things[0].animal
    assert eyes.feed(frame(faces=[[0.47, 0.2, 0.1, 0.13, 0.9]]))
    again = eyes.latest(1.0)
    assert again.people[0].track == person.track and [t.label for t in again.things] == ["cat"]
    assert not eyes.feed("not json") and not eyes.feed(frame(camera="side"))
    assert eyes.status()["frames"] == 2 and eyes.status()["phone"] == {"backend": "fake"}


def test_android_eyes_switch_cameras_and_report_failures(phone):
    async def scenario():
        eyes = make_eyes(phone)
        eyes.feed(frame())
        task = asyncio.create_task(eyes.use_camera("rear"))
        await asyncio.sleep(0.01)
        assert ("use", "rear") in phone.eyes_calls
        threading.Thread(target=eyes.feed, args=(frame(camera="rear"),)).start()
        assert await task
        assert eyes.camera() == "rear"
        task = asyncio.create_task(eyes.use_camera("front"))
        await asyncio.sleep(0.01)
        eyes.state(json.dumps({"state": "failed", "camera": "front", "problem": "the camera is busy"}))
        assert not await task and "busy" in eyes.status()["problem"]
        eyes.set_enabled(False)
        assert ("enable", False) in phone.eyes_calls and eyes.latest(5) is None and not await eyes.use_camera("rear")
        eyes.close()
        assert phone.eyes_calls[-1] == ("stop",)

    run(scenario())


def test_android_eyes_look_closely_with_the_slow_lane(phone):
    async def scenario():
        eyes = make_eyes(phone)
        cup = next(i for i, c in enumerate(eyes.classes) if c["label"] == "cup")
        mug = next((i for i, c in enumerate(eyes.classes) if c["label"] in ("coffee cup", "mug")), None)
        eyes.feed(frame(objects=[[0.3, 0.5, 0.1, 0.1, 0.8, 41]]))
        assert [t.label for t in eyes.latest(1).things] == ["cup"]
        task = asyncio.create_task(eyes.look_closely(2.0))
        await asyncio.sleep(0.01)
        demand = next(call[1] for call in phone.eyes_calls if call[0] == "closely")
        pick = mug if mug is not None else cup
        found = [[0.3, 0.5, 0.1, 0.1, 0.9, pick], [0.7, 0.2, 0.05, 0.05, 0.8, cup]]
        threading.Thread(target=eyes.slow, args=(json.dumps({"camera": "front", "t": time.monotonic(), "w": 640, "h": 480, "found": found, "demand": [demand], "ms": 210}),)).start()
        closer = await task
        labels = sorted(t.label for t in closer.things)
        assert len(closer.things) == 2 and any(t.lane == "slow" for t in closer.things)
        assert eyes.classes[pick]["label"] in labels
        eyes.set_busy(True)
        eyes.moved()
        assert ("busy", True) in phone.eyes_calls and ("moved",) in phone.eyes_calls

    run(scenario())


def test_android_eyes_come_from_the_profile_and_need_the_app(phone):
    profile = BodyProfile.load(resolve_profile("android", "body"))
    eyes = eyes_from_config(profile.eyes, Clock())
    assert isinstance(eyes, AndroidEyes) and phone.sink is eyes
    assert phone.eyes_calls[0][1]["cameras"]["rear"]["width"] == 1280
    bridges.install(None)
    assert isinstance(eyes_from_config(profile.eyes, Clock()), NoEyes)


def test_a_tag_pose_from_the_phone_reads_like_the_opencv_eyes():
    cv2 = pytest.importorskip("cv2", reason="OpenCV is not installed")
    np = pytest.importorskip("numpy")
    from pebble.eyes.detect import Detector
    from pebble.eyes.geometry import focal
    from pebble.eyes.scene import TagPlacement, tag_scene

    detector = Detector(faces=False, bodies=False)
    for distance, bearing, yaw in [(0.5, 5, 20), (0.4, -12, -30), (1.2, 0, 10)]:
        picture = tag_scene(1280, 960, 65, TagPlacement(distance, bearing, 0, yaw))
        expected = detector.tags(picture, 65)[0].seen
        gray = cv2.cvtColor(picture, cv2.COLOR_BGR2GRAY)
        aruco = cv2.aruco
        found = aruco.ArucoDetector(aruco.getPredefinedDictionary(aruco.DICT_APRILTAG_36h11), aruco.DetectorParameters())
        params = found.getDetectorParameters()
        params.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
        found.setDetectorParameters(params)
        corners, ids, _ = found.detectMarkers(gray)
        points = corners[0].reshape(4, 2).astype(np.float64)
        f = focal(1280, 65)
        camera = np.array([[f, 0, 640], [0, f, 480], [0, 0, 1]], np.float64)
        half = 0.048 / 2
        square = np.array([[-half, half, 0], [half, half, 0], [half, -half, 0], [-half, -half, 0]], np.float64)
        _, rvecs, tvecs, errors = cv2.solvePnPGeneric(square, points, camera, None, flags=cv2.SOLVEPNP_IPPE_SQUARE)
        poses = []
        for rvec, tvec, err in zip(rvecs, tvecs, np.array(errors).reshape(-1)):
            rotation, _ = cv2.Rodrigues(rvec)
            poses.append({"t": tvec.reshape(3).tolist(), "n": rotation[:, 2].tolist(), "err": float(err)})
        px = float(np.mean([np.linalg.norm(points[i] - points[(i + 1) % 4]) for i in range(4)]))
        assert tag_seen(int(ids[0][0]), json.loads(json.dumps(poses)), px) == expected


def test_the_android_entry_runs_the_brain_writes_a_heartbeat_and_stops(tmp_path, phone):
    beat = tmp_path / "files" / "brain.alive"
    log_file = tmp_path / "files" / "logs" / "brain.log"
    argv = ["--self", str(tmp_path / "self"), "--sim", "--body", "android", "--mind", "scripted", "--dry-run", "--heartbeat", "0.3", "--screen", "--screen-port", "0", "--presence", "none", "--seconds", "20"]
    result = {}
    worker = threading.Thread(target=lambda: result.setdefault("code", android_main.run(argv, phone, str(beat), str(log_file))))
    worker.start()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not beat.exists():
        time.sleep(0.05)
    assert beat.exists()
    time.sleep(1.0)
    assert android_main.stop()
    worker.join(20)
    assert not worker.is_alive() and result["code"] == 0
    assert "brain starting on Android" in log_file.read_text(encoding="utf-8")
    assert not phone.listening or phone.listening[-1] is False
    assert phone.ears is None
    assert not android_main.stop()


def standing_points(box) -> list:
    x, y, w, h = box
    out = []
    for i in range(17):
        u = x + w * (0.4 + 0.2 * (i % 2))
        v = y + h * (0.05 + 0.055 * i)
        out += [u, v, 0.9]
    return out


def test_android_eyes_give_people_their_body_points(phone):
    pytest.importorskip("numpy")
    eyes = make_eyes(phone)
    body = [0.4, 0.15, 0.2, 0.8]
    assert eyes.feed(frame(faces=[[0.45, 0.2, 0.1, 0.13, 0.9]], objects=[body + [0.8, 0]], poses=[{"box": body, "points": standing_points(body)}], ))
    person = eyes.latest(1.0).people[0]
    assert len(person.points) == 17 and person.points[0].name == "nose"
    assert person.points[0].score == 0.9
    later = eyes.clock.monotonic() + 2.0
    assert eyes.feed(frame(t=later, faces=[[0.45, 0.2, 0.1, 0.13, 0.9]], objects=[body + [0.8, 0]]))
    assert eyes.latest(5.0).people[0].points == ()


def test_android_eyes_learn_a_thing_and_find_it_again(phone):
    pytest.importorskip("numpy")

    async def scenario():
        eyes = make_eyes(phone)
        ball = [0.6, 0.6, 0.1, 0.1]
        eyes.feed(frame(objects=[ball + [0.8, 32]]))
        sight = eyes.latest(1.0)
        track = sight.things[0].track
        vec = await eyes.fingerprint(track)
        assert vec is not None and len(vec) == 384
        assert ("hold",) in phone.eyes_calls and ("release", 7) in phone.eyes_calls
        assert eyes.remember_print("my ball", vec) == 1
        assert ("prints", 6) in phone.eyes_calls
        rows = [ball + [0.9, 0]]
        eyes.slow(json.dumps({"camera": "front", "t": time.monotonic(), "w": 640, "h": 480, "found": rows, "print_rows": [0], "prints": [print_of(ball)]}))
        eyes.feed(frame(objects=[ball + [0.8, 32]]))
        known = [t for t in eyes.latest(1.0).things if t.known]
        assert known and known[0].known == "my ball" and known[0].known_score >= 0.99
        phone.proposals = [ball + [0.2, 5]]
        found = await eyes.look_for("my ball")
        assert found is not None and found.known == "my ball" and found.label == "my ball"
        assert found.bearing_deg > 0 and found.elevation_deg < 0
        assert await eyes.look_for("someone else's ball") is None
        assert eyes.forget_print("my ball") and ("prints", 0) in phone.eyes_calls

    run(scenario())


def test_the_dock_print_is_taken_where_the_tag_says(phone):
    pytest.importorskip("numpy")

    async def scenario():
        eyes = make_eyes(phone)
        eyes.feed(frame(camera="front"))
        phone.held = {"id": 9, "camera": "rear", "t": 0.0, "w": 640, "h": 480, "fov": 65.0, "tags": [{"id": 0, "px": 90.0, "poses": [{"t": [0.0, 0.05, 0.5], "n": [0.0, 0.0, -1.0], "r": [-1.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, -1.0], "err": 0.1}]}]}
        vec = await eyes.dock_print()
        assert vec is not None and len(vec) == 384
        embeds = [c for c in phone.eyes_calls if c[0] == "embed"]
        assert embeds[-1][1] == 9
        phone.held = {"id": 10, "camera": "rear", "w": 640, "h": 480, "fov": 65.0, "tags": []}
        assert await eyes.dock_print() is None

    run(scenario())


def test_ears_choose_a_listening_mode_and_tell_the_phone_only_when_it_changes(phone):
    clock = FakeClock.at(datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc))
    ears = AndroidEars(clock, check_s=0.01)
    ears.policy = lambda quiet, awake: "keywords" if quiet else "words"
    life = EarLife()

    async def scenario():
        task = asyncio.create_task(ears.run(life))
        await asyncio.sleep(0.05)
        assert phone.speech_configs == [{"mode": "words"}] and phone.listening == [True]
        clock.advance(11 * 3600)
        await asyncio.sleep(0.05)
        assert phone.speech_configs[-1] == {"mode": "keywords"} and ears.listening
        ears.wake_for(10)
        await asyncio.sleep(0.05)
        assert phone.speech_configs[-1] == {"mode": "words"}
        clock.advance(11)
        await asyncio.sleep(0.05)
        assert phone.speech_configs[-1] == {"mode": "keywords"}
        assert len(phone.speech_configs) == 4
        ears.policy = lambda quiet, awake: "nonsense"
        await asyncio.sleep(0.05)
        assert phone.speech_configs[-1] == {"mode": "off"} and phone.listening[-1] is False
        ears.configure(keywords=[{"word": "pebble", "tokens": "PE BB LE"}])
        assert phone.speech_configs[-1]["keywords"][0]["word"] == "pebble"
        assert ears.status()["state"]["aec"] is True
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    run(scenario())


def test_the_voice_speaks_part_by_part_and_stops_at_once(tmp_path, phone):
    store = SelfStore.open(tmp_path / "self", FakeClock())
    voice = voice_from({"kind": "android"}, store, FakeClock())
    assert voice.say_part("r7.0", "Hello there,", False, False)
    assert voice.say_part("r7.1", "how are you?", True, True)
    voice.stop_speaking()
    assert phone.parts == [("r7.0", "Hello there,", False, False), ("r7.1", "how are you?", True, True)]
    assert phone.stops == 1


def hazard_eyes(phone, clock=None, **kwargs) -> AndroidEyes:
    eyes = AndroidEyes(clock or Clock(), words=load_words(MODELS / "objects_vocab.json"), **kwargs)
    eyes.start()
    return eyes


def glow_of(box=None, level=0) -> str:
    import base64

    from pebble.eyes.hazards import cells

    grid = bytearray(80 * 60)
    if box is not None:
        x0, y0, x1, y1 = cells(box)
        for y in range(y0, y1):
            grid[y * 80 + x0:y * 80 + x1] = bytes([level]) * (x1 - x0)
    return base64.b64encode(bytes(grid)).decode("ascii")


def hazard_rows(eyes, t, *found, camera="front", ms=850.0) -> str:
    index = {}
    for i, entry in enumerate(eyes.hazard_classes):
        index.setdefault(entry["label"], i)
    rows = [list(box) + [score, index[label]] for label, box, score in found]
    return json.dumps({"camera": camera, "t": t, "w": 640, "h": 480, "ms": ms, "found": rows})


def test_android_eyes_judge_posture_with_the_head_they_are_told(phone):
    pytest.importorskip("numpy")
    from bodies import view

    eyes = make_eyes(phone)

    def judged(pose, **where):
        raw, box = view(pose, 2.5, **where)
        body = [box.x, box.y, box.w, box.h]
        points = [round(float(v), 4) for v in raw.reshape(-1)]
        assert eyes.feed(frame(objects=[body + [0.9, 0]], poses=[{"box": body, "points": points}]))
        person = eyes.latest(1.0).people[0]
        return person.posture, person.posture_score

    assert judged("standing")[0] == "standing"
    label, sure = judged("lying_floor")
    assert label == "lying" and sure >= 0.5
    assert eyes.status()["head"] == {"tilt_deg": 8.0, "roll_deg": 0.0}
    eyes.set_head(tilt_deg=20.0, roll_deg=3.0)
    assert eyes.head("front") == (0.14, 20.0, 3.0) and eyes.head("rear") == (0.14, -20.0, -3.0)
    eyes.set_head(roll_deg=0.0)
    assert judged("lying_floor", pitch_deg=20.0)[0] == "lying"
    assert judged("standing", pitch_deg=20.0)[0] == "standing"
    assert eyes.status()["head"] == {"tilt_deg": 20.0, "roll_deg": 0.0}


def test_android_eyes_place_things_on_the_floor(phone):
    from pebble.eyes.geometry import floor_point

    eyes = make_eyes(phone)
    parts = {"objects": [[0.45, 0.8, 0.1, 0.1, 0.8, 41], [0.2, 0.1, 0.1, 0.1, 0.8, 74]]}
    things = {t.label: t for t in eyes.process(json.loads(frame(**parts))).things}
    assert things["clock"].floor_m is None and things["clock"].floor_bearing_deg is None
    want = floor_point(0.5, 0.9, 640, 480, 70.0, 0.14, 8.0)
    assert things["cup"].floor_m == pytest.approx(want[0], abs=1e-3) and abs(things["cup"].floor_bearing_deg) < 0.01
    eyes.set_head(tilt_deg=-10.0)
    nearer = {t.label: t for t in eyes.process(json.loads(frame(**parts))).things}["cup"]
    assert nearer.floor_m < things["cup"].floor_m
    eyes.set_head(tilt_deg=8.0)
    behind = {t.label: t for t in eyes.process(json.loads(frame(camera="rear", **parts))).things}["cup"]
    assert behind.floor_m == pytest.approx(floor_point(0.5, 0.9, 640, 480, 65.0, 0.14, -8.0)[0], abs=1e-3)


def test_android_eyes_pass_small_life_from_the_hazard_lane_to_the_brain(phone):
    from pebble.respect import life_kind

    clock = FakeClock()
    eyes = hazard_eyes(phone, clock)
    t0 = clock.monotonic()
    assert eyes.feed(frame(t=t0, warm=0.0, glow=glow_of()))
    assert eyes.hazards_seen(hazard_rows(eyes, t0, ("snail", [0.45, 0.82, 0.05, 0.04], 0.5), ("plant", [0.1, 0.4, 0.2, 0.5], 0.6)))
    clock.advance(0.1)
    assert eyes.feed(frame(t=clock.monotonic(), warm=0.0, glow=glow_of()))
    seen = {t.label: t for t in eyes.latest(1.0).things}
    assert seen["snail"].animal and seen["snail"].lane == "hazard" and seen["snail"].floor_m is not None
    assert not seen["plant"].animal and life_kind(seen["plant"].label) == "plant"


def test_android_eyes_watch_for_fire_on_the_phone_s_numbers(phone):
    clock = FakeClock()
    eyes = hazard_eyes(phone, clock)
    assert phone.eyes_calls[0][1]["hazards"] == {"on": True, "every_s": 3.0, "score": 0.25, "threads": 1, "classes": 26}
    fire = [0.4, 0.4, 0.2, 0.2]
    t0 = clock.monotonic()
    assert eyes.feed(frame(t=t0, warm=0.0, glow=glow_of()))
    assert eyes.hazards_seen(hazard_rows(eyes, t0, ("fire", fire, 0.6)))
    assert phone.eyes_calls[-1] == ("hazards_every", 0.8)
    box = eyes.hazards.fire_boxes()[0]
    for n in range(1, 31):
        clock.advance(0.1)
        bright = n % 2
        assert eyes.feed(frame(t=clock.monotonic(), warm=0.05 if bright else 0.0, glow=glow_of(box, 250 if bright else 140)))
    seen = {t.label: t for t in eyes.latest(1.0).things}
    assert seen["fire"].lane == "hazard" and seen["fire"].floor_m is None
    assert eyes.status()["hazards"]["tracks"][0]["flicker"] >= 0.8 and eyes.status()["hazards"]["close_watch"]
    assert eyes.hazards_seen(hazard_rows(eyes, clock.monotonic(), ("fire", fire, 0.6)))
    found = [t for t in eyes.hazards.current("front", clock.monotonic()) if t.label == "fire"]
    assert found[0].box.score >= 0.85
    assert eyes.status()["hazards"]["ms"] == 850.0 and eyes.status()["ms"]["hazards"] == 850.0
    assert eyes.feed(frame(t=clock.monotonic(), warm=0.0, glow="not a picture"))
    for _ in range(12):
        clock.advance(0.1)
        assert eyes.feed(frame(t=clock.monotonic(), warm=0.0, glow=glow_of()))
    assert phone.eyes_calls[-1] == ("hazards_every", 0.8)
    clock.advance(7.0)
    assert eyes.feed(frame(t=clock.monotonic(), warm=0.0, glow=glow_of()))
    assert phone.eyes_calls[-1] == ("hazards_every", 3.0)
    assert not [t for t in eyes.latest(1.0).things if t.lane == "hazard"]
    assert not eyes.hazards_seen(json.dumps({"failed": True, "problem": "the hazard watch is off: no model"}))
    assert eyes.status()["hazards"]["problem"] == "the hazard watch is off: no model"


def test_android_eyes_name_a_fire_inside_a_tv_after_the_tv(phone):
    clock = FakeClock()
    eyes = hazard_eyes(phone, clock)
    t0 = clock.monotonic()
    assert eyes.feed(frame(t=t0, objects=[[0.3, 0.3, 0.3, 0.3, 0.8, 62]], warm=0.0, glow=glow_of()))
    assert eyes.hazards_seen(hazard_rows(eyes, t0, ("fire", [0.4, 0.4, 0.1, 0.1], 0.7), ("tv", [0.31, 0.31, 0.28, 0.28], 0.6)))
    assert sorted(t.label for t in eyes.hazards.current("front", t0)) == ["tv", "tv"]
    clock.advance(0.1)
    assert eyes.feed(frame(t=clock.monotonic(), warm=0.0, glow=glow_of()))
    assert sorted((t.label, t.lane) for t in eyes.latest(1.0).things) == [("tv", "fast"), ("tv", "hazard")]
    clock.advance(2.0)
    t1 = clock.monotonic()
    assert eyes.feed(frame(t=t1, objects=[], warm=0.0, glow=glow_of()))
    assert eyes.hazards_seen(hazard_rows(eyes, t1, ("fire", [0.4, 0.4, 0.1, 0.1], 0.7)))
    assert [t.label for t in eyes.hazards.current("front", t1)] == ["fire"]
    eyes.set_enabled(False)
    assert eyes.hazards.current("front", t1) == [] and eyes.status()["hazards"]["tracks"] == []
    assert not eyes.hazards_seen(hazard_rows(eyes, t1, ("fire", [0.4, 0.4, 0.1, 0.1], 0.7)))


def test_the_phone_s_glow_numbers_match_the_pc_hazard_watch(phone):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    import base64

    from pebble.eyes.android import HazardRows
    from pebble.eyes.geometry import Box
    from pebble.eyes.hazards import HazardWatch
    from pebble.eyes.slow import SlowFound

    image = np.random.default_rng(3).integers(0, 256, (480, 640, 3), dtype=np.uint8)
    image[190:290, 250:390] = (20, 120, 250)
    small = cv2.resize(image, (80, 60), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    warm = float((((hsv[:, :, 0] <= 22) | (hsv[:, :, 0] >= 170)) & (hsv[:, :, 1] >= 110) & (hsv[:, :, 2] >= 190)).mean())
    glow = base64.b64encode(small.max(axis=2).tobytes()).decode("ascii")
    fires = [[0.4, 0.4, 0.2, 0.2], [0.97, 0.9, 0.03, 0.1], [0.0, 0.0, 0.013, 0.02]]
    noted = {}
    clock = FakeClock()
    eyes = hazard_eyes(phone, clock)
    rows = HazardRows(eyes.hazard_classes)
    rows.found = [SlowFound(Box(*box, 0.6), "fire", False, "fire", 6) for box in fires]
    reference = HazardWatch(lambda: rows, clock.monotonic)
    reference.detector = rows
    reference.look(None, "front", clock.monotonic(), 0.0, 70.0)
    reference.note = lambda captured, value, levels=(): noted.setdefault("pc", (value, [round(level, 9) for _, level in levels]))
    reference.offer(image, "front", clock.monotonic(), 0.0, 70.0)
    assert eyes.hazards_seen(hazard_rows(eyes, clock.monotonic(), *[("fire", box, 0.6) for box in fires]))
    eyes.hazards.note = lambda captured, value, levels=(): noted.setdefault("phone", (value, [round(level, 9) for _, level in levels]))
    assert eyes.feed(frame(t=clock.monotonic(), warm=warm, glow=glow))
    assert noted["phone"][0] == pytest.approx(noted["pc"][0], abs=1e-9) and noted["pc"][0] > 0.01
    assert noted["phone"][1] == noted["pc"][1] and len(noted["pc"][1]) == 3


def test_android_eyes_hand_over_one_snapshot_and_keep_nothing(phone):
    async def scenario():
        eyes = make_eyes(phone)
        assert await eyes.snapshot() is None
        eyes.feed(frame())
        assert await eyes.snapshot(max_side=200) == phone.jpeg
        assert phone.eyes_calls[-1] == ("snapshot", "", 200, 1.0)
        task = asyncio.create_task(eyes.snapshot(camera="rear"))
        await asyncio.sleep(0.01)
        assert ("use", "rear") in phone.eyes_calls
        threading.Thread(target=eyes.feed, args=(frame(camera="rear"),)).start()
        assert await task == phone.jpeg
        assert phone.eyes_calls[-1] == ("snapshot", "rear", 768, 1.0) and eyes.camera() == "rear"
        assert not [k for k, v in vars(eyes).items() if isinstance(v, (bytes, bytearray))]
        phone.jpeg = b""
        assert await eyes.snapshot() is None
        eyes.set_enabled(False)
        calls = len(phone.eyes_calls)
        assert await eyes.snapshot() is None and len(phone.eyes_calls) == calls

    run(scenario())


def test_android_eyes_without_the_hazard_model(phone):
    eyes = hazard_eyes(phone, hazards={"hazards": False})
    assert phone.eyes_calls[0][1]["hazards"]["on"] is False and eyes.hazards is None
    assert not eyes.hazards_seen(json.dumps({"camera": "front", "t": 0.0, "w": 640, "h": 480, "found": []}))
    assert eyes.feed(frame(warm=0.5, glow="not a picture"))
    assert "hazards" not in eyes.status()
    assert AndroidEyes(Clock(), hazard_words={}).hazards is None


def test_android_eyes_tell_who_is_speaking_only_while_a_voice_is_heard(phone):
    clock = FakeClock()
    eyes = AndroidEyes(clock, words=load_words(MODELS / "objects_vocab.json"))
    eyes.start()
    assert phone.eyes_calls[0][1]["speaking"] == {"on": True, "faces": 2, "min_face_px": 32.0}
    face = [0.4, 0.2, 0.2, 0.25, 0.9]

    def show(n, mouth=None):
        clock.advance(0.1)
        assert eyes.feed(frame(t=clock.monotonic(), faces=[[0.1, 0.1, 0.05, 0.06, 0.8], face], mouths=[mouth or [1, 0.1 if n % 2 else 0.01, 0.45]]))
        return eyes.latest(1.0)

    for n in range(8):
        sight = show(n)
    assert all(p.speaking is None for p in sight.people) and not [c for c in phone.eyes_calls if c[0] == "mouths"]
    eyes.hear_voice(True)
    assert phone.eyes_calls[-1] == ("mouths", True, 2.0)
    for n in range(8, 16):
        sight = show(n)
    person = max(sight.people, key=lambda p: p.height_frac)
    assert person.face and person.speaking >= 0.9
    assert [p.speaking for p in sight.people if p is not person] == [None]
    assert eyes.spoke(clock.now() - 1.0, clock.now())[person.track] >= 0.9
    assert eyes.status()["speaking"]["listening"]
    assert show(16, [1]).people and max(eyes.latest(1.0).people, key=lambda p: p.height_frac).speaking is None
    eyes.hear_voice(False)
    assert phone.eyes_calls[-1] == ("mouths", False, 2.0)
    eyes.set_enabled(False)
    assert eyes.spoke(0, 1e12) == {}
    always = AndroidEyes(FakeClock(), words={}, speaking={"speaking_gate": "always"})
    always.start()
    assert phone.eyes_calls[-1] == ("mouths", True, 2.0)
    deaf = AndroidEyes(FakeClock(), words={}, speaking={"speaking": False})
    deaf.start()
    calls = len(phone.eyes_calls)
    deaf.hear_voice(True)
    assert phone.eyes_calls[-1][1]["speaking"]["on"] is False and len(phone.eyes_calls) == calls and deaf.spoke(0, 1e12) == {}


@pytest.mark.setup_mode
def test_the_admin_screen_finishes_setup_and_only_then_seals(tmp_path, phone):
    root = tmp_path / "self"
    make_self(root)
    before = json.loads(android_seal.setup_status(str(root)))
    assert before["ok"]
    assert before["setup"]["on"]
    refused = json.loads(android_seal.seal(str(root), PASSWORD))
    assert not refused["ok"] and "Setup finished" in refused["message"]
    done = json.loads(android_seal.finish_setup(str(root)))
    assert done["ok"], done
    after = json.loads(android_seal.setup_status(str(root)))
    assert after["ok"] and not after["setup"].get("on")
    again = json.loads(android_seal.finish_setup(str(root)))
    assert again["ok"] and again["setup"]["already"]
    assert json.loads(android_seal.seal(str(root), PASSWORD))["ok"]


def test_android_eyes_put_the_phone_s_floor_scan_in_the_sight(phone):
    pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    from floor_render import Scene

    from pebble.eyes.floor import rays

    clock = FakeClock()
    eyes = AndroidEyes(clock, words=load_words(MODELS / "objects_vocab.json"))
    eyes.start()
    config = phone.eyes_calls[0][1]
    assert config["floor"] == {"on": True, "every_s": 0.2, "gate": "moving", "threads": 2, "bins": 32, "reach_m": 2.0}
    assert config["head"] == {"front": [0.14, 8.0, 0.0], "rear": [0.14, -8.0, 0.0]}
    assert not eyes.status()["floor"]["moving"]
    eyes.set_moving(True)
    assert phone.eyes_calls[-1] == ("moving", True) and eyes.status()["floor"]["moving"]
    scene = Scene(wall_x=0.9)
    scene.render(pitch_deg=8.0, width=238, rows=182)
    found, quality = rays((3.0 / scene.depth + 0.2).astype(np.float32), 70.0, 0.14, 8.0)
    t0 = clock.monotonic()
    assert eyes.feed(frame(t=t0))
    assert eyes.latest(1.0).floor == () and eyes.latest(1.0).floor_at is None
    seen = {"camera": "front", "t": t0, "rays": [[r.bearing_deg, r.distance_m, r.score] for r in found], "quality": quality, "ms": 180.0, "depth_ms": 170.0, "rays_ms": 10.0, "head": [0.14, 8.0, 0.0]}
    assert eyes.floor_seen(json.dumps(seen))
    clock.advance(0.1)
    assert eyes.feed(frame(t=clock.monotonic()))
    sight = eyes.latest(1.0)
    assert sight.floor == found and sight.floor_at is not None and sight.floor_at <= sight.at
    assert min(r.distance_m for r in sight.floor) == pytest.approx(0.91, abs=0.03)
    clock.advance(0.1)
    assert eyes.feed(frame(t=clock.monotonic(), objects=[[0.45, 0.8, 0.1, 0.1, 0.8, 32]]))
    sight = eyes.latest(1.0)
    ball = next(t for t in sight.things if t.label == "ball")
    near = [r for r in sight.floor if abs(r.bearing_deg - ball.floor_bearing_deg) <= 2.0]
    assert ball.floor_m < 0.85 and near and all(r.distance_m == ball.floor_m for r in near)
    assert eyes.process(json.loads(frame(camera="rear", t=clock.monotonic()))).floor == ()
    clock.advance(1.0)
    assert eyes.feed(frame(t=clock.monotonic()))
    assert eyes.latest(1.0).floor == () and eyes.latest(1.0).floor_at is None
    status = eyes.status()["floor"]
    assert status == {"gate": "moving", "moving": True, "passes": 1, "ms": 180.0, "quality": round(quality, 2), "problem": "", "reach_m": 2.0}
    eyes.set_moving(False)
    assert phone.eyes_calls[-1] == ("moving", False) and eyes.status()["floor"]["moving"]
    clock.advance(1.5)
    assert not eyes.status()["floor"]["moving"]
    eyes.scan_floor()
    assert phone.eyes_calls[-1] == ("scan_floor",)
    eyes.set_head(tilt_deg=20.0, roll_deg=3.0)
    assert phone.eyes_calls[-1] == ("head", {"front": [0.14, 20.0, 3.0], "rear": [0.14, -20.0, -3.0]})
    calls = len(phone.eyes_calls)
    eyes.set_head(tilt_deg=20.0)
    assert len(phone.eyes_calls) == calls
    assert not eyes.floor_seen(json.dumps({"failed": True, "problem": "no floor scan: the depth model is missing"}))
    assert eyes.status()["floor"]["problem"] == "no floor scan: the depth model is missing"
    assert not eyes.floor_seen("not json") and not eyes.floor_seen(json.dumps({"camera": "side", "t": t0, "rays": []}))
    assert not eyes.floor_seen(json.dumps({"camera": "front", "t": t0, "rays": [[1.0, "far", 0.5]]}))
    assert eyes.floor_seen(json.dumps({**seen, "t": clock.monotonic(), "rays": []}))
    assert eyes.status()["floor"]["problem"] == "" and eyes.status()["floor"]["passes"] == 2
    assert eyes.floor_seen(json.dumps({**seen, "t": clock.monotonic()}))
    eyes.set_enabled(False)
    assert eyes.floor.current("front", clock.monotonic()) == ((), None)
    assert not eyes.floor_seen(json.dumps({**seen, "t": clock.monotonic()}))


def test_android_eyes_tell_the_phone_how_to_scan_the_floor(phone):
    eyes = AndroidEyes(Clock(), words={}, floor={"floor_gate": "always", "floor_every_s": 0.5, "floor_threads": 3, "floor_reach_m": 1.5})
    eyes.start()
    assert phone.eyes_calls[-1][1]["floor"] == {"on": True, "every_s": 0.5, "gate": "always", "threads": 3, "bins": 32, "reach_m": 1.5}
    assert AndroidEyes(Clock(), words={}, floor={"floor_gate": "sometimes"}).config()["floor"]["gate"] == "moving"
    blind = AndroidEyes(Clock(), words={}, floor={"floor": False})
    blind.start()
    calls = len(phone.eyes_calls)
    blind.set_moving(True)
    blind.scan_floor()
    assert phone.eyes_calls[-1][1]["floor"]["on"] is False and len(phone.eyes_calls) == calls
    assert "floor" not in blind.status() and not blind.floor_seen(json.dumps({"camera": "front", "t": 0.0, "rays": []}))
    profile = BodyProfile.load(resolve_profile("android", "body"))
    eyes_from_config(profile.eyes, Clock())
    assert phone.eyes_calls[-1][1]["floor"] == {"on": True, "every_s": 0.2, "gate": "moving", "threads": 2, "bins": 32, "reach_m": 2.0}


def test_android_eyes_report_camera_motion_like_the_pc_eyes(phone):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    from pebble.eyes.service import CameraEyes
    from pebble.eyes.sources import Frame

    rng = np.random.default_rng(0)
    texture = cv2.GaussianBlur((rng.random((480, 720, 3)) * 255).astype(np.uint8), (0, 0), 3)
    clock = FakeClock()
    reference = CameraEyes(lambda camera: None, None, clock)
    eyes = AndroidEyes(clock, words={})
    eyes.start()
    window = cv2.createHanningWindow((80, 60), cv2.CV_32F)
    previous = None
    for n, left in enumerate((0, 40, 40, 30)):
        picture = texture[:, left:left + 640].copy()
        reference.process(Frame(picture, "front", clock.monotonic(), n))
        small = cv2.cvtColor(cv2.resize(picture, (80, 60), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
        parts = {}
        if previous is not None:
            change = float(np.abs(small - previous).mean() / 255.0)
            (dx, dy), sure = cv2.phaseCorrelate(previous.copy(), small.copy(), window)
            parts["motion"] = {"dt": 0.1, "shift": [dx, dy], "sure": sure, "change": change}
        previous = small
        assert eyes.feed(frame(t=clock.monotonic(), **parts))
        want, got = reference.motion(), eyes.motion()
        if want is None:
            assert got is None
        else:
            assert {k: v for k, v in got.items() if k != "at"} == {k: v for k, v in want.items() if k != "at"}
            assert got["at"] == pytest.approx(eyes.latest(1.0).at)
        clock.advance(0.1)
    assert eyes.motion()["shift_deg"][0] == pytest.approx(10 * 70.0 / 640, abs=0.6)
    assert eyes.status()["motion"] == eyes.motion()
    kept = eyes.motion()
    assert eyes.feed(frame(t=clock.monotonic(), motion={"dt": 0.1, "shift": [1.0], "sure": 0.5, "change": 0.1}))
    assert eyes.feed(frame(t=clock.monotonic(), motion={"dt": 0.1, "shift": [1.0, "x"], "sure": 0.5, "change": 0.1}))
    assert eyes.motion() == kept
    eyes.set_enabled(False)
    assert eyes.motion() is None and eyes.status()["motion"] is None


def test_android_eyes_take_a_print_of_the_place(phone):
    np = pytest.importorskip("numpy")

    async def scenario():
        eyes = make_eyes(phone)
        assert await eyes.place_print() is None
        eyes.feed(frame())
        vec = await eyes.place_print()
        boxes = [[0.0, 0.0, 1.0, 1.0], [0.0, 0.0, 0.5, 0.5], [0.5, 0.0, 0.5, 0.5], [0.0, 0.5, 0.5, 0.5], [0.5, 0.5, 0.5, 0.5]]
        mean = np.mean([print_of(b) for b in boxes], axis=0)
        assert vec is not None and len(vec) == 384 and np.allclose(vec, mean / np.linalg.norm(mean), atol=1e-6)
        assert abs(sum(x * x for x in vec) - 1) < 1e-4
        assert ("embed", 7, 140) in phone.eyes_calls and phone.eyes_calls[-1] == ("release", 7)
        calls = len(phone.eyes_calls)
        assert await eyes.place_print(camera="rear") is None and len(phone.eyes_calls) == calls
        assert await eyes.place_print(camera="front") == vec
        phone.held = {**phone.held, "id": 8, "camera": "rear"}
        assert await eyes.place_print(camera="front") is None and phone.eyes_calls[-1] == ("release", 8)
        eyes.set_enabled(False)
        assert await eyes.place_print() is None

    run(scenario())


class SentencePhone(FakePhone):
    def __init__(self, folder: Path, choice: dict | None = None):
        super().__init__(folder)
        self.choice = dict(choice or {"rung": "onnx", "standin_now": False, "why": "measured"})
        self.asked: list[tuple[list, bool]] = []
        self.give_up = False
        self.short = False
        self.closed = 0

    def recallChoice(self) -> str:
        return json.dumps(self.choice)

    def recallEmbed(self, texts: str, query: bool) -> bytes:
        lines = json.loads(texts)
        self.asked.append((lines, query))
        if self.give_up:
            return b""
        values = []
        for n in range(len(lines)):
            row = [0.0] * DIM
            row[n % DIM] = 1.0
            values.extend(row)
        blob = struct.pack(f"<{len(values)}f", *values)
        return blob[:-4] if self.short else blob

    def recallClose(self) -> None:
        self.closed += 1


def test_the_phones_sentence_model_speaks_the_brains_embedder_seam(tmp_path):
    phone = SentencePhone(tmp_path)
    seam = bridges.sentences(phone)
    assert isinstance(seam, bridges.PhoneSentences)
    assert seam.name == ONNX_NAME == "snowflake-arctic-embed-xs-int8" and seam.dim == DIM == 384 and seam.related == OnnxEmbedder.related == 0.55
    lines = [f"note {n}" for n in range(70)]
    rows = seam.embed(lines)
    assert len(rows) == 70 and all(len(row) == DIM and isinstance(row[0], float) for row in rows)
    assert [row.index(1.0) for row in rows] == list(range(70))
    assert phone.asked == [(lines, False)]
    seam.embed(["When is Sam's game?"], True)
    assert phone.asked[-1] == (["When is Sam's game?"], True)
    seam.embed([None, 3])
    assert phone.asked[-1] == (["", "3"], False)
    assert seam.embed([]) == [] and len(phone.asked) == 3
    seam.close()
    assert phone.closed == 1


def test_when_the_phones_model_gives_up_the_brain_gets_no_numbers_or_the_stand_in(tmp_path):
    phone = SentencePhone(tmp_path)
    seam = bridges.sentences(phone)
    phone.give_up = True
    assert seam.embed(["the plant by the window"]) == [] and seam.name == ONNX_NAME
    phone.give_up = False
    phone.short = True
    assert seam.embed(["the plant by the window"]) == [] and seam.name == ONNX_NAME
    phone.short = False
    phone.give_up = True
    phone.choice = {"rung": "stand-in", "standin_now": True, "why": "a question took 620 ms (more than 500)"}
    assert seam.embed(["the plant by the window"], True) == StandIn().embed(["the plant by the window"], True)
    assert seam.name == StandIn.name and seam.related == StandIn.related and seam.dim == DIM
    asked = len(phone.asked)
    assert seam.embed(["a loud football match"]) == StandIn().embed(["a loud football match"])
    assert len(phone.asked) == asked
    missing = SentencePhone(tmp_path / "other", {"rung": "missing", "standin_now": True, "why": "the sentence model is not in this app"})
    assert bridges.sentences(missing).name == StandIn.name and not missing.asked


def test_without_the_phones_sentence_model_the_brain_keeps_its_own(tmp_path):
    assert bridges.sentences(FakePhone(tmp_path)) is None
    bridges.install(None)
    assert bridges.sentences() is None
    seam = bridges.sentences(SentencePhone(tmp_path))
    pick = android_main._phone_first(seam, embedder_from)
    assert pick("auto") is seam and isinstance(pick("standin"), StandIn)


def test_the_android_entry_gives_the_brain_the_phones_sentence_model_and_closes_it(tmp_path, monkeypatch):
    from pebble import app as brain

    phone = SentencePhone(tmp_path / "phone")
    seen = {}
    made = brain.LifeParts

    def parts(**kwargs):
        seen["embedder"] = kwargs.get("embedder")
        return made(**kwargs)

    monkeypatch.setattr(brain, "LifeParts", parts)
    chosen = brain.embedder_from
    beat = tmp_path / "files" / "brain.alive"
    argv = ["--self", str(tmp_path / "self"), "--sim", "--body", "android", "--mind", "scripted", "--dry-run", "--heartbeat", "0.3", "--screen", "--screen-port", "0", "--presence", "none", "--seconds", "20"]
    result = {}
    worker = threading.Thread(target=lambda: result.setdefault("code", android_main.run(argv, phone, str(beat), str(tmp_path / "files" / "logs" / "brain.log"))))
    try:
        worker.start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not beat.exists():
            time.sleep(0.05)
        assert beat.exists()
        assert android_main.stop()
        worker.join(20)
        assert not worker.is_alive() and result["code"] == 0
    finally:
        bridges.install(None)
    assert isinstance(seen["embedder"], bridges.PhoneSentences) and seen["embedder"].name == ONNX_NAME
    assert phone.closed == 1 and brain.embedder_from is chosen
