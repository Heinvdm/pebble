import re

from pebble.status import Snapshot, format_status

PATTERN = re.compile(
    r"^battery (\d+%( charging| draining)?|n/a), pack (\d\.\d\dV|n/a), (docked|off dock|dock \?), "
    r"tilt (-?\d+deg|n/a), light (dark|dim|indoor|bright|sunny|n/a), phone (\d+C|n/a), "
    r"(moved \d+ (s|min|h|days) ago|no motion yet)(, body link down)?"
    r" \| needs: ([a-z0-9 ]+|n/a) \| mood: [a-z ,]+ \| fear \d+/10 [a-z]+ \| task: .+ \| age: \d+ days \([a-z]+\) \| state: [a-z]+"
    r"( \| today: .+)?( \| soon: .+)?$"
)


def full() -> Snapshot:
    return Snapshot(
        battery_pct=62.4,
        battery_trend="draining",
        pack_mv=3850,
        docked=False,
        tilt_deg=8.2,
        light_lux=40.0,
        temperature_c=38.4,
        last_motion_s=125.0,
        needs={"energy": 62, "curiosity": 40, "social": 70, "rest": 20},
        mood="good, calm",
        fear=1.2,
        fear_label="calm",
        task="explore the hallway",
        age_days=47,
        stage="teen",
        today=("Ada Lovelace Day",),
        soon=(("R.U.R. Day", 3), ("Turing's birthday", 1)),
        state="active",
    )


def test_full_status_line():
    line = format_status(full())
    assert PATTERN.match(line), line
    assert line == (
        "battery 62% draining, pack 3.85V, off dock, tilt 8deg, light dim, phone 38C, moved 2 min ago"
        " | needs: energy 62 curiosity 40 social 70 rest 20 | mood: good, calm | fear 1/10 calm"
        " | task: explore the hallway | age: 47 days (teen) | state: active"
        " | today: Ada Lovelace Day | soon: R.U.R. Day in 3 days; Turing's birthday in 1 day"
    )


def test_unknown_values_read_as_not_available():
    line = format_status(Snapshot(link_up=False))
    assert PATTERN.match(line), line
    assert line.startswith("battery n/a, pack n/a, dock ?, tilt n/a, light n/a, phone n/a, no motion yet, body link down")
    assert "task: none" in line
    assert "today:" not in line and "soon:" not in line


def test_status_line_is_one_ascii_line():
    line = format_status(full())
    assert "\n" not in line
    assert line.isascii()
    assert len(line) < 400


def test_motion_wording():
    assert "moved 5 s ago" in format_status(Snapshot(last_motion_s=5))
    assert "moved 3 h ago" in format_status(Snapshot(last_motion_s=3 * 3600 + 5))
    assert "moved 3 days ago" in format_status(Snapshot(last_motion_s=3 * 86400))
