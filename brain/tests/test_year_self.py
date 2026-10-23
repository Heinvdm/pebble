import asyncio

import pytest

from pebble.mind.budget import budgets
from pebble.sim.year_self import MEMORIES, WINDOWS, run

PER_CALL = ("people", "task", "board", "matched", "words")


@pytest.fixture(scope="module")
def report():
    return asyncio.run(run(None, False, MEMORIES, ""))


def test_the_year_old_self_is_as_full_as_a_busy_year(report):
    counts = report["counts"]
    assert counts["people"] == 60 and counts["rooms"] + counts["spots"] == 80 and counts["things"] == 800
    assert counts["skills"] == 200 and counts["scripts"] == 40 and counts["lessons"] == 400
    assert counts["rules"] == 30 and counts["sounds"] == 20 and counts["agenda"] == 150
    assert counts["memories"] == 100_000 and counts["notes_chars"] >= 1100


def test_every_call_keeps_its_sections_in_budget_and_fits_the_window(report):
    for window in WINDOWS:
        assert report["passed"][f"sections_{window}"] and report["passed"][f"window_{window}"]
        for name, data in report["year"][window].items():
            if name == "share":
                continue
            table = budgets(data["kind"], window)
            for section in PER_CALL:
                if section in table and section != "words":
                    assert data["rows"].get(section, 0) <= table[section], (window, name, section)


def test_history_and_the_task_keep_their_room_after_a_year(report):
    for window in WINDOWS:
        assert report["year"][window]["share"]["of_ceiling"] >= 0.45
    assert report["year"][8192]["share"]["of_window"] >= 0.45


def test_the_right_item_is_found_on_the_hundred_questions(report):
    assert report["finding"]["of"] == 100 and report["finding"]["right"] >= 95


def test_a_reply_after_read_ahead_reads_no_more_than_a_new_self_does(report):
    assert report["passed"]["speed"]
    assert report["year_fresh"]["mean"] <= report["new_fresh"]["mean"] * 1.1


def test_the_naming_scan_costs_microseconds(report):
    assert report["scan"]["names"] >= 1000 and report["scan"]["mean_us"] < 1000


def test_the_how_to_book_is_found_by_name_and_by_what_it_does_after_a_year(report):
    assert report["counts"]["howto"] == 200
    taught = report["howto_finding"]
    assert taught["howto_by_name"] == [20, 20]
    assert taught["howto_by_description"][1] == 20 and taught["howto_by_description"][0] >= 18
    assert report["passed"]["howto_by_name"] and report["passed"]["howto_by_description"]
    for window in WINDOWS:
        call = report["year"][window]["teach: work out"]
        assert call["fits"] and not call["guard"]["refused"]
