import math

from pebble.link.protocol import Flags, parse_message
from pebble.sim.firmware import SimFirmware
from pebble.sim.world import Pose, World


def make(pose=Pose(500.0, 0.0, 0.0), **kwargs) -> SimFirmware:
    firmware = SimFirmware(World(pose=pose), **kwargs)
    firmware.connected()
    return firmware


def advance(firmware: SimFirmware, seconds: float, motion: str | None = None, ping: bool = True) -> list[str]:
    events = []
    for index in range(int(round(seconds / 0.01))):
        if index % 20 == 0:
            if motion:
                firmware.receive(motion)
            if ping:
                firmware.receive("P 1")
        events.extend(line for line in firmware.step(0.01) if not line.startswith(("S ", "A ")))
    return events


def test_status_line_every_50_ms_parses():
    firmware = make()
    lines = []
    for _ in range(20):
        lines.extend(line for line in firmware.step(0.01) if line.startswith("S "))
    assert 3 <= len(lines) <= 5
    status = parse_message(lines[-1])
    assert status.down_mm == 45 and status.pack_mv > 3900


def test_replies_follow_the_as_built_firmware():
    firmware = make()
    assert firmware.receive("D 400 400") == []
    assert firmware.receive("D 5000 -5000") == []
    assert firmware.command == [1000, -1000]
    assert firmware.receive("T 200") == []
    assert firmware.tilt_target == 90
    assert firmware.receive("X") == ["ok"]
    assert firmware.receive("M 100 100") == ["err M cpm"]
    assert firmware.receive("Z") == ["err ? unknown"]
    assert firmware.receive("d 1 2") == ["err ? unknown"]
    assert firmware.receive("D a b") == ["err D syntax"]
    assert firmware.receive("C bogus 1") == ["err C key"]
    assert firmware.receive("C bogus") == ["err C key"]
    assert firmware.receive("C edge far") == ["err C value"]
    assert firmware.receive("C edge 99999") == ["err C range"]
    assert firmware.receive("C tmin 95") == ["err C range"]
    assert firmware.receive("C " + "x" * 120) == ["err C long"]
    assert firmware.receive("R" + "x" * 120) == ["err R long"]
    assert firmware.receive("") == []
    assert firmware.receive("C stop 40") == ["ok"]
    assert firmware.receive("C stop") == ["c stop 40"]


def test_settings_list_is_nine_keys_in_order_then_ok():
    firmware = make()
    listing = firmware.receive("C ?")
    assert [line.split()[1] for line in listing[:-1]] == ["ssid", "pass", "cpm", "edge", "stop", "tmin", "tmax", "trim", "rest"]
    assert listing[-1] == "ok"
    assert listing[0] == "c ssid -" and listing[1] == "c pass -"
    firmware.receive("C pass hunter2")
    firmware.receive("C ssid Home Net")
    listing = firmware.receive("C ?")
    assert listing[0] == "c ssid Home Net" and listing[1] == "c pass *"
    assert firmware.receive("C pass") == ["c pass *"]
    assert firmware.receive("C ssid -") == ["ok"]
    assert firmware.settings["ssid"] == ""


def test_boot_is_sent_on_the_first_connection_only():
    firmware = SimFirmware(World())
    assert firmware.connected() == ["E boot sim-0.3"]
    assert firmware.connected() == []
    assert firmware.receive("R") == ["ok"]
    assert firmware.reboot_requested
    assert firmware.connected() == ["E boot sim-0.3"]


def test_only_accepted_motion_commands_hold_off_the_deadman():
    firmware = make()
    firmware.receive("D 400 400")
    events = advance(firmware, 1.5, motion=None, ping=True)
    assert events.count("E deadman") == 1
    assert firmware.applied == [0.0, 0.0]
    assert Flags.DEADMAN in firmware.flags()
    for line in ("P 1", "Q", "T 20", "C edge 70", "M 100 100", "Z"):
        firmware.receive(line)
    assert Flags.DEADMAN in firmware.flags()
    firmware.receive("X")
    assert Flags.DEADMAN not in firmware.flags()
    events = advance(firmware, 1.5, motion="D 400 400")
    assert "E deadman" not in events
    assert firmware.applied[0] > 300


def test_refused_speed_commands_do_not_refresh_the_deadman():
    firmware = make()
    firmware.receive("D 400 400")
    events = advance(firmware, 1.0, motion="M 100 100")
    assert "E deadman" in events


def test_no_deadman_event_when_nothing_was_asking_for_motion():
    firmware = make()
    firmware.receive("D 0 0")
    assert advance(firmware, 1.0) == []
    assert Flags.DEADMAN not in firmware.flags()


