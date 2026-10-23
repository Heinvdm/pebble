import asyncio
import json

import pytest
from conftest import run

from pebble.android import bridge as bridges
from pebble.android.closeup import PhoneCloseUp, SimCloseUp, closeup_for
from pebble.android.hearing import AndroidEars
from pebble.android.mic import TODAY_RATE, VERIFY_S, WIDE_RATE, MicLadder, PhoneMic, SimMic, probe_result, probe_words, wide_verdict
from pebble.android.torch import PhoneTorch, SimTorch, torch_for
from pebble.clock import FakeClock
from pebble.hearing.tvcheck import CHECKS, TvCheck, tv_passed
from pebble.house import settings as house_settings
from pebble.house.book import HOUSE
from pebble.house.settings import INBOX, Refused, change, owner_ok, post, send, waiting
from pebble.owner import hash_passphrase
from pebble.seal import FileKeyHolder, open_self, seal_self, throw_away
from pebble.seal.sealing import PHRASE
from pebble.selfstore import SelfStore

FAST = {"n": 2**10, "r": 8, "p": 1}
PASSWORD = "correct horse battery"
JPEG = b"\xff\xd8close\xff\xd9"


def test_the_torch_switches_on_ends_by_itself_and_says_when_there_is_none():
    clock = FakeClock()
    lamp = SimTorch(clock.monotonic)
    torch = PhoneTorch(lamp)
    assert torch.has()
    lit = torch.set(True, 0.4, 600.0)
    assert lit["on"] and lit["level"] == 0.4 and lamp.calls == [(True, 0.4, 600.0)]
    clock.advance(601.0)
    info = torch.info()
    assert not info["on"] and info["ended"] == "its time ran out"
    torch.set(True, 1.0, 0.0)
    assert torch.info()["left_s"] == 600.0
    torch.set(True, 1.0, 99_999.0)
    assert torch.info()["left_s"] == 3600.0
    hot = [False]
    warm = SimTorch(clock.monotonic, hot=lambda: hot[0])
    PhoneTorch(warm).set(True, 1.0, 600.0)
    hot[0] = True
    assert json.loads(warm.torchInfo())["ended"] == "the phone got hot"
    none = PhoneTorch(SimTorch(clock.monotonic, has=False))
    assert not none.has() and none.set(True)["problem"] == "this phone has no light on its back"
    assert torch_for(None) is None and isinstance(torch_for(lamp), PhoneTorch)


class CloseBridge:
    def __init__(self, picture=JPEG, problem=""):
        self.picture = picture
        self.problem = problem
        self.asked = []

    def eyesCloseUp(self, max_side, zoom):
        self.asked.append((max_side, zoom))
        return self.picture

    def eyesCloseUpInfo(self):
        if self.problem:
            return json.dumps({"problem": self.problem})
        return json.dumps({"lenses": [{"id": "2", "fov_deg": 23.5}], "last": {"asked": 4.0, "lens_zoom": 4.0, "digital": 1.0, "lens": "2", "problem": "" if self.picture else "the camera would not focus"}})


class AndroidEyes:
    available = True


def test_the_close_look_comes_from_the_phone_or_the_sims_back_camera():
    phone = CloseBridge()
    closer = PhoneCloseUp(phone)
    assert closer.available()
    assert run(closer.take(1024, 4.0)) == JPEG and phone.asked == [(1024, 4.0)]
    assert closer.how()["lens"] == "2"
    blank = PhoneCloseUp(CloseBridge(b""))
    assert run(blank.take(1024, 4.0)) is None and blank.problem == "the camera would not focus"
    assert not PhoneCloseUp(CloseBridge(problem="the cameras are not available in this process")).available()
    assert isinstance(closeup_for(AndroidEyes(), phone), PhoneCloseUp)
    assert closeup_for(object(), phone) is None and closeup_for(AndroidEyes(), None) is None


