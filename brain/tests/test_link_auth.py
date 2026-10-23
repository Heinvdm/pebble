import asyncio
import hashlib
import hmac
import re

import pytest

from conftest import make_profile, run

from pebble.body.api import Body
from pebble.body.checks import safe_setting, unsafe_settings
from pebble.body.profile import BodyProfile
from pebble.clock import FakeClock
from pebble.link import auth, pair
from pebble.link.auth import RawKey, Session, find_key, session_message
from pebble.link.client import LinkClient, LinkDown, LinkUp
from pebble.link.protocol import Drive, Err, Event, Flags, parse_message
from pebble.link.transport import LinkClosed, Transport

KEY = RawKey(bytes(range(32)))
OTHER = RawKey(bytes(range(1, 33)))
PHONE_NONCE = "00112233445566778899aabbccddeeff"
BODY_NONCE = "101112131415161718191a1b1c1d1e1f"
SAFE = {"ssid": "-", "pass": "-", "cpm": "20.700", "edge": "75", "stop": "60", "tmin": "-35", "tmax": "90", "trim": "0", "rest": "8"}
_TAGGED = re.compile(r"^(.*) #([0-9]+) ([0-9a-f]{12})$")


def proof(session_key: bytes, who: str) -> str:
    return hmac.new(session_key, who.encode(), hashlib.sha256).digest()[:16].hex()


class FakeBody(Transport):
    needs_key = True
    label = "fake:body"

    def __init__(self, key: RawKey | None, settings: dict | None = None, answers_handshake: bool = True):
        self.key = key
        self.settings = dict(settings or SAFE)
        self.answers_handshake = answers_handshake
        self.queue: asyncio.Queue = asyncio.Queue()
        self.received: list[str] = []
        self.commands: list[str] = []
        self.refused: list[str] = []
        self.session_key: bytes | None = None
        self.proven = False
        self.sent = 0
        self.last = 0

    async def open(self) -> None:
        return None

    def say(self, text: str) -> None:
        if self.proven:
            self.sent += 1
            tag = hmac.new(self.session_key, f"b{self.sent} {text}".encode(), hashlib.sha256).digest()[:6].hex()
            text = f"{text} #{self.sent} {tag}"
        self.queue.put_nowait(text)

    async def read_line(self) -> str:
        line = await self.queue.get()
        if line is None:
            raise LinkClosed("closed")
        return line

    def _unwrap(self, line: str) -> str | None:
        found = _TAGGED.match(line)
        if found is None:
            return line if not self.proven or line == "X" else None
        text, counter, given = found.group(1), int(found.group(2)), found.group(3)
        if not self.proven or counter <= self.last:
            return None
        if hmac.new(self.session_key, f"p{counter} {text}".encode(), hashlib.sha256).digest()[:6].hex() != given:
            return None
        self.last = counter
        return text

    async def write_line(self, line: str) -> None:
        self.received.append(line)
        if line.startswith("H "):
            if not self.answers_handshake:
                self.queue.put_nowait("err H unknown")
                return
            if self.key is None:
                self.queue.put_nowait("err H key")
                return
            self.session_key = self.key.mac(session_message(line.split()[1], BODY_NONCE))
            self.queue.put_nowait(f"h {BODY_NONCE} {proof(self.session_key, 'body')}")
            return
        if line.startswith("V "):
            if line.split()[1] == proof(self.session_key, "phone"):
                self.queue.put_nowait("ok")
                self.proven = True
                self.say("E boot 0.2.0")
            else:
                self.queue.put_nowait("err V auth")
            return
        text = self._unwrap(line)
        if text is None:
            self.refused.append(line)
            self.say(f"err {line[:1]} auth")
            return
        self.commands.append(text)
        if text.startswith("P "):
            self.say(f"p {text.split()[1]}")
        elif text == "C ?":
            for key, value in self.settings.items():
                self.say(f"c {key} {value}")
            self.say("ok")
        elif text == "X":
            self.say("ok")

    async def close(self) -> None:
        self.queue.put_nowait(None)


class Loopback(FakeBody):
    needs_key = False


async def until(check, timeout: float = 3.0) -> bool:
    for _ in range(int(timeout / 0.02)):
        if check():
            return True
        await asyncio.sleep(0.02)
    return check()


def test_the_handshake_matches_the_firmware():
    session_key = KEY.mac(session_message(PHONE_NONCE, BODY_NONCE))
    assert session_key.hex() == "c82d126ebaee9f5d482d4a5dcde628f8d8cc33521014ec866e80af85a0f61cf1"
    session = Session(session_key)
    assert session.proof("body") == "56ca065c618e088268640dc2628ad4c3"
    assert session.proof("phone") == "5c97f3affe363f31e642b9d4d9dd7568"
    assert session.seal("D 300 300") == "D 300 300 #1 92edd70232c8"
    assert session.seal("X") == "X #2 6bf0f2c15a3b"
    assert session.open("ok #1 2f9524c7b9ae") == "ok"


