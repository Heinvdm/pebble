import pytest

from pebble.link.protocol import (
    MAX_LINE,
    Drive,
    Event,
    Flags,
    Ok,
    Ping,
    ProtocolError,
    SetSetting,
    Status,
    format_command,
    format_message,
    parse_command,
    parse_message,
)

COMMANDS = [
    "D 0 0",
    "D -1000 1000",
    "D 250 -250",
    "M 120 -80",
    "T 8",
    "T -35",
    "X",
    "P 0",
    "P 42",
    "Q",
    "C edge 75",
    "C cpm 20.7",
    "C ssid My Home WiFi",
    "C pass -",
    "C edge",
    "C ?",
    "R",
]

MESSAGES = [
    "S 123 10 -4 250 45 0 1 3950 8 0",
    "S 0 0 0 -1 -1 3 0 0 -35 127",
    "S 4294967295 -2147483648 2147483647 8190 8190 1 1 4200 90 64",
    "E boot sim-0.1",
    "E boot pebble 1.2.3",
    "E bump L",
    "E bump R",
    "E bump B",
    "E edge",
    "E obstacle 45",
    "E stall L",
    "E stall R",
    "E dock 1",
    "E dock 0",
    "E lowbat 3290",
    "E deadman",
    "E fault vl53 front",
    "p 7",
    "c edge 75",
    "c ssid My Home WiFi",
    "c pass",
    "ok",
    "err M cpm",
    "err C key",
    "err ? unknown",
    "err D long",
]

MALFORMED_MESSAGES = [
    "",
    "   ",
    "S 1 2 3",
    "S 1 2 3 4 5 6 7 8 9 x",
    "S 1 2 3 4 5 0 0 3900 8",
    "S 1 2 3 4 5 9 0 3900 8 0",
    "S 1 2 3 4 5 0 2 3900 8 0",
    "S -1 0 0 0 0 0 0 0 0 0",
    "S 1 0 0 -2 0 0 0 0 0 0",
    "S 1 0 0 0 0 0 0 -5 0 0",
    "E",
    "E bump X",
    "E bump",
    "E edge now",
    "E obstacle near",
    "E stall B",
    "E dock yes",
    "E lowbat",
    "E boot",
    "E Bad-Name",
    "p",
    "p x",
    "ok then",
    "Z 1",
    "hello world",
    "S " + "1 " * 60,
    "E boot café",
    "c",
    "err cpm",
    "err Z key",
    "err C nonsense",
    "err C key extra",
    "err",
]

MALFORMED_COMMANDS = [
    "D 1",
    "D a b",
    "D 1 2 3",
    "D 1.5 2",
    "M 1",
    "T",
    "T up",
    "X 1",
    "P -1",
    "P",
    "C",
    "C speed 3",
    "C edge far",
    "C bogus",
    "Q now",
    "R 1",
    "hello",
    "",
]


@pytest.mark.parametrize("line", COMMANDS)
def test_command_round_trip(line):
    assert format_command(parse_command(line)) == line


@pytest.mark.parametrize("line", MESSAGES)
def test_message_round_trip(line):
    assert format_message(parse_message(line)) == line


@pytest.mark.parametrize("line", MALFORMED_MESSAGES)
def test_malformed_messages_raise(line):
    with pytest.raises(ProtocolError):
        parse_message(line)


@pytest.mark.parametrize("line", MALFORMED_COMMANDS)
def test_malformed_commands_raise(line):
    with pytest.raises(ProtocolError):
        parse_command(line)


def test_status_fields_and_flags():
    status = parse_message("S 123 10 -4 250 45 2 1 3950 8 21")
    assert isinstance(status, Status)
    assert (status.ms, status.enc_left, status.enc_right) == (123, 10, -4)
    assert (status.front_mm, status.down_mm, status.bump, status.dock, status.pack_mv) == (250, 45, 2, 1, 3950)
    assert status.tilt == 8
    assert Flags.EDGE_HOLD in status.flags
    assert Flags.OBSTACLE in status.flags
    assert Flags.LOW_BATTERY in status.flags
    assert Flags.BUMP_HOLD not in status.flags