def test_the_sims_close_look_uses_the_back_camera_and_gives_the_front_back():
    from pebble.sim.eyes import SimEyes
    from pebble.sim.world import World

    clock = FakeClock()
    eyes = SimEyes(World(), clock.monotonic, lambda: 0.0)
    closer = closeup_for(eyes)
    assert isinstance(closer, SimCloseUp) and closer.available()
    picture = run(closer.take(1024, 4.0))
    assert picture[:2] == b"\xff\xd8" and eyes.camera() == "front" and closer.asked == [(1024, 4.0)]


def ladder_for(sim, clock, checked=False):
    return MicLadder(PhoneMic(sim), clock.monotonic, checked)


def rates(sim):
    return [c["mic_rate"] for c in sim.configs if "mic_rate" in c]


def test_the_feed_stays_at_sixteen_kilohertz_until_the_probe_says_wider_loses_nothing():
    clock = FakeClock()
    sim = SimMic()
    ladder = ladder_for(sim, clock)
    ladder.tick()
    assert sim.configs == [] and not ladder.wide()
    assert wide_verdict(json.loads(sim.micPlan()))[1] == "my microphones haven't been measured yet"
    sim.result = probe_result(14_000.0)
    sim.probe_at = 1
    clock.advance(61.0)
    ladder.tick()
    assert sim.configs == []
    assert "the sweep did not show the path carrying sound above 15 kHz" in ladder.status()["why_not"]
    assert ladder.listen_wide(120.0) == (False, "this phone's microphone stops at about 14 kHz")


def test_a_good_probe_brings_the_wide_feed_and_a_lost_echo_canceller_takes_it_back():
    clock = FakeClock()
    sim = SimMic(probe_result(21_000.0), echo_at_wide=False)
    ladder = ladder_for(sim, clock)
    ladder.tick()
    assert rates(sim) == [WIDE_RATE] and ladder.wide()
    clock.advance(VERIFY_S + 1.0)
    ladder.tick()
    assert rates(sim) == [WIDE_RATE, TODAY_RATE] and not ladder.wide()
    assert ladder.status()["failed"]["why"] == "the echo canceller would not work on the 48 kHz feed"
    clock.advance(600.0)
    ladder.tick()
    assert rates(sim) == [WIDE_RATE, TODAY_RATE]
    assert ladder.listen_wide(120.0) == (False, "the echo canceller would not work on the 48 kHz feed")
    sim.echo_at_wide = True
    result = run(ladder.probe())
    assert sim.probes == 1 and probe_words(result).startswith("Done. My microphones hear up to about 21 kHz")
    ladder.tick()
    clock.advance(VERIFY_S + 1.0)
    ladder.tick()
    assert rates(sim)[-1] == WIDE_RATE and ladder.wide() and ladder.status()["failed"] is None


def test_the_microphone_is_never_switched_while_an_alarm_is_going():
    clock = FakeClock()
    sim = SimMic(probe_result(21_000.0))
    alarm = [True]
    ladder = MicLadder(PhoneMic(sim), clock.monotonic, hold=lambda: alarm[0])
    ladder.tick()
    clock.advance(20.0)
    ladder.tick()
    assert rates(sim) == []
    alarm[0] = False
    clock.advance(20.0)
    ladder.tick()
    assert rates(sim) == [WIDE_RATE]


def test_a_phone_that_refuses_the_wide_feed_stays_on_todays():
    clock = FakeClock()
    sim = SimMic(probe_result(21_000.0), refuse_wide="the phone would not open 48 kHz")
    ladder = ladder_for(sim, clock)
    ladder.tick()
    clock.advance(VERIFY_S + 1.0)
    ladder.tick()
    assert rates(sim) == [WIDE_RATE, TODAY_RATE]
    assert "would not give me a 48 kHz feed" in ladder.status()["failed"]["why"]


def test_listening_up_high_on_request_lasts_two_minutes_then_the_feed_goes_back():
    clock = FakeClock()
    sim = SimMic()
    ladder = ladder_for(sim, clock)
    ladder.tick()
    assert ladder.listen_wide(120.0) == (True, "")
    assert rates(sim) == [WIDE_RATE]
    clock.advance(60.0)
    ladder.tick()
    assert ladder.wide()
    clock.advance(61.0)
    ladder.tick()
    assert rates(sim) == [WIDE_RATE, TODAY_RATE] and ladder.status()["listening_wide_for_s"] == 0.0


