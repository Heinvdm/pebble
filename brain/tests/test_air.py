import asyncio

import pytest
from conftest import make_profile, run

from pebble.body import AIR_WARMUP_S, AirReading
from pebble.body.api import Body
from pebble.body.telemetry import Telemetry
from pebble.clock import FakeClock
from pebble.link.client import LinkClient
from pebble.link.protocol import AIR_VERSION, Air, ProtocolError, Status, format_message, parse_message
from pebble.sim.firmware import AIR_PERIOD_MS, SimFirmware

AIR_LINES = [
    "A 1 123456 21.53 45.2 101325 152340 412",
    "A 1 7 -4 50 101325 -1 0",
    "A 1 4294967295 -39.99 99.99 110000 102400000 4294967",
    "A 1 5000 none",
]

BAD_AIR_LINES = [
    "A",
    "A 1",
    "A 1 5",
    "A 1 5 21 40",
    "A 1 5 21 40 101325 1000",
    "A x 5 none",
    "A 1 -5 none",
    "A 1 5 hot 40 101325 1000 3",
    "A 1 5 21 140 101325 1000 3",
    "A 1 5 21 40 0 1000 3",
    "A 1 5 21 40 101325 -2 3",
    "A 1 5 21 40 101325 1000 -3",
    "A 1 5 21 40 1013.25 1000 3",
]


@pytest.mark.parametrize("line", AIR_LINES)
def test_air_line_round_trip(line):
    message = parse_message(line)
    assert isinstance(message, Air)
    assert format_message(message) == line


@pytest.mark.parametrize("line", BAD_AIR_LINES)
def test_bad_air_lines_raise(line):
    with pytest.raises(ProtocolError):
        parse_message(line)


def test_air_fields():
    air = parse_message("A 1 123456 21.53 45.2 101325 152340 412")
    assert (air.version, air.ms, air.present) == (AIR_VERSION, 123456, True)
    assert air.temperature_c == pytest.approx(21.53)
    assert air.humidity_pct == pytest.approx(45.2)
    assert (air.pressure_pa, air.gas_ohm, air.heated_s) == (101325, 152340, 412)
    unsettled = parse_message("A 1 7 -4 50 101325 -1 0")
    assert unsettled.present and unsettled.gas_ohm is None and unsettled.temperature_c == -4.0
    none = parse_message("A 1 5000 none")
    assert not none.present and none.ms == 5000 and none.temperature_c is None


def test_a_newer_version_is_skipped_and_extra_fields_are_ignored():
    with pytest.raises(ProtocolError) as raised:
        parse_message("A 2 5000 21.5 45 101325 1000 3")
    assert raised.value.reason == "unknown"
    longer = parse_message("A 1 5000 21.5 45 101325 1000 3 99 extra")
    assert longer == Air(5000, 21.5, 45.0, 101325, 1000, 3)
    assert parse_message("A 1 5000 none later fields") == Air(5000)


def test_formatting_refuses_half_a_reading():
    with pytest.raises(ProtocolError):
        format_message(Air(5, temperature_c=21.0))
    with pytest.raises(ProtocolError):
        format_message(Air(5, version=2))
    assert format_message(Air(5, 21.004, 45.006, 101325, None, 0)) == "A 1 5 21 45.01 101325 -1 0"
    assert format_message(Air(5, -0.001, 0.0, 101325, 7, 0)) == "A 1 5 0 0 101325 7 0"


def test_the_status_line_is_unchanged():
    status = parse_message("S 123 10 -4 250 45 0 1 3950 8 0")
    assert isinstance(status, Status)
    with pytest.raises(ProtocolError):
        parse_message("S 123 10 -4 250 45 0 1 3950 8 0 A 1 5000 none")


