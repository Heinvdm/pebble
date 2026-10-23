import asyncio
import math
import threading
import time

from conftest import make_profile, run

from pebble.body.api import Body
from pebble.clock import FakeClock
from pebble.link.client import LinkClient, LinkUp
from pebble.link.protocol import Event, Flags
from pebble.link.transport import transport_factory
from pebble.sim.firmware import SimFirmware
from pebble.sim.server import SimServer
from pebble.sim.world import CASTER_MM, Pose, World


async def start_rig(pose: Pose, dry_run: bool = False):
    firmware = SimFirmware(World(pose=pose))
    server = SimServer(firmware, "127.0.0.1", 0)
    port = await server.start()
    link = LinkClient(transport_factory(f"tcp:127.0.0.1:{port}"))
    body = Body(link, FakeClock(), make_profile(), dry_run=dry_run)
    body.start()
    assert await link.wait_connected(3.0)
    for _ in range(100):
        if body.telemetry.status is not None:
            break
        await asyncio.sleep(0.02)
    assert body.telemetry.status is not None
    return firmware, server, body


async def stop_rig(server: SimServer, body: Body) -> None:
    await body.close()
    await server.stop()


async def next_event(queue: asyncio.Queue, name: str, timeout: float):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    seen = []
    while loop.time() < deadline:
        try:
            message = await asyncio.wait_for(queue.get(), deadline - loop.time())
        except asyncio.TimeoutError:
            break
        if isinstance(message, Event):
            seen.append(message.text())
            if message.name == name:
                return message, seen
    return None, seen


def test_edge_reflex_stops_the_body_and_the_brain_sees_it():
    async def scenario():
        firmware, server, body = await start_rig(Pose(850.0, 0.0, 0.0))
        try:
            report = await body.move(500, 500, 3.0)
            assert report.ok and not report.dry_run
            assert report.stopped_early
            assert "edge" in report.events
            await asyncio.sleep(0.6)
            assert not firmware.world.fallen
            assert firmware.world.pose.x + CASTER_MM < firmware.world.table.x_max
            assert Flags.EDGE_HOLD in body.telemetry.flags
            held_at = firmware.world.pose.x
            await body.drive(500, 500)
            await asyncio.sleep(0.4)
            assert firmware.world.pose.x <= held_at + 0.5
            await body.stop()
            await asyncio.sleep(0.2)
            assert not firmware.edge_hold
            assert Flags.EDGE_HOLD not in body.telemetry.flags
        finally:
            await stop_rig(server, body)

    run(scenario())


def test_edge_event_reaches_event_subscribers():
    async def scenario():
        firmware, server, body = await start_rig(Pose(880.0, 0.0, 0.0))
        try:
            events = body.subscribe_events()
            mover = asyncio.create_task(body.move(400, 400, 3.0))
            edge, seen = await next_event(events, "edge", 5.0)
            assert edge is not None, seen
            report = await mover
            assert report.stopped_early and "edge" in report.events
        finally:
            await stop_rig(server, body)

    run(scenario())


def test_bump_reflex_reverses_off_the_wall():
    async def scenario():
        firmware, server, body = await start_rig(Pose(200.0, 0.0, math.pi))
        try:
            assert await body.set_setting("stop", 0) == "ok"
            report = await body.move(500, 500, 3.0)
            assert report.stopped_early
            assert "bump B" in report.events
            await asyncio.sleep(0.4)
            assert firmware.world.pose.x > 100.0 + 20.0
        finally:
            await stop_rig(server, body)

    run(scenario())