def test_tags_refuse_replays_forgeries_and_plain_lines():
    session = Session(KEY.mac(session_message(PHONE_NONCE, BODY_NONCE)))
    assert session.open("ok #1 2f9524c7b9ae") == "ok"
    assert session.open("ok #1 2f9524c7b9ae") is None
    assert session.open("S 1 0 0 100 45 0 0 3900 8 0") is None
    assert session.open("ok #2 2f9524c7b9ae") is None
    assert session.rejected == 3


def test_the_longest_command_still_fits_a_line_once_tagged():
    session = Session(bytes(32))
    session.sent = 4294967294
    line = session.seal("C pass " + "x" * 64)
    assert len(line) <= 96


def test_a_proven_link_tags_both_ways():
    async def scenario():
        body = FakeBody(KEY)
        link = LinkClient(lambda: body, key=KEY)
        events = link.subscribe((Event, LinkUp))
        link.start()
        try:
            assert await link.wait_connected(3.0)
            assert link.proven
            seen = [await asyncio.wait_for(events.get(), 2.0) for _ in range(2)]
            assert isinstance(seen[0], LinkUp)
            assert seen[1] == Event("boot", ("0.2.0",))
            status = link.subscribe((Event,))
            body.say("S 1 0 0 100 45 0 0 3900 8 0")
            body.say("E bump L")
            assert (await asyncio.wait_for(status.get(), 2.0)) == Event("bump", ("L",))
            body.queue.put_nowait("E edge")
            body.say("E bump R")
            assert (await asyncio.wait_for(status.get(), 2.0)) == Event("bump", ("R",))
            assert link.malformed == 1
            assert await link.ping(2.0) is not None
            assert body.commands[-1].startswith("P ")
            assert body.refused == []
            assert all(re.search(r" #\d+ [0-9a-f]{12}$", line) for line in body.received[2:])
        finally:
            await link.stop()

    run(scenario())


def test_a_body_without_the_key_is_never_driven():
    async def scenario():
        body = FakeBody(OTHER)
        link = LinkClient(lambda: body, key=KEY, backoff=(0.05, 0.1))
        downs = link.subscribe((LinkDown,))
        link.start()
        try:
            down = await asyncio.wait_for(downs.get(), 2.0)
            assert "handshake failed" in down.reason and "did not prove" in down.reason
            assert not link.connected
            assert not await link.send(Drive(300, 300))
            assert body.commands == []
            assert not any(line.startswith("V ") for line in body.received)
        finally:
            await link.stop()

    run(scenario())


def test_a_body_with_no_key_or_old_firmware_says_why():
    async def scenario():
        for body, words in ((FakeBody(None), "pair it over USB"), (FakeBody(KEY, answers_handshake=False), "too old")):
            link = LinkClient(lambda body=body: body, key=KEY)
            downs = link.subscribe((LinkDown,))
            link.start()
            try:
                down = await asyncio.wait_for(downs.get(), 2.0)
                assert words in down.reason
                assert not link.connected and words in link.auth_problem
            finally:
                await link.stop()

    run(scenario())


def test_a_phone_that_refuses_its_proof_is_refused():
    async def scenario():
        body = FakeBody(KEY)
        original = Session.proof

        def wrong(self, who):
            return "0" * 32 if who == "phone" else original(self, who)

        Session.proof = wrong
        try:
            link = LinkClient(lambda: body, key=KEY)
            downs = link.subscribe((LinkDown,))
            link.start()
            down = await asyncio.wait_for(downs.get(), 2.0)
            assert "did not accept" in down.reason
            await link.stop()
        finally:
            Session.proof = original

    run(scenario())


def test_no_key_means_no_handshake_and_the_sim_never_needs_one():
    async def scenario():
        for body, key in ((FakeBody(KEY), None), (Loopback(KEY), KEY)):
            link = LinkClient(lambda body=body: body, key=key)
            link.start()
            try:
                assert await link.wait_connected(2.0)
                assert not link.proven
                assert not any(line.startswith("H ") for line in body.received)
            finally:
                await link.stop()

    run(scenario())