def test_telemetry_keeps_the_latest_air_reading():
    telemetry = Telemetry()
    assert telemetry.air is None and telemetry.air_reading(100.0) is None
    assert telemetry.air_snapshot(100.0) is None
    reading = telemetry.apply_air(parse_message("A 1 6000 21.53 45.2 101325 152340 12"), 100.0)
    assert isinstance(reading, AirReading)
    assert telemetry.air is reading
    assert reading.present and reading.warming and reading.body_ms == 6000
    assert reading.pressure_hpa == pytest.approx(1013.25)
    assert telemetry.air_reading(105.0) is reading
    assert telemetry.air_reading(105.0, max_age=10.0) is reading
    assert telemetry.air_reading(111.0, max_age=10.0) is None
    assert telemetry.air_snapshot(103.0) == {
        "temperature_c": 21.5,
        "humidity_pct": 45.2,
        "pressure_hpa": 1013.2,
        "gas_kohm": 152.3,
        "warming_up": True,
        "age_s": 3.0,
    }
    settled = telemetry.apply_air(parse_message(f"A 1 9000 21.5 45 101325 -1 {AIR_WARMUP_S}"), 110.0)
    assert not settled.warming and settled.gas_ohm is None
    assert telemetry.air_snapshot(110.0)["gas_kohm"] is None
    telemetry.apply_air(parse_message("A 1 12000 none"), 113.0)
    assert telemetry.air is not None and not telemetry.air.present
    assert telemetry.air_reading(113.0) is None
    assert telemetry.air_snapshot(113.0) == "no air sensor"


def test_the_body_snapshot_carries_the_air():
    telemetry = Telemetry()
    assert telemetry.snapshot(1.0)["air"] is None
    telemetry.apply_status(parse_message("S 123 10 -4 250 45 0 1 3950 8 0"), 1.0)
    telemetry.apply_air(parse_message("A 1 5000 none"), 1.0)
    snapshot = telemetry.snapshot(2.0)
    assert snapshot["air"] == "no air sensor"
    assert snapshot["front_mm"] == 250


class ScriptedTransport:
    label = "scripted"

    def __init__(self, lines):
        self.lines = list(lines)

    async def open(self):
        return None

    async def read_line(self):
        if self.lines:
            return self.lines.pop(0)
        await asyncio.sleep(0.05)
        return "S 1 0 0 100 45 0 0 3900 8 0"

    async def write_line(self, line):
        return None

    async def close(self):
        return None


def test_the_body_files_air_lines_into_its_telemetry():
    async def scenario():
        transport = ScriptedTransport(["S 1 0 0 100 45 0 0 3900 8 0", "A 1 3000 22.25 51 100900 98000 3", "E edge"])
        link = LinkClient(lambda: transport)
        clock = FakeClock()
        body = Body(link, clock, make_profile(), dry_run=True)
        events = body.subscribe_events()
        body.start()
        try:
            for _ in range(100):
                if body.telemetry.air is not None:
                    break
                await asyncio.sleep(0.02)
            air = body.telemetry.air
            assert air is not None and air.present
            assert (air.temperature_c, air.humidity_pct, air.pressure_pa, air.gas_ohm, air.heated_s) == (22.25, 51.0, 100900, 98000, 3)
            assert air.at == clock.now()
            assert link.malformed == 0
            seen = []
            while not events.empty():
                seen.append(events.get_nowait())
            assert not any(isinstance(item, Air) for item in seen)
        finally:
            await body.close()

    run(scenario())


def test_the_sim_sends_an_air_line_every_three_seconds():
    firmware = SimFirmware()
    firmware.connected()
    lines = []
    for _ in range(int(round(2 * AIR_PERIOD_MS / 10.0)) + 1):
        lines.extend(line for line in firmware.step(0.01) if line.startswith("A "))
    assert len(lines) == 2
    first, second = (parse_message(line) for line in lines)
    assert first.present and first.gas_ohm == 120000 and first.heated_s == 3
    assert second.ms - first.ms == pytest.approx(AIR_PERIOD_MS, abs=10)
    firmware.set_air(None)
    assert parse_message(firmware.air_line()) == Air(int(firmware.ms))
    firmware.set_air({"gas_ohm": 30000, "temperature_c": 24.0})
    back = parse_message(firmware.air_line())
    assert back.present and back.gas_ohm == 30000 and back.temperature_c == 24.0 and back.heated_s == 0
    firmware.set_air({"gas_ohm": None})
    assert parse_message(firmware.air_line()).gas_ohm is None


def test_a_sim_reboot_restarts_the_warm_up_clock():
    firmware = SimFirmware()
    firmware.connected()
    for _ in range(1000):
        firmware.step(0.01)
    assert parse_message(firmware.air_line()).heated_s == 10
    firmware.receive("R")
    firmware.step(0.01)
    assert parse_message(firmware.air_line()).heated_s == 0