def test_settings_ping_and_query():
    async def scenario():
        firmware, server, body = await start_rig(Pose(500.0, 0.0, 0.0))
        try:
            settings = await body.settings()
            assert settings["edge"] == "75"
            assert settings["stop"] == "60"
            assert settings["ssid"] == ""
            assert await body.set_setting("ssid", "Home Net") == "ok"
            assert await body.set_setting("pass", "secret") == "ok"
            settings = await body.settings()
            assert settings["ssid"] == "Home Net"
            assert settings["pass"] == "*"
            assert await body.set_setting("ssid", "") == "ok"
            assert await body.get_setting("ssid") == ""
            assert await body.get_setting("edge") == "75"
            assert (await body.set_setting("edge", "far")).startswith("refused")
            assert await body.set_setting("edge", 99999) == "range"
            assert await body.ping() is not None
            status = await body.query()
            assert status is not None and status.dock == 0
            listing, edge, stop_set, stop_read, _, missing = await asyncio.gather(
                body.settings(),
                body.get_setting("edge"),
                body.set_setting("stop", 50),
                body.get_setting("stop"),
                body.stop(),
                body.get_setting("bogus"),
            )
            assert list(listing) == ["ssid", "pass", "cpm", "edge", "stop", "tmin", "tmax", "trim", "rest"]
            assert (edge, stop_set, stop_read, missing) == ("75", "ok", "50", None)
        finally:
            await stop_rig(server, body)

    run(scenario())


def test_dry_run_keeps_the_wheels_off():
    async def scenario():
        firmware, server, body = await start_rig(Pose(500.0, 0.0, 0.0), dry_run=True)
        try:
            report = await body.move(600, 600, 1.0)
            assert report.dry_run
            await body.drive(500, 500)
            await asyncio.sleep(0.3)
            assert firmware.world.pose.x == 500.0
            assert body.wheel_commands_sent == 0
            assert not any(line.startswith("D ") and line != "D 0 0" for line in server.lines_received)
            assert body.dry_run_requests
        finally:
            await stop_rig(server, body)

    run(scenario())


def test_pings_no_longer_keep_the_wheels_turning():
    async def scenario():
        firmware, server, body = await start_rig(Pose(300.0, 0.0, 0.0))
        events = body.subscribe_events()
        try:
            assert await body.drive(400, 400)
            deadman, seen = await next_event(events, "deadman", 2.0)
            assert deadman is not None, seen
            assert firmware.applied == [0.0, 0.0]
            assert Flags.DEADMAN in firmware.flags()
            await asyncio.sleep(1.2)
            assert body.link.latency_ms is not None
            assert Flags.DEADMAN in firmware.flags()
        finally:
            await stop_rig(server, body)

    run(scenario())


def test_a_live_move_refreshes_its_own_motion():
    async def scenario():
        firmware, server, body = await start_rig(Pose(200.0, 0.0, 0.0))
        try:
            report = await body.move(400, 400, 1.6)
            assert not report.stopped_early, report.events
            assert "deadman" not in report.events
            assert report.seconds >= 1.5
            assert firmware.world.pose.x - 200.0 > 100.0
            await asyncio.sleep(0.8)
            assert "E deadman" not in [line for line in server.lines_received]
            drives = [line for line in server.lines_received if line.startswith("D ")]
            assert len(drives) >= 7 and drives[-1] == "D 0 0"
        finally:
            await stop_rig(server, body)

    run(scenario())


class ThreadedSim:
    def __init__(self, pose: Pose):
        self.firmware = SimFirmware(World(pose=pose))
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.port = 0
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        asyncio.set_event_loop(self.loop)
        server = SimServer(self.firmware, "127.0.0.1", 0)
        self.port = self.loop.run_until_complete(server.start())
        self.ready.set()
        self.loop.run_forever()
        self.loop.run_until_complete(server.stop())
        self.loop.close()

    def __enter__(self) -> "ThreadedSim":
        self.thread.start()
        assert self.ready.wait(5.0)
        return self

    def __exit__(self, *exc) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5.0)


def test_a_stalled_decision_loop_lets_the_deadman_stop_the_wheels():
    with ThreadedSim(Pose(150.0, 0.0, 0.0)) as sim:
        firmware = sim.firmware

        async def scenario():
            link = LinkClient(transport_factory(f"tcp:127.0.0.1:{sim.port}"))
            body = Body(link, FakeClock(), make_profile(), dry_run=False)
            body.start()
            try:
                assert await link.wait_connected(3.0)
                mover = asyncio.create_task(body.move(400, 400, 3.0))
                await asyncio.sleep(0.6)
                assert firmware.applied[0] > 300
                start_x = firmware.world.pose.x
                time.sleep(1.5)
                stalled_x = firmware.world.pose.x
                assert firmware.deadman_active
                assert firmware.applied == [0.0, 0.0]
                assert stalled_x - start_x < 0.6 * 120.0
                time.sleep(0.4)
                assert firmware.world.pose.x == stalled_x
                report = await mover
                assert report.stopped_early and "deadman" in report.events
            finally:
                await body.close()

        run(scenario())