def test_line_endings_and_spacing_are_tolerated():
    assert parse_message("ok\r\n") == Ok()
    assert parse_message("  E   bump   L  ") == Event("bump", ("L",))
    assert parse_command("P 5\n") == Ping(5)


def test_setting_values_keep_inner_spaces():
    assert parse_command("C ssid  My  Home ") == SetSetting("ssid", "My  Home")


def test_unknown_and_truncated_events_are_discarded():
    for line in ("E purr 3", "E bu", "E edg", "E dock"):
        with pytest.raises(ProtocolError):
            parse_message(line)


def test_line_length_limit():
    longest = "C ssid " + "a" * (MAX_LINE - 7)
    assert len(longest) == MAX_LINE
    assert parse_command(longest) == SetSetting("ssid", "a" * (MAX_LINE - 7))
    with pytest.raises(ProtocolError):
        parse_command(longest + "a")
    with pytest.raises(ProtocolError):
        format_command(SetSetting("ssid", "a" * MAX_LINE))


def test_format_refuses_bad_commands():
    with pytest.raises(ProtocolError):
        format_command(Drive(1001, 0))
    with pytest.raises(ProtocolError):
        format_command(SetSetting("bogus", "1"))
    with pytest.raises(ProtocolError):
        format_command(SetSetting("edge", "far"))
    with pytest.raises(ProtocolError):
        format_command(SetSetting("ssid", "line\nbreak"))
    with pytest.raises(ProtocolError):
        format_command(Ping(-1))
    with pytest.raises(ProtocolError):
        format_message(Event("bump", ("X",)))


def test_tilt_is_sent_as_whole_degrees():
    from pebble.link.protocol import Tilt

    assert format_command(Tilt(12.6)) == "T 13"
    assert parse_command("T 12.5") == Tilt(12.5)


@pytest.mark.parametrize(
    "line,letter,reason",
    [
        ("Z 1", "?", "unknown"),
        ("d 1 2", "?", "unknown"),
        ("DD 1", "?", "unknown"),
        ("hello", "?", "unknown"),
        ("D a b", "D", "syntax"),
        ("D 1", "D", "syntax"),
        ("X 1", "X", "syntax"),
        ("C speed 3", "C", "key"),
        ("C bogus", "C", "key"),
        ("C edge far", "C", "value"),
        ("C ssid " + "a" * 95, "C", "long"),
        ("D " + "1" * 100, "D", "long"),
        ("Z" + "x" * 100, "?", "long"),
    ],
)
def test_parse_errors_carry_the_firmware_letter_and_reason(line, letter, reason):
    with pytest.raises(ProtocolError) as caught:
        parse_command(line)
    assert (caught.value.command, caught.value.reason) == (letter, reason)


def test_reply_contract_per_command():
    from pebble.link.protocol import GetSetting, ListSettings, Query, Reboot, Stop, letter_of, reply_kind

    assert [reply_kind(c) for c in (Drive(1, 1), Stop(), SetSetting("edge", "70"), GetSetting("edge"), ListSettings(), Reboot(), Ping(1), Query())] == [
        None, "ok", "ok", "get", "list", "ok", None, None,
    ]
    assert [letter_of(c) for c in (Drive(1, 1), Stop(), GetSetting("edge"), Reboot())] == ["D", "X", "C", "R"]


def test_reading_one_setting_and_clearing_text_settings():
    from pebble.link.protocol import GetSetting, setting_from_wire, setting_text

    assert parse_command("C stop") == GetSetting("stop")
    assert format_command(GetSetting("stop")) == "C stop"
    assert setting_text("pass", "") == "-"
    assert setting_text("edge", " 70 ") == "70"
    assert setting_from_wire("ssid", "-") == ""
    assert setting_from_wire("edge", "-") == "-"
    with pytest.raises(ProtocolError):
        format_command(SetSetting("pass", ""))