def test_forward_refused_clamps_only_the_forward_part():
    firmware = make(Pose(880.0, 0.0, 0.0))
    events = advance(firmware, 2.0, motion="D 500 500")
    assert "E edge" in events and firmware.edge_hold
    x = firmware.world.pose.x
    advance(firmware, 0.5, motion="D 500 500")
    assert abs(firmware.world.pose.x - x) < 0.5
    heading = firmware.world.pose.heading
    advance(firmware, 0.5, motion="D 600 200")
    assert firmware.world.pose.heading < heading
    assert firmware.edge_hold
    assert not firmware.world.fallen


def test_safety_stop_cuts_power_instantly():
    firmware = make(Pose(200.0, 0.0, math.pi))
    firmware.receive("C stop 150")
    for index in range(60):
        if index % 20 == 0:
            firmware.receive("D 600 600")
        firmware.step(0.01)
        if firmware.obstacle_close():
            break
    assert firmware.obstacle_close()
    firmware.step(0.01)
    assert firmware.applied[0] + firmware.applied[1] <= 0


def test_stalled_wheel_stops_and_reports():
    firmware = make()
    firmware.world.jam[0] = True
    events = advance(firmware, 1.0, motion="D 600 600")
    assert "E stall L" in events


def test_low_pack_warns_caps_and_clears_with_hysteresis():
    firmware = make(pack_mv=3290.0, drain_mv_per_s=0.0, load_mv_per_s=0.0)
    events = advance(firmware, 5.5, motion="D 1000 1000")
    assert "E lowbat 3290" in events
    advance(firmware, 0.5, motion="D 1000 1000")
    assert max(abs(v) for v in firmware.applied) <= 500
    firmware.pack_mv = 3420.0
    advance(firmware, 3.0)
    assert firmware.lowbat_sent
    advance(firmware, 2.5)
    assert not firmware.lowbat_sent


def test_cutoff_refuses_wheels_until_the_pack_recovers():
    firmware = make(pack_mv=3050.0, drain_mv_per_s=0.0, load_mv_per_s=0.0)
    advance(firmware, 0.5, motion="D 600 600")
    assert firmware.applied == [0.0, 0.0] and firmware.cutoff
    firmware.pack_mv = 3150.0
    advance(firmware, 3.0)
    assert firmware.cutoff
    firmware.pack_mv = 3250.0
    advance(firmware, 1.0)
    assert firmware.cutoff
    advance(firmware, 1.5)
    assert not firmware.cutoff


def test_a_sensor_fault_refuses_the_wheels_until_it_recovers():
    firmware = make()
    firmware.set_fault("front")
    events = advance(firmware, 0.5, motion="D 600 600")
    assert events == ["E fault front"]
    assert firmware.applied == [0.0, 0.0]
    assert Flags.SENSOR_FAULT in firmware.flags()
    firmware.set_fault("front", False)
    advance(firmware, 0.5, motion="D 600 600")
    assert firmware.applied[0] > 0
    assert Flags.SENSOR_FAULT not in firmware.flags()


def test_tilt_slews_clamps_and_ignores_the_deadman():
    firmware = make()
    firmware.receive("T 90")
    advance(firmware, 0.5)
    assert 60 <= firmware.tilt <= 70
    advance(firmware, 0.5)
    assert firmware.tilt == 90
    firmware.receive("C tmax 30")
    firmware.receive("T 90")
    advance(firmware, 1.0)
    assert firmware.tilt == 30


def test_obstacle_clamps_forward_but_allows_turning():
    firmware = make(Pose(200.0, 0.0, math.pi))
    events = advance(firmware, 3.0, motion="D 400 400")
    assert any(e.startswith("E obstacle") for e in events)
    assert not any(e.startswith("E bump") for e in events)
    assert 0 <= firmware.world.front_mm() < 60
    heading = firmware.world.pose.heading
    advance(firmware, 0.5, motion="D -300 300")
    assert firmware.world.pose.heading != heading


def test_speed_mode_needs_calibration():
    firmware = make()
    assert firmware.receive("M 100 100") == ["err M cpm"]
    assert firmware.receive("C cpm 20.7") == ["ok"]
    assert firmware.receive("M 100 100") == []
    start = firmware.world.pose.x
    advance(firmware, 1.0, motion="M 100 100")
    assert 60 <= firmware.world.pose.x - start <= 140


def test_reversing_onto_the_dock_reports_docked():
    firmware = make(Pose(150.0, 0.0, 0.0))
    events = advance(firmware, 3.0, motion="D -400 -400")
    assert "E dock 1" in events
    assert firmware.world.docked()


def test_driving_at_a_side_edge_is_caught_by_the_drop_sensor():
    firmware = make(Pose(500.0, -300.0, -math.pi / 2))
    events = advance(firmware, 3.0, motion="D 500 500")
    assert "E edge" in events
    assert not firmware.world.fallen