def test_the_name_spotters_gain_stays_off_until_the_television_check_passed():
    clock = FakeClock()
    sim = SimMic()
    ladder = ladder_for(sim, clock)
    ladder.tick()
    assert not any("kws_gain" in c for c in sim.configs)
    passed = ladder_for(SimMic(), clock, checked=True)
    passed.tick()
    assert passed.mic.bridge().configs == [{"kws_gain": True}]
    clock.advance(61.0)
    passed.tick()
    assert passed.mic.bridge().configs == [{"kws_gain": True}]
    no_engine = ladder_for(SimMic(gain_engine=False), clock, checked=True)
    no_engine.tick()
    assert no_engine.mic.bridge().configs == []


def test_the_probe_is_put_into_plain_words():
    assert probe_words({"problem": "no microphone in this process"}) == "The microphone check didn't work: no microphone in this process."
    two = probe_words(probe_result(21_000.0, two=True))
    assert two == "Done. My microphones hear up to about 21 kHz on this phone. I'll try a wider sound feed, so I can listen for high tones all the time. I have two separate microphones, about 16 cm apart."
    copied = probe_words(probe_result(None))
    assert copied.startswith("Done. I couldn't hear my own whistle") and "only when someone asks" in copied and "really one microphone" in copied


def test_the_ears_keep_the_microphone_ladder_and_a_plain_phone_is_left_alone():
    clock = FakeClock()
    sim = SimMic(probe_result(21_000.0))
    sim.listening = []
    sim.earsSink = lambda sink: None
    sim.listen = lambda on: sim.listening.append(on)
    ears = AndroidEars(clock, bridge=sim, check_s=0.01)

    class Life:
        quiet_hours = type("Q", (), {"contains": lambda self, when: False})()

    async def scenario():
        task = asyncio.create_task(ears.run(Life()))
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    run(scenario())
    assert ears.mic is not None and rates(sim) == [WIDE_RATE] and ears.status()["mic"]["using_hz"] == WIDE_RATE