def test_link_reconnects_after_the_body_goes_away():
    async def scenario():
        firmware, server, body = await start_rig(Pose(500.0, 0.0, 0.0))
        port = server.port
        events = body.subscribe_events()
        try:
            await server.stop()
            for _ in range(100):
                if not body.connected:
                    break
                await asyncio.sleep(0.05)
            assert not body.connected
            server = SimServer(firmware, "127.0.0.1", port)
            await server.start()
            assert await body.link.wait_connected(8.0)
            await asyncio.sleep(0.2)
            ups = []
            while not events.empty():
                ups.append(events.get_nowait())
            assert any(isinstance(item, LinkUp) for item in ups)
        finally:
            await stop_rig(server, body)

    run(scenario(), timeout=40)


def test_stop_acks_never_answer_a_settings_request():
    async def scenario():
        firmware, server, body = await start_rig(Pose(500.0, 0.0, 0.0))
        try:
            for _ in range(5):
                await body.stop()
                assert await body.set_setting("edge", 99999) == "range"
                await body.stop()
                assert await body.set_setting("stop", 55) == "ok"
            await body.speed(100, 100)
            assert await body.set_setting("edge", 70) == "ok"
            assert firmware.settings["edge"] == "70"
        finally:
            await stop_rig(server, body)

    run(scenario())


def test_reboot_drops_the_link_and_the_next_connection_gets_boot():
    async def scenario():
        firmware, server, body = await start_rig(Pose(500.0, 0.0, 0.0))
        events = body.subscribe_events()
        try:
            assert await body.reboot()
            boot, seen = await next_event(events, "boot", 8.0)
            assert boot is not None, seen
            assert body.telemetry.boot_version == "sim-0.3"
            assert body.connected
        finally:
            await stop_rig(server, body)

    run(scenario(), timeout=40)


class ScriptedTransport:
    label = "scripted"

    def __init__(self, lines):
        self.lines = list(lines)
        self.written = []

    async def open(self):
        return None

    async def read_line(self):
        if self.lines:
            return self.lines.pop(0)
        await asyncio.sleep(0.05)
        return "S 1 0 0 100 45 0 0 3900 8 0"

    async def write_line(self, line):
        self.written.append(line)

    async def close(self):
        return None


def test_corrupt_lines_are_dropped_and_the_link_carries_on():
    async def scenario():
        transport = ScriptedTransport(["S 12 3 4", "E bu", "#~~ gar bage", "E edge", "S 1 2 3 4 5 6 7 8 9 10 11", "p 3x", "E bump L"])
        link = LinkClient(lambda: transport)
        queue = link.subscribe((Event,))
        link.start()
        try:
            first = await asyncio.wait_for(queue.get(), 2.0)
            second = await asyncio.wait_for(queue.get(), 2.0)
            assert (first.name, second.name) == ("edge", "bump")
            assert link.malformed == 5
            assert link.connected
        finally:
            await link.stop()

    run(scenario())


def test_ble_notifications_are_reassembled_into_lines():
    from pebble.link.ble import BleTransport

    transport = BleTransport()
    transport._queue = asyncio.Queue()
    newline = bytes([10])
    chunks = (b"S 1 2 3 4 5 0 0 39", b"00 8 0" + newline + b"E ed", b"ge" + bytes([13]) + newline + b"E bu", b"mp L" + newline)
    for chunk in chunks:
        transport._on_notify(None, bytearray(chunk))
    lines = [transport._queue.get_nowait() for _ in range(transport._queue.qsize())]
    assert lines == ["S 1 2 3 4 5 0 0 3900 8 0", "E edge", "E bump L"]
    transport._on_notify(None, bytearray(b"x" * 600))
    assert len(transport._buffer) == 0