def test_the_phone_finds_its_key_only_where_it_should(tmp_path, monkeypatch):
    monkeypatch.delenv(auth.KEY_FILE_ENV, raising=False)
    assert find_key() is None
    path = tmp_path / "link.key"
    auth.write_key_file(path, KEY)
    monkeypatch.setenv(auth.KEY_FILE_ENV, str(path))
    found = find_key()
    assert isinstance(found, RawKey) and found.hex() == KEY.hex()
    path.write_text("not a key")
    with pytest.raises(ValueError):
        find_key()


def test_unsafe_reflex_settings_are_named():
    assert unsafe_settings(SAFE) == []
    assert unsafe_settings(dict(SAFE, cpm="0")) == []
    problems = unsafe_settings(dict(SAFE, edge="2000", stop="0", cpm="10000", trim="45", tmin="-90", rest="95"))
    text = " ".join(problems)
    for word in ("edge 2000", "stop 0", "cpm 10000", "trim 45", "tmin -90", "rest 95"):
        assert word in text
    assert unsafe_settings({}) and "could not be read" in unsafe_settings({})[0]
    assert unsafe_settings(dict(SAFE, tmin="50", tmax="40"))
    assert safe_setting("edge", 90) and not safe_setting("edge", 2000) and not safe_setting("ssid", "x")


def test_the_brain_will_not_drive_a_body_with_unsafe_reflexes():
    async def scenario():
        body = FakeBody(KEY, dict(SAFE, edge="2000"))
        link = LinkClient(lambda: body, key=KEY)
        brain = Body(link, FakeClock(), make_profile())
        events = brain.subscribe_events()
        brain.start()
        try:
            assert await link.wait_connected(3.0)
            assert not await brain.drive(300, 300)
            assert brain.settings_state == "unsafe" and "edge 2000" in brain.settings_problem
            assert not any(line.startswith("D ") for line in body.commands if line != "D 0 0")
            report = await brain.move(300, 300, 0.5)
            assert not report.ok and "edge 2000" in report.note
            seen = []
            while not events.empty():
                seen.append(events.get_nowait())
            assert Event("fault", ("settings",)) in seen
            assert await brain.stop()
        finally:
            await brain.close()

    run(scenario())


def test_the_brain_drives_a_body_with_safe_reflexes():
    async def scenario():
        body = FakeBody(KEY)
        link = LinkClient(lambda: body, key=KEY)
        brain = Body(link, FakeClock(), make_profile())
        brain.start()
        try:
            assert await link.wait_connected(3.0)
            assert await brain.drive(300, 300)
            assert brain.settings_state == "ok"
            assert await until(lambda: "D 300 300" in body.commands)
        finally:
            await brain.close()

    run(scenario())


def test_a_profile_cannot_loosen_the_body():
    profile = BodyProfile.from_dict({
        "drive": {"max_speed_mm_s": 5000, "cpm": 1000, "wheel_track_mm": 9},
        "tilt": {"min": -90, "max": 120, "rest": 200},
        "firmware_settings": {"edge": "2000", "stop": "0", "ssid": "theirs", "pass": "x", "cpm": "20.7"},
    })
    assert profile.max_speed_mm_s == 400
    assert profile.cpm == 0.0
    assert profile.wheel_track_mm == 100.0
    assert (profile.tilt_min, profile.tilt_max, profile.tilt_rest) == (-35.0, 90.0, 90.0)
    assert profile.firmware_settings == {"cpm": "20.7"}
    plain = make_profile()
    assert plain.cpm == 20.7 and plain.max_speed_mm_s == 250


def test_the_reverse_limit_flag_parses():
    status = parse_message("S 1 0 0 100 45 0 0 3900 8 128")
    assert Flags.REVERSE_LIMIT in status.flags
    assert parse_message("err D auth") == Err("D", "auth")
    assert parse_message("err C usb") == Err("C", "usb")
    assert parse_message("err H key") == Err("H", "key")


def test_pairing_over_usb_writes_the_key_after_the_body_proves_it(tmp_path, monkeypatch):
    made = []
    stored = {}

    class UsbBody(FakeBody):
        def __init__(self, device, baud=115200):
            super().__init__(stored.get("key"))
            made.append(self)

        async def write_line(self, line):
            if line.startswith("K "):
                self.key = stored["key"] = RawKey.from_hex(line.split()[1])
                self.received.append("K <key>")
                self.queue.put_nowait("ok")
                return
            await super().write_line(line)

    monkeypatch.setattr(pair, "SerialTransport", UsbBody)
    path = tmp_path / "keys" / "link.key"
    said = asyncio.run(pair.pair("COM9", path, new=False))
    assert "Paired" in said
    assert made[0].key.hex() == auth.read_key_file(path).hex()
    assert made[0].proven
    assert asyncio.run(pair.check("COM9", path)) == "The body proved the key."