class Clockwork:
    def __init__(self):
        self.now = 0.0
        self.keyword = None
        self.hits: dict = {}

    def monotonic(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds
        if int(self.now) in self.hits:
            self.keyword = self.hits.pop(int(self.now))
        await asyncio.sleep(0)


def test_the_television_check_counts_names_with_and_without_the_gain():
    work = Clockwork()
    gains = []
    work.hits = {100: 1.0, 1000: 2.0}
    check = TvCheck(gains.append, lambda: work.keyword, work.monotonic, work.sleep)
    result = run(check.run())
    assert gains == [False, True, False, True, False, True, False]
    assert result == {"minutes_off": 15.0, "minutes_on": 15.0, "false_off": 1, "false_on": 1, "passed": True, "stopped": None}
    work = Clockwork()
    work.hits = {400: 1.0, 1000: 2.0}
    worse = run(TvCheck(lambda on: None, lambda: work.keyword, work.monotonic, work.sleep).run())
    assert (worse["false_off"], worse["false_on"], worse["passed"]) == (0, 2, False)
    work = Clockwork()
    stopper = TvCheck(gains.append, lambda: work.keyword, work.monotonic, work.sleep)

    async def stop_soon():
        task = asyncio.create_task(stopper.run())
        await asyncio.sleep(0)
        stopper.stop("someone asked me to stop")
        return await task

    stopped = run(stop_soon())
    assert stopped["passed"] is False and stopped["stopped"] == "someone asked me to stop" and gains[-1] is False
    assert tv_passed({"tv": result}) and not tv_passed({"tv": stopped}) and not tv_passed({})


def sealed_self(tmp_path, clock, passphrase="blue pebble"):
    root = tmp_path / "self"
    store = SelfStore.open(root, clock)
    if passphrase:
        core = json.loads((root / "core.json").read_text(encoding="utf-8"))
        core["passphrase"] = hash_passphrase(passphrase, iterations=1000)
        (root / "core.json").write_text(json.dumps(core), encoding="utf-8")
    store.write("people.json", {"people": [{"id": "p1", "names": ["Ina"]}]})
    holder = FileKeyHolder(tmp_path / "keys" / "self.key")
    seal_self(root, PASSWORD, holder, clock, kdf=FAST)
    return root, holder


def test_on_a_sealed_self_the_owners_password_changes_house_settings_and_the_spoken_passphrase_cannot(tmp_path, clock):
    root, holder = sealed_self(tmp_path, clock)
    store = open_self(root, clock, holder=holder)
    assert store.sealed and not owner_ok(store, "blue pebble")
    with pytest.raises(Refused, match="passphrase did not match"):
        change(store, "blue pebble", town="nelson")
    with pytest.raises(Refused, match="password did not open"):
        change(store, None, password="not the password", town="nelson")
    result = change(store, None, password=PASSWORD, town="nelson")
    assert result["place"]["name"] == "Nelson" and open_self(root, clock, holder=holder).read(HOUSE)["place"]["name"] == "Nelson"


def test_wrong_owners_passwords_lock_the_house_settings_for_a_while(tmp_path, clock, monkeypatch):
    from pebble.seal import tries

    root, holder = sealed_self(tmp_path, clock)
    store = open_self(root, clock, holder=holder)
    now = [1000.0]
    monkeypatch.setattr(tries.time, "time", lambda: now[0])
    for _ in range(5):
        assert not owner_ok(store, None, "wrong password")
    assert not owner_ok(store, None, PASSWORD)
    now[0] += 31.0
    assert owner_ok(store, None, PASSWORD)


def test_after_the_owners_lock_is_thrown_away_the_password_opens_nothing_here(tmp_path, clock):
    root, holder = sealed_self(tmp_path, clock)
    throw_away(root, PASSWORD, PHRASE, clock, holder)
    store = open_self(root, clock, holder=holder)
    assert not owner_ok(store, None, PASSWORD) and not owner_ok(store, "blue pebble")


def test_without_a_spoken_passphrase_the_admin_screen_needs_nothing_as_before(tmp_path, clock):
    root, holder = sealed_self(tmp_path, clock, passphrase="")
    store = open_self(root, clock, holder=holder)
    assert owner_ok(store) and change(store, None, cooking_watch=False)["cooking_watch"] is False


def test_settings_sent_to_a_running_pebble_wait_sealed_in_the_self_until_it_takes_them(tmp_path, clock):
    root, holder = sealed_self(tmp_path, clock)
    answer = json.loads(post(str(root), "", "wrong one", json.dumps({"town": "nelson"}), holder))
    assert not answer["ok"] and "password did not open" in answer["message"]
    answer = json.loads(post(str(root), "", PASSWORD, json.dumps({"town": "atlantis"}), holder))
    assert not answer["ok"] and "atlantis" in answer["message"]
    answer = json.loads(post(str(root), "", PASSWORD, json.dumps({"town": "nelson", "wifi": {"ssid": "guests", "password": "made-up"}, "tsunami": True}), holder))
    assert answer["ok"] and answer["house"]["place"]["name"] == "Nelson" and answer["house"]["tsunami_zone"] is True
    store = open_self(root, clock, holder=holder)
    names = waiting(store)
    assert len(names) == 1 and names[0].startswith(INBOX + "/")
    item = store.read(names[0])
    assert item["changes"]["town"] == "nelson" and item["tsunami"] is True
    assert b"made-up" not in (root / names[0]).read_bytes()
    assert house_settings.pending(str(root)) == 1
    assert json.loads(post(str(root), "", PASSWORD, "{}", holder))["message"] == "Nothing to change."


def test_a_plain_self_takes_sent_settings_too(tmp_path, clock):
    store = SelfStore.open(tmp_path / "self", clock)
    result = send(store, None, None, None, cooking_watch=False)
    assert result["cooking_watch"] is False and len(waiting(store)) == 1
    assert store.read(HOUSE, {}).get("settings", {}).get("cooking_watch", True) is True
    assert CHECKS == "hearing/checks.json"


def test_no_bridge_means_no_phone_parts():
    assert bridges.current() is None
    assert torch_for() is None and closeup_for(AndroidEyes()) is None
